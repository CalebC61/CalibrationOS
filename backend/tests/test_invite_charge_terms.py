"""Invite setup records charge-terms acceptance the same way self-signup does.

Self-signup writes charge_authorization_accepted_at only when the shop accepted
the charge terms and a card was saved. An invite signs first and saves the card
later. The agreement signature alone is not that acceptance.

    cd backend && pytest tests/test_invite_charge_terms.py -v
"""
import asyncio
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from onboarding import AGREEMENT_VERSION, CARD_MESSAGES, CHARGE_ACCEPTANCE_TEXT  # noqa: E402


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
        self.invites = _Store()
        self.jobs = _Store()
        self.vehicles = _Store()
        self.card_changes = _Store()
        self.technicians = _Store()
        self.email_outbox = _Store()


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test")


def _install(monkeypatch):
    db = _DB()
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "get_stripe", lambda: None)

    async def quiet(*args, **kwargs):
        return {"delivered": False}

    monkeypatch.setattr(server, "send_email", quiet)
    monkeypatch.setattr(server, "_send_booking_message", quiet)
    return db


def _shop(**overrides):
    payload = {
        "id": "shop-1",
        "name": "Jarvis Glass",
        "status": "active",
        "requires_billing_setup": True,
        "address": "100 W Guadalupe Rd, Gilbert, AZ",
    }
    payload.update(overrides)
    return payload


def _invite():
    return {
        "id": "inv-1",
        "token": "tok-1",
        "shop_id": "shop-1",
        "shop_name": "Jarvis Glass",
        "recipient_email": "ada@jarvis.example",
        "status": "pending",
        "expires_at": "2099-01-01T00:00:00+00:00",
    }


def _register(**overrides):
    payload = {
        "invite_token": "tok-1",
        "full_name": "Ada Glass",
        "password": "longenough",
        "terms_signature": "Ada Glass",
        "terms_agreed": True,
        "charge_accepted": True,
    }
    payload.update(overrides)
    return payload


BOOK = {
    "job_address": "200 Other St, Mesa, AZ",
    "scheduled_start": "2026-11-20T17:00:00+00:00",
    "customer_last_name": "Ng",
    "year": 2024,
    "make": "Subaru",
    "model": "Outback",
    "adas_system": "multi_camera",
    "calibration_type": "triple",
    "notification_phone": "4805550100",
}


def _ready_user(**overrides):
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
        "agreement_version": AGREEMENT_VERSION,
        "terms_signed_at": "2026-01-01T00:00:00+00:00",
        "terms_signature": "Ada Glass",
        "charge_authorization_accepted_at": None,
    }
    payload.update(overrides)
    return payload


def test_booking_post_rejects_a_shop_with_no_valid_card(monkeypatch):
    db = _install(monkeypatch)
    db.shops.docs.append(_shop(
        stripe_customer_id="cus_shop",
        billing_card_backfilled=True,
        charge_authorization_accepted_at="2026-01-01T00:00:00+00:00",
    ))
    db.shop_users.docs.append(_ready_user(
        stripe_payment_method_id=None,
        card_brand=None,
        card_last4=None,
        card_status=None,
        charge_authorization_accepted_at="2026-01-01T00:00:00+00:00",
    ))
    headers = {"Authorization": f"Bearer {server.make_portal_token('user-1')}"}

    async def run():
        async with _client() as client:
            missing = await client.post("/api/portal/book", json=BOOK, headers=headers)
            db.shops.docs[0]["stripe_payment_method_id"] = "pm_old"
            db.shops.docs[0]["card_last4"] = "4242"
            db.shops.docs[0]["card_exp_month"] = 1
            db.shops.docs[0]["card_exp_year"] = 2020
            db.shops.docs[0]["card_status"] = "active"
            db.shop_users.docs[0]["stripe_payment_method_id"] = "pm_old"
            db.shop_users.docs[0]["card_exp_month"] = 1
            db.shop_users.docs[0]["card_exp_year"] = 2020
            db.shop_users.docs[0]["card_status"] = "active"
            expired = await client.post("/api/portal/book", json=BOOK, headers=headers)
            db.shops.docs[0]["card_status"] = "removed"
            db.shops.docs[0]["stripe_payment_method_id"] = None
            db.shop_users.docs[0]["card_status"] = "removed"
            db.shop_users.docs[0]["stripe_payment_method_id"] = None
            removed = await client.post("/api/portal/book", json=BOOK, headers=headers)
            return missing, expired, removed

    missing, expired, removed = asyncio.run(run())
    assert missing.status_code == 403, missing.text
    assert missing.json()["detail"] == CARD_MESSAGES["missing"]
    assert expired.status_code == 403, expired.text
    assert expired.json()["detail"] == CARD_MESSAGES["expired"]
    assert removed.status_code == 403, removed.text
    assert removed.json()["detail"] == CARD_MESSAGES["removed"]
    assert db.jobs.docs == []


