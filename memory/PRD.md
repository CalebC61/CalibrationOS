# CalibrationOS — Product Requirements Doc

## Original Problem Statement
Build CalibrationOS — a field operations platform for The Calibration Crew, a mobile ADAS windshield calibration business in Phoenix, AZ. Replace Calendly, manual Google Maps routing, manual Xero invoicing via text, and ad-hoc contractor dispatch via text. Spec PDF + builder prompt provided by user (Jan 2026).

User chose **Path B (revenue path) + mocked integrations** for the first build. Hard platform deviations agreed with user:
- Supabase (Postgres) → FastAPI + MongoDB
- React Native/Expo mobile app → React mobile-optimized PWA at `/field`
- Vercel/Expo EAS → Emergent deploy

All other spec items (zones, pricing, invoice format, dark theme, fonts, business logic) match the spec exactly.

## Architecture
- **Backend:** FastAPI (`/app/backend/server.py`), MongoDB via Motor. All routes prefixed `/api`. JWT auth (bcrypt password hashing).
- **Frontend:** React 19 + React Router v7 + Tailwind. Single SPA. Dark theme with Barlow Condensed / DM Sans / JetBrains Mono per spec.
- **Mocked integrations:** Xero (writes to `mock_xero_invoices`), Google Maps geocoding (keyword + haversine), Twilio SMS (writes to `sms_log`).

## User Personas
- **Caleb (Owner):** Solo technician + business owner. Uses dispatcher dashboard (`/dashboard`) on web for planning, mobile PWA (`/field`) on phone in the field.
- **Maddy (Admin/Wife):** Receives invoice notifications, approves drafts in Xero. Email: admin@thecalibrationcrew.us (mocked log entry on each completion).
- **Contractor:** West-side overflow tech. Logs in to `/field` PWA, sees only assigned jobs.
- **Glass shops (clients):** Book via unique public link `/book/:token`, no login required.

## Core Requirements (Static)
- Two-zone geography: West (lng<-112.0, 8:00–14:00) and East (lng>-111.8, 14:30–19:00). Central maps to East.
- 45-min slots, 20-min drive buffer, max 7 jobs/zone/day, Monday–Saturday only.
- Pricing: static $125, dynamic $125, dual $175, triple $185, tesla $225 (per-shop custom overrides supported).
- Invoice format: Line 1 = calibration label; Line 2 = `[LASTNAME] / [YEAR] [MAKE] [MODEL] / [VIN]`.
- Document naming: `Customer_GLASSSHOPNAME_Make_Model_Year.pdf`.

## What's Been Implemented (2026-01)
### Backend
- JWT auth: `/api/auth/login`, `/api/auth/me`. Bcrypt password hashing. Role-based access (owner / contractor).
- Reference: `/api/reference/zones`, `/api/reference/pricing`.
- Mock geocoding: `/api/geocode` (keyword lookup over 17 Phoenix cities + jittered coords).
- Shop CRUD (owner-only): `/api/shops`, `/api/shops/{id}`, `/api/shops/{id}/regenerate-link`. Auto-geocode + zone-detect + booking link token + terms signing.
- Public booking: `/api/public/shop/{token}` lookup; `/api/public/availability` runs the drive-time-aware slot algorithm with home-anchored first slot and previous-job-anchored subsequent slots; `/api/public/book` creates vehicle + job + sends mock booking SMS.
- Job lifecycle: `/api/jobs` (list, owner sees all; contractor sees own), `/api/jobs/{id}` (detail), `/api/jobs/{id}/status` (driving → on_site → cancelled with side-effect SMSes), `/api/jobs/{id}/complete` (creates mock document, mock Xero draft invoice with spec-compliant line items, completion SMS, admin notification).
- Dashboard summary: `/api/dashboard/summary` (count, revenue, est miles, done-by time).
- Mock integration introspection: `/api/sms-log`, `/api/invoices`.
- Seed data on startup: owner, contractor, 3 demo shops (Safelite-Gilbert / AutoGlassNow-Goodyear with custom rates / Glass Doctor-Mesa).

