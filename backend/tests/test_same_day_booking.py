"""Public booking: early arrivals, and today's route versus a later date.

No live Mongo. Drive times are injected.
    cd backend && pytest tests/test_same_day_booking.py -v
"""
import asyncio
import os
import sys
from datetime import datetime, time, timedelta, timezone

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from business_time import zone_window  # noqa: E402
from onboarding import READY_BILLING  # noqa: E402

HOME = (33.3528, -111.7890)
EAG = (33.4372, -111.8210)
GOODYEAR = (33.4353, -112.3576)
SURPRISE = (33.6292, -112.3679)
# 10:00 AM Phoenix on Thursday 2026-11-12.
NOW = datetime(2026, 11, 12, 17, 0, tzinfo=timezone.utc)
AFTER_CUTOFF = datetime(2026, 11, 12, 20, 30, tzinfo=timezone.utc)


def _match(doc, query):
    for key, expected in query.items():
        value = doc.get(key)
        if isinstance(expected, dict):
            if "$gte" in expected and not (value is not None and value >= expected["$gte"]):
                return False
            if "$lt" in expected and not (value is not None and value < expected["$lt"]):
                return False
            if "$nin" in expected and value in expected["$nin"]:
                return False
            if "$ne" in expected and value == expected["$ne"]:
                return False
        elif value != expected:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args, **kwargs):
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, n):
        return self.docs[:n]


class _Store:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return {k: v for k, v in doc.items() if k not in ("_id", "password_hash")}
        return None

    def find(self, query, projection=None):
        return _Cursor([
            {k: v for k, v in doc.items() if k != "password_hash"}
            for doc in self.docs if _match(doc, query)
        ])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _match(doc, query):
                doc.update(update.get("$set", {}))
                return
        if upsert:
            self.docs.append({"_id": query.get("_id"), **update.get("$set", {})})

    async def count_documents(self, query):
        return len([doc for doc in self.docs if _match(doc, query)])


class _DB:
    def __init__(self):
        self.technicians = _Store()
        self.shops = _Store()
        self.jobs = _Store()
        self.vehicles = _Store()
        self.new_booking_alerts = _Store()
        self.drive_time_cache = _Store()


def _office():
    return {"Authorization": f"Bearer {server.make_token('caleb', 'owner')}"}


def _db():
    db = _DB()
    db.technicians.docs.append({
        "id": "caleb", "name": "Caleb", "role": "owner", "is_active": True, "routes_jobs": True,
        "home_address": "Gilbert, AZ", "home_lat": HOME[0], "home_lng": HOME[1],
        "phone": "480-555-0100", "color": "#FF5F1F", "day_start": "08:00", "day_end": "19:00",
    })
    db.technicians.docs.append({
        "id": "field", "name": "Field", "role": "technician", "is_active": True,
    })
    db.shops.docs.append({
        "id": "shop-1", "name": "Preferred", "booking_link_token": "tok", "status": "active",
        "contact_phone": "480-555-0199", **READY_BILLING,
    })
    return db


def _close(a, b):
    return abs(a[0] - b[0]) < 0.02 and abs(a[1] - b[1]) < 0.02


def _minutes(a, b):
    pairs = (
        ((HOME, EAG), 20),
        ((EAG, HOME), 20),
        ((EAG, GOODYEAR), 75),
        ((GOODYEAR, HOME), 45),
        ((HOME, GOODYEAR), 50),
        ((HOME, SURPRISE), 89),
        ((SURPRISE, HOME), 89),
    )
    for (origin, dest), minutes in pairs:
        if _close(a, origin) and _close(b, dest):
            return minutes
    return 15


