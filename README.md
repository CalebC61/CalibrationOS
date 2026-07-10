# CalibrationOS

Field-operations platform for The Calibration Crew — a mobile ADAS windshield calibration
business in Phoenix, AZ. Zone-aware booking with drive-time-calculated slots, a dispatcher
dashboard with route map, a mobile field PWA for job execution, and auto-invoicing on completion.

Built and hosted on **Emergent AI** (FastAPI + MongoDB backend, React/CRACO frontend), with
**Claude Code** used for terminal/IDE development. The two systems collaborate via Git.

## Start here
- **[CLAUDE.md](CLAUDE.md)** — project constitution, tech stack, and the Emergent runtime rules
  every change must respect.
- **[EMERGENT.md](EMERGENT.md)** — how Emergent AI resumes after a Claude Code session.
- **[CHANGELOG.md](CHANGELOG.md)** — what changed, session by session (the reconciliation log).
- **[memory/PRD.md](memory/PRD.md)** — product requirements and as-built notes.
- **[docs/module8/README.md](docs/module8/README.md)** — Module 8: Admin Assist Engine
  (v1 shipped — AI copilot, activates with `GOOGLE_API_KEY`).
- **[docs/module9/README.md](docs/module9/README.md)** — Module 9: Partner Growth Engine
  (v1 shipped, reels deferred).

## Layout
- `backend/` — FastAPI app (`server.py`), MongoDB via Motor, tests in `backend/tests/`.
- `backend/assist/` — Module 8: Admin Assist Engine (tools + Gemini loop + routes), wired into
  `server.py`; inert without `GOOGLE_API_KEY`.
- `backend/growth/` — Module 9: Partner Growth Engine (`models.py` + `routes.py`), wired into
  `server.py` behind `GROWTH_MODULE_ENABLED` (default on).
- `frontend/` — React 19 SPA (Create React App + CRACO, Tailwind, yarn).
- `docs/moduleN/` — design docs / scaffolding notes for larger initiatives beyond the core platform.

## Run
```bash
cd backend  && uvicorn server:app --host 0.0.0.0 --port 8001 --reload   # API (routes under /api)
cd frontend && yarn start                                                # web app
```
