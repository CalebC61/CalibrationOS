"""Shop signup rules: contact checks, the one service agreement, and booking gate.

Pure functions. The FastAPI routes in server.py call these so a shop cannot be
saved, or a new shop cannot book, on rules the tests do not also enforce.
"""
import re
import time
from datetime import date, datetime, timezone
from typing import Optional

from email_validator import EmailNotValidError, validate_email

# Bump when the words the shop signs change. Stored with the signature.
AGREEMENT_VERSION = "2026-11-13.1"
# Shops that already signed the previous wording keep booking.
PRIOR_AGREEMENT_VERSIONS = {"2026-11-12.3", "2026-11-12"}
PUBLIC_SITE_DEFAULT = "https://www.thecalibrationcrew.us"
# Precise Google pins. A free-typed address with one of these is already confirmed.
CLEAN_LOCATION_TYPES = {"ROOFTOP", "RANGE_INTERPOLATED"}
SIGNUP_ATTEMPT_LIMIT = 8
SIGNUP_WINDOW_SECONDS = 60 * 60
CARD_SETUP_ATTEMPT_LIMIT = 20
# Sign-in and password reset. Shorter than signup so a guessed password locks quickly.
LOGIN_ATTEMPT_LIMIT = 8
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_LIMIT_MESSAGE = "Too many sign-in attempts. Wait 15 minutes and try again."
FORGOT_ATTEMPT_LIMIT = 5
FORGOT_WINDOW_SECONDS = 60 * 60
FORGOT_LIMIT_MESSAGE = "Too many reset requests. Wait an hour and try again."
# Public lookups that would otherwise call Google or email the office without a login.
GEOCODE_ATTEMPT_LIMIT = 30
GEOCODE_WINDOW_SECONDS = 60 * 60
GEOCODE_LIMIT_MESSAGE = "Too many address lookups. Wait an hour and try again."
CONTACT_ATTEMPT_LIMIT = 5
CONTACT_WINDOW_SECONDS = 60 * 60
CONTACT_LIMIT_MESSAGE = "Too many messages from this network. Wait an hour and try again, or call the office."
PASSWORD_MIN_LENGTH = 8
PASSWORD_RULE = "At least 8 characters."

AGREEMENT_SECTIONS = [
    {
        "heading": "Who this is between",
        "body": (
            "This is between The Calibration Crew LLC, of Gilbert, Arizona, "
            "and your shop. By typing your name and checking the box, you confirm you are allowed to sign for the shop."
        ),
    },
    {
        "heading": "What we do",
        "body": (
            "We calibrate ADAS cameras and sensors at your shop. Prices at signup are Static $125, "
            "Dynamic $125, Dual $175, Triple / Subaru $185, and Tesla $225. "
            "We can change those prices with 30 days' written notice."
        ),
    },
    {
        "heading": "How you pay",
        "body": (
            "We charge the card on file automatically when a job is marked complete. If you ask in the job notes, "
            "or call us before the job is finished, we invoice that job instead and charge the card only when you say so. "
            "An invoiced job has 7 days to pay. After that, a one-time $25 late fee is added to that invoice. "
            "Every job gets an invoice, so you have a proof of purchase. If the card is declined, you update the card, "
            "and the balance is handled as an invoiced job."
        ),
    },
    {
        "heading": "The $30 trip fee",
        "body": (
            "A $30 trip fee applies in three cases. If the address is outside our service area, the $30 is added on top "
            "of the calibration price. If we cannot calibrate because of a bad installation, such as a broken camera "
            "mounting bracket or a bad or incorrect windshield, we charge only the $30 trip fee, not the calibration price. "
            "The same is true if we cannot calibrate because of the customer or the vehicle, such as the vehicle leaving "
            "without notice, no fuel, a flat tire, or a dead battery."
        ),
    },
    {
        "heading": "What we need from your shop",
        "body": (
            "The vehicle is on site with the keys. The glass is installed and cured. The battery is charged. "
            "The tires are properly inflated. There is enough fuel. The vehicle has no unrelated warning lights. "
            "There is a level place to work."
        ),
    },
    {
        "heading": "No late-cancel fee and no waiting fee",
        "body": "We do not charge a late-cancel fee. We do not charge a waiting fee.",
    },
    {
        "heading": "If we get it wrong",
        "body": "If a calibration we performed is found to be incorrect within 30 days, we re-calibrate it at no charge.",
    },
    {
        "heading": "What we are not responsible for",
        "body": (
            "We are not responsible for problems that were already there, damaged or failed modules or cameras, "
            "aftermarket parts, or installation defects. For any one job, the most we can be responsible for is the amount paid for that job."
        ),
    },
    {
        "heading": "Questions and disputes",
        "body": "Tell us about a billing or service issue within 7 days of the invoice. Contact us before you file a chargeback.",
    },
    {
        "heading": "Your signature",
        "body": (
            "Typing your name and checking the box is your legal signature. We store your name, the time, "
            "your IP address, and the version of this agreement."
        ),
    },
    {
        "heading": "Changes and Arizona law",
        "body": "Updated terms take effect after we give you notice. Arizona law applies. If there is a dispute in court, it is in Maricopa County.",
    },
]

