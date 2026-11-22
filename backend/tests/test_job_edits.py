"""PATCH job edits for the owner and for a logged-in shop.

No live Mongo. The routes run against an in-memory store:
    cd backend && pytest tests/test_job_edits.py -v
"""
import asyncio
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from business_time import BUSINESS_TZ, business_day_bounds, business_date  # noqa: E402

TODAY = business_date()
TODAY_START, _TODAY_END = business_day_bounds(TODAY)
# 10:00 AM Phoenix on the next open day. The shop is closed Sundays, so a
# Saturday run must not book "tomorrow".
_OPEN = TODAY + timedelta(days=1)
if _OPEN.weekday() == 6:
    _OPEN = _OPEN + timedelta(days=1)
_OPEN_START, _ = business_day_bounds(_OPEN)
FUTURE = (_OPEN_START + timedelta(hours=10)).isoformat()
FUTURE_END = (_OPEN_START + timedelta(hours=11)).isoformat()
PAST = (TODAY_START - timedelta(days=2)).isoformat()


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
            if "$in" in expected and value not in expected["$in"]:
                return False
            if "$ne" in expected and value == expected["$ne"]:
                return False
        elif value != expected:
            return False
    return True


def _project(doc, projection):
    out = {k: v for k, v in doc.items() if k != "_id"}
    if not projection:
        return out
    if any(v == 0 for v in projection.values()):
        for key, flag in projection.items():
            if flag == 0:
                out.pop(key, None)
        return out
    return {k: out[k] for k in projection if k in out}


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, limit):
        return self.docs[:limit]


class _Store:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return _project(doc, projection)
        return None

    def find(self, query, projection=None):
        return _Cursor([_project(d, projection) for d in self.docs if _match(d, query)])

    async def update_one(self, query, update):
        for doc in self.docs:
            if _match(doc, query):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                for key, value in update.get("$push", {}).items():
                    doc.setdefault(key, []).append(value)
                return

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class _DB:
    def __init__(self):
        self.technicians = _Store()
        self.shops = _Store()
        self.shop_users = _Store()
        self.jobs = _Store()
        self.vehicles = _Store()
        self.email_outbox = _Store()
        self.days_off = _Store()


def _job(**overrides):
    doc = {
        "id": "job-1",
        "shop_id": "shop-1",
        "shop_name": "Glass Co",
        "technician_id": "tech-1",
        "status": "booked",
        "job_address": "100 W Main, Phoenix, AZ",
        "job_lat": 33.45,
        "job_lng": -112.2,
        "zone": "west",
        "customer_first_name": "Ana",
        "customer_last_name": "Ng",
        "notification_phone": "+16025550100",
        "notification_email": "ana@example.com",
        "vehicle_id": "veh-1",
        "vehicle_year": 2020,
        "vehicle_make": "Honda",
        "vehicle_model": "Civic",
        "vehicle_vin": None,
        "calibration_type": "static",
        "calibration_label": "Static ADAS Calibration",
        "price": 125.0,
        "scheduled_start": FUTURE,
        "scheduled_end": FUTURE_END,
        "notes": "Gate",
        "edit_history": [],
    }
    doc.update(overrides)
    return doc


def _shop(**overrides):
    doc = {
        "id": "shop-1",
        "name": "Glass Co",
        "address": "100 W Main, Phoenix, AZ",
        "contact_name": "Dana",
        "contact_phone": "+16025550111",
        "contact_email": "dana@glass.example",
        "status": "active",
        "booking_link_token": "tok-a",
        "lat": 33.45,
        "lng": -112.2,
        "zone": "west",
        "pricing_tier": "standard",
        "state": "AZ",
    }
    doc.update(overrides)
    return doc


