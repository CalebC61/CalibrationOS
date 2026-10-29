# Smart scheduling — design plan

Status: **plan only**. This document does not change runtime behavior. Implementation is a later PR. Caleb answered the open questions on 2026-10-27; those answers are the rules in section 2. Section 12 lists what is left, which is small.

The Calibration Crew is one technician (Caleb) covering the Phoenix Valley. Glass shops book through the public link (`/book/:token`) and the shop portal (`/portal/book`). The calendar is still the original two-window model: West Valley in the morning, East Valley in the afternoon, as if those were two separate routes. A shop on one side of town is only offered that side's window, and that window is computed without looking at jobs already booked on the other side. Preferred Auto Glass (and any shop whose vehicles sit on both sides of town) can be offered a Surprise arrival that Caleb cannot reach from a San Tan job, or the reverse.

Shops do not pick a minute. They pick an arrival window: **8:00–12:00, 10:00–2:00, or 1:00–5:00**. The app will only offer a window when the route can place an arrival inside it, and it will keep an exact planned ETA for Caleb's board. A customer is texted on a reorder only when that ETA leaves the window they booked.

## Scope

In:

- One feasibility function used by availability, booking, reschedule, and reorder.
- Three shop-facing arrival windows. An exact ETA underneath each one. A 20-minute planned duration per calibration type, a 15-minute buffer, and an owner-only "this one runs long" duration.
- Public arrivals offered from 8:00 AM to 5:00 PM Phoenix. Owner override can book later. No reserved drive home.
- Rank windows by how little drive they add. Prefer a technician's home side. Neither preference is a hard lock.
- Server-side recheck at commit time, under a short day lock.
- Phoenix dates on every day query this feature touches, and the one-time +7 hour re-stamp of existing appointment instants.
- UI on public booking, portal booking, the dispatch board, and Settings.

Out, on purpose:

- No new package. Time zones use stdlib `zoneinfo`. `tzdata` is already in `backend/requirements.txt`. Drive time stays on `get_drive_time()` / `backend/google_maps.py`. No OR-Tools, no Google Routes, no Maps JavaScript SDK, no `googlemaps` client, no `pendulum` / `pytz`.
- No traffic model. `CHANGELOG.md` (2026-07-21) already records that Distance Matrix `departure_time` is out of scope. The daily cache depends on that.
- No Google Calendar sync.
- No automatic reordering of the day's stop sequence. Insertion picks a gap. Drag is how the order changes. A solver that tries every permutation is the thing this plan refuses.
- No deletion of `zone`, no removal of contractor dispatch, no change to Stripe, Xero, Assist's safety model, or Module 9.
- No hard daily job cap.

`SMART_SCHEDULING` (env, default `false`) gates the window algorithm. The clock fix (section 6) is not behind the flag. Defaults already match his answers, so turning the flag on does not wait on another round of numbers. He can still edit durations and windows in Settings first.

---

## 1. Current code audit

Everything below lives in `backend/server.py` unless noted. There is no scheduling module.

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

`detect_zone()` (~234) is `west` if longitude `< -112.0`, otherwise `east`. The east record's `lng_min: -111.8` is never read. Central Phoenix is east. Zone comes from the **job address**, not the shop (`public_availability` ~842, `create_shop` ~706). One shop can already book both sides. The bug is that each side has its own clock.

`memory/PRD.md` states the original spec: West 8:00–14:00, East 14:30–19:00, 45-minute slots, 20-minute buffer, max 7 per zone, Monday–Saturday. The code blocks Sunday only (`weekday() == 6`). Saturday stays open.

`buffer_minutes` is editable in Settings and via Assist's `update_zone` tool. **`compute_available_slots`, `public_book`, and `reorder_jobs` never read it.**

`slot_minutes` (45) is the only duration. `STANDARD_PRICING` (~496) has `label` and `price` only.

`load_settings()` (~525) overlays `start`, `end`, `max_jobs`, `slot_minutes`, `buffer_minutes` from `app_settings` `_id: "zones"`. Those saved hours are **not** the new workday. He has since set 8:00–5:00 for offers. Do not import the east zone's 19:00 as the end of the day.

### What availability does today

`POST /api/public/availability` (~832) geocodes, rejects anything outside the metro box (`backend/google_maps.py` `METRO_*`), rejects Sunday / a UTC-yesterday / more than 21 UTC-days out, then calls `compute_available_slots(zone, day, lat, lng)` (~772).

That function:

1. Loads non-cancelled jobs **in that zone only** whose `scheduled_start` falls in `[UTC midnight, next UTC midnight)`.
2. Returns nothing at `max_jobs` (7).
3. Anchors at the last job's `scheduled_end`, or at zone start on the `CALEB_HOME` constant.
4. Adds one drive time (`get_drive_time`).
5. Rounds up to 15 minutes, then walks by `slot_minutes` (45) until zone end. It does not offer gaps in front of the last job, and it does not look at the other zone.

The shop UI turns those instants into buttons (`PublicBooking.jsx`, `PortalBook.jsx`). Caleb's actual offer to shops is the three windows above. The app never stored a window. The confirmation SMS prints the exact timestamp.

`public_book` (~859) does **not** call `compute_available_slots`. It trusts the client's `scheduled_start`, sets `scheduled_end = start + zone.slot_minutes`, assigns the owner, and sets `sequence_order` to a count. No overlap check, no lock, no "can he reach the next job" test.

`POST /api/portal/book` (~1949) copies the shop token onto the body and calls `public_book`. One writer covers both. Stop trusting the client's instant. The shop will send a window id. The server picks the ETA.

### Other writers

| Path | Today | Change |
|---|---|---|
| `POST /api/jobs/{id}/reschedule` (~1153) | New start. End = zone `slot_minutes`. No drive check. SMS always. | Same pack as booking. Text only when the promise changes (section 5). |
| `POST /api/jobs/reorder` (~1578) | `{zone, date, ordered_job_ids}`. Repacks that zone from `CALEB_HOME`. Rewrites starts. Does not text. | One technician. Pack inside each job's window. Text only the jobs whose new ETA leaves the window. |
| `annotate_at_risk` (~978) | Late start or past `scheduled_end`. | Keep it. Separate `route_conflict`. Do not overload "at risk". |
| `GET /api/jobs`, dashboard summary, `portal_day_map` | UTC-midnight day window. | Phoenix day helper. |
| `portal_day_map` (~1912) | Other shops are anonymous pins, drive time from the viewing shop. | Keep the privacy behavior. |
| Dispatch (~1487–1568) | Sets `technician_id` to the contractor immediately. | A pending offer still blocks Caleb. He confirmed this. Offers are rare. The rule stays. |
| `expire_stale_offers()` (~1467) | Docstring says list-offers and list-jobs. The only caller is `GET /api/contractor-offers` (~1528). | Availability, book, reschedule, cancel, reorder, and `list_jobs` must run it, inside the day lock for anything that also writes. |
| Seed (~2098) | Owner home Gilbert, `home_zone: "east"`. Contractor home Goodyear, `home_zone: "west"`, not bookable. | Slot math reads the technician home, not `CALEB_HOME`. `home_zone` becomes the soft side preference. The contractor stays `accepts_bookings: false`. |

