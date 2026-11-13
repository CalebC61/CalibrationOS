"""CalibrationOS Backend — Phase 1 MVP (Path B: revenue path with mocked integrations)."""
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReadPreference, ReturnDocument
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


def _env(name: str, default: str = "") -> str:
    """Read one env var. A missing or blank value uses default."""
    return (os.environ.get(name) or "").strip() or default


def cors_allow_origins() -> list[str]:
    """Comma-separated CORS_ORIGINS, with spaces and empty entries removed.

    A blank setting matches the historical default of '*'. security_self_check warns on that.
    """
    origins = [part.strip() for part in os.environ.get("CORS_ORIGINS", "*").split(",") if part.strip()]
    return origins or ["*"]


mongo_url = os.environ['MONGO_URL']
# Writes always land on the primary. A URI readPreference of secondary (or
# secondaryPreferred) would let the owner list miss a request that was just
# inserted. Pin reads to the primary so the list sees that write.
client = AsyncIOMotorClient(mongo_url, read_preference=ReadPreference.PRIMARY)
db = client[os.environ['DB_NAME']]

# Stripe + Resend setup
import stripe as stripe_sdk
import resend as resend_sdk

def stripe_secret() -> str:
    """STRIPE_SECRET_KEY is the key to set. STRIPE_API_KEY still works for older deploys."""
    return _env("STRIPE_SECRET_KEY") or _env("STRIPE_API_KEY")


def billing_enabled() -> bool:
    from safety import env_flag
    return env_flag(os.environ.get("BILLING_ENABLED"))


def stripe_configured() -> bool:
    from safety import stripe_key_for_use
    return bool(stripe_key_for_use(stripe_secret(), billing_enabled=billing_enabled()))


def get_stripe():
    from safety import stripe_key_for_use
    key = stripe_key_for_use(stripe_secret(), billing_enabled=billing_enabled())
    if not key:
        return None
    stripe_sdk.api_key = key
    return stripe_sdk.StripeClient(key)


stripe_sdk.api_key = "sk_test_emergent"
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
SENDER_EMAIL = _env('SENDER_EMAIL', 'onboarding@resend.dev')
OWNER_PHONE = _env("OWNER_PHONE", "(480) 269-1329")
# Links in owner emails. A blank value uses the public site, not the browser address.
PUBLIC_SITE_URL = _env('PUBLIC_SITE_URL', 'https://www.thecalibrationcrew.us').rstrip('/')
if RESEND_API_KEY:
    resend_sdk.api_key = RESEND_API_KEY

# Xero (real-if-configured, else mock — mirrors the Stripe/Resend pattern)
from xero_invoice import xero_invoice_body, line_two_description, due_date_string
# Card charging (real-if-Stripe-configured — see /charge-queue/{job_id}/charge)
from charging import cents, chargeable_reason, interpret_payment_intent, decline_message
from onboarding import (
    AGREEMENT_PARAGRAPHS, AGREEMENT_SECTIONS, AGREEMENT_VERSION, CARD_SETUP_ATTEMPT_LIMIT,
    CHARGE_ACCEPTANCE_TEXT, SIGNUP_ATTEMPT_LIMIT, SIGNUP_WINDOW_SECONDS, agreement_text,
    address_needs_confirmation, addresses_match, address_problem, app_link, booking_gate,
    canonical_email, duplicate_fields, invite_email_html, invite_register_url, normalize_phone,
    password_error, rate_limit_exceeded, resolve_frontend_url, reused_shop_pin,
    sender_email_problem, shop_contact_errors, welcome_email_html,
)
# Invite, reset, and booking links. A blank FRONTEND_URL uses the public site.
FRONTEND_URL = resolve_frontend_url(_env("FRONTEND_URL"), PUBLIC_SITE_URL)
from billing import (
    CHARGE_MODE, INVOICE_MODE, TRIP_FEE_REASONS, amount_due, apply_late_fee, apply_trip_fee_only,
    billing_plan, payment_mode, set_outside_service_area, treat_decline_as_invoice,
)
from payments import (
    charge_job as stripe_charge_job,
    create_anonymous_setup_intent, create_checkout_setup, create_customer as stripe_create_customer,
    create_job_invoice, create_late_fee_invoice, create_setup_intent,
    mark_invoice_paid_out_of_band, retrieve_setup_checkout, retrieve_setup_intent,
    save_payment_method,
)
# Google Maps (real-if-configured, else mock — same pattern; see geocode_address()/get_drive_time())
from google_maps import (
    GEOCODE_URL, DISTANCE_MATRIX_URL, ROUTES_COMPUTE_URL, ROUTES_FIELD_MASK, GoogleMapsError,
    geocode_request_params, distance_matrix_request_params,
    parse_geocode_response, parse_distance_matrix_response, parse_routes_response,
    routes_request_body, routes_request_headers, routes_http_failure,
    drive_time_cache_key, departure_bucket, coalesce,
    METRO_LAT_MIN, METRO_LAT_MAX, METRO_LNG_MIN, METRO_LNG_MAX,
)
from address_pin import (
    ADDRESS_NOT_FOUND, OUTSIDE_VALLEY, AddressNotFound,
    came_from_fallback, interpret_live_geocode, pin_refusal,
)
from booking_mail import (
    booking_confirmation_email, mail_route, normalize_us_phone, owner_alert_email,
    owner_needs_alert, shop_emails_enabled, shop_event_email,
)
from days_off import closure_message, holiday_records, jobs_to_flag, parse_range
from owner_links import assess_owner_link, mark_used, mint_owner_link, token_claims
from business_time import (
    BUSINESS_TZ, business_date, business_day_bounds, clamp_start_to_business_day,
    offered_slot_starts, zone_window,
)
from booking_fields import completion_notes, job_customer_fields
from job_edits import changed_keys, is_upcoming, prepare_edit, shift_scheduled_end
from regeocode import (
    detect_zone, jobs_on_phoenix_day, location_set, regeocode_records,
    regeocode_scope, zone_for_geocode,
)
from routing import (
    assign_technician, contractor_routing_updates,
    is_routing_tech, next_tech_color, owner_routing_updates, tech_schedule,
)
from scheduling import (
    BUFFER_MINUTES, DURATION_MINUTES, annotated_drive_queries, block_minutes, candidate_slots,
    insertion_cost, placement_error, round_up, slot_touching_queries,
)
from route_cost import (
    ESSENTIALS, PRO, apply_rush, cache_ttl_seconds, collapse_queries, default_drive_settings,
    leg_signature, normalize_address, routing_mode,
)
from addons import (
    arrival_band, policy_from_tech, request_kind, same_day_closed_message, slot_decision,
)
# Module 9 — Partner Growth Engine (models only here; routes are wired conditionally near the
# bottom of this file, only when GROWTH_MODULE_ENABLED, to avoid registering unused routes)
from growth.models import PartnerContact, enforce_grid_caps
XERO_CLIENT_ID = os.environ.get('XERO_CLIENT_ID', '')
XERO_CLIENT_SECRET = os.environ.get('XERO_CLIENT_SECRET', '')
XERO_REDIRECT_URI = os.environ.get('XERO_REDIRECT_URI', '')
XERO_SALES_ACCOUNT_CODE = _env('XERO_SALES_ACCOUNT_CODE', '200')
XERO_POST_CONNECT_REDIRECT = _env('XERO_POST_CONNECT_REDIRECT', '/settings')
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
SEED_OWNER_EMAIL = _env("OWNER_EMAIL", "caleb@thecalibrationcrew.us")


def owner_notify_email() -> str:
    return _env("OWNER_EMAIL", "caleb@thecalibrationcrew.us")
SEED_OWNER_PASSWORD = _env("OWNER_PASSWORD")
SEED_CONTRACTOR_EMAIL = _env("CONTRACTOR_EMAIL", "contractor@thecalibrationcrew.us")
SEED_CONTRACTOR_PASSWORD = _env("CONTRACTOR_PASSWORD")
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
    """Mock Google Geocoding. Returns lat/lng + formatted address based on city keywords.

    This is a guess. Shop and job saves must not store it. `guessed` is true when
    the address matched no city and the pin is the central-Phoenix default.
    """
    a = address.lower()
    base = None
    for key, coords in PHOENIX_CITY_COORDS.items():
        if key in a:
            base = coords
            break
    guessed = base is None
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
    return {
        "lat": round(lat, 6), "lng": round(lng, 6), "formatted_address": address,
        "in_metro": in_metro, "source": "mock", "guessed": guessed,
        "partial_match": False,
        "location_type": "APPROXIMATE" if guessed else "GEOMETRIC_CENTER",
    }

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

def _google_routes_request(o_lat, o_lng, d_lat, d_lng, departure_iso: str | None,
                           routing_preference: str) -> dict:
    """computeRoutes. The key stays in a header so it is not part of the URL.

    TRAFFIC_UNAWARE does not send departureTime. A non-2xx response, including
    403, is logged with the response body and the key stripped.
    """
    resp = requests.post(
        ROUTES_COMPUTE_URL,
        headers=routes_request_headers(GOOGLE_MAPS_API_KEY),
        json=routes_request_body(
            o_lat, o_lng, d_lat, d_lng, departure_iso, routing_preference,
        ),
        timeout=10,
    )
    if resp.status_code >= 400:
        detail = routes_http_failure(resp.status_code, resp.text or "", GOOGLE_MAPS_API_KEY)
        logger.warning("[MAPS] Routes computeRoutes failed: %s", detail)
        raise GoogleMapsError(detail)
    return resp.json()

def _cached_geocode(cached: dict, address: str) -> dict:
    return {
        "lat": cached["lat"], "lng": cached["lng"],
        "formatted_address": cached.get("formatted_address") or address,
        "in_metro": cached.get("in_metro", True),
        "partial_match": bool(cached.get("partial_match")),
        "location_type": cached.get("location_type"),
        "source": cached.get("source") or "google",
    }


async def geocode_address(address: str) -> dict:
    """Geocode an address with Google. Never invents a pin.

    A missing key, a Google error, a partial match, or the central-Phoenix
    guess raises AddressNotFound. A real result outside the valley is returned
    with in_metro false so the caller can refuse the save without storing it.
    """
    if not (address or "").strip() or not google_maps_enabled():
        raise AddressNotFound(ADDRESS_NOT_FOUND)
    key = normalize_address(address)
    cache = getattr(db, "geocode_cache", None)
    if cache is not None and key:
        try:
            cached = await cache.find_one({"_id": key})
        except Exception as exc:
            logger.warning("[MAPS] geocode cache read failed: %s", exc)
            cached = None
        if cached and cached.get("lat") is not None:
            geo = _cached_geocode(cached, address)
            if pin_refusal(geo) != ADDRESS_NOT_FOUND:
                return geo
    try:
        data = await asyncio.to_thread(_google_geocode_request, address)
        parsed = interpret_live_geocode(address, lambda: data, parse_geocode_response)
    except AddressNotFound:
        logger.error("[MAPS] geocode refused for %s", address)
        raise
    except (requests.RequestException, GoogleMapsError) as exc:
        logger.error("[MAPS] geocode failed: %s", exc)
        raise AddressNotFound(ADDRESS_NOT_FOUND) from exc
    if cache is not None and key and pin_refusal(parsed) is None:
        try:
            await cache.update_one(
                {"_id": key},
                {"$set": {**parsed, "cached_at": now_utc()}},
                upsert=True,
            )
        except Exception as exc:
            logger.warning("[MAPS] geocode cache write failed: %s", exc)
    return parsed


def _refuse_unusable_pin(geo: dict) -> None:
    """Raise 400 when this result must not be written onto a shop or a job."""
    refusal = pin_refusal(geo)
    if refusal:
        raise HTTPException(400, refusal)


def mock_geocode_strict(address: str) -> Optional[dict]:
    """City-keyword geocode with no central-Phoenix guess. None when the city is unknown."""
    lowered = address.lower()
    base = None
    for key, coords in PHOENIX_CITY_COORDS.items():
        if key in lowered:
            base = coords
            break
    if base is None:
        return None
    seed = sum(ord(c) for c in address)
    rng = random.Random(seed)
    lat = base[0] + rng.uniform(-0.02, 0.02)
    lng = base[1] + rng.uniform(-0.02, 0.02)
    return {
        "lat": round(lat, 6), "lng": round(lng, 6),
        "formatted_address": address.strip(),
        "in_metro": METRO_LAT_MIN < lat < METRO_LAT_MAX and METRO_LNG_MIN < lng < METRO_LNG_MAX,
        "fallback": False,
    }


async def geocode_shop_address(address: str) -> dict:
    """Locate a shop. A Maps failure is an error. There is no invented pin."""
    if google_maps_enabled():
        try:
            data = await asyncio.to_thread(_google_geocode_request, address)
            parsed = parse_geocode_response(data, address)
            parsed["fallback"] = False
            return parsed
        except (GoogleMapsError, requests.RequestException, KeyError, IndexError) as exc:
            logger.error("[MAPS] shop geocode failed: %s", exc)
            raise HTTPException(400, "Could not locate that address. Check the street and city and try again.")
    geo = mock_geocode_strict(address)
    if not geo:
        raise HTTPException(400, "Could not locate that address inside the Phoenix Valley.")
    return geo


async def geocode_for_regeocode(address: str) -> dict:
    """Geocode one stored address during a repair pass.

    A failed Google call is an error and the caller leaves the existing pin
    alone. With no API key, the mock is the current geocoder. Shop and job
    saves use geocode_address, which refuses a guess instead of storing one.
    """
    if not google_maps_enabled():
        return mock_geocode(address)
    data = await asyncio.to_thread(_google_geocode_request, address)
    return parse_geocode_response(data, address)

# In-flight Routes API calls, keyed like drive_time_cache. Concurrent lookups that share a
# rounded leg and departure bucket await one request instead of each paying for a miss.
_DRIVE_TIME_INFLIGHT: dict = {}
_LOGGED_MISSING_MAPS_KEY = False
_LOGGED_PAST_DEPARTURE = False
_LOGGED_BUDGET: set = set()

def _log_drive_fallback(reason: str):
    global _LOGGED_MISSING_MAPS_KEY, _LOGGED_PAST_DEPARTURE
    if reason == "no-key":
        if _LOGGED_MISSING_MAPS_KEY:
            return
        _LOGGED_MISSING_MAPS_KEY = True
        logger.warning(
            "[MAPS] GOOGLE_MAPS_API_KEY is not set. Using the mileage estimate for drive time."
        )
        return
    if reason == "departure is not in the future":
        if _LOGGED_PAST_DEPARTURE:
            return
        _LOGGED_PAST_DEPARTURE = True
    logger.warning("[MAPS] drive time fell back to the mileage estimate: %s", reason)

def _cache_is_fresh(cached: dict) -> bool:
    raw = cached.get("expires_at") or cached.get("cached_at")
    if isinstance(raw, datetime):
        seen = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    else:
        try:
            seen = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return False
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
    if cached.get("expires_at"):
        return now_utc() < seen.astimezone(timezone.utc)
    # Older rows only stored cached_at. Treat them as expired so a new mode key is fetched.
    return False

def _departure_for_routes(depart_at: datetime | None) -> datetime | None:
    """A future departure Google will accept, or None when we should not call Routes.

    computeRoutes rejects a departureTime in the past. Callers that omit one
    mean 'leave now'. A past instant (a job that already ended) uses the estimate.
    """
    now = now_utc()
    if depart_at is None:
        depart_at = now + timedelta(minutes=2)
    if depart_at.tzinfo is None:
        depart_at = depart_at.replace(tzinfo=timezone.utc)
    depart_at = depart_at.astimezone(timezone.utc)
    if depart_at <= now + timedelta(seconds=30):
        return None
    return depart_at

def _merge_drive_settings(doc: dict | None) -> dict:
    merged = default_drive_settings()
    for key in merged:
        if doc and doc.get(key) not in (None, ""):
            merged[key] = doc[key]
    return merged


async def load_drive_settings() -> dict:
    store = getattr(db, "app_settings", None)
    if store is None:
        return default_drive_settings()
    try:
        doc = await store.find_one({"_id": "drive"})
    except Exception as exc:
        logger.warning("[MAPS] drive settings unreadable, using defaults: %s", exc)
        return default_drive_settings()
    return _merge_drive_settings(doc)


