"""Assign jobs to technicians by home base, not a fixed East/West cut.

One active routing technician covers the whole valley. Two or more split by
an optional service radius, then by whichever home base is nearest.
No SMS, email, or database access lives here.
"""
import math
from datetime import datetime

GILBERT_HOME = {"lat": 33.3528, "lng": -111.7890, "address": "Gilbert, AZ"}
DEFAULT_DAY_START = "08:00"
DEFAULT_DAY_END = "19:00"
DEFAULT_SLOT_MINUTES = 45
DEFAULT_MAX_JOBS = 14
OWNER_COLOR = "#FF5F1F"
TECH_COLORS = ("#3B82F6", "#10B981", "#F59E0B", "#8B5CF6", "#EC4899")


def haversine_miles(lat1, lng1, lat2, lng2) -> float:
    radius = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def is_routing_tech(person: dict) -> bool:
    """Owners and hired technicians cover routes. Contractors do not."""
    if not person or person.get("role") == "contractor":
        return False
    if person.get("role") not in ("owner", "technician"):
        return False
    if person.get("routes_jobs") is False or not person.get("is_active", True):
        return False
    return person.get("home_lat") is not None and person.get("home_lng") is not None


def _distance(person: dict, lat: float, lng: float) -> float:
    return haversine_miles(person["home_lat"], person["home_lng"], lat, lng)


def covers(person: dict, lat: float, lng: float) -> bool:
    radius = person.get("service_radius_miles")
    if radius is None or radius == "":
        return False
    try:
        miles = float(radius)
    except (TypeError, ValueError):
        return False
    if miles <= 0:
        return False
    return _distance(person, lat, lng) <= miles


def assign_technician(techs: list, lat: float, lng: float):
    """Pick who drives to this point.

    A single routing technician gets every in-valley job. With more than one,
    a tech whose radius covers the point wins (nearest among those). Otherwise
    the nearest home base wins.
    """
    eligible = [person for person in techs if is_routing_tech(person)]
    if not eligible:
        return None
    if len(eligible) == 1:
        return eligible[0]
    covering = [person for person in eligible if covers(person, lat, lng)]
    pool = covering or eligible
    return min(pool, key=lambda person: _distance(person, lat, lng))


def tech_schedule(person: dict | None) -> dict:
    """One full Phoenix day. Not the old west-morning / east-afternoon split.

    Job length defaults to 20 minutes (jobs run 15–25). The buffer is the pad
    between stops, separate from the drive itself.
    """
    from scheduling import BUFFER_MINUTES, DURATION_MINUTES

    source = person or {}
    duration = source.get("job_duration_minutes")
    buffer = source.get("buffer_minutes")
    return {
        "day_start": source.get("day_start") or DEFAULT_DAY_START,
        "day_end": source.get("day_end") or DEFAULT_DAY_END,
        "slot_minutes": int(source.get("slot_minutes") or DEFAULT_SLOT_MINUTES),
        "max_jobs": int(source.get("max_jobs") or DEFAULT_MAX_JOBS),
        "job_duration_minutes": DURATION_MINUTES if duration is None else int(duration),
        "buffer_minutes": BUFFER_MINUTES if buffer is None else int(buffer),
    }


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed


def availability_windows(day_start: datetime, day_end: datetime, jobs: list) -> list:
    """Open time before the first job and after the last one.

    A later job must not hide the morning, and a morning job must not hide
    the afternoon. That was the East/West failure mode.
    """
    ordered = sorted(jobs, key=lambda job: job.get("scheduled_start") or "")
    if not ordered:
        return [{"origin": "home", "start": day_start, "end": day_end, "job": None}]
    windows = []
    first_start = _parse(ordered[0]["scheduled_start"])
    if first_start > day_start:
        windows.append({"origin": "home", "start": day_start, "end": first_start, "job": None})
    last = ordered[-1]
    last_end = _parse(last.get("scheduled_end") or last["scheduled_start"])
    if last_end < day_end:
        windows.append({"origin": "job", "start": last_end, "end": day_end, "job": last})
    return windows


def owner_routing_updates(owner: dict) -> dict:
    """Fill routing fields on the owner without overwriting a home they already set."""
    updates = {}
    if not (owner.get("home_address") or "").strip():
        updates["home_address"] = GILBERT_HOME["address"]
    if owner.get("home_lat") is None or owner.get("home_lng") is None:
        updates["home_lat"] = GILBERT_HOME["lat"]
        updates["home_lng"] = GILBERT_HOME["lng"]
    if "routes_jobs" not in owner:
        updates["routes_jobs"] = True
    if not owner.get("color"):
        updates["color"] = OWNER_COLOR
    if not owner.get("day_start"):
        updates["day_start"] = DEFAULT_DAY_START
    if not owner.get("day_end"):
        updates["day_end"] = DEFAULT_DAY_END
    if not owner.get("slot_minutes"):
        updates["slot_minutes"] = DEFAULT_SLOT_MINUTES
    if not owner.get("max_jobs"):
        updates["max_jobs"] = DEFAULT_MAX_JOBS
    return updates


def contractor_routing_updates(person: dict) -> dict:
    if person.get("role") == "contractor" and "routes_jobs" not in person:
        return {"routes_jobs": False}
    return {}


def next_tech_color(used: list) -> str:
    for color in (OWNER_COLOR, *TECH_COLORS):
        if color not in used:
            return color
    return TECH_COLORS[len(used) % len(TECH_COLORS)]
