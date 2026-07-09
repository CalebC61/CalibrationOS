"""Module 9: Partner Growth Engine — contacts/grid/cap enforcement/nudges/touches/intros.

Reels are explicitly out of scope for v1 (no video-generation capability exists) — not tested.
Same convention as test_iteration3.py: hits a live running server via `requests`, no FastAPI
TestClient. Assumes GROWTH_MODULE_ENABLED defaults to true and the standard seeded owner login.
"""
import os
import pytest
import requests

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


def _create_contact(owner_token, **overrides):
    body = {
        "first_name": "Test", "last_name": "Contact", "company_name": "Test Co",
        "circle": "prospect",
    }
    body.update(overrides)
    r = requests.post(f"{API}/growth/contacts", json=body, headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- RBAC ----------
def test_rbac_contractor_forbidden(contractor_token):
    endpoints = [
        ("GET", "/growth/grid"), ("GET", "/growth/contacts"), ("GET", "/growth/nudges/today"),
        ("GET", "/growth/touches"), ("GET", "/growth/intros"),
    ]
    for method, path in endpoints:
        r = requests.request(method, f"{API}{path}", headers=_auth(contractor_token), timeout=30)
        assert r.status_code == 403, f"{method} {path} should be owner-only"


# ---------- integrations/status ----------
def test_integrations_status_includes_growth(owner_token):
    r = requests.get(f"{API}/integrations/status", headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    growth = r.json()["growth"]
    assert growth["enabled"] is True
    assert "contact_count" in growth and "counts_by_circle" in growth


# ---------- contacts CRUD ----------
def test_contact_create_list_patch(owner_token):
    contact = _create_contact(owner_token, first_name="CRUD", last_name="Test",
                               company_name="CRUD Co", notes="initial")
    assert contact["circle"] == "prospect"
    assert contact["circle_rank"] >= 1

    listed = requests.get(f"{API}/growth/contacts", headers=_auth(owner_token), timeout=30).json()
    assert any(c["id"] == contact["id"] for c in listed)

    r = requests.patch(f"{API}/growth/contacts/{contact['id']}", json={"notes": "updated"},
                        headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    assert r.json()["notes"] == "updated"


def test_contact_search_filter(owner_token):
    unique = _create_contact(owner_token, first_name="Zyxwuv", last_name="Unique", company_name="Zx Co")
    r = requests.get(f"{API}/growth/contacts", params={"search": "Zyxwuv"},
                      headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert unique["id"] in ids


# ---------- grid ----------
def test_grid_never_exceeds_caps(owner_token):
    r = requests.get(f"{API}/growth/grid", headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    grid = r.json()
    for circle, cap in grid["caps"].items():
        if cap < 9999:
            assert len(grid["circles"][circle]) <= cap, f"{circle} exceeds its cap"


# ---------- cap enforcement ----------
def test_cap_enforcement_top5(owner_token):
    """Fills top5 to its cap (whatever the current count is), confirms the next write 409s,
    then confirms demoting an existing member frees a slot."""
    grid = requests.get(f"{API}/growth/grid", headers=_auth(owner_token), timeout=30).json()
    cap = grid["caps"]["top5"]
    current = len(grid["circles"]["top5"])
    for i in range(max(0, cap - current)):
        _create_contact(owner_token, first_name=f"Fill{i}", last_name="Cap",
                         company_name="Cap Co", circle="top5")

    r = requests.post(f"{API}/growth/contacts", json={
        "first_name": "Overflow", "last_name": "Cap", "company_name": "Cap Co", "circle": "top5",
    }, headers=_auth(owner_token), timeout=30)
    assert r.status_code == 409, r.text

    grid = requests.get(f"{API}/growth/grid", headers=_auth(owner_token), timeout=30).json()
    demote_id = grid["circles"]["top5"][0]["id"]
    r = requests.patch(f"{API}/growth/contacts/{demote_id}", json={"circle": "key50"},
                        headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["circle"] == "key50"

    r2 = requests.post(f"{API}/growth/contacts", json={
        "first_name": "Overflow2", "last_name": "Cap", "company_name": "Cap Co", "circle": "top5",
    }, headers=_auth(owner_token), timeout=30)
    assert r2.status_code == 200, r2.text


# ---------- nudges + touch lifecycle ----------
def test_nudge_generation_idempotent_and_touch_send(owner_token):
    r = requests.post(f"{API}/growth/contacts", json={
        "first_name": "Nudge", "last_name": "Test", "company_name": "Nudge Co",
        "circle": "vital100", "phone": "+16025550188",
    }, headers=_auth(owner_token), timeout=30)
    if r.status_code == 409:
        pytest.skip("vital100 is full in this environment")
    assert r.status_code == 200, r.text
    contact = r.json()

    touches1 = requests.get(f"{API}/growth/nudges/today", headers=_auth(owner_token), timeout=30).json()
    mine = [t for t in touches1 if t["partner_contact_id"] == contact["id"]]
    assert len(mine) == 1, "a freshly-created, never-touched contact should get exactly one nudge"
    touch = mine[0]
    # No shop_id / job history → deterministically falls back to the check-in template (sms)
    assert touch["template_key"] == "pc_checkin"
    assert touch["channel"] == "sms"
    assert touch["status"] == "draft"
    assert touch["contact"]["id"] == contact["id"]

    # Idempotent: calling again the same day does not create a duplicate nudge for this contact
    touches2 = requests.get(f"{API}/growth/nudges/today", headers=_auth(owner_token), timeout=30).json()
    mine2 = [t for t in touches2 if t["partner_contact_id"] == contact["id"]]
    assert [t["id"] for t in mine2] == [t["id"] for t in mine]

    # Can't send before approval
    r = requests.post(f"{API}/growth/touches/{touch['id']}/send", headers=_auth(owner_token), timeout=30)
    assert r.status_code == 400

    r = requests.post(f"{API}/growth/touches/{touch['id']}/approve", headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    # Can't approve twice
    r = requests.post(f"{API}/growth/touches/{touch['id']}/approve", headers=_auth(owner_token), timeout=30)
    assert r.status_code == 400

    r = requests.post(f"{API}/growth/touches/{touch['id']}/send", headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200, r.text
    sent = r.json()
    assert sent["status"] == "sent"
    assert sent["sent_at"]

    logs = requests.get(f"{API}/sms-log", headers=_auth(owner_token), timeout=30).json()
    assert any(l["kind"] == "growth_touch" for l in logs)

    contacts = requests.get(f"{API}/growth/contacts", headers=_auth(owner_token), timeout=30).json()
    fresh = next(c for c in contacts if c["id"] == contact["id"])
    assert fresh["last_touch_at"] is not None
    assert fresh["favors_given"] == 0  # pc_checkin has favor_delta=0
    assert fresh["next_touch_due"] is not None


# ---------- intros ----------
def test_intro_approve_and_send(owner_token):
    a = _create_contact(owner_token, first_name="IntroA", last_name="Test", company_name="A Co",
                         email="introa@example.com", city="Gilbert")
    b = _create_contact(owner_token, first_name="IntroB", last_name="Test", company_name="B Co",
                         email="introb@example.com")

    r = requests.post(f"{API}/growth/intros", json={
        "a_contact_id": a["id"], "b_contact_id": b["id"],
        "value_prop_a": "Free lunch & learn", "value_prop_b": "Overflow bays",
    }, headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200, r.text
    intro = r.json()
    assert intro["status"] == "draft"
    assert "IntroA" in intro["intro_body"] and "IntroB" in intro["intro_body"]

    r = requests.post(f"{API}/growth/intros/{intro['id']}/send", headers=_auth(owner_token), timeout=30)
    assert r.status_code == 400  # not approved yet

    r = requests.post(f"{API}/growth/intros/{intro['id']}/approve", headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    r = requests.post(f"{API}/growth/intros/{intro['id']}/send", headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "sent"

    contacts = requests.get(f"{API}/growth/contacts", headers=_auth(owner_token), timeout=30).json()
    ca = next(c for c in contacts if c["id"] == a["id"])
    cb = next(c for c in contacts if c["id"] == b["id"])
    assert ca["favors_given"] == 1
    assert cb["favors_given"] == 1


def test_intro_requires_email_on_both_sides(owner_token):
    a = _create_contact(owner_token, first_name="NoEmailA", last_name="Test", company_name="X Co")
    b = _create_contact(owner_token, first_name="NoEmailB", last_name="Test", company_name="Y Co",
                         email="noemailb@example.com")
    r = requests.post(f"{API}/growth/intros", json={
        "a_contact_id": a["id"], "b_contact_id": b["id"],
        "value_prop_a": "x", "value_prop_b": "y",
    }, headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    intro = r.json()
    requests.post(f"{API}/growth/intros/{intro['id']}/approve", headers=_auth(owner_token), timeout=30)
    r = requests.post(f"{API}/growth/intros/{intro['id']}/send", headers=_auth(owner_token), timeout=30)
    assert r.status_code == 400
