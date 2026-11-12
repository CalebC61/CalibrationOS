"""Closed dates: US holidays, owner toggles, vacation ranges, and jobs already booked.

    cd backend && pytest tests/test_days_off.py -v
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from days_off import (  # noqa: E402
    closure_message,
    holiday_records,
    jobs_to_flag,
    parse_range,
    set_blocked,
)


def _by_label(year, label):
    matches = [row for row in holiday_records(year) if row["label"] == label]
    assert len(matches) == 1
    return date.fromisoformat(matches[0]["start"])


def test_major_holidays_for_2026_are_preloaded_and_closed():
    records = holiday_records(2026)
    labels = {row["label"] for row in records}
    assert labels == {
        "New Year's Day",
        "Memorial Day",
        "July 4",
        "Labor Day",
        "Thanksgiving",
        "Day after Thanksgiving",
        "Christmas Eve",
        "Christmas",
    }
    assert all(row["blocked"] is True and row["kind"] == "holiday" for row in records)
    assert _by_label(2026, "New Year's Day") == date(2026, 1, 1)
    assert _by_label(2026, "Memorial Day") == date(2026, 5, 25)
    assert _by_label(2026, "July 4") == date(2026, 7, 4)
    assert _by_label(2026, "Labor Day") == date(2026, 9, 7)
    assert _by_label(2026, "Thanksgiving") == date(2026, 11, 26)
    assert _by_label(2026, "Day after Thanksgiving") == date(2026, 11, 27)
    assert _by_label(2026, "Christmas Eve") == date(2026, 12, 24)
    assert _by_label(2026, "Christmas") == date(2026, 12, 25)


def test_thanksgiving_week_blocks_thursday_and_friday_only():
    records = holiday_records(2026)
    assert "Thanksgiving" in closure_message(date(2026, 11, 26), records)
    assert "Day after Thanksgiving" in closure_message(date(2026, 11, 27), records)
    assert closure_message(date(2026, 11, 25), records) is None


def test_owner_can_open_a_preloaded_holiday():
    records = set_blocked(holiday_records(2026), "2026-thanksgiving", False)
    assert closure_message(date(2026, 11, 26), records) is None
    assert closure_message(date(2026, 11, 27), records)


def test_vacation_range_blocks_every_day_inside_it():
    records = [{
        "key": "vacation-1",
        "label": "Vacation",
        "kind": "custom",
        "blocked": True,
        "start": "2026-12-20",
        "end": "2026-12-22",
    }]
    assert "Vacation" in closure_message(date(2026, 12, 20), records)
    assert "Vacation" in closure_message(date(2026, 12, 21), records)
    assert "Vacation" in closure_message(date(2026, 12, 22), records)
    assert closure_message(date(2026, 12, 23), records) is None


def test_range_parser_rejects_an_end_before_the_start():
    start, end = parse_range("2026-12-20", "2026-12-22")
    assert (start, end) == (date(2026, 12, 20), date(2026, 12, 22))
    try:
        parse_range("2026-12-22", "2026-12-20")
    except ValueError as exc:
        assert "end" in str(exc).lower()
    else:
        raise AssertionError("expected a range error")


def test_blocking_a_date_flags_live_jobs_and_does_not_cancel_them():
    jobs = [
        {"id": "on-day", "status": "booked", "scheduled_start": "2026-11-26T16:00:00+00:00"},
        {"id": "cancelled", "status": "cancelled", "scheduled_start": "2026-11-26T18:00:00+00:00"},
        {"id": "done", "status": "complete", "scheduled_start": "2026-11-26T19:00:00+00:00"},
        {"id": "other-day", "status": "requested", "scheduled_start": "2026-11-25T16:00:00+00:00"},
    ]
    flagged = jobs_to_flag(jobs, {date(2026, 11, 26)})
    assert [job["id"] for job in flagged] == ["on-day"]
    assert flagged[0]["status"] == "booked"
    assert jobs[0]["status"] == "booked"
