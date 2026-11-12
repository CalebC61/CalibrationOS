"""Decide whether a geocode result is safe to store.

A Google failure, a mock fallback, a partial match, and an approximate pin on
the central-Phoenix default are not stored. An address Google places outside
the valley bounding box is returned so the caller can refuse the save with a
different sentence.
"""
from google_maps import GoogleMapsError

ADDRESS_NOT_FOUND = "We couldn't find that address, please check it"
OUTSIDE_VALLEY = "That address is outside the Phoenix Valley."

# The mock geocoder's default when no city keyword matches.
_CENTRAL_LAT = 33.4484
_CENTRAL_LNG = -112.0740


class AddressNotFound(Exception):
    """The address cannot be placed. The message is safe to show to a shop."""


def near_central_phoenix_guess(lat, lng) -> bool:
    try:
        return abs(float(lat) - _CENTRAL_LAT) < 0.05 and abs(float(lng) - _CENTRAL_LNG) < 0.05
    except (TypeError, ValueError):
        return False


def pin_refusal(geo: dict | None) -> str | None:
    """None when the pin may be saved. A sentence when it must not."""
    if not geo:
        return ADDRESS_NOT_FOUND
    source = geo.get("source")
    if geo.get("guessed") or source in ("fallback", "mock"):
        return ADDRESS_NOT_FOUND
    if geo.get("partial_match"):
        return ADDRESS_NOT_FOUND
    if geo.get("location_type") == "APPROXIMATE" and near_central_phoenix_guess(geo.get("lat"), geo.get("lng")):
        return ADDRESS_NOT_FOUND
    if geo.get("in_metro") is False:
        return OUTSIDE_VALLEY
    return None


def interpret_live_geocode(address: str, fetch, parser) -> dict:
    """Parse one Google response. Raises AddressNotFound when there is no real pin.

    An outside-valley result is returned. `pin_refusal` tells the caller not to
    save it. `fetch` and `parser` are injected so tests do not call Google.
    """
    try:
        geo = dict(parser(fetch(), address))
    except (GoogleMapsError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise AddressNotFound(ADDRESS_NOT_FOUND) from exc
    geo["source"] = "google"
    if pin_refusal(geo) == ADDRESS_NOT_FOUND:
        raise AddressNotFound(ADDRESS_NOT_FOUND)
    return geo


def came_from_fallback(source, lat, lng, mock_lat, mock_lng) -> bool:
    """True when a stored pin is a fallback the owner should correct.

    A pin marked google is trusted. A pin marked fallback is listed even when
    the coordinates no longer match the current mock. Anything else is listed
    only when it still matches the deterministic mock output for that address.
    """
    if source == "google":
        return False
    if source == "fallback":
        return True
    if None in (lat, lng, mock_lat, mock_lng):
        return False
    try:
        return abs(float(lat) - float(mock_lat)) < 1e-5 and abs(float(lng) - float(mock_lng)) < 1e-5
    except (TypeError, ValueError):
        return False
