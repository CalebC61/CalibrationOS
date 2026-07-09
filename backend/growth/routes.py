"""CalibrationOS – Module 9: Partner Growth Engine – API routes.

Built via a factory function so this module never imports from server.py — server.py imports
this file (backend/server.py wires it via `include_router` when GROWTH_MODULE_ENABLED is true),
so a reverse import would create a cycle. db / require_owner / mock_send_sms / send_email are
injected in from server.py's already-constructed objects instead.

v1 scope: contacts, the 5/50/100 grid, daily nurture-touch nudges, and 3-D intros — all real,
with dispatch reusing the existing mock_send_sms (SMS) / send_email (Resend-or-log) helpers.
Reels (ReelAsset) are explicitly out of scope this pass — no video-generation capability exists
yet; see docs/module9/README.md.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import timedelta

from .models import (
    PartnerContact, Touch, Intro, GRID_CAPS, NURTURE_TEMPLATES,
    gen_id, now_utc, iso, enforce_grid_caps, generate_daily_nudges,
)

CIRCLES = ("top5", "key50", "vital100", "prospect")
_CADENCE_DAYS = {"top5": 1, "key50": 7, "vital100": 30, "prospect": 90}

_Role = Literal["owner", "gm", "estimator", "tech", "adjuster", "fleet_mgr", "dealer_sa", "internal"]
_Ecosystem = Literal["glass_shop", "collision", "dealer", "fleet", "insurance", "distributor", "internal"]
_Circle = Literal["top5", "key50", "vital100", "prospect"]


class ContactCreate(BaseModel):
    shop_id: Optional[str] = None
    first_name: str
    last_name: str
    role: _Role = "owner"
    company_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    ecosystem: _Ecosystem = "glass_shop"
    circle: _Circle = "prospect"
    city: Optional[str] = None
    tags: List[str] = []
    notes: Optional[str] = None


class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[_Role] = None
    company_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    ecosystem: Optional[_Ecosystem] = None
    circle: Optional[_Circle] = None
    city: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    robinett_traits: Optional[dict] = None
    is_active: Optional[bool] = None


class IntroCreate(BaseModel):
    a_contact_id: str
    b_contact_id: str
    context: Optional[str] = None
    value_prop_a: str
    value_prop_b: str


def build_growth_router(db, require_owner, mock_send_sms, send_email) -> APIRouter:
    router = APIRouter(prefix="/growth", tags=["growth"])

    # ---------- shared helpers ----------
    async def _log_action(actor_id, action_type, target_type, target_id, channel=None,
                           status="ok", detail=None):
        await db.ai_action_log.insert_one({
            "id": gen_id(), "actor_type": "owner", "actor_id": actor_id,
            "action_type": action_type, "target_type": target_type, "target_id": target_id,
            "channel": channel, "status": status, "detail": detail,
            "created_at": iso(now_utc()),
        })

    async def _next_rank(circle: str) -> int:
        return await db.partner_contacts.count_documents({"circle": circle, "is_active": True}) + 1

    async def _check_cap(circle: str, exclude_id: Optional[str] = None):
        cap = GRID_CAPS.get(circle, 9999)
        if cap >= 9999:
            return
        q = {"circle": circle, "is_active": True}
        if exclude_id:
            q["id"] = {"$ne": exclude_id}
        count = await db.partner_contacts.count_documents(q)
        if count >= cap:
            raise HTTPException(status_code=409,
                                 detail=f"{circle} is full ({count}/{cap}) — demote or remove a contact first")

    async def _enrich_touches(touches: list) -> list:
        if not touches:
            return []
        ids = list({t["partner_contact_id"] for t in touches})
        contacts = await db.partner_contacts.find({"id": {"$in": ids}}, {"_id": 0}).to_list(len(ids))
        by_id = {c["id"]: c for c in contacts}
        return [{**t, "contact": by_id.get(t["partner_contact_id"])} for t in touches]

    # ---------- contacts ----------
    @router.get("/contacts")
    async def list_contacts(circle: Optional[str] = None, ecosystem: Optional[str] = None,
                             search: Optional[str] = None, tech=Depends(require_owner)):
        q = {}
        if circle:
            q["circle"] = circle
        if ecosystem:
            q["ecosystem"] = ecosystem
        docs = await db.partner_contacts.find(q, {"_id": 0}).to_list(2000)
        if search:
            s = search.lower()
            docs = [d for d in docs
                    if s in f"{d['first_name']} {d['last_name']} {d['company_name']}".lower()]
        order = {c: i for i, c in enumerate(CIRCLES)}
        docs.sort(key=lambda d: (order.get(d.get("circle"), 99), d.get("circle_rank", 999)))
        return docs

    @router.post("/contacts")
    async def create_contact(body: ContactCreate, tech=Depends(require_owner)):
        await _check_cap(body.circle)
        contact = PartnerContact(**body.model_dump())
        contact.circle_rank = await _next_rank(contact.circle)
        doc = contact.model_dump()
        await db.partner_contacts.insert_one(doc.copy())
        return doc

    @router.patch("/contacts/{contact_id}")
    async def update_contact(contact_id: str, body: ContactUpdate, tech=Depends(require_owner)):
        existing = await db.partner_contacts.find_one({"id": contact_id})
        if not existing:
            raise HTTPException(status_code=404, detail="Contact not found")
        update = body.model_dump(exclude_unset=True)
        if "circle" in update and update["circle"] != existing.get("circle"):
            await _check_cap(update["circle"], exclude_id=contact_id)
            update["circle_rank"] = await _next_rank(update["circle"])
        update["updated_at"] = iso(now_utc())
        await db.partner_contacts.update_one({"id": contact_id}, {"$set": update})
        return await db.partner_contacts.find_one({"id": contact_id}, {"_id": 0})

    # ---------- grid ----------
    @router.get("/grid")
    async def grid(tech=Depends(require_owner)):
        docs = await db.partner_contacts.find({"is_active": True}, {"_id": 0}).to_list(2000)
        circles = {c: [] for c in CIRCLES}
        for d in docs:
            circles.setdefault(d.get("circle", "prospect"), []).append(d)
        for c in circles:
            circles[c].sort(key=lambda d: d.get("circle_rank", 999))
        return {"caps": GRID_CAPS, "circles": circles}

    # ---------- nudges ----------
    @router.get("/nudges/today")
    async def nudges_today(tech=Depends(require_owner)):
        await generate_daily_nudges(db, tech["id"])
        today_str = now_utc().date().isoformat()
        touches = await db.touches.find(
            {"nudge_date": today_str, "status": {"$in": ["draft", "pending_approval", "approved"]}},
            {"_id": 0},
        ).sort("created_at", 1).to_list(200)
        return await _enrich_touches(touches)

    # ---------- touches ----------
    @router.get("/touches")
    async def list_touches(status: Optional[str] = None, channel: Optional[str] = None,
                            partner_contact_id: Optional[str] = None, tech=Depends(require_owner)):
        q = {}
        if status:
            q["status"] = status
        if channel:
            q["channel"] = channel
        if partner_contact_id:
            q["partner_contact_id"] = partner_contact_id
        touches = await db.touches.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
        return await _enrich_touches(touches)

    @router.post("/touches/{touch_id}/approve")
    async def approve_touch(touch_id: str, tech=Depends(require_owner)):
        touch = await db.touches.find_one({"id": touch_id})
        if not touch:
            raise HTTPException(status_code=404, detail="Touch not found")
        if touch["status"] not in ("draft", "pending_approval"):
            raise HTTPException(status_code=400,
                                 detail=f"Cannot approve a touch in status '{touch['status']}'")
        await db.touches.update_one({"id": touch_id}, {"$set": {
            "status": "approved", "approved_by": tech["id"], "approved_at": iso(now_utc()),
        }})
        await _log_action(tech["id"], "touch_approve", "touch", touch_id, channel=touch.get("channel"))
        return await db.touches.find_one({"id": touch_id}, {"_id": 0})

    async def _dispatch_touch(touch: dict, contact: dict) -> dict:
        """Real dispatch per channel. sms/email always resolve to 'sent' once attempted — the
        underlying helpers (mock_send_sms, send_email) never raise, they log-and-degrade instead.
        The only real failure case here is a missing contact detail to send to."""
        channel = touch.get("channel")
        now_iso = iso(now_utc())
        if channel == "sms":
            to = contact.get("phone")
            if not to:
                return {"status": "failed", "error": "Contact has no phone number on file"}
            await mock_send_sms(to, touch["body"], kind="growth_touch", job_id=touch.get("job_id"))
            return {"status": "sent", "sent_at": now_iso}
        if channel == "email":
            to = contact.get("email")
            if not to:
                return {"status": "failed", "error": "Contact has no email on file"}
            subject = touch.get("subject") or "A note from Calibration Crew"
            html = touch["body"].replace("\n", "<br>")
            log = await send_email(to, subject, html, kind="growth_touch", meta={"touch_id": touch["id"]})
            return {"status": "sent", "sent_at": now_iso, "external_message_id": log.get("provider_id")}
        # linkedin_dm / call / in_person / video_reel — no integration; manual/self-serve, the
        # technician does it themselves after approval, this just records that it happened.
        return {"status": "sent", "sent_at": now_iso}

    async def _apply_favor_and_cadence(contact: dict, favor_delta: int):
        update = {"last_touch_at": iso(now_utc()), "updated_at": iso(now_utc())}
        if favor_delta > 0:
            update["favors_given"] = contact.get("favors_given", 0) + favor_delta
        elif favor_delta < 0:
            update["favors_asked"] = contact.get("favors_asked", 0) + abs(favor_delta)
        cadence_days = _CADENCE_DAYS.get(contact.get("circle"), 90)
        update["next_touch_due"] = iso(now_utc() + timedelta(days=cadence_days))
        await db.partner_contacts.update_one({"id": contact["id"]}, {"$set": update})

    @router.post("/touches/{touch_id}/send")
    async def send_touch(touch_id: str, tech=Depends(require_owner)):
        touch = await db.touches.find_one({"id": touch_id})
        if not touch:
            raise HTTPException(status_code=404, detail="Touch not found")
        if touch["status"] != "approved":
            raise HTTPException(status_code=400, detail="Touch must be approved before it can be sent")
        contact = await db.partner_contacts.find_one({"id": touch["partner_contact_id"]})
        if not contact:
            raise HTTPException(status_code=404, detail="Linked contact not found")

        result = await _dispatch_touch(touch, contact)
        await db.touches.update_one({"id": touch_id}, {"$set": result})
        if result.get("status") == "sent":
            await _apply_favor_and_cadence(contact, touch.get("favor_delta", 0))
        await _log_action(tech["id"], "touch_send", "touch", touch_id,
                           channel=touch.get("channel"), status=result.get("status", "sent"))
        return await db.touches.find_one({"id": touch_id}, {"_id": 0})

    # ---------- intros ----------
    @router.get("/intros")
    async def list_intros(status: Optional[str] = None, tech=Depends(require_owner)):
        q = {"status": status} if status else {}
        return await db.intros.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)

    @router.post("/intros")
    async def create_intro(body: IntroCreate, tech=Depends(require_owner)):
        a = await db.partner_contacts.find_one({"id": body.a_contact_id}, {"_id": 0})
        b = await db.partner_contacts.find_one({"id": body.b_contact_id}, {"_id": 0})
        if not a or not b:
            raise HTTPException(status_code=404, detail="Both contacts must exist")
        shared_geo = a.get("city") or b.get("city") or "the Valley"
        intro_body = NURTURE_TEMPLATES["pc_3d_intro"]["body_template"].format(
            a_first=a["first_name"], b_first=b["first_name"],
            a_company=a["company_name"], b_company=b["company_name"], shared_geo=shared_geo,
        )
        intro = Intro(
            a_contact_id=a["id"], b_contact_id=b["id"], context=body.context,
            value_prop_a=body.value_prop_a, value_prop_b=body.value_prop_b, intro_body=intro_body,
        )
        doc = intro.model_dump()
        await db.intros.insert_one(doc.copy())
        return doc

    @router.post("/intros/{intro_id}/approve")
    async def approve_intro(intro_id: str, tech=Depends(require_owner)):
        intro = await db.intros.find_one({"id": intro_id})
        if not intro:
            raise HTTPException(status_code=404, detail="Intro not found")
        if intro["status"] not in ("draft", "pending_approval"):
            raise HTTPException(status_code=400,
                                 detail=f"Cannot approve an intro in status '{intro['status']}'")
        await db.intros.update_one({"id": intro_id}, {"$set": {
            "status": "approved", "approved_by": tech["id"], "approved_at": iso(now_utc()),
        }})
        await _log_action(tech["id"], "intro_approve", "intro", intro_id)
        return await db.intros.find_one({"id": intro_id}, {"_id": 0})

    @router.post("/intros/{intro_id}/send")
    async def send_intro(intro_id: str, tech=Depends(require_owner)):
        intro = await db.intros.find_one({"id": intro_id})
        if not intro:
            raise HTTPException(status_code=404, detail="Intro not found")
        if intro["status"] != "approved":
            raise HTTPException(status_code=400, detail="Intro must be approved before it can be sent")
        a = await db.partner_contacts.find_one({"id": intro["a_contact_id"]})
        b = await db.partner_contacts.find_one({"id": intro["b_contact_id"]})
        if not a or not b or not a.get("email") or not b.get("email"):
            raise HTTPException(status_code=400,
                                 detail="Both contacts need an email on file to send an intro")
        html = intro["intro_body"].replace("\n", "<br>")
        await send_email(a["email"], f"Introduction: {b['company_name']}", html,
                          kind="growth_intro", meta={"intro_id": intro_id})
        await send_email(b["email"], f"Introduction: {a['company_name']}", html,
                          kind="growth_intro", meta={"intro_id": intro_id})
        await db.intros.update_one({"id": intro_id}, {"$set": {
            "status": "sent", "sent_at": iso(now_utc()),
        }})
        for c in (a, b):
            await db.partner_contacts.update_one({"id": c["id"]}, {"$set": {
                "favors_given": c.get("favors_given", 0) + 1,
                "last_touch_at": iso(now_utc()), "updated_at": iso(now_utc()),
            }})
        await _log_action(tech["id"], "intro_send", "intro", intro_id)
        return await db.intros.find_one({"id": intro_id}, {"_id": 0})

    return router
