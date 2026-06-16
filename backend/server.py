"""CalibrationOS Backend — Phase 1 MVP (Path B: revenue path with mocked integrations)."""
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from fastapi.responses import Response, RedirectResponse
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
from urllib.parse import quote
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta, time, date
import jwt
import bcrypt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=True)

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

app = FastAPI(title="CalibrationOS API")
api = APIRouter(prefix="/api")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ---------- Auth helpers ----------
JWT_SECRET = os.environ.get('JWT_SECRET', 'calibrationos-dev-secret-change-me')
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
    """Geocoding. Uses Google Maps if GOOGLE_MAPS_API_KEY is set, else keyword fallback."""
    gmaps_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if gmaps_key:
        try:
            import requests
            r = requests.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": address, "key": gmaps_key},
                timeout=4,
            )
            data = r.json()
            if data.get("status") == "OK" and data.get("results"):
                top = data["results"][0]
                loc = top["geometry"]["location"]
                lat, lng = loc["lat"], loc["lng"]
                in_metro = 32.9 < lat < 33.9 and -112.9 < lng < -111.4
                return {"lat": round(lat, 6), "lng": round(lng, 6),
                        "formatted_address": top.get("formatted_address", address),
                        "in_metro": in_metro, "source": "google"}
            logger.warning(f"Google geocode status={data.get('status')} for {address}")
        except Exception as e:
            logger.warning(f"Google geocode failed: {e}; falling back to keyword mock")
    # Fallback: keyword-based mock
    a = address.lower()
    base = None
    for key, coords in PHOENIX_CITY_COORDS.items():
        if key in a:
            base = coords
            break
    if base is None:
        base = (33.4484, -112.0740)
    seed = sum(ord(c) for c in address)
    rng = random.Random(seed)
    lat = base[0] + rng.uniform(-0.04, 0.04)
    lng = base[1] + rng.uniform(-0.04, 0.04)
    in_metro = 32.9 < lat < 33.9 and -112.9 < lng < -111.4
    return {"lat": round(lat, 6), "lng": round(lng, 6),
            "formatted_address": address, "in_metro": in_metro, "source": "mock"}

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
    """Drive time. Uses Google Distance Matrix if key set, else haversine fallback."""
    gmaps_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if gmaps_key:
        try:
            import requests
            r = requests.get(
                "https://maps.googleapis.com/maps/api/distancematrix/json",
                params={"origins": f"{o_lat},{o_lng}", "destinations": f"{d_lat},{d_lng}",
                        "departure_time": "now", "key": gmaps_key},
                timeout=4,
            )
            data = r.json()
            if data.get("status") == "OK":
                elem = data["rows"][0]["elements"][0]
                if elem.get("status") == "OK":
                    minutes = int(elem["duration"]["value"] / 60)
                    miles = round(elem["distance"]["value"] / 1609.34, 1)
                    return {"distance_miles": miles, "duration_minutes": max(10, minutes), "source": "google"}
        except Exception as e:
            logger.warning(f"Google distance matrix failed: {e}; falling back to haversine")
    miles = haversine_miles(o_lat, o_lng, d_lat, d_lng)
    minutes = max(10, int(miles * 2.2 + 5))
    return {"distance_miles": round(miles, 1), "duration_minutes": minutes, "source": "mock"}

async def mock_send_sms(to: str, body: str, kind: str = "generic", job_id: Optional[str] = None):
    """SMS sender. Uses Linqapp if LINQAPP_API_KEY + LINQAPP_FROM_NUMBER set, else logs to DB."""
    doc = {
        "id": gen_id(), "to": to, "body": body, "kind": kind,
        "job_id": job_id, "sent_at": iso(now_utc()),
        "provider": "mock", "provider_id": None, "delivered": False, "error": None,
    }
    linq_key = os.environ.get("LINQAPP_API_KEY", "")
    linq_from = os.environ.get("LINQAPP_FROM_NUMBER", "")
    if linq_key and linq_from and to:
        try:
            import requests
            r = await asyncio.to_thread(
                requests.post,
                "https://api.linqapp.com/api/partner/v3/chats",
                headers={"Authorization": f"Bearer {linq_key}", "Content-Type": "application/json"},
                json={"from": linq_from, "to": [to],
                      "message": {"parts": [{"type": "text", "value": body}]}},
                timeout=6,
            )
            if r.status_code < 300:
                data = r.json() if r.content else {}
                doc["provider"] = "linqapp"
                doc["provider_id"] = data.get("id") or data.get("chat_id")
                doc["delivered"] = True
                logger.info(f"[Linq SMS → {to}] sent: {doc['provider_id']}")
            else:
                doc["error"] = f"HTTP {r.status_code}: {r.text[:200]}"
                logger.warning(f"Linq SMS failed: {doc['error']}")
        except Exception as e:
            doc["error"] = str(e)
            logger.warning(f"Linq SMS exception: {e}")
    else:
        logger.info(f"[MOCK SMS → {to}] {body[:80]}")
    await db.sms_log.insert_one(doc)
    return doc

async def mock_xero_create_invoice(job: dict, shop: dict, vehicle: dict, pricing_label: str) -> dict:
    """Mock Xero invoice creation. Returns a fake invoice ID and stores the full payload."""
    invoice_id = f"XERO-{secrets.token_hex(6).upper()}"
    vin_str = (vehicle.get("vin") or "VIN NOT PROVIDED").upper()
    customer_last = (vehicle.get("customer_last_name") or "CUSTOMER").upper()
    line2 = f"{customer_last} / {vehicle['year']} {vehicle['make'].upper()} {vehicle['model'].upper()} / {vin_str}"
    payload = {
        "invoice_id": invoice_id,
        "type": "ACCREC",
        "status": "DRAFT",
        "contact_name": shop["name"],
        "due_date": (now_utc() + timedelta(days=30)).date().isoformat(),
        "line_items": [
            {"description": pricing_label, "quantity": 1, "unit_amount": float(job["price"]), "account_code": "200"},
            {"description": line2, "quantity": 1, "unit_amount": 0.00, "account_code": "200"},
        ],
        "total": float(job["price"]),
        "created_at": iso(now_utc()),
        "job_id": job["id"],
    }
    await db.mock_xero_invoices.insert_one(payload.copy())
    logger.info(f"[MOCK XERO] Created draft invoice {invoice_id} for {shop['name']} — ${job['price']}")
    return payload

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
    # v1 customer-facing flow additions:
    job_type: Optional[Literal["cash", "insurance"]] = "cash"
    insurance_approved_amount: Optional[float] = None

