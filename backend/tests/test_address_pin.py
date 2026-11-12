"""A shop or job is not saved when the map pin would be a guess.

    cd backend && pytest tests/test_address_pin.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from address_pin import (  # noqa: E402
    ADDRESS_NOT_FOUND,
    OUTSIDE_VALLEY,
    AddressNotFound,
    came_from_fallback,
    interpret_live_geocode,
    pin_refusal,
)
from google_maps import (  # noqa: E402
    METRO_LAT_MAX,
    METRO_LAT_MIN,
    METRO_LNG_MAX,
    METRO_LNG_MIN,
    GoogleMapsError,
    geocode_request_params,
    parse_geocode_response,
)

GILBERT = {
    "status": "OK",
    "results": [{
        "formatted_address": "1234 E Williams Field Rd, Gilbert, AZ 85295, USA",
        "geometry": {
            "location": {"lat": 33.3062, "lng": -111.7890},
            "location_type": "ROOFTOP",
        },
        "partial_match": False,
    }],
}


def test_geocode_lookup_is_biased_to_the_phoenix_valley():
    params = geocode_request_params("1234 E Williams Field Rd, Gilbert, AZ", "test-key")
    assert params["address"] == "1234 E Williams Field Rd, Gilbert, AZ"
    assert params["key"] == "test-key"
    assert params["region"] == "us"
    assert params["components"] == "country:US"
    south, west, north, east = (
        params["bounds"].split("|")[0].split(",") + params["bounds"].split("|")[1].split(",")
    )
    assert (float(south), float(north)) == (METRO_LAT_MIN, METRO_LAT_MAX)
    assert (float(west), float(east)) == (METRO_LNG_MIN, METRO_LNG_MAX)


def test_a_google_failure_does_not_return_a_coordinate():
    def fetch():
        raise GoogleMapsError("ZERO_RESULTS")

    with pytest.raises(AddressNotFound) as exc:
        interpret_live_geocode("1 Nowhere", fetch, parse_geocode_response)
    assert str(exc.value) == ADDRESS_NOT_FOUND


def test_a_central_phoenix_guess_is_refused():
    guessed = {
        "lat": 33.4484,
        "lng": -112.0740,
        "formatted_address": "Phoenix, AZ, USA",
        "in_metro": True,
        "source": "google",
        "partial_match": False,
        "location_type": "APPROXIMATE",
    }
    assert pin_refusal(guessed) == ADDRESS_NOT_FOUND


def test_a_fallback_or_mock_pin_is_refused_even_inside_the_valley():
    pin = {
        "lat": 33.3528,
        "lng": -111.7890,
        "formatted_address": "Gilbert, AZ",
        "in_metro": True,
        "source": "fallback",
        "guessed": True,
    }
    assert pin_refusal(pin) == ADDRESS_NOT_FOUND
    pin["source"] = "mock"
    assert pin_refusal(pin) == ADDRESS_NOT_FOUND


def test_a_partial_google_match_is_refused():
    data = {
        "status": "OK",
        "results": [{
            "formatted_address": "Phoenix, AZ, USA",
            "partial_match": True,
            "geometry": {
                "location": {"lat": 33.3062, "lng": -111.7890},
                "location_type": "ROOFTOP",
            },
        }],
    }
    with pytest.raises(AddressNotFound) as exc:
        interpret_live_geocode("not a real street", lambda: data, parse_geocode_response)
    assert str(exc.value) == ADDRESS_NOT_FOUND


def test_an_address_outside_the_valley_is_refused_with_the_valley_message():
    data = {
        "status": "OK",
        "results": [{
            "formatted_address": "Los Angeles, CA, USA",
            "geometry": {
                "location": {"lat": 34.0522, "lng": -118.2437},
                "location_type": "ROOFTOP",
            },
        }],
    }
    geo = interpret_live_geocode("Los Angeles, CA", lambda: data, parse_geocode_response)
    assert pin_refusal(geo) == OUTSIDE_VALLEY


def test_a_real_valley_rooftop_can_be_saved():
    geo = interpret_live_geocode("1234 E Williams Field Rd, Gilbert, AZ", lambda: GILBERT, parse_geocode_response)
    assert pin_refusal(geo) is None
    assert geo["source"] == "google"
    assert geo["lat"] == 33.3062
    assert geo["in_metro"] is True


def test_existing_fallback_coordinates_are_listed_and_google_pins_are_not():
    assert came_from_fallback("fallback", 33.3, -111.8, 33.9, -112.2) is True
    assert came_from_fallback(None, 33.352826, -111.789012, 33.352826, -111.789012) is True
    assert came_from_fallback("google", 33.352826, -111.789012, 33.352826, -111.789012) is False
    assert came_from_fallback(None, 33.3062, -111.8413, 33.3528, -111.7890) is False
