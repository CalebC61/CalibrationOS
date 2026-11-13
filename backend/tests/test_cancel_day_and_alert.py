"""Cancelling a job takes it off the owner day and clears only its new-booking alert.

Shop public cancel, owner cancel, and a status change to cancelled all do this.
The job document stays. The shop portal still lists it. Other alerts stay unseen.

    cd backend && pytest tests/test_cancel_day_and_alert.py -v
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
if DAY.weekday() == 6:
    DAY = DAY + timedelta(days=1)


def _at(hours):
    start, _end = business_day_bounds(DAY)
    return (start + timedelta(hours=hours)).isoformat()


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


class _Result:
    def __init__(self, count):
        self.modified_count = count


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
        self.shops = _Store()
        self.shop_users = _Store()
        self.new_booking_alerts = _Store()


def _job(job_id, status, hour, **overrides):
    doc = {
        "id": job_id,
        "shop_id": "shop-1",
        "shop_name": "Jarvis Glass",
        "technician_id": "tech-owner",
        "technician_name": "Caleb",
        "status": status,
        "zone": "west",
        "job_lat": 33.45,
        "job_lng": -112.2,
        "price": 125.0,
        "scheduled_start": _at(hour),
        "scheduled_end": _at(hour + 1),
        "customer_last_name": "Ng",
        "vehicle_year": 2022,
        "vehicle_make": "Toyota",
        "vehicle_model": "Camry",
        "booking_kind": "addon" if status == "requested" else "standard",
    }
    doc.update(overrides)
    return doc


def _alert(alert_id, job_id):
    return {
        "id": alert_id,
        "job_id": job_id,
        "owner_id": "tech-owner",
        "created_at": _at(8),
        "seen_at": None,
        "shop_name": "Jarvis Glass",
        "scheduled_start": _at(9),
        "zone": "west",
        "vehicle": "2022 Toyota Camry",
        "price": 125.0,
    }


def _world(monkeypatch):
    db = _DB()
    db.technicians.docs.append({
        "id": "tech-owner", "role": "owner", "name": "Caleb",
        "home_lat": 33.35, "home_lng": -111.79,
    })
    db.technicians.docs.append({"id": "tech-field", "role": "technician", "name": "Field Tech"})
    db.shops.docs.append({
        "id": "shop-1", "name": "Jarvis Glass", "status": "active",
        "booking_link_token": "tok-shop", "contact_email": "shop@glass.example",
    })
    db.shop_users.docs.append({
        "id": "su-1", "shop_id": "shop-1", "full_name": "Dana", "is_active": True,
    })
    db.jobs.docs.extend([
        _job("job-shop", "requested", 9),
        _job("job-owner", "booked", 11),
        _job("job-status", "booked", 13),
        _job("job-keep", "booked", 15),
        _job("job-declined", "declined", 16),
        _job("job-already", "cancelled", 17),
    ])
    db.new_booking_alerts.docs.extend([
        _alert("alert-shop", "job-shop"),
        _alert("alert-owner", "job-owner"),
        _alert("alert-status", "job-status"),
        _alert("alert-keep", "job-keep"),
        _alert("alert-already", "job-already"),
    ])

    async def drive(*args, **kwargs):
        return {"duration_minutes": 10, "distance_miles": 4}

    async def no_email(*args, **kwargs):
        return None

    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "get_drive_time", drive)
    monkeypatch.setattr(server, "send_email", no_email)
    return db


def _ids(response):
    assert response.status_code == 200, response.text
    return [job["id"] for job in response.json()]


def _alert_ids(response):
    assert response.status_code == 200, response.text
    body = response.json()
    ids = [alert["job_id"] for alert in body["alerts"]]
    assert body["count"] == len(ids)
    return ids


def test_cancelling_hides_the_job_and_clears_only_its_alert(monkeypatch):
    db = _world(monkeypatch)
    owner = server.make_token("tech-owner", "owner")
    field = server.make_token("tech-field", "technician")
    portal = server.make_portal_token("su-1")
    owner_headers = {"Authorization": f"Bearer {owner}"}
    field_headers = {"Authorization": f"Bearer {field}"}

    async def run():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            cancelled = await client.post("/api/public/bookings/tok-shop/job-shop/cancel")
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()["status"] == "cancelled"

            owner_day = await client.get(f"/api/jobs?date_str={DAY.isoformat()}", headers=owner_headers)
            field_day = await client.get(f"/api/jobs?date_str={DAY.isoformat()}", headers=field_headers)
            summary = await client.get(
                f"/api/dashboard/summary?date_str={DAY.isoformat()}", headers=owner_headers,
            )
            alerts = await client.get("/api/notifications/new-bookings", headers=owner_headers)
            blocked = await client.post("/api/jobs/reorder", headers=owner_headers, json={
                "technician_id": "tech-owner",
                "date": DAY.isoformat(),
                "ordered_job_ids": ["job-shop"],
            })

        owner_ids = _ids(owner_day)
        field_ids = _ids(field_day)
        assert "job-shop" not in owner_ids
        assert "job-already" not in owner_ids
        assert "job-shop" not in field_ids
        assert "job-declined" not in owner_ids
        assert {"job-owner", "job-status", "job-keep"} <= set(owner_ids)
        assert summary.status_code == 200, summary.text
        assert summary.json()["job_count"] == 3
        assert set(_alert_ids(alerts)) == {"job-owner", "job-status", "job-keep"}
        already = next(alert for alert in db.new_booking_alerts.docs if alert["id"] == "alert-already")
        assert already["seen_at"] is None
        assert blocked.status_code == 400
        shop_alert = next(alert for alert in db.new_booking_alerts.docs if alert["id"] == "alert-shop")
        assert shop_alert["seen_at"]
        assert all(
            alert["seen_at"] is None
            for alert in db.new_booking_alerts.docs
            if alert["id"] != "alert-shop"
        )

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            owner_cancel = await client.post(
                "/api/jobs/job-owner/cancel", headers=owner_headers, json={"reason": "shop asked"},
            )
            assert owner_cancel.status_code == 200, owner_cancel.text
            assert owner_cancel.json()["status"] == "cancelled"
            status_cancel = await client.post(
                "/api/jobs/job-status/status", headers=owner_headers, json={"status": "cancelled"},
            )
            assert status_cancel.status_code == 200, status_cancel.text
            assert status_cancel.json()["status"] == "cancelled"

            owner_day = await client.get(f"/api/jobs?date_str={DAY.isoformat()}", headers=owner_headers)
            field_day = await client.get(f"/api/jobs?date_str={DAY.isoformat()}", headers=field_headers)
            summary = await client.get(
                f"/api/dashboard/summary?date_str={DAY.isoformat()}", headers=owner_headers,
            )
            alerts = await client.get("/api/notifications/new-bookings", headers=owner_headers)
            opted = await client.get(
                f"/api/jobs?date_str={DAY.isoformat()}&include_cancelled=false", headers=owner_headers,
            )
            history = await client.get(
                f"/api/jobs?date_str={DAY.isoformat()}&include_cancelled=true", headers=owner_headers,
            )
            route = await client.post("/api/jobs/reorder", headers=owner_headers, json={
                "technician_id": "tech-owner",
                "date": DAY.isoformat(),
                "ordered_job_ids": ["job-keep"],
            })
            portal_jobs = await client.get(
                "/api/portal/jobs", headers={"Authorization": f"Bearer {portal}"},
            )

        assert _ids(owner_day) == ["job-keep"]
        assert "job-shop" not in _ids(field_day)
        assert "job-owner" not in _ids(field_day)
        assert "job-status" not in _ids(field_day)
        assert "job-keep" in _ids(field_day)
        assert summary.json()["job_count"] == 1
        assert set(_alert_ids(alerts)) == {"job-keep"}
        assert "job-shop" not in _ids(opted)
        history_ids = _ids(history)
        assert {"job-shop", "job-owner", "job-status", "job-keep", "job-already"} <= set(history_ids)
        assert "job-declined" not in history_ids
        assert route.status_code == 200, route.text
        assert [row["id"] for row in route.json()["jobs"]] == ["job-keep"]
        portal_ids = _ids(portal_jobs)
        assert {"job-shop", "job-owner", "job-status", "job-keep", "job-already"} <= set(portal_ids)
        stored = {job["id"]: job["status"] for job in db.jobs.docs}
        assert stored["job-shop"] == "cancelled"
        assert stored["job-owner"] == "cancelled"
        assert stored["job-status"] == "cancelled"
        assert stored["job-keep"] == "booked"
        assert len(db.jobs.docs) == 6
        keep = next(alert for alert in db.new_booking_alerts.docs if alert["id"] == "alert-keep")
        assert keep["seen_at"] is None

    asyncio.run(run())
