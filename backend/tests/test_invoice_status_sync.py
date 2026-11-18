"""A successful card charge or invoice.paid webhook marks the local invoice paid.

The first job_invoices row is inserted as open. That insert is not the last
word: the charge and the paid webhook update the same row, and a later
invoice.finalized event must not reopen a job that is already paid.

    cd backend && pytest tests/test_invoice_status_sync.py -v
"""
import asyncio
import logging
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from billing import invoice_due_on  # noqa: E402

# 11:30pm America/Phoenix on Nov 18 is already Nov 19 in UTC.
# Seven Phoenix days later is Nov 25, not Nov 26.
COMPLETED = "2026-11-19T06:30:00+00:00"
DUE = "2026-11-25"
STALE = "2026-11-18T15:00:00+00:00"


def test_due_date_is_seven_phoenix_days_after_completion():
    assert invoice_due_on({"actual_completion": COMPLETED}) == DUE
    assert invoice_due_on({"actual_completion": "2026-11-18T16:00:00+00:00"}) == DUE


def _match(doc, query):
    for key, expected in (query or {}).items():
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

    def limit(self, n):
        self.docs = self.docs[:n]
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
                for key, value in update.get("$setOnInsert", {}).items():
                    doc.setdefault(key, value)
                return None
        if upsert:
            doc = {k: v for k, v in (query or {}).items() if not isinstance(v, dict)}
            doc.update(update.get("$setOnInsert") or {})
            doc.update(update.get("$set") or {})
            self.docs.append(doc)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class _DB:
    def __init__(self):
        self.technicians = _Store()
        self.shops = _Store()
        self.shop_users = _Store()
        self.jobs = _Store()
        self.job_invoices = _Store()
        self.xero_invoices = _Store()
        self.mock_xero_invoices = _Store()


def _job(**overrides):
    doc = {
        "id": "job-1",
        "shop_id": "shop-1",
        "shop_name": "Star Windshield",
        "status": "complete",
        "price": 185.0,
        "payment_mode": "invoice_hold",
        "payment_status": "unpaid",
        "invoice_status": "open",
        "invoice_id": "in_123",
        "stripe_invoice_id": "in_123",
        "calibration_label": "Static ADAS Calibration",
        "actual_completion": COMPLETED,
        "updated_at": STALE,
    }
    doc.update(overrides)
    return doc


def _invoice(**overrides):
    doc = {
        "invoice_id": "in_123",
        "stripe_invoice_id": "in_123",
        "provider": "stripe",
        "status": "open",
        "contact_name": "Star Windshield",
        "total": 185.0,
        "job_id": "job-1",
        "created_at": COMPLETED,
        "due_at": DUE,
    }
    doc.update(overrides)
    return doc


@pytest.fixture
def world(monkeypatch):
    db = _DB()
    db.technicians.docs.append({"id": "tech-1", "role": "owner", "name": "Caleb"})
    db.shops.docs.append({
        "id": "shop-1",
        "name": "Star Windshield",
        "contact_email": "shop@example.com",
        "stripe_customer_id": "cus_ready",
        "stripe_payment_method_id": "pm_ready",
        "card_brand": "visa",
        "card_last4": "4242",
        "card_exp_month": 12,
        "card_exp_year": 2030,
        "card_status": "active",
    })
    db.shop_users.docs.append({
        "id": "su-1", "shop_id": "shop-1", "is_active": True, "email": "shop@example.com",
    })
    db.jobs.docs.append(_job())
    db.job_invoices.docs.append(_invoice())
    calls = {"charge": [], "paid_out_of_band": [], "email": []}

    def charge(*args, **kwargs):
        calls["charge"].append(kwargs or args)
        return {"outcome": "succeeded", "payment_intent_id": "pi_test"}

    def paid_out_of_band(*args, **kwargs):
        calls["paid_out_of_band"].append(args)

    async def email(*args, **kwargs):
        calls["email"].append(kwargs or args)

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    original = server.db
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "get_stripe", lambda: object())
    monkeypatch.setattr(server, "stripe_charge_job", charge)
    monkeypatch.setattr(server, "mark_invoice_paid_out_of_band", paid_out_of_band)
    monkeypatch.setattr(server, "send_email", email)
    monkeypatch.setattr(server, "_send_booking_message", email)
    yield {"db": db, "calls": calls, "owner": server.make_token("tech-1", "owner")}
    monkeypatch.setattr(server, "db", original)


