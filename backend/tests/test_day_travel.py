"""Start Driving and I've Arrived are Phoenix-today only. Contractors are gone.

No live Mongo. These tests do not send email or text outside the in-memory log,
and they do not change BILLING_ENABLED or SHOP_EMAILS_ENABLED.

    cd backend && pytest tests/test_day_travel.py -v
"""
import asyncio
import os
import sys
from datetime import datetime, time, timedelta

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from business_time import BUSINESS_TZ, business_date  # noqa: E402

NOTE = "Available on the day of the job"


def _match(doc, query):
    if "$or" in query:
        return any(_match(doc, part) for part in query["$or"])
    for key, expected in query.items():
        if isinstance(expected, dict) and "$exists" in expected:
            exists = key in doc
            if exists != bool(expected["$exists"]):
                return False
            continue
        if doc.get(key) != expected:
            return False
    return True


def _project(doc, projection):
    out = {k: v for k, v in doc.items() if k != "_id"}
    if not projection:
        return out
    if any(value == 0 for value in projection.values()):
        for key, flag in projection.items():
            if flag == 0:
                out.pop(key, None)
        return out
    return {key: out[key] for key in projection if key in out}


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args, **kwargs):
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, limit):
        return self.docs[:limit]


class _Store:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return _project(doc, projection)
        return None

    def find(self, query, projection=None):
        return _Cursor([_project(doc, projection) for doc in self.docs if _match(doc, query)])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update):
        for doc in self.docs:
            if _match(doc, query):
                doc.update(update.get("$set") or {})
                return
        return None

    async def update_many(self, query, update):
        for doc in self.docs:
            if _match(doc, query):
                doc.update(update.get("$set") or {})

    async def count_documents(self, query):
        return len([doc for doc in self.docs if _match(doc, query)])

    async def delete_many(self, query):
        self.docs = [doc for doc in self.docs if not _match(doc, query)]


class _DB:
    def __init__(self):
        self.technicians = _Store()
        self.jobs = _Store()
        self.shops = _Store()
        self.sms_log = _Store()
        self.contractor_offers = _Store()
        self.documents = _Store()
        self.partner_contacts = _Store()


def _phoenix(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), tzinfo=BUSINESS_TZ).isoformat()


def _job(**overrides):
    today = business_date()
    doc = {
        "id": "job-1",
        "shop_id": "shop-1",
        "shop_name": "Star Windshield",
        "technician_id": "owner-1",
        "status": "booked",
        "vehicle_year": 2020,
        "vehicle_make": "Honda",
        "vehicle_model": "Pilot",
        "calibration_label": "Static ADAS Calibration",
        "job_address": "1 Main St, Gilbert, AZ",
        "scheduled_start": _phoenix(today, 9),
        "scheduled_end": _phoenix(today, 10),
        "price": 125.0,
        "notification_phone": "+16025550100",
        "drive_time_minutes": 18,
    }
    doc.update(overrides)
    return doc


@pytest.fixture
def world(monkeypatch):
    db = _DB()
    db.technicians.docs.append({
        "id": "owner-1",
        "role": "owner",
        "name": "Caleb",
        "email": "caleb@thecalibrationcrew.us",
        "is_active": True,
        "password_hash": server.hash_password("owner-secret"),
    })
    db.technicians.docs.append({
        "id": "tech-field",
        "role": "technician",
        "name": "Field",
        "email": "field@thecalibrationcrew.us",
        "is_active": True,
    })
    contractor = {
        "id": "west",
        "role": "contractor",
        "name": "West-Side Contractor",
        "email": "contractor@thecalibrationcrew.us",
        "phone": "+16025550199",
        "is_active": True,
        "home_address": "Goodyear, AZ",
        "password_hash": server.hash_password("contractor-secret"),
    }
    db.technicians.docs.append(contractor)
    db.jobs.docs.append(_job())
    db.contractor_offers.docs.append({
        "id": "offer-1",
        "job_id": "job-1",
        "status": "pending",
        "contractor_id": "west",
    })
    original = server.db
    monkeypatch.setattr(server, "db", db)
    yield {
        "db": db,
        "owner": server.make_token("owner-1", "owner"),
        "technician": server.make_token("tech-field", "technician"),
        "contractor": server.make_token("west", "contractor"),
        "contractor_row": dict(contractor),
    }
    monkeypatch.setattr(server, "db", original)


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _stored(world, job_id="job-1"):
    return next(job for job in world["db"].jobs.docs if job["id"] == job_id)


