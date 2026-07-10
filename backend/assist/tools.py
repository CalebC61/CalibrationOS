"""CalibrationOS – Module 8: Admin Assist Engine – tool layer.

Every tool the assistant can invoke is a thin wrapper around one of the app's OWN existing
/api/* endpoints, called over localhost with the requesting owner's real JWT. Nothing here
touches the database directly — a malformed LLM tool call fails the exact same request
validation a bad UI request would (400/403/404), so the assistant can never bypass the rules
the rest of the app enforces.

Risk tiering falls out of the HTTP verb each tool wraps:
  - GET-backed tools  -> tier "safe":  executed immediately, result fed back to the model.
  - POST/PUT/PATCH    -> tier "risky": never executed directly by the model loop; the agent
    returns a pending-action proposal that the owner must confirm in the UI first.

The registry (TOOL_REGISTRY) is the single source of truth consumed by both agent.py (which
builds the Gemini function declarations from it) and routes.py (which executes confirmed
pending actions through it).
"""
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.parse import quote

import httpx

# The app calls itself over localhost — same-origin, same port the backend binds (8001 per
# Emergent runtime rules). Overridable for tests via ASSIST_SELF_BASE_URL.
def _self_base_url() -> str:
    return os.environ.get("ASSIST_SELF_BASE_URL", "http://127.0.0.1:8001").rstrip("/")


async def _request(method: str, path: str, token: str,
                   params: Optional[dict] = None, json_body: Optional[dict] = None) -> dict:
    """Perform one internal API call as the owner. Returns a JSON-safe dict either way:
    {"ok": True, "data": ...} or {"ok": False, "status": int, "error": str} — tools never raise,
    so a 404/400 becomes information the model (or the confirm flow) can relay to the owner."""
    url = f"{_self_base_url()}/api{path}"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(method, url, headers=headers, params=params, json=json_body)
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text[:500]}
    if 200 <= resp.status_code < 300:
        return {"ok": True, "data": data}
    detail = data.get("detail") if isinstance(data, dict) else None
    return {"ok": False, "status": resp.status_code, "error": detail or str(data)[:300]}


@dataclass
class Tool:
    name: str
    tier: str                      # "safe" | "risky"
    description: str               # shown to the model as the function description
    parameters: dict               # JSON Schema for the function's parameters
    method: str                    # HTTP verb of the endpoint this wraps
    path_template: str             # e.g. "/jobs/{job_id}/dispatch"
    query_params: list = field(default_factory=list)   # arg names sent as query params
    body_params: list = field(default_factory=list)    # arg names sent in the JSON body
    summary_template: str = ""     # human-readable confirm-card text, .format(**args)

    async def execute(self, token: str, args: dict) -> dict:
        path = self.path_template
        used = set()
        for key, val in args.items():
            placeholder = "{" + key + "}"
            if placeholder in path:
                # quote(safe="") so an LLM-supplied arg like "../shops" can't traverse to a
                # different endpoint — it stays one opaque path segment.
                path = path.replace(placeholder, quote(str(val), safe=""))
                used.add(key)
        params = {k: v for k, v in args.items()
                  if k in self.query_params and k not in used and v is not None}
        body = {k: v for k, v in args.items()
                if k in self.body_params and k not in used and v is not None}
        return await _request(self.method, path, token,
                              params=params or None,
                              json_body=body if self.method in ("POST", "PUT", "PATCH") else None)

    def summary(self, args: dict) -> str:
        if not self.summary_template:
            return f"{self.name}({', '.join(f'{k}={v!r}' for k, v in args.items())})"
        try:
            return self.summary_template.format(**{**{"_": ""}, **args})
        except (KeyError, IndexError):
            return f"{self.name}({', '.join(f'{k}={v!r}' for k, v in args.items())})"


def _str(desc: str) -> dict:
    return {"type": "string", "description": desc}

def _num(desc: str) -> dict:
    return {"type": "number", "description": desc}

def _int(desc: str) -> dict:
    return {"type": "integer", "description": desc}

def _bool(desc: str) -> dict:
    return {"type": "boolean", "description": desc}

