# Module 8 — Admin Assist Engine

### CalibrationOS · The Calibration Crew LLC

Status: **v1 shipped – 2026-07-09** (scope revised from the original concept — see the last
section for what was deferred and why)
Flag: activates when `GOOGLE_API_KEY` is set; kill switch `ASSIST_MODULE_ENABLED` (backend,
default `true`) / `REACT_APP_ASSIST_MODULE_ENABLED` (frontend, default on)

A natural-language operations copilot built directly into the admin dashboard. The owner types
plain English into a floating chat widget — "what's on the board today?", "bump the Tesla price
to $240", "dispatch the Camry job to Marcus" — and the assistant reads live data and performs
real admin actions. **Reads answer instantly; every real action stops at a confirmation card the
owner must approve before anything executes.**

## What shipped in v1

### Backend — `backend/assist/`
- **`tools.py`** — 31 tools across Dispatch/Jobs, Shops, Settings, and Growth (Module 9). Every
  tool is a thin wrapper that calls the app's **own existing `/api/*` endpoints over localhost
  with the owner's real JWT** — no direct DB access, no duplicated business logic. A malformed
  LLM call fails the same request validation a bad UI request would; the assistant can never do
  anything the owner's own session couldn't.
- **Tiering = HTTP verb.** GET-backed tools are `safe` (execute inline, result fed back to the
  model). POST/PUT/PATCH-backed tools are `risky` (never executed by the loop; the first risky
  call halts the turn and produces a pending action).
- **`agent.py`** — a hand-rolled tool-calling loop against the plain Gemini SDK
  (`google-genai`, model `gemini-2.5-flash`, overridable via `ASSIST_MODEL`). Tools are passed
  as FunctionDeclarations only — the SDK is structurally incapable of auto-executing anything.
  Up to 6 tool rounds per message. Conversation history persists in the
  `assist_conversations` Mongo collection (no SQL, no session framework).
  - Power-user / test escape hatch: `/run <tool_name> {"arg": "value"}` skips the LLM and goes
    straight to the tier gate — this is what makes the state machine testable without
    non-deterministic, billable LLM calls.
- **`routes.py`** (all owner-only, under `/api/assist`):
  - `POST /message` — one turn; returns `{"kind": "text"}` or `{"kind": "pending_action"}`.
  - `POST /actions/{id}/confirm` — executes a pending action (410 if past its 5-minute expiry,
    configurable via `ASSIST_PENDING_TTL_SECONDS`), then the model phrases the outcome (with a
    deterministic fallback if the LLM call fails — the action itself has already run).
  - `POST /actions/{id}/cancel` — discards it.
  - `GET /conversations/{id}` — history. `GET /tools` — capability listing for the UI.
- **Audit:** every propose/confirm/cancel/execute writes to the **existing `ai_action_log`
  collection** (created by Module 9 explicitly as the surface "Module 8 can read from later" —
  now Module 8 writes to it too). Action types: `assist_propose`, `assist_confirm`,
  `assist_cancel`, `assist_execute`.

### Frontend
- **`frontend/src/components/Assist.jsx`** — floating chat bubble mounted in `Shell.jsx`
  (owner pages only), expands to a chat panel. Three message shapes: assistant text, error
  text, and the **confirmation card** (plain-language action summary + Confirm/Cancel).
  Self-guards: renders nothing when the backend reports the module disabled or when
  `REACT_APP_ASSIST_MODULE_ENABLED=false`.
- Settings → Integrations shows an Assist status row (live / disabled / unconfigured).

### Wiring (`backend/server.py`)
Same conditional-inclusion pattern as Module 9: `ASSIST_MODULE_ENABLED = bool(GOOGLE_API_KEY)
and env-switch`, router included only when enabled (routes 404 otherwise), `assist` key added
to `GET /api/integrations/status`.

## Verification (2026-07-09)
- `backend/tests/test_assist.py` — 13 deterministic tests (RBAC, tier classification,
  propose→confirm→execute, propose→cancel, double-confirm/cancel rejection, failure surfacing,
  conversation persistence) — all pass; full suite shows no regressions.
- **Real Gemini end-to-end verified**: a natural-language read answered inline from live data;
  a natural-language price change came back as a pending action (nothing mutated), Confirm
  executed it through the real endpoint, and the model phrased the outcome. Expiry path
  verified (confirm on an expired action → 410, no mutation).

## Environment
- `GOOGLE_API_KEY` *(required)* — Google AI Studio key (ai.google.dev; free tier exists). The
  only new secret. Without it the module is inert.
- `ASSIST_MODULE_ENABLED` / `REACT_APP_ASSIST_MODULE_ENABLED` *(optional, default on)* — kill
  switches.
- `ASSIST_MODEL` *(optional, default `gemini-2.5-flash`)*, `ASSIST_PENDING_TTL_SECONDS`
  *(optional, default 300)*, `ASSIST_SELF_BASE_URL` *(optional, default
  `http://127.0.0.1:8001` — the app calling itself; only tests override this)*.
- New Python deps: `google-genai`, `httpx` (neither touches FastAPI/Starlette versions).

## v1 scope boundary (fast-follow candidates)
Invoices, Charges, Messages, and Invites tools; multi-action batching; assistant access from
the `/field` PWA. The tool registry in `tools.py` is the single place to add these.

---

## Original concept — NOT this build (kept for context, not yet scoped)
The first Module 8 write-up (preserved in git history of this file) described a much larger
system: a separate Python microservice on **Google Cloud Run**, orchestrated by **Google ADK
2.0** with Gemini via **Vertex AI**, backed by its own **PostgreSQL/Supabase** store, plus
three field-facing workflow graphs — (1) VIN-triggered OEM calibration-spec checklists, (2)
multimodal pre/post-scan compliance auditing with dual-invoicing sync, (3) long-running
multi-day ticket lifecycles with dormant states and HITL gates.

None of that shipped here, deliberately:
- **No second runtime/database** — `CLAUDE.md`'s as-built rules (single Emergent-hosted app,
  Mongo only, "No Supabase") stand; v1 runs in-process.
- **No google-adk** — checked concretely: every ADK release requires `fastapi>=0.115`, and this
  app pins `fastapi==0.110.1`. Embedding ADK would have forced a framework upgrade across every
  existing endpoint for zero user-visible gain; the plain `google-genai` SDK has no such
  conflict and the ~250-line loop in `agent.py` covers everything v1 needs.
- **VIN/OEM decode, scan auditing, multi-day workflows** — real product ideas, but each needs
  its own data sources (OEM spec databases, document pipelines) and its own scoping pass.
  Revisit when the user calls one of them.

– CalibrationOS Module 8 – v1 shipped 2026-07-09 (original concept captured 2026-07-08)