`get_drive_time()` (~281) uses Distance Matrix `duration` when `GOOGLE_MAPS_API_KEY` is set, else `mock_distance_matrix` (`max(10, int(miles * 2.2 + 5))`). Cache in `drive_time_cache`. On Maps errors, fall back to the mock.

Frontend:

- `PublicBooking.jsx` / `PortalBook.jsx` — address, then date and exact slots, then vehicle, then calibration type. Type is chosen **after** the time. Portal has its own `fmt()` in the browser's local zone.
- `frontend/src/lib/api.js` `formatTime` / `todayStr` — no `timeZone`.
- `Dashboard.jsx` — two panels, hardcoded "8:00 AM – 2:00 PM" and "2:30 PM – 7:00 PM". Drag calls `/jobs/reorder` with a zone.
- `RescheduleCancelModal.jsx` — `POST /public/availability`, then `slots.slice(0, 12)`.
- `Settings.jsx` — per-zone hours, max jobs, slot, buffer. Contractor home is editable. Caleb's home is not. The buffer does nothing.
- Assist (`backend/assist/agent.py` ~72, `tools.py` `reorder_jobs` / `update_zone`) still describes a West morning and an East afternoon.

Tests that assert `zone == "east"|"west"` stay valid. `test_iteration3.py` reorder posts `zone: "east"` and must send `technician_id` when the flag is on. Availability tests that read `slots[0].start` cover the flag-off path. The flag-on path has its own tests (section 10) because the payload becomes windows.

---

## 2. Decisions from Caleb

These replace the old open questions. Implementation should not re-litigate them.

| # | Decision |
|---|---|
| Duration | Planned length is **20 minutes for every calibration type**, editable per type. A smooth job is 10–15. A struggle is 30–45. 60 happens and is rare. The 15-minute buffer is what absorbs a normal overrun past 20. An owner-only difficult flag uses a longer per-type duration, default **45**. Shops cannot set it. |
| Workday | New public arrivals are offered **8:00 AM–5:00 PM Phoenix**. He often works later. Owner override can place an arrival after 5:00. A 7:00 PM Florence is allowed by the override and is the kind of thing he almost never wants. The form shows the drive so that case looks expensive. There is no Florence geofence. |
| End of day | The day ends when the last job is done. **Do not reserve the drive home.** A 4:45 PM arrival that finishes at 5:05 is legal. Public offers stop at a 5:00 PM arrival, not a 5:00 PM finish. |
| Cap and clustering | **No job-count cap.** Time is the limit. Fifteen east-side jobs in a day is a real day. Bouncing east/west is not. Rank windows by added drive, and break near-ties toward the same side of town. Still offer a cross-valley window when it is the one that fits. |
| Contractor offer | Rare. While the 30-minute accept window is open, the job **stays on Caleb's route**. |
| What shops pick | The three windows, not a minute. Offer a window only if some ETA inside it is reachable. Store that ETA. On drag or on the automatic pack, **text only if the new ETA falls outside the booked window.** |
| Clock | Do the one-time **+7 hour** re-stamp of existing `scheduled_start` / `scheduled_end`. |
| Second tech | West-side based, takes most west jobs. Caleb covers east. `home_zone` is a **soft** preference: use their side when they can fit the window, cross-assign when they cannot. |

Why 20 and not 15 or 45:

- 45 is today's slot and it is the struggle case. Planning every job at 45 would hide windows on ordinary days and would make a clustered east day look full long before it is.
- 10–15 is a smooth job. Planning at 10 stacks the next customer into the variance, so one ordinary struggle blows the following window.
- 20 sits just above a smooth job. Buffer is 15. Together they cover a job that runs ~30 minutes without moving the next ETA. A known hard one (the 30–45 band, and the rare hour) is the difficult flag, set by Caleb when he knows, defaulting at 45 because that is the top of the band he named. 60 is not a default. It shows up as running late and, if he marked it difficult and it still ran long, as a route conflict. He can type a different pair of numbers per type in Settings before the flag goes on. Tesla does not get a secret higher default.

Why the buffer stays 15: he asked for about 15, and the 20 in zone settings has never been applied. 20 minutes of work plus 15 of pad is the plan. It is not a second duration.

What "15 east jobs" means under these numbers. Public arrivals have to land by 5:00 PM. Leave Gilbert at 8:00, first east stop ~20 minutes out, then each extra stop costs about 20 + 15 + a short drive. At a 10-minute drive that is 45 minutes per extra stop, and the span from ~8:20 to 5:00 holds on the order of **12 arrivals**, not 15. A 15th clustered arrival lands at about **6:50 PM** (first ETA 8:20, then 14 gaps of 45 minutes). That matches "he often works late" and "override can book past 5." It is not a hidden cap. The 13th public window simply is not offered once no ETA inside 8:00–5:00 still fits. Override is how the long day continues. If a real week shows clustered drives much shorter than 10 minutes, more than 12 will fit before 5 without any code change, because the cap is the clock plus the drive, not a constant.

---

## 3. Data model and migration

MongoDB. Additive fields. `zone` stays, as geography only.

### Schedule

`app_settings` `_id: "schedule"`:

| Field | Default | Meaning |
|---|---|---|
| `timezone` | `America/Phoenix` | No DST. UTC−7. |
| `day_start` | `"08:00"` | He leaves home. First ETA is after the drive, not at 8:00 on site. |
| `offer_end` | `"17:00"` | Latest **arrival** a shop can be offered. Not a finish-by time. Not the old east-zone 19:00. |
| `buffer_minutes` | `15` | Between "work is done" and "wheels are rolling." Not applied to the drive from home. |
| `grid_minutes` | `15` | ETA rounding only. Shops never see the grid. |
| `windows` | the three below | Shop-facing choices. Editable later. A booked job snapshots the bounds it was promised. |
| `horizon_days` | `21` | Unchanged. |
| `closed_weekdays` | `[6]` | Sunday. |

