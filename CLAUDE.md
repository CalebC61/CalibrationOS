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
6. **Active task: Step 2 — make Twilio SMS real** (send + inbound contractor YES/NO webhook), mirroring the existing "real-if-key-present, else mock" pattern. _(Step 1 — real Xero invoicing — is **done and merged to `main`** via PR #1.)_

---

## System status (as of 2026-07-03)
- Bootstrapped and iterated (~4 iterations) by Emergent AI, then extended by Claude Code (Step 1).
  Core business logic is solid; some external integrations are now real, the rest still mocked.
- **Real integrations:** Stripe (card-capture/setup mode), Resend (degrades to a DB log if no key),
  **Xero invoicing** (Step 1 — merged to `main` via PR #1 on 2026-06-16).
- **Mocked:** Twilio SMS, Google Maps (geocoding + drive-time), cloud document storage (base64-in-Mongo).
- **Missing:** Google Calendar sync (explicitly deferred).
- **Next up:** Step 2 — real Twilio SMS.

### Open action items from the last check-in (2026-07-03) — these live on Emergent's side, not in code
- **Xero is live-capable but not yet live.** Set `XERO_CLIENT_ID`, `XERO_CLIENT_SECRET`, and
  `XERO_REDIRECT_URI` in Emergent's env settings (the redirect must point at
  `<app-domain>/api/auth/xero/callback`), then connect the owner via **Settings → Integrations**.
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

## Guidelines for Claude
1. **Build on existing patterns.** Backend integrations follow a "use the real provider if its API
   key is configured, otherwise fall back to a mock/DB log" pattern (see Stripe at
   `backend/server.py` ~L35 and Resend ~L36). Wire Xero the same way so nothing breaks without creds.
   Frontend pages live in `frontend/src/pages`; reuse `components/ui` primitives.
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
