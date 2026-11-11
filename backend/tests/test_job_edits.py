"""PATCH job edits for the owner and for a shop booking token.

No live Mongo. The routes run against an in-memory store:
    cd backend && pytest tests/test_job_edits.py -v
"""
import asyncio
import os
import sys
from datetime import timedelta

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from business_time import business_day_bounds, business_date  # noqa: E402

TODAY = business_date()
TODAY_START, _TODAY_END = business_day_bounds(TODAY)
# 10:00 AM Phoenix the next day. Midnight Phoenix is TODAY_START (07:00 UTC).
FUTURE = (TODAY_START + timedelta(days=1, hours=10)).isoformat()
FUTURE_END = (TODAY_START + timedelta(days=1, hours=11)).isoformat()
PAST = (TODAY_START - timedelta(days=2)).isoformat()


def _match(doc, query):
    for key, expected in query.items():
        if doc.get(key) != expected:
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
        self.jobs = _Store()
        self.vehicles = _Store()


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
    db.shops.docs.append(_shop(id="shop-2", name="Other Shop", booking_link_token="tok-b"))
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
           "technician": server.make_token("tech-3", "technician")}
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
        assert job["notification_phone"] == "+16025550999"
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


def test_shop_token_edits_only_its_own_jobs(world):
    async def run():
        async with _client() as client:
            ok = await client.patch(
                "/api/public/bookings/tok-a/job-1",
                json={"job_address": "500 W Jefferson, Phoenix, AZ", "customer_first_name": "Rio"},
            )
            foreign = await client.patch(
                "/api/public/bookings/tok-a/job-other",
                json={"notes": "should not land"},
            )
            missing = await client.patch(
                "/api/public/bookings/not-a-token/job-1",
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
        assert missing.status_code == 404
        other = await world["db"].jobs.find_one({"id": "job-other"})
        assert other["notes"] == "Gate"
        assert world["calls"]["sms"] == []
        assert world["calls"]["email"] == []

    asyncio.run(run())


def test_shop_token_cannot_change_price_or_zone(world):
    async def run():
        async with _client() as client:
            priced = await client.patch("/api/public/bookings/tok-a/job-1", json={"price": 1})
            zoned = await client.patch("/api/public/bookings/tok-a/job-1", json={"zone": "east"})
        assert priced.status_code == 400
        assert zoned.status_code == 400
        stored = await world["db"].jobs.find_one({"id": "job-1"})
        assert stored["price"] == 125.0
        assert stored["zone"] == "west"
        assert stored.get("edit_history") == []

    asyncio.run(run())


def test_shop_lists_only_its_upcoming_jobs_and_cancel_skips_messages(world):
    async def run():
        async with _client() as client:
            listed = await client.get("/api/public/bookings/tok-a")
            assert listed.status_code == 200, listed.text
            ids = [job["id"] for job in listed.json()]
            assert ids == ["job-1"]
            cancelled = await client.post("/api/public/bookings/tok-a/job-1/cancel")
            assert cancelled.status_code == 200, cancelled.text
            body = cancelled.json()
            assert body["status"] == "cancelled"
            assert "status" in body["edit_history"][-1]["fields"]
            assert body["edit_history"][-1]["who"]["name"] == "Glass Co"
            again = await client.get("/api/public/bookings/tok-a")
            assert again.json() == []
            foreign = await client.post("/api/public/bookings/tok-a/job-other/cancel")
            assert foreign.status_code == 404
        assert world["calls"]["sms"] == []
        assert world["calls"]["email"] == []
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
