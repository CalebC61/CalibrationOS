"""CalibrationOS Backend — Phase 1 MVP (Path B: revenue path with mocked integrations)."""
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import asyncio
import logging
import uuid
import hashlib
import secrets
import random
import math
import base64
import requests
from urllib.parse import quote, urlencode
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta, time, date
import jwt
import bcrypt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Stripe + Resend setup
import stripe as stripe_sdk
import resend as resend_sdk
stripe_sdk.api_key = os.environ.get('STRIPE_API_KEY', 'sk_test_emergent')
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'onboarding@resend.dev')
if RESEND_API_KEY:
    resend_sdk.api_key = RESEND_API_KEY

# Xero (real-if-configured, else mock — mirrors the Stripe/Resend pattern)
from xero_invoice import xero_invoice_body, line_two_description, due_date_string
# Card charging (real-if-Stripe-configured — see /charge-queue/{job_id}/charge)
from charging import cents, chargeable_reason, interpret_payment_intent, decline_message
# Google Maps (real-if-configured, else mock — same pattern; see geocode_address()/get_drive_time())
from google_maps import (
    GEOCODE_URL, DISTANCE_MATRIX_URL, GoogleMapsError,
    geocode_request_params, distance_matrix_request_params,
    parse_geocode_response, parse_distance_matrix_response, drive_time_cache_key, coalesce,
    METRO_LAT_MIN, METRO_LAT_MAX, METRO_LNG_MIN, METRO_LNG_MAX,
)
from business_time import (
    business_date, business_day_bounds, clamp_start_to_business_day, offered_slot_starts,
)
# Module 9 — Partner Growth Engine (models only here; routes are wired conditionally near the
# bottom of this file, only when GROWTH_MODULE_ENABLED, to avoid registering unused routes)
from growth.models import PartnerContact, enforce_grid_caps
XERO_CLIENT_ID = os.environ.get('XERO_CLIENT_ID', '')
XERO_CLIENT_SECRET = os.environ.get('XERO_CLIENT_SECRET', '')
XERO_REDIRECT_URI = os.environ.get('XERO_REDIRECT_URI', '')
XERO_SALES_ACCOUNT_CODE = os.environ.get('XERO_SALES_ACCOUNT_CODE', '200')
XERO_POST_CONNECT_REDIRECT = os.environ.get('XERO_POST_CONNECT_REDIRECT', '/settings')
XERO_SCOPES = "openid profile email accounting.transactions accounting.contacts offline_access"
XERO_AUTH_URL = "https://login.xero.com/identity/connect/authorize"
XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
XERO_CONNECTIONS_URL = "https://api.xero.com/connections"
XERO_API_BASE = "https://api.xero.com/api.xro/2.0"

GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY', '')

def google_maps_enabled() -> bool:
    return bool(GOOGLE_MAPS_API_KEY)

def xero_enabled() -> bool:
    """True when Xero OAuth credentials are configured."""
    return bool(XERO_CLIENT_ID and XERO_CLIENT_SECRET and XERO_REDIRECT_URI)

# Module 9 — Partner Growth Engine (Power Connector 5+50+100 + Zeely-lite reels — reels deferred).
# No external credentials required (dispatch reuses mock_send_sms/send_email below), so this is a
# plain on/off switch rather than a credential-presence check like xero_enabled() above.
GROWTH_MODULE_ENABLED = os.environ.get('GROWTH_MODULE_ENABLED', 'true').lower() == 'true'

# Module 8 — Admin Assist Engine (natural-language admin copilot, Gemini via google-genai).
# Real-if-configured like Stripe/Resend/Xero: needs GOOGLE_API_KEY (Google AI Studio) to activate,
# plus an explicit kill switch. Without the key the module is inert (routes not registered).
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', '')
ASSIST_MODULE_ENABLED = bool(GOOGLE_API_KEY) and \
    os.environ.get('ASSIST_MODULE_ENABLED', 'true').lower() == 'true'

app = FastAPI(title="CalibrationOS API")
api = APIRouter(prefix="/api")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ---------- Security / deployment posture ----------
# APP_ENV gates production hardening. It defaults to "development" so local runs and the test
# suite (which log in with the seeded dev credentials) behave exactly as before. Set
# APP_ENV=production in Emergent to enforce the checks in security_self_check().
APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV in ("production", "prod")

# Seed credentials are env-driven so no real password ships in the repo. When an env password
# is set it is also the source of truth: security-hardened seed_data() rotates an already-seeded
# account whose stored password no longer matches, so the historically-exposed default can be
# fixed by setting OWNER_PASSWORD / CONTRACTOR_PASSWORD in Emergent and restarting.
SEED_OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "caleb@thecalibrationcrew.us").strip()
SEED_OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "")
SEED_CONTRACTOR_EMAIL = os.environ.get("CONTRACTOR_EMAIL", "contractor@thecalibrationcrew.us").strip()
SEED_CONTRACTOR_PASSWORD = os.environ.get("CONTRACTOR_PASSWORD", "")
# Dev-only fallback passwords: used only outside production when no env password is given, so the
# local dev flow and the existing test suite are unchanged.
_DEV_OWNER_PASSWORD = "Owner123!"
_DEV_CONTRACTOR_PASSWORD = "Contractor123!"

# Demo shops / partner-contacts seed in development by default, never in production unless asked.
SEED_DEMO_DATA = os.environ.get(
    "SEED_DEMO_DATA", "false" if IS_PRODUCTION else "true"
).strip().lower() == "true"

# ---------- Auth helpers ----------
_DEV_JWT_SECRET = "calibrationos-dev-secret-change-me"
JWT_SECRET = os.environ.get('JWT_SECRET', _DEV_JWT_SECRET)
JWT_ALG = "HS256"
JWT_EXP_HOURS = 24 * 7
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False

def make_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXP_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

async def get_current_tech(token: Optional[str] = Depends(oauth2_scheme)):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        tech = await db.technicians.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
        if not tech:
            raise HTTPException(status_code=401, detail="User not found")
        return tech
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def require_owner(tech=Depends(get_current_tech)):
    if tech["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner only")
    return tech

