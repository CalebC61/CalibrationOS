"""Rules for editing a booked job without notifying anyone or changing its status.

No Mongo and no HTTP. Routes in server.py apply the result.
"""
from datetime import datetime, timedelta, timezone

from business_time import business_date, business_day_bounds

CALIBRATION_TYPES = ("static", "dynamic", "dual", "triple", "tesla")


def parse_instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid date and time.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def shift_scheduled_end(job: dict, new_start: datetime) -> datetime:
    """Keep the job's current duration when the start time moves."""
    old_start = parse_instant(job["scheduled_start"])
    old_end = parse_instant(job.get("scheduled_end") or job["scheduled_start"])
    duration = old_end - old_start
    if duration.total_seconds() <= 0:
        duration = timedelta(hours=1)
    return new_start + duration


def is_upcoming(job: dict, now: datetime | None = None) -> bool:
    """True for this shop's jobs that are still on today's Phoenix date or later.

    Cancelled and completed jobs are not upcoming.
    """
    if job.get("status") in ("cancelled", "complete"):
        return False
    try:
        start = parse_instant(job["scheduled_start"])
    except (ValueError, KeyError, TypeError):
        return False
    day_start, _day_end = business_day_bounds(business_date(now))
    return start >= day_start


def _text(value):
    if value is None:
        return None
    return str(value).strip()


def _require_text(value, label: str, limit: int) -> str:
    text = _text(value)
    if not text:
        raise ValueError(f"{label} is required.")
    if len(text) > limit:
        raise ValueError(f"{label} is too long.")
    return text


def _optional_text(value, label: str, limit: int):
    text = _text(value)
    if not text:
        return None
    if len(text) > limit:
        raise ValueError(f"{label} is too long.")
    return text


def prepare_edit(raw: dict, *, allow_price: bool, allow_zone: bool) -> dict:
    """Validate a partial job edit.

    `raw` is only the fields the client sent. Price and zone are rejected for a
    shop token. Status is never accepted here.
    """
    if not allow_price and "price" in raw:
        raise ValueError("Price can only be changed by the owner.")
    if not allow_zone and "zone" in raw:
        raise ValueError("Zone can only be changed by the owner.")

    fields = {}
    if "job_address" in raw:
        fields["job_address"] = _require_text(raw["job_address"], "Address", 300)
    if "customer_first_name" in raw:
        fields["customer_first_name"] = _optional_text(raw["customer_first_name"], "First name", 80)
    if "customer_last_name" in raw:
        fields["customer_last_name"] = _require_text(raw["customer_last_name"], "Last name", 80)
    if "notification_phone" in raw:
        fields["notification_phone"] = _optional_text(raw["notification_phone"], "Phone", 40)
    if "notification_email" in raw:
        email = _optional_text(raw["notification_email"], "Email", 120)
        if email and ("@" not in email or "." not in email.split("@")[-1]):
            raise ValueError("Email is not valid.")
        fields["notification_email"] = email
    if "vehicle_year" in raw:
        try:
            year = int(raw["vehicle_year"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Year is not valid.") from exc
        if year < 1980 or year > 2035:
            raise ValueError("Year is not valid.")
        fields["vehicle_year"] = year
    if "vehicle_make" in raw:
        fields["vehicle_make"] = _require_text(raw["vehicle_make"], "Make", 40)
    if "vehicle_model" in raw:
        fields["vehicle_model"] = _require_text(raw["vehicle_model"], "Model", 40)
    if "vehicle_vin" in raw:
        vin = _optional_text(raw["vehicle_vin"], "VIN", 17)
        fields["vehicle_vin"] = vin.upper() if vin else None
    if "calibration_type" in raw:
        cal = _text(raw["calibration_type"])
        if cal not in CALIBRATION_TYPES:
            raise ValueError("Calibration type is not valid.")
        fields["calibration_type"] = cal
    if "price" in raw:
        try:
            price = float(raw["price"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Price is not valid.") from exc
        if price < 0:
            raise ValueError("Price is not valid.")
        fields["price"] = price
    if "zone" in raw:
        zone = _text(raw["zone"])
        if zone not in ("west", "east"):
            raise ValueError("Zone is not valid.")
        fields["zone"] = zone
    if "notes" in raw:
        fields["notes"] = _optional_text(raw["notes"], "Notes", 4000)
    if "scheduled_start" in raw:
        fields["scheduled_start"] = parse_instant(raw["scheduled_start"]).isoformat()
    return fields


def values_differ(old, new) -> bool:
    if isinstance(old, (int, float)) or isinstance(new, (int, float)):
        try:
            return float(old) != float(new)
        except (TypeError, ValueError):
            return True
    return old != new


def changed_keys(job: dict, fields: dict) -> list:
    return [key for key, value in fields.items() if values_differ(job.get(key), value)]