def test_start_driving_and_arrived_work_on_a_phoenix_today_job(world):
    today = business_date()
    # 6:30 PM Phoenix is 01:30 UTC the next calendar day, and it is still today.
    evening = _job(id="job-evening", scheduled_start=_phoenix(today, 18, 30), status="booked")
    world["db"].jobs.docs.append(evening)

    async def run():
        async with _client() as client:
            driving = await client.post(
                "/api/jobs/job-evening/status",
                headers=_auth(world["owner"]),
                json={"status": "driving"},
            )
            arrived = await client.post(
                "/api/jobs/job-1/status",
                headers=_auth(world["owner"]),
                json={"status": "on_site"},
            )
            return driving, arrived

    # job-1 is booked, not driving. Arrived from booked is still a status write
    # the server already allows; the day gate must not block a today job.
    world["db"].jobs.docs[0]["status"] = "driving"
    driving, arrived = asyncio.run(run())

    assert driving.status_code == 200, driving.text
    assert driving.json()["status"] == "driving"
    assert arrived.status_code == 200, arrived.text
    assert arrived.json()["status"] == "on_site"
    assert arrived.json()["actual_arrival"]
    kinds = [row["kind"] for row in world["db"].sms_log.docs]
    assert kinds == ["on_my_way"]
    assert all(row["kind"] != "on_my_way" or row["job_id"] == "job-evening" for row in world["db"].sms_log.docs)


def test_start_driving_and_arrived_reject_other_phoenix_days(world):
    today = business_date()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    # 11:30 PM yesterday is 06:30 UTC on today's UTC date, and it is not today in Phoenix.
    world["db"].jobs.docs.append(_job(
        id="job-yesterday",
        status="driving",
        scheduled_start=_phoenix(yesterday, 23, 30),
    ))
    world["db"].jobs.docs.append(_job(
        id="job-tomorrow",
        status="booked",
        scheduled_start=_phoenix(tomorrow, 8),
    ))
    before = [dict(job) for job in world["db"].jobs.docs]

    async def run():
        async with _client() as client:
            driving = await client.post(
                "/api/jobs/job-tomorrow/status",
                headers=_auth(world["owner"]),
                json={"status": "driving"},
            )
            arrived = await client.post(
                "/api/jobs/job-yesterday/status",
                headers=_auth(world["owner"]),
                json={"status": "on_site"},
            )
            missing_day = await client.post(
                "/api/jobs/job-blank/status",
                headers=_auth(world["owner"]),
                json={"status": "driving"},
            )
            return driving, arrived, missing_day

    world["db"].jobs.docs.append(_job(id="job-blank", scheduled_start=None))
    driving, arrived, missing_day = asyncio.run(run())

    assert driving.status_code == 400, driving.text
    assert arrived.status_code == 400, arrived.text
    assert missing_day.status_code == 400, missing_day.text
    assert NOTE in driving.text
    assert NOTE in arrived.text
    assert NOTE in missing_day.text
    assert world["db"].sms_log.docs == []
    stored = {job["id"]: job for job in world["db"].jobs.docs}
    for job in before:
        assert stored[job["id"]]["status"] == job["status"]
        assert stored[job["id"]].get("actual_arrival") is None


def test_cancel_and_complete_still_work_on_another_day(world, monkeypatch):
    tomorrow = business_date() + timedelta(days=1)
    world["db"].jobs.docs.append(_job(
        id="job-later",
        status="booked",
        scheduled_start=_phoenix(tomorrow, 11),
        notification_phone="+16025550100",
    ))

    async def settle(job_id):
        return {"job_id": job_id}

    async def invoice(job_id):
        return {"status": "needs_attention", "reason": "held in the test"}

    async def latest(job_id):
        return None, None, None

    monkeypatch.setattr(server, "_settle_completed_job", settle)
    monkeypatch.setattr(server, "create_invoice_for_job", invoice)
    monkeypatch.setattr(server, "_latest_scan", latest)

    async def run():
        async with _client() as client:
            cancelled = await client.post(
                "/api/jobs/job-1/status",
                headers=_auth(world["owner"]),
                json={"status": "cancelled"},
            )
            # Cancel above is today. The future job is the one that must still complete.
            world["db"].jobs.docs[0]["status"] = "booked"
            completed = await client.post(
                "/api/jobs/job-later/complete",
                headers=_auth(world["owner"]),
                json={"result": "pass", "notes": "done", "calibration_type": "static", "pop": "none"},
            )
            return cancelled, completed

    # Use a future job for cancel too, so neither travel action is required.
    world["db"].jobs.docs[0]["scheduled_start"] = _phoenix(tomorrow, 9)
    cancelled, completed = asyncio.run(run())

    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert completed.status_code == 200, completed.text
    assert completed.json()["job"]["status"] == "complete"
    kinds = [row["kind"] for row in world["db"].sms_log.docs]
    assert "on_my_way" not in kinds
    assert "cancelled" in kinds
    assert "completed" in kinds