### Frontend
- `/login` — dark themed auth with demo credentials shown
- `/dashboard` — split West/East zone panels, date nav, summary strip (jobs/revenue/miles/done-by), live polling every 5s, status advance actions inline
- `/shops` — list with search, copy booking link
- `/shops/new` — multi-step form with address geocoding, zone preview, optional custom rates editor, terms modal with typed signature
- `/shops/:id` — detail/edit + booking link management
- `/book/:token` — 5-step public flow: address → date+slots → vehicle → calibration type+price → review+confirm. Confirmation screen with booking reference.
- `/field` — mobile-optimized PWA technician view: today's jobs list → job detail → Start Driving / I've Arrived / Complete (with PASS/FAIL + notes + document name)
- `/invoices` — mock Xero invoice list
- `/messages` — mock SMS log
- `/settings` — pricing table, zone config, integration status panel
- Full design system: dark theme (#111/#1A/#22), accent #F97316, blue #3B82F6, all spec'd badge/button/card styles, Barlow Condensed / DM Sans / JetBrains Mono fonts

## Testing Status
- Iteration 1: **15/15 backend tests pass** (auth, RBAC, shops, geocode, public booking, slot rules, custom pricing, full job lifecycle → invoice).
- Iteration 2: New-booking alerts verified end-to-end via curl (create booking → alert appears → mark seen → cleared). UI verified via screenshot — pulsing pill + dropdown panel + NEW badge on job card.
- Frontend: login flows verified, shop creation address geocoding verified.

## Iteration 4 — At-Risk + Reschedule/Cancel + Real Upload + Scorecard (2026-01)
- **At-risk detection:** `annotate_at_risk()` adds `is_at_risk` + `risk_reason` to every job. Booked job >10 min past start, or driving/on_site job past scheduled_end → flagged. Dashboard summary returns `at_risk_count`; UI shows red border + ⚠ AT RISK badge on the card and a red "At Risk" metric tile.
- **Reschedule & cancel-with-reason:** Single modal component handles both. Reschedule loads available slots via `/public/availability` (drive-time aware). Cancel just captures reason. Both send mock SMS to customer (kind `rescheduled` / `cancelled`).
- **Real file upload:** `/api/jobs/{id}/upload-document` accepts multipart, 10 MB cap, stores base64 in `db.documents`. File renamed to spec format. Download endpoint streams binary with **RFC 5987 Content-Disposition** (handles em-dashes / unicode). Field PWA replaced text input with real file picker (`capture="environment"` for camera).
- **Tomorrow preview strip:** Below route map, shows tomorrow's jobs as horizontally scrollable mini-cards with zone badge, time, shop, vehicle.
- **Public Scorecard page:** `/scorecard/:token` shows shop-side view — 30-day stats (jobs/completed/upcoming/total spent), CTA to book, upcoming list, recent completions list. Shop detail page includes copyable scorecard link.

## Testing Status
- Iteration 4: **12/12 backend pass after fix** (one bug found and fixed: unicode em-dash in Content-Disposition → RFC 5987). Frontend visually verified for at-risk badges, reschedule/cancel modals, tomorrow strip, scorecard page (valid + invalid token), shop-detail scorecard URL block.
- **Contractor dispatch:** Owner can dispatch any booked job to a contractor. Backend creates `contractor_offers` record with 30-min expiry + sends mock SMS to contractor. Owner board shows purple `DISPATCHED_TO_CONTRACTOR` badge with live countdown + Mark Accepted/Declined buttons.
- **Offer accept/decline:** Contractor can hit accept/decline from /field PWA (real flow) OR owner can manually mark via the dashboard (simulating SMS reply). Decline reverts the job to `booked` and reassigns to owner + sends owner SMS. Auto-expiry (after 30 min) does same.
- **Drag-and-drop reorder:** Native HTML5 drag-and-drop on job cards within a zone panel. POST `/api/jobs/reorder` recomputes drive times sequentially with the slot algorithm; refuses if the order would push past zone end.
- **Route Map:** Leaflet + Carto dark basemap, numbered colored pins (orange=West, blue=East), tooltip on hover, auto-fit bounds. Free, no API key needed.
- **Editable Settings (4 tabs):** Pricing (5 calibration types, all editable + persisted in `app_settings`). Schedule (per-zone start/end/max_jobs/slot_minutes/buffer_minutes). Contractor (name/phone/home_address/active toggle, with auto-geocode of home address). Integrations (status display).
- **Field PWA pending offers:** Contractor sees orange-glowing offer cards at top of /field with Accept/Decline. Accept reveals the job in today's list and lets them drive→arrive→complete it.

## Testing Status
- Iteration 1: 15/15 backend pass.
- Iteration 2: New booking alerts verified end-to-end.
- Iteration 3: **12/12 backend pass** (dispatch, accept/decline, inactive contractor 400, pricing update + persistence, zone update + persistence, unknown zone 404, reorder recompute, reorder invalid-ids 400, contractor PUT with geocode, double-dispatch 400, list contractors RBAC). Frontend: route-map renders, dispatch modal opens + confirms, offer countdown ticks live, settings tabs all editable + saving, contractor pending-offers view verified on /field.

## Prioritized Backlog
### P0 (next iteration)
- Drag-and-drop reorder of jobs in dispatcher dashboard (recalc drive times)
- Route map embed on dashboard (would use Google Maps in production; mock with simple SVG for now)
- Contractor dispatch flow: 30-min offer window UI + mock SMS + auto-expiry cron simulation

### P1 (when real keys are available)
- Real Xero OAuth + invoice push
- Real Google Maps Geocoding + Distance Matrix (replace mock; add caching layer)
- Real Twilio SMS + webhook for YES/NO contractor replies
- Real Google Calendar sync (create/update/delete events per job)

### P2 (post-real-integrations polish)
- Drag-to-reschedule via calendar interface
- Real document upload (image capture from PWA → cloud storage)
- Invoice status polling from Xero (DRAFT → AUTHORISED → PAID)
- Email template for admin notifications (use SendGrid)
- Reschedule + cancellation workflow with calendar event updates
- Tomorrow preview strip on dispatcher dashboard
- Day-of-overrun "at risk" job warning

## Edge Cases Handled
- Zone detection from vehicle/job address (not shop address) ✓
- Sunday / past / >21-days-out date blocking ✓
- 7-jobs-per-day cap returns no slots ✓
- Custom pricing per shop overrides standard ✓
- Drive time calculated from previous job (or owner home for first job of day) ✓

## Edge Cases Deferred
- Slot gap recalculation after cancellation (currently jobs don't shift)
- Contractor accept-but-unreachable manual reassign
- Duplicate booking warning
- Google Calendar token expiry retry queue (no calendar yet)

## Next Action Items
1. User reviews app, provides feedback on flows and visual polish.
2. When ready, user provides real API credentials (Xero, Google Maps, Twilio, Google Calendar) → swap mocks to real.
3. Decide on contractor dispatch UI priority vs route map priority for iteration 2.
