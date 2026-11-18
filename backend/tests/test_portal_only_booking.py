"""Shops book only after they log in. A booking-link token is not a login.

No live Mongo. The routes run against an in-memory store:
    cd backend && pytest tests/test_portal_only_booking.py -v
"""
import asyncio
import os
import sys
from datetime import timedelta

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from business_time import business_day_bounds, business_date  # noqa: E402
from onboarding import READY_BILLING, invite_email_html, welcome_email_html  # noqa: E402

TODAY_START, _TODAY_END = business_day_bounds(business_date())
FUTURE = (TODAY_START + timedelta(days=1, hours=10)).isoformat()
FUTURE_END = (TODAY_START + timedelta(days=1, hours=11)).isoformat()

SECRET_NAME = "Secretcustomer"
SECRET_PHONE = "(480) 555-0199"
SECRET_VIN = "1HGCM82633A004352"
SECRET_ADDRESS = "900 Hidden Ln, Gilbert, AZ"


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
            continue
        if value != expected:
            return False
    return True


def _project(doc, projection):
    out = {k: v for k, v in doc.items() if k != "_id"}
    if not projection:
        return out
    if any(v == 0 for v in projection.values()):
        for key, flag in projection.items():
            if flag == 0 and key != "_id":
                out.pop(key, None)
        return out
    return {k: out[k] for k in projection if k in out}


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
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return _project(doc, projection)
        return None

    def find(self, query, projection=None):
        return _Cursor([_project(doc, projection) for doc in self.docs if _match(doc, query)])

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
        self.documents = _Store()
        self.new_booking_alerts = _Store()


def _shop(shop_id, name, token):
    return {
        "id": shop_id,
        "name": name,
        "status": "active",
        "booking_link_token": token,
        "address": "100 W Main, Gilbert, AZ",
        "zone": "east",
        "pricing_tier": "standard",
        **READY_BILLING,
    }