```
{ "id": "morning",   "start": "08:00", "end": "12:00", "label": "8:00 AM – 12:00 PM" }
{ "id": "midday",    "start": "10:00", "end": "14:00", "label": "10:00 AM – 2:00 PM" }
{ "id": "afternoon", "start": "13:00", "end": "17:00", "label": "1:00 PM – 5:00 PM" }
```

The windows overlap on purpose. 11:00 is inside the first two. 1:30 is inside the last two. A shop may be offered two or three of them. Overlap is not a double-book. Each job has one window and one ETA.

Window end is **inclusive** for the ETA. Arriving at 12:00 counts as the morning window. Arriving at 5:00 counts as the afternoon window.

### Durations

On the existing pricing document, beside `price` and `label`:

| Type | `duration_minutes` | `difficult_duration_minutes` |
|---|---|---|
| static, dynamic, dual, triple, tesla | 20 | 45 |

Settings shows both numbers on each row. `load_settings()` already overlays this document.

A job snapshots `duration_minutes` at book time (20, or 45 if the owner already marked it difficult). Later edits to the price table do not rewrite booked jobs. `scheduled_end = scheduled_start + duration_minutes`. The buffer is not inside `scheduled_end`. `annotate_at_risk` keeps using `scheduled_end` as the on-site end.

`difficult: true` is owner-only. The public and portal payloads ignore the field if a client sends it.

### Technicians

| Field | Owner row | Contractor row |
|---|---|---|
| `accepts_bookings` | `true` | `false` |
| `home_zone` | already `"east"` | already `"west"` |
| `work_start` / `work_end` | unset, so schedule defaults | unset |

`home_zone` is the soft side. It is not a wall. A second bookable tech is a row with `accepts_bookings: true`, a geocoded home, and `home_zone: "west"`. The seeded contractor does not become that row.

Slot math reads `home_lat` / `home_lng` on the technician. `CALEB_HOME` remains only the seed value.

### Jobs

Keep `zone`, `technician_id`, `scheduled_start` (the ETA), `scheduled_end`, coordinates, `sequence_order`, `drive_time_minutes`.

Add:

- `arrival_window_start`, `arrival_window_end` — UTC instants for the window bounds on that Phoenix day. Snapshot. Editing the schedule later does not change a booked window.
- `arrival_window_id` — `morning` / `midday` / `afternoon`, for display. The instants are the promise.
- `duration_minutes` — snapshot.
- `difficult` — bool, default false.
- `schedule_override`, `override_reason` — set when an owner forced an ETA the pack would not have offered. Typical case: an arrival after 5:00.

Jobs that already exist have no window. They stay **pinned** to their ETA (after the +7 hour re-stamp). The automatic pack will not slide them. They were confirmed as a clock time, not as a window. A drag that moves a pinned ETA texts the customer, because any new minute is outside the promise they were given. New bookings get windows.

`sequence_order` is the order of that technician's non-cancelled jobs on that Phoenix day. `drive_time_minutes` is the display value from the previous stop. Feasibility calls `get_drive_time` again.

### Day lock

`booking_locks`, `_id = "day:YYYY-MM-DD"`. One lock per Phoenix date, not per technician. The assignee is chosen inside the lock.

Non-blocking. A duplicate insert is an immediate `409`, not a wait. Steal the lock if `created_at` is older than 30 seconds. TTL index on `created_at` is only a backstop. Hold the lock for the rest of that one request, including cache-miss Maps calls. Do not hold it while the shop types the vehicle. Do not require a multi-document transaction.

### Migration

Startup, after `load_settings`, before traffic. Insert `app_settings` `_id: "schedule_migration"` version `1` first. If it exists, skip. A second boot must not add another 7 hours.

1. Upsert `schedule` with the defaults above if the document is missing. If it exists, do not overwrite hours, buffer, or windows he has saved. Do not copy zone-document hours into it.
2. For each pricing key missing `duration_minutes`, set 20. Missing `difficult_duration_minutes`, set 45.
3. Set `accepts_bookings` only when the field is absent (owner true, contractor false). Do not overwrite `home_zone`.
4. For each job missing `duration_minutes`: if start and end parse, use the rounded minute difference (a historical 45-minute slot stays 45). Otherwise 20. Do not resize a booked job down to 20.
5. Add 7 hours to existing `scheduled_start` and `scheduled_end` only. Do not touch `actual_arrival`, `actual_completion`, or `created_at`. Do not text. Do not call Maps. Do not invent windows on old jobs.
6. Recompute `sequence_order` per `(technician_id, Phoenix day)` from the new starts.

Index: `jobs` on `{technician_id: 1, scheduled_start: 1}`.

Old days can still be geographically impossible. Leave them. The board shows `route_conflict`. He moves them by hand if he cares. The migration does not reshuffle.

---

## 4. How a window is offered

New module `backend/scheduling.py`. Pure: stdlib plus a drive-time callable. No Motor, no `requests`, no FastAPI. Same split as `charging.py` and `google_maps.py`.

`server.py` owns routes, the lock, geocoding, and `get_drive_time`. Availability **simulates** a pack and does not write ETAs. Book, cancel, drag, and the difficult toggle are what persist ETAs. Opening the booking page must not move the board.

### Whose jobs are on the route

`technician_id` alone is wrong. Dispatch points it at the contractor immediately (`dispatch_job` ~1516), and expiry does not run unless someone opens the offers list.

Inside the day lock, after `expire_stale_offers()`:

1. Non-cancelled jobs for this technician on this Phoenix day.
2. If this technician is the owner, also jobs in `dispatched_to_contractor` with a **pending** offer, whatever `technician_id` says. Accepted, declined, and expired offers are not included. An accepted job sits on the contractor. They are not bookable, so it does not take public windows.
3. Drop `ignore_job_id` on the owner reschedule preview. That argument is not on `POST /api/public/availability`.
4. Sort by `(scheduled_start, id)` before a pack that is not a drag. Pending-offer rows use the job's ETA for that sort even though `technician_id` points at the contractor. Unsorted merge order would change which gap wins.

`POST /api/public/availability` and the owner preview call `expire_stale_offers()` before the pure pack. That can text him when a 30-minute offer actually dies, which is the expiry behavior that already exists. They do not write ETAs. Book, reschedule, cancel, reorder, override, and the difficult toggle call it again inside the day lock so a commit cannot race the revert.

`GET /api/jobs` runs the same expiry helper. Not behind the flag. The docstring already claims it.

### The pack

Order is an input. The pack does not permute it.

Pins, in order: home, then each job. No buffer on the leave-home leg.

Pinned means the pack will not change `scheduled_start`: `driving`, `on_site`, `complete`, a legacy job with no window, and an override whose ETA is after `offer_end`. A completed stop is pinned so we do not rewrite history. It is **not** pinned for the departure clock. If he finished late, the van is not free at `scheduled_end`.

