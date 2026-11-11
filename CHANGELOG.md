# Changelog

All notable changes to CalibrationOS are recorded here. This file is the reconciliation
log between **Emergent AI** and **Claude Code** — every session must append what it did
in plain, technical language so neither system loses context across a handoff.

Format follows [Keep a Changelog](https://keepachangelog.com/). Newest entries on top.

---

## [0.1.0] — current

App version is **0.1.0**, the same number as `frontend/package.json`. `[0.0.3]` further
down is the previous cut (Xero, 2026-06-16), not a second current version.
`backend/tests/test_version.py` fails if the top changelog heading and the package
version drift apart.

### Changed — fewer Google Routes calls (2026-11-11)
Traffic-aware Compute Routes Pro is only for today, and for tomorrow while
it is still before 10:00 AM Phoenix. Later dates use TRAFFIC_UNAWARE
(Essentials), which rejects `departureTime`, plus a 1.25× rush multiplier
from 6:30–9:00 AM and 3:30–6:30 PM. Those windows, the multiplier, the 10:00
cutoff, and the daily caps are owner settings (defaults: Pro 300/day,
Essentials 600/day). Past the cap, drive time falls back to the mileage
estimate and a warning is logged. Settings shows today's counts.

Future departures share a 30-minute bucket. Same-day stays at 15 minutes.
A return home is one call per hour on Pro and one call on Essentials. A
slot that cannot work even at 60 mph never calls Google. A book or an edit
rechecks only the previous stop, the new stop, and the next stop. Future
results stay cached for 7 days or until that date ends. Pro results stay
for 2 hours. Geocodes are cached by the normalized address.

### Fixed — first stop on an empty future day, and Routes 403 logs (2026-11-11)
On an empty future day the technician may leave home at 6:00 AM. A first stop
is offered when arrival minus the drive is still at or after 6:00. An 8:00 AM
Surprise arrival with a 96-minute drive leaves at 6:24 AM and is confirmed.
Times before 8:00 AM that still fit stay pending approval. Same-day limits
are unchanged. A failed `computeRoutes` call, including HTTP 403, logs the
response body with the API key removed.

### Added — early arrivals, traffic-aware drive times, and today's route limits (2026-11-11)
Shops keep one booking page. The scheduler decides from the Phoenix date.

A later date, including a request made the night before, uses the whole-valley
route. Arrivals from 6:00 AM are offered. Before 8:00 AM the job is
`requested` (pending owner approval) and still holds the slot. 8:00 AM–5:00 PM
is confirmed as before. The first stop of the day before 8:00 AM does not
wait on the drive from home; the technician leaves early. Drive time between
jobs still applies.

A booking for today uses the technician's current place (the last job, or a
fresh `live_lat` / `live_lng` / `live_at` when one is stored). It is confirmed
only when the extra drive and the later finish stay inside the technician's
limits (defaults: 20 minutes extra drive, 45 minutes later finish). Past that,
the time is held for approval, or hidden, depending on Settings → Technicians.
Today can be turned off. The cutoff defaults to 1:00 PM. There is no separate
shop control and no "add-on" label. The shop sees the times it can book, and
"Pending approval" when the owner still has to say yes.

Job length defaults to 20 minutes and the buffer between stops defaults to
15. Both are editable per technician.

Drive times call the Routes API `computeRoutes` with `TRAFFIC_AWARE` and that
leg's departure time when `GOOGLE_MAPS_API_KEY` is set. Cache: 12 hours, by
rounded coordinates and a 15-minute departure bucket. A missing key or a
failed call is logged and the mileage estimate is used. Approve and decline
(`POST /api/jobs/{id}/approve` and `/decline`, owner only) do not send SMS or
email. `notify_booking_approval` is the hook. Technicians and contractors
cannot edit jobs or approve times.

### Changed — one technician covers the whole valley (2026-11-11)
Booking, slot availability, the dispatch board, and the route map no longer
split the day into hard-coded East and West. With one active routing
technician (Caleb, home base Gilbert unless the owner changes it), every
in-valley job is theirs. Morning stays bookable when an afternoon job
already exists, and the other way around. A seeded contractor does not
take a side of the valley.

The owner can add technicians under Settings → Technicians. Each one has a
geocoded home base, a day window, and an optional service radius. With two
or more, a job goes to a tech whose radius covers it, otherwise to the
nearest home. Pins and route lines use each tech's color. Existing
appointment times are not moved. Jobs missing a technician are attached to
the owner. Only the owner can edit technicians. No SMS or email is sent.
Shop booking links, job edits, and Refresh map locations are unchanged.
The stored east/west label is still written by geocoding so older tools
keep working; it does not decide who drives or which slots are offered.

Each technician's day is one route. Offered times are grid arrivals that
fit the drive from the previous stop and the drive to the next stop, plus
a 20-minute job and a 15-minute buffer, including gaps between jobs.
`POST /api/public/book` and edits that change the time or address run that
check again and reject a conflict. A Surprise arrival and a San Tan Valley
arrival cannot share 8:00 AM. Shops are not offered an arrival after
5:00 PM. Nothing new is texted or emailed.

