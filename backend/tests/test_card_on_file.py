"""A shop cannot book without a current card, and a card is only saved from a verified SetupIntent.

    cd backend && pytest tests/test_card_on_file.py -v
"""
import asyncio
import json
import os
import sys
from datetime import date

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from onboarding import (  # noqa: E402
    AGREEMENT_VERSION,
    billing_view,
    booking_gate,
    card_block_reason,
    card_is_expired,
    pick_billing_user,
    reset_rate_limits,
    shop_card_backfill,
)
from payments import CardSetupError, verified_card  # noqa: E402


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
            if flag == 0 and key != "_id":
                out.pop(key, None)
        return out
    return {k: out[k] for k in projection if k in out and projection[k]}


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

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _match(doc, query):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                return
        if upsert:
            doc = dict(query)
            doc.update(update.get("$set", {}))
            self.docs.append(doc)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class _DB:
    def __init__(self):
        self.shops = _Store()
        self.shop_users = _Store()
        self.jobs = _Store()
        self.card_changes = _Store()
        self.technicians = _Store()
        self.vehicles = _Store()
        self.email_outbox = _Store()


def _db():
    reset_rate_limits()
    db = _DB()
    server.db = db
    return db


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test")


def _card(**overrides):
    payload = {
        "id": "pm_real",
        "type": "card",
        "card": {"brand": "visa", "last4": "4242", "exp_month": 12, "exp_year": 2099},
    }
    payload.update(overrides)
    return payload


def _intent(**overrides):
    payload = {
        "id": "seti_ok",
        "status": "succeeded",
        "customer": None,
        "metadata": {"purpose": "shop_signup"},
        "payment_method": _card(),
    }
    payload.update(overrides)
    return payload


def _shop(**overrides):
    payload = {
        "id": "shop-1",
        "name": "Jarvis Glass",
        "status": "active",
        "booking_link_token": "tok",
        "address": "100 W Guadalupe Rd, Gilbert, AZ",
        "stripe_customer_id": "cus_shop",
        "stripe_payment_method_id": "pm_shop",
        "card_brand": "visa",
        "card_last4": "4242",
        "card_exp_month": 12,
        "card_exp_year": 2099,
        "card_status": "active",
        "charge_authorization_accepted_at": "2026-01-01T00:00:00+00:00",
        "billing_card_backfilled": True,
        "requires_billing_setup": True,
        "terms_signed_at": "2026-01-01T00:00:00+00:00",
        "terms_signed_by": "Ada Glass",
    }
    payload.update(overrides)
    return payload


def _user(**overrides):
    payload = {
        "id": "user-1",
        "email": "ada@jarvis.example",
        "full_name": "Ada Glass",
        "shop_id": "shop-1",
        "shop_name": "Jarvis Glass",
        "is_active": True,
        "created_at": "2026-01-01T00:00:00+00:00",
        "stripe_customer_id": "cus_shop",
        "stripe_payment_method_id": "pm_shop",
        "card_brand": "visa",
        "card_last4": "4242",
        "card_exp_month": 12,
        "card_exp_year": 2099,
        "card_status": "active",
        "charge_authorization_accepted_at": "2026-01-01T00:00:00+00:00",
        "agreement_version": AGREEMENT_VERSION,
        "terms_signed_at": "2026-01-01T00:00:00+00:00",
        "terms_signature": "Ada Glass",
    }
    payload.update(overrides)
    return payload


BOOK = {
    "booking_token": "tok",
    "job_address": "100 W Guadalupe Rd, Gilbert, AZ",
    "scheduled_start": "2026-11-20T17:00:00+00:00",
    "customer_last_name": "Ng",
    "year": 2024,
    "make": "Subaru",
    "model": "Outback",
    "adas_system": "multi_camera",
    "calibration_type": "triple",
    "notification_phone": "4805550100",
}


def _book(monkeypatch, shop):
    db = _db()
    db.shops.docs.append(shop)

    async def run():
        async with _client() as client:
            return await client.post("/api/public/book", json=BOOK)

    return db, asyncio.run(run())


def test_a_card_is_good_through_the_end_of_its_expiry_month():
    today = date(2026, 11, 14)
    assert card_is_expired(11, 2026, today=today) is False
    assert card_is_expired(10, 2026, today=today) is True
    assert card_is_expired(1, 2027, today=today) is False
    assert card_block_reason({"stripe_payment_method_id": "", "card_status": "active"}, today=today) == "missing"
    assert card_block_reason({"stripe_payment_method_id": "pm_1", "card_status": "removed"}, today=today) == "removed"
    assert card_block_reason({
        "stripe_payment_method_id": "pm_1", "card_exp_month": 10, "card_exp_year": 2026,
    }, today=today) == "expired"


