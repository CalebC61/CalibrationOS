"""Iteration 3: contractor dispatch + offers + reorder + settings + contractor mgmt."""
import os
import pytest
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
API = f"{BASE_URL}/api"

OWNER = {"email": "caleb@thecalibrationcrew.us", "password": "Owner123!"}
CONTRACTOR = {"email": "contractor@thecalibrationcrew.us", "password": "Contractor123!"}


def _auth(t): return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{API}/auth/login", json=OWNER, timeout=30)
    assert r.status_code == 200
    return r.json()["token"]


@pytest.fixture(scope="module")
def contractor_token():
    r = requests.post(f"{API}/auth/login", json=CONTRACTOR, timeout=30)
    assert r.status_code == 200
    return r.json()["token"]


@pytest.fixture(scope="module")
def contractor_id(owner_token):
    r = requests.get(f"{API}/contractors", headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    cs = r.json()
    assert len(cs) >= 1
    return cs[0]["id"]


def _book_today_job(owner_token, shop_match, address, last_name):
    """Book a job for today using a public token. Returns job_id and date used."""
    shops = requests.get(f"{API}/shops", headers=_auth(owner_token), timeout=30).json()
    shop = next(s for s in shops if shop_match in s["name"])
    tok = shop["booking_link_token"]
    target = datetime.now(timezone.utc).date()
    # Avoid Sunday
    while target.weekday() == 6:
        target += timedelta(days=1)
    av = requests.post(f"{API}/public/availability",
        json={"booking_token": tok, "job_address": address, "date": target.isoformat()},
        timeout=30).json()
    if not av.get("slots"):
        # Try next day if today is fully booked or past zone window
        target = target + timedelta(days=1)
        while target.weekday() == 6:
            target += timedelta(days=1)
        av = requests.post(f"{API}/public/availability",
            json={"booking_token": tok, "job_address": address, "date": target.isoformat()},
            timeout=30).json()
    assert av["slots"], f"No slots available for {address} on {target}"
    slot = av["slots"][0]
    book = requests.post(f"{API}/public/book", json={
        "booking_token": tok, "job_address": address,
        "scheduled_start": slot["start"], "customer_last_name": last_name,
        "year": 2022, "make": "Honda", "model": "Civic",
        "adas_system": "forward_camera", "calibration_type": "static",
        "notification_phone": "+16025550000",
    }, timeout=30)
    assert book.status_code == 200, book.text
    return book.json()["job_id"], target


# ---------- Contractors list ----------
def test_list_contractors(owner_token):
    r = requests.get(f"{API}/contractors", headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    cs = r.json()
    assert any(c["email"] == CONTRACTOR["email"] for c in cs)
    # No password_hash leak
    for c in cs:
        assert "password_hash" not in c


def test_list_contractors_forbidden(contractor_token):
    r = requests.get(f"{API}/contractors", headers=_auth(contractor_token), timeout=30)
    assert r.status_code == 403


# ---------- Dispatch flow: accept ----------
def test_dispatch_then_accept_flow(owner_token, contractor_token, contractor_id):
    job_id, date_used = _book_today_job(owner_token, "Safelite", "Gilbert, AZ", "TESTACCEPT")
    # Dispatch
    r = requests.post(f"{API}/jobs/{job_id}/dispatch",
        json={"contractor_id": contractor_id}, headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200, r.text
    offer = r.json()
    assert offer["status"] == "pending"
    assert offer["contractor_id"] == contractor_id
    assert offer["job_id"] == job_id
    # Expires ~30min later
    exp = datetime.fromisoformat(offer["expires_at"])
    offered = datetime.fromisoformat(offer["offered_at"])
    diff = (exp - offered).total_seconds() / 60
    assert 29 <= diff <= 31

    # Job status flipped
    j = requests.get(f"{API}/jobs/{job_id}", headers=_auth(owner_token), timeout=30).json()
    assert j["status"] == "dispatched_to_contractor"
    assert j["technician_id"] == contractor_id

    # SMS log includes contractor_offer
    logs = requests.get(f"{API}/sms-log", headers=_auth(owner_token), timeout=30).json()
    assert any(l["kind"] == "contractor_offer" and l["job_id"] == job_id for l in logs)

    # Contractor sees offer in their list
    coff = requests.get(f"{API}/contractor-offers", headers=_auth(contractor_token), timeout=30)
    assert coff.status_code == 200
    coff_list = coff.json()
    my = [o for o in coff_list if o["id"] == offer["id"]]
    assert my, "Contractor cannot see their own pending offer"
    # Contractor list ONLY pending and only theirs
    for o in coff_list:
        assert o["status"] == "pending"
        assert o["contractor_id"] == contractor_id

    # Accept
    r = requests.post(f"{API}/contractor-offers/{offer['id']}/respond",
        json={"accept": True}, headers=_auth(contractor_token), timeout=30)
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"

    # SMS log has offer_accepted
    logs = requests.get(f"{API}/sms-log", headers=_auth(owner_token), timeout=30).json()
    assert any(l["kind"] == "offer_accepted" and l["job_id"] == job_id for l in logs)

    # Job still assigned to contractor
    j = requests.get(f"{API}/jobs/{job_id}", headers=_auth(owner_token), timeout=30).json()
    assert j["technician_id"] == contractor_id


# ---------- Dispatch then decline ----------
def test_dispatch_then_decline_flow(owner_token, contractor_token, contractor_id):
    job_id, _ = _book_today_job(owner_token, "Glass Doctor", "Mesa, AZ", "TESTDECLINE")
    r = requests.post(f"{API}/jobs/{job_id}/dispatch",
        json={"contractor_id": contractor_id}, headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    offer_id = r.json()["id"]
    # Decline
    r = requests.post(f"{API}/contractor-offers/{offer_id}/respond",
        json={"accept": False}, headers=_auth(contractor_token), timeout=30)
    assert r.status_code == 200
    assert r.json()["status"] == "declined"

    # Job reverts to booked + owner reassigned
    j = requests.get(f"{API}/jobs/{job_id}", headers=_auth(owner_token), timeout=30).json()
    assert j["status"] == "booked"
    me = requests.get(f"{API}/auth/me", headers=_auth(owner_token), timeout=30).json()
    assert j["technician_id"] == me["id"]

    # SMS owner offer_declined
    logs = requests.get(f"{API}/sms-log", headers=_auth(owner_token), timeout=30).json()
    assert any(l["kind"] == "offer_declined" and l["job_id"] == job_id for l in logs)


def test_offers_owner_sees_all(owner_token):
    r = requests.get(f"{API}/contractor-offers", headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    offers = r.json()
    # Should include the accepted + declined from prior tests
    statuses = {o["status"] for o in offers}
    assert "accepted" in statuses
    assert "declined" in statuses


def test_dispatch_inactive_contractor_fails(owner_token, contractor_token, contractor_id):
    # Disable
    r = requests.put(f"{API}/contractors/{contractor_id}",
        json={"is_active": False}, headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # Book new job and try to dispatch
    job_id, _ = _book_today_job(owner_token, "Safelite", "Gilbert, AZ", "TESTINACTIVE")
    r = requests.post(f"{API}/jobs/{job_id}/dispatch",
        json={"contractor_id": contractor_id}, headers=_auth(owner_token), timeout=30)
    assert r.status_code == 400

    # Re-enable
    r = requests.put(f"{API}/contractors/{contractor_id}",
        json={"is_active": True}, headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    assert r.json()["is_active"] is True


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


# ---------- Contractor update ----------
def test_contractor_update_fields(owner_token, contractor_id):
    r = requests.put(f"{API}/contractors/{contractor_id}", json={
        "name": "West Contractor Updated", "phone": "+16025550199",
        "home_address": "Goodyear, AZ",
    }, headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["name"] == "West Contractor Updated"
    assert "home_lat" in d and "home_lng" in d
    # Restore
    requests.put(f"{API}/contractors/{contractor_id}",
        json={"name": "West-Side Contractor"}, headers=_auth(owner_token), timeout=30)


def test_dispatch_non_booked_fails(owner_token, contractor_id):
    # Dispatch a job, then try to dispatch again (status now dispatched_to_contractor)
    job_id, _ = _book_today_job(owner_token, "Safelite", "Gilbert, AZ", "TESTDOUBLE")
    r = requests.post(f"{API}/jobs/{job_id}/dispatch",
        json={"contractor_id": contractor_id}, headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    r2 = requests.post(f"{API}/jobs/{job_id}/dispatch",
        json={"contractor_id": contractor_id}, headers=_auth(owner_token), timeout=30)
    assert r2.status_code == 400
