"""Iteration 4: at-risk detection, reschedule/cancel with reason, real file upload, public shop-status."""
import os
import io
import base64
import pytest
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
API = f"{BASE_URL}/api"

OWNER = {"email": "caleb@thecalibrationcrew.us", "password": "Owner123!"}
CONTRACTOR = {"email": "contractor@thecalibrationcrew.us", "password": "Contractor123!"}


def _auth(t): return {"Authorization": f"Bearer {t}"}


# ---------------- Fixtures ----------------
@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{API}/auth/login", json=OWNER, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def contractor_token():
    r = requests.post(f"{API}/auth/login", json=CONTRACTOR, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def shop_info(owner_token):
    shops = requests.get(f"{API}/shops", headers=_auth(owner_token), timeout=30).json()
    # pick first active one
    shop = next(s for s in shops if s.get("status") == "active")
    return shop


def _book_job(owner_token, shop, address, last_name, target_date=None):
    tok = shop["booking_link_token"]
    target = target_date or datetime.now(timezone.utc).date()
    while target.weekday() == 6:
        target += timedelta(days=1)
    av = requests.post(f"{API}/public/availability",
        json={"booking_token": tok, "job_address": address, "date": target.isoformat()},
        timeout=30).json()
    tries = 0
    while not av.get("slots") and tries < 5:
        target = target + timedelta(days=1)
        while target.weekday() == 6:
            target += timedelta(days=1)
        av = requests.post(f"{API}/public/availability",
            json={"booking_token": tok, "job_address": address, "date": target.isoformat()},
            timeout=30).json()
        tries += 1
    assert av.get("slots"), f"No slots: {av}"
    slot = av["slots"][0]
    payload = {
        "booking_token": tok,
        "scheduled_start": slot["start"],
        "customer_last_name": last_name,
        "year": 2022, "make": "Toyota", "model": "Camry",
        "adas_system": "forward_camera",
        "calibration_type": "static",
        "job_address": address,
        "notification_phone": "+15555550101",
    }
    r = requests.post(f"{API}/public/book", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    # public/book returns {"job_id": ..., ...}
    return {"id": data["job_id"], **data}


# ---------------- 1. At-risk detection ----------------
class TestAtRisk:
    def test_at_risk_booked_past_start(self, owner_token, shop_info):
        # Book a job, then force its scheduled_start into the past via direct mongo? We can't.
        # Instead, book today, and check that a booked job past start+10min is flagged.
        # If today has no past-start booked jobs we'll create one by booking the earliest slot
        # then assert: any booked job whose start was >10 min ago has is_at_risk=true.
        r = requests.get(f"{API}/jobs", headers=_auth(owner_token), timeout=30)
        assert r.status_code == 200
        jobs = r.json()
        now = datetime.now(timezone.utc)
        for j in jobs:
            assert "is_at_risk" in j
            assert "risk_reason" in j
            if j["status"] == "booked":
                start = datetime.fromisoformat(j["scheduled_start"].replace("Z", "+00:00"))
                if (now - start).total_seconds() > 10 * 60:
                    assert j["is_at_risk"] is True, f"Job {j['id']} should be at risk"
                    assert "past scheduled" in (j["risk_reason"] or "").lower()
                else:
                    assert j["is_at_risk"] is False

    def test_at_risk_driving_past_end(self, owner_token):
        r = requests.get(f"{API}/jobs", headers=_auth(owner_token), timeout=30)
        jobs = r.json()
        now = datetime.now(timezone.utc)
        for j in jobs:
            if j["status"] in ("driving", "on_site"):
                end = datetime.fromisoformat(j["scheduled_end"].replace("Z", "+00:00"))
                if now > end:
                    assert j["is_at_risk"] is True
                    assert "over" in (j["risk_reason"] or "").lower()


# ---------------- 2. Dashboard summary has at_risk_count ----------------
class TestDashboardSummary:
    def test_summary_includes_at_risk_count(self, owner_token):
        r = requests.get(f"{API}/dashboard/summary", headers=_auth(owner_token), timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "at_risk_count" in data
        assert isinstance(data["at_risk_count"], int)
        assert data["at_risk_count"] >= 0


# ---------------- 3. Reschedule ----------------
class TestReschedule:
    def test_reschedule_updates_times_and_logs_sms(self, owner_token, shop_info):
        job = _book_job(owner_token, shop_info, "TEST 101 Reschedule St, Phoenix AZ", "TESTRescheduleA")
        job_id = job["id"]
        # find a future slot across several days
        new_start = None
        for delta in range(2, 10):
            target = (datetime.now(timezone.utc) + timedelta(days=delta)).date()
            if target.weekday() == 6:
                continue
            av = requests.post(f"{API}/public/availability",
                json={"booking_token": shop_info["booking_link_token"],
                      "job_address": "TEST 101 Reschedule St, Phoenix AZ",
                      "date": target.isoformat()}, timeout=30).json()
            if av.get("slots"):
                new_start = av["slots"][0]["start"]
                break
        assert new_start, "No reschedule slot found"
        r = requests.post(f"{API}/jobs/{job_id}/reschedule",
            json={"scheduled_start": new_start, "reason": "TEST customer requested earlier time"},
            headers=_auth(owner_token), timeout=30)
        assert r.status_code == 200, r.text
        fresh = r.json()
        assert fresh["scheduled_start"] == new_start
        assert fresh["reschedule_reason"] == "TEST customer requested earlier time"
        assert "rescheduled_at" in fresh
        # scheduled_end recomputed
        s = datetime.fromisoformat(fresh["scheduled_start"].replace("Z", "+00:00"))
        e = datetime.fromisoformat(fresh["scheduled_end"].replace("Z", "+00:00"))
        assert (e - s).total_seconds() > 0

        # SMS log includes kind='rescheduled' for this job
        logs = requests.get(f"{API}/sms-log", headers=_auth(owner_token), timeout=30).json()
        match = [l for l in logs if l.get("job_id") == job_id and l.get("kind") == "rescheduled"]
        assert len(match) >= 1

    def test_reschedule_refuses_cancelled(self, owner_token, shop_info):
        job = _book_job(owner_token, shop_info, "TEST 102 Reschedule St, Phoenix AZ", "TESTRescheduleB")
        # cancel first
        requests.post(f"{API}/jobs/{job['id']}/cancel", json={"reason": "test"},
                      headers=_auth(owner_token), timeout=30)
        r = requests.post(f"{API}/jobs/{job['id']}/reschedule",
            json={"scheduled_start": datetime.now(timezone.utc).isoformat()},
            headers=_auth(owner_token), timeout=30)
        assert r.status_code == 400


# ---------------- 4. Cancel ----------------
class TestCancel:
    def test_cancel_with_reason(self, owner_token, shop_info):
        job = _book_job(owner_token, shop_info, "TEST 201 Cancel Ave, Phoenix AZ", "TESTCancelA")
        r = requests.post(f"{API}/jobs/{job['id']}/cancel",
            json={"reason": "TEST customer no longer needs service"},
            headers=_auth(owner_token), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "cancelled"
        assert d["cancellation_reason"] == "TEST customer no longer needs service"
        assert "cancelled_at" in d
        logs = requests.get(f"{API}/sms-log", headers=_auth(owner_token), timeout=30).json()
        match = [l for l in logs if l.get("job_id") == job["id"] and l.get("kind") == "cancelled"]
        assert len(match) >= 1
        assert "TEST customer no longer" in match[0]["body"]

    def test_double_cancel_400(self, owner_token, shop_info):
        job = _book_job(owner_token, shop_info, "TEST 202 Cancel Ave, Phoenix AZ", "TESTCancelB")
        r1 = requests.post(f"{API}/jobs/{job['id']}/cancel", json={},
                           headers=_auth(owner_token), timeout=30)
        assert r1.status_code == 200
        r2 = requests.post(f"{API}/jobs/{job['id']}/cancel", json={"reason": "again"},
                           headers=_auth(owner_token), timeout=30)
        assert r2.status_code == 400


# ---------------- 5. Document upload ----------------
class TestDocumentUpload:
    def test_upload_list_download(self, owner_token, shop_info):
        job = _book_job(owner_token, shop_info, "TEST 301 Doc Ln, Phoenix AZ", "TESTDoc")
        job_id = job["id"]
        # Minimal PNG bytes
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVQYV2NgYAAAAAMAAWgmWQ0AAAAASUVORK5CYII="
        )
        files = {"file": ("calibration_report.png", io.BytesIO(png), "image/png")}
        r = requests.post(f"{API}/jobs/{job_id}/upload-document", files=files,
                          headers=_auth(owner_token), timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert "data_b64" not in doc
        # Spec naming: Customer_SHOP_Make_Model_Year.ext
        assert doc["file_name"].startswith("TESTDoc_")
        assert doc["file_name"].endswith("_Toyota_Camry_2022.png")
        assert doc["size_bytes"] == len(png)
        doc_id = doc["id"]

        # list docs
        r2 = requests.get(f"{API}/jobs/{job_id}/documents",
                          headers=_auth(owner_token), timeout=30)
        assert r2.status_code == 200
        listed = r2.json()
        assert any(d["id"] == doc_id for d in listed)
        assert all("data_b64" not in d for d in listed)

        # download
        r3 = requests.get(f"{API}/documents/{doc_id}/download",
                          headers=_auth(owner_token), timeout=30)
        assert r3.status_code == 200
        assert r3.content == png
        assert "image/png" in r3.headers.get("content-type", "")
        cd = r3.headers.get("content-disposition", "")
        assert doc["file_name"] in cd

    def test_upload_too_large_rejected(self, owner_token, shop_info):
        job = _book_job(owner_token, shop_info, "TEST 302 Doc Ln, Phoenix AZ", "TESTDocBig")
        big = b"a" * (10 * 1024 * 1024 + 100)
        files = {"file": ("big.pdf", io.BytesIO(big), "application/pdf")}
        r = requests.post(f"{API}/jobs/{job['id']}/upload-document", files=files,
                          headers=_auth(owner_token), timeout=60)
        assert r.status_code == 400

    def test_contractor_cannot_download_others_doc(self, owner_token, contractor_token, shop_info):
        # Owner uploads to a job owned by themselves (no contractor assigned)
        job = _book_job(owner_token, shop_info, "TEST 303 Doc Ln, Phoenix AZ", "TESTDocRBAC")
        files = {"file": ("rep.pdf", io.BytesIO(b"hello"), "application/pdf")}
        r = requests.post(f"{API}/jobs/{job['id']}/upload-document", files=files,
                          headers=_auth(owner_token), timeout=30)
        assert r.status_code == 200
        doc_id = r.json()["id"]
        # Contractor tries to download – should be 403 (job not assigned to them)
        r2 = requests.get(f"{API}/documents/{doc_id}/download",
                          headers=_auth(contractor_token), timeout=30)
        assert r2.status_code == 403


# ---------------- 6. Public shop-status ----------------
class TestPublicShopStatus:
    def test_public_shop_status_ok(self, shop_info):
        tok = shop_info["booking_link_token"]
        r = requests.get(f"{API}/public/shop-status/{tok}", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["shop_name"] == shop_info["name"]
        assert "stats" in data
        stats = data["stats"]
        for key in ("jobs_last_30_days", "completed_count", "upcoming_count",
                    "total_spent_last_30_days", "last_completion"):
            assert key in stats
        assert isinstance(data["upcoming"], list)
        assert isinstance(data["completed"], list)

    def test_public_shop_status_invalid_token_404(self):
        r = requests.get(f"{API}/public/shop-status/totallyfake-token-12345", timeout=30)
        assert r.status_code == 404
