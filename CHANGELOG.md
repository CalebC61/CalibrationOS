# Changelog

All notable changes to CalibrationOS are recorded here. This file is the reconciliation
log between **Emergent AI** and **Claude Code** — every session must append what it did
in plain, technical language so neither system loses context across a handoff.

Format follows [Keep a Changelog](https://keepachangelog.com/). Newest entries on top.

---

## [0.1.0] — current

App version is **0.1.0**, the same number as `frontend/package.json`. `[0.0.3]` further
down is the previous cut (Xero, 2026-06-16), not a second current version.
`backend/tests/test_version.py` fails if the top changelog heading and the package
version drift apart.

### Changed — Style B preview, Field Instrument (2026-11-21)
Visual preview only. Do not merge as the production theme. No billing, Stripe,
Xero, permission, env, or database change.

Tokens, the public Home page, the shop portal, the owner Today board, and the
Field job screen use a graphite chassis (`#0C1014` / `#141A1F` / `#1C242B`) and
one calibration-beam accent (`#1FE0C4`, text `#8FF6E4`). Body is Source Sans 3,
titles are Barlow Condensed, and times, money, and counts are JetBrains Mono.
The wordmark stays Saira Stencil. Corners are 2px with hairline borders.
The Field screen (`.instrument-daylight`) flips to a high-contrast light chassis
(`#F3F5F2` ground, `#10211C` text, black primary keys) so it stays readable in
Arizona sun. Behavior, routes, and copy structure are unchanged.

Job-edit fixtures book the next day the shop can book, skipping Sunday, so
the suite still passes when Phoenix today is Saturday. Booking rules are
unchanged.

### Changed — public header (2026-11-19)
The public header is Home, Pricing, Service area, Contact, Shop login, and
Create account. Services, About, and FAQ stay at `/services`, `/about`, and
`/faq`, linked from the footer. Staff login stays in the footer at `/login`.
Shop login goes to `/portal/login`. Create account goes to `/signup`. There
is no public booking link. The old Book a job shortcut, which opened signup
or portal Book depending on who was logged in, is gone. On a narrow screen
the header is a Menu button, the same pattern as the owner and shop bars.

Public copy no longer says the shop gets ETAs or job updates by text, and it
no longer points at an online scheduler. Booking copy points at the shop
account. Prices are unchanged. No billing, Stripe, email, Xero, permission,
or env change.

### Changed — owner bar is Today, Shops, Money, Settings (2026-11-19)
The owner bar in `Shell.jsx` is four tabs. Today is the dispatch board at
`/dashboard` (new-bookings pill and the held-email notice stay on that board).
Shops is the shop list, with New signups and Invites as sections on that page.
Money is Charges and Invoices on `/money`. Settings keeps Pricing, Technicians,
Schedule, and Integrations, and adds Days off, Held email, Messages, and Growth.

Old paths redirect for an owner: `/requests` → `/shops?section=signups`,
`/invites` → `/shops?section=invites`, `/charges` → `/money`,
`/invoices` → `/money?section=invoices`, `/days-off` → `/settings?section=days-off`,
`/email-preview` → `/settings?section=email`, `/messages` → `/settings?section=messages`,
`/growth` → `/settings?section=growth`. A signed-out visit still goes to login.
The phone bar collapses to a Menu button, same idea as the shop portal.

Invite, Resend, and Growth Send are the same buttons and the same calls.
Nothing on the held-email list sends mail. No billing, Stripe, Xero, permission,
or env change.

### Changed — shop portal on a phone (2026-11-19)
The shop bar is Today, Jobs, Book, and Account. Today is the day map at
`/portal`, plus the four last-30-days counts that used to be the Scorecard
tab (jobs, completed, upcoming, total spent). Jobs is the history. Book is
unchanged. Account is the old Settings page: name, address, valley when the
shop has one, card, charge terms, and the agreement. `/portal/scorecard`
redirects to Today. `/portal/settings` is still the account page.

On a narrow screen the bar is a Menu button. Shop pages use at least a 44px
tap target, and the booking form stacks its two-column fields so a phone
does not scroll sideways.

Picking a Places suggestion on Book, or otherwise changing the address while
a date is set, loads that address's times again. The date does not have to
be changed away and back. Billing, Stripe, email, Xero, warranty, and the
booking rules are unchanged. No new env var.

### Changed — one booking form (2026-11-19)
`/portal/book` is the booking form. The owner screen at `/shops/:id/book` uses
that same component. The owner picks the shop and can type a time. The typed
time is any clock time. The date field keeps the same 21-day bounds it already
had for both the shop and the owner. The server still decides before-8:00 AM,
same-day limits, and whether a time is held. Nothing in billing, Stripe, email,
or Xero changed.

The owner screen does not say "Please invoice me instead" or "until the owner
approves it." A held owner booking says "Pending approval." The shop screen
still shows the warranty redo, the invoice checkbox, "Request this time," and
"This time is held until the owner approves it." Card-on-file and charge-terms
gates are unchanged.

The date field treats a partial or unreadable value as not a day, so it does
not ask for slots with "Invalid date." A slow "That date is in the past."
answer cannot stay on screen after a later valid date has slots.

A Dispatch link (`/dashboard?date=&job=<id>`) draws an orange `#FF5F1F` ring,
a short pulse, and an orange tint on that card. An AT RISK card keeps its red
border. The ring sits outside it. No new env var.

### Changed — the desk card shows one next action (2026-11-19)
The owner Dispatch job card (`/dashboard`) keeps a single next step on the
face of the card: Approve while a time is pending, Start Driving or I've
Arrived on the Phoenix day of the job (still disabled, with the same “Available
on the day of the job” line, on any other day), and Complete Job once the
technician is on site. Charge, delete, the trip fee, the Xero draft or
“needs attention” line, reschedule, cancel, decline, edit, and “Invoice this
job” sit under More on that card. Nothing was removed. The closed-jobs list
still deletes from its own row. The Yes, delete dialog is unchanged.

The card links to the phone screen for that job (`/field?job=<id>`, “Open on
the phone”). The phone opens that job. If it is not on today's Phoenix list,
it is loaded by id and is not mixed into the today list when the technician
goes back.

Errors from those card actions (including a failed upload on Complete and a
failed reorder) show in a dismissible notice on the board. They no longer use
the browser `alert()`. The delete confirmation is still the in-page dialog.

A shop-page job link (`/dashboard?date=YYYY-MM-DD&job=<id>`) highlights and
scrolls to that card. A job whose technician is not one of the columns still
shows, on the owner column. If the day list does not contain the id, Dispatch
reads `GET /api/jobs/{id}` and, when that job's Phoenix day differs from the
link, moves the board to that day once.

`GET /api/jobs?date_str=` and `GET /api/dashboard/summary` keep a job whose
start is on that Phoenix day when the stored value is a datetime or uses a
space instead of `T`. A 2:00 PM Phoenix start (21:00 UTC) stays on that
calendar day. Billing, Stripe, email, and Xero behavior are unchanged. No new
env var. `BILLING_ENABLED` and `SHOP_EMAILS_ENABLED` are unchanged.

### Fixed — owner screens show the rate card, the card on file, and the current booking time (2026-11-18)
The Shops list printed Tier from `pricing_tier`. Website signup stores Standard
there, so a Preferred or Real Fast shop still said Standard. The column is now
the wholesale card that sets the price: `Preferred: $115 / $75 / $165`,
`Real Fast: $115 / $100 / $165`, `Custom: $99 / $80 / $150`, or `Standard`
when the shop is on the standard card. `pricing_tier` stays on the shop
document and in the API.

The shop page lists that shop's upcoming jobs and recent jobs (date, time,
vehicle, status, price) and links each one to Dispatch on that job's day. It
also shows the card on file (brand, last four, expiry, and Active, Expired,
Removed, or None), whether charge terms are accepted, and whether the shop
can book right now. That last line is the existing booking gate's message.
The gate itself is unchanged.

The Dispatch new-bookings pill was keeping `scheduled_start` from the moment
the job was booked. After a shop moves the job, the pill now shows the job's
current time and status (Pending approval when the edit is waiting). The
stored alert still has the original time. Cancelling or declining still drops
that notice.

While shop mail is held, the board says "Shop emails are on hold — view held
emails" and still opens Email preview. `SHOP_EMAILS_ENABLED` and
`BILLING_ENABLED` are unchanged. No new env var.

### Fixed — invited shops can accept charge terms and then book (2026-11-18)
Self-signup writes `charge_authorization_accepted_at` on the shop and the shop
user when the shop accepts the charge terms and a card is saved. Invite
registration saved the agreement signature and left that timestamp empty. The
charge-terms step was a modal that appeared only in the same sitting as the
card save. A shop that signed the invite, left before the card, and later saved
a card in Settings had an active card and a signed agreement, and booking stayed
closed on "Accept the charge terms in Settings before booking." Settings had no
control for that.

The invite form now requires the same charge-terms checkbox signup shows.
Register stores that acceptance (`charge_terms_accepted_at`, the terms text,
IP, and user agent) and still leaves `charge_authorization_accepted_at` empty
until a card exists. Saving the card then writes the timestamp on the shop and
the user, the same fields signup writes when the card is part of create. The
agreement signature alone does not count, and shops already on file are not
backfilled. A shop that already has a signed agreement and an active card, and
is missing that timestamp, sees the terms text and "I accept the charge terms"
on Settings. That posts the existing `/portal/accept-charge`. Booking and the
day map send that shop to accept the terms. A shop with no valid card is still
told to update the card.

`POST /api/portal/book` already returned 403 from the booking gate. Tests now
cover a missing card, an expired card, a removed card, and missing charge
terms, and they check that accepting the terms lets the request past that gate.
`/requests` (New shops) still lists only shops with `signup_source: self_serve`.
An owner invite does not set that, and the page says those rows created their
own accounts. That is intended. No new env var. `BILLING_ENABLED` and
`SHOP_EMAILS_ENABLED` are unchanged.

### Fixed — day miles and Done by follow the jobs still on the board (2026-11-18)
The owner day header (Jobs, Revenue, Est. miles, Done by) was leaving the
last drive and finish time up after every job on that day was deleted. There
is no saved route for the day. `GET /api/dashboard/summary` already adds the
drive minutes and the latest end of the jobs still scheduled that Phoenix
day, and it already skips cancelled and declined jobs. A delete removes the
job, so the next summary is 0 miles and no finish time.

The header did not use that. Delete updated the job count and the revenue in
the browser and left Est. miles and Done by on the previous summary. A slow
summary response could put those two numbers back while the cards stayed
gone. The header now uses the jobs still on the board: drive minutes times
0.5, and the latest end. An empty day shows 0 miles and a dash. Deleting one
job of several uses the jobs that remain. Cancelled and declined jobs stay
out. No new env var. `BILLING_ENABLED` and `SHOP_EMAILS_ENABLED` are unchanged.

### Fixed — shop job edits follow the booking rules, and shop cancel names a reason (2026-11-18)
A shop edit that changes the date, time, address, or service is checked the
same way as a new booking. The time has to be free, the day has to be open
(Sundays, Thanksgiving, and other days off), the address has to be in the
valley, arrivals before 8:00 AM go back to pending and email the owner, and a
same-day stop past the drive limits does too. 6:00 AM is still offered. 8:00 AM
and later confirm. The price follows the shop's rate for the new service.
Names, vehicle, VIN, and notes leave the status alone. An unchanged save sends
nothing.

A real shop edit sends one "Job updated" email listing each change as old to
new, with the ref and a link to the job. A shop cancel sends one "Job
cancelled" email in the same shape as a booking confirmation and stores the
reason "Cancelled by shop", which Dispatch shows on Cancelled & declined. Both
use the shop mail path, so they stay in Email preview while
`SHOP_EMAILS_ENABLED` is off. Owner edits and owner cancel reasons are
unchanged. Warranty links and contractor removal are unchanged. No new env
var. `BILLING_ENABLED` is unchanged.