@pytest.fixture
def world(monkeypatch):
    db = _DB()
    db.technicians.docs.append({"id": "tech-1", "role": "owner", "name": "Caleb", "email": "caleb@thecalibrationcrew.us"})
    db.technicians.docs.append({"id": "tech-2", "role": "contractor", "name": "West Tech", "email": "west@example.com"})
    db.technicians.docs.append({"id": "tech-3", "role": "technician", "name": "Field Tech", "email": "field@example.com"})
    db.shops.docs.append(_shop())
    db.shops.docs.append(_shop(
        id="shop-2", name="Other Shop", booking_link_token="tok-b",
        contact_email="other@glass.example",
    ))
    db.shop_users.docs.append({
        "id": "su-1", "shop_id": "shop-1", "full_name": "Dana", "email": "dana@glass.example", "is_active": True,
    })
    db.shop_users.docs.append({
        "id": "su-2", "shop_id": "shop-2", "full_name": "Other", "email": "other@glass.example", "is_active": True,
    })
    db.jobs.docs.append(_job(technician_id="tech-2"))
    db.jobs.docs.append(_job(id="job-other", shop_id="shop-2"))
    db.jobs.docs.append(_job(id="job-past", scheduled_start=PAST, scheduled_end=PAST))
    db.jobs.docs.append(_job(id="job-cancelled", status="cancelled"))
    db.vehicles.docs.append({
        "id": "veh-1", "year": 2020, "make": "Honda", "model": "Civic",
        "customer_last_name": "Ng", "customer_first_name": "Ana",
    })
    calls = {"sms": [], "email": [], "geo": []}

    async def sms(*args, **kwargs):
        calls["sms"].append((args, kwargs))

    async def email(*args, **kwargs):
        calls["email"].append((args, kwargs))

    async def geo(address):
        calls["geo"].append(address)
        if "nope" in address.lower():
            raise server.GoogleMapsError("ZERO_RESULTS")
        return {"lat": 33.3062, "lng": -111.8413, "formatted_address": address, "in_metro": True}

    original = server.db
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "mock_send_sms", sms)
    monkeypatch.setattr(server, "send_email", email)
    monkeypatch.setattr(server, "geocode_for_regeocode", geo)
    yield {"db": db, "calls": calls, "owner": server.make_token("tech-1", "owner"),
           "contractor": server.make_token("tech-2", "contractor"),
           "technician": server.make_token("tech-3", "technician"),
           "shop": server.make_portal_token("su-1"),
           "other_shop": server.make_portal_token("su-2")}
    monkeypatch.setattr(server, "db", original)