def test_the_shop_card_wins_over_a_different_user_card():
    shop = _shop(stripe_payment_method_id="pm_shop")
    other = _user(id="other", stripe_payment_method_id="pm_other", created_at="2026-06-01")
    earlier = _user(id="early", stripe_payment_method_id="pm_early", created_at="2026-01-01", is_active=False)
    assert pick_billing_user([other, earlier])["id"] == "other"
    assert billing_view(shop, other)["stripe_payment_method_id"] == "pm_shop"
    blank = _shop(stripe_payment_method_id=None, card_status=None, billing_card_backfilled=False)
    assert billing_view(blank, other)["stripe_payment_method_id"] == "pm_other"


def test_backfill_copies_once_and_does_not_replace_a_shop_card():
    copied = shop_card_backfill({"id": "s"}, _user(stripe_payment_method_id="pm_user", stripe_customer_id="cus_user"))
    assert copied["stripe_payment_method_id"] == "pm_user"
    assert copied["billing_card_backfilled"] is True
    again = shop_card_backfill({"id": "s", "billing_card_backfilled": True, "stripe_payment_method_id": "pm_shop"}, _user())
    assert again == {}
    kept = shop_card_backfill({"id": "s", "stripe_payment_method_id": "pm_shop"}, _user(stripe_payment_method_id="pm_user"))
    assert "stripe_payment_method_id" not in kept


def test_verified_card_rejects_a_raw_or_foreign_setup_intent():
    saved = verified_card(_intent(), purpose="shop_signup")
    assert saved["stripe_payment_method_id"] == "pm_real"
    assert saved["card_last4"] == "4242"
    try:
        verified_card(_intent(status="requires_payment_method"))
        raised = False
    except CardSetupError:
        raised = True
    assert raised
    try:
        verified_card(_intent(payment_method=_card(type="us_bank_account")))
        raised = False
    except CardSetupError:
        raised = True
    assert raised
    portal = _intent(customer="cus_shop", metadata={"purpose": "card_on_file", "shop_id": "shop-1"})
    assert verified_card(portal, customer_id="cus_shop", shop_id="shop-1")["card_brand"] == "visa"
    try:
        verified_card(portal, customer_id="cus_other", shop_id="shop-1")
        raised = False
    except CardSetupError:
        raised = True
    assert raised


def test_booking_gate_blocks_every_way_a_card_can_be_missing():
    today = date(2026, 11, 14)
    ready = booking_gate(_shop(), _user(), today=today)
    assert ready["allowed"] is True
    cases = [
        (_shop(stripe_payment_method_id=None, card_status=None), "missing"),
        (_shop(stripe_payment_method_id="", card_status="active"), "missing"),
        (_shop(stripe_payment_method_id=None, card_status="removed"), "removed"),
        (_shop(stripe_payment_method_id=None, card_status="detached"), "removed"),
        (_shop(card_exp_month=10, card_exp_year=2026), "expired"),
    ]
    for shop, reason in cases:
        gate = booking_gate(shop, _user(stripe_payment_method_id="pm_user"), today=today)
        assert gate["allowed"] is False, reason
        assert gate["card_problem"] == reason
        assert "Settings" in gate["message"]
    failed = booking_gate(_shop(unresolved_charge_failure=True), _user(), today=today)
    assert failed["allowed"] is False
    assert "did not go through" in failed["message"]
    assert "Settings" in failed["message"]
    legacy = booking_gate({"id": "old", "status": "active"}, None, today=today)
    assert legacy["allowed"] is False


def test_public_book_rejects_a_shop_with_no_card(monkeypatch):
    cases = [
        _shop(stripe_payment_method_id=None, card_status=None),
        _shop(stripe_payment_method_id="", card_status="active"),
        _shop(stripe_payment_method_id=None, card_status="removed"),
        _shop(card_exp_month=1, card_exp_year=2020),
        _shop(unresolved_charge_failure=True),
    ]
    for shop in cases:
        _db_unused, response = _book(monkeypatch, shop)
        assert response.status_code == 403, response.text
        assert "Settings" in response.json()["detail"]


