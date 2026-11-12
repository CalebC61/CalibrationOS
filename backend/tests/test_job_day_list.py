"""Day lists hide cancelled and declined jobs. The documents stay in Mongo.

    cd backend && pytest tests/test_job_day_list.py -v

Dashboard, Field, TomorrowStrip, and the route map all read GET /api/jobs.
The shop portal uses GET /api/portal/jobs and still returns cancelled jobs.
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

DAY = business_date() + timedelta(days=1)
NEXT = DAY + timedelta(days=1)


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
                doc.update(update.get("$set", {}))
                return


def _project(doc, projection):
    out = {k: v for k, v in doc.items() if k != "_id"}
    if not projection:
        return out
    for key, flag in projection.items():
        if flag == 0:
            out.pop(key, None)
    return out


class _DB:
    def __init__(self):
        self.technicians = _Store()
        self.jobs = _Store()
        self.shop_users = _Store()


def _job(**overrides):
    doc = {
        "id": "job-booked",
        "shop_id": "shop-1",
        "shop_name": "Jarvis Glass",
        "technician_id": "tech-owner",
        "technician_name": "Caleb",
        "status": "booked",
        "zone": "west",
        "job_lat": 33.45,
        "job_lng": -112.2,
        "price": 125.0,
        "scheduled_start": _at(DAY, 10),
        "scheduled_end": _at(DAY, 11),
        "customer_last_name": "Ng",
        "vehicle_year": 2022,
        "vehicle_make": "Toyota",
        "vehicle_model": "Camry",
    }
    doc.update(overrides)
    return doc


def _world(monkeypatch):
    db = _DB()
    db.technicians.docs.append({"id": "tech-owner", "role": "owner", "name": "Caleb"})
    db.technicians.docs.append({"id": "tech-field", "role": "technician", "name": "Field Tech"})
    db.jobs.docs.extend([
        _job(),
        _job(id="job-driving", status="driving", scheduled_start=_at(DAY, 11), scheduled_end=_at(DAY, 12)),
        _job(id="job-complete", status="complete", scheduled_start=_at(DAY, 12), scheduled_end=_at(DAY, 13)),
        _job(id="job-cancelled", status="cancelled", scheduled_start=_at(DAY, 13), scheduled_end=_at(DAY, 14)),
        _job(id="job-declined", status="declined", scheduled_start=_at(DAY, 14), scheduled_end=_at(DAY, 15)),
        _job(id="job-tech-booked", status="booked", technician_id="tech-field",
             scheduled_start=_at(DAY, 15), scheduled_end=_at(DAY, 16)),
        _job(id="job-tech-cancelled", status="cancelled", technician_id="tech-field",
             scheduled_start=_at(DAY, 16), scheduled_end=_at(DAY, 17)),
    ])
    monkeypatch.setattr(server, "db", db)
    return db


def _ids(response):
    assert response.status_code == 200, response.text
    return [job["id"] for job in response.json()]


def test_day_list_omits_cancelled_and_declined_jobs(monkeypatch):
    db = _world(monkeypatch)
    owner = server.make_token("tech-owner", "owner")
    field = server.make_token("tech-field", "technician")

    async def run():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            owner_list = await client.get(
                f"/api/jobs?date_str={DAY.isoformat()}",
                headers={"Authorization": f"Bearer {owner}"},
            )
            field_list = await client.get(
                f"/api/jobs?date_str={DAY.isoformat()}",
                headers={"Authorization": f"Bearer {field}"},
            )
        owner_ids = _ids(owner_list)
        field_ids = _ids(field_list)
        assert "job-cancelled" not in owner_ids
        assert "job-declined" not in owner_ids
        assert "job-tech-cancelled" not in field_ids
        assert {"job-booked", "job-driving", "job-complete", "job-tech-booked"} <= set(owner_ids)
        assert "job-tech-booked" in field_ids
        stored = {job["id"]: job["status"] for job in db.jobs.docs}
        assert stored["job-cancelled"] == "cancelled"
        assert stored["job-declined"] == "declined"
        assert len(db.jobs.docs) == 7

    asyncio.run(run())


def test_include_cancelled_puts_cancelled_jobs_back_on_the_list(monkeypatch):
    _world(monkeypatch)
    owner = server.make_token("tech-owner", "owner")

    async def run():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            opted_in = await client.get(
                f"/api/jobs?date_str={DAY.isoformat()}&include_cancelled=true",
                headers={"Authorization": f"Bearer {owner}"},
            )
        ids = _ids(opted_in)
        assert "job-cancelled" in ids
        assert "job-tech-cancelled" in ids
        assert "job-declined" not in ids
        assert "job-booked" in ids

    asyncio.run(run())


def test_rescheduled_job_appears_only_on_its_new_date(monkeypatch):
    db = _world(monkeypatch)
    sms = []

    async def record_sms(*args, **kwargs):
        sms.append((args, kwargs))

    monkeypatch.setattr(server, "mock_send_sms", record_sms)
    db.jobs.docs.append(_job(
        id="job-move",
        status="booked",
        notification_phone=None,
        scheduled_start=_at(DAY, 9),
        scheduled_end=_at(DAY, 10),
    ))
    owner = server.make_token("tech-owner", "owner")
    new_start = _at(NEXT, 10)

    async def run():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            moved = await client.post(
                "/api/jobs/job-move/reschedule",
                headers={"Authorization": f"Bearer {owner}"},
                json={"scheduled_start": new_start, "reason": "shop asked"},
            )
            assert moved.status_code == 200, moved.text
            old_day = await client.get(
                f"/api/jobs?date_str={DAY.isoformat()}",
                headers={"Authorization": f"Bearer {owner}"},
            )
            new_day = await client.get(
                f"/api/jobs?date_str={NEXT.isoformat()}",
                headers={"Authorization": f"Bearer {owner}"},
            )
        assert "job-move" not in _ids(old_day)
        assert _ids(new_day) == ["job-move"]
        copies = [job for job in db.jobs.docs if job["id"] == "job-move"]
        assert len(copies) == 1
        assert copies[0]["status"] == "booked"
        assert copies[0]["scheduled_start"] == new_start
        assert sms == []

    asyncio.run(run())


def test_shop_portal_still_lists_cancelled_jobs(monkeypatch):
    db = _world(monkeypatch)
    db.shop_users.docs.append({
        "id": "su-1", "shop_id": "shop-1", "full_name": "Dana", "is_active": True,
    })
    db.jobs.docs.append(_job(id="job-other-shop", shop_id="shop-2", status="cancelled"))
    token = server.make_portal_token("su-1")

    async def run():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/portal/jobs",
                headers={"Authorization": f"Bearer {token}"},
            )
        ids = _ids(response)
        assert "job-cancelled" in ids
        assert "job-tech-cancelled" in ids
        assert "job-other-shop" not in ids

    asyncio.run(run())