def _client():
    transport = httpx.ASGITransport(app=server.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_owner_patch_regeocodes_a_new_address_and_sends_nothing(world):
    async def run():
        async with _client() as client:
            response = await client.patch(
                "/api/jobs/job-1",
                headers=_auth(world["owner"]),
                json={"job_address": "1234 E Williams Field Rd, Gilbert, AZ", "notes": "Use the side gate"},
            )
        assert response.status_code == 200, response.text
        job = response.json()
        assert job["status"] == "booked"
        assert job["job_address"] == "1234 E Williams Field Rd, Gilbert, AZ"
        assert job["job_lat"] == 33.3062
        assert job["job_lng"] == -111.8413
        assert job["zone"] == "east"
        assert job["notes"] == "Use the side gate"
        assert job["price"] == 125.0
        assert world["calls"]["geo"] == ["1234 E Williams Field Rd, Gilbert, AZ"]
        assert world["calls"]["sms"] == []
        assert world["calls"]["email"] == []
        assert world["db"].email_outbox.docs == []
        history = job["edit_history"]
        assert history[-1]["who"] == {"kind": "owner", "id": "tech-1", "name": "Caleb"}
        assert "at" in history[-1]
        assert "job_address" in history[-1]["fields"]
        assert "notes" in history[-1]["fields"]
        assert "status" not in history[-1]["fields"]
        assert job["updated_at"]

    asyncio.run(run())


def test_owner_zone_overrides_the_geocoded_zone(world):
    async def run():
        async with _client() as client:
            response = await client.patch(
                "/api/jobs/job-1",
                headers=_auth(world["owner"]),
                json={"job_address": "Gilbert shop", "zone": "west"},
            )
        assert response.status_code == 200, response.text
        job = response.json()
        assert job["job_lat"] == 33.3062
        assert job["zone"] == "west"

    asyncio.run(run())


def test_owner_can_override_customer_vehicle_price_and_time(world):
    async def run():
        async with _client() as client:
            response = await client.patch(
                "/api/jobs/job-1",
                headers=_auth(world["owner"]),
                json={
                    "customer_first_name": "Luis",
                    "customer_last_name": "Martinez",
                    "notification_phone": "+16025550999",
                    "notification_email": "luis@example.com",
                    "vehicle_year": 2024,
                    "vehicle_make": "Toyota",
                    "vehicle_model": "Camry",
                    "vehicle_vin": "1HGCM82633A004352",
                    "calibration_type": "dual",
                    "price": 210,
                    "scheduled_start": (TODAY_START + timedelta(days=1, hours=13)).isoformat(),
                    "notes": "  Call on arrival  ",
                },
            )
        assert response.status_code == 200, response.text
        job = response.json()
        assert job["customer_first_name"] == "Luis"
        assert job["customer_last_name"] == "Martinez"
        assert job["notification_phone"] == "(602) 555-0999"
        assert job["notification_email"] == "luis@example.com"
        assert job["vehicle_year"] == 2024
        assert job["vehicle_make"] == "Toyota"
        assert job["vehicle_model"] == "Camry"
        assert job["vehicle_vin"] == "1HGCM82633A004352"
        assert job["calibration_type"] == "dual"
        assert job["price"] == 210
        assert job["notes"] == "Call on arrival"
        assert job["status"] == "booked"
        assert job["scheduled_start"] == (TODAY_START + timedelta(days=1, hours=13)).isoformat()
        assert job["scheduled_end"] == (TODAY_START + timedelta(days=1, hours=14)).isoformat()
        assert world["calls"]["geo"] == []
        assert world["calls"]["sms"] == []

    asyncio.run(run())


def test_owner_patch_updates_the_vehicle_record(world):
    async def run():
        async with _client() as client:
            response = await client.patch(
                "/api/jobs/job-1",
                headers=_auth(world["owner"]),
                json={"vehicle_make": "Ford", "customer_last_name": "Ali"},
            )
        assert response.status_code == 200, response.text
        vehicle = await world["db"].vehicles.find_one({"id": "veh-1"})
        assert vehicle["make"] == "Ford"
        assert vehicle["customer_last_name"] == "Ali"

    asyncio.run(run())


def test_blank_address_is_rejected_and_the_job_stays(world):
    async def run():
        async with _client() as client:
            response = await client.patch(
                "/api/jobs/job-1",
                headers=_auth(world["owner"]),
                json={"job_address": "   "},
            )
        assert response.status_code == 400
        stored = await world["db"].jobs.find_one({"id": "job-1"})
        assert stored["job_address"] == "100 W Main, Phoenix, AZ"
        assert stored["status"] == "booked"
        assert world["calls"]["sms"] == []

    asyncio.run(run())


def test_geocode_failure_does_not_save_the_new_address(world):
    async def run():
        async with _client() as client:
            response = await client.patch(
                "/api/jobs/job-1",
                headers=_auth(world["owner"]),
                json={"job_address": "nope nowhere"},
            )
        assert response.status_code == 400
        stored = await world["db"].jobs.find_one({"id": "job-1"})
        assert stored["job_address"] == "100 W Main, Phoenix, AZ"
        assert stored["job_lat"] == 33.45
        assert world["calls"]["sms"] == []

    asyncio.run(run())


def test_technician_and_assigned_contractor_cannot_patch_a_job(world):
    async def run():
        async with _client() as client:
            contractor = await client.patch(
                "/api/jobs/job-1",
                headers=_auth(world["contractor"]),
                json={"notes": "mine"},
            )
            technician = await client.patch(
                "/api/jobs/job-1",
                headers=_auth(world["technician"]),
                json={"notes": "mine"},
            )
            shop_edit = await client.put(
                "/api/shops/shop-1",
                headers=_auth(world["contractor"]),
                json={"name": "Taken Over", "address": "200 E Main, Gilbert, AZ"},
            )
        assert contractor.status_code == 403
        assert technician.status_code == 403
        assert shop_edit.status_code == 403
        stored = await world["db"].jobs.find_one({"id": "job-1"})
        assert stored["notes"] == "Gate"
        assert stored["technician_id"] == "tech-2"
        shop = await world["db"].shops.find_one({"id": "shop-1"})
        assert shop["name"] == "Glass Co"
        assert world["calls"]["sms"] == []

    asyncio.run(run())


def test_shop_edits_only_its_own_jobs(world):
    async def run():
        async with _client() as client:
            ok = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={"job_address": "500 W Jefferson, Phoenix, AZ", "customer_first_name": "Rio"},
            )
            foreign = await client.patch(
                "/api/portal/jobs/job-other",
                headers=_auth(world["shop"]),
                json={"notes": "should not land"},
            )
            missing = await client.patch(
                "/api/portal/jobs/job-1",
                json={"notes": "nope"},
            )
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert body["customer_first_name"] == "Rio"
        assert body["job_lat"] == 33.3062
        assert body["status"] == "booked"
        assert body["edit_history"][-1]["who"]["kind"] == "shop"
        assert body["edit_history"][-1]["who"]["id"] == "shop-1"
        assert "job_address" in body["edit_history"][-1]["fields"]
        assert foreign.status_code == 404
        assert missing.status_code == 401
        other = await world["db"].jobs.find_one({"id": "job-other"})
        assert other["notes"] == "Gate"
        assert world["calls"]["sms"] == []
        assert world["calls"]["email"] == []
        held = world["db"].email_outbox.docs
        assert len(held) == 1
        assert held[0]["subject"] == "Job updated"
        assert held[0]["audience"] == "shop"
        assert held[0]["to"] == "ana@example.com"
        assert "500 W Jefferson, Phoenix, AZ" in held[0]["body"]
        assert "Rio" in held[0]["body"]
        assert "->" in held[0]["body"] or "-&gt;" in held[0]["body"]

    asyncio.run(run())