def test_booking_post_rejects_a_shop_that_has_not_accepted_charge_terms(monkeypatch):
    db = _install(monkeypatch)
    db.shops.docs.append(_shop(
        stripe_customer_id="cus_shop",
        stripe_payment_method_id="pm_shop",
        card_brand="visa",
        card_last4="4242",
        card_exp_month=12,
        card_exp_year=2099,
        card_status="active",
        billing_card_backfilled=True,
        terms_signed_at="2026-01-01T00:00:00+00:00",
        terms_signed_by="Ada Glass",
        charge_authorization_accepted_at=None,
    ))
    db.shop_users.docs.append(_ready_user())
    headers = {"Authorization": f"Bearer {server.make_portal_token('user-1')}"}

    async def missing_address(*args, **kwargs):
        raise server.AddressNotFound("We couldn't find that address")

    monkeypatch.setattr(server, "geocode_address", missing_address)

    async def run():
        async with _client() as client:
            blocked = await client.post("/api/portal/book", json=BOOK, headers=headers)
            accepted = await client.post("/api/portal/accept-charge", json={"accepted": True}, headers=headers)
            opened = await client.post("/api/portal/book", json=BOOK, headers=headers)
            return blocked, accepted, opened

    blocked, accepted, opened = asyncio.run(run())
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["detail"] == CARD_MESSAGES["terms"]
    assert db.jobs.docs == []
    assert accepted.status_code == 200, accepted.text
    assert db.shops.docs[0]["charge_authorization_accepted_at"]
    assert db.shop_users.docs[0]["charge_authorization_accepted_at"]
    assert db.shop_users.docs[0]["charge_authorization_text"] == CHARGE_ACCEPTANCE_TEXT
    assert opened.status_code != 403, opened.text
    assert opened.status_code == 400, opened.text
    assert db.jobs.docs == []


def test_invite_registration_requires_the_same_charge_acceptance_as_signup(monkeypatch):
    db = _install(monkeypatch)
    db.shops.docs.append(_shop())
    db.invites.docs.append(_invite())

    async def run():
        async with _client() as client:
            return await client.post(
                "/api/public/invites/tok-1/register",
                json=_register(charge_accepted=False),
            )

    response = asyncio.run(run())
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Accept the charge terms to continue."
    assert db.shop_users.docs == []


def test_invite_stores_charge_acceptance_and_applies_it_when_the_card_is_saved(monkeypatch):
    db = _install(monkeypatch)
    db.shops.docs.append(_shop())
    db.invites.docs.append(_invite())

    def retrieve(client, intent_id):
        user = db.shop_users.docs[0]
        return {
            "id": intent_id,
            "status": "succeeded",
            "customer": "cus_new",
            "metadata": {
                "purpose": "card_on_file",
                "shop_id": "shop-1",
                "shop_user_id": user["id"],
            },
            "payment_method": {
                "id": "pm_real",
                "type": "card",
                "card": {"brand": "visa", "last4": "4242", "exp_month": 12, "exp_year": 2099},
            },
        }

    def save(client, **kwargs):
        assert kwargs["customer_id"] == "cus_new"
        assert kwargs["payment_method_id"] == "pm_real"
        return {
            "stripe_customer_id": "cus_new",
            "stripe_payment_method_id": "pm_real",
            "card_brand": "visa",
            "card_last4": "4242",
            "card_exp_month": 12,
            "card_exp_year": 2099,
            "card_status": "active",
        }

    monkeypatch.setattr(server, "retrieve_setup_intent", retrieve)
    monkeypatch.setattr(server, "save_payment_method", save)

    async def run():
        async with _client() as client:
            created = await client.post("/api/public/invites/tok-1/register", json=_register(), headers={"user-agent": "shop-browser"})
            user = dict(db.shop_users.docs[0])
            shop_at_register = dict(db.shops.docs[0])
            monkeypatch.setattr(server, "get_stripe", lambda: object())
            saved = await client.post(
                "/api/portal/payment-method",
                json={"setup_intent_id": "seti_ok"},
                headers={"Authorization": f"Bearer {created.json()['token']}"},
            )
            me = await client.get(
                "/api/portal/me",
                headers={"Authorization": f"Bearer {created.json()['token']}"},
            )
            return created, user, shop_at_register, saved, me

    created, user_at_register, shop_at_register, saved, me = asyncio.run(run())
    assert created.status_code == 200, created.text
    assert user_at_register["charge_terms_accepted_at"]
    assert user_at_register["charge_authorization_accepted_at"] is None
    assert user_at_register["charge_authorization_text"] == CHARGE_ACCEPTANCE_TEXT
    assert user_at_register["charge_authorization_ip"] is not None
    assert user_at_register["charge_authorization_user_agent"] == "shop-browser"
    assert user_at_register["terms_signature"] == "Ada Glass"
    assert shop_at_register.get("charge_authorization_accepted_at") in (None, "")
    assert saved.status_code == 200, saved.text
    assert saved.json()["needs_acceptance"] is False
    assert db.shop_users.docs[0]["charge_authorization_accepted_at"]
    assert db.shops.docs[0]["charge_authorization_accepted_at"] == db.shop_users.docs[0]["charge_authorization_accepted_at"]
    assert db.shop_users.docs[0]["charge_authorization_text"] == CHARGE_ACCEPTANCE_TEXT
    assert db.shop_users.docs[0]["stripe_payment_method_id"] == "pm_real"
    assert me.status_code == 200, me.text
    assert me.json()["setup"]["allowed"] is True
    assert me.json()["setup"]["accepted"] is True
    assert me.json()["setup"]["has_card"] is True