def test_a_user_card_does_not_let_a_cleared_shop_book(monkeypatch):
    db, response = _book(monkeypatch, _shop(stripe_payment_method_id=None, card_status="removed"))
    db.shop_users.docs.append(_user(stripe_payment_method_id="pm_user"))
    async def run():
        async with _client() as client:
            return await client.post("/api/public/book", json=BOOK)
    response = asyncio.run(run())
    assert response.status_code == 403
    assert "removed" in response.json()["detail"].lower()


def test_signup_rejects_a_client_supplied_payment_method_and_keeps_a_verified_card(monkeypatch):
    db = _db()
    created = []
    deleted = []

    async def send_email(*args, **kwargs):
        return {"delivered": True}

    async def geocode(address):
        return {
            "lat": 33.35, "lng": -111.79, "formatted_address": "100 W Guadalupe Rd, Gilbert, AZ 85233, USA",
            "in_metro": True, "source": "google", "partial_match": False, "fallback": False,
            "location_type": "ROOFTOP",
        }

    def retrieve(client, intent_id):
        if intent_id != "seti_ok":
            raise RuntimeError("missing")
        return _intent()

    def create_customer(client, **kwargs):
        created.append(kwargs)
        return "cus_new"

    def save(client, **kwargs):
        assert kwargs["payment_method_id"] == "pm_real"
        assert kwargs["customer_id"] == "cus_new"
        return {
            "stripe_payment_method_id": "pm_real", "card_brand": "visa", "card_last4": "4242",
            "card_exp_month": 12, "card_exp_year": 2099, "card_status": "active",
        }

    def delete(client, customer_id):
        deleted.append(customer_id)

    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "send_email", send_email)
    monkeypatch.setattr(server, "geocode_address", geocode)
    monkeypatch.setattr(server, "get_stripe", lambda: object())
    monkeypatch.setattr(server, "retrieve_setup_intent", retrieve)
    monkeypatch.setattr(server, "stripe_create_customer", create_customer)
    monkeypatch.setattr(server, "save_payment_method", save)
    monkeypatch.setattr(server, "delete_customer", delete)

    body = {
        "shop_name": "Jarvis Glass", "contact_name": "Ada Glass", "mobile": "4805550100",
        "email": "ada@jarvis.example", "password": "longenough",
        "address": "100 W Guadalupe Rd, Gilbert, AZ", "place_id": "places-gilbert",
        "terms_signature": "Ada Glass", "terms_agreed": True, "charge_accepted": True,
        "payment_method_id": "pm_card_visa",
    }

    async def run():
        async with _client() as client:
            rejected = await client.post("/api/public/shops", json=body)
            accepted = await client.post("/api/public/shops", json={**body, "setup_intent_id": "seti_ok", "email": "new@jarvis.example", "shop_name": "New Glass"})
            return rejected, accepted

    rejected, accepted = asyncio.run(run())
    assert rejected.status_code == 400, rejected.text
    assert accepted.status_code == 200, accepted.text
    assert len(created) == 1
    assert len(db.shops.docs) == 1
    assert accepted.json()["booking_open"] is True
    assert db.shops.docs[-1]["stripe_payment_method_id"] == "pm_real"
    assert db.shops.docs[-1]["card_exp_year"] == 2099
    assert db.card_changes.docs[-1]["action"] == "signup"
    assert "4242" in str(db.card_changes.docs[-1]["card_last4"])
    assert deleted == []


def test_a_failed_signup_deletes_the_stripe_customer(monkeypatch):
    db = _db()
    deleted = []

    async def geocode(address):
        return {
            "lat": 33.35, "lng": -111.79, "formatted_address": "100 W Guadalupe Rd, Gilbert, AZ",
            "in_metro": True, "source": "google", "location_type": "ROOFTOP",
        }

    def save(client, **kwargs):
        raise RuntimeError("attach failed")

    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "geocode_address", geocode)
    monkeypatch.setattr(server, "get_stripe", lambda: object())
    monkeypatch.setattr(server, "retrieve_setup_intent", lambda client, intent_id: _intent())
    monkeypatch.setattr(server, "stripe_create_customer", lambda client, **kwargs: "cus_orphan")
    monkeypatch.setattr(server, "save_payment_method", save)
    monkeypatch.setattr(server, "delete_customer", lambda client, customer_id: deleted.append(customer_id))

    body = {
        "shop_name": "Jarvis Glass", "contact_name": "Ada Glass", "mobile": "4805550100",
        "email": "ada@jarvis.example", "password": "longenough",
        "address": "100 W Guadalupe Rd, Gilbert, AZ", "place_id": "places-gilbert",
        "terms_signature": "Ada Glass", "terms_agreed": True, "charge_accepted": True,
        "setup_intent_id": "seti_ok",
    }

    async def run():
        async with _client() as client:
            return await client.post("/api/public/shops", json=body)

    response = asyncio.run(run())
    assert response.status_code == 502, response.text
    assert deleted == ["cus_orphan"]
    assert db.shops.docs == []