### Fixed — no geocode error while a booking address is still being typed (2026-11-18)
Book a Calibration looks up the address while it is being typed so a real
street can enable the date before blur. That lookup was also painting
"We couldn't find that address, please check it" when the text was still a
business name, such as `Downtown Phoenix Inc`, and the suggestion list was
open. The date went disabled with it.

A miss during typing no longer shows that sentence. Leaving the field does:
`zzzz qqqq nowhere 99999` still shows the error on blur, and the date stays
disabled. Picking a suggestion still fills the street, shows "In our Phoenix
service area", and enables the date. Editing again clears a blur error until
the next blur. No new env var. `BILLING_ENABLED` is unchanged.

### Removed — 5:00 PM day-before shop reminder (2026-11-18)
Shops no longer get an evening email listing the next day's jobs. The
in-process 5:00 PM Phoenix loop, `backend/day_before.py`, the
`day_before_reminder` template, and `day_before_reminders` markers are gone.
The late-fee loop is unchanged. No environment variable changed.
`SHOP_EMAILS_ENABLED` and `BILLING_ENABLED` are unchanged.

A shop still gets one booking confirmation when we have the job. A portal
booking that is booked immediately sends it then. A pending or same-day job
that is waiting on the owner does not send it yet. Approving that job (the
dispatch button or the owner email link) sends the same confirmation, once.
A second approve does not send another. Decline, reschedule, and cancel notes
are unchanged.

The confirmation says we have the job and includes the Phoenix date, the
arrival window (scheduled start through scheduled end), the vehicle, the
address, the ref (the first 8 characters of the job id), and a link to
`/portal/jobs/{id}`. While `SHOP_EMAILS_ENABLED` is false it stays in Email
preview and Resend is not called. `booking_confirmation_sent_at` on the job
blocks a second copy.

### Fixed — a picked business address stays confirmed on booking (2026-11-18)
Typing a business name on Book a Calibration asks Places for that full text.
"Downtown Phoenix Inc" is sent whole, not as an earlier prefix. Places can
still rank other downtown businesses above that name. The street query
"1 E Washington St Phoenix" is what returns Downtown Phoenix Inc.

Picking one of those businesses fills the street, for example
`496 N 5th St, Phoenix, AZ 85004, USA`. Booking then geocoded the words that
were in the box before the pick, or the new street, and a failure replaced the
service-area check with "We couldn't find that address, please check it". The
date stayed disabled. Signup does not geocode on each keystroke, which is why
the same pick showed no error there.

A place picked inside the valley is the confirmed address. The service-area
line comes from that pick. A geocode still running for the typed name cannot
apply after the pick, and a failed lookup of the confirmed street cannot clear
it. Blur during the place-details request does not send the typed business
name. Signup and add-shop still receive the street and the place id from the
same field. No new env var. `BILLING_ENABLED` is unchanged.

### Fixed — Places suggestions lag one character (2026-11-18)
The shop booking address, signup, and the owner "add a shop" form share
`AddressField`. Suggestions sometimes stayed hidden until the next character.

Two races caused it. Characters typed while the Maps script or
`importLibrary("places")` was still loading were dropped, and loading did not
ask again for the text already in the field. The next character was the first
request, so the list appeared one character late. That only happens when typing
wins the race with the script. Separately, every keystroke started its own
lookup. Clearing the field did not retire the lookup already in flight, so a
late response opened the previous list. A second keystroke that joined that
same in-flight lookup was treated as the answer for the newer text, and nothing
asked again until another character.

The field now waits 200ms, then asks once for the text in the field at the end
of that pause. The text is read when the request is sent, not from an older
render. One lookup runs at a time. If the field changes while it is running,
that response is ignored and the current text is requested after the next
pause. A response for an older request cannot open or replace the list. Text
typed before Places is ready is requested when the library finishes, without
another keystroke. A prefilled shop address still does not request suggestions
until it is edited. A business suggestion still fills the street, city, state,
and ZIP. No new env var. `BILLING_ENABLED` is unchanged.

### Changed — warranty banners, past-window booking warning, settings, and paid complete (2026-11-18)
A free warranty redo still confirms with no approval step. The job now shows a
Warranty banner on the owner day cards, the closed-job list, tomorrow's strip,
the route map tip, the field list and job page (including the complete
screen), and the shop's day list, My Jobs, job page, and scorecard. The banner
says the redo is not charged.

Booking a redo, or moving one, whose original completion was more than 30
Phoenix days ago asks the shop first. The notice says the 30-day warranty has
passed and the job will be charged at full price, with Continue and Cancel.
Cancel does not book or save. The price for that redo is the shop's normal
rate for the calibration, including a custom rate. Rescheduling a free redo
onto a day outside the window, from the shop edit or the owner reschedule,
reprices it the same way. A redo still inside 30 days stays $0 and does not
show the notice. `BILLING_ENABLED` and `SHOP_EMAILS_ENABLED` are unchanged.

Shop Settings shows the shop address. Update card has a Cancel button that
closes the form and does not save a card.

The field complete screen shows Paid and the amount as soon as the charge
succeeds. A later day-list response that is still unpaid does not cover that
paid result. A later card decline still replaces it.

### Fixed — health check and owner error mail (2026-11-18)
`GET /api/health` pings Mongo and returns 503 when the database does not
answer. The driver gives up after 2 seconds, and the request itself is capped
at 2.5 seconds. A healthy database still returns `{"status":"ok"}`. A failure
returns `{"status":"unavailable"}` and does not include the connection string.
`render.yaml` already sets `healthCheckPath: /api/health`, so Render's health
check and failure email use this result. No dashboard change is required
unless that path was edited by hand.

An unhandled server error (HTTP 500) emails the owner after the response is
sent. The note has the time, method, route, error type, message, and a trimmed
traceback. Connection strings, tokens, card numbers, and auth headers are
removed. The request body is not included. `POST /api/client-errors` accepts
the same kind of note from the browser. It does not require a login, rejects a
body over 4KB, and allows 8 reports a minute from one IP.

Alerts go to `ALERT_EMAIL`. When that is blank they go to `OWNER_EMAIL`, then
`ADMIN_EMAIL`. When all three are blank, nothing is sent. Sending uses the
existing Resend helper, including while `SHOP_EMAILS_ENABLED` is false. One
error is mailed at most once every 15 minutes, and the process sends at most
10 alerts an hour. A mail failure does not change the HTTP response.

The web app shows "Something went wrong" and a Refresh button when a screen
crashes, a script error fires, or a promise is rejected without a handler. It
reports that to `/api/client-errors` without the auth token or the query
string.

Set `ALERT_EMAIL` on Render when these notes should go somewhere other than
the owner or admin address. `RESEND_API_KEY` and `SENDER_EMAIL` still decide
whether Resend delivers the note or it is only logged.

### Fixed — paid card charges still looked unpaid (2026-11-18)
A live Stripe test-mode charge was succeeding: the PaymentIntent succeeded,
the Stripe invoice was marked paid, and `invoice.paid` was received. Dispatch,
the phone confirmation, and the Invoices page still showed the job as unpaid.

The local `job_invoices` row was inserted once as `open` and never updated.
`_charge_saved_card` set `payment_status` to `paid` but left `invoice_status`
alone and did not bump `updated_at`, so a slower day-list response could keep
the old card. `invoice.finalized` could then write `invoice_status` back to
`open` after the job was already paid.

A successful charge now sets `jobs.invoice_status` to `paid`, sets
`updated_at`, and sets the matching `job_invoices` row to `paid` with
`paid_at`. `invoice.paid` and `invoice.payment_succeeded` do the same row
update. `invoice.finalized` still stores the Stripe invoice id and hosted URL,
and it does not change `invoice_status` once the job is paid. The first insert
stays the only insert, and its opening `open` status is not copied back onto
a job that has already been paid.

`job_invoices.due_at` is the America/Phoenix date 7 days after completion,
the same window as `days_until_due=7` on the Stripe invoice. `GET /api/invoices`
returns that date and the updated status. The Invoices page shows Paid or Open
and a Due column. Dispatch hides "Invoice — hold charge" and "Charge card now"
once `charged_at` is set or `payment_status` is `paid`, and shows a Paid badge
with the amount and Phoenix time for both charge-on-completion and invoice-hold
jobs. Charge card now applies the job in the response immediately. The field
completion card adds one line: Paid $X, Invoiced with the due date, or Charge
failed, next to the Xero message. The Stripe webhook log includes the event
type. `BILLING_ENABLED`, shop-email gating, and amounts are unchanged.

### Removed — contractor dispatch; travel steps are today-only (2026-11-18)
The business does not use contractors. The product no longer offers that path.

Removed from the owner Dispatch board: the Dispatch to Contractor button, the
contractor picker dialog, pending-offer countdown, and Mark Accepted / Mark
Declined. Removed from the phone field view: the pending-offers list and its
Accept / Decline buttons. Removed from Settings: the Contractor tab. Assist no
longer has `dispatch_job`, `list_contractors`, or `update_contractor`.

Removed API routes: `POST /api/jobs/{id}/dispatch`, `GET /api/contractor-offers`,
`POST /api/contractor-offers/{id}/respond`, `GET /api/contractors`, and
`PUT /api/contractors/{id}`. Those paths are 404. The server no longer creates
contractor offers, no longer expires them, and no longer sends the contractor
offer, accept, decline, or expiry texts. Startup no longer creates a contractor
login and no longer rotates `CONTRACTOR_PASSWORD`. An existing contractor row
cannot sign in (`403`, "Contractor accounts are no longer used"). A saved
contractor token is rejected the same way. `CONTRACTOR_EMAIL` and
`CONTRACTOR_PASSWORD` are not read. Leaving them set does nothing.
`BILLING_ENABLED` and `SHOP_EMAILS_ENABLED` are unchanged.

Nothing deletes or rewrites contractor rows, offer rows, or a job already
marked `dispatched_to_contractor`. Deleting a job no longer deletes its offer
rows. The shop portal still counts a leftover `dispatched_to_contractor` job as
upcoming, so that job does not disappear. Hired technicians, route order, the
owner map, and the Dispatch day view stay.

Start Driving and I've Arrived work only when the job's `scheduled_start` is
today in America/Phoenix, including an evening job whose UTC date is already
the next day. On any other day the buttons are disabled and the screen says
"Available on the day of the job". The same words are the `400` from
`POST /api/jobs/{id}/status` for `driving` and `on_site`. That rejection sends
no text. Cancel and Complete still work on a job that is not today. A 6:30 PM
Phoenix job is still today.

### Added — day-before reminder for shops (2026-11-18)
Removed the same day. See "Removed — 5:00 PM day-before shop reminder" above.
Each evening at 5:00 PM America/Phoenix, every shop with jobs the next Phoenix
day gets one email. It lists each job's vehicle, customer, address, calibration
type, and estimated arrival (the scheduled start through the scheduled end,
Phoenix time), and a link to the shop portal. Cancelled and declined jobs are
left out. A shop with only those jobs gets no email.

The note goes through the same shop mail path as a booking confirmation. While
`SHOP_EMAILS_ENABLED` is false, which is still the default, it is stored for
Email preview and Resend is not called. `day_before_reminders` keeps one marker
per shop and Phoenix day, so a second pass does not send again. If the send
throws, that shop's marker is removed and the loop retries in five minutes.

The pass uses the in-process loop that already runs the late-fee sweep. It
sleeps until 5:00 PM Phoenix. If the process is down at 5:00 and comes back
later that evening, it still sends, until midnight. No new environment
variable. `BILLING_ENABLED` is unchanged.

### Fixed — address suggestions when the booking address is already filled (2026-11-18)
`/portal/book` starts with the shop's address. That box was plain text, so
editing it never offered a Google suggestion. The Places widget also hides its
list after a value is written onto it. The field now asks the Places
autocomplete data for suggestions on every edit, whether or not the shop
address was already there. A picked suggestion still fills the street. "In our
Phoenix service area" still follows the shop-address shortcut and the geocode
check, including while the address is being typed. Without
`REACT_APP_GOOGLE_MAPS_API_KEY`, it stays a typed address.