def test_shop_token_cannot_change_price_or_zone(world):
    async def run():
        async with _client() as client:
            priced = await client.patch(
                "/api/portal/jobs/job-1", headers=_auth(world["shop"]), json={"price": 1},
            )
            zoned = await client.patch(
                "/api/portal/jobs/job-1", headers=_auth(world["shop"]), json={"zone": "east"},
            )
        assert priced.status_code == 400
        assert zoned.status_code == 400
        stored = await world["db"].jobs.find_one({"id": "job-1"})
        assert stored["price"] == 125.0
        assert stored["zone"] == "west"
        assert stored.get("edit_history") == []

    asyncio.run(run())


def test_shop_lists_only_its_own_jobs_and_cancel_skips_messages(world):
    async def run():
        async with _client() as client:
            listed = await client.get("/api/portal/jobs", headers=_auth(world["shop"]))
            assert listed.status_code == 200, listed.text
            ids = [job["id"] for job in listed.json()]
            assert "job-1" in ids
            assert "job-other" not in ids
            cancelled = await client.post("/api/portal/jobs/job-1/cancel", headers=_auth(world["shop"]))
            assert cancelled.status_code == 200, cancelled.text
            body = cancelled.json()
            assert body["status"] == "cancelled"
            assert body["cancellation_reason"] == "Cancelled by shop"
            assert "status" in body["edit_history"][-1]["fields"]
            assert body["edit_history"][-1]["who"]["name"] == "Glass Co"
            again = await client.get("/api/portal/jobs", headers=_auth(world["shop"]))
            again_ids = [job["id"] for job in again.json()]
            assert "job-1" in again_ids
            assert "job-other" not in again_ids
            foreign = await client.post("/api/portal/jobs/job-other/cancel", headers=_auth(world["shop"]))
            assert foreign.status_code == 404
            other_shop = await client.get("/api/portal/jobs", headers=_auth(world["other_shop"]))
            assert [job["id"] for job in other_shop.json()] == ["job-other"]
        assert world["calls"]["sms"] == []
        assert world["calls"]["email"] == []
        cancelled_mail = [row for row in world["db"].email_outbox.docs if row["subject"] == "Job cancelled"]
        assert len(cancelled_mail) == 1
        assert cancelled_mail[0]["audience"] == "shop"
        assert cancelled_mail[0]["to"] == "ana@example.com"
        assert "cancelled" in cancelled_mail[0]["body"].lower()
        other = await world["db"].jobs.find_one({"id": "job-other"})
        assert other["status"] == "booked"

    asyncio.run(run())


