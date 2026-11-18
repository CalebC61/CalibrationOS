"""30-day warranty redos.

Phoenix dates decide the price. A shop can only link its own completed jobs.
An eligible Complete files no Xero draft and charges no card.

    cd backend && pytest tests/test_warranty.py -v
"""
import asyncio
import os
import sys
from datetime import datetime, time, timedelta, timezone

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from billing import billing_plan  # noqa: E402
from business_time import BUSINESS_TZ, business_date  # noqa: E402
from charging import chargeable_reason  # noqa: E402
from onboarding import READY_BILLING  # noqa: E402
from warranty import (  # noqa: E402
    BILLED_LABEL,
    FREE_LABEL,
    SKIP_REASON,
    days_after,
    is_within_warranty,
)
from xero_invoice import price_updates_for_calibration_change  # noqa: E402

TODAY = business_date()


def phoenix_noon(day):
    moment = datetime.combine(day, time(12, 0), tzinfo=BUSINESS_TZ)
    return moment.astimezone(timezone.utc).isoformat()


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


class _Result:
    modified_count = 1


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
                for key, value in update.get("$setOnInsert", {}).items():
                    doc.setdefault(key, value)
                for key in update.get("$unset", {}):
                    doc.pop(key, None)
                for key, value in update.get("$push", {}).items():
                    doc.setdefault(key, []).append(value)
                return _Result()
        if upsert:
            doc = {k: v for k, v in query.items() if not isinstance(v, dict)}
            doc.update(update.get("$setOnInsert") or {})
            doc.update(update.get("$set") or {})
            self.docs.append(doc)
        return _Result()

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def count_documents(self, query):
        return len([doc for doc in self.docs if _match(doc, query)])


class _DB:
    def __init__(self):
        self.technicians = _Store()
        self.shops = _Store()
        self.shop_users = _Store()
        self.jobs = _Store()
        self.vehicles = _Store()
        self.documents = _Store()
        self.job_invoices = _Store()
        self.new_booking_alerts = _Store()


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
        "vehicle_id": "veh-1",
        "vehicle_year": 2020,
        "vehicle_make": "Honda",
        "vehicle_model": "Civic",
        "calibration_type": "static",
        "calibration_label": "Static ADAS Calibration",
        "price": 125.0,
        "calibration_price": 125.0,
        "scheduled_start": phoenix_noon(TODAY + timedelta(days=1)),
        "scheduled_end": phoenix_noon(TODAY + timedelta(days=1)),
        "notes": None,
        "edit_history": [],
    }
    doc.update(overrides)
    return doc


def _completed(job_id, shop_id, days_ago, **overrides):
    return _job(
        id=job_id,
        shop_id=shop_id,
        status="complete",
        actual_completion=phoenix_noon(TODAY - timedelta(days=days_ago)),
        **overrides,
    )


@pytest.fixture
def world(monkeypatch):
    db = _DB()
    db.technicians.docs.append({
        "id": "tech-1", "role": "owner", "name": "Caleb", "email": "caleb@thecalibrationcrew.us",
    })
    db.shops.docs.append({
        "id": "shop-1", "name": "Glass Co", "status": "active",
        "address": "100 W Main, Phoenix, AZ", "booking_link_token": "tok-a",
        "pricing_tier": "standard", "contact_email": "dana@glass.example",
        **READY_BILLING,
    })
    db.shops.docs.append({
        "id": "shop-2", "name": "Other Shop", "status": "active",
        "booking_link_token": "tok-b", "pricing_tier": "standard",
    })
    db.shop_users.docs.append({
        "id": "su-1", "shop_id": "shop-1", "is_active": True,
        "email": "dana@glass.example", "full_name": "Dana",
    })
    db.jobs.docs.append(_job())
    db.jobs.docs.append(_completed("done-30", "shop-1", 29, customer_last_name="Reed"))
    db.jobs.docs.append(_completed("done-31", "shop-1", 30, customer_last_name="Reed"))
    db.jobs.docs.append(_completed("done-recent", "shop-1", 10, customer_last_name="Reed"))
    db.jobs.docs.append(_completed("done-old", "shop-1", 91, customer_last_name="Old"))
    db.jobs.docs.append(_job(id="open-1", status="booked"))
    db.jobs.docs.append(_completed("other-done", "shop-2", 5, customer_last_name="Other"))
    calls = {"email": [], "sms": [], "xero": [], "charge": []}

    async def email(*args, **kwargs):
        calls["email"].append((args, kwargs))
        return {"delivered": False}

    async def sms(*args, **kwargs):
        calls["sms"].append((args, kwargs))

    async def booking_message(*args, **kwargs):
        calls["email"].append(("booking", args, kwargs))
        return None

    def xero_file(*args, **kwargs):
        calls["xero"].append((args, kwargs))
        raise AssertionError("Xero draft should not be filed")

    async def charge(*args, **kwargs):
        calls["charge"].append((args, kwargs))
        raise AssertionError("card should not be charged")

    async def lock(_job_id):
        return True

    async def unlock(_job_id):
        return None

    original = server.db
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "send_email", email)
    monkeypatch.setattr(server, "mock_send_sms", sms)
    monkeypatch.setattr(server, "_send_booking_message", booking_message)
    monkeypatch.setattr(server, "file_calibration_draft", xero_file)
    monkeypatch.setattr(server, "_charge_saved_card", charge)
    monkeypatch.setattr(server, "_acquire_xero_lock", lock)
    monkeypatch.setattr(server, "_release_xero_lock", unlock)
    monkeypatch.setattr(server, "billing_enabled", lambda: False)
    monkeypatch.setattr(server, "get_stripe", lambda: None)
    yield {
        "db": db,
        "calls": calls,
        "owner": server.make_token("tech-1", "owner"),
        "portal": server.make_portal_token("su-1"),
    }
    monkeypatch.setattr(server, "db", original)


