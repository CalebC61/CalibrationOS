"""Shared infrastructure: DB, auth, helpers, integrations, constants.

Routers and services depend on this module. This module depends on no router.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import random
import secrets
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env", override=True)

# ---------- Mongo ----------
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

# ---------- Stripe + Resend ----------
import resend as resend_sdk  # noqa: E402
import stripe as stripe_sdk  # noqa: E402

stripe_sdk.api_key = os.environ.get("STRIPE_API_KEY", "sk_test_emergent")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
if RESEND_API_KEY:
    resend_sdk.api_key = RESEND_API_KEY

logger = logging.getLogger("calibrationos")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# ---------- JWT / Auth ----------
JWT_SECRET = os.environ.get("JWT_SECRET", "calibrationos-dev-secret-change-me")
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
    payload = {"sub": user_id, "role": role,
               "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXP_HOURS)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def make_portal_token(shop_user_id: str) -> str:
    payload = {"sub": shop_user_id, "kind": "portal",
               "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXP_HOURS)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


async def get_current_tech(token: Optional[str] = Depends(oauth2_scheme)):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        tech = await db.technicians.find_one({"id": payload["sub"]},
                                             {"_id": 0, "password_hash": 0})
        if not tech:
            raise HTTPException(status_code=401, detail="User not found")
        return tech
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def require_owner(tech=Depends(get_current_tech)):
    if tech["role"] != "owner":
        raise HTTPException(status_code=403, detail="Owner only")
    return tech


async def get_current_shop_user(token: Optional[str] = Depends(oauth2_scheme)):
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated (portal)")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        if payload.get("kind") != "portal":
            raise HTTPException(status_code=401, detail="Not a portal token")
        su = await db.shop_users.find_one({"id": payload["sub"]},
                                          {"_id": 0, "password_hash": 0})
        if not su:
            raise HTTPException(status_code=401, detail="Shop user not found")
        return su
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ---------- Small helpers ----------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def gen_id() -> str:
    return str(uuid.uuid4())


def parse_time_str(t: str) -> time:
    h, m = t.split(":")
    return time(int(h), int(m))


# ---------- Constants ----------
STANDARD_PRICING = {
    "static":  {"label": "Static ADAS Calibration",                 "price": 125.00},
    "dynamic": {"label": "Dynamic ADAS Calibration",                "price": 125.00},
    "dual":    {"label": "Dual ADAS Calibration",                   "price": 175.00},
    "triple":  {"label": "Triple Camera / Subaru ADAS Calibration", "price": 185.00},
    "tesla":   {"label": "Tesla ADAS Calibration",                  "price": 225.00},
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


# ---------- Settings persistence ----------
async def load_settings():
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
                for fld in ("start", "end", "max_jobs", "slot_minutes", "buffer_minutes"):
                    if fld in v and v[fld] is not None:
                        ZONES[k][fld] = v[fld]


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


# ---------- Geocoding / distance ----------
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
    return "east"


def haversine_miles(lat1, lng1, lat2, lng2) -> float:
    R = 3958.8
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def mock_distance_matrix(o_lat, o_lng, d_lat, d_lng) -> dict:
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


# ---------- SMS / Email ----------
async def mock_send_sms(to: str, body: str, kind: str = "generic", job_id: Optional[str] = None):
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


async def send_email(to: str, subject: str, html: str, kind: str = "transactional",
                     meta: Optional[dict] = None):
    """Resend if RESEND_API_KEY, else log entry only."""
    log_doc = {
        "id": gen_id(), "to": to, "subject": subject, "kind": kind, "meta": meta or {},
        "sent_at": iso(now_utc()), "provider": "mock", "provider_id": None,
        "delivered": False, "error": None,
    }
    if RESEND_API_KEY:
        try:
            res = await asyncio.to_thread(
                resend_sdk.Emails.send,
                {"from": SENDER_EMAIL, "to": [to], "subject": subject, "html": html},
            )
            log_doc["provider"] = "resend"
            log_doc["provider_id"] = res.get("id") if isinstance(res, dict) else None
            log_doc["delivered"] = True
            logger.info(f"[RESEND → {to}] {subject} sent: {log_doc['provider_id']}")
        except Exception as e:
            log_doc["error"] = str(e)
            logger.warning(f"Resend send failed: {e}")
    else:
        logger.info(f"[MOCK EMAIL → {to}] {subject}")
    await db.email_log.insert_one(log_doc)
    return log_doc


# ---------- Mock Xero (fallback when Xero not connected) ----------
async def mock_xero_create_invoice(job: dict, shop: dict, vehicle: dict, pricing_label: str) -> dict:
    invoice_id = f"XERO-{secrets.token_hex(6).upper()}"
    vin_str = (vehicle.get("vin") or "VIN NOT PROVIDED").upper()
    customer_last = (vehicle.get("customer_last_name") or "CUSTOMER").upper()
    line2 = f"{customer_last} / {vehicle['year']} {vehicle['make'].upper()} {vehicle['model'].upper()} / {vin_str}"
    payload = {
        "invoice_id": invoice_id, "type": "ACCREC", "status": "DRAFT",
        "contact_name": shop["name"],
        "due_date": (now_utc() + timedelta(days=30)).date().isoformat(),
        "line_items": [
            {"description": pricing_label, "quantity": 1,
             "unit_amount": float(job["price"]), "account_code": "200"},
            {"description": line2, "quantity": 1, "unit_amount": 0.00, "account_code": "200"},
        ],
        "total": float(job["price"]), "created_at": iso(now_utc()), "job_id": job["id"],
    }
    await db.mock_xero_invoices.insert_one(payload.copy())
    logger.info(f"[MOCK XERO] Created draft invoice {invoice_id} for {shop['name']} — ${job['price']}")
    return payload


# ---------- Shop / pricing helpers ----------
def shop_price_for(shop: dict, cal_type: str) -> float:
    if shop.get("pricing_tier") == "custom":
        override = shop.get(f"custom_rate_{cal_type}")
        if override is not None:
            return float(override)
    return float(STANDARD_PRICING[cal_type]["price"])


async def _maybe_activate_shop(shop_id: str) -> None:
    shop = await db.shops.find_one({"id": shop_id})
    if not shop or shop.get("status") == "active":
        return
    ob = shop.get("onboarding") or {}
    if ob.get("business_info") and ob.get("terms_signed") and ob.get("card_on_file"):
        await db.shops.update_one({"id": shop_id}, {"$set": {
            "status": "active", "activated_at": iso(now_utc()),
        }})
        logger.info(f"[ONBOARD] Shop {shop_id} activated")


# ---------- Slot availability + at-risk annotation ----------
async def compute_available_slots(zone_key: str, day: date, job_lat: float, job_lng: float):
    """Slot availability algorithm per spec."""
    z = ZONES[zone_key]
    start_t = parse_time_str(z["start"])
    end_t = parse_time_str(z["end"])
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
    if jobs:
        last = jobs[-1]
        anchor_dt = datetime.fromisoformat(last["scheduled_end"])
        if anchor_dt.tzinfo is None:
            anchor_dt = anchor_dt.replace(tzinfo=timezone.utc)
        origin = (last["job_lat"], last["job_lng"])
    else:
        anchor_dt = datetime.combine(day, start_t, tzinfo=timezone.utc)
        origin = (CALEB_HOME["lat"], CALEB_HOME["lng"])

    dm = mock_distance_matrix(origin[0], origin[1], job_lat, job_lng)
    drive_min = dm["duration_minutes"]
    earliest = anchor_dt + timedelta(minutes=drive_min)
    minute = (earliest.minute // 15) * 15
    if earliest.minute % 15 != 0 or earliest.second > 0:
        minute += 15
    if minute >= 60:
        earliest = earliest.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        earliest = earliest.replace(minute=minute, second=0, microsecond=0)

    zone_end_dt = datetime.combine(day, end_t, tzinfo=timezone.utc)
    cursor = earliest
    while cursor + timedelta(minutes=z["slot_minutes"]) <= zone_end_dt:
        slots.append({
            "start": iso(cursor),
            "end": iso(cursor + timedelta(minutes=z["slot_minutes"])),
            "drive_time_minutes": drive_min,
            "label": cursor.strftime("%-I:%M %p") if hasattr(cursor, "strftime") else cursor.isoformat(),
        })
        cursor = cursor + timedelta(minutes=z["slot_minutes"])
        if len(slots) + len(jobs) >= z["max_jobs"]:
            break
    return slots


def annotate_at_risk(jobs):
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