def _client():
    transport = httpx.ASGITransport(app=server.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _stripe_event(monkeypatch, kind, obj):
    def construct(payload, signature, secret):
        assert secret == "whsec_test"
        return {"type": kind, "data": {"object": obj}}

    monkeypatch.setattr(server.stripe_sdk.Webhook, "construct_event", construct)


def test_charge_marks_the_job_and_the_invoice_row_paid(world):
    async def run():
        async with _client() as client:
            charged = await client.post(
                "/api/jobs/job-1/charge-card", headers=_auth(world["owner"]),
            )
            listed = await client.get("/api/invoices", headers=_auth(world["owner"]))
        assert charged.status_code == 200, charged.text
        job = charged.json()["job"]
        assert job["payment_status"] == "paid"
        assert job["invoice_status"] == "paid"
        assert job["updated_at"] > STALE
        row = await world["db"].job_invoices.find_one({"job_id": "job-1"})
        assert row["status"] == "paid"
        assert row["paid_at"]
        assert listed.status_code == 200, listed.text
        match = next(item for item in listed.json() if item["job_id"] == "job-1")
        assert match["status"] == "paid"
        assert match["due_at"] == DUE

    asyncio.run(run())


def test_settle_stores_due_date_and_an_open_row_does_not_reopen_a_paid_job(world, monkeypatch):
    async def run():
        monkeypatch.setattr(server, "billing_enabled", lambda: False)
        monkeypatch.setattr(server, "get_stripe", lambda: None)
        fresh = _job(
            id="job-new",
            invoice_id=None,
            stripe_invoice_id=None,
            invoice_status="pending",
            payment_status=None,
            payment_mode="charge_on_completion",
        )
        world["db"].jobs.docs.append(fresh)
        settled = await server._settle_completed_job("job-new")
        assert settled["payment_status"] == "not_charged"
        assert settled["invoice_status"] == "open"
        assert settled["invoice_due_at"] == DUE
        created = await world["db"].job_invoices.find_one({"job_id": "job-new"})
        assert created["status"] == "open"
        assert created["due_at"] == DUE

        # The first insert stays open in memory. A later settle must not copy
        # that open status onto a job the card has already paid.
        world["db"].jobs.docs.append(_job(
            id="job-paid",
            invoice_id=None,
            stripe_invoice_id=None,
            payment_status="paid",
            invoice_status="paid",
            charged_at="2026-11-18T17:00:00+00:00",
            payment_mode="charge_on_completion",
        ))
        world["db"].job_invoices.docs.append(_invoice(
            job_id="job-paid", invoice_id="local-job-paid", status="open", due_at=None,
        ))
        again = await server._settle_completed_job("job-paid")
        assert again["invoice_status"] == "paid"
        assert again["payment_status"] == "paid"
        row = await world["db"].job_invoices.find_one({"job_id": "job-paid"})
        assert row["status"] == "paid"
        assert row["paid_at"]
        assert row["due_at"] == DUE

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["invoice.paid", "invoice.payment_succeeded"])
def test_paid_webhook_marks_the_invoice_row_paid(world, monkeypatch, kind, caplog):
    async def run():
        _stripe_event(monkeypatch, kind, {
            "id": "in_123",
            "status": "paid",
            "metadata": {"job_id": "job-1"},
        })
        with caplog.at_level(logging.INFO):
            async with _client() as client:
                response = await client.post(
                    "/api/stripe/webhook",
                    content=b"{}",
                    headers={"stripe-signature": "t=1,v1=test"},
                )
        assert response.status_code == 200, response.text
        job = await world["db"].jobs.find_one({"id": "job-1"})
        row = await world["db"].job_invoices.find_one({"job_id": "job-1"})
        assert job["invoice_status"] == "paid"
        assert job["payment_status"] == "paid"
        assert job["updated_at"] > STALE
        assert row["status"] == "paid"
        assert row["paid_at"]
        assert kind in caplog.text

    asyncio.run(run())


def test_finalized_after_paid_does_not_reopen_the_job(world, monkeypatch):
    async def run():
        world["db"].jobs.docs[0].update({
            "payment_status": "paid",
            "invoice_status": "paid",
            "charged_at": "2026-11-18T17:00:00+00:00",
        })
        world["db"].job_invoices.docs[0].update({"status": "paid", "paid_at": "2026-11-18T17:00:00+00:00"})
        _stripe_event(monkeypatch, "invoice.finalized", {
            "id": "in_123",
            "status": "open",
            "hosted_invoice_url": "https://pay.stripe.test/in_123",
            "metadata": {"job_id": "job-1"},
        })
        async with _client() as client:
            response = await client.post(
                "/api/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=1,v1=test"},
            )
        assert response.status_code == 200, response.text
        job = await world["db"].jobs.find_one({"id": "job-1"})
        row = await world["db"].job_invoices.find_one({"job_id": "job-1"})
        assert job["invoice_status"] == "paid"
        assert job["payment_status"] == "paid"
        assert job["invoice_url"] == "https://pay.stripe.test/in_123"
        assert row["status"] == "paid"

        unpaid = _job(id="job-open", invoice_status="pending", payment_status=None, charged_at=None)
        world["db"].jobs.docs.append(unpaid)
        _stripe_event(monkeypatch, "invoice.finalized", {
            "id": "in_open",
            "status": "open",
            "hosted_invoice_url": "https://pay.stripe.test/in_open",
            "metadata": {"job_id": "job-open"},
        })
        async with _client() as client:
            follow = await client.post(
                "/api/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=1,v1=test"},
            )
        assert follow.status_code == 200, follow.text
        opened = await world["db"].jobs.find_one({"id": "job-open"})
        assert opened["invoice_status"] == "open"

    asyncio.run(run())


def test_late_fee_payment_does_not_mark_the_calibration_invoice_paid(world, monkeypatch):
    async def run():
        _stripe_event(monkeypatch, "invoice.paid", {
            "id": "in_late",
            "status": "paid",
            "metadata": {"job_id": "job-1", "kind": "late_fee"},
        })
        async with _client() as client:
            response = await client.post(
                "/api/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=1,v1=test"},
            )
        assert response.status_code == 200, response.text
        job = await world["db"].jobs.find_one({"id": "job-1"})
        row = await world["db"].job_invoices.find_one({"job_id": "job-1"})
        assert job["payment_status"] == "unpaid"
        assert job["invoice_status"] == "open"
        assert job.get("late_fee_paid_at")
        assert row["status"] == "open"

    asyncio.run(run())
