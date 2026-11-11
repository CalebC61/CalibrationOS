"""Booking notes and customer first name.

Pure helpers, plus the request model. No live server:
    cd backend && pytest tests/test_booking_fields.py -v
"""
import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

from booking_fields import completion_notes, job_customer_fields  # noqa: E402
from server import BookingIn  # noqa: E402


def _booking(**overrides):
    payload = {
        "booking_token": "tok",
        "job_address": "1234 E Williams Field Rd, Gilbert, AZ",
        "scheduled_start": "2026-11-12T16:00:00+00:00",
        "customer_last_name": "Ng",
        "year": 2022,
        "make": "Honda",
        "model": "Civic",
        "adas_system": "forward_camera",
        "calibration_type": "static",
    }
    payload.update(overrides)
    return BookingIn(**payload)


def test_optional_notes_and_first_name_are_stripped_onto_the_job():
    fields = job_customer_fields(notes="  Gate code 1234  ", customer_first_name="  Ana ")
    assert fields == {"notes": "Gate code 1234", "customer_first_name": "Ana"}


def test_blank_notes_and_missing_first_name_store_as_none():
    assert job_customer_fields(notes="   ", customer_first_name=None) == {
        "notes": None,
        "customer_first_name": None,
    }
    assert job_customer_fields(notes=None, customer_first_name="  ") == {
        "notes": None,
        "customer_first_name": None,
    }


def test_legacy_booking_payload_still_omits_notes_and_first_name():
    data = _booking()
    assert data.notes is None
    assert data.customer_first_name is None
    stored = job_customer_fields(notes=data.notes, customer_first_name=data.customer_first_name)
    assert stored == {"notes": None, "customer_first_name": None}


def test_booking_accepts_notes_and_first_name():
    data = _booking(notes="Park behind the shop", customer_first_name="Luis")
    assert data.notes == "Park behind the shop"
    assert data.customer_first_name == "Luis"


def test_booking_rejects_oversized_notes():
    with pytest.raises(ValidationError):
        _booking(notes="x" * 4001)


def test_blank_completion_notes_keep_the_booking_notes():
    assert completion_notes("Gate code 1234", None) == "Gate code 1234"
    assert completion_notes("Gate code 1234", "   ") == "Gate code 1234"


def test_typed_completion_notes_replace_booking_notes():
    assert completion_notes("Gate code 1234", "All good") == "All good"
    assert completion_notes(None, "All good") == "All good"
