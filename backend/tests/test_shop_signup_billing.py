"""Validation, agreement gating, one-charge-per-job, and the late-fee sweep.

    cd backend && pytest tests/test_shop_signup_billing.py -v
"""
from datetime import datetime, timedelta, timezone

from billing import (
    CHARGE_MODE,
    INVOICE_MODE,
    _MemoryGateway,
    apply_billing_pass,
    apply_late_fee,
    billing_plan,
    charge_idempotency_key,
    late_fee_due,
)
from onboarding import (
    AGREEMENT_VERSION,
    agreement_text,
    booking_gate,
    canonical_email,
    duplicate_fields,
    invite_register_url,
    normalize_phone,
    password_error,
    sender_email_problem,
    shop_contact_errors,
    address_problem,
    addresses_match,
)


NOW = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)


def test_phone_email_and_address_validation():
    assert normalize_phone("(480) 269-1329") == "+14802691329"
    assert normalize_phone("1-480-269-1329") == "+14802691329"
    assert normalize_phone("480-269") is None
    assert normalize_phone("123") is None
    assert canonical_email("Shop@Example.com") == "shop@example.com"
    assert canonical_email("not-an-email") is None
    errors = shop_contact_errors(name="  ", phone="12", email="nope", address="")
    assert set(errors) == {"name", "phone", "email", "address"}
    assert shop_contact_errors(
        name="Glass Co", phone="4805550100", email="a@b.co", address="1 Main, Gilbert, AZ",
    ) == {}
    assert address_problem(None)
    assert address_problem({"formatted_address": "x", "in_metro": False, "fallback": False})
    assert address_problem({"formatted_address": "guess", "in_metro": True, "fallback": True})
    assert address_problem({"formatted_address": "1 Main St, Gilbert, AZ", "in_metro": True}) is None
    assert addresses_match("1 Main St, Gilbert, AZ", "1 main st gilbert az")
    assert not addresses_match("1 Main", "2 Main")


def test_duplicate_name_or_email_warns_and_ignores_the_same_shop():
    shops = [
        {"id": "s1", "name": "Glass Co", "contact_email": "a@shop.test"},
        {"id": "s2", "name": "Other Glass", "contact_email": "b@shop.test"},
    ]
    assert duplicate_fields("glass co", "new@shop.test", shops) == ["name"]
    assert duplicate_fields("New Name", "A@shop.test", shops) == ["email"]
    assert duplicate_fields("glass co", "a@shop.test", shops, ignore_shop_id="s1") == []
    users = [{"shop_id": "s9", "email": "taken@shop.test"}]
    assert duplicate_fields("Fresh", "taken@shop.test", shops, users) == ["email"]


def test_password_minimum_is_enforced():
    assert password_error("short") == "Password must be at least 8 characters."
    assert password_error("") 
    assert password_error(None)
    assert password_error("longenough") is None


def test_invite_link_uses_frontend_url_not_an_origin():
    assert invite_register_url("https://thecalibrationcrew.us/", "tok") == (
        "https://thecalibrationcrew.us/portal/invite/tok"
    )
    try:
        invite_register_url("", "tok")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_sender_must_not_be_the_resend_onboarding_address():
    problem = sender_email_problem("onboarding@resend.dev")
    assert problem
    assert "thecalibrationcrew.us" in problem
    assert sender_email_problem("caleb@thecalibrationcrew.us") is None


def test_agreement_states_the_card_invoice_and_late_fee_rules():
    text = agreement_text()
    assert "charge the card" in text
    assert "job notes" in text
    assert "7 days" in text
    assert "$25" in text
    assert "proof of purchase" in text
    # The $50 late-cancel line is not enforced in code, so it stays out.
    assert "$50" not in text
    assert AGREEMENT_VERSION


