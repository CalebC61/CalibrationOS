# CalibrationOS – Module 9: Partner Growth Engine
# Power Connector 5+50+100 + Zeely-lite Reels
# FastAPI + Motor + Pydantic – matches backend/server.py
# Feature-flagged: GROWTH_MODULE_ENABLED=false

from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime, timezone
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
async def enforce_grid_caps(db): pass
async def generate_daily_nudges(db, owner_id: str): pass
# End Module 9 – merge into server.py – see docs/module9/README.md
