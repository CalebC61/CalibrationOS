"""Signed one-tap links for the owner to approve or decline a booking.

The token is an HMAC of the job, the action, a nonce, and an expiry. The
server stores the nonce. Previewing a link does not mark it used. Confirming
it does, and a second confirm fails. A shop purpose, a different job, or a
different secret does not pass.
"""
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

PURPOSE = "owner"


def _b64(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _unb64(token: str) -> str | None:
    try:
        pad = "=" * (-len(token) % 4)
        return base64.urlsafe_b64decode((token + pad).encode()).decode()
    except Exception:
        return None


def mint_owner_link(*, secret: str, job_id: str, action: str, now: datetime, ttl_hours: int = 48, nonce: str | None = None) -> dict:
    """Return {token, record}. The record is what the database stores."""
    if action not in ("approve", "decline"):
        raise ValueError("action must be approve or decline")
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    nonce = nonce or secrets.token_urlsafe(18)
    expires = now.astimezone(timezone.utc) + timedelta(hours=ttl_hours)
    exp_ts = int(expires.timestamp())
    payload = f"{job_id}|{action}|{nonce}|{exp_ts}|{PURPOSE}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = _b64(f"{payload}|{sig}")
    record = {
        "id": nonce,
        "job_id": job_id,
        "action": action,
        "purpose": PURPOSE,
        "expires_at": expires.isoformat(),
        "used_at": None,
    }
    return {"token": token, "record": record}


def token_claims(secret: str, token: str) -> dict | None:
    """Verified claims, or None when the signature does not match. Does not check the database."""
    return _parse(secret, token)


def _parse(secret: str, token: str) -> dict | None:
    raw = _unb64(token or "")
    if not raw:
        return None
    parts = raw.split("|")
    if len(parts) != 6:
        return None
    job_id, action, nonce, exp_ts, purpose, sig = parts
    payload = f"{job_id}|{action}|{nonce}|{exp_ts}|{purpose}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        exp = datetime.fromtimestamp(int(exp_ts), tz=timezone.utc)
    except ValueError:
        return None
    return {
        "job_id": job_id,
        "action": action,
        "nonce": nonce,
        "expires_at": exp,
        "purpose": purpose,
    }


def _invalid(message: str = "This link is not valid.") -> dict:
    return {"ok": False, "error": message, "consumes": False}


def assess_owner_link(secret: str, token: str, record: dict | None, now: datetime) -> dict:
    """Check a link. Does not mark it used."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    parsed = _parse(secret, token)
    if parsed is None:
        return _invalid()
    if record is None:
        return _invalid()
    if (
        record.get("purpose") != PURPOSE
        or parsed["purpose"] != PURPOSE
        or record.get("job_id") != parsed["job_id"]
        or record.get("action") != parsed["action"]
        or record.get("id") != parsed["nonce"]
    ):
        return _invalid()
    if record.get("used_at"):
        return _invalid("This link was already used.")
    if now >= parsed["expires_at"]:
        return _invalid("This link has expired.")
    return {
        "ok": True,
        "action": parsed["action"],
        "job_id": parsed["job_id"],
        "purpose": PURPOSE,
        "nonce": parsed["nonce"],
        "consumes": False,
        "error": None,
    }


def mark_used(record: dict, now: datetime) -> dict:
    """Copy of the stored row with used_at set. The caller writes it back."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return {**record, "used_at": now.astimezone(timezone.utc).isoformat()}