AGREEMENT_PARAGRAPHS = [section["body"] for section in AGREEMENT_SECTIONS]

CHARGE_ACCEPTANCE_TEXT = (
    "You understand that after each job is completed, you authorize The Calibration Crew to charge this card, "
    "unless you asked beforehand to be invoiced, in which case you have 7 days to pay before a one-time $25 late fee. "
    "A $30 trip fee may be added when the address is outside our service area, or charged instead of the calibration "
    "price when we cannot calibrate because of a bad installation or because of the customer or the vehicle."
)

RESEND_TEST_SENDER = "onboarding@resend.dev"


def agreement_text() -> str:
    return "\n\n".join(f"{section['heading']}\n{section['body']}" for section in AGREEMENT_SECTIONS)


def sender_email_problem(sender: str) -> Optional[str]:
    """Why this From address will not reach a shop, or None when it is usable.

    Resend delivers onboarding@resend.dev only to the Resend account owner.
    SENDER_EMAIL must be a verified address on thecalibrationcrew.us.
    """
    if (sender or "").strip().lower() == RESEND_TEST_SENDER:
        return (
            "SENDER_EMAIL is onboarding@resend.dev. Resend will not deliver that "
            "address to a shop. Set SENDER_EMAIL to a verified thecalibrationcrew.us "
            "address in Resend."
        )
    return None


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """US mobile as +1 and 10 digits, or None when the shape is wrong."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return f"+1{digits}"


def canonical_email(raw: Optional[str]) -> Optional[str]:
    try:
        parsed = validate_email((raw or "").strip(), check_deliverability=False)
    except EmailNotValidError:
        return None
    return parsed.normalized.lower()


def shop_contact_errors(*, name: Optional[str], phone: Optional[str], email: Optional[str], address: Optional[str]) -> dict:
    errors = {}
    if not (name or "").strip():
        errors["name"] = "Shop name is required."
    if not normalize_phone(phone):
        errors["phone"] = "Enter a 10-digit mobile number."
    if not canonical_email(email):
        errors["email"] = "Enter a valid email."
    if not (address or "").strip():
        errors["address"] = "Shop address is required."
    return errors


def _norm_name(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def duplicate_fields(name: Optional[str], email: Optional[str], shops: list, users: Optional[list] = None, ignore_shop_id: Optional[str] = None) -> list:
    """Which of name / email already belong to a different shop. Empty when clear."""
    found = []
    wanted_name = _norm_name(name)
    wanted_email = (canonical_email(email) or (email or "").strip().lower())
    for shop in shops or []:
        if ignore_shop_id and shop.get("id") == ignore_shop_id:
            continue
        if wanted_name and _norm_name(shop.get("name")) == wanted_name and "name" not in found:
            found.append("name")
        shop_email = (shop.get("contact_email") or "").strip().lower()
        if wanted_email and shop_email == wanted_email and "email" not in found:
            found.append("email")
    for user in users or []:
        if ignore_shop_id and user.get("shop_id") == ignore_shop_id:
            continue
        user_email = (user.get("email") or "").strip().lower()
        if wanted_email and user_email == wanted_email and "email" not in found:
            found.append("email")
    return found


def address_problem(geo: Optional[dict]) -> Optional[str]:
    """Reject a missing lookup, a guessed pin, or a point outside the valley."""
    if not geo or geo.get("fallback"):
        return "Could not locate that address. Check the street and city and try again."
    if not geo.get("formatted_address"):
        return "Could not locate that address. Check the street and city and try again."
    if not geo.get("in_metro"):
        return "That address is outside the Phoenix Valley."
    return None


def addresses_match(left: Optional[str], right: Optional[str]) -> bool:
    def norm(value: Optional[str]) -> str:
        return re.sub(r"[^a-z0-9]", "", (value or "").lower())
    return bool(norm(left)) and norm(left) == norm(right)


def resolve_frontend_url(explicit: Optional[str], public_site: Optional[str] = None) -> str:
    """Link host. A blank FRONTEND_URL uses PUBLIC_SITE_URL, then the public site."""
    chosen = (explicit or "").strip().rstrip("/")
    if chosen:
        return chosen
    site = (public_site or "").strip().rstrip("/")
    return site or PUBLIC_SITE_DEFAULT


def places_selection(place_id: Optional[str]) -> bool:
    return bool((place_id or "").strip())


def geocode_is_clean(geo: Optional[dict]) -> bool:
    """A precise in-valley pin. Approximate results are not clean."""
    if not geo or geo.get("fallback") or geo.get("partial_match") or geo.get("guessed"):
        return False
    if geo.get("in_metro") is False or not geo.get("formatted_address"):
        return False
    return geo.get("location_type") in CLEAN_LOCATION_TYPES


def address_needs_confirmation(*, place_id: Optional[str], confirmed: bool, confirmed_address: Optional[str], geo: Optional[dict]) -> bool:
    """True when a free-typed address still needs a second submit.

    A Places suggestion is the confirmed address. A free-typed address that
    geocodes to a precise pin is confirmed. The checkbox remains for a
    free-typed address that does not geocode cleanly, and for a shop that
    is accepting the formatted address we already returned.
    """
    if places_selection(place_id):
        return False
    formatted = (geo or {}).get("formatted_address")
    if confirmed and addresses_match(confirmed_address, formatted):
        return False
    if geocode_is_clean(geo):
        return False
    return True


def reused_shop_pin(shop: Optional[dict], address: Optional[str]) -> Optional[dict]:
    """The signup pin when this booking is still at the shop address.

    Returns None when the address differs or the stored pin is not usable,
    so the caller geocodes. A fallback pin is not reused.
    """
    shop = shop or {}
    if shop.get("lat") is None or shop.get("lng") is None:
        return None
    if not (
        addresses_match(address, shop.get("address"))
        or addresses_match(address, shop.get("formatted_address"))
    ):
        return None
    source = shop.get("geocode_source") or ""
    if source in ("fallback", "mock") or shop.get("guessed"):
        return None
    return {
        "lat": shop["lat"],
        "lng": shop["lng"],
        "formatted_address": shop.get("formatted_address") or shop.get("address") or address,
        "in_metro": True,
        "source": source or "google",
        "partial_match": False,
        "fallback": False,
        "location_type": "ROOFTOP",
    }


_RATE_BUCKETS: dict = {}


def reset_rate_limits() -> None:
    _RATE_BUCKETS.clear()


def rate_limit_exceeded(key: str, *, limit: int, window_seconds: int, now: Optional[float] = None) -> bool:
    """True when this key is over the limit. An allowed call is recorded."""
    moment = time.monotonic() if now is None else now
    hits = [stamp for stamp in _RATE_BUCKETS.get(key, []) if moment - stamp < window_seconds]
    if len(hits) >= limit:
        _RATE_BUCKETS[key] = hits
        return True
    hits.append(moment)
    _RATE_BUCKETS[key] = hits
    return False


def password_error(password: Optional[str]) -> Optional[str]:
    if not isinstance(password, str) or len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters."
    return None


def app_link(frontend_url: Optional[str], path: str) -> str:
    """Build a link from FRONTEND_URL. Never from the request's origin."""
    base = (frontend_url or "").strip().rstrip("/")
    if not base:
        raise ValueError(
            "FRONTEND_URL is not set. Links are not built from the browser address."
        )
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def invite_register_url(frontend_url: Optional[str], token: str) -> str:
    return app_link(frontend_url, f"/portal/invite/{token}")


