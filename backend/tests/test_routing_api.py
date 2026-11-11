"""Owner-only technician setup, and one tech can book both sides of the valley."""
import asyncio
import os
import sys
from datetime import timedelta

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from business_time import business_date  # noqa: E402


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
                return {k: v for k, v in doc.items() if k != "_id" and k != "password_hash"}
        return None

    def find(self, query, projection=None):
        return _Cursor([{k: v for k, v in doc.items() if k != "password_hash"} for doc in self.docs if _match(doc, query)])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update):
        for doc in self.docs:
            if _match(doc, query):
                doc.update(update.get("$set", {}))


class _DB:
    def __init__(self):
        self.technicians = _Store()
        self.shops = _Store()
        self.jobs = _Store()


def test_owner_adds_a_tech_and_one_tech_books_both_sides(monkeypatch):
    db = _DB()
    db.technicians.docs.append({
        "id": "caleb", "name": "Caleb", "role": "owner", "is_active": True, "routes_jobs": True,
        "home_address": "Gilbert, AZ", "home_lat": 33.3528, "home_lng": -111.7890,
        "color": "#FF5F1F", "day_start": "08:00", "day_end": "19:00",
        "slot_minutes": 45, "max_jobs": 14,
    })
    db.technicians.docs.append({"id": "west", "name": "West", "role": "contractor", "is_active": True})
    db.shops.docs.append({"id": "shop-1", "booking_link_token": "tok", "status": "active"})
    calls = {"sms": [], "geo": []}

    async def sms(*args, **kwargs):
        calls["sms"].append(args)

    async def geo(address):
        calls["geo"].append(address)
        if "Peoria" in address:
            return {"lat": 33.5806, "lng": -112.2374, "formatted_address": address, "in_metro": True}
        return {"lat": 33.45, "lng": -112.07, "formatted_address": address, "in_metro": True}

    async def drive(*args, **kwargs):
        return {"distance_miles": 10, "duration_minutes": 20}

    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "mock_send_sms", sms)
    monkeypatch.setattr(server, "send_email", sms)
    monkeypatch.setattr(server, "geocode_for_regeocode", geo)
    monkeypatch.setattr(server, "geocode_address", geo)
    monkeypatch.setattr(server, "get_drive_time", drive)
    owner = server.make_token("caleb", "owner")
    contractor = server.make_token("west", "contractor")

    day = business_date() + timedelta(days=1)
    if day.weekday() == 6:
        day = day + timedelta(days=1)

    async def run():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            denied = await client.post(
                "/api/routing-techs",
                headers={"Authorization": f"Bearer {contractor}"},
                json={"name": "Pat", "home_address": "Peoria, AZ"},
            )
            assert denied.status_code == 403
            created = await client.post(
                "/api/routing-techs",
                headers={"Authorization": f"Bearer {owner}"},
                json={"name": "Pat", "home_address": "Peoria, AZ", "service_radius_miles": 20},
            )
            assert created.status_code == 200, created.text
            body = created.json()
            assert body["home_lat"] == 33.5806
            assert body["role"] == "technician"
            assert calls["sms"] == []
            # Deactivate the new hire so the valley is one tech again for the slot check.
            off = await client.put(
                f"/api/routing-techs/{body['id']}",
                headers={"Authorization": f"Bearer {owner}"},
                json={"is_active": False},
            )
            assert off.status_code == 200, off.text
            goodyear = await client.post("/api/public/availability", json={
                "booking_token": "tok", "job_address": "Goodyear, AZ", "date": day.isoformat(),
            })
            mesa = await client.post("/api/public/availability", json={
                "booking_token": "tok", "job_address": "Mesa, AZ", "date": day.isoformat(),
            })
        assert goodyear.status_code == 200, goodyear.text
        assert mesa.status_code == 200, mesa.text
        assert goodyear.json()["slots"], "west-side address should still have slots"
        assert mesa.json()["slots"], "east-side address should still have slots"
        assert goodyear.json()["technician_id"] == "caleb"
        assert mesa.json()["technician_id"] == "caleb"
        assert calls["sms"] == []

    asyncio.run(run())
