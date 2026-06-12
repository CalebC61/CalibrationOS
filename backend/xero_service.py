"""Xero Accounting API integration.

OAuth 2.0 authorization code flow + Accounting API (Contacts, Invoices).
Tokens are persisted in MongoDB collection `xero_tokens` keyed by owner_id.
"""
from __future__ import annotations

import base64
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# --- Endpoints ---
AUTH_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"
REVOCATION_URL = "https://identity.xero.com/connect/revocation"
CONNECTIONS_URL = "https://api.xero.com/connections"
API_BASE = "https://api.xero.com/api.xro/2.0"

# Scopes — minimum needed to read+write contacts, invoices, attachments, and refresh.
SCOPES = "openid profile email accounting.contacts accounting.transactions accounting.attachments offline_access"

REFRESH_SAFETY_MARGIN = timedelta(seconds=60)


def _client_id() -> str:
    v = os.environ.get("XERO_CLIENT_ID", "").strip()
    if not v:
        raise HTTPException(500, "XERO_CLIENT_ID is not set")
    return v


def _client_secret() -> str:
    v = os.environ.get("XERO_CLIENT_SECRET", "").strip()
    if not v:
        raise HTTPException(500, "XERO_CLIENT_SECRET is not set")
    return v


def _redirect_uri() -> str:
    v = os.environ.get("XERO_REDIRECT_URI", "").strip()
    if not v:
        raise HTTPException(500, "XERO_REDIRECT_URI is not set")
    return v


def _basic_auth_header() -> str:
    raw = f"{_client_id()}:{_client_secret()}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def build_authorize_url(state: str) -> str:
    from urllib.parse import urlencode
    qs = urlencode({
        "response_type": "code",
        "client_id": _client_id(),
        "redirect_uri": _redirect_uri(),
        "scope": SCOPES,
        "state": state,
    })
    return f"{AUTH_URL}?{qs}"


async def exchange_code_for_tokens(code: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(),
            },
            headers={
                "Authorization": _basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
    if resp.status_code != 200:
        logger.error(f"[XERO] Token exchange failed {resp.status_code}: {resp.text}")
        raise HTTPException(502, f"Xero token exchange failed: {resp.text[:300]}")
    return resp.json()


async def fetch_tenants(access_token: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(CONNECTIONS_URL, headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        })
    if resp.status_code != 200:
        raise HTTPException(502, f"Xero tenants fetch failed: {resp.text[:300]}")
    return resp.json()


async def fetch_organisation(access_token: str, tenant_id: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/Organisation", headers={
            "Authorization": f"Bearer {access_token}",
            "xero-tenant-id": tenant_id,
            "Accept": "application/json",
        })
    if resp.status_code != 200:
        raise HTTPException(502, f"Xero organisation fetch failed: {resp.text[:300]}")
    return resp.json()["Organisations"][0]