def test_card_setup_failure_tells_the_shop_to_retry_or_call(monkeypatch):
    _db()

    class _Broken:
        def __init__(self):
            self.v1 = type("V1", (), {"setup_intents": self})()

        def create(self, payload):
            raise RuntimeError("stripe down")

    monkeypatch.setattr(server, "get_stripe", lambda: _Broken())

    async def run():
        async with _client() as client:
            return await client.post("/api/public/card-setup")

    response = asyncio.run(run())
    message = response.json()["message"]
    assert "Settings" not in message
    assert "Try again" in message or "call" in message


def _portal(db):
    db.shops.docs.append(_shop())
    db.shop_users.docs.append(_user())
    return server.make_portal_token("user-1")


def test_replacing_a_card_verifies_the_setup_intent_and_detaches_the_old_one(monkeypatch):
    db = _db()
    token = _portal(db)
    db.shops.docs[0]["unresolved_charge_failure"] = True
    detached = []

    def retrieve(client, intent_id):
        if intent_id == "seti_other":
            return _intent(id="seti_other", customer="cus_other", metadata={"shop_id": "shop-9"})
        return _intent(
            id="seti_new", customer="cus_shop",
            metadata={"purpose": "card_on_file", "shop_id": "shop-1", "shop_user_id": "user-1"},
            payment_method=_card(id="pm_new", card={"brand": "mastercard", "last4": "4444", "exp_month": 3, "exp_year": 2030}),
        )

    def save(client, **kwargs):
        return {
            "stripe_payment_method_id": kwargs["payment_method_id"],
            "card_brand": "mastercard", "card_last4": "4444",
            "card_exp_month": 3, "card_exp_year": 2030, "card_status": "active",
        }

    monkeypatch.setattr(server, "get_stripe", lambda: object())
    monkeypatch.setattr(server, "retrieve_setup_intent", retrieve)
    monkeypatch.setattr(server, "save_payment_method", save)
    monkeypatch.setattr(server, "detach_payment_method", lambda client, pm: detached.append(pm))
    headers = {"Authorization": f"Bearer {token}"}

    async def run():
        async with _client() as client:
            foreign = await client.post("/api/portal/payment-method", json={"setup_intent_id": "seti_other"}, headers=headers)
            removed = await client.delete("/api/portal/payment-method", headers=headers)
            still = db.shops.docs[0]["stripe_payment_method_id"]
            untouched = list(detached)
            saved = await client.post("/api/portal/payment-method", json={"setup_intent_id": "seti_new"}, headers=headers)
            session = await client.get("/api/portal/stripe-setup-status?session_id=cs_other", headers=headers)
            return foreign, removed, still, untouched, saved, session

    def checkout(client, session_id):
        return {"id": session_id, "customer": "cus_other", "status": "complete", "setup_intent": _intent(customer="cus_other")}

    monkeypatch.setattr(server, "retrieve_setup_checkout", checkout)
    foreign, removed, still, untouched, saved, session = asyncio.run(run())
    assert foreign.status_code == 400, foreign.text
    assert removed.status_code == 400
    assert "cannot remove" in removed.json()["detail"]
    assert still == "pm_shop"
    assert untouched == []
    assert saved.status_code == 200, saved.text
    assert db.shops.docs[0]["stripe_payment_method_id"] == "pm_new"
    assert db.shop_users.docs[0]["stripe_payment_method_id"] == "pm_new"
    assert db.shops.docs[0]["unresolved_charge_failure"] is False
    assert detached == ["pm_shop"]
    assert db.card_changes.docs[-1]["action"] == "replaced"
    assert db.card_changes.docs[-1]["previous_last4"] == "4242"
    assert session.status_code == 400
    assert db.shops.docs[0]["stripe_payment_method_id"] == "pm_new"


