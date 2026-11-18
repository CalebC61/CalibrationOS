"""Browser responses must not carry Xero tokens, password hashes, or Stripe ids.

    cd backend && pytest tests/test_response_secrets.py -v
"""
import asyncio
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from client_views import public_shop, public_shop_user, public_staff  # noqa: E402


LEAKED = {
    "password_hash": "LEAKED-PASSWORD-HASH",
    "xero_access_token": "LEAKED-XERO-ACCESS",
    "xero_refresh_token": "LEAKED-XERO-REFRESH",
    "xero_id_token": "LEAKED-XERO-ID",
    "xero_token_expiry": "LEAKED-XERO-EXPIRY",
    "xero_tenant_id": "LEAKED-XERO-TENANT",
    "stripe_customer_id": "LEAKED-STRIPE-CUSTOMER",
    "stripe_payment_method_id": "LEAKED-STRIPE-PM",
    "access_token": "LEAKED-ACCESS",
    "refresh_token": "LEAKED-REFRESH",
    "id_token": "LEAKED-ID-TOKEN",
    "client_secret": "LEAKED-CLIENT-SECRET",
    "api_key": "LEAKED-API-KEY",
}

FORBIDDEN_KEYS = set(LEAKED) | {"password", "secret"}


def _match(doc, query):
    for key, expected in (query or {}).items():
        value = doc.get(key)
        if isinstance(expected, dict) and "$in" in expected:
            if value not in expected["$in"]:
                return False
        elif value != expected:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, limit):
        return list(self.docs)[:limit]


class _Store:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return {k: v for k, v in doc.items() if k != "_id"}
        return None

    def find(self, query, projection=None):
        return _Cursor([{k: v for k, v in doc.items() if k != "_id"} for doc in self.docs if _match(doc, query)])

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _match(doc, query):
                doc.update(update.get("$set", {}))
                return


class _DB:
    def __init__(self):
        self.technicians = _Store()
        self.shops = _Store()
        self.shop_users = _Store()


def _walk_keys(value, found):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_KEYS or (key.endswith("_token") and key != "booking_link_token"):
                found.append(key)
            _walk_keys(item, found)
    elif isinstance(value, list):
        for item in value:
            _walk_keys(item, found)


def _assert_clean(payload):
    text = str(payload)
    for marker in LEAKED.values():
        assert marker not in text
    found = []
    _walk_keys(payload, found)
    assert found == []


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test")


def _install():
    db = _DB()
    server.db = db
    db.technicians.docs.append({
        "id": "owner-1",
        "name": "Caleb",
        "email": "caleb@thecalibrationcrew.us",
        "phone": "+16025550101",
        "role": "owner",
        "is_active": True,
        "home_address": "Gilbert, AZ",
        "home_lat": 33.35,
        "home_lng": -111.79,
        "xero_connected": True,
        "xero_org_name": "The Calibration Crew",
        "agreement_ip": "203.0.113.9",
        **LEAKED,
    })
    db.technicians.docs.append({
        "id": "west",
        "name": "West",
        "email": "west@thecalibrationcrew.us",
        "phone": "+16025550199",
        "role": "contractor",
        "is_active": True,
        "home_address": "Goodyear, AZ",
        **LEAKED,
    })
    db.shops.docs.append({
        "id": "shop-1",
        "name": "Jarvis Glass",
        "status": "active",
        "signup_source": "self_serve",
        "booking_link_token": "book-tok-visible",
        "xero_contact_id": "xero-contact-visible",
        "address": "100 W Guadalupe Rd, Gilbert, AZ",
        "card_brand": "visa",
        "card_last4": "4242",
        "notes": "Call Dana",
        **LEAKED,
    })
    db.shop_users.docs.append({
        "id": "user-1",
        "email": "ada@jarvis.example",
        "full_name": "Ada Glass",
        "shop_id": "shop-1",
        "shop_name": "Jarvis Glass",
        "is_active": True,
        "card_brand": "visa",
        "card_last4": "4242",
        "card_exp_month": 12,
        "card_exp_year": 2099,
        "terms_signature": "Ada Glass",
        "agreement_text": "LEAKED-AGREEMENT-TEXT",
        "agreement_ip": "203.0.113.9",
        **LEAKED,
    })
    return db


def test_staff_allowlist_keeps_xero_status_and_drops_tokens():
    view = public_staff({
        "id": "owner-1",
        "name": "Caleb",
        "role": "owner",
        "xero_org_name": "The Calibration Crew",
        **LEAKED,
    })
    assert view["xero_connected"] is True
    assert view["xero_org_name"] == "The Calibration Crew"
    assert view["id"] == "owner-1"
    _assert_clean(view)
    assert "xero_tenant_id" not in view
    assert "password_hash" not in view


def test_shop_user_allowlist_reports_a_card_without_stripe_ids():
    view = public_shop_user({
        "id": "user-1",
        "email": "ada@jarvis.example",
        "full_name": "Ada",
        "card_brand": "visa",
        "card_last4": "4242",
        "agreement_text": "LEAKED-AGREEMENT-TEXT",
        **LEAKED,
    })
    assert view["has_payment_method"] is True
    assert view["card_last4"] == "4242"
    assert "agreement_text" not in view
    _assert_clean(view)