### Added — 30-day warranty redos (2026-11-18)
Every recalibration can be tied to an earlier completed job (`warranty_of_job_id`).
The shop portal booking form has an optional "This is a redo of a past job"
choice. It lists that shop's own completed jobs from the last 90 days, by
vehicle, customer, and completion date. The owner can set or clear the same
link while editing a job. A shop login cannot change the link after booking,
and the server rejects another shop's job or a job that is not completed.

Eligibility is Phoenix calendar days: the redo date minus the original
completion date. 30 days is free. 31 days is billed. A free redo is priced at
$0 and labeled "Warranty redo (free)". On Complete, that job does not get a
Xero draft and the card is not charged. The job records why
(`warranty_skip_reason`, `charge_skipped`, `xero_skipped_reason`). A redo past
30 days keeps the shop's normal rate, the normal Xero draft, and the normal
charge flow, and is labeled "Past 30-day warranty — billed normally".

The badge shows on the owner Dispatch card, the field job page, and the shop's
My Jobs. No new env vars. `BILLING_ENABLED` and `SHOP_EMAILS_ENABLED` are
unchanged. A free redo does not send the completion text or the invoice email.

### Fixed — declined jobs leave the new-booking banner, and the owner can delete them (2026-11-18)
Declining a pending job took it off the dispatch day, but its unseen
new-booking alert stayed. The banner and its count still included that job
until a full reload, and a reload did not help, because
`GET /api/notifications/new-bookings` only dropped alerts whose job was
`cancelled`. Decline never set `seen_at`.

The banner now drops alerts for `declined` jobs as well as `cancelled` jobs,
including ones declined before this change. Decline (the dispatch button and
the owner email link) sets `seen_at` on that job's alerts only. After Decline
or Cancel, the dispatch banner count updates immediately. A later poll cannot
put that job's alert back.

Cancelled and declined jobs are still off the day board, so Delete was
unreachable. `GET /api/jobs?closed=true` is owner-only and returns those jobs
across dates, newest update first, up to 1,000. The day list and `include_cancelled=true`
are unchanged: declined jobs stay out of the day and out of that history flag.
Dispatch has a Cancelled & declined control. The list shows date, shop,
vehicle, customer, status, and reason. Each row uses the existing Delete
action and its Yes, delete confirmation. Delete is still
`DELETE /api/jobs/{job_id}`: owner-only, no email, no text, and invoice rows
stay. `BILLING_ENABLED` and `SHOP_EMAILS_ENABLED` are unchanged.

### Fixed — Xero status updates without a browser reload (2026-11-18)
The owner app kept the previous Xero connection and the previous draft badge
until a full reload. Three things stacked:

- `GET /api/integrations/status`, `GET /api/jobs`, and the other owner reads
  sent no `Cache-Control`. Safari (and any cache in front of the API) can reuse
  that GET, so Disconnect, Retry, and the 5-second poll painted the old JSON.
- Settings → Integrations loaded the connection once. Coming back from Xero
  landed on `/settings?xero=connected` while the page still opened on Pricing,
  so the connected org and the banner never mounted. A page restored from the
  back-forward cache did not run that load again. Focusing the window did not
  refetch.
- Complete and Retry ignored the job in the POST response and waited on the
  job list. A list read that had already started could finish last and put the
  old badge back.

`/api` responses now send `Cache-Control: private, no-store`. Each owner GET
also uses a new query value so a response already sitting in the browser is
not reused. Settings opens Integrations when the URL is `?xero=connected` or
`?xero=error`, refetches on focus and on `pageshow`, and shows Disconnected
as soon as Disconnect succeeds. Dispatch, the field job, and Invoices refetch
on focus. Complete and Retry paint the returned job immediately, and a slower
list read cannot replace it with an older `updated_at`. No new env vars.
`BILLING_ENABLED` and `SHOP_EMAILS_ENABLED` are unchanged. The browser still
receives `xero_connected`, `xero_org_name`, and `/api/integrations/status`
only — not Xero tokens.

### Changed — shops book only after they log in (2026-11-18)
A booking link is no longer a way to book, change, cancel, or read a shop's jobs.
`GET /api/public/shop/{token}`, `POST /api/public/availability`, `POST /api/public/book`,
`GET /api/public/bookings/{token}`, `PATCH /api/public/bookings/{token}/{job_id}`,
`POST /api/public/bookings/{token}/{job_id}/cancel`, and `GET /api/public/shop-status/{token}`
are gone. Old `/book/{token}` and `/scorecard/{token}` pages send the visitor to the shop
portal login and do not show job data.

Shops book, see open times, edit, and cancel through the portal login:
`POST /api/portal/availability`, `POST /api/portal/book`, `PATCH /api/portal/jobs/{job_id}`,
`POST /api/portal/jobs/{job_id}/cancel`, and `GET /api/portal/scorecard` (that shop only).
The card-on-file and charge-terms checks are unchanged. `SHOP_EMAILS_ENABLED` and
`BILLING_ENABLED` are unchanged. Shop and staff responses still use the allowlists from
`backend/client_views.py`: no Stripe ids, Xero tokens, or password hashes. The owner
delete-job action is unchanged.

The owner still books for a shop from the shop page (`POST /api/shops/{shop_id}/book` and
`POST /api/shops/{shop_id}/availability`). Owner reschedule uses that availability route.
Welcome mail and the owner "finished signup" mail point at `/portal/login`. The invite
mail still opens the setup page, and says booking happens in the shop portal.

The public site's Book a job buttons (header, footer, pricing, contact) go to shop
signup, or to portal Book when that browser is already logged into a shop. They no
longer open Calendly. The portal booking form checks a changed address while it is
being typed, so Continue can turn on before the field loses focus.

### Fixed — session and shop responses no longer include credentials (2026-11-18)
`GET /api/auth/me` returned the owner Mongo document. That document holds the
Xero access token, refresh token, token expiry, and tenant id. Password hashes
were already left out of that query. They were not the only secret on the row.

Staff responses (`/api/auth/me`, `/api/contractors`, contractor update, and
`/api/routing-techs`) now use an allowlist (`StaffPublic` in
`backend/client_views.py`). The client still gets `xero_connected` and
`xero_org_name` (the Xero organisation name). It does not get access, refresh,
or id tokens, token expiry, or the tenant id.

Shop-user responses (`/api/portal/me`, card setup completion, charge
acceptance, and public shop signup) use `ShopUserPublic`. Card brand, last4,
and expiry stay, because the portal shows them. `stripe_customer_id` and
`stripe_payment_method_id` do not. `has_payment_method` replaces the raw card
id. The portal settings page reads that boolean.

Shop documents returned to the owner or the shop keep the booking link and the
Xero contact id the owner edits. They drop Stripe customer and payment-method
ids, password hashes, and token fields. `GET /api/public/shop/{token}` was
already an allowlist and did not include those ids.

`/docs`, `/redoc`, and `/openapi.json` are off when `APP_ENV` is `production`
or `prod`, unless `ENABLE_API_DOCS=true`. `ENABLE_API_DOCS=false` turns them
off in any environment. When they are off, those paths return 404. The React
app does not request `/openapi.json`. A SetupIntent `client_secret` is still
returned from the card-setup calls, because Stripe.js in the browser has to
have it to confirm the card. It is not stored on the user document.

### Added — the owner can delete a job (2026-11-18)
`DELETE /api/jobs/{job_id}` is owner-only. A shop portal login, a technician,
and a contractor receive 403. The job row is removed, along with its documents,
new-booking alerts, contractor offers, owner-action tokens, and a vehicle row
no other job still uses. Xero and Stripe invoice rows stay on the invoices
list. The call does not email, text, cancel, reschedule, or contact Xero or
Stripe. `SHOP_EMAILS_ENABLED` and `BILLING_ENABLED` are unchanged.

On the owner Dispatch dashboard, each job card has a Delete action beside
Edit. The confirmation shows the vehicle, shop, and date, and names a linked
Xero draft or Stripe invoice when the job has one. Cancel leaves the job.
Yes, delete removes that card without reloading the page.

### Fixed — triple Xero item and wholesale price at Complete (2026-11-17)
A triple calibration now files the Xero item named Subaru MC Calibration
(code 8). Triple/Subaru Calibration is used only when that item is missing.
The rates are unchanged: standard $185, Real Fast $175, Preferred $165.

Booking and Complete now price the job at that shop's wholesale rate for the
calibration being filed (standard, Real Fast, Preferred, custom, or auto from
the shop name). Complete does this even when the calibration type stays the
same, and it does it before the local invoice, the admin email, and any card
charge. The $30 trip fee stays a separate amount on top. A Xero failure still
leaves the completed job as needs attention, with Retry.

The public booking link and the portal booking screen show that same rate.
The public date step imports `phoenixTodayStr`. It was calling that helper
without an import, so the date field threw before a date could be picked.

### Fixed — Complete files a usable Xero draft (2026-11-17)
The signed post-scan on a real scan tool is a font-encoded PDF. `vin_from_pdf`
now reads that text with pypdf, collapses whitespace, and keeps the 17-character
VIN next to the VIN label. The old compressed-stream reader remains the fallback
when pypdf cannot read the file. `pypdf` is in `backend/requirements.txt`.
The test PDF is built with reportlab and a TrueType font so the old reader
finds nothing.

Dispatch's Complete button no longer posts `{result: pass}` by itself. It opens
the same required fields as the field app: calibration type, POP (None or a
dollar amount), and a signed post-scan PDF already on the job or uploaded then.
The job is not completed until those are present.

A couldn't-calibrate job (trip fee only) still attaches a post-scan when one
was uploaded, and it files the draft when there is no PDF. A normal calibration
still requires the PDF.

When Complete changes the calibration type, the job price becomes that shop's
wholesale rate for the new type (Real Fast, Preferred, custom, or standard).
An outside-area job keeps the extra $30. A trip-fee-only job stays at $30.
The local invoice and the card charge then match the Xero line.

`POST /api/jobs/{id}/upload-document` names the file
`CUSTOMER_SHOP_Make_Model_Year.ext` when the job has no customer last name,
instead of raising.

### Fixed — Xero connect lands on Settings after the callback (2026-11-17)
`GET /api/auth/xero/callback` saved the tokens and then raised
`NameError: RedirectResponse is not defined`, so the browser saw a 500.
The redirect is a 302 to `XERO_POST_CONNECT_REDIRECT` with `?xero=connected`
or `?xero=error`. On Render that setting is
`https://www.thecalibrationcrew.us/settings`, so the owner returns to
Settings on that site. A query string already on the setting is dropped
before `xero` is added.

### Fixed — Xero connect uses granular invoice scopes (2026-11-17)
The Xero app was created after 2 March 2026, so the authorize URL's broad
`accounting.transactions` scope comes back as `invalid_scope`. `XERO_SCOPES`
in `backend/server.py` now requests `accounting.invoices` instead. Invoice
create, update, PDF download, and the status poll all use the Invoices
endpoint, including reading `Status` when it is `PAID`. No code calls the
Payments, Overpayments, or Prepayments endpoints, so `accounting.payments` is
not requested. Reports and journals scopes are not requested. The rest of the
string is unchanged: `openid profile email accounting.contacts
accounting.attachments accounting.settings.read offline_access`. This is still
a code constant, not an env var. A token saved under the old scope stays on
the old grant until the owner connects Xero again.

### Added — completing a job files the Xero draft Maddy builds by hand (2026-11-17)
Completing a job still settles the card the same way. `BILLING_ENABLED` and
`SHOP_EMAILS_ENABLED` are unchanged. After that, `create_invoice_for_job` files
one Xero ACCREC draft for the job, or marks the job `needs attention` and still
leaves the job complete.

