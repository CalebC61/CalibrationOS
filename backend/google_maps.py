"""Pure, dependency-light helpers for Google Maps geocoding + drive-time.

Kept import-light (stdlib only) so response parsing is unit-testable without booting the
full server / MongoDB / a real Google API key. The real HTTP calls (requests + asyncio.to_thread,
same as the existing Xero/Resend integrations) live in server.py; this module only builds request
params and parses responses, so parsing bugs can't hide behind a live network call in tests.

Drive time uses the Routes API (`computeRoutes`) with `TRAFFIC_AWARE` and a departure
time. The legacy Distance Matrix helpers stay so older responses can still be parsed.
"""
import asyncio
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

# Same Phoenix-metro service-area bounding box the mock geocoder has always used, so a real
# geocode result and the mock agree on which addresses count as "in service area."
METRO_LAT_MIN, METRO_LAT_MAX = 32.9, 33.9
METRO_LNG_MIN, METRO_LNG_MAX = -112.9, -111.4

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
ROUTES_COMPUTE_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
# Top-level route fields only. These are valid on computeRoutes. A mask that
# names a field the method does not return is rejected; do not add tolls,
# polylines, or leg details here unless the call needs them.
ROUTES_FIELD_MASK = "routes.duration,routes.distanceMeters"


class GoogleMapsError(Exception):
    """Raised on a non-OK Google Maps API response; callers fall back to the mock."""


def in_metro(lat: float, lng: float) -> bool:
    return METRO_LAT_MIN < lat < METRO_LAT_MAX and METRO_LNG_MIN < lng < METRO_LNG_MAX


def geocode_request_params(address: str, api_key: str) -> dict:
    """Query params for a Geocoding API GET request.

    `bounds` biases the lookup to the Phoenix Valley. It does not hard-filter
    results; callers still refuse anything outside the metro box. `components`
    keeps the result in the United States.
    """
    bounds = f"{METRO_LAT_MIN},{METRO_LNG_MIN}|{METRO_LAT_MAX},{METRO_LNG_MAX}"
    return {
        "address": address,
        "key": api_key,
        "region": "us",
        "bounds": bounds,
        "components": "country:US",
    }


def distance_matrix_request_params(o_lat, o_lng, d_lat, d_lng, api_key: str) -> dict:
    """Query params for a Distance Matrix API GET request (imperial units, single origin/dest)."""
    return {
        "origins": f"{o_lat},{o_lng}",
        "destinations": f"{d_lat},{d_lng}",
        "units": "imperial",
        "key": api_key,
    }


_UNIT_LABEL = re.compile(
    r"^(?:#\s*\S+|(?:suite|ste|apt|apartment|unit|bldg|building|floor|fl|room|rm)\b.*|\d+[a-z]?)$",
    re.IGNORECASE,
)
_PO_BOX = re.compile(r"^p\.?\s*o\.?\s*box\b", re.IGNORECASE)
_PLACE_NAME_TYPES = {"establishment", "point_of_interest"}
_POSTAL_TYPES = {"street_number", "route", "locality", "postal_town", "postal_code", "subpremise"}


def _component_text(component: dict | None, short: bool = False) -> str:
    if not component:
        return ""
    if short:
        keys = ("short_name", "shortText", "long_name", "longText")
    else:
        keys = ("long_name", "longText", "short_name", "shortText")
    value = next((component.get(key) for key in keys if component.get(key)), "")
    return str(value or "").strip()


def _find_component(components, type_name: str):
    for component in components or []:
        if type_name in (component.get("types") or []):
            return component
    return None


def is_unit_label(value: str) -> bool:
    return bool(_UNIT_LABEL.match((value or "").strip()))


def street_line(address: str) -> str:
    """The postal line. A leading business name is removed. A unit and a PO box stay.

    "Downtown Phoenix, Inc., 1 E Washington St, Phoenix, AZ 85004, USA" becomes
    "1 E Washington St, Phoenix, AZ 85004, USA". "Suite 200, 1 E Washington St, ..."
    stays, because the first segment is a unit. A line that already starts with
    the street number is unchanged.
    """
    parts = [part.strip() for part in str(address or "").split(",") if part.strip()]
    if not parts:
        return ""
    street_at = next((index for index, part in enumerate(parts) if part[:1].isdigit()), None)
    if street_at in (None, 0):
        return ", ".join(parts)
    kept = [
        part for part in parts[:street_at]
        if part[:1].isdigit() or is_unit_label(part) or _PO_BOX.match(part)
    ]
    return ", ".join(kept + parts[street_at:])


