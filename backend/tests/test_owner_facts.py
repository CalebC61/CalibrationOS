"""Owner screens show the facts that decide price, booking, and the new-job pill.

The shops list used to print pricing_tier, which stays Standard for a Preferred
shop. The shop page did not list jobs or the card the booking gate uses. The
new-bookings notice kept the time from the moment of booking after a shop
moved the job.

    cd backend && pytest tests/test_owner_facts.py -v
"""
import asyncio
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402
from business_time import business_date, business_day_bounds  # noqa: E402
from onboarding import READY_BILLING, card_on_file_facts  # noqa: E402

DAY = business_date()
DAY_START, _DAY_END = business_day_bounds(DAY)


def _at(delta):
    return (DAY_START + delta).isoformat()


def _match(doc, query):
    for key, expected in (query or {}).items():
        value = doc.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and value not in expected["$in"]:
                return False
            if "$gte" in expected and not (value is not None and value >= expected["$gte"]):
                return False
            if "$ne" in expected and value == expected["$ne"]:
                return False
        elif value != expected:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, limit):
        return self.docs[:limit]


class _Store:
    def __init__(self):
        self.docs = []

    def find(self, query=None, projection=None):
        return _Cursor([dict(doc) for doc in self.docs if _match(doc, query)])

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _match(doc, query):
                return dict(doc)
        return None


class _DB:
    def __init__(self):
        self.shops = _Store()
        self.shop_users = _Store()
        self.jobs = _Store()
        self.new_booking_alerts = _Store()


def _db(monkeypatch):
    db = _DB()
    monkeypatch.setattr(server, "db", db)
    return db


def test_card_on_file_states_follow_the_booking_gate():
    today = DAY
    ready = {
        "id": "shop-ready",
        "status": "active",
        **READY_BILLING,
    }
    active = card_on_file_facts(ready, None, today=today)
    assert active["state"] == "Active"
    assert active["brand"] == "visa"
    assert active["last4"] == "4242"
    assert active["exp_month"] == 12
    assert active["exp_year"] == 2099
    assert active["charge_terms_accepted"] is True
    assert active["can_book"] is True
    assert active["book_block"] is None
    assert "stripe" not in active

    expired = card_on_file_facts({
        **ready,
        "card_exp_month": 1,
        "card_exp_year": 2020,
    }, None, today=today)
    assert expired["state"] == "Expired"
    assert expired["can_book"] is False
    assert "expired" in expired["book_block"].lower()

    removed = card_on_file_facts({
        **ready,
        "card_status": "removed",
        "stripe_payment_method_id": None,
    }, None, today=today)
    assert removed["state"] == "Removed"
    assert removed["can_book"] is False
    assert "removed" in removed["book_block"].lower()

    blank = card_on_file_facts({"id": "shop-new", "status": "active"}, None, today=today)
    assert blank["state"] == "None"
    assert blank["brand"] is None
    assert blank["last4"] is None
    assert blank["charge_terms_accepted"] is False
    assert blank["can_book"] is False

    unsigned = card_on_file_facts({
        **ready,
        "charge_authorization_accepted_at": None,
    }, None, today=today)
    assert unsigned["state"] == "Active"
    assert unsigned["charge_terms_accepted"] is False
    assert unsigned["can_book"] is False
    assert "charge terms" in unsigned["book_block"].lower()


def test_owner_shop_list_shows_the_wholesale_card_and_keeps_pricing_tier(monkeypatch):
    db = _db(monkeypatch)
    db.shops.docs.extend([
        {
            "id": "preferred",
            "name": "Preferred Auto Glass",
            "pricing_tier": "standard",
            "status": "active",
            "zone": "east",
            "address": "Gilbert, AZ",
        },
        {
            "id": "plain",
            "name": "Star Windshield",
            "pricing_tier": "standard",
            "status": "active",
            "zone": "east",
            "address": "Mesa, AZ",
        },
        {
            "id": "custom",
            "name": "Local Glass",
            "pricing_tier": "standard",
            "wholesale_schedule": "custom",
            "custom_rate_static": 99,
            "custom_rate_dynamic": 80,
            "custom_rate_dual": 150,
            "status": "active",
            "zone": "west",
            "address": "Goodyear, AZ",
        },
    ])

    shops = asyncio.run(server.list_shops(tech={"id": "owner", "role": "owner"}))
    by_id = {shop["id"]: shop for shop in shops}

    assert by_id["preferred"]["rate_label"] == "Preferred: $115 / $75 / $165"
    assert by_id["preferred"]["pricing_tier"] == "standard"
    assert by_id["plain"]["rate_label"] == "Standard"
    assert by_id["custom"]["rate_label"] == "Custom: $99 / $80 / $150"
    assert db.shops.docs[0]["pricing_tier"] == "standard"


