"""Unit tests for the money-critical charge-eligibility and Stripe-response-interpretation logic.

These are pure (stdlib only) and run anywhere — no server, MongoDB, or Stripe key needed:
    cd backend && pytest tests/test_charging.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/
from charging import cents, chargeable_reason, interpret_payment_intent, decline_message  # noqa: E402

COMPLETE_JOB = {"id": "job-1", "status": "complete", "price": 125.00}
SHOP_USER_READY = {"stripe_customer_id": "cus_1", "stripe_payment_method_id": "pm_1"}


def test_cents_converts_exact_dollar_amounts():
    assert cents(125.00) == 12500
    assert cents(175.00) == 17500
    assert cents(225.00) == 22500


def test_cents_handles_floating_point_noise():
    assert cents(19.99) == 1999
    assert cents(0.1 + 0.2) == 30  # classic float noise case: 0.30000000000000004


def test_chargeable_when_complete_unbilled_with_card_on_file():
    assert chargeable_reason(COMPLETE_JOB, SHOP_USER_READY) is None


def test_not_chargeable_when_job_not_complete():
    job = {**COMPLETE_JOB, "status": "on_site"}
    assert "not marked complete" in chargeable_reason(job, SHOP_USER_READY)


def test_not_chargeable_when_already_charged():
    job = {**COMPLETE_JOB, "charged_at": "2026-07-21T00:00:00Z"}
    assert "already been charged" in chargeable_reason(job, SHOP_USER_READY)


def test_not_chargeable_with_no_shop_user():
    assert "No portal account" in chargeable_reason(COMPLETE_JOB, None)


def test_not_chargeable_with_no_stripe_customer():
    su = {"stripe_customer_id": None, "stripe_payment_method_id": None}
    assert "no Stripe customer" in chargeable_reason(COMPLETE_JOB, su)


def test_not_chargeable_with_no_payment_method():
    su = {"stripe_customer_id": "cus_1", "stripe_payment_method_id": None}
    assert "no card on file" in chargeable_reason(COMPLETE_JOB, su)


def test_interpret_succeeded():
    result = interpret_payment_intent({"id": "pi_1", "status": "succeeded"})
    assert result == {"outcome": "succeeded", "payment_intent_id": "pi_1", "status": "succeeded"}


def test_interpret_requires_action_surfaces_actionable_message():
    result = interpret_payment_intent({"id": "pi_2", "status": "requires_action"})
    assert result["outcome"] == "requires_action"
    assert "re-add their card" in result["message"]


def test_interpret_unexpected_status_falls_to_other():
    result = interpret_payment_intent({"id": "pi_3", "status": "processing"})
    assert result["outcome"] == "other"
    assert "processing" in result["message"]


def test_decline_message_prefers_decline_code():
    assert decline_message("card_declined", "insufficient_funds") == "Card declined (insufficient funds)."


def test_decline_message_falls_back_to_error_code():
    assert decline_message("expired_card", None) == "Card declined (expired card)."


def test_decline_message_generic_fallback():
    assert decline_message(None, None) == "Card declined."
