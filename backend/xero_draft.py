"""File one Xero draft for a completed job.

The HTTP gateway is the only part that talks to Xero. Tests pass a fake.
A second call with the saved state never creates a second invoice, and this
module has no way to create a Xero contact or to authorise an invoice.
"""
import re

import requests

from billing import TRIP_FEE_DOLLARS
from xero_invoice import (
    ITEM_NAMES,
    calibration_line,
    calibration_skipped,
    contact_search_name,
    descriptor_line,
    find_branding_theme,
    find_exempt_tax,
    find_item,
    invoice_body,
    invoice_date,
    invoice_link,
    invoice_update_body,
    item_description,
    item_search_names,
    job_text,
    money,
    parse_pop,
    trip_fee_wanted,
    trip_line,
    vehicle_descriptor,
    vin_from_pdf,
    wholesale_amount,
)


class XeroCallError(Exception):
    """A Xero call failed. The message is safe to show to the owner."""


def _safe_pdf_name(name: str, fallback: str) -> str:
    base = str(name or "").replace("\\", "/").split("/")[-1]
    base = re.sub(r"[^A-Za-z0-9._ -]", "", base).strip()
    if not base:
        base = fallback
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base[:120]


def state_from_job(job: dict | None) -> dict:
    job = job or {}
    state = dict(job.get("xero_draft_state") or {})
    if job.get("xero_invoice_id") and not state.get("invoice_id"):
        state["invoice_id"] = job.get("xero_invoice_id")
    if job.get("xero_invoice_number") and not state.get("invoice_number"):
        state["invoice_number"] = job.get("xero_invoice_number")
    if job.get("xero_invoice_url") and not state.get("url"):
        state["url"] = job.get("xero_invoice_url")
    return state


def draft_is_finished(state: dict | None) -> bool:
    state = state or {}
    if state.get("status") != "draft" or not state.get("invoice_id"):
        return False
    if not state.get("wholesale_applied"):
        return False
    # A trip-fee-only draft can be filed with no post-scan. scan_not_required records that.
    if not state.get("scan_attached") and not state.get("scan_not_required"):
        return False
    if state.get("pop_amount") and not state.get("pop_attached"):
        return False
    return True


def spec_document_name(job, shop, original_name) -> str:
    """Customer_SHOP_Make_Model_Year.ext. A missing last name becomes CUSTOMER."""
    job = job or {}
    shop = shop or {}
    original = str(original_name or "calibration_report")
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else "pdf"
    if not ext.isalnum():
        ext = "pdf"
    last = str(job.get("customer_last_name") or "").strip() or "CUSTOMER"
    shop_name = str(shop.get("name") or "SHOP").strip() or "SHOP"
    make = str(job.get("vehicle_make") or "Vehicle").strip() or "Vehicle"
    model = str(job.get("vehicle_model") or "Model").strip() or "Model"
    year = job.get("vehicle_year")
    year_text = str(year).strip() if year is not None and str(year).strip() else "0000"
    name = f"{last}_{shop_name.upper().replace(' ', '')}_{make}_{model}_{year_text}.{ext}"
    return name.replace("/", "-").replace("\\", "-")


def _pack(state: dict) -> dict:
    finished = draft_is_finished(state)
    return {
        "ok": finished,
        "status": state.get("status"),
        "reason": None if finished else state.get("reason"),
        "invoice_id": state.get("invoice_id"),
        "invoice_number": state.get("invoice_number"),
        "url": state.get("url"),
        "total": state.get("total"),
        "contact_id_to_save": state.get("contact_id_to_save"),
        "learned_vin": state.get("learned_vin"),
        "state": state,
    }


def _fail(state: dict, reason: str) -> dict:
    state["status"] = "needs_attention"
    state["reason"] = reason
    return _pack(state)


def _capture(inv: dict, state: dict) -> None:
    state["invoice_id"] = inv.get("InvoiceID") or state.get("invoice_id")
    number = inv.get("InvoiceNumber")
    if number:
        state["invoice_number"] = number
    if state.get("invoice_id"):
        state["url"] = invoice_link(state["invoice_id"])
    lines = inv.get("LineItems") or []
    ids = {}
    for key, line in zip(state.get("line_keys") or [], lines):
        if line.get("LineItemID"):
            ids[key] = line["LineItemID"]
    if ids:
        state["line_ids"] = ids