def _signed(shop_user: Optional[dict]) -> bool:
    if not shop_user:
        return False
    version = shop_user.get("agreement_version")
    current = version == AGREEMENT_VERSION or version in PRIOR_AGREEMENT_VERSIONS
    return (
        current
        and bool(shop_user.get("terms_signed_at"))
        and bool((shop_user.get("terms_signature") or "").strip())
    )


CARD_FIELD_KEYS = (
    "stripe_customer_id",
    "stripe_payment_method_id",
    "card_brand",
    "card_last4",
    "card_exp_month",
    "card_exp_year",
    "card_status",
)
REMOVED_CARD_STATUSES = {"detached", "removed", "missing"}
# A shop document that already satisfies the booking gate. Tests that book a job
# spread this onto the shop so the gate and the charge use the same card.
READY_BILLING = {
    "stripe_customer_id": "cus_ready",
    "stripe_payment_method_id": "pm_ready",
    "card_brand": "visa",
    "card_last4": "4242",
    "card_exp_month": 12,
    "card_exp_year": 2099,
    "card_status": "active",
    "charge_authorization_accepted_at": "2026-01-01T00:00:00+00:00",
    "billing_card_backfilled": True,
}
CARD_MESSAGES = {
    "missing": "Add a card in Settings before booking. A shop needs a valid card on file.",
    "removed": "The card on file was removed. Update it in Settings before booking.",
    "expired": "The card on file is expired. Update it in Settings before booking.",
    "failed": "A charge on the card on file did not go through. Update the card in Settings before booking.",
    "terms": "Accept the charge terms in Settings before booking.",
    "signature": "Booking opens after the shop contact signs the agreement and saves a card.",
    "suspended": "This shop is suspended and cannot book.",
}


