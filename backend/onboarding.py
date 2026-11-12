"""Shop signup rules: contact checks, the one service agreement, and booking gate.

Pure functions. The FastAPI routes in server.py call these so a shop cannot be
saved, or a new shop cannot book, on rules the tests do not also enforce.
"""
import re
from typing import Optional

from email_validator import EmailNotValidError, validate_email

# Bump when the words the shop signs change. Stored with the signature.
AGREEMENT_VERSION = "2026-11-12"

# TODO(owner): The old signup screens mentioned a $50 fee when a shop cancels
# less than 4 hours before the start ("$50 trip charge" / "$50 late-cancel").
# Nothing in the server charges that fee, so it is not in this agreement.
# Confirm whether it is still the policy before adding a sentence here.

AGREEMENT_PARAGRAPHS = [
    "When a calibration is finished, you authorize The Calibration Crew to charge the card you keep on file for that job.",
    "If you would rather be invoiced for a job, say so in the job notes or call us before we finish it. We will invoice that job and we will not charge the card until you tell us to.",
    "An invoiced job has 7 days to be paid. After those 7 days, a $25 late fee is added.",
    "Every job comes with an invoice, so you always have a proof of purchase.",
]

CHARGE_ACCEPTANCE_TEXT = (
    "You understand that after each job is completed, you authorize The Calibration Crew "
    "to charge this card, unless you asked beforehand to be invoiced, in which case you "
    "have a 7-day grace period before a $25 late fee."
)

RESEND_TEST_SENDER = "onboarding@resend.dev"


def agreement_text() -> str:
    return "\n\n".join(AGREEMENT_PARAGRAPHS)


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
    return (
        shop_user.get("agreement_version") == AGREEMENT_VERSION
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
    allowed = (not requires) or ready
    message = None
    if not allowed:
        message = "Booking opens after the shop contact signs the agreement and saves a card."
    return {
        "allowed": allowed,
        "grandfathered": not requires,
        "signed": signed,
        "has_card": has_card,
        "accepted": accepted,
        "banner": not ready,
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
