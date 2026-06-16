"""Owner administrative endpoints: dashboard, settings, notifications, invoices, sms-log, invites, contractors, public-status."""
import secrets
from datetime import datetime, time, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from deps import (STANDARD_PRICING, ZONES, annotate_at_risk, db, gen_id, iso,
                  logger, mock_geocode, now_utc, require_owner, save_pricing,
                  save_zones, send_email)
from models import (ContractorUpdate, InviteCreateIn, PricingUpdate, ZoneUpdate)

router = APIRouter()


# ---------- Dashboard summary ----------
@router.get("/dashboard/summary")
async def dashboard_summary(date_str: Optional[str] = None, tech=Depends(require_owner)):
    if date_str:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        d = now_utc().date()
    day_start = datetime.combine(d, time(0, 0), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    jobs = await db.jobs.find({
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(day_end)},
        "status": {"$ne": "cancelled"},
    }, {"_id": 0}).to_list(500)
    revenue = sum(j["price"] for j in jobs)
    drive_min = sum((j.get("drive_time_minutes") or 0) for j in jobs)
    miles = round(drive_min * 0.5, 1)
    done_by = max((j["scheduled_end"] for j in jobs), default=None)
    annotated = annotate_at_risk(jobs)
    at_risk = sum(1 for j in annotated if j["is_at_risk"])
    return {
        "date": d.isoformat(), "job_count": len(jobs),
        "revenue": revenue, "estimated_miles": miles,
        "done_by": done_by, "at_risk_count": at_risk,
    }


# ---------- Public shop status ----------
@router.get("/public/shop-status/{token}")
async def public_shop_status(token: str):
    shop = await db.shops.find_one({"booking_link_token": token, "status": "active"}, {"_id": 0})
    if not shop:
        raise HTTPException(404, "Shop not found or link inactive")
    cutoff = iso(now_utc() - timedelta(days=30))
    jobs = await db.jobs.find(
        {"shop_id": shop["id"], "scheduled_start": {"$gte": cutoff}},
        {"_id": 0, "id": 1, "scheduled_start": 1, "scheduled_end": 1, "status": 1,
         "calibration_label": 1, "price": 1, "vehicle_year": 1, "vehicle_make": 1,
         "vehicle_model": 1, "customer_last_name": 1, "actual_completion": 1, "result": 1}
    ).sort("scheduled_start", -1).limit(50).to_list(50)
    completed = [j for j in jobs if j["status"] == "complete"]
    upcoming = [j for j in jobs if j["status"] in ("booked", "driving", "on_site", "dispatched_to_contractor")]
    total_spent = sum(j["price"] for j in completed)
    return {
        "shop_name": shop["name"], "shop_address": shop["address"],
        "zone": shop["zone"], "booking_link": shop["booking_link_token"],
        "stats": {
            "jobs_last_30_days": len(jobs),
            "completed_count": len(completed),
            "upcoming_count": len(upcoming),
            "total_spent_last_30_days": total_spent,
            "last_completion": completed[0]["actual_completion"] if completed else None,
        },
        "upcoming": upcoming, "completed": completed,
    }


# ---------- SMS / Email / Invoice logs ----------
@router.get("/sms-log")
async def sms_log(limit: int = 50, tech=Depends(require_owner)):
    return await db.sms_log.find({}, {"_id": 0}).sort("sent_at", -1).limit(limit).to_list(limit)


@router.get("/email-log")
async def email_log(tech=Depends(require_owner)):
    logs = await db.email_log.find({}, {"_id": 0}).sort("sent_at", -1).limit(100).to_list(100)
    pending = await db.admin_notifications.find(
        {"subject": {"$regex": "^\\[MANUAL SEND\\]"}}, {"_id": 0}
    ).sort("sent_at", -1).limit(50).to_list(50)
    return {"sent": logs, "pending_manual": pending}


@router.get("/invoices")
async def list_invoices(tech=Depends(require_owner)):
    return await db.mock_xero_invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