def card_is_expired(month, year, *, today: Optional[date] = None) -> bool:
    """True when the card's expiry month is already over.

    A card is good through the last day of its expiry month. A missing month or
    year is not treated as expired; the caller decides whether a card with no
    expiry can be saved.
    """
    if month in (None, "") or year in (None, ""):
        return False
    try:
        month_n = int(month)
        year_n = int(year)
    except (TypeError, ValueError):
        return True
    if year_n < 100:
        year_n += 2000
    if month_n < 1 or month_n > 12:
        return True
    current = today or datetime.now(timezone.utc).date()
    if year_n < current.year:
        return True
    if year_n == current.year and month_n < current.month:
        return True
    return False


def shop_owns_card(shop: Optional[dict]) -> bool:
    """The shop document is the card of record, including when that card was cleared."""
    shop = shop or {}
    if shop.get("billing_card_backfilled"):
        return True
    status = shop.get("card_status")
    if status in REMOVED_CARD_STATUSES or status == "active":
        return True
    if (shop.get("stripe_payment_method_id") or "").strip():
        return True
    return False


def billing_view(shop: Optional[dict], shop_user: Optional[dict] = None) -> dict:
    """The one card the booking gate and a charge both use.

    Once the shop has stored a card (or an explicit removal), that record wins.
    Otherwise the billing user's card is used. Charge acceptance is kept if
    either record has it.
    """
    shop = shop or {}
    user = shop_user or {}
    source = shop if shop_owns_card(shop) else user
    view = {key: source.get(key) for key in CARD_FIELD_KEYS}
    if not view.get("stripe_customer_id"):
        view["stripe_customer_id"] = shop.get("stripe_customer_id") or user.get("stripe_customer_id")
    view["charge_authorization_accepted_at"] = (
        shop.get("charge_authorization_accepted_at") or user.get("charge_authorization_accepted_at")
    )
    view["unresolved_charge_failure"] = bool(shop.get("unresolved_charge_failure"))
    return view


def card_block_reason(record: Optional[dict], *, today: Optional[date] = None) -> Optional[str]:
    """Why this card cannot be used, or None when it can."""
    record = record or {}
    if record.get("card_status") in REMOVED_CARD_STATUSES:
        return "removed"
    if not (record.get("stripe_payment_method_id") or "").strip():
        return "missing"
    if card_is_expired(record.get("card_exp_month"), record.get("card_exp_year"), today=today):
        return "expired"
    return None


def pick_billing_user(users: list) -> Optional[dict]:
    """The shop's billing contact: the earliest active user, then the earliest user."""
    active = [user for user in users if user.get("is_active", True)]
    pool = active or list(users)
    if not pool:
        return None
    pool.sort(key=lambda user: (str(user.get("created_at") or ""), str(user.get("id") or "")))
    return pool[0]


def shop_card_backfill(shop: dict, user: Optional[dict]) -> dict:
    """Copy a billing user's card onto the shop once.

    A shop that already has a card keeps it. A second call, after
    billing_card_backfilled is set, copies nothing.
    """
    if shop.get("billing_card_backfilled"):
        return {}
    user = user or {}
    fields = {"billing_card_backfilled": True}
    if not (shop.get("stripe_payment_method_id") or "").strip() and (user.get("stripe_payment_method_id") or "").strip():
        for key in ("stripe_payment_method_id", "card_brand", "card_last4", "card_exp_month", "card_exp_year"):
            if user.get(key) not in (None, ""):
                fields[key] = user.get(key)
        fields["card_status"] = user.get("card_status") or "active"
    if not shop.get("stripe_customer_id") and user.get("stripe_customer_id"):
        fields["stripe_customer_id"] = user["stripe_customer_id"]
    if not shop.get("charge_authorization_accepted_at") and user.get("charge_authorization_accepted_at"):
        fields["charge_authorization_accepted_at"] = user["charge_authorization_accepted_at"]
    return fields