def postal_address_from_components(components) -> str:
    """Street, city, state, and ZIP. An establishment or point-of-interest name is not a line."""
    number = _component_text(_find_component(components, "street_number"))
    route = _component_text(_find_component(components, "route"), short=True)
    street = " ".join(part for part in (number, route) if part).strip()
    if not street:
        return ""
    unit = _component_text(_find_component(components, "subpremise"))
    if unit and is_unit_label(unit):
        street = f"{street} {unit}".strip()
    city_component = (
        _find_component(components, "locality")
        or _find_component(components, "postal_town")
        or _find_component(components, "sublocality")
    )
    city = _component_text(city_component)
    state = _component_text(_find_component(components, "administrative_area_level_1"), short=True)
    postal = _component_text(_find_component(components, "postal_code"))
    region = " ".join(part for part in (state, postal) if part)
    city_line = ", ".join(part for part in (city, region) if part)
    country = _component_text(_find_component(components, "country"), short=True)
    if country in ("US", "USA"):
        country = "USA"
    return ", ".join(part for part in (street, city_line, country) if part)


def _has_place_name(components) -> bool:
    for component in components or []:
        types = set(component.get("types") or [])
        if types & _PLACE_NAME_TYPES and not types & _POSTAL_TYPES:
            return True
    return False


def postal_formatted_address(result: dict) -> str:
    """The address to store. Google's formatted line sometimes starts with the business name."""
    formatted = str((result or {}).get("formatted_address") or "").strip()
    components = (result or {}).get("address_components") or []
    stripped = street_line(formatted)
    if _has_place_name(components):
        return postal_address_from_components(components) or stripped or formatted
    if stripped and stripped != formatted:
        return stripped
    return formatted


def address_lookup_queries(address: str) -> list[str]:
    """The typed line, then the street line when a leading business name was removed.

    A plain street is one lookup. Callers try the second query only after the first
    is not a usable pin.
    """
    cleaned = str(address or "").strip()
    if not cleaned:
        return []
    street = street_line(cleaned)
    if street and street.casefold() != cleaned.casefold():
        return [cleaned, street]
    return [cleaned]


def parse_geocode_response(data: dict, original_address: str) -> dict:
    """Parse a Geocoding API response into the app's geocode shape.

    Returns the same shape the mock returns: {lat, lng, formatted_address, in_metro}.
    Raises GoogleMapsError if the API returned no usable result.
    """
    results = data.get("results") or []
    if data.get("status") != "OK" or not results:
        raise GoogleMapsError(f"geocode failed: status={data.get('status')}")
    geometry = results[0].get("geometry") or {}
    location = geometry["location"]
    lat, lng = location["lat"], location["lng"]
    return {
        "lat": round(lat, 6),
        "lng": round(lng, 6),
        "formatted_address": (
            postal_formatted_address(results[0])
            or results[0].get("formatted_address", original_address)
        ),
        "in_metro": in_metro(lat, lng),
        "partial_match": bool(results[0].get("partial_match")),
        "location_type": geometry.get("location_type"),
        "source": "google",
    }


def parse_distance_matrix_response(data: dict) -> dict:
    """Parse a Distance Matrix API response into the app's drive-time shape.

    Returns the same shape the mock returns: {distance_miles, duration_minutes}.
    Raises GoogleMapsError if the API, or the specific origin/destination element, failed.
    """
    if data.get("status") != "OK":
        raise GoogleMapsError(f"distance matrix failed: status={data.get('status')}")
    try:
        element = data["rows"][0]["elements"][0]
    except (KeyError, IndexError):
        raise GoogleMapsError("distance matrix response missing rows/elements")
    if element.get("status") != "OK":
        raise GoogleMapsError(f"distance matrix element failed: status={element.get('status')}")
    meters = element["distance"]["value"]
    seconds = element["duration"]["value"]
    return {
        "distance_miles": round(meters / 1609.344, 1),
        "duration_minutes": max(1, round(seconds / 60)),
    }


