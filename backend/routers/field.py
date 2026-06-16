"""Field PWA + dispatch + contractor offers + reorder + send-eta."""
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from deps import (CALEB_HOME, ZONES, db, gen_id, get_current_tech, iso, logger,
                  mock_distance_matrix, mock_send_sms, now_utc, parse_time_str,
                  require_owner)
from models import DispatchIn, OfferResponseIn, ReorderIn

router = APIRouter()


@router.post("/field/jobs/{job_id}/send-eta")
async def send_eta(job_id: str, tech=Depends(get_current_tech)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if not job.get("notification_phone"):
        raise HTTPException(400, "This job has no contact phone")
    drive = int(job.get("drive_time_minutes") or 20)
    eta_min = ((drive + 4) // 5) * 5
    eta_dt = now_utc() + timedelta(minutes=eta_min)
    arrival = eta_dt.strftime("%-I:%M %p") if hasattr(eta_dt, "strftime") else eta_dt.isoformat()
    msg = (f"Your ADAS calibration technician is on the way. "
           f"ETA ~{eta_min} minutes (around {arrival}). — The Calibration Crew")
    await mock_send_sms(job["notification_phone"], msg, kind="eta", job_id=job_id)
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "last_eta_sent_at": iso(now_utc()),
        "last_eta_minutes": eta_min,
    }})
    return {"sent": True, "eta_minutes": eta_min, "eta_at": iso(eta_dt)}


async def _expire_stale_offers():
    now = iso(now_utc())
    stale = await db.contractor_offers.find(
        {"status": "pending", "expires_at": {"$lt": now}}, {"_id": 0}
    ).to_list(100)
    for offer in stale:
        await db.contractor_offers.update_one({"id": offer["id"]}, {"$set": {"status": "expired", "responded_at": now}})
        owner = await db.technicians.find_one({"role": "owner"})
        await db.jobs.update_one(
            {"id": offer["job_id"]},
            {"$set": {"status": "booked", "technician_id": owner["id"] if owner else None, "updated_at": now}}
        )
        if owner and owner.get("phone"):
            await mock_send_sms(owner["phone"],
                f"Contractor did not respond. Job {offer['job_id'][:8].upper()} is back on your board.",
                kind="offer_expired", job_id=offer["job_id"])


@router.post("/jobs/{job_id}/dispatch")
async def dispatch_job(job_id: str, data: DispatchIn, tech=Depends(require_owner)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] not in ("booked",):
        raise HTTPException(400, f"Cannot dispatch a job in '{job['status']}' state")
    contractor = await db.technicians.find_one({"id": data.contractor_id, "role": "contractor", "is_active": True})
    if not contractor:
        raise HTTPException(400, "Active contractor not found")
    now = now_utc()
    offer = {
        "id": gen_id(), "job_id": job_id, "contractor_id": contractor["id"],
        "contractor_name": contractor["name"],
        "offered_at": iso(now), "expires_at": iso(now + timedelta(minutes=30)),
        "status": "pending", "responded_at": None, "sms_sent": True,
        "shop_name": job["shop_name"], "scheduled_start": job["scheduled_start"],
        "job_address": job["job_address"],
        "vehicle": f"{job['vehicle_year']} {job['vehicle_make']} {job['vehicle_model']}",
        "calibration_label": job["calibration_label"], "price": job["price"],
    }
    await db.contractor_offers.insert_one(offer.copy())
    await db.jobs.update_one({"id": job_id}, {"$set": {"status": "dispatched_to_contractor", "technician_id": contractor["id"], "updated_at": iso(now)}})
    msg = (f"New job available: {job['shop_name']} at {job['job_address']}. "
           f"{job['vehicle_year']} {job['vehicle_make']} {job['vehicle_model']}. "
           f"{job['calibration_label']} at {datetime.fromisoformat(job['scheduled_start']).strftime('%-I:%M %p')}. "
           f"Reply YES to accept, NO to decline. Offer expires in 30 minutes.")
    if contractor.get("phone"):
        await mock_send_sms(contractor["phone"], msg, kind="contractor_offer", job_id=job_id)
    return offer


@router.get("/contractor-offers")
async def list_offers(tech=Depends(get_current_tech)):
    await _expire_stale_offers()
    q = {}
    if tech["role"] == "contractor":
        q["contractor_id"] = tech["id"]
        q["status"] = "pending"
    offers = await db.contractor_offers.find(q, {"_id": 0}).sort("offered_at", -1).limit(100).to_list(100)
    return offers


