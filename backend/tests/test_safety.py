"""Shop mail stays in the outbox, and automatic charges stay off, until the flags are on.

    cd backend && pytest tests/test_safety.py -v
"""
from safety import (
    ALLOWLIST_EMAIL_KINDS,
    HELD_REASON,
    automatic_charge_allowed,
    email_delivery,
    env_flag,
    late_fee_sweep_allowed,
    parse_allowlist,
    stripe_key_for_use,
    stripe_key_mode,
)


def test_flags_default_off():
    assert env_flag(None) is False
    assert env_flag("") is False
    assert env_flag("false") is False
    assert env_flag("true") is True
    assert env_flag("YES") is True


def test_shop_mail_is_held_until_the_flag_is_on():
    allow = parse_allowlist("")
    for kind in (
        "invite", "welcome", "job_invoice", "receipt", "payment_failed_shop",
        "password_reset", "late_fee_shop", "booking_confirmation",
    ):
        assert email_delivery(kind, "shop@glass.test", enabled=False, allowlist=allow) == "hold"
        assert email_delivery(kind, "shop@glass.test", enabled=True, allowlist=allow) == "send"
    assert email_delivery("contact", "caleb@thecalibrationcrew.us", enabled=False, allowlist=allow) == "send"
    assert email_delivery("payment_failed_owner", "caleb@thecalibrationcrew.us", enabled=False, allowlist=allow) == "send"
    assert email_delivery("signup_finished", "caleb@thecalibrationcrew.us", enabled=False, allowlist=allow) == "send"
    assert HELD_REASON


def test_allowlist_sends_only_invite_and_password_reset():
    allow = parse_allowlist(" Caleb@TheCalibrationCrew.us , other@test.com ")
    assert "caleb@thecalibrationcrew.us" in allow
    assert email_delivery("invite", "caleb@thecalibrationcrew.us", enabled=False, allowlist=allow) == "send"
    assert email_delivery("password_reset", "caleb@thecalibrationcrew.us", enabled=False, allowlist=allow) == "send"
    assert email_delivery("welcome", "caleb@thecalibrationcrew.us", enabled=False, allowlist=allow) == "hold"
    assert email_delivery("job_invoice", "caleb@thecalibrationcrew.us", enabled=False, allowlist=allow) == "hold"
    assert email_delivery("invite", "shop@glass.test", enabled=False, allowlist=allow) == "hold"
    assert ALLOWLIST_EMAIL_KINDS == frozenset({"invite", "password_reset"})


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