class ShopSelfRegisterIn(BaseModel):
    # Step 1: Business Info
    shop_legal_name: str
    shop_display_name: str
    contact_full_name: str
    email: EmailStr
    password: str
    contact_phone: str
    shop_address: str
    shop_city: Optional[str] = None
    shop_state: str = "AZ"
    shop_zip: Optional[str] = None

class TermsAcceptanceIn(BaseModel):
    terms_version: str
    signature_full_name: str

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

class JobEditIn(BaseModel):
    # All optional — only provided fields are updated.
    customer_last_name: Optional[str] = None
    vehicle_year: Optional[int] = None
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_trim: Optional[str] = None
    vehicle_vin: Optional[str] = None
    adas_system: Optional[Literal["forward_camera", "surround_view", "radar", "multi_camera", "tesla", "other"]] = None
    calibration_type: Optional[Literal["static", "dynamic", "dual", "triple", "tesla"]] = None
    job_address: Optional[str] = None
    scheduled_start: Optional[str] = None  # ISO datetime; end recomputed from zone slot_minutes
    notification_phone: Optional[str] = None
    notification_email: Optional[str] = None
    price: Optional[float] = None
    notes: Optional[str] = None

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
    geo = mock_geocode(addr)
    zone = detect_zone(geo["lng"]) if geo["in_metro"] else None
    return {**geo, "zone": zone}

# ---------- Shops ----------
@api.get("/shops")
async def list_shops(tech=Depends(require_owner)):
    shops = await db.shops.find({}, {"_id": 0}).to_list(1000)
    return shops

