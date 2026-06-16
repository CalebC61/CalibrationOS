"""Unit tests for the spec-critical Xero invoice payload builder.

These are pure (stdlib only) and run anywhere — no server, MongoDB, or Xero needed:
    cd backend && pytest tests/test_xero_invoice.py -v
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/
from xero_invoice import xero_invoice_body, line_two_description, due_date_string  # noqa: E402

NOW = datetime(2026, 6, 16, tzinfo=timezone.utc)
VEHICLE = {
    "customer_last_name": "Johnson", "year": 2023,
    "make": "Honda", "model": "Accord", "vin": "1hgcv1f30pa012345",
}


def test_invoice_is_accrec_draft_due_in_30_days():
    body = xero_invoice_body("CID-1", 125.00, "Static ADAS Calibration", VEHICLE, "200", NOW)
    assert body["Type"] == "ACCREC"
    assert body["Status"] == "DRAFT"
    assert body["Contact"] == {"ContactID": "CID-1"}
    assert body["DueDate"] == "2026-07-16"


def test_line_item_one_is_label_at_rate():
    body = xero_invoice_body("CID-1", 175.00, "Dual ADAS Calibration", VEHICLE, "200", NOW)
    line1 = body["LineItems"][0]
    assert line1["Description"] == "Dual ADAS Calibration"
    assert line1["UnitAmount"] == 175.00
    assert line1["Quantity"] == 1.0
    assert line1["AccountCode"] == "200"


def test_line_item_two_is_zero_priced_vehicle_descriptor():
    body = xero_invoice_body("CID-1", 125.00, "Static ADAS Calibration", VEHICLE, "200", NOW)
    line2 = body["LineItems"][1]
    assert line2["Description"] == "JOHNSON / 2023 HONDA ACCORD / 1HGCV1F30PA012345"
    assert line2["UnitAmount"] == 0.00
    assert line2["AccountCode"] == "200"


def test_line_two_uppercases_and_handles_missing_vin():
    veh = {"customer_last_name": "Martinez", "year": 2022, "make": "Tesla", "model": "Model Y"}
    assert line_two_description(veh) == "MARTINEZ / 2022 TESLA MODEL Y / VIN NOT PROVIDED"


def test_line_two_handles_missing_last_name():
    veh = {"year": 2020, "make": "Subaru", "model": "Outback", "vin": "abc123"}
    assert line_two_description(veh) == "CUSTOMER / 2020 SUBARU OUTBACK / ABC123"


def test_account_code_is_configurable():
    body = xero_invoice_body("CID-1", 225.00, "Tesla ADAS Calibration", VEHICLE, "201", NOW)
    assert all(li["AccountCode"] == "201" for li in body["LineItems"])


def test_due_date_string():
    assert due_date_string(NOW, 30) == "2026-07-16"
    assert due_date_string(NOW, 0) == "2026-06-16"
