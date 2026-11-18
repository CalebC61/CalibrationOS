"""Private API reads must not be stored by the browser or a CDN.

Safari reuses a GET that has no Cache-Control. The owner then keeps the old
Xero connection and the old draft badge until a full reload.
"""
import asyncio
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402


def test_api_responses_are_not_stored(monkeypatch):
    async def ping():
        return {"ok": 1}

    monkeypatch.setattr(server, "ping_database", ping)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            health = await client.get("/api/health")
            status = await client.get("/api/integrations/status")
            return health, status

    health, status = asyncio.run(run())
    assert health.status_code == 200
    assert health.headers["cache-control"] == "private, no-store"
    assert status.status_code == 401
    assert status.headers["cache-control"] == "private, no-store"
