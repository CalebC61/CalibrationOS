# EMERGENT.md — Resuming after a Claude Code session

Read this when you (Emergent AI) resume development after Claude Code worked on the repo
(e.g. while Emergent credits were paused). Companion files: `CLAUDE.md` (full conventions) and
`CHANGELOG.md` (what changed, newest on top).

## How to resume safely
1. **Re-sync this repo from GitHub `main`** so you have the absolute latest commit. Claude's work is
   merged to `main` via a reviewed PR before any handoff back to you.
2. **Read the top of `CHANGELOG.md`** for a plain-language summary of everything Claude changed.
3. **Read `CLAUDE.md`** for the shared runtime rules both systems follow.

## Conventions Claude followed (so you can continue cleanly)
- Kept all Emergent runtime rules intact: every backend route under `/api`; URLs/ports driven by env
  (`REACT_APP_BACKEND_URL`, `MONGO_URL`); yarn for the frontend; services restarted via supervisor.
- **Did not edit** the protected protocol block in `test_result.md`. Any test data was appended below
  the data marker in your YAML format.
- **Additive changes only** — no folder refactors, no deletion of Emergent-generated modules.
- Mirrored your integration pattern: use the real provider when its API key is configured, otherwise
  fall back to the existing mock / DB log.
- Never committed secrets; `.env` stayed gitignored.

## What changed in the latest Claude sessions
See `CHANGELOG.md` for the full log. Current state:
- **Session (2026-10-27): Phoenix day boundaries.** Job-by-date queries (`/portal/day-map`, `/jobs`,
  `/dashboard/summary`, reorder, availability, public booking) use America/Phoenix midnight converted
  to UTC, not UTC midnight. Default "today" is the Phoenix date. The portal day map and booking
  date limits use that date too. Zone clock times stay UTC wall times; a saved zone that starts
  before 07:00 UTC no longer offers those starts on the requested Phoenix day (they were the
  previous evening, so the booking disappeared from `/jobs` and the slot could be offered again).
  Reorder clamps an early start up onto the day. Concurrent drive-time lookups that share a
  rounded destination share one in-flight Google call. Details in `CHANGELOG.md`.
- **Design guidance only, plus a small token/contrast pass.** Impeccable's skill
  text is vendored under `.cursor/skills/impeccable/` (Apache 2.0; scripts not
  included; no new npm/pip dependency). Brand fill is `#FF5F1F`. A few CSS
  contrast and type-size fixes landed with it. No API, collection, or hosting
  change. Details in `CHANGELOG.md`.