def test_shop_view_keeps_the_booking_link_and_drops_stripe_ids():
    view = public_shop({
        "id": "shop-1",
        "name": "Jarvis Glass",
        "booking_link_token": "book-tok-visible",
        "xero_contact_id": "xero-contact-visible",
        **LEAKED,
    })
    assert view["booking_link_token"] == "book-tok-visible"
    assert view["xero_contact_id"] == "xero-contact-visible"
    assert view["has_payment_method"] is True
    _assert_clean(view)


def test_auth_me_shops_and_portal_omit_secrets():
    _install()
    owner = server.make_token("owner-1", "owner")
    portal = server.make_portal_token("user-1")
    owner_headers = {"Authorization": f"Bearer {owner}"}
    portal_headers = {"Authorization": f"Bearer {portal}"}

    async def run():
        async with _client() as client:
            me = await client.get("/api/auth/me", headers=owner_headers)
            contractors = await client.get("/api/contractors", headers=owner_headers)
            routing = await client.get("/api/routing-techs", headers=owner_headers)
            shops = await client.get("/api/shops", headers=owner_headers)
            shop = await client.get("/api/shops/shop-1", headers=owner_headers)
            fresh = await client.get("/api/new-shops", headers=owner_headers)
            portal_me = await client.get("/api/portal/me", headers=portal_headers)
            return me, contractors, routing, shops, shop, fresh, portal_me

    me, contractors, routing, shops, shop, fresh, portal_me = asyncio.run(run())

    assert me.status_code == 200, me.text
    body = me.json()
    assert body["id"] == "owner-1"
    assert body["email"] == "caleb@thecalibrationcrew.us"
    assert body["xero_connected"] is True
    assert body["xero_org_name"] == "The Calibration Crew"
    assert "agreement_ip" not in body
    _assert_clean(body)

    assert contractors.status_code == 404

    assert routing.status_code == 200, routing.text
    routed = routing.json()
    assert any(person["id"] == "owner-1" for person in routed)
    assert all(person["id"] != "west" for person in routed)
    owner_row = next(person for person in routed if person["id"] == "owner-1")
    assert owner_row["xero_connected"] is True
    assert owner_row["xero_org_name"] == "The Calibration Crew"
    _assert_clean(routed)

    assert shops.status_code == 200, shops.text
    assert shops.json()[0]["booking_link_token"] == "book-tok-visible"
    assert shops.json()[0]["xero_contact_id"] == "xero-contact-visible"
    assert shops.json()[0]["has_payment_method"] is True
    assert shops.json()[0]["notes"] == "Call Dana"
    _assert_clean(shops.json())

    assert shop.status_code == 200, shop.text
    assert shop.json()["name"] == "Jarvis Glass"
    _assert_clean(shop.json())

    assert fresh.status_code == 200, fresh.text
    assert fresh.json()[0]["id"] == "shop-1"
    _assert_clean(fresh.json())

    assert portal_me.status_code == 200, portal_me.text
    portal_body = portal_me.json()
    assert portal_body["shop_user"]["has_payment_method"] is True
    assert portal_body["shop_user"]["card_brand"] == "visa"
    assert portal_body["shop_user"]["card_last4"] == "4242"
    assert portal_body["shop_user"]["full_name"] == "Ada Glass"
    assert "agreement_text" not in portal_body["shop_user"]
    assert "agreement_ip" not in portal_body["shop_user"]
    assert "LEAKED-AGREEMENT-TEXT" not in str(portal_body)
    assert portal_body["shop"]["booking_link_token"] == "book-tok-visible"
    assert portal_body["setup"]["has_card"] is True
    _assert_clean(portal_body)


def test_docs_are_off_in_production_unless_the_flag_is_true(monkeypatch):
    monkeypatch.delenv("ENABLE_API_DOCS", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    assert server.api_docs_enabled() is True

    monkeypatch.setenv("APP_ENV", "production")
    assert server.api_docs_enabled() is False
    monkeypatch.setenv("APP_ENV", "prod")
    assert server.api_docs_enabled() is False

    monkeypatch.setenv("ENABLE_API_DOCS", "true")
    assert server.api_docs_enabled() is True

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_API_DOCS", "false")
    assert server.api_docs_enabled() is False


def test_docs_routes_are_404_when_disabled(monkeypatch):
    monkeypatch.setattr(server, "api_docs_enabled", lambda: False)

    async def ping():
        return {"ok": 1}

    monkeypatch.setattr(server, "ping_database", ping)

    async def run():
        async with _client() as client:
            docs = await client.get("/docs")
            redoc = await client.get("/redoc")
            schema = await client.get("/openapi.json")
            redirect = await client.get("/docs/oauth2-redirect")
            health = await client.get("/api/health")
            return docs, redoc, schema, redirect, health

    docs, redoc, schema, redirect, health = asyncio.run(run())
    assert docs.status_code == 404
    assert redoc.status_code == 404
    assert schema.status_code == 404
    assert redirect.status_code == 404
    assert health.status_code == 200
    assert health.json()["status"] == "ok"


def test_docs_routes_stay_available_when_enabled(monkeypatch):
    monkeypatch.setattr(server, "api_docs_enabled", lambda: True)
    if server.app.openapi_url is None:
        return

    async def run():
        async with _client() as client:
            return await client.get("/openapi.json")

    response = asyncio.run(run())
    assert response.status_code == 200
    assert "openapi" in response.json()
