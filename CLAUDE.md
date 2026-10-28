# CLAUDE.md — Project Constitution for CalibrationOS

This file is the bridge between **Claude Code** and **Emergent AI**, the two systems
developing this project. Claude Code reads this file first every session. Keep it
accurate. The companion files are `EMERGENT.md` (handoff back to Emergent) and
`CHANGELOG.md` (the reconciliation log between the two systems).

> **Read this whole file before making changes.** This app is hosted on Emergent AI;
> several conventions below are load-bearing for hosting. Violating them will break the
> app when Emergent re-syncs the repo.

---

## TL;DR for Claude (every session)
1. This app is built and **hosted on Emergent AI**. Obey the *Emergent runtime rules* below.
2. Work on a **feature branch, never `main`**. Open a PR. Get a visual diff review before merge.
3. **Update `CHANGELOG.md`** for every feature / collection / endpoint you add or change.
4. **Never commit secrets.** `.env` files are gitignored and managed in Emergent's env settings.
5. **Preserve Emergent artifacts:** the protected block in `test_result.md`, `.emergent/`, `memory/PRD.md`.
6. **Active: launch push (target end of week, 2026-07-21). All code launch-blockers are now
   closed.** Security hardening (pass 1), real Google Maps (geocoding + drive-time), and real card
   charging (Stripe, off-session via the Charge Queue) are all **done**. Modules 8 and 9 are both
   shipped (Module 8 needs `GOOGLE_API_KEY` to go live; Module 9 is on by default). **What's left
   to actually launch is credentials/config on Emergent's side, not more code** — see "Open action
   items" below. No task is queued in code unless the user redirects. _(Step 2 — real Twilio SMS —
   is **on hold, not required for MVP**. Step 1 — real Xero invoicing — is **done and merged to
   `main`** via PR #1, but see the QuickBooks note below before touching it again.)_

---

## System status (as of 2026-07-21)
- Bootstrapped and iterated (~4 iterations) by Emergent AI, then extended by Claude Code (Step 1,
  Module 9, Module 8, security hardening, Google Maps). Core business logic is solid; most external
  integrations are now real, credential-optional (real-if-key-present, else mock).
- **Real integrations:** Stripe (card-capture/setup mode **+ off-session charging** via the Charge
  Queue, 2026-07-21), Resend (degrades to a DB log if no key), **Xero invoicing** (Step 1 — merged
  to `main` via PR #1 on 2026-06-16), **Google Maps** (geocoding + drive-time, 2026-07-21 —
  daily-cached; `GOOGLE_MAPS_API_KEY`). **Pending decision:**
  the business just hired a CPA who exclusively uses **QuickBooks**, so Xero may be replaced by a
  real QuickBooks integration. Nothing has changed in code yet — Xero stays live-capable/mock-fallback
  as documented until a QuickBooks migration is explicitly scoped and approved. Don't start that
  migration without a go-ahead; when it comes, mirror the same "real-if-configured, else mock"
  pattern and keep the Xero code until the swap is verified end-to-end (don't delete it preemptively).
- **Mocked:** Twilio SMS, cloud document storage (base64-in-Mongo).
- **Missing:** Google Calendar sync (explicitly deferred).
- **On hold:** Twilio SMS (Step 2) — deprioritized by the user, not needed for MVP. Don't pick this
  up unless asked.
- **Shipped, credential-gated:** **Module 8 — Admin Assist Engine v1** (`docs/module8/README.md`)
  — natural-language admin copilot in a floating chat widget on every owner page. Reads answer
  inline; every mutating action stops at a confirmation card (propose→confirm→execute, 5-min
  expiry, all audited to `ai_action_log`). Runs in-process on the plain Gemini SDK
  (`google-genai`) — **deliberately not google-adk**, whose `fastapi>=0.115` floor conflicts with
  this app's `fastapi==0.110.1` pin. Inert until `GOOGLE_API_KEY` is set in Emergent's env. The
  original bigger concept (Cloud Run/ADK/Vertex/Postgres, VIN-OEM/scan-audit workflows) is
  documented in the module README as not-yet-scoped.
- **Shipped, flagged on:** **Module 9 — Partner Growth Engine v1** (`docs/module9/README.md`) —
  Judy Robinett Power Connector CRM (Top 5 / Key 50 / Vital 100, cap-enforced), deterministic daily
  nurture-touch nudges, touch/intro approve→send with real dispatch via the existing
  `mock_send_sms`/`send_email` helpers, `/growth` owner nav page. `GROWTH_MODULE_ENABLED=true` by
  default. **Reels are explicitly deferred** — no video-generation capability exists; the
  `ReelAsset` model and `/api/growth/reels/generate` are not implemented.

### Production hardening (2026-07-21) — required before launch, set on Emergent's side
- The app now has a production mode. To go live: set `APP_ENV=production`, a strong random
  `JWT_SECRET`, `OWNER_PASSWORD` (retires the old `Owner123!` default — rotates on restart), and
  `CORS_ORIGINS` to the real domain. In production the backend **refuses to boot on the default
  `JWT_SECRET`** and does not seed demo data. Full list + steps in `EMERGENT.md`. Behavior is
  unchanged until `APP_ENV=production` is set, so tests and the preview deployment are unaffected.
- **No code launch-blockers remain.** What's left is a live `STRIPE_API_KEY` (see the Stripe
  section below) plus the other credential/env items already tracked in "Open action items."