@router.post("/contractor-offers/{offer_id}/respond")
async def respond_to_offer(offer_id: str, body: OfferResponseIn, tech=Depends(get_current_tech)):
    offer = await db.contractor_offers.find_one({"id": offer_id})
    if not offer:
        raise HTTPException(404, "Offer not found")
    if offer["status"] != "pending":
        raise HTTPException(400, f"Offer already {offer['status']}")
    if tech["role"] == "contractor" and offer["contractor_id"] != tech["id"]:
        raise HTTPException(403, "Not your offer")
    now = iso(now_utc())
    new_status = "accepted" if body.accept else "declined"
    await db.contractor_offers.update_one({"id": offer_id}, {"$set": {"status": new_status, "responded_at": now}})
    if body.accept:
        await db.jobs.update_one({"id": offer["job_id"]}, {"$set": {"technician_id": offer["contractor_id"], "updated_at": now}})
        owner = await db.technicians.find_one({"role": "owner"})
        if owner and owner.get("phone"):
            await mock_send_sms(owner["phone"],
                f"✓ {offer['contractor_name']} accepted job {offer['job_id'][:8].upper()} ({offer['shop_name']}).",
                kind="offer_accepted", job_id=offer["job_id"])
    else:
        owner = await db.technicians.find_one({"role": "owner"})
        await db.jobs.update_one({"id": offer["job_id"]}, {"$set": {"status": "booked", "technician_id": owner["id"] if owner else None, "updated_at": now}})
        if owner and owner.get("phone"):
            await mock_send_sms(owner["phone"],
                f"✗ {offer['contractor_name']} declined job {offer['job_id'][:8].upper()}. Back on your board.",
                kind="offer_declined", job_id=offer["job_id"])
    return {"status": new_status}


@router.get("/contractors")
async def list_contractors(tech=Depends(require_owner)):
    return await db.technicians.find({"role": "contractor"}, {"_id": 0, "password_hash": 0}).to_list(50)


@router.post("/jobs/reorder")
async def reorder_jobs(data: ReorderIn, tech=Depends(require_owner)):
    z = ZONES[data.zone]
    try:
        d = datetime.strptime(data.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date")
    day_start = datetime.combine(d, time(0, 0), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    jobs = await db.jobs.find({
        "id": {"$in": data.ordered_job_ids},
        "zone": data.zone,
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(day_end)},
        "status": {"$nin": ["cancelled", "complete"]},
    }, {"_id": 0}).to_list(100)
    by_id = {j["id"]: j for j in jobs}
    if set(data.ordered_job_ids) - set(by_id.keys()):
        raise HTTPException(400, "Some job IDs are invalid or not reorderable")
    cursor = datetime.combine(d, parse_time_str(z["start"]), tzinfo=timezone.utc)
    origin = (CALEB_HOME["lat"], CALEB_HOME["lng"])
    updates = []
    for seq, jid in enumerate(data.ordered_job_ids, start=1):
        j = by_id[jid]
        dm = mock_distance_matrix(origin[0], origin[1], j["job_lat"], j["job_lng"])
        earliest = cursor + timedelta(minutes=dm["duration_minutes"])
        minute = (earliest.minute // 15) * 15
        if earliest.minute % 15 != 0 or earliest.second > 0:
            minute += 15
        if minute >= 60:
            earliest = earliest.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            earliest = earliest.replace(minute=minute, second=0, microsecond=0)
        new_start = earliest
        new_end = new_start + timedelta(minutes=z["slot_minutes"])
        zone_end_dt = datetime.combine(d, parse_time_str(z["end"]), tzinfo=timezone.utc)
        if new_end > zone_end_dt:
            raise HTTPException(400, "Reorder would push job past zone end. Try a different order.")
        updates.append({
            "id": jid, "scheduled_start": iso(new_start), "scheduled_end": iso(new_end),
            "drive_time_minutes": dm["duration_minutes"], "sequence_order": seq,
        })
        cursor = new_end
        origin = (j["job_lat"], j["job_lng"])
    for u in updates:
        await db.jobs.update_one({"id": u["id"]}, {"$set": {
            "scheduled_start": u["scheduled_start"], "scheduled_end": u["scheduled_end"],
            "drive_time_minutes": u["drive_time_minutes"], "sequence_order": u["sequence_order"],
            "updated_at": iso(now_utc()),
        }})
    return {"updated": len(updates), "jobs": updates}
