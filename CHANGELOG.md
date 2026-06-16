# Changelog

All notable changes to CalibrationOS are recorded here. This file is the reconciliation
log between **Emergent AI** and **Claude Code** — every session must append what it did
in plain, technical language so neither system loses context across a handoff.

Format follows [Keep a Changelog](https://keepachangelog.com/). Newest entries on top.

---

## [Unreleased]

_Nothing yet._

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
