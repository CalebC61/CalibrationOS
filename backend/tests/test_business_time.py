"""Phoenix business-day boundaries.

Pure (stdlib + zoneinfo). No server, MongoDB, or API key:
    cd backend && pytest tests/test_business_time.py -v
"""
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/
from business_time import (  # noqa: E402
    BUSINESS_TZ, business_date, business_day_bounds, clamp_start_to_business_day,
    offered_slot_starts,
)

PHOENIX_DAY = date(2026, 10, 27)
# 6:00 PM America/Phoenix on that day — 1:00 AM UTC the next calendar day.
SIX_PM_PHOENIX = datetime(2026, 10, 27, 18, 0, tzinfo=BUSINESS_TZ)


def test_six_pm_phoenix_is_on_that_phoenix_day_and_not_the_utc_day():
    start, end = business_day_bounds(PHOENIX_DAY)
    job_utc = SIX_PM_PHOENIX.astimezone(timezone.utc)
    assert job_utc == datetime(2026, 10, 28, 1, 0, tzinfo=timezone.utc)

    assert start <= job_utc < end

    utc_start = datetime.combine(PHOENIX_DAY, time.min, tzinfo=timezone.utc)
    utc_end = utc_start + timedelta(days=1)
    assert not (utc_start <= job_utc < utc_end)

    # Mongo compares scheduled_start as ISO strings. The same window must hold there.
    job_s, start_s, end_s = job_utc.isoformat(), start.isoformat(), end.isoformat()
    assert start_s <= job_s < end_s
    assert not (utc_start.isoformat() <= job_s < utc_end.isoformat())


def test_phoenix_day_bounds_are_seven_utc_through_next_seven_utc():
    start, end = business_day_bounds(PHOENIX_DAY)
    assert start == datetime(2026, 10, 27, 7, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 28, 7, 0, tzinfo=timezone.utc)
    assert start.isoformat() == "2026-10-27T07:00:00+00:00"
    assert end.isoformat() == "2026-10-28T07:00:00+00:00"


def test_bounds_are_half_open_at_next_phoenix_midnight():
    start, end = business_day_bounds(PHOENIX_DAY)
    next_midnight = datetime(2026, 10, 28, 0, 0, tzinfo=BUSINESS_TZ).astimezone(timezone.utc)
    assert next_midnight == end
    assert not (start <= next_midnight < end)
    assert business_date(next_midnight) == date(2026, 10, 28)


def test_one_am_utc_is_still_the_previous_phoenix_date():
    instant = datetime(2026, 10, 28, 1, 0, tzinfo=timezone.utc)
    assert business_date(instant) == PHOENIX_DAY
    # Naive datetimes are UTC, same as the rest of the backend.
    assert business_date(datetime(2026, 10, 28, 1, 0)) == PHOENIX_DAY


def test_existing_utc_slot_clocks_stay_on_the_labeled_phoenix_day():
    """Zone windows are still combined as UTC clock times (08:00–19:00 UTC).

    Those instants are 1:00 AM–12:00 PM Phoenix, which is inside the same
    Phoenix civil date. Widening the query window must not drop them.
    """
    start, end = business_day_bounds(PHOENIX_DAY)
    for hour in (8, 14, 19):
        slot = datetime(2026, 10, 27, hour, 0, tzinfo=timezone.utc)
        assert business_date(slot) == PHOENIX_DAY
        assert start <= slot < end


def test_phoenix_offset_is_minus_seven_in_january_and_july():
    for month in (1, 7):
        local = datetime(2026, month, 15, 12, 0, tzinfo=BUSINESS_TZ)
        assert local.utcoffset() == timedelta(hours=-7)
        assert business_date(local) == date(2026, month, 15)


def test_zone_hours_before_0700_utc_are_not_offered_on_that_phoenix_day():
    """A saved zone of 05:00–10:00 is a UTC wall clock. 05:00 UTC is the previous Phoenix evening.

    Offering it on the requested date, then querying that Phoenix day, hides the booking
    and the slot is offered again. Every offered start must fall inside the same window /jobs uses.
    """
    day = date(2026, 10, 27)
    five_am = datetime(2026, 10, 27, 5, 0, tzinfo=timezone.utc)
    zone_end = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)
    starts = offered_slot_starts(day, five_am, zone_end, slot_minutes=45)
    day_start, day_end = business_day_bounds(day)

    assert five_am not in starts
    assert business_date(five_am) == date(2026, 10, 26)
    assert starts == [
        datetime(2026, 10, 27, 7, 15, tzinfo=timezone.utc),
        datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 27, 8, 45, tzinfo=timezone.utc),
    ]
    for start in starts:
        assert day_start <= start < day_end
        assert day_start.isoformat() <= start.isoformat() < day_end.isoformat()


def test_zone_entirely_before_phoenix_midnight_offers_no_slots():
    day = date(2026, 10, 27)
    starts = offered_slot_starts(
        day,
        datetime(2026, 10, 27, 4, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 27, 6, 0, tzinfo=timezone.utc),
        slot_minutes=45,
    )
    assert starts == []


def test_default_0800_utc_zone_still_offers_its_first_slot():
    day = date(2026, 10, 27)
    starts = offered_slot_starts(
        day,
        datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 27, 14, 0, tzinfo=timezone.utc),
        slot_minutes=45,
        limit=7,
    )
    assert starts[0] == datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc)
    assert len(starts) == 7
    assert all(business_date(s) == day for s in starts)


def test_nonpositive_slot_minutes_is_rejected():
    day = date(2026, 10, 27)
    earliest = datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc)
    zone_end = datetime(2026, 10, 27, 14, 0, tzinfo=timezone.utc)
    for bad in (0, -15):
        with pytest.raises(ValueError, match="slot_minutes"):
            offered_slot_starts(day, earliest, zone_end, slot_minutes=bad)


def test_reorder_start_before_phoenix_midnight_moves_up_to_the_day():
    day = date(2026, 10, 27)
    clamped = clamp_start_to_business_day(datetime(2026, 10, 27, 5, 15, tzinfo=timezone.utc), day)
    assert clamped == datetime(2026, 10, 27, 7, 0, tzinfo=timezone.utc)
    kept = clamp_start_to_business_day(datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc), day)
    assert kept == datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc)
    assert clamp_start_to_business_day(datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc), day) is None
