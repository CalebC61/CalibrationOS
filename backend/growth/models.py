# CalibrationOS – Module 9: Partner Growth Engine
# Power Connector 5+50+100 + Zeely-lite Reels
# FastAPI + Motor + Pydantic – matches backend/server.py
# Feature-flagged: GROWTH_MODULE_ENABLED (default true) – see backend/growth/routes.py
# v1: contacts/grid/nudges/touches/intros are real. Reels (ReelAsset) are deferred — no video
# generation capability exists yet; the model stays defined but unused/unrouted this pass.

from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta
import uuid

def gen_id() -> str: return str(uuid.uuid4())
def now_utc() -> datetime: return datetime.now(timezone.utc)
def iso(dt: datetime) -> str: return dt.isoformat()

class PartnerContact(BaseModel):
    id: str = Field(default_factory=gen_id)
    shop_id: Optional[str] = None
    first_name: str
    last_name: str
    role: Literal["owner","gm","estimator","tech","adjuster","fleet_mgr","dealer_sa","internal"] = "owner"
    company_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    ecosystem: Literal["glass_shop","collision","dealer","fleet","insurance","distributor","internal"] = "glass_shop"
    circle: Literal["top5","key50","vital100","prospect"] = "prospect"
    circle_rank: int = 999
    city: Optional[str] = None
    tags: List[str] = []
    robinett_traits: dict = Field(default_factory=lambda: {"authentic":3,"trustworthy":3,"respectful":3,"caring":3,"listening":3,"engaged":3,"patient":3,"intelligent":3,"sociable":3,"connected":3})
    favors_given: int = 0
    favors_asked: int = 0
    last_touch_at: Optional[str] = None
    next_touch_due: Optional[str] = None
    referral_count_90d: int = 0
    revenue_90d: float = 0.0
    calibration_types: List[str] = []
    is_active: bool = True
    notes: Optional[str] = None
    created_at: str = Field(default_factory=lambda: iso(now_utc()))
    updated_at: Optional[str] = None
    def robinett_score(self) -> float:
        return sum(self.robinett_traits.values())/len(self.robinett_traits) if self.robinett_traits else 3.0
    def can_ask(self) -> bool:
        return self.favors_given >= 2 and self.favors_given > self.favors_asked
    def touch_cadence_days(self) -> int:
        return {"top5":1,"key50":7,"vital100":30,"prospect":90}.get(self.circle,90)

class Touch(BaseModel):
    id: str = Field(default_factory=gen_id)
    partner_contact_id: str
    channel: Literal["sms","email","linkedin_dm","call","in_person","video_reel"] = "sms"
    direction: Literal["outbound","inbound"] = "outbound"
    template_key: str
    subject: Optional[str] = None
    body: str
    favor_delta: int = 0
    job_id: Optional[str] = None
    reel_id: Optional[str] = None
    status: Literal["draft","pending_approval","approved","sent","failed","cancelled"] = "draft"
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    sent_at: Optional[str] = None
    ai_action_log_id: Optional[str] = None
    external_message_id: Optional[str] = None
    error: Optional[str] = None
    nudge_date: Optional[str] = None  # YYYY-MM-DD; set only on auto-generated touches, for idempotency
    created_at: str = Field(default_factory=lambda: iso(now_utc()))

class Intro(BaseModel):
    id: str = Field(default_factory=gen_id)
    a_contact_id: str
    b_contact_id: str
    context: Optional[str] = None
    value_prop_a: str
    value_prop_b: str
    intro_body: str
    status: Literal["draft","pending_approval","approved","sent","accepted","declined"] = "draft"
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    sent_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: iso(now_utc()))

