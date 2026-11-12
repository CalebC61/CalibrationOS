"""Route wiring for a refused geocode and a one-tap owner link.

    cd backend && pytest tests/test_p0_guards.py -v
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from address_pin import ADDRESS_NOT_FOUND  # noqa: E402
from google_maps import GoogleMapsError  # noqa: E402
from owner_links import mint_owner_link  # noqa: E402


def _match(doc, query):
    for key, expected in query.items():
        value = doc.get(key)
        if isinstance(expected, dict):
            if "$nin" in expected and value in expected["$nin"]:
                return False
            if "$gte" in expected and not (value is not None and value >= expected["$gte"]):
                return False
            if "$lt" in expected and not (value is not None and value < expected["$lt"]):
                return False
        elif value != expected:
            return False
    return True


class _Store:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return {k: v for k, v in doc.items() if k != "_id"}
        return None

    def find(self, query, projection=None):
        return self

    async def to_list(self, n):
        return list(self.docs)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _match(doc, query):
                doc.update(update.get("$set", {}))
                return
        if upsert:
            self.docs.append(dict(update.get("$set", {})))

    async def count_documents(self, query):
        return len([doc for doc in self.docs if _match(doc, query)])


class _DB:
    def __init__(self):
        self.technicians = _Store()
        self.shops = _Store()
        self.jobs = _Store()
        self.owner_action_tokens = _Store()


def test_creating_a_shop_refuses_a_failed_geocode(monkeypatch):
    db = _DB()
    db.technicians.docs.append({"id": "caleb", "role": "owner", "name": "Caleb"})
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "google_maps_enabled", lambda: True)

    def boom(address):
        raise GoogleMapsError("ZERO_RESULTS")

    monkeypatch.setattr(server, "_google_geocode_request", boom)
    owner = server.make_token("caleb", "owner")

    async def run():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/shops",
                headers={"Authorization": f"Bearer {owner}"},
                json={"name": "Glass Co", "address": "not a real place"},
            )
        assert response.status_code == 400
        assert response.json()["detail"] == ADDRESS_NOT_FOUND
        assert db.shops.docs == []

    asyncio.run(run())


def test_approve_link_previews_then_works_once(monkeypatch):
    db = _DB()
    db.jobs.docs.append({
        "id": "job-1",
        "shop_id": "shop-1",
        "shop_name": "Preferred",
        "status": "requested",
        "scheduled_start": "2026-11-13T14:00:00+00:00",
        "job_address": "Surprise, AZ",
        "vehicle_year": 2022,
        "vehicle_make": "Honda",
        "vehicle_model": "Civic",
        "calibration_label": "Static ADAS Calibration",
        "price": 125,
        "notification_email": "shop@glass.example",
    })
    now = datetime(2026, 11, 12, 17, 0, tzinfo=timezone.utc)
    minted = mint_owner_link(secret=server.JWT_SECRET, job_id="job-1", action="approve", now=now)
    db.owner_action_tokens.docs.append(dict(minted["record"]))
    emails = []

    async def record_email(*args, **kwargs):
        emails.append(args)

    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "send_email", record_email)
    monkeypatch.setattr(server, "now_utc", lambda: now)

    async def run():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            preview = await client.get(f"/api/public/owner-action/{minted['token']}")
            assert preview.status_code == 200, preview.text
            assert preview.json()["requires_confirm"] is True
            assert preview.json()["action"] == "approve"
            assert db.jobs.docs[0]["status"] == "requested"
            assert db.owner_action_tokens.docs[0]["used_at"] is None
            assert emails == []
            confirmed = await client.post(f"/api/public/owner-action/{minted['token']}")
            assert confirmed.status_code == 200, confirmed.text
            assert confirmed.json()["job"]["status"] == "booked"
            assert db.owner_action_tokens.docs[0]["used_at"]
            assert emails and "shop@glass.example" in emails[0]
            again = await client.post(f"/api/public/owner-action/{minted['token']}")
            assert again.status_code == 400
            assert "already used" in again.json()["detail"].lower()

    asyncio.run(run())


def test_a_tampered_approve_link_does_not_change_the_job(monkeypatch):
    db = _DB()
    db.jobs.docs.append({"id": "job-1", "status": "requested", "shop_name": "Preferred"})
    now = datetime(2026, 11, 12, 17, 0, tzinfo=timezone.utc)
    minted = mint_owner_link(secret=server.JWT_SECRET, job_id="job-1", action="approve", now=now)
    db.owner_action_tokens.docs.append(dict(minted["record"]))
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "now_utc", lambda: now + timedelta(minutes=1))
    token = minted["token"]
    bad = ("A" if token[0] != "A" else "B") + token[1:]

    async def run():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(f"/api/public/owner-action/{bad}")
        assert response.status_code == 400
        assert db.jobs.docs[0]["status"] == "requested"
        assert db.owner_action_tokens.docs[0]["used_at"] is None

    asyncio.run(run())
