"""Unit tests for the Google Maps geocode/distance-matrix response parsing + cache keying.

These are pure (stdlib only) and run anywhere — no server, MongoDB, or Google API key needed:
    cd backend && pytest tests/test_google_maps.py -v
"""
import asyncio
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/
from google_maps import (  # noqa: E402
    GoogleMapsError, in_metro, parse_geocode_response, parse_distance_matrix_response,
    geocode_request_params, distance_matrix_request_params, drive_time_cache_key, coalesce,
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


def test_coalesce_runs_one_factory_for_concurrent_same_key():
    async def scenario():
        pending = {}
        calls = 0

        async def factory():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return {"duration_minutes": 12}

        results = await asyncio.gather(*(coalesce(pending, "same", factory) for _ in range(5)))
        assert results == [{"duration_minutes": 12}] * 5
        assert calls == 1
        assert pending == {}
        # A later call is not stuck on the finished task.
        await coalesce(pending, "same", factory)
        assert calls == 2

    asyncio.run(scenario())


def test_coalesce_shares_a_rounded_drive_time_key_and_isolates_others():
    async def scenario():
        # Same origin, destinations that round to one cache key, plus a different pin.
        day = "2026-10-27"
        shared = drive_time_cache_key(33.4484, -112.0740, 33.30621, -111.78901, day)
        also_shared = drive_time_cache_key(33.4484, -112.0740, 33.30619, -111.78899, day)
        other = drive_time_cache_key(33.4484, -112.0740, 33.4500, -112.0200, day)
        assert shared == also_shared
        assert shared != other

        pending = {}
        calls = []

        def make(name):
            async def factory():
                calls.append(name)
                await asyncio.sleep(0)
                return name
            return factory

        results = await asyncio.gather(
            coalesce(pending, shared, make("a")),
            coalesce(pending, also_shared, make("b")),
            coalesce(pending, other, make("c")),
        )
        assert results[0] == results[1]
        assert sorted(calls) == ["a", "c"] or sorted(calls) == ["b", "c"]
        assert len(calls) == 2
        assert pending == {}

    asyncio.run(scenario())


def test_coalesce_clears_the_key_after_a_failure():
    async def scenario():
        pending = {}

        async def boom():
            raise RuntimeError("maps down")

        with pytest.raises(RuntimeError):
            await coalesce(pending, "k", boom)
        assert pending == {}

        async def ok():
            return "recovered"

        assert await coalesce(pending, "k", ok) == "recovered"

    asyncio.run(scenario())
