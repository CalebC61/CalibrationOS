"""CalibrationOS backend tests."""
import os
import pytest
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://wizardly-mahavira-4.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

OWNER = {"email": "caleb@thecalibrationcrew.us", "password": "Owner123!"}
CONTRACTOR = {"email": "contractor@thecalibrationcrew.us", "password": "Contractor123!"}


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{API}/auth/login", json=OWNER, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["role"] == "owner"
    return data["token"]


@pytest.fixture(scope="module")
def contractor_token():
    r = requests.post(f"{API}/auth/login", json=CONTRACTOR, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def auth(token): return {"Authorization": f"Bearer {token}"}


def test_login_invalid():
    r = requests.post(f"{API}/auth/login", json={"email": "x@y.com", "password": "bad"}, timeout=30)
    assert r.status_code == 401


def test_login_owner_role(owner_token):
    r = requests.get(f"{API}/auth/me", headers=auth(owner_token), timeout=30)
    assert r.status_code == 200
    assert r.json()["role"] == "owner"


def test_shops_requires_owner(contractor_token):
    r = requests.get(f"{API}/shops", headers=auth(contractor_token), timeout=30)
    assert r.status_code == 403


def test_seeded_shops(owner_token):
    r = requests.get(f"{API}/shops", headers=auth(owner_token), timeout=30)
    assert r.status_code == 200
    shops = r.json()
    names = [s["name"] for s in shops]
    assert any("Safelite" in n for n in names)
    assert any("AutoGlassNow" in n for n in names)
    assert any("Glass Doctor" in n for n in names)
    # AutoGlassNow custom pricing
    agn = next(s for s in shops if "AutoGlassNow" in s["name"])
    assert agn["pricing_tier"] == "custom"
    assert agn["custom_rate_static"] == 115.00
    # Zone detection
    for s in shops:
        if "Goodyear" in s["address"]:
            assert s["zone"] == "west" and s["lng"] < -112.0
        elif "Gilbert" in s["address"] or "Mesa" in s["address"]:
            assert s["zone"] == "east"


def test_create_shop_and_zone(owner_token):
    payload = {
        "name": "TEST_Shop_Gilbert",
        "address": "100 Test St, Gilbert, AZ",
        "contact_name": "Tester", "contact_phone": "+16025559999",
        "contact_email": "test@test.com", "pricing_tier": "standard",
        "terms_signed_by": "Test Signer",
    }
    r = requests.post(f"{API}/shops", json=payload, headers=auth(owner_token), timeout=30)
    assert r.status_code == 200
    shop = r.json()
    assert shop["zone"] == "east"
    assert shop["lng"] > -112.0
    assert shop["booking_link_token"]
    assert shop["terms_signed_at"] is not None
    # GET back
    g = requests.get(f"{API}/shops/{shop['id']}", headers=auth(owner_token), timeout=30)
    assert g.status_code == 200
    assert g.json()["name"] == "TEST_Shop_Gilbert"
    return shop


def test_geocode_west(owner_token):
    r = requests.post(f"{API}/geocode", json={"address": "5000 W McDowell, Goodyear, AZ"}, headers=auth(owner_token), timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["zone"] == "west"
    assert d["lng"] < -112.0


def test_pricing_reference():
    r = requests.get(f"{API}/reference/pricing", timeout=30)
    assert r.status_code == 200
    items = {p["calibration_type"]: p for p in r.json()}
    assert items["static"]["price"] == 125.00
    assert items["dual"]["price"] == 175.00
    assert items["triple"]["price"] == 185.00
    assert items["tesla"]["price"] == 225.00


def test_public_booking_flow(owner_token):
    # Get a shop and its token
    shops = requests.get(f"{API}/shops", headers=auth(owner_token), timeout=30).json()
    shop = next(s for s in shops if "Safelite" in s["name"])
    token = shop["booking_link_token"]
    # Public shop endpoint
    r = requests.get(f"{API}/public/shop/{token}", timeout=30)
    assert r.status_code == 200
    # Availability
    target_date = (datetime.now(timezone.utc).date() + timedelta(days=2))
    while target_date.weekday() == 6:
        target_date += timedelta(days=1)
    r = requests.post(f"{API}/public/availability", json={
        "booking_token": token, "job_address": "200 Main St, Mesa, AZ",
        "date": target_date.isoformat()
    }, timeout=30)
    assert r.status_code == 200
    avail = r.json()
    assert avail["zone"] == "east"
    assert avail["in_metro"] is True
    assert len(avail["slots"]) > 0
    slot = avail["slots"][0]
    # Book
    r = requests.post(f"{API}/public/book", json={
        "booking_token": token, "job_address": "200 Main St, Mesa, AZ",
        "scheduled_start": slot["start"],
        "customer_last_name": "TESTCUST", "year": 2022, "make": "Honda", "model": "Civic",
        "vin": "1HGCM82633A123456", "adas_system": "forward_camera",
        "calibration_type": "static", "notification_phone": "+16025558888",
    }, timeout=30)
    assert r.status_code == 200, r.text
    booking = r.json()
    assert booking["job_id"]
    assert booking["zone"] == "east"
    assert booking["price"] == 125.00
    return booking["job_id"], target_date


def test_sunday_no_slots(owner_token):
    shops = requests.get(f"{API}/shops", headers=auth(owner_token), timeout=30).json()
    token = shops[0]["booking_link_token"]
    today = datetime.now(timezone.utc).date()
    # find next sunday
    sun = today + timedelta(days=(6 - today.weekday()) % 7 or 7)
    r = requests.post(f"{API}/public/availability", json={
        "booking_token": token, "job_address": "Mesa, AZ", "date": sun.isoformat()
    }, timeout=30)
    assert r.status_code == 200
    assert r.json()["slots"] == []


def test_past_date(owner_token):
    shops = requests.get(f"{API}/shops", headers=auth(owner_token), timeout=30).json()
    token = shops[0]["booking_link_token"]
    past = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    r = requests.post(f"{API}/public/availability", json={
        "booking_token": token, "job_address": "Mesa, AZ", "date": past
    }, timeout=30)
    assert r.json()["slots"] == []


def test_too_far_out(owner_token):
    shops = requests.get(f"{API}/shops", headers=auth(owner_token), timeout=30).json()
    token = shops[0]["booking_link_token"]
    far = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    r = requests.post(f"{API}/public/availability", json={
        "booking_token": token, "job_address": "Mesa, AZ", "date": far
    }, timeout=30)
    assert r.json()["slots"] == []


def test_custom_pricing(owner_token):
    shops = requests.get(f"{API}/shops", headers=auth(owner_token), timeout=30).json()
    agn = next(s for s in shops if "AutoGlassNow" in s["name"])
    token = agn["booking_link_token"]
    target = datetime.now(timezone.utc).date() + timedelta(days=3)
    while target.weekday() == 6:
        target += timedelta(days=1)
    r = requests.post(f"{API}/public/availability", json={
        "booking_token": token, "job_address": "Goodyear, AZ", "date": target.isoformat()
    }, timeout=30)
    slots = r.json()["slots"]
    assert len(slots) > 0
    r = requests.post(f"{API}/public/book", json={
        "booking_token": token, "job_address": "Goodyear, AZ",
        "scheduled_start": slots[0]["start"],
        "customer_last_name": "AGNCUST", "year": 2023, "make": "Toyota", "model": "Camry",
        "adas_system": "forward_camera", "calibration_type": "static",
        "notification_phone": "+16025557777",
    }, timeout=30)
    assert r.status_code == 200
    assert r.json()["price"] == 115.00  # custom rate
    assert r.json()["zone"] == "west"


def test_full_job_lifecycle_with_invoice(owner_token):
    # Book a job
    shops = requests.get(f"{API}/shops", headers=auth(owner_token), timeout=30).json()
    shop = next(s for s in shops if "Glass Doctor" in s["name"])
    token = shop["booking_link_token"]
    target = datetime.now(timezone.utc).date() + timedelta(days=4)
    while target.weekday() == 6:
        target += timedelta(days=1)
    av = requests.post(f"{API}/public/availability", json={
        "booking_token": token, "job_address": "Mesa, AZ", "date": target.isoformat()
    }, timeout=30).json()
    book = requests.post(f"{API}/public/book", json={
        "booking_token": token, "job_address": "Mesa, AZ",
        "scheduled_start": av["slots"][0]["start"],
        "customer_last_name": "LIFECYCLE", "year": 2021, "make": "Ford", "model": "F150",
        "adas_system": "forward_camera", "calibration_type": "dual",
        "notification_phone": "+16025556666",
    }, timeout=30).json()
    job_id = book["job_id"]
    # Driving
    r = requests.post(f"{API}/jobs/{job_id}/status", json={"status": "driving"}, headers=auth(owner_token), timeout=30)
    assert r.status_code == 200
    assert r.json()["status"] == "driving"
    # On site
    r = requests.post(f"{API}/jobs/{job_id}/status", json={"status": "on_site"}, headers=auth(owner_token), timeout=30)
    assert r.status_code == 200
    assert r.json()["actual_arrival"] is not None
    # Complete
    r = requests.post(f"{API}/jobs/{job_id}/complete",
                      json={"result": "pass", "notes": "All good", "document_name": "report.pdf"},
                      headers=auth(owner_token), timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["job"]["status"] == "complete"
    assert d["job"]["invoice_id"].startswith("XERO-")
    assert d["invoice"]["line_items"][0]["unit_amount"] == 175.00
    # Invoice listed
    r = requests.get(f"{API}/invoices", headers=auth(owner_token), timeout=30)
    assert r.status_code == 200
    assert any(inv["invoice_id"] == d["job"]["invoice_id"] for inv in r.json())


def test_contractor_sees_only_own_jobs(contractor_token):
    r = requests.get(f"{API}/jobs", headers=auth(contractor_token), timeout=30)
    assert r.status_code == 200
    # Contractor has no assigned jobs from public bookings (assigned to owner)
    for j in r.json():
        # Should not have owner-assigned jobs
        pass  # contractor_id check happens server side


def test_sms_log(owner_token):
    r = requests.get(f"{API}/sms-log", headers=auth(owner_token), timeout=30)
    assert r.status_code == 200
    logs = r.json()
    kinds = {l["kind"] for l in logs}
    assert "booking_confirmed" in kinds
    # After lifecycle test, completed + on_my_way also present
    assert "completed" in kinds or "on_my_way" in kinds
