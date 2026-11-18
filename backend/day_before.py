"""Day-before reminder for shops with jobs tomorrow.

America/Phoenix, 5:00 PM. One email per shop. Cancelled and declined jobs
are left out. The caller sends the message through the shop mail path and
stores one marker per shop and day so a second pass does not send again.

No Resend import and no server import.
"""
import html
import logging
from datetime import date, datetime, time, timedelta, timezone

from business_time import BUSINESS_TZ, business_day_bounds
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

REMINDER_AT = time(17, 0)
SKIP_STATUSES = frozenset({"cancelled", "declined"})
RETRY_SECONDS = 300.0


def _local(now: datetime) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(BUSINESS_TZ)


def reminder_is_due(now: datetime) -> bool:
    """True from 5:00 PM Phoenix until midnight. After midnight it is a new day."""
    local = _local(now)
    return local.timetz().replace(tzinfo=None) >= REMINDER_AT


def reminder_day(now: datetime) -> date:
    """The Phoenix date the reminder describes: tomorrow."""
    return _local(now).date() + timedelta(days=1)


def seconds_until_reminder(now: datetime) -> float:
    """Seconds until the next 5:00 PM Phoenix. At that instant, the next one is tomorrow."""
    local = _local(now)
    target = local.replace(hour=REMINDER_AT.hour, minute=0, second=0, microsecond=0)
    if local >= target:
        target += timedelta(days=1)
    return (target - local).total_seconds()


def next_reminder_delay(now: datetime, *, failed: int = 0) -> float:
    """How long the loop should sleep. A failed shop is retried in five minutes."""
    if failed:
        return RETRY_SECONDS
    return max(seconds_until_reminder(now), 1.0)


def marker_key(shop_id: str, day: date) -> str:
    return f"{shop_id}:{day.isoformat()}"


def job_is_skipped(job: dict) -> bool:
    status = str(job.get("status") or "").strip().lower()
    return status in SKIP_STATUSES


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


def _one_line(value) -> str:
    return " ".join(str(value or "").split())


def vehicle_line(job: dict) -> str:
    return " ".join(
        str(job.get(key) or "").strip()
        for key in ("vehicle_year", "vehicle_make", "vehicle_model")
    ).strip()


def customer_name(job: dict) -> str:
    parts = [
        str(job.get("customer_first_name") or "").strip(),
        str(job.get("customer_last_name") or "").strip(),
    ]
    return " ".join(part for part in parts if part)


def calibration_name(job: dict) -> str:
    return str(job.get("calibration_label") or job.get("calibration_type") or "").strip()


def arrival_window(start, end) -> str:
    """Estimated arrival, Phoenix clock. Same meridiem collapses to one AM/PM."""
    start_dt = _parse(start)
    if start_dt is None:
        return "—"
    start_local = start_dt.astimezone(BUSINESS_TZ)
    end_dt = _parse(end)
    if end_dt is None:
        return start_local.strftime("%-I:%M %p") + " Phoenix"
    end_local = end_dt.astimezone(BUSINESS_TZ)
    if end_local <= start_local:
        return start_local.strftime("%-I:%M %p") + " Phoenix"
    if start_local.strftime("%p") == end_local.strftime("%p"):
        return f"{start_local.strftime('%-I:%M')}–{end_local.strftime('%-I:%M %p')} Phoenix"
    return f"{start_local.strftime('%-I:%M %p')}–{end_local.strftime('%-I:%M %p')} Phoenix"


def shop_recipient(shop: dict, jobs: list) -> str | None:
    """Shop contact first. A job notification address is only the fallback."""
    candidates = [shop.get("contact_email")]
    candidates.extend(job.get("notification_email") for job in jobs)
    for value in candidates:
        text = str(value or "").strip()
        if "@" in text:
            return text
    return None


