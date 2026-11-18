"""Health pings Mongo. Unhandled errors and client reports email the owner once.

    cd backend && pytest tests/test_health_and_alerts.py -v
"""
import asyncio
import os
import sys
import time

import httpx
import pytest
from fastapi import Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
import error_alerts  # noqa: E402
from onboarding import reset_rate_limits  # noqa: E402


def _client():
    # Starlette re-raises after a 500 handler so the server can log it.
    # The response is already the handler's body.
    transport = httpx.ASGITransport(app=server.app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _silence_mail(monkeypatch):
    sent = []

    async def fake_send(to, subject, html, kind="transactional", meta=None, reply_to=None):
        sent.append({"to": to, "subject": subject, "html": html, "kind": kind})
        return {"delivered": True}

    monkeypatch.setattr(server, "send_email", fake_send)
    return sent


async def _drain():
    for _ in range(20):
        pending = [task for task in list(server._ALERT_TASKS) if not task.done()]
        if not pending:
            return
        await asyncio.gather(*pending)


@pytest.fixture(autouse=True)
def _reset_alerts(monkeypatch):
    error_alerts.reset_alerts()
    reset_rate_limits()
    for name in ("ALERT_EMAIL", "OWNER_EMAIL", "ADMIN_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    yield
    error_alerts.reset_alerts()
    reset_rate_limits()
    server.app.router.routes[:] = [
        route for route in server.app.router.routes
        if getattr(route, "path", None) != "/api/__error_alert_probe"
    ]


def test_health_timeout_is_a_few_seconds():
    assert 2 <= server.HEALTH_PING_TIMEOUT_SECONDS <= 3


def test_health_is_ok_when_mongo_answers(monkeypatch):
    async def ping():
        return {"ok": 1}

    monkeypatch.setattr(server, "ping_database", ping)

    async def run():
        async with _client() as client:
            return await client.get("/api/health")

    response = asyncio.run(run())
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "private, no-store"


def test_health_is_503_when_mongo_is_down_and_leaks_nothing(monkeypatch):
    sent = _silence_mail(monkeypatch)

    async def ping():
        raise RuntimeError("mongodb+srv://user:secret@cluster.mongodb.net/db unreachable")

    monkeypatch.setattr(server, "ping_database", ping)
    monkeypatch.setenv("ALERT_EMAIL", "alerts@thecalibrationcrew.us")

    async def run():
        async with _client() as client:
            response = await client.get("/api/health")
            await _drain()
            return response

    response = asyncio.run(run())
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "secret" not in response.text
    assert "mongodb" not in response.text
    assert sent == []


def test_health_does_not_wait_on_a_stuck_database(monkeypatch):
    monkeypatch.setattr(server, "HEALTH_PING_TIMEOUT_SECONDS", 0.05)

    async def ping():
        await asyncio.sleep(5)

    monkeypatch.setattr(server, "ping_database", ping)

    async def run():
        async with _client() as client:
            started = time.monotonic()
            response = await client.get("/api/health")
            return response, time.monotonic() - started

    response, elapsed = asyncio.run(run())
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert elapsed < 1


def test_forced_exception_emails_once_even_when_shop_mail_is_off(monkeypatch):
    sent = _silence_mail(monkeypatch)
    monkeypatch.setenv("ALERT_EMAIL", "alerts@thecalibrationcrew.us")
    monkeypatch.setenv("SHOP_EMAILS_ENABLED", "false")
    monkeypatch.setenv("OWNER_EMAILS_ENABLED", "false")

    async def probe(request: Request):
        await request.json()
        raise RuntimeError("probe failed")

    server.app.add_api_route("/api/__error_alert_probe", probe, methods=["POST"])

    async def run():
        async with _client() as client:
            headers = {"Authorization": "Bearer super-secret-token"}
            body = {"password": "hunter2", "card": "4242424242424242"}
            first = await client.post("/api/__error_alert_probe", json=body, headers=headers)
            second = await client.post("/api/__error_alert_probe", json=body, headers=headers)
            await _drain()
            return first, second

    first, second = asyncio.run(run())
    assert first.status_code == 500
    assert second.status_code == 500
    assert first.json() == {"detail": "Internal Server Error"}
    assert "hunter2" not in first.text
    assert "4242" not in first.text
    assert "super-secret-token" not in first.text
    assert len(sent) == 1
    blob = sent[0]["subject"] + sent[0]["html"]
    assert sent[0]["to"] == "alerts@thecalibrationcrew.us"
    assert sent[0]["kind"] == "error_alert"
    assert "RuntimeError" in blob
    assert "POST" in blob
    assert "/api/__error_alert_probe" in blob
    assert "hunter2" not in blob
    assert "4242424242424242" not in blob
    assert "super-secret-token" not in blob
    assert "Authorization" not in blob


def test_a_slow_alert_does_not_hold_the_response(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_send(to, subject, html, kind="transactional", meta=None, reply_to=None):
        started.set()
        await release.wait()
        return {"delivered": True}

    monkeypatch.setattr(server, "send_email", slow_send)
    monkeypatch.setenv("ALERT_EMAIL", "alerts@thecalibrationcrew.us")

    async def probe():
        raise RuntimeError("slow alert")

    server.app.add_api_route("/api/__error_alert_probe", probe, methods=["GET"])

    async def run():
        async with _client() as client:
            begun = time.monotonic()
            response = await client.get("/api/__error_alert_probe")
            elapsed = time.monotonic() - begun
            await asyncio.wait_for(started.wait(), timeout=1)
            release.set()
            await _drain()
            return response, elapsed

    response, elapsed = asyncio.run(run())
    assert response.status_code == 500
    assert elapsed < 0.5


def test_http_errors_do_not_email(monkeypatch):
    sent = _silence_mail(monkeypatch)
    monkeypatch.setenv("ALERT_EMAIL", "alerts@thecalibrationcrew.us")

    async def run():
        async with _client() as client:
            missing = await client.get("/api/does-not-exist")
            invalid = await client.post("/api/auth/login", json={})
            await _drain()
            return missing, invalid

    missing, invalid = asyncio.run(run())
    assert missing.status_code == 404
    assert invalid.status_code == 422
    assert sent == []


def test_client_error_endpoint_emails_once_and_limits_abuse(monkeypatch):
    sent = _silence_mail(monkeypatch)
    monkeypatch.setenv("OWNER_EMAIL", "owner@thecalibrationcrew.us")
    monkeypatch.setenv("SHOP_EMAILS_ENABLED", "false")

    async def run():
        async with _client() as client:
            body = {
                "message": "Render failed",
                "stack": "at Dashboard",
                "path": "/dashboard?token=secret-token",
                "source": "boundary",
            }
            first = await client.post("/api/client-errors", json=body)
            second = await client.post("/api/client-errors", json=body)
            await _drain()
            huge = await client.post(
                "/api/client-errors",
                content=b"{" + b"x" * (error_alerts.CLIENT_ERROR_MAX_BYTES + 50),
                headers={"Content-Type": "application/json"},
            )
            await _drain()
            before_flood = len(sent)
            limited = []
            for index in range(error_alerts.CLIENT_ERROR_IP_LIMIT + 2):
                limited.append(await client.post(
                    "/api/client-errors",
                    json={"message": f"unique {index}", "source": "window", "path": "/field"},
                    headers={"X-Forwarded-For": "203.0.113.9"},
                ))
            other = await client.post(
                "/api/client-errors",
                json={"message": "from somewhere else", "source": "window", "path": "/field"},
                headers={"X-Forwarded-For": "203.0.113.10"},
            )
            capped = await client.post(
                "/api/client-errors",
                json={"message": "past the hourly cap", "source": "window", "path": "/field"},
                headers={"X-Forwarded-For": "203.0.113.11"},
            )
            await _drain()
            return first, second, huge, before_flood, limited, other, capped

    first, second, huge, before_flood, limited, other, capped = asyncio.run(run())
    assert first.status_code == 200
    assert first.json() == {"ok": True}
    assert "secret-token" not in first.text
    assert second.status_code == 200
    assert huge.status_code == 413
    assert before_flood == 1
    blob = sent[0]["subject"] + sent[0]["html"]
    assert "Render failed" in blob
    assert "/dashboard" in blob
    assert "secret-token" not in blob
    assert sent[0]["to"] == "owner@thecalibrationcrew.us"
    codes = [response.status_code for response in limited]
    assert codes[:error_alerts.CLIENT_ERROR_IP_LIMIT] == [200] * error_alerts.CLIENT_ERROR_IP_LIMIT
    assert codes[error_alerts.CLIENT_ERROR_IP_LIMIT:] == [429, 429]
    assert other.status_code == 200
    assert capped.status_code == 200
    assert len(sent) == error_alerts.HOURLY_CAP
    assert not any("past the hourly cap" in item["subject"] + item["html"] for item in sent)


def test_client_error_with_no_address_does_not_send(monkeypatch):
    sent = _silence_mail(monkeypatch)

    async def run():
        async with _client() as client:
            response = await client.post("/api/client-errors", json={"message": "Render failed", "path": "/"})
            await _drain()
            return response

    response = asyncio.run(run())
    assert response.status_code == 200
    assert sent == []
