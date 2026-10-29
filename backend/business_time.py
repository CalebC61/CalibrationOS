"""America/Phoenix calendar dates for job queries.

The shop runs on America/Phoenix (UTC−7, no daylight saving). API date strings
are Phoenix civil dates. Job instants are stored as UTC ISO strings, so a
6 PM Phoenix appointment is 01:00 UTC the next calendar day and must be queried
with that shift.

Stdlib only (`zoneinfo`). Naive datetimes are treated as UTC, matching the rest
of the backend.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

BUSINESS_TZ = ZoneInfo("America/Phoenix")


def _as_utc(instant: datetime) -> datetime:
    if instant.tzinfo is None:
        return instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc)


def business_date(instant: datetime | None = None) -> date:
    """Phoenix calendar date of an instant. Defaults to the current UTC time."""
    if instant is None:
        instant = datetime.now(timezone.utc)
    return _as_utc(instant).astimezone(BUSINESS_TZ).date()


def business_day_bounds(day: date) -> tuple[datetime, datetime]:
    """Half-open [start, end) of a Phoenix civil day, as UTC datetimes.

    Phoenix has no DST, so this is a 24-hour span starting at 07:00 UTC.
    The end is the next Phoenix midnight, converted to UTC — not assumed.
    """
    start_local = datetime.combine(day, time.min, tzinfo=BUSINESS_TZ)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def in_business_day(instant: datetime, day: date) -> bool:
    """True when instant falls in the half-open Phoenix day."""
    start, end = business_day_bounds(day)
    utc = _as_utc(instant)
    return start <= utc < end


def offered_slot_starts(
    day: date,
    earliest: datetime,
    zone_end: datetime,
    slot_minutes: int,
    limit: int | None = None,
) -> list[datetime]:
    """UTC-wall-clock slot starts that still land on the requested Phoenix day.

    Zone hours are combined as UTC on the calendar label (`05:00` → 05:00 UTC).
    That instant is 10 PM Phoenix the day before, so the job query for `day`
    would not see it and the same slot could be offered again. Starts before
    the Phoenix day are skipped; the step from `earliest` is unchanged.
    """
    if slot_minutes <= 0:
        raise ValueError("slot_minutes must be greater than 0")
    if limit is not None and limit <= 0:
        return []
    cursor = _as_utc(earliest)
    zone_end_utc = _as_utc(zone_end)
    day_start, day_end = business_day_bounds(day)
    step = timedelta(minutes=slot_minutes)
    starts: list[datetime] = []
    while cursor + step <= zone_end_utc:
        if cursor >= day_end:
            break
        if cursor >= day_start:
            starts.append(cursor)
            if limit is not None and len(starts) >= limit:
                break
        cursor = cursor + step
    return starts


def clamp_start_to_business_day(start: datetime, day: date) -> datetime | None:
    """Keep a computed start on `day`.

    Earlier than the Phoenix day (a UTC wall clock before 07:00) moves up to
    that day's start. A start on a later day cannot be clamped and returns None.
    """
    day_start, day_end = business_day_bounds(day)
    start_utc = _as_utc(start)
    if start_utc < day_start:
        return day_start
    if start_utc >= day_end:
        return None
    return start_utc