async def _routes_budget_allows(mode: str, settings: dict) -> bool:
    """Count one Google Routes call for today. False when that mode's daily cap is already hit."""
    limit = int(settings["pro_daily_limit"] if mode == PRO else settings["essentials_daily_limit"])
    field = "pro" if mode == PRO else "essentials"
    day = business_date(now_utc()).isoformat()
    store = getattr(db, "routes_budget", None)
    if store is None:
        return True
    try:
        doc = await store.find_one_and_update(
            {"_id": day},
            {"$inc": {field: 1}, "$setOnInsert": {"date": day}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except Exception as exc:
        logger.warning("[MAPS] route budget counter failed open: %s", exc)
        return True
    used = int((doc or {}).get(field) or 0)
    if used <= limit:
        return True
    try:
        await store.update_one({"_id": day}, {"$inc": {field: -1}})
    except Exception:
        pass
    if day + field not in _LOGGED_BUDGET:
        _LOGGED_BUDGET.add(day + field)
        logger.warning(
            "[MAPS] daily %s Routes limit of %s is reached; using the mileage estimate",
            field, limit,
        )
    return False


async def routes_budget_snapshot() -> dict:
    settings = await load_drive_settings()
    day = business_date(now_utc()).isoformat()
    doc = {}
    store = getattr(db, "routes_budget", None)
    if store is not None:
        try:
            doc = await store.find_one({"_id": day}) or {}
        except Exception:
            doc = {}
    return {
        "date": day,
        "pro": int(doc.get("pro") or 0),
        "essentials": int(doc.get("essentials") or 0),
        "pro_limit": int(settings["pro_daily_limit"]),
        "essentials_limit": int(settings["essentials_daily_limit"]),
        "pro_cutoff": settings["pro_cutoff"],
        "rush_multiplier": settings["rush_multiplier"],
        "rush_morning_start": settings["rush_morning_start"],
        "rush_morning_end": settings["rush_morning_end"],
        "rush_evening_start": settings["rush_evening_start"],
        "rush_evening_end": settings["rush_evening_end"],
    }


async def get_drive_time(
    o_lat, o_lng, d_lat, d_lng,
    depart_at: datetime | None = None,
    *,
    mode: str = PRO,
    appointment_day: date | None = None,
    settings: dict | None = None,
) -> dict:
    """One leg. Pro uses TRAFFIC_AWARE and a departure. Essentials does not send one.

    Essentials minutes are multiplied for Phoenix rush hour. A missing key, a
    past Pro departure, a failed call, or a full daily budget uses the mileage
    estimate and logs the reason.
    """
    if (o_lat, o_lng) == (d_lat, d_lng):
        return {"distance_miles": 0.0, "duration_minutes": 0}
    settings = settings or default_drive_settings()
    estimate = mock_distance_matrix(o_lat, o_lng, d_lat, d_lng)
    if not google_maps_enabled():
        _log_drive_fallback("no-key")
        return estimate
    preference = "TRAFFIC_AWARE" if mode == PRO else "TRAFFIC_UNAWARE"
    depart = None
    departure_iso = None
    if mode == PRO:
        depart = _departure_for_routes(depart_at)
        if depart is None:
            _log_drive_fallback("departure is not in the future")
            return estimate
        departure_iso = depart.strftime("%Y-%m-%dT%H:%M:%SZ")
        bucket = departure_bucket(depart)
    else:
        bucket = None
    key = drive_time_cache_key(
        o_lat, o_lng, d_lat, d_lng,
        (appointment_day or business_date(depart_at or now_utc())).isoformat(),
        bucket,
    )
    key = f"{key}|{mode}"

    async def _load():
        cache = getattr(db, "drive_time_cache", None)
        cached = None
        if cache is not None:
            try:
                cached = await cache.find_one({"_id": key})
            except Exception as exc:
                logger.warning("[MAPS] drive-time cache read failed, calling Routes: %s", exc)
        if cached and _cache_is_fresh(cached):
            minutes = int(cached["duration_minutes"])
            if mode == ESSENTIALS:
                minutes = apply_rush(minutes, depart_at, settings)
            return {"distance_miles": cached["distance_miles"], "duration_minutes": minutes}
        if not await _routes_budget_allows(mode, settings):
            return estimate
        try:
            data = await asyncio.to_thread(
                _google_routes_request, o_lat, o_lng, d_lat, d_lng, departure_iso, preference,
            )
            result = parse_routes_response(data)
            expires = now_utc() + timedelta(seconds=cache_ttl_seconds(mode, now_utc(), appointment_day))
            if cache is not None:
                try:
                    await cache.update_one(
                        {"_id": key},
                        {"$set": {
                            **result, "cached_at": now_utc(), "expires_at": expires,
                            "mode": mode, "departure_bucket": bucket,
                        }},
                        upsert=True,
                    )
                except Exception as exc:
                    logger.warning("[MAPS] drive-time cache write failed: %s", exc)
            if mode == ESSENTIALS:
                result = {
                    **result,
                    "duration_minutes": apply_rush(result["duration_minutes"], depart_at, settings),
                }
            return result
        except (GoogleMapsError, requests.RequestException, KeyError, IndexError, ValueError) as exc:
            _log_drive_fallback(str(exc))
            return estimate

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
    address_confirmed: bool = False
    confirmed_address: Optional[str] = None
    acknowledge_duplicate: bool = False
    place_id: Optional[str] = None

class ShopUpdate(ShopIn):
    status: Optional[Literal["active", "paused", "inactive", "suspended"]] = None

class SlotQuery(BaseModel):
    booking_token: str
    job_address: str
    date: str  # YYYY-MM-DD

class BookingIn(BaseModel):
    booking_token: str
    job_address: str
    scheduled_start: str  # ISO datetime
    customer_last_name: str
    customer_first_name: Optional[str] = Field(default=None, max_length=80)
    notes: Optional[str] = Field(default=None, max_length=4000)
    year: int
    make: str
    model: str
    trim: Optional[str] = None
    vin: Optional[str] = None
    adas_system: Literal["forward_camera", "surround_view", "radar", "multi_camera", "tesla", "other"]
    calibration_type: Literal["static", "dynamic", "dual", "triple", "tesla"]
    notification_phone: Optional[str] = None
    notification_email: Optional[str] = None
    invoice_instead: bool = False

class JobEditIn(BaseModel):
    job_address: Optional[str] = None
    customer_first_name: Optional[str] = None
    customer_last_name: Optional[str] = None
    notification_phone: Optional[str] = None
    notification_email: Optional[str] = None
    vehicle_year: Optional[int] = None
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_vin: Optional[str] = None
    calibration_type: Optional[Literal["static", "dynamic", "dual", "triple", "tesla"]] = None
    price: Optional[float] = None
    scheduled_start: Optional[str] = None
    zone: Optional[Literal["west", "east"]] = None
    notes: Optional[str] = None

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

class RoutingTechIn(BaseModel):
    name: str
    phone: Optional[str] = None
    home_address: str
    service_radius_miles: Optional[float] = None
    day_start: str = "08:00"
    day_end: str = "19:00"
    slot_minutes: int = 45
    max_jobs: int = 14
    job_duration_minutes: int = 20
    buffer_minutes: int = 15
    same_day_bookings_enabled: bool = True
    same_day_cutoff: str = "13:00"
    same_day_max_extra_drive_minutes: int = 20
    same_day_max_later_finish_minutes: int = 45
    same_day_over_limit: Literal["pending", "hide"] = "pending"

class RoutingTechUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    home_address: Optional[str] = None
    service_radius_miles: Optional[float] = None
    clear_service_radius: bool = False
    day_start: Optional[str] = None
    day_end: Optional[str] = None
    slot_minutes: Optional[int] = None
    max_jobs: Optional[int] = None
    is_active: Optional[bool] = None
    routes_jobs: Optional[bool] = None
    job_duration_minutes: Optional[int] = None
    buffer_minutes: Optional[int] = None
    same_day_bookings_enabled: Optional[bool] = None
    same_day_cutoff: Optional[str] = None
    same_day_max_extra_drive_minutes: Optional[int] = None
    same_day_max_later_finish_minutes: Optional[int] = None
    same_day_over_limit: Optional[Literal["pending", "hide"]] = None

class ReorderIn(BaseModel):
    zone: Optional[Literal["west", "east"]] = None
    technician_id: Optional[str] = None
    date: str  # YYYY-MM-DD
    ordered_job_ids: List[str]

class PricingUpdate(BaseModel):
    static: Optional[float] = None
    dynamic: Optional[float] = None
    dual: Optional[float] = None
    triple: Optional[float] = None
    tesla: Optional[float] = None

class DriveSettingsIn(BaseModel):
    pro_cutoff: Optional[str] = None
    rush_multiplier: Optional[float] = None
    rush_morning_start: Optional[str] = None
    rush_morning_end: Optional[str] = None
    rush_evening_start: Optional[str] = None
    rush_evening_end: Optional[str] = None
    pro_daily_limit: Optional[int] = None
    essentials_daily_limit: Optional[int] = None

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

class ShopRequestIn(BaseModel):
    shop_name: str
    contact_name: str
    mobile: str
    email: str
    address: str
    address_confirmed: bool = False
    confirmed_address: Optional[str] = None
    place_id: Optional[str] = None


class PublicShopIn(BaseModel):
    shop_name: str = Field(max_length=160)
    contact_name: str = Field(max_length=160)
    mobile: str = Field(max_length=32)
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)
    address: str = Field(max_length=300)
    address_confirmed: bool = False
    confirmed_address: Optional[str] = Field(default=None, max_length=300)
    place_id: Optional[str] = Field(default=None, max_length=200)
    terms_signature: str = Field(max_length=160)
    terms_agreed: bool = False
    charge_accepted: bool = False
    second_location: bool = False
    payment_method_id: Optional[str] = Field(default=None, max_length=80)


class SetupIntentCompleteIn(BaseModel):
    setup_intent_id: str = Field(max_length=80)


class ShopFlagIn(BaseModel):
    flagged: bool = True


class ShopSuspendIn(BaseModel):
    suspended: bool = True

class ContactIn(BaseModel):
    shop_name: Optional[str] = None
    name: str
    email: str
    phone: Optional[str] = None
    message: str

class PaymentModeIn(BaseModel):
    mode: Literal["charge_on_completion", "invoice_hold"]

class TripFeeIn(BaseModel):
    reason: Literal["bad_install", "customer_vehicle"]

class OutsideAreaIn(BaseModel):
    enabled: bool = True

class ForgotPasswordIn(BaseModel):
    email: EmailStr

class ResetPasswordIn(BaseModel):
    token: str
    password: str

class PaymentMethodIn(BaseModel):
    payment_method_id: str

class AcceptChargeIn(BaseModel):
    accepted: bool = False

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
    try:
        geo = await geocode_address(addr)
    except AddressNotFound as exc:
        raise HTTPException(400, str(exc))
    refusal = pin_refusal(geo)
    if refusal:
        raise HTTPException(400, refusal)
    zone = detect_zone(geo["lng"]) if geo["in_metro"] else None
    return {**geo, "zone": zone}


def _regeocode_counts(result: dict) -> dict:
    return {k: result[k] for k in ("updated", "unchanged", "skipped", "failed")}


@api.post("/admin/regeocode")
async def admin_regeocode(date: Optional[str] = None, tech=Depends(require_owner)):
    """Re-geocode stored pins.

    Omit `date` to refresh every shop and every job. Pass `date=YYYY-MM-DD` to
    refresh only jobs scheduled on that America/Phoenix day (shops are skipped).
    Writes coordinates and zone. Does not change status and does not send SMS or email.
    A Google failure leaves that record unchanged (`failed`). No key uses the mock.
    """
    try:
        scope = regeocode_scope(date)
    except ValueError:
        raise HTTPException(400, "Invalid date. Use YYYY-MM-DD.")

    shop_result = None
    if scope["shops"]:
        shops = await db.shops.find({}, {"_id": 0}).to_list(5000)
        shop_result = await regeocode_records(
            shops, geocode_for_regeocode, "lat", "lng", "address", zone_for_geocode,
        )
    if scope["jobs"] == "all":
        jobs = await db.jobs.find({}, {"_id": 0}).to_list(20000)
    else:
        jobs = await db.jobs.find(jobs_on_phoenix_day(scope["day"]), {"_id": 0}).to_list(20000)
    job_result = await regeocode_records(
        jobs, geocode_for_regeocode, "job_lat", "job_lng", "job_address", zone_for_geocode,
    )

    stamp = iso(now_utc())
    if shop_result:
        for change in shop_result["changes"]:
            await db.shops.update_one(
                {"id": change["id"]}, {"$set": location_set(change["set"], stamp)},
            )
    for change in job_result["changes"]:
        await db.jobs.update_one(
            {"id": change["id"]}, {"$set": location_set(change["set"], stamp)},
        )
    return {
        "date": scope["day"].isoformat() if scope["day"] else None,
        "shops": _regeocode_counts(shop_result) if shop_result else None,
        "jobs": _regeocode_counts(job_result),
    }

# ---------- Shops ----------
@api.get("/shops")
async def list_shops(tech=Depends(require_owner)):
    shops = await db.shops.find({}, {"_id": 0}).to_list(1000)
    return shops

async def _duplicate_lists():
    shops = await db.shops.find({}, {"_id": 0, "id": 1, "name": 1, "contact_email": 1}).to_list(5000)
    users_col = getattr(db, "shop_users", None)
    users = []
    if users_col is not None:
        users = await users_col.find({}, {"_id": 0, "shop_id": 1, "email": 1}).to_list(5000)
    return shops, users


async def _checked_shop_address(
    address: str, confirmed: bool, confirmed_address: Optional[str], place_id: Optional[str] = None,
) -> dict:
    try:
        geo = await geocode_address(address)
    except AddressNotFound as exc:
        raise HTTPException(400, str(exc))
    _refuse_unusable_pin(geo)
    problem = address_problem(geo)
    if problem:
        raise HTTPException(400, problem)
    if address_needs_confirmation(
        place_id=place_id, confirmed=confirmed, confirmed_address=confirmed_address, geo=geo,
    ):
        raise HTTPException(status_code=409, detail={
            "code": "needs_confirmation",
            "message": "Confirm the address we found before saving.",
            "formatted_address": geo.get("formatted_address"),
            "lat": geo.get("lat"),
            "lng": geo.get("lng"),
            "in_metro": True,
            "zone": detect_zone(geo["lng"]),
        })
    return geo


def _raise_if_duplicates(name, email, shops, users, acknowledge: bool, ignore_shop_id=None):
    dupes = duplicate_fields(name, email, shops, users, ignore_shop_id=ignore_shop_id)
    if dupes and not acknowledge:
        label = " and ".join(dupes)
        raise HTTPException(status_code=409, detail={
            "code": "duplicate",
            "duplicates": dupes,
            "message": f"A shop with this {label} is already on file. Save anyway only if that is intentional.",
        })


def _shop_document(data: ShopIn, geo: dict) -> dict:
    payload = data.model_dump()
    payload.pop("address_confirmed", None)
    payload.pop("confirmed_address", None)
    payload.pop("acknowledge_duplicate", None)
    payload.pop("terms_signed_by", None)
    payload["name"] = data.name.strip()
    payload["contact_phone"] = normalize_phone(data.contact_phone)
    payload["contact_email"] = canonical_email(data.contact_email)
    payload["address"] = geo.get("formatted_address") or data.address.strip()
    payload["formatted_address"] = geo.get("formatted_address")
    return {
        "id": gen_id(),
        **payload,
        "lat": geo["lat"], "lng": geo["lng"],
        "geocode_source": geo.get("source") or ("google" if google_maps_enabled() else "mock"),
        "zone": detect_zone(geo["lng"]),
        "booking_link_token": secrets.token_hex(16),
        "terms_signed_at": None,
        "terms_signed_by": None,
        "requires_billing_setup": True,
        "status": "active",
        "created_at": iso(now_utc()),
        "updated_at": iso(now_utc()),
    }


@api.post("/shops")
async def create_shop(data: ShopIn, tech=Depends(require_owner)):
    geo = await _checked_shop_address(
        data.address, data.address_confirmed, data.confirmed_address, data.place_id,
    )
    errors = shop_contact_errors(
        name=data.name, phone=data.contact_phone, email=data.contact_email, address=data.address,
    )
    if errors:
        raise HTTPException(400, errors)
    shops, users = await _duplicate_lists()
    _raise_if_duplicates(data.name, data.contact_email, shops, users, data.acknowledge_duplicate)
    shop = _shop_document(data, geo)
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
    for flag in ("address_confirmed", "confirmed_address", "acknowledge_duplicate", "terms_signed_by"):
        update.pop(flag, None)
    if "contact_phone" in update:
        phone = normalize_phone(update.get("contact_phone"))
        if not phone:
            raise HTTPException(400, "Enter a 10-digit mobile number.")
        update["contact_phone"] = phone
    if "contact_email" in update:
        email = canonical_email(update.get("contact_email"))
        if not email:
            raise HTTPException(400, "Enter a valid email.")
        update["contact_email"] = email
    if "address" in update and (update["address"] or "").strip() != (shop.get("address") or "").strip():
        try:
            geo = await geocode_for_regeocode(update["address"])
        except (GoogleMapsError, requests.RequestException, AddressNotFound):
            raise HTTPException(400, ADDRESS_NOT_FOUND)
        _refuse_unusable_pin(geo)
        update["lat"] = geo["lat"]
        update["lng"] = geo["lng"]
        update["formatted_address"] = geo.get("formatted_address") or update["address"]
        update["address"] = update["formatted_address"]
        update["geocode_source"] = geo.get("source") or "google"
        zone = zone_for_geocode(geo)
        if zone:
            update["zone"] = zone
    shops, users = await _duplicate_lists()
    _raise_if_duplicates(
        update.get("name", shop.get("name")),
        update.get("contact_email", shop.get("contact_email")),
        shops, users, data.acknowledge_duplicate, ignore_shop_id=shop_id,
    )
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
async def _booking_gate_for_shop(shop: dict) -> dict:
    users_col = getattr(db, "shop_users", None)
    user = None
    if users_col is not None and shop.get("id"):
        user = await users_col.find_one({"shop_id": shop["id"]}, {"_id": 0})
    return booking_gate(shop, user)


@api.get("/public/shop/{token}")
async def public_shop(token: str):
    shop = await db.shops.find_one({"booking_link_token": token},
                                   {"_id": 0, "custom_rate_static": 1, "custom_rate_dynamic": 1,
                                    "custom_rate_dual": 1, "custom_rate_triple": 1, "custom_rate_tesla": 1,
                                    "pricing_tier": 1, "name": 1, "address": 1, "contact_phone": 1,
                                    "contact_email": 1, "id": 1, "booking_link_token": 1, "zone": 1,
                                    "requires_billing_setup": 1, "status": 1, "lat": 1, "lng": 1,
                                    "formatted_address": 1, "geocode_source": 1})
    if not shop or shop.get("status") not in ("active", "suspended"):
        raise HTTPException(404, "This booking link is not active. Contact The Calibration Crew.")
    gate = await _booking_gate_for_shop(shop)
    return {**shop, "booking_open": gate["allowed"], "booking_message": gate["message"]}

def shop_price_for(shop: dict, cal_type: str) -> float:
    if shop.get("pricing_tier") == "custom":
        custom = shop.get(f"custom_rate_{cal_type}")
        if custom is not None:
            return float(custom)
    return float(STANDARD_PRICING[cal_type]["price"])

def parse_time_str(t: str) -> time:
    h, m = t.split(":")
    return time(int(h), int(m))

def _round_up_quarter_hour(moment: datetime) -> datetime:
    minute = (moment.minute // 15) * 15
    if moment.minute % 15 != 0 or moment.second > 0 or moment.microsecond > 0:
        minute += 15
    if minute >= 60:
        return moment.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return moment.replace(minute=minute, second=0, microsecond=0)


async def load_routing_techs():
    """Active owners and hired technicians with a home base. Contractors are excluded."""
    people = await db.technicians.find({}, {"_id": 0, "password_hash": 0}).to_list(100)
    return [person for person in people if is_routing_tech(person)]


async def _assigned_tech(lat: float, lng: float):
    chosen = assign_technician(await load_routing_techs(), lat, lng)
    if chosen:
        return chosen
    return await db.technicians.find_one({"role": "owner"}, {"_id": 0, "password_hash": 0})


def _tech_home(tech: dict | None) -> tuple:
    if tech and tech.get("home_lat") is not None and tech.get("home_lng") is not None:
        return (tech["home_lat"], tech["home_lng"])
    return (CALEB_HOME["lat"], CALEB_HOME["lng"])


async def _drive_lookup(queries: list, *, mode: str, same_day: bool, home, appointment_day: date, settings: dict):
    """Minutes for the collapsed legs. Essentials results pick up the rush multiplier per departure."""
    unique = collapse_queries(queries, mode=mode, same_day=same_day, home=home)
    sem = asyncio.Semaphore(8)

    async def one(item):
        origin, dest, depart, signature = item
        async with sem:
            if (origin[0], origin[1]) == (dest[0], dest[1]):
                return signature, 0
            dm = await get_drive_time(
                origin[0], origin[1], dest[0], dest[1],
                depart_at=depart, mode=mode, appointment_day=appointment_day, settings=settings,
            )
            minutes = dm["duration_minutes"]
            # get_drive_time already applies rush for Essentials. Store the raw-to-caller number
            # for Pro, and the unmultiplied API minutes are not available. Re-apply would double.
            # For Essentials the table holds the multiplied value of the prefetch departure.
            # Lookups at a different rush band recompute below from a stored base when present.
            return signature, minutes

    rows = await asyncio.gather(*(one(item) for item in unique)) if unique else []
    table = dict(rows)

    def drive(origin, dest, depart=None):
        if not origin or not dest or origin[0] is None or dest[0] is None:
            return 0
        if (origin[0], origin[1]) == (dest[0], dest[1]):
            return 0
        signature = leg_signature(origin, dest, depart, mode=mode, same_day=same_day, home=home)
        if signature not in table:
            estimate = mock_distance_matrix(origin[0], origin[1], dest[0], dest[1])["duration_minutes"]
            if mode == ESSENTIALS:
                return apply_rush(estimate, depart, settings)
            return estimate
        got = table[signature]
        if mode != ESSENTIALS:
            return got
        # Prefetch stored the rushed minutes for its own departure. Scale back to the
        # base, then apply the rush factor for the departure the slot actually uses.
        base_depart = None
        for origin_q, dest_q, depart_q, sig in unique:
            if sig == signature:
                base_depart = depart_q
                break
        base_factor = apply_rush(100, base_depart, settings) / 100 if base_depart is not None else 1
        raw = got / base_factor if base_factor else got
        return apply_rush(int(round(raw)), depart, settings)

    return drive


async def _route_jobs(tech_id: str, day: date, ignore_job_id: str | None = None):
    day_start, day_end = business_day_bounds(day)
    found = await db.jobs.find({
        "technician_id": tech_id,
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(day_end)},
        "status": {"$nin": ["cancelled", "declined"]},
    }, {"_id": 0}).to_list(200)
    if ignore_job_id:
        found = [job for job in found if job.get("id") != ignore_job_id]
    return found


def _live_anchor(tech: dict | None, now: datetime):
    """Where the technician is, when a fresh live position is stored. Not a saved job."""
    if not tech or tech.get("live_lat") is None or tech.get("live_lng") is None or not tech.get("live_at"):
        return None
    try:
        seen = datetime.fromisoformat(str(tech["live_at"]).replace("Z", "+00:00"))
    except ValueError:
        return None
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    if abs((now - seen.astimezone(timezone.utc)).total_seconds()) > 45 * 60:
        return None
    return {
        "id": f"live-{tech.get('id')}",
        "job_lat": tech["live_lat"],
        "job_lng": tech["live_lng"],
        "scheduled_start": iso(now),
        "scheduled_end": iso(now),
        "duration_minutes": 0,
        "status": "booked",
    }


def _clocks_for(day: date, schedule: dict, now: datetime, kind: str) -> dict:
    """Public grid, leave-home time, and the early-arrival waiver.

    Advance days offer 6:00 AM–5:00 PM. Leaving home for a normal first stop
    is still the technician's day start (default 8:00). Arrivals before 8:00
    skip that wait. Same-day offers start at the next grid time from now, and
    the drive leaves from now once the normal day has started.
    """
    early_start, offer_end = zone_window(day, time(6, 0), time(17, 0))
    auto_at, _ignored = zone_window(day, time(8, 0), time(17, 0))
    home_leave, _end = zone_window(day, parse_time_str(schedule["day_start"]), time(17, 0))
    if kind == "same_day":
        grid_start = max(early_start, round_up(now))
        if now > home_leave:
            home_leave = now
        # Same-day first stops before 8:00 still skip the home-drive check.
        waive = auto_at
        home_floor = None
    else:
        grid_start = early_start
        waive = None
        # Future day: the technician may leave home at 6:00 AM. A first stop
        # is legal when arrival minus the drive is still at or after 6:00.
        home_floor = early_start
    return {
        "grid_start": grid_start,
        "day_start": home_leave,
        "offer_end": offer_end,
        "earliest_public": early_start,
        "waive_home_drive_before": waive,
        "earliest_home_departure": home_floor,
        "home_ready": home_leave,
    }


async def load_days_off() -> list:
    store = getattr(db, "days_off", None)
    if store is None:
        return []
    try:
        return await store.find({}, {"_id": 0}).to_list(500)
    except Exception as exc:
        logger.warning("days off unreadable: %s", exc)
        return []


def _dates_between(start: date, end: date) -> list:
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


async def flag_jobs_on_dates(days: list, label: str) -> list:
    """Mark jobs already booked on a newly closed day. Does not cancel them."""
    jobs_store = getattr(db, "jobs", None)
    if jobs_store is None or not days:
        return []
    found = []
    for day in days:
        start, end = business_day_bounds(day)
        try:
            rows = await jobs_store.find({
                "scheduled_start": {"$gte": iso(start), "$lt": iso(end)},
                "status": {"$nin": ["cancelled", "declined", "complete"]},
            }, {"_id": 0}).to_list(500)
        except Exception as exc:
            logger.warning("could not list jobs for %s: %s", day, exc)
            continue
        for job in jobs_to_flag(rows, {day}):
            await jobs_store.update_one({"id": job["id"]}, {"$set": {
                "day_off_conflict": True,
                "day_off_label": label,
                "updated_at": iso(now_utc()),
            }})
            found.append(job)
    return found


async def clear_day_off_flags(days: list) -> None:
    """Drop the flag once every closure covering that Phoenix day is open again."""
    jobs_store = getattr(db, "jobs", None)
    if jobs_store is None:
        return
    records = await load_days_off()
    for day in days:
        if closure_message(day, records):
            continue
        start, end = business_day_bounds(day)
        try:
            rows = await jobs_store.find({
                "scheduled_start": {"$gte": iso(start), "$lt": iso(end)},
                "day_off_conflict": True,
            }, {"_id": 0}).to_list(500)
        except Exception as exc:
            logger.warning("could not clear day-off flags for %s: %s", day, exc)
            continue
        for job in rows:
            await jobs_store.update_one({"id": job["id"]}, {"$set": {
                "day_off_conflict": False,
                "day_off_label": None,
                "updated_at": iso(now_utc()),
            }})


async def ensure_holidays() -> None:
    """Insert this year and next year's holidays the first time we see each one.

    An existing row keeps the owner's blocked flag. A new closed holiday flags
    jobs already on that date and does not cancel them.
    """
    store = getattr(db, "days_off", None)
    if store is None:
        return
    year = business_date().year
    for row in holiday_records(year) + holiday_records(year + 1):
        try:
            existing = await store.find_one({"key": row["key"]})
        except Exception as exc:
            logger.warning("days off unreadable: %s", exc)
            return
        if existing:
            continue
        await store.insert_one(dict(row))
        await flag_jobs_on_dates([date.fromisoformat(row["start"])], row["label"])


async def closed_day_message(day: date) -> str | None:
    """Sunday, a blocked holiday, or a vacation. None when the day can be booked."""
    if day.weekday() == 6:
        return "No availability on Sundays."
    await ensure_holidays()
    return closure_message(day, await load_days_off())


def _job_when(job: dict) -> datetime:
    raw = str(job.get("scheduled_start") or "")
    try:
        instant = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return now_utc()
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


def _vehicle_line(job: dict) -> str:
    return " ".join(
        str(job.get(key) or "").strip()
        for key in ("vehicle_year", "vehicle_make", "vehicle_model")
    ).strip()


def _shop_email(job: dict | None, shop: dict | None) -> str | None:
    for value in (
        (job or {}).get("notification_email"),
        (shop or {}).get("contact_email"),
    ):
        if value and "@" in str(value):
            return str(value).strip()
    return None


async def _hold_booking_message(message: dict, audience: str) -> dict:
    """Save a shop or owner email that must not be sent. Does not call Resend."""
    doc = {
        "id": gen_id(),
        "to": message["to"],
        "subject": message["subject"],
        "body": message.get("html") or "",
        "created_at": iso(now_utc()),
        "audience": audience,
        "kind": message.get("kind") or "transactional",
        "reply_to": message.get("reply_to"),
        "delivered": False,
    }
    store = getattr(db, "email_outbox", None)
    if store is not None:
        try:
            await store.insert_one(dict(doc))
        except Exception as exc:
            logger.warning("email outbox write failed: %s", exc)
    else:
        logger.info("[EMAIL HELD → %s] %s", message["to"], message["subject"])
    return doc


async def _send_booking_message(message: dict | None, audience: str = "shop"):
    """Send or hold one booking email.

    audience is 'shop' or 'owner'. Shop mail is held while SHOP_EMAILS_ENABLED
    is false, and that path never calls send_email or Resend.
    """
    if not message or not (message.get("to") or "").strip():
        return None
    if mail_route(audience, message.get("kind"), message.get("to")) == "hold":
        return await _hold_booking_message(message, audience)
    return await send_email(
        message["to"], message["subject"], message["html"],
        kind=message.get("kind") or "transactional",
        meta=message.get("meta"),
        reply_to=message.get("reply_to"),
    )


async def email_shop_confirmation(job: dict, shop: dict | None, pending: bool):
    message = booking_confirmation_email(
        to=_shop_email(job, shop) or "",
        reply_to=SEED_OWNER_EMAIL,
        when=_job_when(job),
        vehicle=_vehicle_line(job),
        address=job.get("job_address") or "",
        calibration=job.get("calibration_label") or job.get("calibration_type") or "",
        price=job.get("price") or 0,
        pending=pending,
    )
    message["meta"] = {"job_id": job.get("id")}
    return await _send_booking_message(message, audience="shop")


async def _issue_owner_link(job_id: str, action: str) -> dict:
    minted = mint_owner_link(secret=JWT_SECRET, job_id=job_id, action=action, now=now_utc())
    store = getattr(db, "owner_action_tokens", None)
    if store is not None:
        try:
            await store.insert_one(dict(minted["record"]))
        except Exception as exc:
            logger.warning("owner link not stored: %s", exc)
    return minted


async def email_owner_alert(job: dict, shop: dict | None, pending: bool, same_day: bool):
    approve = await _issue_owner_link(job["id"], "approve")
    decline = await _issue_owner_link(job["id"], "decline")
    message = owner_alert_email(
        to=SEED_OWNER_EMAIL,
        reply_to=SEED_OWNER_EMAIL,
        when=_job_when(job),
        shop_name=(shop or {}).get("name") or job.get("shop_name") or "Shop",
        vehicle=_vehicle_line(job),
        address=job.get("job_address") or "",
        calibration=job.get("calibration_label") or "",
        price=job.get("price") or 0,
        pending=pending,
        same_day=same_day,
        approve_url=f"{PUBLIC_SITE_URL}/owner-action/{approve['token']}",
        decline_url=f"{PUBLIC_SITE_URL}/owner-action/{decline['token']}",
    )
    message["meta"] = {"job_id": job.get("id")}
    return await _send_booking_message(message, audience="owner")


async def email_shop_event(job: dict, shop: dict | None, event: str):
    message = shop_event_email(
        to=_shop_email(job, shop) or "",
        reply_to=SEED_OWNER_EMAIL,
        event=event,
        when=_job_when(job),
        vehicle=_vehicle_line(job),
        address=job.get("job_address") or "",
        calibration=job.get("calibration_label") or "",
        price=job.get("price") or 0,
    )
    message["meta"] = {"job_id": job.get("id"), "event": event}
    return await _send_booking_message(message, audience="shop")


async def _shop_for_job(job: dict) -> dict | None:
    shops = getattr(db, "shops", None)
    if shops is None or not job.get("shop_id"):
        return None
    try:
        return await shops.find_one({"id": job["shop_id"]}, {"_id": 0})
    except Exception as exc:
        logger.warning("shop lookup failed: %s", exc)
        return None


async def notify_booking_approval(job: dict, event: str) -> None:
    """Email the shop when the owner approves or declines. Does not text."""
    if event in ("approved", "declined"):
        await email_shop_event(job, await _shop_for_job(job), event)
    logger.info(
        "[NOTIFY] booking %s job=%s status=%s kind=%s reason=%s",
        event, job.get("id"), job.get("status"), job.get("booking_kind"), job.get("approval_reason"),
    )


def _too_far_message(extra: int, later: int) -> str:
    return (
        "That time doesn't fit today's route. "
        f"It adds about {extra} minutes of driving and would finish about {later} minutes later."
    )


def _aware_start(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _route_context(tech, day: date, new_point: tuple, jobs: list, now: datetime, duration: int | None = None, slot: datetime | None = None):
    """Drive table and clock window for one address on one technician's day.

    `slot` is set for a book or an edit. Only the legs that touch that arrival
    are fetched. Availability leaves it empty and walks the day, collapsed.
    """
    schedule = tech_schedule(tech)
    kind = request_kind(day, now)
    clocks = _clocks_for(day, schedule, now, kind)
    anchor = _live_anchor(tech, now) if kind == "same_day" else None
    had_route = bool(jobs) or anchor is not None
    planned = list(jobs)
    if anchor:
        planned = planned + [anchor]
    duration = schedule["job_duration_minutes"] if duration is None else int(duration)
    buffer = schedule["buffer_minutes"]
    home = _tech_home(tech)
    settings = await load_drive_settings()
    mode = routing_mode(day, now, settings["pro_cutoff"])
    same_day = kind == "same_day"
    if slot is not None:
        queries = slot_touching_queries(
            start=slot, day_start=clocks["day_start"], home=home, jobs=planned,
            new_point=new_point, duration=duration, buffer=buffer,
            earliest_home_departure=clocks["earliest_home_departure"],
        )
    else:
        queries = annotated_drive_queries(
            day_start=clocks["day_start"], offer_end=clocks["offer_end"], home=home,
            jobs=planned, new_point=new_point, duration=duration, buffer=buffer,
            grid_start=clocks["grid_start"], home_ready=clocks["home_ready"],
            earliest_home_departure=clocks["earliest_home_departure"],
        )
    drive = await _drive_lookup(
        queries, mode=mode, same_day=same_day, home=home,
        appointment_day=day, settings=settings,
    )
    return {
        "schedule": schedule, "kind": kind, "clocks": clocks, "had_route": had_route,
        "jobs": planned, "duration": duration, "buffer": buffer, "drive": drive,
        "home": home, "policy": policy_from_tech(tech), "new_point": new_point,
    }


def _decide_one(ctx: dict, start: datetime, *, allow_outside: bool) -> dict | None:
    """None when the slot must not be offered. Otherwise status and approval fields."""
    start = _aware_start(start)
    clocks = ctx["clocks"]
    message = placement_error(
        start=start, duration=ctx["duration"], buffer=ctx["buffer"],
        day_start=clocks["day_start"], offer_end=clocks["offer_end"], home=ctx["home"],
        jobs=ctx["jobs"], new_point=ctx["new_point"], drive=ctx["drive"],
        allow_after_offer_end=allow_outside,
        earliest_public=clocks["earliest_public"],
        waive_home_drive_before=clocks["waive_home_drive_before"],
        earliest_home_departure=clocks["earliest_home_departure"],
    )
    if message:
        return {"error": message}
    cost = insertion_cost(
        start=start, duration=ctx["duration"], buffer=ctx["buffer"],
        home=ctx["home"], home_ready=clocks["home_ready"], jobs=ctx["jobs"],
        new_point=ctx["new_point"], drive=ctx["drive"],
    )
    had_route = ctx["had_route"] and not cost["empty_route"]
    decision = slot_decision(
        band=arrival_band(start), kind=ctx["kind"], had_route=had_route,
        extra=cost["extra_drive_minutes"], later=cost["later_finish_minutes"],
        policy=ctx["policy"], allow_outside=allow_outside,
    )
    if decision is None:
        return {
            "error": _too_far_message(cost["extra_drive_minutes"], cost["later_finish_minutes"]),
            "hidden": True,
        }
    booking_kind = "addon" if ctx["kind"] == "same_day" else "standard"
    return {
        "error": None,
        "status": decision["status"],
        "requires_approval": decision["requires_approval"],
        "approval_reason": decision["approval_reason"],
        "booking_kind": booking_kind,
        "drive_time_minutes": cost["to_stop_minutes"],
        "extra_drive_minutes": cost["extra_drive_minutes"] if had_route else None,
        "later_finish_minutes": cost["later_finish_minutes"] if had_route else None,
    }


async def compute_available_slots(zone_key: str, day: date, job_lat: float, job_lng: float, tech: dict = None, now: datetime = None):
    """Open arrivals on one technician's route, including gaps between jobs.

    `zone_key` is ignored. East/West no longer has its own clock.
    Returns (slots, message, booking_kind).
    """
    del zone_key
    now = now or now_utc()
    kind = request_kind(day, now)
    policy = policy_from_tech(tech)
    if kind == "same_day":
        closed = same_day_closed_message(now, policy)
        if closed:
            return [], closed, "addon"
    jobs = []
    if tech and tech.get("id"):
        jobs = await _route_jobs(tech["id"], day)
    ctx = await _route_context(tech, day, (job_lat, job_lng), jobs, now)
    raw = candidate_slots(
        day_start=ctx["clocks"]["day_start"], offer_end=ctx["clocks"]["offer_end"],
        home=ctx["home"], jobs=ctx["jobs"], new_point=ctx["new_point"], drive=ctx["drive"],
        duration=ctx["duration"], buffer=ctx["buffer"],
        grid_start=ctx["clocks"]["grid_start"],
        earliest_public=ctx["clocks"]["earliest_public"],
        waive_home_drive_before=ctx["clocks"]["waive_home_drive_before"],
        earliest_home_departure=ctx["clocks"]["earliest_home_departure"],
    )
    slots = []
    hidden = 0
    for slot in raw:
        start = datetime.fromisoformat(slot["start"])
        decided = _decide_one(ctx, start, allow_outside=False)
        if decided.get("error"):
            if decided.get("hidden"):
                hidden += 1
            continue
        label = start.astimezone(BUSINESS_TZ).strftime("%-I:%M %p")
        slots.append({
            "start": slot["start"],
            "end": slot["end"],
            "drive_time_minutes": decided["drive_time_minutes"],
            "label": label,
            "requires_approval": decided["requires_approval"],
        })
    message = None
    if not slots and hidden:
        message = "No times left that fit today's route."
    return slots, message, "addon" if kind == "same_day" else "standard"


async def _arrival_plan(tech, day, start: datetime, new_point: tuple, jobs: list, *, allow_outside: bool, now: datetime = None, duration: int | None = None) -> dict:
    """Server-side recheck for a book or an edit. Raises 400 when the time does not fit."""
    now = now or now_utc()
    start = _aware_start(start)
    kind = request_kind(day, now)
    if kind == "past" and not allow_outside:
        raise HTTPException(400, "That date is in the past.")
    if kind == "same_day" and not allow_outside:
        closed = same_day_closed_message(now, policy_from_tech(tech))
        if closed:
            raise HTTPException(400, closed)
    ctx = await _route_context(tech, day, new_point, jobs, now, duration=duration, slot=start)
    decided = _decide_one(ctx, start, allow_outside=allow_outside)
    if decided.get("error"):
        raise HTTPException(400, decided["error"])
    decided["duration_minutes"] = ctx["duration"]
    return decided

async def _shop_for_booking_token(token: str) -> dict:
    """Active shop for a booking link. A suspended shop is a 403, not a missing link."""
    shop = await db.shops.find_one({"booking_link_token": token})
    if shop and shop.get("status") == "suspended":
        raise HTTPException(403, "This shop is suspended and cannot book.")
    if not shop or shop.get("status") != "active":
        raise HTTPException(404, "Invalid booking link")
    return shop


async def _pin_for_job(shop: dict, address: str) -> dict:
    """Reuse the shop's signup pin when the job is still at that address."""
    saved = reused_shop_pin(shop, address)
    if saved and not pin_refusal(saved):
        return saved
    try:
        return await geocode_address(address)
    except AddressNotFound as exc:
        raise HTTPException(400, str(exc))


@api.post("/public/availability")
async def public_availability(query: SlotQuery):
    try:
        shop = await _shop_for_booking_token(query.booking_token)
    except HTTPException as exc:
        if exc.status_code == 403:
            return {"zone": None, "in_metro": True, "slots": [], "booking_open": False,
                    "message": exc.detail if isinstance(exc.detail, str) else "This shop is suspended and cannot book."}
        raise
    gate = await _booking_gate_for_shop(shop)
    if not gate["allowed"]:
        return {"zone": None, "in_metro": True, "slots": [], "booking_open": False,
                "message": gate["message"]}
    geo = await _pin_for_job(shop, query.job_address)
    if not geo["in_metro"] or pin_refusal(geo):
        return {"zone": None, "in_metro": False, "slots": [],
                "message": OUTSIDE_VALLEY}
    zone = detect_zone(geo["lng"])
    # Parse date
    try:
        day = datetime.strptime(query.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date")
    # Validate: not Sunday, not a day off, not past, not > 21 days out.
    # "Today" is the Phoenix date.
    now = now_utc()
    today = business_date(now)
    closed = await closed_day_message(day)
    if closed:
        return {"zone": zone, "in_metro": True, "slots": [], "message": closed}
    if day < today:
        return {"zone": zone, "in_metro": True, "slots": [], "message": "That date is in the past."}
    if (day - today).days > 21:
        return {"zone": zone, "in_metro": True, "slots": [], "message": "Bookings are only available 21 days out."}
    # One technician covers every in-valley address. Extra technicians split by home base.
    # Today uses the stricter same-day limits. A later date stays on the advance rules.
    tech = await _assigned_tech(geo["lat"], geo["lng"])
    slots, closed_message, _kind = await compute_available_slots(
        zone, day, geo["lat"], geo["lng"], tech=tech, now=now,
    )
    payload = {
        "zone": zone, "in_metro": True, "slots": slots,
        "job_lat": geo["lat"], "job_lng": geo["lng"],
        "technician_id": tech.get("id") if tech else None,
        "technician_name": tech.get("name") if tech else None,
    }
    if not slots and closed_message:
        payload["message"] = closed_message
    return payload

@api.post("/public/book")
async def public_book(data: BookingIn):
    try:
        data.notification_phone = normalize_us_phone(data.notification_phone)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    shop = await _shop_for_booking_token(data.booking_token)
    gate = await _booking_gate_for_shop(shop)
    if not gate["allowed"]:
        raise HTTPException(403, gate["message"])
    geo = await _pin_for_job(shop, data.job_address)
    if not geo["in_metro"] or pin_refusal(geo):
        raise HTTPException(400, OUTSIDE_VALLEY)
    zone = detect_zone(geo["lng"])
    # Parse start
    try:
        start_dt = datetime.fromisoformat(data.scheduled_start.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "Invalid scheduled_start")
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    tech = await _assigned_tech(geo["lat"], geo["lng"])
    now = now_utc()
    route_day = business_date(start_dt)
    closed = await closed_day_message(route_day)
    if closed:
        raise HTTPException(400, closed)
    route_jobs = await _route_jobs(tech.get("id"), route_day) if tech and tech.get("id") else []
    plan = await _arrival_plan(
        tech, route_day, start_dt, (geo["lat"], geo["lng"]), route_jobs,
        allow_outside=False, now=now,
    )
    end_dt = start_dt + timedelta(minutes=plan["duration_minutes"])

    # Sequence follows this technician's day, not an East/West zone.
    day_start, day_end = business_day_bounds(route_day)
    tech_id = tech.get("id") if tech else None

    # Find owner technician (alerts still go to the owner, not a hired tech)
    owner = await db.technicians.find_one({"role": "owner"})

    customer = job_customer_fields(notes=data.notes, customer_first_name=data.customer_first_name)

    # Create vehicle
    vehicle = {
        "id": gen_id(), "year": data.year, "make": data.make, "model": data.model,
        "trim": data.trim, "vin": data.vin, "adas_system": data.adas_system,
        "shop_id": shop["id"], "customer_last_name": data.customer_last_name,
        "customer_first_name": customer["customer_first_name"],
        "created_at": iso(now_utc()),
    }
    await db.vehicles.insert_one(vehicle.copy())

    # Determine price from shop rate card
    price = shop_price_for(shop, data.calibration_type)

    # Sequence is this technician's jobs that Phoenix day, on either side of the valley.
    seq_query = {
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(day_end)},
        "status": {"$nin": ["cancelled", "declined"]},
    }
    if tech_id:
        seq_query["technician_id"] = tech_id
    seq_count = await db.jobs.count_documents(seq_query)

    job = {
        "id": gen_id(),
        "shop_id": shop["id"],
        "shop_name": shop["name"],  # denormalized for fast reads
        "vehicle_id": vehicle["id"],
        "technician_id": tech_id or (owner["id"] if owner else None),
        "technician_name": (tech or owner or {}).get("name"),
        "technician_color": (tech or {}).get("color") or "#FF5F1F",
        "zone": zone,
        "calibration_type": data.calibration_type,
        "calibration_label": STANDARD_PRICING[data.calibration_type]["label"],
        "scheduled_start": iso(start_dt),
        "scheduled_end": iso(end_dt),
        "duration_minutes": plan["duration_minutes"],
        "job_address": data.job_address,
        "job_lat": geo["lat"], "job_lng": geo["lng"],
        "geocode_source": "google" if geo.get("source") in (None, "google") else geo.get("source"),
        "status": plan["status"],
        "booking_kind": plan["booking_kind"],
        "approval_reason": plan["approval_reason"],
        "extra_drive_minutes": plan["extra_drive_minutes"],
        "later_finish_minutes": plan["later_finish_minutes"],
        "drive_time_minutes": plan["drive_time_minutes"],
        "actual_arrival": None, "actual_completion": None,
        "result": None, "notes": customer["notes"],
        "price": price,
        "payment_mode": INVOICE_MODE if data.invoice_instead else CHARGE_MODE,
        "invoice_id": None, "invoice_status": "pending",
        "google_calendar_event_id": None,
        "sequence_order": seq_count + 1,
        "notification_phone": data.notification_phone or shop.get("contact_phone"),
        "notification_email": data.notification_email or shop.get("contact_email"),
        "customer_last_name": data.customer_last_name,
        "customer_first_name": customer["customer_first_name"],
        "vehicle_year": data.year, "vehicle_make": data.make, "vehicle_model": data.model, "vehicle_vin": data.vin,
        "created_at": iso(now_utc()), "updated_at": iso(now_utc()),
    }
    await db.jobs.insert_one(job.copy())

    pending = job["status"] == "requested"
    shop_mail = await email_shop_confirmation(job, shop, pending=pending)
    same_day = job.get("booking_kind") == "addon" or business_date(start_dt) == business_date(now)
    if owner_needs_alert(start_dt, job.get("booking_kind") or "", now):
        await email_owner_alert(job, shop, pending=pending, same_day=same_day)

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

    return {
        "job_id": job["id"], "booking_reference": job["id"][:8].upper(),
        "scheduled_start": job["scheduled_start"], "zone": zone, "price": price,
        "status": job["status"],
        "requires_approval": pending,
        "shop_email_delivered": bool(shop_mail and shop_mail.get("delivered")),
    }

async def _job_for_shop_token(token: str, job_id: str) -> tuple:
    shop = await _shop_for_booking_token(token)
    job = await db.jobs.find_one({"id": job_id, "shop_id": shop["id"]}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Booking not found")
    return shop, job

@api.get("/public/bookings/{token}")
async def public_booking_list(token: str):
    """Upcoming jobs for this booking link only. Other shops' jobs are not included."""
    shop = await _shop_for_booking_token(token)
    jobs = await db.jobs.find({"shop_id": shop["id"]}, {"_id": 0}).to_list(500)
    upcoming = [job for job in jobs if is_upcoming(job)]
    upcoming.sort(key=lambda job: job.get("scheduled_start") or "")
    return upcoming

@api.patch("/public/bookings/{token}/{job_id}")
async def public_booking_edit(token: str, job_id: str, body: JobEditIn):
    """Shop edit via its booking token. Price and zone stay owner-only. No messages."""
    shop, job = await _job_for_shop_token(token, job_id)
    try:
        fields = prepare_edit(body.model_dump(exclude_unset=True), allow_price=False, allow_zone=False)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return await _apply_job_edit(
        job, fields, {"kind": "shop", "id": shop["id"], "name": shop["name"]},
    )

@api.post("/public/bookings/{token}/{job_id}/cancel")
async def public_booking_cancel(token: str, job_id: str):
    """Cancel one of this shop's jobs. Does not send SMS or email."""
    shop, job = await _job_for_shop_token(token, job_id)
    if job.get("status") == "cancelled":
        raise HTTPException(400, "Job is already cancelled")
    if job.get("status") == "complete":
        raise HTTPException(400, "A completed job cannot be cancelled here")
    now = iso(now_utc())
    entry = {
        "at": now,
        "who": {"kind": "shop", "id": shop["id"], "name": shop["name"]},
        "fields": ["status"],
    }
    await db.jobs.update_one(
        {"id": job["id"]},
        {"$set": {"status": "cancelled", "updated_at": now}, "$push": {"edit_history": entry}},
    )
    await dismiss_new_booking_alert(job["id"])
    return await db.jobs.find_one({"id": job["id"]}, {"_id": 0})

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
async def list_jobs(
    date_str: Optional[str] = None,
    include_cancelled: bool = False,
    tech=Depends(get_current_tech),
):
    """List jobs for a Phoenix date (default: today in America/Phoenix).

    Cancelled and declined jobs stay in the database and are left off the day
    list. Pass include_cancelled=true to put cancelled jobs back in the
    response for a history view. Declined jobs stay out. Contractors only see
    their own jobs. The shop portal list is a different route and is unchanged.
    """
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "Invalid date")
    else:
        d = business_date()
    day_start, day_end = business_day_bounds(d)
    hidden = ["declined"] if include_cancelled else ["cancelled", "declined"]
    q = {
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(day_end)},
        "status": {"$nin": hidden},
    }
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

_VEHICLE_FIELD_MAP = {
    "vehicle_year": "year",
    "vehicle_make": "make",
    "vehicle_model": "model",
    "vehicle_vin": "vin",
    "customer_last_name": "customer_last_name",
    "customer_first_name": "customer_first_name",
}

async def _apply_job_edit(job: dict, fields: dict, who: dict) -> dict:
    """Write a job edit. Does not send SMS or email.

    Status stays put unless the new time is before 8:00 AM or no longer fits
    today's route without approval. Those become requested or booked. Driving,
    on site, complete, cancelled, and declined are left alone.
    """
    if "job_address" in fields and fields["job_address"] != (job.get("job_address") or ""):
        try:
            geo = await geocode_for_regeocode(fields["job_address"])
        except (GoogleMapsError, requests.RequestException, AddressNotFound):
            raise HTTPException(400, ADDRESS_NOT_FOUND)
        _refuse_unusable_pin(geo)
        fields["job_lat"] = geo["lat"]
        fields["job_lng"] = geo["lng"]
        fields["geocode_source"] = "google" if geo.get("source") == "google" else geo.get("source") or "google"
        if "zone" not in fields:
            zone = zone_for_geocode(geo)
            if zone:
                fields["zone"] = zone
        chosen = assign_technician(await load_routing_techs(), geo["lat"], geo["lng"])
        if chosen and chosen.get("id") != job.get("technician_id"):
            fields["technician_id"] = chosen["id"]
            fields["technician_name"] = chosen.get("name")
            fields["technician_color"] = chosen.get("color") or "#FF5F1F"
    if "notification_phone" in fields:
        try:
            fields["notification_phone"] = normalize_us_phone(fields["notification_phone"])
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    if "calibration_type" in fields:
        fields["calibration_label"] = STANDARD_PRICING[fields["calibration_type"]]["label"]
    if "scheduled_start" in fields:
        new_start = datetime.fromisoformat(fields["scheduled_start"])
        if new_start.tzinfo is None:
            new_start = new_start.replace(tzinfo=timezone.utc)
        fields["scheduled_end"] = shift_scheduled_end(job, new_start).isoformat()
        previous = _job_when(job)
        if business_date(new_start) != business_date(previous):
            closed = await closed_day_message(business_date(new_start))
            if closed:
                raise HTTPException(400, closed)
    changed = changed_keys(job, fields)
    if not changed:
        return job
    route_touch = {"scheduled_start", "job_lat", "job_lng", "technician_id"} & set(changed)
    if route_touch:
        merged = {**job, **fields}
        try:
            start = datetime.fromisoformat(str(merged["scheduled_start"]).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            raise HTTPException(400, "Invalid date and time.")
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        tech_id = merged.get("technician_id")
        person = await db.technicians.find_one({"id": tech_id}, {"_id": 0, "password_hash": 0}) if tech_id else None
        if person is None:
            person = await _assigned_tech(merged.get("job_lat"), merged.get("job_lng"))
        siblings = await _route_jobs(person["id"], business_date(start), ignore_job_id=job.get("id")) if person else []
        plan = await _arrival_plan(
            person, business_date(start), start,
            (merged.get("job_lat"), merged.get("job_lng")),
            siblings, allow_outside=(who.get("kind") == "owner"),
            duration=block_minutes(merged),
        )
        if job.get("status") in ("booked", "requested"):
            if plan["status"] != job.get("status") or plan.get("approval_reason") != job.get("approval_reason"):
                fields["status"] = plan["status"]
                fields["approval_reason"] = plan["approval_reason"]
                fields["booking_kind"] = plan["booking_kind"]
                fields["extra_drive_minutes"] = plan["extra_drive_minutes"]
                fields["later_finish_minutes"] = plan["later_finish_minutes"]
                fields["drive_time_minutes"] = plan["drive_time_minutes"]
        changed = changed_keys(job, fields)
    now = iso(now_utc())
    entry = {"at": now, "who": who, "fields": changed}
    await db.jobs.update_one(
        {"id": job["id"]},
        {"$set": {**{key: fields[key] for key in changed}, "updated_at": now},
         "$push": {"edit_history": entry}},
    )
    vehicle_updates = {
        _VEHICLE_FIELD_MAP[key]: fields[key]
        for key in changed if key in _VEHICLE_FIELD_MAP
    }
    if vehicle_updates and job.get("vehicle_id"):
        await db.vehicles.update_one({"id": job["vehicle_id"]}, {"$set": vehicle_updates})
    fresh = await db.jobs.find_one({"id": job["id"]}, {"_id": 0})
    return fresh

@api.patch("/jobs/{job_id}")
async def patch_job(job_id: str, body: JobEditIn, tech=Depends(require_owner)):
    """Owner edit. Technicians and contractors cannot change a job. No messages, no status change."""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    try:
        fields = prepare_edit(body.model_dump(exclude_unset=True), allow_price=True, allow_zone=True)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return await _apply_job_edit(
        job, fields, {"kind": tech["role"], "id": tech["id"], "name": tech["name"]},
    )

@api.post("/jobs/{job_id}/approve")
async def approve_requested_job(job_id: str, tech=Depends(require_owner)):
    """Owner confirms a time that was not auto-confirmed. No SMS or email."""
    return await _decide_requested_job(job_id, tech, approve=True)

@api.post("/jobs/{job_id}/decline")
async def decline_requested_job(job_id: str, tech=Depends(require_owner)):
    """Owner turns down a held time and frees it. No SMS or email."""
    return await _decide_requested_job(job_id, tech, approve=False)

async def _decide_requested_job(job_id: str, tech: dict, *, approve: bool) -> dict:
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("status") != "requested":
        raise HTTPException(400, "That job is not waiting for approval.")
    now = iso(now_utc())
    status = "booked" if approve else "declined"
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "status": status,
        "approved_at": now if approve else None,
        "approved_by": tech["id"] if approve else None,
        "declined_at": None if approve else now,
        "updated_at": now,
    }})
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    await notify_booking_approval(fresh, "approved" if approve else "declined")
    return fresh

