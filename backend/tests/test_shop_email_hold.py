"""Shop mail stays in the outbox until SHOP_EMAILS_ENABLED is on.

Resend must not be called for a shop or customer while that flag is false.
Owner alerts still send when OWNER_EMAILS_ENABLED is left on.

    cd backend && pytest tests/test_shop_email_hold.py -v
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from booking_mail import owner_emails_enabled, shop_emails_enabled  # noqa: E402

WHEN = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)
JOB = {
    "id": "job-1",
    "shop_name": "Preferred",
    "scheduled_start": WHEN.isoformat(),
    "job_address": "1234 E Williams Field Rd, Gilbert, AZ",
    "vehicle_year": 2022,
    "vehicle_make": "Honda",
    "vehicle_model": "Civic",
    "calibration_label": "Static ADAS Calibration",
    "calibration_type": "static",
    "price": 125,
    "booking_kind": "standard",
    "status": "booked",
}
SHOP = {"name": "Preferred", "contact_email": "shop@glass.example"}


class _Store:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    def find(self, query=None, projection=None):
        return self

    async def to_list(self, n):
        return list(self.docs)


class _DB:
    def __init__(self):
        self.email_outbox = _Store()
        self.email_log = _Store()
        self.admin_notifications = _Store()


def test_shop_emails_default_off_and_owner_emails_default_on(monkeypatch):
    monkeypatch.delenv("SHOP_EMAILS_ENABLED", raising=False)
    monkeypatch.delenv("OWNER_EMAILS_ENABLED", raising=False)
    assert shop_emails_enabled() is False
    assert owner_emails_enabled() is True


def _install(monkeypatch, shop_on, owner_on):
    monkeypatch.setenv("SHOP_EMAILS_ENABLED", "true" if shop_on else "false")
    monkeypatch.setenv("OWNER_EMAILS_ENABLED", "true" if owner_on else "false")
    monkeypatch.setattr(server, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr(server, "db", _DB())
    sent = []

    def fake_send(payload):
        sent.append(payload)
        return {"id": "re_test"}

    monkeypatch.setattr(server.resend_sdk.Emails, "send", fake_send)
    return sent


def _shop_recipients(sent):
    found = []
    for payload in sent:
        for addr in payload.get("to") or []:
            if addr != server.SEED_OWNER_EMAIL:
                found.append(addr)
    return found


def test_shop_confirmation_and_status_mail_do_not_call_resend_while_off(monkeypatch):
    sent = _install(monkeypatch, shop_on=False, owner_on=True)

    async def run():
        await server.email_shop_confirmation(JOB, SHOP, pending=False)
        for event in ("approved", "declined", "rescheduled", "cancelled"):
            await server.email_shop_event(JOB, SHOP, event)

    asyncio.run(run())
    assert sent == []
    assert _shop_recipients(sent) == []
    outbox = server.db.email_outbox.docs
    assert len(outbox) == 5
    for row in outbox:
        assert row["to"] == "shop@glass.example"
        assert row["subject"]
        assert row["body"]
        assert row["created_at"]
        assert "2022 Honda Civic" in row["body"]
        assert row["audience"] == "shop"


def test_owner_alert_still_calls_resend_while_shop_mail_is_off(monkeypatch):
    sent = _install(monkeypatch, shop_on=False, owner_on=True)

    async def run():
        await server.email_owner_alert(JOB, SHOP, pending=True, same_day=False)
        await server.email_shop_confirmation(JOB, SHOP, pending=True)

    asyncio.run(run())
    assert len(sent) == 1
    assert sent[0]["to"] == [server.SEED_OWNER_EMAIL]
    assert _shop_recipients(sent) == []
    assert server.db.email_outbox.docs[0]["to"] == "shop@glass.example"


def test_shop_mail_calls_resend_only_after_the_flag_is_on(monkeypatch):
    sent = _install(monkeypatch, shop_on=True, owner_on=True)
    asyncio.run(server.email_shop_confirmation(JOB, SHOP, pending=False))
    assert len(sent) == 1
    assert sent[0]["to"] == ["shop@glass.example"]
    assert server.db.email_outbox.docs == []


def test_owner_alerts_hold_when_their_own_flag_is_off(monkeypatch):
    sent = _install(monkeypatch, shop_on=False, owner_on=False)
    asyncio.run(server.email_owner_alert(JOB, SHOP, pending=True, same_day=True))
    assert sent == []
    assert server.db.email_outbox.docs[0]["to"] == server.SEED_OWNER_EMAIL
    assert server.db.email_outbox.docs[0]["audience"] == "owner"