def _install(monkeypatch, db, now):
    texts = []
    emails = []

    async def drive(o_lat, o_lng, d_lat, d_lng, depart_at=None, **kwargs):
        return {"duration_minutes": _minutes((o_lat, o_lng), (d_lat, d_lng)), "distance_miles": 10}

    async def geo(address):
        text = address.lower()
        if "goodyear" in text:
            point = GOODYEAR
        elif "surprise" in text:
            point = SURPRISE
        elif "mesa" in text or "brown" in text:
            point = EAG
        else:
            point = (33.45, -112.07)
        return {"lat": point[0], "lng": point[1], "formatted_address": address, "in_metro": True}

    async def record_sms(*args, **kwargs):
        texts.append(args)

    async def record_email(*args, **kwargs):
        emails.append(args)

    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "geocode_address", geo)
    monkeypatch.setattr(server, "geocode_for_regeocode", geo)
    monkeypatch.setattr(server, "get_drive_time", drive)
    monkeypatch.setattr(server, "mock_send_sms", record_sms)
    monkeypatch.setattr(server, "send_email", record_email)
    monkeypatch.setattr(server, "now_utc", lambda: now)
    return texts, emails


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test")


PAYLOAD = {
    "booking_token": "tok",
    "customer_last_name": "Ng",
    "year": 2022, "make": "Honda", "model": "Civic",
    "adas_system": "forward_camera", "calibration_type": "static",
    "notification_phone": "480-555-0142",
}


def test_early_arrival_is_held_until_the_owner_decides(monkeypatch):
    db = _db()
    texts, emails = _install(monkeypatch, db, NOW)
    day = datetime(2026, 11, 13).date()
    six, _end = zone_window(day, time(6, 0), time(17, 0))
    ten, _ignored = zone_window(day, time(10, 0), time(17, 0))

    async def run():
        async with _client() as client:
            avail = await client.post("/api/shops/shop-1/availability", headers=_office(), json={
                "booking_token": "tok", "job_address": "Surprise, AZ", "date": day.isoformat(),
            })
            assert avail.status_code == 200, avail.text
            starts = {slot["start"]: slot for slot in avail.json()["slots"]}
            # 89 minutes from home. Leaving at 6:00 AM arrives at 7:29, so the
            # first grid time is 7:30 (pending). 8:00 leaves at 6:31 and is confirmed.
            seven_thirty, _ = zone_window(day, time(7, 30), time(17, 0))
            eight, _ = zone_window(day, time(8, 0), time(17, 0))
            assert six.isoformat() not in starts
            assert seven_thirty.isoformat() in starts
            assert starts[seven_thirty.isoformat()]["requires_approval"] is True
            assert eight.isoformat() in starts
            assert starts[eight.isoformat()]["requires_approval"] is False
            for hour, minute in ((8, 15), (8, 30), (8, 45), (9, 0), (9, 15), (9, 30)):
                instant, _ = zone_window(day, time(hour, minute), time(17, 0))
                assert instant.isoformat() in starts
                assert starts[instant.isoformat()]["requires_approval"] is False
            booked = await client.post("/api/shops/shop-1/book", headers=_office(), json={
                **PAYLOAD, "job_address": "Surprise, AZ", "scheduled_start": seven_thirty.isoformat(),
            })
            assert booked.status_code == 200, booked.text
            body = booked.json()
            assert body["status"] == "requested"
            assert body["requires_approval"] is True
            assert texts == []
            assert emails
            again = await client.post("/api/shops/shop-1/book", headers=_office(), json={
                **PAYLOAD, "job_address": "Surprise, AZ", "scheduled_start": seven_thirty.isoformat(),
            })
            assert again.status_code == 400
            tech = server.make_token("field", "technician")
            denied = await client.post(
                f"/api/jobs/{body['job_id']}/approve",
                headers={"Authorization": f"Bearer {tech}"},
            )
            assert denied.status_code == 403
            owner = server.make_token("caleb", "owner")
            approved = await client.post(
                f"/api/jobs/{body['job_id']}/approve",
                headers={"Authorization": f"Bearer {owner}"},
            )
            assert approved.status_code == 200, approved.text
            assert approved.json()["status"] == "booked"
            assert texts == []
            # A normal late-morning time on a future day is still confirmed.
            # This shop has no email, and 10:00 is not an owner alert, so nothing is texted.
            standard = await client.post("/api/shops/shop-1/book", headers=_office(), json={
                **PAYLOAD, "job_address": "Mesa, AZ", "scheduled_start": ten.isoformat(),
            })
            assert standard.status_code == 200, standard.text
            assert standard.json()["status"] == "booked"
            assert standard.json()["requires_approval"] is False
            assert texts == []

    asyncio.run(run())


