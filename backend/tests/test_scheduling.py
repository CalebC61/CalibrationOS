"""One route per technician: drive time, buffer, and no double-booking.

Surprise and San Tan Valley are on opposite sides of the Phoenix Valley.
Injected drives match the smart-scheduling plan (Gilbert home):
home→Surprise 89, home→San Tan 34, San Tan↔Surprise 117.
Duration 20, buffer 15, grid 15. 8:00 AM Phoenix is 15:00 UTC.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scheduling import candidate_slots, placement_error  # noqa: E402

HOME = (33.3528, -111.7890)       # Gilbert
SURPRISE = (33.6292, -112.3679)
SANTAN = (33.1962, -111.6463)
DAY = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)   # 8:00 AM Phoenix
OFFER_END = datetime(2026, 11, 13, 0, 0, tzinfo=timezone.utc)  # 5:00 PM Phoenix
DRIVES = {
    (HOME, SURPRISE): 89,
    (HOME, SANTAN): 34,
    (SURPRISE, SANTAN): 117,
    (SANTAN, SURPRISE): 117,
    (SURPRISE, HOME): 89,
    (SANTAN, HOME): 34,
}


def drive(a, b):
    return DRIVES[(a, b)]


def at(hour_phoenix):
    """hour_phoenix is minutes after 8:00 AM, or a 'H:MM' 24h Phoenix clock."""
    if isinstance(hour_phoenix, str):
        hh, mm = hour_phoenix.split(":")
        minutes = (int(hh) - 8) * 60 + int(mm)
    else:
        minutes = hour_phoenix
    return DAY + timedelta(minutes=minutes)


def job(start, point, duration=20, job_id="j"):
    return {
        "id": job_id,
        "scheduled_start": start.isoformat(),
        "scheduled_end": (start + timedelta(minutes=duration)).isoformat(),
        "duration_minutes": duration,
        "job_lat": point[0],
        "job_lng": point[1],
        "status": "booked",
    }


def test_empty_day_surprise_is_not_offered_at_8am():
    slots = candidate_slots(
        day_start=DAY, offer_end=OFFER_END, home=HOME, jobs=[],
        new_point=SURPRISE, drive=drive, duration=20, buffer=15,
    )
    starts = [slot["start"] for slot in slots]
    assert at("8:00").isoformat() not in starts
    assert at("9:30").isoformat() in starts


def test_surprise_at_8am_blocks_san_tan_at_8am():
    surprise = job(at("8:00"), SURPRISE, job_id="surprise")
    error = placement_error(
        start=at("8:00"), duration=20, buffer=15,
        day_start=DAY, offer_end=OFFER_END, home=HOME,
        jobs=[surprise], new_point=SANTAN, drive=drive,
    )
    assert error
    assert "route" in error.lower() or "overlap" in error.lower()


def test_cross_valley_back_to_back_fits_only_after_the_drive():
    # San Tan ETA 8:45. Leave 9:20. Surprise is 117 minutes away → 11:17, grid 11:30.
    santan = job(at("8:45"), SANTAN, job_id="santan")
    too_soon = placement_error(
        start=at("10:00"), duration=20, buffer=15,
        day_start=DAY, offer_end=OFFER_END, home=HOME,
        jobs=[santan], new_point=SURPRISE, drive=drive,
    )
    assert too_soon
    fits = placement_error(
        start=at("11:30"), duration=20, buffer=15,
        day_start=DAY, offer_end=OFFER_END, home=HOME,
        jobs=[santan], new_point=SURPRISE, drive=drive,
    )
    assert fits is None
    slots = candidate_slots(
        day_start=DAY, offer_end=OFFER_END, home=HOME, jobs=[santan],
        new_point=SURPRISE, drive=drive, duration=20, buffer=15,
    )
    starts = [slot["start"] for slot in slots]
    assert at("8:00").isoformat() not in starts
    assert at("11:30").isoformat() in starts


def test_overlapping_clock_times_are_rejected_even_with_no_drive():
    def zero(a, b):
        return 0
    first = job(at("9:00"), SANTAN, job_id="a")
    error = placement_error(
        start=at("9:10"), duration=20, buffer=15,
        day_start=DAY, offer_end=OFFER_END, home=HOME,
        jobs=[first], new_point=SANTAN, drive=zero,
    )
    assert error
    assert "overlap" in error.lower()


def test_insert_between_jobs_when_both_drives_fit():
    morning = job(at("8:45"), SANTAN, job_id="santan")
    afternoon = job(at("15:00"), SANTAN, job_id="later")
    # A second nearby stop between them is fine. A Surprise squeezed at 9:00 is not.
    near = (33.20, -111.65)
    def local_drive(a, b):
        if a == HOME and b == SURPRISE:
            return 89
        if SURPRISE in (a, b) and SANTAN in (a, b):
            return 117
        return 10
    assert placement_error(
        start=at("10:30"), duration=20, buffer=15,
        day_start=DAY, offer_end=OFFER_END, home=HOME,
        jobs=[morning, afternoon], new_point=near, drive=local_drive,
    ) is None
    assert placement_error(
        start=at("9:00"), duration=20, buffer=15,
        day_start=DAY, offer_end=OFFER_END, home=HOME,
        jobs=[morning, afternoon], new_point=SURPRISE, drive=local_drive,
    )
