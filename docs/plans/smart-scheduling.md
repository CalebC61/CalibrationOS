# Smart scheduling — design plan

Status: **plan only**. This document does not change runtime behavior. Implementation is a later PR after Caleb answers the open questions at the bottom.

The Calibration Crew is one technician (Caleb) covering the Phoenix Valley. Glass shops book through the public link (`/book/:token`) and the shop portal (`/portal/book`). The calendar is still the original two-window model: West Valley in the morning, East Valley in the afternoon, as if those were two separate routes. A shop on one side of town is only offered that side's window, and that window is computed without looking at jobs already booked on the other side. Preferred Auto Glass (and any shop whose vehicles sit on both sides of I-17) can therefore be offered a Surprise time that Caleb cannot reach from a San Tan job, or the reverse.

This plan replaces the zone-window calendar with a per-technician route. With one bookable technician the shop sees only times that technician can actually drive. Adding a second bookable technician later is a data change: mark them `accepts_bookings`, give them a home base, and the same function assigns the job to whichever technician can fit it, preferring the earliest feasible start.

## Scope

In:

- One shared feasibility function used by availability **and** by booking, reschedule, and reorder.
- Per-calibration-type duration, one configurable buffer, a single workday window, home base as the start of the day.
- Server-side recheck at commit time, including a short lock so two shops cannot take the same gap.
- Phoenix calendar dates on every day query this feature touches.
- UI on the public booking page, the portal booking page, the owner dispatch board, and Settings so the new rules are what shops and Caleb actually see.
- A startup migration that backfills fields, re-stamps existing appointment instants by +7 hours so the wall clock stays 8:00 AM Phoenix (section 5), and does not reshuffle the route or text anyone.

Out, on purpose:

- No new package. Time zones use the stdlib `zoneinfo` module. `tzdata` is already in `backend/requirements.txt`, which is what makes `America/Phoenix` available on slim images. Drive time stays on the existing Google Distance Matrix helper (`backend/google_maps.py` + `get_drive_time()`). No OR-Tools, no Google Routes / waypoint optimization, no Maps JavaScript SDK, no `googlemaps` client, no `pendulum` / `pytz`.
- No traffic model. `CHANGELOG.md` (2026-07-21) already records that Distance Matrix `departure_time` / `duration_in_traffic` is out of scope. This plan keeps typical duration. The cache below depends on that choice.
- No Google Calendar sync (still deferred in `CLAUDE.md`).
- No automatic sliding of other customers when one job is cancelled or runs late. Promised times stay put. The freed gap becomes bookable; a late job is flagged, not silently moved.
- No deletion of `zone` on shops or jobs, no removal of contractor dispatch, no change to Stripe, Xero, Assist's safety model, or Module 9.

`SMART_SCHEDULING` (env, default `false`) gates the new read path. Deploy stays on the current algorithm until durations, hours, and buffer are confirmed and the flag is turned on. The migration backfill is safe to run either way.

---

## 1. Current code audit

Everything below lives in `backend/server.py` unless noted. There is no scheduling module. The slot rules, the book write, and the dispatch board's notion of a "day" disagree with each other.

### Zones are a calendar, not just a label

```504:513:backend/server.py
ZONES = {
    "west": {"name": "West Valley", "slug": "west", "start": "08:00", "end": "14:00",
             "slot_minutes": 45, "max_jobs": 7, "buffer_minutes": 20, "color": "#F97316",
             "lng_min": None, "lng_max": -112.0},
    "east": {"name": "East Valley", "slug": "east", "start": "14:30", "end": "19:00",
             "slot_minutes": 45, "max_jobs": 7, "buffer_minutes": 20, "color": "#3B82F6",
             "lng_min": -111.8, "lng_max": None},
}
CALEB_HOME = {"lat": 33.3528, "lng": -111.7890, "address": "Gilbert, AZ"}
```

`detect_zone()` (`server.py` ~234) is `west` if longitude `< -112.0`, otherwise `east`. The east record's `lng_min: -111.8` is never read. Central Phoenix is east. Zone is computed from the **job address**, not the shop address (`public_availability` ~842, `create_shop` ~706). A single shop can already book both sides. The bug is that each side has its own clock.

`memory/PRD.md` states the original spec: West 8:00–14:00, East 14:30–19:00, 45-minute slots, 20-minute buffer, max 7 jobs per zone, Monday–Saturday. The code blocks Sunday only (`weekday() == 6`). Saturday is open. That part stays.

`buffer_minutes` is stored and editable in Settings (`frontend/src/pages/Settings.jsx`) and via Assist's `update_zone` tool. **Nothing in `compute_available_slots`, `public_book`, or `reorder_jobs` reads it.** The 20-minute buffer has never affected an offered time.

`slot_minutes` (45) is the only duration, for every calibration type. `STANDARD_PRICING` (~496) has `label` and `price` only. There is no per-type duration anywhere.

Persisted zone edits load from `app_settings` `_id: "zones"` in `load_settings()` (~525) for `start`, `end`, `max_jobs`, `slot_minutes`, `buffer_minutes`.

### What `compute_available_slots` actually does

`POST /api/public/availability` (`public_availability`, ~832) geocodes the address, rejects anything outside the metro box (`backend/google_maps.py` `METRO_*`), rejects Sunday / a UTC-yesterday / more than 21 UTC-days out, then calls `compute_available_slots(zone, day, lat, lng)` (~772).

That function:

1. Loads non-cancelled jobs **in that zone only** whose `scheduled_start` string falls in `[UTC midnight, next UTC midnight)`.
2. Returns nothing if that zone already has `max_jobs` (7).
3. Anchors at the **last** job's `scheduled_end`, or at the zone start sitting on `CALEB_HOME` when the zone is empty.
4. Adds one drive time from that origin to the new pin (`get_drive_time`).
5. Rounds up to a 15-minute mark, then walks forward by `slot_minutes` (45) until `zone end`. It does not step by 15. It does not look at gaps in front of the last job. It does not look at the other zone at all.

So an empty West window offers Surprise times anchored at Gilbert, and an empty East window offers San Tan times anchored at Gilbert at 14:30, even when a West job has him in Buckeye at 14:00. A hole between two West jobs is never offered. A San Tan job and a Surprise job on the same morning can both exist if one of them was rescheduled, because reschedule does not check the route.

`public_book` (~859) does **not** call `compute_available_slots`. It trusts `scheduled_start` from the client, sets `scheduled_end = start + zone.slot_minutes`, computes drive time from the previous in-zone job only, assigns `technician_id` to whoever has `role: "owner"`, and sets `sequence_order` to "count of in-zone jobs that day + 1". A later booking of an earlier time gets a higher sequence number. There is no overlap check, no lock, and no "can he still reach the next job" test. Any client that can post the booking payload can store any timestamp.

`POST /api/portal/book` (`portal_book`, ~1949) copies the shop's booking token onto the body and calls `public_book`. One fix covers both writers. It currently mutates the request model in place; keep that delegation, just stop trusting the requested instant.

### Other writers and readers

