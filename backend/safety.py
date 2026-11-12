"""Testing gates. Shop mail and automatic charges stay off unless the owner turns them on.

SHOP_EMAILS_ENABLED defaults off. While it is off, mail to a shop or a customer is
stored in the email_outbox collection instead of being sent. Invite and password-reset
mail may still send when the address is on TEST_EMAIL_ALLOWLIST.

BILLING_ENABLED defaults off. Completing a job does not charge the card, and the
late-fee sweep does nothing, until it is on. A live Stripe key is not used until then.
"""
from typing import Optional

# Kinds that would land in a shop or customer inbox. Owner and admin mail is not in this set.
# booking_* matches the shop messages from the booking-email work so a merge stays held.
SHOP_EMAIL_KINDS = frozenset({
    "invite",
    "welcome",
    "job_invoice",
    "receipt",
    "payment_failed_shop",
    "password_reset",
    "late_fee_shop",
    "booking_confirmation",
    "booking_approved",
    "booking_declined",
    "booking_rescheduled",
    "booking_cancelled",
})

# The only shop mail that may leave while SHOP_EMAILS_ENABLED is off, and only to the allow-list.
ALLOWLIST_EMAIL_KINDS = frozenset({"invite", "password_reset"})

HELD_REASON = "SHOP_EMAILS_ENABLED is off"
OUTBOX_STATUS = "held"


def env_flag(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def parse_allowlist(raw: Optional[str]) -> frozenset:
    return frozenset(part.strip().lower() for part in (raw or "").split(",") if part.strip())


def email_delivery(kind: Optional[str], to: Optional[str], *, enabled: bool, allowlist: frozenset) -> str:
    """'send' or 'hold'. Owner mail always sends. Shop mail sends only when enabled or allow-listed."""
    if kind not in SHOP_EMAIL_KINDS:
        return "send"
    if enabled:
        return "send"
    address = (to or "").strip().lower()
    if kind in ALLOWLIST_EMAIL_KINDS and address in allowlist:
        return "send"
    return "hold"


def stripe_key_mode(key: Optional[str]) -> str:
    """test, live, or unusable. Only sk_test_ and rk_test_ count as test."""
    value = (key or "").strip()
    if not value or value.endswith("_emergent") or "placeholder" in value:
        return "unusable"
    if value.startswith("sk_test_") or value.startswith("rk_test_"):
        return "test"
    if value.startswith("sk_live_") or value.startswith("rk_live_"):
        return "live"
    return "unusable"


def stripe_key_for_use(key: Optional[str], *, billing_enabled: bool) -> str:
    """The key Stripe calls may use. A live key is ignored until billing is turned on."""
    mode = stripe_key_mode(key)
    if mode == "test":
        return (key or "").strip()
    if mode == "live" and billing_enabled:
        return (key or "").strip()
    return ""


def automatic_charge_allowed(billing_enabled: bool) -> bool:
    return bool(billing_enabled)


def late_fee_sweep_allowed(billing_enabled: bool) -> bool:
    return bool(billing_enabled)
