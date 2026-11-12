"""What to charge, when to invoice, and when a late fee is due.

Pure decisions. Stripe calls stay in server.py. A second complete of the same
job must not create a second invoice or a second successful charge.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

CHARGE_MODE = "charge_on_completion"
INVOICE_MODE = "invoice_hold"
LATE_FEE_DOLLARS = 25
LATE_FEE_GRACE_DAYS = 7
PAID_STATUSES = {"paid", "succeeded"}


def payment_mode(job: Optional[dict]) -> str:
    mode = (job or {}).get("payment_mode") or CHARGE_MODE
    if mode not in (CHARGE_MODE, INVOICE_MODE):
        return CHARGE_MODE
    return mode


def is_paid(job: Optional[dict]) -> bool:
    job = job or {}
    if job.get("charged_at"):
        return True
    return job.get("payment_status") in PAID_STATUSES


def has_invoice(job: Optional[dict]) -> bool:
    job = job or {}
    return bool(job.get("invoice_id") or job.get("stripe_invoice_id"))


def amount_due(job: Optional[dict]) -> float:
    job = job or {}
    return round(float(job.get("price") or 0) + float(job.get("late_fee") or 0), 2)


def billing_plan(job: Optional[dict]) -> dict:
    """Whether this complete (or a retry of it) should invoice and/or charge.

    create_invoice is false once an invoice id is stored, so a second click
    cannot open a second bill. charge is false once the job is paid, and false
    in invoice-hold mode.
    """
    job = job or {}
    mode = payment_mode(job)
    return {
        "mode": mode,
        "create_invoice": not has_invoice(job),
        "charge": mode == CHARGE_MODE and not is_paid(job),
    }


def charge_idempotency_key(job_id: str, attempt: int = 0) -> str:
    """Stable for a given attempt so a double-click cannot charge twice.

    A recorded decline bumps the attempt. The next try uses a new key so a
    replaced card is actually charged. Stripe replays one key for 24 hours,
    including card errors, which would otherwise stick the shop on the old decline.
    """
    if int(attempt or 0) <= 0:
        return f"charge-job-{job_id}"
    return f"charge-job-{job_id}-retry-{int(attempt)}"


def invoice_idempotency_key(job_id: str) -> str:
    return f"invoice-job-{job_id}"


def late_fee_invoice_key(job_id: str) -> str:
    return f"late-fee-invoice-{job_id}"


def _aware(value) -> datetime:
    if isinstance(value, datetime):
        moment = value
    else:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def late_fee_due(job: Optional[dict], now: datetime) -> Optional[dict]:
    """The one $25 fee for an unpaid invoice-mode job, or None.

    Due once the completion time is at least 7 days ago. A second call after
    late_fee_applied_at is set returns None. Charge-on-completion jobs and
    paid jobs are skipped.
    """
    job = job or {}
    if payment_mode(job) != INVOICE_MODE:
        return None
    if job.get("status") != "complete":
        return None
    if job.get("late_fee_applied_at"):
        return None
    if is_paid(job):
        return None
    completed = job.get("actual_completion")
    if not completed:
        return None
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if now.astimezone(timezone.utc) < _aware(completed) + timedelta(days=LATE_FEE_GRACE_DAYS):
        return None
    return {
        "job_id": job.get("id"),
        "shop_id": job.get("shop_id"),
        "amount": LATE_FEE_DOLLARS,
        "reason": "Invoice unpaid 7 days after the job was completed.",
    }


def apply_late_fee(job: dict, now: datetime) -> Optional[dict]:
    """Return the job with the fee stored, or None when no fee is due."""
    decision = late_fee_due(job, now)
    if not decision:
        return None
    updated = dict(job)
    updated["late_fee"] = LATE_FEE_DOLLARS
    updated["late_fee_applied_at"] = now.astimezone(timezone.utc).isoformat()
    updated["late_fee_reason"] = decision["reason"]
    return updated


class _MemoryGateway:
    """Test double: one Stripe result per idempotency key."""

    def __init__(self, charge_outcome="succeeded"):
        self.invoices = {}
        self.charges = {}
        self.charge_outcome = charge_outcome

    def invoice(self, key: str) -> str:
        self.invoices.setdefault(key, f"in_{len(self.invoices) + 1}")
        return self.invoices[key]

    def charge(self, key: str, amount: float) -> dict:
        if key not in self.charges:
            self.charges[key] = {
                "id": f"pi_{len(self.charges) + 1}",
                "outcome": self.charge_outcome,
                "amount": amount,
                "key": key,
            }
        return self.charges[key]


def apply_billing_pass(job: dict, gateway: _MemoryGateway) -> dict:
    """One completion pass. A second pass does not add an invoice or a paid charge."""
    job = dict(job)
    plan = billing_plan(job)
    if plan["create_invoice"]:
        job["invoice_id"] = gateway.invoice(invoice_idempotency_key(job["id"]))
        job["invoice_status"] = "open"
    if plan["charge"]:
        attempt = int(job.get("charge_attempts") or 0)
        result = gateway.charge(charge_idempotency_key(job["id"], attempt), amount_due(job))
        job["stripe_payment_intent_id"] = result["id"]
        if result["outcome"] == "succeeded":
            job["charged_at"] = "charged"
            job["payment_status"] = "paid"
            job.pop("charge_error", None)
        else:
            job["payment_status"] = "payment_failed"
            job["charge_error"] = result.get("message") or "Card declined."
            job["charge_attempts"] = attempt + 1
    return job
