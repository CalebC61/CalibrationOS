"""/portal/* and /public/invites/* (terms, self-register, accept-terms, login, jobs, day-map, book)."""
import asyncio
import base64
import os
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from urllib.parse import quote

import stripe as stripe_sdk
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

import terms_service
from deps import (annotate_at_risk, db, detect_zone, gen_id,
                  get_current_shop_user, hash_password, iso, logger,
                  make_portal_token, mock_distance_matrix, mock_geocode,
                  now_utc, require_owner, verify_password,
                  _maybe_activate_shop)
from models import (BookingIn, InviteCreateIn, ShopSelfRegisterIn,
                    ShopUserLoginIn, ShopUserRegisterIn, TermsAcceptanceIn)
from routers.shops import public_book

router = APIRouter()


# ---------- Terms ----------
@router.get("/portal/terms/current")
async def get_current_terms():
    doc = await db.terms_versions.find_one({"is_current": True}, {"_id": 0})
    if not doc:
        return terms_service.current_terms()
    return doc


# ---------- Self-registration ----------
@router.post("/portal/self-register")
async def portal_self_register(body: ShopSelfRegisterIn, request: Request):
    email = body.email.lower()
    if await db.shop_users.find_one({"email": email}):
        raise HTTPException(400, "An account already exists for this email")
    geo = mock_geocode(body.shop_address)
    if not geo["in_metro"]:
        raise HTTPException(400, "Shop address is outside the Phoenix metro service area")
    zone = detect_zone(geo["lng"])
    shop_id = gen_id()
    shop_doc = {
        "id": shop_id, "name": body.shop_display_name, "legal_name": body.shop_legal_name,
        "contact_name": body.contact_full_name, "contact_phone": body.contact_phone,
        "contact_email": email, "address": body.shop_address,
        "city": body.shop_city, "state": body.shop_state, "zip": body.shop_zip,
        "lat": geo["lat"], "lng": geo["lng"], "zone": zone,
        "pricing_tier": "standard", "status": "pending",
        "booking_link_token": gen_id(),
        "onboarding": {"business_info": True, "terms_signed": False, "card_on_file": False},
        "created_via": "self_register",
        "created_at": iso(now_utc()), "updated_at": iso(now_utc()),
    }
    await db.shops.insert_one(shop_doc.copy())

    stripe_customer_id = None
    checkout_url = None
    stripe_error = None
    if stripe_sdk.api_key and not stripe_sdk.api_key.endswith("_emergent"):
        try:
            cust = await asyncio.to_thread(stripe_sdk.Customer.create,
                email=email, name=body.contact_full_name,
                metadata={"shop_id": shop_id, "source": "self_register"})
            stripe_customer_id = cust["id"]
        except Exception as e:
            stripe_error = str(e)
            logger.warning(f"[STRIPE] Customer create failed: {e}")

    user_id = gen_id()
    user_doc = {
        "id": user_id, "email": email, "full_name": body.contact_full_name,
        "password_hash": hash_password(body.password),
        "shop_id": shop_id, "shop_name": body.shop_display_name,
        "stripe_customer_id": stripe_customer_id,
        "stripe_payment_method_id": None,
        "card_brand": None, "card_last4": None, "card_exp_month": None, "card_exp_year": None,
        "auth_popup_dismissed": False, "is_active": True,
        "created_at": iso(now_utc()),
    }
    await db.shop_users.insert_one(user_doc.copy())

    origin = (os.environ.get("FRONTEND_APP_URL") or str(request.base_url)).rstrip("/")
    if stripe_customer_id:
        try:
            session = await asyncio.to_thread(stripe_sdk.checkout.Session.create,
                mode="setup", payment_method_types=["card"],
                customer=stripe_customer_id,
                success_url=f"{origin}/portal/setup-return?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{origin}/portal/setup-return?cancelled=1",
                metadata={"shop_user_id": user_id, "shop_id": shop_id})
            checkout_url = session["url"]
        except Exception as e:
            stripe_error = str(e)
            logger.warning(f"[STRIPE] Checkout setup failed: {e}")

    portal_token = make_portal_token(user_id)
    return {
        "shop_user_id": user_id, "shop_id": shop_id, "token": portal_token,
        "stripe_checkout_url": checkout_url,
        "stripe_unavailable": checkout_url is None,
        "stripe_error": stripe_error,
    }