def _resolve_contact(shop: dict, gateway) -> tuple:
    existing = str((shop or {}).get("xero_contact_id") or "").strip()
    if existing:
        return existing, None, None
    name = contact_search_name(shop)
    if not name:
        return None, None, "This shop has no Xero contact to match. Nothing was created."
    found = gateway.find_contacts(name) or []
    exact = [
        contact for contact in found
        if str(contact.get("Name") or "").strip().lower() == name.strip().lower()
        and contact.get("ContactID")
    ]
    if len(exact) == 1:
        contact_id = exact[0]["ContactID"]
        return contact_id, contact_id, None
    if len(exact) > 1:
        return None, None, f"More than one Xero contact is named {name}. Nothing was created."
    return None, None, f"No Xero contact is named {name}. Nothing was created."


def _prepare(job, shop, vehicle, calibration_type, pop, scan_pdf, standard_prices, special_rates, state, gateway):
    """Fill state with the lines we will send. Does not create an invoice."""
    if state.get("prepared"):
        return None
    if calibration_type not in ITEM_NAMES:
        return "Pick a calibration type, then retry the Xero draft."
    skipped = calibration_skipped(job)
    try:
        pop_amount = parse_pop(pop if pop is not None else (job or {}).get("pop_approved"))
    except ValueError as exc:
        return str(exc)
    # A couldn't-calibrate job is trip-fee-only. The post-scan is optional there.
    if not scan_pdf and not skipped:
        return "Upload the signed post-scan PDF, then retry the Xero draft."

    contact_id, save_id, problem = _resolve_contact(shop, gateway)
    if problem:
        return problem
    state["contact_id"] = contact_id
    if save_id:
        state["contact_id_to_save"] = save_id

    theme = find_branding_theme(gateway.list_branding_themes())
    item = None if calibration_skipped(job) else find_item(gateway.list_items(), calibration_type)
    tax = find_exempt_tax(gateway.list_tax_rates())
    if theme is None:
        return "Xero has no branding theme named Calibration Template."
    if not calibration_skipped(job) and item is None:
        wanted = " or ".join(item_search_names(calibration_type)) or ITEM_NAMES[calibration_type]
        return f"Xero has no item named {wanted}."
    if tax is None:
        return "Xero has no Tax Exempt tax type."

    try:
        wholesale = None if calibration_skipped(job) else wholesale_amount(
            shop, calibration_type, standard_prices, special_rates,
        )
    except ValueError as exc:
        return str(exc)

    pdf_vin = vin_from_pdf(scan_pdf)
    job_vin = job_text(job, vehicle, "vehicle_vin", "vin") or job_text(job, vehicle, "vin", "vin")
    vin = pdf_vin or job_vin
    if pdf_vin and not job_vin:
        state["learned_vin"] = pdf_vin
    first = job_text(job, vehicle, "customer_first_name", "customer_first_name")
    last = job_text(job, vehicle, "customer_last_name", "customer_last_name")
    year = job_text(job, vehicle, "vehicle_year", "year")
    make = job_text(job, vehicle, "vehicle_make", "make")
    model = job_text(job, vehicle, "vehicle_model", "model")

    wanted = trip_fee_wanted(job)
    # POP is the insurance amount on the calibration line. A trip-only job has no such line.
    use_pop = pop_amount if (pop_amount and not skipped) else None
    state.update({
        "prepared": True,
        "date": invoice_date(job),
        "branding_theme_id": theme["BrandingThemeID"],
        "tax_type": tax["TaxType"],
        "descriptor": vehicle_descriptor(first, last, year, make, model, vin),
        "calibration_skipped": skipped,
        "item_code": None if skipped else (item.get("Code") or item.get("Name")),
        "item_description": None if skipped else item_description(item),
        "wholesale": wholesale,
        "pop_amount": use_pop,
        "trip": wanted,
        "trip_amount": money(TRIP_FEE_DOLLARS) if wanted else None,
        "calibration_type": calibration_type,
    })
    total = 0.0
    if not skipped and wholesale is not None:
        total += wholesale
    if wanted:
        total += money(TRIP_FEE_DOLLARS)
    state["total"] = money(total)
    return None


def _money_lines(state: dict, calibration_amount):
    """Priced lines and the description-only line, in send order."""
    lines = []
    keys = []
    if not state.get("calibration_skipped"):
        lines.append(calibration_line(
            {"Code": state["item_code"], "Description": state["item_description"]},
            state["tax_type"],
            calibration_amount,
        ))
        keys.append("calibration")
    if state.get("trip"):
        lines.append(trip_line(state["tax_type"], state["trip_amount"]))
        keys.append("trip")
    lines.append(descriptor_line(state["descriptor"]))
    keys.append("descriptor")
    # The vehicle line stays last when there is a calibration, matching line 2.
    # A trip-only draft has the trip fee, then the same description-only line.
    if not state.get("calibration_skipped") and state.get("trip"):
        # calibration, descriptor, trip fee — descriptor remains line 2.
        calibration = lines[0]
        trip = lines[1]
        note = lines[2]
        lines = [calibration, note, trip]
        keys = ["calibration", "descriptor", "trip"]
    return lines, keys


