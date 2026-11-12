"""Closed dates for the Phoenix shop calendar.

Holidays are a fixed US list the owner can turn off. A custom range is a
vacation. Nothing here reads the database or sends a message. Sunday stays a
separate rule in the booking route so that copy does not change.
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BUSINESS_TZ = ZoneInfo("America/Phoenix")

_HOLIDAYS = (
    ("new-years", "New Year's Day"),
    ("memorial", "Memorial Day"),
    ("july-4", "July 4"),
    ("labor", "Labor Day"),
    ("thanksgiving", "Thanksgiving"),
    ("day-after-thanksgiving", "Day after Thanksgiving"),
    ("christmas-eve", "Christmas Eve"),
    ("christmas", "Christmas"),
)

_SKIP_STATUSES = {"cancelled", "declined", "complete"}


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last = next_month - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _holiday_date(year: int, key: str) -> date:
    if key == "new-years":
        return date(year, 1, 1)
    if key == "memorial":
        return _last_weekday(year, 5, 0)
    if key == "july-4":
        return date(year, 7, 4)
    if key == "labor":
        return _nth_weekday(year, 9, 0, 1)
    if key == "thanksgiving":
        return _nth_weekday(year, 11, 3, 4)
    if key == "day-after-thanksgiving":
        return _nth_weekday(year, 11, 3, 4) + timedelta(days=1)
    if key == "christmas-eve":
        return date(year, 12, 24)
    if key == "christmas":
        return date(year, 12, 25)
    raise KeyError(key)


def holiday_records(year: int) -> list[dict]:
    """One closed row per major holiday in `year`. Keys stay stable so a toggle sticks."""
    rows = []
    for key, label in _HOLIDAYS:
        day = _holiday_date(year, key).isoformat()
        rows.append({
            "key": f"{year}-{key}",
            "label": label,
            "kind": "holiday",
            "blocked": True,
            "start": day,
            "end": day,
        })
    return rows


def set_blocked(records: list[dict], key: str, blocked: bool) -> list[dict]:
    """Copy of `records` with one row's blocked flag changed. Missing keys are left alone."""
    updated = []
    for row in records:
        if row.get("key") == key:
            updated.append({**row, "blocked": bool(blocked)})
        else:
            updated.append(dict(row))
    return updated


def _covered(row: dict) -> list[date]:
    start = date.fromisoformat(row["start"])
    end = date.fromisoformat(row.get("end") or row["start"])
    if end < start:
        start, end = end, start
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def closure_message(day: date, records: list[dict]) -> str | None:
    """Why `day` is closed, or None when shops may book it.

    A row with blocked false is an open holiday. Sunday is not decided here.
    """
    for row in records:
        if row.get("blocked", True) and day in _covered(row):
            label = row.get("label") or "a day off"
            return f"Closed for {label}."
    return None


def parse_range(start: str, end: str | None) -> tuple[date, date]:
    """Inclusive start and end. A missing end is a single day."""
    try:
        first = date.fromisoformat(start)
        last = date.fromisoformat(end) if end else first
    except ValueError as exc:
        raise ValueError("Use dates like 2026-12-20.") from exc
    if last < first:
        raise ValueError("The end date has to be on or after the start.")
    if (last - first).days > 62:
        raise ValueError("Pick a shorter range.")
    return first, last


def _phoenix_day(value: str) -> date | None:
    try:
        instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(BUSINESS_TZ).date()


def jobs_to_flag(jobs: list[dict], days: set[date]) -> list[dict]:
    """Jobs already on a newly closed day. Cancelled and finished jobs are skipped.

    The returned dicts are the same objects. Their status is not changed.
    """
    flagged = []
    for job in jobs:
        if job.get("status") in _SKIP_STATUSES:
            continue
        day = _phoenix_day(job.get("scheduled_start") or "")
        if day in days:
            flagged.append(job)
    return flagged
