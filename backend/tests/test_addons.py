"""Today's route is stricter than a booking for a later date.

The Goodyear case: the last stop is EAG in Mesa (East Valley). A shop asks
for Goodyear the same day. The drive out and back is about two hours
(75 + 45). Straight home from EAG is 20 minutes, so the extra drive is 100.
That is not auto-accepted.

    cd backend && pytest tests/test_addons.py -v
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from addons import (  # noqa: E402
    policy_from_tech, request_kind, same_day_closed_message, slot_decision,
)
from business_time import zone_window  # noqa: E402
from datetime import time
from scheduling import insertion_cost  # noqa: E402

HOME = (33.3528, -111.7890)          # Gilbert
EAG = (33.4372, -111.8210)           # 855 E Brown Rd, Mesa
GOODYEAR = (33.4353, -112.3576)      # west valley
NEAR = (33.36, -111.80)              # a few minutes from home
DAY = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)  # 8:00 AM Phoenix


def _drive(table):
    def drive(origin, dest, depart=None):
        if origin == dest:
            return 0
        return table[(origin, dest)]
    return drive


GOODYEAR_DRIVE = _drive({
    (HOME, EAG): 20,
    (EAG, HOME): 20,
    (EAG, GOODYEAR): 75,
    (GOODYEAR, EAG): 75,
    (GOODYEAR, HOME): 45,
    (HOME, GOODYEAR): 50,
    (NEAR, HOME): 8,
    (HOME, NEAR): 8,
    (EAG, NEAR): 15,
    (NEAR, EAG): 15,
    (NEAR, GOODYEAR): 40,
    (GOODYEAR, NEAR): 40,
})


def _at(hhmm):
    hour, minute = hhmm.split(":")
    return DAY + timedelta(minutes=(int(hour) - 8) * 60 + int(minute))


def _job(start, point, job_id="eag"):
    return {
        "id": job_id,
        "scheduled_start": start.isoformat(),
        "scheduled_end": (start + timedelta(minutes=20)).isoformat(),
        "duration_minutes": 20,
        "job_lat": point[0],
        "job_lng": point[1],
        "status": "booked",
    }


def test_a_future_date_is_advance_including_the_night_before():
    # 11:00 PM Phoenix on Nov 11 is 06:00 UTC Nov 12. The appointment is Nov 12.
    night_before = datetime(2026, 11, 12, 6, 0, tzinfo=timezone.utc)
    assert request_kind(datetime(2026, 11, 12).date(), night_before) == "advance"
    ten_am = datetime(2026, 11, 12, 17, 0, tzinfo=timezone.utc)
    assert request_kind(datetime(2026, 11, 12).date(), ten_am) == "same_day"
    assert request_kind(datetime(2026, 11, 13).date(), ten_am) == "advance"


def test_goodyear_after_east_valley_is_not_auto_accepted():
    """Last job EAG. Goodyear adds about two hours out and back, 100 minutes extra."""
    eag = _job(_at("9:00"), EAG)
    # Leave EAG 9:35. 75 minutes to Goodyear lands at 10:50, so 11:00 is the slot.
    cost = insertion_cost(
        start=_at("11:00"), duration=20, buffer=15,
        home=HOME, home_ready=_at("8:00"), jobs=[eag],
        new_point=GOODYEAR, drive=GOODYEAR_DRIVE,
    )
    assert cost["extra_drive_minutes"] == 100
    assert cost["to_stop_minutes"] + 45 == 120  # out and back, about two hours
    assert cost["later_finish_minutes"] > 45
    policy = policy_from_tech({})
    decision = slot_decision(
        band="standard", kind="same_day", had_route=True,
        extra=cost["extra_drive_minutes"], later=cost["later_finish_minutes"],
        policy=policy, allow_outside=False,
    )
    assert decision["status"] == "requested"
    assert decision["requires_approval"] is True
    hidden = slot_decision(
        band="standard", kind="same_day", had_route=True,
        extra=cost["extra_drive_minutes"], later=cost["later_finish_minutes"],
        policy=policy_from_tech({"same_day_over_limit": "hide"}), allow_outside=False,
    )
    assert hidden is None


def test_a_stop_near_home_can_be_auto_accepted():
    # On the way home: 5 minutes out, 6 back, 8 direct. Extra drive is 3.
    # 20-minute job + 15-minute buffer + 3 minutes of drive = 38 minutes later.
    near_drive = _drive({
        (HOME, NEAR): 5,
        (NEAR, HOME): 6,
        (EAG, HOME): 8,
        (EAG, NEAR): 5,
        (NEAR, EAG): 5,
        (HOME, EAG): 8,
    })
    eag = _job(_at("10:00"), EAG, job_id="last")
    # Leave 10:35. 5 minutes away. Slot 10:45 is a 5-minute wait past 10:40.
    # Use 10:40 exactly so there is no extra wait: leave 10:35 + 5 = 10:40.
    cost = insertion_cost(
        start=_at("10:40"), duration=20, buffer=15,
        home=HOME, home_ready=_at("8:00"), jobs=[eag],
        new_point=NEAR, drive=near_drive,
    )
    assert cost["extra_drive_minutes"] == 3
    assert cost["later_finish_minutes"] <= 45
    decision = slot_decision(
        band="standard", kind="same_day", had_route=True,
        extra=cost["extra_drive_minutes"], later=cost["later_finish_minutes"],
        policy=policy_from_tech({}), allow_outside=False,
    )
    assert decision["status"] == "booked"
    assert decision["requires_approval"] is False


def test_an_empty_day_does_not_use_the_detour_limit():
    decision = slot_decision(
        band="standard", kind="same_day", had_route=False,
        extra=90, later=120, policy=policy_from_tech({}), allow_outside=False,
    )
    assert decision["status"] == "booked"


def test_before_8_on_a_future_day_needs_approval():
    decision = slot_decision(
        band="early", kind="advance", had_route=False,
        extra=0, later=0, policy=policy_from_tech({}), allow_outside=False,
    )
    assert decision["status"] == "requested"
    assert decision["approval_reason"] == "early_arrival"


def test_cutoff_and_the_off_switch_close_today():
    ten_am = datetime(2026, 11, 12, 17, 0, tzinfo=timezone.utc)
    one_thirty = datetime(2026, 11, 12, 20, 30, tzinfo=timezone.utc)
    assert same_day_closed_message(ten_am, policy_from_tech({})) is None
    closed = same_day_closed_message(one_thirty, policy_from_tech({}))
    assert closed
    assert "1:00 PM" in closed
    assert "add-on" not in closed.lower()
    off = same_day_closed_message(ten_am, policy_from_tech({"same_day_bookings_enabled": False}))
    assert off
    assert "turned off" in off.lower()


def test_defaults_match_the_owner_limits():
    policy = policy_from_tech(None)
    assert policy["enabled"] is True
    assert policy["cutoff"] == "13:00"
    assert policy["max_extra_drive_minutes"] == 20
    assert policy["max_later_finish_minutes"] == 45
    assert policy["over_limit"] == "pending"
    # zone_window is imported so a reader can see 11:00 Phoenix is 18:00 UTC.
    start, _end = zone_window(DAY.date(), time(11, 0), time(17, 0))
    assert start == _at("11:00")