The draft is due the same day as the job, with no tax, a blank reference, and the
branding theme named Calibration Template. Line 1 is the Xero item for the
calibration type (Static, Dynamic, Dual, Triple/Subaru, Tesla) at the shop's
wholesale rate, account 4100, tax exempt. Line 2 is only
`FIRST LAST - YEAR MAKE MODEL - VIN`. A $30 trip fee is its own priced line when
the job is out of area. A trip-fee-only job (could not calibrate) does not also
sell the calibration. When POP is a dollar amount, the draft is saved at that
amount, the invoice PDF is fetched, both PDFs are attached with IncludeOnline,
and line 1 is then updated to the wholesale rate. The draft is never authorised
and never sent from Xero.

The shop's Xero contact id can be set by the owner. If it is blank, the app
matches an existing contact by the exact name (the known shop list, or the shop's
own name) and saves the id. It does not create a contact. No confident match
means no invoice, and the job is flagged. Wholesale cards for Real Fast and
Preferred are editable under Settings → Pricing. Standard wholesale follows the
standard prices. A retry uses the invoice id already stored on the job.

The field screen requires the signed post-scan PDF, the calibration type, and
POP (or None) before Complete. The uploaded PDF is the document that downloads.
Completion no longer inserts a second document row with no bytes. The field
screen and the day board say either `Draft INV-#### created` or the attention
reason. Maddy is emailed at `ADMIN_EMAIL` through the owner-mail path with the
number and link.

The connect URL reads `XERO_SCOPES` in `backend/server.py` (a code constant, not
an env var). That string now also requests `accounting.attachments` and
`accounting.settings.read`. A token saved before this change keeps its old
scopes until the owner connects Xero again.

### Fixed — pre-launch privacy, limits, and a few shop-facing snags (2026-11-17)
A logged-in shop's day map (`GET /api/portal/day-map`) shows every stop on the
owner's route for that America/Phoenix day, in route order. This shop's jobs
stay in full (customer, vehicle, address, status, and the arrival window).
Another shop's stop is a gray pin: route position, the arrival window, and a
coordinate rounded to three decimal places (about a block). The response for
that stop does not include a job id, shop name, customer, vehicle, VIN, address
text, phone, notes, or price. The empty state is only for a day with no stops
at all. The legend says the gray pins are other stops and show the time window
only.

`POST /api/auth/login`, `POST /api/portal/auth/login`, and
`POST /api/portal/auth/forgot-password` use the same in-memory counter as
signup. Sign-in allows 8 attempts per 15 minutes per network and per email,
then `429` with "Too many sign-in attempts. Wait 15 minutes and try again."
Password reset allows 5 per hour per network and per email, then a clear `429`,
and does not send another email. `POST /api/geocode` allows 30 lookups per hour
per network. `POST /api/public/contact` allows 5 messages per hour per network
and per email. Signup's own limit is unchanged.

A portal report download now requests the file with the shop's login token and
saves it from that response. The old plain link had no token, so the download
could not be authorized.

A geocode cache hit runs the street-line strip again. An older cached line that
still starts with a business name is saved as the street
(`1 E Washington St, Phoenix, AZ 85004, USA`). A suite number stays. A fresh
Google lookup was already doing this; the cache path was not.

The card form in signup and Settings → Update card uses Stripe's tabs layout
with the card fields open, still cards only, with Link and wallets off.

A failed booking in the shop portal shows the error on the page. It no longer
uses a browser alert.

`SHOP_EMAILS_ENABLED`, `BILLING_ENABLED`, the public booking link, the
scorecard link, job completion, Xero, and SMS are unchanged.

### Fixed — every shop needs a verified card before it can book (2026-11-14)
The server no longer trusts a payment method id from the browser. Signup and
the portal send a SetupIntent id. The API retrieves it and saves the card only
when the status is `succeeded`, the method is a card, and the intent was created
for this signup (`metadata.purpose` `shop_signup`) or for this shop's Stripe
customer. A test id such as `pm_card_visa` does not unlock booking.
`POST /api/portal/complete-setup-intent` and `GET /api/portal/stripe-setup-status`
use the same check, and a Checkout session must belong to the logged-in shop's
customer. A failed signup deletes the Stripe customer it just created.

The card is stored on the shop. The booking gate and a charge both read that
record. Until a shop has been backfilled, they use the earliest active shop
user. Startup copies that user's card onto the shop once
(`billing_card_backfilled`). Brand, last4, and expiry are saved with the card.

Every shop, including ones created before card-on-file billing, must have a
current card and accepted charge terms to book. A blank, removed, detached, or
expired card blocks `POST /api/public/book` and `POST /api/portal/book`. An
unresolved failed charge does too, until the card is replaced or a later charge
succeeds. The shop sees a message that points at Settings. Owner job actions
are unchanged. `DELETE /api/portal/payment-method` refuses, so a shop cannot
remove its only card.

Settings → Update card opens the card-only Payment Element
(`allowed_payment_method_types: ["card"]`, Link and wallets off) for the shop's
existing customer. After the SetupIntent is verified, that card becomes
`invoice_settings.default_payment_method`, the shop record is updated, and the
previous card is detached. Later charges, including jobs still waiting to be
invoiced, use the new card. A disabled shop user is rejected. The agreement IP
and the signup rate limit use the rightmost `X-Forwarded-For` entry, which is
the one Render appends. Card changes are written to `card_changes` (brand and
last4 only).

`POST /api/stripe/webhook` still verifies `STRIPE_WEBHOOK_SECRET`. It now also
handles `payment_method.detached` (clears the card when it is the one on file)
and `setup_intent.succeeded` (saves the card for that customer).
`payment_intent.payment_failed`, `payment_intent.requires_action`, and
`invoice.payment_failed` set `unresolved_charge_failure`. A later
`payment_intent.succeeded` or paid invoice clears it. No new env var.
`BILLING_ENABLED` and `SHOP_EMAILS_ENABLED` are unchanged.

Signup retry still reuses a succeeded SetupIntent, and the duplicate and
address pre-checks are unchanged. If card setup does not start, the page says
to try again or call. It does not say the card can be added from Settings
after the shop exists.

### Fixed — a Places business suggestion is a street address (2026-11-14)
The first suggestion for "1 E Washington St, Phoenix" is the subpremise
`Downtown Phoenix Inc, 1 E Washington St, Phoenix, AZ 85004, USA`. Places
`formattedAddress` starts with that establishment name. `POST /api/public/shops/check`
geocodes that string and answers "We couldn't find that address, please check it",
so signup stays on `/signup`. The same building without the name geocodes to a
rooftop, and Google's formatted line puts the business name back on the front.

`AddressField` now asks for `addressComponents` and submits the street, city,
state, and ZIP. A unit stays. The business name does not. If the widget then
writes the suggestion label back into the field, the field is put back to the
street, and `place_id` is left in place. The same field is used for signup and
for a shop the owner adds by hand.

The geocoder stores that street line instead of the business-prefixed formatted
address, and keeps the rooftop lat/lng. A query that still arrives with the
business name is looked up once more as the street. A plain street is still one
lookup. A partial match, a guess, and an address outside the valley are still
refused. Duplicate checks and the card retry are unchanged.

### Fixed — signup card form starts on Stripe API 2026-09-30 (2026-11-14)
`stripe==16.0.0` pins API version `2026-09-30.endive`. That version returns
400 `payment_method_types_no_longer_supported` when a SetupIntent, PaymentIntent,
or Checkout Session is created with `payment_method_types`. Signup was the only
caller that sent it (`["card"]`), so `POST /api/public/card-setup` answered
`stripe_unavailable` and the page never mounted the card form.

Card setup now sends `allowed_payment_method_types: ["card"]` and does not send
`payment_method_types` or `automatic_payment_methods`. The allow-list is the
code-side replacement: a method that is not in it is not offered, even when the
Dashboard has that method turned on. That covers the signup SetupIntent, the
Settings and invite SetupIntent, and the Checkout setup fallback. Checkout also
sets `wallet_options.link.display` to `never`. Link, Apple Pay, and Google Pay
are wallets on top of `card`, so both Payment Elements still set those wallets
to `never`. No Dashboard payment-method change is required.

Job charges do not send `payment_method_types`. They confirm the card already
saved on the customer, off-session. That path is unchanged. Signup retry still
reuses a succeeded SetupIntent, and the duplicate and address pre-checks are
unchanged.

