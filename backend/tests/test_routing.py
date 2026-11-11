"""One technician covers the valley. Extra technicians split by home base.

    cd backend && pytest tests/test_routing.py -v
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routing import (  # noqa: E402
    assign_technician,
    availability_windows,
    contractor_routing_updates,
    owner_routing_updates,
    tech_schedule,
)

GILBERT = {"home_lat": 33.3528, "home_lng": -111.7890}
PEORIA = {"home_lat": 33.5806, "home_lng": -112.2374}
SOUTH_MOUNTAIN = {"home_lat": 33.3700, "home_lng": -112.0800}
GOODYEAR = (33.4353, -112.3576)
MESA = (33.4152, -111.8315)
LAVEEN = (33.3600, -112.1500)


def _tech(tech_id, home, **extra):
    return {
        "id": tech_id,
        "role": "technician",
        "is_active": True,
        "routes_jobs": True,
        **home,
        **extra,
    }


def test_one_tech_covers_goodyear_and_mesa():
    caleb = _tech("caleb", GILBERT, role="owner", name="Caleb")
    assert assign_technician([caleb], *GOODYEAR)["id"] == "caleb"
    assert assign_technician([caleb], *MESA)["id"] == "caleb"


def test_contractor_does_not_split_the_valley():
    caleb = _tech("caleb", GILBERT, role="owner")
    west = _tech("west", PEORIA, role="contractor", routes_jobs=False)
    assert assign_technician([caleb, west], *GOODYEAR)["id"] == "caleb"


def test_two_techs_follow_the_nearer_home():
    peoria = _tech("peoria", PEORIA, name="Peoria")
    gilbert = _tech("gilbert", GILBERT, role="owner", name="Caleb")
    assert assign_technician([peoria, gilbert], *GOODYEAR)["id"] == "peoria"
    assert assign_technician([peoria, gilbert], *MESA)["id"] == "gilbert"


def test_service_radius_beats_a_nearer_home_outside_that_radius():
    peoria = _tech("peoria", PEORIA, service_radius_miles=15)
    south = _tech("south", SOUTH_MOUNTAIN, service_radius_miles=12)
    # Laveen is inside the South Mountain radius and outside Peoria's.
    assert assign_technician([peoria, south], *LAVEEN)["id"] == "south"


def test_no_radius_falls_back_to_the_nearest_home():
    peoria = _tech("peoria", PEORIA, service_radius_miles=5)
    gilbert = _tech("gilbert", GILBERT, service_radius_miles=5)
    # Goodyear is outside both small radii, and closer to Peoria.
    assert assign_technician([peoria, gilbert], *GOODYEAR)["id"] == "peoria"


def test_inactive_tech_is_skipped():
    caleb = _tech("caleb", GILBERT, role="owner")
    gone = _tech("gone", PEORIA, is_active=False)
    assert assign_technician([caleb, gone], *GOODYEAR)["id"] == "caleb"


def test_schedule_is_the_full_day_not_a_half_valley_window():
    schedule = tech_schedule({})
    assert schedule["day_start"] == "08:00"
    assert schedule["day_end"] == "19:00"
    assert schedule["max_jobs"] >= 14


def test_afternoon_job_does_not_hide_the_morning():
    day_start = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)  # 08:00 Phoenix
    day_end = datetime(2026, 11, 13, 2, 0, tzinfo=timezone.utc)  # 19:00 Phoenix
    afternoon = {
        "scheduled_start": "2026-11-12T22:00:00+00:00",  # 15:00 Phoenix
        "scheduled_end": "2026-11-12T22:45:00+00:00",
        "job_lat": 33.4,
        "job_lng": -111.8,
    }
    windows = availability_windows(day_start, day_end, [afternoon])
    assert windows[0]["origin"] == "home"
    assert windows[0]["end"].isoformat().startswith("2026-11-12T22:00:00")
    assert windows[1]["origin"] == "job"
    assert windows[1]["start"].isoformat().startswith("2026-11-12T22:45:00")


def test_owner_home_is_not_overwritten_once_set():
    updates = owner_routing_updates({
        "role": "owner",
        "home_address": "123 Custom Rd, Chandler, AZ",
        "home_lat": 33.30,
        "home_lng": -111.84,
        "routes_jobs": True,
        "color": "#FF5F1F",
        "day_start": "08:00",
        "day_end": "19:00",
        "slot_minutes": 45,
        "max_jobs": 14,
    })
    assert "home_address" not in updates
    assert "home_lat" not in updates


def test_owner_missing_home_defaults_to_gilbert_and_routes_jobs():
    updates = owner_routing_updates({"role": "owner"})
    assert updates["home_address"] == "Gilbert, AZ"
    assert updates["home_lat"] == 33.3528
    assert updates["routes_jobs"] is True
    assert updates["day_start"] == "08:00"
    assert updates["day_end"] == "19:00"


def test_existing_contractor_does_not_start_routing():
    assert contractor_routing_updates({"role": "contractor"}) == {"routes_jobs": False}
    assert contractor_routing_updates({"role": "contractor", "routes_jobs": False}) == {}