def test_shop_address_change_regeocodes_without_messages(world):
    async def run():
        async with _client() as client:
            response = await client.put(
                "/api/shops/shop-1",
                headers=_auth(world["owner"]),
                json={
                    "name": "Glass Co East",
                    "address": "200 E Main, Gilbert, AZ",
                    "contact_name": "Dana",
                    "contact_phone": "+16025550111",
                    "contact_email": "dana@glass.example",
                    "pricing_tier": "standard",
                },
            )
        assert response.status_code == 200, response.text
        shop = response.json()
        assert shop["name"] == "Glass Co East"
        assert shop["address"] == "200 E Main, Gilbert, AZ"
        assert shop["lat"] == 33.3062
        assert shop["lng"] == -111.8413
        assert shop["zone"] == "east"
        assert shop["status"] == "active"
        assert world["calls"]["geo"] == ["200 E Main, Gilbert, AZ"]
        assert world["calls"]["sms"] == []
        assert world["calls"]["email"] == []

    asyncio.run(run())


def _phoenix(day, hour, minute=0):
    moment = datetime.combine(day, time(hour, minute), tzinfo=BUSINESS_TZ)
    return moment.astimezone(timezone.utc)


def _park_tech(world):
    tech = next(row for row in world["db"].technicians.docs if row["id"] == "tech-2")
    tech["home_lat"] = 33.45
    tech["home_lng"] = -112.2
    tech["day_start"] = "08:00"
    return tech


def _sent_subjects(world):
    subjects = []
    for args, _kwargs in world["calls"]["email"]:
        subjects.append(args[1] if len(args) > 1 else "")
    return subjects


def test_shop_detail_edit_keeps_an_approved_early_job_booked(world):
    """Names, vehicle, VIN, and notes do not send the job back for approval."""
    early = _phoenix(date(2026, 11, 25), 7)
    _park_tech(world)
    job = world["db"].jobs.docs[0]
    job["scheduled_start"] = early.isoformat()
    job["scheduled_end"] = (early + timedelta(hours=1)).isoformat()
    job["status"] = "booked"
    job["approval_reason"] = None
    same_time = early.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    async def run():
        async with _client() as client:
            response = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={
                    "customer_last_name": "Patel",
                    "vehicle_vin": "1HGCM82633A004352",
                    "vehicle_make": "Honda",
                    "notes": "Side gate",
                    "job_address": job["job_address"],
                    "scheduled_start": same_time,
                    "calibration_type": "static",
                },
            )
        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved["status"] == "booked"
        assert saved["approval_reason"] is None
        assert saved["price"] == 125.0
        assert saved["customer_last_name"] == "Patel"
        assert saved["vehicle_vin"] == "1HGCM82633A004352"
        assert saved["notes"] == "Side gate"
        assert _sent_subjects(world) == []
        held = world["db"].email_outbox.docs
        assert len(held) == 1
        assert held[0]["subject"] == "Job updated"
        assert "Patel" in held[0]["body"]
        assert "1HGCM82633A004352" in held[0]["body"]
        assert "Side gate" in held[0]["body"]
        assert "Date and time" not in held[0]["body"]
        assert "Pending approval" not in held[0]["body"]

    asyncio.run(run())


