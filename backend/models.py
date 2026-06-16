"""All Pydantic input/output models."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    token: str
    role: str
    name: str
    tech_id: str


class ShopIn(BaseModel):
    name: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    address: str
    city: Optional[str] = None
    state: str = "AZ"
    zip: Optional[str] = None
    pricing_tier: Literal["standard", "custom"] = "standard"
    custom_rate_static: Optional[float] = None
    custom_rate_dynamic: Optional[float] = None
    custom_rate_dual: Optional[float] = None
    custom_rate_triple: Optional[float] = None
    custom_rate_tesla: Optional[float] = None
    notes: Optional[str] = None
    terms_signed_by: Optional[str] = None


class ShopUpdate(ShopIn):
    status: Optional[Literal["active", "paused", "inactive"]] = None


class SlotQuery(BaseModel):
    booking_token: str
    job_address: str
    date: str  # YYYY-MM-DD


class BookingIn(BaseModel):
    booking_token: str
    job_address: str
    scheduled_start: str
    customer_last_name: str
    year: int
    make: str
    model: str
    trim: Optional[str] = None
    vin: Optional[str] = None
    adas_system: Literal["forward_camera", "surround_view", "radar", "multi_camera", "tesla", "other"]
    calibration_type: Literal["static", "dynamic", "dual", "triple", "tesla"]
    notification_phone: Optional[str] = None
    notification_email: Optional[str] = None
    job_type: Optional[Literal["cash", "insurance"]] = "cash"
    insurance_approved_amount: Optional[float] = None


class ShopSelfRegisterIn(BaseModel):
    shop_legal_name: str
    shop_display_name: str
    contact_full_name: str
    email: EmailStr
    password: str
    contact_phone: str
    shop_address: str
    shop_city: Optional[str] = None
    shop_state: str = "AZ"
    shop_zip: Optional[str] = None


class TermsAcceptanceIn(BaseModel):
    terms_version: str
    signature_full_name: str


class JobStatusUpdate(BaseModel):
    status: Literal["driving", "on_site", "complete", "cancelled"]


class JobComplete(BaseModel):
    result: Literal["pass", "fail"]
    notes: Optional[str] = None
    document_name: Optional[str] = "calibration_report.pdf"


class DispatchIn(BaseModel):
    contractor_id: str


class OfferResponseIn(BaseModel):
    accept: bool


class ReorderIn(BaseModel):
    zone: Literal["west", "east"]
    date: str
    ordered_job_ids: List[str]


class PricingUpdate(BaseModel):
    static: Optional[float] = None
    dynamic: Optional[float] = None
    dual: Optional[float] = None
    triple: Optional[float] = None
    tesla: Optional[float] = None


class ZoneUpdate(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None
    max_jobs: Optional[int] = None
    slot_minutes: Optional[int] = None
    buffer_minutes: Optional[int] = None


class ContractorUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    home_address: Optional[str] = None
    is_active: Optional[bool] = None


class RescheduleIn(BaseModel):
    scheduled_start: str
    reason: Optional[str] = None


class CancelIn(BaseModel):
    reason: Optional[str] = None


class JobEditIn(BaseModel):
    customer_last_name: Optional[str] = None
    vehicle_year: Optional[int] = None
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_trim: Optional[str] = None
    vehicle_vin: Optional[str] = None
    adas_system: Optional[Literal["forward_camera", "surround_view", "radar", "multi_camera", "tesla", "other"]] = None
    calibration_type: Optional[Literal["static", "dynamic", "dual", "triple", "tesla"]] = None
    job_address: Optional[str] = None
    scheduled_start: Optional[str] = None
    notification_phone: Optional[str] = None
    notification_email: Optional[str] = None
    price: Optional[float] = None
    notes: Optional[str] = None


class InviteCreateIn(BaseModel):
    shop_id: str
    recipient_email: EmailStr
    origin: Optional[str] = None


class ShopUserRegisterIn(BaseModel):
    invite_token: str
    full_name: str
    password: str
    terms_signature: str
    terms_agreed: bool
    origin: Optional[str] = None


class ShopUserLoginIn(BaseModel):
    email: EmailStr
    password: str
