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

## What changed in the latest Claude session
See `CHANGELOG.md` → `[Unreleased]`. Summary:
- Added the collaboration bridge docs (`CLAUDE.md`, `EMERGENT.md`, `CHANGELOG.md`).
- Started **Step 1: real Xero invoicing** (status tracked in CHANGELOG).

## Environment variables (set in Emergent's env settings — never commit values)
**Existing:** `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `STRIPE_API_KEY`, `RESEND_API_KEY`,
`SENDER_EMAIL`, `ADMIN_EMAIL`, `CORS_ORIGINS`, `REACT_APP_BACKEND_URL`.
**Added for Step 1 (Xero):** `XERO_CLIENT_ID`, `XERO_CLIENT_SECRET`, `XERO_REDIRECT_URI`
(per-technician OAuth tokens are stored in the DB, not in env). When these are absent, Xero falls
back to the existing mock so the app keeps running.

## Testing
- Backend: `cd backend && pytest tests/ -v`.
- Before delegating to the testing agent, update `test_result.md`'s data section per the protocol
  block at the top of that file.

## Roadmap (post Step 1)
Real Twilio SMS (+ inbound contractor YES/NO webhook) → real Google Maps (geocoding + Distance Matrix
with daily caching) → Google Calendar sync → migrate documents from base64-in-Mongo to real cloud
storage → production hardening (rotate `JWT_SECRET`, lock down CORS, monitoring, backups).