### Card charging (2026-07-21) — done, reuses the existing STRIPE_API_KEY, set on Emergent's side
- `POST /api/charge-queue/{job_id}/charge` (owner-only, from the Charge Queue page) charges a
  completed job's card on file — off-session, idempotent per job. `POST
  /api/charge-queue/{job_id}/skip` marks a job billed outside Stripe instead. See
  `backend/charging.py` + `CHANGELOG.md` for the full design (decline/requires_action handling,
  why nothing auto-charges). **Gated by the same `STRIPE_API_KEY` placeholder-check already used
  for card capture** — no new env var. Once a **live** Stripe key is set, charging goes live
  automatically; no separate toggle.
- Recommended before trusting this with real money: run one charge through Stripe **test mode**
  first (`sk_test_...` key + card `4242 4242 4242 4242`, any future expiry/CVC) to see the full
  setup→charge cycle succeed before switching to a live key.

### Google Maps (2026-07-21) — done, credential-optional, set on Emergent's side
- Real geocoding + drive-time via `GOOGLE_MAPS_API_KEY` (Geocoding API + Distance Matrix API, both
  need billing enabled on the Google Cloud project). No key = mock exactly as before. Drive times
  are daily-cached (`drive_time_cache`, TTL-indexed, Phoenix calendar day) since the shop-portal
  day map computes drive time across other shops' jobs — see `backend/google_maps.py` and
  `geocode_address()`/`get_drive_time()` in `server.py`. Job-by-date queries use America/Phoenix
  day bounds (`backend/business_time.py`). Full detail in `CHANGELOG.md`.

### Open action items from the last check-in (2026-07-09) — these live on Emergent's side, not in code
- **Turn on the Assist copilot:** set `GOOGLE_API_KEY` (Google AI Studio key from ai.google.dev)
  in Emergent's env settings. That's the only step — the module self-activates, and the chat
  bubble appears on every owner page.
- **Xero is live-capable but not yet live**, and may be superseded by QuickBooks — see above before
  investing further setup time in Xero credentials. If Xero is kept: set `XERO_CLIENT_ID`,
  `XERO_CLIENT_SECRET`, and `XERO_REDIRECT_URI` in Emergent's env settings (the redirect must point
  at `<app-domain>/api/auth/xero/callback`), then connect the owner via **Settings → Integrations**.
  Until both are done, Xero gracefully stays in mock mode. Full key list is in `EMERGENT.md`.
- **Verify the frontend build on Emergent/Vercel.** The Step 1 `Settings.jsx` change was not built
  during the Claude session — the SPA pulls the private `@emergentbase/visual-edits` dependency, so it
  only builds inside Emergent.
- **Version numbers are out of sync:** `CHANGELOG.md` is at `0.0.3` while `frontend/package.json` is at
  `0.1.0`. Reconcile to a single scheme next time either file is touched.

## Architecture & tech stack (as-built — do NOT change without explicit approval)
- **Backend:** FastAPI in a single module `backend/server.py`; MongoDB via Motor (async). All API
  routes are mounted under `APIRouter(prefix="/api")`. JWT auth (bcrypt/passlib). Python deps in
  `backend/requirements.txt`.
- **Frontend:** React 19 SPA via **Create React App + CRACO** (`craco start|build|test`), Tailwind
  + Radix/shadcn UI components (`frontend/src/components/ui`), React Router v7, axios. **Package
  manager: yarn 1.22** (see `packageManager` in `frontend/package.json`). The "mobile field app"
  is a mobile-optimized **PWA route `/field`**, not a React Native app.
- **Database:** MongoDB (document collections, not SQL tables). No Supabase.
- **Hosting/runtime:** Emergent cloud, base image
  `fastapi_react_mongo_shadcn_base_image_cloud_arm`; services managed by **supervisor**.
- The original build spec (`memory/PRD.md` references it) asked for Supabase + Expo + Vite. The
  as-built stack deliberately deviates. **Build on the as-built stack** unless told otherwise.

## Modules beyond the core platform
Larger initiatives get their own doc under `docs/moduleN/` instead of living only in this file.
Check there before starting work on either:
- **`docs/module8/README.md` — Admin Assist Engine.** v1 shipped: `backend/assist/` (tools /
  agent loop / routes under `/api/assist`), `frontend/src/components/Assist.jsx` chat widget in
  `Shell.jsx`. Activates when `GOOGLE_API_KEY` is set. New admin capabilities should be added as
  tools in `backend/assist/tools.py` (tier = HTTP verb of the endpoint wrapped). The original
  larger concept (second runtime, ADK/Vertex, Postgres, VIN/OEM + scan-audit workflows) is
  parked in the doc's final section — do not start it without explicit scoping.
- **`docs/module9/README.md` — Partner Growth Engine.** v1 shipped and flagged **on**
  (`GROWTH_MODULE_ENABLED=true` by default): `backend/growth/models.py` + `backend/growth/routes.py`
  (contacts/grid/nudges/touches/intros, all real) and `frontend/src/pages/growth/Growth.jsx`
  (routed at `/growth`, owner nav). Reels are deferred — see the doc's "Deferred" section before
  picking that up.

## Emergent runtime rules (CRITICAL — breaking these breaks hosting)
1. **`/api` prefix:** every backend route MUST live under `/api`. Emergent's ingress routes
   `/api/*` to the backend (port 8001). Routes outside `/api` will not be reachable.
2. **No hardcoded URLs/ports.** Frontend reaches the backend via `process.env.REACT_APP_BACKEND_URL`
   + `/api`. Backend reads `MONGO_URL` and `DB_NAME` from env. Never hardcode hostnames, ports, or URLs.
3. **Don't change ports** (backend 8001, frontend 3000) or the server bind config.
4. **Environment variables** live in `.env` files (gitignored) and Emergent's env settings. Add new
   keys; never delete existing ones; never commit secret values. Document required keys in this
   file and `EMERGENT.md`.
5. **Package managers:** **yarn** for the frontend (never npm — it would create a conflicting
   lockfile). Add backend dependencies to `requirements.txt`.
6. **Restart services** with `sudo supervisorctl restart backend|frontend|all`. Don't kill PIDs by hand.
7. **`test_result.md`** contains a block marked *"DO NOT EDIT OR REMOVE"* — it is Emergent's
   main↔testing-agent protocol. Never modify it. Append testing data only **below** the data marker,
   in the documented YAML format.
8. **Preserve** `.emergent/` and `memory/PRD.md`.

## Build, run & test
| Action | Command |
|---|---|
| Backend (manual run) | `cd backend && uvicorn server:app --host 0.0.0.0 --port 8001 --reload` |
| Backend tests | `cd backend && pytest tests/ -v` |
| Frontend dev | `cd frontend && yarn start` |
| Frontend build | `cd frontend && yarn build` |
| Restart on Emergent | `sudo supervisorctl restart all` |

## Design (Impeccable)

UI work follows the vendored [Impeccable](https://github.com/pbakaus/impeccable)
skill (Apache 2.0, Paul Bakaus, v4.8.0) at `.cursor/skills/impeccable/`. Read
`SKILL.md` before a visual change and `reference/craft-floor.md` immediately
before editing UI. License and third-party notices are in that directory.
The skill's `scripts/` runtime is intentionally not vendored and `impeccable`
is not a project dependency — follow the skill's launcher-unavailable path
rather than downloading a binary or installing hooks.

CalibrationOS screens are **Operate** mode (dispatch, shop portal, admin).
Brand orange is **#FF5F1F** (`--accent`, used as a fill with near-black text).
Orange text on the gunsteel surfaces uses `--accent-ink` (#FF7E1E), because
#FF5F1F as small text misses WCAG AA on `#2A2E37` / `#343843`. Cursor also
loads `.cursor/rules/impeccable-design.mdc` for `frontend/` files. Do not
restyle toward generic AI defaults (Inter/Roboto, purple gradients, eyebrow
kickers, side-tab borders, nested cards).

## Guidelines for Claude
1. **Build on existing patterns.** Backend integrations follow a "use the real provider if its API
   key is configured, otherwise fall back to a mock/DB log" pattern (see Stripe at
   `backend/server.py` ~L35 and Resend ~L36, and Xero at ~L42). New accounting integrations
   (QuickBooks, if it replaces Xero) should follow the same pattern. Frontend pages live in
   `frontend/src/pages`; reuse `components/ui` primitives. Larger, riskier initiatives (Module 9)
   additionally use an env-driven feature flag (`GROWTH_MODULE_ENABLED`) to ship inert scaffolding
   ahead of the UI/routes being switched on — prefer this over a long-lived unmerged branch.
2. **Additive, not destructive.** Don't refactor whole folders or rewrite working modules unless
   explicitly asked. Never delete Emergent-generated code without approval.
3. **Update `CHANGELOG.md`** with every change (feature, collection/schema change, endpoint).
4. **Conventional commits:** `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`. Keep commits scoped
   and reviewable.
5. **Branch discipline:** never commit to `main`. Feature branch → PR → visual diff review → merge.
   (On Claude Code **web**, the branch is auto-assigned, e.g. `claude/<name>` — that already
   satisfies "never touch main".)
6. **Never commit secrets.** `.env` is gitignored; keep it that way.
7. When ending a session that hands back to Emergent, follow `EMERGENT.md`.

## Dev-tooling note (`.claude/`)
`.claude/settings.json` + `.claude/hooks/*` install skill packs (gstack, awesome-claude-skills) for
Claude Code **web sessions only** (guarded on `CLAUDE_CODE_REMOTE`). They do not affect the app
runtime or Emergent hosting and can be ignored from the product's perspective.

## Handoff protocol (summary; see EMERGENT.md for the return trip)
- **Emergent → Claude:** pull latest `main`, branch, read `CLAUDE.md` + `CHANGELOG.md`, work, open a PR.
- **Claude → Emergent:** update `CHANGELOG.md` + `EMERGENT.md`, merge the PR into `main`, then re-sync
  Emergent from GitHub.
- **Single source of truth = Git `main`. Reconciliation log = `CHANGELOG.md`.** Don't run both
  systems against the repo at the same time.
