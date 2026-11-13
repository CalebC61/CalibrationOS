"""Public shop signup: one request creates the shop, and a suspended shop cannot book.

    cd backend && pytest tests/test_public_signup.py -v
"""
import asyncio
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from onboarding import (  # noqa: E402
    AGREEMENT_VERSION,
    reset_rate_limits,
    resolve_frontend_url,
)


def _match(doc, query):
    for key, expected in query.items():
        if isinstance(expected, dict):
            return False
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
                return

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class _DB:
    def __init__(self):
        self.shops = _Store()
        self.shop_users = _Store()
        self.invites = _Store()
        self.email_outbox = _Store()


ROUGH_PIN = {
    "lat": 33.3528,
    "lng": -111.789,
    "formatted_address": "100 W Guadalupe Rd, Gilbert, AZ 85233, USA",
    "in_metro": True,
    "source": "google",
    "partial_match": False,
    "fallback": False,
    "location_type": "GEOMETRIC_CENTER",
}


def _body(**overrides):
    payload = {
        "shop_name": "Jarvis Glass",
        "contact_name": "Ada Glass",
        "mobile": "4805550100",
        "email": "ada@jarvis.example",
        "password": "longenough",
        "address": "100 W Guadalupe Rd, Gilbert, AZ",
        "place_id": "places-gilbert",
        "address_confirmed": False,
        "terms_signature": "Ada Glass",
        "terms_agreed": True,
        "charge_accepted": True,
    }
    payload.update(overrides)
    return payload


def _install(monkeypatch, geo=None):
    reset_rate_limits()
    db = _DB()
    emails = []

    async def send_email(to, subject, html, kind="transactional", meta=None, reply_to=None):
        emails.append({"to": to, "subject": subject, "html": html, "kind": kind})
        return {"delivered": True, "kind": kind}

    async def geocode(address):
        pin = dict(ROUGH_PIN if geo is None else geo)
        pin.setdefault("formatted_address", address)
        return pin

    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "send_email", send_email)
    monkeypatch.setattr(server, "geocode_address", geocode)
    monkeypatch.setattr(server, "get_stripe", lambda: None)
    return db, emails


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test")


def test_signup_creates_the_shop_user_agreement_and_jwt(monkeypatch):
    db, emails = _install(monkeypatch)

    async def run():
        async with _client() as client:
            return await client.post("/api/public/shops", json=_body())

    response = asyncio.run(run())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token"]
    assert body["booking_open"] is False
    assert body["stripe_unavailable"] is True
    assert len(db.shops.docs) == 1
    assert len(db.shop_users.docs) == 1
    assert db.invites.docs == []
    shop = db.shops.docs[0]
    user = db.shop_users.docs[0]
    assert shop["signup_source"] == "self_serve"
    assert shop["requires_billing_setup"] is True
    assert shop["status"] == "active"
    assert shop["address"] == ROUGH_PIN["formatted_address"]
    assert user["email"] == "ada@jarvis.example"
    assert user["agreement_version"] == AGREEMENT_VERSION
    assert user["terms_signature"] == "Ada Glass"
    assert user["agreement_text"]
    assert "Triple / Subaru $185" in user["agreement_text"]
    assert user["password_hash"] != "longenough"
    assert server.verify_password("longenough", user["password_hash"])
    assert user["stripe_payment_method_id"] is None
    assert emails and emails[0]["kind"] == "shop_request"
    assert "Gilbert" in emails[0]["html"]
    assert "/requests" in emails[0]["html"]


def test_duplicate_email_returns_409_and_points_at_login(monkeypatch):
    db, _emails = _install(monkeypatch)

    async def run():
        async with _client() as client:
            first = await client.post("/api/public/shops", json=_body())
            second = await client.post("/api/public/shops", json=_body(
                shop_name="Another Glass", email="Ada@jarvis.example",
            ))
            return first, second

    first, second = asyncio.run(run())
    assert first.status_code == 200, first.text
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["code"] == "duplicate_email"
    assert "Log in" in detail["message"]
    assert detail["login_path"] == "/portal/login"
    assert detail["forgot_path"] == "/portal/forgot"
    assert len(db.shops.docs) == 1