### Fixed — signup retry no longer re-confirms a saved card (2026-11-13)
The signup page created one SetupIntent and called `stripe.confirmSetup()` before
`POST /api/public/shops`. A 409 (duplicate email, or `needs_confirmation` for a
typed address) left that SetupIntent succeeded, and the retry confirmed it
again. Stripe returned `setup_intent_unexpected_state` ("A processing error
occurred.").

After a successful confirm, the payment method id is kept and reused. A card
edit clears it. Before confirming, the page reads the SetupIntent and uses the
payment method when the status is already `succeeded`. `setup_intent_unexpected_state`
and other Stripe errors use plain copy.

`POST /api/public/shops/check` runs the same duplicate-email, duplicate-name,
and address-confirmation checks as create, including `needs_confirmation` and
`formatted_address`. It shares the signup rate limit, creates nothing, and does
not add a new way to learn whether an email exists. The page calls it before
`confirmSetup`.

The signup SetupIntent allows only `card` (see the 2026-11-14 fix above; this
used to be `payment_method_types: ["card"]`). The signup Payment
Element hides Link, Apple Pay, and Google Pay. With no
`REACT_APP_GOOGLE_MAPS_API_KEY`, the address hint tells the shop to type the
address and confirm the one the server finds. The password field shows the
rule from `GET /api/public/agreement` (`password_rule`, `password_min_length`;
at least 8 characters) and checks it before submit.

The address field uses Places API (New): `PlaceAutocompleteElement`, loaded
with `loading=async` and `importLibrary("places")`, limited to US addresses
inside the Phoenix Valley. A picked suggestion still sends `place_id` and the
formatted address. If the Maps script or Places fails (`ApiNotActivatedMapError`,
`gm_authFailure`, `gmp-error`), the field stays an enabled text input and the
server confirm step handles it.

### Fixed — owner Shops and Invites lists, and the held setup link (2026-11-13)
Approving shop request `6ea62a50-7898-4e6e-a730-196b4cf30606` returned 200.
Shop mail is off, so the invite was stored as `email_status: held` with no
error string. Requests said "Invite was not delivered." and did not show
`register_url`, which is built from `FRONTEND_URL`.

`GET /api/invites`, `GET /api/jobs`, and `GET /api/email-log` still sorted
inside the Mongo find. That is the query that hid shop requests: a sorted
find can follow an index and omit documents that are not in it, then return
200 and `[]`. `GET /api/shops` did not sort and does not filter on status,
cancelled, archived, or an owner id. The client was already pinned to the
primary. Shops and Invites still painted "No shops yet." / "No invitations
yet." when the load threw or the body was not a list, and a shop with no
string `name` crashed the Shops table. Invites loads shops, invites, and the
email log together, so one bad body left every list empty.

Owner reads for jobs, shops, invites, the email log, and shop requests now
go through `owner_documents`: primary, no server-side sort, then order in
process. Approve returns `register_url`. Requests shows that link, and the
copy button says Held when the mail is held. Held invites on `/invites`
show the same link. The raw token is not a response field and is not logged.
A failed load shows an error instead of the empty line.

### Added — glass shops sign up themselves (2026-11-13)
`POST /api/public/shops` creates the shop, the shop user, and the signed agreement
(version `2026-11-13.1`, which adds Triple / Subaru at $185) and returns a portal
JWT. A duplicate email is 409 and points at login and forgot-password. A Places
`place_id` counts as a confirmed address, so that signup does not 409 for a
second submit. A free-typed address still confirms only when the geocode is not
a precise pin. The same rule applies when the owner adds a shop by hand.

The signup page is `/signup`: shop, contact, mobile, email, password, address,
the agreement and signature, the Stripe card, and the charge-acceptance line,
then one Create my shop button. Success opens Book a job. If Stripe is not
configured the account is still created and booking stays closed until the card
is saved from Settings. Card setup is not a one-time invite link. The public
routes are rate-limited per IP.

`/requests` is New shops. The owner can Flag or Suspend. A suspended shop cannot
book. The new-shop email still goes out through `send_email` (kind `shop_request`),
and only after the new shop can be read back. Shop-facing mail is unchanged and
still waits on `SHOP_EMAILS_ENABLED`. Pending rows already in `shop_requests` stay
on that page, and Approve still sends an invite. Invites remain for shops the
owner adds by hand. When that mail is held, the setup URL is on screen with a
copy button labeled Held. New shops use the same `owner_documents` read as
the other owner lists: primary, no server-side sort. A failed load shows an
error instead of an empty list.

`FRONTEND_URL`, when blank, uses `PUBLIC_SITE_URL`, or
`https://www.thecalibrationcrew.us`. The ready-page booking link uses that host.
Requesting a new invite while shop mail is held does not say the mail is on the way.

The first portal booking is two screens. The shop address reuses the signup pin
and does not geocode again. Screen two is the vehicle, the calibration and price,
and “invoice me instead”. Static $125, Dynamic $125, Dual $175, Triple / Subaru
$185, and Tesla $225 are on the agreement and the public price lists.

`BILLING_ENABLED` is unchanged. No Google Calendar events are created.

### Fixed — shop account requests show on the owner Requests page (2026-11-13)
`POST /api/public/shop-requests` saved the request and emailed the owner, and
`GET /api/shop-requests` returned 200, but `/requests` stayed on "No requests
yet." The page renders that line only when the JSON array is empty. The list
was a sorted Mongo find, which can follow an index and omit a document that is
not in the index. The client also followed `readPreference` from `MONGO_URL`,
so a secondary read could miss a write the primary had already accepted. The
list now reads from the primary with no server-side sort, then orders by
`created_at`. The signup handler emails the owner only after it can read the
new request back. `/requests` shows a load error when the response is not a
list, and leaves the empty line for a list that really is empty.

### Fixed — cancelled bookings leave the day and their new-booking alert (2026-11-13)
A shop cancel, an owner cancel, and a status change to `cancelled` already set
`status` to `cancelled`. `GET /api/jobs` (the day board, Field, tomorrow
preview, and route map) and `GET /api/dashboard/summary` already omit that
status, and route reorder refuses a cancelled id. Those screens also drop
`cancelled` and `declined` before drawing, so a stale payload cannot put the
job back on the board or the map. The job stays in Mongo. The shop portal
list is unchanged.

The unseen new-booking alert for that job was left in place, so the owner
still saw a new-booking notice after the booking was gone. Cancel now sets
`seen_at` on that job's alerts only. `GET /api/notifications/new-bookings`
also skips alerts whose job is already `cancelled`, including ones cancelled
before this change. Other unseen alerts stay.

### Removed — Emergent badge (2026-11-12)
The public HTML no longer includes the “Made with Emergent” badge, the `emergent-main.js` script, the PostHog snippet that script sat next to, or the Inter font that only the badge used. The page title and description were already “The Calibration Crew” and the Phoenix Valley calibration line.

### Added — public site, shop requests, and card-on-file billing (2026-11-12)
Logged-out `/` is the public site (home, services, pricing, service area, about, FAQ, contact, sign up). Staff login stays at `/login`.

A shop requests an account (name, contact, mobile, email, Phoenix Valley address). That emails the owner and waits. Approve creates the shop and sends one invite. The owner can also add a shop directly: name, valley address he confirms, mobile, and email are required, and a duplicate name or email warns. He does not sign for the shop. The success screen sends the invite to the contact email.

One agreement, version `2026-11-12`, is signed by the shop contact during invite setup (name, time, IP, user agent). Then they save a card with a Stripe SetupIntent. A modal records that they accept a charge after each completed job unless they asked to be invoiced, with a 7-day grace period and a $25 late fee. New shops cannot book until that is done. Shops already on file keep booking and see a banner. Password reset is a one-time emailed link. The server rejects passwords shorter than 8 characters.

Invite mail uses `SENDER_EMAIL`, Reply-To the owner, and `FRONTEND_URL` (not the browser origin). Startup logs an error if the sender is `onboarding@resend.dev`. Each invite stores sent or failed. Resend issues a new 14-day token and revokes the old one. An expired link can request a new one and shows `OWNER_PHONE`. When setup finishes, the shop gets a welcome with the booking link and the owner gets "{shop} finished signup".

Completing a job creates one invoice (Stripe when a customer exists, otherwise a local record) and emails it. Charge-on-completion also creates one off-session PaymentIntent, idempotent per attempt, and does not open a second Xero invoice. Invoice mode does not charge until the owner presses Charge card now. A shop can tick "Please invoice me instead" while booking. A daily sweep adds one $25 late fee to unpaid invoice-mode jobs after 7 days. Card declines mark the job payment failed and email the owner and the shop. `POST /api/stripe/webhook` verifies `STRIPE_WEBHOOK_SECRET`.

Technicians and contractors cannot change a job's status, complete it, or upload a document. The owner still can, including from the phone view.

Shop and customer mail (invite, welcome, invoice, receipt, payment failed, password reset, and the booking kinds from the other mail work) is held in `email_outbox` while `SHOP_EMAILS_ENABLED` is off, which is the default. The owner reads them at Email preview. Invite and password-reset mail still sends when the address is on `TEST_EMAIL_ALLOWLIST`. Completing a job does not charge the card, and the late-fee sweep does not run, while `BILLING_ENABLED` is off. A live Stripe key is ignored until that flag is on. Use `sk_test_` / `rk_test_` and `pk_test_`.

The shop agreement is version `2026-11-12.3`. The legal name is The Calibration Crew LLC. It covers the parties, prices, card and invoice rules, the $30 trip fee, shop responsibilities, no late-cancel fee and no waiting fee, a 30-day re-calibration, liability, disputes, the electronic signature, and Arizona law. There is no $50 late-cancel fee.

An owner can mark a job "Outside service area, +$30", which adds $30 to the price once. "Couldn't calibrate, charge $30 trip fee" sets the amount to $30, records bad install or customer/vehicle, and invoices or charges through the same completion path. A declined card becomes an invoiced balance. Automatic charges still wait on `BILLING_ENABLED`, and shop mail still waits on `SHOP_EMAILS_ENABLED`.

Shop and customer mail uses the same `SHOP_EMAILS_ENABLED` flag and `email_outbox` as booking mail. Invite and password-reset messages can still send to `TEST_EMAIL_ALLOWLIST`. Completing a job does not charge the card, and the late-fee sweep does not run, while `BILLING_ENABLED` is off. A live Stripe key is ignored until that flag is on.

### Added — booking email, days off, and real map pins (2026-11-12)
A booking emails the shop contact through Resend (`SENDER_EMAIL`, Reply-To
`OWNER_EMAIL`) with the Phoenix time, vehicle, address, calibration, price,
and either "confirmed" or "pending Caleb's OK". Same-day bookings and arrivals
before 8:00 AM also email `OWNER_EMAIL` with signed Approve and Decline links.
Each link is single-use, expires in 48 hours, and opens a confirmation page
before it changes the job. Approving, declining, rescheduling, or cancelling
emails the shop. The booking screens no longer say a text was sent. A failed
time lookup says "Couldn't load times, try again" and offers a retry. A phone
that is not 10 digits is rejected.

Days off (`/days-off`) starts with New Year's Day, Memorial Day, July 4, Labor
Day, Thanksgiving and the day after, Christmas Eve, and Christmas for this year
and next. The owner can open a holiday or add a vacation range. Closed dates
are not offered, and a booking on one is rejected. Jobs already on a newly
closed date are flagged on that screen and are not cancelled.

Shop and job saves refuse a Google failure, a partial match, a mock fallback,
and an approximate central-Phoenix guess. The message is "We couldn't find
that address, please check it". Lookups are biased to the Phoenix Valley and
an address outside it is refused. `/map-pins` lists shops and jobs whose
stored coordinates still match a fallback so they can be looked up again.
`PUBLIC_SITE_URL` is the host used in the owner links (default
`https://www.thecalibrationcrew.us`).

Shop and customer mail is off until `SHOP_EMAILS_ENABLED=true`. While it is
false, those messages are stored in `email_outbox` and shown read-only at
`/email-preview`. They are not sent through Resend. Owner alerts follow
`OWNER_EMAILS_ENABLED`, which defaults to true, so the approve links can be
tested. The dispatch board shows "Shop emails: OFF (testing)" while shop mail
is held.

### Fixed — cancelled jobs leave the day list (2026-11-12)
`GET /api/jobs` omitted `declined` and still returned `cancelled`. The owner
dashboard, Field, the tomorrow preview, and the route map all read that list,
so cancelled jobs sat next to booked work. The list now omits both statuses.
The Mongo documents are not deleted. `include_cancelled=true` puts cancelled
jobs back in that response for a future history view; declined stays out, and
those screens do not send the flag. A reschedule still updates the same job's
`scheduled_start`, so the job shows on the new Phoenix date only. `GET
/api/portal/jobs` is unchanged, including the shop Cancelled tab. Cancel,
reschedule, and notification behavior are unchanged. This change sends no SMS
or email.

### Changed — fewer Google Routes calls (2026-11-11)
Traffic-aware Compute Routes Pro is only for today, and for tomorrow while
it is still before 10:00 AM Phoenix. Later dates use TRAFFIC_UNAWARE
(Essentials), which rejects `departureTime`, plus a 1.25× rush multiplier
from 6:30–9:00 AM and 3:30–6:30 PM. Those windows, the multiplier, the 10:00
cutoff, and the daily caps are owner settings (defaults: Pro 300/day,
Essentials 600/day). Past the cap, drive time falls back to the mileage
estimate and a warning is logged. Settings shows today's counts.

Future departures share a 30-minute bucket. Same-day stays at 15 minutes.
A return home is one call per hour on Pro and one call on Essentials. A
slot that cannot work even at 60 mph never calls Google. A book or an edit
rechecks only the previous stop, the new stop, and the next stop. Future
results stay cached for 7 days or until that date ends. Pro results stay
for 2 hours. Geocodes are cached by the normalized address.

### Fixed — first stop on an empty future day, and Routes 403 logs (2026-11-11)
On an empty future day the technician may leave home at 6:00 AM. A first stop
is offered when arrival minus the drive is still at or after 6:00. An 8:00 AM
Surprise arrival with a 96-minute drive leaves at 6:24 AM and is confirmed.
Times before 8:00 AM that still fit stay pending approval. Same-day limits
are unchanged. A failed `computeRoutes` call, including HTTP 403, logs the
response body with the API key removed.

### Added — early arrivals, traffic-aware drive times, and today's route limits (2026-11-11)
Shops keep one booking page. The scheduler decides from the Phoenix date.

A later date, including a request made the night before, uses the whole-valley
route. Arrivals from 6:00 AM are offered. Before 8:00 AM the job is
`requested` (pending owner approval) and still holds the slot. 8:00 AM–5:00 PM
is confirmed as before. The first stop of the day before 8:00 AM does not
wait on the drive from home; the technician leaves early. Drive time between
jobs still applies.

A booking for today uses the technician's current place (the last job, or a
fresh `live_lat` / `live_lng` / `live_at` when one is stored). It is confirmed
only when the extra drive and the later finish stay inside the technician's
limits (defaults: 20 minutes extra drive, 45 minutes later finish). Past that,
the time is held for approval, or hidden, depending on Settings → Technicians.
Today can be turned off. The cutoff defaults to 1:00 PM. There is no separate
shop control and no "add-on" label. The shop sees the times it can book, and
"Pending approval" when the owner still has to say yes.

Job length defaults to 20 minutes and the buffer between stops defaults to
15. Both are editable per technician.