def test_unchanged_shop_edit_sends_nothing(world):
    async def run():
        async with _client() as client:
            response = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={"notes": "Gate"},
            )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "booked"
        assert world["db"].email_outbox.docs == []
        assert _sent_subjects(world) == []

    asyncio.run(run())


def test_shop_service_change_uses_the_shop_rate_and_confirms_a_normal_time(world):
    shop = world["db"].shops.docs[0]
    shop["pricing_tier"] = "custom"
    shop["custom_rate_dual"] = 150

    async def run():
        async with _client() as client:
            response = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={"calibration_type": "dual"},
            )
        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved["status"] == "booked"
        assert saved["calibration_type"] == "dual"
        assert saved["calibration_label"] == "Dual ADAS Calibration"
        assert saved["price"] == 150
        assert saved["calibration_price"] == 150
        assert _sent_subjects(world) == []
        held = world["db"].email_outbox.docs
        assert len(held) == 1
        body = held[0]["body"]
        assert "Dual ADAS Calibration" in body
        assert "$125.00" in body
        assert "$150.00" in body

    asyncio.run(run())


def test_shop_move_before_8_needs_approval_and_emails_both_sides(world):
    _park_tech(world)
    early = _phoenix(date(2026, 11, 25), 7, 15)

    async def run():
        async with _client() as client:
            response = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={"scheduled_start": early.isoformat()},
            )
        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved["status"] == "requested"
        assert saved["approval_reason"] == "early_arrival"
        assert saved["price"] == 125.0
        subjects = _sent_subjects(world)
        assert len(subjects) == 1
        assert "Before 8:00" in subjects[0]
        held = world["db"].email_outbox.docs
        assert len(held) == 1
        assert held[0]["subject"] == "Job updated"
        assert held[0]["audience"] == "shop"
        assert "Pending approval" in held[0]["body"]
        assert "7:15 AM" in held[0]["body"]

    asyncio.run(run())


def test_shop_six_am_is_offered_pending_and_eight_am_confirms(world):
    _park_tech(world)
    day = date(2026, 11, 25)

    async def run():
        async with _client() as client:
            too_early = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={"scheduled_start": _phoenix(day, 5, 45).isoformat()},
            )
            assert too_early.status_code == 400
            assert "6:00" in too_early.json()["detail"]
            assert world["db"].email_outbox.docs == []
            stored = await world["db"].jobs.find_one({"id": "job-1"})
            assert stored["status"] == "booked"

            six = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={"scheduled_start": _phoenix(day, 6).isoformat()},
            )
            assert six.status_code == 200, six.text
            assert six.json()["status"] == "requested"
            assert six.json()["approval_reason"] == "early_arrival"

            eight = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={"scheduled_start": _phoenix(day, 8).isoformat()},
            )
            assert eight.status_code == 200, eight.text
            assert eight.json()["status"] == "booked"
            assert eight.json()["approval_reason"] is None

        owner_mail = _sent_subjects(world)
        assert len(owner_mail) == 1
        assert "Before 8:00" in owner_mail[0]
        shop_mail = world["db"].email_outbox.docs
        assert [row["subject"] for row in shop_mail] == ["Job updated", "Job updated"]

    asyncio.run(run())


