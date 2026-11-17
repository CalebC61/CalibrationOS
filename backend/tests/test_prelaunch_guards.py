"""Pre-launch guards: a shop sees only its own day, sign-in is limited, and a
cached geocode does not put a business name back on the street.

    cd backend && pytest tests/test_prelaunch_guards.py -v
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
from business_time import business_date, business_day_bounds  # noqa: E402
from onboarding import (  # noqa: E402
    CONTACT_ATTEMPT_LIMIT,
    CONTACT_LIMIT_MESSAGE,
    FORGOT_ATTEMPT_LIMIT,
    FORGOT_LIMIT_MESSAGE,
    GEOCODE_ATTEMPT_LIMIT,
    GEOCODE_LIMIT_MESSAGE,
    LOGIN_ATTEMPT_LIMIT,
    LOGIN_LIMIT_MESSAGE,
    reset_rate_limits,
)
from route_cost import normalize_address  # noqa: E402

STREET = "1 E Washington St, Phoenix, AZ 85004, USA"
BUSINESS = "Downtown Phoenix Inc, " + STREET
SUITE = "Suite 200, " + STREET


@pytest.fixture(autouse=True)
def _clear_limits():
    reset_rate_limits()
    yield
    reset_rate_limits()


def _match(doc, query):
    for key, expected in query.items():
        value = doc.get(key)
        if isinstance(expected, dict):
            for op, operand in expected.items():
                if op == "$gte":
                    ok = value is not None and value >= operand
                elif op == "$lt":
                    ok = value is not None and value < operand
                elif op == "$nin":
                    ok = value not in operand
                elif op == "$in":
                    ok = value in operand
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
        return out
    for key, flag in projection.items():
        if flag == 0:
            out.pop(key, None)
    return out


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

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _match(doc, query):
                doc.update(update.get("$set", {}))
                return
        if upsert:
            self.docs.append({"_id": query.get("_id"), **update.get("$set", {})})


class _DB:
    def __init__(self):
        self.technicians = _Store()
        self.shops = _Store()
        self.shop_users = _Store()
        self.jobs = _Store()
        self.password_resets = _Store()
        self.geocode_cache = _Store()


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test")


def _day_jobs():
    day = business_date() + timedelta(days=2)
    if day.weekday() == 6:
        day = day + timedelta(days=1)
    start, _end = business_day_bounds(day)
    when = (start + timedelta(hours=4)).isoformat()
    done = (start + timedelta(hours=5)).isoformat()
    return day, when, done


def test_day_map_shows_the_route_and_strips_other_shops(monkeypatch):
    db = _DB()
    day, when, done = _day_jobs()
    later = (business_day_bounds(day)[0] + timedelta(hours=6)).isoformat()
    later_end = (business_day_bounds(day)[0] + timedelta(hours=7)).isoformat()
    db.shop_users.docs.extend([
        {"id": "su-a", "shop_id": "shop-a", "full_name": "Ada", "is_active": True},
        {"id": "su-new", "shop_id": "shop-new", "full_name": "New", "is_active": True},
    ])
    db.jobs.docs.extend([
        {
            "id": "job-own", "shop_id": "shop-a", "status": "booked",
            "sequence_order": 2,
            "scheduled_start": later, "scheduled_end": later_end,
            "job_address": STREET, "job_lat": 33.448093, "job_lng": -112.072849,
            "customer_last_name": "Ng", "customer_first_name": "Ada",
            "shop_name": "Ada Glass",
            "vehicle_year": 2022, "vehicle_make": "Honda", "vehicle_model": "Civic",
            "vehicle_vin": "1HGCM82633A123456",
            "notification_phone": "+14805550100", "notes": "Use the side gate",
            "price": 125,
        },
        {
            "id": "job-cancelled", "shop_id": "shop-a", "status": "cancelled",
            "sequence_order": 9,
            "scheduled_start": when, "scheduled_end": done,
            "job_address": "cancelled own", "job_lat": 33.45, "job_lng": -112.08,
        },
        {
            "id": "job-secret", "shop_id": "shop-b", "status": "booked",
            "sequence_order": 1,
            "scheduled_start": when, "scheduled_end": done,
            "job_address": "SECRET-OTHER-ADDRESS",
            "job_lat": 33.111111, "job_lng": -111.222222,
            "customer_last_name": "SecretOther", "customer_first_name": "Hidden",
            "shop_name": "Secret Shop",
            "vehicle_year": 2019, "vehicle_make": "SecretMake", "vehicle_model": "SecretModel",
            "vehicle_vin": "SECRETVIN123456789",
            "notification_phone": "+16025550999", "notes": "SECRET-NOTES",
            "price": 225,
        },
    ])

    monkeypatch.setattr(server, "db", db)
    token = server.make_portal_token("su-a")
    fresh = server.make_portal_token("su-new")
    quiet = (day + timedelta(days=3)).isoformat()

    async def run():
        async with _client() as client:
            mine = await client.get(
                f"/api/portal/day-map?date_str={day.isoformat()}",
                headers={"Authorization": f"Bearer {token}"},
            )
            seen = await client.get(
                f"/api/portal/day-map?date_str={day.isoformat()}",
                headers={"Authorization": f"Bearer {fresh}"},
            )
            empty = await client.get(
                f"/api/portal/day-map?date_str={quiet}",
                headers={"Authorization": f"Bearer {fresh}"},
            )
            return mine, seen, empty

    mine, seen, empty = asyncio.run(run())
    assert mine.status_code == 200, mine.text
    body = mine.json()
    assert [job["id"] for job in body["own"]] == ["job-own"]
    own_job = body["own"][0]
    assert own_job["route_order"] == 2
    assert own_job["customer_last_name"] == "Ng"
    assert own_job["vehicle_make"] == "Honda"
    assert own_job["vehicle_vin"] == "1HGCM82633A123456"
    assert own_job["job_address"] == STREET
    assert own_job["status"] == "booked"
    assert own_job["price"] == 125
    assert own_job["scheduled_start"] == later
    assert own_job["scheduled_end"] == later_end
    assert body["others"] == [{
        "route_order": 1,
        "arrival_start": when,
        "arrival_end": done,
        "job_lat": 33.111,
        "job_lng": -111.222,
    }]
    leaked = (
        "SECRET-OTHER-ADDRESS", "SecretOther", "Secret Shop", "SecretMake",
        "SECRETVIN", "SECRET-NOTES", "+16025550999", "job-secret", "33.111111",
        "-111.222222", "225",
    )
    for secret in leaked:
        assert secret not in mine.text
    assert "cancelled own" not in mine.text

    assert seen.status_code == 200, seen.text
    stranger = seen.json()
    assert stranger["own"] == []
    assert [stop["route_order"] for stop in stranger["others"]] == [1, 2]
    assert stranger["others"][1]["job_lat"] == 33.448
    assert stranger["others"][1]["job_lng"] == -112.073
    for secret in ("Ng", "Honda", "Ada Glass", STREET, "job-own", "1HGCM82633A123456", "Use the side gate"):
        assert secret not in seen.text

    assert empty.status_code == 200, empty.text
    assert empty.json() == {"own": [], "others": [], "date": quiet}


def _staff(db):
    db.technicians.docs.append({
        "id": "tech-1", "email": "owner@example.com", "name": "Caleb", "role": "owner",
        "is_active": True, "password_hash": server.hash_password("correct-horse"),
    })


def _shop_user(db):
    db.shop_users.docs.append({
        "id": "su-1", "shop_id": "shop-1", "email": "ada@shop.example",
        "full_name": "Ada", "shop_name": "Ada Glass", "is_active": True,
        "password_hash": server.hash_password("correct-horse"),
    })


def test_staff_login_locks_after_repeated_attempts(monkeypatch):
    db = _DB()
    _staff(db)
    monkeypatch.setattr(server, "db", db)

    async def run():
        async with _client() as client:
            headers = {"X-Forwarded-For": "203.0.113.10"}
            ok = await client.post(
                "/api/auth/login",
                headers=headers,
                json={"email": "owner@example.com", "password": "correct-horse"},
            )
            wrong = []
            for _ in range(LOGIN_ATTEMPT_LIMIT - 1):
                wrong.append(await client.post(
                    "/api/auth/login",
                    headers=headers,
                    json={"email": "owner@example.com", "password": "nope"},
                ))
            locked = await client.post(
                "/api/auth/login",
                headers=headers,
                json={"email": "owner@example.com", "password": "correct-horse"},
            )
            other_email = await client.post(
                "/api/auth/login",
                headers=headers,
                json={"email": "someone@example.com", "password": "nope"},
            )
            same_email = await client.post(
                "/api/auth/login",
                headers={"X-Forwarded-For": "203.0.113.11"},
                json={"email": "owner@example.com", "password": "correct-horse"},
            )
            fresh = await client.post(
                "/api/auth/login",
                headers={"X-Forwarded-For": "203.0.113.12"},
                json={"email": "other@example.com", "password": "nope"},
            )
            return ok, wrong, locked, other_email, same_email, fresh

    ok, wrong, locked, other_email, same_email, fresh = asyncio.run(run())
    assert ok.status_code == 200, ok.text
    assert [item.status_code for item in wrong] == [401] * (LOGIN_ATTEMPT_LIMIT - 1)
    assert locked.status_code == 429
    assert locked.json()["detail"] == LOGIN_LIMIT_MESSAGE
    assert other_email.status_code == 429
    assert same_email.status_code == 429
    assert same_email.json()["detail"] == LOGIN_LIMIT_MESSAGE
    assert fresh.status_code == 401


def test_portal_login_locks_with_the_same_message(monkeypatch):
    db = _DB()
    _shop_user(db)
    monkeypatch.setattr(server, "db", db)

    async def run():
        async with _client() as client:
            headers = {"X-Forwarded-For": "203.0.113.20"}
            codes = []
            for _ in range(LOGIN_ATTEMPT_LIMIT):
                response = await client.post(
                    "/api/portal/auth/login",
                    headers=headers,
                    json={"email": "ada@shop.example", "password": "nope"},
                )
                codes.append(response.status_code)
            locked = await client.post(
                "/api/portal/auth/login",
                headers=headers,
                json={"email": "ada@shop.example", "password": "correct-horse"},
            )
            return codes, locked

    codes, locked = asyncio.run(run())
    assert codes == [401] * LOGIN_ATTEMPT_LIMIT
    assert locked.status_code == 429
    assert locked.json()["detail"] == LOGIN_LIMIT_MESSAGE


def test_forgot_password_locks_before_another_email(monkeypatch):
    db = _DB()
    _shop_user(db)
    sent = []

    async def send(payload, audience):
        sent.append(payload)
        return {"delivered": False}

    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "_send_booking_message", send)

    async def run():
        async with _client() as client:
            headers = {"X-Forwarded-For": "203.0.113.30"}
            first = await client.post(
                "/api/portal/auth/forgot-password",
                headers=headers,
                json={"email": "ada@shop.example"},
            )
            for _ in range(FORGOT_ATTEMPT_LIMIT - 1):
                await client.post(
                    "/api/portal/auth/forgot-password",
                    headers=headers,
                    json={"email": "ada@shop.example"},
                )
            locked = await client.post(
                "/api/portal/auth/forgot-password",
                headers={"X-Forwarded-For": "203.0.113.31"},
                json={"email": "ada@shop.example"},
            )
            return first, locked

    first, locked = asyncio.run(run())
    assert first.status_code == 200, first.text
    assert "reset link" in first.json()["message"].lower()
    assert len(sent) == FORGOT_ATTEMPT_LIMIT
    assert locked.status_code == 429
    assert locked.json()["detail"] == FORGOT_LIMIT_MESSAGE
    assert len(sent) == FORGOT_ATTEMPT_LIMIT
    assert len(db.password_resets.docs) == FORGOT_ATTEMPT_LIMIT


def test_public_geocode_and_contact_are_rate_limited(monkeypatch):
    sent = []

    async def geocode(address):
        return {
            "lat": 33.35, "lng": -111.79,
            "formatted_address": "100 W Guadalupe Rd, Gilbert, AZ 85233, USA",
            "in_metro": True, "partial_match": False, "location_type": "ROOFTOP",
            "source": "google",
        }

    async def send_email(to, subject, html, kind="transactional", meta=None, reply_to=None):
        sent.append(subject)
        return {"delivered": False}

    monkeypatch.setattr(server, "geocode_address", geocode)
    monkeypatch.setattr(server, "send_email", send_email)

    async def run():
        async with _client() as client:
            geo_headers = {"X-Forwarded-For": "203.0.113.40"}
            geos = []
            for _ in range(GEOCODE_ATTEMPT_LIMIT):
                geos.append(await client.post(
                    "/api/geocode", headers=geo_headers, json={"address": "Gilbert, AZ"},
                ))
            geo_locked = await client.post(
                "/api/geocode", headers=geo_headers, json={"address": "Gilbert, AZ"},
            )
            contact_headers = {"X-Forwarded-For": "203.0.113.41"}
            notes = []
            for _ in range(CONTACT_ATTEMPT_LIMIT):
                notes.append(await client.post(
                    "/api/public/contact",
                    headers=contact_headers,
                    json={"name": "Ada", "email": "ada@shop.example", "message": "Hello"},
                ))
            note_locked = await client.post(
                "/api/public/contact",
                headers={"X-Forwarded-For": "203.0.113.42"},
                json={"name": "Ada", "email": "ada@shop.example", "message": "Again"},
            )
            return geos, geo_locked, notes, note_locked

    geos, geo_locked, notes, note_locked = asyncio.run(run())
    assert [item.status_code for item in geos] == [200] * GEOCODE_ATTEMPT_LIMIT
    assert geo_locked.status_code == 429
    assert geo_locked.json()["detail"] == GEOCODE_LIMIT_MESSAGE
    assert [item.status_code for item in notes] == [200] * CONTACT_ATTEMPT_LIMIT
    assert len(sent) == CONTACT_ATTEMPT_LIMIT
    assert note_locked.status_code == 429
    assert note_locked.json()["detail"] == CONTACT_LIMIT_MESSAGE
    assert len(sent) == CONTACT_ATTEMPT_LIMIT


def _pin(formatted):
    return {
        "_id": normalize_address(formatted),
        "lat": 33.448093, "lng": -112.072849,
        "formatted_address": formatted,
        "in_metro": True, "partial_match": False, "location_type": "ROOFTOP",
        "source": "google",
    }


def test_geocode_cache_hit_strips_a_business_name_and_keeps_a_suite(monkeypatch):
    db = _DB()
    db.geocode_cache.docs.extend([
        _pin(BUSINESS),
        _pin("Downtown Phoenix, Inc., " + STREET),
        _pin(SUITE),
        _pin(STREET),
    ])
    calls = []

    def fetch(address):
        calls.append(address)
        raise AssertionError("a cache hit must not call Google")

    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "google_maps_enabled", lambda: True)
    monkeypatch.setattr(server, "_google_geocode_request", fetch)

    async def run():
        business = await server.geocode_address(BUSINESS)
        comma = await server.geocode_address("Downtown Phoenix, Inc., " + STREET)
        suite = await server.geocode_address(SUITE)
        plain = await server.geocode_address(STREET)
        return business, comma, suite, plain

    business, comma, suite, plain = asyncio.run(run())
    assert business["formatted_address"] == STREET
    assert comma["formatted_address"] == STREET
    assert suite["formatted_address"] == SUITE
    assert plain["formatted_address"] == STREET
    assert business["lat"] == 33.448093
    assert calls == []


def test_a_cached_business_name_is_saved_as_the_street(monkeypatch):
    db = _DB()
    db.technicians.docs.append({"id": "caleb", "role": "owner", "name": "Caleb"})
    db.geocode_cache.docs.append(_pin(BUSINESS))

    def fetch(address):
        raise AssertionError("a cache hit must not call Google")

    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "google_maps_enabled", lambda: True)
    monkeypatch.setattr(server, "_google_geocode_request", fetch)
    owner = server.make_token("caleb", "owner")

    async def run():
        async with _client() as client:
            return await client.post(
                "/api/shops",
                headers={"Authorization": f"Bearer {owner}"},
                json={
                    "name": "Downtown Glass",
                    "address": BUSINESS,
                    "contact_name": "Ada",
                    "contact_phone": "4805550100",
                    "contact_email": "ada@downtown.example",
                    "place_id": "ChIJdowntown",
                },
            )

    response = asyncio.run(run())
    assert response.status_code == 200, response.text
    shop = db.shops.docs[0]
    assert shop["address"] == STREET
    assert shop["formatted_address"] == STREET
    assert shop["lat"] == 33.448093
    assert shop["lng"] == -112.072849
