"""Iteration 7 — Backend refactor regression sweep.

Verify that the split of server.py into routers (auth, shops, jobs, field,
owner, billing, portal, xero) preserved every endpoint and behaviour.
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"

OWNER = ("caleb@thecalibrationcrew.us", "Owner123!")
CONTRACTOR = ("contractor@thecalibrationcrew.us", "Contractor123!")
PORTAL = ("live-test-1781157576@thecalibrationcrew.us", "TestPass123!")


def _login(path, email, pw):
    r = requests.post(f"{API}{path}", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, f"{path} login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner_token():
    return _login("/auth/login", *OWNER)


@pytest.fixture(scope="module")
def contractor_token():
    return _login("/auth/login", *CONTRACTOR)


@pytest.fixture(scope="module")
def portal_token():
    return _login("/portal/auth/login", *PORTAL)


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------- auth router ----------
class TestAuthRouter:
    def test_login_returns_jwt(self):
        r = requests.post(f"{API}/auth/login", json={"email": OWNER[0], "password": OWNER[1]})
        assert r.status_code == 200
        body = r.json()
        assert "token" in body and isinstance(body["token"], str) and len(body["token"]) > 20

    def test_login_bad_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": OWNER[0], "password": "WRONG"})
        assert r.status_code == 401

    def test_me(self, owner_token):
        r = requests.get(f"{API}/auth/me", headers=H(owner_token))
        assert r.status_code == 200
        assert r.json()["email"] == OWNER[0]

    def test_me_unauth(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code in (401, 403)

    def test_reference_zones(self):
        r = requests.get(f"{API}/reference/zones")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list) and len(body) > 0
        assert "slug" in body[0] or "key" in body[0]

    def test_reference_pricing(self):
        r = requests.get(f"{API}/reference/pricing")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_geocode_az(self, owner_token):
        r = requests.post(
            f"{API}/geocode",
            headers=H(owner_token),
            json={"address": "123 W Bell Rd, Phoenix, AZ 85023"},
        )
        assert r.status_code == 200
        b = r.json()
        assert "lat" in b and "lng" in b and "zone" in b


# ---------- shops router ----------
class TestShopsRouter:
    def test_list_shops(self, owner_token):
        r = requests.get(f"{API}/shops", headers=H(owner_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) > 0

    def test_get_shop(self, owner_token):
        shops = requests.get(f"{API}/shops", headers=H(owner_token)).json()
        sid = shops[0]["id"]
        r = requests.get(f"{API}/shops/{sid}", headers=H(owner_token))
        assert r.status_code == 200
        assert r.json()["id"] == sid

    def test_public_shop_token(self, owner_token):
        shops = requests.get(f"{API}/shops", headers=H(owner_token)).json()
        token = next((s["booking_link_token"] for s in shops if s.get("booking_link_token")), None)
        assert token
        r = requests.get(f"{API}/public/shop/{token}")
        assert r.status_code == 200
        assert "name" in r.json()

    def test_public_shop_unknown(self):
        r = requests.get(f"{API}/public/shop/UNKNOWN_TOKEN_XYZ")
        assert r.status_code == 404

    def test_public_availability(self, owner_token):
        from datetime import datetime, timezone, timedelta
        shops = requests.get(f"{API}/shops", headers=H(owner_token)).json()
        gilbert = next((s for s in shops if "Gilbert" in s["name"]), shops[0])
        token = gilbert["booking_link_token"]
        target = datetime.now(timezone.utc).date()
        while target.weekday() == 6:
            target += timedelta(days=1)
        r = requests.post(
            f"{API}/public/availability",
            json={"booking_token": token, "job_address": "123 W Bell Rd, Phoenix, AZ 85023", "date": target.isoformat()},
        )
        assert r.status_code == 200
        body = r.json()
        assert "slots" in body and isinstance(body["slots"], list)


# ---------- jobs router ----------
class TestJobsRouter:
    def test_list_jobs(self, owner_token):
        r = requests.get(f"{API}/jobs", headers=H(owner_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_jobs_unauth(self):
        r = requests.get(f"{API}/jobs")
        assert r.status_code in (401, 403)

    def test_get_job_404(self, owner_token):
        r = requests.get(f"{API}/jobs/NONEXISTENT", headers=H(owner_token))
        assert r.status_code == 404


# ---------- field router ----------
class TestFieldRouter:
    def test_contractors_list(self, owner_token):
        r = requests.get(f"{API}/contractors", headers=H(owner_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_contractor_offers_list(self, owner_token):
        r = requests.get(f"{API}/contractor-offers", headers=H(owner_token))
        assert r.status_code == 200


# ---------- billing router ----------
class TestBillingRouter:
    def test_charge_queue(self, owner_token):
        r = requests.get(f"{API}/charge-queue", headers=H(owner_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- xero router ----------
class TestXeroRouter:
    def test_xero_status(self, owner_token):
        r = requests.get(f"{API}/xero/status", headers=H(owner_token))
        assert r.status_code == 200
        body = r.json()
        assert "connected" in body

    def test_xero_auth_start(self, owner_token):
        r = requests.get(f"{API}/xero/auth/start", headers=H(owner_token))
        assert r.status_code == 200
        b = r.json()
        # accepts {url:...} or similar
        url = b.get("url") or b.get("authorize_url") or b.get("auth_url")
        assert url and "xero.com" in url
        assert "client_id" in url
        assert "scope" in url or "scopes" in url


# ---------- portal router ----------
class TestPortalRouter:
    def test_terms_current(self):
        r = requests.get(f"{API}/portal/terms/current")
        assert r.status_code == 200
        b = r.json()
        assert b.get("version") in ("1.0", "v1.0")
        assert "body" in b or "content" in b or "html" in b or "title" in b

    def test_portal_me(self, portal_token):
        r = requests.get(f"{API}/portal/me", headers=H(portal_token))
        assert r.status_code == 200
        b = r.json()
        assert "shop" in b and "shop_user" in b
        assert b["shop_user"]["email"] == PORTAL[0]

    def test_portal_jobs(self, portal_token):
        r = requests.get(f"{API}/portal/jobs", headers=H(portal_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_portal_day_map(self, portal_token):
        r = requests.get(f"{API}/portal/day-map", headers=H(portal_token))
        assert r.status_code == 200

    def test_portal_dismiss_auth_popup(self, portal_token):
        r = requests.post(f"{API}/portal/dismiss-auth-popup", headers=H(portal_token))
        assert r.status_code == 200

    def test_public_invite_invalid(self):
        r = requests.get(f"{API}/public/invites/INVALID_TOKEN_XYZ")
        assert r.status_code in (400, 404)


# ---------- owner router ----------
class TestOwnerRouter:
    def test_dashboard_summary(self, owner_token):
        r = requests.get(f"{API}/dashboard/summary", headers=H(owner_token))
        assert r.status_code == 200
        b = r.json()
        # must contain some metric keys
        assert isinstance(b, dict) and len(b) > 0

    def test_sms_log(self, owner_token):
        r = requests.get(f"{API}/sms-log", headers=H(owner_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_email_log(self, owner_token):
        r = requests.get(f"{API}/email-log", headers=H(owner_token))
        assert r.status_code == 200
        b = r.json()
        # email-log returns dict with sent + pending_manual
        assert isinstance(b, dict) and "sent" in b and "pending_manual" in b
        assert isinstance(b["sent"], list)

    def test_invoices(self, owner_token):
        r = requests.get(f"{API}/invoices", headers=H(owner_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_notifications_new_bookings(self, owner_token):
        r = requests.get(f"{API}/notifications/new-bookings", headers=H(owner_token))
        assert r.status_code == 200

    def test_invites_list(self, owner_token):
        r = requests.get(f"{API}/invites", headers=H(owner_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_public_shop_status(self, owner_token):
        shops = requests.get(f"{API}/shops", headers=H(owner_token)).json()
        tok = next((s["booking_link_token"] for s in shops if s.get("booking_link_token")), None)
        assert tok
        r = requests.get(f"{API}/public/shop-status/{tok}")
        assert r.status_code == 200


# ---------- 403 / forbidden cross-role ----------
class TestForbidden:
    def test_contractor_cannot_list_shops(self, contractor_token):
        r = requests.get(f"{API}/shops", headers=H(contractor_token))
        assert r.status_code in (401, 403)

    def test_portal_cannot_hit_owner_endpoints(self, portal_token):
        r = requests.get(f"{API}/dashboard/summary", headers=H(portal_token))
        assert r.status_code in (401, 403)


# ---------- end-to-end booking + cancel (exercises shops, jobs, billing) ----------
class TestPublicBookingFlow:
    def _avail_slot(self, owner_token):
        from datetime import datetime, timezone, timedelta
        shops = requests.get(f"{API}/shops", headers=H(owner_token)).json()
        gilbert = next((s for s in shops if "Gilbert" in s["name"]), None)
        assert gilbert, "Safelite — Gilbert shop must exist"
        token = gilbert["booking_link_token"]
        target = datetime.now(timezone.utc).date()
        for _ in range(7):
            if target.weekday() == 6:
                target += timedelta(days=1); continue
            av = requests.post(
                f"{API}/public/availability",
                json={"booking_token": token, "job_address": "123 W Bell Rd, Phoenix, AZ 85023", "date": target.isoformat()},
            )
            assert av.status_code == 200
            slots = av.json().get("slots", [])
            if slots:
                return token, target, slots[0]
            target += timedelta(days=1)
        pytest.skip("No availability slots found in next 7 days")

    def test_book_and_cancel(self, owner_token):
        token, target, slot = self._avail_slot(owner_token)
        book = requests.post(
            f"{API}/public/book",
            json={
                "booking_token": token,
                "job_address": "123 W Bell Rd, Phoenix, AZ 85023",
                "scheduled_start": slot["start"],
                "customer_last_name": "TEST_Refactor",
                "year": 2022, "make": "Toyota", "model": "Camry",
                "adas_system": "forward_camera", "calibration_type": "static",
                "notification_phone": "+14805551212",
            },
        )
        assert book.status_code == 200, book.text
        job_id = book.json().get("job_id") or book.json().get("id")
        assert job_id

        gj = requests.get(f"{API}/jobs/{job_id}", headers=H(owner_token))
        assert gj.status_code == 200

        cx = requests.post(f"{API}/jobs/{job_id}/cancel", headers=H(owner_token), json={"reason": "TEST regression cleanup"})
        assert cx.status_code == 200

    def test_insurance_booking_requires_approved_amount(self, owner_token):
        token, target, slot = self._avail_slot(owner_token)
        r = requests.post(
            f"{API}/public/book",
            json={
                "booking_token": token,
                "job_address": "123 W Bell Rd, Phoenix, AZ 85023",
                "scheduled_start": slot["start"],
                "customer_last_name": "TEST_InsNoAmount",
                "year": 2022, "make": "Toyota", "model": "Camry",
                "adas_system": "forward_camera", "calibration_type": "static",
                "notification_phone": "+14805551212",
                "job_type": "insurance",
            },
        )
        # should 400 because insurance_approved_amount missing
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
