# Changelog

All notable changes to CalibrationOS are recorded here. This file is the reconciliation
log between **Emergent AI** and **Claude Code** — every session must append what it did
in plain, technical language so neither system loses context across a handoff.

Format follows [Keep a Changelog](https://keepachangelog.com/). Newest entries on top.

---

## [Unreleased] — Claude Code session (branch `claude/gracious-meitner-ef67wz`)

### Added
- **Collaboration bridge docs:** `CLAUDE.md` (project constitution + Emergent runtime rules),
  `EMERGENT.md` (return-handoff instructions for Emergent AI), and this `CHANGELOG.md`.
- **`.claude/` dev tooling** (web sessions only): SessionStart hooks that install the gstack and
  curated awesome-claude-skills packs. No effect on app runtime or Emergent hosting.

### In progress
- **Step 1 — Real Xero invoicing.** Replacing the mocked `mock_xero_create_invoice()` with a real
  Xero OAuth 2.0 + REST API integration (contact lookup/create, ACCREC draft invoice with the
  spec's two line items, PDF attachment, and DRAFT→AUTHORISED→PAID status sync), gated on
  `XERO_CLIENT_ID`/`XERO_CLIENT_SECRET` with graceful fallback to the existing mock. *(Details will
  be filled in here as the work lands.)*

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