def test_goodyear_after_east_valley_is_not_auto_accepted(monkeypatch):
    db = _db()
    nine, _ = zone_window(NOW.date(), time(9, 0), time(17, 0))
    db.jobs.docs.append({
        "id": "eag", "technician_id": "caleb", "status": "booked",
        "scheduled_start": nine.isoformat(),
        "scheduled_end": (nine + timedelta(minutes=20)).isoformat(),
        "duration_minutes": 20,
        "job_lat": EAG[0], "job_lng": EAG[1],
        "job_address": "855 East Brown Road, Mesa, AZ",
        "shop_id": "shop-1",
    })
    texts, emails = _install(monkeypatch, db, NOW)

    async def run():
        async with _client() as client:
            avail = await client.post("/api/shops/shop-1/availability", headers=_office(), json={
                "booking_token": "tok", "job_address": "Goodyear, AZ", "date": NOW.date().isoformat(),
            })
            assert avail.status_code == 200, avail.text
            slots = avail.json()["slots"]
            assert slots, avail.text
            assert all(slot["requires_approval"] for slot in slots)
            assert "add-on" not in avail.text.lower()
            chosen = slots[0]["start"]
            booked = await client.post("/api/shops/shop-1/book", headers=_office(), json={
                **PAYLOAD, "job_address": "Goodyear, AZ", "scheduled_start": chosen,
            })
            assert booked.status_code == 200, booked.text
            assert booked.json()["status"] == "requested"
            assert booked.json()["requires_approval"] is True
            assert texts == []
            assert emails
            saved = [job for job in db.jobs.docs if job.get("approval_reason") == "same_day_addon"]
            assert saved
            assert saved[0]["extra_drive_minutes"] >= 90

    asyncio.run(run())


def test_over_limit_can_be_hidden_and_today_closes_at_the_cutoff(monkeypatch):
    db = _db()
    db.technicians.docs[0]["same_day_over_limit"] = "hide"
    nine, _ = zone_window(NOW.date(), time(9, 0), time(17, 0))
    db.jobs.docs.append({
        "id": "eag", "technician_id": "caleb", "status": "booked",
        "scheduled_start": nine.isoformat(),
        "scheduled_end": (nine + timedelta(minutes=20)).isoformat(),
        "duration_minutes": 20,
        "job_lat": EAG[0], "job_lng": EAG[1],
        "job_address": "855 East Brown Road, Mesa, AZ",
    })
    _install(monkeypatch, db, NOW)
    eleven, _ = zone_window(NOW.date(), time(11, 0), time(17, 0))

    async def run():
        async with _client() as client:
            hidden = await client.post("/api/shops/shop-1/availability", headers=_office(), json={
                "booking_token": "tok", "job_address": "Goodyear, AZ", "date": NOW.date().isoformat(),
            })
            assert hidden.status_code == 200, hidden.text
            assert hidden.json()["slots"] == []
            forced = await client.post("/api/shops/shop-1/book", headers=_office(), json={
                **PAYLOAD, "job_address": "Goodyear, AZ", "scheduled_start": eleven.isoformat(),
            })
            assert forced.status_code == 400
            assert "today" in forced.json()["detail"].lower()
            monkeypatch.setattr(server, "now_utc", lambda: AFTER_CUTOFF)
            db.technicians.docs[0]["same_day_over_limit"] = "pending"
            closed = await client.post("/api/shops/shop-1/availability", headers=_office(), json={
                "booking_token": "tok", "job_address": "Goodyear, AZ", "date": NOW.date().isoformat(),
            })
            assert closed.json()["slots"] == []
            assert "1:00 PM" in closed.json()["message"]

    asyncio.run(run())