@api.post("/jobs/{job_id}/payment-mode")
async def set_payment_mode(job_id: str, body: PaymentModeIn, tech=Depends(require_owner)):
    """Only the owner can switch a job between charge-on-completion and invoice hold."""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("charged_at") or job.get("payment_status") in ("paid", "succeeded"):
        raise HTTPException(400, "This job is already paid.")
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "payment_mode": body.mode, "updated_at": iso(now_utc()),
    }})
    return await db.jobs.find_one({"id": job_id}, {"_id": 0})


@api.post("/jobs/{job_id}/status")
async def update_status(job_id: str, body: JobStatusUpdate, tech=Depends(get_current_tech)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if tech["role"] != "owner":
        raise HTTPException(403, "Only the owner can change a job.")
    if tech["role"] == "contractor" and job.get("technician_id") != tech["id"]:
        raise HTTPException(403, "Not your job")
    if job.get("status") in ("requested", "declined"):
        raise HTTPException(400, "The owner has to approve this time before the job can move.")
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
    if body.status == "cancelled":
        await dismiss_new_booking_alert(job_id)
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return fresh

def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return ""


async def _shop_user_for(shop_id: str):
    col = getattr(db, "shop_users", None)
    if col is None or not shop_id:
        return None
    return await col.find_one({"shop_id": shop_id}, {"_id": 0})


async def _record_local_invoice(job, shop, description: str, provider: str, stripe_invoice_id=None, hosted_url=None, total=None) -> dict:
    """One invoice row per job. A second complete updates nothing new."""
    existing = await db.job_invoices.find_one({"job_id": job["id"]}, {"_id": 0})
    if existing:
        return existing
    row = {
        "invoice_id": stripe_invoice_id or f"local-{job['id']}",
        "stripe_invoice_id": stripe_invoice_id,
        "provider": provider,
        "status": "open",
        "contact_name": shop.get("name"),
        "total": total if total is not None else amount_due(job),
        "hosted_url": hosted_url,
        "description": description,
        "created_at": iso(now_utc()),
        "job_id": job["id"],
    }
    await db.job_invoices.update_one({"job_id": job["id"]}, {"$setOnInsert": row}, upsert=True)
    stored = await db.job_invoices.find_one({"job_id": job["id"]}, {"_id": 0})
    return stored or row


async def _email_proof(job, shop, invoice: dict):
    shop_user = await _shop_user_for(job.get("shop_id"))
    to = (shop_user or {}).get("email") or shop.get("contact_email") or job.get("notification_email")
    if not to:
        return
    link = invoice.get("hosted_url") or ""
    mode = payment_mode(job)
    if mode == INVOICE_MODE:
        how = "This job is invoiced. The card is not charged unless you ask us to. You have 7 days before a $25 late fee."
    else:
        how = "The card on file is charged for this completed job. This invoice is your proof of purchase."
    html = (
        f"<p>Invoice for {shop.get('name')} — {job.get('calibration_label')}.</p>"
        f"<p>{job.get('vehicle_year')} {job.get('vehicle_make')} {job.get('vehicle_model')}</p>"
        f"<p>Amount: ${amount_due(job):.2f}</p><p>{how}</p>"
    )
    if link:
        html += f"<p><a href=\"{link}\">View invoice</a></p>"
    await _send_booking_message({
        "to": to, "subject": f"Invoice — {shop.get('name')}", "html": html,
        "kind": "job_invoice", "reply_to": owner_notify_email(),
        "meta": {"job_id": job["id"], "invoice_id": invoice.get("invoice_id")},
    }, "shop")


async def _notify_payment_failed(job, shop, message: str):
    attempt = int(job.get("charge_attempts") or 0)
    if job.get("payment_failure_notified_attempt") == attempt and job.get("payment_status") == "payment_failed":
        return
    card_link = ""
    try:
        card_link = app_link(FRONTEND_URL, "/portal/settings")
    except ValueError:
        card_link = "/portal/settings"
    await send_email(
        owner_notify_email(),
        f"Card declined — {shop.get('name')}",
        f"<p>{shop.get('name')} — {message}</p><p>Job {job.get('id')} is marked payment failed.</p>",
        kind="payment_failed_owner",
        meta={"job_id": job["id"]},
    )
    shop_user = await _shop_user_for(job.get("shop_id"))
    shop_email = (shop_user or {}).get("email") or shop.get("contact_email")
    if shop_email:
        await _send_booking_message({
            "to": shop_email,
            "subject": "Please update the card on file",
            "html": (
                f"<p>We could not charge the card for a completed calibration. {message}</p>"
                f"<p><a href=\"{card_link}\">Update the card</a></p>"
            ),
            "kind": "payment_failed_shop",
            "reply_to": owner_notify_email(),
            "meta": {"job_id": job["id"]},
        }, "shop")
    await db.jobs.update_one({"id": job["id"]}, {"$set": {
        "payment_failure_notified_attempt": attempt,
    }})


async def _charge_saved_card(job, shop) -> dict:
    """Off-session charge. Refuses when the job is already paid. One Stripe key per attempt."""
    plan = billing_plan(job)
    if not plan["charge"]:
        return job
    shop_user = await _shop_user_for(job.get("shop_id"))
    if not shop_user or not shop_user.get("stripe_customer_id") or not shop_user.get("stripe_payment_method_id"):
        message = "No card on file to charge."
        await db.jobs.update_one({"id": job["id"]}, {"$set": {
            "payment_status": "payment_failed",
            "charge_error": message,
            "charge_error_at": iso(now_utc()),
        }})
        await _notify_payment_failed({**job, "payment_status": "payment_failed"}, shop, message)
        return await db.jobs.find_one({"id": job["id"]}, {"_id": 0})
    client = get_stripe()
    if client is None:
        message = "Stripe is not configured (set STRIPE_SECRET_KEY)."
        await db.jobs.update_one({"id": job["id"]}, {"$set": {
            "payment_status": "payment_failed", "charge_error": message, "charge_error_at": iso(now_utc()),
        }})
        logger.error("[CHARGE] %s", message)
        return await db.jobs.find_one({"id": job["id"]}, {"_id": 0})
    try:
        result = await asyncio.to_thread(
            stripe_charge_job, client,
            job=job, customer_id=shop_user["stripe_customer_id"],
            payment_method_id=shop_user["stripe_payment_method_id"],
            receipt_email=None,
        )
    except stripe_sdk.error.CardError as exc:
        decline_code = getattr(exc.error, "decline_code", None) if getattr(exc, "error", None) else None
        message = decline_message(exc.code, decline_code)
        attempt = int(job.get("charge_attempts") or 0) + 1
        declined = treat_decline_as_invoice(job)
        await db.jobs.update_one({"id": job["id"]}, {"$set": {
            "payment_status": "payment_failed",
            "payment_mode": declined["payment_mode"],
            "invoiced_after_decline": True,
            "charge_error": message,
            "charge_error_at": iso(now_utc()),
            "charge_attempts": attempt,
        }})
        failed = await db.jobs.find_one({"id": job["id"]}, {"_id": 0})
        await _notify_payment_failed(failed, shop, message)
        logger.warning("[CHARGE] job %s declined: %s", job["id"], message)
        return failed
    except stripe_sdk.error.StripeError as exc:
        message = getattr(exc, "user_message", None) or str(exc)
        await db.jobs.update_one({"id": job["id"]}, {"$set": {
            "payment_status": "payment_failed",
            "charge_error": message,
            "charge_error_at": iso(now_utc()),
            "charge_attempts": int(job.get("charge_attempts") or 0) + 1,
        }})
        failed = await db.jobs.find_one({"id": job["id"]}, {"_id": 0})
        await _notify_payment_failed(failed, shop, message)
        logger.error("[CHARGE] job %s failed: %s", job["id"], message)
        return failed
    if result.get("outcome") != "succeeded":
        message = result.get("message") or "Card requires authentication."
        declined = treat_decline_as_invoice(job)
        await db.jobs.update_one({"id": job["id"]}, {"$set": {
            "payment_status": "payment_failed",
            "payment_mode": declined["payment_mode"],
            "invoiced_after_decline": True,
            "charge_error": message,
            "charge_error_at": iso(now_utc()),
            "stripe_payment_intent_id": result.get("payment_intent_id"),
            "charge_attempts": int(job.get("charge_attempts") or 0) + 1,
        }})
        failed = await db.jobs.find_one({"id": job["id"]}, {"_id": 0})
        await _notify_payment_failed(failed, shop, message)
        return failed
    await db.jobs.update_one({"id": job["id"]}, {"$set": {
        "charged_at": iso(now_utc()),
        "charge_method": "stripe",
        "payment_status": "paid",
        "stripe_payment_intent_id": result.get("payment_intent_id"),
        "charged_amount": amount_due(job),
        "charge_error": None,
    }})
    paid = await db.jobs.find_one({"id": job["id"]}, {"_id": 0})
    for invoice_id in (paid.get("stripe_invoice_id"), paid.get("stripe_late_fee_invoice_id")):
        if not invoice_id:
            continue
        try:
            await asyncio.to_thread(mark_invoice_paid_out_of_band, client, invoice_id, job["id"])
        except Exception as exc:
            logger.warning("[CHARGE] could not mark invoice %s paid out of band: %s", invoice_id, exc)
    logger.info("[CHARGE] job %s charged %s", job["id"], result.get("payment_intent_id"))
    receipt_to = shop_user.get("email") or shop.get("contact_email")
    if receipt_to:
        await _send_booking_message({
            "to": receipt_to,
            "subject": f"Receipt — {shop.get('name')}",
            "html": f"<p>Paid ${amount_due(paid):.2f} for {paid.get('calibration_label') or 'a calibration'}.</p>",
            "kind": "receipt",
            "reply_to": owner_notify_email(),
            "meta": {"job_id": job["id"]},
        }, "shop")
    return paid


async def _settle_completed_job(job_id: str) -> dict:
    """Create at most one invoice, then charge only in charge-on-completion mode."""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    shop = await db.shops.find_one({"id": job["shop_id"]}) or {"name": job.get("shop_name"), "id": job.get("shop_id")}
    plan = billing_plan(job)
    description = job.get("billing_description") or job.get("calibration_label") or "ADAS calibration"
    if plan["create_invoice"]:
        client = get_stripe()
        shop_user = await _shop_user_for(job.get("shop_id"))
        invoice = None
        if client and shop_user and shop_user.get("stripe_customer_id"):
            try:
                created = await asyncio.to_thread(
                    create_job_invoice, client,
                    customer_id=shop_user["stripe_customer_id"], job=job, description=description,
                    email_customer=shop_emails_enabled(),
                )
                invoice = await _record_local_invoice(
                    job, shop, description, "stripe",
                    stripe_invoice_id=created["stripe_invoice_id"],
                    hosted_url=created.get("hosted_url"),
                    total=created.get("total"),
                )
            except Exception as exc:
                logger.error("[BILLING] Stripe invoice failed for %s: %s", job_id, exc)
        if invoice is None:
            invoice = await _record_local_invoice(job, shop, description, "local")
        await db.jobs.update_one({"id": job_id}, {"$set": {
            "invoice_id": invoice["invoice_id"],
            "stripe_invoice_id": invoice.get("stripe_invoice_id"),
            "invoice_status": invoice.get("status") or "open",
            "invoice_url": invoice.get("hosted_url"),
            "invoice_provider": invoice.get("provider"),
        }})
        job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
        await _email_proof(job, shop, invoice)
        await send_email(
            _env("ADMIN_EMAIL", "admin@thecalibrationcrew.us"),
            f"Invoice — {shop.get('name')}",
            f"<p>Invoice {invoice['invoice_id']} for {shop.get('name')}, ${amount_due(job):.2f}. "
            f"Mode: {payment_mode(job).replace('_', ' ')}.</p>",
            kind="invoice_notification",
            meta={"job_id": job_id, "invoice_id": invoice["invoice_id"], "provider": invoice.get("provider")},
        )
    if billing_plan(job)["charge"]:
        if not billing_enabled():
            await db.jobs.update_one({"id": job_id}, {"$set": {
                "payment_status": "not_charged",
                "charge_skipped": "BILLING_ENABLED is off",
            }})
            logger.info("[BILLING] skipped automatic charge for job %s. BILLING_ENABLED is off.", job_id)
            job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
        else:
            job = await _charge_saved_card(job, shop)
    return job


def _job_already_billed(job: dict) -> bool:
    return bool(
        job.get("invoice_id")
        or job.get("stripe_invoice_id")
        or job.get("charged_at")
        or job.get("payment_status") in ("paid", "succeeded")
    )


@api.post("/jobs/{job_id}/outside-service-area")
async def set_job_outside_service_area(job_id: str, body: OutsideAreaIn, tech=Depends(require_owner)):
    """Add or remove the $30 outside-area trip fee on top of the calibration price."""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("status") in ("cancelled", "declined"):
        raise HTTPException(400, "That job is closed.")
    if _job_already_billed(job):
        raise HTTPException(400, "This job already has an invoice.")
    updated = set_outside_service_area(job, body.enabled)
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "price": updated["price"],
        "calibration_price": updated["calibration_price"],
        "outside_service_area": updated["outside_service_area"],
        "trip_fee": updated["trip_fee"],
        "trip_fee_kind": updated["trip_fee_kind"],
        "updated_at": iso(now_utc()),
    }})
    return await db.jobs.find_one({"id": job_id}, {"_id": 0})


