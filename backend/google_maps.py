"""Pure, dependency-light helpers for Google Maps geocoding + drive-time.

Kept import-light (stdlib only) so response parsing is unit-testable without booting the
full server / MongoDB / a real Google API key. The real HTTP calls (requests + asyncio.to_thread,
same as the existing Xero/Resend integrations) live in server.py; this module only builds request
params and parses responses, so parsing bugs can't hide behind a live network call in tests.
"""

# Same Phoenix-metro service-area bounding box the mock geocoder has always used, so a real
# geocode result and the mock agree on which addresses count as "in service area."
METRO_LAT_MIN, METRO_LAT_MAX = 32.9, 33.9
METRO_LNG_MIN, METRO_LNG_MAX = -112.9, -111.4

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


class GoogleMapsError(Exception):
    """Raised on a non-OK Google Maps API response; callers fall back to the mock."""


def in_metro(lat: float, lng: float) -> bool:
    return METRO_LAT_MIN < lat < METRO_LAT_MAX and METRO_LNG_MIN < lng < METRO_LNG_MAX


def geocode_request_params(address: str, api_key: str) -> dict:
    """Query params for a Geocoding API GET request."""
    return {"address": address, "key": api_key}


def distance_matrix_request_params(o_lat, o_lng, d_lat, d_lng, api_key: str) -> dict:
    """Query params for a Distance Matrix API GET request (imperial units, single origin/dest)."""
    return {
        "origins": f"{o_lat},{o_lng}",
        "destinations": f"{d_lat},{d_lng}",
        "units": "imperial",
        "key": api_key,
    }


def parse_geocode_response(data: dict, original_address: str) -> dict:
    """Parse a Geocoding API response into the app's geocode shape.

    Returns the same shape the mock returns: {lat, lng, formatted_address, in_metro}.
    Raises GoogleMapsError if the API returned no usable result.
    """
    results = data.get("results") or []
    if data.get("status") != "OK" or not results:
        raise GoogleMapsError(f"geocode failed: status={data.get('status')}")
    location = results[0]["geometry"]["location"]
    lat, lng = location["lat"], location["lng"]
    return {
        "lat": round(lat, 6),
        "lng": round(lng, 6),
        "formatted_address": results[0].get("formatted_address", original_address),
        "in_metro": in_metro(lat, lng),
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


def drive_time_cache_key(o_lat, o_lng, d_lat, d_lng, day_iso: str) -> str:
    """Cache key for a day's drive time between two points, rounded to ~11m precision.

    Coordinates are rounded so nearby-but-not-identical floats (e.g. re-geocoding the same
    address) still hit the cache. Keying on the calendar day matches the "daily caching" the
    project's own roadmap called for — bounds real API spend without a separate TTL sweep needed
    to keep results fresh. Callers pass an America/Phoenix date (`business_date()`), not the UTC date.
    """
    return (f"{round(o_lat, 4)},{round(o_lng, 4)}|"
            f"{round(d_lat, 4)},{round(d_lng, 4)}|{day_iso}")