def _client():
    transport = httpx.ASGITransport(app=server.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_thirty_phoenix_days_is_free_and_thirty_one_is_billed():
    original = datetime(2026, 1, 1, 19, 0, tzinfo=timezone.utc)  # noon Phoenix, Jan 1
    day_30 = datetime(2026, 1, 31, 19, 0, tzinfo=timezone.utc)
    day_31 = datetime(2026, 2, 1, 19, 0, tzinfo=timezone.utc)
    assert days_after(original, day_30) == 30
    assert days_after(original, day_31) == 31
    assert is_within_warranty(original, day_30) is True
    assert is_within_warranty(original, day_31) is False

    # 6:30am UTC Jan 1 is still Dec 31 in Phoenix. 8:00am UTC Jan 31 is Jan 31
    # in Phoenix (31 Phoenix days) but only 30 UTC days.
    original_late = datetime(2026, 1, 1, 6, 30, tzinfo=timezone.utc)
    redo_utc_would_allow = datetime(2026, 1, 31, 8, 0, tzinfo=timezone.utc)
    assert (redo_utc_would_allow.date() - original_late.date()).days == 30
    assert days_after(original_late, redo_utc_would_allow) == 31
    assert is_within_warranty(original_late, redo_utc_would_allow) is False


def test_a_free_warranty_is_not_repriced_or_charged():
    job = {"id": "redo", "warranty_eligible": True, "price": 0, "payment_mode": "charge_on_completion"}
    assert price_updates_for_calibration_change(
        job, {"name": "Glass Co"}, "static", {"static": 125}, {},
    ) == {}
    assert billing_plan(job) == {
        "mode": "charge_on_completion",
        "create_invoice": False,
        "charge": False,
    }
    assert "not charged" in chargeable_reason(
        {**job, "status": "complete"},
        {"stripe_customer_id": "cus", "stripe_payment_method_id": "pm"},
    )


def test_owner_link_is_free_at_30_days_and_billed_at_31(world):
    async def run():
        async with _client() as client:
            free = await client.patch(
                "/api/jobs/job-1",
                headers=_auth(world["owner"]),
                json={"warranty_of_job_id": "done-30"},
            )
            billed = await client.patch(
                "/api/jobs/job-1",
                headers=_auth(world["owner"]),
                json={"warranty_of_job_id": "done-31"},
            )
        assert free.status_code == 200, free.text
        free_job = free.json()
        assert free_job["warranty_eligible"] is True
        assert free_job["warranty_label"] == FREE_LABEL
        assert free_job["price"] == 0
        assert free_job["calibration_price"] == 0

        assert billed.status_code == 200, billed.text
        billed_job = billed.json()
        assert billed_job["warranty_eligible"] is False
        assert billed_job["warranty_label"] == BILLED_LABEL
        assert billed_job["price"] == 125
        assert world["calls"]["email"] == []
        assert world["calls"]["sms"] == []

    asyncio.run(run())


def test_owner_can_clear_the_warranty_link(world):
    async def run():
        async with _client() as client:
            await client.patch(
                "/api/jobs/job-1",
                headers=_auth(world["owner"]),
                json={"warranty_of_job_id": "done-30"},
            )
            cleared = await client.patch(
                "/api/jobs/job-1",
                headers=_auth(world["owner"]),
                json={"warranty_of_job_id": None},
            )
        assert cleared.status_code == 200, cleared.text
        job = cleared.json()
        assert job["warranty_of_job_id"] is None
        assert job["warranty_label"] is None
        assert job["warranty_eligible"] is None
        assert job["price"] == 125

    asyncio.run(run())


def test_other_shops_job_and_an_open_job_are_rejected(world):
    async def run():
        async with _client() as client:
            other = await client.patch(
                "/api/jobs/job-1",
                headers=_auth(world["owner"]),
                json={"warranty_of_job_id": "other-done"},
            )
            open_job = await client.patch(
                "/api/jobs/job-1",
                headers=_auth(world["owner"]),
                json={"warranty_of_job_id": "open-1"},
            )
            portal_other = await client.post(
                "/api/portal/book",
                headers=_auth(world["portal"]),
                json=_booking("other-done"),
            )
            portal_open = await client.post(
                "/api/portal/book",
                headers=_auth(world["portal"]),
                json=_booking("open-1"),
            )
        assert other.status_code == 400
        assert other.json()["detail"] == "A shop can only link its own jobs."
        assert open_job.status_code == 400
        assert open_job.json()["detail"] == "Only a completed job can be a warranty redo."
        assert portal_other.status_code == 400
        assert portal_other.json()["detail"] == "A shop can only link its own jobs."
        assert portal_open.status_code == 400
        assert portal_open.json()["detail"] == "Only a completed job can be a warranty redo."
        assert await world["db"].jobs.find_one({"customer_last_name": "Ng", "status": "booked", "warranty_of_job_id": "other-done"}) is None
        stored = await world["db"].jobs.find_one({"id": "job-1"})
        assert stored["price"] == 125
        assert "warranty_of_job_id" not in stored or stored["warranty_of_job_id"] in (None, "")
        assert world["calls"]["email"] == []
        assert world["calls"]["sms"] == []

    asyncio.run(run())


def test_warranty_list_is_this_shops_completed_jobs_from_the_last_90_days(world):
    async def run():
        async with _client() as client:
            response = await client.get("/api/portal/warranty-jobs", headers=_auth(world["portal"]))
        assert response.status_code == 200, response.text
        rows = response.json()
        ids = [row["id"] for row in rows]
        assert "done-recent" in ids
        assert "done-30" in ids
        assert "done-old" not in ids
        assert "open-1" not in ids
        assert "other-done" not in ids
        recent = next(row for row in rows if row["id"] == "done-recent")
        assert recent["vehicle"] == "2020 Honda Civic"
        assert recent["customer"] == "Ana Reed"
        assert recent["completed_on"] == (TODAY - timedelta(days=10)).isoformat()

    asyncio.run(run())


def test_complete_skips_xero_and_the_card_when_the_redo_is_within_30_days(world):
    async def run():
        world["db"].jobs.docs.append(_job(
            id="redo-free",
            status="on_site",
            warranty_of_job_id="orig-free",
            notification_phone="(480) 555-0100",
            scheduled_start=phoenix_noon(TODAY),
        ))
        world["db"].jobs.docs.append(_completed("orig-free", "shop-1", 30))
        async with _client() as client:
            response = await client.post(
                "/api/jobs/redo-free/complete",
                headers=_auth(world["owner"]),
                json={"result": "pass", "calibration_type": "static", "pop": "none"},
            )
        assert response.status_code == 200, response.text
        job = response.json()["job"]
        assert job["warranty_eligible"] is True
        assert job["warranty_label"] == FREE_LABEL
        assert job["price"] == 0
        assert job["warranty_skip_reason"] == SKIP_REASON
        assert job["charge_skipped"] == SKIP_REASON
        assert job["xero_draft_status"] == "skipped"
        assert job["xero_skipped_reason"] == SKIP_REASON
        assert job.get("invoice_id") in (None, "")
        assert job.get("charged_at") in (None, "")
        assert response.json()["xero"]["status"] == "skipped"
        assert world["calls"]["xero"] == []
        assert world["calls"]["charge"] == []
        assert world["calls"]["email"] == []
        assert world["calls"]["sms"] == []

    asyncio.run(run())


def test_complete_bills_a_redo_on_day_31(world):
    async def run():
        world["db"].jobs.docs.append(_job(
            id="redo-billed",
            status="on_site",
            warranty_of_job_id="orig-billed",
            scheduled_start=phoenix_noon(TODAY),
        ))
        world["db"].jobs.docs.append(_completed("orig-billed", "shop-1", 31))
        async with _client() as client:
            response = await client.post(
                "/api/jobs/redo-billed/complete",
                headers=_auth(world["owner"]),
                json={"result": "pass", "calibration_type": "static", "pop": "none"},
            )
        assert response.status_code == 200, response.text
        job = response.json()["job"]
        assert job["warranty_eligible"] is False
        assert job["warranty_label"] == BILLED_LABEL
        assert job["price"] == 125
        assert job.get("xero_draft_status") != "skipped"
        assert job.get("charge_skipped") != SKIP_REASON
        assert job.get("invoice_id")
        assert world["calls"]["xero"] == []
        assert world["calls"]["charge"] == []

    asyncio.run(run())


def _booking(warranty_id):
    return {
        "job_address": "100 W Main, Phoenix, AZ",
        "scheduled_start": phoenix_noon(TODAY + timedelta(days=1)),
        "customer_last_name": "Ng",
        "year": 2020,
        "make": "Honda",
        "model": "Civic",
        "adas_system": "forward_camera",
        "calibration_type": "static",
        "warranty_of_job_id": warranty_id,
    }
