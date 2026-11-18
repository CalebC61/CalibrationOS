"""Day-before shop reminder. Held while SHOP_EMAILS_ENABLED is off.

    cd backend && pytest tests/test_day_before.py -v
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

from pymongo.errors import DuplicateKeyError  # noqa: E402

from day_before import (  # noqa: E402
    arrival_window,
    next_reminder_delay,
    reminder_is_due,
    reminder_message,
    run_reminders,
)
import server  # noqa: E402

# 5:00 PM Phoenix on 2026-11-18.
EVENING = datetime(2026, 11, 19, 0, 0, tzinfo=timezone.utc)
# 4:00 PM Phoenix that same day.
AFTERNOON = datetime(2026, 11, 18, 23, 0, tzinfo=timezone.utc)
# 8:00–8:20 AM Phoenix on 2026-11-19.
START = "2026-11-19T15:00:00+00:00"
END = "2026-11-19T15:20:00+00:00"
PORTAL = "https://thecalibrationcrew.us/portal"


def _match(doc, query):
    for key, expected in (query or {}).items():
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
        elif value != expected:
            return False
    return True


class _Col:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    def find(self, query=None, projection=None):
        self._query = query or {}
        return self

    async def to_list(self, n):
        return [dict(doc) for doc in self.docs if _match(doc, self._query)][:n]

    async def insert_one(self, doc):
        if doc.get("_id") is not None and any(row.get("_id") == doc.get("_id") for row in self.docs):
            raise DuplicateKeyError("duplicate")
        self.docs.append(dict(doc))

    async def delete_one(self, query):
        self.docs = [doc for doc in self.docs if not _match(doc, query)]

    async def update_one(self, query, update):
        for doc in self.docs:
            if _match(doc, query):
                doc.update(update.get("$set") or {})
                return


class _DB:
    def __init__(self, jobs, shops=None):
        self.jobs = _Col(jobs)
        self.shops = _Col(shops or [])
        self.day_before_reminders = _Col()
        self.email_outbox = _Col()
        self.email_log = _Col()
        self.admin_notifications = _Col()


def _job(**overrides):
    row = {
        "id": "job-1",
        "shop_id": "shop-1",
        "shop_name": "Preferred Glass",
        "status": "booked",
        "scheduled_start": START,
        "scheduled_end": END,
        "job_address": "1234 E Williams Field Rd, Gilbert, AZ",
        "vehicle_year": 2022,
        "vehicle_make": "Honda",
        "vehicle_model": "Civic",
        "customer_first_name": "Pat",
        "customer_last_name": "Ng",
        "calibration_label": "Static ADAS Calibration",
        "calibration_type": "static",
        "notification_email": "shop@glass.example",
    }
    row.update(overrides)
    return row


def _shop(**overrides):
    row = {"id": "shop-1", "name": "Preferred Glass", "contact_email": "shop@glass.example"}
    row.update(overrides)
    return row


def test_the_reminder_is_due_from_5pm_phoenix_until_midnight():
    assert reminder_is_due(EVENING) is True
    assert reminder_is_due(AFTERNOON) is False
    eleven = EVENING + timedelta(hours=6, minutes=59)
    assert reminder_is_due(eleven) is True
    midnight = datetime(2026, 11, 19, 7, 0, tzinfo=timezone.utc)
    assert reminder_is_due(midnight) is False
    assert next_reminder_delay(AFTERNOON) == 60 * 60
    assert next_reminder_delay(EVENING + timedelta(minutes=30), failed=0) == 23.5 * 60 * 60
    assert next_reminder_delay(EVENING, failed=1) == 300


def test_arrival_window_uses_phoenix_and_collapses_one_meridiem():
    assert arrival_window(START, END) == "8:00–8:20 AM Phoenix"
    assert arrival_window("2026-11-19T18:50:00+00:00", "2026-11-19T19:10:00+00:00") == "11:50 AM–12:10 PM Phoenix"


def test_the_message_lists_the_job_and_the_portal_and_escapes_the_address():
    message = reminder_message(
        to="shop@glass.example",
        reply_to="caleb@thecalibrationcrew.us",
        shop_name="Preferred Glass",
        day=reminder_day(),
        jobs=[_job(job_address="1 <Main> St")],
        portal_url=PORTAL,
    )
    assert message["kind"] == "day_before_reminder"
    assert message["to"] == "shop@glass.example"
    blob = message["subject"] + message["html"]
    assert "Preferred Glass" in message["subject"]
    assert "2022 Honda Civic" in blob
    assert "Pat Ng" in blob
    assert "1 &lt;Main&gt; St" in message["html"]
    assert "1 <Main> St" not in message["html"]
    assert "Static ADAS Calibration" in blob
    assert "8:00–8:20 AM Phoenix" in blob
    assert PORTAL in message["html"]
    assert "Open the shop portal" in message["html"]


def reminder_day():
    from day_before import reminder_day as day_for
    return day_for(EVENING)


def test_before_5pm_sends_nothing_and_writes_no_marker():
    sent = []

    async def send(message):
        sent.append(message)

    db = _DB([_job()])
    result = asyncio.run(run_reminders(
        db, now=AFTERNOON, send=send, portal_url=PORTAL, reply_to="caleb@thecalibrationcrew.us",
    ))
    assert result["reason"] == "before 5:00 PM Phoenix"
    assert sent == []
    assert db.day_before_reminders.docs == []


def test_one_email_per_shop_skips_cancelled_and_does_not_repeat():
    sent = []

    async def send(message):
        sent.append(message)

    today = "2026-11-18T23:00:00+00:00"
    jobs = [
        _job(),
        _job(id="job-cancel", status="cancelled", customer_last_name="Cancelled"),
        _job(id="job-decline", status="Declined", customer_last_name="Declined"),
        _job(id="job-today", scheduled_start=today, scheduled_end=today, customer_last_name="Today"),
        _job(
            id="job-2", shop_id="shop-2", shop_name="Mesa Glass",
            customer_first_name="Ada", customer_last_name="Glass",
            vehicle_year=2020, vehicle_make="Toyota", vehicle_model="Camry",
            calibration_label="Dynamic ADAS Calibration",
            job_address="9 Stapley Dr, Mesa, AZ",
            notification_email="mesa@glass.example",
        ),
        _job(id="job-quiet", shop_id="shop-3", shop_name="Quiet Glass", status="cancelled"),
    ]
    shops = [
        _shop(),
        _shop(id="shop-2", name="Mesa Glass", contact_email="mesa@glass.example"),
        _shop(id="shop-3", name="Quiet Glass", contact_email="quiet@glass.example"),
    ]
    db = _DB(jobs, shops)
    first = asyncio.run(run_reminders(
        db, now=EVENING, send=send, portal_url=PORTAL, reply_to="caleb@thecalibrationcrew.us",
    ))
    assert first["sent"] == 2
    assert {message["to"] for message in sent} == {"shop@glass.example", "mesa@glass.example"}
    preferred = next(message for message in sent if message["to"] == "shop@glass.example")
    assert "Pat Ng" in preferred["html"]
    assert "2022 Honda Civic" in preferred["html"]
    assert "Cancelled" not in preferred["html"]
    assert "Declined" not in preferred["html"]
    assert "Today" not in preferred["html"]
    assert "8:00–8:20 AM Phoenix" in preferred["html"]
    assert PORTAL in preferred["html"]
    mesa = next(message for message in sent if message["to"] == "mesa@glass.example")
    assert "Ada Glass" in mesa["html"]
    assert "2020 Toyota Camry" in mesa["html"]
    assert "Dynamic ADAS Calibration" in mesa["html"]

    asyncio.run(run_reminders(
        db, now=EVENING, send=send, portal_url=PORTAL, reply_to="caleb@thecalibrationcrew.us",
    ))
    assert len(sent) == 2
    assert first["failed"] == 0
    sent_markers = [row for row in db.day_before_reminders.docs if row["status"] == "sent"]
    assert {row["shop_id"] for row in sent_markers} == {"shop-1", "shop-2"}


def test_a_failed_send_releases_the_marker_and_the_next_pass_sends():
    calls = {"n": 0}

    async def send(message):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("mail down")

    db = _DB([_job()], [_shop()])
    first = asyncio.run(run_reminders(
        db, now=EVENING, send=send, portal_url=PORTAL, reply_to="caleb@thecalibrationcrew.us",
    ))
    assert first["failed"] == 1
    assert db.day_before_reminders.docs == []
    second = asyncio.run(run_reminders(
        db, now=EVENING, send=send, portal_url=PORTAL, reply_to="caleb@thecalibrationcrew.us",
    ))
    assert second["sent"] == 1
    assert calls["n"] == 2


def test_shop_mail_is_held_in_the_outbox_and_resend_is_not_called(monkeypatch):
    monkeypatch.setenv("SHOP_EMAILS_ENABLED", "false")
    monkeypatch.setattr(server, "RESEND_API_KEY", "re_test_key")
    db = _DB([_job()], [_shop()])
    monkeypatch.setattr(server, "db", db)
    sent = []

    def fake_send(payload):
        sent.append(payload)
        return {"id": "re_test"}

    monkeypatch.setattr(server.resend_sdk.Emails, "send", fake_send)
    result = asyncio.run(server.run_day_before_reminders(EVENING))
    assert result["sent"] == 1
    assert sent == []
    assert len(db.email_outbox.docs) == 1
    row = db.email_outbox.docs[0]
    assert row["to"] == "shop@glass.example"
    assert row["audience"] == "shop"
    assert row["kind"] == "day_before_reminder"
    assert row["delivered"] is False
    assert "2022 Honda Civic" in row["body"]
    assert "Pat Ng" in row["body"]
    assert "Gilbert, AZ" in row["body"]
    assert "Static ADAS Calibration" in row["body"]
    assert "8:00–8:20 AM Phoenix" in row["body"]
    assert "/portal" in row["body"]
    assert db.email_log.docs == []

    asyncio.run(server.run_day_before_reminders(EVENING))
    assert len(db.email_outbox.docs) == 1
    assert sent == []
