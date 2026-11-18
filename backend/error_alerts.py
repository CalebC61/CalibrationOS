"""Owner alerts for unhandled failures.

Shop mail stays on SHOP_EMAILS_ENABLED. These notes go to the owner even when
that flag is off. One fingerprint sends at most once every 15 minutes, and the
process sends at most HOURLY_CAP alerts an hour. No connection string, token,
card number, or auth header is left in the message.
"""
import html
import json
import os
import re
import time
from datetime import datetime, timezone

DEDUPE_SECONDS = 15 * 60
HOURLY_CAP = 10
CLIENT_ERROR_MAX_BYTES = 4096
CLIENT_ERROR_IP_LIMIT = 8
CLIENT_ERROR_WINDOW_SECONDS = 60
_TRACE_LINES = 40
_TRACE_CHARS = 2500

_SCRUBS = (
    re.compile(r"mongodb(?:\+srv)?://\S+", re.IGNORECASE),
    re.compile(r"(?i)\b(?:authorization|cookie|set-cookie)\b\s*[:=]?\s*(?:bearer\s+)?\S+"),
    re.compile(r"(?i)\bbearer\s+\S+"),
    re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]+\b"),
    re.compile(r"\bwhsec_[A-Za-z0-9]+\b"),
    re.compile(r"\bre_[A-Za-z0-9]{8,}\b"),
    re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|token)\b\s*[:=]\s*\S+"),
    re.compile(r"\b\d{13,19}\b"),
)


def scrub(value) -> str:
    text = str(value or "")
    for pattern in _SCRUBS:
        text = pattern.sub("[redacted]", text)
    return text


def alert_recipient() -> str | None:
    """ALERT_EMAIL, then OWNER_EMAIL, then ADMIN_EMAIL. Blank means do not send."""
    for name in ("ALERT_EMAIL", "OWNER_EMAIL", "ADMIN_EMAIL"):
        value = (os.environ.get(name) or "").strip()
        domain = value.split("@", 1)[-1] if "@" in value else ""
        if value and "@" in value and "." in domain:
            return value
    return None


def public_path(path: str) -> str:
    text = str(path or "/").split("?", 1)[0].split("#", 1)[0]
    text = text.replace("\r", " ").replace("\n", " ").strip() or "/"
    return text[:200]


class AlertGate:
    def __init__(self, dedupe_seconds: int = DEDUPE_SECONDS, hourly_cap: int = HOURLY_CAP):
        self.dedupe_seconds = dedupe_seconds
        self.hourly_cap = hourly_cap
        self._last: dict[str, float] = {}
        self._sent_at: list[float] = []

    def allow(self, fingerprint: str, now: float) -> bool:
        self._sent_at = [stamp for stamp in self._sent_at if now - stamp < 3600]
        expired = [key for key, stamp in self._last.items() if now - stamp >= 3600]
        for key in expired:
            del self._last[key]
        if len(self._sent_at) >= self.hourly_cap:
            return False
        last = self._last.get(fingerprint)
        if last is not None and now - last < self.dedupe_seconds:
            return False
        self._last[fingerprint] = now
        self._sent_at.append(now)
        return True

    def clear(self) -> None:
        self._last.clear()
        self._sent_at.clear()


GATE = AlertGate()


def reset_alerts() -> None:
    GATE.clear()


def _when(now: float | None) -> str:
    moment = datetime.now(timezone.utc) if now is None else datetime.fromtimestamp(now, timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M:%S UTC")


def _trim_trace(text: str) -> str:
    lines = scrub(text).splitlines()
    tail = "\n".join(lines[-_TRACE_LINES:])
    if len(tail) > _TRACE_CHARS:
        tail = tail[-_TRACE_CHARS:]
    return tail


def _message(subject: str, rows: list[tuple[str, str]], trace: str, to: str) -> dict:
    items = "".join(
        f"<li>{html.escape(label)}: {html.escape(scrub(value))}</li>"
        for label, value in rows
    )
    body = (
        "<p>CalibrationOS hit an error.</p>"
        f"<ul>{items}</ul>"
        f"<pre>{html.escape(_trim_trace(trace))}</pre>"
    )
    return {
        "to": to,
        "subject": scrub(subject)[:180],
        "html": body,
        "kind": "error_alert",
    }


def prepare_server_alert(*, method: str, path: str, exc: BaseException, traceback_text: str, now: float | None = None):
    recipient = alert_recipient()
    if recipient is None:
        return None
    route = public_path(path)
    verb = (method or "GET").upper()
    detail = scrub(str(exc))[:500]
    fingerprint = f"server|{verb}|{route}|{type(exc).__name__}|{detail[:180]}"
    moment = time.time() if now is None else now
    if not GATE.allow(fingerprint, moment):
        return None
    return _message(
        f"CalibrationOS error: {type(exc).__name__} on {verb} {route}",
        [
            ("Time", _when(moment)),
            ("Route", f"{verb} {route}"),
            ("Error", f"{type(exc).__name__}: {detail}"),
        ],
        traceback_text or "",
        recipient,
    )


def prepare_client_report(raw: bytes, now: float | None = None):
    """Email payload for a browser report. ValueError means the body is not JSON."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Client error report was not JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("Client error report was not a JSON object.")
    message = scrub(data.get("message") or "")[:500].strip()
    stack = str(data.get("stack") or "")
    route = public_path(str(data.get("path") or "/"))
    source = scrub(data.get("source") or "client")[:40].strip() or "client"
    if not message and not scrub(stack).strip():
        return None
    recipient = alert_recipient()
    if recipient is None:
        return None
    fingerprint = f"client|{route}|{message[:180]}"
    moment = time.time() if now is None else now
    if not GATE.allow(fingerprint, moment):
        return None
    shown = message or "Client error"
    return _message(
        f"CalibrationOS client error on {route}",
        [
            ("Time", _when(moment)),
            ("Page", route),
            ("Source", source),
            ("Error", shown),
        ],
        stack,
        recipient,
    )
