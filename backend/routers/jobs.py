"""/jobs/* endpoints (list, get, status, complete, reschedule, cancel, edit, documents)."""
from __future__ import annotations

import asyncio
import base64
import os
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from urllib.parse import quote

import stripe as stripe_sdk
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

import xero_service
from deps import (CALEB_HOME, STANDARD_PRICING, ZONES, annotate_at_risk, db,
                  detect_zone, gen_id, get_current_tech, iso, logger,
                  mock_distance_matrix, mock_geocode, mock_send_sms,
                  mock_xero_create_invoice, now_utc, require_owner,
                  shop_price_for)
from models import CancelIn, JobComplete, JobEditIn, JobStatusUpdate, RescheduleIn

router = APIRouter()


@router.get("/jobs")
async def list_jobs(date_str: Optional[str] = None, tech=Depends(get_current_tech)):
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "Invalid date")
    else:
        d = now_utc().date()
    day_start = datetime.combine(d, time(0, 0), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    q = {"scheduled_start": {"$gte": iso(day_start), "$lt": iso(day_end)}}
    if tech["role"] == "contractor":
        q["technician_id"] = tech["id"]
    jobs = await db.jobs.find(q, {"_id": 0}).sort("scheduled_start", 1).to_list(500)
    return annotate_at_risk(jobs)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, tech=Depends(get_current_tech)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    if tech["role"] == "contractor" and job.get("technician_id") != tech["id"]:
        raise HTTPException(403, "Not your job")
    return job


@router.post("/jobs/{job_id}/status")
async def update_status(job_id: str, body: JobStatusUpdate, tech=Depends(get_current_tech)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if tech["role"] == "contractor" and job.get("technician_id") != tech["id"]:
        raise HTTPException(403, "Not your job")
    update = {"status": body.status, "updated_at": iso(now_utc())}
    if body.status == "driving":
        msg = (f"Your technician is on the way to {job['job_address']}. "
               f"ETA approximately {job.get('drive_time_minutes', 20)} minutes.")
        if job.get("notification_phone"):
            await mock_send_sms(job["notification_phone"], msg, kind="on_my_way", job_id=job_id)
    elif body.status == "on_site":
        update["actual_arrival"] = iso(now_utc())
    elif body.status == "cancelled":
        msg = "Your scheduled calibration has been cancelled. Please contact us to reschedule."
        if job.get("notification_phone"):
            await mock_send_sms(job["notification_phone"], msg, kind="cancelled", job_id=job_id)
    await db.jobs.update_one({"id": job_id}, {"$set": update})
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return fresh


@router.post("/jobs/{job_id}/complete")
async def complete_job(job_id: str, body: JobComplete, tech=Depends(get_current_tech)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if tech["role"] == "contractor" and job.get("technician_id") != tech["id"]:
        raise HTTPException(403, "Not your job")

    shop = await db.shops.find_one({"id": job["shop_id"]})
    vehicle = await db.vehicles.find_one({"id": job["vehicle_id"]})

    file_name = f"{job['customer_last_name']}_{shop['name'].upper().replace(' ', '')}_{job['vehicle_make']}_{job['vehicle_model']}_{job['vehicle_year']}.pdf"
    doc = {
        "id": gen_id(), "job_id": job_id, "file_name": file_name,
        "storage_path": f"calibration-docs/Recals/Recal - Caleb/{datetime.fromisoformat(job['scheduled_start']).strftime('%Y/%B')}/{file_name}",
        "file_type": "pdf", "uploaded_at": iso(now_utc()), "uploaded_by": tech["id"],
    }
    await db.documents.insert_one(doc.copy())

    pricing_label = STANDARD_PRICING[job["calibration_type"]]["label"]
    xero_token = await db.xero_tokens.find_one({"owner_id": tech["id"]}, {"owner_id": 1})
    if not xero_token:
        xero_token = await db.xero_tokens.find_one({}, {"owner_id": 1})

    xero_invoice = None
    if xero_token:
        try:
            creds = await xero_service.get_valid_credentials(db, xero_token["owner_id"])
            contact_id = shop.get("xero_contact_id")
            if not contact_id:
                contact_id = await xero_service.find_or_create_contact(creds, shop)
                await db.shops.update_one({"id": shop["id"]}, {"$set": {"xero_contact_id": contact_id}})
            xero_invoice = await xero_service.create_invoice(
                creds, contact_id=contact_id, job=job, line_label=pricing_label
            )
            logger.info(f"[XERO] Auto-pushed invoice for job {job_id} → {xero_invoice['invoice_number']}")
        except Exception as e:
            logger.warning(f"[XERO] Auto-push failed for job {job_id}: {e}; falling back to mock")

    if xero_invoice:
        invoice_update = {
            "xero_invoice_id": xero_invoice["invoice_id"],
            "xero_invoice_number": xero_invoice["invoice_number"],
            "invoice_id": xero_invoice["invoice_number"] or xero_invoice["invoice_id"],
            "invoice_status": (xero_invoice["status"] or "").lower(),
            "invoice_amount_due": xero_invoice.get("amount_due"),
            "invoice_amount_paid": xero_invoice.get("amount_paid"),
            "invoice_online_url": xero_invoice.get("online_url"),
        }
    else:
        mock_invoice = await mock_xero_create_invoice(job, shop, vehicle, pricing_label)
        invoice_update = {"invoice_id": mock_invoice["invoice_id"], "invoice_status": "draft"}

    update = {
        "status": "complete",
        "actual_completion": iso(now_utc()),
        "result": body.result,
        "notes": body.notes,
        **invoice_update,
        "updated_at": iso(now_utc()),
    }
    await db.jobs.update_one({"id": job_id}, {"$set": update})

    msg = (f"ADAS calibration complete on your {job['vehicle_year']} {job['vehicle_make']} {job['vehicle_model']}. "
           f"Documentation will be included with your invoice. — The Calibration Crew")
    if job.get("notification_phone"):
        await mock_send_sms(job["notification_phone"], msg, kind="completed", job_id=job_id)

    inv_display = invoice_update.get("invoice_id") or invoice_update.get("xero_invoice_number") or "—"
    await db.admin_notifications.insert_one({
        "id": gen_id(),
        "subject": f"New Invoice Created — {shop['name']} — {job['vehicle_year']} {job['vehicle_make']} {job['vehicle_model']}",
        "body": f"Invoice {inv_display} created for {shop['name']} — ${job['price']}.",
        "to": os.environ.get("ADMIN_EMAIL", "admin@thecalibrationcrew.us"),
        "sent_at": iso(now_utc()),
    })

    # Auto-charge (best effort)
    charge_result = None
    if (stripe_sdk.api_key and not stripe_sdk.api_key.endswith("_emergent")
            and not job.get("charged_at")):
        try:
            shop_user = await db.shop_users.find_one({
                "shop_id": job["shop_id"],
                "stripe_payment_method_id": {"$ne": None},
            })
            if shop_user:
                amount_cents = int(round(float(job["price"]) * 100))
                auth_pi_id = job.get("stripe_auth_intent_id")
                intent = None
                used_capture = False
                if auth_pi_id:
                    try:
                        existing = await asyncio.to_thread(stripe_sdk.PaymentIntent.retrieve, auth_pi_id)
                        if existing.get("status") == "requires_capture":
                            cap = min(amount_cents, existing.get("amount_capturable") or amount_cents)
                            intent = await asyncio.to_thread(stripe_sdk.PaymentIntent.capture, auth_pi_id, amount_to_capture=cap)
                            used_capture = True
                        elif existing.get("status") == "succeeded":
                            intent = existing
                            used_capture = True
                    except stripe_sdk.error.StripeError as e:
                        logger.warning(f"[STRIPE] Auto-charge: hold capture failed for {auth_pi_id}: {e}")
                if intent is None:
                    intent = await asyncio.to_thread(
                        stripe_sdk.PaymentIntent.create,
                        amount=amount_cents, currency="usd",
                        customer=shop_user["stripe_customer_id"],
                        payment_method=shop_user["stripe_payment_method_id"],
                        off_session=True, confirm=True,
                        description=f"Calibration {job.get('calibration_label','')} — {job.get('vehicle_year','')} {job.get('vehicle_make','')} {job.get('vehicle_model','')}",
                        metadata={"job_id": job_id, "shop_id": job["shop_id"], "auto_charge": "true"},
                    )
                if intent.get("status") == "succeeded":
                    await db.jobs.update_one({"id": job_id}, {"$set": {
                        "charged_at": iso(now_utc()),
                        "charge_payment_intent_id": intent["id"],
                        "charge_amount_cents": amount_cents,
                        "charge_status": "succeeded",
                        "charge_currency": "usd",
                        "charge_card_brand": shop_user.get("card_brand"),
                        "charge_card_last4": shop_user.get("card_last4"),
                        "charged_by": tech["id"],
                        "charge_via": "auto_capture" if used_capture else "auto_off_session",
                    }})
                    charge_result = {"succeeded": True, "amount_cents": amount_cents,
                                     "payment_intent_id": intent["id"],
                                     "captured_from_hold": used_capture}
                    logger.info(f"[STRIPE] Auto-charged ${job['price']} on completion of job {job_id}")
                else:
                    charge_result = {"succeeded": False,
                                     "error": f"PaymentIntent status={intent.get('status')}"}
        except stripe_sdk.error.CardError as e:
            charge_result = {"succeeded": False, "error": f"Card declined: {getattr(e, 'user_message', str(e))}"}
            await db.jobs.update_one({"id": job_id}, {"$set": {
                "last_charge_error": charge_result["error"],
                "last_charge_attempt_at": iso(now_utc()),
            }})
        except Exception as e:
            charge_result = {"succeeded": False, "error": str(e)[:300]}
            logger.warning(f"[STRIPE] Auto-charge failed for job {job_id}: {e}")

    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return {"job": fresh, "invoice": invoice_update, "document": doc, "charge": charge_result}


@router.post("/jobs/{job_id}/reschedule")
async def reschedule_job(job_id: str, body: RescheduleIn, tech=Depends(require_owner)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] in ("complete", "cancelled"):
        raise HTTPException(400, f"Cannot reschedule a {job['status']} job")
    try:
        new_start = datetime.fromisoformat(body.scheduled_start.replace("Z", "+00:00"))
        if new_start.tzinfo is None:
            new_start = new_start.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(400, "Invalid scheduled_start")
    z = ZONES[job["zone"]]
    new_end = new_start + timedelta(minutes=z["slot_minutes"])
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "scheduled_start": iso(new_start),
        "scheduled_end": iso(new_end),
        "reschedule_reason": body.reason,
        "rescheduled_at": iso(now_utc()),
        "updated_at": iso(now_utc()),
    }})
    if job.get("notification_phone"):
        msg = (f"Your calibration appointment has been rescheduled to "
               f"{new_start.strftime('%a %b %d at %-I:%M %p')}. "
               f"Reply if this doesn't work for you. — The Calibration Crew")
        await mock_send_sms(job["notification_phone"], msg, kind="rescheduled", job_id=job_id)
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return fresh


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, body: CancelIn, tech=Depends(require_owner)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] in ("complete", "cancelled"):
        raise HTTPException(400, f"Already {job['status']}")
    auth_pi = job.get("stripe_auth_intent_id")
    if auth_pi and stripe_sdk.api_key and not stripe_sdk.api_key.endswith("_emergent"):
        try:
            existing = await asyncio.to_thread(stripe_sdk.PaymentIntent.retrieve, auth_pi)
            if existing.get("status") == "requires_capture":
                await asyncio.to_thread(stripe_sdk.PaymentIntent.cancel, auth_pi)
                logger.info(f"[STRIPE] Released auth hold {auth_pi} on cancellation of job {job_id}")
        except Exception as e:
            logger.warning(f"[STRIPE] Could not release hold {auth_pi}: {e}")
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "status": "cancelled",
        "cancellation_reason": body.reason,
        "cancelled_at": iso(now_utc()),
        "updated_at": iso(now_utc()),
    }})
    if job.get("notification_phone"):
        reason_suffix = f" Reason: {body.reason}" if body.reason else ""
        msg = f"Your scheduled calibration has been cancelled.{reason_suffix} Please contact us to reschedule."
        await mock_send_sms(job["notification_phone"], msg, kind="cancelled", job_id=job_id)
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return fresh


