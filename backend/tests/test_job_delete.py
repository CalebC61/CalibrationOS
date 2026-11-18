"""Owner delete of a job. No live Mongo.

    cd backend && pytest tests/test_job_delete.py -v

Deleting removes the job and the rows that only exist for it. It does not
cancel, reschedule, email, text, or call Xero or Stripe. Invoice rows stay,
because the invoice in Xero or Stripe is left alone.
"""
import asyncio
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402

START = "2026-11-17T16:00:00+00:00"
END = "2026-11-17T17:00:00+00:00"


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

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, limit):
        return self.docs[:limit]


class _Result:
    def __init__(self, count):
        self.deleted_count = count


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

    async def delete_one(self, query):
        for index, doc in enumerate(self.docs):
            if _match(doc, query):
                del self.docs[index]
                return _Result(1)
        return _Result(0)

    async def delete_many(self, query):
        kept = [doc for doc in self.docs if not _match(doc, query)]
        removed = len(self.docs) - len(kept)
        self.docs = kept
        return _Result(removed)


class _DB:
    def __init__(self):
        self.technicians = _Store()
        self.shop_users = _Store()
        self.shops = _Store()
        self.jobs = _Store()
        self.vehicles = _Store()
        self.documents = _Store()
        self.new_booking_alerts = _Store()
        self.contractor_offers = _Store()
        self.owner_action_tokens = _Store()
        self.xero_invoices = _Store()
        self.mock_xero_invoices = _Store()
        self.job_invoices = _Store()
        self.sms_log = _Store()
        self.email_log = _Store()
        self.email_outbox = _Store()


def _job(**overrides):
    doc = {
        "id": "job-1",
        "shop_id": "shop-1",
        "shop_name": "Star Windshield",
        "technician_id": "tech-1",
        "status": "booked",
        "vehicle_id": "veh-1",
        "vehicle_year": 2020,
        "vehicle_make": "Honda",
        "vehicle_model": "Pilot",
        "calibration_label": "Static ADAS Calibration",
        "scheduled_start": START,
        "scheduled_end": END,
        "price": 125.0,
        "notification_phone": "+16025550100",
        "notification_email": "shop@example.com",
    }
    doc.update(overrides)
    return doc


@pytest.fixture
def world(monkeypatch):
    db = _DB()
    db.technicians.docs.append({"id": "tech-1", "role": "owner", "name": "Caleb"})
    db.technicians.docs.append({"id": "tech-field", "role": "technician", "name": "Field"})
    db.technicians.docs.append({"id": "tech-contractor", "role": "contractor", "name": "West"})
    db.shops.docs.append({
        "id": "shop-1", "name": "Star Windshield", "status": "active",
        "booking_link_token": "tok-shop",
    })
    db.shop_users.docs.append({
        "id": "su-1", "shop_id": "shop-1", "email": "shop@example.com", "is_active": True,
    })
    db.jobs.docs.extend([
        _job(
            xero_invoice_number="INV-1042",
            xero_invoice_id="xero-inv-1",
            xero_draft_status="draft",
            stripe_invoice_id="in_123",
            invoice_id="in_123",
        ),
        _job(id="job-keep", vehicle_id="veh-keep", shop_name="Other Glass"),
        _job(id="job-share", vehicle_id="veh-shared"),
        _job(id="job-share-other", vehicle_id="veh-shared"),
    ])
    db.vehicles.docs.extend([
        {"id": "veh-1", "make": "Honda"},
        {"id": "veh-keep", "make": "Toyota"},
        {"id": "veh-shared", "make": "Ford"},
    ])
    db.documents.docs.extend([
        {"id": "doc-1", "job_id": "job-1", "file_name": "scan.pdf"},
        {"id": "doc-keep", "job_id": "job-keep", "file_name": "keep.pdf"},
    ])
    db.new_booking_alerts.docs.extend([
        {"id": "alert-1", "job_id": "job-1", "owner_id": "tech-1", "seen_at": None, "shop_name": "Star Windshield"},
        {"id": "alert-keep", "job_id": "job-keep", "owner_id": "tech-1", "seen_at": None, "shop_name": "Other Glass"},
    ])
    db.contractor_offers.docs.append({"id": "offer-1", "job_id": "job-1", "status": "pending"})
    db.owner_action_tokens.docs.append({"id": "token-1", "job_id": "job-1", "action": "approve"})
    db.xero_invoices.docs.append({
        "invoice_id": "INV-1042", "job_id": "job-1", "provider": "xero",
        "status": "DRAFT", "contact_name": "Star Windshield", "total": 125.0,
        "created_at": START,
    })
    db.job_invoices.docs.append({
        "invoice_id": "in_123", "job_id": "job-1", "provider": "stripe",
        "stripe_invoice_id": "in_123", "status": "open",
        "contact_name": "Star Windshield", "total": 125.0, "created_at": START,
    })
    calls = []

    async def sms(*args, **kwargs):
        calls.append("sms")

    async def email(*args, **kwargs):
        calls.append("email")

    async def shop_event(*args, **kwargs):
        calls.append("email_shop_event")

    async def booking_message(*args, **kwargs):
        calls.append("booking_message")

    async def xero(*args, **kwargs):
        calls.append("xero")
        return {}

    def stripe_client():
        calls.append("stripe")
        raise AssertionError("delete must not call Stripe")

    def charge(*args, **kwargs):
        calls.append("stripe_charge")
        raise AssertionError("delete must not charge a card")

    original = server.db
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "mock_send_sms", sms)
    monkeypatch.setattr(server, "send_email", email)
    monkeypatch.setattr(server, "email_shop_event", shop_event)
    monkeypatch.setattr(server, "_send_booking_message", booking_message)
    monkeypatch.setattr(server, "create_invoice_for_job", xero)
    monkeypatch.setattr(server, "get_stripe", stripe_client)
    monkeypatch.setattr(server, "stripe_charge_job", charge)
    yield {
        "db": db,
        "calls": calls,
        "owner": server.make_token("tech-1", "owner"),
        "technician": server.make_token("tech-field", "technician"),
        "contractor": server.make_token("tech-contractor", "contractor"),
        "shop": server.make_portal_token("su-1"),
    }
    monkeypatch.setattr(server, "db", original)


