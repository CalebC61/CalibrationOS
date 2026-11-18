"""Day totals follow the jobs still on that day.

Est. miles and Done by are not a saved route. GET /api/dashboard/summary adds
the drive minutes and latest end of the jobs that are still on the Phoenix day.
Deleted jobs are gone. Cancelled and declined jobs stay in the database and
are left out. No live Mongo, and this does not send mail or change billing.

    cd backend && pytest tests/test_dashboard_day_totals.py -v
"""
import asyncio
import os
import sys
from datetime import date, timedelta

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from business_time import business_day_bounds  # noqa: E402

DAY = date(2026, 12, 8)


def _at(hours, minutes=0, day=DAY):
    start, _end = business_day_bounds(day)
    return (start + timedelta(hours=hours, minutes=minutes)).isoformat()


def _match(doc, query):
    for key, expected in query.items():
        value = doc.get(key)
        if isinstance(expected, dict):
            for op, operand in expected.items():
                if op == "$gte" and not (value is not None and value >= operand):
                    return False
                if op == "$lt" and not (value is not None and value < operand):
                    return False
                if op == "$nin" and value in operand:
                    return False
                if op == "$in" and value not in operand:
                    return False
                if op == "$ne" and value == operand:
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


class _Result:
    def __init__(self, count):
        self.deleted_count = count


class _Store:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return _project(doc, projection)
        return None

    def find(self, query, projection=None):
        return _Cursor([_project(doc, projection) for doc in self.docs if _match(doc, query)])

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
        self.jobs = _Store()
        self.documents = _Store()
        self.new_booking_alerts = _Store()
        self.owner_action_tokens = _Store()


def _job(job_id, status, hour, minute, drive, price, day=DAY):
    return {
        "id": job_id,
        "shop_id": "shop-1",
        "shop_name": "Test Glass",
        "technician_id": "tech-owner",
        "status": status,
        "price": price,
        "drive_time_minutes": drive,
        "scheduled_start": _at(hour, minute, day),
        "scheduled_end": _at(hour, minute, day),
        "zone": "west",
    }


def _world(monkeypatch, jobs):
    db = _DB()
    db.technicians.docs.append({"id": "tech-owner", "role": "owner", "name": "Caleb"})
    db.jobs.docs.extend(jobs)
    original = server.db
    monkeypatch.setattr(server, "db", db)
    return db, original


def _restore(monkeypatch, original):
    monkeypatch.setattr(server, "db", original)


async def _summary(client, token):
    response = await client.get(
        f"/api/dashboard/summary?date_str={DAY.isoformat()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _delete(client, token, job_id):
    response = await client.delete(
        f"/api/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text


def test_deleting_the_last_job_resets_miles_and_done_by(monkeypatch):
    """Tue Dec 8 had one active job. After it is deleted the day is empty."""
    late = _job("job-late", "booked", 10, 50, 23, 125.0)
    cancelled = _job("job-cancelled", "cancelled", 15, 0, 200, 999.0)
    declined = _job("job-declined", "declined", 16, 0, 80, 50.0)
    other_day = _job("job-other", "booked", 9, 0, 100, 500.0, day=date(2026, 12, 9))
    db, original = _world(monkeypatch, [late, cancelled, declined, other_day])
    token = server.make_token("tech-owner", "owner")

    async def run():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            before = await _summary(client, token)
            await _delete(client, token, "job-late")
            after = await _summary(client, token)
        assert before["job_count"] == 1
        assert before["revenue"] == 125
        assert before["estimated_miles"] == 11.5
        assert before["done_by"] == late["scheduled_end"]
        assert after["job_count"] == 0
        assert after["revenue"] == 0
        assert after["estimated_miles"] == 0
        assert after["done_by"] is None
        assert [job["id"] for job in db.jobs.docs] == ["job-cancelled", "job-declined", "job-other"]

    try:
        asyncio.run(run())
    finally:
        _restore(monkeypatch, original)


def test_deleting_one_job_recomputes_miles_and_done_by_from_the_rest(monkeypatch):
    """Three active jobs total 53 miles and finish at 10:50. One delete leaves the other two."""
    early = _job("job-early", "booked", 9, 0, 40, 125.0)
    mid = _job("job-mid", "booked", 10, 0, 43, 125.0)
    late = _job("job-late", "booked", 10, 50, 23, 125.0)
    cancelled = _job("job-cancelled", "cancelled", 15, 0, 200, 999.0)
    declined = _job("job-declined", "declined", 16, 0, 80, 50.0)
    db, original = _world(monkeypatch, [early, mid, late, cancelled, declined])
    token = server.make_token("tech-owner", "owner")

    async def run():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            before = await _summary(client, token)
            await _delete(client, token, "job-late")
            after = await _summary(client, token)
        assert before["job_count"] == 3
        assert before["revenue"] == 375
        assert before["estimated_miles"] == 53
        assert before["done_by"] == late["scheduled_end"]
        assert after["job_count"] == 2
        assert after["revenue"] == 250
        assert after["estimated_miles"] == 41.5
        assert after["done_by"] == mid["scheduled_end"]
        assert "job-late" not in [job["id"] for job in db.jobs.docs]
        assert "job-cancelled" in [job["id"] for job in db.jobs.docs]
        assert "job-declined" in [job["id"] for job in db.jobs.docs]

    try:
        asyncio.run(run())
    finally:
        _restore(monkeypatch, original)