- **Session (2026-07-21c): real card charging via Stripe — the Charge Queue is now wired up.**
  `POST /api/charge-queue/{job_id}/charge` (off-session PaymentIntent against the shop's stored
  card, idempotent per job — a double-click or retry can't double-charge) and `POST
  /api/charge-queue/{job_id}/skip` (bill outside Stripe instead). Both were already stubbed in the
  frontend (`ChargeQueue.jsx`'s "Charge Now" button said "next iteration") — now wired end to end.
  New pure module `backend/charging.py` (14 unit tests). **No new env var** — reuses the existing
  `STRIPE_API_KEY`. **This was the last open code launch-blocker.** See the "Stripe go-live
  checklist" below for exactly what to do on your side — that's what's actually left before launch.
- **Session (2026-07-21b): real Google Maps (geocoding + drive time) — credential-optional,
  same real-if-key-present-else-mock pattern.** New module `backend/google_maps.py`; new
  `geocode_address()`/`get_drive_time()` wrappers in `server.py` replace every mock call site;
  drive times are daily-cached (new `drive_time_cache` collection, TTL-indexed) since the
  shop-portal day map calls drive-time in a loop. `GET /api/integrations/status` and the Settings →
  Integrations Google Maps row now reflect real status instead of a hardcoded "Mock" label. New env
  var: `GOOGLE_MAPS_API_KEY`. This was the last of the three originally-mocked integrations that
  were launch blockers — Twilio SMS remains on hold (not required for MVP, see below).
- **Session (2026-07-21a): production hardening pass 1** (security — env-driven seed credentials,
  demo data gated off in production, startup self-check that fails closed on the default
  `JWT_SECRET` in production). Fully backward-compatible, gated on `APP_ENV`. See env vars below.
- **Step 1: real Xero invoicing — DONE and merged to `main`** (credential-optional, mock fallback).
  New module `backend/xero_invoice.py`; endpoints under `/api/auth/xero/*` and `/api/integrations/*`;
  real draft-invoice creation + PDF attachment on job completion; Settings → Integrations
  Connect/Disconnect UI. No new Python dependency (uses `requests` + `asyncio.to_thread`).
- Added the collaboration bridge docs (`CLAUDE.md`, `EMERGENT.md`, `CHANGELOG.md`).
- One session was a **docs-only status refresh** — no code or runtime changes.
- **Session (2026-07-08a): docs/context consolidation, no runtime changes.**
  - Landed the previously-unmerged `feature/module9-partner-growth` scaffold onto `main`.
  - Captured a previously-unsaved architecture doc as `docs/module8/README.md` (Agentic AI Assist
    Engine — Google ADK/Gemini/Cloud Run/Postgres). Design-only, no code.
  - Flagged that the business's new CPA uses QuickBooks exclusively, so Xero may be replaced. No
    code changed — Xero stays exactly as documented until a migration is scoped.
  - Deprioritized Step 2 (real Twilio SMS) — not required for MVP, on hold indefinitely.
- **Session (2026-07-09): Module 8 — Admin Assist Engine v1 shipped.**
  - Natural-language admin copilot: floating chat widget on every owner page
    (`frontend/src/components/Assist.jsx`), backed by `backend/assist/` under `/api/assist/*`.
  - Safety model: read tools execute inline; every mutating tool stops at a confirmation card
    (propose → owner confirms → execute; 5-minute expiry; everything audited to `ai_action_log`).
  - Built on the plain Gemini SDK (`google-genai`) — **not google-adk**, whose minimum
    `fastapi>=0.115` conflicts with the app's pinned `fastapi==0.110.1`. Your FastAPI version is
    untouched.
  - New collections: `assist_conversations`, `assist_pending_actions`. New deps: `google-genai`,
    `httpx` (added to `backend/requirements.txt`).
  - Inert until `GOOGLE_API_KEY` is set (see env list below). Verified end-to-end against real
    Gemini during the session; `backend/tests/test_assist.py` covers the deterministic paths.
  - A late fix closed a race condition in the confirm/cancel handlers (atomic status claim via
    `find_one_and_update`). Re-verified with a full live run — disposable MongoDB + real `uvicorn`
    server, not mocks: `test_assist.py` 13/13 and `test_growth.py` 9/9 both pass.
- **Session (2026-07-08b): Module 9 — Partner Growth Engine v1 shipped.**
  - New `backend/growth/routes.py` (`/api/growth/*`: contacts CRUD + cap enforcement, grid, daily
    nudge generation, touch/intro approve→send), wired into `server.py` behind
    `GROWTH_MODULE_ENABLED` (**now defaults `true`**).
  - Real dispatch on send reuses the existing `mock_send_sms`/`send_email` helpers — no new
    outbound-comms integration, no new secrets.
  - New collections: `partner_contacts`, `touches`, `intros`, `ai_action_log`.
  - `frontend/src/pages/growth/Growth.jsx` rewritten into a real page, routed at `/growth`, added
    to the owner nav, plus a status row in Settings → Integrations.
  - **Reels are deferred** — no video-generation capability available; `ReelAsset`/
    `/api/growth/reels/generate` are not implemented (see `docs/module9/README.md`).
  - New tests: `backend/tests/test_growth.py`.

### Stripe go-live checklist (2026-07-21) — this is what's actually left before launch
Card charging is fully built (see above) and reuses the **existing** `STRIPE_API_KEY` — there's no
new integration to wire up, only account setup:

1. **Activate the Stripe account for live payments.** If the business's Stripe account hasn't
   completed onboarding yet, do that first in the Stripe Dashboard (legal business details + a
   bank account for payouts). Until "Activate your account" is complete, the account can only run
   in test mode — no real money moves, which is fine for step 2 below but not for launch.
2. **Test the full cycle before using real money.** In the Stripe Dashboard, grab a **test** secret
   key (`sk_test_...`) from Developers → API keys and set it as `STRIPE_API_KEY` temporarily. Have
   a shop go through portal registration and card setup using Stripe's test card
   `4242 4242 4242 4242` (any future expiry, any 3-digit CVC), complete a job, then click
   **Charge Now** in the owner's Charge Queue. Confirm it shows as a successful test payment in the
   Stripe Dashboard. This costs nothing and proves the whole flow works end to end.
3. **Switch to the live key.** Once step 2 looks right, replace `STRIPE_API_KEY` with the **live**
   secret key (`sk_live_...`) from the same Dashboard page. Real charges go live immediately — no
   redeploy, no other toggle.
4. **Nothing else is required** — no webhook, no separate "enable charging" flag, no new env var.
   A statement descriptor (what shows on the shop's card statement) and payout schedule are
   account-level Stripe Dashboard settings, not required to start charging; set them whenever
   convenient.

### Action items for you (Emergent) — everything else, in rough priority order
1. **Turn on real Google Maps:** set `GOOGLE_MAPS_API_KEY` in Emergent's env settings (a Google
   Cloud API key with the **Geocoding API** and **Distance Matrix API** enabled + billing on the
   project — this is a paid API past its free tier, budget accordingly). That's the only step: the
   backend self-activates (geocoding + drive times go real, daily-cached) and Settings →
   Integrations reflects it. No key = mock exactly as before, nothing breaks either way. Also
   confirm the frontend build is green — `Settings.jsx`'s Google Maps row changed again (now reads
   live status instead of a hardcoded label).
2. **Turn on the Assist copilot (Module 8):** set `GOOGLE_API_KEY` in Emergent's env settings
   (Google AI Studio key from ai.google.dev — free tier exists; no GCP project needed). That's
   the only step: the backend self-activates and the chat bubble appears on every owner page.
   Also confirm the frontend build is green (new `Assist.jsx` component in `Shell.jsx`).
3. **Xero:** still live-capable but not yet live, and may be replaced by QuickBooks — hold off on
   spending setup time here until that's decided. If you do turn it on: add the Xero env vars listed
   below, then connect the owner account via **Settings → Integrations**.
4. **Verify the frontend build.** The Step 1 `Settings.jsx` change wasn't built during the Claude
   session because the SPA pulls the private `@emergentbase/visual-edits` dependency, which only
   resolves inside Emergent. Confirm the build is green — this now matters more, since the Module 9
   Growth page is live in the nav, not just an inert placeholder, `Settings.jsx` has since changed
   twice more (Module 8's Assist row, then the Google Maps row), and `ChargeQueue.jsx`'s buttons
   are now live (previously a permanently-disabled "next iteration" button — verify **Charge Now**
   and **Skip / Bill Manually** both render and work against Stripe test mode, per the checklist
   above, before flipping to a live key).
5. **Version is 0.1.0** in both `CHANGELOG.md` and `frontend/package.json`. `[0.0.3]` is the
   previous cut.
6. **Module 9 is live** — no external credentials needed (dispatch reuses existing SMS/email
   helpers). If you want it off for any reason, set `GROWTH_MODULE_ENABLED=false` and
   `REACT_APP_GROWTH_MODULE_ENABLED=false` — the backend routes 404 and the frontend falls back to
   its placeholder card, no redeploy of app logic needed either way.
7. **Neither Module 8 nor Module 9's frontend has been visually verified yet.** Both `Assist.jsx`
   (Module 8) and `Growth.jsx` (Module 9) were built and backend-tested outside Emergent — the CRA
   build depends on the private `@emergentbase/visual-edits` package, which only resolves inside
   Emergent. Give both a real browser pass (chat widget open/close, a full propose→confirm
   round-trip; the Growth grid/nudges/intros panels) before calling either done.
8. **Production hardening (2026-07-21) is in place but off by default** — set `APP_ENV=production`
   plus `JWT_SECRET`/`OWNER_PASSWORD`/`CORS_ORIGINS` when actually ready to launch. See the env var
   list below. Nothing changes until `APP_ENV=production` is set.

## Environment variables (set in Emergent's env settings — never commit values)
**Existing:** `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `STRIPE_API_KEY`, `RESEND_API_KEY`,
`SENDER_EMAIL`, `ADMIN_EMAIL`, `CORS_ORIGINS`, `REACT_APP_BACKEND_URL`.

**Added for production hardening (2026-07-21) — set these before going live:**
- `APP_ENV` — set to `production` to turn on the hardening checks. Leave unset/`development` for
  local + Emergent preview (behaves exactly as before). **When `production`, the app refuses to boot
  if `JWT_SECRET` is still the built-in dev default** — this is intentional (fail closed).
- `JWT_SECRET` *(already existed; now enforced)* — a long random string. This signs login tokens; the
  repo's default is public, so a real deployment MUST override it.
- `OWNER_PASSWORD` — the owner login password. Set this and restart; on an existing DB the stored
  owner password is rotated to match (this is how you retire the old `Owner123!` default).
- `CONTRACTOR_PASSWORD` *(optional)* — same idea for the starter contractor account.
- `OWNER_EMAIL` / `CONTRACTOR_EMAIL` *(optional, default to the existing seeded emails)*.
- `SEED_DEMO_DATA` *(optional; default `true` in dev, `false` in production)* — whether to seed the
  3 demo shops + demo partner contacts. Off in production so a real deployment starts clean.
  *(Note: this only stops NEW demo data from seeding; any demo shops already in the live DB should be
  deleted via the UI.)*
- `CORS_ORIGINS` *(already existed; now checked)* — set to your real app domain(s), comma-separated,
  instead of the `*` default.

**Added for real Google Maps (2026-07-21):**
- `GOOGLE_MAPS_API_KEY` — a Google Cloud API key with the **Geocoding API** and **Distance Matrix
  API** enabled and billing active on the project. Without it, geocoding and drive-time stay on the
  existing mock exactly as before — the app never fails to start or run over this.

**Added for Step 1 (Xero):**
- `XERO_CLIENT_ID`, `XERO_CLIENT_SECRET` — from your Xero developer app.
- `XERO_REDIRECT_URI` — must exactly match the redirect URI registered in the Xero app, pointing at
  `<app-domain>/api/auth/xero/callback`.
- `XERO_SALES_ACCOUNT_CODE` *(optional, default `200`)* — sales account code for the line items.
- `XERO_POST_CONNECT_REDIRECT` *(optional, default `/settings`)* — where the callback returns the user.

Per-technician OAuth tokens (access/refresh/expiry/tenant) are stored in the DB on the owner record,
not in env. When `XERO_CLIENT_ID/SECRET/REDIRECT_URI` are absent — or the owner hasn't connected —
Xero gracefully falls back to the existing mock, so the app keeps running and existing tests stay green.

**Added for Module 9 (Partner Growth Engine):**
- `GROWTH_MODULE_ENABLED` *(optional, default `true`)* — backend on/off switch. No external
  credentials required; dispatch reuses the existing `mock_send_sms`/`send_email` helpers.
- `REACT_APP_GROWTH_MODULE_ENABLED` *(optional, default `true`)* — frontend counterpart; set to
  `false` to fall back to the inert placeholder card without a code change.

**Added for Module 8 (Admin Assist Engine):**
- `GOOGLE_API_KEY` *(required to activate)* — Google AI Studio key (ai.google.dev). The only new
  secret; without it the module is fully inert (routes not registered, widget hidden).
- `ASSIST_MODULE_ENABLED` *(optional, default `true`)* / `REACT_APP_ASSIST_MODULE_ENABLED`
  *(optional, default on; set `false` to hide the widget)* — kill switches.
- `ASSIST_MODEL` *(optional, default `gemini-2.5-flash`)* — Gemini model id.
- `ASSIST_PENDING_TTL_SECONDS` *(optional, default `300`)* — how long a proposed action stays
  confirmable.
- `ASSIST_SELF_BASE_URL` *(optional, default `http://127.0.0.1:8001`)* — where the assistant's
  tools reach the app's own API; the default matches the backend's port on your runtime, leave
  it alone in production.

## Testing
- Backend: `cd backend && pytest tests/ -v`.
- Before delegating to the testing agent, update `test_result.md`'s data section per the protocol
  block at the top of that file.

## Roadmap (updated 2026-07-09)
1. ~~**Module 9 — Partner Growth Engine** build-out~~ — **v1 shipped 2026-07-08** (reels deferred).
2. ~~**Module 8 — Admin Assist Engine**~~ — **v1 shipped 2026-07-09** (in-process copilot; the
   original Cloud Run/ADK/Postgres concept is parked in `docs/module8/README.md`, not scoped).
3. Possible **Xero → QuickBooks** migration, if/when scoped.
4. Module 8 fast-follows: Invoices/Charges/Messages/Invites tools for the assistant; assistant in
   the `/field` PWA.
5. Real Google Maps (geocoding + Distance Matrix with daily caching), Google Calendar sync, migrate
   documents from base64-in-Mongo to real cloud storage, production hardening (rotate `JWT_SECRET`,
   lock down CORS, monitoring, backups).
6. Module 9 reels (AI-generated case-study video) — needs a video-generation pipeline first; not
   started.

**On hold, not scheduled:** real Twilio SMS (+ inbound contractor YES/NO webhook) — not required for
MVP; revisit only if asked.