def make_portal_token(shop_user_id: str) -> str:
    payload = {
        "sub": shop_user_id, "kind": "portal",
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXP_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

async def get_current_shop_user(token: Optional[str] = Depends(oauth2_scheme)):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated (portal)")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        if payload.get("kind") != "portal":
            raise HTTPException(status_code=401, detail="Not a portal token")
        su = await db.shop_users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
        if not su:
            raise HTTPException(status_code=401, detail="Shop user not found")
        return su
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ---------- Helpers ----------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def iso(dt: datetime) -> str:
    return dt.isoformat()

def gen_id() -> str:
    return str(uuid.uuid4())

# ---------- Mock integrations ----------
# Mock geocoding: simple keyword-based zone lookup with realistic Phoenix-area coordinates
PHOENIX_CITY_COORDS = {
    "goodyear":   (33.4353, -112.3576),
    "avondale":   (33.4356, -112.3496),
    "buckeye":    (33.3703, -112.5838),
    "surprise":   (33.6292, -112.3679),
    "peoria":     (33.5806, -112.2374),
    "glendale":   (33.5387, -112.1860),
    "litchfield": (33.4942, -112.3577),
    "mesa":       (33.4152, -111.8315),
    "chandler":   (33.3062, -111.8413),
    "gilbert":    (33.3528, -111.7890),
    "queen creek":(33.2487, -111.6343),
    "san tan":    (33.1962, -111.6463),
    "apache":     (33.4151, -111.5495),
    "phoenix":    (33.4484, -112.0740),
    "scottsdale": (33.4942, -111.9261),
    "tempe":      (33.4255, -111.9400),
    "paradise":   (33.5722, -111.9509),
}

def mock_geocode(address: str) -> dict:
    """Mock Google Geocoding. Returns lat/lng + formatted address based on city keywords."""
    a = address.lower()
    base = None
    for key, coords in PHOENIX_CITY_COORDS.items():
        if key in a:
            base = coords
            break
    if base is None:
        # Default: somewhere in central Phoenix with slight jitter
        base = (33.4484, -112.0740)
    # Small jitter so each address has a unique-ish coordinate
    seed = sum(ord(c) for c in address)
    rng = random.Random(seed)
    lat = base[0] + rng.uniform(-0.04, 0.04)
    lng = base[1] + rng.uniform(-0.04, 0.04)
    # Same bounding box the real geocoder uses (google_maps.py), so mock and live agree on
    # which addresses are in the service area.
    in_metro = METRO_LAT_MIN < lat < METRO_LAT_MAX and METRO_LNG_MIN < lng < METRO_LNG_MAX
    return {"lat": round(lat, 6), "lng": round(lng, 6), "formatted_address": address, "in_metro": in_metro}

def detect_zone(lng: float) -> str:
    if lng < -112.0:
        return "west"
    return "east"  # Central also maps to East per spec

def haversine_miles(lat1, lng1, lat2, lng2) -> float:
    R = 3958.8
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lng2 - lng1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def mock_distance_matrix(o_lat, o_lng, d_lat, d_lng) -> dict:
    """Mock drive time: ~2 min per mile + traffic buffer."""
    miles = haversine_miles(o_lat, o_lng, d_lat, d_lng)
    minutes = max(10, int(miles * 2.2 + 5))
    return {"distance_miles": round(miles, 1), "duration_minutes": minutes}

# ---------- Google Maps real integration (used when google_maps_enabled()) ----------
def _google_geocode_request(address: str) -> dict:
    resp = requests.get(GEOCODE_URL, params=geocode_request_params(address, GOOGLE_MAPS_API_KEY), timeout=10)
    resp.raise_for_status()
    return resp.json()

def _google_distance_matrix_request(o_lat, o_lng, d_lat, d_lng) -> dict:
    resp = requests.get(
        DISTANCE_MATRIX_URL,
        params=distance_matrix_request_params(o_lat, o_lng, d_lat, d_lng, GOOGLE_MAPS_API_KEY),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()

async def geocode_address(address: str) -> dict:
    """Geocode an address — real Google Geocoding API when configured, otherwise the mock.

    Falls back to the mock on any error (bad address, quota, network) so booking/shop/contractor
    flows never fail on a geocoding hiccup, mirroring the Xero invoice fallback pattern.
    """
    if google_maps_enabled():
        try:
            data = await asyncio.to_thread(_google_geocode_request, address)
            return parse_geocode_response(data, address)
        except (GoogleMapsError, requests.RequestException, KeyError, IndexError) as e:
            logger.error(f"[MAPS] geocode failed, falling back to mock: {e}")
    return mock_geocode(address)

# In-flight real Distance Matrix calls, keyed like drive_time_cache. Concurrent day-map
# lookups that share a rounded destination await one request instead of each paying for a miss.
_DRIVE_TIME_INFLIGHT: dict = {}

async def get_drive_time(o_lat, o_lng, d_lat, d_lng) -> dict:
    """Drive time between two points — real Google Distance Matrix when configured, else mock.

    Real lookups are cached per Phoenix calendar day (rounded coordinates) in `drive_time_cache`.
    The day bucket follows America/Phoenix so it does not roll at 5 PM local. Callers that miss
    the cache together share one in-flight request per cache key. The mock path is not cached
    (it is a local haversine). Falls back to the mock on any error.
    """
    if not google_maps_enabled():
        return mock_distance_matrix(o_lat, o_lng, d_lat, d_lng)
    key = drive_time_cache_key(o_lat, o_lng, d_lat, d_lng, business_date().isoformat())

    async def _load():
        cached = await db.drive_time_cache.find_one({"_id": key})
        if cached:
            return {"distance_miles": cached["distance_miles"], "duration_minutes": cached["duration_minutes"]}
        try:
            data = await asyncio.to_thread(_google_distance_matrix_request, o_lat, o_lng, d_lat, d_lng)
            result = parse_distance_matrix_response(data)
            await db.drive_time_cache.update_one(
                {"_id": key}, {"$set": {**result, "cached_at": now_utc()}}, upsert=True
            )
            return result
        except (GoogleMapsError, requests.RequestException, KeyError, IndexError) as e:
            logger.error(f"[MAPS] distance matrix failed, falling back to mock: {e}")
            return mock_distance_matrix(o_lat, o_lng, d_lat, d_lng)

    return await coalesce(_DRIVE_TIME_INFLIGHT, key, _load)

async def mock_send_sms(to: str, body: str, kind: str = "generic", job_id: Optional[str] = None):
    """Mock Twilio. Logs to sms_log collection so we can show it in UI."""
    doc = {
        "id": gen_id(), "to": to, "body": body, "kind": kind,
        "job_id": job_id, "sent_at": iso(now_utc()),
    }
    await db.sms_log.insert_one(doc)
    logger.info(f"[MOCK SMS → {to}] {body[:80]}")
    return doc

async def mock_xero_create_invoice(job: dict, shop: dict, vehicle: dict, pricing_label: str) -> dict:
    """Mock Xero invoice creation. Returns a fake invoice ID and stores the full payload."""
    invoice_id = f"XERO-{secrets.token_hex(6).upper()}"
    line2 = line_two_description(vehicle)
    payload = {
        "invoice_id": invoice_id,
        "provider": "mock",
        "type": "ACCREC",
        "status": "DRAFT",
        "contact_name": shop["name"],
        "due_date": due_date_string(now_utc()),
        "line_items": [
            {"description": pricing_label, "quantity": 1, "unit_amount": float(job["price"]), "account_code": XERO_SALES_ACCOUNT_CODE},
            {"description": line2, "quantity": 1, "unit_amount": 0.00, "account_code": XERO_SALES_ACCOUNT_CODE},
        ],
        "total": float(job["price"]),
        "created_at": iso(now_utc()),
        "job_id": job["id"],
    }
    await db.mock_xero_invoices.insert_one(payload.copy())
    logger.info(f"[MOCK XERO] Created draft invoice {invoice_id} for {shop['name']} — ${job['price']}")
    return payload

# ---------- Xero real integration (used when xero_enabled() and the owner is connected) ----------
def _xero_token_request(form: dict) -> dict:
    """Exchange or refresh tokens at Xero's identity endpoint (Basic-auth client creds)."""
    resp = requests.post(
        XERO_TOKEN_URL, data=form, auth=(XERO_CLIENT_ID, XERO_CLIENT_SECRET),
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30,
    )
    resp.raise_for_status()
    return resp.json()

def _xero_connections(access_token: str) -> list:
    resp = requests.get(
        XERO_CONNECTIONS_URL,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()

def _xero_headers(access_token: str, tenant_id: str, json_body: bool = True) -> dict:
    h = {"Authorization": f"Bearer {access_token}", "Xero-tenant-id": tenant_id, "Accept": "application/json"}
    if json_body:
        h["Content-Type"] = "application/json"
    return h

def _xero_get_contact_id(access_token, tenant_id, name) -> Optional[str]:
    safe = name.replace('"', '\\"')
    resp = requests.get(f"{XERO_API_BASE}/Contacts", headers=_xero_headers(access_token, tenant_id),
                        params={"where": f'Name=="{safe}"'}, timeout=30)
    resp.raise_for_status()
    contacts = resp.json().get("Contacts", [])
    return contacts[0]["ContactID"] if contacts else None

def _xero_create_contact(access_token, tenant_id, shop) -> str:
    body = {"Contacts": [{
        "Name": shop["name"],
        "EmailAddress": shop.get("contact_email") or "",
        "Phones": [{"PhoneType": "DEFAULT", "PhoneNumber": shop.get("contact_phone") or ""}],
    }]}
    resp = requests.post(f"{XERO_API_BASE}/Contacts", headers=_xero_headers(access_token, tenant_id), json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()["Contacts"][0]["ContactID"]

def _xero_post_invoice(access_token, tenant_id, invoice_body) -> dict:
    resp = requests.post(f"{XERO_API_BASE}/Invoices", headers=_xero_headers(access_token, tenant_id),
                         json={"Invoices": [invoice_body]}, timeout=30)
    resp.raise_for_status()
    return resp.json()["Invoices"][0]

def _xero_attach_pdf(access_token, tenant_id, invoice_id, filename, pdf_bytes) -> dict:
    url = f"{XERO_API_BASE}/Invoices/{invoice_id}/Attachments/{quote(filename)}"
    headers = {"Authorization": f"Bearer {access_token}", "Xero-tenant-id": tenant_id,
               "Accept": "application/json", "Content-Type": "application/pdf"}
    resp = requests.post(url, headers=headers, data=pdf_bytes, timeout=60)
    resp.raise_for_status()
    return resp.json()

def _xero_get_invoice(access_token, tenant_id, invoice_id) -> Optional[dict]:
    resp = requests.get(f"{XERO_API_BASE}/Invoices/{invoice_id}", headers=_xero_headers(access_token, tenant_id), timeout=30)
    resp.raise_for_status()
    invs = resp.json().get("Invoices", [])
    return invs[0] if invs else None

async def _xero_owner() -> Optional[dict]:
    return await db.technicians.find_one({"role": "owner"})

def _xero_token_expired(owner: dict) -> bool:
    exp = owner.get("xero_token_expiry")
    if not exp:
        return True
    try:
        return datetime.fromisoformat(exp) <= now_utc() + timedelta(seconds=60)
    except Exception:
        return True

async def _xero_store_tokens(owner_id, token, tenant_id=None, org_name=None):
    """Persist tokens on the owner record. Xero rotates refresh tokens, so always store the new one."""
    update = {
        "xero_access_token": token.get("access_token"),
        "xero_refresh_token": token.get("refresh_token"),
        "xero_token_expiry": iso(now_utc() + timedelta(seconds=int(token.get("expires_in", 1800)))),
        "xero_connected": True,
        "updated_at": iso(now_utc()),
    }
    if tenant_id:
        update["xero_tenant_id"] = tenant_id
    if org_name is not None:
        update["xero_org_name"] = org_name
    await db.technicians.update_one({"id": owner_id}, {"$set": update})

async def _xero_access_token(owner: dict) -> str:
    """Return a valid access token, refreshing (and persisting the rotated refresh token) if expired."""
    if _xero_token_expired(owner):
        if not owner.get("xero_refresh_token"):
            raise RuntimeError("Xero not connected (no refresh token)")
        token = await asyncio.to_thread(_xero_token_request, {
            "grant_type": "refresh_token", "refresh_token": owner["xero_refresh_token"],
        })
        await _xero_store_tokens(owner["id"], token)
        return token["access_token"]
    return owner["xero_access_token"]

def xero_owner_connected(owner: Optional[dict]) -> bool:
    return bool(owner and owner.get("xero_tenant_id") and (owner.get("xero_access_token") or owner.get("xero_refresh_token")))

async def create_invoice_for_job(job, shop, vehicle, pricing_label, pdf_bytes=None, pdf_name=None) -> dict:
    """Create an ACCREC draft invoice — real Xero when configured + connected, otherwise the mock.

    Always returns a dict with at least: invoice_id, provider, status, total, line_items, job_id.
    On any Xero error it falls back to the mock so job completion never fails on an invoicing hiccup.
    """
    if xero_enabled():
        owner = await _xero_owner()
        if xero_owner_connected(owner):
            try:
                access = await _xero_access_token(owner)
                tenant = owner["xero_tenant_id"]
                contact_id = await asyncio.to_thread(_xero_get_contact_id, access, tenant, shop["name"])
                if not contact_id:
                    contact_id = await asyncio.to_thread(_xero_create_contact, access, tenant, shop)
                body = xero_invoice_body(contact_id, job["price"], pricing_label, vehicle,
                                         XERO_SALES_ACCOUNT_CODE, now_utc())
                inv = await asyncio.to_thread(_xero_post_invoice, access, tenant, body)
                invoice_id = inv.get("InvoiceID")
                attachment_added = False
                if pdf_bytes and invoice_id:
                    try:
                        await asyncio.to_thread(_xero_attach_pdf, access, tenant, invoice_id,
                                                pdf_name or "calibration.pdf", pdf_bytes)
                        attachment_added = True
                    except Exception as e:
                        logger.error(f"[XERO] attachment failed for {invoice_id}: {e}")
                due = inv.get("DueDateString") or inv.get("DueDate") or ""
                result = {
                    "invoice_id": invoice_id,
                    "provider": "xero",
                    "type": "ACCREC",
                    "status": inv.get("Status", "DRAFT"),
                    "contact_name": shop["name"],
                    "due_date": (due[:10] if due else due_date_string(now_utc())),
                    "line_items": [
                        {"description": pricing_label, "quantity": 1, "unit_amount": float(job["price"]), "account_code": XERO_SALES_ACCOUNT_CODE},
                        {"description": line_two_description(vehicle), "quantity": 1, "unit_amount": 0.00, "account_code": XERO_SALES_ACCOUNT_CODE},
                    ],
                    "total": float(inv.get("Total", job["price"])),
                    "attachment_added": attachment_added,
                    "invoice_number": inv.get("InvoiceNumber"),
                    "created_at": iso(now_utc()),
                    "job_id": job["id"],
                }
                await db.xero_invoices.insert_one(result.copy())
                logger.info(f"[XERO] Created {inv.get('Status', 'DRAFT')} invoice {invoice_id} for {shop['name']} (attachment={attachment_added})")
                return result
            except Exception as e:
                logger.error(f"[XERO] real invoice failed, falling back to mock: {e}")
    return await mock_xero_create_invoice(job, shop, vehicle, pricing_label)

# ---------- Constants ----------
STANDARD_PRICING = {
    "static":  {"label": "Static ADAS Calibration",                "price": 125.00},
    "dynamic": {"label": "Dynamic ADAS Calibration",               "price": 125.00},
    "dual":    {"label": "Dual ADAS Calibration",                  "price": 175.00},
    "triple":  {"label": "Triple Camera / Subaru ADAS Calibration","price": 185.00},
    "tesla":   {"label": "Tesla ADAS Calibration",                 "price": 225.00},
}

ZONES = {
    "west": {"name": "West Valley", "slug": "west", "start": "08:00", "end": "14:00",
             "slot_minutes": 45, "max_jobs": 7, "buffer_minutes": 20, "color": "#F97316",
             "lng_min": None, "lng_max": -112.0},
    "east": {"name": "East Valley", "slug": "east", "start": "14:30", "end": "19:00",
             "slot_minutes": 45, "max_jobs": 7, "buffer_minutes": 20, "color": "#3B82F6",
             "lng_min": -111.8, "lng_max": None},
}

CALEB_HOME = {"lat": 33.3528, "lng": -111.7890, "address": "Gilbert, AZ"}

# ---------- Settings persistence (pricing + zones can be edited at runtime) ----------
async def load_settings():
    """Load pricing and zones from DB into the in-memory dicts. Idempotent."""
    pricing_doc = await db.app_settings.find_one({"_id": "pricing"})
    if pricing_doc and "data" in pricing_doc:
        for k, v in pricing_doc["data"].items():
            if k in STANDARD_PRICING and "price" in v:
                STANDARD_PRICING[k]["price"] = float(v["price"])
                if "label" in v:
                    STANDARD_PRICING[k]["label"] = v["label"]
    zones_doc = await db.app_settings.find_one({"_id": "zones"})
    if zones_doc and "data" in zones_doc:
        for k, v in zones_doc["data"].items():
            if k in ZONES:
                for field in ("start", "end", "max_jobs", "slot_minutes", "buffer_minutes"):
                    if field in v and v[field] is not None:
                        ZONES[k][field] = v[field]

async def save_pricing():
    await db.app_settings.update_one(
        {"_id": "pricing"},
        {"$set": {"data": STANDARD_PRICING, "updated_at": iso(now_utc())}},
        upsert=True,
    )

async def save_zones():
    await db.app_settings.update_one(
        {"_id": "zones"},
        {"$set": {"data": ZONES, "updated_at": iso(now_utc())}},
        upsert=True,
    )

# ---------- Pydantic models ----------
class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    token: str
    role: str
    name: str
    tech_id: str

class ShopIn(BaseModel):
    name: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    address: str
    city: Optional[str] = None
    state: str = "AZ"
    zip: Optional[str] = None
    pricing_tier: Literal["standard", "custom"] = "standard"
    custom_rate_static: Optional[float] = None
    custom_rate_dynamic: Optional[float] = None
    custom_rate_dual: Optional[float] = None
    custom_rate_triple: Optional[float] = None
    custom_rate_tesla: Optional[float] = None
    notes: Optional[str] = None
    terms_signed_by: Optional[str] = None

class ShopUpdate(ShopIn):
    status: Optional[Literal["active", "paused", "inactive"]] = None

class SlotQuery(BaseModel):
    booking_token: str
    job_address: str
    date: str  # YYYY-MM-DD

class BookingIn(BaseModel):
    booking_token: str
    job_address: str
    scheduled_start: str  # ISO datetime
    customer_last_name: str
    year: int
    make: str
    model: str
    trim: Optional[str] = None
    vin: Optional[str] = None
    adas_system: Literal["forward_camera", "surround_view", "radar", "multi_camera", "tesla", "other"]
    calibration_type: Literal["static", "dynamic", "dual", "triple", "tesla"]
    notification_phone: Optional[str] = None
    notification_email: Optional[str] = None

class JobStatusUpdate(BaseModel):
    status: Literal["driving", "on_site", "complete", "cancelled"]

class JobComplete(BaseModel):
    result: Literal["pass", "fail"]
    notes: Optional[str] = None
    document_name: Optional[str] = "calibration_report.pdf"

class DispatchIn(BaseModel):
    contractor_id: str

class OfferResponseIn(BaseModel):
    accept: bool

class ReorderIn(BaseModel):
    zone: Literal["west", "east"]
    date: str  # YYYY-MM-DD
    ordered_job_ids: List[str]

class PricingUpdate(BaseModel):
    static: Optional[float] = None
    dynamic: Optional[float] = None
    dual: Optional[float] = None
    triple: Optional[float] = None
    tesla: Optional[float] = None

class ZoneUpdate(BaseModel):
    start: Optional[str] = None  # "HH:MM"
    end: Optional[str] = None
    max_jobs: Optional[int] = None
    slot_minutes: Optional[int] = None
    buffer_minutes: Optional[int] = None

class ContractorUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    home_address: Optional[str] = None
    is_active: Optional[bool] = None

class RescheduleIn(BaseModel):
    scheduled_start: str  # ISO datetime
    reason: Optional[str] = None

class CancelIn(BaseModel):
    reason: Optional[str] = None

class SkipChargeIn(BaseModel):
    reason: Optional[str] = None

class InviteCreateIn(BaseModel):
    shop_id: str
    recipient_email: EmailStr
    origin: Optional[str] = None  # Frontend passes window.location.origin

class ShopUserRegisterIn(BaseModel):
    invite_token: str
    full_name: str
    password: str
    terms_signature: str
    terms_agreed: bool
    origin: Optional[str] = None

class ShopUserLoginIn(BaseModel):
    email: EmailStr
    password: str

# ---------- Auth routes ----------
@api.post("/auth/login", response_model=TokenOut)
async def login(data: LoginIn):
    tech = await db.technicians.find_one({"email": data.email.lower()})
    if not tech or not verify_password(data.password, tech.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not tech.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is disabled")
    token = make_token(tech["id"], tech["role"])
    return TokenOut(token=token, role=tech["role"], name=tech["name"], tech_id=tech["id"])

@api.get("/auth/me")
async def me(tech=Depends(get_current_tech)):
    return tech

# ---------- Reference data ----------
@api.get("/reference/zones")
async def get_zones():
    return list(ZONES.values())

@api.get("/reference/pricing")
async def get_pricing():
    return [{"calibration_type": k, **v} for k, v in STANDARD_PRICING.items()]

# ---------- Geocoding (mock) ----------
@api.post("/geocode")
async def geocode(payload: dict):
    addr = payload.get("address", "")
    geo = await geocode_address(addr)
    zone = detect_zone(geo["lng"]) if geo["in_metro"] else None
    return {**geo, "zone": zone}

# ---------- Shops ----------
@api.get("/shops")
async def list_shops(tech=Depends(require_owner)):
    shops = await db.shops.find({}, {"_id": 0}).to_list(1000)
    return shops

@api.post("/shops")
async def create_shop(data: ShopIn, tech=Depends(require_owner)):
    geo = await geocode_address(data.address)
    zone = detect_zone(geo["lng"])
    shop = {
        "id": gen_id(),
        **data.model_dump(),
        "lat": geo["lat"], "lng": geo["lng"],
        "zone": zone,
        "booking_link_token": secrets.token_hex(16),
        "terms_signed_at": iso(now_utc()) if data.terms_signed_by else None,
        "status": "active",
        "created_at": iso(now_utc()),
        "updated_at": iso(now_utc()),
    }
    await db.shops.insert_one(shop.copy())
    return shop

@api.get("/shops/{shop_id}")
async def get_shop(shop_id: str, tech=Depends(require_owner)):
    shop = await db.shops.find_one({"id": shop_id}, {"_id": 0})
    if not shop:
        raise HTTPException(404, "Shop not found")
    return shop

@api.put("/shops/{shop_id}")
async def update_shop(shop_id: str, data: ShopUpdate, tech=Depends(require_owner)):
    shop = await db.shops.find_one({"id": shop_id})
    if not shop:
        raise HTTPException(404, "Shop not found")
    update = data.model_dump(exclude_unset=True)
    if "address" in update and update["address"] != shop["address"]:
        geo = await geocode_address(update["address"])
        update["lat"] = geo["lat"]; update["lng"] = geo["lng"]
        update["zone"] = detect_zone(geo["lng"])
    update["updated_at"] = iso(now_utc())
    await db.shops.update_one({"id": shop_id}, {"$set": update})
    fresh = await db.shops.find_one({"id": shop_id}, {"_id": 0})
    return fresh

@api.post("/shops/{shop_id}/regenerate-link")
async def regenerate_link(shop_id: str, tech=Depends(require_owner)):
    token = secrets.token_hex(16)
    await db.shops.update_one({"id": shop_id}, {"$set": {"booking_link_token": token, "updated_at": iso(now_utc())}})
    return {"booking_link_token": token}

# ---------- Public booking by token ----------
@api.get("/public/shop/{token}")
async def public_shop(token: str):
    shop = await db.shops.find_one({"booking_link_token": token, "status": "active"},
                                   {"_id": 0, "custom_rate_static": 1, "custom_rate_dynamic": 1,
                                    "custom_rate_dual": 1, "custom_rate_triple": 1, "custom_rate_tesla": 1,
                                    "pricing_tier": 1, "name": 1, "address": 1, "contact_phone": 1,
                                    "contact_email": 1, "id": 1, "booking_link_token": 1, "zone": 1})
    if not shop:
        raise HTTPException(404, "This booking link is not active. Contact The Calibration Crew.")
    return shop

def shop_price_for(shop: dict, cal_type: str) -> float:
    if shop.get("pricing_tier") == "custom":
        custom = shop.get(f"custom_rate_{cal_type}")
        if custom is not None:
            return float(custom)
    return float(STANDARD_PRICING[cal_type]["price"])

def parse_time_str(t: str) -> time:
    h, m = t.split(":")
    return time(int(h), int(m))

async def compute_available_slots(zone_key: str, day: date, job_lat: float, job_lng: float):
    """Slot availability algorithm per spec."""
    z = ZONES[zone_key]
    start_t = parse_time_str(z["start"])
    end_t = parse_time_str(z["end"])
    # Fetch existing jobs in zone on this Phoenix date, ordered by scheduled_start.
    # Zone start/end clocks stay UTC wall times. offered_slot_starts drops any start
    # that would fall on the previous Phoenix day (before 07:00 UTC), including when
    # the hours were saved via /settings/zones.
    day_start, day_end = business_day_bounds(day)
    jobs = await db.jobs.find({
        "zone": zone_key,
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(day_end)},
        "status": {"$nin": ["cancelled"]},
    }, {"_id": 0}).sort("scheduled_start", 1).to_list(100)

    if len(jobs) >= z["max_jobs"]:
        return []

    slots = []
    # Anchor: end of last booked job + drive time, or zone start at home
    if jobs:
        last = jobs[-1]
        anchor_dt = datetime.fromisoformat(last["scheduled_end"])
        if anchor_dt.tzinfo is None:
            anchor_dt = anchor_dt.replace(tzinfo=timezone.utc)
        origin = (last["job_lat"], last["job_lng"])
    else:
        anchor_dt = datetime.combine(day, start_t, tzinfo=timezone.utc)
        origin = (CALEB_HOME["lat"], CALEB_HOME["lng"])

    # Drive time from origin to new job
    dm = await get_drive_time(origin[0], origin[1], job_lat, job_lng)
    drive_min = dm["duration_minutes"]

    # Earliest start = anchor + drive, rounded up to next 15-min boundary
    earliest = anchor_dt + timedelta(minutes=drive_min)
    # Round up to next slot boundary (every 15 min within window)
    minute = (earliest.minute // 15) * 15
    if earliest.minute % 15 != 0 or earliest.second > 0:
        minute += 15
    if minute >= 60:
        earliest = earliest.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        earliest = earliest.replace(minute=minute, second=0, microsecond=0)

    # Generate slots from earliest until zone end, only when the start is on this Phoenix day.
    zone_end_dt = datetime.combine(day, end_t, tzinfo=timezone.utc)
    remaining = z["max_jobs"] - len(jobs)
    for cursor in offered_slot_starts(day, earliest, zone_end_dt, z["slot_minutes"], remaining):
        slots.append({
            "start": iso(cursor),
            "end": iso(cursor + timedelta(minutes=z["slot_minutes"])),
            "drive_time_minutes": drive_min,
            "label": cursor.strftime("%-I:%M %p") if hasattr(cursor, 'strftime') else cursor.isoformat(),
        })
    return slots

@api.post("/public/availability")
async def public_availability(query: SlotQuery):
    shop = await db.shops.find_one({"booking_link_token": query.booking_token, "status": "active"})
    if not shop:
        raise HTTPException(404, "Invalid booking link")
    # Geocode job address
    geo = await geocode_address(query.job_address)
    if not geo["in_metro"]:
        return {"zone": None, "in_metro": False, "slots": [],
                "message": "This address is outside our current service area."}
    zone = detect_zone(geo["lng"])
    # Parse date
    try:
        day = datetime.strptime(query.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date")
    # Validate: not Sunday, not past, not > 21 days out. "Today" is the Phoenix date.
    today = business_date()
    if day.weekday() == 6:
        return {"zone": zone, "in_metro": True, "slots": [], "message": "No availability on Sundays."}
    if day < today:
        return {"zone": zone, "in_metro": True, "slots": [], "message": "That date is in the past."}
    if (day - today).days > 21:
        return {"zone": zone, "in_metro": True, "slots": [], "message": "Bookings are only available 21 days out."}
    slots = await compute_available_slots(zone, day, geo["lat"], geo["lng"])
    return {"zone": zone, "in_metro": True, "slots": slots, "job_lat": geo["lat"], "job_lng": geo["lng"]}

@api.post("/public/book")
async def public_book(data: BookingIn):
    shop = await db.shops.find_one({"booking_link_token": data.booking_token, "status": "active"})
    if not shop:
        raise HTTPException(404, "Invalid booking link")
    geo = await geocode_address(data.job_address)
    if not geo["in_metro"]:
        raise HTTPException(400, "Address outside service area")
    zone = detect_zone(geo["lng"])
    # Parse start
    try:
        start_dt = datetime.fromisoformat(data.scheduled_start.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "Invalid scheduled_start")
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    z = ZONES[zone]
    end_dt = start_dt + timedelta(minutes=z["slot_minutes"])

    # Previous job and sequence are scoped to the Phoenix day of this start instant.
    day_start, day_end = business_day_bounds(business_date(start_dt))
    prev = await db.jobs.find({
        "zone": zone,
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(start_dt)},
        "status": {"$nin": ["cancelled"]},
    }, {"_id": 0}).sort("scheduled_start", -1).limit(1).to_list(1)
    if prev:
        origin = (prev[0]["job_lat"], prev[0]["job_lng"])
    else:
        origin = (CALEB_HOME["lat"], CALEB_HOME["lng"])
    dm = await get_drive_time(origin[0], origin[1], geo["lat"], geo["lng"])

    # Find owner technician
    owner = await db.technicians.find_one({"role": "owner"})

    # Create vehicle
    vehicle = {
        "id": gen_id(), "year": data.year, "make": data.make, "model": data.model,
        "trim": data.trim, "vin": data.vin, "adas_system": data.adas_system,
        "shop_id": shop["id"], "customer_last_name": data.customer_last_name,
        "created_at": iso(now_utc()),
    }
    await db.vehicles.insert_one(vehicle.copy())

    # Determine price from shop rate card
    price = shop_price_for(shop, data.calibration_type)

    # Compute sequence_order: count of existing non-cancelled jobs on this day in this zone + 1
    seq_count = await db.jobs.count_documents({
        "zone": zone,
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(day_end)},
        "status": {"$nin": ["cancelled"]},
    })

    job = {
        "id": gen_id(),
        "shop_id": shop["id"],
        "shop_name": shop["name"],  # denormalized for fast reads
        "vehicle_id": vehicle["id"],
        "technician_id": owner["id"] if owner else None,
        "zone": zone,
        "calibration_type": data.calibration_type,
        "calibration_label": STANDARD_PRICING[data.calibration_type]["label"],
        "scheduled_start": iso(start_dt),
        "scheduled_end": iso(end_dt),
        "job_address": data.job_address,
        "job_lat": geo["lat"], "job_lng": geo["lng"],
        "status": "booked",
        "drive_time_minutes": dm["duration_minutes"],
        "actual_arrival": None, "actual_completion": None,
        "result": None, "notes": None,
        "price": price,
        "invoice_id": None, "invoice_status": "pending",
        "google_calendar_event_id": None,
        "sequence_order": seq_count + 1,
        "notification_phone": data.notification_phone or shop.get("contact_phone"),
        "notification_email": data.notification_email or shop.get("contact_email"),
        "customer_last_name": data.customer_last_name,
        "vehicle_year": data.year, "vehicle_make": data.make, "vehicle_model": data.model, "vehicle_vin": data.vin,
        "created_at": iso(now_utc()), "updated_at": iso(now_utc()),
    }
    await db.jobs.insert_one(job.copy())

    # Mock confirmation SMS
    msg = (f"Booking confirmed with The Calibration Crew. "
           f"{start_dt.strftime('%a %b %d at %-I:%M %p')} for your {data.year} {data.make} {data.model}. "
           f"Questions? Reply to this message.")
    if job["notification_phone"]:
        await mock_send_sms(job["notification_phone"], msg, kind="booking_confirmed", job_id=job["id"])

    # Notify owner of the new booking (alert + mock SMS)
    if owner:
        await db.new_booking_alerts.insert_one({
            "id": gen_id(),
            "job_id": job["id"],
            "owner_id": owner["id"],
            "created_at": iso(now_utc()),
            "seen_at": None,
            "shop_name": shop["name"],
            "scheduled_start": job["scheduled_start"],
            "zone": zone,
            "vehicle": f"{data.year} {data.make} {data.model}",
            "price": price,
        })
        owner_msg = (
            f"🎉 New booking from {shop['name']}: "
            f"{start_dt.strftime('%a %b %d at %-I:%M %p')} — "
            f"{data.year} {data.make} {data.model} (${price:.0f}). "
            f"View on dispatch board."
        )
        if owner.get("phone"):
            await mock_send_sms(owner["phone"], owner_msg, kind="owner_new_booking", job_id=job["id"])

    return {"job_id": job["id"], "booking_reference": job["id"][:8].upper(),
            "scheduled_start": job["scheduled_start"], "zone": zone, "price": price}

# ---------- Jobs (dispatcher + field) ----------
def annotate_at_risk(jobs: List[dict]) -> List[dict]:
    """Mark jobs that are running late or are next-up after a late job."""
    now = now_utc()
    for j in jobs:
        j["is_at_risk"] = False
        j["risk_reason"] = None
        if j["status"] in ("driving", "on_site"):
            sched_end = datetime.fromisoformat(j["scheduled_end"])
            if sched_end.tzinfo is None:
                sched_end = sched_end.replace(tzinfo=timezone.utc)
            if now > sched_end:
                overrun = int((now - sched_end).total_seconds() / 60)
                j["is_at_risk"] = True
                j["risk_reason"] = f"Running {overrun} min over scheduled end"
        elif j["status"] == "booked":
            sched_start = datetime.fromisoformat(j["scheduled_start"])
            if sched_start.tzinfo is None:
                sched_start = sched_start.replace(tzinfo=timezone.utc)
            if now > sched_start + timedelta(minutes=10):
                late = int((now - sched_start).total_seconds() / 60)
                j["is_at_risk"] = True
                j["risk_reason"] = f"Start {late} min past scheduled time"
    return jobs

@api.get("/jobs")
async def list_jobs(date_str: Optional[str] = None, tech=Depends(get_current_tech)):
    """List jobs for a Phoenix date (default: today in America/Phoenix). Contractors only see their own jobs."""
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "Invalid date")
    else:
        d = business_date()
    day_start, day_end = business_day_bounds(d)
    q = {"scheduled_start": {"$gte": iso(day_start), "$lt": iso(day_end)}}
    if tech["role"] == "contractor":
        q["technician_id"] = tech["id"]
    jobs = await db.jobs.find(q, {"_id": 0}).sort("scheduled_start", 1).to_list(500)
    return annotate_at_risk(jobs)

@api.get("/jobs/{job_id}")
async def get_job(job_id: str, tech=Depends(get_current_tech)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    if tech["role"] == "contractor" and job.get("technician_id") != tech["id"]:
        raise HTTPException(403, "Not your job")
    return job

@api.post("/jobs/{job_id}/status")
async def update_status(job_id: str, body: JobStatusUpdate, tech=Depends(get_current_tech)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if tech["role"] == "contractor" and job.get("technician_id") != tech["id"]:
        raise HTTPException(403, "Not your job")
    update = {"status": body.status, "updated_at": iso(now_utc())}
    if body.status == "driving":
        msg = (f"Your technician is on the way to {job['job_address']}. "
               f"ETA approximately {job.get('drive_time_minutes', 20)} minutes.")
        if job.get("notification_phone"):
            await mock_send_sms(job["notification_phone"], msg, kind="on_my_way", job_id=job_id)
    elif body.status == "on_site":
        update["actual_arrival"] = iso(now_utc())
    elif body.status == "cancelled":
        msg = "Your scheduled calibration has been cancelled. Please contact us to reschedule."
        if job.get("notification_phone"):
            await mock_send_sms(job["notification_phone"], msg, kind="cancelled", job_id=job_id)
    await db.jobs.update_one({"id": job_id}, {"$set": update})
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return fresh

@api.post("/jobs/{job_id}/complete")
async def complete_job(job_id: str, body: JobComplete, tech=Depends(get_current_tech)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if tech["role"] == "contractor" and job.get("technician_id") != tech["id"]:
        raise HTTPException(403, "Not your job")

    shop = await db.shops.find_one({"id": job["shop_id"]})
    vehicle = await db.vehicles.find_one({"id": job["vehicle_id"]})

    # Mock document upload
    file_name = f"{job['customer_last_name']}_{shop['name'].upper().replace(' ', '')}_{job['vehicle_make']}_{job['vehicle_model']}_{job['vehicle_year']}.pdf"
    doc = {
        "id": gen_id(), "job_id": job_id, "file_name": file_name,
        "storage_path": f"calibration-docs/Recals/Recal - Caleb/{datetime.fromisoformat(job['scheduled_start']).strftime('%Y/%B')}/{file_name}",
        "file_type": "pdf", "uploaded_at": iso(now_utc()), "uploaded_by": tech["id"],
    }
    await db.documents.insert_one(doc.copy())

    # Create the invoice — real Xero draft if connected, else mock. Attach the
    # technician's uploaded calibration PDF when one exists for this job.
    pricing_label = STANDARD_PRICING[job["calibration_type"]]["label"]
    pdf_bytes = None
    pdf_name = None
    real_doc = await db.documents.find_one({"job_id": job_id, "data_b64": {"$exists": True}})
    if real_doc and real_doc.get("data_b64"):
        try:
            pdf_bytes = base64.b64decode(real_doc["data_b64"])
            pdf_name = real_doc.get("file_name") or file_name
        except Exception:
            pdf_bytes = None
    invoice = await create_invoice_for_job(job, shop, vehicle, pricing_label, pdf_bytes=pdf_bytes, pdf_name=pdf_name)

    update = {
        "status": "complete",
        "actual_completion": iso(now_utc()),
        "result": body.result,
        "notes": body.notes,
        "invoice_id": invoice["invoice_id"],
        "invoice_status": "draft",
        "updated_at": iso(now_utc()),
    }
    await db.jobs.update_one({"id": job_id}, {"$set": update})

    # Completion SMS
    msg = (f"ADAS calibration complete on your {job['vehicle_year']} {job['vehicle_make']} {job['vehicle_model']}. "
           f"Documentation will be included with your invoice. — The Calibration Crew")
    if job.get("notification_phone"):
        await mock_send_sms(job["notification_phone"], msg, kind="completed", job_id=job_id)

    # Notify admin (Maddy). Real email via Resend when configured, else logged for manual send.
    provider = invoice.get("provider", "mock")
    veh_str = f"{job['vehicle_year']} {job['vehicle_make']} {job['vehicle_model']}"
    admin_subject = f"New Invoice Created — {shop['name']} — {veh_str}"
    admin_html = (
        f"<p>A new <b>{invoice.get('status', 'DRAFT')}</b> invoice was created "
        f"({'in Xero' if provider == 'xero' else 'in mock mode'}).</p>"
        f"<ul><li>Invoice: {invoice.get('invoice_id')}</li>"
        f"<li>Shop: {shop['name']}</li><li>Vehicle: {veh_str}</li>"
        f"<li>Amount: ${job['price']}</li></ul>"
        f"<p>Review and approve it in Xero.</p>"
    )
    await send_email(
        os.environ.get("ADMIN_EMAIL", "admin@thecalibrationcrew.us"),
        admin_subject, admin_html, kind="invoice_notification",
        meta={"job_id": job_id, "invoice_id": invoice.get("invoice_id"), "provider": provider},
    )

    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return {"job": fresh, "invoice": invoice, "document": doc}

# ---------- Dashboard summary ----------
@api.get("/dashboard/summary")
async def dashboard_summary(date_str: Optional[str] = None, tech=Depends(require_owner)):
    if date_str:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        d = business_date()
    day_start, day_end = business_day_bounds(d)
    jobs = await db.jobs.find({
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(day_end)},
        "status": {"$ne": "cancelled"},
    }, {"_id": 0}).to_list(500)
    revenue = sum(j["price"] for j in jobs)
    drive_min = sum((j.get("drive_time_minutes") or 0) for j in jobs)
    miles = round(drive_min * 0.5, 1)  # ~30 mph average
    done_by = max((j["scheduled_end"] for j in jobs), default=None)
    annotated = annotate_at_risk(jobs)
    at_risk = sum(1 for j in annotated if j["is_at_risk"])
    return {
        "date": d.isoformat(),
        "job_count": len(jobs),
        "revenue": revenue,
        "estimated_miles": miles,
        "done_by": done_by,
        "at_risk_count": at_risk,
    }

# ---------- Reschedule + cancel (with reason) ----------
@api.post("/jobs/{job_id}/reschedule")
async def reschedule_job(job_id: str, body: RescheduleIn, tech=Depends(require_owner)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] in ("complete", "cancelled"):
        raise HTTPException(400, f"Cannot reschedule a {job['status']} job")
    try:
        new_start = datetime.fromisoformat(body.scheduled_start.replace("Z", "+00:00"))
        if new_start.tzinfo is None:
            new_start = new_start.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(400, "Invalid scheduled_start")
    z = ZONES[job["zone"]]
    new_end = new_start + timedelta(minutes=z["slot_minutes"])
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "scheduled_start": iso(new_start),
        "scheduled_end": iso(new_end),
        "reschedule_reason": body.reason,
        "rescheduled_at": iso(now_utc()),
        "updated_at": iso(now_utc()),
    }})
    # Notify customer
    if job.get("notification_phone"):
        msg = (f"Your calibration appointment has been rescheduled to "
               f"{new_start.strftime('%a %b %d at %-I:%M %p')}. "
               f"Reply if this doesn't work for you. — The Calibration Crew")
        await mock_send_sms(job["notification_phone"], msg, kind="rescheduled", job_id=job_id)
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return fresh

@api.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, body: CancelIn, tech=Depends(require_owner)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] in ("complete", "cancelled"):
        raise HTTPException(400, f"Already {job['status']}")
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "status": "cancelled",
        "cancellation_reason": body.reason,
        "cancelled_at": iso(now_utc()),
        "updated_at": iso(now_utc()),
    }})
    if job.get("notification_phone"):
        reason_suffix = f" Reason: {body.reason}" if body.reason else ""
        msg = f"Your scheduled calibration has been cancelled.{reason_suffix} Please contact us to reschedule."
        await mock_send_sms(job["notification_phone"], msg, kind="cancelled", job_id=job_id)
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return fresh

