"""Optional booking notes and customer first name.

Kept free of FastAPI and Mongo so the storage rules can be tested without a server.
"""
from typing import Optional


def clean_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def job_customer_fields(notes: Optional[str] = None, customer_first_name: Optional[str] = None) -> dict:
    """Values to store on a new job. Blank text becomes None."""
    return {
        "notes": clean_optional_text(notes),
        "customer_first_name": clean_optional_text(customer_first_name),
    }


def completion_notes(existing: Optional[str], submitted: Optional[str]) -> Optional[str]:
    """Keep booking notes when the technician leaves the completion note blank.

    A typed completion note replaces them. The original spacing of a typed note is kept.
    """
    if submitted is None or not str(submitted).strip():
        return existing
    return submitted