def departure_bucket(moment: datetime) -> str:
    """UTC instant floored to 15 minutes. Legs that leave in the same quarter-hour share a cache entry."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc).replace(second=0, microsecond=0)
    return moment.replace(minute=(moment.minute // 15) * 15).strftime("%Y-%m-%dT%H:%MZ")


def drive_time_cache_key(o_lat, o_lng, d_lat, d_lng, day_iso: str, departure_bucket: str | None = None) -> str:
    """Cache key for a drive between two points, rounded to ~11m precision.

    Coordinates are rounded so nearby-but-not-identical floats (e.g. re-geocoding the same
    address) still hit the cache. The Phoenix day is always part of the key. A departure
    bucket (15-minute UTC floor) keeps a rush-hour leg from reusing a midday one.
    """
    base = (f"{round(float(o_lat), 4)},{round(float(o_lng), 4)}|"
            f"{round(float(d_lat), 4)},{round(float(d_lng), 4)}|{day_iso}")
    if departure_bucket:
        return f"{base}|{departure_bucket}"
    return base


def routes_request_headers(api_key: str) -> dict:
    """Headers for computeRoutes. The key is a header, not a query parameter, so it stays out of the URL."""
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": ROUTES_FIELD_MASK,
    }


def redact_maps_secret(text: str, api_key: str) -> str:
    """Remove the API key from a log line. The response body itself is kept."""
    if not text:
        return ""
    if api_key:
        text = text.replace(api_key, "[redacted]")
    return text


def routes_http_failure(status_code: int, body: str, api_key: str = "") -> str:
    """One log line for a non-2xx computeRoutes response. Includes the body, never the key."""
    detail = redact_maps_secret(body or "", api_key).strip()
    if len(detail) > 2000:
        detail = detail[:2000]
    if not detail:
        return f"HTTP {status_code} with an empty body"
    return f"HTTP {status_code}: {detail}"


def routes_request_body(o_lat, o_lng, d_lat, d_lng, departure_iso: str | None = None,
                        routing_preference: str = "TRAFFIC_AWARE") -> dict:
    """JSON body for Routes API computeRoutes.

    `TRAFFIC_AWARE` bills as Compute Routes Pro and may include departureTime.
    `TRAFFIC_UNAWARE` bills as Compute Routes Essentials and must not include
    departureTime: Google returns 400 "Timestamp cannot be set for TRAFFIC_UNAWARE".
    """
    body = {
        "origin": {"location": {"latLng": {"latitude": float(o_lat), "longitude": float(o_lng)}}},
        "destination": {"location": {"latLng": {"latitude": float(d_lat), "longitude": float(d_lng)}}},
        "travelMode": "DRIVE",
        "routingPreference": routing_preference,
    }
    if routing_preference != "TRAFFIC_UNAWARE" and departure_iso:
        body["departureTime"] = departure_iso
    return body


def _duration_seconds(value) -> float:
    text = str(value or "")
    if not text.endswith("s"):
        raise GoogleMapsError(f"routes duration missing: {value!r}")
    try:
        return float(text[:-1])
    except ValueError as exc:
        raise GoogleMapsError(f"routes duration unreadable: {value!r}") from exc


def parse_routes_response(data: dict) -> dict:
    """Parse a computeRoutes response into {distance_miles, duration_minutes}.

    `duration` is the traffic-aware time when routingPreference was TRAFFIC_AWARE.
    Raises GoogleMapsError when Google returned an error object or no route.
    """
    if data.get("error"):
        message = (data.get("error") or {}).get("message") or data.get("error")
        raise GoogleMapsError(f"routes failed: {message}")
    routes = data.get("routes") or []
    if not routes:
        raise GoogleMapsError("routes API returned no route")
    route = routes[0]
    seconds = _duration_seconds(route.get("duration"))
    meters = route.get("distanceMeters") or 0
    return {
        "distance_miles": round(float(meters) / 1609.344, 1),
        "duration_minutes": max(1, round(seconds / 60)),
    }


async def coalesce(pending: dict, key: str, factory: Callable[[], Awaitable]):
    """Run factory once per key. Concurrent callers await that same task.

    `pending` is owned by the caller. The key is removed when the task finishes
    so a later call can run again (the Mongo cache, not this dict, holds the result).
    Check-and-set happens before the first await, so asyncio callers cannot both miss.
    """
    task = pending.get(key)
    if task is None:
        task = asyncio.create_task(factory())
        pending[key] = task
    try:
        return await task
    finally:
        if pending.get(key) is task and task.done():
            pending.pop(key, None)