def test_new_shops_cannot_book_until_signed_and_card_saved():
    shop = {"id": "new", "requires_billing_setup": True}
    blocked = booking_gate(shop, None)
    assert blocked["allowed"] is False
    assert blocked["grandfathered"] is False
    assert blocked["message"]

    signed_only = booking_gate(shop, {
        "agreement_version": AGREEMENT_VERSION,
        "terms_signed_at": "t",
        "terms_signature": "Ada Glass",
    })
    assert signed_only["allowed"] is False
    assert signed_only["signed"] is True
    assert signed_only["has_card"] is False

    ready_user = {
        "agreement_version": AGREEMENT_VERSION,
        "terms_signed_at": "t",
        "terms_signature": "Ada Glass",
        "stripe_payment_method_id": "pm_1",
        "charge_authorization_accepted_at": "t",
    }
    ready = booking_gate(shop, ready_user)
    assert ready["allowed"] is True
    assert ready["banner"] is False

    missing_acceptance = dict(ready_user)
    missing_acceptance["charge_authorization_accepted_at"] = None
    assert booking_gate(shop, missing_acceptance)["allowed"] is False


def test_existing_shops_keep_booking_and_still_see_a_setup_banner():
    legacy = {"id": "old", "name": "Safelite"}
    gate = booking_gate(legacy, None)
    assert gate["allowed"] is True
    assert gate["grandfathered"] is True
    assert gate["banner"] is True
    finished = booking_gate(legacy, {
        "agreement_version": AGREEMENT_VERSION,
        "terms_signed_at": "t",
        "terms_signature": "Ada",
        "stripe_payment_method_id": "pm_1",
        "charge_authorization_accepted_at": "t",
    })
    assert finished["allowed"] is True
    assert finished["banner"] is False


def _job(**overrides):
    job = {
        "id": "job-1",
        "shop_id": "shop-1",
        "status": "complete",
        "price": 125,
        "payment_mode": CHARGE_MODE,
        "actual_completion": (NOW - timedelta(days=8)).isoformat(),
    }
    job.update(overrides)
    return job


def test_completing_twice_invoices_once_and_charges_once():
    gateway = _MemoryGateway()
    first = apply_billing_pass(_job(), gateway)
    second = apply_billing_pass(first, gateway)
    assert first["invoice_id"] == second["invoice_id"]
    assert len(gateway.invoices) == 1
    assert len(gateway.charges) == 1
    assert second["payment_status"] == "paid"
    assert billing_plan(second) == {
        "mode": CHARGE_MODE,
        "create_invoice": False,
        "charge": False,
    }
    assert charge_idempotency_key("job-1", 0) == "charge-job-job-1"
    assert charge_idempotency_key("job-1", 0) == charge_idempotency_key("job-1")


def test_a_declined_card_can_be_retried_without_a_second_invoice():
    gateway = _MemoryGateway(charge_outcome="declined")
    failed = apply_billing_pass(_job(), gateway)
    assert failed["payment_status"] == "payment_failed"
    assert failed["charge_attempts"] == 1
    assert billing_plan(failed)["create_invoice"] is False
    assert billing_plan(failed)["charge"] is True
    gateway.charge_outcome = "succeeded"
    retried = apply_billing_pass(failed, gateway)
    assert retried["payment_status"] == "paid"
    assert len(gateway.invoices) == 1
    assert set(gateway.charges) == {"charge-job-job-1", "charge-job-job-1-retry-1"}


def test_invoice_mode_does_not_charge_on_complete():
    gateway = _MemoryGateway()
    done = apply_billing_pass(_job(payment_mode=INVOICE_MODE), gateway)
    assert done["invoice_id"]
    assert gateway.charges == {}
    assert billing_plan(done)["charge"] is False


def test_late_fee_applies_once_after_seven_days_on_unpaid_invoices():
    invoiced = _job(payment_mode=INVOICE_MODE, invoice_id="in_1")
    six_days = datetime.fromisoformat(invoiced["actual_completion"]) + timedelta(days=6)
    assert late_fee_due(invoiced, six_days) is None
    decision = late_fee_due(invoiced, NOW)
    assert decision["amount"] == 25
    assert decision["job_id"] == "job-1"

    updated = apply_late_fee(invoiced, NOW)
    assert updated["late_fee"] == 25
    assert late_fee_due(updated, NOW + timedelta(days=30)) is None
    assert apply_late_fee(updated, NOW + timedelta(days=30)) is None

    assert late_fee_due(_job(payment_mode=CHARGE_MODE), NOW) is None
    paid = _job(payment_mode=INVOICE_MODE, payment_status="paid", invoice_id="in_1")
    assert late_fee_due(paid, NOW) is None
    charged = _job(payment_mode=INVOICE_MODE, charged_at="t", invoice_id="in_1")
    assert late_fee_due(charged, NOW) is None
