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

### Action items for you (Emergent) — these are on your side, not in code
1. **Xero:** still live-capable but not yet live, and may be replaced by QuickBooks — hold off on
   spending setup time here until that's decided. If you do turn it on: add the Xero env vars listed
   below, then connect the owner account via **Settings → Integrations**.
2. **Verify the frontend build.** The Step 1 `Settings.jsx` change wasn't built during the Claude
   session because the SPA pulls the private `@emergentbase/visual-edits` dependency, which only
   resolves inside Emergent. Confirm the build is green — this now matters more, since the Module 9
   Growth page is live in the nav, not just an inert placeholder.
3. **Reconcile version numbers:** `CHANGELOG.md` says `0.0.3`, `frontend/package.json` says `0.1.0`.
   Pick one scheme.
4. **Module 9 is live** — no external credentials needed (dispatch reuses existing SMS/email
   helpers). If you want it off for any reason, set `GROWTH_MODULE_ENABLED=false` and
   `REACT_APP_GROWTH_MODULE_ENABLED=false` — the backend routes 404 and the frontend falls back to
   its placeholder card, no redeploy of app logic needed either way.
5. **Module 8 is still design-only** — nothing to configure, no code exists yet.

## Environment variables (set in Emergent's env settings — never commit values)
**Existing:** `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `STRIPE_API_KEY`, `RESEND_API_KEY`,
`SENDER_EMAIL`, `ADMIN_EMAIL`, `CORS_ORIGINS`, `REACT_APP_BACKEND_URL`.
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

## Testing
- Backend: `cd backend && pytest tests/ -v`.
- Before delegating to the testing agent, update `test_result.md`'s data section per the protocol
  block at the top of that file.

## Roadmap (reprioritized 2026-07-08)
1. ~~**Module 9 — Partner Growth Engine** build-out~~ — **v1 shipped 2026-07-08** (reels deferred).
2. **Module 8 — Agentic AI Assist Engine** (`docs/module8/README.md`) — design/approval pass, then
   build. Bigger lift: new runtime, new persistence layer.
3. Possible **Xero → QuickBooks** migration, if/when scoped.
4. Real Google Maps (geocoding + Distance Matrix with daily caching), Google Calendar sync, migrate
   documents from base64-in-Mongo to real cloud storage, production hardening (rotate `JWT_SECRET`,
   lock down CORS, monitoring, backups).
5. Module 9 reels (AI-generated case-study video) — needs a video-generation pipeline first; not
   started.

**On hold, not scheduled:** real Twilio SMS (+ inbound contractor YES/NO webhook) — not required for
MVP; revisit only if asked.
