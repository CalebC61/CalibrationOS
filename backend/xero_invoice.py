"""Pure, dependency-light helpers for building Xero invoice payloads.

Kept import-light (stdlib only) so the spec-critical invoice format is unit-testable
without booting the full server / MongoDB / Xero. Both the real Xero path and the mock
in `server.py` share these helpers so the two always produce an identical invoice shape.
"""
from datetime import datetime, timedelta

INVOICE_DUE_DAYS = 30


def line_two_description(vehicle: dict) -> str:
    """Spec invoice line item 2: ``[LASTNAME] / [YEAR] [MAKE] [MODEL] / [VIN]`` (all caps)."""
    last = (vehicle.get("customer_last_name") or "CUSTOMER").upper()
    year = vehicle.get("year", "")
    make = (vehicle.get("make") or "").upper()
    model = (vehicle.get("model") or "").upper()
    vin = (vehicle.get("vin") or "VIN NOT PROVIDED").upper()
    return f"{last} / {year} {make} {model} / {vin}"


def due_date_string(now: datetime, days: int = INVOICE_DUE_DAYS) -> str:
    """Invoice due date as ``YYYY-MM-DD`` (today + ``days``)."""
    return (now + timedelta(days=days)).date().isoformat()


def xero_invoice_body(contact_id, price, pricing_label, vehicle, account_code,
                      now: datetime, due_days: int = INVOICE_DUE_DAYS) -> dict:
    """Build the Xero REST API body for a single ACCREC DRAFT invoice, per spec.

    Line 1 = calibration label @ the shop's rate. Line 2 = the vehicle/customer
    descriptor @ $0.00. Both post to the sales account code.
    """
    return {
        "Type": "ACCREC",
        "Contact": {"ContactID": contact_id},
        "Status": "DRAFT",
        "DueDate": due_date_string(now, due_days),
        "LineAmountTypes": "Exclusive",
        "LineItems": [
            {
                "Description": pricing_label,
                "Quantity": 1.0,
                "UnitAmount": float(price),
                "AccountCode": str(account_code),
            },
            {
                "Description": line_two_description(vehicle),
                "Quantity": 1.0,
                "UnitAmount": 0.00,
                "AccountCode": str(account_code),
            },
        ],
    }