def test_places_selection_skips_the_confirmation_submit(monkeypatch):
    db, _emails = _install(monkeypatch)

    async def run():
        async with _client() as client:
            typed = await client.post("/api/public/shops", json=_body(
                email="typed@jarvis.example", place_id=None, address_confirmed=False,
            ))
            picked = await client.post("/api/public/shops", json=_body(
                email="picked@jarvis.example", shop_name="Picked Glass",
                place_id="ChIJ-suggestion", address_confirmed=False,
            ))
            return typed, picked

    typed, picked = asyncio.run(run())
    assert typed.status_code == 409
    assert typed.json()["detail"]["code"] == "needs_confirmation"
    assert picked.status_code == 200, picked.text
    assert len(db.shops.docs) == 1
    assert db.shops.docs[0]["name"] == "Picked Glass"


def test_a_clean_free_typed_address_also_skips_confirmation(monkeypatch):
    clean = dict(ROUGH_PIN)
    clean["location_type"] = "ROOFTOP"
    _install(monkeypatch, geo=clean)

    async def run():
        async with _client() as client:
            return await client.post("/api/public/shops", json=_body(
                email="roof@jarvis.example", place_id=None, address_confirmed=False,
            ))

    response = asyncio.run(run())
    assert response.status_code == 200, response.text


def test_suspended_shop_cannot_book(monkeypatch):
    db, _emails = _install(monkeypatch)
    db.shops.docs.append({
        "id": "shop-1",
        "name": "Held Glass",
        "booking_link_token": "tok",
        "status": "suspended",
        "requires_billing_setup": True,
        "lat": 33.35,
        "lng": -111.79,
        "address": "1 Main, Gilbert, AZ",
        "geocode_source": "google",
    })
    db.shop_users.docs.append({
        "shop_id": "shop-1",
        "agreement_version": AGREEMENT_VERSION,
        "terms_signed_at": "t",
        "terms_signature": "Ada Glass",
        "stripe_payment_method_id": "pm_1",
        "charge_authorization_accepted_at": "t",
    })
    async def run():
        async with _client() as client:
            return await client.post("/api/public/book", json={
                "booking_token": "tok",
                "job_address": "1 Main, Gilbert, AZ",
                "scheduled_start": "2026-11-20T17:00:00+00:00",
                "customer_last_name": "Ng",
                "year": 2024,
                "make": "Subaru",
                "model": "Outback",
                "adas_system": "multi_camera",
                "calibration_type": "triple",
                "notification_phone": "4805550100",
            })

    response = asyncio.run(run())
    assert response.status_code == 403
    assert "suspended" in response.json()["detail"].lower()


def test_shop_address_reuses_the_signup_pin(monkeypatch):
    async def boom(address):
        raise AssertionError(address)

    monkeypatch.setattr(server, "geocode_address", boom)
    shop = {
        "address": "100 W Guadalupe Rd, Gilbert, AZ 85233, USA",
        "formatted_address": "100 W Guadalupe Rd, Gilbert, AZ 85233, USA",
        "lat": 33.3528,
        "lng": -111.789,
        "geocode_source": "google",
    }
    pin = asyncio.run(server._pin_for_job(shop, "100 w guadalupe rd gilbert az 85233 usa"))
    assert pin["lat"] == 33.3528
    assert pin["source"] == "google"


def test_request_new_does_not_claim_mail_is_on_the_way_when_held(monkeypatch):
    db, _emails = _install(monkeypatch)
    monkeypatch.setenv("SHOP_EMAILS_ENABLED", "false")
    monkeypatch.delenv("TEST_EMAIL_ALLOWLIST", raising=False)
    monkeypatch.setattr(server, "FRONTEND_URL", "")
    db.shops.docs.append({"id": "shop-1", "name": "Jarvis Glass"})
    db.invites.docs.append({
        "id": "inv-1",
        "token": "expired-token",
        "shop_id": "shop-1",
        "shop_name": "Jarvis Glass",
        "recipient_email": "ada@jarvis.example",
        "status": "expired",
        "expires_at": "2000-01-01T00:00:00+00:00",
    })
    async def run():
        async with _client() as client:
            return await client.post("/api/public/invites/expired-token/request-new")

    response = asyncio.run(run())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["held"] is True
    assert "on the way" not in body["message"].lower()
    created = [row for row in db.invites.docs if row.get("status") == "pending"]
    assert created
    assert created[-1]["register_url"].startswith("https://")
    assert "/portal/invite/" in created[-1]["register_url"]
    assert created[-1]["email_status"] == "held"


def test_blank_frontend_url_uses_the_public_site():
    assert resolve_frontend_url("", "") == "https://www.thecalibrationcrew.us"
    assert resolve_frontend_url("", "https://www.thecalibrationcrew.us") == "https://www.thecalibrationcrew.us"
    assert resolve_frontend_url("https://app.example/", "https://www.thecalibrationcrew.us") == "https://app.example"
