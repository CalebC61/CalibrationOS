"""The Xero draft Maddy files by hand, as data.

One ACCREC draft per completed job. Due the same day as the job. No tax.
Line 1 is the calibration item at the shop's wholesale rate. Line 2 is only
the customer, vehicle, and VIN. A trip fee is its own priced line when the
job is flagged. Nothing here talks to Xero, and nothing here creates a contact.
"""
import re
import zlib
from datetime import datetime

from billing import TRIP_FEE_DOLLARS
from business_time import business_date

ACCOUNT_CODE = "4100"
BRANDING_THEME_NAME = "Calibration Template"
TRIP_DESCRIPTION = "TRIP FEE"

ITEM_NAMES = {
    "static": "Static Calibration",
    "dynamic": "Dynamic Calibration",
    "dual": "Dual Calibration",
    "triple": "Triple/Subaru Calibration",
    "tesla": "Tesla Calibration",
}

# Shop code or shop name -> the contact that already exists in Xero.
# The app looks the contact up. It does not create one.
KNOWN_CONTACTS = {
    "PREFERRED": "Preferred Auto Glass",
    "REALFAST": "Real Fast Auto Glass",
    "STAR": "Star Windshield",
    "DYNAMIC": "Dynamic Auto Glass",
    "AIM": "AIM Auto Glass",
    "PINEDA": "Pinedas Auto Glass",
    "WARRIOR": "American Warrior Auto Glass",
    "11BRAVO": "11 Bravo Mobile Auto Glass",
    "JL": "J&L Auto Glass",
    "APEX": "Apex Auto Glass",
    "BURTON": "Burton Glass",
    "AGS": "AGS Auto Glass",
    "MONROYS": "Monroys Auto Glass",
    "EAG": "EAG",
    "AGE": "Auto Glass Excellence",
    "ALIGN": "Align Auto Glass",
    "REN": "Mobile Glassworks",
    "GLASSWORKS": "Mobile Glassworks",
}

RATE_SCHEDULE_FOR_KEY = {
    "REALFAST": "realfast",
    "PREFERRED": "preferred",
}

# Standard rates live on the owner's pricing screen. These two are the other
# wholesale cards, edited in Settings and stored in app_settings.
DEFAULT_SPECIAL_RATES = {
    "realfast": {
        "static": 115.0,
        "dynamic": 100.0,
        "dual": 165.0,
        "triple": 175.0,
        "tesla": 215.0,
    },
    "preferred": {
        "static": 115.0,
        "dynamic": 75.0,
        "dual": 165.0,
        "triple": 165.0,
        "tesla": 215.0,
    },
}

_RATE_KEYS = ("static", "dynamic", "dual", "triple", "tesla")
_SUFFIXES = {"LLC", "INC", "CO", "AZ"}
_VIN_RE = re.compile(r"(?<![A-HJ-NPR-Z0-9])([A-HJ-NPR-Z0-9]{17})(?![A-HJ-NPR-Z0-9])")
_VIN_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
_VIN_VALUES = {
    **{str(i): i for i in range(10)},
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
    "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
}
_NONE_POP = {"no", "none", "n/a", "na", "null", "nil"}


def money(value) -> float:
    return round(float(value), 2)


def merge_special_rates(saved) -> dict:
    """Defaults, with any saved Real Fast / Preferred amounts written over them."""
    merged = {name: dict(card) for name, card in DEFAULT_SPECIAL_RATES.items()}
    if not isinstance(saved, dict):
        return merged
    for name, card in saved.items():
        if name not in merged or not isinstance(card, dict):
            continue
        for key in _RATE_KEYS:
            if card.get(key) is None:
                continue
            merged[name][key] = money(card[key])
    return merged


def _compact(value) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _known_key(value) -> str | None:
    """The mapping key when `value` is that shop, or None when it is not one of them."""
    compact = _compact(value)
    if not compact:
        return None
    hits = []
    for key, xero_name in KNOWN_CONTACTS.items():
        bases = {_compact(key), _compact(xero_name)}
        if compact in bases:
            hits.append(key)
            continue
        for base in bases:
            if len(base) < 3 or not compact.startswith(base):
                continue
            if compact[len(base):] in _SUFFIXES:
                hits.append(key)
    unique = list(dict.fromkeys(hits))
    if len(unique) == 1:
        return unique[0]
    return None


def contact_search_name(shop: dict | None) -> str | None:
    """Exact Xero contact name to look up. None when the shop already has an id."""
    shop = shop or {}
    if str(shop.get("xero_contact_id") or "").strip():
        return None
    explicit = str(shop.get("xero_contact_name") or "").strip()
    if explicit:
        return explicit
    for source in (shop.get("shop_code"), shop.get("name")):
        key = _known_key(source)
        if key:
            return KNOWN_CONTACTS[key]
    raw = str(shop.get("name") or "").strip()
    return raw or None