```
cursor   = day_start at home          # leave-home instant, not an arrival
prev_pin = home
for job in order:
    earliest = round_up(cursor + drive(prev_pin → job), grid)   # Phoenix local
    if job is pinned:
        eta = job.scheduled_start
        if earliest > eta: route_conflict = true          # keep the stored ETA anyway
    else:
        eta = max(earliest, job.arrival_window_start)
        if eta > job.arrival_window_end: this order cannot honor the window
    if job.status == "complete" and actual_completion parses:
        leave = max(job.scheduled_end, actual_completion) + buffer_minutes
    else if today and job.status in (driving, on_site):
        leave = max(eta + duration_minutes, now) + buffer_minutes
    else if today and job.status == "booked" and now > eta:
        leave = max(eta + duration_minutes, now) + buffer_minutes
    else:
        leave = eta + duration_minutes + buffer_minutes
    cursor, prev_pin = leave, job.pin
```

`scheduled_end` on a completed job is the planned on-site end (`start + duration`), which the +7 hour migration did not resize. `max(scheduled_end, actual_completion)` is what stops a long job from offering the next window early. An early `actual_completion` does not pull `leave` forward of `scheduled_end`. The next booked job can still move earlier inside its own window, because its `earliest` is computed from this `leave` and the automatic pack takes the earliest in-window ETA. That slide does not text.

Public placement of a **new** job requires `eta <= offer_end`. Do not also require `eta >= day_start`. `day_start` is when he leaves home. The drive already pushes the first arrival later than 8:00. Finishing after `offer_end` is fine.

Future days ignore `now` and ignore `actual_completion`. A completed job on a future day should not exist. If it does, it is pinned to its ETA and leaves at `scheduled_end + buffer`.

A missing coordinate fails the day closed: no windows, and a log line. Do not offer a route we cannot measure.

### Insertion, which is the clustering

Drive cost depends on the gap, not on the minute inside the gap. For each gap (before the first job, between two, after the last):

```
added = drive(prev → new) + drive(new → next) − drive(prev → next)
```

When the gap is at the end of the day, `added = drive(prev or home → new)`.

Try the new job in that gap, with the window being tested as its promise, and run the pack. The gap is legal when the pack places the new ETA inside the window and inside 8:00–5:00, and places every other non-pinned job inside its own window. Pinned jobs keep their ETA. A gap that only works by pushing someone else out of their window is not legal. That is what "only offer a window if it can be reached given the route" means.

The window's score is the legal gap with the smallest `added`. If two legal gaps are within 10 minutes of each other, prefer the one whose neighboring job is on the same side of town as the new job (`detect_zone`). Home counts as the technician's `home_zone` for that comparison. A same-side gap that costs 40 extra minutes does not beat a cross-town gap. The 10-minute band is the whole soft preference. There is no zone wall.

ETA inside the winning gap is the earliest grid instant the pack produced, not a search over minutes. Earliest keeps the rest of the window usable for the next shop.

### What the shop sees

For each of the three windows, compute the score above. Drop windows with no legal gap. Return the rest sorted by score, then by window start. The first is `recommended: true`.

Do not return the ETA on the public or portal payload. The promise is the window. The owner preview and the dispatch board include the ETA.

An empty day in Surprise (mock drive 89 from Gilbert, so the first possible ETA is 9:30) still offers **all three** windows, because 9:30, 10:00, and 1:00 are all reachable when nothing else is booked. Recommended is the morning window, on the tie. He is not offered 8:00 as a minute. He is offered "8:00–12:00," and the board's ETA is 9:30.

### Worked examples

Pins and mock minutes, injected in tests so a live geocode cannot fail them. Gilbert home `(33.3528, -111.7890)`, Surprise `(33.6292, -112.3679)`, San Tan `(33.1962, -111.6463)`, Goodyear `(33.4353, -112.3576)`. Mock formula as in `server.py`: Gilbert→Surprise 89, Gilbert→San Tan 34, San Tan↔Surprise 117, Goodyear→Surprise 34. Duration 20, buffer 15, grid 15. One technician. Chain not already broken.

**Empty day, San Tan.** Leave 8:00, arrive 8:34, ETA 8:45. All three windows fit. Morning is recommended. Internal ETA if they pick morning: 8:45. If they pick 1:00–5:00: 1:00.

**Empty day, Surprise.** ETA 9:30. Morning still fits, because 9:30 is inside 8:00–12:00. So does midday, so does afternoon. 8:00 itself is not an ETA.

**San Tan already booked, window 8:00–12:00, ETA 8:45.** Leave = 8:45+20+15 = 9:20. Surprise drive 117. Arrive 11:17, ETA **11:30**. Morning still fits (11:30 ≤ 12:00). Midday and afternoon fit too. Added drive is the same gap, so morning is recommended. This is a bounce, and it is still offered. There is no same-side gap to prefer. Hiding it would be the hard lock he rejected. The shop can pick 1:00–5:00 instead and leave the late morning alone. The board ETA will not be 8:00.

**Surprise already booked, window 8:00–12:00, ETA 9:30. Shop wants San Tan.** Before the Surprise job: the earliest San Tan ETA is 8:45, so leave = 8:45+20+15 = 9:20, plus 117 minutes, is 11:17 at Surprise. That is after the stored 9:30 ETA, so the gap is illegal. After Surprise: leave 9:30+20+15 = 10:05, plus 117 = 12:02, ETA **12:15**. Morning ends at 12:00, so **8:00–12:00 is not offered**. Midday is (12:15 is inside 10:00–2:00). Afternoon is. Recommended is midday, the cheaper of the two only by the tie-break of earlier start (same gap). This is the old zone bug in window form: a San Tan "morning" is not bookable on top of a Surprise morning, even though the two addresses used to live on different calendars.

**Same shop, both sides.** Preferred's link has no side. The pin does. They can book San Tan in the morning (ETA 8:45) and Surprise in the midday window (ETA 11:30). They cannot book Surprise in a way that places the ETA at 8:00.

**Clustered east day.** Two San Tan-area stops, 10-minute drive. Second ETA = first + 20 + 15 + 10 = first + 45, rounded up to the grid. Both can share 8:00–12:00. Added drive for the second is about 10 minutes, so that window ranks ahead of any window that inserts a west-side stop (added drive ~100). The west window is still returned if it fits. It is not first.

### Assignment when a second technician accepts bookings

```
for each window:
    candidates = bookable techs who have a legal gap in that window
    same_side  = those whose home_zone == the job's zone
    pool       = same_side if same_side else candidates
    if pool is empty: window is hidden
    else: offer it, assignee = the pool member with the smallest added drive,
          then fewer jobs that day, then technician id
```

