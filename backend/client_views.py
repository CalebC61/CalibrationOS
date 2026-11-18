"""Fields safe to send to a browser.

Staff and shop-user responses are an allowlist. A new column on the Mongo
document stays on the server until it is added here. Shop documents keep their
business fields (the owner edits most of them) and drop credential fields.
The shop booking link stays: the owner and that shop use it as the public URL.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict


class StaffPublic(BaseModel):
    """Owner, contractor, or technician as the client may see them."""

    model_config = ConfigDict(extra="ignore")

    id: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    home_zone: Optional[str] = None
    home_address: Optional[str] = None
    home_lat: Optional[float] = None
    home_lng: Optional[float] = None
    service_radius_miles: Optional[float] = None
    day_start: Optional[str] = None
    day_end: Optional[str] = None
    slot_minutes: Optional[int] = None
    max_jobs: Optional[int] = None
    color: Optional[str] = None
    routes_jobs: Optional[bool] = None
    job_duration_minutes: Optional[int] = None
    buffer_minutes: Optional[int] = None
    same_day_bookings_enabled: Optional[bool] = None
    same_day_cutoff: Optional[str] = None
    same_day_max_extra_drive_minutes: Optional[int] = None
    same_day_max_later_finish_minutes: Optional[int] = None
    same_day_over_limit: Optional[str] = None
    google_calendar_connected: Optional[bool] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    xero_connected: bool = False
    xero_org_name: Optional[str] = None


class ShopUserPublic(BaseModel):
    """Shop portal account. Card brand and last4 are display data, not the Stripe ids."""

    model_config = ConfigDict(extra="ignore")

    id: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    shop_id: Optional[str] = None
    shop_name: Optional[str] = None
    is_active: Optional[bool] = None
    card_brand: Optional[str] = None
    card_last4: Optional[str] = None
    card_exp_month: Optional[int] = None
    card_exp_year: Optional[int] = None
    card_status: Optional[str] = None
    has_payment_method: bool = False
    terms_signature: Optional[str] = None
    terms_signed_at: Optional[str] = None
    agreement_version: Optional[str] = None
    charge_authorization_accepted_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# Names that must never appear on a shop payload. booking_link_token is not in
# this set: it is the shop's public booking URL.
SHOP_SECRET_KEYS = frozenset({
    "_id",
    "password",
    "password_hash",
    "stripe_customer_id",
    "stripe_payment_method_id",
    "xero_access_token",
    "xero_refresh_token",
    "xero_id_token",
    "xero_token_expiry",
    "xero_tenant_id",
    "access_token",
    "refresh_token",
    "id_token",
    "client_secret",
    "api_key",
})

_SECRET_FRAGMENTS = (
    "password",
    "secret",
    "access_token",
    "refresh_token",
    "id_token",
    "token_expiry",
    "api_key",
    "client_secret",
)


def staff_xero_connected(person: Optional[dict]) -> bool:
    """Same rule as a live Xero call: a tenant and a token, without returning either."""
    person = person or {}
    return bool(
        person.get("xero_tenant_id")
        and (person.get("xero_access_token") or person.get("xero_refresh_token"))
    )


def public_staff(person: Optional[dict]) -> dict:
    person = dict(person or {})
    person["xero_connected"] = staff_xero_connected(person)
    return StaffPublic.model_validate(person).model_dump()


def public_shop_user(user: Optional[dict]) -> dict:
    user = dict(user or {})
    user["has_payment_method"] = bool((user.get("stripe_payment_method_id") or "").strip())
    return ShopUserPublic.model_validate(user).model_dump()


def _shop_key_is_secret(key: str) -> bool:
    if key == "booking_link_token":
        return False
    if key in SHOP_SECRET_KEYS:
        return True
    lowered = key.lower()
    if lowered.endswith("_token"):
        return True
    return any(fragment in lowered for fragment in _SECRET_FRAGMENTS)


def public_shop(shop: Optional[dict]) -> Optional[dict]:
    """Shop fields the owner or that shop may see. Stripe customer and card ids stay off."""
    if not shop:
        return None
    out = {key: value for key, value in shop.items() if not _shop_key_is_secret(key)}
    out["has_payment_method"] = bool((shop.get("stripe_payment_method_id") or "").strip())
    return out