Deferred from the smart-scheduling plan (PR #12): shop-facing arrival
windows instead of a clock time, sliding later ETAs inside a window, the
per-day booking lock, the one-time +7 hour restamp, and a text when a
drag moves an ETA out of a promised window.

### Added — edit jobs and shop addresses (2026-11-11)
Dispatch job cards and the field job screen have an Edit button. It can change
the address, customer name, phone, email, vehicle, service, price, Phoenix
date and time, zone, and notes. `PATCH /api/jobs/{id}` saves that. A new
address is geocoded with Google when `GOOGLE_MAPS_API_KEY` is set (otherwise
the mock). An explicit zone still wins over the geocoded zone. Only an owner can
call `PATCH /api/jobs/{id}` or save a shop. Technicians and contractors,
including a contractor assigned to the job, get 403. Edit is hidden on
dispatch and the field screen unless the signed-in role is owner. The
shop booking link is unchanged.

Shops → Edit opens the existing shop form (name, address, contacts). Changing
the address re-geocodes that shop the same way.

`/book/:token` lists that shop’s upcoming jobs. The shop can edit the same
fields except price and zone, or cancel. The token cannot read or change
another shop’s jobs. Edits store `updated_at` and `edit_history` (who, when,
which fields). Editing and this cancel do not send SMS or email, and do not
change status unless the shop cancels.

### Added — Refresh map locations on dispatch (2026-11-11)
The owner dispatch board has a **Refresh map locations** button beside the route
map. It asks for confirmation, then `POST /api/admin/regeocode` with no date
(shops and jobs). The confirm copy states that this only updates coordinates
and sends no messages. The button shows shops and jobs counts for updated,
failed, and skipped, then reloads the day's jobs so the map uses the new pins.
No endpoint behavior changed.

### Fixed — route map tiles, booking notes, re-geocode (2026-11-11)
CARTO's public `dark_all` raster URL now returns one "API KEY REQUIRED" watermark
for every tile (same PNG, etag `wm-da89c20e77c1-dark`). The dispatch route map and
the shop day map use Esri World Dark Gray instead (street canvas plus a label
overlay). Those tiles load with no key. Attribution is Esri, HERE, Garmin,
OpenStreetMap contributors, and the GIS user community.

`POST /api/public/book` (and `POST /api/portal/book`, which calls it) accepts
optional `notes` (max 4000) and `customer_first_name` (max 80). Blank text is
stored as null. Both are written on the job; the first name is also on the
vehicle. The public page `/book/:token` collects them, including when an owner
opens Book a job and sets a custom time. The shop portal booking form does too.
Dispatch cards, the field job screen, and the portal job page show them.
A completion note replaces booking notes only when the technician types one.
Confirmation SMS is unchanged. Nothing new is emailed or texted.

`POST /api/admin/regeocode` is owner-only. With no query it re-geocodes every
shop and every job and writes coordinates and zone. Shops use `lat`/`lng`;
jobs use `job_lat`/`job_lng`. With `GOOGLE_MAPS_API_KEY` set it calls Google
and counts a failure as `failed` without writing the mock centroid. With no
key it uses the mock geocoder. `?date=YYYY-MM-DD` limits the run to jobs on
that America/Phoenix day and does not touch shops. The body is
`{"date": null, "shops": {"updated", "unchanged", "skipped", "failed"}, "jobs": {...}}`
(`shops` is null on a dated run). It does not send SMS or email and does not
change job status. A point outside the metro moves the pin and leaves zone as it was.

### Fixed — public booking and Phoenix slot clocks (2026-11-11)
`/book/:token` is routed. Logged-out visitors and a logged-in owner both reach
`PublicBooking`; the catch-all no longer sends that URL to the dashboard.
Shop detail has a Book a job button for that shop's token. An owner on the
booking page can type any time on the chosen date, which is stored as the
matching UTC instant (Phoenix is UTC−7, no DST).

Zone hours are America/Phoenix. West 08:00 is 15:00 UTC, not 08:00 UTC (which
displayed as 1:00 AM). East 14:30–19:00 crosses UTC midnight and stays on that
Phoenix day. `scheduled_start` is still a UTC ISO string. Dispatch, the route
map, and `formatTime` render it in America/Phoenix. Booking still logs a mock
SMS and does not send email.

### Changed — self-host deploy targets (2026-11-11)
The website is `thecalibrationcrew.us` and `www` (Vercel). The API stays
`api.thecalibrationcrew.us` (Render). `DEPLOY.md` no longer tells you to create an Atlas
user named `calibrationos`; any read/write user works, including `admin_db_user`.
`CORS_ORIGINS` should list both web origins. Assist calls itself at `http://127.0.0.1:$PORT`
when `ASSIST_SELF_BASE_URL` is blank, so Render's assigned port works. The login form no
longer prefills the dev owner password.

### Fixed — zero-length zone slots (2026-10-29)
`offered_slot_starts()` stepped by `slot_minutes`. A zone saved with `slot_minutes` of 0
(allowed by `PUT /settings/zones/{zone_key}`) never advanced the cursor, so availability
looped forever. Nonpositive lengths now raise before the loop, and the zone settings
endpoint rejects them with 400. Negative lengths are rejected too.

### Fixed — Phoenix day boundaries for the shop day map (and the same date window elsewhere) (2026-10-27)
Job queries treated a calendar date as UTC midnight-to-midnight and defaulted "today" to
`now_utc().date()`. The shop is in America/Phoenix (UTC−7, no DST), so a 6 PM Phoenix job is
01:00 UTC the next day and was missing from that Phoenix date. From 5 PM to midnight Phoenix,
"today" was already tomorrow.

- **New `backend/business_time.py`** (stdlib `zoneinfo` only). `business_date()` is the Phoenix
  civil date of an instant (default: now). `business_day_bounds()` is that day's half-open window
  as UTC datetimes (07:00 UTC through 07:00 UTC next day). Naive datetimes are UTC, same as the
  rest of the backend.
- **Query windows and default dates** now use that helper: `GET /portal/day-map`, `GET /jobs`,
  `GET /dashboard/summary`, `POST /jobs/reorder`, `compute_available_slots` (availability),
  `POST /public/book` (previous-job drive time and `sequence_order`, using the Phoenix date of
  the start instant), and `POST /public/availability` ("today" for the past / 21-day checks).
  Assist tools that call `/jobs` and `/dashboard/summary` pick this up with no tool changes.
- **Not changed:** zone start/end clocks (`08:00`–`19:00`) are still combined as UTC wall times.
  Those slots are 1:00 AM–12:00 PM Phoenix, so they stay on the same civil date. Reinterpreting
  them as Phoenix local time would shift every existing appointment by 7 hours.
- **Portal date pickers** (`frontend/src/lib/api.js` `phoenixTodayStr`, `Intl` `America/Phoenix`,
  no new dependency). The day map's initial date and the portal booking date input's min/max were
  `toISOString().slice(0, 10)` (the UTC date). They now use today's Phoenix date. Booking's max is
  that date plus 21 days (Phoenix has no DST, so 21×24h lands on the same civil date). Owner
  dashboard, field app, and public booking already used the browser's local calendar date
  (`todayStr` / `dateStr`), not a UTC timestamp, and were left as they are.
- **Drive times:** `get_drive_time` already cached real Distance Matrix results in `drive_time_cache`
  (rounded coordinates, TTL index left at 2 days). The cache day was the UTC date, so it rolled at
  5 PM Phoenix. It now uses the Phoenix date. No second cache. `GET /portal/day-map` runs the
  per-other-shop lookup concurrently (`asyncio.gather`, order preserved). The mock path stays
  uncached. No new dependency.
- **Tests:** `backend/tests/test_business_time.py`. A 6 PM Phoenix instant on 2026-10-27 is inside
  that Phoenix day's bounds (and its ISO string sorts inside them) and outside the old UTC-midnight
  window. January and July offsets are both −07:00. Existing 08:00–19:00 UTC slot clocks stay on
  the labeled day.
- **Slots stay on the day they are offered** (review follow-up). Zone hours are still UTC wall
  clocks, including hours saved via `PUT /settings/zones/{zone_key}`. A zone of `05:00`–`10:00`
  was offering 05:00 UTC, which is the previous Phoenix evening, so the booking did not match
  the Phoenix-day job query and the slot could be offered again. `offered_slot_starts()` skips
  those starts. `POST /jobs/reorder` clamps a computed start that would fall before the Phoenix
  day up to that day's start, and still rejects a start that would land on a later day.
  Default 08:00 UTC zones are unchanged.
- **One paid lookup per drive-time key.** `asyncio.gather` on the day map let jobs that share a
  rounded destination all miss an empty cache and each call Google. `coalesce()` shares the
  in-flight request for a `drive_time_cache_key`. The mock path is still uncached.

### Added — Impeccable design guidance (no runtime dependency)
Vendored the Impeccable skill (v4.8.0, Apache 2.0, Paul Bakaus, commit
`d34c87e`) as agent guidance so later UI work does not drift into generic
AI-looking design. Markdown only: `.cursor/skills/impeccable/SKILL.md` plus
`reference/`, with `LICENSE` and `NOTICE`. The upstream `scripts/` launcher
and live-browser bundle are not included, and `impeccable` is not a package
dependency. `.cursor/rules/impeccable-design.mdc` and a short section in
`CLAUDE.md` point at the skill and record the brand.

Brand orange is **#FF5F1F** (`--accent`) for fills. Small text on gunsteel uses
`--accent-ink` (#FF7E1E); text on an orange tint uses `--accent-on-tint`. A
`npx impeccable detect` pass (source regex on `frontend/src`, plus a rendered
scan of login, dashboard, portal jobs, and a job detail page) found no regex
hits and a short list of rendered issues. Fixed only the trivial ones: muted
label contrast, zone-header and east/west badge contrast, white-on-blue map
pins, the Leaflet attribution bar, the 10px "Shop Portal" tag (floor is now
12px), the "Dispatch board" kicker above the date heading, and the skipped
heading on the job detail page (`h3` → `h2`, same visual class), and the
zero-offset orange glow on a new job card. A rescan of those four rendered
pages reports no remaining findings. Not done here: a layout or type redesign,
and installing Impeccable's hooks or CLI as a dependency.

### Added — Real card charging via Stripe (2026-07-21)
Wires up the Charge Queue, which previously listed completed jobs with a card on file but had no
way to actually bill them — the "Charge Now" button existed in the UI but was disabled
("next iteration"). This was the last open code launch-blocker.

- **New module `backend/charging.py`** — pure, stdlib-only, unit-tested: `cents()` (dollar→cent
  conversion, handles float noise like `0.1+0.2`), `chargeable_reason()` (centralized eligibility
  check — job complete, not already charged, shop has a Stripe customer + card on file),
  `interpret_payment_intent()` (classifies a PaymentIntent's status into succeeded /
  requires_action / other), `decline_message()` (formats a card decline for the owner).
- **`POST /api/charge-queue/{job_id}/charge`** (owner-only) — creates and confirms an off-session
  Stripe `PaymentIntent` for the job's price against the shop's stored `stripe_customer_id` +
  `stripe_payment_method_id`. **Idempotent per job** (`idempotency_key=f"charge-job-{job_id}"`) so
  a double-click or retried request can never double-charge — Stripe dedupes concurrent requests
  sharing a key on its own. On success: sets `charged_at`, `charge_method: "stripe"`,
  `stripe_payment_intent_id`, `charged_amount` on the job (removing it from the queue, whose query
  already filters on `charged_at` not existing). On a card decline (`CardError`) or a stuck
  `requires_action` state (rare — issuer wants authentication the app can't complete without the
  shop present): the job is **not** marked charged, a `charge_error`/`charge_error_at` is recorded
  and returned to the owner, and the job stays in the queue for a retry. Never fails a booking flow
  — this is an owner-initiated action, not automatic.
  - Fixed while wiring this up: `stripe.error.CardError`'s `decline_code` is **not** a direct
    attribute of the exception — it lives on the nested `e.error` object
    (`e.error.decline_code`). Verified against the installed `stripe` package source directly
    rather than assumed.
- **`POST /api/charge-queue/{job_id}/skip`** (owner-only, optional `reason`) — the "Skip / Bill
  Manually" escape hatch already stubbed in the UI. Marks the job `charge_method: "manual"` and
  sets `charged_at` (leaves the queue) without touching Stripe — for jobs the owner wants to
  invoice outside the app.
- **Frontend** (`frontend/src/pages/ChargeQueue.jsx`) — both buttons wired: per-row busy state,
  inline decline/error messages (from the request and, on reload, from the persisted
  `charge_error` field so a prior failure is still visible after a page refresh), confirmation
  dialog before skipping.
- **Tests:** `backend/tests/test_charging.py` (14 pure tests) — cent conversion incl. float-noise
  cases, every eligibility-rejection reason, PaymentIntent status interpretation, decline-message
  formatting. No live Stripe call is testable/mocked in this pass (consistent with how the Xero
  and Google Maps integrations were tested — pure logic only; no CI or Stripe test key available
  in this environment). **Recommended before relying on this in production:** run one real charge
  through Stripe **test mode** (`sk_test_...` key + card `4242 4242 4242 4242`) end-to-end.
- **No new env var** — reuses the existing `STRIPE_API_KEY` (already required for card capture).
  Charging is only guarded by the same "is this the placeholder key" check already used elsewhere.
- **Deliberately not built here:** automatic charge-on-completion (this stays a reviewed,
  owner-triggered action from the queue, matching the page's own original design intent), and
  webhook-based handling of `requires_action` (would need `STRIPE_WEBHOOK_SECRET` + a registered
  endpoint — out of scope for a Friday launch; the rare stuck case is surfaced to the owner
  instead of silently retried).

### Added — Real Google Maps (geocoding + drive time), credential-optional (2026-07-21)
Mirrors the existing Stripe/Resend/Xero "real-if-key-present, else mock" pattern: when
`GOOGLE_MAPS_API_KEY` is set, addresses are geocoded and drive times computed via the real Google
Geocoding + Distance Matrix APIs; otherwise the app falls back to the existing mock exactly as
before, so nothing breaks without a key. This was the last of the three launch-blocking mocks
(Stripe/Resend/Xero already real; Twilio is on hold, not required for MVP).

- **New module `backend/google_maps.py`** — stdlib-only, unit-tested request-param builders +
  response parsers for both APIs, shared by the real path (server.py has no parsing logic of its
  own). Uses the same Phoenix-metro bounding box the mock always used (now imported from this
  module into `mock_geocode` too, so real and mock never disagree on what's "in service area").
- **`geocode_address()` / `get_drive_time()`** (`backend/server.py`) replace all 10 real call
  sites (`mock_geocode`/`mock_distance_matrix` calls in shop create/edit, public booking
  availability + booking, contractor home-address edit, dispatch reorder, and the shop-portal day
  map). Both fall back to the mock on any error (bad address, quota, network) so a Maps hiccup
  never fails a booking — same resilience pattern as Xero invoice creation. The demo-shop seeder
  deliberately keeps calling the mock directly (fake addresses, no reason to spend a real API call).
- **Daily-cached drive times** (`drive_time_cache` collection, new) — `portal_day_map` calls
  `get_drive_time` once per other-shop job in a loop, so repeated calls for the same
  origin/destination/day are served from cache instead of re-hitting the API on every page load.
  Cache key rounds coordinates to ~11m precision and includes the calendar day; a TTL index
  (`cached_at`, 2 days) auto-expires old entries so the collection self-bounds. This is the "daily
  caching" the roadmap already called for.
- **`GET /api/integrations/status`** — `google_maps` now reports real `configured`/`connected`/
  `mode` instead of the hardcoded `false`/`mock` stub.
- **Frontend** — Settings → Integrations' Google Maps row is now driven by live status (previously
  a hardcoded "Mock" label, unlike Xero/Growth/Assist which were already dynamic).
- **New env var:** `GOOGLE_MAPS_API_KEY`. No new Python dependency (`requests` already present,
  same as Xero).
- **Tests:** `backend/tests/test_google_maps.py` (15 pure tests — geocode/distance-matrix parsing,
  error statuses, the metro bounding box, and cache-key rounding/day-rollover). Backend integration
  tests (`backend/tests/test_*.py` that hit a live server) were not run in this environment — they
  exercise these code paths in mock mode only (no `GOOGLE_MAPS_API_KEY` set), which is unchanged.
- **Not addressed here:** real-time traffic (Distance Matrix `departure_time`) — the scheduling
  algorithm doesn't model time-of-day traffic today, mock or real; out of scope for this pass.

### Security — Production hardening pass, part 1 (2026-07-21)
First launch-blocker cleanup: get the app out of its "demo defaults" configuration so it's safe to
expose to real shops. **Fully backward-compatible** — everything is gated on a new `APP_ENV` flag
that defaults to `development`, so local runs, CI, and the current Emergent deployment behave exactly
as before until `APP_ENV=production` is set. No route, schema, or data-model changes.

- **Env-driven seed credentials (`backend/server.py`).** The owner/contractor accounts no longer ship
  a hardcoded password. Owner password now comes from `OWNER_PASSWORD` (contractor from
  `CONTRACTOR_PASSWORD`); outside production they fall back to the previous dev defaults so tests are
  unchanged. **The seeded password is no longer written to the logs.**
- **Password rotation on mismatch.** If `OWNER_PASSWORD` / `CONTRACTOR_PASSWORD` is set and an account
  already exists with a different password, startup rotates the stored hash to match. This is how the
  historically-exposed default gets fixed on the existing production DB: set the env var, restart.
- **Demo data gated.** The three demo shops (and the demo-derived Module 9 partner contacts) seed only
  when `SEED_DEMO_DATA=true`, which defaults on in development and **off in production** — so a real
  deployment starts clean instead of pre-populated with Safelite/AutoGlassNow/Glass Doctor fakes.
- **Startup security self-check (`security_self_check()`).** Logs a clear posture report and warns on
  the public dev `JWT_SECRET`, the placeholder `STRIPE_API_KEY`, wildcard `CORS_ORIGINS`, and a
  missing `OWNER_PASSWORD`. In production only, it **fails closed** (refuses to boot) if `JWT_SECRET`
  is still the public dev default — so the app can't be launched signing tokens with a known secret.
- **New env vars:** `APP_ENV`, `OWNER_PASSWORD`, `CONTRACTOR_PASSWORD`, `OWNER_EMAIL`,
  `CONTRACTOR_EMAIL`, `SEED_DEMO_DATA`. Existing `JWT_SECRET`, `STRIPE_API_KEY`, `CORS_ORIGINS` are
  now checked at startup. Full list + launch steps in `EMERGENT.md`.
- **Not yet addressed (still open launch blockers):** live Stripe key + actual card-charging code is
  still not wired (the charge queue lists jobs but nothing bills the card), and Google Maps drive-times
  are still mocked. Tracked for the next passes.

### Added — Module 8: Admin Assist Engine v1 (2026-07-09)
Natural-language admin copilot built into the owner dashboard. Chat widget on every owner page;
reads answer instantly from live data, every real action (dispatch, cancel, reschedule, pricing,
shop edits, growth touches/intros) stops at a confirmation card the owner must approve. Activates
when `GOOGLE_API_KEY` (Google AI Studio) is set in env; inert otherwise.

- **New package `backend/assist/`**:
  - `tools.py` — 31 tools wrapping the app's own existing `/api/*` endpoints over localhost with
    the owner's JWT (no direct DB access; a bad LLM call fails normal request validation). Tier =
    HTTP verb: GET → safe (inline), POST/PUT/PATCH → risky (confirm-gated).
  - `agent.py` — hand-rolled Gemini tool-calling loop (`google-genai`, `gemini-2.5-flash`,
    FunctionDeclarations only so the SDK can never auto-execute; max 6 tool rounds). Includes a
    deterministic `/run <tool> {json}` escape hatch used by tests and power users.
  - `routes.py` — `POST /api/assist/message`, `POST /api/assist/actions/{id}/confirm|cancel`
    (5-min expiry, configurable), `GET /api/assist/conversations/{id}`, `GET /api/assist/tools`.
    All owner-only.
- **Deliberately NOT google-adk:** every ADK release requires `fastapi>=0.115`; this app pins
  `fastapi==0.110.1`. The plain `google-genai` SDK has no FastAPI dependency, so the existing
  app's framework stays untouched.
- **New collections:** `assist_conversations` (chat history), `assist_pending_actions`
  (propose→confirm state). **Reused:** `ai_action_log` (Module 9's audit collection — Module 8
  now writes `assist_propose|confirm|cancel|execute` rows to it, as originally intended).
- **`GET /api/integrations/status`** gained an `assist` key (`configured`/`enabled`/`mode`).
- **Frontend:** new `frontend/src/components/Assist.jsx` floating chat widget mounted in
  `Shell.jsx` (owner role only) with confirmation cards; Assist status row in
  Settings → Integrations. Self-guards on `REACT_APP_ASSIST_MODULE_ENABLED` and on the backend
  status flag — renders nothing when the module is off.
- **New deps:** `google-genai`, `httpx`. **New env:** `GOOGLE_API_KEY` (required to activate),
  `ASSIST_MODULE_ENABLED`, `ASSIST_MODEL`, `ASSIST_PENDING_TTL_SECONDS`, `ASSIST_SELF_BASE_URL`,
  `REACT_APP_ASSIST_MODULE_ENABLED`.
- **Tests:** `backend/tests/test_assist.py` (13 deterministic tests — RBAC, tier gate,
  propose→confirm→execute, propose→cancel, expiry, failure surfacing, persistence). Also
  verified end-to-end against real Gemini: NL read answered inline, NL price change gated then
  executed on confirm, expired action rejected with 410.
- **Fixed a race condition** in the confirm/cancel pending-action handlers (`routes.py`): the
  status check-then-update was non-atomic, so two near-simultaneous confirm/cancel calls on the
  same action could both pass validation. Now claimed atomically via a single `find_one_and_update`
  filtered on `status: "pending"`, so only the first caller wins and the second gets its expected
  400. Re-verified with a full live run (disposable MongoDB container + real `uvicorn` server, not
  mocks): `pytest tests/test_assist.py` 13/13 pass and `pytest tests/test_growth.py` 9/9 pass
  (Module 9 unaffected).
- **Deferred (documented in `docs/module8/README.md`, not silently dropped):** the original
  Cloud Run/ADK/Vertex/Postgres architecture and the VIN-OEM checklist / scan-audit / multi-day
  workflow concepts; Invoices/Charges/Messages/Invites tools are the named fast-follow.

### Added — Module 9: Partner Growth Engine v1 (2026-07-08)
Power Connector 5+50+100 CRM + 3-D introductions, built out from the previously-inert scaffold.
Flag now **defaults on** (`GROWTH_MODULE_ENABLED=true`, `REACT_APP_GROWTH_MODULE_ENABLED=true`).
**Reels are explicitly deferred** — no video-generation capability exists in this environment, so
`ReelAsset`/`POST /api/growth/reels/generate` are not implemented rather than shipped as a
misleading stub.

- **New module `backend/growth/routes.py`** — `build_growth_router(db, require_owner,
  mock_send_sms, send_email)` factory (avoids a circular import with `server.py`), included
  conditionally from `server.py` only when `GROWTH_MODULE_ENABLED` is true.
- **New endpoints** (all under `/api/growth/*`, owner-only):
  `GET/POST /contacts`, `PATCH /contacts/{id}` (circle changes cap-enforced, 409 on overflow),
  `GET /grid`, `GET /nudges/today`, `GET /touches`, `POST /touches/{id}/approve|send`,
  `GET/POST /intros`, `POST /intros/{id}/approve|send`.
- **Real dispatch on send** — reuses the existing `mock_send_sms` (sms channel) and `send_email`
  (email channel, Resend-if-configured else logged) helpers; no new outbound-comms code. Sending
  updates the contact's `favors_given`/`favors_asked`/`last_touch_at`/`next_touch_due`.
- **`backend/growth/models.py`** — implemented the previously-stubbed `enforce_grid_caps()`
  (idempotent corrective sweep, demotes overflow one tier down) and `generate_daily_nudges()`
  (deterministic, no LLM, idempotent per calendar day via a new `nudge_date` field on `Touch`).
- **New collections:** `partner_contacts`, `touches`, `intros`, `ai_action_log` (a minimal audit
  trail written on every approve/send — not dependent on Module 8 existing).
- **Seed data** extended: `partner_contacts` seeded from the 3 real demo shops + the owner as
  `top5` entries (not the doc's aspirational fake Phoenix contact list); `key50`/`vital100` start
  empty.
- **`GET /api/integrations/status`** gained a `growth` key (`enabled`, `contact_count`,
  `counts_by_circle`).
- **Frontend** — `frontend/src/pages/growth/Growth.jsx` rewritten from a static placeholder into a
  real page: circle-grouped contact grid with an add-contact form, a Today's Nudges panel
  (approve/send), and a 3-D intro creator/list. Routed at `/growth`, added to the owner nav
  (`Shell.jsx`), and a status row added to Settings → Integrations. Still self-guards on
  `REACT_APP_GROWTH_MODULE_ENABLED` so it can be flipped back to the old placeholder without a
  redeploy.
- **Tests** — `backend/tests/test_growth.py`: RBAC, contact CRUD, cap enforcement (409 then
  succeeds after a demotion), nudge-generation idempotency, touch approve→send lifecycle
  (send-before-approve rejected), intro approve→send (favor bump on both sides, email required on
  both sides).

### Docs — context/priority sync (2026-07-08)
Doc-only session per user request ("before we do any building... update so everything is current,
all context is pushed and saved"). No runtime changes.

- **Added `docs/module8/README.md`** — the Module 8 (Agentic AI Assist Engine) system-context
  handoff doc, which existed only outside the repo until now. Design-only spec for a Google
  ADK 2.0 / Gemini / Cloud Run / Postgres-Supabase agentic layer (VIN-triggered OEM setup
  checklists, dual-invoicing + compliance audit workflow, long-running ticket lifecycles with HITL
  gates). Flagged in `CLAUDE.md` as a significant stack deviation needing its own approval pass
  before implementation.
- **Landed the Module 9 (Partner Growth Engine) scaffold onto `main`**, previously stranded on the
  unmerged `feature/module9-partner-growth` branch: `backend/growth/models.py` (`PartnerContact`,
  `Touch`, `Intro`, `ReelAsset` Pydantic models + nurture templates for the Judy Robinett Power
  Connector 5+50+100 method), `frontend/src/pages/growth/Growth.jsx` (flagged placeholder page),
  `docs/module9/README.md`. Everything is inert behind `GROWTH_MODULE_ENABLED=false` — not imported
  by `server.py`, not routed in the frontend. User has flagged this module as the next build
  priority, ahead of Twilio/Module 8.
- **Xero → QuickBooks:** recorded that the business's newly-hired CPA uses QuickBooks exclusively,
  so the Xero integration may be replaced. No code changed; Xero remains exactly as shipped in Step 1
  (live-capable, mock-fallback) until a migration is explicitly scoped and approved.
- **Twilio SMS (Step 2) deprioritized:** the user confirmed it's not required for MVP. Removed it as
  the "active task" in `CLAUDE.md`; it's on hold, not scheduled.
- Updated `CLAUDE.md` and `EMERGENT.md` system-status/roadmap sections accordingly, and added a
  "Modules beyond the core platform" pointer section to `CLAUDE.md` so future sessions check
  `docs/moduleN/` before starting related work.

### Docs
- **Status check-in (2026-07-03):** refreshed `CLAUDE.md` to reflect that Step 1 (real Xero invoicing)
  is done and merged to `main` (PR #1), moved the active task to Step 2 (real Twilio SMS), and recorded
  the open action items on Emergent's side: (1) Xero is live-capable but not yet live — needs env vars +
  owner connect; (2) verify the frontend build on Emergent/Vercel; (3) reconcile the version mismatch
  between `CHANGELOG.md` (0.0.3) and `frontend/package.json` (0.1.0). No code or runtime changes.

## [0.0.3] — 2026-06-16 — Claude Code session (Step 1: real Xero invoicing)

### Added
- **Collaboration bridge docs:** `CLAUDE.md` (project constitution + Emergent runtime rules),
  `EMERGENT.md` (return-handoff instructions for Emergent AI), and this `CHANGELOG.md`.
- **`.claude/` dev tooling** (web sessions only): SessionStart hooks that install the gstack and
  curated awesome-claude-skills packs. No effect on app runtime or Emergent hosting.

### Added — Step 1: real Xero invoicing (credential-optional)
Real Xero OAuth 2.0 + REST API integration that mirrors the existing Stripe/Resend pattern: when
Xero credentials are configured **and** the owner has connected, completed jobs create real **draft**
invoices in Xero; otherwise the app falls back to the existing mock so nothing breaks without creds.
Implemented with the already-present `requests` library wrapped in `asyncio.to_thread` (no new
dependency), matching the existing Resend code.

- **New module `backend/xero_invoice.py`** — stdlib-only, unit-testable builder for the spec's exact
  invoice payload (Line 1 = calibration label @ rate; Line 2 = `LASTNAME / YEAR MAKE MODEL / VIN` @
  $0.00; ACCREC, DRAFT, due +30 days). Shared by both the real and mock paths so they're identical.
- **New endpoints** (`backend/server.py`, all under `/api`):
  - `GET /auth/xero/connect` — returns the Xero authorize URL (owner only; signed-JWT `state`).
  - `GET /auth/xero/callback` — exchanges the code, fetches the tenant via `/connections`, stores
    tokens on the owner record, redirects to `/settings?xero=connected|error`.
  - `POST /auth/xero/disconnect` — clears stored Xero tokens.
  - `GET /integrations/status` — per-integration configured/connected/mode (backs the Settings UI).
  - `POST /integrations/xero/poll` — polls Xero and syncs invoice status DRAFT→AUTHORISED→PAID onto
    jobs (spec's ~4-hour poll; call on a schedule or from the dashboard).
- **Token handling** — access/refresh tokens + expiry + tenant id + org name stored on the owner
  `technicians` record; auto-refresh before calls, persisting Xero's rotated refresh token.
- **Invoice creation** — `create_invoice_for_job()` dispatcher: real Contact lookup/create, ACCREC
  draft invoice, and **PDF attachment** of the technician's uploaded calibration document when present.
  Real invoices are also stored in a new `xero_invoices` collection; `GET /invoices` now merges real +
  mock.
- **Admin notification** — the invoice-created notice to `ADMIN_EMAIL` now goes through `send_email`
  (real via Resend if configured, else logged), instead of a bare DB insert.
- **Seed change** — the owner record now starts with `xero_connected: false` and empty token fields
  (real connection happens via OAuth). `mock_xero_create_invoice` now reuses the shared payload
  helpers and tags invoices `provider: "mock"`.
- **Frontend** — Settings → Integrations now shows live Xero status with **Connect Xero / Disconnect**
  buttons and a success/error banner after the OAuth redirect.
- **Tests** — `backend/tests/test_xero_invoice.py` (pure, runs anywhere) asserts the spec-exact
  invoice format, account-code configurability, and VIN/last-name fallbacks.

**New environment variables** (set in Emergent env settings; never commit): `XERO_CLIENT_ID`,
`XERO_CLIENT_SECRET`, `XERO_REDIRECT_URI`, and optional `XERO_SALES_ACCOUNT_CODE` (default `200`),
`XERO_POST_CONNECT_REDIRECT` (default `/settings`). The Xero app's redirect URI must equal
`XERO_REDIRECT_URI` and point at `<app-domain>/api/auth/xero/callback`.

### Still mocked / not yet done
- Twilio SMS, Google Maps (geocoding + Distance Matrix), Google Calendar, and cloud document storage
  remain mocked/deferred — these are later steps.

---

## [0.0.x] — Emergent AI baseline (through 2026-06-11)

Built and iterated by Emergent AI. Stack: FastAPI + MongoDB (Motor) backend, React 19 (CRA/CRACO)
SPA frontend, JWT auth. Integrations intentionally mocked for the first builds (see `memory/PRD.md`).

### Iteration 1 — Core platform (15/15 backend tests passing)
- JWT auth (`/api/auth/login`, `/api/auth/me`), bcrypt hashing, owner/contractor RBAC.
- Reference data (`/api/reference/zones`, `/api/reference/pricing`); seed: owner, contractor, 3 shops.
- Mock geocoding (`/api/geocode`) over Phoenix-area cities; zone detection (west < -112.0, east > -111.8).
- Shop CRUD (owner-only) with auto-geocode, zone assignment, booking-link token, terms signing.
- Public booking: shop lookup by token, drive-time-aware slot availability algorithm, booking creation.
- Job lifecycle (booked → driving → on_site → complete), price locked at booking, custom per-shop rates.
- On completion: mock Xero draft invoice (spec's 2-line-item format), mock completion SMS, admin notice.
- Mock SMS log and mock invoice list for UI introspection.

### Iteration 2 — Live booking alerts
- New-booking alert pipeline (`/api/notifications/new-bookings`, `/api/notifications/mark-seen`);
  dashboard alert pill + NEW badge (5s polling).

### Iteration 3 — Contractor dispatch, settings, routing
- Contractor offers with 30-minute expiry, accept/decline, owner visibility, auto-expire back to board.
- Editable settings (standard pricing, zone times/limits, contractor profile).
- Drag-and-drop job reorder with drive-time recalculation.

### Iteration 4 — Field operations hardening
- "At-risk" job detection (overdue start / overrun) surfaced on the dashboard.
- Reschedule and cancel (with reasons) + SMS side-effects.
- Real document upload (multipart, base64-in-Mongo, 10 MB cap, RFC 5987 download) with spec filename.
- Public shop status / scorecard page (`/api/public/shop-status/{token}`).

### Shop self-service portal (additional)
- Email invites via Resend (`/api/invites`), shop-user registration, Stripe card capture (setup mode),
  portal auth + booking + day-map, and a charge queue for completed jobs.