def _params(props: dict, required: Optional[list] = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


TOOLS: list[Tool] = [
    # ---------------- Dispatch / Jobs ----------------
    Tool(
        name="list_jobs", tier="safe", method="GET", path_template="/jobs",
        query_params=["date_str"],
        description=(
            "List jobs on the schedule. Optionally filter to a single day with date_str "
            "(YYYY-MM-DD). Returns each job's id, shop, vehicle, zone, scheduled times, status, "
            "price, and technician. Use this to find a job's id before acting on it."),
        parameters=_params({"date_str": _str("Day to list, YYYY-MM-DD. Omit for all jobs.")}),
    ),
    Tool(
        name="get_job", tier="safe", method="GET", path_template="/jobs/{job_id}",
        description="Fetch full detail for one job by its id.",
        parameters=_params({"job_id": _str("The job's id (UUID).")}, ["job_id"]),
    ),
    Tool(
        name="get_dashboard_summary", tier="safe", method="GET", path_template="/dashboard/summary",
        query_params=["date_str"],
        description=(
            "Day-level dashboard summary: job count, revenue, estimated drive miles, projected "
            "done-by time, and at-risk job count. Defaults to today; pass date_str (YYYY-MM-DD) "
            "for another day."),
        parameters=_params({"date_str": _str("Day to summarize, YYYY-MM-DD. Omit for today.")}),
    ),
    Tool(
        name="dispatch_job", tier="risky", method="POST",
        path_template="/jobs/{job_id}/dispatch", body_params=["contractor_id"],
        description=(
            "Offer a booked job to a contractor (starts a 30-minute accept/decline window and "
            "notifies them). Find the contractor's id with list_contractors first."),
        parameters=_params({
            "job_id": _str("The job's id."),
            "contractor_id": _str("The contractor's id."),
        }, ["job_id", "contractor_id"]),
        summary_template="Dispatch job {job_id} to contractor {contractor_id} (30-min offer, sends notification)",
    ),
    Tool(
        name="update_job_status", tier="risky", method="POST",
        path_template="/jobs/{job_id}/status", body_params=["status"],
        description=(
            "Advance or change a job's status: driving, on_site, complete, or cancelled. "
            "Status changes can trigger customer notifications."),
        parameters=_params({
            "job_id": _str("The job's id."),
            "status": {"type": "string", "enum": ["driving", "on_site", "complete", "cancelled"],
                        "description": "New status."},
        }, ["job_id", "status"]),
        summary_template="Set job {job_id} status to {status}",
    ),
    Tool(
        name="reschedule_job", tier="risky", method="POST",
        path_template="/jobs/{job_id}/reschedule", body_params=["scheduled_start", "reason"],
        description=(
            "Move a job to a new start time (ISO datetime). Recomputes the slot and notifies the "
            "customer. Check availability/other jobs on the target day first with list_jobs."),
        parameters=_params({
            "job_id": _str("The job's id."),
            "scheduled_start": _str("New start, ISO 8601 datetime (e.g. 2026-07-10T15:30:00+00:00)."),
            "reason": _str("Optional reason shared internally."),
        }, ["job_id", "scheduled_start"]),
        summary_template="Reschedule job {job_id} to {scheduled_start} (notifies customer)",
    ),
    Tool(
        name="cancel_job", tier="risky", method="POST",
        path_template="/jobs/{job_id}/cancel", body_params=["reason"],
        description="Cancel a job with an optional reason. Notifies the customer. Not reversible from here.",
        parameters=_params({
            "job_id": _str("The job's id."),
            "reason": _str("Why it's being cancelled."),
        }, ["job_id"]),
        summary_template="CANCEL job {job_id} (notifies customer; not reversible from the assistant)",
    ),
    Tool(
        name="reorder_jobs", tier="risky", method="POST",
        path_template="/jobs/reorder", body_params=["zone", "date", "ordered_job_ids"],
        description=(
            "Re-sequence a zone's jobs for one day; drive times and slots are recomputed in the "
            "new order. Rejected if the new order would run past the zone's end time."),
        parameters=_params({
            "zone": {"type": "string", "enum": ["west", "east"], "description": "Zone to reorder."},
            "date": _str("Day, YYYY-MM-DD."),
            "ordered_job_ids": {"type": "array", "items": {"type": "string"},
                                 "description": "Job ids in the desired new order."},
        }, ["zone", "date", "ordered_job_ids"]),
        summary_template="Reorder {zone}-zone jobs on {date} (recomputes drive times)",
    ),
    # ---------------- Shops ----------------
    Tool(
        name="list_shops", tier="safe", method="GET", path_template="/shops",
        description="List all glass-shop clients with contact info, pricing tier, zone, and booking link.",
        parameters=_params({}),
    ),
    Tool(
        name="get_shop", tier="safe", method="GET", path_template="/shops/{shop_id}",
        description="Fetch one shop's full record by id.",
        parameters=_params({"shop_id": _str("The shop's id.")}, ["shop_id"]),
    ),
    Tool(
        name="create_shop", tier="risky", method="POST", path_template="/shops",
        body_params=["name", "contact_name", "contact_phone", "contact_email", "address",
                     "pricing_tier", "custom_rate_static", "custom_rate_dynamic",
                     "custom_rate_dual", "custom_rate_triple", "custom_rate_tesla", "notes"],
        description=(
            "Create a new glass-shop client. The address is geocoded and zone-assigned "
            "automatically, and a booking link is generated."),
        parameters=_params({
            "name": _str("Shop name."),
            "address": _str("Street address (city matters — it drives zone assignment)."),
            "contact_name": _str("Primary contact person."),
            "contact_phone": _str("Contact phone, E.164 preferred."),
            "contact_email": _str("Contact email."),
            "pricing_tier": {"type": "string", "enum": ["standard", "custom"],
                              "description": "standard uses global pricing; custom uses per-shop rates."},
            "custom_rate_static": _num("Custom static-cal rate (only if pricing_tier=custom)."),
            "custom_rate_dynamic": _num("Custom dynamic-cal rate."),
            "custom_rate_dual": _num("Custom dual-cal rate."),
            "custom_rate_triple": _num("Custom triple-cal rate."),
            "custom_rate_tesla": _num("Custom Tesla-cal rate."),
            "notes": _str("Internal notes."),
        }, ["name", "address"]),
        summary_template="Create new shop \"{name}\" at {address}",
    ),
    Tool(
        name="update_shop", tier="risky", method="PUT", path_template="/shops/{shop_id}",
        body_params=["name", "contact_name", "contact_phone", "contact_email", "address",
                     "pricing_tier", "custom_rate_static", "custom_rate_dynamic",
                     "custom_rate_dual", "custom_rate_triple", "custom_rate_tesla",
                     "notes", "status"],
        description=(
            "Update a shop's record. Changing the address re-geocodes and may move it to the "
            "other zone. status can pause or deactivate the shop."),
        parameters=_params({
            "shop_id": _str("The shop's id."),
            "name": _str("New name."),
            "contact_name": _str("New contact person."),
            "contact_phone": _str("New contact phone."),
            "contact_email": _str("New contact email."),
            "address": _str("New address (re-geocodes and may change zone)."),
            "pricing_tier": {"type": "string", "enum": ["standard", "custom"], "description": "Pricing tier."},
            "custom_rate_static": _num("Custom static rate."),
            "custom_rate_dynamic": _num("Custom dynamic rate."),
            "custom_rate_dual": _num("Custom dual rate."),
            "custom_rate_triple": _num("Custom triple rate."),
            "custom_rate_tesla": _num("Custom Tesla rate."),
            "notes": _str("Internal notes."),
            "status": {"type": "string", "enum": ["active", "paused", "inactive"], "description": "Shop status."},
        }, ["shop_id"]),
        summary_template="Update shop {shop_id}",
    ),
    Tool(
        name="regenerate_booking_link", tier="risky", method="POST",
        path_template="/shops/{shop_id}/regenerate-link",
        description=(
            "Generate a new booking-link token for a shop. The OLD LINK STOPS WORKING immediately "
            "— anyone holding it can no longer book."),
        parameters=_params({"shop_id": _str("The shop's id.")}, ["shop_id"]),
        summary_template="Regenerate booking link for shop {shop_id} (old link stops working)",
    ),
    # ---------------- Settings ----------------
    Tool(
        name="get_pricing", tier="safe", method="GET", path_template="/reference/pricing",
        description="Current standard pricing for the five calibration types.",
        parameters=_params({}),
    ),
    Tool(
        name="get_zones", tier="safe", method="GET", path_template="/reference/zones",
        description="Zone configuration: West/East hours, slot length, buffer, max jobs per day.",
        parameters=_params({}),
    ),
    Tool(
        name="list_contractors", tier="safe", method="GET", path_template="/contractors",
        description="List contractors with id, name, phone, home zone, and active status.",
        parameters=_params({}),
    ),
    Tool(
        name="update_pricing", tier="risky", method="PUT", path_template="/settings/pricing",
        body_params=["static", "dynamic", "dual", "triple", "tesla"],
        description=(
            "Change standard pricing. Only pass the types being changed. Affects every future "
            "booking at standard-tier shops (already-booked jobs keep their locked price)."),
        parameters=_params({
            "static": _num("New static-cal price, USD."),
            "dynamic": _num("New dynamic-cal price, USD."),
            "dual": _num("New dual-cal price, USD."),
            "triple": _num("New triple-cal price, USD."),
            "tesla": _num("New Tesla-cal price, USD."),
        }),
        summary_template="Update standard pricing (affects all future standard-tier bookings)",
    ),
    Tool(
        name="update_zone", tier="risky", method="PUT", path_template="/settings/zones/{zone_key}",
        body_params=["start", "end", "max_jobs", "slot_minutes", "buffer_minutes"],
        description=(
            "Change a zone's schedule settings (hours, slot length, buffer, daily job cap). "
            "Affects what booking slots are offered going forward."),
        parameters=_params({
            "zone_key": {"type": "string", "enum": ["west", "east"], "description": "Which zone."},
            "start": _str("Zone opening time, HH:MM."),
            "end": _str("Zone closing time, HH:MM."),
            "max_jobs": _int("Max jobs per day in this zone."),
            "slot_minutes": _int("Slot length in minutes."),
            "buffer_minutes": _int("Drive buffer in minutes."),
        }, ["zone_key"]),
        summary_template="Update {zone_key} zone schedule settings",
    ),
    Tool(
        name="update_contractor", tier="risky", method="PUT",
        path_template="/contractors/{contractor_id}",
        body_params=["name", "phone", "home_address", "is_active"],
        description=(
            "Update a contractor's profile, or activate/deactivate them (inactive contractors "
            "can't be dispatched)."),
        parameters=_params({
            "contractor_id": _str("The contractor's id."),
            "name": _str("New name."),
            "phone": _str("New phone."),
            "home_address": _str("New home base address (re-geocoded)."),
            "is_active": _bool("false blocks new dispatches to them."),
        }, ["contractor_id"]),
        summary_template="Update contractor {contractor_id}",
    ),
    # ---------------- Growth (Module 9) ----------------
    Tool(
        name="get_growth_grid", tier="safe", method="GET", path_template="/growth/grid",
        description=(
            "The Power Connector grid: partner contacts grouped into top5/key50/vital100/prospect "
            "circles, with each circle's cap."),
        parameters=_params({}),
    ),
    Tool(
        name="list_partner_contacts", tier="safe", method="GET", path_template="/growth/contacts",
        query_params=["circle", "ecosystem", "search"],
        description="Search/filter partner contacts. Use this to find a contact's id.",
        parameters=_params({
            "circle": {"type": "string", "enum": ["top5", "key50", "vital100", "prospect"],
                        "description": "Filter to one circle."},
            "ecosystem": _str("Filter by ecosystem, e.g. glass_shop, collision, insurance."),
            "search": _str("Name/company substring search."),
        }),
    ),
    Tool(
        name="get_todays_nudges", tier="safe", method="GET", path_template="/growth/nudges/today",
        description=(
            "Today's due nurture touches (drafted messages per contact, per the 5/50/100 cadence). "
            "Each has an id, status (draft/approved/sent), channel, and message body."),
        parameters=_params({}),
    ),
    Tool(
        name="list_touches", tier="safe", method="GET", path_template="/growth/touches",
        query_params=["status", "channel", "partner_contact_id"],
        description="List nurture touches, filterable by status, channel, or contact.",
        parameters=_params({
            "status": _str("Filter: draft, pending_approval, approved, sent, failed, cancelled."),
            "channel": _str("Filter: sms, email, linkedin_dm, call, in_person."),
            "partner_contact_id": _str("Filter to one contact's touches."),
        }),
    ),
    Tool(
        name="list_intros", tier="safe", method="GET", path_template="/growth/intros",
        query_params=["status"],
        description="List 3-D introductions and their statuses.",
        parameters=_params({"status": _str("Filter: draft, approved, sent, accepted, declined.")}),
    ),
    Tool(
        name="create_partner_contact", tier="risky", method="POST", path_template="/growth/contacts",
        body_params=["first_name", "last_name", "company_name", "role", "ecosystem",
                     "circle", "phone", "email", "city", "notes"],
        description=(
            "Add a partner contact to the growth grid. Capped circles (top5=5, key50=50, "
            "vital100=100) reject the add if full — someone must be demoted first."),
        parameters=_params({
            "first_name": _str("First name."),
            "last_name": _str("Last name."),
            "company_name": _str("Their company."),
            "role": {"type": "string",
                      "enum": ["owner", "gm", "estimator", "tech", "adjuster", "fleet_mgr", "dealer_sa", "internal"],
                      "description": "Their role."},
            "ecosystem": {"type": "string",
                           "enum": ["glass_shop", "collision", "dealer", "fleet", "insurance", "distributor", "internal"],
                           "description": "Which ecosystem they belong to."},
            "circle": {"type": "string", "enum": ["top5", "key50", "vital100", "prospect"],
                        "description": "Starting circle (default prospect)."},
            "phone": _str("Phone."),
            "email": _str("Email."),
            "city": _str("City."),
            "notes": _str("Notes."),
        }, ["first_name", "last_name", "company_name"]),
        summary_template="Add {first_name} {last_name} ({company_name}) to the growth grid",
    ),
    Tool(
        name="move_contact_circle", tier="risky", method="PATCH",
        path_template="/growth/contacts/{contact_id}", body_params=["circle"],
        description=(
            "Move a partner contact to a different circle. Rejected with a conflict if the target "
            "circle is at its cap."),
        parameters=_params({
            "contact_id": _str("The contact's id."),
            "circle": {"type": "string", "enum": ["top5", "key50", "vital100", "prospect"],
                        "description": "Target circle."},
        }, ["contact_id", "circle"]),
        summary_template="Move contact {contact_id} to {circle}",
    ),
    Tool(
        name="approve_touch", tier="risky", method="POST",
        path_template="/growth/touches/{touch_id}/approve",
        description="Approve a drafted nurture touch so it becomes sendable. Does not send it yet.",
        parameters=_params({"touch_id": _str("The touch's id.")}, ["touch_id"]),
        summary_template="Approve touch {touch_id} (makes it sendable; doesn't send yet)",
    ),
    Tool(
        name="send_touch", tier="risky", method="POST",
        path_template="/growth/touches/{touch_id}/send",
        description=(
            "SEND an approved nurture touch — this delivers a REAL message (SMS or email) to the "
            "partner contact. The touch must already be approved."),
        parameters=_params({"touch_id": _str("The touch's id.")}, ["touch_id"]),
        summary_template="SEND touch {touch_id} — delivers a real SMS/email to the contact",
    ),
    Tool(
        name="create_intro", tier="risky", method="POST", path_template="/growth/intros",
        body_params=["a_contact_id", "b_contact_id", "context", "value_prop_a", "value_prop_b"],
        description=(
            "Draft a 3-D introduction between two partner contacts. Drafting is harmless — "
            "nothing is sent until the intro is separately approved and sent."),
        parameters=_params({
            "a_contact_id": _str("First contact's id."),
            "b_contact_id": _str("Second contact's id."),
            "context": _str("Why they should meet."),
            "value_prop_a": _str("What contact A gets from the intro."),
            "value_prop_b": _str("What contact B gets from the intro."),
        }, ["a_contact_id", "b_contact_id", "value_prop_a", "value_prop_b"]),
        summary_template="Draft an introduction between contacts {a_contact_id} and {b_contact_id}",
    ),
    Tool(
        name="approve_intro", tier="risky", method="POST",
        path_template="/growth/intros/{intro_id}/approve",
        description="Approve a drafted introduction so it becomes sendable. Does not send it yet.",
        parameters=_params({"intro_id": _str("The intro's id.")}, ["intro_id"]),
        summary_template="Approve intro {intro_id} (makes it sendable; doesn't send yet)",
    ),
    Tool(
        name="send_intro", tier="risky", method="POST",
        path_template="/growth/intros/{intro_id}/send",
        description=(
            "SEND an approved introduction — emails BOTH contacts for real. Both must have an "
            "email on file."),
        parameters=_params({"intro_id": _str("The intro's id.")}, ["intro_id"]),
        summary_template="SEND intro {intro_id} — emails both contacts for real",
    ),
]

TOOL_REGISTRY: dict[str, Tool] = {t.name: t for t in TOOLS}
