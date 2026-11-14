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
from onboarding import card_is_expired


class CardSetupError(ValueError):
    """The SetupIntent cannot be saved as this shop's card."""


SIGNUP_SETUP_PURPOSE = "shop_signup"


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


# stripe-python 16 pins API version 2026-09-30.endive. That version rejects
# payment_method_types on SetupIntent, PaymentIntent, and Checkout Session
# creates (error payment_method_types_no_longer_supported). The replacement
# allow-list is allowed_payment_method_types. A type that is not in the list
# cannot be offered, including when the Dashboard has it turned on.
# automatic_payment_methods follows the Dashboard instead, so card setup does
# not send it. Link, Apple Pay, and Google Pay are wallets on top of card;
# the Payment Element turns those off. Do not send payment_method_types.
CARD_ONLY_PAYMENT_METHODS = ["card"]


def _card_only_params() -> dict:
    return {"allowed_payment_method_types": list(CARD_ONLY_PAYMENT_METHODS)}


def create_setup_intent(client, *, customer_id: str, shop_user_id: str, shop_id: str | None = None) -> dict:
    """Card-only SetupIntent for Settings and invite registration."""
    metadata = {"shop_user_id": shop_user_id, "purpose": "card_on_file"}
    if shop_id:
        metadata["shop_id"] = shop_id
    intent = client.v1.setup_intents.create({
        "customer": customer_id,
        "usage": "off_session",
        "metadata": metadata,
        **_card_only_params(),
    })
    data = _data(intent)
    return {"id": data.get("id") or intent.id, "client_secret": data.get("client_secret") or intent.client_secret}


def create_anonymous_setup_intent(client) -> dict:
    """Card-only SetupIntent before a shop exists. The card is attached on signup.

    Signup saves a card for off-session job charges. The signup Payment Element
    also hides Link, Apple Pay, and Google Pay.
    """
    intent = client.v1.setup_intents.create({
        "usage": "off_session",
        "metadata": {"purpose": "shop_signup"},
        **_card_only_params(),
    })
    data = _data(intent)
    return {"id": data.get("id") or intent.id, "client_secret": data.get("client_secret") or intent.client_secret}


def retrieve_setup_intent(client, intent_id: str) -> dict:
    intent = client.v1.setup_intents.retrieve(intent_id, {"expand": ["payment_method"]})
    return _data(intent)


def create_checkout_setup(client, *, customer_id: str, shop_user_id: str, success_url: str, cancel_url: str) -> str:
    session = client.v1.checkout.sessions.create({
        "mode": "setup",
        "customer": customer_id,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {"shop_user_id": shop_user_id},
        # Checkout's allow-list filters the dynamic set. wallet_options is the
        # code-side switch that hides the Link button. Apple Pay and Google Pay
        # on hosted Checkout are still Dashboard wallet settings.
        **_card_only_params(),
        "wallet_options": {"link": {"display": "never"}},
    })
    data = _data(session)
    return data.get("url") or session.url


def retrieve_setup_checkout(client, session_id: str) -> dict:
    session = client.v1.checkout.sessions.retrieve(
        session_id,
        {"expand": ["setup_intent", "setup_intent.payment_method"]},
    )
    return _data(session)


def _id_of(value):
    if isinstance(value, dict):
        return value.get("id")
    if isinstance(value, str) and value:
        return value
    return None


def verified_card(intent: dict, *, customer_id: str | None = None, shop_id: str | None = None, purpose: str | None = None) -> dict:
    """Card fields from a SetupIntent this shop is allowed to save.

    status must be succeeded, the payment method must be an expanded card, and
    the intent must be the signup intent or this shop's customer. A raw payment
    method id is not accepted here.
    """
    if not isinstance(intent, dict):
        raise CardSetupError("That card setup could not be confirmed.")
    if intent.get("status") != "succeeded":
        raise CardSetupError("The card was not saved.")
    method = intent.get("payment_method")
    if not isinstance(method, dict) or method.get("type") != "card":
        raise CardSetupError("Only a card can be saved.")
    card = method.get("card") or {}
    if not card.get("last4") or card.get("exp_month") in (None, "") or card.get("exp_year") in (None, ""):
        raise CardSetupError("Stripe did not return a card.")
    if card_is_expired(card.get("exp_month"), card.get("exp_year")):
        raise CardSetupError("That card is expired. Use a different card.")
    payment_method_id = method.get("id")
    if not payment_method_id:
        raise CardSetupError("Stripe did not return a card.")
    meta = intent.get("metadata") or {}
    intent_customer = _id_of(intent.get("customer"))
    pm_customer = _id_of(method.get("customer"))
    if purpose == SIGNUP_SETUP_PURPOSE:
        if meta.get("purpose") != SIGNUP_SETUP_PURPOSE:
            raise CardSetupError("That card setup is not for this signup.")
        if intent_customer or pm_customer:
            raise CardSetupError("That card setup was already used.")
    else:
        belongs = bool(customer_id and intent_customer == customer_id)
        if shop_id and meta.get("shop_id") == shop_id and intent_customer and intent_customer == customer_id:
            belongs = True
        if not belongs:
            raise CardSetupError("That card setup is not for this shop.")
        if pm_customer and pm_customer != customer_id:
            raise CardSetupError("That card is already saved on another account.")
    return {
        "stripe_payment_method_id": payment_method_id,
        "card_brand": card.get("brand"),
        "card_last4": card.get("last4"),
        "card_exp_month": card.get("exp_month"),
        "card_exp_year": card.get("exp_year"),
        "card_status": "active",
    }


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
        "card_status": "active",
    }


def detach_payment_method(client, payment_method_id: str) -> None:
    """Detach a card that is no longer the default. Never call this on the only card."""
    if payment_method_id:
        client.v1.payment_methods.detach(payment_method_id)


def delete_customer(client, customer_id: str) -> None:
    if customer_id:
        client.v1.customers.delete(customer_id)


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
    # Confirms the card already saved on the customer. Do not pass
    # payment_method_types: API 2026-09-30.endive rejects that parameter.
    # An off-session confirm of a known payment method needs no allow-list.
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
