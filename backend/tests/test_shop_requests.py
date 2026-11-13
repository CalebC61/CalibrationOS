"""A public shop request is what the owner sees on /requests.

    cd backend && pytest tests/test_shop_requests.py -v
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402


def _match(doc, query):
    for key, expected in query.items():
        if doc.get(key) != expected:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, n):
        return self.docs[:n]


class _Store:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return {k: v for k, v in doc.items() if k != "_id"}
        return None

    def find(self, query, projection=None):
        return _Cursor([
            {k: v for k, v in doc.items() if k != "_id"}
            for doc in self.docs if _match(doc, query)
        ])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class _DB:
    def __init__(self):
        self.shop_requests = _Store()


def test_submitted_request_shows_in_the_owner_list(monkeypatch):
    db = _DB()
    formatted = "1 E Main St, Gilbert, AZ 85234"

    async def geo(address):
        return {
            "lat": 33.352826, "lng": -111.789027,
            "formatted_address": formatted,
            "in_metro": True, "fallback": False, "source": "google",
        }

    sent = []

    async def fake_send(to, subject, html, kind="transactional", meta=None, reply_to=None):
        sent.append({"to": to, "subject": subject, "kind": kind})
        return {"delivered": True}

    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "geocode_address", geo)
    monkeypatch.setattr(server, "send_email", fake_send)

    async def run():
        older = {
            "id": "older", "shop_name": "Older Glass", "contact_name": "Bo",
            "mobile": "+14805550199", "email": "bo@older.test",
            "address": formatted, "status": "pending",
            "created_at": "2026-11-01T00:00:00+00:00",
        }
        await db.shop_requests.insert_one(older)
        body = server.ShopRequestIn(
            shop_name="TEST Jarvis Signup Shop",
            contact_name="Ada Glass",
            mobile="4805550100",
            email="Ada@example.com",
            address="1 E Main St, Gilbert, AZ",
            address_confirmed=True,
            confirmed_address=formatted,
        )
        created = await server.create_shop_request(body)
        assert created["ok"] is True
        assert sent and sent[0]["kind"] == "shop_request"
        assert "TEST Jarvis Signup Shop" in sent[0]["subject"]
        rows = await server.list_shop_requests(tech={"id": "owner", "role": "owner"})
        assert [row["shop_name"] for row in rows] == ["TEST Jarvis Signup Shop", "Older Glass"]
        fresh = rows[0]
        assert fresh["status"] == "pending"
        assert fresh["email"] == "ada@example.com"
        assert fresh["contact_name"] == "Ada Glass"
        assert fresh["address"] == formatted

    asyncio.run(run())