A west job goes to the west-side tech whenever he can fit that window, even if Caleb could also fit it and could get there earlier. Caleb takes a west window only when the west-side tech has no legal gap. The reverse for an east job. A tech with no `home_zone` never counts as same-side. A tech with no home coordinates is skipped. If nobody bookable remains, availability is empty and book returns 503.

The shop payload has no technician name. `public_book` ignores a client-supplied technician id and runs this again inside the lock.

With only Caleb bookable, and his `home_zone` east, the pool is always just him. That is what ships.

### Reorder and the automatic pack

`POST /api/jobs/reorder` body is `{technician_id, date, ordered_job_ids}`. It takes the day lock after expiry.

The payload is the new order of **movable** jobs only: `booked`, with or without a window. It must be exactly that set. A missing booked job is a 400, not a silent drop. `complete`, `driving`, and `on_site` are anchors. So is a pending contractor offer. The server splices each anchor back into the timeline at its current ETA, then runs one pack over the merged sequence. Anchors keep their ETA. The pack's leave-time rule still applies, so a completed job that ran long keeps the van busy until `actual_completion + buffer`. A drag cannot slide a booked job into the same minutes as that stop.

- Drag sets the order of the movable jobs. The pack then runs on the merged sequence.
- Book and cancel do **not** change order, except that a new job is inserted in the winning gap. Then the same pack runs, which may pull later ETAs earlier **inside their windows**.
- There is no "try all orders" action.

Notify rule, same for drag and for the automatic pack:

| New ETA vs the promise | Customer SMS |
|---|---|
| Inside the snapshotted window | None. |
| Outside the window | Text the new ETA, and say it is outside the window they booked. |
| Pinned legacy job, ETA unchanged | None. |
| Pinned legacy job, ETA moved | Text. The promise was that minute. |
| Already outside, and this commit moves it again | Text the new ETA. |
| ETA unchanged | None. |

Drag that would push someone outside their window returns the list and does not write, unless the body includes `confirm_outside_window: true`. The confirm copy names who will be texted. A drag that stays inside every window writes quietly and the copy says nobody will be texted.

The automatic pack never pushes a job outside its window and never moves a pinned job. If the earliest in-window ETA is impossible, the stored ETA stays and `route_conflict` is set. Caleb decides whether to drag and text. Running late is not itself a text, even when the only reachable arrival is now past the window. The stored promise is still the window until a drag or a confirmed write moves the ETA. An automatic "you're late" SMS is how a 20-minute overrun texts every later shop. He did not ask for that. The board shows the conflict. He texts by confirming a move.

Cancel still sends the cancellation SMS it sends today. That is not a reorder.

### Route conflict

Same pack. `route_conflict` when the arrival the drive implies is after the stored ETA (pinned or not), or when a windowed job's earliest feasible ETA is past its window end. One walk. Do not keep a second check that only looks at the previous scheduled start. This is not `is_at_risk`.

---

## 5. Commit path

### Shop booking

`public_book` and, through it, `portal_book`:

1. Resolve the shop, geocode, reject out of metro. The client does not send coordinates. Ignore `difficult` and `technician_id` on this payload.
2. Require `arrival_window_id` to be one of the configured windows. Reject Sunday, a past Phoenix date, and anything past the horizon. There is no client `scheduled_start` on this path.
3. Take the day lock. If it is held, `409` with `That window just filled. Refresh and pick another.` Log `lock_held`.
4. Expire offers, load the route, run section 4 for the submitted type's **20-minute** duration (not the difficult one). If that window is no longer legal, `409`, log `infeasible`, write nothing.
5. Insert the vehicle, then the job, at the pack's ETA. Snapshot the window bounds, `duration_minutes` 20, `scheduled_end`, geographic `zone`, `sequence_order`, `drive_time_minutes`. Persist ETA slides for other windowed jobs that stayed inside their windows.
6. Release the lock in `finally`. SMS the **window**, in Phoenix: "between 8:00 AM and 12:00 PM," not the ETA. Owner alert can include the ETA. He is the one who drives to a minute.

Two shops can both book the morning window if both packs fit. The lock is what makes the second pack see the first job. A 409 means the window no longer fits, not that a single minute was taken.

### Reschedule

Owner `POST /api/jobs/{id}/reschedule`. Lock the source and destination Phoenix dates in ascending date order, non-blocking. If the second lock is held, release the first and `409`.

- A changed `arrival_window_id` is a new promise. Run the pack with this job excluded, then inserted. Text the new window bounds. Set `scheduled_end` from the snapshotted duration, not from zone `slot_minutes`.
- The same window id uses the notify table in section 4. An ETA that stays inside does not text. Do not treat "he pressed reschedule" as a reason to text.
- `force: true` plus `scheduled_start` plus a required `override_reason` writes that ETA even after 5:00 PM, sets `schedule_override`, and texts only when the ETA is outside the current window (an after-5 ETA always is, unless they had no window and the minute did not change). Still refuses a past instant and an out-of-metro address. Does not move the other jobs out of their windows. The same pack walk then sets `route_conflict` on **every** job whose drive arrival is after its stored ETA, including neighbors, not only on the forced job. Otherwise the board would keep showing in-window times he can no longer make.
- Uses stored `job_lat` / `job_lng`.

`POST /api/jobs/{id}/availability` is owner-only, returns windows plus the ETA the pack would use, this job excluded. The reschedule modal calls that, not the public endpoint.

### Owner override for a new job

`POST /api/jobs/override-book` (owner). Shop, address, vehicle, type, required reason, and an exact `scheduled_start` that may be after 5:00 PM. Same lock and expiry. If some bookable tech can legally make that minute inside a normal window, assign them by the section 4 rule and do not set the override flag. If the minute is after `offer_end`, or nobody's pack can make it, assign the owner, set `schedule_override`, and text the shop the exact ETA. The response says who was assigned. One short form, not a second wizard. The drive from the previous stop is on the form so a 7:00 PM Florence is an obvious "are you sure" and not a special case in code.

### Difficult toggle

`POST /api/jobs/{id}/difficult` owner-only, `{difficult: bool}`. Swaps the snapshot to the type's normal or difficult duration, reruns the pack in the current order. If his own ETA would leave the window, do not write unless `confirm_outside_window` is set, and then text him the same way a drag does. Other customers are not pushed out of their windows. Shops have no control for this.

---

## 6. Phoenix time

`ZoneInfo("America/Phoenix")`. No new dependency.

Store instants as timezone-aware UTC ISO strings. Do not store naive local times.

### Wall clock was stored as UTC

