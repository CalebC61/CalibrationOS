"""CalibrationOS Backend — Phase 1 MVP (Path B: revenue path with mocked integrations)."""
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import hashlib
import secrets
import random
import math
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
    in_metro = 32.9 < lat < 33.9 and -112.9 < lng < -111.4
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
    return jobs

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

    # Mock Xero invoice
    pricing_label = STANDARD_PRICING[job["calibration_type"]]["label"]
    invoice = await mock_xero_create_invoice(job, shop, vehicle, pricing_label)

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

    # Admin email (mocked as log entry)
    await db.admin_notifications.insert_one({
        "id": gen_id(),
        "subject": f"New Invoice Created — {shop['name']} — {job['vehicle_year']} {job['vehicle_make']} {job['vehicle_model']}",
        "body": f"Invoice {invoice['invoice_id']} created for {shop['name']} — ${job['price']}.",
        "to": os.environ.get("ADMIN_EMAIL", "admin@thecalibrationcrew.us"),
        "sent_at": iso(now_utc()),
    })

    fresh = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    return {"job": fresh, "invoice": invoice, "document": doc}

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
    return {
        "date": d.isoformat(),
        "job_count": len(jobs),
        "revenue": revenue,
        "estimated_miles": miles,
        "done_by": done_by,
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
