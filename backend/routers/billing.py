"""/charge-queue + /jobs/{id}/charge + /jobs/{id}/skip-charge endpoints."""
import asyncio

import stripe as stripe_sdk
from fastapi import APIRouter, Depends, HTTPException

from deps import db, iso, logger, now_utc, require_owner

router = APIRouter()


@router.get("/charge-queue")
async def charge_queue(tech=Depends(require_owner)):
    portal_users = await db.shop_users.find(
        {"stripe_payment_method_id": {"$ne": None}}, {"_id": 0}
    ).to_list(500)
    shop_id_to_user = {u["shop_id"]: u for u in portal_users}
    jobs = await db.jobs.find({
        "status": "complete",
        "shop_id": {"$in": list(shop_id_to_user.keys())},
        "charged_at": {"$exists": False},
        "charge_skipped_at": {"$exists": False},
    }, {"_id": 0}).sort("actual_completion", -1).to_list(200)
    enriched = []
    for j in jobs:
        u = shop_id_to_user.get(j["shop_id"], {})
        enriched.append({**j,
            "card_brand": u.get("card_brand"), "card_last4": u.get("card_last4"),
            "shop_user_email": u.get("email")})
    return enriched


@router.post("/jobs/{job_id}/charge")
async def charge_job(job_id: str, tech=Depends(require_owner)):
    if not stripe_sdk.api_key or stripe_sdk.api_key.endswith("_emergent"):
        raise HTTPException(400, "Stripe is not configured. Add a real STRIPE_API_KEY to backend/.env.")
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "complete":
        raise HTTPException(400, f"Cannot charge a {job['status']} job")
    if job.get("charged_at"):
        raise HTTPException(400, "This job has already been charged")
    shop_user = await db.shop_users.find_one({
        "shop_id": job["shop_id"], "stripe_payment_method_id": {"$ne": None},
    })
    if not shop_user:
        raise HTTPException(400, "No card on file for this shop")
    amount_cents = int(round(float(job["price"]) * 100))
    if amount_cents <= 0:
        raise HTTPException(400, "Job price must be greater than zero")

    auth_pi_id = job.get("stripe_auth_intent_id")
    used_capture = False
    intent = None
    if auth_pi_id:
        try:
            existing = await asyncio.to_thread(stripe_sdk.PaymentIntent.retrieve, auth_pi_id)
            if existing.get("status") == "requires_capture":
                cap_amount = min(amount_cents, existing.get("amount_capturable") or existing.get("amount") or amount_cents)
                intent = await asyncio.to_thread(stripe_sdk.PaymentIntent.capture, auth_pi_id, amount_to_capture=cap_amount)
                used_capture = True
                logger.info(f"[STRIPE] Captured auth hold {auth_pi_id} for job {job_id}")
            elif existing.get("status") == "succeeded":
                intent = existing
                used_capture = True
        except stripe_sdk.error.StripeError as e:
            logger.warning(f"[STRIPE] Auth hold capture failed for {auth_pi_id}: {e}; will create fresh PI")

    if intent is None:
        try:
            intent = await asyncio.to_thread(
                stripe_sdk.PaymentIntent.create,
                amount=amount_cents, currency="usd",
                customer=shop_user["stripe_customer_id"],
                payment_method=shop_user["stripe_payment_method_id"],
                off_session=True, confirm=True,
                description=f"Calibration {job.get('calibration_label','')} — {job.get('vehicle_year','')} {job.get('vehicle_make','')} {job.get('vehicle_model','')}",
                metadata={"job_id": job_id, "shop_id": job["shop_id"],
                          "shop_name": job.get("shop_name", ""),
                          "invoice_id": job.get("invoice_id") or ""},
            )
        except stripe_sdk.error.CardError as e:
            err = e.error or {}
            decline_code = getattr(err, "decline_code", None) or err.get("decline_code") if isinstance(err, dict) else None
            message = getattr(err, "message", None) or str(e)
            await db.jobs.update_one({"id": job_id}, {"$set": {
                "last_charge_error": message, "last_charge_attempt_at": iso(now_utc())}})
            raise HTTPException(402, f"Card declined: {message}{f' ({decline_code})' if decline_code else ''}")
        except stripe_sdk.error.StripeError as e:
            message = getattr(e, "user_message", None) or str(e)
            await db.jobs.update_one({"id": job_id}, {"$set": {
                "last_charge_error": message, "last_charge_attempt_at": iso(now_utc())}})
            raise HTTPException(502, f"Stripe error: {message}")

    status = intent.get("status")
    if status != "succeeded":
        await db.jobs.update_one({"id": job_id}, {"$set": {
            "charge_payment_intent_id": intent["id"], "charge_status": status,
            "last_charge_attempt_at": iso(now_utc()),
            "last_charge_error": f"PaymentIntent returned status={status}"}})
        raise HTTPException(402, f"Charge not completed: status={status}. Customer may need to re-authenticate.")

    update = {
        "charged_at": iso(now_utc()),
        "charge_payment_intent_id": intent["id"],
        "charge_amount_cents": amount_cents,
        "charge_status": "succeeded", "charge_currency": "usd",
        "charge_card_brand": shop_user.get("card_brand"),
        "charge_card_last4": shop_user.get("card_last4"),
        "charged_by": tech["id"],
        "charge_via": "auth_capture" if used_capture else "off_session_pi",
        "updated_at": iso(now_utc()),
    }
    await db.jobs.update_one({"id": job_id}, {"$set": update,
        "$unset": {"last_charge_error": "", "last_charge_attempt_at": ""}})
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    logger.info(f"[STRIPE] Charged ${job['price']} for job {job_id} → PI {intent['id']} (capture={used_capture})")
    return {"job": fresh, "payment_intent_id": intent["id"],
            "amount_cents": amount_cents, "captured_from_hold": used_capture}


@router.post("/jobs/{job_id}/skip-charge")
async def skip_charge_job(job_id: str, tech=Depends(require_owner)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("charged_at"):
        raise HTTPException(400, "This job has already been charged")
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "charge_skipped_at": iso(now_utc()),
        "charge_skipped_by": tech["id"],
        "updated_at": iso(now_utc()),
    }})
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return fresh
