"""/shops/* and public booking endpoints."""
from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, time, timedelta, timezone

import stripe as stripe_sdk
from fastapi import APIRouter, Depends, HTTPException

from deps import (CALEB_HOME, STANDARD_PRICING, ZONES, compute_available_slots, db,
                  detect_zone, gen_id, iso, logger, mock_distance_matrix, mock_geocode,
                  mock_send_sms, now_utc, require_owner, shop_price_for)
from models import BookingIn, ShopIn, ShopUpdate, SlotQuery

router = APIRouter()


@router.get("/shops")
async def list_shops(tech=Depends(require_owner)):
    shops = await db.shops.find({}, {"_id": 0}).to_list(1000)
    return shops


@router.post("/shops")
async def create_shop(data: ShopIn, tech=Depends(require_owner)):
    geo = mock_geocode(data.address)
    zone = detect_zone(geo["lng"])
    shop = {
        "id": gen_id(),
        **data.model_dump(),
        "lat": geo["lat"], "lng": geo["lng"],
        "zone": zone,
        "booking_link_token": secrets.token_hex(16),
        "terms_signed_at": iso(now_utc()) if data.terms_signed_by else None,
        "status": "active",
        "created_at": iso(now_utc()),
        "updated_at": iso(now_utc()),
    }
    await db.shops.insert_one(shop.copy())
    return shop


@router.get("/shops/{shop_id}")
async def get_shop(shop_id: str, tech=Depends(require_owner)):
    shop = await db.shops.find_one({"id": shop_id}, {"_id": 0})
    if not shop:
        raise HTTPException(404, "Shop not found")
    return shop


@router.put("/shops/{shop_id}")
async def update_shop(shop_id: str, data: ShopUpdate, tech=Depends(require_owner)):
    shop = await db.shops.find_one({"id": shop_id})
    if not shop:
        raise HTTPException(404, "Shop not found")
    update = data.model_dump(exclude_unset=True)
    if "address" in update and update["address"] != shop["address"]:
        geo = mock_geocode(update["address"])
        update["lat"] = geo["lat"]; update["lng"] = geo["lng"]
        update["zone"] = detect_zone(geo["lng"])
    update["updated_at"] = iso(now_utc())
    await db.shops.update_one({"id": shop_id}, {"$set": update})
    fresh = await db.shops.find_one({"id": shop_id}, {"_id": 0})
    return fresh


@router.post("/shops/{shop_id}/regenerate-link")
async def regenerate_link(shop_id: str, tech=Depends(require_owner)):
    token = secrets.token_hex(16)
    await db.shops.update_one({"id": shop_id}, {"$set": {"booking_link_token": token, "updated_at": iso(now_utc())}})
    return {"booking_link_token": token}


# ---------- Public booking by token ----------
@router.get("/public/shop/{token}")
async def public_shop(token: str):
    shop = await db.shops.find_one(
        {"booking_link_token": token, "status": "active"},
        {"_id": 0, "custom_rate_static": 1, "custom_rate_dynamic": 1,
         "custom_rate_dual": 1, "custom_rate_triple": 1, "custom_rate_tesla": 1,
         "pricing_tier": 1, "name": 1, "address": 1, "contact_phone": 1,
         "contact_email": 1, "id": 1, "booking_link_token": 1, "zone": 1},
    )
    if not shop:
        raise HTTPException(404, "This booking link is not active. Contact The Calibration Crew.")
    return shop