def rate_schedule_name(shop: dict | None) -> str:
    """standard, realfast, preferred, or custom.

    An explicit wholesale_schedule on the shop wins. Otherwise Real Fast and
    Preferred are recognized by name. Everyone else is standard, and a custom
    pricing tier uses that shop's own rates.
    """
    shop = shop or {}
    choice = str(shop.get("wholesale_schedule") or "").strip().lower()
    if choice in {"standard", "realfast", "preferred", "custom"}:
        return choice
    for source in (shop.get("shop_code"), shop.get("name")):
        key = _known_key(source)
        if key in RATE_SCHEDULE_FOR_KEY:
            return RATE_SCHEDULE_FOR_KEY[key]
    if shop.get("pricing_tier") == "custom":
        return "custom"
    return "standard"


def wholesale_amount(shop, calibration_type: str, standard_prices: dict, special_rates: dict) -> float:
    """The shop's wholesale unit amount for this calibration type."""
    if calibration_type not in ITEM_NAMES:
        raise ValueError("Pick a calibration type, then retry the Xero draft.")
    schedule = rate_schedule_name(shop)
    if schedule == "custom":
        custom = (shop or {}).get(f"custom_rate_{calibration_type}")
        if custom is None:
            raise ValueError("This shop has no custom rate for that calibration.")
        return money(custom)
    if schedule == "standard":
        if calibration_type not in standard_prices:
            raise ValueError("Pick a calibration type, then retry the Xero draft.")
        return money(standard_prices[calibration_type])
    card = (special_rates or {}).get(schedule) or {}
    if calibration_type not in card:
        raise ValueError("That wholesale rate is not set.")
    return money(card[calibration_type])


def parse_pop(value):
    """A dollar amount, or None for blank, 0, NO, or none.

    Raises ValueError when the field is present and is not a number.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        amount = float(value)
        return money(amount) if amount > 0 else None
    text = str(value).strip()
    if not text or text.lower() in _NONE_POP:
        return None
    cleaned = text.replace("$", "").replace(",", "").strip()
    try:
        amount = float(cleaned)
    except ValueError:
        raise ValueError("POP must be a dollar amount, or none.") from None
    if amount != amount:  # NaN
        raise ValueError("POP must be a dollar amount, or none.")
    return money(amount) if amount > 0 else None


def _piece(value) -> str:
    return " ".join(str(value or "").split())


def vehicle_descriptor(first, last, year, make, model, vin) -> str:
    """FIRST LAST - YEAR MAKE MODEL - VIN, in capitals."""
    who = _piece(" ".join(part for part in (_piece(first), _piece(last)) if part)).upper()
    car = _piece(" ".join(part for part in (_piece(year), _piece(make), _piece(model)) if part)).upper()
    vin_text = _piece(vin).upper()
    return " - ".join(part for part in (who, car, vin_text) if part)


def vin_ok(vin: str) -> bool:
    """True when `vin` is 17 characters and the check digit matches."""
    if not isinstance(vin, str) or len(vin) != 17:
        return False
    if any(ch not in _VIN_VALUES for ch in vin):
        return False
    total = sum(_VIN_VALUES[ch] * weight for ch, weight in zip(vin, _VIN_WEIGHTS))
    check = total % 11
    expected = "X" if check == 10 else str(check)
    return vin[8] == expected


def _vins_in_text(text: str) -> list[str]:
    found = []
    for match in _VIN_RE.findall((text or "").upper()):
        if vin_ok(match) and match not in found:
            found.append(match)
    return found


def vin_from_pdf(data: bytes | None) -> str | None:
    """A VIN printed in the post-scan PDF, when the file actually contains one."""
    if not data:
        return None
    chunks = [data.decode("latin-1", errors="ignore")]
    for match in re.finditer(rb"stream\r?\n", data):
        end = data.find(b"endstream", match.end())
        if end == -1:
            continue
        raw = data[match.end():end].strip(b"\r\n")
        try:
            inflated = zlib.decompress(raw)
        except zlib.error:
            continue
        chunks.append(inflated[:2_000_000].decode("latin-1", errors="ignore"))
    for text in chunks:
        found = _vins_in_text(text)
        if found:
            return found[0]
    return None


def _as_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def invoice_date(job: dict | None) -> str:
    """The job's calendar date in Phoenix. Due the same day."""
    job = job or {}
    moment = _as_datetime(job.get("scheduled_start")) or _as_datetime(job.get("actual_completion"))
    if moment is None:
        return business_date().isoformat()
    return business_date(moment).isoformat()