def _lines_for_update(state: dict):
    amount = state["wholesale"]
    lines, keys = _money_lines(state, amount)
    ids = state.get("line_ids") or {}
    updated = []
    for key, line in zip(keys, lines):
        line_id = ids.get(key)
        if key == "descriptor":
            payload = {"Description": line["Description"]}
        else:
            payload = dict(line)
        if line_id:
            payload = {"LineItemID": line_id, **payload}
        updated.append(payload)
    return updated


def file_calibration_draft(
    *,
    job,
    shop,
    vehicle=None,
    calibration_type,
    pop,
    scan_pdf,
    scan_name,
    standard_prices,
    special_rates,
    gateway,
    state=None,
) -> dict:
    """Create or finish the one draft for this job.

    `state` is what was saved last time. When it already has an invoice id,
    this does not call create again.
    """
    state = dict(state or {})
    try:
        return _file(
            job=job, shop=shop, vehicle=vehicle, calibration_type=calibration_type,
            pop=pop, scan_pdf=scan_pdf, scan_name=scan_name,
            standard_prices=standard_prices, special_rates=special_rates,
            gateway=gateway, state=state,
        )
    except XeroCallError as exc:
        return _fail(state, str(exc)[:500] or "Xero did not accept the draft.")
    except Exception as exc:
        # Keep an invoice id captured before the failure so a retry cannot open a second draft.
        return _fail(state, str(exc)[:500] or "The Xero draft did not finish.")


def _file(*, job, shop, vehicle, calibration_type, pop, scan_pdf, scan_name,
          standard_prices, special_rates, gateway, state) -> dict:
    if draft_is_finished(state):
        return _pack(state)
    if state.get("remote_status") and str(state.get("remote_status")).upper() != "DRAFT":
        return _fail(state, state.get("reason") or "Xero did not leave the invoice as a draft.")

    if not state.get("invoice_id"):
        problem = _prepare(
            job, shop, vehicle, calibration_type, pop, scan_pdf,
            standard_prices, special_rates, state, gateway,
        )
        if problem:
            return _fail(state, problem)
        opening = state["pop_amount"] if state.get("pop_amount") else state.get("wholesale")
        lines, keys = _money_lines(state, opening)
        state["line_keys"] = keys
        body = invoice_body(
            contact_id=state["contact_id"],
            date=state["date"],
            branding_theme_id=state["branding_theme_id"],
            line_items=lines,
        )
        # Draft only. The HTTP gateway also refuses to send any other status.
        body["Status"] = "DRAFT"
        created = gateway.create_invoice(body)
        _capture(created, state)
        if not state.get("invoice_id"):
            return _fail(state, "Xero did not return an invoice id. Nothing else was filed.")
        remote = str(created.get("Status") or "").upper()
        if remote != "DRAFT":
            state["remote_status"] = remote
            return _fail(
                state,
                f"Xero returned {created.get('Status')} instead of a draft. It was not sent.",
            )
        state["remote_status"] = "DRAFT"
        if not state.get("pop_amount"):
            state["wholesale_applied"] = True

    pop_bytes = None
    if state.get("pop_amount") and not state.get("pop_attached"):
        pop_bytes = gateway.get_invoice_pdf(state["invoice_id"])
        if not pop_bytes:
            return _fail(state, "Xero did not return the POP invoice PDF.")
        number = state.get("invoice_number") or state["invoice_id"]
        gateway.attach(
            state["invoice_id"],
            f"Invoice {number}.pdf",
            pop_bytes,
            include_online=True,
        )
        state["pop_attached"] = True

    if not state.get("scan_attached") and not state.get("scan_not_required"):
        if scan_pdf:
            gateway.attach(
                state["invoice_id"],
                _safe_pdf_name(scan_name, "post-scan.pdf"),
                scan_pdf,
                include_online=True,
            )
            state["scan_attached"] = True
        elif state.get("calibration_skipped") or calibration_skipped(job):
            state["scan_not_required"] = True
        else:
            return _fail(state, "Upload the signed post-scan PDF, then retry the Xero draft.")

    if state.get("pop_amount") and not state.get("wholesale_applied"):
        updated = gateway.update_invoice(invoice_update_body(
            invoice_id=state["invoice_id"],
            line_items=_lines_for_update(state),
        ))
        remote = str(updated.get("Status") or "DRAFT").upper()
        if remote != "DRAFT":
            state["remote_status"] = remote
            return _fail(
                state,
                f"Xero returned {updated.get('Status')} instead of a draft. It was not sent.",
            )
        _capture(updated, state)
        state["wholesale_applied"] = True

    state["status"] = "draft"
    state["reason"] = None
    return _pack(state)