@router.post("/public/availability")
async def public_availability(query: SlotQuery):
    shop = await db.shops.find_one({"booking_link_token": query.booking_token, "status": "active"})
    if not shop:
        raise HTTPException(404, "Invalid booking link")
    geo = mock_geocode(query.job_address)
    if not geo["in_metro"]:
        return {"zone": None, "in_metro": False, "slots": [],
                "message": "This address is outside our current service area."}
    zone = detect_zone(geo["lng"])
    try:
        day = datetime.strptime(query.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date")
    today = now_utc().date()
    if day.weekday() == 6:
        return {"zone": zone, "in_metro": True, "slots": [], "message": "No availability on Sundays."}
    if day < today:
        return {"zone": zone, "in_metro": True, "slots": [], "message": "That date is in the past."}
    if (day - today).days > 21:
        return {"zone": zone, "in_metro": True, "slots": [], "message": "Bookings are only available 21 days out."}
    slots = await compute_available_slots(zone, day, geo["lat"], geo["lng"])
    return {"zone": zone, "in_metro": True, "slots": slots, "job_lat": geo["lat"], "job_lng": geo["lng"]}


@router.post("/public/book")
async def public_book(data: BookingIn):
    shop = await db.shops.find_one({"booking_link_token": data.booking_token, "status": "active"})
    if not shop:
        raise HTTPException(404, "Invalid booking link")
    geo = mock_geocode(data.job_address)
    if not geo["in_metro"]:
        raise HTTPException(400, "Address outside service area")
    zone = detect_zone(geo["lng"])
    try:
        start_dt = datetime.fromisoformat(data.scheduled_start.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "Invalid scheduled_start")
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    z = ZONES[zone]
    end_dt = start_dt + timedelta(minutes=z["slot_minutes"])

    day = start_dt.date()
    day_start = datetime.combine(day, time(0, 0), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    prev = await db.jobs.find({
        "zone": zone,
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(start_dt)},
        "status": {"$nin": ["cancelled"]},
    }, {"_id": 0}).sort("scheduled_start", -1).limit(1).to_list(1)
    if prev:
        origin = (prev[0]["job_lat"], prev[0]["job_lng"])
    else:
        origin = (CALEB_HOME["lat"], CALEB_HOME["lng"])
    dm = mock_distance_matrix(origin[0], origin[1], geo["lat"], geo["lng"])
    owner = await db.technicians.find_one({"role": "owner"})

    vehicle = {
        "id": gen_id(), "year": data.year, "make": data.make, "model": data.model,
        "trim": data.trim, "vin": data.vin, "adas_system": data.adas_system,
        "shop_id": shop["id"], "customer_last_name": data.customer_last_name,
        "created_at": iso(now_utc()),
    }
    await db.vehicles.insert_one(vehicle.copy())

    price = shop_price_for(shop, data.calibration_type)
    job_type = data.job_type or "cash"
    insurance_approved_amount = None
    if job_type == "insurance":
        if data.insurance_approved_amount is None or data.insurance_approved_amount <= 0:
            raise HTTPException(400, "Insurance jobs require an approved amount greater than $0")
        insurance_approved_amount = float(data.insurance_approved_amount)

    seq_count = await db.jobs.count_documents({
        "zone": zone,
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(day_end)},
        "status": {"$nin": ["cancelled"]},
    })

    job = {
        "id": gen_id(),
        "shop_id": shop["id"],
        "shop_name": shop["name"],
        "vehicle_id": vehicle["id"],
        "technician_id": owner["id"] if owner else None,
        "zone": zone,
        "calibration_type": data.calibration_type,
        "calibration_label": STANDARD_PRICING[data.calibration_type]["label"],
        "scheduled_start": iso(start_dt),
        "scheduled_end": iso(end_dt),
        "job_address": data.job_address,
        "job_lat": geo["lat"], "job_lng": geo["lng"],
        "status": "booked",
        "drive_time_minutes": dm["duration_minutes"],
        "actual_arrival": None, "actual_completion": None,
        "result": None, "notes": None,
        "price": price,
        "job_type": job_type,
        "insurance_approved_amount": insurance_approved_amount,
        "invoice_id": None, "invoice_status": "pending",
        "google_calendar_event_id": None,
        "sequence_order": seq_count + 1,
        "notification_phone": data.notification_phone or shop.get("contact_phone"),
        "notification_email": data.notification_email or shop.get("contact_email"),
        "customer_last_name": data.customer_last_name,
        "vehicle_year": data.year, "vehicle_make": data.make,
        "vehicle_model": data.model, "vehicle_vin": data.vin,
        "created_at": iso(now_utc()), "updated_at": iso(now_utc()),
    }

    # Stripe auth-hold for bookings ≤ 6 days out
    try:
        days_out = (start_dt.date() - now_utc().date()).days
        if 0 <= days_out <= 6 and stripe_sdk.api_key and not stripe_sdk.api_key.endswith("_emergent"):
            shop_user = await db.shop_users.find_one({
                "shop_id": shop["id"],
                "stripe_payment_method_id": {"$ne": None},
            })
            if shop_user:
                amount_cents = int(round(price * 100))
                hold = await asyncio.to_thread(
                    stripe_sdk.PaymentIntent.create,
                    amount=amount_cents, currency="usd",
                    customer=shop_user["stripe_customer_id"],
                    payment_method=shop_user["stripe_payment_method_id"],
                    off_session=True, confirm=True, capture_method="manual",
                    description=f"Auth hold — {STANDARD_PRICING[data.calibration_type]['label']}",
                    metadata={"job_id": job["id"], "shop_id": shop["id"]},
                )
                job["stripe_auth_intent_id"] = hold["id"]
                job["stripe_auth_status"] = hold["status"]
                job["stripe_auth_amount_cents"] = amount_cents
                job["stripe_auth_placed_at"] = iso(now_utc())
                logger.info(f"[STRIPE] Auth hold placed for job {job['id']} → PI {hold['id']} ({hold['status']})")
    except Exception as e:
        logger.warning(f"[STRIPE] Auth hold skipped for job {job['id']}: {e}")
        job["stripe_auth_error"] = str(e)[:300]

    await db.jobs.insert_one(job.copy())

    msg = (f"Booking confirmed with The Calibration Crew. "
           f"{start_dt.strftime('%a %b %d at %-I:%M %p')} for your {data.year} {data.make} {data.model}. "
           f"Questions? Reply to this message.")
    if job["notification_phone"]:
        await mock_send_sms(job["notification_phone"], msg, kind="booking_confirmed", job_id=job["id"])

    if owner:
        await db.new_booking_alerts.insert_one({
            "id": gen_id(),
            "job_id": job["id"],
            "owner_id": owner["id"],
            "created_at": iso(now_utc()),
            "seen_at": None,
            "shop_name": shop["name"],
            "scheduled_start": job["scheduled_start"],
            "zone": zone,
            "vehicle": f"{data.year} {data.make} {data.model}",
            "price": price,
        })
        owner_msg = (
            f"🎉 New booking from {shop['name']}: "
            f"{start_dt.strftime('%a %b %d at %-I:%M %p')} — "
            f"{data.year} {data.make} {data.model} (${price:.0f}). "
            f"View on dispatch board."
        )
        if owner.get("phone"):
            await mock_send_sms(owner["phone"], owner_msg, kind="owner_new_booking", job_id=job["id"])

    return {"job_id": job["id"], "booking_reference": job["id"][:8].upper(),
            "scheduled_start": job["scheduled_start"], "zone": zone, "price": price,
            "job_type": job["job_type"],
            "insurance_approved_amount": job.get("insurance_approved_amount"),
            "stripe_auth_intent_id": job.get("stripe_auth_intent_id"),
            "stripe_auth_status": job.get("stripe_auth_status"),
            "stripe_auth_error": job.get("stripe_auth_error")}
