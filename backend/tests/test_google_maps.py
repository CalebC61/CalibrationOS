"""Unit tests for the Google Maps geocode/distance-matrix response parsing + cache keying.

These are pure (stdlib only) and run anywhere — no server, MongoDB, or Google API key needed:
    cd backend && pytest tests/test_google_maps.py -v
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/
from google_maps import (  # noqa: E402
    GoogleMapsError, in_metro, parse_geocode_response, parse_distance_matrix_response,
    geocode_request_params, distance_matrix_request_params, drive_time_cache_key,
)

GEOCODE_OK = {
    "status": "OK",
    "results": [{
        "formatted_address": "1234 E Williams Field Rd, Gilbert, AZ 85295, USA",
        "geometry": {"location": {"lat": 33.3062, "lng": -111.7890}},
    }],
}

DISTANCE_OK = {
    "status": "OK",
    "rows": [{"elements": [{
        "status": "OK",
        "distance": {"value": 24140, "text": "15.0 mi"},   # meters
        "duration": {"value": 1260, "text": "21 mins"},    # seconds
    }]}],
}


def test_geocode_parses_lat_lng_and_formatted_address():
    geo = parse_geocode_response(GEOCODE_OK, "1234 E Williams Field Rd, Gilbert, AZ")
    assert geo["lat"] == 33.3062
    assert geo["lng"] == -111.789
    assert geo["formatted_address"] == "1234 E Williams Field Rd, Gilbert, AZ 85295, USA"


def test_geocode_in_metro_true_for_phoenix_area_address():
    geo = parse_geocode_response(GEOCODE_OK, "Gilbert, AZ")
    assert geo["in_metro"] is True


def test_geocode_in_metro_false_outside_bounding_box():
    data = {"status": "OK", "results": [{
        "formatted_address": "Los Angeles, CA, USA",
        "geometry": {"location": {"lat": 34.0522, "lng": -118.2437}},
    }]}
    geo = parse_geocode_response(data, "Los Angeles, CA")
    assert geo["in_metro"] is False


def test_geocode_zero_results_raises():
    with pytest.raises(GoogleMapsError):
        parse_geocode_response({"status": "ZERO_RESULTS", "results": []}, "gibberish address")


def test_geocode_request_denied_raises():
    with pytest.raises(GoogleMapsError):
        parse_geocode_response({"status": "REQUEST_DENIED", "results": []}, "123 Main St")


def test_distance_matrix_converts_meters_to_miles_and_seconds_to_minutes():
    dm = parse_distance_matrix_response(DISTANCE_OK)
    assert dm["distance_miles"] == 15.0
    assert dm["duration_minutes"] == 21


def test_distance_matrix_non_ok_top_level_status_raises():
    with pytest.raises(GoogleMapsError):
        parse_distance_matrix_response({"status": "OVER_QUERY_LIMIT", "rows": []})


def test_distance_matrix_element_not_found_raises():
    data = {"status": "OK", "rows": [{"elements": [{
        "status": "NOT_FOUND", "distance": {}, "duration": {},
    }]}]}
    with pytest.raises(GoogleMapsError):
        parse_distance_matrix_response(data)


def test_distance_matrix_missing_rows_raises():
    with pytest.raises(GoogleMapsError):
        parse_distance_matrix_response({"status": "OK", "rows": []})


def test_distance_matrix_never_returns_zero_minutes():
    data = {"status": "OK", "rows": [{"elements": [{
        "status": "OK", "distance": {"value": 50}, "duration": {"value": 10},
    }]}]}
    dm = parse_distance_matrix_response(data)
    assert dm["duration_minutes"] >= 1


def test_geocode_request_params_include_address_and_key():
    params = geocode_request_params("1234 Main St, Phoenix, AZ", "test-key")
    assert params == {"address": "1234 Main St, Phoenix, AZ", "key": "test-key"}


def test_distance_matrix_request_params_format_lat_lng_pairs():
    params = distance_matrix_request_params(33.1, -111.9, 33.4, -112.0, "test-key")
    assert params["origins"] == "33.1,-111.9"
    assert params["destinations"] == "33.4,-112.0"
    assert params["units"] == "imperial"
    assert params["key"] == "test-key"


def test_in_metro_boundary_helper_matches_bounding_box():
    assert in_metro(33.45, -112.07) is True   # central Phoenix
    assert in_metro(34.05, -118.24) is False  # Los Angeles


def test_cache_key_rounds_coordinates_and_includes_day():
    key_a = drive_time_cache_key(33.30621, -111.78901, 33.45, -112.02, "2026-07-21")
    key_b = drive_time_cache_key(33.30619, -111.78899, 33.45, -112.02, "2026-07-21")
    assert key_a == key_b  # sub-11m float noise collapses to the same cache entry


def test_cache_key_changes_on_new_day():
    key_day1 = drive_time_cache_key(33.3062, -111.789, 33.45, -112.02, "2026-07-21")
    key_day2 = drive_time_cache_key(33.3062, -111.789, 33.45, -112.02, "2026-07-22")
    assert key_day1 != key_day2
