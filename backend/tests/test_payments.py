"""Stripe payload shape for card setup and off-session charges.

stripe-python 16 pins API version 2026-09-30.endive, which rejects
payment_method_types on create. These tests do not call Stripe.

    cd backend && pytest tests/test_payments.py -v
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from payments import (  # noqa: E402
    charge_job,
    create_anonymous_setup_intent,
    create_checkout_setup,
    create_setup_intent,
)


class _StripeObject:
    id = "seti_test"
    client_secret = "seti_test_secret"
    url = "https://checkout.stripe.test/session"

    def to_dict(self):
        return {
            "id": self.id,
            "client_secret": self.client_secret,
            "url": self.url,
            "status": "succeeded",
        }


class _Calls:
    def __init__(self, name, calls):
        self.name = name
        self.calls = calls

    def create(self, payload, options=None):
        self.calls.append((self.name, payload, options))
        return _StripeObject()


class _Client:
    def __init__(self):
        self.calls = []
        sessions = _Calls("checkout", self.calls)
        self.v1 = type("V1", (), {
            "setup_intents": _Calls("setup_intent", self.calls),
            "payment_intents": _Calls("payment_intent", self.calls),
            "checkout": type("Checkout", (), {"sessions": sessions})(),
        })()


def _assert_card_only(payload):
    assert payload["allowed_payment_method_types"] == ["card"]
    assert "link" not in payload["allowed_payment_method_types"]
    assert "us_bank_account" not in payload["allowed_payment_method_types"]
    assert "payment_method_types" not in payload
    assert "automatic_payment_methods" not in payload


def test_signup_setup_intent_allows_only_card():
    client = _Client()
    created = create_anonymous_setup_intent(client)
    assert created["client_secret"] == "seti_test_secret"
    name, payload, options = client.calls[0]
    assert name == "setup_intent"
    assert options is None
    assert payload["usage"] == "off_session"
    assert payload["metadata"] == {"purpose": "shop_signup"}
    assert "customer" not in payload
    _assert_card_only(payload)


def test_settings_setup_intent_allows_only_card():
    client = _Client()
    create_setup_intent(client, customer_id="cus_shop", shop_user_id="user-1")
    _, payload, _ = client.calls[0]
    assert payload["customer"] == "cus_shop"
    assert payload["usage"] == "off_session"
    assert payload["metadata"] == {"shop_user_id": "user-1"}
    _assert_card_only(payload)


def test_checkout_setup_allows_only_card_and_hides_link():
    client = _Client()
    url = create_checkout_setup(
        client,
        customer_id="cus_shop",
        shop_user_id="user-1",
        success_url="https://example.test/ok",
        cancel_url="https://example.test/cancel",
    )
    assert url == "https://checkout.stripe.test/session"
    _, payload, _ = client.calls[0]
    assert payload["mode"] == "setup"
    assert payload["customer"] == "cus_shop"
    _assert_card_only(payload)
    assert payload["wallet_options"] == {"link": {"display": "never"}}


def test_job_charge_confirms_the_saved_card_without_payment_method_types():
    client = _Client()
    result = charge_job(
        client,
        job={"id": "job-1", "price": 185, "charge_attempts": 0, "shop_id": "shop-1"},
        customer_id="cus_shop",
        payment_method_id="pm_card",
        receipt_email=None,
    )
    assert result["outcome"] == "succeeded"
    _, payload, options = client.calls[0]
    assert payload["payment_method"] == "pm_card"
    assert payload["customer"] == "cus_shop"
    assert payload["off_session"] is True
    assert payload["confirm"] is True
    assert payload["amount"] == 18500
    assert "payment_method_types" not in payload
    assert "allowed_payment_method_types" not in payload
    assert options["idempotency_key"]


def test_stripe_call_sites_do_not_send_the_removed_parameter():
    backend = Path(__file__).resolve().parents[1]
    for name in ("payments.py", "server.py"):
        text = (backend / name).read_text()
        assert '"payment_method_types"' not in text
        assert "'payment_method_types'" not in text