| Path | What it does today | Why it has to change with this |
|---|---|---|
| `POST /api/jobs/{id}/reschedule` (~1153) | Writes a new start. End = start + that job's **zone** `slot_minutes`. No drive check. SMS uses the datetime's own clock. | Must use the same feasibility function, excluding this job, or the owner modal will keep placing unreachable times. |
| `POST /api/jobs/reorder` (~1578) | Owner-only. Body is `{zone, date, ordered_job_ids}`. Repacks that zone from `CALEB_HOME` at zone start, 15-minute rounding, `slot_minutes` length. Refuses if the pack would pass zone end. **Rewrites `scheduled_start`** and does not text the customer. | Pack a technician's day, not a zone. Same duration + buffer + home rules. |
| `annotate_at_risk` (~978) | `driving` / `on_site` past `scheduled_end`, or `booked` more than 10 minutes past `scheduled_start`. Does not know about the next job. | Keep it. Add a separate route-conflict flag (below). Do not overload "at risk". |
| `GET /api/jobs`, `GET /api/dashboard/summary`, `GET /api/portal/day-map` | Same UTC-midnight day window. | Same Phoenix day helper, or a 6 PM Phoenix job will not show on the day the shop booked. |
| `GET /api/portal/day-map` (~1912) | Other shops' jobs as anonymous pins with drive time **from the viewing shop**, not along Caleb's route. | Leave the privacy behavior. Only the day window changes. |
| Dispatch (`POST /api/jobs/{id}/dispatch`, offer accept/decline/expire, ~1487–1568) | Offer sets `technician_id` to the contractor immediately, while `status` becomes `dispatched_to_contractor`. Decline and expiry put it back on the owner. | A pending offer must still block Caleb even though it is no longer on his `technician_id`. See the route loader below. |
| `expire_stale_offers()` (~1467) | Docstring says it runs on list-offers and list-jobs reads. The only caller is `GET /api/contractor-offers` (~1528). `GET /api/jobs` does not call it. A 30-minute offer stays `pending` until someone opens that list. | Availability, book, reschedule, cancel, reorder, and `list_jobs` must expire stale offers or a dead offer blocks the day all afternoon (or, if the loader only looks at `technician_id`, it doesn't block him and the job snaps back on top of a new booking). |
| Seed (~2098) | Owner home Gilbert; contractor home Goodyear, `role: "contractor"`, `home_zone: "west"`. | The slot math never reads either home. It reads the `CALEB_HOME` constant. The contractor is not a second route today. |

`get_drive_time()` (~281) calls Google Distance Matrix when `GOOGLE_MAPS_API_KEY` is set, else `mock_distance_matrix` (haversine, `max(10, int(miles * 2.2 + 5))`). Real results cache in `drive_time_cache`. On any Maps error it falls back to the mock so a quota blip does not fail the request. `distance_matrix_request_params()` asks for `duration`, not `duration_in_traffic`, and does not send `departure_time`.

Frontend, the parts shops and Caleb touch:

- `frontend/src/pages/PublicBooking.jsx` — steps are address → date and slots → vehicle → calibration type → confirm. The type, which will decide duration, is chosen **after** the slot. Copy says the job "is in our West/East Valley service area."
- `frontend/src/pages/PortalBook.jsx` — same step order. Its own `fmt()` formats in the browser's local zone instead of `formatTime`.
- `frontend/src/lib/api.js` `formatTime` / `todayStr` — `toLocaleTimeString(undefined)` and the computer's local date. No `timeZone`.
- `frontend/src/pages/Dashboard.jsx` — two panels, subtitles hardcoded `"8:00 AM – 2:00 PM"` and `"2:30 PM – 7:00 PM"`, drag-and-drop calls `/jobs/reorder` with a zone. `RouteMap.jsx` draws two polylines. `TomorrowStrip.jsx` counts West vs East.
- `frontend/src/components/RescheduleCancelModal.jsx` — loads `POST /public/availability` (so the job being moved still blocks itself) and renders `slots.slice(0, 12)`.
- `frontend/src/pages/Settings.jsx` — per-zone start, end, max jobs, slot length, buffer. Contractor home is editable. **Caleb's home is not.** Changing the buffer here currently does nothing to slots.
- Assist (`backend/assist/agent.py` system prompt ~72, `backend/assist/tools.py` `reorder_jobs` / `update_zone`) still describes a West-morning / East-afternoon business and can edit the zone fields the new algorithm will ignore.

Existing tests that book through availability and then assert `zone == "east"|"west"` (`backend/tests/test_calibrationos.py`, `test_iteration3.py`, `test_iteration4.py`) stay valid if `zone` remains a geographic label. `test_iteration3.py` `test_reorder_*` posts `zone: "east"` and will need to match the new reorder body in the implementation PR. Do not weaken those tests to hide a behavior change; update the request shape and keep the "sequence and times actually move" assertions.

---

## 2. Data model and migration

MongoDB, no new database. New fields are additive. Old `zone` stays.

### Schedule settings

New `app_settings` document `_id: "schedule"`:

| Field | Default | Why |
|---|---|---|
| `timezone` | `America/Phoenix` | Arizona does not observe DST. Fixed offset UTC−7. |
| `day_start` | `"08:00"` | Leave home. If a zones document exists, prefer its west `start` so an edit Caleb already saved is not thrown away. |
| `day_end` | `"19:00"` | Last job must **finish** by this time. Prefer the saved east `end` when present. |
| `buffer_minutes` | `15` | Caleb asked for ~15. The stored zone buffer of 20 has never been applied. Do not copy 20 forward and call it the live value. |
| `grid_minutes` | `15` | Same rounding the code already uses. Not a Settings control in v1. |
| `horizon_days` | `21` | Unchanged. |
| `closed_weekdays` | `[6]` | Sunday. Unchanged. |

Per-type duration lives on the pricing document the app already saves (`app_settings` `_id: "pricing"`), next to `price` and `label`:

| Type | `duration_minutes` until Caleb edits it |
|---|---|
| static, dynamic, dual, triple, tesla | `45` |

45 is the only number the product has ever used. Inventing 60/75/90 would change how many jobs fit a day before anyone has confirmed real ADAS times. Settings gains a minutes input beside each price. `load_settings()` already overlays that document; extend it to read `duration_minutes`.

A job stores its own `duration_minutes` at booking time. Later edits to the price table do not rewrite history. `scheduled_end = scheduled_start + duration_minutes`. The buffer is **not** baked into `scheduled_end`. It is the gap between "work is done" and "wheels are rolling" (pack-up, walk to the van). `annotate_at_risk` keeps comparing against `scheduled_end`, which remains the on-site end.

### Technicians

On `technicians` (the collection already has `home_lat`, `home_lng`, `home_address`, `home_zone`, `role`, `is_active`):

| Field | Owner (existing row) | Contractor (existing row) |
|---|---|---|
| `accepts_bookings` | `true` | `false` |
| `work_start` / `work_end` | unset → use schedule defaults | unset |

`home_zone` stays as a label and is not read by the new math. A second technician is: insert or edit a `technicians` row, set `accepts_bookings: true`, set `is_active: true`, set a geocoded home. No schema migration beyond that. The seeded "West-Side Contractor" does **not** become bookable just because this ships. Dispatch to that contractor stays a manual owner action.

Slot generation reads `technician.home_lat/lng`, never the `CALEB_HOME` constant. The constant remains only as the seed value.

### Jobs

Keep `zone`, `technician_id`, `scheduled_start`, `scheduled_end`, `job_lat`, `job_lng`, `sequence_order`, `drive_time_minutes`.

Add:

- `duration_minutes` — snapshot.
- `schedule_override` — `true` when an owner forced a time that failed feasibility. Absent on normal bookings.
- `override_reason` — optional string, set only with the flag above.

`sequence_order` becomes the order of that technician's non-cancelled jobs on that Phoenix day, by `scheduled_start`. It is no longer "Nth job in this zone."

`drive_time_minutes` remains "minutes from the previous stop (or home) to this job," recomputed when a job is inserted, cancelled, reordered, or reassigned. It is a display value. Feasibility always calls `get_drive_time` again rather than trusting the stored number. The +7 hour re-stamp does not recompute it; the number was a drive, not a clock.

### Day lock

New collection `booking_locks`, one document per Phoenix date, `_id = "day:YYYY-MM-DD"`. Fields: `created_at`. Not a per-technician lock: the assignee is chosen inside the critical section, so two requests that both want Caleb must share one mutex. Volume is a handful of bookings a day; a day-wide lock held for a recheck plus one insert is the smallest thing that is actually correct.

Steal the lock if `created_at` is older than 30 seconds (a crashed worker must not freeze the day). Also a TTL index on `created_at` as a backstop. Mongo's TTL sweeper is coarse, so the steal is the real mechanism. Do not require a multi-document transaction. Emergent's Mongo may or may not be a replica set; the lock document does not care.

Acquisition is non-blocking. `insert_one` on a duplicate `_id` is an immediate `409`, not a wait. Waiting is what turns two cross-day reschedules into a deadlock. The lock is held only for the rest of that one request (expire offers, load, feasibility, write), including any Distance Matrix calls that miss the cache. It is not held while the shop fills in the vehicle form. A solo calendar can live with a multi-second hold; a scraper cannot, because a held lock just makes the next book `409` and retry.

### Migration (startup, idempotent)

Run from startup after `load_settings`, before the process serves traffic (same place as `seed_data()`). Guard: insert `app_settings` `_id: "schedule_migration"` version `1` **first**. If that `_id` already exists, skip. Two workers booting together then cannot both recompute. Safe to run on every subsequent boot.

1. Upsert the `schedule` document with the defaults above if missing. Do not overwrite hours or buffer Caleb has since saved.
2. For each pricing key missing `duration_minutes`, set `45`.
3. Set `accepts_bookings` on existing technicians as in the table above, only when the field is absent.
4. For each job missing `duration_minutes`: if both start and end parse, set it to the rounded minute difference (so a historical 45- or 60-minute slot stays what it was). Otherwise use the type default.
5. Re-stamp `scheduled_start` and `scheduled_end` only, once, by **+7 hours**. See "Wall clock was stored as UTC" below. Do not touch `actual_arrival`, `actual_completion`, `created_at`, or anything else. Do not reorder the day and do not text anyone. The version document is what makes this run once; a second run would add another 7 hours.
6. Recompute `sequence_order` per `(technician_id, Phoenix day)` by the new start time. The customer's wall-clock promise does not change. The stored instant does, by the offset that was missing.

After migration, some existing days will be geographically impossible (a West 8:00 and an East 8:00 that the old windows allowed, or a cross-valley pair the old code never compared). Leave them. The dispatch board shows a route conflict. Caleb moves them by hand if he wants to. The migration must not text customers and must not call Maps.

Index (startup, next to the existing `drive_time_cache` TTL): `jobs` compound index `{technician_id: 1, scheduled_start: 1}`. The lock collection uses `_id` lookups only.

---

## 3. Slot algorithm

New module `backend/scheduling.py`. Pure: stdlib + a drive-time callable the caller passes in. No Motor, no `requests`, no FastAPI. Same split as `backend/charging.py` and `backend/google_maps.py`, so the tests do not need Mongo or a Maps key.

`server.py` keeps the route handlers, the lock, geocoding, and `get_drive_time`. It loads the day's jobs and calls the pure function. Callers of the gap function: public availability, public book, owner reschedule, the override check. Reorder is a separate pack helper in the same module (same rounding, duration, buffer, and home rules) so the two cannot drift.

### Inputs

For one technician and one Phoenix calendar date:

- Work window `day_start`–`day_end` in `America/Phoenix` (technician `work_start`/`work_end` override the global ones when set).
- `grid_minutes`, `buffer_minutes`.
- The new job's coordinates and `new_duration` (the calibration type being booked).
- Home coordinates.
- The route job list from the loader below. Each job contributes `scheduled_start`, `duration_minutes`, `lat`, `lng`, `status`, and `actual_completion` when set.
- `now`, used only for the lateness rule below.
- Optional `ignore_job_id` for reschedule, so the job being moved is not an obstacle to itself. This argument exists on the owner path only. It is not a field on `POST /api/public/availability` (a public caller could pass another shop's job id and see through that job, or book on top of it).

A job with no coordinates fails the day closed: return no slots and log it. Do not offer a route we cannot measure. That should be impossible for anything `public_book` wrote.

### Whose jobs are on the route

Filtering by `technician_id` alone is wrong. Dispatch rewrites `technician_id` to the contractor the moment the offer is sent (`dispatch_job`, ~1516), and `expire_stale_offers` does not run unless someone hits `GET /api/contractor-offers`.

`load_route_jobs(technician, phoenix_day)`, called inside the day lock after `expire_stale_offers()`:

1. Expire pending offers whose `expires_at` is past. That reassigns those jobs to the owner and texts him, which is the existing expiry behavior; booking and the dashboard poll are now allowed to be the thing that fires it. Do this inside the lock so the reassignment and a new insert cannot interleave.
2. Start from non-cancelled jobs on that Phoenix day with this `technician_id`.
3. If this technician is the owner, also include jobs that are `dispatched_to_contractor` and have a **pending** (not yet expired) `contractor_offers` row, whatever `technician_id` says. Accepted, declined, and expired offers do not. Once the contractor accepts, the job leaves Caleb's route. The seeded contractor is not bookable, so an accepted job simply sits on their id until `accepts_bookings` is turned on later.
4. Drop `ignore_job_id` when present.

`GET /api/jobs` calls the same expiry helper on the way in, so the 5-second dashboard poll cannot show a countdown for an offer that already died. That call is not behind `SMART_SCHEDULING`. The docstring already claims it happens.

### Predecessor ready time

Sort the day's jobs by `scheduled_start`. The new job falls into exactly one gap: before the first, between two, or after the last.

For a previous job, wheels-rolling time is:

```
ready = scheduled_start + duration_minutes + buffer_minutes
```

That is the rule Caleb stated (start + type duration + buffer), not "whatever `scheduled_end` happens to say," and not the unused zone buffer. Do not implement ready as `scheduled_end + buffer`. For jobs this system writes, `scheduled_end = start + duration` and the buffer sits after that, so adding buffer again on top of `scheduled_end` would double-count. For old jobs, `scheduled_end` is start plus the old slot length; the snapshotted `duration_minutes` is that same delta. One formula.

The neighbor formula is necessary and not sufficient. If an earlier stop is already unreachable, trusting the next job's scheduled end offers a time after it that assumes he finished on time when he has not arrived yet.

Walk the existing route once and keep a departure cursor. It only ever moves **later** than the scheduled ready time. It never opens a hole by assuming he will start early, and it never changes a stored `scheduled_start`.

```
cursor_time = day_start          # at home; no buffer on the leave-home leg
cursor_pin  = home
for each existing job in scheduled order:
    arrival = cursor_time + drive(cursor_pin → job)
    leave   = max(job.scheduled_start, arrival) + job.duration_minutes + buffer_minutes
    if the Phoenix date is today:
        if status is driving or on_site, or (status is booked and now > job.scheduled_start):
            leave = max(leave, now + buffer_minutes)
        if status is complete and actual_completion parses:
            leave = max(leave, actual_completion + buffer_minutes)   # late finish pushes; early finish does not pull
    job.ready = leave
    cursor_time, cursor_pin = leave, job.pin
```

The gap **before** the first job uses `ready = day_start` at home. He is not on site in Surprise at 8:00 unless the pin is at home. There is no calibration buffer on that leg; the buffer is pack-up between jobs.

The gap **after** job `i` uses `job.ready` from the cursor, which is at least `scheduled_start + duration + buffer` and later when the chain in front of it is already broken or he is still on site.

Future days still run the cursor (a migrated impossible pair has to poison the gaps after it) but ignore `now` and `actual_completion`. A completed job on a future day should not exist; if it does, it occupies its scheduled window only.

### The test for one gap

Drive lookups, at most two per gap:

- `drive_in` = drive(previous pin or home → new pin)
- `drive_out` = drive(new pin → next job's pin), or 0 when this gap has no next job

```
ready    = day_start in the first gap, otherwise the previous job's cursor ready
earliest = ready + drive_in
latest   = next.scheduled_start - drive_out - buffer - new_duration     # no next job: latest = day_end - new_duration
```

`latest` stays anchored on the next job's **scheduled** start. Propagation does not move the promise. If the cursor says he cannot leave the previous job in time to be back for that promise, `earliest > latest` and the gap is empty.

Round `earliest` **up** to the next grid mark (7:01 and 7:15 both become 7:15; an exact 7:15 stays). Round `latest` **down**. If `earliest > latest`, the gap is empty.

Also require `earliest >= day_start` and `latest + new_duration <= day_end`. The drive home after the last job is **not** reserved. Quitting time means the last calibration is done, matching today's zone-end rule (the slot had to finish by zone end; the drive home was his).

Emit every grid instant from `earliest` through `latest` inclusive. Unreachable instants are simply absent. Do not return them greyed out.

No Maps call per grid point. A day with `n` existing jobs needs the `n` drives along the existing chain (home → first → … → last, for the cursor) plus at most two drives per gap between those stops and the new pin. Under about `3n` lookups, `n` under 20, all through `get_drive_time`, so repeats are cache hits. Round grid instants in **Phoenix local time**, not by looking at the UTC hour. The offset is a whole 7 hours, so the minute-of-hour happens to match UTC, but "is this inside 8:00–19:00" and "what Phoenix date is this" do not. An implementer who checks `hour >= 8` on the UTC datetime will accept 8:00 UTC (1:00 AM Phoenix) and reject a real 6:00 PM.

`max_jobs` per zone goes away. The workday is the cap. Whether a hard count cap should also exist is an open question; the recommendation is no second cap in v1.

### Worked examples

Drive minutes below are today's **mock** formula (`max(10, int(miles * 2.2 + 5))`) on these exact pins, which are already in the repo (`CALEB_HOME`, the contractor seed, and `PHOENIX_CITY_COORDS`): Gilbert home `(33.3528, -111.7890)`, Surprise `(33.6292, -112.3679)`, San Tan `(33.1962, -111.6463)`, Goodyear `(33.4353, -112.3576)`. They are the mock city anchors, not a live Google geocode of the words "San Tan Valley". Tests inject the minute values (Gilbert→Surprise 89, Gilbert→San Tan 34, San Tan↔Surprise 117, Goodyear→Surprise 34) so a different geocoder cannot fail the test. Live Distance Matrix replaces the minutes in production. The comparisons stay the same. Duration 45, buffer 15, grid 15, day 8:00–19:00 Phoenix, one technician, chain not already broken.

**Empty day, Surprise.** Leave Gilbert 8:00, mock drive 89 minutes, arrive 9:29, round up to 9:30. Job must finish by 19:00, so the last legal start is 18:15. Offered: 9:30, 9:45, …, 18:15. 8:00 is not offered. He cannot be in Surprise at 8:00 if he leaves Gilbert at 8:00.

**Empty day, San Tan.** Mock drive 34 minutes. Arrive 8:34, first slot 8:45.

**San Tan already booked at 8:45 (static).** Ready = 8:45 + 45 + 15 = 9:45. Mock drive San Tan → Surprise is 117 minutes. Arrive Surprise 11:42, first offered Surprise time is **11:45**. An 8:00 or 9:30 Surprise button does not exist. This is the case the zone model gets wrong: those two addresses are in different zones, so today's code never compares them.

**Surprise already booked at 9:30, shop asks for San Tan in the morning.** Earliest San Tan from home is 8:45. To start Surprise at 9:30 he would have to finish San Tan, wait out the buffer, and drive ~117 minutes, which means the San Tan start would have to be before 6:33. No morning slot. First San Tan time is after Surprise: ready 9:30 + 45 + 15 = 10:30, plus 117 minutes → 12:27, round up to **12:30**.

**Same shop, both sides.** Preferred's booking link does not have a side. The job address is the pin. They can book San Tan at 8:45 and Surprise at 11:45. They cannot book both at 8:45.

**Second technician, later, not in v1 data.** Goodyear home → Surprise is mock 34 minutes, so that technician's first Surprise slot is 8:45. Caleb's first is 9:30. The shop sees 8:45 (assigned to the Goodyear technician) and 9:30 (either can make it; see assignment). Caleb's row stays `accepts_bookings: true` only until that second row exists.

### Assignment when more than one technician accepts bookings

```
for each bookable, active technician with a home:
    compute that technician's feasible grid
for each distinct start instant that at least one technician can make:
    keep a single slot
    assignee = the technician who can make that instant
               with the smallest drive_in,
               then fewer non-cancelled jobs that day,
               then technician id (stable)
```

"Earliest feasible" means the shop is offered the earliest instant **any** bookable technician can reach. It does not mean "always give the job to Caleb if he could also do a later slot." At a tied instant, the shorter inbound drive wins, so a Goodyear technician already on the west side takes the Surprise 9:30 rather than pulling Caleb across the valley to arrive at the same clock time with a longer drive.

The availability payload may include `technician_id` for the server's own debugging. The shop UI does not show a technician name. `public_book` does not trust a client-supplied technician id. Inside the lock it runs this choice again and assigns whoever can still make that exact instant.

With only Caleb bookable, the loop is one iteration. That is the configuration this ships with.

### Reorder pack

`POST /api/jobs/reorder` body becomes `{technician_id, date, ordered_job_ids}`, and it takes that day's lock (after expiring stale offers) so it cannot repack under a book that has already read the old order. Same packing idea as today, but:

- Anchor at that technician's home at their `day_start`.
- Each stop's length is its snapshotted `duration_minutes`.
- Insert `buffer_minutes` and a fresh drive time between stops.
- Refuse the whole reorder if any stop would finish after `day_end` or if a job id is not his, not on that Phoenix day, or is `cancelled` / `complete`.

This **still rewrites `scheduled_start`**, which is what reorder does now, and it still does not send SMS. The dashboard confirm copy has to say the times will move. Adding the buffer, which reorder has never applied, will push stops later than a reorder does today. That is intended once the flag is on, and it is why the flag exists.

Do not build a separate "optimize the route" action. Drag order remains Caleb's order.

### Route conflict flag

Same cursor walk as slot generation, called from `GET /api/jobs` and the dashboard summary. Set `route_conflict` when the cursor's `arrival` at that job is after its `scheduled_start` (he cannot be there when the customer was promised, given everything in front of it). Do not keep a second, weaker inequality that only looks at the immediate previous scheduled start; that one misses a break two stops back. This catches migrated impossible pairs and a contractor job that snapped back onto Caleb. It is not `is_at_risk`. A job can be on time relative to its own clock and still unreachable, and a job can be late without the next pin being the problem.

---

## 4. Commit path, races, owner override

### Normal booking

`public_book` and, through it, `portal_book`:

1. Resolve the shop, geocode, reject out-of-metro. Unchanged. The client does not submit lat/lng. Feasibility uses this fresh geocode. If it drifted from the availability call, the recheck returns 409 and the shop refreshes. That is acceptable; do not trust a client coordinate.
2. Parse `scheduled_start` as an absolute instant. Convert to Phoenix local before any grid, Sunday, past, or horizon test. Reject if the Phoenix local minute is not on the grid, if the Phoenix date is Sunday, past, or past the horizon, or if the local time is outside the work window.
3. Take the day lock (steal if stale, don't wait). If the lock is held, `409` with `That time was just taken. Refresh and pick another.` Log the reason as `lock_held`, not `infeasible`. The shop sees one sentence either way; the log has to tell those apart.
4. `expire_stale_offers()`, then `load_route_jobs`, then assignment for the requested instant and the **submitted** `calibration_type`. If nobody can make that exact instant, `409` with the same sentence, logged as `infeasible`. Do not create a vehicle on the failure path.
5. Insert vehicle, then job, with `technician_id`, snapshotted `duration_minutes`, `scheduled_end = start + duration_minutes` (buffer not included), geographic `zone` (still from longitude, for badges only), `sequence_order`, `drive_time_minutes`.
6. Release the lock in a `finally`. SMS and the owner alert stay as they are, except the clock in the SMS is formatted in Phoenix (see timezone).

Availability and booking share the pure function, so the only way a shown slot fails is if the day changed between the click and the submit (another shop, a cancel, a reschedule, Maps returning a different minute). That is the race the lock plus the recheck exist for. There is no multi-minute hold on a slot. The wizard is short; a hold collection would be abandoned locks and a second expiry story. Not worth it at this volume.

A double click is already guarded by the button's submitting state. The lock makes the second request a 409 even if the UI slips.

### Reschedule

Owner `POST /api/jobs/{id}/reschedule` loads feasibility with `ignore_job_id` set. Lock every Phoenix date the move touches (source day and destination day), acquiring in ascending date-string order, non-blocking. One date means one lock. If the second insert hits a duplicate, release the first and `409`. Reject when the new instant is not feasible, unless `force` is set. On success set `scheduled_end = new_start + job.duration_minutes` from the snapshot already on the job, not from the zone's `slot_minutes`. Today's handler (~1166) uses the zone slot, so a reschedule would otherwise desync `annotate_at_risk` and the portal from the route math the moment durations stop being 45.

Uses the job's stored `job_lat` / `job_lng`. Do not geocode the address string again for a move that is not changing the pin.

New owner-only preview: `POST /api/jobs/{id}/availability` with `{date}`, returning the same slot shape, this job excluded. The reschedule modal calls that, not the public endpoint. It takes the same lock, expires stale offers, and releases before responding.

### Owner force-book

Shops cannot force. Two owner-only paths:

- Reschedule body gains `force: true` and a required `override_reason`. The time is written, `schedule_override: true`, conflict flag will show, customer SMS still goes out.
- `POST /api/jobs/override-book` (owner auth) creates a job the same way `public_book` does, but skips the feasibility rejection. Required: `shop_id`, job address, `scheduled_start`, vehicle fields, `calibration_type`, `override_reason`. It still geocodes, still refuses out-of-metro, still refuses a past instant, still takes the day lock, still expires stale offers, still assigns the bookable technician with the earliest-feasible rule **if** someone can make that exact instant, and if nobody can, assigns the owner and sets `schedule_override`. Overlap with his existing jobs is allowed in that last case. The other job is not moved. The conflict banner is the consequence. The response includes which technician was assigned so the form doesn't imply it landed on Caleb when a second bookable tech actually took it. This is the "the shop called, put them on anyway" path. It is one form on the dispatch board, not a second five-step wizard.

Force never bypasses the metro box, the lock, or "don't book in the past." It bypasses drive-time feasibility only. A forced reschedule writes `scheduled_end` from `duration_minutes` the same way a normal one does.

---

## 5. Day bounds, home, Phoenix time

`ZoneInfo("America/Phoenix")` from the stdlib. No new dependency (`tzdata` is already pinned).

Store instants as timezone-aware UTC ISO strings, which is what the code stores today (`datetime.isoformat()` with `+00:00`). Do not store naive local times.

### Wall clock was stored as UTC

Every slot, book, and reorder builds "8:00" with `datetime.combine(..., tzinfo=timezone.utc)`. The SMS then `strftime`s that UTC value, so the text says **8:00 AM**. A browser in Phoenix running `formatTime` (`toLocaleTimeString` with no time zone) shows the same instant as **1:00 AM**. The zone settings and the dashboard subtitles also say 8:00 AM. The wall clock the business meant is the one in the text and the settings, not the one a Phoenix browser paints today.

Shipping Phoenix formatting without moving those instants would make every existing appointment, and every slot the old algorithm still emits, read as 1:00 AM. Shipping the +7 hour re-stamp without Phoenix formatting would make the SMS say 3:00 PM.

So these ship together, and they are **not** behind `SMART_SCHEDULING`:

- Migration adds 7 hours to existing `scheduled_start` / `scheduled_end` exactly once (step 5 above). 8:00 stored as `08:00Z` becomes `15:00Z`, which is 8:00 AM Phoenix. `19:00Z` becomes 7:00 PM Phoenix (`02:00Z` the next UTC date), which is why the day-bound helper has to land in the same deploy or that job falls off "today."
- The old zone algorithm, while the flag is off, still only looks at one zone and still ignores buffer and the other side of town. It stops using `timezone.utc` for `combine`. "08:00" means 8:00 AM Phoenix. Otherwise the flag-off calendar shows 1:00 AM the moment formatting is fixed.
- SMS, alerts, and `formatTime` / `formatDate` / `todayStr` format in Phoenix. Portal's private `fmt` goes away in the same change.

This is the one place the migration writes `scheduled_start`. It preserves the wall clock in the text message. It does not reshuffle who is before whom.

Every "jobs on date D" query goes through one helper:

```
phoenix_day_bounds(day: date) -> (start_utc, end_utc)
# [D 00:00 Phoenix, D+1 00:00 Phoenix) converted to UTC
```

Today the handlers do `datetime.combine(day, time(0, 0), tzinfo=timezone.utc)`. That window is 5:00 PM the previous Phoenix evening through 5:00 PM on the named day. A 6:00 PM Phoenix job is `01:00Z` the next UTC date, so it falls out of the dashboard, the field list, the portal day map, and the slot query, and the previous evening's jobs fall in. "Today" is `now_utc().date()`, so after 5:00 PM Phoenix (midnight UTC) the API treats the real today as a past date and refuses it.

Replace that bound in: `compute_available_slots` / the new loader, `public_book`'s day scan, `list_jobs`, `dashboard_summary`, `reorder_jobs`, `portal_day_map`, and the Sunday / past / horizon checks (`public_availability`). JWT expiry and similar stay UTC. This is not a drive-by rewrite of every `datetime` in the file.

Horizon and "is this date in the past" use the Phoenix calendar date of `now`, not the UTC date.

Customer-facing clocks:

- `formatTime` / `formatDate` / `todayStr` in `frontend/src/lib/api.js` pass `timeZone: "America/Phoenix"`. A phone set to another zone still shows Phoenix appointment times. `todayStr` must not be the browser's local date either; build `YYYY-MM-DD` with `Intl.DateTimeFormat("en-CA", { timeZone: "America/Phoenix", ... })`.
- `PortalBook.jsx` deletes its local `fmt` and uses that helper.
- SMS and alert strings that `strftime` a start time convert to Phoenix first. Otherwise a 6:00 PM job texts "1:00 AM".

Server-rendered slot `label`s, if kept, are formatted in Phoenix too. The UI should prefer formatting the ISO itself so there is one clock.

Home base: the technician document. Settings gets an "Your home base" address on the schedule section, saved with the existing `geocode_address()` onto the owner row's `home_lat` / `home_lng` / `home_address`. Until he changes it, it stays Gilbert, which is what `CALEB_HOME` and the seed already use. First job of the day always pays the drive from that pin. There is no west depot.

---

## 6. Drive-time cache

Keep `get_drive_time()` and `drive_time_cache`. Do not add a second cache. Key today (`backend/google_maps.py` `drive_time_cache_key`): coordinates rounded to 4 decimal places (~11 m) plus a calendar day, so a re-geocode of the same address hits, and a day's lookups from the portal map and the slot loop do not each call Google.

Two corrections while this code is open, both small:

1. The day component is `now_utc().date()` (`server.py` ~290). Flip it to the Phoenix date. Around 5:00 PM Phoenix the UTC date rolls and every pair misses for no reason. The value being cached is typical duration, not live traffic, so the day component exists to bound staleness the way the 2026-07-21 changelog describes, not to represent the trip's date.
2. Do not key on the appointment date either. A booking three weeks out and a booking tomorrow share a typical duration. That is the current design and it matches "no `departure_time`."

Fallback stays: Maps error → mock, availability and booking both go through `get_drive_time`, so they cannot disagree with each other inside one request. They can both be wrong together if Maps is down and the mock is short. That is the existing resilience choice (same as the Xero fallback). Failing closed on a Maps error would turn a Google outage into "no slots all day," which is worse for a one-person shop. Record it as a known risk, not a new mode.

Geocode itself is not cached. Public availability geocodes every keystroke-equivalent request. Leave that alone in this PR. Slot generation must not multiply it (one geocode per availability call, then cached drives).

`portal_day_map` keeps calling `get_drive_time` in a loop. The cache is why that is acceptable. No change to that loop beyond the day-bound fix.

---

## 7. UI

Flag off: the booking wizard, the two zone columns, and the cross-town feasibility stay as they are. The zone windows still exist. What does change on deploy, because it is already wrong, is the clock: Phoenix day bounds, Phoenix formatting, the +7 hour re-stamp of existing appointment instants, and the old algorithm emitting 8:00 AM Phoenix instead of 8:00 UTC (section 5). `expire_stale_offers()` from `list_jobs` ships too; the docstring already promises it. After that deploy a Phoenix browser and the SMS agree on 8:00 AM. They do not today.

Flag on:

**Public booking (`PublicBooking.jsx`) and portal booking (`PortalBook.jsx`).**

- Move calibration type up to sit with the vehicle, **before** the date. Duration depends on it. Changing the type clears the chosen slot and reloads times.
- `POST /api/public/availability` accepts `calibration_type`. If a caller omits it, default `static`, so older clients and the current tests keep working while every type is 45 minutes. Once durations differ, the wizard always sends the type.
- Remove the "West Valley / East Valley service area" sentence. In-metro copy is "Inside the Phoenix service area." Out of metro copy stays. The zone badge on this screen implies a window we are about to stop honoring.
- Slot buttons render whatever the server returned. No client-side filtering. Empty list uses the server `message` (`No times that day fit the drive from the jobs already booked.` when the day is otherwise valid).
- On `409`, show the sentence and reload that date's slots. Do not leave the confirmation step spinning on a dead time.
- `PortalBook` uses the shared Phoenix formatter.

**Dispatch board (`Dashboard.jsx`).**

- One route column for the bookable technician (Caleb), titled with his name, subtitle from `day_start`–`day_end` (not the hardcoded 8:00–2:00 / 2:30–7:00 strings). Jobs sorted by `scheduled_start`.
- Geographic zone stays a small badge on the card (orange / blue). It is no longer a column.
- `route_conflict` renders a distinct banner ("Can't make this from the previous job"). Existing at-risk styling stays for lateness.
- `schedule_override` shows on the card so a forced booking is visible the next morning.
- Drag-and-drop still reorders, but the payload is `{technician_id, date, ordered_job_ids}`, and the confirm text says customer times will be rewritten and they will **not** be texted.
- A "Book anyway" button opens the short override form (shop, address, date and time, type, customer, vehicle, required reason).
- `RouteMap.jsx` draws one polyline in route order. Pin color can still follow geographic zone.
- `TomorrowStrip.jsx` drops the "N West · M East" summary. Show the job count and the first/last times.

**Reschedule modal.**

- Calls `POST /api/jobs/{id}/availability`.
- Removes `slice(0, 12)`. A 15-minute grid has more than 12 legal times; hiding the afternoon would send him back to the bug.
- Checkbox "Book this time even if the drive doesn't fit," visible only here (owner), requires a reason, sends `force`.

**Settings.**

- Pricing rows gain duration minutes. Saving goes through the existing `PUT /api/settings/pricing` extended with those fields.
- The zone hour / slot / buffer / max-jobs form is replaced by one schedule form: day start, day end, buffer minutes, and the owner's home address. `PUT /api/settings/schedule` (owner). Geographic zone reference (`GET /api/reference/zones`) stays for badges and shop lists.
- Assist: rewrite the one system-prompt sentence that says the business runs a West morning and an East afternoon. Point `update_zone`'s schedule fields at the new schedule document, or drop those parameters and add a `update_schedule` tool that writes the same `PUT`. `reorder_jobs` parameters change from `zone` to `technician_id`. If we leave the old tool writing `app_settings.zones`, the copilot will edit fields the flag ignores and report success. That is a real footgun, so it is in scope, not a follow-up.

**Unchanged on purpose:** shop admin zone badges, scorecard zone badge, portal day-map anonymity and "drive minutes from your shop," field PWA job list (it is already one list; it picks up the Phoenix formatter and the corrected day query), contractor dispatch modal.

---

## 8. Edge cases

| Case | Behavior |
|---|---|
| First job of the day | Leave home at `day_start`. First offered start is `day_start + drive(home, job)`, rounded up. No previous-job term. |
| Last job of the day | `start + duration <= day_end`. No reserved drive home. |
| Gap in the middle | Offered when both the inbound and the outbound inequality hold. Cancellation of a middle job makes that gap appear on the next availability call. Other jobs do not slide. |
| Shop cancels | Takes the day lock, expires stale offers, sets `cancelled`. Recompute `sequence_order` and `drive_time_minutes` only for that job's `(technician_id, Phoenix day)` — not every technician. Promised starts stay. A cancel cannot create an overlap (it only removes a stop), but it still takes the lock so it doesn't interleave with a book that has already read the day. |
| Job running late | The departure cursor pushes every later gap out to `now + buffer` (or `actual_completion + buffer` when he already finished late). New slots in front of a broken chain disappear. Already-booked later jobs stay at their promised times and pick up `route_conflict`. No automatic SMS, no automatic move. Finishing early does not open slots. |
| Two shops, same gap | Day lock. One insert wins. The other gets 409 and a refreshed list. |
| Owner force | Writes the job, sets `schedule_override` and the reason, shows the conflict. Shops have no equivalent parameter. |
| Pending contractor offer | Defined in the route loader, not as a special case at insert time. The job blocks Caleb while the offer is pending. On accept it blocks only the contractor. On decline or expiry (which book, availability, reschedule, cancel, reorder, and the dashboard poll all run) it blocks Caleb again. Because he was blocked the whole time, the snap-back does not land on a job a shop booked underneath him. |
| Contractor `accepts_bookings` later flipped to true | Their already-assigned jobs are the route. New public slots use the assignment rule. No backfill of old jobs onto them. |
| Reschedule onto the job's own current time | Allowed. `ignore_job_id` is why. |
| Reschedule / book in the past, or off the 15-minute grid | Rejected, including for force. |
| Missing home on a bookable technician | Skip that technician, log it. If none remain, availability is empty and book returns 503 `Scheduling is not configured.` |
| Maps down | Mock drive times, same as today. Both the list and the recheck use them. |
| Same address twice (two cars at one shop) | Legal. Drive is a few minutes (mock minimum is 10). Buffer still applies between them. No special case. |
| Sunday, >21 days, out of metro | Unchanged rejections. |
| Override and the lock | Force still takes the lock so two forces cannot interleave with a normal book half-written. It does not skip the feasibility **check** internally; it skips the **rejection** and records the override. |

---

## 9. Tests

`backend/tests/test_scheduling.py`, pure, no server. Mirror `test_charging.py` / `test_google_maps.py`. Inject a dict-backed drive function so the examples above are exact.

- Empty day, Surprise: first slot 9:30 Phoenix given an 89-minute drive; 8:00 absent; last start 18:15 for a 45-minute job and a 19:00 end.
- Empty day, San Tan: first slot 8:45 given a 34-minute drive.
- San Tan at 8:45 blocks Surprise until 11:45 (117-minute drive, 45 duration, 15 buffer).
- Surprise at 9:30 blocks a morning San Tan; afternoon San Tan starts at 12:30.
- Longer duration blocks a gap the 45-minute type still fits (one synthetic 90 vs 45, not a guessed Tesla default).
- Buffer 0 vs 15 moves the boundary by exactly 15.
- Grid rounding: arrival at 9:29 → 9:30; arrival exactly on a grid mark stays; `latest` rounds down.
- `ignore_job_id` frees the moved job's gap and still respects its neighbors.
- Cancelled jobs are ignored. A non-cancelled job on the other side of town is not.
- Today + `on_site` past scheduled end pushes `earliest` off `now`, not off the scheduled ready time. A future day does not. A completed job with `actual_completion` after its scheduled end pushes the same way; an early `actual_completion` does not pull.
- Broken chain: San Tan 8:45 then an impossible Surprise at 10:00. A new slot after that Surprise is **not** offered at 10:45. The cursor arrives at Surprise at 11:45, so the following gap opens at 11:45 + 45 + 15 + drive, not at the scheduled 10:45 end.
- Pending offer: a job with `technician_id` set to the contractor and a pending offer still blocks the owner's grid. The same job with an accepted offer does not. A pending offer whose `expires_at` is past is treated as back on the owner (the handler test covers the expiry call, not the pure function).
- First job cannot start before `day_start + drive(home)`.
- Two technicians: the earlier start is offered; at a tied start the shorter `drive_in` wins; a technician with `accepts_bookings` false is invisible; a technician with no home is skipped.
- Phoenix day bounds: 18:00 Phoenix is inside that Phoenix date and outside the next one; 18:00 Phoenix is `01:00Z` the following UTC date (the bug the helper exists to kill).
- Route-conflict helper flags a pair the inequality rejects and stays quiet for the San Tan 8:45 / Surprise 11:45 pair.

Handler tests, added beside the existing booking tests, run only with the flag on (or by calling the handler functions with the flag patched). They need the same API server the current suite uses:

- `public_book` of a start not in the feasible set returns 409 and writes no job.
- Two concurrent books of one slot: one 200, one 409.
- `portal_book` hits the same rejection (it delegates to `public_book`).
- Reschedule without force rejects a cross-valley time; with force persists `schedule_override`.
- Public availability ignores a client-supplied `ignore_job_id` / `technician_id` if we accidentally leave them on the model. Assert the public schema does not have those fields.
- With the flag off, `test_public_booking_flow` and the zone assertions stay green.

Update, don't delete, `test_reorder_invalid_ids` and the successful reorder test so they post `technician_id`.

No new frontend test runner. The implementation PR verifies the wizard in a browser: type before time, a Surprise morning hidden while a San Tan morning exists, 409 returns the user to a fresh slot list, dispatch board is one route, Settings saves a duration and a buffer and the next availability call moves.

---

## 10. Rollout

1. Implementation PR, flag default `false`. Includes `scheduling.py`, the handler changes, the migration, Settings, both wizards, the dispatch board, Assist tool/prompt updates, tests, and `CHANGELOG.md` / `EMERGENT.md` notes. This plan's PR does not include that code. Phoenix day bounds and offer expiry on `list_jobs` ship in that PR even with the flag off (section 7). The unreachable-slot behavior itself stays off until step 4, which is deliberate: durations and hours are still open questions, and flipping them on in the same deploy as the migration is how a guessed 45-minute Tesla would start rejecting real bookings.
2. Migration runs on boot regardless of the flag. Take a backup first. Confirm job count is unchanged, every existing `scheduled_start` moved by exactly +7 hours and not by any other amount, a second boot does not move them again, owner `accepts_bookings` is true, contractor is false, durations are 45. Spot-check one job: the SMS wall clock and a Phoenix browser now show the same time.
3. Caleb sets real durations, buffer, day start/end, and confirms home (Gilbert unless he says otherwise). Those writes are live settings; the flag still decides whether slots use them.
4. Turn `SMART_SCHEDULING=true` in Emergent's env and restart the backend (`sudo supervisorctl restart backend`). Watch one real booking day: a same-side pair, a cross-valley pair, a cancel, and a forced reschedule.
5. Leave the flag. Removing it and the old branch of `compute_available_slots` is a cleanup PR after that day looks right, not part of the first implementation. The old zone hour fields stay in `app_settings` until that cleanup so we can turn the flag back off.

Rollback of the new feasibility is the flag back to `false` and a restart. Jobs booked under the new rules stay booked; the old algorithm will simply ignore cross-zone conflicts again until the flag is back on. The clock fix does not roll back with the flag. Reversing the +7 hours would be a deliberate second migration, not a flag flip, and it would make the SMS and the browser disagree again.

---

## 11. Risks and open questions for Caleb

These are the decisions the implementation should not guess past. Recommendations are what the plan uses if he says "go."

1. **How long is each calibration, really?** The plan starts every type at 45 minutes, which is today's slot, and puts the number in Settings. A dynamic calibration that includes a road loop may not be a fixed block. If he types five numbers before the flag flips, those are the numbers shops will feel. **Recommendation:** ship 45s, edit before turning the flag on.

2. **Is 15 minutes the right buffer, and is 8:00–7:00 the right day?** Zone settings show a 20-minute buffer that has never done anything, and two windows (8:00–2:00 and 2:30–7:00) that add up to 8:00–7:00 with a fake 30-minute hole. **Recommendation:** one window 8:00–7:00 Phoenix, buffer 15, both editable. He leaves home at 8:00; the first job starts after the drive, not at 8:00 on site.

3. **Does the day have to end back at home?** The plan does not reserve the drive home. A 6:15 PM start in Surprise can be legal if it finishes by 7:00, and he gets home after 8:00. **Recommendation:** keep that, unless he wants `day_end` to mean "van in the driveway."

4. **Hard cap on jobs per day?** The old cap is 7 per side, 14 theoretical, and it is part of why the zone model felt like two techs. **Recommendation:** no count cap. Quitting time plus drive time is the cap. Say if a number should stay (10 is the figure if he wants one).

5. **Pending dispatch.** While a contractor has 30 minutes to accept, the plan keeps that job on Caleb's route so a shop cannot take the gap underneath him. The alternative is to free him immediately and live with a conflict if the contractor declines. **Recommendation:** keep it on his route until they answer.

6. **Reorder rewrites promised times and does not text anyone.** That is already true. The new pack also inserts the buffer, so a reorder moves times further than it does today. **Recommendation:** keep the tool, add an explicit confirm, don't add SMS in this work. Say if reorder should stop moving times and only change the map order.

7. **Maps outage uses the mock drive,** which can be shorter or longer than the valley that morning. A slot offered during an outage can be tight in real traffic. This matches the rest of the app and avoids a total booking blackout. Traffic-aware ETAs (`departure_time`) stay deferred. **Recommendation:** accept that, revisit only if a real Maps key is on and a week of bookings shows the mock (or the typical duration) is the thing that bites.

8. **Existing impossible days are not auto-fixed.** After the flag flips he may see conflict banners on jobs the old windows allowed. Nobody is texted, nobody is moved. **Recommendation:** look at the next few booked days once, move what is real, leave the rest.

9. **The 7-hour re-stamp.** Existing appointment instants move by +7 hours in the database so that "8:00" keeps meaning 8:00 AM Phoenix once the UI stops rendering UTC. The time printed in old confirmation texts does not change. Arrival timestamps (when he tapped "I've arrived") are real UTC and are not shifted. **Recommendation:** do this once, in the startup migration, before any Phoenix formatting ships. If he would rather leave old rows alone and only fix new bookings, say so before implementation — splitting them means old jobs display at 1:00 AM forever.

10. **Second technician.** Nothing in the data makes the Goodyear contractor bookable. When there is a second person, they need their own home and `accepts_bookings: true`, and shops will be assigned across both routes with the earliest-start / shorter-drive rule. That person does not get a zone. If the real second technician is "west side only" by policy rather than by drive time, the model does not express that, and we should not pretend a longitude split is a substitute. **Recommendation:** build the general rule now, turn on the second row only when that person exists, and if they must be geographically limited, say so before then rather than reviving East/West windows.

---

## 12. Adversarial review

Read against the code paths in section 1, then attacked again after the first draft. The first draft treated "jobs where `technician_id` is Caleb" as the route. That is wrong the moment dispatch runs, and it is wrong again 30 minutes later because expiry never runs unless the offers list is opened. The worked examples were checked against the mock formula on the pinned coordinates (they hold). Reschedule was still going to leave `scheduled_end` on the zone's 45-minute slot. A follow-up pass added the departure cursor: the neighbor formula alone still lets a shop book behind a stop that is already impossible. What changed:

| Attack | What changed |
|---|---|
| Calibration type is chosen after the slot in both wizards, so a Tesla duration computed too late still shows a static-sized hole. | Type moves before the date. Book rechecks the submitted type. Changing type clears the slot. |
| Route = `technician_id` match. Dispatch points that field at the contractor immediately, so a pending offer frees Caleb and a decline stacks the job on top of whatever a shop booked in the gap. | Loader definition in section 3: owner's jobs **plus** jobs with a pending offer, regardless of `technician_id`. Accepted offers leave his route. |
| `expire_stale_offers` is not on the book path (and not on `list_jobs`, despite the docstring). A pending offer older than 30 minutes blocks him for the rest of the day, or doesn't, depending on which filter you code. | Expiry runs inside the day lock at the start of availability, book, reschedule, cancel, and reorder, and on `list_jobs`. Not behind the flag. |
| Reschedule writes `scheduled_end` from zone `slot_minutes`, so at-risk and the portal disagree with per-type duration. | Reschedule and reorder set `scheduled_end = start + snapshotted duration_minutes`. |
| Neighbor check on scheduled times offers a slot after a stop he cannot reach, as if that stop finished on time. | Departure cursor walks the chain and only moves ready-times later. `latest` stays on the next promised start. `route_conflict` uses the same walk. |
| Grid test on the UTC clock. Minute-of-hour matches because the offset is a whole 7 hours; the hour and the calendar date do not. | Spec says convert to Phoenix first. Called out so "minute % 15 happened to work" doesn't get copied onto the hour check. |
| Examples named "San Tan city center" without a coordinate, so a Google geocode of that phrase would not reproduce 34 minutes. | Pins are the mock dict values already in `server.py`. Tests inject 89 / 34 / 117. |
| Cancel recomputes every technician's sequence, and doesn't say it takes the lock. | One technician, one Phoenix day, inside the lock. |
| Cross-day reschedule deadlock if the lock call waits. | Non-blocking insert, dates acquired in ascending order, release the first if the second is held. |
| Flag off "no visible change" contradicted the day-bound fix, which today's zone algorithm also needs. | Day bounds, Phoenix formatting, and offer expiry are called out as shipping with the code. Slot feasibility stays behind the flag. |
| Phoenix `formatTime` on top of instants that were built with `combine(..., utc)` displays 8:00 AM as 1:00 AM, and the SMS `strftime`s the opposite clock. Fixing only the formatter, or only the stamp, makes one of those two lie. | Migration adds 7 hours to `scheduled_start` / `scheduled_end` once. Old and new writers both mean 8:00 AM Phoenix. SMS and the UI both format Phoenix. Not behind the flag. `actual_arrival` is a real UTC click and is not shifted. |
| `ignore_job_id` on the public availability route lets anyone hide a job or book through it. | Owner-only preview endpoint. Public model does not grow that field. |
| A per-technician lock taken after choosing the assignee still races two requests onto Caleb. | One lock per Phoenix day, assignee chosen inside it. Stale locks are stolen at 30s, not left to Mongo's TTL sweeper. |
| Vehicle insert before the feasibility check orphans vehicles on 409. | Check, then insert, inside the lock. |
| Pending dispatch already rewrites `technician_id`, so "block the current assignee" would free Caleb for the whole offer window and double-book him when the contractor declines. | Pending offer keeps blocking the owner. Called out as a question, default is the safe one. |
| Migration that "fixes" `scheduled_end` to a new duration moves the on-site window of jobs customers already have. | Backfill `duration_minutes` from the existing start/end delta. Do not resize the window to a new type duration. The separate +7 hour re-stamp preserves wall clock; it is not a resize. |
| Copying the unused 20-minute zone buffer forward would surprise him, because he asked for 15 and because 20 never did anything. | Default 15. Saved zone **hours** are still read as the initial day window so a real Settings edit is kept. |
| UTC midnight splits a Phoenix workday at 5:00 PM, and `formatTime(undefined)` plus SMS `strftime` show the UTC clock to anyone whose phone isn't doing him a favor. | One bounds helper on every day query this feature uses. Phoenix timezone on formatters and on SMS. Portal's private `fmt` is removed. |
| Assist `update_zone` would keep editing dead fields and report success. | In scope for the implementation PR, not a follow-up. |
| Reschedule UI's `slice(0, 12)` hides legal afternoon slots once the grid is 15 minutes. | Remove the slice. |
| "Earliest feasible technician" implemented as "first row in the collection" dumps west-side work on Caleb whenever he can physically arrive. | Tied instants go to the shorter inbound drive, then the lighter day, then a stable id. |
| Holding a slot reservation for the length of the wizard adds an expiry path this volume does not need. | No hold. Recheck plus lock. 409 refreshes the list. |
| Failing closed when Maps errors turns a Google blip into an empty calendar. | Keep the mock fallback. Named as a risk instead of a new mode. |
| Reorder already rewrites customer times without SMS; adding buffer makes it rewrite them more. | Confirm copy says so. Not silently "fixed" by texting people inside this project. |

Attacks considered and rejected:

- A routing solver or Routes API optimization. The decision is a linear gap check on one van. A solver is a new dependency and a worse explanation when a shop asks why a time disappeared.
- `departure_time` traffic. Already declined in `CHANGELOG.md`, and it would make the daily cache lie (the cached value would depend on when they asked).
- Auto-shifting the rest of the day after a cancel. Breaks promised times to fill a gap the next booking can fill anyway.
- Treating the seeded contractor as technician number two. He is an overflow dispatch target with a Goodyear home the slot code has never read. Turning him on is Caleb's later data change, not this migration.
