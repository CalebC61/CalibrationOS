"""Feasibility for one technician's route across the valley.

A shop picks a clock time. That time is legal only when the drive from the
previous stop and the drive to the next stop both fit around the job and the
buffer. Inserting between two jobs is allowed. Appending after the last job
is not the only gap.

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
    """On-site minutes. Legacy jobs keep the gap between their stored start and end."""
    if job.get("duration_minutes"):
        return int(job["duration_minutes"])
    if job.get("scheduled_start") and job.get("scheduled_end"):
        try:
            minutes = int(round((_parse(job["scheduled_end"]) - _parse(job["scheduled_start"])).total_seconds() / 60))
        except (TypeError, ValueError):
            minutes = 0
        if minutes > 0:
            return minutes
    return DURATION_MINUTES


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
):
    """None when `start` fits on this route. Otherwise a message for the shop or owner."""
    start = _aware(start)
    day_start = _aware(day_start)
    offer_end = _aware(offer_end)
    new_end = start + timedelta(minutes=duration)
    if not allow_after_offer_end and start > offer_end:
        return "Public arrivals have to be by 5:00 PM."

    ordered = []
    for job in jobs:
        if job.get("status") == "cancelled":
            continue
        try:
            job_start = _parse(job["scheduled_start"])
        except (TypeError, ValueError, KeyError):
            continue
        ordered.append((job, job_start, block_minutes(job)))
    ordered.sort(key=lambda item: (item[1], item[0].get("id") or ""))

    for job, job_start, job_duration in ordered:
        job_end = job_start + timedelta(minutes=job_duration)
        if start < job_end and job_start < new_end:
            return "That time overlaps another job on this technician's route."

    previous = None
    nxt = None
    for item in ordered:
        if item[1] <= start:
            previous = item
        elif nxt is None:
            nxt = item

    if previous:
        leave = previous[1] + timedelta(minutes=previous[2] + buffer)
        origin = (previous[0]["job_lat"], previous[0]["job_lng"])
    else:
        leave = day_start
        origin = home
    earliest = leave + timedelta(minutes=drive(origin, new_point))
    if start < earliest:
        return (
            "That arrival doesn't fit this technician's route. "
            "The drive from the previous stop doesn't leave enough room."
        )
    if nxt:
        depart = start + timedelta(minutes=duration + buffer)
        destination = (nxt[0]["job_lat"], nxt[0]["job_lng"])
        if depart + timedelta(minutes=drive(new_point, destination)) > nxt[1]:
            return (
                "That arrival doesn't fit this technician's route. "
                "The drive to the next stop doesn't leave enough room."
            )
    return None


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
) -> list:
    """Every grid arrival that fits in some gap, including between jobs."""
    cursor = round_up(_aware(day_start), grid)
    offer_end = _aware(offer_end)
    slots = []
    while cursor <= offer_end:
        if placement_error(
            start=cursor, duration=duration, buffer=buffer,
            day_start=day_start, offer_end=offer_end, home=home,
            jobs=jobs, new_point=new_point, drive=drive,
        ) is None:
            slots.append({
                "start": cursor.isoformat(),
                "end": (cursor + timedelta(minutes=duration)).isoformat(),
                "drive_time_minutes": drive(home, new_point) if not jobs else None,
            })
        cursor += timedelta(minutes=grid)
    return slots