def test_owner_shop_page_lists_jobs_and_whether_the_shop_can_book(monkeypatch):
    db = _db(monkeypatch)
    shop_doc = {
        "id": "shop-1",
        "name": "Preferred Auto Glass",
        "pricing_tier": "standard",
        "status": "active",
        "zone": "east",
        "address": "Gilbert, AZ",
        **READY_BILLING,
    }
    shop_doc["stripe_payment_method_id"] = "pm_secret"
    shop_doc["stripe_customer_id"] = "cus_secret"
    db.shops.docs.append(shop_doc)
    db.jobs.docs.extend([
        {
            "id": "job-later",
            "shop_id": "shop-1",
            "status": "requested",
            "scheduled_start": _at(timedelta(days=2, hours=9)),
            "vehicle_year": 2021,
            "vehicle_make": "Ford",
            "vehicle_model": "F-150",
            "price": 75,
            "calibration_label": "Dynamic ADAS Calibration",
        },
        {
            "id": "job-next",
            "shop_id": "shop-1",
            "status": "booked",
            "scheduled_start": _at(timedelta(days=1, hours=10)),
            "vehicle_year": 2020,
            "vehicle_make": "Honda",
            "vehicle_model": "Civic",
            "price": 115,
            "calibration_label": "Static ADAS Calibration",
        },
        {
            "id": "job-done",
            "shop_id": "shop-1",
            "status": "complete",
            "scheduled_start": _at(timedelta(days=-3, hours=11)),
            "vehicle_year": 2019,
            "vehicle_make": "Toyota",
            "vehicle_model": "Camry",
            "price": 165,
            "calibration_label": "Dual ADAS Calibration",
        },
        {
            "id": "job-cancelled",
            "shop_id": "shop-1",
            "status": "cancelled",
            "scheduled_start": _at(timedelta(days=1, hours=12)),
            "vehicle_year": 2018,
            "vehicle_make": "Nissan",
            "vehicle_model": "Rogue",
            "price": 125,
        },
        {
            "id": "job-other",
            "shop_id": "shop-2",
            "status": "booked",
            "scheduled_start": _at(timedelta(days=1, hours=10)),
            "vehicle_year": 2024,
            "vehicle_make": "Tesla",
            "vehicle_model": "Y",
            "price": 215,
        },
    ])

    shop = asyncio.run(server.get_shop("shop-1", tech={"id": "owner", "role": "owner"}))

    assert shop["rate_label"] == "Preferred: $115 / $75 / $165"
    assert shop["pricing_tier"] == "standard"
    card = shop["card_on_file"]
    assert card["state"] == "Active"
    assert card["brand"] == "visa"
    assert card["last4"] == "4242"
    assert card["charge_terms_accepted"] is True
    assert card["can_book"] is True
    assert card["book_block"] is None
    assert "pm_secret" not in str(shop)
    assert "cus_secret" not in str(shop)
    assert "stripe_payment_method_id" not in card
    assert "stripe_customer_id" not in shop

    upcoming = [job["id"] for job in shop["jobs"]["upcoming"]]
    recent = [job["id"] for job in shop["jobs"]["recent"]]
    assert upcoming == ["job-next", "job-later"]
    assert recent == ["job-cancelled", "job-done"]
    assert "job-other" not in upcoming + recent
    nxt = shop["jobs"]["upcoming"][0]
    assert nxt["vehicle"] == "2020 Honda Civic"
    assert nxt["price"] == 115
    assert nxt["status"] == "booked"
    assert nxt["scheduled_start"] == _at(timedelta(days=1, hours=10))
    assert nxt["board_date"]
    pending = shop["jobs"]["upcoming"][1]
    assert pending["status_label"] == "Pending approval"


def test_new_booking_notice_uses_the_current_time_after_a_shop_moves_it(monkeypatch):
    db = _db(monkeypatch)
    original = _at(timedelta(days=1, hours=9))
    moved = _at(timedelta(days=1, hours=15, minutes=30))
    db.jobs.docs.append({
        "id": "job-moved",
        "shop_id": "shop-1",
        "shop_name": "Preferred Auto Glass",
        "status": "requested",
        "scheduled_start": moved,
        "vehicle_year": 2020,
        "vehicle_make": "Honda",
        "vehicle_model": "Civic",
        "price": 115,
    })
    db.jobs.docs.append({
        "id": "job-same",
        "shop_name": "Star Windshield",
        "status": "booked",
        "scheduled_start": original,
        "vehicle_year": 2019,
        "vehicle_make": "Toyota",
        "vehicle_model": "Camry",
        "price": 125,
    })
    db.new_booking_alerts.docs.extend([
        {
            "id": "alert-moved",
            "job_id": "job-moved",
            "owner_id": "owner",
            "created_at": original,
            "seen_at": None,
            "shop_name": "Preferred Auto Glass",
            "scheduled_start": original,
            "zone": "east",
            "vehicle": "2020 Honda Civic",
            "price": 115,
        },
        {
            "id": "alert-same",
            "job_id": "job-same",
            "owner_id": "owner",
            "created_at": original,
            "seen_at": None,
            "shop_name": "Star Windshield",
            "scheduled_start": original,
            "zone": "east",
            "vehicle": "2019 Toyota Camry",
            "price": 125,
        },
    ])

    body = asyncio.run(server.new_booking_alerts(tech={"id": "owner", "role": "owner"}))
    by_job = {alert["job_id"]: alert for alert in body["alerts"]}

    assert body["count"] == 2
    assert by_job["job-moved"]["scheduled_start"] == moved
    assert by_job["job-moved"]["status"] == "requested"
    assert by_job["job-moved"]["status_label"] == "Pending approval"
    assert by_job["job-moved"]["scheduled_start"] != original
    assert by_job["job-same"]["scheduled_start"] == original
    assert by_job["job-same"]["status"] == "booked"
    stored = next(alert for alert in db.new_booking_alerts.docs if alert["id"] == "alert-moved")
    assert stored["scheduled_start"] == original