def test_technician_and_contractor_cannot_start_driving(world):
    async def run():
        async with _client() as client:
            technician = await client.post(
                "/api/jobs/job-1/status",
                headers=_auth(world["technician"]),
                json={"status": "driving"},
            )
            contractor = await client.post(
                "/api/jobs/job-1/status",
                headers=_auth(world["contractor"]),
                json={"status": "driving"},
            )
            return technician, contractor

    technician, contractor = asyncio.run(run())
    assert technician.status_code == 403
    assert contractor.status_code == 403
    assert _stored(world)["status"] == "booked"
    assert world["db"].sms_log.docs == []


def test_contractor_routes_are_gone_and_stored_rows_stay(world):
    offer_before = [dict(row) for row in world["db"].contractor_offers.docs]
    contractor_before = dict(world["contractor_row"])

    async def run():
        async with _client() as client:
            headers = _auth(world["owner"])
            listed = await client.get("/api/contractors", headers=headers)
            updated = await client.put("/api/contractors/west", headers=headers, json={"name": "Changed"})
            offers = await client.get("/api/contractor-offers", headers=headers)
            respond = await client.post(
                "/api/contractor-offers/offer-1/respond",
                headers=headers,
                json={"accept": True},
            )
            dispatched = await client.post(
                "/api/jobs/job-1/dispatch",
                headers=headers,
                json={"contractor_id": "west"},
            )
            return listed, updated, offers, respond, dispatched

    listed, updated, offers, respond, dispatched = asyncio.run(run())
    assert listed.status_code == 404
    assert updated.status_code == 404
    assert offers.status_code == 404
    assert respond.status_code == 404
    assert dispatched.status_code == 404
    assert world["db"].contractor_offers.docs == offer_before
    stored = next(person for person in world["db"].technicians.docs if person["id"] == "west")
    assert stored == contractor_before
    assert _stored(world)["status"] == "booked"
    assert world["db"].sms_log.docs == []


def test_contractor_login_is_rejected_and_the_row_is_not_rewritten(world):
    before = dict(next(person for person in world["db"].technicians.docs if person["id"] == "west"))

    async def run():
        async with _client() as client:
            bad = await client.post("/api/auth/login", json={
                "email": "contractor@thecalibrationcrew.us",
                "password": "wrong-secret",
            })
            denied = await client.post("/api/auth/login", json={
                "email": "contractor@thecalibrationcrew.us",
                "password": "contractor-secret",
            })
            return bad, denied

    bad, denied = asyncio.run(run())
    assert bad.status_code == 401
    assert denied.status_code == 403
    assert "token" not in denied.json()
    assert "no longer used" in denied.text.lower()
    after = next(person for person in world["db"].technicians.docs if person["id"] == "west")
    assert after == before


def test_seed_does_not_read_or_write_contractor_rows(world, monkeypatch):
    before = [dict(person) for person in world["db"].technicians.docs if person["role"] == "contractor"]
    monkeypatch.setattr(server, "SEED_DEMO_DATA", False)
    monkeypatch.setattr(server, "GROWTH_MODULE_ENABLED", False)
    monkeypatch.setenv("CONTRACTOR_PASSWORD", "should-not-rotate")
    monkeypatch.setenv("CONTRACTOR_EMAIL", "contractor@thecalibrationcrew.us")

    asyncio.run(server.seed_data())

    after = [dict(person) for person in world["db"].technicians.docs if person["role"] == "contractor"]
    assert after == before
    assert len(after) == 1
    assert world["db"].contractor_offers.docs[0]["status"] == "pending"
    assert world["db"].sms_log.docs == []