Drive times call the Routes API `computeRoutes` with `TRAFFIC_AWARE` and that
leg's departure time when `GOOGLE_MAPS_API_KEY` is set. Cache: 12 hours, by
rounded coordinates and a 15-minute departure bucket. A missing key or a
failed call is logged and the mileage estimate is used. Approve and decline
(`POST /api/jobs/{id}/approve` and `/decline`, owner only) do not send SMS or
email. `notify_booking_approval` is the hook. Technicians and contractors
cannot edit jobs or approve times.

### Changed — one technician covers the whole valley (2026-11-11)
Booking, slot availability, the dispatch board, and the route map no longer
split the day into hard-coded East and West. With one active routing
technician (Caleb, home base Gilbert unless the owner changes it), every
in-valley job is theirs. Morning stays bookable when an afternoon job
already exists, and the other way around. A seeded contractor does not
take a side of the valley.

The owner can add technicians under Settings → Technicians. Each one has a
geocoded home base, a day window, and an optional service radius. With two
or more, a job goes to a tech whose radius covers it, otherwise to the
nearest home. Pins and route lines use each tech's color. Existing
appointment times are not moved. Jobs missing a technician are attached to
the owner. Only the owner can edit technicians. No SMS or email is sent.
Shop booking links, job edits, and Refresh map locations are unchanged.
The stored east/west label is still written by geocoding so older tools
keep working; it does not decide who drives or which slots are offered.

Each technician's day is one route. Offered times are grid arrivals that
fit the drive from the previous stop and the drive to the next stop, plus
a 20-minute job and a 15-minute buffer, including gaps between jobs.
`POST /api/public/book` and edits that change the time or address run that
check again and reject a conflict. A Surprise arrival and a San Tan Valley
arrival cannot share 8:00 AM. Shops are not offered an arrival after
5:00 PM. Nothing new is texted or emailed.

