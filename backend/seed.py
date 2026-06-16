"""DB seeding for first-boot."""
import secrets

from deps import (CALEB_HOME, db, detect_zone, gen_id, hash_password, iso,
                  logger, mock_geocode, now_utc)


async def seed_data():
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
            "xero_connected": True, "google_calendar_connected": True,
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

    if await db.shops.count_documents({}) == 0:
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