@router.post("/portal/accept-terms")
async def accept_terms(body: TermsAcceptanceIn, request: Request, su=Depends(get_current_shop_user)):
    if not body.signature_full_name.strip():
        raise HTTPException(400, "Signature is required")
    terms = await db.terms_versions.find_one({"version": body.terms_version, "is_current": True})
    if not terms:
        raise HTTPException(400, "Terms version is not current — please refresh and re-accept")
    record = {
        "id": gen_id(), "shop_user_id": su["id"], "shop_id": su["shop_id"],
        "terms_version": body.terms_version,
        "signature_full_name": body.signature_full_name.strip(),
        "signed_at": iso(now_utc()),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    await db.terms_acceptances.insert_one(record.copy())
    await db.shop_users.update_one({"id": su["id"]}, {"$set": {
        "terms_signature": body.signature_full_name.strip(),
        "terms_signed_at": record["signed_at"],
        "terms_version_signed": body.terms_version,
    }})
    await db.shops.update_one({"id": su["shop_id"]}, {"$set": {
        "onboarding.terms_signed": True, "updated_at": iso(now_utc()),
    }})
    await _maybe_activate_shop(su["shop_id"])
    return {"accepted": True, "version": body.terms_version}


@router.post("/portal/dismiss-auth-popup")
async def dismiss_auth_popup(su=Depends(get_current_shop_user)):
    await db.shop_users.update_one({"id": su["id"]}, {"$set": {
        "auth_popup_dismissed": True,
        "auth_popup_dismissed_at": iso(now_utc()),
    }})
    return {"dismissed": True}


# ---------- Invite-based registration ----------
@router.post("/public/invites/{token}/register")
async def register_shop_user(token: str, body: ShopUserRegisterIn):
    if not body.terms_agreed:
        raise HTTPException(400, "You must agree to the terms")
    inv = await db.invites.find_one({"token": token})
    if not inv or inv["status"] != "pending" or inv["expires_at"] < iso(now_utc()):
        raise HTTPException(400, "Invitation invalid or expired")
    existing = await db.shop_users.find_one({"email": inv["recipient_email"].lower()})
    if existing:
        raise HTTPException(400, "An account already exists for this email")
    stripe_customer_id = None
    stripe_error = None
    if stripe_sdk.api_key and not stripe_sdk.api_key.endswith("_emergent"):
        try:
            cust = await asyncio.to_thread(stripe_sdk.Customer.create,
                email=inv["recipient_email"], name=body.full_name,
                metadata={"shop_id": inv["shop_id"]})
            stripe_customer_id = cust["id"]
        except Exception as e:
            stripe_error = str(e)
            logger.warning(f"Stripe customer creation skipped: {e}")
    else:
        stripe_error = "Stripe key not configured (using placeholder)"
    user_id = gen_id()
    su = {
        "id": user_id, "email": inv["recipient_email"].lower(),
        "full_name": body.full_name, "password_hash": hash_password(body.password),
        "shop_id": inv["shop_id"], "shop_name": inv["shop_name"],
        "stripe_customer_id": stripe_customer_id,
        "stripe_payment_method_id": None,
        "card_brand": None, "card_last4": None, "card_exp_month": None, "card_exp_year": None,
        "terms_signature": body.terms_signature, "terms_signed_at": iso(now_utc()),
        "is_active": True, "created_at": iso(now_utc()),
    }
    await db.shop_users.insert_one(su.copy())
    await db.invites.update_one({"token": token}, {"$set": {
        "status": "registered", "registered_at": iso(now_utc()), "shop_user_id": user_id,
    }})
    origin = (body.origin or "").rstrip("/")
    checkout_url = None
    if stripe_customer_id and origin:
        try:
            session = await asyncio.to_thread(stripe_sdk.checkout.Session.create,
                mode="setup", payment_method_types=["card"],
                customer=stripe_customer_id,
                success_url=f"{origin}/portal/setup-return?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{origin}/portal/setup-return?cancelled=1",
                metadata={"shop_user_id": user_id})
            checkout_url = session["url"]
        except Exception as e:
            logger.warning(f"Stripe Checkout setup skipped: {e}")
            stripe_error = str(e)
    token_jwt = make_portal_token(user_id)
    return {"shop_user_id": user_id, "token": token_jwt,
            "stripe_checkout_url": checkout_url,
            "stripe_unavailable": checkout_url is None,
            "stripe_error": stripe_error}


@router.get("/portal/stripe-setup-status")
async def portal_stripe_setup_status(session_id: str, su=Depends(get_current_shop_user)):
    try:
        session = await asyncio.to_thread(stripe_sdk.checkout.Session.retrieve, session_id,
            expand=["setup_intent", "setup_intent.payment_method"])
    except Exception as e:
        raise HTTPException(500, f"Could not retrieve setup session: {e}")
    setup_intent = session.get("setup_intent") or {}
    pm = setup_intent.get("payment_method") or {}
    pm_id = pm.get("id") if isinstance(pm, dict) else pm
    if not pm_id:
        return {"status": "incomplete", "session_status": session.get("status")}
    try:
        await asyncio.to_thread(stripe_sdk.Customer.modify, su["stripe_customer_id"],
            invoice_settings={"default_payment_method": pm_id})
        pm_obj = pm if isinstance(pm, dict) and pm.get("card") else \
                 await asyncio.to_thread(stripe_sdk.PaymentMethod.retrieve, pm_id)
        card = pm_obj.get("card", {}) if isinstance(pm_obj, dict) else {}
    except Exception as e:
        raise HTTPException(500, f"Could not attach payment method: {e}")
    await db.shop_users.update_one({"id": su["id"]}, {"$set": {
        "stripe_payment_method_id": pm_id,
        "card_brand": card.get("brand"), "card_last4": card.get("last4"),
        "card_exp_month": card.get("exp_month"), "card_exp_year": card.get("exp_year"),
        "updated_at": iso(now_utc()),
    }})
    await db.shops.update_one({"id": su["shop_id"]}, {"$set": {
        "onboarding.card_on_file": True, "updated_at": iso(now_utc()),
    }})
    await _maybe_activate_shop(su["shop_id"])
    fresh = await db.shop_users.find_one({"id": su["id"]}, {"_id": 0, "password_hash": 0})
    return {"status": "complete", "shop_user": fresh}


@router.post("/portal/auth/login")
async def portal_login(body: ShopUserLoginIn):
    su = await db.shop_users.find_one({"email": body.email.lower()})
    if not su or not verify_password(body.password, su.get("password_hash", "")):
        raise HTTPException(401, "Invalid email or password")
    if not su.get("is_active", True):
        raise HTTPException(403, "Account disabled")
    shop = await db.shops.find_one({"id": su["shop_id"]})
    token = make_portal_token(su["id"])
    return {"token": token, "shop_user_id": su["id"], "full_name": su["full_name"],
            "shop_name": su["shop_name"], "shop_id": su["shop_id"],
            "has_payment_method": bool(su.get("stripe_payment_method_id")),
            "auth_popup_dismissed": bool(su.get("auth_popup_dismissed", False)),
            "shop_status": (shop or {}).get("status", "pending"),
            "onboarding": (shop or {}).get("onboarding", {})}


@router.get("/portal/me")
async def portal_me(su=Depends(get_current_shop_user)):
    shop = await db.shops.find_one({"id": su["shop_id"]}, {"_id": 0})
    return {"shop_user": su, "shop": shop}


@router.get("/portal/jobs")
async def portal_jobs(su=Depends(get_current_shop_user)):
    jobs = await db.jobs.find({"shop_id": su["shop_id"]}, {"_id": 0}).sort("scheduled_start", -1).to_list(500)
    return annotate_at_risk(jobs)


@router.get("/portal/jobs/{job_id}")
async def portal_job_detail(job_id: str, su=Depends(get_current_shop_user)):
    job = await db.jobs.find_one({"id": job_id, "shop_id": su["shop_id"]}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    docs = await db.documents.find({"job_id": job_id}, {"_id": 0, "data_b64": 0}).to_list(50)
    return {"job": job, "documents": docs}


@router.get("/portal/jobs/{job_id}/documents/{doc_id}/download")
async def portal_document_download(job_id: str, doc_id: str, su=Depends(get_current_shop_user)):
    job = await db.jobs.find_one({"id": job_id, "shop_id": su["shop_id"]})
    if not job:
        raise HTTPException(404, "Job not found")
    doc = await db.documents.find_one({"id": doc_id, "job_id": job_id})
    if not doc:
        raise HTTPException(404, "Document not found")
    binary = base64.b64decode(doc["data_b64"])
    quoted = quote(doc["file_name"])
    return Response(content=binary, media_type=doc.get("content_type", "application/octet-stream"),
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"})


@router.get("/portal/day-map")
async def portal_day_map(date_str: Optional[str] = None, su=Depends(get_current_shop_user)):
    if date_str:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        d = now_utc().date()
    day_start = datetime.combine(d, time(0, 0), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    all_jobs = await db.jobs.find({
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(day_end)},
        "status": {"$ne": "cancelled"},
    }, {"_id": 0}).sort("scheduled_start", 1).to_list(500)
    shop = await db.shops.find_one({"id": su["shop_id"]})
    origin_lat = shop.get("lat") if shop else 33.4484
    origin_lng = shop.get("lng") if shop else -112.0740
    own, others = [], []
    for j in all_jobs:
        if j["shop_id"] == su["shop_id"]:
            own.append(j)
        else:
            dm = mock_distance_matrix(origin_lat, origin_lng, j["job_lat"], j["job_lng"])
            others.append({
                "id": j["id"], "scheduled_start": j["scheduled_start"],
                "scheduled_end": j["scheduled_end"], "zone": j["zone"],
                "sequence_order": j.get("sequence_order"),
                "job_lat": j["job_lat"], "job_lng": j["job_lng"],
                "drive_minutes_from_you": dm["duration_minutes"],
                "status": j["status"],
            })
    return {"own": annotate_at_risk(own), "others": others, "date": d.isoformat()}


@router.post("/portal/book")
async def portal_book(data: BookingIn, su=Depends(get_current_shop_user)):
    shop = await db.shops.find_one({"id": su["shop_id"], "status": "active"})
    if not shop:
        raise HTTPException(400, "Your shop is not active")
    data.booking_token = shop["booking_link_token"]
    return await public_book(data)
