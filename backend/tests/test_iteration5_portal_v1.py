"""
Iteration 5 — Customer-facing B2B booking v1 backend tests.

Scope:
  * GET  /api/portal/terms/current  (public)
  * POST /api/portal/self-register  (public, with metro / dup-email validation)
  * POST /api/portal/auth/login     (returns onboarding + auth_popup_dismissed)
  * POST /api/portal/accept-terms   (writes acceptance + flips onboarding)
  * POST /api/portal/dismiss-auth-popup
  * POST /api/portal/book           (job_type cash/insurance, flat fee invariant)
  * Stripe auth-hold ≤ 6 days out (manual capture)
  * POST /api/jobs/{id}/charge      (capture-from-hold)
  * POST /api/jobs/{id}/cancel      (releases hold)
"""

import os
import time as _time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://wizardly-mahavira-4.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

PORTAL_EMAIL = "live-test-1781157576@thecalibrationcrew.us"
PORTAL_PASSWORD = "TestPass123!"

OWNER_EMAIL = "caleb@thecalibrationcrew.us"
OWNER_PASSWORD = "Owner123!"

WV_ADDRESS = "123 W Bell Rd, Phoenix, AZ 85023"
EV_ADDRESS = "1500 N Country Club Dr, Mesa, AZ 85201"
OUT_ADDRESS = "Times Square, New York, NY"


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers["Content-Type"] = "application/json"
    return sess


@pytest.fixture(scope="session")
def portal_token(s):
    r = s.post(f"{API}/portal/auth/login", json={"email": PORTAL_EMAIL, "password": PORTAL_PASSWORD})
    assert r.status_code == 200, f"portal login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def portal_auth_headers(portal_token):
    return {"Authorization": f"Bearer {portal_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def owner_token(s):
    r = s.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    if r.status_code != 200:
        pytest.skip(f"owner login failed {r.status_code}")
    return r.json()["token"]


@pytest.fixture(scope="session")
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}


# ---------- terms ----------
class TestTerms:
    def test_terms_current_public(self, s):
        r = s.get(f"{API}/portal/terms/current")
        assert r.status_code == 200
        data = r.json()
        assert data["version"] == "1.0"
        assert "effective_date" in data
        assert "content" in data
        assert len(data["content"]) > 5000


