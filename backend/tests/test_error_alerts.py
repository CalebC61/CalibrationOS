"""Owner error alerts: who receives them, what is stripped, and how often they send.

    cd backend && pytest tests/test_error_alerts.py -v
"""
import json

import pytest

from error_alerts import (
    CLIENT_ERROR_MAX_BYTES,
    DEDUPE_SECONDS,
    HOURLY_CAP,
    AlertGate,
    alert_recipient,
    prepare_client_report,
    prepare_server_alert,
    reset_alerts,
    scrub,
)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    reset_alerts()
    for name in ("ALERT_EMAIL", "OWNER_EMAIL", "ADMIN_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    yield
    reset_alerts()


def test_scrub_removes_connection_strings_tokens_and_card_numbers():
    raw = (
        "boom mongodb+srv://user:secret@cluster.mongodb.net/db "
        "Authorization: Bearer super-secret-token "
        "sk_live_abc123456789 whsec_abcdef123456 re_abcdefghij "
        "card 4242424242424242 password=hunter2"
    )
    cleaned = scrub(raw)
    for secret in (
        "mongodb",
        "secret@",
        "super-secret-token",
        "Bearer",
        "Authorization",
        "sk_live_",
        "whsec_",
        "re_abcdefghij",
        "4242424242424242",
        "hunter2",
    ):
        assert secret not in cleaned


def test_recipient_uses_alert_email_then_owner_then_admin(monkeypatch):
    assert alert_recipient() is None
    monkeypatch.setenv("ADMIN_EMAIL", "admin@thecalibrationcrew.us")
    assert alert_recipient() == "admin@thecalibrationcrew.us"
    monkeypatch.setenv("OWNER_EMAIL", "owner@thecalibrationcrew.us")
    assert alert_recipient() == "owner@thecalibrationcrew.us"
    monkeypatch.setenv("ALERT_EMAIL", "alerts@thecalibrationcrew.us")
    assert alert_recipient() == "alerts@thecalibrationcrew.us"
    monkeypatch.setenv("ALERT_EMAIL", "   ")
    assert alert_recipient() == "owner@thecalibrationcrew.us"


def test_blank_recipient_does_not_fall_back_to_a_hardcoded_address(monkeypatch):
    monkeypatch.setenv("ALERT_EMAIL", "")
    monkeypatch.setenv("OWNER_EMAIL", "")
    monkeypatch.setenv("ADMIN_EMAIL", "")
    assert alert_recipient() is None


def test_same_error_sends_once_per_fifteen_minutes_and_again_after():
    gate = AlertGate()
    assert gate.allow("same", 1_000.0) is True
    assert gate.allow("same", 1_000.0 + 60) is False
    assert gate.allow("same", 1_000.0 + DEDUPE_SECONDS - 1) is False
    assert gate.allow("same", 1_000.0 + DEDUPE_SECONDS) is True


def test_a_different_error_still_sends_inside_the_window():
    gate = AlertGate()
    assert gate.allow("one", 1_000.0) is True
    assert gate.allow("two", 1_001.0) is True


def test_hourly_cap_blocks_further_unique_errors():
    gate = AlertGate()
    start = 5_000.0
    for index in range(HOURLY_CAP):
        assert gate.allow(f"err-{index}", start + index) is True
    assert gate.allow("one-more", start + HOURLY_CAP) is False
    assert gate.allow("after-the-hour", start + 3600) is True


def test_server_alert_includes_route_and_type_and_omits_the_request(monkeypatch):
    monkeypatch.setenv("ALERT_EMAIL", "alerts@thecalibrationcrew.us")
    monkeypatch.setenv("SHOP_EMAILS_ENABLED", "false")
    exc = RuntimeError("disk full sk_live_abc123456789")
    mail = prepare_server_alert(
        method="POST",
        path="/api/jobs/{job_id}?token=secret-token",
        exc=exc,
        traceback_text="Traceback\nAuthorization: Bearer super-secret-token\n",
        now=10_000.0,
    )
    assert mail["to"] == "alerts@thecalibrationcrew.us"
    assert mail["kind"] == "error_alert"
    blob = mail["subject"] + mail["html"]
    assert "RuntimeError" in blob
    assert "POST" in blob
    assert "/api/jobs/{job_id}" in blob
    assert "disk full" in blob
    assert "secret-token" not in blob
    assert "super-secret-token" not in blob
    assert "sk_live_" not in blob
    assert "Authorization" not in blob
    assert "SHOP_EMAILS_ENABLED" not in blob
    again = prepare_server_alert(
        method="POST",
        path="/api/jobs/{job_id}",
        exc=exc,
        traceback_text="Traceback",
        now=10_030.0,
    )
    assert again is None


def test_server_alert_is_skipped_when_no_address_is_configured():
    exc = RuntimeError("disk full")
    assert prepare_server_alert(
        method="GET",
        path="/api/health",
        exc=exc,
        traceback_text="Traceback",
        now=20_000.0,
    ) is None


def test_client_report_reuses_the_same_dedupe_and_strips_the_query(monkeypatch):
    monkeypatch.setenv("OWNER_EMAIL", "owner@thecalibrationcrew.us")
    raw = json.dumps({
        "message": "Something broke",
        "stack": "at Page sk_test_abc123456789",
        "path": "/dashboard?token=secret-token",
        "source": "boundary",
    }).encode()
    assert len(raw) < CLIENT_ERROR_MAX_BYTES
    mail = prepare_client_report(raw, now=30_000.0)
    assert mail["to"] == "owner@thecalibrationcrew.us"
    assert mail["kind"] == "error_alert"
    blob = mail["subject"] + mail["html"]
    assert "Something broke" in blob
    assert "/dashboard" in blob
    assert "boundary" in blob
    assert "secret-token" not in blob
    assert "sk_test_" not in blob
    assert prepare_client_report(raw, now=30_010.0) is None


def test_client_report_rejects_bad_json():
    with pytest.raises(ValueError):
        prepare_client_report(b"not-json", now=40_000.0)
    with pytest.raises(ValueError):
        prepare_client_report(b"[]", now=40_000.0)


def test_client_report_with_no_message_does_not_email(monkeypatch):
    monkeypatch.setenv("ALERT_EMAIL", "alerts@thecalibrationcrew.us")
    assert prepare_client_report(b'{"message":"","stack":""}', now=50_000.0) is None