@api.post("/jobs/{job_id}/trip-fee")
async def charge_trip_fee_only(job_id: str, body: TripFeeIn, tech=Depends(require_owner)):
    """Couldn't calibrate. Charge the $30 trip fee through the same invoice path as a completed job."""
    if body.reason not in TRIP_FEE_REASONS:
        raise HTTPException(400, "Pick a trip-fee reason.")
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("status") in ("cancelled", "declined"):
        raise HTTPException(400, "That job is closed.")
    if _job_already_billed(job):
        raise HTTPException(400, "This job already has an invoice.")
    priced = apply_trip_fee_only(job, body.reason)
    now = iso(now_utc())
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "price": priced["price"],
        "trip_fee": priced["trip_fee"],
        "trip_fee_reason": priced["trip_fee_reason"],
        "trip_fee_kind": priced["trip_fee_kind"],
        "calibration_not_performed": True,
        "outside_service_area": False,
        "billing_description": priced["billing_description"],
        "status": "complete",
        "result": "not_performed",
        "actual_completion": job.get("actual_completion") or now,
        "payment_mode": job.get("payment_mode") or CHARGE_MODE,
        "updated_at": now,
    }})
    fresh = await _settle_completed_job(job_id)
    return {"job": fresh}


@api.post("/jobs/{job_id}/charge-card")
async def charge_card_now(job_id: str, tech=Depends(require_owner)):
    """Owner charges the saved card for an invoiced job, or retries a failed charge."""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("status") != "complete":
        raise HTTPException(400, "Complete the job before charging the card.")
    if job.get("charged_at") or job.get("payment_status") in ("paid", "succeeded"):
        raise HTTPException(400, "This job is already paid.")
    shop = await db.shops.find_one({"id": job["shop_id"]}) or {"name": job.get("shop_name"), "id": job.get("shop_id")}
    # Treat a held invoice as chargeable for this explicit button without flipping the stored mode
    # until the charge succeeds. billing_plan only charges charge_on_completion, so force that view.
    payable = {**job, "payment_mode": CHARGE_MODE}
    fresh = await _charge_saved_card(payable, shop)
    if fresh.get("payment_status") == "payment_failed":
        raise HTTPException(402, fresh.get("charge_error") or "The card was not charged.")
    return {"job": fresh}