def _user(user_id, shop_id, **overrides):
    doc = {
        "id": user_id,
        "shop_id": shop_id,
        "full_name": "Dana",
        "email": f"{user_id}@glass.example",
        "is_active": True,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    doc.update(overrides)
    return doc


def _job(job_id, shop_id, shop_name, last_name=SECRET_NAME):
    return {
        "id": job_id,
        "shop_id": shop_id,
        "shop_name": shop_name,
        "status": "booked",
        "job_address": SECRET_ADDRESS,
        "job_lat": 33.35,
        "job_lng": -111.79,
        "zone": "east",
        "customer_last_name": last_name,
        "customer_first_name": "Pat",
        "notification_phone": SECRET_PHONE,
        "vehicle_vin": SECRET_VIN,
        "vehicle_year": 2022,
        "vehicle_make": "Honda",
        "vehicle_model": "Civic",
        "calibration_label": "Static ADAS Calibration",
        "calibration_type": "static",
        "price": 125.0,
        "scheduled_start": FUTURE,
        "scheduled_end": FUTURE_END,
        "notes": "Gate code",
        "edit_history": [],
    }


def _world(monkeypatch):
    db = _DB()
    db.technicians.docs.append({"id": "tech-owner", "role": "owner", "name": "Caleb"})
    db.technicians.docs.append({"id": "tech-field", "role": "technician", "name": "Field"})
    db.shops.docs.append(_shop("shop-a", "Shop A", "token-a"))
    db.shops.docs.append(_shop("shop-b", "Shop B", "token-b"))
    db.shop_users.docs.append(_user("user-a", "shop-a"))
    db.shop_users.docs.append(_user("user-b", "shop-b"))
    db.jobs.docs.append(_job("job-a", "shop-a", "Shop A", "Ng"))
    db.jobs.docs.append(_job("job-b", "shop-b", "Shop B"))
    monkeypatch.setattr(server, "db", db)
    return db


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test")


def _portal(user_id):
    return {"Authorization": f"Bearer {server.make_portal_token(user_id)}"}


def _owner():
    return {"Authorization": f"Bearer {server.make_token('tech-owner', 'owner')}"}


BOOK = {
    "booking_token": "token-b",
    "job_address": "100 W Main, Gilbert, AZ",
    "scheduled_start": FUTURE,
    "customer_last_name": "Ng",
    "year": 2024,
    "make": "Subaru",
    "model": "Outback",
    "adas_system": "forward_camera",
    "calibration_type": "static",
    "notification_phone": "4805550100",
}


def test_public_token_routes_do_not_return_job_data(monkeypatch):
    _world(monkeypatch)

    async def run():
        async with _client() as client:
            shop = await client.get("/api/public/shop/token-b")
            avail = await client.post("/api/public/availability", json={
                "booking_token": "token-b", "job_address": SECRET_ADDRESS, "date": "2026-11-20",
            })
            booked = await client.post("/api/public/book", json=BOOK)
            listed = await client.get("/api/public/bookings/token-b")
            edited = await client.patch("/api/public/bookings/token-b/job-b", json={"notes": "stolen"})
            cancelled = await client.post("/api/public/bookings/token-b/job-b/cancel")
            score = await client.get("/api/public/shop-status/token-b")
            return shop, avail, booked, listed, edited, cancelled, score

    responses = asyncio.run(run())
    for response in responses:
        assert response.status_code == 404, response.text
        body = response.text
        assert SECRET_NAME not in body
        assert SECRET_PHONE not in body
        assert SECRET_VIN not in body
        assert SECRET_ADDRESS not in body
        assert "job-b" not in body


def test_portal_booking_still_requires_a_card_and_accepted_terms(monkeypatch):
    db = _world(monkeypatch)
    bare = _shop("shop-a", "Shop A", "token-a")
    bare.pop("stripe_payment_method_id")
    bare["card_status"] = None
    db.shops.docs[0] = bare

    async def run():
        async with _client() as client:
            missing = await client.post("/api/portal/book", json=BOOK, headers=_portal("user-a"))
            bare["stripe_payment_method_id"] = "pm_ready"
            bare["card_brand"] = "visa"
            bare["card_last4"] = "4242"
            bare["card_exp_month"] = 12
            bare["card_exp_year"] = 2099
            bare["card_status"] = "active"
            bare["charge_authorization_accepted_at"] = None
            db.shop_users.docs[0]["charge_authorization_accepted_at"] = None
            terms = await client.post("/api/portal/book", json=BOOK, headers=_portal("user-a"))
            return missing, terms

    missing, terms = asyncio.run(run())
    assert missing.status_code == 403, missing.text
    assert "Settings" in missing.json()["detail"]
    assert terms.status_code == 403, terms.text
    assert "terms" in terms.json()["detail"].lower()
    assert db.jobs.docs[0]["id"] == "job-a"
    assert len(db.jobs.docs) == 2


def test_one_shop_cannot_see_or_change_another_shops_jobs(monkeypatch):
    db = _world(monkeypatch)

    async def quiet(*args, **kwargs):
        return None

    monkeypatch.setattr(server, "send_email", quiet)
    monkeypatch.setattr(server, "mock_send_sms", quiet)

    async def run():
        async with _client() as client:
            listed = await client.get("/api/portal/jobs", headers=_portal("user-a"))
            foreign_job = await client.get("/api/portal/jobs/job-b", headers=_portal("user-a"))
            foreign_edit = await client.patch(
                "/api/portal/jobs/job-b", headers=_portal("user-a"), json={"notes": "stolen"},
            )
            foreign_cancel = await client.post("/api/portal/jobs/job-b/cancel", headers=_portal("user-a"))
            own_edit = await client.patch(
                "/api/portal/jobs/job-a", headers=_portal("user-a"), json={"notes": "Use the side gate"},
            )
            score_a = await client.get("/api/portal/scorecard", headers=_portal("user-a"))
            anonymous = await client.get("/api/portal/jobs/job-a")
            return listed, foreign_job, foreign_edit, foreign_cancel, own_edit, score_a, anonymous

    listed, foreign_job, foreign_edit, foreign_cancel, own_edit, score_a, anonymous = asyncio.run(run())
    assert listed.status_code == 200, listed.text
    ids = [job["id"] for job in listed.json()]
    assert ids == ["job-a"]
    assert "job-b" not in listed.text
    assert SECRET_NAME not in listed.text
    assert foreign_job.status_code == 404
    assert foreign_edit.status_code == 404
    assert foreign_cancel.status_code == 404
    assert own_edit.status_code == 200, own_edit.text
    assert own_edit.json()["notes"] == "Use the side gate"
    assert own_edit.json()["edit_history"][-1]["who"]["id"] == "shop-a"
    other = next(job for job in db.jobs.docs if job["id"] == "job-b")
    assert other["notes"] == "Gate code"
    assert other["status"] == "booked"
    assert score_a.status_code == 200, score_a.text
    assert score_a.json()["shop_name"] == "Shop A"
    assert "booking_link" not in score_a.json()
    assert "token-b" not in score_a.text
    assert "Shop B" not in score_a.text
    assert anonymous.status_code == 401


def test_owner_can_book_for_a_shop_and_staff_cannot_use_that_route(monkeypatch):
    db = _world(monkeypatch)
    db.shops.docs[0]["charge_authorization_accepted_at"] = None

    async def run():
        async with _client() as client:
            blocked = await client.post("/api/shops/shop-a/book", json=BOOK, headers=_owner())
            staff = await client.post(
                "/api/shops/shop-a/book",
                json=BOOK,
                headers={"Authorization": f"Bearer {server.make_token('tech-field', 'technician')}"},
            )
            stranger = await client.post("/api/shops/shop-a/book", json=BOOK)
            return blocked, staff, stranger

    blocked, staff, stranger = asyncio.run(run())
    assert blocked.status_code == 403, blocked.text
    assert "terms" in blocked.json()["detail"].lower()
    assert staff.status_code == 403
    assert stranger.status_code == 401
    assert len(db.jobs.docs) == 2


def test_welcome_and_invite_mail_do_not_include_a_booking_token(monkeypatch):
    html = welcome_email_html("Jarvis Glass", "https://www.thecalibrationcrew.us/portal/login")
    assert "/portal/login" in html
    assert "/book/" not in html
    invite = invite_email_html("Jarvis Glass", "https://www.thecalibrationcrew.us/portal/invite/setup-token")
    assert "/portal/invite/setup-token" in invite
    assert "/book/" not in invite
    assert "shop portal" in invite.lower()

    sent = []

    async def capture(payload, audience):
        sent.append(payload)
        return {"delivered": False}

    async def owner_mail(*args, **kwargs):
        sent.append({"html": args[2], "kind": kwargs.get("kind")})

    monkeypatch.setattr(server, "_send_booking_message", capture)
    monkeypatch.setattr(server, "send_email", owner_mail)
    monkeypatch.setattr(server, "FRONTEND_URL", "https://www.thecalibrationcrew.us")
    asyncio.run(server._send_signup_finished(
        {"id": "shop-a", "name": "Jarvis Glass", "booking_link_token": "sekret-token"},
        "ada@jarvis.example",
    ))
    blob = str(sent)
    assert "sekret-token" not in blob
    assert "/book/" not in blob
    assert "https://www.thecalibrationcrew.us/portal/login" in blob
