"""30-day warranty redos.

A calibration that is redone on or before the 30th America/Phoenix day after
the original job was completed is free. Day 31 is billed at the shop's normal
rate. Dates are Phoenix civil dates, not UTC dates: a job finished at 11:30pm
Phoenix is still that Phoenix day even though UTC has already rolled over.
"""
from datetime import date, datetime, timedelta, timezone

from business_time import business_date

WARRANTY_DAYS = 30
LOOKBACK_DAYS = 90
FREE_LABEL = "Warranty redo (free)"
BILLED_LABEL = "Past 30-day warranty — billed normally"
SKIP_REASON = (
    "Warranty redo (free). The redo is within 30 days of the original "
    "completion, so no Xero draft is filed and the card is not charged."
)


class WarrantyError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def civil_day(value) -> date:
    """America/Phoenix calendar date of an instant, or a YYYY-MM-DD civil date."""
    if isinstance(value, datetime):
        return business_date(value)
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if len(text) == 10 and text[4] == "-" and "T" not in text:
        return date.fromisoformat(text)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return business_date(parsed)


def days_after(original_completed, redo_when) -> int:
    """Phoenix days from the original completion to the redo. Negative is before."""
    return (civil_day(redo_when) - civil_day(original_completed)).days


def is_within_warranty(original_completed, redo_when) -> bool:
    """True when the redo is 30 Phoenix days or fewer after the original completion."""
    return days_after(original_completed, redo_when) <= WARRANTY_DAYS


def validate_original(original: dict | None, shop_id: str, redo_job_id: str | None = None) -> None:
    """A shop may only link its own completed jobs."""
    if not original or original.get("shop_id") != shop_id:
        raise WarrantyError("A shop can only link its own jobs.")
    if redo_job_id and original.get("id") == redo_job_id:
        raise WarrantyError("A job cannot be a warranty redo of itself.")
    if original.get("status") != "complete":
        raise WarrantyError("Only a completed job can be a warranty redo.")
    if not (original.get("actual_completion") or original.get("updated_at")):
        raise WarrantyError("That completed job has no completion date.")


def priced_warranty(original: dict, redo_when, shop_price: float) -> dict:
    """Price and label for a redo of `original`. Eligible redos are $0."""
    completed = original.get("actual_completion") or original.get("updated_at")
    eligible = is_within_warranty(completed, redo_when)
    fields = {
        "warranty_of_job_id": original.get("id"),
        "warranty_eligible": eligible,
        "warranty_label": FREE_LABEL if eligible else BILLED_LABEL,
        "warranty_original_completed_on": civil_day(completed).isoformat(),
    }
    if eligible:
        fields["price"] = 0.0
        fields["calibration_price"] = 0.0
        fields["trip_fee"] = 0
        fields["trip_fee_kind"] = None
        fields["outside_service_area"] = False
        fields["warranty_skip_reason"] = None
    else:
        amount = round(float(shop_price), 2)
        fields["price"] = amount
        fields["calibration_price"] = amount
        fields["warranty_skip_reason"] = None
    return fields


def completion_skip_fields() -> dict:
    """What Complete writes when the redo is free, so Xero and Stripe are not used."""
    return {
        "warranty_skip_reason": SKIP_REASON,
        "charge_skipped": SKIP_REASON,
        "xero_draft_status": "skipped",
        "xero_skipped_reason": SKIP_REASON,
        "payment_status": "not_charged",
    }


def _customer_name(job: dict) -> str:
    first = (job.get("customer_first_name") or "").strip()
    last = (job.get("customer_last_name") or "").strip()
    return " ".join(part for part in (first, last) if part)


def _vehicle_name(job: dict) -> str:
    parts = []
    for key in ("vehicle_year", "vehicle_make", "vehicle_model"):
        value = job.get(key)
        if value not in (None, ""):
            parts.append(str(value))
    return " ".join(parts)


def candidate_row(job: dict, today) -> dict | None:
    """One completed job this shop can pick, or None when it is outside 90 days."""
    if job.get("status") != "complete" or not job.get("id"):
        return None
    completed = job.get("actual_completion") or job.get("updated_at")
    if not completed:
        return None
    try:
        completed_on = civil_day(completed)
        today_on = civil_day(today)
    except (TypeError, ValueError):
        return None
    age = (today_on - completed_on).days
    if age < 0 or age > LOOKBACK_DAYS:
        return None
    return {
        "id": job["id"],
        "vehicle": _vehicle_name(job),
        "customer": _customer_name(job),
        "completed_on": completed_on.isoformat(),
        "warranty_through": (completed_on + timedelta(days=WARRANTY_DAYS)).isoformat(),
    }


def list_warranty_candidates(jobs, today) -> list:
    rows = []
    for job in jobs or []:
        row = candidate_row(job, today)
        if row:
            rows.append(row)
    rows.sort(key=lambda row: row["completed_on"], reverse=True)
    return rows