@api.post("/jobs/{job_id}/complete")
async def complete_job(job_id: str, body: JobComplete, tech=Depends(get_current_tech)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if tech["role"] != "owner":
        raise HTTPException(403, "Only the owner can complete a job.")
    if tech["role"] == "contractor" and job.get("technician_id") != tech["id"]:
        raise HTTPException(403, "Not your job")

    shop = await db.shops.find_one({"id": job["shop_id"]})
    vehicle = await db.vehicles.find_one({"id": job["vehicle_id"]})

    already_complete = job.get("status") == "complete"
    file_name = f"{job['customer_last_name']}_{shop['name'].upper().replace(' ', '')}_{job['vehicle_make']}_{job['vehicle_model']}_{job['vehicle_year']}.pdf"
    doc = None
    if not already_complete:
        doc = {
            "id": gen_id(), "job_id": job_id, "file_name": file_name,
            "storage_path": f"calibration-docs/Recals/Recal - Caleb/{datetime.fromisoformat(job['scheduled_start']).strftime('%Y/%B')}/{file_name}",
            "file_type": "pdf", "uploaded_at": iso(now_utc()), "uploaded_by": tech["id"],
        }
        await db.documents.insert_one(doc.copy())
        await db.jobs.update_one({"id": job_id}, {"$set": {
            "status": "complete",
            "actual_completion": job.get("actual_completion") or iso(now_utc()),
            "result": body.result,
            "notes": completion_notes(job.get("notes"), body.notes),
            "payment_mode": job.get("payment_mode") or CHARGE_MODE,
            "updated_at": iso(now_utc()),
        }})
        msg = (f"ADAS calibration complete on your {job['vehicle_year']} {job['vehicle_make']} {job['vehicle_model']}. "
               f"Your invoice is the proof of purchase. — The Calibration Crew")
        if job.get("notification_phone"):
            await mock_send_sms(job["notification_phone"], msg, kind="completed", job_id=job_id)

    fresh = await _settle_completed_job(job_id)
    invoice = {
        "invoice_id": fresh.get("invoice_id"),
        "provider": fresh.get("invoice_provider"),
        "status": fresh.get("invoice_status"),
    }
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
        "status": {"$nin": ["cancelled", "declined"]},
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
        "shop_emails_enabled": shop_emails_enabled(),
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
    closed = await closed_day_message(business_date(new_start))
    if closed:
        raise HTTPException(400, closed)
    z = ZONES[job["zone"]]
    new_end = new_start + timedelta(minutes=z["slot_minutes"])
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "scheduled_start": iso(new_start),
        "scheduled_end": iso(new_end),
        "reschedule_reason": body.reason,
        "rescheduled_at": iso(now_utc()),
        "updated_at": iso(now_utc()),
    }})
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    await email_shop_event(fresh, await _shop_for_job(fresh), "rescheduled")
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
    await dismiss_new_booking_alert(job_id)
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    await email_shop_event(fresh, await _shop_for_job(fresh), "cancelled")
    return fresh