def test_saving_a_card_does_not_treat_the_agreement_signature_as_charge_acceptance(monkeypatch):
    db = _install(monkeypatch)
    db.shops.docs.append(_shop(stripe_customer_id="cus_shop", billing_card_backfilled=True))
    db.shop_users.docs.append(_ready_user(
        stripe_payment_method_id=None,
        card_brand=None,
        card_last4=None,
        card_status=None,
    ))

    def retrieve(client, intent_id):
        return {
            "id": intent_id,
            "status": "succeeded",
            "customer": "cus_shop",
            "metadata": {"purpose": "card_on_file", "shop_id": "shop-1", "shop_user_id": "user-1"},
            "payment_method": {
                "id": "pm_real",
                "type": "card",
                "card": {"brand": "visa", "last4": "4242", "exp_month": 12, "exp_year": 2099},
            },
        }

    monkeypatch.setattr(server, "get_stripe", lambda: object())
    monkeypatch.setattr(server, "retrieve_setup_intent", retrieve)
    monkeypatch.setattr(server, "save_payment_method", lambda client, **kwargs: {
        "stripe_customer_id": "cus_shop",
        "stripe_payment_method_id": "pm_real",
        "card_brand": "visa",
        "card_last4": "4242",
        "card_exp_month": 12,
        "card_exp_year": 2099,
        "card_status": "active",
    })
    headers = {"Authorization": f"Bearer {server.make_portal_token('user-1')}"}

    async def run():
        async with _client() as client:
            saved = await client.post("/api/portal/payment-method", json={"setup_intent_id": "seti_ok"}, headers=headers)
            booked = await client.post("/api/portal/book", json=BOOK, headers=headers)
            return saved, booked

    saved, booked = asyncio.run(run())
    assert saved.status_code == 200, saved.text
    assert saved.json()["needs_acceptance"] is True
    assert db.shop_users.docs[0].get("charge_authorization_accepted_at") in (None, "")
    assert db.shops.docs[0].get("charge_authorization_accepted_at") in (None, "")
    assert db.shop_users.docs[0]["stripe_payment_method_id"] == "pm_real"
    assert booked.status_code == 403, booked.text
    assert booked.json()["detail"] == CARD_MESSAGES["terms"]
    assert db.jobs.docs == []


def test_owner_invited_shops_are_not_listed_as_new_shops(monkeypatch):
    """New shops is accounts the shop created. An owner invite is not one of those."""
    db = _install(monkeypatch)
    db.technicians.docs.append({"id": "owner-1", "name": "Caleb", "role": "owner", "is_active": True})
    db.shops.docs.append(_shop(id="invited", name="Invited Glass", created_at="2026-11-18T00:00:00+00:00"))
    db.shops.docs.append(_shop(
        id="self",
        name="Self Glass",
        signup_source="self_serve",
        created_at="2026-11-18T00:00:00+00:00",
    ))
    headers = {"Authorization": f"Bearer {server.make_token('owner-1', 'owner')}"}

    async def run():
        async with _client() as client:
            return await client.get("/api/new-shops", headers=headers)

    response = asyncio.run(run())
    assert response.status_code == 200, response.text
    ids = [row["id"] for row in response.json()]
    assert ids == ["self"]
