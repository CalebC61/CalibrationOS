# Module 9 — Partner Growth Engine
## Power Connector 5+50+100 + Zeely-lite Reels
### CalibrationOS · The Calibration Crew · Phoenix, AZ

Status: **v1 shipped (reels deferred) – 2026-07-08**
Flag: `GROWTH_MODULE_ENABLED` (backend, default `true`) / `REACT_APP_GROWTH_MODULE_ENABLED`
(frontend, default `true`)

Objective: Bake Judy Robinett Power Connector CRM + Zeely-style AI case reels into CalibrationOS –
ADAS calibration B2B sublet growth (glass shops → collision radar).

- Top 5 – daily touch
- Key 50 – weekly value-add
- Vital 100 – monthly nurture
- Enforced caps 5/50/100
- Give Two Favors Before Asking
- Three Golden Questions
- 3-D introductions

## What shipped in v1
- **Contacts** — full CRUD (`PartnerContact`), circle assignment with cap enforcement (409 on
  overflow; the owner explicitly demotes someone rather than auto-shuffling).
- **Grid** — `GET /api/growth/grid` returns all contacts grouped by circle with caps.
- **Daily nudges** — deterministic (no LLM) nurture-touch generator, idempotent per calendar day,
  picks a `NURTURE_TEMPLATES` entry by favor state (first favor → TSB tip, second favor → co-branded
  reel offer, 2+ favors → Three Golden Questions, `can_ask()` → the Ask, otherwise a check-in).
- **Touches** — approve → send, with **real dispatch**: `sms` via the existing `mock_send_sms`
  (Twilio itself is separately on hold, not part of this module), `email` via the existing
  `send_email` (Resend-if-configured, else logged). Sending updates the contact's
  `favors_given`/`favors_asked`/`last_touch_at`/`next_touch_due`.
- **3-D Introductions** — approve → send, emails both sides, bumps `favors_given` on both contacts
  once both sends complete.
- **`ai_action_log`** — a plain audit-trail collection written on every approve/send. Not dependent
  on Module 8 existing; Module 8 can read from it later.
- **Seed data** — grounded in the real 3 demo shops + the owner as `top5` contacts. `key50`/
  `vital100` start empty; real partners get added through the Growth UI, not fabricated.
- **Frontend** — `/growth` page (owner nav), circle-grouped grid + add-contact form, Today's Nudges
  panel with Approve/Send, a simple intro creator/list. Settings → Integrations shows a Growth
  status row.

## Deferred — not in v1
- **Reels (`ReelAsset`, `/api/growth/reels/generate`)** — the doc originally described
  AI-generated video case studies. No video-generation capability was available to build this, so
  it's explicitly out of scope this pass rather than shipped as a misleading stub. The `ReelAsset`
  model stays defined in `backend/growth/models.py` for whenever a video pipeline exists.
- Real Twilio SMS (separately on hold, not required for MVP) — `sms` dispatch reuses the existing
  mock/log helper either way.
- LLM-driven template selection / personalization — v1's nudge generator is fully deterministic.

## API
- `GET/POST /api/growth/contacts`, `PATCH /api/growth/contacts/{id}`
- `GET /api/growth/grid`
- `GET /api/growth/nudges/today`
- `GET /api/growth/touches`, `POST /api/growth/touches/{id}/approve`, `POST /api/growth/touches/{id}/send`
- `GET/POST /api/growth/intros`, `POST /api/growth/intros/{id}/approve`, `POST /api/growth/intros/{id}/send`
- `POST /api/growth/reels/generate` — **deferred**, not implemented

## Files
- `backend/growth/models.py` — `PartnerContact`, `Touch`, `Intro`, `ReelAsset` (unused this pass),
  `GRID_CAPS`, `NURTURE_TEMPLATES`, `enforce_grid_caps()`, `generate_daily_nudges()`.
- `backend/growth/routes.py` — `build_growth_router(db, require_owner, mock_send_sms, send_email)`,
  a factory so this package never imports from `server.py` (avoids a circular import). Included
  from `server.py` only when `GROWTH_MODULE_ENABLED` is true.
- `frontend/src/pages/growth/Growth.jsx` — the real page; still self-guards on
  `REACT_APP_GROWTH_MODULE_ENABLED` so it can be flipped back to the placeholder without a redeploy.
- `backend/tests/test_growth.py` — RBAC, contact CRUD, cap enforcement, nudge idempotency, touch
  and intro approve→send lifecycles.
- DB collections: `partner_contacts`, `touches`, `intros`, `ai_action_log` (`reel_assets` unused).

## Integration points
- `shops` → seeds `partner_contacts` at startup (real demo-shop contacts + the owner).
- `jobs` → most-recent-job lookup fills nurture-template placeholders (make/model/year/cal type);
  `revenue_90d`/`referral_count_90d` computed the same fetch-then-sum way `dashboard_summary` does.
- `sms_log` / `email_log` reused via the existing `mock_send_sms`/`send_email` helpers — no new
  outbound-comms code paths.
- `ai_action_log` — new, Module 8 can read from it later; this module only writes to it.

Emergent runtime rules preserved: `/api/*` prefix, `REACT_APP_BACKEND_URL`, JWT owner-only, Mongo
Motor, ports 8001/3000.

– CalibrationOS Module 9 – v1 shipped 2026-07-08 (scaffolded 2026-07-06)
