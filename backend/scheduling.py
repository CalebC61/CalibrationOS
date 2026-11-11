"""Feasibility for one technician's route across the valley.

A shop picks a clock time. That time is legal only when the drive from the
previous stop and the drive to the next stop both fit around the job and the
buffer. Inserting between two jobs is allowed. Appending after the last job
is not the only gap.

`drive(origin, destination, depart)` returns minutes. A two-argument callable
still works. `depart` is when the technician leaves the origin, so a caller
can use a traffic-aware time for that leg.

Pure: stdlib plus a drive-minutes callable. No database and no messages.

Deferred from docs/plans/smart-scheduling.md (PR #12): shop-facing arrival
windows instead of minutes, sliding other jobs' ETAs inside a window, the
day lock, the +7 hour restamp, and SMS when a drag leaves a promised window.
"""
from datetime import datetime, timedelta, timezone

DURATION_MINUTES = 20
BUFFER_MINUTES = 15
GRID_MINUTES = 15


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _parse(value: str) -> datetime:
    return _aware(datetime.fromisoformat(str(value).replace("Z", "+00:00")))


def round_up(moment: datetime, grid: int = GRID_MINUTES) -> datetime:
    moment = _aware(moment)
    if moment.second or moment.microsecond:
        moment = moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
    else:
        moment = moment.replace(second=0, microsecond=0)
    extra = moment.minute % grid
    if extra:
        moment += timedelta(minutes=grid - extra)
    return moment


def block_minutes(job: dict) -> int:
    """On-site minutes. An explicit 0 is a live position, not a missing value.

    Legacy jobs keep the gap between their stored start and end.
    """
    if job.get("duration_minutes") is not None and "duration_minutes" in job:
        return max(0, int(job["duration_minutes"]))
    if job.get("scheduled_start") and job.get("scheduled_end"):
        try:
            minutes = int(round((_parse(job["scheduled_end"]) - _parse(job["scheduled_start"])).total_seconds() / 60))
        except (TypeError, ValueError):
            minutes = 0
        if minutes > 0:
            return minutes
    return DURATION_MINUTES


def drive_minutes(drive, origin, dest, depart) -> int:
    """Minutes for one leg. Same point is zero. Two-arg callables still work."""
    if origin is None or dest is None:
        return 0
    if (origin[0], origin[1]) == (dest[0], dest[1]):
        return 0
    try:
        value = drive(origin, dest, depart)
    except TypeError:
        value = drive(origin, dest)
    return max(0, int(value))


def _ordered(jobs: list) -> list:
    ordered = []
    for job in jobs:
        if job.get("status") in ("cancelled", "declined"):
            continue
        if str(job.get("id") or "").startswith("live-"):
            # A live position is a place and a clock, not a job that can overlap.
            pass
        try:
            job_start = _parse(job["scheduled_start"])
        except (TypeError, ValueError, KeyError):
            continue
        if job.get("job_lat") is None or job.get("job_lng") is None:
            continue
        ordered.append((job, job_start, block_minutes(job)))
    ordered.sort(key=lambda item: (item[1], item[0].get("id") or ""))
    return ordered


def _neighbors(start: datetime, ordered: list):
    previous = None
    nxt = None
    for item in ordered:
        if item[1] <= start:
            previous = item
        elif nxt is None:
            nxt = item
    return previous, nxt


def placement_error(
    *,
    start: datetime,
    duration: int,
    buffer: int,
    day_start: datetime,
    offer_end: datetime,
    home: tuple,
    jobs: list,
    new_point: tuple,
    drive,
    allow_after_offer_end: bool = False,
    earliest_public: datetime | None = None,
    waive_home_drive_before: datetime | None = None,
    earliest_home_departure: datetime | None = None,
):
    """None when `start` fits on this route. Otherwise a message for the shop or owner.

    On a future day, `earliest_home_departure` is the first minute the technician
    may leave home (6:00 AM). A first stop is legal when arrival minus the drive
    is still at or after that minute. An 8:00 AM arrival with a 96-minute drive
    leaves at 6:24 AM and is legal. `waive_home_drive_before` is the same-day
    path: a first stop before that clock skips the home-drive check. Drive time
    between jobs still applies either way.
    `allow_after_offer_end` is the owner override for the public window
    (before the first public minute, and after 5:00 PM).
    """
    start = _aware(start)
    day_start = _aware(day_start)
    offer_end = _aware(offer_end)
    new_end = start + timedelta(minutes=duration)
    if earliest_public is not None and not allow_after_offer_end and start < _aware(earliest_public):
        return "Public arrivals start at 6:00 AM."
    if not allow_after_offer_end and start > offer_end:
        return "Public arrivals have to be by 5:00 PM."

    ordered = _ordered(jobs)

    for job, job_start, job_duration in ordered:
        if str(job.get("id") or "").startswith("live-"):
            continue
        job_end = job_start + timedelta(minutes=job_duration)
        if start < job_end and job_start < new_end:
            return "That time overlaps another job on this technician's route."

    previous, nxt = _neighbors(start, ordered)

    if previous:
        leave = previous[1] + timedelta(minutes=previous[2] + buffer)
        origin = (previous[0]["job_lat"], previous[0]["job_lng"])
        earliest = leave + timedelta(minutes=drive_minutes(drive, origin, new_point, leave))
        if start < earliest:
            return (
                "That arrival doesn't fit this technician's route. "
                "The drive from the previous stop doesn't leave enough room."
            )
    elif earliest_home_departure is not None:
        # Future day, no previous stop. Leave = arrival minus the drive.
        # That leave has to be at or after the earliest allowed departure.
        floor = _aware(earliest_home_departure)
        minutes = drive_minutes(drive, home, new_point, floor)
        if start - timedelta(minutes=minutes) < floor:
            return (
                "That arrival doesn't fit this technician's route. "
                "The drive from the previous stop doesn't leave enough room."
            )
    elif waive_home_drive_before is not None and start < _aware(waive_home_drive_before):
        pass
    else:
        earliest = day_start + timedelta(minutes=drive_minutes(drive, home, new_point, day_start))
        if start < earliest:
            return (
                "That arrival doesn't fit this technician's route. "
                "The drive from the previous stop doesn't leave enough room."
            )
    if nxt:
        depart = start + timedelta(minutes=duration + buffer)
        destination = (nxt[0]["job_lat"], nxt[0]["job_lng"])
        if depart + timedelta(minutes=drive_minutes(drive, new_point, destination, depart)) > nxt[1]:
            return (
                "That arrival doesn't fit this technician's route. "
                "The drive to the next stop doesn't leave enough room."
            )
    return None