def test_shop_cannot_move_onto_a_closed_day_or_outside_the_valley(world, monkeypatch):
    async def outside(address):
        return {"lat": 40.0, "lng": -105.0, "formatted_address": address, "in_metro": False}

    monkeypatch.setattr(server, "geocode_for_regeocode", outside)

    async def run():
        async with _client() as client:
            sunday = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={"scheduled_start": _phoenix(date(2026, 11, 22), 10).isoformat()},
            )
            assert sunday.status_code == 400
            assert "Sunday" in sunday.json()["detail"]
            thanksgiving = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={"scheduled_start": _phoenix(date(2026, 11, 26), 10).isoformat()},
            )
            assert thanksgiving.status_code == 400, thanksgiving.text
            assert "Thanksgiving" in thanksgiving.json()["detail"]
            valley = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={"job_address": "Outside the valley"},
            )
            assert valley.status_code == 400
            assert "outside" in valley.json()["detail"].lower()
        stored = await world["db"].jobs.find_one({"id": "job-1"})
        assert stored["status"] == "booked"
        assert stored["job_address"] == "100 W Main, Phoenix, AZ"
        assert stored["price"] == 125.0
        assert world["db"].email_outbox.docs == []
        assert _sent_subjects(world) == []

    asyncio.run(run())


def test_service_change_on_thanksgiving_is_rejected(world):
    day = date(2026, 11, 26)
    start = _phoenix(day, 10)
    job = world["db"].jobs.docs[0]
    job["scheduled_start"] = start.isoformat()
    job["scheduled_end"] = (start + timedelta(hours=1)).isoformat()

    async def run():
        async with _client() as client:
            response = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={"calibration_type": "dual"},
            )
        assert response.status_code == 400, response.text
        assert "Thanksgiving" in response.json()["detail"]
        stored = await world["db"].jobs.find_one({"id": "job-1"})
        assert stored["calibration_type"] == "static"
        assert stored["price"] == 125.0
        assert world["db"].email_outbox.docs == []

    asyncio.run(run())


def test_shop_cannot_double_book_a_time(world):
    _park_tech(world)
    start = _phoenix(date(2026, 11, 25), 10)
    world["db"].jobs.docs.append(_job(
        id="job-taken",
        technician_id="tech-2",
        scheduled_start=start.isoformat(),
        scheduled_end=(start + timedelta(minutes=20)).isoformat(),
        duration_minutes=20,
        job_lat=33.45,
        job_lng=-112.2,
    ))
    job = world["db"].jobs.docs[0]
    job["duration_minutes"] = 20
    job["scheduled_end"] = (datetime.fromisoformat(job["scheduled_start"]) + timedelta(minutes=20)).isoformat()

    async def run():
        async with _client() as client:
            response = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={"scheduled_start": start.isoformat()},
            )
        assert response.status_code == 400, response.text
        assert "overlap" in response.json()["detail"].lower()
        stored = await world["db"].jobs.find_one({"id": "job-1"})
        assert stored["scheduled_start"] != start.isoformat()
        assert world["db"].email_outbox.docs == []

    asyncio.run(run())