Slots, book, and reorder build "8:00" with `datetime.combine(..., tzinfo=timezone.utc)`. The SMS `strftime`s that value, so the text says 8:00 AM. A Phoenix browser running `formatTime` with no time zone shows 1:00 AM. He confirmed the one-time correction.

These ship together, not behind `SMART_SCHEDULING`:

- Migration adds 7 hours to existing `scheduled_start` / `scheduled_end` once. `08:00Z` becomes `15:00Z`, which is 8:00 AM Phoenix. A stored `19:00Z` becomes 7:00 PM Phoenix (`02:00Z` the next UTC date).
- While the flag is off, the old zone algorithm still ignores the other side of town and still ignores the buffer. It stops using `timezone.utc` for `combine`, so "08:00" means 8:00 AM Phoenix. Otherwise the flag-off calendar shows 1:00 AM the moment formatting is fixed.
- SMS, alerts, `formatTime`, `formatDate`, and `todayStr` use `America/Phoenix`. `todayStr` is `Intl.DateTimeFormat("en-CA", { timeZone: "America/Phoenix", ... })`. `PortalBook.jsx` deletes its local `fmt`.

`actual_arrival` is a real UTC click. It is not shifted.

```
phoenix_day_bounds(day) -> [that Phoenix midnight UTC, next Phoenix midnight UTC)
```

Today's `datetime.combine(day, time(0, 0), tzinfo=timezone.utc)` is 5:00 PM the previous Phoenix evening through 5:00 PM on the named day. The bug is the UTC date rolling at midnight UTC, which is 5:00 PM Phoenix, so `now_utc().date()` becomes "tomorrow" while Phoenix is still on today. Past-date checks use the Phoenix calendar date of `now`, via `phoenix_day_bounds`. `offer_end` does **not** mean the calendar day is over at 5:00 PM. Same-day owner override after 5:00 PM stays legal. Shop windows are what stop at a 5:00 PM arrival.

Replace the UTC-midnight bound in the loader, `public_book`'s day scan, `list_jobs`, `dashboard_summary`, `reorder_jobs`, `portal_day_map`, and the Sunday / past / horizon checks. JWT expiry stays UTC.

Grid checks convert to Phoenix first. The offset is a whole 7 hours, so the minute-of-hour matches UTC, but the hour does not. `hour >= 8` on a UTC datetime accepts 1:00 AM Phoenix.

Home base is the technician document. Settings gets his home address, geocoded with the existing `geocode_address()` onto `home_lat` / `home_lng` / `home_address`. Until he changes it, it stays Gilbert. There is no west depot until a west-side tech exists.

---

## 7. Drive-time cache

Keep `get_drive_time()` and `drive_time_cache`. Do not add a second cache and do not send `departure_time`.

1. The cache key's day (`server.py` ~290) is `now_utc().date()`. Use the Phoenix date of the **lookup** (`now`), not the UTC date and not the appointment date. Around 5:00 PM Phoenix the UTC date rolls and every pair misses. Keying on the appointment date would pretend a drive three weeks out is a different typical duration. It is not. `departure_time` stays out.
2. That is the whole cache change.

Availability and booking both call `get_drive_time`, so a Maps failure falls back to the mock for both. They can be wrong together. They cannot disagree. Failing closed would turn a Google blip into an empty day. That stays a known risk.

One geocode per availability call. The pack then uses cached drives. `portal_day_map` keeps its loop. The cache is why that loop is acceptable.

A day with `n` jobs needs the drives along the chain plus, per window, the drives for each gap's `added`. Three windows, `n` under 20. All through the cache.

---

## 8. UI

Flag off: the two zone columns and the exact-slot wizard stay. What still changes, because it is already wrong: Phoenix day bounds, Phoenix formatting, the +7 hour re-stamp, the old algorithm emitting 8:00 AM Phoenix instead of 8:00 UTC, and `expire_stale_offers()` from `list_jobs`.

Flag on:

**Public booking and portal booking.**

- Calibration type moves up with the vehicle, before the date. Duration depends on it. Changing type reloads windows. No difficult checkbox.
- The time step is up to three window buttons, recommended first. Copy is the window label. No minute grid. No zone badge. In-metro copy is "Inside the Phoenix service area."
- Empty list uses the server message: `No arrival window that day fits the drive from the jobs already booked.`
- On 409, show the sentence and reload the windows.
- Confirmation shows the window, not the ETA.
- Portal uses the shared Phoenix formatter.

**Dispatch board.**

- One column for Caleb while he is the only bookable tech. Subtitle `8:00 AM – 5:00 PM` from the schedule, not the hardcoded zone hours. A second bookable tech gets a second column later. That is the same component, one per tech. It is not the return of East/West calendars.
- Each card shows the window and the ETA. Geographic zone stays a small badge.
- `route_conflict` and `schedule_override` are separate from the late badge.
- Drag calls reorder with `technician_id`. If the response says someone would leave their window, the confirm names them and says they will be texted. If not, the copy says nobody will be texted.
- "Book anyway" opens the short override form (shop, address, exact time, type, customer, vehicle, reason) and shows drive minutes from the previous stop.
- A "Runs long" control on the card calls the difficult toggle.
- `RouteMap.jsx` draws one polyline per technician, in ETA order. Pin color can still follow zone.
- `TomorrowStrip.jsx` drops "N West · M East."

**Reschedule modal.**

- Owner availability, windows not a 12-slot slice.
- Picking a new window texts the shop the new window.
- Force is an exact time, reason required, and it is how he books past 5:00.

**Settings.**

- Per type: normal minutes and difficult minutes.
- Schedule form: day start, offer end, buffer, the three windows, his home address, his home side (east).
- `PUT /api/settings/schedule` and the existing pricing PUT, extended. `GET /api/reference/zones` stays for badges.
- Assist: replace the West-morning / East-afternoon sentence with the windows, the 8:00–5:00 offer range, and the soft home side. `reorder_jobs` takes `technician_id`. Retire the zone hour fields on `update_zone` so the copilot cannot save a buffer into a document the flag ignores.

**Unchanged:** shop-admin zone badges, the scorecard badge, portal day-map anonymity, the field PWA list (it picks up the formatter, the day query, and it shows window plus ETA), contractor dispatch.

---

## 9. Edge cases