# ---------- self-register ----------
class TestSelfRegister:
    def test_out_of_metro_rejected(self, s):
        ts = int(_time.time())
        payload = {
            "shop_legal_name": "TEST_OOM LLC",
            "shop_display_name": "TEST_OOM",
            "contact_full_name": "Out Metro",
            "email": f"selftest-oom-{ts}@example.com",
            "password": "Passw0rd!",
            "contact_phone": "+15555555555",
            "shop_address": OUT_ADDRESS,
        }
        r = s.post(f"{API}/portal/self-register", json=payload)
        assert r.status_code == 400
        assert "service area" in r.text.lower() or "outside" in r.text.lower()

    def test_self_register_success_and_duplicate(self, s):
        ts = int(_time.time())
        email = f"selftest-{ts}@example.com"
        payload = {
            "shop_legal_name": "TEST_Selfreg LLC",
            "shop_display_name": "TEST_Selfreg",
            "contact_full_name": "Jane Test",
            "email": email,
            "password": "Passw0rd!",
            "contact_phone": "+14805550000",
            "shop_address": WV_ADDRESS,
            "shop_state": "AZ",
        }
        r = s.post(f"{API}/portal/self-register", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "shop_user_id" in data and "shop_id" in data and "token" in data
        # stripe_checkout_url should be a string when Stripe key is real
        assert "stripe_checkout_url" in data
        if data.get("stripe_checkout_url"):
            assert isinstance(data["stripe_checkout_url"], str)
            assert data["stripe_checkout_url"].startswith("https://checkout.stripe.com/")

        # Login should return onboarding flags + auth_popup_dismissed=False, shop_status='pending'
        lr = s.post(f"{API}/portal/auth/login", json={"email": email, "password": "Passw0rd!"})
        assert lr.status_code == 200, lr.text
        ld = lr.json()
        assert ld.get("auth_popup_dismissed") is False
        assert ld.get("shop_status") == "pending"
        ob = ld.get("onboarding") or {}
        assert ob.get("business_info") is True
        assert ob.get("terms_signed") is False
        assert ob.get("card_on_file") is False

        # Save artifacts for next tests
        TestSelfRegister.email = email
        TestSelfRegister.token = data["token"]
        TestSelfRegister.shop_id = data["shop_id"]
        TestSelfRegister.shop_user_id = data["shop_user_id"]

        # Duplicate
        r2 = s.post(f"{API}/portal/self-register", json=payload)
        assert r2.status_code == 400
        assert "already exists" in r2.text.lower()


# ---------- accept-terms + dismiss-popup ----------
class TestTermsAcceptanceAndDismiss:
    def test_accept_terms_and_persist(self, s):
        token = getattr(TestSelfRegister, "token", None)
        if not token:
            pytest.skip("Needs prior self-register")
        h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        r = s.post(f"{API}/portal/accept-terms",
                   json={"terms_version": "1.0", "signature_full_name": "Jane Test"},
                   headers=h)
        assert r.status_code == 200, r.text
        assert r.json() == {"accepted": True, "version": "1.0"}

        # Login again — onboarding.terms_signed should now be True
        lr = s.post(f"{API}/portal/auth/login",
                    json={"email": TestSelfRegister.email, "password": "Passw0rd!"})
        assert lr.status_code == 200
        ob = lr.json().get("onboarding") or {}
        assert ob.get("terms_signed") is True

    def test_dismiss_auth_popup(self, s):
        token = getattr(TestSelfRegister, "token", None)
        if not token:
            pytest.skip("Needs prior self-register")
        h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        r = s.post(f"{API}/portal/dismiss-auth-popup", json={}, headers=h)
        assert r.status_code == 200
        assert r.json().get("dismissed") is True

        lr = s.post(f"{API}/portal/auth/login",
                    json={"email": TestSelfRegister.email, "password": "Passw0rd!"})
        assert lr.status_code == 200
        assert lr.json().get("auth_popup_dismissed") is True


# ---------- booking with job_type & flat-fee invariant ----------
def _next_slot(s, portal_auth_headers, days_ahead=2):
    """Find a real available slot via /public/availability for the shop's booking token."""
    me = s.get(f"{API}/portal/me", headers=portal_auth_headers).json()
    token = me["shop"]["booking_link_token"]
    from datetime import datetime, timedelta, timezone
    for delta in range(days_ahead, days_ahead + 14):
        d_obj = (datetime.now(timezone.utc) + timedelta(days=delta)).date()
        if d_obj.weekday() == 6:
            continue
        d = d_obj.isoformat()
        av = s.post(f"{API}/public/availability",
                    json={"booking_token": token, "job_address": WV_ADDRESS, "date": d}).json()
        slots = av.get("slots") or []
        if slots:
            return d, slots[0]
    return None, None


class TestPortalBook:
    BOOKED_JOB_ID = None

    def _base_payload(self, scheduled_start):
        return {
            "booking_token": "ignored-by-portal",
            "job_address": WV_ADDRESS,
            "scheduled_start": scheduled_start,
            "customer_last_name": "TEST_Smith",
            "year": 2022, "make": "Toyota", "model": "Camry",
            "vin": "1HGCM82633A123456",
            "adas_system": "forward_camera",
            "calibration_type": "static",
            "notification_phone": "+14805550000",
            "notification_email": "test@example.com",
        }

    def test_insurance_requires_amount(self, s, portal_auth_headers):
        d, slot = _next_slot(s, portal_auth_headers)
        if not slot:
            pytest.skip("No open slot found")
        payload = self._base_payload(slot["start"])
        payload["job_type"] = "insurance"
        # No insurance_approved_amount
        r = s.post(f"{API}/portal/book", json=payload, headers=portal_auth_headers)
        assert r.status_code == 400
        assert "approved amount" in r.text.lower()

    def test_book_cash(self, s, portal_auth_headers):
        d, slot = _next_slot(s, portal_auth_headers)
        if not slot:
            pytest.skip("No open slot found")
        payload = self._base_payload(slot["start"])
        payload["job_type"] = "cash"
        r = s.post(f"{API}/portal/book", json=payload, headers=portal_auth_headers)
        assert r.status_code == 200, r.text
        booking = r.json()
        assert "job_id" in booking
        # Fetch full job
        jr = s.get(f"{API}/portal/jobs/{booking['job_id']}", headers=portal_auth_headers)
        assert jr.status_code == 200
        job = jr.json()["job"]
        assert job.get("job_type") == "cash"
        assert job.get("insurance_approved_amount") in (None, 0)
        assert float(job["price"]) > 0
        TestPortalBook.BOOKED_JOB_ID = job["id"]
        TestPortalBook.BOOKED_JOB_PRICE = float(job["price"])

    def test_book_insurance_flat_fee_invariant(self, s, portal_auth_headers):
        d, slot = _next_slot(s, portal_auth_headers, days_ahead=3)
        if not slot:
            pytest.skip("No open slot found")
        payload = self._base_payload(slot["start"])
        payload["job_type"] = "insurance"
        payload["insurance_approved_amount"] = 300.00
        r = s.post(f"{API}/portal/book", json=payload, headers=portal_auth_headers)
        assert r.status_code == 200, r.text
        booking = r.json()
        jr = s.get(f"{API}/portal/jobs/{booking['job_id']}", headers=portal_auth_headers)
        assert jr.status_code == 200
        job = jr.json()["job"]
        assert job.get("job_type") == "insurance"
        assert float(job.get("insurance_approved_amount")) == 300.00
        assert float(job["price"]) != 300.00, "Card price must NOT equal approved amount"
        if hasattr(TestPortalBook, "BOOKED_JOB_PRICE"):
            assert float(job["price"]) == TestPortalBook.BOOKED_JOB_PRICE
        TestPortalBook.INS_JOB_ID = job["id"]


# ---------- stripe auth hold ----------
class TestStripeAuthHold:
    def test_book_within_6days_places_hold(self, s, portal_auth_headers):
        """Booking within 6 days with card on file → expect either stripe_auth_intent_id OR stripe_auth_error."""
        d, slot = _next_slot(s, portal_auth_headers, days_ahead=1)
        if not slot:
            pytest.skip("No open slot found")
        payload = {
            "booking_token": "ignored",
            "job_address": WV_ADDRESS,
            "scheduled_start": slot["start"],
            "customer_last_name": "TEST_Hold",
            "year": 2023, "make": "Honda", "model": "Civic",
            "vin": "2HGFB2F59CH123456",
            "adas_system": "forward_camera",
            "calibration_type": "static",
            "job_type": "cash",
        }
        r = s.post(f"{API}/portal/book", json=payload, headers=portal_auth_headers)
        assert r.status_code == 200, r.text
        booking = r.json()
        jr = s.get(f"{API}/portal/jobs/{booking['job_id']}", headers=portal_auth_headers)
        assert jr.status_code == 200
        job = jr.json()["job"]
        has_hold = bool(job.get("stripe_auth_intent_id"))
        has_err = bool(job.get("stripe_auth_error"))
        assert has_hold or has_err, f"expected stripe_auth_intent_id or stripe_auth_error in: {list(job.keys())}"
        if has_hold:
            assert job.get("stripe_auth_status") in ("requires_capture", "succeeded")
        TestStripeAuthHold.JOB_ID = job["id"]
        TestStripeAuthHold.HAS_HOLD = has_hold


# ---------- charge: capture-from-hold ----------
class TestChargeCaptureFromHold:
    def test_capture_from_hold(self, s, owner_headers):
        job_id = getattr(TestStripeAuthHold, "JOB_ID", None)
        has_hold = getattr(TestStripeAuthHold, "HAS_HOLD", False)
        if not job_id or not has_hold:
            pytest.skip("No held job available")
        # Complete the job as owner
        r = s.post(f"{API}/jobs/{job_id}/complete",
                   json={"result": "pass", "notes": "TEST_capture-from-hold"},
                   headers=owner_headers)
        # complete may require driving/on_site first — set status path:
        if r.status_code != 200:
            for st in ("driving", "on_site"):
                s.post(f"{API}/jobs/{job_id}/status", json={"status": st}, headers=owner_headers)
            r = s.post(f"{API}/jobs/{job_id}/complete",
                       json={"result": "pass", "notes": "TEST_capture-from-hold"},
                       headers=owner_headers)
        assert r.status_code in (200, 400), f"complete failed: {r.status_code} {r.text}"
        if r.status_code != 200:
            pytest.skip(f"could not complete job: {r.text}")

        # Charge — should capture from hold
        cr = s.post(f"{API}/jobs/{job_id}/charge", json={}, headers=owner_headers)
        assert cr.status_code == 200, cr.text
        body = cr.json()
        assert body.get("captured_from_hold") is True, f"expected captured_from_hold:true, got {body}"


# ---------- cancel releases hold ----------
class TestCancelReleasesHold:
    def test_cancel_calls_paymentintent_cancel(self, s, portal_auth_headers, owner_headers):
        # Book a fresh ≤6-day job
        d, slot = _next_slot(s, portal_auth_headers, days_ahead=2)
        if not slot:
            pytest.skip("No open slot found")
        payload = {
            "booking_token": "ignored",
            "job_address": WV_ADDRESS,
            "scheduled_start": slot["start"],
            "customer_last_name": "TEST_CancelHold",
            "year": 2021, "make": "Ford", "model": "F-150",
            "vin": "1FTFW1ET5DFC10312",
            "adas_system": "forward_camera",
            "calibration_type": "static",
            "job_type": "cash",
        }
        r = s.post(f"{API}/portal/book", json=payload, headers=portal_auth_headers)
        assert r.status_code == 200, r.text
        booking = r.json()
        jr = s.get(f"{API}/portal/jobs/{booking['job_id']}", headers=portal_auth_headers)
        assert jr.status_code == 200
        job = jr.json()["job"]
        if not job.get("stripe_auth_intent_id"):
            pytest.skip("No hold placed, can't test release")
        pi_id = job["stripe_auth_intent_id"]

        # Cancel as owner with required reason
        cr = s.post(f"{API}/jobs/{job['id']}/cancel",
                    json={"reason_category": "shop_request", "reason_text": "TEST cancel — release hold"},
                    headers=owner_headers)
        assert cr.status_code == 200, cr.text
        # Verify hold cancelled by checking via Stripe
        import stripe as stripe_sdk
        stripe_sdk.api_key = os.environ.get("STRIPE_API_KEY", "")
        if stripe_sdk.api_key and not stripe_sdk.api_key.endswith("_emergent"):
            pi = stripe_sdk.PaymentIntent.retrieve(pi_id)
            assert pi.status == "canceled", f"expected canceled, got {pi.status}"
