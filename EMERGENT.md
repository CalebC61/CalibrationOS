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
- **Session (2026-11-18): shop edits use the booking rules, and a shop cancel names itself.**
  Changing the date, time, address, or service rechecks the open day, the
  valley, the free slot, before-8:00 AM approval, and same-day drive limits.
  The price follows the shop's rate. Names, vehicle, VIN, and notes do not
  change the status. A real edit emails the shop one "Job updated" note, with
  the ref and a portal link. A shop cancel emails "Job cancelled" in the same
  shape as a booking confirmation, and Dispatch shows "Cancelled by shop".
  Both stay in Email preview while `SHOP_EMAILS_ENABLED` is off. Owner edits
  are not emailed this way. No new env var. `BILLING_ENABLED` is unchanged.
- **Session (2026-11-18): booking does not show a geocode error while the address is being typed.**
  A miss on the in-progress text stays quiet, including while Places suggestions
  are open. Blur still reports an address that cannot be found, such as
  `zzzz qqqq nowhere 99999`. A picked suggestion still confirms the street and
  enables the date. No new env var. `BILLING_ENABLED` is unchanged.
- **Session (2026-11-18): a picked business on booking stays in the service area.**
  The suggestion request uses the full typed name. Places may still rank other
  businesses above that name. Picking one fills the street and confirms the
  valley from the place itself. A geocode of the typed name cannot show
  "We couldn't find that address" after the pick. Signup and add-shop still
  get the street and the place id. No new env var. `BILLING_ENABLED` is unchanged.
- **Session (2026-11-18): Places suggestions keep up with the address being typed.**
  The booking, signup, and add-shop address fields wait 200ms, then request
  suggestions for the current text. A keystroke typed before Places has loaded
  is requested when the library is ready. An older response cannot replace the
  list. A prefilled shop address still does not suggest until it is edited. A
  business suggestion still fills the street. No new env var. `BILLING_ENABLED`
  is unchanged.
- **Session (2026-11-18): warranty is visible, and a late redo warns before it books.**
  A free warranty redo still confirms immediately. It shows a Warranty banner
  on the owner day board, field job, complete screen, and the shop's own job
  views. Booking or moving a redo after 30 Phoenix days asks the shop to
  continue or cancel. Continue books it at the shop's normal rate. Shop
  Settings shows the address and Cancel on the card form. The complete screen
  shows Paid and the amount when the charge succeeded. `BILLING_ENABLED` and
  `SHOP_EMAILS_ENABLED` are unchanged. No new env vars.
- **Session (2026-11-18): health check and owner error mail.** `GET /api/health`
  pings Mongo and returns 503 when it is unreachable. Unhandled 500s and
  browser crashes email `ALERT_EMAIL`, then `OWNER_EMAIL`, then `ADMIN_EMAIL`.
  Nothing is sent when all three are blank. The mail still goes out while
  `SHOP_EMAILS_ENABLED` is false, at most once per error every 15 minutes and
  10 times an hour. The web app shows a refresh screen and reports the crash.
  New env var: `ALERT_EMAIL` (optional).
- **Session (2026-11-18): a paid card charge shows as paid.** A successful
  charge, and `invoice.paid` / `invoice.payment_succeeded`, set the job and
  the `job_invoices` row to paid. `invoice.finalized` no longer reopens a
  paid job. Invoices show Paid or Open and a due date 7 Phoenix days after
  completion. Dispatch and the field completion card show Paid, Invoiced, or
  Charge failed. `BILLING_ENABLED` and `SHOP_EMAILS_ENABLED` are unchanged.
  No new env vars.
- **Session (2026-11-18): contractors are gone, and travel steps are today-only.**
  Dispatch to Contractor, contractor offers, the Settings contractor tab, the
  field-app offer list, contractor login, and the contractor API routes are
  removed. Assist cannot dispatch to a contractor. Existing contractor rows and
  offer rows stay in Mongo and are not read or written. `CONTRACTOR_EMAIL` and
  `CONTRACTOR_PASSWORD` are ignored. Start Driving and I've Arrived work only
  on a job scheduled for today in America/Phoenix. Cancel, Complete, Xero
  drafts, billing, and the shop portal are unchanged. `BILLING_ENABLED` and
  `SHOP_EMAILS_ENABLED` are unchanged. No new env vars.
- **Session (2026-11-18): no nightly shop reminder. One booking confirmation.**
  The 5:00 PM Phoenix day-before email is removed. A shop gets one confirmation
  when a portal booking is booked, or when the owner approves a pending or
  same-day job. It includes the date, arrival window, vehicle, address, ref,
  and a link to the job in the portal. It stays in Email preview while
  `SHOP_EMAILS_ENABLED` is false. No new env var. `BILLING_ENABLED` is unchanged.
  On `/portal/book`, editing the prefilled shop address still shows Places
  suggestions. The Phoenix service-area check is unchanged.
