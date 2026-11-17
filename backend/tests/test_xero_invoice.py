"""Wholesale rates, contact names, and the draft's line shape.

    cd backend && pytest tests/test_xero_invoice.py tests/test_xero_draft.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xero_invoice import (  # noqa: E402
    DEFAULT_SPECIAL_RATES,
    contact_search_name,
    invoice_date,
    parse_pop,
    rate_schedule_name,
    vehicle_descriptor,
    vin_from_pdf,
    vin_ok,
    wholesale_amount,
)

STANDARD = {"static": 125, "dynamic": 125, "dual": 175, "triple": 185, "tesla": 225}


def test_descriptor_is_first_last_vehicle_vin():
    text = vehicle_descriptor("Dan", "Forsley", 2020, "Honda", "Pilot", "5fnyf5h57lb019570")
    assert text == "DAN FORSLEY - 2020 HONDA PILOT - 5FNYF5H57LB019570"


def test_example_vin_passes_the_check_digit():
    assert vin_ok("5FNYF5H57LB019570")


def test_pdf_vin_is_used_when_the_file_contains_one():
    pdf = b"%PDF-1.1\n1 0 obj<<>>stream\nBT (1HGCM82633A004352) Tj ET\nendstream\nendobj\n%%EOF"
    assert vin_from_pdf(pdf) == "1HGCM82633A004352"
    assert vin_from_pdf(b"%PDF no vin here") is None


def test_job_date_is_the_phoenix_day_and_due_the_same_day():
    # 06:30 UTC is still the previous evening in Phoenix (UTC-7).
    job = {"scheduled_start": "2026-06-17T06:30:00+00:00"}
    assert invoice_date(job) == "2026-06-16"
    midday = {"scheduled_start": "2026-06-16T18:00:00+00:00"}
    assert invoice_date(midday) == "2026-06-16"


def test_pop_blank_zero_and_no_are_not_amounts():
    assert parse_pop(None) is None
    assert parse_pop("") is None
    assert parse_pop("none") is None
    assert parse_pop("NO") is None
    assert parse_pop("0") is None
    assert parse_pop(0) is None
    assert parse_pop("$0.00") is None
    assert parse_pop("450") == 450
    assert parse_pop("$1,200.50") == 1200.50
    try:
        parse_pop("maybe")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_known_shops_map_to_the_exact_xero_contact_name():
    assert contact_search_name({"name": "PREFERRED"}) == "Preferred Auto Glass"
    assert contact_search_name({"name": "Real Fast Auto Glass"}) == "Real Fast Auto Glass"
    assert contact_search_name({"shop_code": "REN"}) == "Mobile Glassworks"
    assert contact_search_name({"name": "Glassworks"}) == "Mobile Glassworks"
    assert contact_search_name({"name": "J&L Auto Glass"}) == "J&L Auto Glass"
    assert contact_search_name({"name": "11 Bravo"}) == "11 Bravo Mobile Auto Glass"
    # An id already on the shop is used as-is. We do not search or create.
    assert contact_search_name({"name": "PREFERRED", "xero_contact_id": "CID"}) is None
    assert contact_search_name({"name": "Some Other Glass"}) == "Some Other Glass"


def test_preferred_and_real_fast_rates_and_standard():
    preferred = {"name": "Preferred Auto Glass"}
    realfast = {"name": "REALFAST"}
    other = {"name": "Star Windshield"}
    assert rate_schedule_name(preferred) == "preferred"
    assert rate_schedule_name(realfast) == "realfast"
    assert rate_schedule_name(other) == "standard"
    assert wholesale_amount(preferred, "dynamic", STANDARD, DEFAULT_SPECIAL_RATES) == 75
    assert wholesale_amount(preferred, "static", STANDARD, DEFAULT_SPECIAL_RATES) == 115
    assert wholesale_amount(preferred, "dual", STANDARD, DEFAULT_SPECIAL_RATES) == 165
    assert wholesale_amount(preferred, "triple", STANDARD, DEFAULT_SPECIAL_RATES) == 165
    assert wholesale_amount(preferred, "tesla", STANDARD, DEFAULT_SPECIAL_RATES) == 215
    assert wholesale_amount(realfast, "static", STANDARD, DEFAULT_SPECIAL_RATES) == 115
    assert wholesale_amount(realfast, "dynamic", STANDARD, DEFAULT_SPECIAL_RATES) == 100
    assert wholesale_amount(realfast, "dual", STANDARD, DEFAULT_SPECIAL_RATES) == 165
    assert wholesale_amount(realfast, "triple", STANDARD, DEFAULT_SPECIAL_RATES) == 175
    assert wholesale_amount(realfast, "tesla", STANDARD, DEFAULT_SPECIAL_RATES) == 215
    assert wholesale_amount(other, "static", STANDARD, DEFAULT_SPECIAL_RATES) == 125
    # The owner can pin a schedule, and can edit the card the draft reads.
    pinned = {"name": "Preferred Auto Glass", "wholesale_schedule": "standard"}
    assert wholesale_amount(pinned, "dynamic", STANDARD, DEFAULT_SPECIAL_RATES) == 125
    edited = {"realfast": {**DEFAULT_SPECIAL_RATES["realfast"], "dynamic": 90}}
    assert wholesale_amount(realfast, "dynamic", STANDARD, edited) == 90


def test_custom_shop_rate_is_used_when_it_is_not_a_named_schedule():
    shop = {
        "name": "AutoGlassNow",
        "pricing_tier": "custom",
        "custom_rate_static": 99,
    }
    assert wholesale_amount(shop, "static", STANDARD, DEFAULT_SPECIAL_RATES) == 99
    # Preferred keeps the Preferred card even if custom rates are also filled in.
    preferred = {
        "name": "Preferred",
        "pricing_tier": "custom",
        "custom_rate_dynamic": 50,
    }
    assert wholesale_amount(preferred, "dynamic", STANDARD, DEFAULT_SPECIAL_RATES) == 75