@router.patch("/jobs/{job_id}")
async def edit_job(job_id: str, body: JobEditIn, tech=Depends(require_owner)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] in ("complete", "cancelled"):
        raise HTTPException(400, f"Cannot edit a {job['status']} job")
    data = body.model_dump(exclude_unset=True)
    update: dict = {}
    if "customer_last_name" in data: update["customer_last_name"] = data["customer_last_name"]
    if "vehicle_year" in data: update["vehicle_year"] = data["vehicle_year"]
    if "vehicle_make" in data: update["vehicle_make"] = data["vehicle_make"]
    if "vehicle_model" in data: update["vehicle_model"] = data["vehicle_model"]
    if "vehicle_vin" in data: update["vehicle_vin"] = data["vehicle_vin"]
    vehicle_update = {}
    for k_src, k_dst in [("vehicle_year", "year"), ("vehicle_make", "make"),
                         ("vehicle_model", "model"), ("vehicle_vin", "vin"),
                         ("vehicle_trim", "trim"), ("customer_last_name", "customer_last_name"),
                         ("adas_system", "adas_system")]:
        if k_src in data:
            vehicle_update[k_dst] = data[k_src]
    if vehicle_update and job.get("vehicle_id"):
        await db.vehicles.update_one({"id": job["vehicle_id"]}, {"$set": vehicle_update})
    if "calibration_type" in data:
        ct = data["calibration_type"]
        update["calibration_type"] = ct
        update["calibration_label"] = STANDARD_PRICING[ct]["label"]
        if "price" not in data:
            shop = await db.shops.find_one({"id": job["shop_id"]})
            if shop:
                update["price"] = shop_price_for(shop, ct)
    if "price" in data and data["price"] is not None:
        update["price"] = float(data["price"])
    if "notification_phone" in data: update["notification_phone"] = data["notification_phone"]
    if "notification_email" in data: update["notification_email"] = data["notification_email"]
    if "notes" in data: update["notes"] = data["notes"]
    if "job_address" in data and data["job_address"] and data["job_address"] != job["job_address"]:
        geo = mock_geocode(data["job_address"])
        if not geo["in_metro"]:
            raise HTTPException(400, "Address is outside the service area")
        new_zone = detect_zone(geo["lng"])
        update["job_address"] = data["job_address"]
        update["job_lat"] = geo["lat"]; update["job_lng"] = geo["lng"]
        update["zone"] = new_zone
        start_dt = datetime.fromisoformat(job["scheduled_start"])
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        day_start = datetime.combine(start_dt.date(), time(0, 0), tzinfo=timezone.utc)
        prev = await db.jobs.find({
            "zone": new_zone, "id": {"$ne": job_id},
            "scheduled_start": {"$gte": iso(day_start), "$lt": iso(start_dt)},
            "status": {"$nin": ["cancelled"]},
        }, {"_id": 0}).sort("scheduled_start", -1).limit(1).to_list(1)
        if prev:
            o = (prev[0]["job_lat"], prev[0]["job_lng"])
        else:
            o = (CALEB_HOME["lat"], CALEB_HOME["lng"])
        dm = mock_distance_matrix(o[0], o[1], geo["lat"], geo["lng"])
        update["drive_time_minutes"] = dm["duration_minutes"]
    if "scheduled_start" in data and data["scheduled_start"]:
        try:
            new_start = datetime.fromisoformat(data["scheduled_start"].replace("Z", "+00:00"))
            if new_start.tzinfo is None:
                new_start = new_start.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(400, "Invalid scheduled_start")
        z_key = update.get("zone", job["zone"])
        slot_min = ZONES[z_key]["slot_minutes"]
        update["scheduled_start"] = iso(new_start)
        update["scheduled_end"] = iso(new_start + timedelta(minutes=slot_min))
    if not update:
        fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
        return fresh
    update["updated_at"] = iso(now_utc())
    await db.jobs.update_one({"id": job_id}, {"$set": update})
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return fresh