def reminder_message(*, to, reply_to, shop_name, day: date, jobs: list, portal_url: str) -> dict:
    """One shop email. `jobs` are the ones still on tomorrow's board."""
    when = day.strftime("%a, %b %-d, %Y")
    name = _one_line(shop_name) or "your shop"
    subject = f"Tomorrow's calibrations for {name} — {day.strftime('%a, %b %-d')}"
    blocks = []
    for job in jobs:
        lines = "<br>".join([
            f"Vehicle: {html.escape(vehicle_line(job) or '—')}",
            f"Customer: {html.escape(customer_name(job) or '—')}",
            f"Address: {html.escape(str(job.get('job_address') or '—'))}",
            f"Type: {html.escape(calibration_name(job) or '—')}",
            "Estimated arrival: "
            + html.escape(arrival_window(job.get("scheduled_start"), job.get("scheduled_end"))),
        ])
        blocks.append(f"<p>{lines}</p>")
    link = html.escape(portal_url or "", quote=True)
    portal = f'<p><a href="{link}">Open the shop portal</a></p>' if portal_url else ""
    body = (
        f"<p>Jobs scheduled for {html.escape(when)}.</p>"
        + "".join(blocks)
        + portal
        + "<p>Reply to this email and it comes to Caleb.</p>"
    )
    return {
        "to": to,
        "reply_to": reply_to,
        "subject": subject,
        "html": body,
        "kind": "day_before_reminder",
        "meta": {"shop_id": None, "day": day.isoformat()},
    }


async def _claim(markers, key: str, doc: dict) -> bool:
    try:
        await markers.insert_one(dict(doc))
        return True
    except DuplicateKeyError:
        return False


async def run_reminders(db, *, now: datetime, send, portal_url: str, reply_to: str) -> dict:
    """Build and hand off tomorrow's reminders.

    `send` is the shop mail path. A marker is written before the send so two
    passes cannot both deliver. If the send raises, the marker is removed
    and that shop is counted as failed so the loop can retry.
    """
    if not reminder_is_due(now):
        return {"sent": 0, "already": 0, "skipped": 0, "failed": 0, "reason": "before 5:00 PM Phoenix"}

    day = reminder_day(now)
    empty = {"day": day.isoformat(), "sent": 0, "already": 0, "skipped": 0, "failed": 0}
    jobs_col = getattr(db, "jobs", None)
    markers = getattr(db, "day_before_reminders", None)
    if jobs_col is None or markers is None:
        logger.warning("[REMIND] day-before reminder skipped. Jobs or the marker store is missing.")
        return empty

    start, end = business_day_bounds(day)
    query = {
        "scheduled_start": {"$gte": start.isoformat(), "$lt": end.isoformat()},
        "status": {"$nin": sorted(SKIP_STATUSES)},
    }
    found = await jobs_col.find(query, {"_id": 0}).to_list(2000)
    grouped: dict[str, list] = {}
    for job in found:
        if job_is_skipped(job):
            continue
        shop_id = job.get("shop_id")
        if not shop_id:
            continue
        grouped.setdefault(shop_id, []).append(job)
    for rows in grouped.values():
        rows.sort(key=lambda job: str(job.get("scheduled_start") or ""))

    shops: dict = {}
    shops_col = getattr(db, "shops", None)
    if shops_col is not None and grouped:
        rows = await shops_col.find({"id": {"$in": list(grouped)}}, {"_id": 0}).to_list(len(grouped))
        shops = {row.get("id"): row for row in rows if row.get("id")}

    sent = already = skipped = failed = 0
    stamp = _local(now).astimezone(timezone.utc).isoformat()
    for shop_id, rows in grouped.items():
        shop = shops.get(shop_id) or {"id": shop_id, "name": rows[0].get("shop_name") or "Shop"}
        key = marker_key(shop_id, day)
        claimed = await _claim(markers, key, {
            "_id": key,
            "shop_id": shop_id,
            "day": day.isoformat(),
            "status": "claimed",
            "at": stamp,
        })
        if not claimed:
            already += 1
            continue
        recipient = shop_recipient(shop, rows)
        if not recipient:
            await markers.update_one({"_id": key}, {"$set": {"status": "skipped"}})
            skipped += 1
            continue
        message = reminder_message(
            to=recipient,
            reply_to=reply_to,
            shop_name=shop.get("name") or rows[0].get("shop_name") or "Shop",
            day=day,
            jobs=rows,
            portal_url=portal_url,
        )
        message["meta"] = {"shop_id": shop_id, "day": day.isoformat()}
        try:
            await send(message)
        except Exception:
            logger.exception("[REMIND] reminder failed for shop %s", shop_id)
            try:
                await markers.delete_one({"_id": key})
            except Exception:
                logger.exception("[REMIND] could not release the marker for shop %s", shop_id)
            failed += 1
            continue
        await markers.update_one({"_id": key}, {"$set": {"status": "sent", "to": recipient}})
        sent += 1

    logger.info("[REMIND] %s sent %s already %s skipped %s failed %s", day.isoformat(), sent, already, skipped, failed)
    return {"day": day.isoformat(), "sent": sent, "already": already, "skipped": skipped, "failed": failed}