def test_portal_booking_and_approval_each_send_one_confirmation(monkeypatch):
    """A confirmed portal booking emails once. A pending job emails once, on approval."""
    db = _db()
    db.shops.docs[0]["contact_email"] = "shop@glass.example"
    db.shop_users = _Store()
    db.shop_users.docs.append({
        "id": "su-1", "shop_id": "shop-1", "is_active": True, "email": "shop@glass.example",
    })
    db.email_outbox = _Store()
    texts, emails = _install(monkeypatch, db, NOW)
    monkeypatch.setenv("SHOP_EMAILS_ENABLED", "false")
    monkeypatch.setattr(server, "FRONTEND_URL", "https://www.thecalibrationcrew.us")
    day = datetime(2026, 11, 13).date()
    seven_thirty, _ = zone_window(day, time(7, 30), time(17, 0))
    ten, _ = zone_window(day, time(10, 0), time(17, 0))
    portal = {"Authorization": f"Bearer {server.make_portal_token('su-1')}"}

    def confirmations():
        return [row for row in db.email_outbox.docs if row.get("kind") == "booking_confirmation"]

    async def run():
        async with _client() as client:
            pending = await client.post("/api/portal/book", headers=portal, json={
                **PAYLOAD, "job_address": "Surprise, AZ", "scheduled_start": seven_thirty.isoformat(),
            })
            assert pending.status_code == 200, pending.text
            assert pending.json()["status"] == "requested"
            assert confirmations() == []
            assert texts == []
            assert emails
            owner = server.make_token("caleb", "owner")
            approved = await client.post(
                f"/api/jobs/{pending.json()['job_id']}/approve",
                headers={"Authorization": f"Bearer {owner}"},
            )
            assert approved.status_code == 200, approved.text
            assert len(confirmations()) == 1
            again = await client.post(
                f"/api/jobs/{pending.json()['job_id']}/approve",
                headers={"Authorization": f"Bearer {owner}"},
            )
            assert again.status_code == 400
            assert len(confirmations()) == 1
            booked = await client.post("/api/portal/book", headers=portal, json={
                **PAYLOAD, "job_address": "Mesa, AZ", "scheduled_start": ten.isoformat(),
            })
            assert booked.status_code == 200, booked.text
            assert booked.json()["status"] == "booked"
            assert booked.json()["requires_approval"] is False
            assert len(confirmations()) == 2
            repeat = await server.email_shop_confirmation(
                next(job for job in db.jobs.docs if job["id"] == booked.json()["job_id"]),
                db.shops.docs[0],
            )
            assert repeat is None
            assert len(confirmations()) == 2
            return pending.json(), booked.json()

    pending, booked = asyncio.run(run())
    kinds = {row["kind"] for row in db.email_outbox.docs}
    assert "day_before_reminder" not in kinds
    assert "booking_approved" not in kinds
    held = {row["body"]: row for row in confirmations()}
    early = next(body for body in held if "Surprise, AZ" in body)
    later = next(body for body in held if "Mesa, AZ" in body)
    assert "We have this job." in early
    assert "Fri, Nov 13, 2026" in early
    assert "7:30–7:50 AM Phoenix" in early
    assert "2022 Honda Civic" in early
    assert pending["booking_reference"] in early
    assert f"/portal/jobs/{pending['job_id']}" in early
    assert "We have this job." in later
    assert "10:00–10:20 AM Phoenix" in later
    assert booked["booking_reference"] in later
    assert f"https://www.thecalibrationcrew.us/portal/jobs/{booked['job_id']}" in later
    assert all(row["to"] == "shop@glass.example" for row in confirmations())
    assert all(row["delivered"] is False for row in confirmations())