def insertion_cost(
    *,
    start: datetime,
    duration: int,
    buffer: int,
    home: tuple,
    home_ready: datetime,
    jobs: list,
    new_point: tuple,
    drive,
) -> dict:
    """How a new stop changes the leg it splits.

    Extra drive is the drive in and onward, minus the drive that leg would
    have been. When the new stop is after the last job, onward is toward home
    and later_finish is how much later the technician gets home. When a later
    job stays at its clock time, the day does not run longer (later_finish is 0)
    as long as the drive to that job still fits.
    """
    start = _aware(start)
    home_ready = _aware(home_ready)
    ordered = _ordered(jobs)
    previous, nxt = _neighbors(start, ordered)
    if previous:
        origin = (previous[0]["job_lat"], previous[0]["job_lng"])
        origin_ready = previous[1] + timedelta(minutes=previous[2] + buffer)
    else:
        origin = home
        origin_ready = home_ready
    if nxt:
        dest = (nxt[0]["job_lat"], nxt[0]["job_lng"])
    else:
        dest = home
    direct = drive_minutes(drive, origin, dest, origin_ready)
    to_stop = drive_minutes(drive, origin, new_point, origin_ready)
    depart = start + timedelta(minutes=duration + buffer)
    onward = drive_minutes(drive, new_point, dest, depart)
    extra = to_stop + onward - direct
    if nxt is None:
        finish_without = origin_ready + timedelta(minutes=direct)
        finish_with = depart + timedelta(minutes=onward)
        later = int(round((finish_with - finish_without).total_seconds() / 60))
    else:
        later = 0
    return {
        "extra_drive_minutes": extra,
        "later_finish_minutes": max(0, later),
        "to_stop_minutes": to_stop,
        "empty_route": previous is None and nxt is None,
    }


def candidate_slots(
    *,
    day_start: datetime,
    offer_end: datetime,
    home: tuple,
    jobs: list,
    new_point: tuple,
    drive,
    duration: int = DURATION_MINUTES,
    buffer: int = BUFFER_MINUTES,
    grid: int = GRID_MINUTES,
    grid_start: datetime | None = None,
    earliest_public: datetime | None = None,
    waive_home_drive_before: datetime | None = None,
    earliest_home_departure: datetime | None = None,
) -> list:
    """Every grid arrival that fits in some gap, including between jobs.

    `grid_start` defaults to `day_start`. Public booking passes 6:00 AM so an
    early request can be offered while `day_start` stays the normal leave-home time.
    """
    cursor = round_up(_aware(grid_start or day_start), grid)
    offer_end = _aware(offer_end)
    slots = []
    while cursor <= offer_end:
        if placement_error(
            start=cursor, duration=duration, buffer=buffer,
            day_start=day_start, offer_end=offer_end, home=home,
            jobs=jobs, new_point=new_point, drive=drive,
            earliest_public=earliest_public,
            waive_home_drive_before=waive_home_drive_before,
            earliest_home_departure=earliest_home_departure,
        ) is None:
            slots.append({
                "start": cursor.isoformat(),
                "end": (cursor + timedelta(minutes=duration)).isoformat(),
                "drive_time_minutes": drive_minutes(drive, home, new_point, _aware(day_start)),
            })
        cursor += timedelta(minutes=grid)
    return slots


