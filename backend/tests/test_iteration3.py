"""Iteration 3: reorder and settings. Contractor dispatch has been removed."""
import os
import pytest
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
API = f"{BASE_URL}/api"

OWNER = {"email": "caleb@thecalibrationcrew.us", "password": "Owner123!"}


def _auth(t): return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{API}/auth/login", json=OWNER, timeout=30)
    assert r.status_code == 200
    return r.json()["token"]


def test_contractor_routes_are_gone(owner_token):
    headers = _auth(owner_token)
    assert requests.get(f"{API}/contractors", headers=headers, timeout=30).status_code == 404
    assert requests.get(f"{API}/contractor-offers", headers=headers, timeout=30).status_code == 404
    missing = requests.post(
        f"{API}/jobs/not-a-job/dispatch",
        json={"contractor_id": "nobody"},
        headers=headers,
        timeout=30,
    )
    assert missing.status_code == 404


# ---------- Pricing settings ----------
def test_update_pricing_persists(owner_token):
    # Save current
    cur = {p["calibration_type"]: p["price"] for p in requests.get(f"{API}/reference/pricing", timeout=30).json()}
    # Update tesla to 250
    r = requests.put(f"{API}/settings/pricing", json={"tesla": 250},
        headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    after = requests.get(f"{API}/reference/pricing", timeout=30).json()
    tesla = next(p for p in after if p["calibration_type"] == "tesla")
    assert tesla["price"] == 250.0
    # Restore
    requests.put(f"{API}/settings/pricing", json={"tesla": cur["tesla"]},
        headers=_auth(owner_token), timeout=30)


# ---------- Zone settings ----------
def test_update_zone_persists(owner_token):
    zones_before = {z["slug"]: z for z in requests.get(f"{API}/reference/zones", timeout=30).json()}
    orig_max = zones_before["west"]["max_jobs"]
    r = requests.put(f"{API}/settings/zones/west", json={"max_jobs": 5},
        headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    zones_after = {z["slug"]: z for z in requests.get(f"{API}/reference/zones", timeout=30).json()}
    assert zones_after["west"]["max_jobs"] == 5
    # Restore
    requests.put(f"{API}/settings/zones/west", json={"max_jobs": orig_max},
        headers=_auth(owner_token), timeout=30)


def test_zone_unknown_404(owner_token):
    r = requests.put(f"{API}/settings/zones/middle", json={"max_jobs": 1},
        headers=_auth(owner_token), timeout=30)
    assert r.status_code == 404


# ---------- Reorder ----------
def test_reorder_jobs_recomputes(owner_token):
    """Book 2 jobs in east zone today; reorder them and verify sequence + drive recompute."""
    # Two east jobs same day
    target = datetime.now(timezone.utc).date()
    while target.weekday() == 6:
        target += timedelta(days=1)
    shops = requests.get(f"{API}/shops", headers=_auth(owner_token), timeout=30).json()
    safelite = next(s for s in shops if "Safelite" in s["name"])
    glass = next(s for s in shops if "Glass Doctor" in s["name"])

    # Book on safelite (Gilbert, east)
    av = requests.post(f"{API}/public/availability", json={
        "booking_token": safelite["booking_link_token"],
        "job_address": "300 Reorder St, Gilbert, AZ",
        "date": target.isoformat()}, timeout=30).json()
    if not av["slots"]:
        pytest.skip("No east slots today")
    b1 = requests.post(f"{API}/public/book", json={
        "booking_token": safelite["booking_link_token"],
        "job_address": "300 Reorder St, Gilbert, AZ",
        "scheduled_start": av["slots"][0]["start"],
        "customer_last_name": "REORDER1", "year": 2022, "make": "Honda", "model": "Civic",
        "adas_system": "forward_camera", "calibration_type": "static",
    }, timeout=30).json()

    av = requests.post(f"{API}/public/availability", json={
        "booking_token": glass["booking_link_token"],
        "job_address": "400 Reorder Ave, Mesa, AZ",
        "date": target.isoformat()}, timeout=30).json()
    if not av["slots"]:
        pytest.skip("No east slots today (second)")
    b2 = requests.post(f"{API}/public/book", json={
        "booking_token": glass["booking_link_token"],
        "job_address": "400 Reorder Ave, Mesa, AZ",
        "scheduled_start": av["slots"][0]["start"],
        "customer_last_name": "REORDER2", "year": 2023, "make": "Toyota", "model": "Camry",
        "adas_system": "forward_camera", "calibration_type": "static",
    }, timeout=30).json()

    # Reorder reversed
    r = requests.post(f"{API}/jobs/reorder", json={
        "zone": "east", "date": target.isoformat(),
        "ordered_job_ids": [b2["job_id"], b1["job_id"]],
    }, headers=_auth(owner_token), timeout=30)
    if r.status_code == 400 and "past zone end" in r.text:
        pytest.skip("Reorder would overflow zone end — expected behavior")
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["updated"] == 2
    seqs = {u["id"]: u["sequence_order"] for u in res["jobs"]}
    assert seqs[b2["job_id"]] == 1
    assert seqs[b1["job_id"]] == 2

    # Times sequential
    first = next(u for u in res["jobs"] if u["sequence_order"] == 1)
    second = next(u for u in res["jobs"] if u["sequence_order"] == 2)
    assert second["scheduled_start"] > first["scheduled_end"] or second["scheduled_start"] >= first["scheduled_end"]


def test_reorder_invalid_ids(owner_token):
    r = requests.post(f"{API}/jobs/reorder", json={
        "zone": "east", "date": datetime.now(timezone.utc).date().isoformat(),
        "ordered_job_ids": ["nonexistent-id"],
    }, headers=_auth(owner_token), timeout=30)
    assert r.status_code == 400


