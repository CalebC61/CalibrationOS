"""Pure, dependency-light helpers for charging a completed job's card on file.

Kept import-light (stdlib only) so the money-critical logic — is this job chargeable, what does
a PaymentIntent status mean, how to phrase a decline — is unit-testable without booting the full
server / MongoDB / a real Stripe key. The actual Stripe API calls (requests via the stripe SDK,
wrapped in asyncio.to_thread, same as the existing Xero/Resend integrations) live in server.py;
this module only makes decisions from data it's handed.
"""
from typing import Optional


def cents(amount: float) -> int:
    """Dollar amount -> integer cents for Stripe (which takes amounts in the smallest currency unit)."""
    return int(round(float(amount) * 100))


def chargeable_reason(job: dict, shop_user: Optional[dict]) -> Optional[str]:
    """Why a completed job can't be charged right now, or None if it's chargeable.

    Centralizes the eligibility check so both the charge endpoint and (if ever needed) the
    queue listing agree on what counts as chargeable, instead of duplicating conditions.
    """
    if job.get("status") != "complete":
        return "Job is not marked complete."
    if job.get("charged_at"):
        return "Job has already been charged or resolved."
    if not shop_user:
        return "No portal account found for this job's shop."
    if not shop_user.get("stripe_customer_id"):
        return "This shop has no Stripe customer on file."
    if not shop_user.get("stripe_payment_method_id"):
        return "This shop has no card on file."
    return None


def interpret_payment_intent(pi: dict) -> dict:
    """Classify a Stripe PaymentIntent response into the app's charge outcome.

    off_session=True + confirm=True charges normally resolve straight to "succeeded" or raise a
    CardError (handled separately, see decline_message). The "requires_action" family is the rare
    edge case where the card's issuer demands authentication that can't happen without the
    customer present — this app has no customer-facing checkout at charge time, so that case is
    surfaced as a stuck state for the owner to resolve (ask the shop to re-add their card), not
    silently retried.
    """
    status = pi.get("status")
    pi_id = pi.get("id")
    if status == "succeeded":
        return {"outcome": "succeeded", "payment_intent_id": pi_id, "status": status}
    if status in ("requires_action", "requires_confirmation", "requires_capture"):
        return {
            "outcome": "requires_action", "payment_intent_id": pi_id, "status": status,
            "message": ("Card requires authentication that can't complete without the shop "
                        "present. Ask them to re-add their card in the portal, then retry."),
        }
    return {
        "outcome": "other", "payment_intent_id": pi_id, "status": status,
        "message": f"Unexpected payment status: {status}.",
    }


def decline_message(error_code: Optional[str], decline_code: Optional[str] = None) -> str:
    """User-facing message for a Stripe CardError (a hard decline)."""
    reason = decline_code or error_code
    if reason:
        return f"Card declined ({reason.replace('_', ' ')})."
    return "Card declined."
