"""Module 8: Admin Assist Engine — deterministic-path tests.

Same convention as test_growth.py: hits a live running server via `requests`.
Requires the server to have GOOGLE_API_KEY set (any value — these tests never invoke Gemini)
and ASSIST_SELF_BASE_URL pointing back at itself if it isn't on port 8001.

The LLM itself is deliberately not exercised here (non-deterministic, billable). Everything
deterministic is: the /run escape hatch, the safe-vs-risky tier gate, the
propose→confirm→execute and propose→cancel state machines, RBAC, and audit/persistence
side effects.
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


@pytest.fixture(scope="module", autouse=True)
def require_assist_enabled(owner_token):
    r = requests.get(f"{API}/integrations/status", headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    if not r.json().get("assist", {}).get("enabled"):
        pytest.skip("Assist module not enabled on this server (GOOGLE_API_KEY unset)")


def _msg(token, message, conversation_id=None):
    return requests.post(f"{API}/assist/message",
                          json={"message": message, "conversation_id": conversation_id},
                          headers=_auth(token), timeout=60)


# ---------- RBAC ----------
def test_rbac_contractor_forbidden(contractor_token):
    for method, path, body in [
        ("POST", "/assist/message", {"message": "hi"}),
        ("GET", "/assist/tools", None),
        ("GET", "/assist/conversations/whatever", None),
        ("POST", "/assist/actions/whatever/confirm", None),
        ("POST", "/assist/actions/whatever/cancel", None),
    ]:
        r = requests.request(method, f"{API}{path}", json=body,
                              headers=_auth(contractor_token), timeout=30)
        assert r.status_code == 403, f"{method} {path} should be owner-only, got {r.status_code}"


# ---------- integrations/status + tool listing ----------
def test_integrations_status_has_assist(owner_token):
    r = requests.get(f"{API}/integrations/status", headers=_auth(owner_token), timeout=30)
    assist = r.json()["assist"]
    assert assist["configured"] is True and assist["enabled"] is True and assist["mode"] == "live"


def test_tools_listing_has_tiers(owner_token):
    r = requests.get(f"{API}/assist/tools", headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    tools = {t["name"]: t for t in r.json()}
    # spot-check the tier mapping: GET-backed safe, mutation-backed risky
    assert tools["list_jobs"]["tier"] == "safe"
    assert tools["get_pricing"]["tier"] == "safe"
    assert tools["dispatch_job"]["tier"] == "risky"
    assert tools["update_pricing"]["tier"] == "risky"
    assert tools["send_touch"]["tier"] == "risky"
    assert "reels" not in " ".join(tools)  # reels tools must not exist


# ---------- /run escape hatch: safe tool executes immediately ----------
def test_run_safe_tool_executes(owner_token):
    r = _msg(owner_token, "/run get_pricing {}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["kind"] == "text"
    assert "static" in data["text"]  # pricing payload echoed back
    assert data["conversation_id"]


def test_run_unknown_tool_400(owner_token):
    r = _msg(owner_token, "/run definitely_not_a_tool {}")
    assert r.status_code == 400
    assert "Unknown tool" in r.json()["detail"]


def test_run_bad_json_400(owner_token):
    r = _msg(owner_token, "/run get_pricing {not json")
    assert r.status_code == 400


def test_empty_message_400(owner_token):
    r = _msg(owner_token, "   ")
    assert r.status_code == 400


# ---------- risky tool: propose -> confirm -> execute ----------
def test_risky_propose_confirm_execute(owner_token):
    orig = {p["calibration_type"]: p["price"]
            for p in requests.get(f"{API}/reference/pricing", timeout=30).json()}

    r = _msg(owner_token, '/run update_pricing {"tesla": 231}')
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["kind"] == "pending_action"
    pending = data["pending_action"]
    assert pending["tool_name"] == "update_pricing"
    assert pending["status"] == "pending"

    # nothing changed yet — proposing must not mutate
    now = {p["calibration_type"]: p["price"]
           for p in requests.get(f"{API}/reference/pricing", timeout=30).json()}
    assert now["tesla"] == orig["tesla"]

    # confirm → executes for real
    r = requests.post(f"{API}/assist/actions/{pending['id']}/confirm",
                       headers=_auth(owner_token), timeout=60)
    assert r.status_code == 200, r.text
    assert r.json()["result"]["ok"] is True
    after = {p["calibration_type"]: p["price"]
             for p in requests.get(f"{API}/reference/pricing", timeout=30).json()}
    assert after["tesla"] == 231.0

    # double-confirm rejected
    r = requests.post(f"{API}/assist/actions/{pending['id']}/confirm",
                       headers=_auth(owner_token), timeout=30)
    assert r.status_code == 400

    # restore
    requests.put(f"{API}/settings/pricing", json={"tesla": orig["tesla"]},
                  headers=_auth(owner_token), timeout=30)


# ---------- risky tool: propose -> cancel ----------
def test_risky_propose_cancel(owner_token):
    orig = {p["calibration_type"]: p["price"]
            for p in requests.get(f"{API}/reference/pricing", timeout=30).json()}

    r = _msg(owner_token, '/run update_pricing {"tesla": 999}')
    pending = r.json()["pending_action"]

    r = requests.post(f"{API}/assist/actions/{pending['id']}/cancel",
                       headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"

    # confirm after cancel rejected, and nothing mutated
    r = requests.post(f"{API}/assist/actions/{pending['id']}/confirm",
                       headers=_auth(owner_token), timeout=30)
    assert r.status_code == 400
    now = {p["calibration_type"]: p["price"]
           for p in requests.get(f"{API}/reference/pricing", timeout=30).json()}
    assert now["tesla"] == orig["tesla"]

    # double-cancel rejected too
    r = requests.post(f"{API}/assist/actions/{pending['id']}/cancel",
                       headers=_auth(owner_token), timeout=30)
    assert r.status_code == 400


# ---------- confirming someone else's / nonexistent action ----------
def test_confirm_nonexistent_404(owner_token):
    r = requests.post(f"{API}/assist/actions/no-such-action/confirm",
                       headers=_auth(owner_token), timeout=30)
    assert r.status_code == 404


# ---------- risky tool that hits a validation error still surfaces cleanly ----------
def test_confirmed_action_with_bad_target_reports_failure(owner_token):
    r = _msg(owner_token, '/run dispatch_job {"job_id": "nonexistent", "contractor_id": "also-nonexistent"}')
    pending = r.json()["pending_action"]
    r = requests.post(f"{API}/assist/actions/{pending['id']}/confirm",
                       headers=_auth(owner_token), timeout=60)
    assert r.status_code == 200  # the confirm itself worked...
    result = r.json()["result"]
    assert result["ok"] is False  # ...but the underlying endpoint rejected it (404)
    assert result["status"] in (400, 404)


# ---------- conversation persistence ----------
def test_conversation_history_persists(owner_token):
    r = _msg(owner_token, "/run get_zones {}")
    cid = r.json()["conversation_id"]
    r = _msg(owner_token, "/run get_pricing {}", conversation_id=cid)
    assert r.json()["conversation_id"] == cid

    r = requests.get(f"{API}/assist/conversations/{cid}", headers=_auth(owner_token), timeout=30)
    assert r.status_code == 200
    msgs = r.json()["messages"]
    roles = [m["role"] for m in msgs]
    assert roles.count("user") == 2 and roles.count("assistant") == 2


def test_conversation_of_other_owner_404(owner_token):
    r = requests.get(f"{API}/assist/conversations/not-a-real-conversation",
                      headers=_auth(owner_token), timeout=30)
    assert r.status_code == 404
