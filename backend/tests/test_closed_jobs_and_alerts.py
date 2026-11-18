"""Declined and cancelled jobs leave the new-booking banner, and the owner can list them.

The day board already omits both statuses. Decline did not clear the banner.
Cancelled jobs were already left out of the banner, including ones cancelled
before seen_at was set. The owner still needs a list of those jobs so Delete
can reach them. Delete stays the existing owner-only route.

    cd backend && pytest tests/test_closed_jobs_and_alerts.py -v
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
from business_time import business_date, business_day_bounds  # noqa: E402

DAY = business_date() + timedelta(days=2)
if DAY.weekday() == 6:
    DAY = DAY + timedelta(days=1)
OTHER = DAY + timedelta(days=2)


def _at(day, hours):
    start, _end = business_day_bounds(day)
    return (start + timedelta(hours=hours)).isoformat()


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
                elif op == "$ne":
                    ok = value != operand
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
    if any(flag == 0 for flag in projection.values()):
        for key, flag in projection.items():
            if flag == 0:
                out.pop(key, None)
        return out
    return {k: out[k] for k in projection if k in out}


class _Result:
    def __init__(self, count):
        self.modified_count = count
        self.deleted_count = count


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=1):
        self.docs = sorted(self.docs, key=lambda doc: doc.get(key) or "", reverse=direction < 0)
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
                doc.update(update.get("$set", {}))
                for key, value in update.get("$push", {}).items():
                    doc.setdefault(key, []).append(value)
                return

    async def update_many(self, query, update):
        count = 0
        for doc in self.docs:
            if _match(doc, query):
                doc.update(update.get("$set", {}))
                count += 1
        return _Result(count)

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

    async def count_documents(self, query):
        return sum(1 for doc in self.docs if _match(doc, query))


class _DB:
    def __init__(self):
        self.technicians = _Store()
        self.jobs = _Store()
        self.shops = _Store()
        self.shop_users = _Store()
        self.new_booking_alerts = _Store()
        self.documents = _Store()
        self.contractor_offers = _Store()
        self.owner_action_tokens = _Store()
        self.vehicles = _Store()
        self.email_outbox = _Store()
        self.sms_log = _Store()


def _job(job_id, status, day, hour, **overrides):
    doc = {
        "id": job_id,
        "shop_id": "shop-1",
        "shop_name": "Jarvis Glass",
        "technician_id": "tech-owner",
        "status": status,
        "zone": "west",
        "price": 125.0,
        "scheduled_start": _at(day, hour),
        "scheduled_end": _at(day, hour + 1),
        "customer_first_name": "Ana",
        "customer_last_name": "Ng",
        "vehicle_year": 2022,
        "vehicle_make": "Toyota",
        "vehicle_model": "Camry",
        "updated_at": _at(day, hour),
    }
    doc.update(overrides)
    return doc


def _alert(alert_id, job_id):
    return {
        "id": alert_id,
        "job_id": job_id,
        "owner_id": "tech-owner",
        "created_at": _at(DAY, 8),
        "seen_at": None,
        "shop_name": "Jarvis Glass",
        "scheduled_start": _at(DAY, 9),
        "zone": "west",
        "vehicle": "2022 Toyota Camry",
        "price": 125.0,
    }


def _world(monkeypatch):
    db = _DB()
    db.technicians.docs.append({"id": "tech-owner", "role": "owner", "name": "Caleb"})
    db.technicians.docs.append({"id": "tech-field", "role": "technician", "name": "Field"})
    db.shops.docs.append({
        "id": "shop-1", "name": "Jarvis Glass", "status": "active",
        "contact_email": "shop@glass.example",
    })
    db.jobs.docs.extend([
        _job("job-open", "requested", DAY, 9),
        _job("job-keep", "booked", DAY, 11),
        _job("job-done", "complete", DAY, 12),
        _job("job-declined", "declined", DAY, 13, customer_first_name="Ben"),
        _job(
            "job-cancelled", "cancelled", OTHER, 10,
            shop_name="Star Windshield",
            customer_first_name="Casey",
            customer_last_name="Lee",
            vehicle_year=2019,
            vehicle_make="Honda",
            vehicle_model="Civic",
            cancellation_reason="Customer requested",
            updated_at=_at(OTHER, 15),
        ),
    ])
    db.new_booking_alerts.docs.extend([
        _alert("alert-open", "job-open"),
        _alert("alert-keep", "job-keep"),
        _alert("alert-declined", "job-declined"),
        _alert("alert-cancelled", "job-cancelled"),
    ])
    calls = []

    async def send_email(*args, **kwargs):
        calls.append("email")

    async def sms(*args, **kwargs):
        calls.append("sms")

    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "send_email", send_email)
    monkeypatch.setattr(server, "mock_send_sms", sms)
    return db, calls


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _alert_ids(response):
    assert response.status_code == 200, response.text
    body = response.json()
    ids = [alert["job_id"] for alert in body["alerts"]]
    assert body["count"] == len(ids)
    return ids


def test_banner_count_skips_declined_and_cancelled_jobs(monkeypatch):
    _world(monkeypatch)
    owner = server.make_token("tech-owner", "owner")

    async def run():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            alerts = await client.get("/api/notifications/new-bookings", headers=_auth(owner))
        assert set(_alert_ids(alerts)) == {"job-open", "job-keep"}

    asyncio.run(run())


def test_declining_a_pending_job_clears_only_its_banner_alert(monkeypatch):
    db, calls = _world(monkeypatch)
    owner = server.make_token("tech-owner", "owner")

    async def run():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            declined = await client.post("/api/jobs/job-open/decline", headers=_auth(owner))
            alerts = await client.get("/api/notifications/new-bookings", headers=_auth(owner))
        assert declined.status_code == 200, declined.text
        assert declined.json()["status"] == "declined"
        assert set(_alert_ids(alerts)) == {"job-keep"}
        closed = next(alert for alert in db.new_booking_alerts.docs if alert["id"] == "alert-open")
        kept = next(alert for alert in db.new_booking_alerts.docs if alert["id"] == "alert-keep")
        assert closed["seen_at"]
        assert kept["seen_at"] is None
        assert "sms" not in calls
        stored = next(job for job in db.jobs.docs if job["id"] == "job-open")
        assert stored["status"] == "declined"

    asyncio.run(run())


def test_owner_closed_list_is_cancelled_and_declined_jobs(monkeypatch):
    db, calls = _world(monkeypatch)
    owner = server.make_token("tech-owner", "owner")
    field = server.make_token("tech-field", "technician")

    async def run():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            closed = await client.get("/api/jobs?closed=true", headers=_auth(owner))
            day = await client.get(f"/api/jobs?date_str={DAY.isoformat()}", headers=_auth(owner))
            history = await client.get(
                f"/api/jobs?date_str={DAY.isoformat()}&include_cancelled=true",
                headers=_auth(owner),
            )
            denied = await client.get("/api/jobs?closed=true", headers=_auth(field))
            blocked = await client.delete("/api/jobs/job-declined", headers=_auth(field))
            still_there = any(job["id"] == "job-declined" for job in db.jobs.docs)
            removed = await client.delete("/api/jobs/job-declined", headers=_auth(owner))
            after = await client.get("/api/jobs?closed=true", headers=_auth(owner))

        assert closed.status_code == 200, closed.text
        rows = closed.json()
        assert [row["id"] for row in rows] == ["job-cancelled", "job-declined"]
        cancelled = rows[0]
        assert cancelled["shop_name"] == "Star Windshield"
        assert cancelled["status"] == "cancelled"
        assert cancelled["cancellation_reason"] == "Customer requested"
        assert cancelled["customer_first_name"] == "Casey"
        assert cancelled["customer_last_name"] == "Lee"
        assert cancelled["vehicle_make"] == "Honda"
        assert cancelled["scheduled_start"]
        declined = rows[1]
        assert declined["status"] == "declined"
        assert declined["shop_name"] == "Jarvis Glass"
        assert declined["customer_first_name"] == "Ben"
        assert "job-declined" not in [job["id"] for job in day.json()]
        assert "job-cancelled" not in [job["id"] for job in day.json()]
        assert "job-open" in [job["id"] for job in day.json()]
        assert "job-declined" not in [job["id"] for job in history.json()]
        assert denied.status_code == 403
        assert blocked.status_code == 403
        assert still_there
        assert removed.status_code == 200, removed.text
        assert removed.json()["deleted"] is True
        assert [row["id"] for row in after.json()] == ["job-cancelled"]
        assert "sms" not in calls
        assert "email" not in calls

    asyncio.run(run())