def _client():
    transport = httpx.ASGITransport(app=server.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_owner_delete_removes_the_job_and_sends_nothing(world):
    async def run():
        async with _client() as client:
            deleted = await client.delete("/api/jobs/job-1", headers=_auth(world["owner"]))
            assert deleted.status_code == 200, deleted.text
            assert deleted.json()["id"] == "job-1"
            missing = await client.get("/api/jobs/job-1", headers=_auth(world["owner"]))
            portal = await client.get("/api/portal/jobs", headers=_auth(world["shop"]))
            invoices = await client.get("/api/invoices", headers=_auth(world["owner"]))
        assert missing.status_code == 404
        assert world["calls"] == []
        assert [job["id"] for job in world["db"].jobs.docs] == ["job-keep", "job-share", "job-share-other"]
        assert all(job.get("status") != "cancelled" for job in world["db"].jobs.docs)
        portal_ids = [job["id"] for job in portal.json()]
        assert "job-1" not in portal_ids
        assert "job-keep" in portal_ids
        assert [doc["id"] for doc in world["db"].documents.docs] == ["doc-keep"]
        assert [alert["id"] for alert in world["db"].new_booking_alerts.docs] == ["alert-keep"]
        assert world["db"].contractor_offers.docs == [{"id": "offer-1", "job_id": "job-1", "status": "pending"}]
        assert world["db"].owner_action_tokens.docs == []
        assert [row["id"] for row in world["db"].vehicles.docs] == ["veh-keep", "veh-shared"]
        assert world["db"].sms_log.docs == []
        assert world["db"].email_log.docs == []
        assert world["db"].email_outbox.docs == []
        listed = {row["invoice_id"] for row in invoices.json()}
        assert "INV-1042" in listed
        assert "in_123" in listed
        assert len(world["db"].xero_invoices.docs) == 1
        assert len(world["db"].job_invoices.docs) == 1

    asyncio.run(run())


def test_shop_and_other_logins_cannot_delete_a_job(world):
    async def run():
        async with _client() as client:
            shop = await client.delete("/api/jobs/job-1", headers=_auth(world["shop"]))
            technician = await client.delete("/api/jobs/job-1", headers=_auth(world["technician"]))
            contractor = await client.delete("/api/jobs/job-1", headers=_auth(world["contractor"]))
            anonymous = await client.delete("/api/jobs/job-1")
            missing = await client.delete("/api/jobs/missing", headers=_auth(world["owner"]))
        assert shop.status_code == 403
        assert technician.status_code == 403
        assert contractor.status_code == 403
        assert anonymous.status_code == 401
        assert missing.status_code == 404
        assert any(job["id"] == "job-1" for job in world["db"].jobs.docs)
        stored = next(job for job in world["db"].jobs.docs if job["id"] == "job-1")
        assert stored["status"] == "booked"
        assert world["calls"] == []
        assert len(world["db"].documents.docs) == 2

    asyncio.run(run())