def test_complete_setup_intent_must_belong_to_this_shops_customer(monkeypatch):
    db = _db()
    token = _portal(db)
    monkeypatch.setattr(server, "get_stripe", lambda: object())
    monkeypatch.setattr(server, "retrieve_setup_intent", lambda client, intent_id: _intent(customer="cus_other", metadata={"shop_id": "shop-1"}))
    headers = {"Authorization": f"Bearer {token}"}

    async def run():
        async with _client() as client:
            return await client.post("/api/portal/complete-setup-intent", json={"setup_intent_id": "seti_x"}, headers=headers)

    response = asyncio.run(run())
    assert response.status_code == 400, response.text
    assert db.shops.docs[0]["stripe_payment_method_id"] == "pm_shop"


def test_a_disabled_shop_user_cannot_use_the_portal(monkeypatch):
    db = _db()
    db.shop_users.docs.append(_user(is_active=False))
    token = server.make_portal_token("user-1")

    async def run():
        async with _client() as client:
            return await client.get("/api/portal/me", headers={"Authorization": f"Bearer {token}"})

    response = asyncio.run(run())
    assert response.status_code == 403
    assert response.json()["detail"] == "Account disabled"


def test_webhook_signature_is_required_and_a_detach_blocks_booking(monkeypatch):
    db = _db()
    db.shops.docs.append(_shop())
    db.shop_users.docs.append(_user())
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")

    def construct(payload, sig, secret):
        if sig != "good":
            raise ValueError("bad signature")
        return json.loads(payload)

    async def quiet(*args, **kwargs):
        return {"delivered": False}

    monkeypatch.setattr(server.stripe_sdk.Webhook, "construct_event", construct)
    monkeypatch.setattr(server, "send_email", quiet)
    monkeypatch.setattr(server, "_send_booking_message", quiet)

    detach = {
        "type": "payment_method.detached",
        "data": {"object": {"id": "pm_shop", "customer": "cus_shop", "type": "card"}},
    }
    old = {
        "type": "payment_method.detached",
        "data": {"object": {"id": "pm_old", "customer": "cus_shop"}},
    }

    async def run():
        async with _client() as client:
            missing = await client.post("/api/stripe/webhook", content=b"{}")
            bad = await client.post("/api/stripe/webhook", content=json.dumps(detach).encode(), headers={"stripe-signature": "nope"})
            stale = await client.post("/api/stripe/webhook", content=json.dumps(old).encode(), headers={"stripe-signature": "good"})
            still = db.shops.docs[0]["stripe_payment_method_id"]
            gone = await client.post("/api/stripe/webhook", content=json.dumps(detach).encode(), headers={"stripe-signature": "good"})
            booked = await client.post("/api/public/book", json=BOOK)
            return missing, bad, stale, still, gone, booked

    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    async def missing_secret():
        async with _client() as client:
            return await client.post("/api/stripe/webhook", content=b"{}")
    no_secret = asyncio.run(missing_secret())
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    missing, bad, stale, still, gone, booked = asyncio.run(run())
    assert no_secret.status_code == 503
    assert bad.status_code == 400
    assert stale.status_code == 200
    assert still == "pm_shop"
    assert gone.status_code == 200
    assert db.shops.docs[0]["stripe_payment_method_id"] is None
    assert db.shops.docs[0]["card_status"] == "removed"
    assert db.shop_users.docs[0]["card_status"] == "removed"
    assert booked.status_code == 403
    assert "Settings" in booked.json()["detail"]
    assert missing.status_code == 400


def test_a_failed_charge_webhook_blocks_the_next_booking(monkeypatch):
    db = _db()
    db.shops.docs.append(_shop())
    db.jobs.docs.append({"id": "job-1", "shop_id": "shop-1", "shop_name": "Jarvis Glass", "payment_status": "open"})
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(server.stripe_sdk.Webhook, "construct_event", lambda payload, sig, secret: json.loads(payload))

    async def quiet(*args, **kwargs):
        return {"delivered": False}

    monkeypatch.setattr(server, "send_email", quiet)
    monkeypatch.setattr(server, "_send_booking_message", quiet)
    event = {
        "type": "payment_intent.payment_failed",
        "data": {"object": {
            "id": "pi_fail",
            "metadata": {"job_id": "job-1", "shop_id": "shop-1"},
            "last_payment_error": {"message": "Your card was declined."},
        }},
    }

    async def run():
        async with _client() as client:
            hooked = await client.post("/api/stripe/webhook", content=json.dumps(event).encode(), headers={"stripe-signature": "good"})
            booked = await client.post("/api/public/book", json=BOOK)
            return hooked, booked

    hooked, booked = asyncio.run(run())
    assert hooked.status_code == 200, hooked.text
    assert db.shops.docs[0]["unresolved_charge_failure"] is True
    assert booked.status_code == 403
    assert "Settings" in booked.json()["detail"]


