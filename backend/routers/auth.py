"""/auth, /reference, /geocode endpoints."""
from fastapi import APIRouter, Depends, HTTPException

from deps import (STANDARD_PRICING, ZONES, db, detect_zone, get_current_tech,
                  make_token, mock_geocode, verify_password)
from models import LoginIn, TokenOut

router = APIRouter()


@router.post("/auth/login", response_model=TokenOut)
async def login(data: LoginIn):
    tech = await db.technicians.find_one({"email": data.email.lower()})
    if not tech or not verify_password(data.password, tech.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not tech.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is disabled")
    token = make_token(tech["id"], tech["role"])
    return TokenOut(token=token, role=tech["role"], name=tech["name"], tech_id=tech["id"])


@router.get("/auth/me")
async def me(tech=Depends(get_current_tech)):
    return tech


@router.get("/reference/zones")
async def get_zones():
    return list(ZONES.values())


@router.get("/reference/pricing")
async def get_pricing():
    return [{"calibration_type": k, **v} for k, v in STANDARD_PRICING.items()]


@router.post("/geocode")
async def geocode(payload: dict):
    addr = payload.get("address", "")
    geo = mock_geocode(addr)
    geo["zone"] = detect_zone(geo["lng"]) if geo["in_metro"] else None
    return geo