async def get_valid_credentials(db, owner_id: str) -> dict:
    """Return {access_token, tenant_id, org_name}. Refreshes if near expiry."""
    doc = await db.xero_tokens.find_one({"owner_id": owner_id})
    if not doc:
        raise HTTPException(400, "Xero is not connected. Connect from the Settings page.")

    now = datetime.now(timezone.utc)
    expires_at = doc["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at - now <= REFRESH_SAFETY_MARGIN:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TOKEN_URL,
                data={"grant_type": "refresh_token", "refresh_token": doc["refresh_token"]},
                headers={
                    "Authorization": _basic_auth_header(),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
        if resp.status_code != 200:
            logger.error(f"[XERO] Refresh failed {resp.status_code}: {resp.text}")
            raise HTTPException(401, "Xero token refresh failed. Please reconnect Xero in Settings.")
        td = resp.json()
        new_access = td["access_token"]
        new_refresh = td.get("refresh_token", doc["refresh_token"])
        expires_in = td.get("expires_in", 1800)
        new_expires_at = now + timedelta(seconds=expires_in)
        await db.xero_tokens.update_one(
            {"_id": doc["_id"]},
            {"$set": {
                "access_token": new_access,
                "refresh_token": new_refresh,
                "expires_at": new_expires_at.isoformat(),
                "scope": td.get("scope", doc.get("scope", "")),
                "updated_at": now.isoformat(),
            }},
        )
        doc["access_token"] = new_access
        doc["refresh_token"] = new_refresh

    return {
        "access_token": doc["access_token"],
        "tenant_id": doc["tenant_id"],
        "org_name": doc.get("org_name"),
    }


def _api_headers(access_token: str, tenant_id: str, *, content_type: str = "application/json") -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "xero-tenant-id": tenant_id,
        "Accept": "application/json",
        "Content-Type": content_type,
    }


async def revoke_refresh_token(refresh_token: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                REVOCATION_URL,
                data={"token": refresh_token},
                headers={
                    "Authorization": _basic_auth_header(),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
    except Exception as e:  # noqa
        logger.warning(f"[XERO] Revoke failed (continuing to delete local doc): {e}")


# ---------- Domain operations ----------

async def find_or_create_contact(creds: dict, shop: dict) -> str:
    """Return Xero ContactID. Looks up by email or name, else POSTs a new contact."""
    headers = _api_headers(creds["access_token"], creds["tenant_id"])
    name = shop["name"]
    email = shop.get("contact_email")

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1) Search by email
        if email:
            r = await client.get(f"{API_BASE}/Contacts", headers=headers,
                                 params={"where": f'EmailAddress=="{email}"'})
            if r.status_code == 200:
                items = r.json().get("Contacts", [])
                if items:
                    return items[0]["ContactID"]

        # 2) Search by name
        r = await client.get(f"{API_BASE}/Contacts", headers=headers,
                             params={"where": f'Name=="{name}"'})
        if r.status_code == 200:
            items = r.json().get("Contacts", [])
            if items:
                return items[0]["ContactID"]

        # 3) Create
        addr = {
            "AddressType": "STREET",
            "AddressLine1": shop.get("address") or "",
            "City": shop.get("city") or "",
            "Region": shop.get("state") or "AZ",
            "PostalCode": shop.get("zip") or "",
            "Country": "United States",
        }
        phones = []
        if shop.get("contact_phone"):
            phones.append({"PhoneType": "DEFAULT", "PhoneNumber": shop["contact_phone"]})
        payload = {"Contacts": [{
            "Name": name,
            "EmailAddress": email or "",
            "Phones": phones,
            "Addresses": [addr],
        }]}
        r = await client.post(f"{API_BASE}/Contacts", headers=headers, json=payload)
    if r.status_code not in (200, 201):
        raise HTTPException(502, f"Xero create contact failed: {r.text[:300]}")
    return r.json()["Contacts"][0]["ContactID"]


async def create_invoice(creds: dict, *, contact_id: str, job: dict, line_label: str) -> dict:
    """Create an ACCREC DRAFT invoice. Returns {invoice_id, invoice_number, status}."""
    headers = _api_headers(creds["access_token"], creds["tenant_id"])
    customer_last = (job.get("customer_last_name") or "CUSTOMER").upper()
    vin = (job.get("vehicle_vin") or "VIN NOT PROVIDED").upper()
    line2 = (
        f"{customer_last} / {job.get('vehicle_year','')} "
        f"{(job.get('vehicle_make') or '').upper()} {(job.get('vehicle_model') or '').upper()} / {vin}"
    ).strip()
    today = datetime.now(timezone.utc).date().isoformat()
    due = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()

    payload = {"Invoices": [{
        "Type": "ACCREC",
        "Contact": {"ContactID": contact_id},
        "Date": today,
        "DueDate": due,
        "Status": "DRAFT",
        "Reference": str(job["id"]),
        "LineItems": [
            {"Description": line_label, "Quantity": 1,
             "UnitAmount": float(job["price"]), "AccountCode": "200"},
            {"Description": line2, "Quantity": 1,
             "UnitAmount": 0.0, "AccountCode": "200"},
        ],
    }]}
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(f"{API_BASE}/Invoices", headers=headers, json=payload)
    if r.status_code not in (200, 201):
        raise HTTPException(502, f"Xero create invoice failed ({r.status_code}): {r.text[:400]}")
    inv = r.json()["Invoices"][0]
    return {
        "invoice_id": inv["InvoiceID"],
        "invoice_number": inv.get("InvoiceNumber"),
        "status": inv.get("Status"),
        "amount_due": inv.get("AmountDue"),
        "amount_paid": inv.get("AmountPaid"),
        "online_url": inv.get("Url"),
    }


async def fetch_invoice(creds: dict, invoice_id: str) -> dict:
    headers = _api_headers(creds["access_token"], creds["tenant_id"])
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(f"{API_BASE}/Invoices/{invoice_id}", headers=headers)
    if r.status_code != 200:
        raise HTTPException(502, f"Xero fetch invoice failed: {r.text[:300]}")
    inv = r.json()["Invoices"][0]
    return {
        "invoice_id": inv["InvoiceID"],
        "invoice_number": inv.get("InvoiceNumber"),
        "status": inv.get("Status"),
        "amount_due": inv.get("AmountDue"),
        "amount_paid": inv.get("AmountPaid"),
    }


async def attach_pdf(creds: dict, invoice_id: str, filename: str, pdf_bytes: bytes) -> dict:
    headers = _api_headers(creds["access_token"], creds["tenant_id"], content_type="application/pdf")
    url = f"{API_BASE}/Invoices/{invoice_id}/Attachments/{filename}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=headers, content=pdf_bytes)
    if r.status_code not in (200, 201):
        raise HTTPException(502, f"Xero attach failed: {r.text[:300]}")
    return r.json()