@api.post("/shops")
async def create_shop(data: ShopIn, tech=Depends(require_owner)):
    geo = mock_geocode(data.address)
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
        geo = mock_geocode(update["address"])
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
    # Fetch existing jobs in zone on this date, ordered by scheduled_start
    day_start = datetime.combine(day, time(0, 0), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
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
    dm = mock_distance_matrix(origin[0], origin[1], job_lat, job_lng)
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

    # Generate slots from earliest until zone end
    zone_end_dt = datetime.combine(day, end_t, tzinfo=timezone.utc)
    cursor = earliest
    while cursor + timedelta(minutes=z["slot_minutes"]) <= zone_end_dt:
        slots.append({
            "start": iso(cursor),
            "end": iso(cursor + timedelta(minutes=z["slot_minutes"])),
            "drive_time_minutes": drive_min,
            "label": cursor.strftime("%-I:%M %p") if hasattr(cursor, 'strftime') else cursor.isoformat(),
        })
        # Increment by slot duration for next available slot
        cursor = cursor + timedelta(minutes=z["slot_minutes"])
        if len(slots) + len(jobs) >= z["max_jobs"]:
            break
    return slots

@api.post("/public/availability")
async def public_availability(query: SlotQuery):
    shop = await db.shops.find_one({"booking_link_token": query.booking_token, "status": "active"})
    if not shop:
        raise HTTPException(404, "Invalid booking link")
    # Geocode job address
    geo = mock_geocode(query.job_address)
    if not geo["in_metro"]:
        return {"zone": None, "in_metro": False, "slots": [],
                "message": "This address is outside our current service area."}
    zone = detect_zone(geo["lng"])
    # Parse date
    try:
        day = datetime.strptime(query.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date")
    # Validate: not Sunday, not past, not > 21 days out
    today = now_utc().date()
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
    geo = mock_geocode(data.job_address)
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

    # Compute drive time from previous job (or home)
    day = start_dt.date()
    day_start = datetime.combine(day, time(0, 0), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    prev = await db.jobs.find({
        "zone": zone,
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(start_dt)},
        "status": {"$nin": ["cancelled"]},
    }, {"_id": 0}).sort("scheduled_start", -1).limit(1).to_list(1)
    if prev:
        origin = (prev[0]["job_lat"], prev[0]["job_lng"])
    else:
        origin = (CALEB_HOME["lat"], CALEB_HOME["lng"])
    dm = mock_distance_matrix(origin[0], origin[1], geo["lat"], geo["lng"])

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

    # Determine price from shop rate card (the Flat Calibration Fee)
    price = shop_price_for(shop, data.calibration_type)

    # Validate job type / insurance approved amount
    job_type = data.job_type or "cash"
    insurance_approved_amount = None
    if job_type == "insurance":
        if data.insurance_approved_amount is None or data.insurance_approved_amount <= 0:
            raise HTTPException(400, "Insurance jobs require an approved amount greater than $0")
        insurance_approved_amount = float(data.insurance_approved_amount)

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
        "price": price,  # Flat Calibration Fee (always what we charge)
        "job_type": job_type,
        "insurance_approved_amount": insurance_approved_amount,
        "invoice_id": None, "invoice_status": "pending",
        "google_calendar_event_id": None,
        "sequence_order": seq_count + 1,
        "notification_phone": data.notification_phone or shop.get("contact_phone"),
        "notification_email": data.notification_email or shop.get("contact_email"),
        "customer_last_name": data.customer_last_name,
        "vehicle_year": data.year, "vehicle_make": data.make, "vehicle_model": data.model, "vehicle_vin": data.vin,
        "created_at": iso(now_utc()), "updated_at": iso(now_utc()),
    }

    # Stripe auth-hold for bookings ≤ 6 days out (Stripe holds expire at 7 days).
    # Looks up the shop_user for this shop. If no card or out of window, skip silently.
    try:
        days_out = (start_dt.date() - now_utc().date()).days
        if 0 <= days_out <= 6 and stripe_sdk.api_key and not stripe_sdk.api_key.endswith("_emergent"):
            shop_user = await db.shop_users.find_one({
                "shop_id": shop["id"],
                "stripe_payment_method_id": {"$ne": None},
            })
            if shop_user:
                amount_cents = int(round(price * 100))
                hold = await asyncio.to_thread(
                    stripe_sdk.PaymentIntent.create,
                    amount=amount_cents,
                    currency="usd",
                    customer=shop_user["stripe_customer_id"],
                    payment_method=shop_user["stripe_payment_method_id"],
                    off_session=True,
                    confirm=True,
                    capture_method="manual",   # ← hold; we capture on completion
                    description=f"Auth hold — {STANDARD_PRICING[data.calibration_type]['label']}",
                    metadata={"job_id": job["id"], "shop_id": shop["id"]},
                )
                job["stripe_auth_intent_id"] = hold["id"]
                job["stripe_auth_status"] = hold["status"]  # 'requires_capture' on success
                job["stripe_auth_amount_cents"] = amount_cents
                job["stripe_auth_placed_at"] = iso(now_utc())
                logger.info(f"[STRIPE] Auth hold placed for job {job['id']} → PI {hold['id']} ({hold['status']})")
    except Exception as e:
        # Auth hold is best-effort; never block a booking on it.
        logger.warning(f"[STRIPE] Auth hold skipped for job {job['id']}: {e}")
        job["stripe_auth_error"] = str(e)[:300]

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
            "scheduled_start": job["scheduled_start"], "zone": zone, "price": price,
            "job_type": job["job_type"],
            "insurance_approved_amount": job.get("insurance_approved_amount"),
            "stripe_auth_intent_id": job.get("stripe_auth_intent_id"),
            "stripe_auth_status": job.get("stripe_auth_status"),
            "stripe_auth_error": job.get("stripe_auth_error")}

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
    """List jobs for a given date (default: today). Contractors only see their own jobs."""
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "Invalid date")
    else:
        d = now_utc().date()
    day_start = datetime.combine(d, time(0, 0), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
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

    # Xero invoice — real push if Xero is connected, otherwise mock
    pricing_label = STANDARD_PRICING[job["calibration_type"]]["label"]
    xero_token = await db.xero_tokens.find_one({"owner_id": tech["id"]}, {"owner_id": 1})
    if not xero_token:
        # Fall back to internal owner token (jobs are often completed by a tech, not the owner)
        xero_token = await db.xero_tokens.find_one({}, {"owner_id": 1})

    xero_invoice = None
    if xero_token:
        try:
            shop_doc = shop
            creds = await xero_service.get_valid_credentials(db, xero_token["owner_id"])
            contact_id = shop_doc.get("xero_contact_id")
            if not contact_id:
                contact_id = await xero_service.find_or_create_contact(creds, shop_doc)
                await db.shops.update_one({"id": shop_doc["id"]}, {"$set": {"xero_contact_id": contact_id}})
            xero_invoice = await xero_service.create_invoice(
                creds, contact_id=contact_id, job=job, line_label=pricing_label
            )
            logger.info(f"[XERO] Auto-pushed invoice for job {job_id} → {xero_invoice['invoice_number']}")
        except Exception as e:  # don't block job completion on Xero failure
            logger.warning(f"[XERO] Auto-push failed for job {job_id}: {e}; falling back to mock")

    if xero_invoice:
        invoice_update = {
            "xero_invoice_id": xero_invoice["invoice_id"],
            "xero_invoice_number": xero_invoice["invoice_number"],
            "invoice_id": xero_invoice["invoice_number"] or xero_invoice["invoice_id"],
            "invoice_status": (xero_invoice["status"] or "").lower(),
            "invoice_amount_due": xero_invoice.get("amount_due"),
            "invoice_amount_paid": xero_invoice.get("amount_paid"),
            "invoice_online_url": xero_invoice.get("online_url"),
        }
    else:
        mock_invoice = await mock_xero_create_invoice(job, shop, vehicle, pricing_label)
        invoice_update = {
            "invoice_id": mock_invoice["invoice_id"],
            "invoice_status": "draft",
        }

    update = {
        "status": "complete",
        "actual_completion": iso(now_utc()),
        "result": body.result,
        "notes": body.notes,
        **invoice_update,
        "updated_at": iso(now_utc()),
    }
    await db.jobs.update_one({"id": job_id}, {"$set": update})

    # Completion SMS
    msg = (f"ADAS calibration complete on your {job['vehicle_year']} {job['vehicle_make']} {job['vehicle_model']}. "
           f"Documentation will be included with your invoice. — The Calibration Crew")
    if job.get("notification_phone"):
        await mock_send_sms(job["notification_phone"], msg, kind="completed", job_id=job_id)

    # Admin email (mocked as log entry)
    inv_display = invoice_update.get("invoice_id") or invoice_update.get("xero_invoice_number") or "—"
    await db.admin_notifications.insert_one({
        "id": gen_id(),
        "subject": f"New Invoice Created — {shop['name']} — {job['vehicle_year']} {job['vehicle_make']} {job['vehicle_model']}",
        "body": f"Invoice {inv_display} created for {shop['name']} — ${job['price']}.",
        "to": os.environ.get("ADMIN_EMAIL", "admin@thecalibrationcrew.us"),
        "sent_at": iso(now_utc()),
    })

    # Auto-charge the shop's card on file (best-effort; doesn't block completion).
    charge_result = None
    if (stripe_sdk.api_key and not stripe_sdk.api_key.endswith("_emergent")
            and not job.get("charged_at")):
        try:
            shop_user = await db.shop_users.find_one({
                "shop_id": job["shop_id"],
                "stripe_payment_method_id": {"$ne": None},
            })
            if shop_user:
                amount_cents = int(round(float(job["price"]) * 100))
                auth_pi_id = job.get("stripe_auth_intent_id")
                intent = None
                used_capture = False
                if auth_pi_id:
                    try:
                        existing = await asyncio.to_thread(stripe_sdk.PaymentIntent.retrieve, auth_pi_id)
                        if existing.get("status") == "requires_capture":
                            cap = min(amount_cents, existing.get("amount_capturable") or amount_cents)
                            intent = await asyncio.to_thread(stripe_sdk.PaymentIntent.capture, auth_pi_id, amount_to_capture=cap)
                            used_capture = True
                        elif existing.get("status") == "succeeded":
                            intent = existing
                            used_capture = True
                    except stripe_sdk.error.StripeError as e:
                        logger.warning(f"[STRIPE] Auto-charge: hold capture failed for {auth_pi_id}: {e}")
                if intent is None:
                    intent = await asyncio.to_thread(
                        stripe_sdk.PaymentIntent.create,
                        amount=amount_cents, currency="usd",
                        customer=shop_user["stripe_customer_id"],
                        payment_method=shop_user["stripe_payment_method_id"],
                        off_session=True, confirm=True,
                        description=f"Calibration {job.get('calibration_label','')} — {job.get('vehicle_year','')} {job.get('vehicle_make','')} {job.get('vehicle_model','')}",
                        metadata={"job_id": job_id, "shop_id": job["shop_id"], "auto_charge": "true"},
                    )
                if intent.get("status") == "succeeded":
                    await db.jobs.update_one({"id": job_id}, {"$set": {
                        "charged_at": iso(now_utc()),
                        "charge_payment_intent_id": intent["id"],
                        "charge_amount_cents": amount_cents,
                        "charge_status": "succeeded",
                        "charge_currency": "usd",
                        "charge_card_brand": shop_user.get("card_brand"),
                        "charge_card_last4": shop_user.get("card_last4"),
                        "charged_by": tech["id"],
                        "charge_via": "auto_capture" if used_capture else "auto_off_session",
                    }})
                    charge_result = {"succeeded": True, "amount_cents": amount_cents,
                                     "payment_intent_id": intent["id"],
                                     "captured_from_hold": used_capture}
                    logger.info(f"[STRIPE] Auto-charged ${job['price']} on completion of job {job_id}")
                else:
                    charge_result = {"succeeded": False,
                                     "error": f"PaymentIntent status={intent.get('status')}"}
        except stripe_sdk.error.CardError as e:
            charge_result = {"succeeded": False, "error": f"Card declined: {getattr(e, 'user_message', str(e))}"}
            await db.jobs.update_one({"id": job_id}, {"$set": {
                "last_charge_error": charge_result["error"],
                "last_charge_attempt_at": iso(now_utc()),
            }})
        except Exception as e:
            charge_result = {"succeeded": False, "error": str(e)[:300]}
            logger.warning(f"[STRIPE] Auto-charge failed for job {job_id}: {e}")

    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return {"job": fresh, "invoice": invoice_update, "document": doc, "charge": charge_result}

# ---------- Field PWA helpers ----------
@api.post("/field/jobs/{job_id}/send-eta")
async def send_eta(job_id: str, tech=Depends(get_current_tech)):
    """Send a fresh ETA SMS to the customer. ETA = NOW + drive_time_minutes (rounded up to next 5)."""
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if not job.get("notification_phone"):
        raise HTTPException(400, "This job has no contact phone")
    drive = int(job.get("drive_time_minutes") or 20)
    # Round up to next 5 mins for cleanliness
    eta_min = ((drive + 4) // 5) * 5
    eta_dt = now_utc() + timedelta(minutes=eta_min)
    arrival = eta_dt.strftime("%-I:%M %p") if hasattr(eta_dt, "strftime") else eta_dt.isoformat()
    msg = (f"Your ADAS calibration technician is on the way. "
           f"ETA ~{eta_min} minutes (around {arrival}). — The Calibration Crew")
    await mock_send_sms(job["notification_phone"], msg, kind="eta", job_id=job_id)
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "last_eta_sent_at": iso(now_utc()),
        "last_eta_minutes": eta_min,
    }})
    return {"sent": True, "eta_minutes": eta_min, "eta_at": iso(eta_dt)}

