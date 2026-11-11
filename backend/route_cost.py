"""How many Google Routes calls a schedule is allowed to make.

Pure. TRAFFIC_UNAWARE (Compute Routes Essentials) rejects departureTime, so a
later date uses one call per origin/destination and a local rush-hour
multiplier. TRAFFIC_AWARE (Pro) is only for today, and for tomorrow while it
is still before the cutoff (default 10:00 AM Phoenix).

Same-day Pro departures stay on a 15-minute bucket. Future dates use 30
minutes. A drive back home is one call per hour on Pro, and one call total
on Essentials.
"""
from datetime import date, datetime, time, timedelta

from business_time import BUSINESS_TZ, business_date, business_day_bounds
from routing import haversine_miles

PRO = "pro"
ESSENTIALS = "essentials"

DEFAULT_PRO_CUTOFF = "10:00"
DEFAULT_RUSH_MULTIPLIER = 1.25
DEFAULT_RUSH_MORNING = ("06:30", "09:00")
DEFAULT_RUSH_EVENING = ("15:30", "18:30")
DEFAULT_PRO_DAILY_LIMIT = 300
DEFAULT_ESSENTIALS_DAILY_LIMIT = 600

PRO_CACHE_SECONDS = 2 * 3600
ESSENTIALS_CACHE_SECONDS = 7 * 86400
# Faster than the mileage estimate. If even this cannot make the slot, skip Google.
FAST_MINUTES_PER_MILE = 1.0


def default_drive_settings() -> dict:
    return {
        "pro_cutoff": DEFAULT_PRO_CUTOFF,
        "rush_multiplier": DEFAULT_RUSH_MULTIPLIER,
        "rush_morning_start": DEFAULT_RUSH_MORNING[0],
        "rush_morning_end": DEFAULT_RUSH_MORNING[1],
        "rush_evening_start": DEFAULT_RUSH_EVENING[0],
        "rush_evening_end": DEFAULT_RUSH_EVENING[1],
        "pro_daily_limit": DEFAULT_PRO_DAILY_LIMIT,
        "essentials_daily_limit": DEFAULT_ESSENTIALS_DAILY_LIMIT,
    }


def _hhmm(value: str) -> time:
    hour, minute = str(value).split(":")[:2]
    return time(int(hour), int(minute))


def _clock(moment: datetime) -> time:
    if moment is None:
        return time(12, 0)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BUSINESS_TZ)
    return moment.astimezone(BUSINESS_TZ).timetz().replace(tzinfo=None)


def routing_mode(appointment_day: date, now: datetime, pro_cutoff: str = DEFAULT_PRO_CUTOFF) -> str:
    """Pro for today, and for tomorrow while the Phoenix clock is still before the cutoff."""
    today = business_date(now)
    if appointment_day <= today:
        return PRO
    if appointment_day == today + timedelta(days=1) and _clock(now) < _hhmm(pro_cutoff):
        return PRO
    return ESSENTIALS


def in_rush_hour(depart: datetime | None, settings: dict | None = None) -> bool:
    settings = settings or default_drive_settings()
    clock = _clock(depart)
    morning = _hhmm(settings["rush_morning_start"]) <= clock < _hhmm(settings["rush_morning_end"])
    evening = _hhmm(settings["rush_evening_start"]) <= clock < _hhmm(settings["rush_evening_end"])
    return morning or evening


def rush_factor(depart: datetime | None, settings: dict | None = None) -> float:
    settings = settings or default_drive_settings()
    if in_rush_hour(depart, settings):
        return float(settings["rush_multiplier"])
    return 1.0


def apply_rush(minutes: int, depart: datetime | None, settings: dict | None = None) -> int:
    if minutes <= 0:
        return 0
    return max(1, round(minutes * rush_factor(depart, settings)))


def cache_ttl_seconds(mode: str, now: datetime, appointment_day: date | None) -> int:
    """Pro stays for 2 hours. Essentials stays 7 days, or until that date ends."""
    if mode == PRO:
        return PRO_CACHE_SECONDS
    cap = ESSENTIALS_CACHE_SECONDS
    if appointment_day is None:
        return cap
    _start, end = business_day_bounds(appointment_day)
    remaining = int((end - now.astimezone(end.tzinfo)).total_seconds())
    if remaining <= 0:
        return 60
    return min(cap, remaining)


def _point(point) -> tuple:
    return (round(float(point[0]), 4), round(float(point[1]), 4))


def _same(a, b) -> bool:
    if not a or not b or a[0] is None or b[0] is None:
        return False
    return _point(a) == _point(b)


def _bucket(moment: datetime, minutes: int) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BUSINESS_TZ)
    local = moment.astimezone(BUSINESS_TZ).replace(second=0, microsecond=0)
    floored = (local.minute // minutes) * minutes
    local = local.replace(minute=floored)
    return local.strftime("%Y-%m-%dT%H:%M")


def leg_signature(origin, dest, depart, *, mode: str, same_day: bool, home) -> str:
    """Cache and prefetch identity. Essentials ignores the clock. Pro buckets it."""
    left, right = _point(origin), _point(dest)
    if mode == ESSENTIALS:
        return f"{left}|{right}|essentials"
    if depart is None:
        slot = "none"
    elif home is not None and _same(dest, home):
        slot = _bucket(depart, 60)
    else:
        slot = _bucket(depart, 15 if same_day else 30)
    return f"{left}|{right}|pro|{slot}"


def obviously_impossible(origin, dest, depart, arrive_by) -> bool:
    """True when even 60 mph cannot reach arrive_by. Those legs skip Google."""
    if depart is None or arrive_by is None:
        return False
    if origin[0] is None or dest[0] is None:
        return False
    if depart.tzinfo is None:
        depart = depart.replace(tzinfo=BUSINESS_TZ)
    if arrive_by.tzinfo is None:
        arrive_by = arrive_by.replace(tzinfo=BUSINESS_TZ)
    miles = haversine_miles(origin[0], origin[1], dest[0], dest[1])
    fastest = timedelta(minutes=miles * FAST_MINUTES_PER_MILE)
    return depart.astimezone(BUSINESS_TZ) + fastest > arrive_by.astimezone(BUSINESS_TZ)


def collapse_queries(queries, *, mode: str, same_day: bool, home) -> list:
    """Unique Google calls after the prefilter and the home-return collapse.

    Each item is (origin, dest, depart, signature). `depart` is what Pro sends
    to the API. Essentials ignores it.
    """
    seen = {}
    for item in queries:
        origin, dest = item[0], item[1]
        depart = item[2] if len(item) > 2 else None
        arrive_by = item[3] if len(item) > 3 else None
        if not origin or not dest or origin[0] is None or dest[0] is None:
            continue
        if _same(origin, dest):
            continue
        if obviously_impossible(origin, dest, depart, arrive_by):
            continue
        signature = leg_signature(origin, dest, depart, mode=mode, same_day=same_day, home=home)
        if signature not in seen:
            seen[signature] = (origin, dest, depart, signature)
    return list(seen.values())


def normalize_address(address: str) -> str:
    return " ".join(str(address or "").lower().split())