| Case | Behavior |
|---|---|
| First job of the day | Leave home at 8:00. ETA is `8:00 + drive`, rounded up. A window is offered if that ETA, or a later one, sits inside it. No buffer on the drive from home. |
| Last public arrival | ETA ≤ 5:00 PM. The job may finish after 5:00. No drive home is reserved. |
| Arrival after 5:00 | Shop UI cannot. Owner override can. |
| Several jobs, one window | Legal. The pack sequences them. The window is not a single slot. |
| Overlapping windows | All that fit are shown. Recommended is the one with the least added drive. |
| Cross-valley | Offered when the pack fits. Ranked behind a same-side gap within 10 minutes. Never the only reason to hide a window. |
| Cancel | Lock, expire offers, mark cancelled. Repack the remaining order inside windows. No extra text for a slide that stays inside. The cancellation SMS still goes out. Pinned jobs do not slide. |
| Running late | Leave-time uses `now` or `actual_completion`, so a long completed job does not free the van early. A later booked ETA may slide inside its window with no text. If no in-window ETA is reachable, the stored ETA stays, `route_conflict` shows, and nobody is texted until he confirms a move. |
| Two shops, one window | Both can succeed when both packs fit. Otherwise the second gets 409. |
| Pending contractor offer | Blocks Caleb until accept, decline, or expiry. Confirmed. |
| Difficult flag | Owner only. 45 minutes unless he edited that type. Confirm + text if his ETA leaves the window. |
| Legacy job, no window | Pinned. Drag that moves it texts them. |
| Reschedule to the same window | Allowed. Pack runs. Text only if the ETA leaves the window. Changing the window id always texts. |
| Past, or off the grid, on an override minute | Rejected. |
| Missing home | Skip that tech. If none remain, 503 `Scheduling is not configured.` |
| Maps down | Mock drives, same function for the list and the recheck. |
| Two cars, one address | Legal. Mock drive minimum is 10 minutes. Buffer still applies. |
| Sunday, >21 days, out of metro | Unchanged rejections. |

---

## 10. Tests

`backend/tests/test_scheduling.py`, pure, injected drives. No server, no Maps.

- Empty Surprise day: first ETA 9:30. All three windows offered. Morning recommended. 8:00 is not the ETA.
- Empty San Tan day: first ETA 8:45. All three windows.
- San Tan at 8:45, then Surprise: Surprise ETA 11:30. Morning still offered.
- Surprise at 9:30, then San Tan: morning window absent, midday ETA 12:15, afternoon offered.
- Two east stops 10 minutes apart both fit in the morning window. A west alternative has a much higher `added` and is not recommended. It is still present if it fits.
- Gaps within 10 minutes: the same-zone neighbor wins. A same-zone gap 40 minutes worse does not.
- A window that fits only by pushing another job past its window end is not offered.
- Pinned legacy job: pack does not move it. A following windowed job still packs around it.
- Difficult duration 45 blocks a midday insert that 20 allows.
- Buffer 15 vs 0 moves the boundary by 15. No buffer added on the home leg.
- `ignore_job_id` frees the moved job.
- Today, `on_site` past the planned end, pushes the next ETA off `now`. The push that stays inside the next window is allowed. The push that cannot land inside the window does not change the stored ETA and sets `route_conflict`.
- A `complete` job whose `actual_completion` is after `scheduled_end` does not free the van at `scheduled_end`. The next ETA uses `actual_completion + buffer`. An earlier `actual_completion` does not pull departure before `scheduled_end`.
- Reorder: a payload that drops a booked job is a 400. `complete`, `driving`, `on_site`, and a pending offer stay at their ETA, and a booked job cannot be packed onto those minutes.
- Pending offer blocks the owner. An accepted offer does not. The pure function takes the job list the loader already built. Expiry itself is a handler test.
- Second tech, `home_zone` west: a Surprise window he can fit is assigned to him even when Caleb's ETA would be earlier. The same window is assigned to Caleb when the west tech has no legal gap. A tech with `accepts_bookings` false is invisible.
- Phoenix bounds: 6:00 PM Phoenix is inside that Phoenix date and is `01:00Z` the next UTC date.
- Notify helper: inside the window → no text; outside → text; pinned minute changed → text; pinned minute unchanged → no text.

Handler tests, flag on:

- `public_book` with a window id that the pack rejects returns 409 and writes no job. A client `difficult: true` does not change the duration.
- Two concurrent books of a window that can hold only one of them: one 200, one 409. Two that both fit: two 200s, two ETAs, no text about the other.
- Portal book hits the same path.
- Drag that stays inside windows writes and reports nobody to text. Drag that exits a window does not write without `confirm_outside_window`, and with it, only the exited jobs are the SMS targets.
- Override at 7:00 PM persists `schedule_override` and is owner-only.
- Public availability has no `ignore_job_id` field.
- Flag off: existing `test_public_booking_flow` still sees `slots`.

No new frontend test runner. The implementation PR checks in a browser: windows instead of minutes, type before the date, the San Tan morning window hidden when a Surprise morning is already booked (the example above), recommended order, 409 reloads the windows, the board shows ETA plus window, a drag inside the window does not pretend to text anyone.

---

## 11. Rollout

1. Implementation PR, flag default `false`. This plan's PR does not contain that code. Clock fix and offer expiry on `list_jobs` ship even with the flag off.
2. Backup, then boot. Confirm the migration document exists, a second boot does not move times again, each existing appointment instant moved by exactly +7 hours, old jobs did **not** gain a window and did **not** get their duration rewritten to 20, pricing durations are 20 / 45, owner `accepts_bookings` is true, contractor is false, `home_zone` values are unchanged. SMS wall clock and a Phoenix browser agree.
3. Optional: he edits a duration, the buffer, or a window label in Settings. The defaults are already his answers.
4. `SMART_SCHEDULING=true`, restart the backend. Watch one day: two east jobs in one morning window, a cross-valley window ranked behind them, a cancel that pulls an ETA forward without a text, a drag that exits a window and does text, an override after 5:00.
5. A later cleanup can delete the old slot branch. Not this implementation. Zone hour fields stay in `app_settings` until then so the flag can go back off.

Rollback of feasibility is the flag off and a restart. The clock fix does not roll back with the flag. Jobs booked under the new rules keep their windows.

---

## 12. What is still open

The eight questions he was asked are closed. What remains is not a blocker for writing the implementation PR. It is worth a look after the first real week.

- **Maps fallback.** An outage uses the mock drive, which can be short. The window and the recheck use the same number, so they match each other and can both be tight. Traffic-aware ETAs stay deferred.
- **Old impossible days** show a conflict banner after the flag flips. Nobody is texted and nobody is moved by the migration.
- **Arrivals before 5:00 vs a 15-job east day.** The arithmetic in section 2 says about a dozen clustered arrivals fit before 5:00, and the rest of a 15-job day runs later via override. If a real week shows he is turning shops away before the day feels full, the fix is a smaller buffer or a shorter planned duration, both of which are Settings values, not a new design.

---

## 13. Adversarial review

### First draft