# ---------- Real document upload (replaces mocked filename) ----------
@api.post("/jobs/{job_id}/upload-document")
async def upload_document(job_id: str, file: UploadFile = File(...), tech=Depends(get_current_tech)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if tech["role"] == "contractor" and job.get("technician_id") != tech["id"]:
        raise HTTPException(403, "Not your job")
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(400, "File too large (max 10 MB)")
    shop = await db.shops.find_one({"id": job["shop_id"]})
    file_name = file.filename or "calibration_report"
    # Spec naming: Customer_SHOP_Make_Model_Year.ext
    ext = (file_name.rsplit(".", 1)[-1] if "." in file_name else "pdf").lower()
    spec_name = (f"{job['customer_last_name']}_{shop['name'].upper().replace(' ', '')}_"
                 f"{job['vehicle_make']}_{job['vehicle_model']}_{job['vehicle_year']}.{ext}")
    doc = {
        "id": gen_id(),
        "job_id": job_id,
        "file_name": spec_name,
        "original_name": file_name,
        "content_type": file.content_type or "application/octet-stream",
        "size_bytes": len(contents),
        "data_b64": base64.b64encode(contents).decode(),
        "uploaded_at": iso(now_utc()),
        "uploaded_by": tech["id"],
        "storage_path": f"calibration-docs/Recals/Recal - {tech['name']}/{datetime.fromisoformat(job['scheduled_start']).strftime('%Y/%B')}/{spec_name}",
    }
    await db.documents.insert_one(doc.copy())
    # Return without the big data field
    return {k: v for k, v in doc.items() if k != "data_b64"}

@api.get("/jobs/{job_id}/documents")
async def list_job_documents(job_id: str, tech=Depends(get_current_tech)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if tech["role"] == "contractor" and job.get("technician_id") != tech["id"]:
        raise HTTPException(403, "Not your job")
    docs = await db.documents.find({"job_id": job_id}, {"_id": 0, "data_b64": 0}).to_list(50)
    return docs

@api.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, tech=Depends(get_current_tech)):
    doc = await db.documents.find_one({"id": doc_id})
    if not doc or "data_b64" not in doc:
        raise HTTPException(404, "Document not found")
    # Permission: owner sees all; contractor only theirs
    if tech["role"] == "contractor":
        job = await db.jobs.find_one({"id": doc["job_id"]})
        if not job or job.get("technician_id") != tech["id"]:
            raise HTTPException(403, "Not your document")
    binary = base64.b64decode(doc["data_b64"])
    # RFC 5987 — handles non-Latin-1 filenames (em-dashes, accents, etc.) without crashing
    quoted = quote(doc["file_name"])
    return Response(content=binary, media_type=doc.get("content_type", "application/octet-stream"),
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"})

# ---------- Public shop status page ----------
@api.get("/public/shop-status/{token}")
async def public_shop_status(token: str):
    shop = await db.shops.find_one({"booking_link_token": token, "status": "active"}, {"_id": 0})
    if not shop:
        raise HTTPException(404, "Shop not found or link inactive")
    # Last 30 days of jobs for this shop
    cutoff = iso(now_utc() - timedelta(days=30))
    jobs = await db.jobs.find(
        {"shop_id": shop["id"], "scheduled_start": {"$gte": cutoff}},
        {"_id": 0, "id": 1, "scheduled_start": 1, "scheduled_end": 1, "status": 1,
         "calibration_label": 1, "price": 1, "vehicle_year": 1, "vehicle_make": 1,
         "vehicle_model": 1, "customer_last_name": 1, "actual_completion": 1, "result": 1}
    ).sort("scheduled_start", -1).limit(50).to_list(50)
    completed = [j for j in jobs if j["status"] == "complete"]
    upcoming = [j for j in jobs if j["status"] in ("booked", "driving", "on_site", "dispatched_to_contractor")]
    total_spent = sum(j["price"] for j in completed)
    return {
        "shop_name": shop["name"],
        "shop_address": shop["address"],
        "zone": shop["zone"],
        "booking_link": shop["booking_link_token"],
        "stats": {
            "jobs_last_30_days": len(jobs),
            "completed_count": len(completed),
            "upcoming_count": len(upcoming),
            "total_spent_last_30_days": total_spent,
            "last_completion": completed[0]["actual_completion"] if completed else None,
        },
        "upcoming": upcoming,
        "completed": completed,
    }

# ---------- SMS log (for transparency in mock mode) ----------
@api.get("/sms-log")
async def sms_log(limit: int = 50, tech=Depends(require_owner)):
    logs = await db.sms_log.find({}, {"_id": 0}).sort("sent_at", -1).limit(limit).to_list(limit)
    return logs

@api.get("/invoices")
async def list_invoices(tech=Depends(require_owner)):
    real = await db.xero_invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    mock = await db.mock_xero_invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    invs = real + mock
    invs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return invs[:200]

# ---------- Xero OAuth connect / callback / disconnect + integration status & polling ----------
def _xero_state_token(owner_id: str) -> str:
    return jwt.encode(
        {"sub": owner_id, "purpose": "xero_oauth",
         "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        JWT_SECRET, algorithm=JWT_ALG,
    )

def _verify_xero_state(state: str) -> Optional[str]:
    try:
        p = jwt.decode(state, JWT_SECRET, algorithms=[JWT_ALG])
        return p.get("sub") if p.get("purpose") == "xero_oauth" else None
    except jwt.PyJWTError:
        return None

@api.get("/auth/xero/connect")
async def xero_connect(tech=Depends(require_owner)):
    """Return the Xero authorize URL for the owner to begin the OAuth flow."""
    if not xero_enabled():
        raise HTTPException(400, "Xero is not configured. Set XERO_CLIENT_ID, XERO_CLIENT_SECRET and XERO_REDIRECT_URI.")
    params = {
        "response_type": "code", "client_id": XERO_CLIENT_ID,
        "redirect_uri": XERO_REDIRECT_URI, "scope": XERO_SCOPES,
        "state": _xero_state_token(tech["id"]),
    }
    return {"authorize_url": f"{XERO_AUTH_URL}?{urlencode(params)}"}

@api.get("/auth/xero/callback")
async def xero_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """OAuth redirect target. Exchanges the code, stores tokens + tenant, redirects back to the app."""
    base = (XERO_POST_CONNECT_REDIRECT or "/settings").split("?")[0]

    def _redirect(status_str):
        return RedirectResponse(url=f"{base}?xero={status_str}", status_code=302)

    if error or not code or not state:
        return _redirect("error")
    owner_id = _verify_xero_state(state)
    if not owner_id:
        return _redirect("error")
    try:
        token = await asyncio.to_thread(_xero_token_request, {
            "grant_type": "authorization_code", "code": code, "redirect_uri": XERO_REDIRECT_URI,
        })
        conns = await asyncio.to_thread(_xero_connections, token["access_token"])
        if not conns:
            return _redirect("error")
        await _xero_store_tokens(owner_id, token, tenant_id=conns[0]["tenantId"], org_name=conns[0].get("tenantName"))
        logger.info(f"[XERO] Connected org '{conns[0].get('tenantName')}' for owner {owner_id}")
        return _redirect("connected")
    except Exception as e:
        logger.error(f"[XERO] OAuth callback failed: {e}")
        return _redirect("error")

@api.post("/auth/xero/disconnect")
async def xero_disconnect(tech=Depends(require_owner)):
    await db.technicians.update_one({"id": tech["id"]}, {"$set": {
        "xero_connected": False, "xero_access_token": None, "xero_refresh_token": None,
        "xero_token_expiry": None, "xero_tenant_id": None, "xero_org_name": None,
    }})
    return {"ok": True}

@api.get("/integrations/status")
async def integrations_status(tech=Depends(require_owner)):
    owner = await _xero_owner()
    connected = xero_owner_connected(owner)
    growth_status = {"enabled": False, "contact_count": 0, "counts_by_circle": {}}
    if GROWTH_MODULE_ENABLED:
        counts_by_circle = {}
        for circle in ("top5", "key50", "vital100", "prospect"):
            counts_by_circle[circle] = await db.partner_contacts.count_documents(
                {"circle": circle, "is_active": True})
        growth_status = {
            "enabled": True,
            "contact_count": sum(counts_by_circle.values()),
            "counts_by_circle": counts_by_circle,
        }
    return {
        "xero": {
            "configured": xero_enabled(),
            "connected": connected,
            "org_name": (owner or {}).get("xero_org_name"),
            "mode": "live" if connected else ("ready" if xero_enabled() else "mock"),
        },
        "google_maps": {
            "configured": google_maps_enabled(),
            "connected": google_maps_enabled(),  # API key only — no separate OAuth connect step
            "mode": "live" if google_maps_enabled() else "mock",
        },
        "twilio": {"configured": False, "connected": False, "mode": "mock"},
        "google_calendar": {"configured": False, "connected": False, "mode": "deferred"},
        "growth": growth_status,
        "assist": {
            "configured": bool(GOOGLE_API_KEY),
            "enabled": ASSIST_MODULE_ENABLED,
            "mode": "live" if ASSIST_MODULE_ENABLED else
                    ("disabled" if GOOGLE_API_KEY else "unconfigured"),
        },
    }

_XERO_STATUS_MAP = {"DRAFT": "draft", "SUBMITTED": "sent", "AUTHORISED": "sent", "PAID": "paid", "VOIDED": "voided"}

@api.post("/integrations/xero/poll")
async def xero_poll(tech=Depends(require_owner)):
    """Poll Xero for invoice status changes (DRAFT→AUTHORISED→PAID) and update jobs. Spec: every ~4h."""
    if not xero_enabled():
        return {"updated": 0, "detail": "Xero not configured"}
    owner = await _xero_owner()
    if not xero_owner_connected(owner):
        return {"updated": 0, "detail": "Xero not connected"}
    try:
        access = await _xero_access_token(owner)
    except Exception as e:
        return {"updated": 0, "detail": f"token error: {e}"}
    tenant = owner["xero_tenant_id"]
    jobs = await db.jobs.find({"invoice_id": {"$nin": [None, ""]}},
                              {"_id": 0, "id": 1, "invoice_id": 1, "invoice_status": 1}).to_list(500)
    updated = 0
    for j in jobs:
        inv_id = j.get("invoice_id") or ""
        if inv_id.startswith("XERO-"):  # mock invoice id — skip
            continue
        try:
            inv = await asyncio.to_thread(_xero_get_invoice, access, tenant, inv_id)
        except Exception as e:
            logger.error(f"[XERO] poll failed for {inv_id}: {e}")
            continue
        if not inv:
            continue
        new_status = _XERO_STATUS_MAP.get(inv.get("Status", ""), j.get("invoice_status"))
        if new_status and new_status != j.get("invoice_status"):
            await db.jobs.update_one({"id": j["id"]}, {"$set": {"invoice_status": new_status, "updated_at": iso(now_utc())}})
            await db.xero_invoices.update_one({"invoice_id": inv_id}, {"$set": {"status": inv.get("Status", "")}})
            updated += 1
    return {"updated": updated}

# ---------- New-booking alerts ----------
@api.get("/notifications/new-bookings")
async def new_booking_alerts(tech=Depends(require_owner)):
    """Returns unseen new-booking alerts for the owner."""
    alerts = await db.new_booking_alerts.find(
        {"owner_id": tech["id"], "seen_at": None},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return {"count": len(alerts), "alerts": alerts}

@api.post("/notifications/mark-seen")
async def mark_alerts_seen(tech=Depends(require_owner)):
    """Mark all unseen new-booking alerts as seen for this owner."""
    now = iso(now_utc())
    res = await db.new_booking_alerts.update_many(
        {"owner_id": tech["id"], "seen_at": None},
        {"$set": {"seen_at": now}}
    )
    return {"marked": res.modified_count}

# ---------- Contractor dispatch ----------
async def expire_stale_offers():
    """Expire offers past their 30-min window. Called on each list-offers / list-jobs read."""
    now = iso(now_utc())
    stale = await db.contractor_offers.find(
        {"status": "pending", "expires_at": {"$lt": now}}, {"_id": 0}
    ).to_list(100)
    for offer in stale:
        await db.contractor_offers.update_one({"id": offer["id"]}, {"$set": {"status": "expired", "responded_at": now}})
        # Revert job back to booked + assign to owner
        owner = await db.technicians.find_one({"role": "owner"})
        await db.jobs.update_one(
            {"id": offer["job_id"]},
            {"$set": {"status": "booked", "technician_id": owner["id"] if owner else None, "updated_at": now}}
        )
        # Mock SMS to owner
        if owner and owner.get("phone"):
            await mock_send_sms(owner["phone"],
                f"Contractor did not respond. Job {offer['job_id'][:8].upper()} is back on your board.",
                kind="offer_expired", job_id=offer["job_id"])

@api.post("/jobs/{job_id}/dispatch")
async def dispatch_job(job_id: str, data: DispatchIn, tech=Depends(require_owner)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] not in ("booked",):
        raise HTTPException(400, f"Cannot dispatch a job in '{job['status']}' state")
    contractor = await db.technicians.find_one({"id": data.contractor_id, "role": "contractor", "is_active": True})
    if not contractor:
        raise HTTPException(400, "Active contractor not found")
    now = now_utc()
    offer = {
        "id": gen_id(),
        "job_id": job_id,
        "contractor_id": contractor["id"],
        "contractor_name": contractor["name"],
        "offered_at": iso(now),
        "expires_at": iso(now + timedelta(minutes=30)),
        "status": "pending",
        "responded_at": None,
        "sms_sent": True,
        "shop_name": job["shop_name"],
        "scheduled_start": job["scheduled_start"],
        "job_address": job["job_address"],
        "vehicle": f"{job['vehicle_year']} {job['vehicle_make']} {job['vehicle_model']}",
        "calibration_label": job["calibration_label"],
        "price": job["price"],
    }
    await db.contractor_offers.insert_one(offer.copy())
    await db.jobs.update_one({"id": job_id}, {"$set": {"status": "dispatched_to_contractor", "technician_id": contractor["id"], "updated_at": iso(now)}})
    # Mock SMS to contractor
    msg = (f"New job available: {job['shop_name']} at {job['job_address']}. "
           f"{job['vehicle_year']} {job['vehicle_make']} {job['vehicle_model']}. "
           f"{job['calibration_label']} at {datetime.fromisoformat(job['scheduled_start']).strftime('%-I:%M %p')}. "
           f"Reply YES to accept, NO to decline. Offer expires in 30 minutes.")
    if contractor.get("phone"):
        await mock_send_sms(contractor["phone"], msg, kind="contractor_offer", job_id=job_id)
    return offer

@api.get("/contractor-offers")
async def list_offers(tech=Depends(get_current_tech)):
    await expire_stale_offers()
    q = {}
    if tech["role"] == "contractor":
        q["contractor_id"] = tech["id"]
        q["status"] = "pending"
    offers = await db.contractor_offers.find(q, {"_id": 0}).sort("offered_at", -1).limit(100).to_list(100)
    return offers

@api.post("/contractor-offers/{offer_id}/respond")
async def respond_to_offer(offer_id: str, body: OfferResponseIn, tech=Depends(get_current_tech)):
    """Contractor accepts/declines; also callable by owner as manual override (simulating SMS reply)."""
    offer = await db.contractor_offers.find_one({"id": offer_id})
    if not offer:
        raise HTTPException(404, "Offer not found")
    if offer["status"] != "pending":
        raise HTTPException(400, f"Offer already {offer['status']}")
    # Auth check: contractor on own offer, or owner
    if tech["role"] == "contractor" and offer["contractor_id"] != tech["id"]:
        raise HTTPException(403, "Not your offer")
    now = iso(now_utc())
    new_status = "accepted" if body.accept else "declined"
    await db.contractor_offers.update_one({"id": offer_id},
        {"$set": {"status": new_status, "responded_at": now}})
    if body.accept:
        # Confirm assignment
        await db.jobs.update_one({"id": offer["job_id"]},
            {"$set": {"technician_id": offer["contractor_id"], "updated_at": now}})
        owner = await db.technicians.find_one({"role": "owner"})
        if owner and owner.get("phone"):
            await mock_send_sms(owner["phone"],
                f"✓ {offer['contractor_name']} accepted job {offer['job_id'][:8].upper()} ({offer['shop_name']}).",
                kind="offer_accepted", job_id=offer["job_id"])
    else:
        # Revert to owner
        owner = await db.technicians.find_one({"role": "owner"})
        await db.jobs.update_one({"id": offer["job_id"]},
            {"$set": {"status": "booked", "technician_id": owner["id"] if owner else None, "updated_at": now}})
        if owner and owner.get("phone"):
            await mock_send_sms(owner["phone"],
                f"✗ {offer['contractor_name']} declined job {offer['job_id'][:8].upper()}. Back on your board.",
                kind="offer_declined", job_id=offer["job_id"])
    return {"status": new_status}

@api.get("/contractors")
async def list_contractors(tech=Depends(require_owner)):
    techs = await db.technicians.find(
        {"role": "contractor"}, {"_id": 0, "password_hash": 0}
    ).to_list(50)
    return techs

# ---------- Job reorder with drive-time recalc ----------
@api.post("/jobs/reorder")
async def reorder_jobs(data: ReorderIn, tech=Depends(require_owner)):
    z = ZONES[data.zone]
    try:
        d = datetime.strptime(data.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date")
    day_start, day_end = business_day_bounds(d)
    # Fetch jobs in scope
    jobs = await db.jobs.find({
        "id": {"$in": data.ordered_job_ids},
        "zone": data.zone,
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(day_end)},
        "status": {"$nin": ["cancelled", "complete"]},
    }, {"_id": 0}).to_list(100)
    by_id = {j["id"]: j for j in jobs}
    if set(data.ordered_job_ids) - set(by_id.keys()):
        raise HTTPException(400, "Some job IDs are invalid or not reorderable")
    # Sequential recalc from zone start, anchored at owner home for first job
    cursor = datetime.combine(d, parse_time_str(z["start"]), tzinfo=timezone.utc)
    origin = (CALEB_HOME["lat"], CALEB_HOME["lng"])
    updates = []
    for seq, jid in enumerate(data.ordered_job_ids, start=1):
        j = by_id[jid]
        dm = await get_drive_time(origin[0], origin[1], j["job_lat"], j["job_lng"])
        # Earliest start = cursor + drive, rounded up to next 15-min boundary
        earliest = cursor + timedelta(minutes=dm["duration_minutes"])
        minute = (earliest.minute // 15) * 15
        if earliest.minute % 15 != 0 or earliest.second > 0:
            minute += 15
        if minute >= 60:
            earliest = earliest.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            earliest = earliest.replace(minute=minute, second=0, microsecond=0)
        new_start = clamp_start_to_business_day(earliest, d)
        if new_start is None:
            raise HTTPException(400, "Reorder would place a job outside this day.")
        new_end = new_start + timedelta(minutes=z["slot_minutes"])
        zone_end_dt = datetime.combine(d, parse_time_str(z["end"]), tzinfo=timezone.utc)
        if new_end > zone_end_dt:
            raise HTTPException(400, "Reorder would push job past zone end. Try a different order.")
        updates.append({
            "id": jid,
            "scheduled_start": iso(new_start),
            "scheduled_end": iso(new_end),
            "drive_time_minutes": dm["duration_minutes"],
            "sequence_order": seq,
        })
        cursor = new_end
        origin = (j["job_lat"], j["job_lng"])
    # Persist
    for u in updates:
        await db.jobs.update_one({"id": u["id"]}, {"$set": {
            "scheduled_start": u["scheduled_start"], "scheduled_end": u["scheduled_end"],
            "drive_time_minutes": u["drive_time_minutes"], "sequence_order": u["sequence_order"],
            "updated_at": iso(now_utc()),
        }})
    return {"updated": len(updates), "jobs": updates}

# ---------- Editable settings ----------
@api.put("/settings/pricing")
async def update_pricing(body: PricingUpdate, tech=Depends(require_owner)):
    d = body.model_dump(exclude_unset=True)
    for k, v in d.items():
        if k in STANDARD_PRICING and v is not None:
            STANDARD_PRICING[k]["price"] = float(v)
    await save_pricing()
    return [{"calibration_type": k, **v} for k, v in STANDARD_PRICING.items()]

@api.put("/settings/zones/{zone_key}")
async def update_zone(zone_key: str, body: ZoneUpdate, tech=Depends(require_owner)):
    if zone_key not in ZONES:
        raise HTTPException(404, "Zone not found")
    d = body.model_dump(exclude_unset=True)
    for k, v in d.items():
        if k in ZONES[zone_key] and v is not None:
            ZONES[zone_key][k] = v
    await save_zones()
    return list(ZONES.values())

@api.put("/contractors/{contractor_id}")
async def update_contractor(contractor_id: str, body: ContractorUpdate, tech=Depends(require_owner)):
    c = await db.technicians.find_one({"id": contractor_id, "role": "contractor"})
    if not c:
        raise HTTPException(404, "Contractor not found")
    update = body.model_dump(exclude_unset=True)
    if "home_address" in update and update["home_address"]:
        geo = await geocode_address(update["home_address"])
        update["home_lat"] = geo["lat"]
        update["home_lng"] = geo["lng"]
    update["updated_at"] = iso(now_utc())
    await db.technicians.update_one({"id": contractor_id}, {"$set": update})
    fresh = await db.technicians.find_one({"id": contractor_id}, {"_id": 0, "password_hash": 0})
    return fresh

# ---------- Email (Resend) ----------
async def send_email(to: str, subject: str, html: str, kind: str = "transactional", meta: Optional[dict] = None):
    """Send transactional email via Resend. Gracefully falls back to DB log if no key."""
    log = {
        "id": gen_id(), "to": to, "from": SENDER_EMAIL, "subject": subject,
        "html": html, "kind": kind, "meta": meta or {}, "sent_at": iso(now_utc()),
        "delivered": False, "provider_id": None, "error": None,
    }
    if not RESEND_API_KEY:
        log["error"] = "No RESEND_API_KEY configured — saved to admin_notifications for manual send"
        await db.admin_notifications.insert_one({**log, "subject": f"[MANUAL SEND] {subject}"})
        logger.info(f"[MOCK EMAIL → {to}] {subject}")
        return log
    try:
        import asyncio
        result = await asyncio.to_thread(resend_sdk.Emails.send, {
            "from": SENDER_EMAIL, "to": [to], "subject": subject, "html": html,
        })
        log["delivered"] = True
        log["provider_id"] = result.get("id") if isinstance(result, dict) else None
        await db.email_log.insert_one(log)
        return log
    except Exception as e:
        log["error"] = str(e)
        await db.email_log.insert_one(log)
        logger.error(f"Resend send failed: {e}")
        return log

def invite_email_html(shop_name: str, register_url: str) -> str:
    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#2A2E37;color:#f5f5f5;font-family:'DM Sans',Arial,sans-serif;padding:40px 0;">
      <tr><td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="background:#343843;border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:32px;">
          <tr><td>
            <div style="font-family:'Saira Stencil One','Courier New',monospace;font-size:28px;letter-spacing:0.04em;color:#F97316;margin:0 0 8px;">CALIBRATION<span style="background:#F97316;color:#2A2E37;padding:2px 8px;margin-left:6px;border-radius:2px;">OS</span></div>
            <p style="color:#9CA0AB;font-size:11px;letter-spacing:0.18em;text-transform:uppercase;margin:0 0 24px;font-weight:600;">By The Calibration Crew · Shop Portal Invitation</p>
            <h2 style="font-family:'Saira Stencil One','Courier New',monospace;font-size:22px;margin:0 0 12px;letter-spacing:0.02em;">{shop_name}, YOU&rsquo;RE INVITED.</h2>
            <p style="color:#c4c4c4;line-height:1.6;font-size:15px;">The Calibration Crew has set up a dedicated portal for your shop. Inside you can:</p>
            <ul style="color:#c4c4c4;line-height:1.7;font-size:15px;">
              <li>View all your scheduled and completed calibrations</li>
              <li>See our daily route map so you can spot add-on opportunities</li>
              <li>Download recalibration documentation for invoicing</li>
              <li>Book new calibrations 24/7</li>
            </ul>
            <p style="color:#c4c4c4;line-height:1.6;font-size:15px;">Setup takes ~2 minutes and includes a card-on-file requirement (we charge per completed job to keep things friction-free).</p>
            <p style="text-align:center;margin:32px 0;">
              <a href="{register_url}" style="background:#F97316;color:#2A2E37;text-decoration:none;padding:14px 28px;border-radius:8px;font-weight:700;display:inline-block;font-family:'Saira Stencil One','Courier New',monospace;letter-spacing:0.06em;">REGISTER NOW &rarr;</a>
            </p>
            <p style="color:#6B7280;font-size:12px;">This link expires in 14 days. Questions? Reply to this email.</p>
          </td></tr>
        </table>
      </td></tr>
    </table>
    """

# ---------- Shop user auth + portal endpoints ----------
@api.post("/invites")
async def create_invite(body: InviteCreateIn, tech=Depends(require_owner)):
    shop = await db.shops.find_one({"id": body.shop_id})
    if not shop:
        raise HTTPException(404, "Shop not found")
    token = secrets.token_urlsafe(24)
    invite = {
        "id": gen_id(), "shop_id": body.shop_id, "shop_name": shop["name"],
        "recipient_email": body.recipient_email, "token": token,
        "status": "pending",
        "created_at": iso(now_utc()),
        "expires_at": iso(now_utc() + timedelta(days=14)),
        "registered_at": None, "shop_user_id": None,
    }
    await db.invites.insert_one(invite.copy())
    origin = (body.origin or "").rstrip('/')
    register_url = f"{origin}/portal/invite/{token}" if origin else f"/portal/invite/{token}"
    await send_email(
        to=body.recipient_email,
        subject=f"You're invited to the CalibrationOS Shop Portal — {shop['name']}",
        html=invite_email_html(shop["name"], register_url),
        kind="invite", meta={"invite_id": invite["id"], "shop_id": shop["id"]},
    )
    return {**invite, "register_url": register_url}

@api.get("/invites")
async def list_invites(tech=Depends(require_owner)):
    invites = await db.invites.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return invites

@api.get("/public/invites/{token}")
async def public_invite_lookup(token: str):
    inv = await db.invites.find_one({"token": token}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invitation not found")
    if inv["status"] != "pending":
        raise HTTPException(400, f"Invitation already {inv['status']}")
    if inv["expires_at"] < iso(now_utc()):
        raise HTTPException(400, "Invitation expired")
    shop = await db.shops.find_one({"id": inv["shop_id"]},
        {"_id": 0, "name": 1, "address": 1, "contact_phone": 1})
    return {**inv, "shop": shop}

@api.post("/public/invites/{token}/register")
async def register_shop_user(token: str, body: ShopUserRegisterIn):
    if not body.terms_agreed:
        raise HTTPException(400, "You must agree to the terms")
    inv = await db.invites.find_one({"token": token})
    if not inv or inv["status"] != "pending" or inv["expires_at"] < iso(now_utc()):
        raise HTTPException(400, "Invitation invalid or expired")
    existing = await db.shop_users.find_one({"email": inv["recipient_email"].lower()})
    if existing:
        raise HTTPException(400, "An account already exists for this email")
    # Create Stripe customer (graceful fallback if Stripe key is the placeholder)
    stripe_customer_id = None
    stripe_error = None
    if stripe_sdk.api_key and not stripe_sdk.api_key.endswith("_emergent"):
        try:
            cust = await asyncio.to_thread(stripe_sdk.Customer.create,
                email=inv["recipient_email"], name=body.full_name,
                metadata={"shop_id": inv["shop_id"]})
            stripe_customer_id = cust["id"]
        except Exception as e:
            stripe_error = str(e)
            logger.warning(f"Stripe customer creation skipped: {e}")
    else:
        stripe_error = "Stripe key not configured (using placeholder)"
    user_id = gen_id()
    su = {
        "id": user_id, "email": inv["recipient_email"].lower(),
        "full_name": body.full_name,
        "password_hash": hash_password(body.password),
        "shop_id": inv["shop_id"], "shop_name": inv["shop_name"],
        "stripe_customer_id": stripe_customer_id,
        "stripe_payment_method_id": None,
        "card_brand": None, "card_last4": None, "card_exp_month": None, "card_exp_year": None,
        "terms_signature": body.terms_signature,
        "terms_signed_at": iso(now_utc()),
        "is_active": True,
        "created_at": iso(now_utc()),
    }
    await db.shop_users.insert_one(su.copy())
    await db.invites.update_one({"token": token}, {"$set": {
        "status": "registered", "registered_at": iso(now_utc()), "shop_user_id": user_id,
    }})
    # Create Stripe Checkout in setup mode to capture card (only if Stripe configured)
    origin = (body.origin or "").rstrip('/')
    checkout_url = None
    if stripe_customer_id and origin:
        try:
            session = await asyncio.to_thread(stripe_sdk.checkout.Session.create,
                mode="setup", payment_method_types=["card"],
                customer=stripe_customer_id,
                success_url=f"{origin}/portal/setup-return?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{origin}/portal/setup-return?cancelled=1",
                metadata={"shop_user_id": user_id})
            checkout_url = session["url"]
        except Exception as e:
            logger.warning(f"Stripe Checkout setup skipped: {e}")
            stripe_error = str(e)
    token_jwt = make_portal_token(user_id)
    return {
        "shop_user_id": user_id, "token": token_jwt,
        "stripe_checkout_url": checkout_url,
        "stripe_unavailable": checkout_url is None,
        "stripe_error": stripe_error,
    }

@api.get("/portal/stripe-setup-status")
async def portal_stripe_setup_status(session_id: str, su=Depends(get_current_shop_user)):
    """Called after Stripe redirect to confirm + persist the payment method."""
    try:
        session = await asyncio.to_thread(stripe_sdk.checkout.Session.retrieve, session_id,
            expand=["setup_intent", "setup_intent.payment_method"])
    except Exception as e:
        raise HTTPException(500, f"Could not retrieve setup session: {e}")
    setup_intent = session.get("setup_intent") or {}
    pm = setup_intent.get("payment_method") or {}
    pm_id = pm.get("id") if isinstance(pm, dict) else pm
    if not pm_id:
        return {"status": "incomplete", "session_status": session.get("status")}
    # Attach as default + fetch card details
    try:
        await asyncio.to_thread(stripe_sdk.Customer.modify, su["stripe_customer_id"],
            invoice_settings={"default_payment_method": pm_id})
        pm_obj = pm if isinstance(pm, dict) and pm.get("card") else \
                 await asyncio.to_thread(stripe_sdk.PaymentMethod.retrieve, pm_id)
        card = pm_obj.get("card", {}) if isinstance(pm_obj, dict) else {}
    except Exception as e:
        raise HTTPException(500, f"Could not attach payment method: {e}")
    await db.shop_users.update_one({"id": su["id"]}, {"$set": {
        "stripe_payment_method_id": pm_id,
        "card_brand": card.get("brand"), "card_last4": card.get("last4"),
        "card_exp_month": card.get("exp_month"), "card_exp_year": card.get("exp_year"),
        "updated_at": iso(now_utc()),
    }})
    fresh = await db.shop_users.find_one({"id": su["id"]}, {"_id": 0, "password_hash": 0})
    return {"status": "complete", "shop_user": fresh}

@api.post("/portal/auth/login")
async def portal_login(body: ShopUserLoginIn):
    su = await db.shop_users.find_one({"email": body.email.lower()})
    if not su or not verify_password(body.password, su.get("password_hash", "")):
        raise HTTPException(401, "Invalid email or password")
    if not su.get("is_active", True):
        raise HTTPException(403, "Account disabled")
    token = make_portal_token(su["id"])
    return {"token": token, "shop_user_id": su["id"], "full_name": su["full_name"],
            "shop_name": su["shop_name"], "shop_id": su["shop_id"],
            "has_payment_method": bool(su.get("stripe_payment_method_id"))}

@api.get("/portal/me")
async def portal_me(su=Depends(get_current_shop_user)):
    shop = await db.shops.find_one({"id": su["shop_id"]}, {"_id": 0})
    return {"shop_user": su, "shop": shop}

@api.get("/portal/jobs")
async def portal_jobs(su=Depends(get_current_shop_user)):
    """List ALL of this shop's jobs."""
    jobs = await db.jobs.find({"shop_id": su["shop_id"]}, {"_id": 0}).sort("scheduled_start", -1).to_list(500)
    return annotate_at_risk(jobs)

@api.get("/portal/jobs/{job_id}")
async def portal_job_detail(job_id: str, su=Depends(get_current_shop_user)):
    job = await db.jobs.find_one({"id": job_id, "shop_id": su["shop_id"]}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    docs = await db.documents.find({"job_id": job_id}, {"_id": 0, "data_b64": 0}).to_list(50)
    return {"job": job, "documents": docs}

@api.get("/portal/jobs/{job_id}/documents/{doc_id}/download")
async def portal_document_download(job_id: str, doc_id: str, su=Depends(get_current_shop_user)):
    job = await db.jobs.find_one({"id": job_id, "shop_id": su["shop_id"]})
    if not job:
        raise HTTPException(404, "Job not found")
    doc = await db.documents.find_one({"id": doc_id, "job_id": job_id})
    if not doc:
        raise HTTPException(404, "Document not found")
    binary = base64.b64decode(doc["data_b64"])
    quoted = quote(doc["file_name"])
    return Response(content=binary, media_type=doc.get("content_type", "application/octet-stream"),
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"})

@api.get("/portal/day-map")
async def portal_day_map(date_str: Optional[str] = None, su=Depends(get_current_shop_user)):
    """OWN jobs in full, plus other shops' jobs as anonymized blocks with drive time from this shop.

    `date_str` is an America/Phoenix civil date. Omitted, it is today's Phoenix date.
    """
    if date_str:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        d = business_date()
    day_start, day_end = business_day_bounds(d)
    all_jobs = await db.jobs.find({
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(day_end)},
        "status": {"$ne": "cancelled"},
    }, {"_id": 0}).sort("scheduled_start", 1).to_list(500)
    # This shop's coordinates as drive-window origin
    shop = await db.shops.find_one({"id": su["shop_id"]})
    origin_lat = shop.get("lat") if shop else 33.4484
    origin_lng = shop.get("lng") if shop else -112.0740
    own, other_jobs = [], []
    for j in all_jobs:
        if j["shop_id"] == su["shop_id"]:
            own.append(j)
        else:
            other_jobs.append(j)

    async def _anon(j):
        # Real lookups hit drive_time_cache (rounded coords, Phoenix day). Run them together
        # so a cold cache does not wait on one Distance Matrix call per other-shop job.
        dm = await get_drive_time(origin_lat, origin_lng, j["job_lat"], j["job_lng"])
        return {
            "id": j["id"],
            "scheduled_start": j["scheduled_start"],
            "scheduled_end": j["scheduled_end"],
            "zone": j["zone"],
            "sequence_order": j.get("sequence_order"),
            "job_lat": j["job_lat"], "job_lng": j["job_lng"],
            "drive_minutes_from_you": dm["duration_minutes"],
            "status": j["status"],
            # NO shop_name, vehicle, customer, calibration, price, address
        }

    others = list(await asyncio.gather(*(_anon(j) for j in other_jobs)))
    return {"own": annotate_at_risk(own), "others": others, "date": d.isoformat()}

@api.post("/portal/book")
async def portal_book(data: BookingIn, su=Depends(get_current_shop_user)):
    """Booking through the portal — uses authenticated shop_user instead of token."""
    shop = await db.shops.find_one({"id": su["shop_id"], "status": "active"})
    if not shop:
        raise HTTPException(400, "Your shop is not active")
    # Override booking_token to the shop's current token internally
    data.booking_token = shop["booking_link_token"]
    return await public_book(data)

# ---------- Owner: charge queue ----------
@api.get("/charge-queue")
async def charge_queue(tech=Depends(require_owner)):
    """Completed jobs from portal shops whose card is on file, not yet charged."""
    portal_users = await db.shop_users.find(
        {"stripe_payment_method_id": {"$ne": None}}, {"_id": 0}
    ).to_list(500)
    shop_id_to_user = {u["shop_id"]: u for u in portal_users}
    jobs = await db.jobs.find({
        "status": "complete",
        "shop_id": {"$in": list(shop_id_to_user.keys())},
        "charged_at": {"$exists": False},
    }, {"_id": 0}).sort("actual_completion", -1).to_list(200)
    enriched = []
    for j in jobs:
        u = shop_id_to_user.get(j["shop_id"], {})
        enriched.append({
            **j,
            "card_brand": u.get("card_brand"),
            "card_last4": u.get("card_last4"),
            "shop_user_email": u.get("email"),
        })
    return enriched

@api.post("/charge-queue/{job_id}/charge")
async def charge_job(job_id: str, tech=Depends(require_owner)):
    """Charge a completed job's card on file — off-session, idempotent per job.

    Falls back to a clear error (never a silent failure) when Stripe isn't configured, the shop
    has no card on file, or the card is declined. Never fails a booking flow — this is an
    owner-initiated action from the Charge Queue, not something automatic.
    """
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    shop_user = await db.shop_users.find_one({"shop_id": job["shop_id"]}, {"_id": 0})
    reason = chargeable_reason(job, shop_user)
    if reason:
        raise HTTPException(400, reason)
    if not (stripe_sdk.api_key and not stripe_sdk.api_key.endswith("_emergent")):
        raise HTTPException(400, "Stripe is not configured yet (set STRIPE_API_KEY).")

    try:
        pi = await asyncio.to_thread(
            stripe_sdk.PaymentIntent.create,
            amount=cents(job["price"]), currency="usd",
            customer=shop_user["stripe_customer_id"],
            payment_method=shop_user["stripe_payment_method_id"],
            off_session=True, confirm=True,
            description=(f"CalibrationOS — {job.get('calibration_label', 'ADAS Calibration')} — "
                         f"{job.get('vehicle_year')} {job.get('vehicle_make')} {job.get('vehicle_model')}"),
            receipt_email=shop_user.get("email"),
            metadata={"job_id": job_id, "shop_id": job["shop_id"]},
            # Stable per job so a double-click or a retried request can't double-charge — Stripe
            # serializes/dedupes concurrent requests sharing an idempotency key on its own.
            idempotency_key=f"charge-job-{job_id}",
        )
    except stripe_sdk.error.CardError as e:
        # decline_code lives on the nested error object (e.error), not on the exception itself
        decline_code = getattr(e.error, "decline_code", None) if e.error else None
        msg = decline_message(e.code, decline_code)
        await db.jobs.update_one({"id": job_id}, {"$set": {
            "charge_error": msg, "charge_error_at": iso(now_utc()),
        }})
        logger.warning(f"[CHARGE] job {job_id} declined: {msg}")
        raise HTTPException(402, msg)
    except stripe_sdk.error.StripeError as e:
        msg = f"Stripe error: {getattr(e, 'user_message', None) or str(e)}"
        await db.jobs.update_one({"id": job_id}, {"$set": {
            "charge_error": msg, "charge_error_at": iso(now_utc()),
        }})
        logger.error(f"[CHARGE] job {job_id} failed: {msg}")
        raise HTTPException(502, msg)

    result = interpret_payment_intent(pi)
    if result["outcome"] != "succeeded":
        msg = result.get("message", "Charge did not complete.")
        await db.jobs.update_one({"id": job_id}, {"$set": {
            "charge_error": msg, "charge_error_at": iso(now_utc()),
        }})
        logger.warning(f"[CHARGE] job {job_id} not completed: {result}")
        raise HTTPException(402, msg)

    await db.jobs.update_one({"id": job_id}, {
        "$set": {
            "charged_at": iso(now_utc()),
            "charge_method": "stripe",
            "stripe_payment_intent_id": result["payment_intent_id"],
            "charged_amount": job["price"],
        },
        "$unset": {"charge_error": "", "charge_error_at": ""},
    })
    logger.info(f"[CHARGE] job {job_id} charged {result['payment_intent_id']} for ${job['price']}")
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return {"status": "charged", "job": fresh}

@api.post("/charge-queue/{job_id}/skip")
async def skip_charge(job_id: str, body: SkipChargeIn, tech=Depends(require_owner)):
    """Mark a completed job as billed outside Stripe (e.g. invoiced manually) — leaves the queue."""
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("charged_at"):
        raise HTTPException(400, "Job has already been charged or resolved.")
    await db.jobs.update_one({"id": job_id}, {
        "$set": {
            "charged_at": iso(now_utc()),
            "charge_method": "manual",
            "skip_reason": body.reason,
        },
        "$unset": {"charge_error": "", "charge_error_at": ""},
    })
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return {"status": "skipped", "job": fresh}

# ---------- Email log ----------
@api.get("/email-log")
async def email_log(tech=Depends(require_owner)):
    logs = await db.email_log.find({}, {"_id": 0}).sort("sent_at", -1).limit(100).to_list(100)
    pending = await db.admin_notifications.find(
        {"subject": {"$regex": "^\\[MANUAL SEND\\]"}}, {"_id": 0}
    ).sort("sent_at", -1).limit(50).to_list(50)
    return {"sent": logs, "pending_manual": pending}

# ---------- Seed ----------
async def seed_data():
    # Owner — password comes from OWNER_PASSWORD (env). Outside production it falls back to a
    # known dev default so local runs and tests are unchanged; in production it is required.
    # The password is never written to the logs.
    owner_email = SEED_OWNER_EMAIL
    owner_pw = SEED_OWNER_PASSWORD or (None if IS_PRODUCTION else _DEV_OWNER_PASSWORD)
    existing = await db.technicians.find_one({"email": owner_email})
    if not existing:
        if owner_pw is None:
            logger.error(
                "[SECURITY] OWNER_PASSWORD is not set and APP_ENV=production — the owner account "
                "was NOT seeded. Set OWNER_PASSWORD in Emergent env and restart to create it."
            )
        else:
            owner = {
                "id": gen_id(), "name": "Caleb (Owner)", "email": owner_email,
                "phone": "+16025550101", "role": "owner",
                "home_zone": "east", "home_address": "Gilbert, AZ",
                "home_lat": CALEB_HOME["lat"], "home_lng": CALEB_HOME["lng"],
                "is_active": True,
                "password_hash": hash_password(owner_pw),
                "xero_connected": False, "xero_access_token": None, "xero_refresh_token": None,
                "xero_token_expiry": None, "xero_tenant_id": None, "xero_org_name": None,
                "google_calendar_connected": True,  # still mocked (out of scope for Step 1)
                "created_at": iso(now_utc()),
            }
            await db.technicians.insert_one(owner)
            logger.info(f"Seeded owner account: {owner_email}")
    elif SEED_OWNER_PASSWORD and not verify_password(SEED_OWNER_PASSWORD, existing.get("password_hash", "")):
        await db.technicians.update_one(
            {"id": existing["id"]}, {"$set": {"password_hash": hash_password(SEED_OWNER_PASSWORD)}}
        )
        logger.warning(f"[SECURITY] Rotated owner password to match OWNER_PASSWORD env for {owner_email}.")

    # Contractor — demo/starter account. Seeds with CONTRACTOR_PASSWORD when set (any env), or the
    # dev default when demo data is enabled; skipped in production if neither applies.
    contractor_email = SEED_CONTRACTOR_EMAIL
    contractor_pw = SEED_CONTRACTOR_PASSWORD or (_DEV_CONTRACTOR_PASSWORD if SEED_DEMO_DATA else None)
    existing_c = await db.technicians.find_one({"email": contractor_email})
    if not existing_c:
        if contractor_pw is not None:
            contractor = {
                "id": gen_id(), "name": "West-Side Contractor", "email": contractor_email,
                "phone": "+16025550199", "role": "contractor",
                "home_zone": "west", "home_address": "Goodyear, AZ",
                "home_lat": 33.4353, "home_lng": -112.3576,
                "is_active": True,
                "password_hash": hash_password(contractor_pw),
                "created_at": iso(now_utc()),
            }
            await db.technicians.insert_one(contractor)
            logger.info(f"Seeded contractor account: {contractor_email}")
    elif SEED_CONTRACTOR_PASSWORD and not verify_password(SEED_CONTRACTOR_PASSWORD, existing_c.get("password_hash", "")):
        await db.technicians.update_one(
            {"id": existing_c["id"]}, {"$set": {"password_hash": hash_password(SEED_CONTRACTOR_PASSWORD)}}
        )
        logger.warning(f"[SECURITY] Rotated contractor password to match CONTRACTOR_PASSWORD env for {contractor_email}.")

    # Demo shops (gated: on in dev, off in production unless SEED_DEMO_DATA=true)
    shop_count = await db.shops.count_documents({})
    if SEED_DEMO_DATA and shop_count == 0:
        demo_shops = [
            {"name": "Safelite — Gilbert", "address": "1234 E Williams Field Rd, Gilbert, AZ",
             "contact_name": "Dana", "contact_phone": "+16025550102", "contact_email": "gilbert@safelite.demo"},
            {"name": "AutoGlassNow — Goodyear", "address": "5678 W McDowell Rd, Goodyear, AZ",
             "contact_name": "Marcus", "contact_phone": "+16025550103", "contact_email": "goodyear@agn.demo",
             "pricing_tier": "custom", "custom_rate_static": 115.00, "custom_rate_dynamic": 115.00},
            {"name": "Glass Doctor — Mesa", "address": "9876 E Main St, Mesa, AZ",
             "contact_name": "Priya", "contact_phone": "+16025550104", "contact_email": "mesa@glassdoc.demo"},
        ]
        for s in demo_shops:
            # Deliberately mock, not geocode_address(): these are fake demo addresses (gated off
            # in production by SEED_DEMO_DATA) — no reason to spend a real Maps API call on them.
            geo = mock_geocode(s["address"])
            zone = detect_zone(geo["lng"])
            shop = {
                "id": gen_id(),
                "name": s["name"], "contact_name": s.get("contact_name"),
                "contact_phone": s.get("contact_phone"), "contact_email": s.get("contact_email"),
                "address": s["address"], "city": None, "state": "AZ", "zip": None,
                "lat": geo["lat"], "lng": geo["lng"], "zone": zone,
                "booking_link_token": secrets.token_hex(16),
                "pricing_tier": s.get("pricing_tier", "standard"),
                "custom_rate_static": s.get("custom_rate_static"),
                "custom_rate_dynamic": s.get("custom_rate_dynamic"),
                "custom_rate_dual": s.get("custom_rate_dual"),
                "custom_rate_triple": s.get("custom_rate_triple"),
                "custom_rate_tesla": s.get("custom_rate_tesla"),
                "terms_signed_at": iso(now_utc()), "terms_signed_by": "Demo Signer",
                "status": "active", "notes": None,
                "created_at": iso(now_utc()), "updated_at": iso(now_utc()),
            }
            await db.shops.insert_one(shop)
        logger.info(f"Seeded {len(demo_shops)} demo shops")

    # Module 9 seed: partner_contacts grounded in the real demo shops + the owner — not the
    # doc's aspirational 60-tech Phoenix list. key50/vital100 start empty; real partners get
    # added via the Growth UI once live.
    if GROWTH_MODULE_ENABLED:
        if await db.partner_contacts.count_documents({}) == 0:
            rank = 1
            shops_for_seed = await db.shops.find({}, {"_id": 0}).to_list(10)
            for s in shops_for_seed:
                if not s.get("contact_name"):
                    continue
                contact = PartnerContact(
                    shop_id=s["id"], first_name=s["contact_name"], last_name="(Shop Contact)",
                    role="owner", company_name=s["name"], phone=s.get("contact_phone"),
                    email=s.get("contact_email"), ecosystem="glass_shop",
                    circle="top5", circle_rank=rank,
                )
                await db.partner_contacts.insert_one(contact.model_dump())
                rank += 1
            owner_tech = await db.technicians.find_one({"role": "owner"})
            if owner_tech:
                internal = PartnerContact(
                    first_name=owner_tech["name"].split(" ")[0], last_name="(Owner)",
                    role="internal", company_name="Calibration Crew", phone=owner_tech.get("phone"),
                    email=owner_tech.get("email"), ecosystem="internal",
                    circle="top5", circle_rank=rank,
                )
                await db.partner_contacts.insert_one(internal.model_dump())
            logger.info("Seeded partner_contacts for Module 9 (Partner Growth Engine)")
        await enforce_grid_caps(db)  # idempotent safety net, cheap to run every startup

def security_self_check():
    """Log deployment security posture at startup; fail closed in production on an unsafe secret."""
    warnings = []
    if JWT_SECRET == _DEV_JWT_SECRET:
        warnings.append("JWT_SECRET is the public dev default — set a strong random JWT_SECRET.")
    if not (stripe_sdk.api_key and not stripe_sdk.api_key.endswith("_emergent")):
        warnings.append("STRIPE_API_KEY is the placeholder — real card charges stay disabled until a live key is set.")
    if os.environ.get("CORS_ORIGINS", "*").strip() == "*":
        warnings.append("CORS_ORIGINS is '*' (any site) — set it to your app domain(s).")
    if IS_PRODUCTION and not SEED_OWNER_PASSWORD:
        warnings.append("OWNER_PASSWORD is not set — the owner login has no env-managed password.")

    if not warnings:
        logger.info("[SECURITY] Startup posture OK (env=%s).", APP_ENV)
    else:
        for w in warnings:
            logger.warning("[SECURITY] %s", w)
        # Refuse to expose a production deployment that is still signing tokens with the public
        # dev secret — anyone reading the repo could forge a login. Only trips once APP_ENV is
        # explicitly set to production, so development and CI are never affected.
        if IS_PRODUCTION and JWT_SECRET == _DEV_JWT_SECRET:
            raise RuntimeError(
                "Refusing to start in production with the default JWT_SECRET. "
                "Set JWT_SECRET (and OWNER_PASSWORD, CORS_ORIGINS) in the environment first."
            )


@app.on_event("startup")
async def startup():
    security_self_check()
    await seed_data()
    await load_settings()
    # Auto-expire cached real-Maps drive times after 2 days. Keys are already one per Phoenix
    # calendar day, so this only caps collection size. Leave expireAfterSeconds as-is: changing
    # it on a database that already has the index raises IndexOptionsConflict.
    await db.drive_time_cache.create_index("cached_at", expireAfterSeconds=172800)

# Include router
if GROWTH_MODULE_ENABLED:
    from growth.routes import build_growth_router
    api.include_router(build_growth_router(
        db=db, require_owner=require_owner, mock_send_sms=mock_send_sms, send_email=send_email,
    ))
if ASSIST_MODULE_ENABLED:
    from assist.routes import build_assist_router
    api.include_router(build_assist_router(db=db, require_owner=require_owner))
    logger.info("[ASSIST] Module 8 Admin Assist Engine enabled (model via GOOGLE_API_KEY)")
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown():
    client.close()
