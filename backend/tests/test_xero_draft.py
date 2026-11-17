"""One Xero draft per job. Xero is a fake. Status is always DRAFT.

    cd backend && pytest tests/test_xero_draft.py -v
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xero_draft import HttpXeroGateway, XeroCallError, file_calibration_draft  # noqa: E402
from xero_invoice import ACCOUNT_CODE, DEFAULT_SPECIAL_RATES  # noqa: E402

STANDARD = {"static": 125.0, "dynamic": 125.0, "dual": 175.0, "triple": 185.0, "tesla": 225.0}
SCAN = b"%PDF-1.4 post-scan signed report"
DESCRIPTOR = "DAN FORSLEY - 2020 HONDA PILOT - 5FNYF5H57LB019570"

ITEMS = [
    {"Code": "Static Calibration", "Name": "Static Calibration", "Description": "Static calibration per the OEM procedure"},
    {"Code": "Dynamic Calibration", "Name": "Dynamic Calibration", "Description": "Dynamic calibration per the OEM procedure"},
    {"Code": "Dual Calibration", "Name": "Dual Calibration", "Description": "Dual calibration per the OEM procedure"},
    {"Code": "8", "Name": "Subaru MC Calibration", "Description": "Subaru EyeSight calibration"},
    {"Code": "Triple/Subaru Calibration", "Name": "Triple/Subaru Calibration", "Description": "Triple or Subaru calibration"},
    {"Code": "Tesla Calibration", "Name": "Tesla Calibration", "Description": "Tesla calibration per the OEM procedure"},
]
TAXES = [{
    "Name": "Tax Exempt",
    "TaxType": "NONE",
    "Status": "ACTIVE",
    "EffectiveRate": 0,
    "CanApplyToRevenue": True,
}]
THEMES = [{"Name": "Calibration Template", "BrandingThemeID": "THEME-CAL"}]


class FakeXero:
    """Records calls. Has no method that creates a contact or authorises an invoice."""

    def __init__(self, contacts=None, items=None, taxes=None, themes=None, fail_at=None):
        self.contacts = contacts or []
        self.items = items if items is not None else ITEMS
        self.taxes = taxes if taxes is not None else TAXES
        self.themes = themes if themes is not None else THEMES
        self.fail_at = fail_at
        self.created = []
        self.updated = []
        self.attachments = []
        self.pdfs = []
        self.contact_lookups = []
        self._n = 0
        self.status_override = None

    def _fail(self, step):
        if self.fail_at == step:
            self.fail_at = None
            raise XeroCallError(f"{step} failed")

    def find_contacts(self, name):
        self.contact_lookups.append(name)
        self._fail("contacts")
        return [c for c in self.contacts if str(c.get("Name") or "").lower() == name.lower()]

    def list_items(self):
        self._fail("items")
        return self.items

    def list_tax_rates(self):
        return self.taxes

    def list_branding_themes(self):
        return self.themes

    def create_invoice(self, body):
        self._fail("create")
        self.created.append(copy.deepcopy(body))
        self._n += 1
        lines = []
        for index, line in enumerate(body["LineItems"]):
            lines.append({**line, "LineItemID": f"LI-{self._n}-{index}"})
        status = self.status_override or "DRAFT"
        return {
            "InvoiceID": f"inv-{self._n}",
            "InvoiceNumber": f"INV-{self._n:04d}",
            "Status": status,
            "LineItems": lines,
        }

    def update_invoice(self, body):
        self._fail("update")
        self.updated.append(copy.deepcopy(body))
        return {"InvoiceID": body.get("InvoiceID"), "Status": "DRAFT", "LineItems": body.get("LineItems") or []}

    def get_invoice_pdf(self, invoice_id):
        self._fail("pdf")
        self.pdfs.append(invoice_id)
        return b"%PDF-POP"

    def attach(self, invoice_id, filename, content, include_online=True):
        self._fail("attach")
        self.attachments.append({
            "invoice_id": invoice_id,
            "filename": filename,
            "content": content,
            "include_online": include_online,
        })


def _job(**extra):
    job = {
        "id": "job-1",
        "scheduled_start": "2026-06-16T18:00:00+00:00",
        "customer_first_name": "Dan",
        "customer_last_name": "Forsley",
        "vehicle_year": 2020,
        "vehicle_make": "Honda",
        "vehicle_model": "Pilot",
        "vehicle_vin": "5FNYF5H57LB019570",
        "calibration_type": "static",
    }
    job.update(extra)
    return job


def _file(shop, pop="none", calibration_type="static", gateway=None, job=None, state=None, scan=SCAN):
    return file_calibration_draft(
        job=job or _job(),
        shop=shop,
        calibration_type=calibration_type,
        pop=pop,
        scan_pdf=scan,
        scan_name="Forsley_post_scan.pdf",
        standard_prices=STANDARD,
        special_rates=DEFAULT_SPECIAL_RATES,
        gateway=gateway or FakeXero(),
        state=state,
    )


def _statuses(gateway):
    bodies = gateway.created + gateway.updated
    return [body.get("Status") for body in bodies]


def test_no_pop_draft_is_wholesale_with_the_vehicle_line_and_one_attachment():
    shop = {"name": "Star Windshield", "xero_contact_id": "CID-STAR"}
    gateway = FakeXero()
    result = _file(shop, pop="NO", gateway=gateway)
    assert result["status"] == "draft"
    assert result["invoice_number"] == "INV-0001"
    assert result["reason"] is None
    assert gateway.contact_lookups == []
    assert len(gateway.created) == 1
    assert gateway.updated == []
    assert gateway.pdfs == []
    body = gateway.created[0]
    assert body["Type"] == "ACCREC"
    assert body["Status"] == "DRAFT"
    assert body["LineAmountTypes"] == "NoTax"
    assert body["Reference"] == ""
    assert body["Date"] == "2026-06-16"
    assert body["DueDate"] == "2026-06-16"
    assert body["BrandingThemeID"] == "THEME-CAL"
    assert body["Contact"] == {"ContactID": "CID-STAR"}
    line1, line2 = body["LineItems"]
    assert line1["ItemCode"] == "Static Calibration"
    assert line1["Description"] == "Static calibration per the OEM procedure"
    assert line1["Quantity"] == 1
    assert line1["UnitAmount"] == 125
    assert line1["AccountCode"] == ACCOUNT_CODE
    assert line1["TaxType"] == "NONE"
    assert list(line2.keys()) == ["Description"]
    assert line2["Description"] == DESCRIPTOR
    assert len(gateway.attachments) == 1
    assert gateway.attachments[0]["filename"] == "Forsley_post_scan.pdf"
    assert gateway.attachments[0]["content"] == SCAN
    assert gateway.attachments[0]["include_online"] is True
    assert _statuses(gateway) == ["DRAFT"]
    assert "AUTHORISED" not in json.dumps(gateway.created)


def test_pop_saves_at_the_pop_amount_then_updates_to_wholesale_and_attaches_both():
    shop = {"name": "Star Windshield", "xero_contact_id": "CID-STAR"}
    gateway = FakeXero()
    result = _file(shop, pop="$450.00", gateway=gateway)
    assert result["status"] == "draft"
    assert gateway.created[0]["LineItems"][0]["UnitAmount"] == 450
    assert list(gateway.created[0]["LineItems"][1].keys()) == ["Description"]
    assert gateway.pdfs == ["inv-1"]
    assert len(gateway.updated) == 1
    updated = gateway.updated[0]
    assert updated["Status"] == "DRAFT"
    assert updated["InvoiceID"] == "inv-1"
    assert updated["LineItems"][0]["UnitAmount"] == 125
    assert updated["LineItems"][0]["LineItemID"] == "LI-1-0"
    assert list(updated["LineItems"][1].keys()) == ["LineItemID", "Description"]
    names = [item["filename"] for item in gateway.attachments]
    assert names == ["Invoice INV-0001.pdf", "Forsley_post_scan.pdf"]
    assert gateway.attachments[0]["content"] == b"%PDF-POP"
    assert all(item["include_online"] is True for item in gateway.attachments)
    assert _statuses(gateway) == ["DRAFT", "DRAFT"]


def test_preferred_and_real_fast_use_their_wholesale_cards():
    preferred = FakeXero(contacts=[{"Name": "Preferred Auto Glass", "ContactID": "CID-P"}])
    result = _file({"name": "Preferred"}, pop="none", calibration_type="dynamic", gateway=preferred)
    assert result["status"] == "draft"
    assert preferred.contact_lookups == ["Preferred Auto Glass"]
    assert result["contact_id_to_save"] == "CID-P"
    assert preferred.created[0]["LineItems"][0]["UnitAmount"] == 75
    assert preferred.created[0]["LineItems"][0]["ItemCode"] == "Dynamic Calibration"
    assert preferred.created[0]["Contact"]["ContactID"] == "CID-P"

    realfast = FakeXero(contacts=[{"Name": "Real Fast Auto Glass", "ContactID": "CID-R"}])
    for cal, amount in (("static", 115), ("dynamic", 100), ("tesla", 215)):
        realfast.created.clear()
        filed = _file({"name": "Real Fast Auto Glass"}, pop="none", calibration_type=cal, gateway=realfast)
        assert filed["status"] == "draft"
        assert realfast.created[-1]["LineItems"][0]["UnitAmount"] == amount


def test_triple_uses_subaru_mc_calibration_and_the_old_name_is_only_a_fallback():
    shop = {"name": "Star Windshield", "xero_contact_id": "CID-STAR"}
    gateway = FakeXero()
    filed = _file(shop, pop="none", calibration_type="triple", gateway=gateway)
    assert filed["status"] == "draft"
    line = gateway.created[0]["LineItems"][0]
    assert line["ItemCode"] == "8"
    assert line["Description"] == "Subaru EyeSight calibration"
    assert line["UnitAmount"] == 185

    legacy_items = [item for item in ITEMS if item.get("Code") != "8"]
    legacy = FakeXero(items=legacy_items)
    filed = _file(shop, pop="none", calibration_type="triple", gateway=legacy)
    assert filed["status"] == "draft"
    assert legacy.created[0]["LineItems"][0]["ItemCode"] == "Triple/Subaru Calibration"
    assert legacy.created[0]["LineItems"][0]["UnitAmount"] == 185

    missing_items = [
        item for item in ITEMS
        if item.get("Code") not in ("8", "Triple/Subaru Calibration")
    ]
    missing = FakeXero(items=missing_items)
    result = _file(shop, pop="none", calibration_type="triple", gateway=missing)
    assert result["status"] == "needs_attention"
    assert result["invoice_id"] is None
    assert "Subaru MC Calibration" in result["reason"]
    assert "Triple/Subaru Calibration" in result["reason"]
    assert missing.created == []

    preferred = FakeXero()
    filed = _file(
        {"name": "Preferred Auto Glass", "xero_contact_id": "CID-P"},
        pop="none", calibration_type="triple", gateway=preferred,
    )
    assert filed["status"] == "draft"
    assert preferred.created[0]["LineItems"][0]["ItemCode"] == "8"
    assert preferred.created[0]["LineItems"][0]["UnitAmount"] == 165

    realfast = FakeXero()
    filed = _file(
        {"name": "Real Fast Auto Glass", "xero_contact_id": "CID-R"},
        pop="none", calibration_type="triple", gateway=realfast,
    )
    assert filed["status"] == "draft"
    assert realfast.created[0]["LineItems"][0]["ItemCode"] == "8"
    assert realfast.created[0]["LineItems"][0]["UnitAmount"] == 175


def test_unknown_contact_is_flagged_and_nothing_is_created():
    gateway = FakeXero(contacts=[])
    result = _file({"name": "Mystery Glass"}, gateway=gateway)
    assert result["status"] == "needs_attention"
    assert result["invoice_id"] is None
    assert "Mystery Glass" in result["reason"]
    assert "Nothing was created" in result["reason"]
    assert gateway.created == []
    assert gateway.attachments == []
    assert not hasattr(gateway, "create_contact")


def test_two_contacts_with_the_same_name_are_not_a_confident_match():
    gateway = FakeXero(contacts=[
        {"Name": "EAG", "ContactID": "A"},
        {"Name": "EAG", "ContactID": "B"},
    ])
    result = _file({"name": "EAG"}, gateway=gateway)
    assert result["status"] == "needs_attention"
    assert gateway.created == []
    assert "More than one" in result["reason"]


def test_retry_does_not_create_a_second_invoice():
    shop = {"name": "AIM Auto Glass", "xero_contact_id": "CID-AIM"}
    gateway = FakeXero(fail_at="attach")
    first = _file(shop, pop="none", gateway=gateway)
    assert first["status"] == "needs_attention"
    assert first["invoice_id"] == "inv-1"
    assert gateway.created and len(gateway.created) == 1
    assert gateway.attachments == []
    second = _file(shop, pop="none", gateway=gateway, state=first["state"])
    assert second["status"] == "draft"
    assert second["invoice_id"] == "inv-1"
    assert len(gateway.created) == 1
    third = _file(shop, pop="none", gateway=gateway, state=second["state"])
    assert third["status"] == "draft"
    assert len(gateway.created) == 1
    assert len(gateway.attachments) == 1


def test_pop_retry_after_a_failed_pdf_still_uses_the_same_draft():
    shop = {"name": "AIM", "xero_contact_id": "CID-AIM"}
    gateway = FakeXero(fail_at="pdf")
    first = _file(shop, pop="450", gateway=gateway)
    assert first["status"] == "needs_attention"
    assert gateway.created[0]["LineItems"][0]["UnitAmount"] == 450
    assert gateway.updated == []
    second = _file(shop, pop="450", gateway=gateway, state=first["state"])
    assert second["status"] == "draft"
    assert len(gateway.created) == 1
    assert gateway.updated[0]["LineItems"][0]["UnitAmount"] == 125
    assert [item["filename"] for item in gateway.attachments][0] == "Invoice INV-0001.pdf"


def test_a_non_draft_response_is_not_sent_on_and_is_not_filed_again():
    shop = {"name": "AIM", "xero_contact_id": "CID-AIM"}
    gateway = FakeXero()
    gateway.status_override = "AUTHORISED"
    first = _file(shop, gateway=gateway)
    assert first["status"] == "needs_attention"
    assert "AUTHORISED" in first["reason"]
    assert gateway.created[0]["Status"] == "DRAFT"
    assert gateway.attachments == []
    second = _file(shop, gateway=gateway, state=first["state"])
    assert len(gateway.created) == 1
    assert gateway.attachments == []
    assert second["status"] == "needs_attention"


def test_out_of_area_adds_a_trip_fee_line_and_a_miss_does_not_sell_the_calibration():
    shop = {"name": "Burton Glass", "xero_contact_id": "CID-B"}
    outside = FakeXero()
    filed = _file(shop, gateway=outside, job=_job(outside_service_area=True, trip_fee_kind="outside_service_area"))
    assert filed["status"] == "draft"
    lines = outside.created[0]["LineItems"]
    assert lines[0]["UnitAmount"] == 125
    assert list(lines[1].keys()) == ["Description"]
    assert lines[2]["Description"] == "TRIP FEE"
    assert lines[2]["UnitAmount"] == 30
    assert lines[2]["AccountCode"] == ACCOUNT_CODE
    assert "ItemCode" not in lines[2]

    missed = FakeXero()
    trip_only = _file(
        shop, gateway=missed,
        job=_job(calibration_not_performed=True, trip_fee_kind="bad_install"),
    )
    assert trip_only["status"] == "draft"
    missed_lines = missed.created[0]["LineItems"]
    assert missed_lines[0]["Description"] == "TRIP FEE"
    assert missed_lines[0]["UnitAmount"] == 30
    assert "ItemCode" not in missed_lines[0]
    assert list(missed_lines[1].keys()) == ["Description"]
    assert missed_lines[1]["Description"] == DESCRIPTOR


def test_trip_fee_only_draft_does_not_require_a_post_scan():
    shop = {"name": "Burton Glass", "xero_contact_id": "CID-B"}
    job = _job(calibration_not_performed=True, trip_fee_kind="bad_install")
    missing = FakeXero()
    filed = _file(shop, gateway=missing, job=job, scan=None)
    assert filed["status"] == "draft"
    assert filed["reason"] is None
    assert filed["ok"] is True
    assert missing.attachments == []
    assert missing.created[0]["LineItems"][0]["Description"] == "TRIP FEE"
    assert missing.created[0]["LineItems"][0]["UnitAmount"] == 30
    again = _file(shop, gateway=missing, job=job, scan=None, state=filed["state"])
    assert again["status"] == "draft"
    assert len(missing.created) == 1

    attached = FakeXero()
    with_scan = _file(shop, gateway=attached, job=job, scan=SCAN)
    assert with_scan["status"] == "draft"
    assert [item["filename"] for item in attached.attachments] == ["Forsley_post_scan.pdf"]
    assert attached.attachments[0]["content"] == SCAN


def test_a_calibration_still_requires_the_post_scan():
    shop = {"name": "Star Windshield", "xero_contact_id": "CID-STAR"}
    gateway = FakeXero()
    result = _file(shop, gateway=gateway, scan=None)
    assert result["status"] == "needs_attention"
    assert "post-scan" in result["reason"].lower()
    assert gateway.created == []


def test_upload_name_falls_back_when_the_last_name_is_missing():
    from xero_draft import spec_document_name

    assert spec_document_name(
        {"customer_last_name": "TESTDoc", "vehicle_make": "Toyota", "vehicle_model": "Camry", "vehicle_year": 2022},
        {"name": "Star Windshield"},
        "calibration_report.png",
    ) == "TESTDoc_STARWINDSHIELD_Toyota_Camry_2022.png"
    assert spec_document_name(
        {"vehicle_make": "Honda", "vehicle_model": "Civic", "vehicle_year": 2020},
        {"name": "Star Windshield"},
        "scan.pdf",
    ) == "CUSTOMER_STARWINDSHIELD_Honda_Civic_2020.pdf"
    assert spec_document_name(
        {"customer_last_name": None, "vehicle_make": "Ford", "vehicle_model": "F150", "vehicle_year": 2021},
        None,
        "report.PDF",
    ) == "CUSTOMER_SHOP_Ford_F150_2021.pdf"


def test_pdf_vin_replaces_the_job_vin_on_the_description_line():
    pdf = b"%PDF-1.1\nstream\nVIN 1HGCM82633A004352 end\nendstream"
    shop = {"name": "Apex Auto Glass", "xero_contact_id": "CID-A"}
    gateway = FakeXero()
    result = _file(shop, gateway=gateway, scan=pdf, job=_job(vehicle_vin=""))
    assert result["status"] == "draft"
    assert result["learned_vin"] == "1HGCM82633A004352"
    note = gateway.created[0]["LineItems"][1]["Description"]
    assert note == "DAN FORSLEY - 2020 HONDA PILOT - 1HGCM82633A004352"


def test_http_gateway_forces_draft_and_asks_for_a_pdf_with_include_online(monkeypatch):
    calls = []

    class Resp:
        status_code = 200
        content = b"%PDF"
        text = ""

        def json(self):
            return {"Invoices": [{
                "InvoiceID": "abc",
                "InvoiceNumber": "INV-9",
                "Status": "DRAFT",
                "LineItems": [],
            }]}

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return Resp()

    monkeypatch.setattr("xero_draft.requests.request", fake_request)
    gateway = HttpXeroGateway("token", "tenant", "https://api.xero.com/api.xro/2.0")
    gateway.get_invoice_pdf("abc")
    assert calls[0][2]["headers"]["Accept"] == "application/pdf"
    assert "Content-Type" not in calls[0][2]["headers"]
    gateway.attach("abc", "Invoice INV-9.pdf", b"%PDF", include_online=True)
    assert "IncludeOnline=true" in calls[1][1]
    assert calls[1][2]["headers"]["Content-Type"] == "application/pdf"
    assert calls[1][2]["data"] == b"%PDF"
    gateway.create_invoice({"Status": "AUTHORISED", "Type": "ACCREC", "LineItems": []})
    sent = calls[2][2]["json"]["Invoices"][0]
    assert sent["Status"] == "DRAFT"
    assert "SentToContact" not in sent
    gateway.find_contacts('Preferred Auto Glass')
    assert 'Name=="Preferred Auto Glass"' in calls[3][2]["params"]["where"]