def trip_fee_wanted(job: dict | None) -> bool:
    job = job or {}
    if job.get("calibration_not_performed"):
        return True
    if job.get("outside_service_area"):
        return True
    return bool(job.get("trip_fee_kind"))


def calibration_skipped(job: dict | None) -> bool:
    """A trip-fee-only job was not calibrated, so the draft does not sell a calibration."""
    return bool((job or {}).get("calibration_not_performed"))


def find_branding_theme(themes) -> dict | None:
    matches = [
        theme for theme in (themes or [])
        if str(theme.get("Name") or "").strip().lower() == BRANDING_THEME_NAME.lower()
    ]
    if len(matches) != 1:
        return None
    if not matches[0].get("BrandingThemeID"):
        return None
    return matches[0]


def find_item(items, calibration_type: str) -> dict | None:
    target = ITEM_NAMES.get(calibration_type)
    if not target:
        return None
    target_compact = _compact(target)
    matches = []
    for item in items or []:
        code = str(item.get("Code") or "").strip()
        name = str(item.get("Name") or "").strip()
        if code.lower() == target.lower() or name.lower() == target.lower():
            matches.append(item)
            continue
        if _compact(code) == target_compact or _compact(name) == target_compact:
            matches.append(item)
    unique = []
    seen = set()
    for item in matches:
        marker = item.get("ItemID") or item.get("Code") or id(item)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(item)
    if len(unique) != 1 or not (unique[0].get("Code") or unique[0].get("Name")):
        return None
    return unique[0]


def item_description(item: dict) -> str:
    text = str(item.get("Description") or "").strip()
    if text:
        return text
    return str(item.get("Name") or item.get("Code") or "").strip()


def find_exempt_tax(rates) -> dict | None:
    """The revenue tax rate named Tax Exempt. One match, or none."""
    active = []
    for rate in rates or []:
        status = str(rate.get("Status") or "ACTIVE").upper()
        if status != "ACTIVE":
            continue
        if rate.get("CanApplyToRevenue") is False:
            continue
        if not rate.get("TaxType"):
            continue
        active.append(rate)
    named = [rate for rate in active if str(rate.get("Name") or "").strip().lower() == "tax exempt"]
    if len(named) == 1:
        return named[0]
    if len(named) > 1:
        return None
    exempt = [
        rate for rate in active
        if "exempt" in str(rate.get("Name") or "").lower()
        and float(rate.get("EffectiveRate") or rate.get("DisplayTaxRate") or 0) == 0
    ]
    if len(exempt) == 1:
        return exempt[0]
    none = [rate for rate in active if rate.get("TaxType") == "NONE"]
    if len(none) == 1:
        return none[0]
    return None


def calibration_line(item: dict, tax_type: str, amount: float) -> dict:
    return {
        "ItemCode": item.get("Code") or item.get("Name"),
        "Description": item_description(item),
        "Quantity": 1,
        "UnitAmount": money(amount),
        "AccountCode": ACCOUNT_CODE,
        "TaxType": tax_type,
    }


def descriptor_line(description: str) -> dict:
    """Description only. No item, quantity, price, account, or tax."""
    return {"Description": description}


def trip_line(tax_type: str, amount: float = TRIP_FEE_DOLLARS) -> dict:
    return {
        "Description": TRIP_DESCRIPTION,
        "Quantity": 1,
        "UnitAmount": money(amount),
        "AccountCode": ACCOUNT_CODE,
        "TaxType": tax_type,
    }


def invoice_body(*, contact_id: str, date: str, branding_theme_id: str, line_items: list) -> dict:
    return {
        "Type": "ACCREC",
        "Contact": {"ContactID": contact_id},
        "Date": date,
        "DueDate": date,
        "Status": "DRAFT",
        "LineAmountTypes": "NoTax",
        "BrandingThemeID": branding_theme_id,
        "Reference": "",
        "LineItems": line_items,
    }


def invoice_update_body(*, invoice_id: str, line_items: list) -> dict:
    return {
        "InvoiceID": invoice_id,
        "Status": "DRAFT",
        "LineItems": line_items,
    }


def invoice_link(invoice_id: str) -> str:
    return f"https://go.xero.com/AccountsReceivable/View.aspx?InvoiceID={invoice_id}"


def job_text(job, vehicle, job_key, vehicle_key) -> str:
    value = (job or {}).get(job_key)
    if value is None or str(value).strip() == "":
        value = (vehicle or {}).get(vehicle_key)
    if value is None:
        return ""
    return str(value).strip()