def test_same_day_addon_is_held_and_an_empty_today_confirms(world, monkeypatch):
    day = date(2026, 11, 18)
    morning = _phoenix(day, 9)
    monkeypatch.setattr(server, "now_utc", lambda: morning)
    tech = _park_tech(world)
    tech["home_lat"] = 33.3528
    tech["home_lng"] = -111.7890
    nine = _phoenix(day, 9)
    world["db"].jobs.docs.append(_job(
        id="job-eag",
        technician_id="tech-2",
        scheduled_start=nine.isoformat(),
        scheduled_end=(nine + timedelta(minutes=20)).isoformat(),
        duration_minutes=20,
        job_lat=33.4372,
        job_lng=-111.8210,
        job_address="855 East Brown Road, Mesa, AZ",
    ))
    job = world["db"].jobs.docs[0]
    job["scheduled_start"] = _phoenix(day, 14).isoformat()
    job["scheduled_end"] = _phoenix(day, 15).isoformat()
    job["duration_minutes"] = 20
    job["job_lat"] = 33.3528
    job["job_lng"] = -111.7890

    async def geo(address):
        if "goodyear" in address.lower():
            return {"lat": 33.4353, "lng": -112.3576, "formatted_address": address, "in_metro": True}
        return {"lat": 33.3528, "lng": -111.7890, "formatted_address": address, "in_metro": True}

    monkeypatch.setattr(server, "geocode_for_regeocode", geo)

    async def run():
        async with _client() as client:
            addon = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={
                    "job_address": "Goodyear shop",
                    "scheduled_start": _phoenix(day, 11).isoformat(),
                },
            )
            assert addon.status_code == 200, addon.text
            assert addon.json()["status"] == "requested"
            assert addon.json()["approval_reason"] == "same_day_addon"
            # Drop the other stop and move this one back beside home. An empty
            # today confirms a normal time.
            world["db"].jobs.docs[:] = [row for row in world["db"].jobs.docs if row["id"] != "job-eag"]
            job_doc = next(row for row in world["db"].jobs.docs if row["id"] == "job-1")
            job_doc["job_lat"] = 33.3528
            job_doc["job_lng"] = -111.7890
            job_doc["job_address"] = "Gilbert home"
            plain = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={
                    "job_address": "Gilbert home",
                    "scheduled_start": _phoenix(day, 10).isoformat(),
                },
            )
            assert plain.status_code == 200, plain.text
            assert plain.json()["status"] == "booked"
            assert plain.json()["approval_reason"] is None
            late = morning.replace(hour=20, minute=30)
            monkeypatch.setattr(server, "now_utc", lambda: late)
            closed = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={"scheduled_start": _phoenix(day, 15).isoformat()},
            )
            assert closed.status_code == 400, closed.text
            assert "1:00 PM" in closed.json()["detail"]

        subjects = _sent_subjects(world)
        assert any("Same-day" in subject for subject in subjects)
        assert len(world["db"].email_outbox.docs) == 2

    asyncio.run(run())


def test_owner_edit_does_not_email_the_shop(world):
    _park_tech(world)
    early = _phoenix(date(2026, 11, 25), 7)

    async def run():
        async with _client() as client:
            response = await client.patch(
                "/api/jobs/job-1",
                headers=_auth(world["owner"]),
                json={"scheduled_start": early.isoformat(), "notes": "Owner moved it"},
            )
            cancelled = await client.post(
                "/api/jobs/job-other/cancel",
                headers=_auth(world["owner"]),
                json={"reason": "Customer requested"},
            )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "booked"
        assert response.json()["notes"] == "Owner moved it"
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["cancellation_reason"] == "Customer requested"
        shop_notes = [
            row for row in world["db"].email_outbox.docs
            if row["subject"] in ("Job updated", "Job cancelled")
        ]
        assert shop_notes == []
        assert _sent_subjects(world) == []

    asyncio.run(run())


def test_early_service_change_goes_back_to_requested(world):
    _park_tech(world)
    early = _phoenix(date(2026, 11, 25), 7)
    job = world["db"].jobs.docs[0]
    job["scheduled_start"] = early.isoformat()
    job["scheduled_end"] = (early + timedelta(hours=1)).isoformat()
    job["status"] = "booked"
    job["approval_reason"] = None

    async def run():
        async with _client() as client:
            response = await client.patch(
                "/api/portal/jobs/job-1",
                headers=_auth(world["shop"]),
                json={"calibration_type": "dual"},
            )
        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved["status"] == "requested"
        assert saved["approval_reason"] == "early_arrival"
        assert saved["price"] == 175
        assert saved["calibration_label"] == "Dual ADAS Calibration"
        assert any("Before 8:00" in subject for subject in _sent_subjects(world))
        assert len(world["db"].email_outbox.docs) == 1
        assert "$175.00" in world["db"].email_outbox.docs[0]["body"]

    asyncio.run(run())