Deferred from the smart-scheduling plan (PR #12): shop-facing arrival
windows instead of a clock time, sliding later ETAs inside a window, the
per-day booking lock, the one-time +7 hour restamp, and a text when a
drag moves an ETA out of a promised window.

### Added — edit jobs and shop addresses (2026-11-11)
Dispatch job cards and the field job screen have an Edit button. It can change
the address, customer name, phone, email, vehicle, service, price, Phoenix
date and time, zone, and notes. `PATCH /api/jobs/{id}` saves that. A new
address is geocoded with Google when `GOOGLE_MAPS_API_KEY` is set (otherwise
the mock). An explicit zone still wins over the geocoded zone. Only an owner can
call `PATCH /api/jobs/{id}` or save a shop. Technicians and contractors,
including a contractor assigned to the job, get 403. Edit is hidden on
dispatch and the field screen unless the signed-in role is owner. The
shop booking link is unchanged.

Shops → Edit opens the existing shop form (name, address, contacts). Changing
the address re-geocodes that shop the same way.

`/book/:token` lists that shop’s upcoming jobs. The shop can edit the same
fields except price and zone, or cancel. The token cannot read or change
another shop’s jobs. Edits store `updated_at` and `edit_history` (who, when,
which fields). Editing and this cancel do not send SMS or email, and do not
change status unless the shop cancels.

### Added — Refresh map locations on dispatch (2026-11-11)
The owner dispatch board has a **Refresh map locations** button beside the route
map. It asks for confirmation, then `POST /api/admin/regeocode` with no date
(shops and jobs). The confirm copy states that this only updates coordinates
and sends no messages. The button shows shops and jobs counts for updated,
failed, and skipped, then reloads the day's jobs so the map uses the new pins.
No endpoint behavior changed.

### Fixed — route map tiles, booking notes, re-geocode (2026-11-11)
CARTO's public `dark_all` raster URL now returns one "API KEY REQUIRED" watermark
for every tile (same PNG, etag `wm-da89c20e77c1-dark`). The dispatch route map and
the shop day map use Esri World Dark Gray instead (street canvas plus a label
overlay). Those tiles load with no key. Attribution is Esri, HERE, Garmin,
OpenStreetMap contributors, and the GIS user community.

`POST /api/public/book` (and `POST /api/portal/book`, which calls it) accepts
optional `notes` (max 4000) and `customer_first_name` (max 80). Blank text is
stored as null. Both are written on the job; the first name is also on the
vehicle. The public page `/book/:token` collects them, including when an owner
opens Book a job and sets a custom time. The shop portal booking form does too.
Dispatch cards, the field job screen, and the portal job page show them.
A completion note replaces booking notes only when the technician types one.
Confirmation SMS is unchanged. Nothing new is emailed or texted.

`POST /api/admin/regeocode` is owner-only. With no query it re-geocodes every
shop and every job and writes coordinates and zone. Shops use `lat`/`lng`;
jobs use `job_lat`/`job_lng`. With `GOOGLE_MAPS_API_KEY` set it calls Google
and counts a failure as `failed` without writing the mock centroid. With no
key it uses the mock geocoder. `?date=YYYY-MM-DD` limits the run to jobs on
that America/Phoenix day and does not touch shops. The body is
`{"date": null, "shops": {"updated", "unchanged", "skipped", "failed"}, "jobs": {...}}`
(`shops` is null on a dated run). It does not send SMS or email and does not
change job status. A point outside the metro moves the pin and leaves zone as it was.

### Fixed — public booking and Phoenix slot clocks (2026-11-11)
`/book/:token` is routed. Logged-out visitors and a logged-in owner both reach
`PublicBooking`; the catch-all no longer sends that URL to the dashboard.
Shop detail has a Book a job button for that shop's token. An owner on the
booking page can type any time on the chosen date, which is stored as the
matching UTC instant (Phoenix is UTC−7, no DST).

Zone hours are America/Phoenix. West 08:00 is 15:00 UTC, not 08:00 UTC (which
displayed as 1:00 AM). East 14:30–19:00 crosses UTC midnight and stays on that
Phoenix day. `scheduled_start` is still a UTC ISO string. Dispatch, the route
map, and `formatTime` render it in America/Phoenix. Booking still logs a mock
SMS and does not send email.

### Changed — self-host deploy targets (2026-11-11)
The website is `thecalibrationcrew.us` and `www` (Vercel). The API stays
`api.thecalibrationcrew.us` (Render). `DEPLOY.md` no longer tells you to create an Atlas
user named `calibrationos`; any read/write user works, including `admin_db_user`.
`CORS_ORIGINS` should list both web origins. Assist calls itself at `http://127.0.0.1:$PORT`
when `ASSIST_SELF_BASE_URL` is blank, so Render's assigned port works. The login form no
longer prefills the dev owner password.

### Fixed — zero-length zone slots (2026-10-29)
`offered_slot_starts()` stepped by `slot_minutes`. A zone saved with `slot_minutes` of 0
(allowed by `PUT /settings/zones/{zone_key}`) never advanced the cursor, so availability
looped forever. Nonpositive lengths now raise before the loop, and the zone settings
endpoint rejects them with 400. Negative lengths are rejected too.

### Fixed — Phoenix day boundaries for the shop day map (and the same date window elsewhere) (2026-10-27)
Job queries treated a calendar date as UTC midnight-to-midnight and defaulted "today" to
`now_utc().date()`. The shop is in America/Phoenix (UTC−7, no DST), so a 6 PM Phoenix job is
01:00 UTC the next day and was missing from that Phoenix date. From 5 PM to midnight Phoenix,
"today" was already tomorrow.

- **New `backend/business_time.py`** (stdlib `zoneinfo` only). `business_date()` is the Phoenix
  civil date of an instant (default: now). `business_day_bounds()` is that day's half-open window
  as UTC datetimes (07:00 UTC through 07:00 UTC next day). Naive datetimes are UTC, same as the
  rest of the backend.
- **Query windows and default dates** now use that helper: `GET /portal/day-map`, `GET /jobs`,
  `GET /dashboard/summary`, `POST /jobs/reorder`, `compute_available_slots` (availability),
  `POST /public/book` (previous-job drive time and `sequence_order`, using the Phoenix date of
  the start instant), and `POST /public/availability` ("today" for the past / 21-day checks).
  Assist tools that call `/jobs` and `/dashboard/summary` pick this up with no tool changes.
- **Not changed:** zone start/end clocks (`08:00`–`19:00`) are still combined as UTC wall times.
  Those slots are 1:00 AM–12:00 PM Phoenix, so they stay on the same civil date. Reinterpreting
  them as Phoenix local time would shift every existing appointment by 7 hours.
- **Portal date pickers** (`frontend/src/lib/api.js` `phoenixTodayStr`, `Intl` `America/Phoenix`,
  no new dependency). The day map's initial date and the portal booking date input's min/max were
  `toISOString().slice(0, 10)` (the UTC date). They now use today's Phoenix date. Booking's max is
  that date plus 21 days (Phoenix has no DST, so 21×24h lands on the same civil date). Owner
  dashboard, field app, and public booking already used the browser's local calendar date
  (`todayStr` / `dateStr`), not a UTC timestamp, and were left as they are.
- **Drive times:** `get_drive_time` already cached real Distance Matrix results in `drive_time_cache`
  (rounded coordinates, TTL index left at 2 days). The cache day was the UTC date, so it rolled at
  5 PM Phoenix. It now uses the Phoenix date. No second cache. `GET /portal/day-map` runs the
  per-other-shop lookup concurrently (`asyncio.gather`, order preserved). The mock path stays
  uncached. No new dependency.
- **Tests:** `backend/tests/test_business_time.py`. A 6 PM Phoenix instant on 2026-10-27 is inside
  that Phoenix day's bounds (and its ISO string sorts inside them) and outside the old UTC-midnight
  window. January and July offsets are both −07:00. Existing 08:00–19:00 UTC slot clocks stay on
  the labeled day.
- **Slots stay on the day they are offered** (review follow-up). Zone hours are still UTC wall
  clocks, including hours saved via `PUT /settings/zones/{zone_key}`. A zone of `05:00`–`10:00`
  was offering 05:00 UTC, which is the previous Phoenix evening, so the booking did not match
  the Phoenix-day job query and the slot could be offered again. `offered_slot_starts()` skips
  those starts. `POST /jobs/reorder` clamps a computed start that would fall before the Phoenix
  day up to that day's start, and still rejects a start that would land on a later day.
  Default 08:00 UTC zones are unchanged.
- **One paid lookup per drive-time key.** `asyncio.gather` on the day map let jobs that share a
  rounded destination all miss an empty cache and each call Google. `coalesce()` shares the
  in-flight request for a `drive_time_cache_key`. The mock path is still uncached.

### Added — Impeccable design guidance (no runtime dependency)
Vendored the Impeccable skill (v4.8.0, Apache 2.0, Paul Bakaus, commit
`d34c87e`) as agent guidance so later UI work does not drift into generic
AI-looking design. Markdown only: `.cursor/skills/impeccable/SKILL.md` plus
`reference/`, with `LICENSE` and `NOTICE`. The upstream `scripts/` launcher
and live-browser bundle are not included, and `impeccable` is not a package
dependency. `.cursor/rules/impeccable-design.mdc` and a short section in
`CLAUDE.md` point at the skill and record the brand.

Brand orange is **#FF5F1F** (`--accent`) for fills. Small text on gunsteel uses
`--accent-ink` (#FF7E1E); text on an orange tint uses `--accent-on-tint`. A
`npx impeccable detect` pass (source regex on `frontend/src`, plus a rendered
scan of login, dashboard, portal jobs, and a job detail page) found no regex
hits and a short list of rendered issues. Fixed only the trivial ones: muted
label contrast, zone-header and east/west badge contrast, white-on-blue map
pins, the Leaflet attribution bar, the 10px "Shop Portal" tag (floor is now
12px), the "Dispatch board" kicker above the date heading, and the skipped
heading on the job detail page (`h3` → `h2`, same visual class), and the
zero-offset orange glow on a new job card. A rescan of those four rendered
pages reports no remaining findings. Not done here: a layout or type redesign,
and installing Impeccable's hooks or CLI as a dependency.

### Added — Real card charging via Stripe (2026-07-21)
Wires up the Charge Queue, which previously listed completed jobs with a card on file but had no
way to actually bill them — the "Charge Now" button existed in the UI but was disabled
("next iteration"). This was the last open code launch-blocker.

- **New module `backend/charging.py`** — pure, stdlib-only, unit-tested: `cents()` (dollar→cent
  conversion, handles float noise like `0.1+0.2`), `chargeable_reason()` (centralized eligibility
  check — job complete, not already charged, shop has a Stripe customer + card on file),
  `interpret_payment_intent()` (classifies a PaymentIntent's status into succeeded /
  requires_action / other), `decline_message()` (formats a card decline for the owner).
- **`POST /api/charge-queue/{job_id}/charge`** (owner-only) — creates and confirms an off-session
  Stripe `PaymentIntent` for the job's price against the shop's stored `stripe_customer_id` +
  `stripe_payment_method_id`. **Idempotent per job** (`idempotency_key=f"charge-job-{job_id}"`) so
  a double-click or retried request can never double-charge — Stripe dedupes concurrent requests
  sharing a key on its own. On success: sets `charged_at`, `charge_method: "stripe"`,
  `stripe_payment_intent_id`, `charged_amount` on the job (removing it from the queue, whose query
  already filters on `charged_at` not existing). On a card decline (`CardError`) or a stuck
  `requires_action` state (rare — issuer wants authentication the app can't complete without the
  shop present): the job is **not** marked charged, a `charge_error`/`charge_error_at` is recorded
  and returned to the owner, and the job stays in the queue for a retry. Never fails a booking flow
  — this is an owner-initiated action, not automatic.
  - Fixed while wiring this up: `stripe.error.CardError`'s `decline_code` is **not** a direct
    attribute of the exception — it lives on the nested `e.error` object
    (`e.error.decline_code`). Verified against the installed `stripe` package source directly
    rather than assumed.
- **`POST /api/charge-queue/{job_id}/skip`** (owner-only, optional `reason`) — the "Skip / Bill
  Manually" escape hatch already stubbed in the UI. Marks the job `charge_method: "manual"` and
  sets `charged_at` (leaves the queue) without touching Stripe — for jobs the owner wants to
  invoice outside the app.
- **Frontend** (`frontend/src/pages/ChargeQueue.jsx`) — both buttons wired: per-row busy state,
  inline decline/error messages (from the request and, on reload, from the persisted
  `charge_error` field so a prior failure is still visible after a page refresh), confirmation
  dialog before skipping.
- **Tests:** `backend/tests/test_charging.py` (14 pure tests) — cent conversion incl. float-noise
  cases, every eligibility-rejection reason, PaymentIntent status interpretation, decline-message
  formatting. No live Stripe call is testable/mocked in this pass (consistent with how the Xero
  and Google Maps integrations were tested — pure logic only; no CI or Stripe test key available
  in this environment). **Recommended before relying on this in production:** run one real charge
  through Stripe **test mode** (`sk_test_...` key + card `4242 4242 4242 4242`) end-to-end.
- **No new env var** — reuses the existing `STRIPE_API_KEY` (already required for card capture).
  Charging is only guarded by the same "is this the placeholder key" check already used elsewhere.
- **Deliberately not built here:** automatic charge-on-completion (this stays a reviewed,
  owner-triggered action from the queue, matching the page's own original design intent), and
  webhook-based handling of `requires_action` (would need `STRIPE_WEBHOOK_SECRET` + a registered
  endpoint — out of scope for a Friday launch; the rare stuck case is surfaced to the owner
  instead of silently retried).

### Added — Real Google Maps (geocoding + drive time), credential-optional (2026-07-21)
Mirrors the existing Stripe/Resend/Xero "real-if-key-present, else mock" pattern: when
`GOOGLE_MAPS_API_KEY` is set, addresses are geocoded and drive times computed via the real Google
Geocoding + Distance Matrix APIs; otherwise the app falls back to the existing mock exactly as
before, so nothing breaks without a key. This was the last of the three launch-blocking mocks
(Stripe/Resend/Xero already real; Twilio is on hold, not required for MVP).

- **New module `backend/google_maps.py`** — stdlib-only, unit-tested request-param builders +
  response parsers for both APIs, shared by the real path (server.py has no parsing logic of its
  own). Uses the same Phoenix-metro bounding box the mock always used (now imported from this
  module into `mock_geocode` too, so real and mock never disagree on what's "in service area").
- **`geocode_address()` / `get_drive_time()`** (`backend/server.py`) replace all 10 real call
  sites (`mock_geocode`/`mock_distance_matrix` calls in shop create/edit, public booking
  availability + booking, contractor home-address edit, dispatch reorder, and the shop-portal day
  map). Both fall back to the mock on any error (bad address, quota, network) so a Maps hiccup
  never fails a booking — same resilience pattern as Xero invoice creation. The demo-shop seeder
  deliberately keeps calling the mock directly (fake addresses, no reason to spend a real API call).
- **Daily-cached drive times** (`drive_time_cache` collection, new) — `portal_day_map` calls
  `get_drive_time` once per other-shop job in a loop, so repeated calls for the same
  origin/destination/day are served from cache instead of re-hitting the API on every page load.
  Cache key rounds coordinates to ~11m precision and includes the calendar day; a TTL index
  (`cached_at`, 2 days) auto-expires old entries so the collection self-bounds. This is the "daily
  caching" the roadmap already called for.
- **`GET /api/integrations/status`** — `google_maps` now reports real `configured`/`connected`/
  `mode` instead of the hardcoded `false`/`mock` stub.
- **Frontend** — Settings → Integrations' Google Maps row is now driven by live status (previously
  a hardcoded "Mock" label, unlike Xero/Growth/Assist which were already dynamic).
- **New env var:** `GOOGLE_MAPS_API_KEY`. No new Python dependency (`requests` already present,
  same as Xero).
- **Tests:** `backend/tests/test_google_maps.py` (15 pure tests — geocode/distance-matrix parsing,
  error statuses, the metro bounding box, and cache-key rounding/day-rollover). Backend integration
  tests (`backend/tests/test_*.py` that hit a live server) were not run in this environment — they
  exercise these code paths in mock mode only (no `GOOGLE_MAPS_API_KEY` set), which is unchanged.
- **Not addressed here:** real-time traffic (Distance Matrix `departure_time`) — the scheduling
  algorithm doesn't model time-of-day traffic today, mock or real; out of scope for this pass.

### Security — Production hardening pass, part 1 (2026-07-21)
First launch-blocker cleanup: get the app out of its "demo defaults" configuration so it's safe to
expose to real shops. **Fully backward-compatible** — everything is gated on a new `APP_ENV` flag
that defaults to `development`, so local runs, CI, and the current Emergent deployment behave exactly
as before until `APP_ENV=production` is set. No route, schema, or data-model changes.

- **Env-driven seed credentials (`backend/server.py`).** The owner/contractor accounts no longer ship
  a hardcoded password. Owner password now comes from `OWNER_PASSWORD` (contractor from
  `CONTRACTOR_PASSWORD`); outside production they fall back to the previous dev defaults so tests are
  unchanged. **The seeded password is no longer written to the logs.**
- **Password rotation on mismatch.** If `OWNER_PASSWORD` / `CONTRACTOR_PASSWORD` is set and an account
  already exists with a different password, startup rotates the stored hash to match. This is how the
  historically-exposed default gets fixed on the existing production DB: set the env var, restart.
- **Demo data gated.** The three demo shops (and the demo-derived Module 9 partner contacts) seed only
  when `SEED_DEMO_DATA=true`, which defaults on in development and **off in production** — so a real
  deployment starts clean instead of pre-populated with Safelite/AutoGlassNow/Glass Doctor fakes.
- **Startup security self-check (`security_self_check()`).** Logs a clear posture report and warns on
  the public dev `JWT_SECRET`, the placeholder `STRIPE_API_KEY`, wildcard `CORS_ORIGINS`, and a
  missing `OWNER_PASSWORD`. In production only, it **fails closed** (refuses to boot) if `JWT_SECRET`
  is still the public dev default — so the app can't be launched signing tokens with a known secret.
- **New env vars:** `APP_ENV`, `OWNER_PASSWORD`, `CONTRACTOR_PASSWORD`, `OWNER_EMAIL`,
  `CONTRACTOR_EMAIL`, `SEED_DEMO_DATA`. Existing `JWT_SECRET`, `STRIPE_API_KEY`, `CORS_ORIGINS` are
  now checked at startup. Full list + launch steps in `EMERGENT.md`.
- **Not yet addressed (still open launch blockers):** live Stripe key + actual card-charging code is
  still not wired (the charge queue lists jobs but nothing bills the card), and Google Maps drive-times
  are still mocked. Tracked for the next passes.

### Added — Module 8: Admin Assist Engine v1 (2026-07-09)
Natural-language admin copilot built into the owner dashboard. Chat widget on every owner page;
reads answer instantly from live data, every real action (dispatch, cancel, reschedule, pricing,
shop edits, growth touches/intros) stops at a confirmation card the owner must approve. Activates
when `GOOGLE_API_KEY` (Google AI Studio) is set in env; inert otherwise.

- **New package `backend/assist/`**:
  - `tools.py` — 31 tools wrapping the app's own existing `/api/*` endpoints over localhost with
    the owner's JWT (no direct DB access; a bad LLM call fails normal request validation). Tier =
    HTTP verb: GET → safe (inline), POST/PUT/PATCH → risky (confirm-gated).
  - `agent.py` — hand-rolled Gemini tool-calling loop (`google-genai`, `gemini-2.5-flash`,
    FunctionDeclarations only so the SDK can never auto-execute; max 6 tool rounds). Includes a
    deterministic `/run <tool> {json}` escape hatch used by tests and power users.
  - `routes.py` — `POST /api/assist/message`, `POST /api/assist/actions/{id}/confirm|cancel`
    (5-min expiry, configurable), `GET /api/assist/conversations/{id}`, `GET /api/assist/tools`.
    All owner-only.
- **Deliberately NOT google-adk:** every ADK release requires `fastapi>=0.115`; this app pins
  `fastapi==0.110.1`. The plain `google-genai` SDK has no FastAPI dependency, so the existing
  app's framework stays untouched.
- **New collections:** `assist_conversations` (chat history), `assist_pending_actions`
  (propose→confirm state). **Reused:** `ai_action_log` (Module 9's audit collection — Module 8
  now writes `assist_propose|confirm|cancel|execute` rows to it, as originally intended).
- **`GET /api/integrations/status`** gained an `assist` key (`configured`/`enabled`/`mode`).
- **Frontend:** new `frontend/src/components/Assist.jsx` floating chat widget mounted in
  `Shell.jsx` (owner role only) with confirmation cards; Assist status row in
  Settings → Integrations. Self-guards on `REACT_APP_ASSIST_MODULE_ENABLED` and on the backend
  status flag — renders nothing when the module is off.
- **New deps:** `google-genai`, `httpx`. **New env:** `GOOGLE_API_KEY` (required to activate),
  `ASSIST_MODULE_ENABLED`, `ASSIST_MODEL`, `ASSIST_PENDING_TTL_SECONDS`, `ASSIST_SELF_BASE_URL`,
  `REACT_APP_ASSIST_MODULE_ENABLED`.
- **Tests:** `backend/tests/test_assist.py` (13 deterministic tests — RBAC, tier gate,
  propose→confirm→execute, propose→cancel, expiry, failure surfacing, persistence). Also
  verified end-to-end against real Gemini: NL read answered inline, NL price change gated then
  executed on confirm, expired action rejected with 410.
- **Fixed a race condition** in the confirm/cancel pending-action handlers (`routes.py`): the
  status check-then-update was non-atomic, so two near-simultaneous confirm/cancel calls on the
  same action could both pass validation. Now claimed atomically via a single `find_one_and_update`
  filtered on `status: "pending"`, so only the first caller wins and the second gets its expected
  400. Re-verified with a full live run (disposable MongoDB container + real `uvicorn` server, not
  mocks): `pytest tests/test_assist.py` 13/13 pass and `pytest tests/test_growth.py` 9/9 pass
  (Module 9 unaffected).
- **Deferred (documented in `docs/module8/README.md`, not silently dropped):** the original
  Cloud Run/ADK/Vertex/Postgres architecture and the VIN-OEM checklist / scan-audit / multi-day
  workflow concepts; Invoices/Charges/Messages/Invites tools are the named fast-follow.

### Added — Module 9: Partner Growth Engine v1 (2026-07-08)
Power Connector 5+50+100 CRM + 3-D introductions, built out from the previously-inert scaffold.
Flag now **defaults on** (`GROWTH_MODULE_ENABLED=true`, `REACT_APP_GROWTH_MODULE_ENABLED=true`).
**Reels are explicitly deferred** — no video-generation capability exists in this environment, so
`ReelAsset`/`POST /api/growth/reels/generate` are not implemented rather than shipped as a
misleading stub.

- **New module `backend/growth/routes.py`** — `build_growth_router(db, require_owner,
  mock_send_sms, send_email)` factory (avoids a circular import with `server.py`), included
  conditionally from `server.py` only when `GROWTH_MODULE_ENABLED` is true.
- **New endpoints** (all under `/api/growth/*`, owner-only):
  `GET/POST /contacts`, `PATCH /contacts/{id}` (circle changes cap-enforced, 409 on overflow),
  `GET /grid`, `GET /nudges/today`, `GET /touches`, `POST /touches/{id}/approve|send`,
  `GET/POST /intros`, `POST /intros/{id}/approve|send`.
- **Real dispatch on send** — reuses the existing `mock_send_sms` (sms channel) and `send_email`
  (email channel, Resend-if-configured else logged) helpers; no new outbound-comms code. Sending
  updates the contact's `favors_given`/`favors_asked`/`last_touch_at`/`next_touch_due`.
- **`backend/growth/models.py`** — implemented the previously-stubbed `enforce_grid_caps()`
  (idempotent corrective sweep, demotes overflow one tier down) and `generate_daily_nudges()`
  (deterministic, no LLM, idempotent per calendar day via a new `nudge_date` field on `Touch`).
- **New collections:** `partner_contacts`, `touches`, `intros`, `ai_action_log` (a minimal audit
  trail written on every approve/send — not dependent on Module 8 existing).
- **Seed data** extended: `partner_contacts` seeded from the 3 real demo shops + the owner as
  `top5` entries (not the doc's aspirational fake Phoenix contact list); `key50`/`vital100` start
  empty.
- **`GET /api/integrations/status`** gained a `growth` key (`enabled`, `contact_count`,
  `counts_by_circle`).
- **Frontend** — `frontend/src/pages/growth/Growth.jsx` rewritten from a static placeholder into a
  real page: circle-grouped contact grid with an add-contact form, a Today's Nudges panel
  (approve/send), and a 3-D intro creator/list. Routed at `/growth`, added to the owner nav
  (`Shell.jsx`), and a status row added to Settings → Integrations. Still self-guards on
  `REACT_APP_GROWTH_MODULE_ENABLED` so it can be flipped back to the old placeholder without a
  redeploy.
- **Tests** — `backend/tests/test_growth.py`: RBAC, contact CRUD, cap enforcement (409 then
  succeeds after a demotion), nudge-generation idempotency, touch approve→send lifecycle
  (send-before-approve rejected), intro approve→send (favor bump on both sides, email required on
  both sides).

### Docs — context/priority sync (2026-07-08)
Doc-only session per user request ("before we do any building... update so everything is current,
all context is pushed and saved"). No runtime changes.

- **Added `docs/module8/README.md`** — the Module 8 (Agentic AI Assist Engine) system-context
  handoff doc, which existed only outside the repo until now. Design-only spec for a Google
  ADK 2.0 / Gemini / Cloud Run / Postgres-Supabase agentic layer (VIN-triggered OEM setup
  checklists, dual-invoicing + compliance audit workflow, long-running ticket lifecycles with HITL
  gates). Flagged in `CLAUDE.md` as a significant stack deviation needing its own approval pass
  before implementation.
- **Landed the Module 9 (Partner Growth Engine) scaffold onto `main`**, previously stranded on the
  unmerged `feature/module9-partner-growth` branch: `backend/growth/models.py` (`PartnerContact`,
  `Touch`, `Intro`, `ReelAsset` Pydantic models + nurture templates for the Judy Robinett Power
  Connector 5+50+100 method), `frontend/src/pages/growth/Growth.jsx` (flagged placeholder page),
  `docs/module9/README.md`. Everything is inert behind `GROWTH_MODULE_ENABLED=false` — not imported
  by `server.py`, not routed in the frontend. User has flagged this module as the next build
  priority, ahead of Twilio/Module 8.
- **Xero → QuickBooks:** recorded that the business's newly-hired CPA uses QuickBooks exclusively,
  so the Xero integration may be replaced. No code changed; Xero remains exactly as shipped in Step 1
  (live-capable, mock-fallback) until a migration is explicitly scoped and approved.
- **Twilio SMS (Step 2) deprioritized:** the user confirmed it's not required for MVP. Removed it as
  the "active task" in `CLAUDE.md`; it's on hold, not scheduled.
- Updated `CLAUDE.md` and `EMERGENT.md` system-status/roadmap sections accordingly, and added a
  "Modules beyond the core platform" pointer section to `CLAUDE.md` so future sessions check
  `docs/moduleN/` before starting related work.

### Docs
- **Status check-in (2026-07-03):** refreshed `CLAUDE.md` to reflect that Step 1 (real Xero invoicing)
  is done and merged to `main` (PR #1), moved the active task to Step 2 (real Twilio SMS), and recorded
  the open action items on Emergent's side: (1) Xero is live-capable but not yet live — needs env vars +
  owner connect; (2) verify the frontend build on Emergent/Vercel; (3) reconcile the version mismatch
  between `CHANGELOG.md` (0.0.3) and `frontend/package.json` (0.1.0). No code or runtime changes.

## [0.0.3] — 2026-06-16 — Claude Code session (Step 1: real Xero invoicing)

### Added
- **Collaboration bridge docs:** `CLAUDE.md` (project constitution + Emergent runtime rules),
  `EMERGENT.md` (return-handoff instructions for Emergent AI), and this `CHANGELOG.md`.
- **`.claude/` dev tooling** (web sessions only): SessionStart hooks that install the gstack and
  curated awesome-claude-skills packs. No effect on app runtime or Emergent hosting.

### Added — Step 1: real Xero invoicing (credential-optional)
Real Xero OAuth 2.0 + REST API integration that mirrors the existing Stripe/Resend pattern: when
Xero credentials are configured **and** the owner has connected, completed jobs create real **draft**
invoices in Xero; otherwise the app falls back to the existing mock so nothing breaks without creds.
Implemented with the already-present `requests` library wrapped in `asyncio.to_thread` (no new
dependency), matching the existing Resend code.

- **New module `backend/xero_invoice.py`** — stdlib-only, unit-testable builder for the spec's exact
  invoice payload (Line 1 = calibration label @ rate; Line 2 = `LASTNAME / YEAR MAKE MODEL / VIN` @
  $0.00; ACCREC, DRAFT, due +30 days). Shared by both the real and mock paths so they're identical.
- **New endpoints** (`backend/server.py`, all under `/api`):
  - `GET /auth/xero/connect` — returns the Xero authorize URL (owner only; signed-JWT `state`).
  - `GET /auth/xero/callback` — exchanges the code, fetches the tenant via `/connections`, stores
    tokens on the owner record, redirects to `/settings?xero=connected|error`.
  - `POST /auth/xero/disconnect` — clears stored Xero tokens.
  - `GET /integrations/status` — per-integration configured/connected/mode (backs the Settings UI).
  - `POST /integrations/xero/poll` — polls Xero and syncs invoice status DRAFT→AUTHORISED→PAID onto
    jobs (spec's ~4-hour poll; call on a schedule or from the dashboard).
- **Token handling** — access/refresh tokens + expiry + tenant id + org name stored on the owner
  `technicians` record; auto-refresh before calls, persisting Xero's rotated refresh token.
- **Invoice creation** — `create_invoice_for_job()` dispatcher: real Contact lookup/create, ACCREC
  draft invoice, and **PDF attachment** of the technician's uploaded calibration document when present.
  Real invoices are also stored in a new `xero_invoices` collection; `GET /invoices` now merges real +
  mock.
- **Admin notification** — the invoice-created notice to `ADMIN_EMAIL` now goes through `send_email`
  (real via Resend if configured, else logged), instead of a bare DB insert.
- **Seed change** — the owner record now starts with `xero_connected: false` and empty token fields
  (real connection happens via OAuth). `mock_xero_create_invoice` now reuses the shared payload
  helpers and tags invoices `provider: "mock"`.
- **Frontend** — Settings → Integrations now shows live Xero status with **Connect Xero / Disconnect**
  buttons and a success/error banner after the OAuth redirect.
- **Tests** — `backend/tests/test_xero_invoice.py` (pure, runs anywhere) asserts the spec-exact
  invoice format, account-code configurability, and VIN/last-name fallbacks.

**New environment variables** (set in Emergent env settings; never commit): `XERO_CLIENT_ID`,
`XERO_CLIENT_SECRET`, `XERO_REDIRECT_URI`, and optional `XERO_SALES_ACCOUNT_CODE` (default `200`),
`XERO_POST_CONNECT_REDIRECT` (default `/settings`). The Xero app's redirect URI must equal
`XERO_REDIRECT_URI` and point at `<app-domain>/api/auth/xero/callback`.

### Still mocked / not yet done
- Twilio SMS, Google Maps (geocoding + Distance Matrix), Google Calendar, and cloud document storage
  remain mocked/deferred — these are later steps.

---

## [0.0.x] — Emergent AI baseline (through 2026-06-11)

Built and iterated by Emergent AI. Stack: FastAPI + MongoDB (Motor) backend, React 19 (CRA/CRACO)
SPA frontend, JWT auth. Integrations intentionally mocked for the first builds (see `memory/PRD.md`).

### Iteration 1 — Core platform (15/15 backend tests passing)
- JWT auth (`/api/auth/login`, `/api/auth/me`), bcrypt hashing, owner/contractor RBAC.
- Reference data (`/api/reference/zones`, `/api/reference/pricing`); seed: owner, contractor, 3 shops.
- Mock geocoding (`/api/geocode`) over Phoenix-area cities; zone detection (west < -112.0, east > -111.8).
- Shop CRUD (owner-only) with auto-geocode, zone assignment, booking-link token, terms signing.
- Public booking: shop lookup by token, drive-time-aware slot availability algorithm, booking creation.
- Job lifecycle (booked → driving → on_site → complete), price locked at booking, custom per-shop rates.
- On completion: mock Xero draft invoice (spec's 2-line-item format), mock completion SMS, admin notice.
- Mock SMS log and mock invoice list for UI introspection.

### Iteration 2 — Live booking alerts
- New-booking alert pipeline (`/api/notifications/new-bookings`, `/api/notifications/mark-seen`);
  dashboard alert pill + NEW badge (5s polling).

### Iteration 3 — Contractor dispatch, settings, routing
- Contractor offers with 30-minute expiry, accept/decline, owner visibility, auto-expire back to board.
- Editable settings (standard pricing, zone times/limits, contractor profile).
- Drag-and-drop job reorder with drive-time recalculation.

### Iteration 4 — Field operations hardening
- "At-risk" job detection (overdue start / overrun) surfaced on the dashboard.
- Reschedule and cancel (with reasons) + SMS side-effects.
- Real document upload (multipart, base64-in-Mongo, 10 MB cap, RFC 5987 download) with spec filename.
- Public shop status / scorecard page (`/api/public/shop-status/{token}`).

### Shop self-service portal (additional)
- Email invites via Resend (`/api/invites`), shop-user registration, Stripe card capture (setup mode),
  portal auth + booking + day-map, and a charge queue for completed jobs.