@router.post("/jobs/{job_id}/upload-document")
async def upload_document(job_id: str, file: UploadFile = File(...), tech=Depends(get_current_tech)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if tech["role"] == "contractor" and job.get("technician_id") != tech["id"]:
        raise HTTPException(403, "Not your job")
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 10 MB)")
    shop = await db.shops.find_one({"id": job["shop_id"]})
    file_name = file.filename or "calibration_report"
    ext = (file_name.rsplit(".", 1)[-1] if "." in file_name else "pdf").lower()
    spec_name = (f"{job['customer_last_name']}_{shop['name'].upper().replace(' ', '')}_"
                 f"{job['vehicle_make']}_{job['vehicle_model']}_{job['vehicle_year']}.{ext}")
    doc = {
        "id": gen_id(),
        "job_id": job_id,
        "file_name": spec_name,
        "original_name": file_name,
        "content_type": file.content_type or "application/octet-stream",
        "size_bytes": len(contents),
        "data_b64": base64.b64encode(contents).decode(),
        "uploaded_at": iso(now_utc()),
        "uploaded_by": tech["id"],
        "storage_path": f"calibration-docs/Recals/Recal - {tech['name']}/{datetime.fromisoformat(job['scheduled_start']).strftime('%Y/%B')}/{spec_name}",
    }
    await db.documents.insert_one(doc.copy())
    return {k: v for k, v in doc.items() if k != "data_b64"}


@router.get("/jobs/{job_id}/documents")
async def list_job_documents(job_id: str, tech=Depends(get_current_tech)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if tech["role"] == "contractor" and job.get("technician_id") != tech["id"]:
        raise HTTPException(403, "Not your job")
    docs = await db.documents.find({"job_id": job_id}, {"_id": 0, "data_b64": 0}).to_list(50)
    return docs


@router.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, tech=Depends(get_current_tech)):
    doc = await db.documents.find_one({"id": doc_id})
    if not doc or "data_b64" not in doc:
        raise HTTPException(404, "Document not found")
    if tech["role"] == "contractor":
        job = await db.jobs.find_one({"id": doc["job_id"]})
        if not job or job.get("technician_id") != tech["id"]:
            raise HTTPException(403, "Not your document")
    binary = base64.b64decode(doc["data_b64"])
    quoted = quote(doc["file_name"])
    return Response(content=binary, media_type=doc.get("content_type", "application/octet-stream"),
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"})