def slot_touching_queries(
    *,
    start: datetime,
    day_start: datetime,
    home: tuple,
    jobs: list,
    new_point: tuple,
    duration: int = DURATION_MINUTES,
    buffer: int = BUFFER_MINUTES,
    earliest_home_departure: datetime | None = None,
) -> list:
    """Only the legs that touch one chosen arrival: previous→new, new→next, and the direct leg.

    A book or an edit rechecks these. It does not walk the whole day's grid.
    """
    start = _aware(start)
    ordered = _ordered(jobs)
    previous, nxt = _neighbors(start, ordered)
    if previous:
        origin = (previous[0]["job_lat"], previous[0]["job_lng"])
        ready = previous[1] + timedelta(minutes=previous[2] + buffer)
    else:
        origin = home
        ready = _aware(earliest_home_departure or day_start)
    if nxt:
        dest = (nxt[0]["job_lat"], nxt[0]["job_lng"])
        arrive_by = nxt[1]
    else:
        dest = home
        arrive_by = None
    depart = start + timedelta(minutes=duration + buffer)
    return [
        (origin, new_point, ready, None),
        (new_point, dest, depart, arrive_by),
        (origin, dest, ready, None),
    ]


def annotated_drive_queries(
    *,
    day_start: datetime,
    offer_end: datetime,
    home: tuple,
    jobs: list,
    new_point: tuple,
    duration: int = DURATION_MINUTES,
    buffer: int = BUFFER_MINUTES,
    grid: int = GRID_MINUTES,
    grid_start: datetime | None = None,
    home_ready: datetime | None = None,
    earliest_home_departure: datetime | None = None,
) -> list:
    """Every leg the slot walk can ask for, with the deadline that makes it impossible.

    The fourth item is the latest arrival, or None when the leg is only a duration.
    """
    day_start = _aware(day_start)
    offer_end = _aware(offer_end)
    ready = _aware(home_ready or day_start)
    ordered = _ordered(jobs)
    queries = [
        (home, new_point, day_start, None),
        (home, new_point, ready, None),
    ]
    if earliest_home_departure is not None:
        queries.append((home, new_point, _aware(earliest_home_departure), None))
    for _job, job_start, job_duration in ordered:
        leave = job_start + timedelta(minutes=job_duration + buffer)
        point = (_job["job_lat"], _job["job_lng"])
        queries.append((point, new_point, leave, None))
        queries.append((point, home, leave, None))
    cursor = round_up(_aware(grid_start or day_start), grid)
    while cursor <= offer_end:
        previous, nxt = _neighbors(cursor, ordered)
        if previous:
            origin = (previous[0]["job_lat"], previous[0]["job_lng"])
            origin_ready = previous[1] + timedelta(minutes=previous[2] + buffer)
        else:
            origin = home
            origin_ready = day_start
        if nxt:
            dest = (nxt[0]["job_lat"], nxt[0]["job_lng"])
            arrive_by = nxt[1]
        else:
            dest = home
            arrive_by = None
        depart = cursor + timedelta(minutes=duration + buffer)
        queries.append((origin, new_point, origin_ready, None))
        queries.append((new_point, dest, depart, arrive_by))
        queries.append((origin, dest, origin_ready, None))
        cursor += timedelta(minutes=grid)
    return queries


def schedule_drive_queries(
    *,
    day_start: datetime,
    offer_end: datetime,
    home: tuple,
    jobs: list,
    new_point: tuple,
    duration: int = DURATION_MINUTES,
    buffer: int = BUFFER_MINUTES,
    grid: int = GRID_MINUTES,
    grid_start: datetime | None = None,
    home_ready: datetime | None = None,
    earliest_home_departure: datetime | None = None,
) -> list:
    """Legs a slot check will ask for, including the direct leg a detour replaces.

    Callers prefetch these once. The same leave and depart instants are used
    by placement_error and insertion_cost.
    """
    day_start = _aware(day_start)
    offer_end = _aware(offer_end)
    ready = _aware(home_ready or day_start)
    ordered = _ordered(jobs)
    queries = [(home, new_point, day_start), (home, new_point, ready)]
    if earliest_home_departure is not None:
        queries.append((home, new_point, _aware(earliest_home_departure)))
    for _job, job_start, job_duration in ordered:
        leave = job_start + timedelta(minutes=job_duration + buffer)
        point = (_job["job_lat"], _job["job_lng"])
        queries.append((point, new_point, leave))
        queries.append((point, home, leave))
    cursor = round_up(_aware(grid_start or day_start), grid)
    while cursor <= offer_end:
        previous, nxt = _neighbors(cursor, ordered)
        if previous:
            origin = (previous[0]["job_lat"], previous[0]["job_lng"])
            origin_ready = previous[1] + timedelta(minutes=previous[2] + buffer)
        else:
            origin = home
            origin_ready = day_start
        dest = (nxt[0]["job_lat"], nxt[0]["job_lng"]) if nxt else home
        depart = cursor + timedelta(minutes=duration + buffer)
        queries.append((origin, new_point, origin_ready))
        queries.append((new_point, dest, depart))
        queries.append((origin, dest, origin_ready))
        cursor += timedelta(minutes=grid)
    return queries