class HttpXeroGateway:
    """Xero Accounting API. Status on every invoice write is forced to DRAFT."""

    def __init__(self, access_token: str, tenant_id: str, api_base: str):
        self.access_token = access_token
        self.tenant_id = tenant_id
        self.api_base = api_base.rstrip("/")

    def _headers(self, accept="application/json", content_type="application/json"):
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Xero-tenant-id": self.tenant_id,
            "Accept": accept,
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _check(self, resp):
        if resp.status_code >= 400:
            detail = (resp.text or "").strip().replace("\n", " ")[:300]
            raise XeroCallError(f"Xero returned {resp.status_code}: {detail}".strip())
        return resp

    def _request(self, method, url, **kwargs):
        try:
            resp = requests.request(method, url, timeout=kwargs.pop("timeout", 30), **kwargs)
        except requests.RequestException as exc:
            raise XeroCallError("Xero could not be reached.") from exc
        return self._check(resp)

    def find_contacts(self, name: str) -> list:
        safe = str(name).replace('"', '\\"')
        resp = self._request(
            "GET", f"{self.api_base}/Contacts",
            headers=self._headers(),
            params={"where": f'Name=="{safe}"'},
        )
        return resp.json().get("Contacts") or []

    def list_items(self) -> list:
        resp = self._request("GET", f"{self.api_base}/Items", headers=self._headers())
        return resp.json().get("Items") or []

    def list_tax_rates(self) -> list:
        resp = self._request("GET", f"{self.api_base}/TaxRates", headers=self._headers())
        return resp.json().get("TaxRates") or []

    def list_branding_themes(self) -> list:
        resp = self._request("GET", f"{self.api_base}/BrandingThemes", headers=self._headers())
        return resp.json().get("BrandingThemes") or []

    def get_invoice(self, invoice_id: str) -> dict:
        resp = self._request(
            "GET", f"{self.api_base}/Invoices/{invoice_id}", headers=self._headers(),
        )
        invoices = resp.json().get("Invoices") or []
        if not invoices:
            raise XeroCallError("Xero did not return that invoice.")
        return invoices[0]

    def _write_invoice(self, body: dict) -> dict:
        payload = dict(body)
        payload["Status"] = "DRAFT"
        payload.pop("SentToContact", None)
        resp = self._request(
            "POST", f"{self.api_base}/Invoices",
            headers=self._headers(),
            json={"Invoices": [payload]},
            timeout=30,
        )
        invoices = resp.json().get("Invoices") or []
        if not invoices:
            raise XeroCallError("Xero did not return the draft.")
        invoice = invoices[0]
        if invoice.get("HasErrors"):
            messages = []
            for element in invoice.get("ValidationErrors") or []:
                messages.append(element.get("Message") or "")
            raise XeroCallError("Xero rejected the draft: " + "; ".join(m for m in messages if m))
        return invoice

    def create_invoice(self, body: dict) -> dict:
        return self._write_invoice(body)

    def update_invoice(self, body: dict) -> dict:
        if not body.get("InvoiceID"):
            raise XeroCallError("The draft has no Xero id to update.")
        return self._write_invoice(body)

    def get_invoice_pdf(self, invoice_id: str) -> bytes:
        resp = self._request(
            "GET", f"{self.api_base}/Invoices/{invoice_id}",
            headers=self._headers(accept="application/pdf", content_type=None),
            timeout=60,
        )
        return resp.content or b""

    def attach(self, invoice_id: str, filename: str, content: bytes, include_online: bool = True) -> None:
        from urllib.parse import quote
        safe = quote(filename)
        url = f"{self.api_base}/Invoices/{invoice_id}/Attachments/{safe}"
        if include_online:
            url += "?IncludeOnline=true"
        self._request(
            "POST", url,
            headers=self._headers(accept="application/json", content_type="application/pdf"),
            data=content,
            timeout=60,
        )


def public_xero(result: dict) -> dict:
    return {
        "status": result.get("status"),
        "invoice_id": result.get("invoice_id"),
        "invoice_number": result.get("invoice_number"),
        "url": result.get("url"),
        "reason": result.get("reason"),
    }
