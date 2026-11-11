"""Routes spend: mode by date, fewer calls, rush multiplier, cache, budget.

    cd backend && pytest tests/test_route_cost.py -v
"""
import asyncio
import os
import sys
from datetime import datetime, time, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

from business_time import zone_window  # noqa: E402
from route_cost import (  # noqa: E402
    ESSENTIALS, PRO, apply_rush, cache_ttl_seconds, collapse_queries,
    default_drive_settings, normalize_address, obviously_impossible, routing_mode,
)
from scheduling import (  # noqa: E402
    annotated_drive_queries, schedule_drive_queries, slot_touching_queries,
)

HOME = (33.3528, -111.7890)
SURPRISE = (33.6292, -112.3679)
# Friday 13 Nov 2026. 6:00 AM Phoenix is 13:00 UTC.
DAY = datetime(2026, 11, 13).date()
SIX, OFFER_END = zone_window(DAY, time(6, 0), time(17, 0))
EIGHT, _ = zone_window(DAY, time(8, 0), time(17, 0))
# 9:00 AM Phoenix on Friday, so tomorrow-morning Pro is still on.
NINE_AM = datetime(2026, 11, 13, 16, 0, tzinfo=timezone.utc)
ELEVEN_AM = datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc)


def _job(hour, minute, point, job_id):
    start, _ = zone_window(DAY, time(hour, minute), time(17, 0))
    return {
        "id": job_id,
        "scheduled_start": start.isoformat(),
        "scheduled_end": (start + timedelta(minutes=20)).isoformat(),
        "duration_minutes": 20,
        "job_lat": point[0],
        "job_lng": point[1],
        "status": "booked",
    }


def _five_jobs():
    # Spread through the valley so some cross-town inserts are impossible at 60 mph.
    spots = [
        (8, 0, (33.40, -111.85), "a"),
        (10, 0, (33.45, -111.95), "b"),
        (12, 0, (33.50, -112.10), "c"),
        (14, 0, (33.55, -112.20), "d"),
        (16, 0, SURPRISE, "e"),
    ]
    return [_job(h, m, point, name) for h, m, point, name in spots]


def _args(jobs):
    return dict(
        day_start=EIGHT, offer_end=OFFER_END, home=HOME, jobs=jobs,
        new_point=(33.42, -111.90), duration=20, buffer=15,
        grid_start=SIX, home_ready=EIGHT, earliest_home_departure=SIX,
    )


def _before(jobs):
    raw = schedule_drive_queries(**_args(jobs))
    unique = set()
    for origin, dest, depart in raw:
        if origin == dest:
            continue
        stamp = "" if depart is None else depart.isoformat()
        unique.add((round(origin[0], 4), round(origin[1], 4), round(dest[0], 4), round(dest[1], 4), stamp))
    return len(unique)


def _after(jobs, mode, same_day):
    raw = annotated_drive_queries(**_args(jobs))
    return len(collapse_queries(raw, mode=mode, same_day=same_day, home=HOME))


def test_routing_mode_uses_pro_only_for_today_and_early_tomorrow():
    today = datetime(2026, 11, 13).date()
    tomorrow = datetime(2026, 11, 14).date()
    later = datetime(2026, 11, 16).date()
    assert routing_mode(today, NINE_AM) == PRO
    assert routing_mode(tomorrow, NINE_AM) == PRO
    assert routing_mode(tomorrow, ELEVEN_AM) == ESSENTIALS
    assert routing_mode(later, NINE_AM) == ESSENTIALS


def test_rush_multiplier_covers_both_windows_and_skips_midday():
    settings = default_drive_settings()
    morning = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)  # 8:00 AM Phoenix
    midday = datetime(2026, 11, 13, 19, 0, tzinfo=timezone.utc)  # noon
    evening = datetime(2026, 11, 13, 23, 30, tzinfo=timezone.utc)  # 4:30 PM
    assert apply_rush(40, morning, settings) == 50
    assert apply_rush(40, evening, settings) == 50
    assert apply_rush(40, midday, settings) == 40
    assert settings["rush_multiplier"] == 1.25
    assert settings["pro_cutoff"] == "10:00"


def test_cache_ttl_is_two_hours_for_pro_and_at_most_seven_days():
    now = NINE_AM
    assert cache_ttl_seconds(PRO, now, DAY) == 2 * 3600
    far = datetime(2026, 11, 20).date()
    assert cache_ttl_seconds(ESSENTIALS, now, far) == 7 * 86400
    soon = datetime(2026, 11, 14).date()
    assert cache_ttl_seconds(ESSENTIALS, now, soon) < 7 * 86400


def test_availability_call_counts_drop_for_an_empty_day_and_a_five_job_day():
    empty_before = _before([])
    empty_after = _after([], ESSENTIALS, False)
    five_before = _before(_five_jobs())
    five_after = _after(_five_jobs(), ESSENTIALS, False)
    same_empty = _after([], PRO, True)
    same_five = _after(_five_jobs(), PRO, True)
    # Before is one Pro call per 15-minute departure. After collapses that.
    assert (empty_before, empty_after, five_before, five_after, same_empty, same_five) == (
        47, 2, 62, 22, 14, 45,
    )


def test_a_far_slot_does_not_call_google():
    leave = EIGHT
    soon = EIGHT + timedelta(minutes=10)
    assert obviously_impossible(HOME, SURPRISE, leave, soon) is True
    near = (33.36, -111.80)
    assert obviously_impossible(HOME, near, leave, EIGHT + timedelta(hours=2)) is False


def test_book_recheck_is_only_the_legs_touching_the_slot():
    start, _ = zone_window(DAY, time(11, 0), time(17, 0))
    legs = slot_touching_queries(
        start=start, day_start=EIGHT, home=HOME, jobs=_five_jobs(),
        new_point=(33.42, -111.90), duration=20, buffer=15, earliest_home_departure=SIX,
    )
    collapsed = collapse_queries(legs, mode=ESSENTIALS, same_day=False, home=HOME)
    assert len(legs) == 3
    assert len(collapsed) <= 3


def test_address_cache_key_ignores_case_and_spacing():
    assert normalize_address("  855 East  Brown Road, Mesa ") == normalize_address(
        "855 east brown road, mesa"
    )


def test_daily_budget_stops_and_logs(monkeypatch):
    import server

    class _Budget:
        def __init__(self):
            self.doc = {"_id": "2026-11-13", "pro": 0, "essentials": 0}

        async def find_one_and_update(self, query, update, upsert=False, return_document=None):
            field = next(iter(update["$inc"]))
            self.doc[field] = self.doc.get(field, 0) + update["$inc"][field]
            return dict(self.doc)

        async def update_one(self, query, update, upsert=False):
            field = next(iter(update["$inc"]))
            self.doc[field] = self.doc.get(field, 0) + update["$inc"][field]

        async def find_one(self, query, projection=None):
            if query.get("_id") == self.doc["_id"]:
                return dict(self.doc)
            return None

    budget = _Budget()
    monkeypatch.setattr(server, "db", type("DB", (), {"routes_budget": budget, "app_settings": None})())
    monkeypatch.setattr(server, "now_utc", lambda: NINE_AM)
    settings = default_drive_settings()
    settings["pro_daily_limit"] = 1

    async def run():
        assert await server._routes_budget_allows(PRO, settings) is True
        assert await server._routes_budget_allows(PRO, settings) is False
        assert budget.doc["pro"] == 1

    asyncio.run(run())