Checked against `server.py` and the booking wizards. The holes that were real, and what the plan did:

| Attack | What changed |
|---|---|
| Type is chosen after the slot, so duration is applied too late. | Type moves before the date. |
| Route = `technician_id`. Dispatch repoints it immediately. | Loader includes pending offers on the owner's route. |
| `expire_stale_offers` does not run on book or `list_jobs`, despite the docstring. | Those paths call it. Expiry is inside the day lock for writes. |
| Reschedule leaves `scheduled_end` on the zone's 45-minute slot. | End is start + snapshotted duration. |
| Checking only the neighbor's scheduled start offers a time behind a stop he cannot reach. | The pack walks the chain. |
| Grid math on the UTC hour. | Convert to Phoenix first. |
| Examples that said "San Tan" without a coordinate. | Tests inject 89 / 34 / 117 on the mock pins in `server.py`. |
| Cross-day lock that waits can deadlock. | Non-blocking, dates in ascending order. |
| Phoenix formatting on top of UTC wall-clock instants shows 8:00 AM as 1:00 AM, and the SMS shows the other clock. | +7 hours once, and both clocks format Phoenix. Not behind the flag. |
| `ignore_job_id` on the public route. | Owner preview only. |
| Per-tech lock taken after choosing the assignee. | One lock per Phoenix day, assignee chosen inside it. |
| Vehicle insert before the feasibility check. | Check, then insert. |
| Copying the unused 20-minute zone buffer, or the east zone's 7:00 PM end. | Buffer 15. Offer end 5:00 PM. Do not import zone hours. |
| A routing solver, or `departure_time`. | Refused. Gap insertion is linear. The cache stays typical-duration. |
| Treating the seeded contractor as technician two. | He stays dispatch-only until a real west-side row is marked bookable. |

### After his answers

The exact-minute grid was the wrong product. Shops book windows. A second pass against that change:

| Attack | What the plan does |
|---|---|
| Treating a window as one slot, so a second morning job is "taken." | The pack sequences as many jobs as the drive allows inside one window. Two legal packs both get 200s. |
| Availability that writes the simulated pack. Opening the page would move the board. | Availability is read-only. Book, cancel, drag, and the difficult toggle persist ETAs. |
| Auto-pack that permutes order to "optimize." That is the solver this plan already refused, and it can pull a 1:00–5:00 job up to 8:30. | Order changes only by insertion gap or by drag. The pack is earliest-inside-the-window in that order. |
| Sliding a legacy exact-time job inside a guessed window and not texting. Their SMS promised a minute. | No window on old rows. They are pinned. Moving one texts. |
| Recommending the earliest window even when a same-side gap is slightly worse, or hiding a cross-valley window. | Score is added drive. A same-side gap wins only inside a 10-minute band. The other window stays on the list. |
| "Earliest feasible tech" sending west work to Caleb because he can leave at 8:00. | Same-side pool first. The west tech gets a west window he can fit, even if Caleb's ETA is earlier. Cross-assign only when that pool is empty. |
| Public `difficult: true` so a shop can shrink or stretch the day. | Field ignored on shop payloads. Owner toggle only. |
| Texting on every ETA slide, which contradicts him, or never texting a drag that lands at 6:30. | Text only on the way out of the window (or on any move of a pinned minute). Drag that exits requires `confirm_outside_window` before the write. |
| Offering 8:00–12:00 only when he can arrive at 8:00. Surprise from Gilbert cannot. | The window is offered when **some** ETA inside it works. Empty-day Surprise recommends morning with an internal ETA of 9:30. |
| Finish-by-5, which would reject a 4:45 arrival. | 5:00 is the last public arrival. Work may run past it. Override is the path for a later arrival. |
| Importing the saved east-zone end of 7:00 PM over the 5:00 PM he just set. | Offer end defaults to 17:00 and does not read the zone document. |

Attacks considered and rejected this pass:

- Reserving the morning for unknown future east jobs when a west window is the only legal gap. That hides a window he said to show, in favor of a job that does not exist yet.
- A separate zone penalty on top of added drive. Drive time is already the penalty. The 10-minute band is only a tie-break so two nearly equal gaps prefer the side he is already on.
- Shrinking the buffer automatically when two stops are close. He tied the buffer to variance, not to distance. If the 12-arrival arithmetic is wrong in practice, Settings is the fix.

### Second critique, after the window rewrite

A second pass read the revised plan against `server.py` (booking, dispatch, expiry, reorder) and rechecked the worked examples. Two holes would have shipped a day he cannot drive. Both are now in the body above.

| Attack | What changed |
|---|---|
| A completed job was pinned, but the van was treated as free at `scheduled_end`. A same-day job that ran long would still offer the next window. | Leave time for `complete` is `max(scheduled_end, actual_completion) + buffer`. An early finish does not pull the next departure earlier than the plan. The ETA itself stays pinned. |
| A drag payload of `ordered_job_ids` could omit `complete`, `driving`, `on_site`, and a pending offer, then slide booked jobs onto those minutes. | The payload must be exactly the movable booked set. A missing booked job is a 400. Anchors are spliced back at their current ETA, then one pack runs over the merged sequence. |
| Unsorted merge of pending-offer rows (their `technician_id` is already the contractor) could change which gap wins. | Sort by `(scheduled_start, id)` before a pack that is not a drag. |
| Expiry only inside the write lock still lets a stale offer block the availability read, or lets a read pack a route the next commit will revert. | Availability and the owner preview expire first and still do not write ETAs. Commit paths expire again inside the day lock. `GET /api/jobs` expires too. Expiry is not behind the flag. |
| Forcing one job past 5:00 left neighbors looking on time. | The same pack walk sets `route_conflict` on every job whose drive arrival is after its stored ETA. |
| "He pressed reschedule" and "the window id changed" were one SMS rule. | A new window id always texts the new window. The same window id uses the notify table. |
| "After 5:00 PM today is past" mixed the UTC-date bug with the offer end. | Past means the Phoenix calendar date is over. `offer_end` only stops shop arrivals. Same-day override after 5:00 PM stays legal. |
| Requiring `eta >= day_start` rejects a legal first arrival that is simply the drive after he leaves at 8:00. | A new public job only needs `eta <= offer_end`. |
| The cache key was still the UTC date of `now`. | It is the Phoenix date of the lookup. |

Two suggestions from that pass were refused:

- Texting automatically when running late makes the earliest arrival fall outside the window. That texts every later shop on a 20-minute overrun. The board shows `route_conflict`. He texts by confirming a drag.
- Keying the drive cache on the appointment date. The cache is a typical duration for the lookup day. A date three weeks out is not a different drive, and `departure_time` stays out.