# ---------- New-booking alerts ----------
@router.get("/notifications/new-bookings")
async def new_booking_alerts(tech=Depends(require_owner)):
    alerts = await db.new_booking_alerts.find(
        {"owner_id": tech["id"], "seen_at": None}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return {"count": len(alerts), "alerts": alerts}


@router.post("/notifications/mark-seen")
async def mark_alerts_seen(tech=Depends(require_owner)):
    now = iso(now_utc())
    res = await db.new_booking_alerts.update_many(
        {"owner_id": tech["id"], "seen_at": None}, {"$set": {"seen_at": now}})
    return {"marked": res.modified_count}


# ---------- Settings ----------
@router.put("/settings/pricing")
async def update_pricing(body: PricingUpdate, tech=Depends(require_owner)):
    d = body.model_dump(exclude_unset=True)
    for k, v in d.items():
        if k in STANDARD_PRICING and v is not None:
            STANDARD_PRICING[k]["price"] = float(v)
    await save_pricing()
    return [{"calibration_type": k, **v} for k, v in STANDARD_PRICING.items()]


@router.put("/settings/zones/{zone_key}")
async def update_zone(zone_key: str, body: ZoneUpdate, tech=Depends(require_owner)):
    if zone_key not in ZONES:
        raise HTTPException(404, "Zone not found")
    d = body.model_dump(exclude_unset=True)
    for k, v in d.items():
        if k in ZONES[zone_key] and v is not None:
            ZONES[zone_key][k] = v
    await save_zones()
    return list(ZONES.values())


@router.put("/contractors/{contractor_id}")
async def update_contractor(contractor_id: str, body: ContractorUpdate, tech=Depends(require_owner)):
    c = await db.technicians.find_one({"id": contractor_id, "role": "contractor"})
    if not c:
        raise HTTPException(404, "Contractor not found")
    update = body.model_dump(exclude_unset=True)
    if "home_address" in update and update["home_address"]:
        geo = mock_geocode(update["home_address"])
        update["home_lat"] = geo["lat"]; update["home_lng"] = geo["lng"]
    update["updated_at"] = iso(now_utc())
    await db.technicians.update_one({"id": contractor_id}, {"$set": update})
    return await db.technicians.find_one({"id": contractor_id}, {"_id": 0, "password_hash": 0})


# ---------- Invites ----------
def _invite_email_html(shop_name: str, register_url: str) -> str:
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#2A2E37;color:#f5f5f5;font-family:'DM Sans',Arial,sans-serif;padding:40px 0;">
      <tr><td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="background:#343843;border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:32px;">
          <tr><td>
            <div style="font-family:'Saira Stencil One','Courier New',monospace;font-size:28px;letter-spacing:0.04em;color:#F97316;margin:0 0 8px;">CALIBRATION<span style="background:#F97316;color:#2A2E37;padding:2px 8px;margin-left:6px;border-radius:2px;">OS</span></div>
            <p style="color:#9CA0AB;font-size:11px;letter-spacing:0.18em;text-transform:uppercase;margin:0 0 24px;font-weight:600;">By The Calibration Crew · Shop Portal Invitation</p>
            <h2 style="font-family:'Saira Stencil One','Courier New',monospace;font-size:22px;margin:0 0 12px;letter-spacing:0.02em;">{shop_name}, YOU&rsquo;RE INVITED.</h2>
            <p style="color:#c4c4c4;line-height:1.6;font-size:15px;">The Calibration Crew has set up a dedicated portal for your shop.</p>
            <p style="text-align:center;margin:32px 0;">
              <a href="{register_url}" style="background:#F97316;color:#2A2E37;text-decoration:none;padding:14px 28px;border-radius:8px;font-weight:700;display:inline-block;font-family:'Saira Stencil One','Courier New',monospace;letter-spacing:0.06em;">REGISTER NOW &rarr;</a>
            </p>
            <p style="color:#6B7280;font-size:12px;">This link expires in 14 days. Questions? Reply to this email.</p>
          </td></tr>
        </table>
      </td></tr>
    </table>
    """


@router.post("/invites")
async def create_invite(body: InviteCreateIn, tech=Depends(require_owner)):
    shop = await db.shops.find_one({"id": body.shop_id})
    if not shop:
        raise HTTPException(404, "Shop not found")
    token = secrets.token_urlsafe(24)
    invite = {
        "id": gen_id(), "shop_id": body.shop_id, "shop_name": shop["name"],
        "recipient_email": body.recipient_email, "token": token,
        "status": "pending",
        "created_at": iso(now_utc()),
        "expires_at": iso(now_utc() + timedelta(days=14)),
        "registered_at": None, "shop_user_id": None,
    }
    await db.invites.insert_one(invite.copy())
    origin = (body.origin or "").rstrip("/")
    register_url = f"{origin}/portal/invite/{token}" if origin else f"/portal/invite/{token}"
    await send_email(
        to=body.recipient_email,
        subject=f"You're invited to the CalibrationOS Shop Portal — {shop['name']}",
        html=_invite_email_html(shop["name"], register_url),
        kind="invite", meta={"invite_id": invite["id"], "shop_id": shop["id"]},
    )
    return {**invite, "register_url": register_url}


@router.get("/invites")
async def list_invites(tech=Depends(require_owner)):
    return await db.invites.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.get("/public/invites/{token}")
async def public_invite_lookup(token: str):
    inv = await db.invites.find_one({"token": token}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invitation not found")
    if inv["status"] != "pending":
        raise HTTPException(400, f"Invitation already {inv['status']}")
    if inv["expires_at"] < iso(now_utc()):
        raise HTTPException(400, "Invitation expired")
    shop = await db.shops.find_one({"id": inv["shop_id"]},
        {"_id": 0, "name": 1, "address": 1, "contact_phone": 1})
    return {**inv, "shop": shop}