class ReelAsset(BaseModel):
    id: str = Field(default_factory=gen_id)
    job_id: Optional[str] = None
    shop_id: Optional[str] = None
    vehicle_label: Optional[str] = None
    calibration_type: Optional[str] = None
    type: Literal["case_study","radar_launch","testimonial","sop_tip"] = "case_study"
    script_framework: Literal["AIDA","PAS","BeforeAfterBridge","FAB","4U","3Reasons"] = "PAS"
    hook: Optional[str] = None
    script_text: str
    cta_text: str = "Book your next cal – reply CAL"
    avatar_id: Optional[str] = None
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration_sec: Optional[int] = 27
    status: Literal["script","pending_approval","rendering","ready","sent","failed"] = "script"
    sent_to_contacts: List[str] = []
    ai_action_log_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: iso(now_utc()))
    rendered_at: Optional[str] = None

GRID_CAPS = {"top5":5,"key50":50,"vital100":100,"prospect":9999}
TOUCH_CADENCE_DAYS = {"top5":1,"key50":7,"vital100":30,"prospect":90}
THREE_GOLDEN_QUESTIONS = [
    "How can I help you?",
    "What ideas do you have for me?",
    "Who else do you know that I should talk to?"
]
NURTURE_TEMPLATES = {
  "pc_favor_1_tsb": {"channel":"sms","favor_delta":1,"body_template":"Morning {first_name} – Caleb / Calibration Crew. Saw new {make} {model} {cal_type} TSB – new target board req. I'll bring updated board free next cal."},
  "pc_favor_2_value": {"channel":"email","favor_delta":1,"body_template":"Made you a 27-sec co-branded ADAS reel from yesterday's {year} {make} – OEM documented. Perfect for your Google Business."},
  "pc_3_golden_q": {"channel":"sms","favor_delta":0,"body_template":"Quick 3 Qs, {first_name}:\n1) How can I help you hit cycle time?\n2) What ideas do you have for me?\n3) Who else should I talk to?"},
  "pc_ask": {"channel":"sms","favor_delta":-1,"requires_favors":2,"body_template":"{first_name} – 2 {zone} bays open {day}. Radar/BSM cals live Aug – free first cal + lunch & learn for Key partners. Lock slots?"},
  "pc_3d_intro": {"channel":"email","favor_delta":1,"body_template":"{a_first}, meet {b_first} – {b_company}. {b_first}, {a_first} runs {a_company}. You both serve {shared_geo}. Warm intro – I'll step out."},
  "pc_radar_launch": {"channel":"sms","favor_delta":1,"body_template":"Heads up {first_name} – Calibration Crew front radar + BSM live Aug 1. Key partners: first cal free + on-site lunch & learn. Early access?"},
  "pc_checkin": {"channel":"sms","favor_delta":0,"body_template":"Hey {first_name} – pulse check. Glass volume? I have {open_bays} open bays {day}. Need a swing-by?"}
}
_DEMOTE_TO = {"top5": "key50", "key50": "vital100", "vital100": "prospect"}
_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _next_business_day_name() -> str:
    """Next Mon-Sat day name (spec: shop is closed Sundays)."""
    d = (now_utc() + timedelta(days=1)).date()
    while d.weekday() == 6:
        d += timedelta(days=1)
    return _WEEKDAY_NAMES[d.weekday()]


async def enforce_grid_caps(db):
    """Idempotent corrective sweep: repairs any circle that exceeds GRID_CAPS (e.g. from a
    direct DB edit or seed anomaly) by demoting the lowest-ranked overflow contacts one tier
    down, then re-sequencing circle_rank within each tier. Safe to call repeatedly.
    This is NOT the primary cap gate — routes.py rejects over-cap writes at request time so the
    owner explicitly chooses who moves; this function only cleans up drift."""
    for circle in ("top5", "key50", "vital100"):
        cap = GRID_CAPS[circle]
        docs = await db.partner_contacts.find(
            {"circle": circle, "is_active": True}, {"_id": 0}
        ).sort("circle_rank", 1).to_list(10000)
        if len(docs) > cap:
            keep, overflow = docs[:cap], docs[cap:]
            for rank, d in enumerate(keep, start=1):
                if d.get("circle_rank") != rank:
                    await db.partner_contacts.update_one({"id": d["id"]}, {"$set": {"circle_rank": rank}})
            target = _DEMOTE_TO[circle]
            target_count = await db.partner_contacts.count_documents({"circle": target, "is_active": True})
            for i, d in enumerate(overflow):
                target_count += 1
                await db.partner_contacts.update_one({"id": d["id"]}, {"$set": {
                    "circle": target, "circle_rank": target_count, "updated_at": iso(now_utc()),
                }})


