"""Booking confirmation email, with the mailer mocked.

    cd backend && pytest tests/test_booking_mail.py -v
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from booking_mail import (  # noqa: E402
    booking_confirmation_email,
    deliver_message,
    normalize_us_phone,
    owner_alert_email,
    owner_needs_alert,
    shop_event_email,
)

WHEN = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)  # 8:00 AM Phoenix
EARLY = datetime(2026, 11, 13, 14, 0, tzinfo=timezone.utc)  # 7:00 AM Phoenix
NOW = datetime(2026, 11, 12, 17, 0, tzinfo=timezone.utc)


def test_confirmation_email_includes_the_booking_and_phoenix_time():
    message = booking_confirmation_email(
        to="shop@glass.example",
        reply_to="caleb@thecalibrationcrew.us",
        when=WHEN,
        vehicle="2022 Honda Civic",
        address="1234 E Williams Field Rd, Gilbert, AZ",
        calibration="Static ADAS Calibration",
        price=125,
        pending=False,
    )
    assert message["to"] == "shop@glass.example"
    assert message["reply_to"] == "caleb@thecalibrationcrew.us"
    assert message["kind"] == "booking_confirmation"
    body = message["subject"] + message["html"]
    assert "confirmed" in body
    assert "pending Caleb's OK" not in body
    assert "Fri, Nov 13, 2026" in body
    assert "8:00 AM" in body
    assert "Phoenix" in body
    assert "2022 Honda Civic" in body
    assert "1234 E Williams Field Rd, Gilbert, AZ" in body
    assert "Static ADAS Calibration" in body
    assert "$125.00" in body


def test_a_held_booking_says_pending_calebs_ok():
    message = booking_confirmation_email(
        to="shop@glass.example",
        reply_to="caleb@thecalibrationcrew.us",
        when=EARLY,
        vehicle="2022 Honda Civic",
        address="Surprise, AZ",
        calibration="Static ADAS Calibration",
        price=125,
        pending=True,
    )
    assert "pending Caleb's OK" in message["html"]
    assert "pending Caleb's OK" in message["subject"]


def test_deliver_message_calls_the_mailer_and_does_not_send_without_a_recipient():
    sent = []

    async def send(to, subject, html, kind="transactional", meta=None, reply_to=None):
        sent.append({
            "to": to, "subject": subject, "html": html, "kind": kind, "reply_to": reply_to,
        })
        return {"delivered": True}

    message = booking_confirmation_email(
        to="shop@glass.example",
        reply_to="caleb@thecalibrationcrew.us",
        when=WHEN,
        vehicle="2022 Honda Civic",
        address="Gilbert, AZ",
        calibration="Static ADAS Calibration",
        price=125,
        pending=False,
    )
    result = asyncio.run(deliver_message(send, message))
    assert result["delivered"] is True
    assert sent[0]["to"] == "shop@glass.example"
    assert sent[0]["reply_to"] == "caleb@thecalibrationcrew.us"
    assert "2022 Honda Civic" in sent[0]["html"]
    assert asyncio.run(deliver_message(send, {**message, "to": ""})) is None
    assert len(sent) == 1


def test_owner_alert_has_distinct_approve_and_decline_links():
    message = owner_alert_email(
        to="caleb@thecalibrationcrew.us",
        reply_to="caleb@thecalibrationcrew.us",
        when=EARLY,
        shop_name="Preferred Glass",
        vehicle="2022 Honda Civic",
        address="Surprise, AZ",
        calibration="Static ADAS Calibration",
        price=125,
        pending=True,
        same_day=False,
        approve_url="https://www.thecalibrationcrew.us/owner-action/approve-token",
        decline_url="https://www.thecalibrationcrew.us/owner-action/decline-token",
    )
    assert message["to"] == "caleb@thecalibrationcrew.us"
    assert "approve-token" in message["html"]
    assert "decline-token" in message["html"]
    assert message["html"].index("approve-token") != message["html"].index("decline-token")
    assert "Approve" in message["html"]
    assert "Decline" in message["html"]
    assert "7:00 AM" in message["html"]
    assert "Phoenix" in message["html"]


def test_shop_is_emailed_when_the_owner_decides_or_moves_the_job():
    for event, phrase in (
        ("approved", "approved"),
        ("declined", "declined"),
        ("rescheduled", "rescheduled"),
        ("cancelled", "cancelled"),
    ):
        message = shop_event_email(
            to="shop@glass.example",
            reply_to="caleb@thecalibrationcrew.us",
            event=event,
            when=WHEN,
            vehicle="2022 Honda Civic",
            address="Gilbert, AZ",
            calibration="Static ADAS Calibration",
            price=125,
        )
        assert message["reply_to"] == "caleb@thecalibrationcrew.us"
        blob = (message["subject"] + message["html"]).lower()
        assert phrase in blob
        assert "8:00 AM" in message["html"]
        assert "Phoenix" in message["html"]
        assert "2022 Honda Civic" in message["html"]


def test_owner_is_alerted_for_same_day_and_before_8():
    assert owner_needs_alert(EARLY, "standard", NOW) is True
    assert owner_needs_alert(WHEN, "addon", NOW) is True
    assert owner_needs_alert(WHEN, "standard", NOW) is False


def test_phone_numbers_must_look_like_a_us_phone():
    assert normalize_us_phone("480-555-0142") == "(480) 555-0142"
    assert normalize_us_phone("(480) 555-0142") == "(480) 555-0142"
    assert normalize_us_phone("+1 480 555 0142") == "(480) 555-0142"
    assert normalize_us_phone(None) is None
    assert normalize_us_phone("  ") is None
    for bad in ("call me", "555-0142", "123", "480-555-01421"):
        try:
            normalize_us_phone(bad)
        except ValueError as exc:
            assert "phone" in str(exc).lower()
        else:
            raise AssertionError(f"expected {bad!r} to be rejected")
