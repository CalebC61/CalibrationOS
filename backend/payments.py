"""Stripe calls for saving a card, invoicing a job, and charging it once.

Decisions (should we charge, which idempotency key) live in billing.py.
This module only talks to Stripe. Callers pass a StripeClient.
"""
from billing import (
    amount_due,
    charge_idempotency_key,
    invoice_idempotency_key,
    late_fee_invoice_key,
)
from charging import cents, interpret_payment_intent


def _data(obj):
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return {}


def create_customer(client, *, email: str, name: str, shop_id: str) -> str:
    customer = client.v1.customers.create({
        "email": email,
        "name": name,
        "metadata": {"shop_id": shop_id},
    })
    return _data(customer).get("id") or customer.id


def create_setup_intent(client, *, customer_id: str, shop_user_id: str) -> dict:
    intent = client.v1.setup_intents.create({
        "customer": customer_id,
        "usage": "off_session",
        "metadata": {"shop_user_id": shop_user_id},
        "automatic_payment_methods": {"enabled": True},
    })
    data = _data(intent)
    return {"id": data.get("id") or intent.id, "client_secret": data.get("client_secret") or intent.client_secret}


def create_checkout_setup(client, *, customer_id: str, shop_user_id: str, success_url: str, cancel_url: str) -> str:
    session = client.v1.checkout.sessions.create({
        "mode": "setup",
        "customer": customer_id,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {"shop_user_id": shop_user_id},
    })
    data = _data(session)
    return data.get("url") or session.url


def retrieve_setup_checkout(client, session_id: str) -> dict:
    session = client.v1.checkout.sessions.retrieve(
        session_id,
        {"expand": ["setup_intent", "setup_intent.payment_method"]},
    )
    return _data(session)


def save_payment_method(client, *, customer_id: str, payment_method_id: str) -> dict:
    """Attach the method and make it the customer's default for off-session charges."""
    client.v1.payment_methods.attach(payment_method_id, {"customer": customer_id})
    client.v1.customers.update(customer_id, {
        "invoice_settings": {"default_payment_method": payment_method_id},
    })
    method = _data(client.v1.payment_methods.retrieve(payment_method_id))
    card = method.get("card") or {}
    return {
        "stripe_payment_method_id": payment_method_id,
        "card_brand": card.get("brand"),
        "card_last4": card.get("last4"),
        "card_exp_month": card.get("exp_month"),
        "card_exp_year": card.get("exp_year"),
    }


def _invoice_lines(job: dict, description: str) -> list:
    lines = [{
        "amount": cents(job.get("price") or 0),
        "description": description,
    }]
    late = float(job.get("late_fee") or 0)
    if late:
        lines.append({"amount": cents(late), "description": "Late fee — invoice unpaid after 7 days"})
    return lines


def create_job_invoice(client, *, customer_id: str, job: dict, description: str, email_customer: bool = False) -> dict:
    """One Stripe invoice per job. Idempotency key is the job id.

    collection_method is send_invoice so Stripe does not also charge the card.
    The off-session PaymentIntent, when the job is in charge mode, is separate
    and uses its own idempotency key. After that charge succeeds the caller
    marks this invoice paid out of band.
    """
    job_id = job["id"]
    invoice = client.v1.invoices.create({
        "customer": customer_id,
        "collection_method": "send_invoice",
        "days_until_due": 7,
        "auto_advance": False,
        "pending_invoice_items_behavior": "exclude",
        "metadata": {"job_id": job_id, "shop_id": job.get("shop_id") or ""},
        "description": description,
    }, {"idempotency_key": invoice_idempotency_key(job_id)})
    invoice_id = _data(invoice).get("id") or invoice.id
    for index, line in enumerate(_invoice_lines(job, description)):
        client.v1.invoice_items.create({
            "customer": customer_id,
            "invoice": invoice_id,
            "amount": line["amount"],
            "currency": "usd",
            "description": line["description"],
        }, {"idempotency_key": f"{invoice_idempotency_key(job_id)}-line-{index}"})
    finalized = client.v1.invoices.finalize_invoice(
        invoice_id, options={"idempotency_key": f"{invoice_idempotency_key(job_id)}-finalize"},
    )
    # send_invoice emails the shop from Stripe. Skip it unless shop mail is turned on.
    if email_customer:
        try:
            sent = client.v1.invoices.send_invoice(
                invoice_id, options={"idempotency_key": f"{invoice_idempotency_key(job_id)}-send"},
            )
            finalized = sent
        except Exception:
            # Already sent on a retry. The finalized invoice is still the proof.
            pass
    data = _data(finalized)
    return {
        "invoice_id": invoice_id,
        "stripe_invoice_id": invoice_id,
        "provider": "stripe",
        "status": data.get("status") or "open",
        "hosted_url": data.get("hosted_invoice_url"),
        "total": amount_due(job),
        "contact_name": None,
    }


def create_late_fee_invoice(client, *, customer_id: str, job: dict) -> dict:
    job_id = job["id"]
    invoice = client.v1.invoices.create({
        "customer": customer_id,
        "collection_method": "send_invoice",
        "days_until_due": 0,
        "auto_advance": False,
        "pending_invoice_items_behavior": "exclude",
        "metadata": {"job_id": job_id, "kind": "late_fee"},
        "description": "Late fee",
    }, {"idempotency_key": late_fee_invoice_key(job_id)})
    invoice_id = _data(invoice).get("id") or invoice.id
    client.v1.invoice_items.create({
        "customer": customer_id,
        "invoice": invoice_id,
        "amount": cents(25),
        "currency": "usd",
        "description": "Late fee — invoice unpaid after 7 days",
    }, {"idempotency_key": f"{late_fee_invoice_key(job_id)}-line"})
    finalized = client.v1.invoices.finalize_invoice(
        invoice_id, options={"idempotency_key": f"{late_fee_invoice_key(job_id)}-finalize"},
    )
    try:
        finalized = client.v1.invoices.send_invoice(
            invoice_id, options={"idempotency_key": f"{late_fee_invoice_key(job_id)}-send"},
        )
    except Exception:
        pass
    data = _data(finalized)
    return {"stripe_invoice_id": invoice_id, "hosted_url": data.get("hosted_invoice_url")}


def charge_job(client, *, job: dict, customer_id: str, payment_method_id: str, receipt_email: str | None) -> dict:
    attempt = int(job.get("charge_attempts") or 0)
    intent = client.v1.payment_intents.create({
        "amount": cents(amount_due(job)),
        "currency": "usd",
        "customer": customer_id,
        "payment_method": payment_method_id,
        "off_session": True,
        "confirm": True,
        "description": job.get("calibration_label") or "ADAS calibration",
        "receipt_email": receipt_email or None,
        "metadata": {"job_id": job["id"], "shop_id": job.get("shop_id") or ""},
    }, {"idempotency_key": charge_idempotency_key(job["id"], attempt)})
    return interpret_payment_intent(_data(intent))


def mark_invoice_paid_out_of_band(client, invoice_id: str, job_id: str) -> None:
    if not invoice_id or not str(invoice_id).startswith("in_"):
        return
    client.v1.invoices.pay(
        invoice_id,
        {"paid_out_of_band": True},
        {"idempotency_key": f"invoice-paid-{job_id}-{invoice_id}"},
    )
