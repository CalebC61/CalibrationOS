# Module 8 — Agentic AI Assist Engine

### CalibrationOS · The Calibration Crew LLC

Status: **design/context doc only — no code written yet.** Captured 2026-07-08 after the
original write-up went unsaved. This file is the system-context handoff for whoever (Claude
Code or otherwise) eventually scaffolds and builds it — treat it as a spec, not as a
description of code that exists today.

> **This is a significant architecture deviation from the as-built stack** documented in
> `CLAUDE.md` (FastAPI + MongoDB/Motor + React/CRACO, all under one Emergent-hosted app).
> Module 8 introduces a second runtime (Python microservice on Google Cloud Run), a second
> LLM-orchestration dependency (Google ADK 2.0 + Gemini), and a second persistence layer
> (PostgreSQL/Supabase) alongside the existing Mongo store. Per `CLAUDE.md`'s "Architecture &
> tech stack ... do NOT change without explicit approval" rule, **building this requires an
> explicit go-ahead and its own design/integration pass** before implementation starts — this
> doc alone is not that approval.

## 1. System Identity & Domain Definition
- **System Name:** Calibration OS
- **Target Enterprise:** The Calibration Crew LLC (Mobile Advanced Driver Assistance Systems
  [ADAS] Calibration Service).
- **Core Objective:** Transition from a static, manual operations portal to an agentic,
  tool-integrated intelligent operating system capable of handling complex vehicle lifecycles,
  real-time safety compliance auditing, and administrative automations.

## 2. Core Technical Stack
- **Frontend Engine:** Web/mobile client interface (React/Next.js) featuring an interactive
  "Assist Button" (Command Tray/Chat Interface) for field technicians.
- **Backend Runtime:** Python 3.10+ microservice layer hosted on **Google Cloud Run**.
- **Orchestration Engine:** **Google Agent Development Kit (ADK 2.0)** (`google-adk` library),
  interfacing with **Google Gemini** LLM models via Google AI Studio / Vertex AI.
- **State & Persistence Layer:** **PostgreSQL / Supabase** for structured transaction logs,
  relational application state, and client records.
- **External Integrations:** Google Drive API (document artifact storage), accounting/invoicing
  software APIs (Xero — pending possible migration to QuickBooks, see `CLAUDE.md`), and
  OEM/VIN decoding data services.

## 3. ADK 2.0 Python Framework Paradigms
Code-first patterns native to `google-adk` v2.x abstractions:
- **Agent Abstraction:** Individual, specialized "brains" encapsulating system instructions,
  model assignment (e.g. `gemini-2.5-flash`), and localized tools.
- **Workflow Abstraction (graph-based execution engine):** Weaves deterministic Python code
  logic with adaptive AI reasoning using structural nodes and edges. Must support routing,
  loops, error-retry policies, and human-in-the-loop (HITL) gates.
- **Task API:** Structured agent-to-agent delegation, enabling multi-turn conversations and
  single-turn controlled tool outputs.
- **Ecosystem & Tools:** Wraps standard Python functions with rich docstrings to expose them to
  the LLM as executable tools.

## 4. Operational Architecture & Agent Workflows

### Component A — The "Assist Button" Pipeline
The client-side command bar executes an asynchronous request loop to the ADK backend service:
1. **Ingress:** Technician submits free-form natural language text input (e.g. "Pull the
   diagnostic history for the Camry we did yesterday and dispatch the invoice to the
   customer").
2. **Orchestration:** The root coordinator agent analyzes the payload, determines missing
   variables, and dynamically maps intent to explicit tool calls.
3. **Tool Execution:** The Python backend processes database queries or external service
   mutations, returns structured output to the model, and updates the frontend client UI state
   reactively.

### Component B — Graph-Based Core Workflows

**Workflow 1 — Dynamic OEM Specification Setup Checklist**
- Trigger: VIN ingestion at job initialization.
- An ingestion node invokes a `decode_vin()` tool.
- An ADK sub-agent queries internal vehicle databases or OEM technical service endpoints via
  specialized tools.
- A processing node extracts geometric target setup patterns, distance requirements, camera
  calibration heights, and pre-conditions (fuel levels, tire pressure).
- The workflow outputs a deterministic step-by-step UI checklist so the mobile technician
  completes mechanical compliance checks before unlocking the software verification steps.

**Workflow 2 — Dual-Invoicing, Compliance, and Accounting Sync**
- Trigger: job marked complete by a field technician.
- An auditing agent scans uploaded digital pre-scan and post-scan sheets via multimodal tools.
- The workflow computes flat-rate labor matrix conversions and cross-references lines against
  auto insurance compliance parameters.
- If discrepancies or unresolved Diagnostic Trouble Codes (DTCs) are found, the workflow
  executes a conditional branch to open an internal validation ticket.
- Upon validation, an invoicing tool maps lines to the target billing engine and syncs
  transactions, exporting the final execution log. *(Billing target is Xero today; see the
  pending QuickBooks migration note in `CLAUDE.md` — this workflow should target whichever
  accounting integration is live at build time.)*

**Workflow 3 — Long-Running Ticket Lifecycles & State Persistence**
- Trigger: intermittent field multi-stage calibrations (e.g. pre-scan → physical structural
  repair wait time → post-repair dynamic alignment).
- Uses ADK 2.0's durable session states to sustain token and interaction history across hours
  or days.
- Implements `DORMANT` workflow statuses to suspend execution context without draining compute
  runtime resources while waiting for real-world tasks.
- Leverages Human-in-the-Loop (HITL) validation gates to prompt structural managers for
  override clearance when hardware anomalies occur.

## 5. Architectural Constraints & Anti-Patterns
- **Separation of persistence concerns (database vs. file cloud):** Do not treat unstructured
  storage (Google Drive) as a primary relational index. Use PostgreSQL/Supabase to store
  structural metadata (dates, job history, VINs, client relationships) for O(1) database-tool
  queries. Google Drive is an object store only, for archival artifacts (raw scan records,
  exported PDF certificates).
- **Deterministic enclosure:** Safety-critical workflows (target distances, tool alignment
  tolerances) must be constrained inside deterministic Workflow graph edges, not left to
  open-ended LLM planning. Agent reasoning is used exclusively for extraction, text
  formulation, semantic evaluation, and dynamic routing within the defined edges.
- **Strict typing & error trapping:** All tools exposed to the `google-adk` framework must
  implement explicit Python type hints, comprehensive docstrings (defining args and return
  structures for LLM visibility), and runtime error handling so agent loops don't crash on
  network or database exceptions.

## Open questions before implementation starts
- How does this second runtime (Cloud Run + Postgres/Supabase) talk to the existing
  Emergent-hosted FastAPI/Mongo app — a sidecar service called over HTTP, or a deeper merge?
  `CLAUDE.md`'s Emergent runtime rules (routes under `/api`, no hardcoded URLs, single Mongo
  `DB_NAME`) were written for one runtime; Module 8 needs its own integration contract.
  Relates to `docs/module9/README.md` — Module 9's `ai_action_log` (HITL audit trail for every
  outbound touch) already assumes a Module 8 action-logging surface exists.
- Which accounting API does Workflow 2 target — current Xero integration or the QuickBooks
  migration under discussion?
- Scope/sequencing relative to Module 9 (Partner Growth Engine), which the user has flagged as
  the nearer-term priority.