def test_setup_intent_succeeded_webhook_saves_the_card_for_that_customer(monkeypatch):
    db = _db()
    db.shops.docs.append(_shop(stripe_payment_method_id="pm_shop"))
    db.shop_users.docs.append(_user())
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(server.stripe_sdk.Webhook, "construct_event", lambda payload, sig, secret: json.loads(payload))
    monkeypatch.setattr(server, "get_stripe", lambda: object())
    monkeypatch.setattr(server, "retrieve_setup_intent", lambda client, intent_id: _intent(
        customer="cus_shop",
        metadata={"purpose": "card_on_file", "shop_id": "shop-1"},
        payment_method=_card(id="pm_webhook", card={"brand": "visa", "last4": "1111", "exp_month": 8, "exp_year": 2031}),
    ))
    monkeypatch.setattr(server, "save_payment_method", lambda client, **kwargs: {
        "stripe_payment_method_id": "pm_webhook", "card_brand": "visa", "card_last4": "1111",
        "card_exp_month": 8, "card_exp_year": 2031, "card_status": "active",
    })
    detached = []
    monkeypatch.setattr(server, "detach_payment_method", lambda client, pm: detached.append(pm))
    event = {"type": "setup_intent.succeeded", "data": {"object": {"id": "seti_hook", "customer": "cus_shop"}}}

    async def run():
        async with _client() as client:
            return await client.post("/api/stripe/webhook", content=json.dumps(event).encode(), headers={"stripe-signature": "good"})

    response = asyncio.run(run())
    assert response.status_code == 200, response.text
    assert db.shops.docs[0]["stripe_payment_method_id"] == "pm_webhook"
    assert detached == ["pm_shop"]


def test_a_charge_uses_the_shop_card_not_another_users_card(monkeypatch):
    db = _db()
    db.technicians.docs.append({"id": "owner-1", "role": "owner", "name": "Caleb", "is_active": True})
    db.shops.docs.append(_shop(stripe_customer_id="cus_shop", stripe_payment_method_id="pm_shop"))
    db.shop_users.docs.append(_user(
        id="later", created_at="2026-08-01", stripe_customer_id="cus_other", stripe_payment_method_id="pm_other",
    ))
    db.shop_users.docs.append(_user(
        id="earlier", created_at="2026-01-01", stripe_customer_id="cus_shop", stripe_payment_method_id="pm_user_old",
    ))
    db.jobs.docs.append({
        "id": "job-1", "status": "complete", "price": 125, "shop_id": "shop-1",
        "vehicle_year": 2024, "vehicle_make": "Subaru", "vehicle_model": "Outback",
        "calibration_label": "Static",
    })
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return {"id": "pi_1", "status": "succeeded"}

    monkeypatch.setattr(server, "stripe_configured", lambda: True)
    monkeypatch.setattr(server.stripe_sdk.PaymentIntent, "create", create)
    token = server.make_token("owner-1", "owner")

    async def run():
        async with _client() as client:
            return await client.post("/api/charge-queue/job-1/charge", headers={"Authorization": f"Bearer {token}"})

    response = asyncio.run(run())
    assert response.status_code == 200, response.text
    assert seen["customer"] == "cus_shop"
    assert seen["payment_method"] == "pm_shop"


def test_startup_backfill_is_idempotent(monkeypatch):
    db = _db()
    db.shops.docs.append({"id": "shop-1", "name": "Old Glass"})
    db.shop_users.docs.append(_user(
        stripe_payment_method_id="pm_from_user", stripe_customer_id="cus_from_user",
        card_brand="visa", card_last4="4242", card_exp_month=12, card_exp_year=2099,
        charge_authorization_accepted_at="t",
    ))

    async def run():
        first = await server.backfill_shop_cards()
        second = await server.backfill_shop_cards()
        return first, second

    first, second = asyncio.run(run())
    assert first == 1
    assert second == 0
    assert db.shops.docs[0]["stripe_payment_method_id"] == "pm_from_user"
    assert db.shops.docs[0]["billing_card_backfilled"] is True
