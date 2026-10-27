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