def _shop_signed(shop: Optional[dict]) -> bool:
    shop = shop or {}
    signed_by = (shop.get("terms_signed_by") or shop.get("terms_signature") or "").strip()
    return bool(shop.get("terms_signed_at") and signed_by)


def booking_gate(shop: Optional[dict], shop_user: Optional[dict] = None, *, today: Optional[date] = None) -> dict:
    """Whether this shop may book a job.

    Every shop needs a current card and accepted charge terms. A blank, removed,
    detached, or expired card blocks booking. An unresolved failed charge blocks
    booking until the card is replaced or a later charge succeeds. Shops flagged
    requires_billing_setup also need a signed agreement. Owner job actions are
    not this gate.
    """
    shop = shop or {}
    user = shop_user or {}
    view = billing_view(shop, user)
    requires = shop.get("requires_billing_setup") is True
    signed = _signed(user) or _shop_signed(shop)
    reason = card_block_reason(view, today=today)
    has_card = reason is None
    accepted = bool(view.get("charge_authorization_accepted_at"))
    failed = bool(view.get("unresolved_charge_failure"))
    suspended = shop.get("status") == "suspended"
    allowed = (not suspended) and has_card and (not failed) and accepted and ((not requires) or signed)
    message = None
    if suspended:
        message = CARD_MESSAGES["suspended"]
    elif failed:
        message = CARD_MESSAGES["failed"]
    elif not has_card:
        message = CARD_MESSAGES.get(reason or "missing", CARD_MESSAGES["missing"])
    elif not accepted:
        message = CARD_MESSAGES["terms"]
    elif requires and not signed:
        message = CARD_MESSAGES["signature"]
    return {
        "allowed": allowed,
        "grandfathered": False,
        "signed": signed,
        "has_card": has_card,
        "accepted": accepted,
        "card_problem": reason,
        "charge_failed": failed,
        "suspended": suspended,
        "banner": not allowed,
        "message": message,
    }


def invite_email_html(shop_name: str, register_url: str) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;background:#2A2E37;color:#f5f5f5;padding:32px;">
      <div style="max-width:560px;margin:0 auto;background:#343843;border-radius:12px;padding:28px;">
        <p style="letter-spacing:0.08em;color:#FF7E1E;font-weight:700;margin:0 0 12px;">THE CALIBRATION CREW</p>
        <h1 style="font-size:22px;margin:0 0 12px;">{shop_name}, your shop account is ready to set up.</h1>
        <p style="line-height:1.55;">Caleb set up {shop_name} on CalibrationOS. This link is for the shop contact. It expires in 14 days.</p>
        <p style="line-height:1.55;">You will choose a password, sign a short agreement, and save a card. After each calibration is finished, that card is charged, unless you asked us beforehand to invoice the job. An invoiced job has 7 days before a $25 late fee. Every job still gets an invoice as your proof of purchase.</p>
        <p style="line-height:1.55;">After setup, book from the shop portal. Log in with this email. There is no public booking link.</p>
        <p style="text-align:center;margin:28px 0;">
          <a href="{register_url}" style="background:#FF5F1F;color:#0a0a0a;text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:700;display:inline-block;">Set up your shop</a>
        </p>
        <p style="color:#B4B8C2;font-size:13px;">Questions? Reply to this email and it comes to Caleb.</p>
      </div>
    </div>
    """


def welcome_email_html(shop_name: str, portal_url: str) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;background:#2A2E37;color:#f5f5f5;padding:32px;">
      <div style="max-width:560px;margin:0 auto;background:#343843;border-radius:12px;padding:28px;">
        <h1 style="font-size:22px;margin:0 0 12px;">You're set, {shop_name}.</h1>
        <p style="line-height:1.55;">Your agreement is signed and your card is saved. Log in to your shop portal to book a calibration. After each job is completed we charge that card, unless you asked to be invoiced. An invoiced job has 7 days, then a $25 late fee. You get an invoice for every job.</p>
        <p style="text-align:center;margin:28px 0;">
          <a href="{portal_url}" style="background:#FF5F1F;color:#0a0a0a;text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:700;display:inline-block;">Log in to book</a>
        </p>
        <p style="color:#B4B8C2;font-size:13px;word-break:break-all;">{portal_url}</p>
      </div>
    </div>
    """
