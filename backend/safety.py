"""Billing stays off until the owner turns it on. Shop mail lives in booking_mail.

A live Stripe key is not used until BILLING_ENABLED is true. Completing a job
does not charge a card, and the late-fee sweep does not run, until then.
"""
from typing import Optional


def env_flag(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


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