- **Session (2026-11-18): 30-day warranty redos.** A job can be a redo of one
  of that shop's completed jobs. Within 30 Phoenix days of the original
  completion the redo is $0, and Complete skips the Xero draft and the card
  charge and records why. Day 31 is billed normally. The shop picks the
  original job while booking. The owner can set or clear the link on edit.
  Another shop's job, or a job that is not completed, is rejected. Badges show
  on Dispatch, the field job, and My Jobs. No new env vars. `BILLING_ENABLED`
  and `SHOP_EMAILS_ENABLED` are unchanged. A free redo sends no email or text.
- **Session (2026-11-18): declined jobs leave the new-booking banner.**
  `GET /api/notifications/new-bookings` skips `declined` as well as
  `cancelled`. Decline marks that job's alert seen. Dispatch updates the
  banner count as soon as the owner declines or cancels. `GET /api/jobs?closed=true`
  is the owner list of cancelled and declined jobs. Dispatch shows that list
  with the existing Delete confirmation. The day board and
  `include_cancelled=true` are unchanged. No new env vars.
  `SHOP_EMAILS_ENABLED` and `BILLING_ENABLED` are unchanged.
- **Session (2026-11-18): Xero badges update without a reload.** Connection
  status and draft badges were stuck until a full refresh because API GETs
  were cacheable, Settings did not reopen Integrations after the Xero
  redirect, and Complete/Retry ignored the job in the response. `/api`
  responses are `Cache-Control: private, no-store`. The owner UI refetches
  on focus and after the OAuth return. No new env vars. Tokens stay off the
  client. `BILLING_ENABLED` and `SHOP_EMAILS_ENABLED` are unchanged.
- **Session (2026-11-18): shops book only after they log in.** Public `/book/{token}` and
  `/scorecard/{token}` no longer show or change jobs. Booking, edits, cancels, and the
  scorecard go through the shop portal. The owner still books for a shop from the shop
  page, and can still delete a job. Response allowlists still hide Stripe ids, Xero
  tokens, and password hashes. The public site Book a job buttons go to signup, or to
  portal Book when the shop is already logged in. Welcome mail points at the portal
  login. `SHOP_EMAILS_ENABLED` and `BILLING_ENABLED` are unchanged. Details in `CHANGELOG.md`.
- **Session (2026-11-18): the owner can delete a job.** `DELETE /api/jobs/{id}`
  is owner-only (shop and technician logins are 403). It removes the job and
  its documents, alerts, and action tokens. Offer rows are left in place.
  It does not email, text, cancel, or call Xero or Stripe. Invoice rows stay.
  Dispatch shows Delete with a confirmation. No new env vars.
  `SHOP_EMAILS_ENABLED` and `BILLING_ENABLED` are unchanged.
- **Session (2026-11-17): triple drafts and wholesale prices.** Triple files
  the Xero item Subaru MC Calibration (code 8), with Triple/Subaru Calibration
  as the fallback name. Booking and Complete price the job at the shop's
  wholesale rate, including when the calibration type does not change. The
  $30 trip fee stays separate. A Xero miss still marks the completed job
  needs attention. The public booking date step imports `phoenixTodayStr`.
  No new env vars.
- **Session (2026-11-17): Complete can file the Xero draft.** Post-scan VINs are
  read with pypdf (the old stream reader is the fallback). Dispatch Complete
  asks for calibration type, POP, and a signed PDF before it completes the job.
  A trip-fee-only draft does not require that PDF. Changing the calibration
  type at Complete updates the job price to the shop's wholesale rate. An
  upload with no customer last name gets a safe filename. New dependency:
  `pypdf` (and `reportlab`, used by the VIN test).
- **Session (2026-11-17): the Xero callback redirects.** After the tokens are
  saved, the browser is sent to `XERO_POST_CONNECT_REDIRECT` with `?xero=connected`
  or `?xero=error`. The missing `RedirectResponse` import was a 500.
- **Session (2026-11-17): Xero connect uses granular scopes.** `XERO_SCOPES`
  requests `accounting.invoices` instead of `accounting.transactions`. It does
  not request `accounting.payments`, reports, or journals. The owner connects
  Xero again so the saved token matches.
- **Session (2026-11-17): completing a job files one Xero draft.** The card charge is
  unchanged (`BILLING_ENABLED`, `SHOP_EMAILS_ENABLED`). The draft is ACCREC, status
  DRAFT, due the job date, no tax. It does not create a Xero contact and it does not
  send the invoice. A miss is marked needs attention on the job. The owner can set a
  shop's Xero contact id and edit Real Fast / Preferred wholesale rates. No new env
  vars. Connect requests `accounting.attachments` and `accounting.settings.read` from
  the `XERO_SCOPES` constant in `backend/server.py`. The owner connects Xero again
  so the saved token includes them.
