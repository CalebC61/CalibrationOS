"""Owner approve and decline links are signed, single-use, expiring, and owner-only.

Opening a link does not change the job. Confirming it does, once.

    cd backend && pytest tests/test_owner_links.py -v
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from owner_links import (  # noqa: E402
    assess_owner_link,
    mark_used,
    mint_owner_link,
)

SECRET = "test-secret"
NOW = datetime(2026, 11, 12, 17, 0, tzinfo=timezone.utc)


def _mint(action="approve", **kwargs):
    return mint_owner_link(secret=SECRET, job_id="job-1", action=action, now=NOW, **kwargs)


def test_a_fresh_link_previews_without_being_used():
    minted = _mint()
    decision = assess_owner_link(SECRET, minted["token"], minted["record"], NOW)
    assert decision["ok"] is True
    assert decision["action"] == "approve"
    assert decision["job_id"] == "job-1"
    assert decision["purpose"] == "owner"
    assert minted["record"]["used_at"] is None
    assert decision["consumes"] is False


def test_confirming_a_link_uses_it_once():
    minted = _mint()
    used = mark_used(minted["record"], NOW)
    assert used["used_at"] == NOW.isoformat()
    again = assess_owner_link(SECRET, minted["token"], used, NOW + timedelta(minutes=1))
    assert again["ok"] is False
    assert "already used" in again["error"].lower()


def test_an_expired_link_is_rejected():
    minted = _mint(ttl_hours=1)
    later = NOW + timedelta(hours=2)
    decision = assess_owner_link(SECRET, minted["token"], minted["record"], later)
    assert decision["ok"] is False
    assert "expired" in decision["error"].lower()


def test_a_tampered_link_is_rejected():
    minted = _mint()
    token = minted["token"]
    flipped = ("A" if token[0] != "A" else "B") + token[1:]
    decision = assess_owner_link(SECRET, flipped, minted["record"], NOW)
    assert decision["ok"] is False
    assert "not valid" in decision["error"].lower()


def test_a_link_signed_with_the_wrong_secret_is_rejected():
    minted = _mint()
    decision = assess_owner_link("other-secret", minted["token"], minted["record"], NOW)
    assert decision["ok"] is False


def test_a_decline_link_cannot_be_treated_as_approve():
    minted = _mint("decline")
    decision = assess_owner_link(SECRET, minted["token"], minted["record"], NOW)
    assert decision["ok"] is True
    assert decision["action"] == "decline"
    swapped = dict(minted["record"], action="approve")
    mismatch = assess_owner_link(SECRET, minted["token"], swapped, NOW)
    assert mismatch["ok"] is False


def test_a_non_owner_purpose_is_rejected():
    minted = _mint()
    shop_record = dict(minted["record"], purpose="shop")
    decision = assess_owner_link(SECRET, minted["token"], shop_record, NOW)
    assert decision["ok"] is False
    assert "not valid" in decision["error"].lower()


def test_a_link_for_a_different_job_is_rejected():
    minted = _mint()
    other = dict(minted["record"], job_id="job-2")
    decision = assess_owner_link(SECRET, minted["token"], other, NOW)
    assert decision["ok"] is False


def test_an_unknown_link_is_rejected():
    minted = _mint()
    decision = assess_owner_link(SECRET, minted["token"], None, NOW)
    assert decision["ok"] is False
    assert "not valid" in decision["error"].lower()
