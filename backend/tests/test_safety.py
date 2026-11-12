"""Automatic charges stay off until BILLING_ENABLED is on.

Shop mail uses booking_mail.mail_route and the shared email_outbox.
Invite and password-reset mail may still send to TEST_EMAIL_ALLOWLIST.

    cd backend && pytest tests/test_safety.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from booking_mail import mail_route  # noqa: E402
from safety import (  # noqa: E402
    automatic_charge_allowed,
    env_flag,
    late_fee_sweep_allowed,
    stripe_key_for_use,
    stripe_key_mode,
)


def test_flags_default_off():
    assert env_flag(None) is False
    assert env_flag("") is False
    assert env_flag("false") is False
    assert env_flag("true") is True
    assert env_flag("YES") is True


def test_allowlist_sends_only_invite_and_password_reset(monkeypatch):
    monkeypatch.setenv("SHOP_EMAILS_ENABLED", "false")
    monkeypatch.setenv("TEST_EMAIL_ALLOWLIST", " Caleb@TheCalibrationCrew.us , other@test.com ")
    assert mail_route("shop", "booking_confirmation", "shop@glass.test") == "hold"
    assert mail_route("shop", "welcome", "caleb@thecalibrationcrew.us") == "hold"
    assert mail_route("shop", "job_invoice", "caleb@thecalibrationcrew.us") == "hold"
    assert mail_route("shop", "invite", "caleb@thecalibrationcrew.us") == "send"
    assert mail_route("shop", "password_reset", "caleb@thecalibrationcrew.us") == "send"
    assert mail_route("shop", "invite", "shop@glass.test") == "hold"
    monkeypatch.setenv("SHOP_EMAILS_ENABLED", "true")
    assert mail_route("shop", "welcome", "shop@glass.test") == "send"


def test_live_stripe_key_is_ignored_until_billing_is_on():
    live = "sk_live_example"
    test = "sk_test_example"
    restricted = "rk_test_example"
    assert stripe_key_mode(live) == "live"
    assert stripe_key_mode(test) == "test"
    assert stripe_key_mode("sk_test_emergent") == "unusable"
    assert stripe_key_for_use(live, billing_enabled=False) == ""
    assert stripe_key_for_use(live, billing_enabled=True) == live
    assert stripe_key_for_use(test, billing_enabled=False) == test
    assert stripe_key_for_use(restricted, billing_enabled=False) == restricted
    assert automatic_charge_allowed(False) is False
    assert automatic_charge_allowed(True) is True
    assert late_fee_sweep_allowed(False) is False
