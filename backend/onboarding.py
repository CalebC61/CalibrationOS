"""Shop signup rules: contact checks, the one service agreement, and booking gate.

Pure functions. The FastAPI routes in server.py call these so a shop cannot be
saved, or a new shop cannot book, on rules the tests do not also enforce.
"""
import re
import time
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
    if not isinstance(password, str) or len(password) < 8:
        return "Password must be at least 8 characters."
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


def _has_card(shop_user: Optional[dict]) -> bool:
    return bool(shop_user and shop_user.get("stripe_payment_method_id"))


def _accepted_charge(shop_user: Optional[dict]) -> bool:
    return bool(shop_user and shop_user.get("charge_authorization_accepted_at"))


def booking_gate(shop: Optional[dict], shop_user: Optional[dict] = None) -> dict:
    """Whether this shop may book, and whether the portal should nag them.

    Shops saved before card-on-file billing do not have requires_billing_setup.
    They keep booking. The portal still asks them to finish setup.
    A shop created under this agreement cannot book until the contact has
    signed, saved a card, and accepted the charge wording.
    """
    shop = shop or {}
    requires = shop.get("requires_billing_setup") is True
    signed = _signed(shop_user)
    has_card = _has_card(shop_user)
    accepted = _accepted_charge(shop_user)
    ready = signed and has_card and accepted
    suspended = shop.get("status") == "suspended"
    allowed = ((not requires) or ready) and not suspended
    message = None
    if suspended:
        message = "This shop is suspended and cannot book."
    elif not allowed:
        message = "Booking opens after the shop contact signs the agreement and saves a card."
    return {
        "allowed": allowed,
        "grandfathered": not requires,
        "signed": signed,
        "has_card": has_card,
        "accepted": accepted,
        "suspended": suspended,
        "banner": not ready or suspended,
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
        <p style="text-align:center;margin:28px 0;">
          <a href="{register_url}" style="background:#FF5F1F;color:#0a0a0a;text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:700;display:inline-block;">Set up your shop</a>
        </p>
        <p style="color:#B4B8C2;font-size:13px;">Questions? Reply to this email and it comes to Caleb.</p>
      </div>
    </div>
    """


def welcome_email_html(shop_name: str, booking_url: str) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;background:#2A2E37;color:#f5f5f5;padding:32px;">
      <div style="max-width:560px;margin:0 auto;background:#343843;border-radius:12px;padding:28px;">
        <h1 style="font-size:22px;margin:0 0 12px;">You're set, {shop_name}.</h1>
        <p style="line-height:1.55;">Your agreement is signed and your card is saved. Book a calibration with the link below. After each job is completed we charge that card, unless you asked to be invoiced. An invoiced job has 7 days, then a $25 late fee. You get an invoice for every job.</p>
        <p style="text-align:center;margin:28px 0;">
          <a href="{booking_url}" style="background:#FF5F1F;color:#0a0a0a;text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:700;display:inline-block;">Book a job</a>
        </p>
        <p style="color:#B4B8C2;font-size:13px;word-break:break-all;">{booking_url}</p>
      </div>
    </div>
    """
