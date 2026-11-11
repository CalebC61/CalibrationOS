"""Plan lat/lng/zone updates from the current geocoder.

No Mongo, HTTP, SMS, or email. The route in server.py applies the plan.
"""
from datetime import date, datetime
from typing import Optional

from business_time import business_day_bounds

# Same cut detect_zone has always used: west of -112, central and east otherwise.
_WEST_LNG = -112.0
_FORBIDDEN_WRITE_KEYS = {"status", "invoice_status", "notification_phone", "notification_email", "result"}


def detect_zone(lng: float) -> str:
    if lng < _WEST_LNG:
        return "west"
    return "east"  # Central also maps to East per spec


def zone_for_geocode(geo: dict) -> Optional[str]:
    """Zone for a geocode result, or None when the point is outside the metro.

    Outside the metro the caller still moves the pin and leaves the stored zone alone.
    """
    if not geo.get("in_metro"):
        return None
    return detect_zone(geo["lng"])


def regeocode_scope(date_str: Optional[str]) -> dict:
    """What a re-geocode call refreshes.

    No date (or a blank one): every shop and every job.
    YYYY-MM-DD: jobs on that America/Phoenix day only. Shops are not dated, so they
    are left out of a dated run.
    """
    if date_str is None or not str(date_str).strip():
        return {"shops": True, "jobs": "all", "day": None}
    raw = str(date_str).strip()
    try:
        day = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Invalid date. Use YYYY-MM-DD.") from exc
    return {"shops": False, "jobs": "day", "day": day}


def jobs_on_phoenix_day(day: date) -> dict:
    """Mongo filter for jobs whose scheduled_start falls on a Phoenix civil date."""
    start, end = business_day_bounds(day)
    return {"scheduled_start": {"$gte": start.isoformat(), "$lt": end.isoformat()}}


def location_set(fields: dict, updated_at: str) -> dict:
    """$set document for a coordinate write. Refuses status and messaging fields."""
    overlap = _FORBIDDEN_WRITE_KEYS & set(fields)
    if overlap:
        raise ValueError(f"refusing to change {sorted(overlap)}")
    return {**fields, "updated_at": updated_at}


async def regeocode_records(records, geocode, lat_key: str, lng_key: str, address_key: str, zone_for) -> dict:
    """Compare each record to a fresh geocode. Does not write and does not notify.

    `zone_for(geo)` returns a zone string, or None to leave the stored zone unchanged.
    A geocoder exception counts as failed and the rest of the batch continues.
    """
    updated = unchanged = skipped = failed = 0
    changes = []
    for rec in records:
        address = (rec.get(address_key) or "").strip()
        if not address:
            skipped += 1
            continue
        try:
            geo = await geocode(address)
        except Exception:
            failed += 1
            continue
        fields = {}
        if rec.get(lat_key) != geo["lat"]:
            fields[lat_key] = geo["lat"]
        if rec.get(lng_key) != geo["lng"]:
            fields[lng_key] = geo["lng"]
        zone = zone_for(geo)
        if zone is not None and rec.get("zone") != zone:
            fields["zone"] = zone
        if not fields:
            unchanged += 1
            continue
        updated += 1
        changes.append({"id": rec.get("id"), "set": fields})
    return {
        "updated": updated,
        "unchanged": unchanged,
        "skipped": skipped,
        "failed": failed,
        "changes": changes,
    }
