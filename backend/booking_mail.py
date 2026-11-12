"""Email copy for a booking, and the US phone check.

The mailer is passed in. This module does not import Resend or the server.
"""
import html
import re
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

BUSINESS_TZ = ZoneInfo("America/Phoenix")


def normalize_us_phone(value) -> str | None:
    """10-digit US number, or None when the field was left blank.

    Raises ValueError when the shop typed something that is not a phone.
    """
    if value is None or str(value).strip() == "":
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError("Enter a 10-digit phone number.")
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def phoenix_clock(when: datetime) -> str:
    """Wall time in America/Phoenix, with the city named in the sentence."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    local = when.astimezone(BUSINESS_TZ)
    return local.strftime("%a, %b %-d, %Y at %-I:%M %p") + " Phoenix"


def _money(price) -> str:
    return f"${float(price):.2f}"


def _row(label: str, value: str) -> str:
    return f"<li>{html.escape(label)}: {html.escape(value)}</li>"


def booking_confirmation_email(*, to, reply_to, when, vehicle, address, calibration, price, pending: bool) -> dict:
    """Shop confirmation. `pending` uses the words 'pending Caleb's OK'."""
    status = "pending Caleb's OK" if pending else "confirmed"
    when_text = phoenix_clock(when)
    subject = f"Calibration {status}: {when_text}"
    body = (
        f"<p>Your calibration is <strong>{status}</strong>.</p>"
        "<ul>"
        + _row("When", when_text)
        + _row("Vehicle", vehicle)
        + _row("Address", address)
        + _row("Calibration", calibration)
        + _row("Price", _money(price))
        + "</ul>"
        "<p>Reply to this email and it comes to Caleb.</p>"
    )
    return {
        "to": to,
        "reply_to": reply_to,
        "subject": subject,
        "html": body,
        "kind": "booking_confirmation",
    }


def owner_alert_email(
    *, to, reply_to, when, shop_name, vehicle, address, calibration, price,
    pending: bool, same_day: bool, approve_url: str, decline_url: str,
) -> dict:
    """Owner alert for a same-day or before-8:00 booking, with one-tap links."""
    when_text = phoenix_clock(when)
    if same_day and pending:
        why = "Same-day request"
    elif same_day:
        why = "Same-day booking"
    else:
        why = "Before 8:00 AM request"
    status = "pending Caleb's OK" if pending else "confirmed"
    subject = f"{why}: {shop_name}"
    body = (
        f"<p>{html.escape(why)} from {html.escape(shop_name)}. "
        f"It is <strong>{status}</strong>.</p>"
        "<ul>"
        + _row("When", when_text)
        + _row("Vehicle", vehicle)
        + _row("Address", address)
        + _row("Calibration", calibration)
        + _row("Price", _money(price))
        + "</ul>"
        f'<p><a href="{html.escape(approve_url)}">Approve</a></p>'
        f'<p><a href="{html.escape(decline_url)}">Decline</a></p>'
        "<p>Each link opens a confirmation page before it changes the job. "
        "The link works once and then expires.</p>"
    )
    return {
        "to": to,
        "reply_to": reply_to,
        "subject": subject,
        "html": body,
        "kind": "owner_booking_alert",
    }


def shop_event_email(*, to, reply_to, event, when, vehicle, address, calibration, price) -> dict:
    """Shop note after the owner approves, declines, reschedules, or cancels."""
    sentences = {
        "approved": "Caleb approved this calibration.",
        "declined": "Caleb declined this calibration.",
        "rescheduled": "This calibration was rescheduled.",
        "cancelled": "This calibration was cancelled.",
    }
    sentence = sentences.get(event) or "This calibration was updated."
    when_text = phoenix_clock(when)
    subject = f"Calibration {event}: {when_text}"
    body = (
        f"<p>{html.escape(sentence)}</p>"
        "<ul>"
        + _row("When", when_text)
        + _row("Vehicle", vehicle)
        + _row("Address", address)
        + _row("Calibration", calibration)
        + _row("Price", _money(price))
        + "</ul>"
        "<p>Reply to this email and it comes to Caleb.</p>"
    )
    return {
        "to": to,
        "reply_to": reply_to,
        "subject": subject,
        "html": body,
        "kind": f"booking_{event}",
    }


def owner_needs_alert(start: datetime, booking_kind: str, now: datetime) -> bool:
    """Same-day bookings and arrivals before 8:00 AM Phoenix."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = start.astimezone(BUSINESS_TZ)
    if local.time() < time(8, 0):
        return True
    if booking_kind == "addon":
        return True
    return start.astimezone(BUSINESS_TZ).date() == now.astimezone(BUSINESS_TZ).date()


async def deliver_message(send, message: dict):
    """Call the mailer. A blank recipient is skipped so we never claim a send."""
    if not (message.get("to") or "").strip():
        return None
    return await send(
        message["to"],
        message["subject"],
        message["html"],
        kind=message.get("kind") or "transactional",
        meta=message.get("meta"),
        reply_to=message.get("reply_to"),
    )
