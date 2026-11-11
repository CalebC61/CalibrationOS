"""Advance bookings versus a booking for today.

The shop uses one flow. The engine looks at the Phoenix date they picked:
a later date is an advance booking (including a request made the night before),
and today uses the stricter same-day limits. Nothing here is a separate
shop-facing choice.

No database and no messages.
"""
from datetime import datetime, time

from business_time import BUSINESS_TZ, business_date

EARLY_START = time(6, 0)
AUTO_CONFIRM_AT = time(8, 0)
PUBLIC_END = time(17, 0)
DEFAULT_CUTOFF = "13:00"
DEFAULT_MAX_EXTRA_DRIVE = 20
DEFAULT_MAX_LATER_FINISH = 45
DEFAULT_OVER_LIMIT = "pending"


def _clock(moment: datetime) -> time:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BUSINESS_TZ)
    return moment.astimezone(BUSINESS_TZ).timetz().replace(tzinfo=None)


def arrival_band(moment: datetime) -> str:
    """before_open, early (needs approval), standard, or after_close."""
    clock = _clock(moment)
    if clock < EARLY_START:
        return "before_open"
    if clock < AUTO_CONFIRM_AT:
        return "early"
    if clock <= PUBLIC_END:
        return "standard"
    return "after_close"


def request_kind(appointment_day, now: datetime) -> str:
    """advance, same_day, or past.

    Tomorrow or later is advance, including a request made the night before.
    The same Phoenix date as `now` is same-day, whatever the clock says.
    """
    today = business_date(now)
    if appointment_day > today:
        return "advance"
    if appointment_day < today:
        return "past"
    return "same_day"


def _hhmm(value: str) -> time:
    hour, minute = str(value or DEFAULT_CUTOFF).split(":")
    return time(int(hour), int(minute))


def policy_from_tech(person: dict | None) -> dict:
    """Owner limits. Missing fields use the defaults so existing technicians pick them up."""
    source = person or {}
    over = source.get("same_day_over_limit") or DEFAULT_OVER_LIMIT
    if over not in ("pending", "hide"):
        over = DEFAULT_OVER_LIMIT
    enabled = source.get("same_day_bookings_enabled")
    if enabled is None:
        enabled = source.get("same_day_addons_enabled")
    extra = source.get("same_day_max_extra_drive_minutes")
    later = source.get("same_day_max_later_finish_minutes")
    return {
        "enabled": True if enabled is None else bool(enabled),
        "cutoff": source.get("same_day_cutoff") or DEFAULT_CUTOFF,
        "max_extra_drive_minutes": DEFAULT_MAX_EXTRA_DRIVE if extra is None else int(extra),
        "max_later_finish_minutes": DEFAULT_MAX_LATER_FINISH if later is None else int(later),
        "over_limit": over,
    }


def cutoff_label(cutoff: str) -> str:
    clock = _hhmm(cutoff)
    hour = clock.hour % 12 or 12
    suffix = "AM" if clock.hour < 12 else "PM"
    return f"{hour}:{clock.minute:02d} {suffix}"


def same_day_closed_message(now: datetime, policy: dict) -> str | None:
    """Why a same-day request is closed, or None when shops may still ask."""
    if not policy["enabled"]:
        return "Bookings for today are turned off. Pick another date."
    if _clock(now) > _hhmm(policy["cutoff"]):
        return f"Bookings for today have to be requested by {cutoff_label(policy['cutoff'])}."
    return None


def over_addon_limit(extra: int, later: int, policy: dict) -> bool:
    return extra > policy["max_extra_drive_minutes"] or later > policy["max_later_finish_minutes"]


def slot_decision(
    *,
    band: str,
    kind: str,
    had_route: bool,
    extra: int,
    later: int,
    policy: dict,
    allow_outside: bool,
) -> dict | None:
    """How to offer one feasible arrival.

    None means do not offer it. Owner edits pass allow_outside and are booked:
    saving is the approval. Shops do not get that override.
    """
    if allow_outside:
        return {"requires_approval": False, "approval_reason": None, "status": "booked"}
    if kind == "same_day" and had_route and over_addon_limit(extra, later, policy):
        if policy["over_limit"] == "hide":
            return None
        return {
            "requires_approval": True,
            "approval_reason": "same_day_addon",
            "status": "requested",
        }
    if band == "early":
        return {
            "requires_approval": True,
            "approval_reason": "early_arrival",
            "status": "requested",
        }
    if band in ("before_open", "after_close"):
        return None
    return {"requires_approval": False, "approval_reason": None, "status": "booked"}