# ---------- Dashboard summary ----------
@api.get("/dashboard/summary")
async def dashboard_summary(date_str: Optional[str] = None, tech=Depends(require_owner)):
    if date_str:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        d = now_utc().date()
    day_start = datetime.combine(d, time(0, 0), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
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
    # Release any uncaptured Stripe auth hold so funds return to the shop's card.
    auth_pi = job.get("stripe_auth_intent_id")
    if auth_pi and stripe_sdk.api_key and not stripe_sdk.api_key.endswith("_emergent"):
        try:
            existing = await asyncio.to_thread(stripe_sdk.PaymentIntent.retrieve, auth_pi)
            if existing.get("status") == "requires_capture":
                await asyncio.to_thread(stripe_sdk.PaymentIntent.cancel, auth_pi)
                logger.info(f"[STRIPE] Released auth hold {auth_pi} on cancellation of job {job_id}")
        except Exception as e:
            logger.warning(f"[STRIPE] Could not release hold {auth_pi}: {e}")
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

# ---------- Edit job (all-fields editor) ----------
@api.patch("/jobs/{job_id}")
async def edit_job(job_id: str, body: JobEditIn, tech=Depends(require_owner)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] in ("complete", "cancelled"):
        raise HTTPException(400, f"Cannot edit a {job['status']} job")

    data = body.model_dump(exclude_unset=True)
    update: dict = {}

    # Customer & vehicle denormalized fields
    if "customer_last_name" in data:
        update["customer_last_name"] = data["customer_last_name"]
    if "vehicle_year" in data:
        update["vehicle_year"] = data["vehicle_year"]
    if "vehicle_make" in data:
        update["vehicle_make"] = data["vehicle_make"]
    if "vehicle_model" in data:
        update["vehicle_model"] = data["vehicle_model"]
    if "vehicle_vin" in data:
        update["vehicle_vin"] = data["vehicle_vin"]

    # Sync the underlying vehicle document too
    vehicle_update = {}
    for k_src, k_dst in [("vehicle_year", "year"), ("vehicle_make", "make"),
                         ("vehicle_model", "model"), ("vehicle_vin", "vin"),
                         ("vehicle_trim", "trim"), ("customer_last_name", "customer_last_name"),
                         ("adas_system", "adas_system")]:
        if k_src in data:
            vehicle_update[k_dst] = data[k_src]
    if vehicle_update and job.get("vehicle_id"):
        await db.vehicles.update_one({"id": job["vehicle_id"]}, {"$set": vehicle_update})

    if "adas_system" in data:
        # not stored on job, but vehicle update above handles it
        pass

    # Calibration type → label + suggested price (unless price also provided)
    if "calibration_type" in data:
        ct = data["calibration_type"]
        update["calibration_type"] = ct
        update["calibration_label"] = STANDARD_PRICING[ct]["label"]
        if "price" not in data:
            shop = await db.shops.find_one({"id": job["shop_id"]})
            if shop:
                update["price"] = shop_price_for(shop, ct)

    # Manual price override
    if "price" in data and data["price"] is not None:
        update["price"] = float(data["price"])

    if "notification_phone" in data:
        update["notification_phone"] = data["notification_phone"]
    if "notification_email" in data:
        update["notification_email"] = data["notification_email"]
    if "notes" in data:
        update["notes"] = data["notes"]

    # Address change → re-geocode, update lat/lng/zone, recompute drive time
    if "job_address" in data and data["job_address"] and data["job_address"] != job["job_address"]:
        geo = mock_geocode(data["job_address"])
        if not geo["in_metro"]:
            raise HTTPException(400, "Address is outside the service area")
        new_zone = detect_zone(geo["lng"])
        update["job_address"] = data["job_address"]
        update["job_lat"] = geo["lat"]
        update["job_lng"] = geo["lng"]
        update["zone"] = new_zone
        # Recompute drive from previous job in zone+day
        start_dt = datetime.fromisoformat(job["scheduled_start"])
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        day_start = datetime.combine(start_dt.date(), time(0, 0), tzinfo=timezone.utc)
        prev = await db.jobs.find({
            "zone": new_zone, "id": {"$ne": job_id},
            "scheduled_start": {"$gte": iso(day_start), "$lt": iso(start_dt)},
            "status": {"$nin": ["cancelled"]},
        }, {"_id": 0}).sort("scheduled_start", -1).limit(1).to_list(1)
        if prev:
            o = (prev[0]["job_lat"], prev[0]["job_lng"])
        else:
            o = (CALEB_HOME["lat"], CALEB_HOME["lng"])
        dm = mock_distance_matrix(o[0], o[1], geo["lat"], geo["lng"])
        update["drive_time_minutes"] = dm["duration_minutes"]

    # Scheduled start change → recompute end based on zone slot_minutes
    if "scheduled_start" in data and data["scheduled_start"]:
        try:
            new_start = datetime.fromisoformat(data["scheduled_start"].replace("Z", "+00:00"))
            if new_start.tzinfo is None:
                new_start = new_start.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(400, "Invalid scheduled_start")
        z_key = update.get("zone", job["zone"])
        slot_min = ZONES[z_key]["slot_minutes"]
        update["scheduled_start"] = iso(new_start)
        update["scheduled_end"] = iso(new_start + timedelta(minutes=slot_min))

    if not update:
        # Nothing to change
        fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
        return fresh

    update["updated_at"] = iso(now_utc())
    await db.jobs.update_one({"id": job_id}, {"$set": update})
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
    invs = await db.mock_xero_invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return invs

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
    day_start = datetime.combine(d, time(0, 0), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
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
        dm = mock_distance_matrix(origin[0], origin[1], j["job_lat"], j["job_lng"])
        # Earliest start = cursor + drive, rounded up to next 15-min boundary
        earliest = cursor + timedelta(minutes=dm["duration_minutes"])
        minute = (earliest.minute // 15) * 15
        if earliest.minute % 15 != 0 or earliest.second > 0:
            minute += 15
        if minute >= 60:
            earliest = earliest.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            earliest = earliest.replace(minute=minute, second=0, microsecond=0)
        new_start = earliest
        new_end = new_start + timedelta(minutes=z["slot_minutes"])
        zone_end_dt = datetime.combine(d, parse_time_str(z["end"]), tzinfo=timezone.utc)
        if new_end > zone_end_dt:
            raise HTTPException(400, f"Reorder would push job past zone end. Try a different order.")
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
        geo = mock_geocode(update["home_address"])
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

# ---------- Customer-facing v1: terms, self-registration, auth modal ----------
import terms_service  # noqa: E402

@api.get("/portal/terms/current")
async def get_current_terms():
    """Returns the current published T&A. Public — no auth needed (shown pre-registration)."""
    doc = await db.terms_versions.find_one({"is_current": True}, {"_id": 0})
    if not doc:
        return terms_service.current_terms()
    return doc

@api.post("/portal/self-register")
async def portal_self_register(body: ShopSelfRegisterIn, request: Request):
    """Open shop self-registration. Creates the Shop (status=pending) and ShopUser,
    then returns a Stripe Checkout setup URL so the shop can save their card.
    Account flips to active once both Terms are accepted AND card is on file."""
    email = body.email.lower()
    if await db.shop_users.find_one({"email": email}):
        raise HTTPException(400, "An account already exists for this email")

    # Geocode the address to drop the shop into the metro
    geo = mock_geocode(body.shop_address)
    if not geo["in_metro"]:
        raise HTTPException(400, "Shop address is outside the Phoenix metro service area")
    zone = detect_zone(geo["lng"])

    shop_id = gen_id()
    shop_doc = {
        "id": shop_id,
        "name": body.shop_display_name,
        "legal_name": body.shop_legal_name,
        "contact_name": body.contact_full_name,
        "contact_phone": body.contact_phone,
        "contact_email": email,
        "address": body.shop_address,
        "city": body.shop_city,
        "state": body.shop_state,
        "zip": body.shop_zip,
        "lat": geo["lat"], "lng": geo["lng"],
        "zone": zone,
        "pricing_tier": "standard",
        "status": "pending",
        "booking_link_token": gen_id(),
        "onboarding": {"business_info": True, "terms_signed": False, "card_on_file": False},
        "created_via": "self_register",
        "created_at": iso(now_utc()),
        "updated_at": iso(now_utc()),
    }
    await db.shops.insert_one(shop_doc.copy())

    # Stripe customer + checkout setup session (best-effort if Stripe configured)
    stripe_customer_id = None
    checkout_url = None
    stripe_error = None
    if stripe_sdk.api_key and not stripe_sdk.api_key.endswith("_emergent"):
        try:
            cust = await asyncio.to_thread(stripe_sdk.Customer.create,
                email=email, name=body.contact_full_name,
                metadata={"shop_id": shop_id, "source": "self_register"})
            stripe_customer_id = cust["id"]
        except Exception as e:
            stripe_error = str(e)
            logger.warning(f"[STRIPE] Customer create failed: {e}")

    user_id = gen_id()
    user_doc = {
        "id": user_id,
        "email": email,
        "full_name": body.contact_full_name,
        "password_hash": hash_password(body.password),
        "shop_id": shop_id,
        "shop_name": body.shop_display_name,
        "stripe_customer_id": stripe_customer_id,
        "stripe_payment_method_id": None,
        "card_brand": None, "card_last4": None, "card_exp_month": None, "card_exp_year": None,
        "auth_popup_dismissed": False,
        "is_active": True,
        "created_at": iso(now_utc()),
    }
    await db.shop_users.insert_one(user_doc.copy())

    # Stripe Checkout Session in setup mode (returns hosted URL)
    origin = (os.environ.get("FRONTEND_APP_URL") or str(request.base_url)).rstrip("/")
    if stripe_customer_id:
        try:
            session = await asyncio.to_thread(stripe_sdk.checkout.Session.create,
                mode="setup", payment_method_types=["card"],
                customer=stripe_customer_id,
                success_url=f"{origin}/portal/setup-return?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{origin}/portal/setup-return?cancelled=1",
                metadata={"shop_user_id": user_id, "shop_id": shop_id})
            checkout_url = session["url"]
        except Exception as e:
            stripe_error = str(e)
            logger.warning(f"[STRIPE] Checkout setup failed: {e}")

    portal_token = make_portal_token(user_id)
    return {
        "shop_user_id": user_id,
        "shop_id": shop_id,
        "token": portal_token,
        "stripe_checkout_url": checkout_url,
        "stripe_unavailable": checkout_url is None,
        "stripe_error": stripe_error,
    }

@api.post("/portal/accept-terms")
async def accept_terms(body: TermsAcceptanceIn, request: Request, su=Depends(get_current_shop_user)):
    if not body.signature_full_name.strip():
        raise HTTPException(400, "Signature is required")
    terms = await db.terms_versions.find_one({"version": body.terms_version, "is_current": True})
    if not terms:
        raise HTTPException(400, "Terms version is not current — please refresh and re-accept")
    record = {
        "id": gen_id(),
        "shop_user_id": su["id"],
        "shop_id": su["shop_id"],
        "terms_version": body.terms_version,
        "signature_full_name": body.signature_full_name.strip(),
        "signed_at": iso(now_utc()),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    await db.terms_acceptances.insert_one(record.copy())
    await db.shop_users.update_one({"id": su["id"]}, {"$set": {
        "terms_signature": body.signature_full_name.strip(),
        "terms_signed_at": record["signed_at"],
        "terms_version_signed": body.terms_version,
    }})
    await db.shops.update_one({"id": su["shop_id"]}, {"$set": {
        "onboarding.terms_signed": True,
        "updated_at": iso(now_utc()),
    }})
    await _maybe_activate_shop(su["shop_id"])
    return {"accepted": True, "version": body.terms_version}

@api.post("/portal/dismiss-auth-popup")
async def dismiss_auth_popup(su=Depends(get_current_shop_user)):
    await db.shop_users.update_one({"id": su["id"]}, {"$set": {
        "auth_popup_dismissed": True,
        "auth_popup_dismissed_at": iso(now_utc()),
    }})
    return {"dismissed": True}

async def _maybe_activate_shop(shop_id: str) -> None:
    """Flip shop status to 'active' when all onboarding steps are complete."""
    shop = await db.shops.find_one({"id": shop_id})
    if not shop or shop.get("status") == "active":
        return
    ob = shop.get("onboarding") or {}
    if ob.get("business_info") and ob.get("terms_signed") and ob.get("card_on_file"):
        await db.shops.update_one({"id": shop_id}, {"$set": {
            "status": "active",
            "activated_at": iso(now_utc()),
        }})
        logger.info(f"[ONBOARD] Shop {shop_id} activated")


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
    await db.shops.update_one({"id": su["shop_id"]}, {"$set": {
        "onboarding.card_on_file": True,
        "updated_at": iso(now_utc()),
    }})
    await _maybe_activate_shop(su["shop_id"])
    fresh = await db.shop_users.find_one({"id": su["id"]}, {"_id": 0, "password_hash": 0})
    return {"status": "complete", "shop_user": fresh}

@api.post("/portal/auth/login")
async def portal_login(body: ShopUserLoginIn):
    su = await db.shop_users.find_one({"email": body.email.lower()})
    if not su or not verify_password(body.password, su.get("password_hash", "")):
        raise HTTPException(401, "Invalid email or password")
    if not su.get("is_active", True):
        raise HTTPException(403, "Account disabled")
    shop = await db.shops.find_one({"id": su["shop_id"]})
    token = make_portal_token(su["id"])
    return {"token": token, "shop_user_id": su["id"], "full_name": su["full_name"],
            "shop_name": su["shop_name"], "shop_id": su["shop_id"],
            "has_payment_method": bool(su.get("stripe_payment_method_id")),
            "auth_popup_dismissed": bool(su.get("auth_popup_dismissed", False)),
            "shop_status": (shop or {}).get("status", "pending"),
            "onboarding": (shop or {}).get("onboarding", {})}

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
    """Returns OWN jobs fully detailed + other shops' jobs as anonymized blocks with drive-window from this shop."""
    if date_str:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        d = now_utc().date()
    day_start = datetime.combine(d, time(0, 0), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    all_jobs = await db.jobs.find({
        "scheduled_start": {"$gte": iso(day_start), "$lt": iso(day_end)},
        "status": {"$ne": "cancelled"},
    }, {"_id": 0}).sort("scheduled_start", 1).to_list(500)
    # This shop's coordinates as drive-window origin
    shop = await db.shops.find_one({"id": su["shop_id"]})
    origin_lat = shop.get("lat") if shop else 33.4484
    origin_lng = shop.get("lng") if shop else -112.0740
    own, others = [], []
    for j in all_jobs:
        if j["shop_id"] == su["shop_id"]:
            own.append(j)
        else:
            # Drive estimate from THIS shop to that pin
            dm = mock_distance_matrix(origin_lat, origin_lng, j["job_lat"], j["job_lng"])
            others.append({
                "id": j["id"],
                "scheduled_start": j["scheduled_start"],
                "scheduled_end": j["scheduled_end"],
                "zone": j["zone"],
                "sequence_order": j.get("sequence_order"),
                "job_lat": j["job_lat"], "job_lng": j["job_lng"],
                "drive_minutes_from_you": dm["duration_minutes"],
                "status": j["status"],
                # NO shop_name, vehicle, customer, calibration, price, address
            })
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
    """Completed jobs from portal shops whose card is on file, not yet charged or skipped."""
    portal_users = await db.shop_users.find(
        {"stripe_payment_method_id": {"$ne": None}}, {"_id": 0}
    ).to_list(500)
    shop_id_to_user = {u["shop_id"]: u for u in portal_users}
    jobs = await db.jobs.find({
        "status": "complete",
        "shop_id": {"$in": list(shop_id_to_user.keys())},
        "charged_at": {"$exists": False},
        "charge_skipped_at": {"$exists": False},
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

@api.post("/jobs/{job_id}/charge")
async def charge_job(job_id: str, tech=Depends(require_owner)):
    """Charge the portal shop's card on file for this completed job."""
    if not stripe_sdk.api_key or stripe_sdk.api_key.endswith("_emergent"):
        raise HTTPException(400, "Stripe is not configured. Add a real STRIPE_API_KEY to backend/.env.")

    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "complete":
        raise HTTPException(400, f"Cannot charge a {job['status']} job")
    if job.get("charged_at"):
        raise HTTPException(400, "This job has already been charged")

    shop_user = await db.shop_users.find_one({
        "shop_id": job["shop_id"],
        "stripe_payment_method_id": {"$ne": None},
    })
    if not shop_user:
        raise HTTPException(400, "No card on file for this shop")

    amount_cents = int(round(float(job["price"]) * 100))
    if amount_cents <= 0:
        raise HTTPException(400, "Job price must be greater than zero")

    # If we placed an auth hold at booking and it's still capturable, capture it.
    # Otherwise fall back to creating a fresh PaymentIntent.
    auth_pi_id = job.get("stripe_auth_intent_id")
    used_capture = False
    intent = None
    if auth_pi_id:
        try:
            existing = await asyncio.to_thread(stripe_sdk.PaymentIntent.retrieve, auth_pi_id)
            if existing.get("status") == "requires_capture":
                # Capture (full or partial if price changed)
                cap_amount = min(amount_cents, existing.get("amount_capturable") or existing.get("amount") or amount_cents)
                intent = await asyncio.to_thread(
                    stripe_sdk.PaymentIntent.capture, auth_pi_id,
                    amount_to_capture=cap_amount,
                )
                used_capture = True
                logger.info(f"[STRIPE] Captured auth hold {auth_pi_id} for job {job_id}")
            elif existing.get("status") == "succeeded":
                # Already captured (defensive)
                intent = existing
                used_capture = True
        except stripe_sdk.error.StripeError as e:
            logger.warning(f"[STRIPE] Auth hold capture failed for {auth_pi_id}: {e}; will create fresh PI")

    if intent is None:
        try:
            intent = await asyncio.to_thread(
                stripe_sdk.PaymentIntent.create,
                amount=amount_cents,
                currency="usd",
                customer=shop_user["stripe_customer_id"],
                payment_method=shop_user["stripe_payment_method_id"],
                off_session=True,
                confirm=True,
                description=f"Calibration {job.get('calibration_label','')} — {job.get('vehicle_year','')} {job.get('vehicle_make','')} {job.get('vehicle_model','')}",
                metadata={
                    "job_id": job_id,
                    "shop_id": job["shop_id"],
                    "shop_name": job.get("shop_name", ""),
                    "invoice_id": job.get("invoice_id") or "",
                },
            )
        except stripe_sdk.error.CardError as e:
            err = e.error or {}
            decline_code = getattr(err, "decline_code", None) or err.get("decline_code") if isinstance(err, dict) else None
            message = getattr(err, "message", None) or str(e)
            await db.jobs.update_one({"id": job_id}, {"$set": {
                "last_charge_error": message,
                "last_charge_attempt_at": iso(now_utc()),
            }})
            raise HTTPException(402, f"Card declined: {message}{f' ({decline_code})' if decline_code else ''}")
        except stripe_sdk.error.StripeError as e:
            message = getattr(e, "user_message", None) or str(e)
            await db.jobs.update_one({"id": job_id}, {"$set": {
                "last_charge_error": message,
                "last_charge_attempt_at": iso(now_utc()),
            }})
            raise HTTPException(502, f"Stripe error: {message}")

    status = intent.get("status")
    if status != "succeeded":
        # e.g. requires_action (3DS) — for off_session this is rare on test card 4242
        await db.jobs.update_one({"id": job_id}, {"$set": {
            "charge_payment_intent_id": intent["id"],
            "charge_status": status,
            "last_charge_attempt_at": iso(now_utc()),
            "last_charge_error": f"PaymentIntent returned status={status}",
        }})
        raise HTTPException(402, f"Charge not completed: status={status}. Customer may need to re-authenticate.")

    update = {
        "charged_at": iso(now_utc()),
        "charge_payment_intent_id": intent["id"],
        "charge_amount_cents": amount_cents,
        "charge_status": "succeeded",
        "charge_currency": "usd",
        "charge_card_brand": shop_user.get("card_brand"),
        "charge_card_last4": shop_user.get("card_last4"),
        "charged_by": tech["id"],
        "charge_via": "auth_capture" if used_capture else "off_session_pi",
        "updated_at": iso(now_utc()),
    }
    # Clear any previous error
    await db.jobs.update_one({"id": job_id}, {
        "$set": update,
        "$unset": {"last_charge_error": "", "last_charge_attempt_at": ""},
    })
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    logger.info(f"[STRIPE] Charged ${job['price']} for job {job_id} → PI {intent['id']} (capture={used_capture})")
    return {"job": fresh, "payment_intent_id": intent["id"], "amount_cents": amount_cents, "captured_from_hold": used_capture}

@api.post("/jobs/{job_id}/skip-charge")
async def skip_charge_job(job_id: str, tech=Depends(require_owner)):
    """Remove a job from the charge queue (owner is billing manually outside Stripe)."""
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("charged_at"):
        raise HTTPException(400, "This job has already been charged")
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "charge_skipped_at": iso(now_utc()),
        "charge_skipped_by": tech["id"],
        "updated_at": iso(now_utc()),
    }})
    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return fresh

# ---------- Xero OAuth + invoice push ----------
import xero_service  # noqa: E402

@api.get("/xero/status")
async def xero_status(tech=Depends(require_owner)):
    doc = await db.xero_tokens.find_one({"owner_id": tech["id"]})
    if not doc:
        return {"connected": False, "tenant_id": None, "org_name": None, "expires_at": None}
    return {
        "connected": True,
        "tenant_id": doc["tenant_id"],
        "org_name": doc.get("org_name"),
        "expires_at": doc.get("expires_at"),
        "scope": doc.get("scope"),
    }

@api.get("/xero/auth/start")
async def xero_auth_start(tech=Depends(require_owner)):
    state = secrets.token_urlsafe(24)
    await db.xero_oauth_state.update_one(
        {"owner_id": tech["id"]},
        {"$set": {"owner_id": tech["id"], "state": state, "created_at": iso(now_utc())}},
        upsert=True,
    )
    return {"authorize_url": xero_service.build_authorize_url(state)}

@api.get("/xero/auth/callback")
async def xero_auth_callback(code: Optional[str] = None, state: Optional[str] = None,
                              error: Optional[str] = None):
    frontend = os.environ.get("FRONTEND_APP_URL", "/").rstrip("/")
    if error:
        return RedirectResponse(f"{frontend}/settings?xero=error&detail={error}")
    if not code or not state:
        raise HTTPException(400, "Missing code or state")

    state_doc = await db.xero_oauth_state.find_one({"state": state})
    if not state_doc:
        raise HTTPException(400, "Invalid OAuth state")
    owner_id = state_doc["owner_id"]
    await db.xero_oauth_state.delete_many({"owner_id": owner_id})

    td = await xero_service.exchange_code_for_tokens(code)
    access_token = td["access_token"]
    refresh_token = td.get("refresh_token")
    expires_in = td.get("expires_in", 1800)
    expires_at = (now_utc() + timedelta(seconds=expires_in)).isoformat()

    tenants = await xero_service.fetch_tenants(access_token)
    if not tenants:
        return RedirectResponse(f"{frontend}/settings?xero=error&detail=no_tenants")
    tenant = tenants[0]
    tenant_id = tenant["tenantId"]

    try:
        org = await xero_service.fetch_organisation(access_token, tenant_id)
        org_name = org.get("Name") or tenant.get("tenantName")
    except Exception:
        org_name = tenant.get("tenantName")

    await db.xero_tokens.update_one(
        {"owner_id": owner_id},
        {"$set": {
            "owner_id": owner_id,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "scope": td.get("scope"),
            "token_type": td.get("token_type", "Bearer"),
            "tenant_id": tenant_id,
            "org_name": org_name,
            "updated_at": iso(now_utc()),
        }, "$setOnInsert": {"created_at": iso(now_utc())}},
        upsert=True,
    )
    logger.info(f"[XERO] Connected owner {owner_id} → tenant {tenant_id} ({org_name})")
    return RedirectResponse(f"{frontend}/settings?xero=connected")

@api.post("/xero/disconnect")
async def xero_disconnect(tech=Depends(require_owner)):
    doc = await db.xero_tokens.find_one({"owner_id": tech["id"]})
    if doc and doc.get("refresh_token"):
        await xero_service.revoke_refresh_token(doc["refresh_token"])
    await db.xero_tokens.delete_one({"owner_id": tech["id"]})
    return {"disconnected": True}

@api.post("/xero/jobs/{job_id}/push-invoice")
async def xero_push_invoice(job_id: str, tech=Depends(require_owner)):
    """Create (or refresh) a Xero invoice for the given job."""
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("xero_invoice_id"):
        # Already pushed — just refresh status
        creds = await xero_service.get_valid_credentials(db, tech["id"])
        info = await xero_service.fetch_invoice(creds, job["xero_invoice_id"])
        await db.jobs.update_one({"id": job_id}, {"$set": {
            "invoice_status": (info["status"] or "").lower(),
            "invoice_amount_due": info.get("amount_due"),
            "invoice_amount_paid": info.get("amount_paid"),
            "updated_at": iso(now_utc()),
        }})
        return {"job_id": job_id, **info, "already_existed": True}

    shop = await db.shops.find_one({"id": job["shop_id"]})
    if not shop:
        raise HTTPException(400, "Shop not found for job")

    creds = await xero_service.get_valid_credentials(db, tech["id"])
    contact_id = shop.get("xero_contact_id")
    if not contact_id:
        contact_id = await xero_service.find_or_create_contact(creds, shop)
        await db.shops.update_one({"id": shop["id"]}, {"$set": {"xero_contact_id": contact_id}})

    pricing_label = STANDARD_PRICING[job["calibration_type"]]["label"]
    info = await xero_service.create_invoice(creds, contact_id=contact_id, job=job, line_label=pricing_label)
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "xero_invoice_id": info["invoice_id"],
        "xero_invoice_number": info["invoice_number"],
        "invoice_id": info["invoice_number"] or info["invoice_id"],  # legacy display field
        "invoice_status": (info["status"] or "").lower(),
        "invoice_amount_due": info.get("amount_due"),
        "invoice_amount_paid": info.get("amount_paid"),
        "invoice_online_url": info.get("online_url"),
        "updated_at": iso(now_utc()),
    }})
    logger.info(f"[XERO] Pushed invoice for job {job_id} → {info['invoice_number']} ({info['status']})")
    return {"job_id": job_id, **info, "already_existed": False}

@api.post("/xero/jobs/{job_id}/refresh-status")
async def xero_refresh_invoice_status(job_id: str, tech=Depends(require_owner)):
    job = await db.jobs.find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    inv_id = job.get("xero_invoice_id")
    if not inv_id:
        raise HTTPException(400, "Job has no Xero invoice yet — push it first")
    creds = await xero_service.get_valid_credentials(db, tech["id"])
    info = await xero_service.fetch_invoice(creds, inv_id)
    await db.jobs.update_one({"id": job_id}, {"$set": {
        "invoice_status": (info["status"] or "").lower(),
        "invoice_amount_due": info.get("amount_due"),
        "invoice_amount_paid": info.get("amount_paid"),
        "updated_at": iso(now_utc()),
    }})
    return {"job_id": job_id, **info}

@api.post("/xero/refresh-all")
async def xero_refresh_all(tech=Depends(require_owner)):
    """Batch refresh status for all jobs with a Xero invoice that isn't PAID yet."""
    jobs = await db.jobs.find({
        "xero_invoice_id": {"$exists": True, "$ne": None},
        "invoice_status": {"$nin": ["paid", "voided"]},
    }, {"_id": 0, "id": 1, "xero_invoice_id": 1}).to_list(500)
    if not jobs:
        return {"refreshed": 0}
    creds = await xero_service.get_valid_credentials(db, tech["id"])
    n = 0
    for j in jobs:
        try:
            info = await xero_service.fetch_invoice(creds, j["xero_invoice_id"])
            await db.jobs.update_one({"id": j["id"]}, {"$set": {
                "invoice_status": (info["status"] or "").lower(),
                "invoice_amount_due": info.get("amount_due"),
                "invoice_amount_paid": info.get("amount_paid"),
                "updated_at": iso(now_utc()),
            }})
            n += 1
        except HTTPException as e:
            logger.warning(f"[XERO] Refresh job {j['id']} failed: {e.detail}")
    return {"refreshed": n, "total": len(jobs)}

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
    # Owner
    owner_email = "caleb@thecalibrationcrew.us"
    existing = await db.technicians.find_one({"email": owner_email})
    if not existing:
        owner = {
            "id": gen_id(), "name": "Caleb (Owner)", "email": owner_email,
            "phone": "+16025550101", "role": "owner",
            "home_zone": "east", "home_address": "Gilbert, AZ",
            "home_lat": CALEB_HOME["lat"], "home_lng": CALEB_HOME["lng"],
            "is_active": True,
            "password_hash": hash_password("Owner123!"),
            "xero_connected": True, "google_calendar_connected": True,  # mocked
            "created_at": iso(now_utc()),
        }
        await db.technicians.insert_one(owner)
        logger.info(f"Seeded owner: {owner_email} / Owner123!")
    contractor_email = "contractor@thecalibrationcrew.us"
    existing_c = await db.technicians.find_one({"email": contractor_email})
    if not existing_c:
        contractor = {
            "id": gen_id(), "name": "West-Side Contractor", "email": contractor_email,
            "phone": "+16025550199", "role": "contractor",
            "home_zone": "west", "home_address": "Goodyear, AZ",
            "home_lat": 33.4353, "home_lng": -112.3576,
            "is_active": True,
            "password_hash": hash_password("Contractor123!"),
            "created_at": iso(now_utc()),
        }
        await db.technicians.insert_one(contractor)
        logger.info(f"Seeded contractor: {contractor_email} / Contractor123!")

    # Demo shops
    shop_count = await db.shops.count_documents({})
    if shop_count == 0:
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

@app.on_event("startup")
async def startup():
    await seed_data()
    await load_settings()
    import terms_service
    await terms_service.ensure_terms_seeded(db)

# Include router
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
