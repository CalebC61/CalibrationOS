"""Owner lists still return rows when a server-side sort would return none.

A sorted find can follow an index and omit every document that is not in it.
These fakes do that: calling sort() empties the cursor. The owner reads must
not call it.

    cd backend && pytest tests/test_owner_lists.py -v
"""
import asyncio
import logging
import os
import re
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from business_time import business_date, business_day_bounds  # noqa: E402
from pymongo import ReadPreference  # noqa: E402

DAY = business_date()
FRONTEND = "https://www.thecalibrationcrew.us"


def _match(doc, query):
    for key, expected in (query or {}).items():
        value = doc.get(key)
        if isinstance(expected, dict):
            for op, operand in expected.items():
                if op == "$gte":
                    ok = value is not None and value >= operand
                elif op == "$lt":
                    ok = value is not None and value < operand
                elif op == "$nin":
                    ok = value not in operand
                elif op == "$regex":
                    ok = isinstance(value, str) and re.search(operand, value) is not None
                else:
                    raise AssertionError(f"unsupported query op {op}")
                if not ok:
                    return False
        elif value != expected:
            return False
    return True


def _project(doc, projection):
    out = {k: v for k, v in doc.items() if k != "_id"}
    if not projection:
        return dict(out)
    for key, flag in projection.items():
        if flag == 0:
            out.pop(key, None)
    return out


class _Cursor:
    """sort() drops every row, which is the production failure mode."""

    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, *args, **kwargs):
        self.docs = []
        return self

    def limit(self, _n):
        return self

    async def to_list(self, n):
        return self.docs[:n]


class _Collection:
    def __init__(self):
        self.docs = []
        self.read_preference = None

    def with_options(self, read_preference=None):
        self.read_preference = read_preference
        return self

    def find(self, query=None, projection=None):
        rows = [_project(doc, projection) for doc in self.docs if _match(doc, query)]
        return _Cursor(rows)

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return _project(doc, projection)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update):
        for doc in self.docs:
            if _match(doc, query):
                doc.update(update.get("$set") or {})
                return


class _DB:
    def __init__(self):
        self.shops = _Collection()
        self.invites = _Collection()
        self.shop_requests = _Collection()
        self.jobs = _Collection()
        self.email_log = _Collection()
        self.admin_notifications = _Collection()
        self.email_outbox = _Collection()


def _db(monkeypatch):
    db = _DB()
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "FRONTEND_URL", FRONTEND)
    monkeypatch.setenv("SHOP_EMAILS_ENABLED", "false")
    return db


def test_sorted_find_would_hide_shops_and_invites_but_the_owner_lists_do_not(monkeypatch, caplog):
    db = _db(monkeypatch)
    caplog.set_level(logging.INFO)
    db.shops.docs.append({
        "id": "shop-old", "name": "Preferred Auto Glass", "status": "active",
        "address": "Gilbert, AZ",
    })
    db.shops.docs.append({
        "id": "shop-noname", "status": "active", "address": "Mesa, AZ",
    })
    db.shop_requests.docs.append({
        "id": "6ea62a50-7898-4e6e-a730-196b4cf30606",
        "shop_name": "TEST Jarvis Signup Shop",
        "contact_name": "Ada Glass",
        "mobile": "4805550100",
        "email": "ada@example.com",
        "address": "1 E Main St, Gilbert, AZ 85234",
        "lat": 33.35,
        "lng": -111.78,
        "status": "pending",
        "created_at": "2026-11-13T20:30:00+00:00",
    })

    async def run():
        approved = await server.approve_shop_request(
            "6ea62a50-7898-4e6e-a730-196b4cf30606",
            tech={"id": "owner", "role": "owner"},
        )
        shops = await server.list_shops(tech={"id": "owner", "role": "owner"})
        invites = await server.list_invites(tech={"id": "owner", "role": "owner"})
        return approved, shops, invites

    approved, shops, invites = asyncio.run(run())

    assert db.shops.read_preference == ReadPreference.PRIMARY
    assert db.invites.read_preference == ReadPreference.PRIMARY
    url = approved["register_url"]
    assert url == approved["invite"]["register_url"]
    assert url.startswith(f"{FRONTEND}/portal/invite/")
    token = url.rsplit("/", 1)[-1]
    assert token
    assert "token" not in approved["invite"]
    assert approved["invite"]["email_status"] == "held"
    assert approved["invite"]["shop_name"] == "TEST Jarvis Signup Shop"
    stored = next(doc for doc in db.invites.docs if doc["shop_name"] == "TEST Jarvis Signup Shop")
    assert stored["token"] == token

    assert [shop.get("name") for shop in shops] == [
        None, "Preferred Auto Glass", "TEST Jarvis Signup Shop",
    ]

    assert len(invites) == 1
    assert invites[0]["email_status"] == "held"
    assert invites[0]["register_url"] == url
    assert "token" not in invites[0]

    logged = caplog.text
    assert token not in logged
    assert url not in logged
    assert "[SHOPS] owner list 3" in logged
    assert "[INVITES] owner list 1 held 1" in logged


def test_job_and_email_lists_keep_rows_a_sorted_find_would_drop(monkeypatch):
    db = _db(monkeypatch)
    start, _end = business_day_bounds(DAY)
    when = (start + timedelta(hours=10)).isoformat()
    later = (start + timedelta(hours=11)).isoformat()
    db.jobs.docs.append({
        "id": "job-1", "status": "booked", "shop_name": "Preferred Auto Glass",
        "scheduled_start": when, "scheduled_end": later,
    })
    db.email_log.docs.extend([
        {"id": "old-mail", "to": "a@shop.test", "subject": "Older", "sent_at": "2026-11-01T00:00:00+00:00"},
        {"id": "new-mail", "to": "b@shop.test", "subject": "Newer", "sent_at": "2026-11-13T21:00:00+00:00"},
    ])
    db.admin_notifications.docs.append({
        "id": "manual-1", "to": "c@shop.test", "subject": "[MANUAL SEND] Invite",
        "sent_at": "2026-11-13T21:01:00+00:00",
    })

    async def run():
        jobs = await server.list_jobs(
            date_str=DAY.isoformat(), tech={"id": "owner", "role": "owner"},
        )
        mail = await server.email_log(tech={"id": "owner", "role": "owner"})
        return jobs, mail

    jobs, mail = asyncio.run(run())
    assert [job["id"] for job in jobs] == ["job-1"]
    assert db.jobs.read_preference == ReadPreference.PRIMARY
    assert [row["id"] for row in mail["sent"]] == ["new-mail", "old-mail"]
    assert [row["id"] for row in mail["pending_manual"]] == ["manual-1"]
    assert db.email_log.read_preference == ReadPreference.PRIMARY
