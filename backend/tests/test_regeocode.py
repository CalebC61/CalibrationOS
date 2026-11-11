"""Owner re-geocode planning. No Mongo, SMS, or Google key:
    cd backend && pytest tests/test_regeocode.py -v
"""
import asyncio
import os
import sys
from datetime import date, datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

from regeocode import (  # noqa: E402
    detect_zone,
    jobs_on_phoenix_day,
    location_set,
    regeocode_records,
    regeocode_scope,
    zone_for_geocode,
)
import server  # noqa: E402
from server import app  # noqa: E402

GILBERT = {"lat": 33.3062, "lng": -111.8413, "formatted_address": "Gilbert, AZ", "in_metro": True}
GOODYEAR = {"lat": 33.4353, "lng": -112.3576, "formatted_address": "Goodyear, AZ", "in_metro": True}
LA = {"lat": 34.0522, "lng": -118.2437, "formatted_address": "Los Angeles, CA", "in_metro": False}


def _geocode_for(table):
    async def geocode(address):
        if address not in table:
            raise RuntimeError(f"geocoder down for {address}")
        return table[address]
    return geocode


def test_zone_cut_matches_the_west_east_split():
    assert detect_zone(-112.0001) == "west"
    assert detect_zone(-112.0) == "east"
    assert detect_zone(-111.8) == "east"
    assert zone_for_geocode(GILBERT) == "east"
    assert zone_for_geocode(GOODYEAR) == "west"
    assert zone_for_geocode(LA) is None


def test_scope_without_a_date_covers_every_shop_and_job():
    assert regeocode_scope(None) == {"shops": True, "jobs": "all", "day": None}
    assert regeocode_scope("  ") == {"shops": True, "jobs": "all", "day": None}


def test_scope_with_a_date_is_jobs_on_that_phoenix_day_only():
    scope = regeocode_scope("2026-10-27")
    assert scope["shops"] is False
    assert scope["jobs"] == "day"
    assert scope["day"] == date(2026, 10, 27)


def test_scope_rejects_a_bad_date():
    with pytest.raises(ValueError):
        regeocode_scope("10/27/2026")


def test_phoenix_day_query_includes_evening_and_excludes_the_neighbors():
    query = jobs_on_phoenix_day(date(2026, 10, 27))
    window = query["scheduled_start"]
    evening = datetime(2026, 10, 28, 1, 0, tzinfo=timezone.utc).isoformat()
    before = datetime(2026, 10, 27, 6, 59, tzinfo=timezone.utc).isoformat()
    assert window["$gte"] <= evening < window["$lt"]
    assert not (window["$gte"] <= before < window["$lt"])


def test_regeocode_updates_coordinates_and_zone_without_status_or_messages():
    shops = [
        {"id": "shop-old", "address": "Gilbert shop", "lat": 33.45, "lng": -112.2,
         "zone": "west", "status": "active"},
        {"id": "shop-same", "address": "Gilbert shop", "lat": 33.3062, "lng": -111.8413,
         "zone": "east", "status": "active"},
        {"id": "shop-blank", "address": "   ", "lat": 1, "lng": 1, "zone": "east", "status": "paused"},
    ]
    jobs = [
        {"id": "job-1", "job_address": "Goodyear job", "job_lat": 33.44, "job_lng": -112.07,
         "zone": "east", "status": "driving"},
        {"id": "job-la", "job_address": "LA job", "job_lat": 33.44, "job_lng": -112.07,
         "zone": "west", "status": "booked"},
        {"id": "job-bad", "job_address": "nowhere", "job_lat": 1, "job_lng": 1,
         "zone": "east", "status": "booked"},
    ]

    async def geocode(address):
        if address == "nowhere":
            raise RuntimeError("geocoder down")
        return {"Gilbert shop": GILBERT, "Goodyear job": GOODYEAR, "LA job": LA}[address]

    shop_result = asyncio.run(regeocode_records(
        shops, geocode, "lat", "lng", "address", zone_for_geocode,
    ))
    job_result = asyncio.run(regeocode_records(
        jobs, geocode, "job_lat", "job_lng", "job_address", zone_for_geocode,
    ))

    assert shop_result["updated"] == 1
    assert shop_result["unchanged"] == 1
    assert shop_result["skipped"] == 1
    assert shop_result["failed"] == 0
    shop_change = shop_result["changes"][0]
    assert shop_change["id"] == "shop-old"
    assert shop_change["set"] == {"lat": 33.3062, "lng": -111.8413, "zone": "east"}
    assert "status" not in shop_change["set"]

    by_id = {c["id"]: c["set"] for c in job_result["changes"]}
    assert by_id["job-1"] == {"job_lat": 33.4353, "job_lng": -112.3576, "zone": "west"}
    # Outside the metro: move the pin, leave the zone alone.
    assert by_id["job-la"] == {"job_lat": 34.0522, "job_lng": -118.2437}
    assert "zone" not in by_id["job-la"]
    assert job_result["failed"] == 1
    assert job_result["updated"] == 2
    for change in job_result["changes"]:
        assert "status" not in change["set"]
        written = location_set(change["set"], "2026-11-11T20:00:00+00:00")
        assert set(written) <= {"job_lat", "job_lng", "lat", "lng", "zone", "updated_at"}
        assert "status" not in written
        assert written["updated_at"] == "2026-11-11T20:00:00+00:00"


def test_location_write_refuses_a_status_change():
    with pytest.raises(ValueError):
        location_set({"lat": 1.0, "status": "cancelled"}, "2026-11-11T20:00:00+00:00")


def test_second_pass_is_unchanged_when_coordinates_already_match():
    records = [{
        "id": "shop-same", "address": "Gilbert shop",
        "lat": 33.3062, "lng": -111.8413, "zone": "east", "status": "active",
    }]

    async def geocode(address):
        return GILBERT

    result = asyncio.run(regeocode_records(
        records, geocode, "lat", "lng", "address", zone_for_geocode,
    ))
    assert result == {
        "updated": 0, "unchanged": 1, "skipped": 0, "failed": 0, "changes": [],
    }


def _iter_routes(routes):
    for route in routes:
        yield route
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from _iter_routes(included.routes)
        children = getattr(route, "routes", None)
        if children:
            yield from _iter_routes(children)


def test_regeocode_does_not_write_a_mock_pin_when_google_fails(monkeypatch):
    monkeypatch.setattr(server, "google_maps_enabled", lambda: True)

    def boom(address):
        raise server.GoogleMapsError("REQUEST_DENIED")

    monkeypatch.setattr(server, "_google_geocode_request", boom)
    with pytest.raises(server.GoogleMapsError):
        asyncio.run(server.geocode_for_regeocode("1234 E Williams Field Rd, Gilbert, AZ"))


def test_regeocode_uses_the_mock_when_google_is_not_configured(monkeypatch):
    monkeypatch.setattr(server, "google_maps_enabled", lambda: False)
    geo = asyncio.run(server.geocode_for_regeocode("Gilbert, AZ"))
    assert geo["in_metro"] is True
    assert geo["lng"] < -111.4


def test_regeocode_route_is_registered():
    matches = [r for r in _iter_routes(app.routes) if getattr(r, "path", None) == "/api/admin/regeocode"]
    assert matches, "POST /api/admin/regeocode is not registered"
    assert "POST" in matches[0].methods
