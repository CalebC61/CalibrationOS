"""/xero/* endpoints."""
import os
import secrets
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

import xero_service
from deps import (STANDARD_PRICING, db, iso, logger, now_utc, require_owner)

router = APIRouter()


@router.get("/xero/status")
async def xero_status(tech=Depends(require_owner)):
    doc = await db.xero_tokens.find_one({"owner_id": tech["id"]})
    if not doc:
        return {"connected": False, "tenant_id": None, "org_name": None, "expires_at": None}
    return {
        "connected": True, "tenant_id": doc["tenant_id"],
        "org_name": doc.get("org_name"), "expires_at": doc.get("expires_at"),
        "scope": doc.get("scope"),
    }


@router.get("/xero/auth/start")
async def xero_auth_start(tech=Depends(require_owner)):
    state = secrets.token_urlsafe(24)
    await db.xero_oauth_state.update_one(
        {"owner_id": tech["id"]},
        {"$set": {"owner_id": tech["id"], "state": state, "created_at": iso(now_utc())}},
        upsert=True,
    )
    return {"authorize_url": xero_service.build_authorize_url(state)}


@router.get("/xero/auth/callback")
async def xero_auth_callback(code: Optional[str] = None, state: Optional[str] = None,
                              error: Optional[str] = None):
    frontend = os.environ.get("FRONTEND_APP_URL", "/").rstrip("/")
    if error:
        return RedirectResponse(f"{frontend}/settings?xero=error&detail={error}")
    if not code or not state:
        raise HTTPException(400, "Missing code or state")
    state_doc = await db.xero_oauth_state.find_one({"state": state})
    if not state_doc:
        raise HTTPException(400, "Invalid OAuth state")
    owner_id = state_doc["owner_id"]
    await db.xero_oauth_state.delete_many({"owner_id": owner_id})
    td = await xero_service.exchange_code_for_tokens(code)
    access_token = td["access_token"]
    refresh_token = td.get("refresh_token")
    expires_in = td.get("expires_in", 1800)
    expires_at = (now_utc() + timedelta(seconds=expires_in)).isoformat()
    tenants = await xero_service.fetch_tenants(access_token)
    if not tenants:
        return RedirectResponse(f"{frontend}/settings?xero=error&detail=no_tenants")
    tenant = tenants[0]
    tenant_id = tenant["tenantId"]
    try:
        org = await xero_service.fetch_organisation(access_token, tenant_id)
        org_name = org.get("Name") or tenant.get("tenantName")
    except Exception:
        org_name = tenant.get("tenantName")
    await db.xero_tokens.update_one(
        {"owner_id": owner_id},
        {"$set": {
            "owner_id": owner_id, "access_token": access_token,
            "refresh_token": refresh_token, "expires_at": expires_at,
            "scope": td.get("scope"), "token_type": td.get("token_type", "Bearer"),
            "tenant_id": tenant_id, "org_name": org_name,
            "updated_at": iso(now_utc()),
        }, "$setOnInsert": {"created_at": iso(now_utc())}},
        upsert=True,
    )
    logger.info(f"[XERO] Connected owner {owner_id} → tenant {tenant_id} ({org_name})")
    return RedirectResponse(f"{frontend}/settings?xero=connected")


@router.post("/xero/disconnect")
async def xero_disconnect(tech=Depends(require_owner)):
    doc = await db.xero_tokens.find_one({"owner_id": tech["id"]})
    if doc and doc.get("refresh_token"):
        await xero_service.revoke_refresh_token(doc["refresh_token"])
    await db.xero_tokens.delete_one({"owner_id": tech["id"]})
    return {"disconnected": True}


@router.post("/xero/jobs/{job_id}/push-invoice")
async def xero_push_invoice(job_id: str, tech=Depends(require_owner)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("xero_invoice_id"):
        creds = await xero_service.get_valid_credentials(db, tech["id"])
        info = await xero_service.fetch_invoice(creds, job["xero_invoice_id"])
        await db.jobs.update_one({"id": job_id}, {"$set": {
            "invoice_status": (info["status"] or "").lower(),
            "invoice_amount_due": info.get("amount_due"),
            "invoice_amount_paid": info.get("amount_paid"),
            "updated_at": iso(now_utc())}})
        return {"job_id": job_id, **info, "already_existed": True}
    shop = await db.shops.find_one({"id": job["shop_id"]})
    if not shop:
        raise HTTPException(400, "Shop not found for job")
    creds = await xero_service.get_valid_credentials(db, tech["id"])
    contact_id = shop.get("xero_contact_id")
    if not contact_id:
        contact_id = await xero_service.find_or_create_contact(creds, shop)
        await db.shops.update_one({"id": shop["id"]}, {"$set": {"xero_contact_id": contact_id}})
    pricing_label = STANDARD_PRICING[job["calibration_type"]]["label"]
    info = await xero_service.create_invoice(creds, contact_id=contact_id, job=job, line_label=pricing_label)
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "xero_invoice_id": info["invoice_id"],
        "xero_invoice_number": info["invoice_number"],
        "invoice_id": info["invoice_number"] or info["invoice_id"],
        "invoice_status": (info["status"] or "").lower(),
        "invoice_amount_due": info.get("amount_due"),
        "invoice_amount_paid": info.get("amount_paid"),
        "invoice_online_url": info.get("online_url"),
        "updated_at": iso(now_utc())}})
    logger.info(f"[XERO] Pushed invoice for job {job_id} → {info['invoice_number']} ({info['status']})")
    return {"job_id": job_id, **info, "already_existed": False}


@router.post("/xero/jobs/{job_id}/refresh-status")
async def xero_refresh_invoice_status(job_id: str, tech=Depends(require_owner)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    inv_id = job.get("xero_invoice_id")
    if not inv_id:
        raise HTTPException(400, "Job has no Xero invoice yet — push it first")
    creds = await xero_service.get_valid_credentials(db, tech["id"])
    info = await xero_service.fetch_invoice(creds, inv_id)
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "invoice_status": (info["status"] or "").lower(),
        "invoice_amount_due": info.get("amount_due"),
        "invoice_amount_paid": info.get("amount_paid"),
        "updated_at": iso(now_utc())}})
    return {"job_id": job_id, **info}


@router.post("/xero/refresh-all")
async def xero_refresh_all(tech=Depends(require_owner)):
    jobs = await db.jobs.find({
        "xero_invoice_id": {"$exists": True, "$ne": None},
        "invoice_status": {"$nin": ["paid", "voided"]},
    }, {"_id": 0, "id": 1, "xero_invoice_id": 1}).to_list(500)
    if not jobs:
        return {"refreshed": 0}
    creds = await xero_service.get_valid_credentials(db, tech["id"])
    n = 0
    for j in jobs:
        try:
            info = await xero_service.fetch_invoice(creds, j["xero_invoice_id"])
            await db.jobs.update_one({"id": j["id"]}, {"$set": {
                "invoice_status": (info["status"] or "").lower(),
                "invoice_amount_due": info.get("amount_due"),
                "invoice_amount_paid": info.get("amount_paid"),
                "updated_at": iso(now_utc())}})
            n += 1
        except HTTPException as e:
            logger.warning(f"[XERO] Refresh job {j['id']} failed: {e.detail}")
    return {"refreshed": n, "total": len(jobs)}