- **Session (2026-11-17): pre-launch guards.** The shop day map shows the whole
  route. Other shops' stops are a rough pin and a time window, without names or
  the job id. Sign-in, password reset, public geocode, and the contact form
  are rate limited. A cached geocode drops a leading business name before the
  street is saved. Portal report downloads send the login token. The card form
  opens expanded. A failed portal booking shows an inline error. No env, Stripe,
  Render, or Vercel setting changes. Public booking, scorecard, job completion,
  Xero, and SMS are unchanged.
- **Session (2026-11-12): cancelled jobs leave the owner and technician day list.**
  `GET /api/jobs` now omits `cancelled` and `declined`. The jobs stay in Mongo.
  `include_cancelled=true` is an opt-in for a future history view; the dashboard,
  Field, tomorrow preview, and route map do not send it. Reschedule still moves
  the same document, so it does not remain on the old date. The shop portal
  list, including its Cancelled tab, is unchanged. No SMS or email.
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
4. **Register the Stripe webhook.** In test mode, add an endpoint for
   `https://<api-host>/api/stripe/webhook` and set `STRIPE_WEBHOOK_SECRET` to that endpoint's
   `whsec_` signing secret. Enable `setup_intent.succeeded`, `payment_method.detached`,
   `payment_intent.succeeded`, `payment_intent.payment_failed`, `invoice.payment_failed`,
   `invoice.paid`, and `invoice.payment_succeeded`. That is how a detached or declined card
   stops the next booking. There is no new env var and no change to `BILLING_ENABLED`.
   A statement descriptor and the payout schedule stay account-level Dashboard settings.

### Action items for you (Emergent) — everything else, in rough priority order
1. **Turn on real Google Maps:** set `GOOGLE_MAPS_API_KEY` in Emergent's env settings (a Google
   Cloud API key with the **Geocoding API** and **Routes API** enabled + billing on the
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
- `ALERT_EMAIL` *(optional)* — inbox for unhandled 500s and browser crash
  reports. Blank uses `OWNER_EMAIL`, then `ADMIN_EMAIL`. Blank for all three
  sends nothing. These notes ignore `SHOP_EMAILS_ENABLED`. Resend still needs
  `RESEND_API_KEY` and `SENDER_EMAIL`.
- `OWNER_EMAIL` *(optional, default `caleb@thecalibrationcrew.us`)*.
  This is where same-day and before-8:00 AM booking alerts go, and the
  Reply-To on shop booking mail. `CONTRACTOR_EMAIL` and `CONTRACTOR_PASSWORD`
  are no longer read. Leaving them set does nothing.
- `PUBLIC_SITE_URL` *(optional)* — host used in the owner's Approve and Decline links.
  Blank uses `https://www.thecalibrationcrew.us`.
- `SENDER_EMAIL` must be a verified address on `thecalibrationcrew.us`. The code default
  `onboarding@resend.dev` only delivers to the Resend account owner.
- `SHOP_EMAILS_ENABLED` *(default false)* — shop and customer booking mail. While false,
  confirmations and approve/decline/reschedule/cancel notices are stored in the email
  outbox and are not sent. The owner dashboard shows "Shop emails: OFF (testing)".
- `OWNER_EMAILS_ENABLED` *(default true)* — owner alert emails. Stays on when shop mail is off
  so the approve links can be tested. Set `false` to hold those too.
- `SEED_DEMO_DATA` *(optional; default `true` in dev, `false` in production)* — whether to seed the
  3 demo shops + demo partner contacts. Off in production so a real deployment starts clean.
  *(Note: this only stops NEW demo data from seeding; any demo shops already in the live DB should be
  deleted via the UI.)*
- `CORS_ORIGINS` *(already existed; now checked)* — set to your real app domain(s), comma-separated,
  instead of the `*` default.
- `ENABLE_API_DOCS` *(optional)* — interactive docs (`/docs`, `/redoc`, `/openapi.json`).
  Unset: on in development, off when `APP_ENV` is `production` or `prod`. Set `true` to turn
  them on in production (the pages are mounted at process start), or `false` to turn them off
  everywhere. Turning them off takes effect on the next request. Turning them on in a process
  that booted with them unmounted needs a restart.

**Added for real Google Maps (2026-07-21):**
- `GOOGLE_MAPS_API_KEY` — a Google Cloud API key with the **Geocoding API** and **Routes API**
  (`computeRoutes` with `TRAFFIC_AWARE`) enabled and billing active on the project. Without it,
  drive time stays on the mileage estimate and the app still starts. Saving a shop or a job
  address is refused instead of storing a guessed pin.

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
- `ASSIST_SELF_BASE_URL` *(optional)* — where the assistant's tools reach the app's own API.
  Leave it unset. The default is `http://127.0.0.1:$PORT`, or port `8001` when `PORT` is unset
  (this Emergent runtime). Set it only to override that.

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
