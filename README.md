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

## Layout
- `backend/` — FastAPI app (`server.py`), MongoDB via Motor, tests in `backend/tests/`.
- `frontend/` — React 19 SPA (Create React App + CRACO, Tailwind, yarn).

## Run
```bash
cd backend  && uvicorn server:app --host 0.0.0.0 --port 8001 --reload   # API (routes under /api)
cd frontend && yarn start                                                # web app
```
