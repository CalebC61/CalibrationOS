"""The Xero OAuth callback redirects instead of raising NameError.

    cd backend && pytest tests/test_xero_callback.py -v
"""
import asyncio
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402

BASE = "https://www.thecalibrationcrew.us/settings"


class _Store:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return {k: v for k, v in doc.items() if k != "_id"}
        return None

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set", {}))
                return
        if upsert:
            self.docs.append(dict(update.get("$set", {})))


class _DB:
    def __init__(self):
        self.technicians = _Store()


def _client():
    transport = httpx.ASGITransport(app=server.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test", follow_redirects=False)


def test_callback_error_and_success_redirect_to_the_post_connect_url(monkeypatch):
    db = _DB()
    db.technicians.docs.append({"id": "owner-1", "role": "owner", "name": "Caleb"})
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "XERO_POST_CONNECT_REDIRECT", BASE)
    calls = {"token": 0}

    def fake_token(form):
        calls["token"] += 1
        assert form["grant_type"] == "authorization_code"
        assert form["code"] == "auth-code"
        return {"access_token": "atk", "refresh_token": "rtk", "expires_in": 1800}

    def fake_connections(access_token):
        assert access_token == "atk"
        return [{"tenantId": "ten-1", "tenantName": "The Calibration Crew"}]

    monkeypatch.setattr(server, "_xero_token_request", fake_token)
    monkeypatch.setattr(server, "_xero_connections", fake_connections)
    state = server._xero_state_token("owner-1")

    async def run():
        async with _client() as client:
            denied = await client.get("/api/auth/xero/callback", params={"error": "access_denied"})
            assert denied.status_code == 302
            assert denied.headers["location"] == f"{BASE}?xero=error"
            assert calls["token"] == 0

            connected = await client.get(
                "/api/auth/xero/callback", params={"code": "auth-code", "state": state},
            )
            assert connected.status_code == 302
            assert connected.headers["location"] == f"{BASE}?xero=connected"

        owner = db.technicians.docs[0]
        assert owner["xero_connected"] is True
        assert owner["xero_access_token"] == "atk"
        assert owner["xero_refresh_token"] == "rtk"
        assert owner["xero_tenant_id"] == "ten-1"
        assert owner["xero_org_name"] == "The Calibration Crew"
        assert calls["token"] == 1

    asyncio.run(run())