def _pick_template_key(contact: "PartnerContact", has_recent_job: bool, has_prior_golden_q: bool) -> str:
    if contact.can_ask():
        return "pc_ask"
    if contact.favors_given == 0:
        return "pc_favor_1_tsb" if has_recent_job else "pc_checkin"
    if contact.favors_given == 1:
        return "pc_favor_2_value" if has_recent_job else "pc_checkin"
    if contact.favors_given >= 2 and not has_prior_golden_q:
        return "pc_3_golden_q"
    return "pc_checkin"


async def generate_daily_nudges(db, owner_id: str) -> int:
    """Deterministic daily nurture-touch generator (no LLM — 0 LLM deterministic enforcement per
    docs/module9/README.md). Idempotent per calendar day via the nudge_date field: repeated calls
    the same day produce zero new inserts for contacts already nudged. Returns count created."""
    today_str = now_utc().date().isoformat()
    already = set()
    async for t in db.touches.find({"nudge_date": today_str}, {"_id": 0, "partner_contact_id": 1}):
        already.add(t["partner_contact_id"])

    contacts = await db.partner_contacts.find(
        {"circle": {"$in": ["top5", "key50", "vital100"]}, "is_active": True}, {"_id": 0}
    ).to_list(200)
    day_name = _next_business_day_name()
    created = 0

    for doc in contacts:
        if doc["id"] in already:
            continue
        contact = PartnerContact(**doc)
        due = contact.last_touch_at is None
        if not due:
            last = datetime.fromisoformat(contact.last_touch_at)
            due = (now_utc() - last).days >= contact.touch_cadence_days()
        if not due:
            continue

        prior_golden_q = await db.touches.find_one(
            {"partner_contact_id": contact.id, "template_key": "pc_3_golden_q"}, {"_id": 1})

        recent_job = None
        if contact.shop_id:
            jobs = await db.jobs.find(
                {"shop_id": contact.shop_id, "status": {"$ne": "cancelled"}}, {"_id": 0}
            ).sort("scheduled_start", -1).limit(1).to_list(1)
            recent_job = jobs[0] if jobs else None

        key = _pick_template_key(contact, recent_job is not None, prior_golden_q is not None)
        tmpl = NURTURE_TEMPLATES[key]
        placeholders = {
            "first_name": contact.first_name, "last_name": contact.last_name,
            "day": day_name, "open_bays": 2,
            "zone": (recent_job or {}).get("zone", "West/East"),
            "make": (recent_job or {}).get("vehicle_make", "your"),
            "model": (recent_job or {}).get("vehicle_model", "vehicle"),
            "year": (recent_job or {}).get("vehicle_year", ""),
            "cal_type": (recent_job or {}).get("calibration_label", "calibration"),
        }
        try:
            body = tmpl["body_template"].format(**placeholders)
        except KeyError:
            continue  # template needs a placeholder we couldn't fill — skip this round

        touch = Touch(
            partner_contact_id=contact.id, channel=tmpl["channel"], template_key=key,
            body=body, favor_delta=tmpl.get("favor_delta", 0), nudge_date=today_str,
        )
        await db.touches.insert_one(touch.model_dump())
        created += 1

    return created
# End Module 9 – see backend/growth/routes.py for the API surface + docs/module9/README.md
