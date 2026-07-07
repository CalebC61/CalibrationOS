# Module 9 — Partner Growth Engine
## Power Connector 5+50+100 + Zeely-lite Reels
### CalibrationOS · The Calibration Crew · Phoenix, AZ

Branch: `feature/module9-partner-growth`  
Status: scaffold – 2026-07-06  
Flag: `GROWTH_MODULE_ENABLED=false`

Objective: Bake Judy Robinett Power Connector CRM + Zeely-style AI case reels into CalibrationOS – ADAS calibration B2B sublet growth (glass shops → collision radar).

- Top 5 – daily touch
- Key 50 – weekly value-add
- Vital 100 – monthly nurture
- Enforced caps 5/50/100
- Give Two Favors Before Asking
- Three Golden Questions
- 3-D introductions

Zeely layer: case-study reels auto-generated from completed CalibrationOS jobs – uses existing Xero line2 `[LASTNAME] / [YEAR] [MAKE] [MODEL] / [VIN]` and documents collection.

Files in this scaffold:
- `backend/growth/models.py` – PartnerContact, Touch, Intro, ReelAsset – Pydantic / Motor – matches server.py style – 0 LLM deterministic enforcement
- `frontend/src/pages/growth/Growth.jsx` – Power Grid UI – Saira Stencil One / gunsteel #2A2E37 / orange #F97316 – feature-flagged OFF
- API (staged): /api/growth/grid, /api/growth/contacts, /api/growth/nudges/today, /api/growth/touches/{id}/approve|send, /api/growth/intros, /api/growth/reels/generate
- DB: partner_contacts, touches, intros, reel_assets

Integration:
- shops / shop_users → seed partner_contacts
- jobs → revenue_90d / referral_count_90d
- sms_log / email_log reused
- documents → ReelAsset proof-frame
- ai_action_log (Module 8) – every outbound touch writes here – HITL

Phoenix ADAS seed: Top5 = 2 glass GMs + 1 collision estimator + 1 insurance adjuster + internal tech. Key50 = 25 glass, 15 collision, 5 insurance/fleet, 3 dealers, 2 distributors. Vital100 = 60 techs, 25 body, 10 fleet, 5 tint/PPF.

Radar launch 8-week nurture – favors counter gates Ask.

Emergent runtime rules preserved: /api/* prefix, REACT_APP_BACKEND_URL, JWT owner-only, Mongo Motor, ports 8001/3000.

See `backend/growth/models.py` for full Pydantic models + NURTURE_TEMPLATES (pc_favor_1_tsb, pc_favor_2_value, pc_3_golden_q, pc_ask, pc_3d_intro, pc_radar_launch, pc_checkin).

– CalibrationOS Module 9 – 2026-07-06