# ---------- Real document upload (replaces mocked filename) ----------
@api.post("/jobs/{job_id}/upload-document")
async def upload_document(job_id: str, file: UploadFile = File(...), tech=Depends(get_current_tech)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if tech["role"] != "owner":
        raise HTTPException(403, "Only the owner can change a job.")
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
    proof = []
    proof_col = getattr(db, "job_invoices", None)
    if proof_col is not None:
        proof = await proof_col.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    invs = real + mock + proof
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
            "routes": await routes_budget_snapshot(),
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
async def dismiss_new_booking_alert(job_id: str) -> None:
    """Mark this job's unseen new-booking alerts seen.

    Other jobs' alerts stay unseen. A missing alerts collection is ignored so
    a cancel still succeeds on older doubles that do not mount one.
    """
    if not job_id:
        return
    store = getattr(db, "new_booking_alerts", None)
    if store is None:
        return
    try:
        await store.update_many(
            {"job_id": job_id, "seen_at": None},
            {"$set": {"seen_at": iso(now_utc())}},
        )
    except Exception as exc:
        logger.warning("could not dismiss new-booking alert for %s: %s", job_id, exc)


async def _alerts_for_open_jobs(alerts: list) -> list:
    """Drop notices for jobs that are already cancelled.

    A cancel that happened before this write still leaves seen_at empty.
    Those notices are not new bookings anymore. Other unseen alerts stay.
    """
    if not alerts:
        return []
    ids = [alert.get("job_id") for alert in alerts if alert.get("job_id")]
    jobs_store = getattr(db, "jobs", None)
    closed = set()
    if jobs_store is not None and ids:
        try:
            rows = await jobs_store.find(
                {"id": {"$in": ids}}, {"_id": 0, "id": 1, "status": 1},
            ).to_list(len(ids))
        except Exception as exc:
            logger.warning("could not check jobs for new-booking alerts: %s", exc)
            rows = []
        closed = {row.get("id") for row in rows if row.get("status") == "cancelled"}
    return [alert for alert in alerts if alert.get("job_id") not in closed]


@api.get("/notifications/new-bookings")
async def new_booking_alerts(tech=Depends(require_owner)):
    """Returns unseen new-booking alerts for the owner."""
    alerts = await db.new_booking_alerts.find(
        {"owner_id": tech["id"], "seen_at": None},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    alerts = await _alerts_for_open_jobs(alerts)
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

def _tech_public(person: dict) -> dict:
    keys = (
        "id", "name", "role", "phone", "email", "home_address", "home_lat", "home_lng",
        "service_radius_miles", "day_start", "day_end", "slot_minutes", "max_jobs",
        "is_active", "color", "routes_jobs",
        "job_duration_minutes", "buffer_minutes",
        "same_day_bookings_enabled", "same_day_cutoff",
        "same_day_max_extra_drive_minutes", "same_day_max_later_finish_minutes",
        "same_day_over_limit",
    )
    return {key: person.get(key) for key in keys}

def _check_routing_fields(fields: dict):
    radius = fields.get("service_radius_miles")
    if radius is not None and float(radius) <= 0:
        raise HTTPException(400, "Service area must be greater than 0 miles, or left blank.")
    slot = fields.get("slot_minutes")
    if slot is not None and int(slot) <= 0:
        raise HTTPException(400, "Slot length must be greater than 0.")
    cap = fields.get("max_jobs")
    if cap is not None and int(cap) <= 0:
        raise HTTPException(400, "Max jobs must be greater than 0.")
    start, end = fields.get("day_start"), fields.get("day_end")
    if start and end and start >= end:
        raise HTTPException(400, "Day start must be before day end.")
    duration = fields.get("job_duration_minutes")
    if duration is not None and not (10 <= int(duration) <= 90):
        raise HTTPException(400, "Job length must be between 10 and 90 minutes.")
    buffer = fields.get("buffer_minutes")
    if buffer is not None and not (0 <= int(buffer) <= 90):
        raise HTTPException(400, "Buffer must be between 0 and 90 minutes.")
    extra = fields.get("same_day_max_extra_drive_minutes")
    if extra is not None and int(extra) < 0:
        raise HTTPException(400, "Extra drive limit cannot be negative.")
    later = fields.get("same_day_max_later_finish_minutes")
    if later is not None and int(later) < 0:
        raise HTTPException(400, "Later-finish limit cannot be negative.")
    cutoff = fields.get("same_day_cutoff")
    if cutoff:
        parts = str(cutoff).split(":")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise HTTPException(400, "Cutoff must be HH:MM.")
        hour, minute = int(parts[0]), int(parts[1])
        if hour > 23 or minute > 59:
            raise HTTPException(400, "Cutoff must be HH:MM.")
    over = fields.get("same_day_over_limit")
    if over is not None and over not in ("pending", "hide"):
        raise HTTPException(400, "Choose approval or hide when a same-day time is over the limit.")

@api.put("/settings/drive")
async def update_drive_settings(body: DriveSettingsIn, tech=Depends(require_owner)):
    """Owner limits for Routes spend and the rush-hour multiplier. No messages."""
    incoming = {key: value for key, value in body.model_dump().items() if value is not None}
    if "rush_multiplier" in incoming and not (1 <= float(incoming["rush_multiplier"]) <= 3):
        raise HTTPException(400, "Rush multiplier must be between 1 and 3.")
    for key in ("pro_daily_limit", "essentials_daily_limit"):
        if key in incoming and int(incoming[key]) < 0:
            raise HTTPException(400, "Daily route limit cannot be negative.")
    current = await load_drive_settings()
    current.update(incoming)
    await db.app_settings.update_one({"_id": "drive"}, {"$set": current}, upsert=True)
    return await routes_budget_snapshot()

@api.get("/routing-techs")
async def list_routing_techs_route(tech=Depends(require_owner)):
    people = await db.technicians.find(
        {"role": {"$in": ["owner", "technician"]}},
        {"_id": 0, "password_hash": 0},
    ).to_list(50)
    return [_tech_public(person) for person in people]

@api.post("/routing-techs")
async def create_routing_tech(body: RoutingTechIn, tech=Depends(require_owner)):
    """Add a technician with a geocoded home base. Does not send SMS or email."""
    if not body.name.strip() or not body.home_address.strip():
        raise HTTPException(400, "Name and home address are required.")
    _check_routing_fields(body.model_dump())
    try:
        geo = await geocode_for_regeocode(body.home_address.strip())
    except (GoogleMapsError, requests.RequestException):
        raise HTTPException(400, "Could not locate that home address.")
    used = []
    for person in await db.technicians.find({}, {"_id": 0, "color": 1}).to_list(50):
        if person.get("color"):
            used.append(person["color"])
    tech_id = gen_id()
    doc = {
        "id": tech_id,
        "name": body.name.strip(),
        "email": f"tech-{tech_id}@technicians.invalid",
        "phone": body.phone,
        "role": "technician",
        "home_address": body.home_address.strip(),
        "home_lat": geo["lat"],
        "home_lng": geo["lng"],
        "service_radius_miles": body.service_radius_miles,
        "day_start": body.day_start,
        "day_end": body.day_end,
        "slot_minutes": body.slot_minutes,
        "max_jobs": body.max_jobs,
        "job_duration_minutes": body.job_duration_minutes,
        "buffer_minutes": body.buffer_minutes,
        "same_day_bookings_enabled": body.same_day_bookings_enabled,
        "same_day_cutoff": body.same_day_cutoff,
        "same_day_max_extra_drive_minutes": body.same_day_max_extra_drive_minutes,
        "same_day_max_later_finish_minutes": body.same_day_max_later_finish_minutes,
        "same_day_over_limit": body.same_day_over_limit,
        "is_active": True,
        "routes_jobs": True,
        "color": next_tech_color(used),
        "password_hash": hash_password(secrets.token_urlsafe(24)),
        "created_at": iso(now_utc()),
    }
    await db.technicians.insert_one(doc.copy())
    doc.pop("password_hash", None)
    return _tech_public(doc)

@api.put("/routing-techs/{tech_id}")
async def update_routing_tech(tech_id: str, body: RoutingTechUpdate, tech=Depends(require_owner)):
    """Edit a home base or service area. Contractors are not changed here. No messages."""
    person = await db.technicians.find_one({"id": tech_id}, {"_id": 0})
    if not person or person.get("role") not in ("owner", "technician"):
        raise HTTPException(404, "Technician not found")
    update = body.model_dump(exclude_unset=True)
    _check_routing_fields(update)
    turning_off = update.get("is_active") is False or update.get("routes_jobs") is False
    if turning_off:
        still = [p for p in await load_routing_techs() if p.get("id") != tech_id]
        if not still:
            raise HTTPException(400, "At least one technician has to cover the valley.")
    if update.get("clear_service_radius"):
        update["service_radius_miles"] = None
    update.pop("clear_service_radius", None)
    if update.get("home_address") and update["home_address"].strip() != (person.get("home_address") or "").strip():
        try:
            geo = await geocode_for_regeocode(update["home_address"].strip())
        except (GoogleMapsError, requests.RequestException):
            raise HTTPException(400, "Could not locate that home address.")
        update["home_address"] = update["home_address"].strip()
        update["home_lat"] = geo["lat"]
        update["home_lng"] = geo["lng"]
    if not update:
        return _tech_public(person)
    update["updated_at"] = iso(now_utc())
    await db.technicians.update_one({"id": tech_id}, {"$set": update})
    fresh = await db.technicians.find_one({"id": tech_id}, {"_id": 0, "password_hash": 0})
    return _tech_public(fresh)

# ---------- Job reorder with drive-time recalc ----------
@api.post("/jobs/reorder")
async def reorder_jobs(data: ReorderIn, tech=Depends(require_owner)):
    if not data.technician_id and not data.zone:
        raise HTTPException(400, "technician_id is required")
    try:
        d = datetime.strptime(data.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date")
    day_start, day_end = business_day_bounds(d)
    if data.technician_id:
        person = await db.technicians.find_one({"id": data.technician_id}, {"_id": 0, "password_hash": 0})
        if not person:
            raise HTTPException(404, "Technician not found")
        schedule = tech_schedule(person)
        origin_home = (
            (person["home_lat"], person["home_lng"])
            if person.get("home_lat") is not None else (CALEB_HOME["lat"], CALEB_HOME["lng"])
        )
        scope = {"technician_id": data.technician_id}
    else:
        schedule = {
            "day_start": ZONES[data.zone]["start"],
            "day_end": ZONES[data.zone]["end"],
            "slot_minutes": ZONES[data.zone]["slot_minutes"],
            "max_jobs": ZONES[data.zone]["max_jobs"],
        }
        origin_home = (CALEB_HOME["lat"], CALEB_HOME["lng"])
        scope = {"zone": data.zone}
    # Fetch jobs in scope
    jobs = await db.jobs.find({
        "id": {"$in": data.ordered_job_ids},
        **scope,
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(day_end)},
        "status": {"$nin": ["cancelled", "complete", "declined", "requested"]},
    }, {"_id": 0}).to_list(100)
    by_id = {j["id"]: j for j in jobs}
    if set(data.ordered_job_ids) - set(by_id.keys()):
        raise HTTPException(400, "Some job IDs are invalid or not reorderable")
    # Sequential recalc from this technician's day start, anchored at their home.
    cursor, zone_end_dt = zone_window(
        d, parse_time_str(schedule["day_start"]), parse_time_str(schedule["day_end"]),
    )
    origin = origin_home
    updates = []
    for seq, jid in enumerate(data.ordered_job_ids, start=1):
        j = by_id[jid]
        dm = await get_drive_time(origin[0], origin[1], j["job_lat"], j["job_lng"], depart_at=cursor)
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
        new_end = new_start + timedelta(minutes=schedule["slot_minutes"])
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
    # A zero or negative length makes offered_slot_starts step by nothing and loop forever.
    if d.get("slot_minutes") is not None and d["slot_minutes"] <= 0:
        raise HTTPException(400, "slot_minutes must be greater than 0")
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
async def send_email(to: str, subject: str, html: str, kind: str = "transactional", meta: Optional[dict] = None, reply_to: Optional[str] = None):
    """Send transactional email via Resend. Gracefully falls back to DB log if no key.

    Shop and customer mail does not come through here while testing. That mail
    uses _send_booking_message, which holds it in email_outbox.
    reply_to is the address a reply should reach. Blank uses the owner email.
    """
    reply = reply_to if reply_to is not None else owner_notify_email()
    log = {
        "id": gen_id(), "to": to, "from": SENDER_EMAIL, "reply_to": reply, "subject": subject,
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
        payload = {"from": SENDER_EMAIL, "to": [to], "subject": subject, "html": html}
        if reply:
            payload["reply_to"] = reply
        result = await asyncio.to_thread(resend_sdk.Emails.send, payload)
        log["delivered"] = True
        log["provider_id"] = result.get("id") if isinstance(result, dict) else None
        await db.email_log.insert_one(log)
        return log
    except Exception as e:
        log["error"] = str(e)
        await db.email_log.insert_one(log)
        logger.error(f"Resend send failed: {e}")
        return log

async def _issue_invite(shop: dict, recipient_email: str, previous_id: Optional[str] = None) -> dict:
    """14-day invite. The link always comes from FRONTEND_URL, never the browser origin."""
    token = secrets.token_urlsafe(24)
    try:
        register_url = invite_register_url(resolve_frontend_url(FRONTEND_URL, PUBLIC_SITE_URL), token)
        link_error = None
    except ValueError as exc:
        register_url = None
        link_error = str(exc)
        logger.error("[EMAIL] %s", link_error)
    invite = {
        "id": gen_id(), "shop_id": shop["id"], "shop_name": shop["name"],
        "recipient_email": recipient_email, "token": token,
        "status": "pending",
        "created_at": iso(now_utc()),
        "expires_at": iso(now_utc() + timedelta(days=14)),
        "registered_at": None, "shop_user_id": None,
        "previous_invite_id": previous_id,
        "email_status": "failed",
        "email_error": link_error,
        "register_url": register_url,
    }
    if register_url:
        log = await _send_booking_message({
            "to": recipient_email,
            "subject": f"Set up {shop['name']} with The Calibration Crew",
            "html": invite_email_html(shop["name"], register_url),
            "kind": "invite",
            "reply_to": owner_notify_email(),
            "meta": {"invite_id": invite["id"], "shop_id": shop["id"]},
        }, "shop")
        if log and log.get("delivered"):
            invite["email_status"] = "sent"
            invite["email_error"] = None
        elif log and log.get("audience"):
            invite["email_status"] = "held"
            invite["email_error"] = None
        else:
            invite["email_status"] = "failed"
            invite["email_error"] = (log or {}).get("error") or "Email was not delivered."
    await db.invites.insert_one(invite.copy())
    return invite


# ---------- Shop user auth + portal endpoints ----------
@api.post("/invites")
async def create_invite(body: InviteCreateIn, tech=Depends(require_owner)):
    shop = await db.shops.find_one({"id": body.shop_id}, {"_id": 0})
    if not shop:
        raise HTTPException(404, "Shop not found")
    # body.origin is ignored on purpose. A preview URL must not land in a shop inbox.
    return await _issue_invite(shop, str(body.recipient_email))


@api.post("/invites/{invite_id}/resend")
async def resend_invite(invite_id: str, tech=Depends(require_owner)):
    """New 14-day token. The previous token stops working."""
    old = await db.invites.find_one({"id": invite_id})
    if not old:
        raise HTTPException(404, "Invitation not found")
    if old.get("status") == "registered":
        raise HTTPException(400, "This shop already finished registration. Send a password reset instead.")
    shop = await db.shops.find_one({"id": old["shop_id"]}, {"_id": 0})
    if not shop:
        raise HTTPException(404, "Shop not found")
    await db.invites.update_one({"id": invite_id}, {"$set": {"status": "revoked", "revoked_at": iso(now_utc())}})
    return await _issue_invite(shop, old["recipient_email"], previous_id=invite_id)

@api.get("/invites")
async def list_invites(tech=Depends(require_owner)):
    invites = await db.invites.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return invites

def _invite_unusable(inv: dict) -> Optional[dict]:
    if inv.get("status") == "revoked":
        return {"code": "revoked", "message": "This link was replaced. Request a new one."}
    if inv.get("status") not in (None, "pending"):
        return {"code": "used", "message": "This link was already used."}
    if inv.get("expires_at") and inv["expires_at"] < iso(now_utc()):
        return {"code": "expired", "message": "This link has expired."}
    return None


@api.get("/public/invites/{token}")
async def public_invite_lookup(token: str):
    inv = await db.invites.find_one({"token": token}, {"_id": 0})
    if not inv:
        raise HTTPException(404, detail={"code": "missing", "message": "Invitation not found"})
    problem = _invite_unusable(inv)
    if problem:
        raise HTTPException(400, detail=problem)
    shop = await db.shops.find_one({"id": inv["shop_id"]},
        {"_id": 0, "name": 1, "address": 1, "contact_phone": 1})
    return {
        **inv, "shop": shop,
        "agreement_version": AGREEMENT_VERSION,
        "agreement_paragraphs": AGREEMENT_PARAGRAPHS,
        "agreement_sections": AGREEMENT_SECTIONS,
        "owner_phone": OWNER_PHONE,
    }


@api.post("/public/invites/{token}/request-new")
async def request_new_invite(token: str):
    inv = await db.invites.find_one({"token": token})
    if not inv:
        raise HTTPException(404, "Invitation not found")
    shop = await db.shops.find_one({"id": inv["shop_id"]}, {"_id": 0})
    if not shop:
        raise HTTPException(404, "Shop not found")
    if inv.get("status") == "pending":
        await db.invites.update_one({"id": inv["id"]}, {"$set": {"status": "revoked", "revoked_at": iso(now_utc())}})
    created = await _issue_invite(shop, inv["recipient_email"], previous_id=inv["id"])
    if created.get("email_status") == "failed":
        raise HTTPException(502, detail={
            "code": "email_failed",
            "message": created.get("email_error") or "We could not email a new link.",
            "owner_phone": OWNER_PHONE,
        })
    if created.get("email_status") == "held":
        return {
            "ok": True, "held": True, "owner_phone": OWNER_PHONE,
            "message": "The new link is in Email preview. Shop email is off, so it was not sent.",
        }
    return {"ok": True, "message": "A new link is on the way.", "owner_phone": OWNER_PHONE}


@api.post("/public/invites/{token}/register")
async def register_shop_user(token: str, body: ShopUserRegisterIn, request: Request):
    if not body.terms_agreed:
        raise HTTPException(400, "You must agree to the terms")
    if not (body.terms_signature or "").strip():
        raise HTTPException(400, "Type your name to sign.")
    pw_problem = password_error(body.password)
    if pw_problem:
        raise HTTPException(400, pw_problem)
    inv = await db.invites.find_one({"token": token})
    if not inv:
        raise HTTPException(400, "Invitation invalid or expired")
    problem = _invite_unusable(inv)
    if problem:
        raise HTTPException(400, problem["message"])
    existing = await db.shop_users.find_one({"email": inv["recipient_email"].lower()})
    if existing:
        raise HTTPException(400, "An account already exists for this email")
    user_id = gen_id()
    stripe_customer_id = None
    stripe_error = None
    client = get_stripe()
    if client:
        try:
            stripe_customer_id = await asyncio.to_thread(
                stripe_create_customer, client,
                email=inv["recipient_email"], name=body.full_name, shop_id=inv["shop_id"],
            )
        except Exception as exc:
            stripe_error = str(exc)
            logger.error("[STRIPE] customer create failed: %s", exc)
    else:
        stripe_error = "Stripe is not configured. Set STRIPE_SECRET_KEY to a test key."
        logger.error("[STRIPE] %s", stripe_error)
    signed_at = iso(now_utc())
    su = {
        "id": user_id, "email": inv["recipient_email"].lower(),
        "full_name": body.full_name.strip(),
        "password_hash": hash_password(body.password),
        "shop_id": inv["shop_id"], "shop_name": inv["shop_name"],
        "stripe_customer_id": stripe_customer_id,
        "stripe_payment_method_id": None,
        "card_brand": None, "card_last4": None, "card_exp_month": None, "card_exp_year": None,
        "terms_signature": body.terms_signature.strip(),
        "terms_signed_at": signed_at,
        "agreement_version": AGREEMENT_VERSION,
        "agreement_text": agreement_text(),
        "agreement_ip": _client_ip(request),
        "agreement_user_agent": request.headers.get("user-agent", ""),
        "charge_authorization_accepted_at": None,
        "is_active": True,
        "created_at": signed_at,
    }
    await db.shop_users.insert_one(su.copy())
    await db.invites.update_one({"token": token}, {"$set": {
        "status": "registered", "registered_at": signed_at, "shop_user_id": user_id,
    }})
    setup = None
    checkout_url = None
    if client and stripe_customer_id and FRONTEND_URL:
        try:
            setup = await asyncio.to_thread(
                create_setup_intent, client, customer_id=stripe_customer_id, shop_user_id=user_id,
            )
            checkout_url = await asyncio.to_thread(
                create_checkout_setup, client,
                customer_id=stripe_customer_id, shop_user_id=user_id,
                success_url=app_link(FRONTEND_URL, "/portal/setup-return?session_id={CHECKOUT_SESSION_ID}"),
                cancel_url=app_link(FRONTEND_URL, "/portal/setup-return?cancelled=1"),
            )
        except Exception as exc:
            stripe_error = str(exc)
            logger.error("[STRIPE] card setup was not created: %s", exc)
    token_jwt = make_portal_token(user_id)
    return {
        "shop_user_id": user_id, "token": token_jwt,
        "stripe_client_secret": (setup or {}).get("client_secret"),
        "stripe_checkout_url": checkout_url,
        "stripe_unavailable": not (setup or checkout_url),
        "stripe_error": stripe_error,
        "agreement_version": AGREEMENT_VERSION,
    }


async def _store_card(su: dict, card: dict) -> dict:
    await db.shop_users.update_one({"id": su["id"]}, {"$set": {**card, "updated_at": iso(now_utc())}})
    return await db.shop_users.find_one({"id": su["id"]}, {"_id": 0, "password_hash": 0})


@api.post("/portal/setup-intent")
async def portal_setup_intent(su=Depends(get_current_shop_user)):
    """Start or replace the card. Creates the Stripe customer if signup could not."""
    client = get_stripe()
    if client is None:
        raise HTTPException(400, "Stripe is not configured. Set STRIPE_SECRET_KEY to a test key.")
    customer_id = su.get("stripe_customer_id")
    if not customer_id:
        try:
            customer_id = await asyncio.to_thread(
                stripe_create_customer, client,
                email=su["email"], name=su.get("full_name") or su["email"], shop_id=su["shop_id"],
            )
        except Exception as exc:
            logger.error("[STRIPE] customer create failed: %s", exc)
            raise HTTPException(502, "Could not start card setup.")
        await db.shop_users.update_one({"id": su["id"]}, {"$set": {"stripe_customer_id": customer_id}})
    try:
        setup = await asyncio.to_thread(
            create_setup_intent, client, customer_id=customer_id, shop_user_id=su["id"],
        )
    except Exception as exc:
        logger.error("[STRIPE] setup intent failed: %s", exc)
        raise HTTPException(502, "Could not start card setup.")
    return {"client_secret": setup["client_secret"]}


@api.post("/portal/complete-setup-intent")
async def portal_complete_setup_intent(body: SetupIntentCompleteIn, su=Depends(get_current_shop_user)):
    """Save the card after Stripe redirects back from 3-D Secure."""
    client = get_stripe()
    if client is None:
        raise HTTPException(400, "Stripe is not configured.")
    try:
        intent = await asyncio.to_thread(retrieve_setup_intent, client, body.setup_intent_id)
    except Exception as exc:
        logger.error("[STRIPE] could not read setup intent: %s", exc)
        raise HTTPException(400, "That card setup could not be confirmed.")
    if intent.get("status") != "succeeded":
        raise HTTPException(400, "The card was not saved.")
    payment_method_id = _payment_method_id(intent)
    if not payment_method_id:
        raise HTTPException(400, "Stripe did not return a card.")
    customer_id = su.get("stripe_customer_id")
    if not customer_id:
        try:
            customer_id = await asyncio.to_thread(
                stripe_create_customer, client,
                email=su["email"], name=su.get("full_name") or su["email"], shop_id=su["shop_id"],
            )
        except Exception as exc:
            logger.error("[STRIPE] customer create failed: %s", exc)
            raise HTTPException(502, "Could not save that card.")
        await db.shop_users.update_one({"id": su["id"]}, {"$set": {"stripe_customer_id": customer_id}})
        su = {**su, "stripe_customer_id": customer_id}
    try:
        card = await asyncio.to_thread(
            save_payment_method, client,
            customer_id=customer_id, payment_method_id=payment_method_id,
        )
    except Exception as exc:
        logger.error("[STRIPE] could not save card: %s", exc)
        raise HTTPException(502, "Could not save that card.")
    fresh = await _store_card(su, card)
    return {
        "status": "complete",
        "shop_user": fresh,
        "needs_acceptance": not fresh.get("charge_authorization_accepted_at"),
        "acceptance_text": CHARGE_ACCEPTANCE_TEXT,
    }


@api.post("/portal/payment-method")
async def portal_save_payment_method(body: PaymentMethodIn, su=Depends(get_current_shop_user)):
    client = get_stripe()
    if client is None or not su.get("stripe_customer_id"):
        raise HTTPException(400, "Card setup is not available yet.")
    try:
        card = await asyncio.to_thread(
            save_payment_method, client,
            customer_id=su["stripe_customer_id"], payment_method_id=body.payment_method_id,
        )
    except Exception as exc:
        logger.error("[STRIPE] could not save card: %s", exc)
        raise HTTPException(502, "Could not save that card.")
    fresh = await _store_card(su, card)
    return {"status": "complete", "shop_user": fresh, "needs_acceptance": not fresh.get("charge_authorization_accepted_at")}


@api.post("/portal/accept-charge")
async def portal_accept_charge(body: AcceptChargeIn, request: Request, su=Depends(get_current_shop_user)):
    if not body.accepted:
        raise HTTPException(400, "Accept the card agreement to finish setup.")
    if not su.get("stripe_payment_method_id"):
        raise HTTPException(400, "Save a card before accepting.")
    accepted_at = iso(now_utc())
    await db.shop_users.update_one({"id": su["id"]}, {"$set": {
        "charge_authorization_accepted_at": accepted_at,
        "charge_authorization_text": CHARGE_ACCEPTANCE_TEXT,
        "charge_authorization_ip": _client_ip(request),
        "charge_authorization_user_agent": request.headers.get("user-agent", ""),
    }})
    shop = await db.shops.find_one({"id": su["shop_id"]}, {"_id": 0})
    fresh = await db.shop_users.find_one({"id": su["id"]}, {"_id": 0, "password_hash": 0})
    if shop and not su.get("charge_authorization_accepted_at"):
        await _send_signup_finished(shop, fresh["email"])
    return {"shop_user": fresh, "booking_link_token": (shop or {}).get("booking_link_token")}


@api.get("/portal/stripe-setup-status")
async def portal_stripe_setup_status(session_id: str, su=Depends(get_current_shop_user)):
    """Called after Stripe Checkout redirect to confirm and persist the payment method."""
    client = get_stripe()
    if client is None:
        raise HTTPException(400, "Stripe is not configured.")
    try:
        session = await asyncio.to_thread(retrieve_setup_checkout, client, session_id)
    except Exception as exc:
        raise HTTPException(500, f"Could not retrieve setup session: {exc}")
    setup_intent = session.get("setup_intent") or {}
    pm = setup_intent.get("payment_method") or {}
    pm_id = pm.get("id") if isinstance(pm, dict) else pm
    if not pm_id:
        return {"status": "incomplete", "session_status": session.get("status")}
    try:
        card = await asyncio.to_thread(
            save_payment_method, client,
            customer_id=su["stripe_customer_id"], payment_method_id=pm_id,
        )
    except Exception as exc:
        raise HTTPException(500, f"Could not attach payment method: {exc}")
    fresh = await _store_card(su, card)
    return {
        "status": "complete",
        "shop_user": fresh,
        "needs_acceptance": not fresh.get("charge_authorization_accepted_at"),
        "acceptance_text": CHARGE_ACCEPTANCE_TEXT,
    }

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
    return {
        "shop_user": su, "shop": shop, "setup": booking_gate(shop or {}, su),
        "site_url": FRONTEND_URL,
    }


@api.post("/portal/auth/forgot-password")
async def portal_forgot_password(body: ForgotPasswordIn):
    """Always the same reply. A one-time link is emailed when the account exists."""
    su = await db.shop_users.find_one({"email": body.email.lower()})
    if su:
        token = secrets.token_urlsafe(24)
        await db.password_resets.insert_one({
            "id": gen_id(), "token": token, "shop_user_id": su["id"],
            "email": su["email"], "created_at": iso(now_utc()),
            "expires_at": iso(now_utc() + timedelta(hours=1)), "used_at": None,
        })
        try:
            link = app_link(FRONTEND_URL, f"/portal/reset/{token}")
        except ValueError:
            link = None
            logger.error("[EMAIL] FRONTEND_URL is not set. Password reset was not emailed.")
        if link:
            await _send_booking_message({
                "to": su["email"],
                "subject": "Reset your CalibrationOS password",
                "html": f"<p>This link works once and expires in one hour.</p><p><a href=\"{link}\">Choose a new password</a></p>",
                "kind": "password_reset",
                "reply_to": owner_notify_email(),
            }, "shop")
    return {"ok": True, "message": "If that email has an account, a reset link is on the way."}


@api.post("/portal/auth/reset-password")
async def portal_reset_password(body: ResetPasswordIn):
    pw_problem = password_error(body.password)
    if pw_problem:
        raise HTTPException(400, pw_problem)
    reset = await db.password_resets.find_one({"token": body.token, "used_at": None})
    if not reset or reset.get("expires_at", "") < iso(now_utc()):
        raise HTTPException(400, "This reset link is not valid. Request a new one.")
    await db.shop_users.update_one(
        {"id": reset["shop_user_id"]},
        {"$set": {"password_hash": hash_password(body.password), "updated_at": iso(now_utc())}},
    )
    await db.password_resets.update_one({"id": reset["id"]}, {"$set": {"used_at": iso(now_utc())}})
    return {"ok": True}


@api.get("/public/agreement")
async def public_agreement():
    return {
        "version": AGREEMENT_VERSION,
        "paragraphs": AGREEMENT_PARAGRAPHS,
        "sections": AGREEMENT_SECTIONS,
        "acceptance": CHARGE_ACCEPTANCE_TEXT,
    }


@api.get("/public/site")
async def public_site():
    return {"owner_phone": OWNER_PHONE, "owner_email": owner_notify_email(), "site_url": FRONTEND_URL}


def _signup_limited(request: Request, kind: str, limit: int) -> None:
    ip = _client_ip(request) or "unknown"
    if rate_limit_exceeded(f"{kind}:{ip}", limit=limit, window_seconds=SIGNUP_WINDOW_SECONDS):
        raise HTTPException(429, "Too many attempts from this network. Wait an hour and try again, or call the office.")


async def _send_signup_finished(shop: dict, email: str) -> None:
    """Welcome the shop and tell the owner. Shop mail still follows SHOP_EMAILS_ENABLED."""
    try:
        booking_url = app_link(FRONTEND_URL, f"/book/{shop['booking_link_token']}")
    except ValueError:
        booking_url = f"/book/{shop['booking_link_token']}"
        logger.error("[EMAIL] FRONTEND_URL is not set, welcome email has a relative booking link.")
    await _send_booking_message({
        "to": email,
        "subject": f"You're set — {shop['name']}",
        "html": welcome_email_html(shop["name"], booking_url),
        "kind": "welcome",
        "reply_to": owner_notify_email(),
        "meta": {"shop_id": shop["id"]},
    }, "shop")
    await send_email(
        owner_notify_email(),
        f"{shop['name']} finished signup",
        f"<p>{shop['name']} finished signup. Booking link: {booking_url}</p>",
        kind="signup_finished",
        meta={"shop_id": shop["id"]},
    )


def _payment_method_id(intent: dict) -> Optional[str]:
    method = intent.get("payment_method")
    if isinstance(method, dict):
        return method.get("id")
    if isinstance(method, str) and method:
        return method
    return None


@api.post("/public/card-setup")
async def public_card_setup(request: Request):
    """SetupIntent for the signup page. No shop is created."""
    _signup_limited(request, "card-setup", CARD_SETUP_ATTEMPT_LIMIT)
    client = get_stripe()
    if client is None:
        return {
            "stripe_unavailable": True,
            "message": "Card setup is not available yet. The account can still be created, and the card is added from Settings after you log in.",
        }
    try:
        setup = await asyncio.to_thread(create_anonymous_setup_intent, client)
    except Exception as exc:
        logger.error("[STRIPE] signup setup intent failed: %s", exc)
        return {
            "stripe_unavailable": True,
            "message": "Card setup did not start. You can add the card from Settings after you log in.",
        }
    return {"client_secret": setup.get("client_secret"), "setup_intent_id": setup.get("id"), "stripe_unavailable": False}


@api.post("/public/card-setup/complete")
async def public_card_setup_complete(body: SetupIntentCompleteIn, request: Request):
    """Payment method id after a card redirect. The shop is created by the next call."""
    _signup_limited(request, "card-setup", CARD_SETUP_ATTEMPT_LIMIT)
    client = get_stripe()
    if client is None:
        raise HTTPException(400, "Stripe is not configured.")
    try:
        intent = await asyncio.to_thread(retrieve_setup_intent, client, body.setup_intent_id)
    except Exception as exc:
        logger.error("[STRIPE] could not read setup intent: %s", exc)
        raise HTTPException(400, "That card setup could not be confirmed.")
    if intent.get("status") != "succeeded":
        raise HTTPException(400, "The card was not saved.")
    payment_method_id = _payment_method_id(intent)
    if not payment_method_id:
        raise HTTPException(400, "Stripe did not return a card.")
    return {"payment_method_id": payment_method_id}


@api.post("/public/shops")
async def public_create_shop(body: PublicShopIn, request: Request):
    """Create the shop, the shop user, and the signed agreement. Returns a portal JWT."""
    _signup_limited(request, "public-shop", SIGNUP_ATTEMPT_LIMIT)
    if not (body.contact_name or "").strip():
        raise HTTPException(400, {"contact_name": "Contact name is required."})
    if not body.terms_agreed or not (body.terms_signature or "").strip():
        raise HTTPException(400, "Sign the agreement to create the shop.")
    if not body.charge_accepted:
        raise HTTPException(400, "Accept the card charge terms to create the shop.")
    pw_problem = password_error(body.password)
    if pw_problem:
        raise HTTPException(400, pw_problem)
    errors = shop_contact_errors(
        name=body.shop_name, phone=body.mobile, email=body.email, address=body.address,
    )
    if errors:
        raise HTTPException(400, errors)
    email = canonical_email(body.email)
    geo = await _checked_shop_address(
        body.address, body.address_confirmed, body.confirmed_address, body.place_id,
    )
    shops, users = await _duplicate_lists()
    dupes = duplicate_fields(body.shop_name, email, shops, users)
    if "email" in dupes:
        raise HTTPException(status_code=409, detail={
            "code": "duplicate_email",
            "message": "That email already has a shop account. Log in, or reset the password.",
            "login_path": "/portal/login",
            "forgot_path": "/portal/forgot",
        })
    if "name" in dupes and not body.second_location:
        raise HTTPException(status_code=409, detail={
            "code": "duplicate_name",
            "message": "A shop with this name is already on file. Check the box if this is a second location.",
        })

    client = get_stripe()
    card = None
    stripe_error = None
    stripe_unavailable = client is None
    if client is not None and not body.payment_method_id:
        raise HTTPException(400, "Save a card to create the shop.")
    shop_id = gen_id()
    user_id = gen_id()
    if client is not None and body.payment_method_id:
        try:
            customer_id = await asyncio.to_thread(
                stripe_create_customer, client,
                email=email, name=body.contact_name.strip(), shop_id=shop_id,
            )
            card = await asyncio.to_thread(
                save_payment_method, client,
                customer_id=customer_id, payment_method_id=body.payment_method_id,
            )
            card["stripe_customer_id"] = customer_id
        except Exception as exc:
            logger.error("[STRIPE] signup card was not saved: %s", exc)
            raise HTTPException(502, "Could not save that card. Try another card, or call the office.")

    signed_at = iso(now_utc())
    shop = {
        "id": shop_id,
        "name": body.shop_name.strip(),
        "contact_name": body.contact_name.strip(),
        "contact_phone": normalize_phone(body.mobile),
        "contact_email": email,
        "address": geo.get("formatted_address") or body.address.strip(),
        "formatted_address": geo.get("formatted_address"),
        "city": None, "state": "AZ", "zip": None,
        "lat": geo["lat"], "lng": geo["lng"],
        "geocode_source": geo.get("source") or "google",
        "zone": detect_zone(geo["lng"]),
        "place_id": body.place_id,
        "booking_link_token": secrets.token_hex(16),
        "pricing_tier": "standard",
        "terms_signed_at": signed_at,
        "terms_signed_by": body.terms_signature.strip(),
        "requires_billing_setup": True,
        "status": "active",
        "signup_source": "self_serve",
        "second_location": bool(body.second_location),
        "flagged": bool(body.second_location),
        "flag_reason": "second_location" if body.second_location else None,
        "notes": None,
        "created_at": signed_at,
        "updated_at": signed_at,
    }
    accepted_at = signed_at if card else None
    su = {
        "id": user_id,
        "email": email,
        "full_name": body.contact_name.strip(),
        "password_hash": hash_password(body.password),
        "shop_id": shop_id,
        "shop_name": shop["name"],
        "stripe_customer_id": (card or {}).get("stripe_customer_id"),
        "stripe_payment_method_id": (card or {}).get("stripe_payment_method_id"),
        "card_brand": (card or {}).get("card_brand"),
        "card_last4": (card or {}).get("card_last4"),
        "card_exp_month": (card or {}).get("card_exp_month"),
        "card_exp_year": (card or {}).get("card_exp_year"),
        "terms_signature": body.terms_signature.strip(),
        "terms_signed_at": signed_at,
        "agreement_version": AGREEMENT_VERSION,
        "agreement_text": agreement_text(),
        "agreement_ip": _client_ip(request),
        "agreement_user_agent": request.headers.get("user-agent", ""),
        "charge_authorization_accepted_at": accepted_at,
        "charge_authorization_text": CHARGE_ACCEPTANCE_TEXT if accepted_at else None,
        "charge_authorization_ip": _client_ip(request) if accepted_at else None,
        "charge_authorization_user_agent": request.headers.get("user-agent", "") if accepted_at else None,
        "is_active": True,
        "created_at": signed_at,
    }
    await db.shops.insert_one(shop.copy())
    await db.shop_users.insert_one(su.copy())
    saved_shop = await db.shops.find_one({"id": shop_id}, {"_id": 0})
    if not saved_shop:
        logger.error("[SHOP SIGNUP] id %s was not readable after insert", shop_id)
        raise HTTPException(500, "Could not save that shop. Call (480) 269-1329.")
    review_url = f"{PUBLIC_SITE_URL}/requests"
    html = (
        f"<p>{shop['contact_name']} created {shop['name']}.</p>"
        f"<ul><li>{shop['contact_phone']}</li><li>{shop['contact_email']}</li><li>{shop['address']}</li></ul>"
        f"<p><a href=\"{review_url}\">Review new shops</a></p>"
    )
    await send_email(
        owner_notify_email(),
        f"New shop — {shop['name']}",
        html, kind="shop_request", meta={"shop_id": shop_id},
    )
    if accepted_at:
        await _send_signup_finished(shop, email)
    token = make_portal_token(user_id)
    public_user = {k: v for k, v in su.items() if k != "password_hash"}
    return {
        "token": token,
        "shop_user_id": user_id,
        "shop_id": shop_id,
        "shop_name": shop["name"],
        "full_name": su["full_name"],
        "has_payment_method": bool(card),
        "stripe_unavailable": stripe_unavailable,
        "stripe_error": stripe_error,
        "booking_open": booking_gate(shop, public_user)["allowed"],
        "shop_user": public_user,
        "shop": shop,
    }


@api.post("/public/contact")
async def public_contact(body: ContactIn):
    if not (body.name or "").strip() or not (body.message or "").strip():
        raise HTTPException(400, "Name and message are required.")
    if not canonical_email(body.email):
        raise HTTPException(400, "Enter a valid email.")
    html = (
        f"<p>From {body.name} ({canonical_email(body.email)})</p>"
        f"<p>Shop: {body.shop_name or '—'}</p><p>Phone: {body.phone or '—'}</p>"
        f"<p>{body.message}</p>"
    )
    log = await send_email(owner_notify_email(), f"Website message from {body.name}", html, kind="contact")
    return {"ok": True, "delivered": bool(log.get("delivered")), "message": "Caleb has your note."}


@api.post("/public/shop-requests")
async def create_shop_request(body: ShopRequestIn):
    if not (body.contact_name or "").strip():
        raise HTTPException(400, {"contact_name": "Contact name is required."})
    errors = shop_contact_errors(
        name=body.shop_name, phone=body.mobile, email=body.email, address=body.address,
    )
    if errors:
        raise HTTPException(400, errors)
    geo = await _checked_shop_address(
        body.address, body.address_confirmed, body.confirmed_address, body.place_id,
    )
    record = {
        "id": gen_id(),
        "shop_name": body.shop_name.strip(),
        "contact_name": body.contact_name.strip(),
        "mobile": normalize_phone(body.mobile),
        "email": canonical_email(body.email),
        "address": geo.get("formatted_address"),
        "formatted_address": geo.get("formatted_address"),
        "lat": geo["lat"], "lng": geo["lng"],
        "place_id": body.place_id,
        "zone": detect_zone(geo["lng"]),
        "status": "pending",
        "created_at": iso(now_utc()),
    }
    await db.shop_requests.insert_one(record.copy())
    saved = await db.shop_requests.find_one({"id": record["id"]}, {"_id": 0})
    if not saved:
        logger.error("[SHOP REQUEST] id %s was not readable after insert", record["id"])
        raise HTTPException(500, "Could not save that request. Call (480) 269-1329.")
    html = (
        f"<p>{record['contact_name']} at {record['shop_name']} asked for a shop account.</p>"
        f"<ul><li>{record['mobile']}</li><li>{record['email']}</li><li>{record['address']}</li></ul>"
        f"<p>Open Requests in CalibrationOS to approve and send the invite.</p>"
    )
    await send_email(
        owner_notify_email(),
        f"Shop account request — {record['shop_name']}",
        html, kind="shop_request", meta={"request_id": record["id"]},
    )
    return {"ok": True, "message": "Caleb will send your setup link shortly."}


_SHOP_REQUEST_FIELDS = (
    "id", "shop_name", "contact_name", "mobile", "email", "address",
    "formatted_address", "lat", "lng", "place_id", "zone", "status",
    "created_at", "shop_id", "invite_id", "decided_at",
)


def _public_shop_request(doc: dict) -> dict:
    """Plain JSON fields. Drops Mongo types the owner page does not render."""
    out = {}
    for key in _SHOP_REQUEST_FIELDS:
        if key not in doc or doc[key] is None:
            continue
        value = doc[key]
        if key in ("lat", "lng"):
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
        out[key] = value
    return out


@api.get("/shop-requests")
async def list_shop_requests(tech=Depends(require_owner)):
    """Every shop account request, newest first.

    Do not sort inside the query. A sorted find can use an index and leave out
    documents that are not in that index, which is an empty page for the owner
    even though the insert succeeded. Read the collection, then order here.
    """
    docs = await db.shop_requests.find({}, {"_id": 0}).to_list(200)
    docs.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    rows = [_public_shop_request(doc) for doc in docs]
    logger.info("[SHOP REQUEST] owner list %s", len(rows))
    return rows


@api.post("/shop-requests/{request_id}/approve")
async def approve_shop_request(request_id: str, tech=Depends(require_owner)):
    """Create the shop and send the invite in one step."""
    req = await db.shop_requests.find_one({"id": request_id}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Request not found")
    if req.get("status") != "pending":
        raise HTTPException(400, f"Request is already {req.get('status')}.")
    data = ShopIn(
        name=req["shop_name"], contact_name=req.get("contact_name"),
        contact_phone=req["mobile"], contact_email=req["email"],
        address=req["address"], address_confirmed=True, confirmed_address=req["address"],
        place_id=req.get("place_id"), acknowledge_duplicate=True,
    )
    geo = {
        "lat": req["lat"], "lng": req["lng"], "formatted_address": req["address"],
        "in_metro": True, "fallback": False,
    }
    shop = _shop_document(data, geo)
    await db.shops.insert_one(shop.copy())
    invite = await _issue_invite(shop, req["email"])
    await db.shop_requests.update_one({"id": request_id}, {"$set": {
        "status": "approved", "shop_id": shop["id"], "invite_id": invite["id"],
        "decided_at": iso(now_utc()),
    }})
    return {"shop": shop, "invite": invite}


@api.post("/shop-requests/{request_id}/decline")
async def decline_shop_request(request_id: str, tech=Depends(require_owner)):
    req = await db.shop_requests.find_one({"id": request_id})
    if not req:
        raise HTTPException(404, "Request not found")
    if req.get("status") != "pending":
        raise HTTPException(400, f"Request is already {req.get('status')}.")
    await db.shop_requests.update_one({"id": request_id}, {"$set": {
        "status": "declined", "decided_at": iso(now_utc()),
    }})
    return {"ok": True}


@api.get("/new-shops")
async def list_new_shops(tech=Depends(require_owner)):
    """Shops that created themselves. Pending requests stay on /shop-requests."""
    docs = await db.shops.find({"signup_source": "self_serve"}, {"_id": 0}).to_list(200)
    docs.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return docs


@api.post("/shops/{shop_id}/flag")
async def flag_shop(shop_id: str, body: ShopFlagIn, tech=Depends(require_owner)):
    shop = await db.shops.find_one({"id": shop_id})
    if not shop:
        raise HTTPException(404, "Shop not found")
    await db.shops.update_one({"id": shop_id}, {"$set": {
        "flagged": body.flagged,
        "flagged_at": iso(now_utc()) if body.flagged else None,
        "updated_at": iso(now_utc()),
    }})
    return {"id": shop_id, "flagged": body.flagged}


@api.post("/shops/{shop_id}/suspend")
async def suspend_shop(shop_id: str, body: ShopSuspendIn, tech=Depends(require_owner)):
    shop = await db.shops.find_one({"id": shop_id})
    if not shop:
        raise HTTPException(404, "Shop not found")
    status_value = "suspended" if body.suspended else "active"
    await db.shops.update_one({"id": shop_id}, {"$set": {
        "status": status_value, "updated_at": iso(now_utc()),
    }})
    return {"id": shop_id, "status": status_value}


@api.get("/billing/late-fees")
async def list_late_fees(tech=Depends(require_owner)):
    events = await db.billing_events.find({"kind": "late_fee"}, {"_id": 0}).sort("applied_at", -1).to_list(200)
    return {"events": events}


@api.post("/billing/late-fees/run")
async def run_late_fees_now(tech=Depends(require_owner)):
    return await run_late_fee_sweep()


@api.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    secret = _env("STRIPE_WEBHOOK_SECRET")
    if not secret:
        logger.error("[STRIPE] STRIPE_WEBHOOK_SECRET is not set. Refusing unsigned webhook.")
        raise HTTPException(503, "Webhook secret is not configured.")
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        event = stripe_sdk.Webhook.construct_event(payload, signature, secret)
    except Exception as exc:
        logger.warning("[STRIPE] webhook signature failed: %s", exc)
        raise HTTPException(400, "Invalid webhook signature.")
    data = event["data"]["object"]
    kind = event["type"]
    if kind.startswith("payment_intent."):
        await _apply_payment_intent_event(kind, data)
    elif kind.startswith("invoice."):
        await _apply_invoice_event(kind, data)
    return {"received": True}

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
        "status": {"$nin": ["cancelled", "declined"]},
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
        # Real lookups hit drive_time_cache (rounded coords and departure bucket). Run them together
        # so a cold cache does not wait on one Routes call per other-shop job.
        dm = await get_drive_time(
            origin_lat, origin_lng, j["job_lat"], j["job_lng"],
            depart_at=datetime.fromisoformat(str(j["scheduled_start"]).replace("Z", "+00:00")),
            mode=ESSENTIALS,
        )
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
    shop = await db.shops.find_one({"id": su["shop_id"]})
    if shop and shop.get("status") == "suspended":
        raise HTTPException(403, "This shop is suspended and cannot book.")
    if not shop or shop.get("status") != "active":
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
    if not stripe_configured():
        raise HTTPException(400, "Stripe is not configured with a test key. A live key stays unused until BILLING_ENABLED is on.")

    try:
        pi = await asyncio.to_thread(
            stripe_sdk.PaymentIntent.create,
            amount=cents(job["price"]), currency="usd",
            customer=shop_user["stripe_customer_id"],
            payment_method=shop_user["stripe_payment_method_id"],
            off_session=True, confirm=True,
            description=(f"CalibrationOS — {job.get('calibration_label', 'ADAS Calibration')} — "
                         f"{job.get('vehicle_year')} {job.get('vehicle_make')} {job.get('vehicle_model')}"),
            receipt_email=None,
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

@api.get("/email-outbox")
async def list_email_outbox(tech=Depends(require_owner)):
    """Read-only list of emails that were held instead of sent."""
    store = getattr(db, "email_outbox", None)
    if store is None:
        return []
    try:
        rows = await store.find({}, {"_id": 0}).to_list(200)
    except Exception as exc:
        logger.warning("email outbox unreadable: %s", exc)
        return []
    rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    return [
        {
            "id": row.get("id"),
            "to": row.get("to"),
            "subject": row.get("subject"),
            "body": row.get("body") or "",
            "created_at": row.get("created_at"),
            "audience": row.get("audience"),
            "kind": row.get("kind"),
        }
        for row in rows[:100]
    ]

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

    # Routing defaults for the owner. Never overwrites a home address they already saved,
    # and does not move existing appointment times.
    owner_doc = await db.technicians.find_one({"role": "owner"})
    if owner_doc:
        routing_updates = owner_routing_updates(owner_doc)
        if routing_updates:
            await db.technicians.update_one({"id": owner_doc["id"]}, {"$set": routing_updates})
        await db.jobs.update_many(
            {"$or": [{"technician_id": None}, {"technician_id": {"$exists": False}}]},
            {"$set": {"technician_id": owner_doc["id"]}},
        )

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

    # Contractors stay off the automatic route. Existing jobs keep their times.
    for person in await db.technicians.find({"role": "contractor"}, {"_id": 0}).to_list(20):
        routing_updates = contractor_routing_updates(person)
        if routing_updates:
            await db.technicians.update_one({"id": person["id"]}, {"$set": routing_updates})

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
                "geocode_source": "fallback",
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

    await ensure_holidays()

def security_self_check():
    """Log deployment security posture at startup; fail closed in production on an unsafe secret."""
    warnings = []
    if JWT_SECRET == _DEV_JWT_SECRET:
        warnings.append("JWT_SECRET is the public dev default — set a strong random JWT_SECRET.")
    from safety import stripe_key_mode
    key_mode = stripe_key_mode(stripe_secret())
    if key_mode == "live" and not billing_enabled():
        logger.error(
            "[STRIPE] A live key is set but BILLING_ENABLED is off. That key will not be used. "
            "Use sk_test_ or rk_test_ until you turn billing on."
        )
        warnings.append("Live Stripe key ignored until BILLING_ENABLED is on. Use a test key.")
    elif not stripe_configured():
        warnings.append("STRIPE_SECRET_KEY is not a test key — card setup and charges stay off until sk_test_ or rk_test_ is set.")
    if not shop_emails_enabled():
        logger.info("[EMAIL] SHOP_EMAILS_ENABLED is off. Shop and customer mail is written to email_outbox.")
    if not billing_enabled():
        logger.info("[BILLING] BILLING_ENABLED is off. Completing a job will not charge a card, and late fees will not run.")
    sender_problem = sender_email_problem(SENDER_EMAIL)
    if sender_problem:
        logger.error("[EMAIL] %s", sender_problem)
        warnings.append(sender_problem)
    if not _env("FRONTEND_URL"):
        logger.info(
            "[EMAIL] FRONTEND_URL is not set. Invite, reset, and booking links use %s.",
            FRONTEND_URL,
        )
    if cors_allow_origins() == ["*"]:
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


def _stripe_obj(data) -> dict:
    if isinstance(data, dict):
        return data
    if hasattr(data, "to_dict"):
        return data.to_dict()
    return {}


async def _apply_payment_intent_event(kind: str, raw) -> None:
    data = _stripe_obj(raw)
    job_id = (data.get("metadata") or {}).get("job_id")
    if not job_id:
        return
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        return
    if kind == "payment_intent.succeeded":
        if job.get("charged_at"):
            return
        await db.jobs.update_one({"id": job_id}, {"$set": {
            "charged_at": iso(now_utc()),
            "payment_status": "paid",
            "charge_method": "stripe",
            "stripe_payment_intent_id": data.get("id"),
            "charged_amount": round((data.get("amount") or 0) / 100, 2),
        }})
        logger.info("[STRIPE] payment_intent.succeeded for job %s", job_id)
        return
    if kind in ("payment_intent.payment_failed", "payment_intent.requires_action"):
        err = data.get("last_payment_error") or {}
        message = err.get("message") or (
            "Card requires authentication. Ask the shop to update the card."
            if kind.endswith("requires_action") else "Card declined."
        )
        await db.jobs.update_one({"id": job_id}, {"$set": {
            "payment_status": "payment_failed",
            "charge_error": message,
            "charge_error_at": iso(now_utc()),
            "stripe_payment_intent_id": data.get("id"),
        }})
        shop = await db.shops.find_one({"id": job.get("shop_id")}) or {"name": job.get("shop_name"), "id": job.get("shop_id")}
        fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
        await _notify_payment_failed(fresh, shop, message)
        logger.warning("[STRIPE] %s for job %s: %s", kind, job_id, message)


async def _apply_invoice_event(kind: str, raw) -> None:
    data = _stripe_obj(raw)
    meta = data.get("metadata") or {}
    job_id = meta.get("job_id")
    if not job_id:
        return
    if meta.get("kind") == "late_fee":
        if kind in ("invoice.paid", "invoice.payment_succeeded"):
            await db.jobs.update_one({"id": job_id}, {"$set": {"late_fee_paid_at": iso(now_utc())}})
        return
    if kind in ("invoice.paid", "invoice.payment_succeeded"):
        await db.jobs.update_one({"id": job_id}, {"$set": {
            "payment_status": "paid",
            "charged_at": iso(now_utc()),
            "invoice_status": "paid",
            "stripe_invoice_id": data.get("id") or None,
        }})
        logger.info("[STRIPE] invoice paid for job %s", job_id)
    elif kind == "invoice.payment_failed":
        await db.jobs.update_one({"id": job_id}, {"$set": {
            "payment_status": "payment_failed",
            "invoice_status": "payment_failed",
            "charge_error": "Invoice payment failed.",
            "charge_error_at": iso(now_utc()),
        }})
        job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
        shop = await db.shops.find_one({"id": (job or {}).get("shop_id")}) or {"name": "Shop"}
        if job:
            await _notify_payment_failed(job, shop, "Invoice payment failed.")
    elif kind == "invoice.finalized":
        await db.jobs.update_one({"id": job_id}, {"$set": {
            "stripe_invoice_id": data.get("id"),
            "invoice_url": data.get("hosted_invoice_url"),
            "invoice_status": data.get("status") or "open",
        }})


async def run_late_fee_sweep() -> dict:
    """Add one $25 fee to each unpaid invoice-mode job past the 7-day grace.

    Safe to run every hour. A job that already has late_fee_applied_at is skipped,
    and the write itself requires that field to be missing. The sweep does nothing
    while BILLING_ENABLED is off.
    """
    now = now_utc()
    if not billing_enabled():
        logger.info("[BILLING] late fee sweep skipped. BILLING_ENABLED is off.")
        return {
            "day": business_date(now).isoformat(), "applied": 0, "skipped": True,
            "reason": "BILLING_ENABLED is off",
        }
    day = business_date(now).isoformat()
    jobs = await db.jobs.find({
        "status": "complete",
        "payment_mode": INVOICE_MODE,
    }, {"_id": 0}).to_list(2000)
    applied = []
    for job in jobs:
        updated = apply_late_fee(job, now)
        if not updated:
            continue
        result = await db.jobs.update_one(
            {"id": job["id"], "late_fee_applied_at": {"$exists": False}},
            {"$set": {
                "late_fee": updated["late_fee"],
                "late_fee_applied_at": updated["late_fee_applied_at"],
                "late_fee_reason": updated["late_fee_reason"],
            }},
        )
        if getattr(result, "modified_count", 1) == 0:
            continue
        event = {
            "id": gen_id(), "kind": "late_fee", "job_id": job["id"],
            "shop_id": job.get("shop_id"), "shop_name": job.get("shop_name"),
            "amount": updated["late_fee"], "applied_at": updated["late_fee_applied_at"],
            "reason": updated["late_fee_reason"],
        }
        await db.billing_events.insert_one(event.copy())
        applied.append(event)
        logger.info("[BILLING] $25 late fee on job %s (%s)", job["id"], job.get("shop_name"))
        shop = await db.shops.find_one({"id": job.get("shop_id")}) or {}
        note = (
            f"<p>A $25 late fee was added to the invoice for {job.get('shop_name')} "
            f"({job.get('calibration_label')}). It was unpaid 7 days after the job was completed.</p>"
        )
        await send_email(owner_notify_email(), f"Late fee — {job.get('shop_name')}", note, kind="late_fee")
        shop_email = shop.get("contact_email") or job.get("notification_email")
        if shop_email:
            await _send_booking_message({
                "to": shop_email,
                "subject": "A $25 late fee was added",
                "html": note,
                "kind": "late_fee_shop",
                "reply_to": owner_notify_email(),
            }, "shop")
        client = get_stripe()
        shop_user = await _shop_user_for(job.get("shop_id"))
        if client and shop_user and shop_user.get("stripe_customer_id") and not job.get("stripe_late_fee_invoice_id"):
            try:
                created = await asyncio.to_thread(
                    create_late_fee_invoice, client,
                    customer_id=shop_user["stripe_customer_id"], job=job,
                )
                await db.jobs.update_one({"id": job["id"]}, {"$set": {
                    "stripe_late_fee_invoice_id": created["stripe_invoice_id"],
                }})
            except Exception as exc:
                logger.error("[BILLING] late-fee invoice failed for %s: %s", job["id"], exc)
    logger.info("[BILLING] late fee sweep %s applied %s", day, len(applied))
    await db.billing_runs.update_one(
        {"_id": f"late-fee-{day}"},
        {"$set": {"day": day, "applied": len(applied), "at": iso(now)}},
        upsert=True,
    )
    return {"day": day, "applied": len(applied)}


async def _late_fee_loop():
    await asyncio.sleep(30)
    while True:
        try:
            await run_late_fee_sweep()
        except Exception:
            logger.exception("[BILLING] late fee sweep failed")
        await asyncio.sleep(60 * 60)


@app.on_event("startup")
async def startup():
    security_self_check()
    await seed_data()
    await load_settings()
    asyncio.create_task(_late_fee_loop())
    # Essentials rows live up to 7 days. Pro rows set expires_at two hours out and the
    # reader ignores them after that. Drop the old 2-day cached_at TTL if it is still there,
    # because it would delete a 7-day row early. A conflicting drop is not fatal.
    try:
        await db.drive_time_cache.drop_index("cached_at_1")
    except Exception:
        pass
    await db.drive_time_cache.create_index("expires_at", expireAfterSeconds=0)

class DayOffIn(BaseModel):
    start: str
    end: Optional[str] = None
    label: str = "Vacation"


class DayOffToggle(BaseModel):
    blocked: bool


def _owner_action_job(job: dict) -> dict:
    return {
        "id": job.get("id"),
        "shop_name": job.get("shop_name"),
        "when": job.get("scheduled_start"),
        "vehicle": _vehicle_line(job),
        "address": job.get("job_address"),
        "calibration": job.get("calibration_label"),
        "price": job.get("price"),
        "status": job.get("status"),
    }


async def _assess_saved_link(token: str):
    claims = token_claims(JWT_SECRET, token)
    record = None
    store = getattr(db, "owner_action_tokens", None)
    if claims and store is not None:
        record = await store.find_one({"id": claims["nonce"]}, {"_id": 0})
    decision = assess_owner_link(JWT_SECRET, token, record, now_utc())
    job = None
    if decision.get("ok"):
        job = await db.jobs.find_one({"id": decision["job_id"]}, {"_id": 0})
        if not job:
            decision = {"ok": False, "error": "This link is not valid.", "consumes": False}
    return decision, record, job


@api.get("/public/owner-action/{token}")
async def preview_owner_action(token: str):
    """Show the job. Does not approve, decline, or use up the link."""
    decision, _record, job = await _assess_saved_link(token)
    if not decision["ok"]:
        raise HTTPException(400, decision["error"])
    return {
        "action": decision["action"],
        "requires_confirm": True,
        "job": _owner_action_job(job),
    }


@api.post("/public/owner-action/{token}")
async def confirm_owner_action(token: str):
    """Use the link once. The shop is emailed when the job actually changes."""
    decision, record, job = await _assess_saved_link(token)
    if not decision["ok"]:
        raise HTTPException(400, decision["error"])
    used = mark_used(record, now_utc())
    store = db.owner_action_tokens
    claim = getattr(store, "find_one_and_update", None)
    if claim is not None:
        stored = await claim(
            {"id": record["id"], "used_at": None},
            {"$set": {"used_at": used["used_at"]}},
        )
        if not stored:
            raise HTTPException(400, "This link was already used.")
    else:
        await store.update_one({"id": record["id"]}, {"$set": {"used_at": used["used_at"]}})
    action = decision["action"]
    status = job.get("status")
    changed = False
    if action == "approve" and status == "requested":
        await db.jobs.update_one({"id": job["id"]}, {"$set": {
            "status": "booked",
            "approved_at": used["used_at"],
            "approved_by": "owner-link",
            "approval_reason": None,
            "declined_at": None,
            "updated_at": used["used_at"],
        }})
        changed = True
        message = "Approved. The shop will get an email."
    elif action == "approve":
        message = "This job is already confirmed." if status == "booked" else "This job can no longer be approved."
    elif action == "decline" and status in ("requested", "booked"):
        await db.jobs.update_one({"id": job["id"]}, {"$set": {
            "status": "declined",
            "declined_at": used["used_at"],
            "approved_at": None,
            "approved_by": None,
            "updated_at": used["used_at"],
        }})
        changed = True
        message = "Declined. The time is free."
    else:
        message = "This job can no longer be declined."
    fresh = await db.jobs.find_one({"id": job["id"]}, {"_id": 0})
    if changed:
        await email_shop_event(fresh, await _shop_for_job(fresh), "approved" if action == "approve" else "declined")
    return {"ok": True, "message": message, "job": _owner_action_job(fresh or job)}


def _day_off_public(row: dict) -> dict:
    return {key: row.get(key) for key in ("key", "label", "kind", "blocked", "start", "end")}


@api.get("/days-off")
async def get_days_off(tech=Depends(require_owner)):
    """Holidays, custom days off, and jobs already sitting on a closed day."""
    await ensure_holidays()
    records = sorted(await load_days_off(), key=lambda row: (row.get("start") or "", row.get("label") or ""))
    conflicts = []
    jobs_store = getattr(db, "jobs", None)
    if jobs_store is not None:
        try:
            rows = await jobs_store.find({"day_off_conflict": True}, {"_id": 0}).to_list(200)
        except Exception:
            rows = []
        for job in rows:
            if job.get("status") in ("cancelled", "declined", "complete"):
                continue
            conflicts.append({
                "id": job.get("id"),
                "shop_name": job.get("shop_name"),
                "when": job.get("scheduled_start"),
                "vehicle": _vehicle_line(job),
                "address": job.get("job_address"),
                "status": job.get("status"),
                "label": job.get("day_off_label"),
            })
    return {"days": [_day_off_public(row) for row in records], "conflicts": conflicts}


@api.put("/days-off/{key}")
async def toggle_day_off(key: str, body: DayOffToggle, tech=Depends(require_owner)):
    await ensure_holidays()
    store = getattr(db, "days_off", None)
    if store is None:
        raise HTTPException(400, "Days off are not available.")
    row = await store.find_one({"key": key}, {"_id": 0})
    if not row:
        raise HTTPException(404, "That day is not on the list.")
    was_blocked = bool(row.get("blocked", True))
    await store.update_one({"key": key}, {"$set": {"blocked": body.blocked}})
    fresh = await store.find_one({"key": key}, {"_id": 0}) or {**row, "blocked": body.blocked}
    span = _dates_between(date.fromisoformat(fresh["start"]), date.fromisoformat(fresh.get("end") or fresh["start"]))
    if body.blocked and not was_blocked:
        await flag_jobs_on_dates(span, fresh.get("label") or "a day off")
    if not body.blocked and was_blocked:
        await clear_day_off_flags(span)
    return _day_off_public(fresh)


@api.post("/days-off")
async def add_day_off(body: DayOffIn, tech=Depends(require_owner)):
    try:
        start, end = parse_range(body.start, body.end)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    label = (body.label or "").strip() or "Vacation"
    row = {
        "key": "custom-" + secrets.token_hex(6),
        "label": label,
        "kind": "custom",
        "blocked": True,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    store = getattr(db, "days_off", None)
    if store is None:
        raise HTTPException(400, "Days off are not available.")
    await store.insert_one(dict(row))
    await flag_jobs_on_dates(_dates_between(start, end), label)
    return row


@api.delete("/days-off/{key}")
async def delete_day_off(key: str, tech=Depends(require_owner)):
    store = getattr(db, "days_off", None)
    if store is None:
        raise HTTPException(400, "Days off are not available.")
    row = await store.find_one({"key": key}, {"_id": 0})
    if not row:
        raise HTTPException(404, "That day is not on the list.")
    if row.get("kind") == "holiday":
        raise HTTPException(400, "Holidays stay on the list. Turn the day off if you are working.")
    if hasattr(store, "delete_one"):
        await store.delete_one({"key": key})
    else:
        await store.update_one({"key": key}, {"$set": {"blocked": False}})
    span = _dates_between(date.fromisoformat(row["start"]), date.fromisoformat(row.get("end") or row["start"]))
    await clear_day_off_flags(span)
    return {"deleted": key}


def _pin_row_shop(shop: dict) -> dict:
    return {
        "id": shop.get("id"),
        "name": shop.get("name"),
        "address": shop.get("address"),
        "lat": shop.get("lat"),
        "lng": shop.get("lng"),
    }


def _pin_row_job(job: dict) -> dict:
    return {
        "id": job.get("id"),
        "shop_name": job.get("shop_name"),
        "address": job.get("job_address"),
        "when": job.get("scheduled_start"),
        "vehicle": _vehicle_line(job),
        "status": job.get("status"),
        "lat": job.get("job_lat"),
        "lng": job.get("job_lng"),
    }


class PinRecheckIn(BaseModel):
    kind: Literal["shop", "job"]
    id: str


@api.post("/address-pins/recheck")
async def recheck_address_pin(body: PinRecheckIn, tech=Depends(require_owner)):
    """Look the saved address up again. A guess is not written back."""
    if body.kind == "shop":
        shop = await db.shops.find_one({"id": body.id})
        if not shop:
            raise HTTPException(404, "Shop not found")
        address = shop.get("address") or ""
        try:
            geo = await geocode_address(address)
        except AddressNotFound as exc:
            raise HTTPException(400, str(exc))
        _refuse_unusable_pin(geo)
        zone = detect_zone(geo["lng"]) if geo.get("in_metro") else shop.get("zone")
        await db.shops.update_one({"id": shop["id"]}, {"$set": {
            "lat": geo["lat"], "lng": geo["lng"], "zone": zone,
            "geocode_source": "google", "updated_at": iso(now_utc()),
        }})
        return {"ok": True, "formatted_address": geo.get("formatted_address")}
    job = await db.jobs.find_one({"id": body.id})
    if not job:
        raise HTTPException(404, "Job not found")
    address = job.get("job_address") or ""
    try:
        geo = await geocode_address(address)
    except AddressNotFound as exc:
        raise HTTPException(400, str(exc))
    _refuse_unusable_pin(geo)
    zone = detect_zone(geo["lng"]) if geo.get("in_metro") else job.get("zone")
    await db.jobs.update_one({"id": job["id"]}, {"$set": {
        "job_lat": geo["lat"], "job_lng": geo["lng"], "zone": zone,
        "geocode_source": "google", "updated_at": iso(now_utc()),
    }})
    return {"ok": True, "formatted_address": geo.get("formatted_address")}


@api.get("/address-pins")
async def list_address_pins(tech=Depends(require_owner)):
    """Shops and jobs whose saved coordinates came from a fallback guess."""
    shops = await db.shops.find({}, {"_id": 0}).to_list(5000)
    jobs = await db.jobs.find({}, {"_id": 0}).to_list(20000)
    bad_shops = []
    for shop in shops:
        mock = mock_geocode(shop.get("address") or "")
        if came_from_fallback(shop.get("geocode_source"), shop.get("lat"), shop.get("lng"), mock["lat"], mock["lng"]):
            bad_shops.append(_pin_row_shop(shop))
    bad_jobs = []
    for job in jobs:
        if job.get("status") in ("cancelled", "declined"):
            continue
        mock = mock_geocode(job.get("job_address") or "")
        if came_from_fallback(job.get("geocode_source"), job.get("job_lat"), job.get("job_lng"), mock["lat"], mock["lng"]):
            bad_jobs.append(_pin_row_job(job))
    return {"shops": bad_shops, "jobs": bad_jobs}


@api.get("/health")
async def health():
    """Unauthenticated liveness probe for Render / uptime checks."""
    return {"status": "ok"}


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
    allow_origins=cors_allow_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown():
    client.close()
