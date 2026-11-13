# Glass shop onboarding audit

As implemented on 2026-11-13, from the marketing Sign Up link through the first booked job. This is the path in the current code, including the production behavior checked against Render logs for the 20:30 UTC test signup.

Ratings: 1 is bloated, 5 is optimized. Effort for the target flow is S (one module, little risk), M (a few modules, needs a careful test), L (crosses signup, auth, billing, and mail).

Business rules the target flow keeps: a card is saved in Stripe at signup, and a pop-up records that completed jobs may be charged. Every completed job is charged unless the shop asked for an invoice. An invoice has 7 days, then one $25 late fee. Prices are Static $125, Dynamic $125, Dual $175, Tesla $225. A $30 trip fee applies outside the service area, or instead of the calibration price when the job cannot be done because of a bad install or the customer/vehicle. There is no late-cancel fee and no waiting fee. A bad calibration is redone free within 30 days.

The code also has a Triple / Subaru price of $185 (`STANDARD_PRICING` in `backend/server.py`, and the same number hardcoded in `frontend/src/pages/PortalBook.jsx`). The agreement text does not mention Triple.

## What the shop and the owner do today

### 1. Find Sign Up on the marketing site

**Who sees what.** A logged-out visitor on `www.thecalibrationcrew.us` gets the public site (`frontend/src/App.js` route `/`). The header and footer in `frontend/src/marketing/SiteChrome.jsx` have Sign up and "Create a shop account". The home page (`frontend/src/marketing/HomePage.jsx`), pricing, services, about, FAQ, and contact pages repeat "Create your shop account" linking to `/signup`. The home copy says Caleb sends the setup link.

**Do.** Click Sign up. No fields yet.

**Code.** `frontend/src/marketing/HomePage.jsx`, `InfoPages.jsx`, `ContactPage.jsx`, `SiteChrome.jsx`. No API call. No email.

**Friction.** The same pitch is repeated on every marketing page. The home "From signup to the report" section describes a flow (Caleb sends a link, then the shop books) that is longer than the screens that follow. Staff login is a separate `/login` and is easy to miss if a shop clicks the wrong door later.

**Rating: 4.** The entry point is one click and the label matches the form. The repeated pitch is the only extra weight.

### 2. Request a shop account

**Who sees what.** `/signup` (`frontend/src/marketing/SignupPage.jsx`) is "Request a shop account". The lede says this does not create a password. Fields: shop name, contact name, mobile, email, shop address. The address box is `frontend/src/components/AddressField.jsx`. If `REACT_APP_GOOGLE_MAPS_API_KEY` is set, Google Places suggests addresses inside a Phoenix Valley box. The helper text says to pick the shop from the suggestions. The button says "Request a shop account" and changes to "Sending…".

**Do.** Fill five fields. The address can be typed or picked from Places. Submit once.

**Code.** `POST /api/public/shop-requests` (`create_shop_request` in `backend/server.py`). The body is `ShopRequestIn`: `shop_name`, `contact_name`, `mobile`, `email`, `address`, `place_id`, `address_confirmed` (default false), `confirmed_address`. The server checks the contact (`shop_contact_errors` in `backend/onboarding.py`: name, 10-digit mobile, email, address) and geocodes with `geocode_address`. A missing Maps key, a Google failure, a partial match, or a point outside the valley is a 400. A real in-valley result that the shop has not confirmed is a **409** with `code: "needs_confirmation"` and `formatted_address`.

**Email.** None on this first submit. The 409 is returned before the insert.

**Friction.** Places can fill the address, and the page still sends `address_confirmed: false`. The server always answers 409 the first time, even when the shop picked a suggestion. The shop has to submit, read an error, and submit again. Autocomplete does not complete the step.

**Rating: 2.** Five fields is reasonable. Forcing a second submit after a successful lookup is a dead step.

### 3. Confirm the address and submit again

**Who sees what.** After the 409, the form stays filled and a checkbox appears: "Use this address: {formatted address}". The error line says "Check the address below, then send the request." Checking the box copies the formatted address into the field. Editing the address clears the checkbox.

**Do.** Check the box. Click "Request a shop account" again. Wait on "Sending…".

**Code.** Same `POST /api/public/shop-requests`. `address_confirmed: true` and `confirmed_address` must match the geocoded string after letters and digits are compared (`addresses_match`). On success the handler inserts one document in `shop_requests` (id, shop, contact, normalized mobile, lowercased email, formatted address, lat/lng, place id, zone, `status: "pending"`, `created_at`) and returns `{ok, message: "Caleb will send your setup link shortly."}`. The page replaces the form with that sentence and a link to `/portal/login`.

**Email.** One owner alert, sent through `send_email` (Resend when `RESEND_API_KEY` is set). This path does not use the shop-mail hold. Subject: `Shop account request — {shop name}`. Body: contact, shop, mobile, email, address, and "Open Requests in CalibrationOS to approve and send the invite." Kind `shop_request`. Reply-To is the owner address. The 20:30 UTC test (`TEST Jarvis Signup Shop`) returned 200 and that email was delivered.

**Friction.** The shop is told a setup link is coming. Nothing on this screen creates an account, and the login link goes to a portal that does not exist yet. A duplicate shop name or email is not checked here. Two requests for the same shop both land as `pending`. If the insert cannot be read back, the handler now returns 500 and does not send the owner email (see the fix in this change). A Maps outage blocks signup with "We couldn't find that address". Closing the tab after the success screen is safe: the request is already stored. Closing the tab between the 409 and the second submit loses nothing but the checkbox; they start the confirm step again.

**Rating: 2.** The confirm step is a checkbox that restates an address the server already found. It exists to stop a bad pin, and it costs a full extra round trip.

### 4. Owner opens Requests and approves

**Who sees what.** The owner signs in at `/login` and opens `/requests` (`frontend/src/pages/Requests.jsx`, owner-only). The page says approve creates the shop and emails the setup link. The table columns are shop, contact, address, status, and Approve / Decline for `pending` rows. An empty list says "No requests yet." A failed load now says it could not load, and does not use that empty line.

**Do.** Click Approve or Decline. Approve waits, then shows a note. Decline removes the pending actions and sets status `declined`.

**Code.** `GET /api/shop-requests` (`list_shop_requests`, owner JWT). `POST /api/shop-requests/{id}/approve` creates the shop with `requires_billing_setup: true`, issues one invite, and marks the request `approved` with `shop_id` and `invite_id`. `POST /api/shop-requests/{id}/decline` sets `declined`. Approve does not call the duplicate check. `acknowledge_duplicate=True` is set on the shop payload and then ignored, so a second approval of the same name or email creates a second shop.

**What the 20:33 UTC test actually did.** Render logged `GET /api/shop-requests` 200 at 20:33:45 and again at 20:33:54 (reload), from the same signed-in browser that had just logged in. The production bundle sets the table from that JSON body. "No requests yet." renders only when the array length is 0. CORS allows `https://www.thecalibrationcrew.us` and `https://thecalibrationcrew.us`, so the browser could read a non-empty array. The list was empty. The insert and the list use the same `shop_requests` collection in the same process. Locally, with Motor 3.7.1 and PyMongo 4.19, that round trip returns the new row. The production list was a sorted find, and the Mongo client honored `readPreference` on `MONGO_URL`. Either one can hide a document the insert already acknowledged. The list now reads the primary with no server-side sort.

**Email.** None from the list or from Decline. Approve tries to email the invite (next step).

**Friction.** The owner has no request to approve until this list works. There is no badge on the nav, so the only signal is the email. Reload used to look the same as "nobody has signed up."

**Rating: 2.** One click to approve is right. A list that can miss the only row blocks the whole launch.

### 5. Invite is created, and the shop may not receive it

**Who sees what.** After Approve, the Requests note is either "Shop created and the invite was sent to {email}" or "Shop created. Invite was not delivered…". The note does not show the link. `/invites` (`frontend/src/pages/Invites.jsx`) lists invitations and has a send form. The table columns are shop, email, status, email delivery, expires, and Resend. The setup URL is shown, with a Copy link button, only in the "last created" box after Send or Resend on that page. It is not in the table. The 20:34 UTC visit to `/invites` correctly showed no invitations, because Approve had not run.

**Do.** If the email was held or failed, the owner opens Invites and clicks Resend to reveal a URL, then copies it. Resend revokes the previous token and mints a new 14-day one.

**Code.** `_issue_invite` in `backend/server.py`. The URL is `FRONTEND_URL + /portal/invite/{token}` (`invite_register_url`). The browser origin is ignored on purpose. Token is 14 days, status `pending`. Delivery goes through `_send_booking_message` with audience `shop` and kind `invite`.

**Email.** Subject `Set up {shop} with The Calibration Crew`. HTML says the link expires in 14 days and that the shop will choose a password, sign the agreement, and save a card. Reply-To is the owner. `SHOP_EMAILS_ENABLED=false` holds this mail in `email_outbox` (Email preview) unless the address is on `TEST_EMAIL_ALLOWLIST`. Held invites store `email_status: "held"`. The Requests page treats anything other than `sent` as "not delivered", including held. The owner can copy a link when `register_url` exists and they Resend from `/invites`.

**Failure.** Production startup at 20:12 UTC logged `FRONTEND_URL is not set`. With that blank, `_issue_invite` stores `register_url: null` and `email_status: "failed"`. There is no link to copy until `FRONTEND_URL` is set (no trailing slash, the public site). A failed send returns the error string on the request note. An expired or revoked link is the next step. Closing the tab here changes nothing: the shop and the invite are already saved.

**Rating: 2.** The invite is one record and one email, which is the right shape, and the owner cannot see the link on the screen that just created it. With shop mail held and `FRONTEND_URL` unset, Approve cannot finish onboarding.

### 6. Shop opens the invite and creates a password

**Who sees what.** `/portal/invite/:token` (`frontend/src/pages/PortalRegister.jsx`) loads "Set up {shop}". Fields: your name, email (disabled, from the invite), password, confirm password. Below that, the full service agreement (`AgreementView`, sections from the invite payload). Then "Type your name to sign" and a checkbox: "I am allowed to sign for this shop. My typed name is my signature." The button is "Continue to card".

**Do.** Read the agreement, type a name, check the box, choose a password of at least 8 characters, submit. Wait on "Saving…".

**Code.** `GET /api/public/invites/{token}` returns the invite, a small shop record, agreement sections, and `owner_phone`. `POST /api/public/invites/{token}/register` (`register_shop_user`) requires `terms_agreed`, a signature, and a password of at least 8 characters (`password_error`). It stores `shop_users` with the signature, time, IP, user agent, and `agreement_version` `2026-11-12.3` (`backend/onboarding.py`). The invite becomes `registered`. A portal JWT is returned and saved in `localStorage`. An email that already has a shop user is rejected.

**Email.** None at this moment. Welcome mail waits until the charge pop-up is accepted.

**Failure.** A missing, revoked, used, or expired token shows "This link won't open" and "Request a new link" (`POST /api/public/invites/{token}/request-new`), plus `OWNER_PHONE` (default (480) 269-1329). Request-new revokes the old token and issues another. If that mail is held, the API still says "A new link is on the way." The shop does not get the new URL on screen. If `FRONTEND_URL` is unset, request-new fails because the link cannot be built. A password under 8 characters is rejected in the browser and again on the server. Closing the tab after a successful register is the important break: the invite is already used, so the link will not open again. The account exists. The shop has to know to use `/portal/login` and finish on Settings. The register page does not say that.

**Rating: 3.** Name, password, and one signature is a normal account step. Burning the invite before the card exists makes a closed tab look like a dead link.

### 7. Service agreement

**Who sees what.** The agreement is on the same screen as the password, not a later page. Ten sections from `AGREEMENT_SECTIONS`: parties (The Calibration Crew LLC, Gilbert, Arizona), work and prices, card and invoice rules, the $30 trip fee, what the shop must have ready, no late-cancel fee and no waiting fee, free re-calibration within 30 days, liability capped at the amount paid, 7 days to raise a billing issue and contact before a chargeback, electronic signature, Arizona law and Maricopa County. Version `2026-11-12.3`. The shop types their name and checks the box. The server stores the full text with the signature.

**Do.** Scroll the agreement. Type the name. Check the box. That is part of the same submit as the password.

**Code.** `GET /api/public/agreement` and the paragraphs embedded in the invite payload. `backend/onboarding.py`.

**Email.** None.

**Friction.** The agreement is long for one screen under a password form. Triple at $185 is offered later at booking and is absent here. Prices can change with 30 days' notice, which the agreement states.

**Rating: 3.** One signature, stored with name, time, and IP, is the right record. It is buried under the password fields and it omits a price the booking screen sells.

### 8. Save a card (Stripe)

**Who sees what.** After register, the same page switches to "Save a card". Copy: "No charge today. The card is used after a job is completed, unless you asked to be invoiced." If the API returned a SetupIntent client secret, `frontend/src/components/CardSetup.jsx` mounts Stripe Payment Element. The button is "Save card". If there is no client secret and there is a Checkout URL, the button is "Continue in Stripe". A live publishable key (`pk_live_`) is refused on the page: "Use a pk_test_ key until you turn billing on." A missing publishable key says card setup needs test keys.

**Do.** Enter the card in Stripe. Click Save card. Stripe.js calls `confirmSetup` with `redirect: "if_required"` and return URL `{origin}/portal/setup-return`. On success the page posts the payment method id.

**Code.** Register calls `create_setup_intent` and `create_checkout_setup` when Stripe is configured and `FRONTEND_URL` is set (`backend/payments.py` via `backend/server.py`). Checkout success and cancel URLs are `{FRONTEND_URL}/portal/setup-return`. `POST /api/portal/payment-method` attaches the payment method and stores brand, last4, and expiry on `shop_users`. `GET /api/portal/stripe-setup-status?session_id=` does the same after a Checkout redirect (`frontend/src/pages/PortalSetupReturn.jsx`). `POST /api/portal/setup-intent` can start the card again from Settings.

**Email.** None yet.

**Failure.** No Stripe secret, or customer create fails: the register response sets `stripe_unavailable` and the page shows the error. The account and the signature are already saved. Booking stays closed. `FRONTEND_URL` blank skips both the SetupIntent and the Checkout URL, so the shop gets the unavailable message even when a Stripe key exists. A card error from Stripe stays on the form (`result.error.message`). A 3-D Secure redirect lands on `/portal/setup-return`. Cancelling Checkout (`?cancelled=1`) leaves the card unset. Closing the tab on this step is the same dead invite as step 6: log in and open Settings (`frontend/src/pages/PortalSettings.jsx`) to start the card again. A declined card at signup is Stripe refusing the SetupIntent. Nothing is charged. The shop can try another card.

**Rating: 3.** SetupIntent with no charge today matches the rule. It is a second sitting on the same URL, and it depends on `FRONTEND_URL` plus two Stripe keys. A closed tab dumps the shop onto a used invite.

### 9. Charge-authorization pop-up

**Who sees what.** This pop-up comes after the card is saved, not before it. `ChargeAcceptance` is a modal: "Before you finish" and the charge text. The button is "I understand". The text (`CHARGE_ACCEPTANCE_TEXT`) says the card is charged after each completed job unless they asked to be invoiced, with 7 days and a one-time $25 late fee, and it restates the $30 trip fee.

**Do.** Click "I understand". The page goes to `/portal/ready`.

**Code.** `POST /api/portal/accept-charge` with `{accepted: true}`. The server rejects the call if no card is saved or `accepted` is false. It stores the time, the text, the IP, and the user agent. The first acceptance sends the welcome mail and the owner mail.

**Email.** Shop welcome, kind `welcome`, subject `You're set — {shop}`. It includes the booking link when `FRONTEND_URL` is set, otherwise a relative `/book/{token}` and an error log. Held while `SHOP_EMAILS_ENABLED` is false (unless that path is shop audience, which it is, so it is held). Owner mail, kind `signup_finished`, subject `{shop} finished signup`, sent through `send_email` (not held). Reply-To on the welcome is the owner.

**Failure.** Dismissing the modal is not offered. Reloading the invite URL will not bring it back (the invite is used). Settings shows the same modal after a card is saved if `charge_authorization_accepted_at` is empty. Until they accept, `booking_gate` blocks a new shop. Closing the tab after "I understand" is safe: the timestamp is stored and `/portal/ready` is only a confirmation.

**Rating: 4.** One button, the right promise, stored with the card. It is a third beat on a page the shop can lose by reloading.

### 10. First view of the shop portal

**Who sees what.** `/portal/ready` (`frontend/src/pages/PortalReady.jsx`) says "You're all set", shows a booking URL built from `window.location.origin` (this one does use the browser origin), and offers "Book a job" and "Go to the portal". `/portal` (`frontend/src/pages/PortalDashboard.jsx`) is a day map of today's jobs. A new shop with setup finished sees an empty map centered on Phoenix. If setup is unfinished, a yellow banner says "Finish setup to book" and links to Settings. Shops created before `requires_billing_setup` keep booking and see "Finish setup when you can".

**Do.** Click Book a job, or look at the empty day. They can also open Jobs, a job, or Settings from the portal shell.

**Code.** `GET /api/portal/me` includes `setup` from `booking_gate`. `GET /api/portal/day-map`. Routes in `frontend/src/App.js`.

**Email.** None from opening the portal.

**Friction.** The ready screen's booking link uses the current origin, while emails use `FRONTEND_URL`. Those can differ. The dashboard is a dispatch map, which is a lot of chrome for a shop that has zero jobs. The banner and the book page both block booking until signature, card, and acceptance are all present.

**Rating: 3.** The ready screen tells them the next action. The home of the portal is an empty map.

### 11. First booked job

**Who sees what.** `/portal/book` (`frontend/src/pages/PortalBook.jsx`) is four steps. If `booking_gate` says no, the page is "Finish setup to book" and a button to Settings. Otherwise:

1. Address, defaulting to the shop address. Blur calls `POST /api/geocode`. Outside the valley, or a failed lookup, cannot continue.
2. A date from today through 21 days. `POST /api/public/availability` with the shop's booking token. Slots show a time. Some are labeled "Pending approval". Sundays and blocked days are not offered. A failure says "Couldn't load times, try again" with a retry.
3. Customer first and last name, year, make, model, trim, VIN, ADAS system (forward camera, surround view, radar, multi-camera, Tesla). ADAS picks a default calibration type.
4. Calibration type with a price: Static $125, Dynamic $125, Dual $175, Triple $185, Tesla $225, or the shop's custom rate when `pricing_tier` is `custom`. A line says the card is charged when the job is completed unless they ask to be invoiced. Checkbox "Please invoice me instead". Phone (prefilled from the shop) and optional notes. Confirm Booking, or "Request this time" when the slot needs approval.

**Do.** Walk the four steps and confirm. The result is "Booking Confirmed" or "Pending owner approval", with a short reference, and a button to My Jobs.

**Code.** `POST /api/portal/book` sets the booking token from the logged-in shop and calls `public_book`. That checks the gate, geocodes again, refuses a point outside the valley, rejects a closed day, prices the job, and inserts `jobs` plus a `vehicles` row. `payment_mode` is invoice when the checkbox is set, otherwise charge on completion. Status is `booked` or `requested` when the slot needs approval. Same-day work and arrivals before 8:00 AM Phoenix email the owner with one-time Approve and Decline links (`/owner-action/{token}`, 48 hours, confirm page before the job changes). A new-booking alert is written for the owner dashboard.

**Email.** Shop confirmation (held while shop mail is off): Phoenix time, vehicle, address, calibration, price, and either confirmed or pending. Owner alert when `owner_needs_alert` is true (same-day, before 8:00 AM, or an add-on). Owner alerts send when `OWNER_EMAILS_ENABLED` is on, which is the default, independent of shop mail.

**After completion (not part of the click, but the rule the shop just accepted).** Completing a job invoices once. Charge mode also creates one off-session PaymentIntent when `BILLING_ENABLED` is on. That flag is off in production today, so completion does not charge and the late-fee sweep does not run. Invoice mode waits for the owner to charge. A declined card is recorded as payment failed and the balance is treated as an invoice. Seven days after completion, one $25 late fee can be added to an unpaid invoice-mode job. The $30 trip fee is an owner action on the job ("Outside service area" adds $30 once, or "Couldn't calibrate" replaces the price with $30). The shop does not pick those at booking.

**Failure.** Booking before the card and the pop-up returns 403 with the gate message. A bad phone (not 10 digits) is rejected. A Maps failure blocks the address step. Slot load failure is retryable. Same-day or early slots sit in `requested` until the owner approves, from the dashboard or the email link. Closing the tab mid-wizard loses the unsaved steps. The shop can start again. A duplicate booking is a second job. Cancelling does not add a fee. The portal job list still shows cancelled jobs. The owner day board does not.

**Rating: 3.** The wizard collects a real job and the invoice choice is one checkbox. Four steps, a second geocode, and a pending-approval branch are a lot for the first booking, and Triple's $185 is a price the agreement never stated.

## Scoreboard

| Step | Rating | Why |
|---|---|---|
| Marketing Sign Up | 4 | One obvious link. The promise is repeated on every page. |
| Request form, first submit | 2 | Places can fill the address and the server still demands another submit. |
| Address checkbox and second submit | 2 | The checkbox restates a pin the server already resolved. |
| Owner Requests list | 2 | Approve is one click, and the list could miss the row the email just announced. |
| Invite delivery | 2 | Held mail plus a missing `FRONTEND_URL` means there is often no link to copy on the approve screen. |
| Password on the invite | 3 | Short form. The invite is consumed before the card exists. |
| Agreement | 3 | One signature with a real record. It is long, and it skips the Triple price. |
| Stripe card | 3 | No charge today, which is correct. It dies without `FRONTEND_URL` and a test key, and a reload looks like a dead invite. |
| Charge pop-up | 4 | One acceptance, stored, after the card exists. |
| First portal view | 3 | "You're all set" is clear. The home screen is an empty dispatch map. |
| First job | 3 | The invoice choice is in the right place. Four steps and a second address lookup are heavy. |

## Target flow

Keep the card, the charge acceptance, the prices, the trip fee, the 7-day invoice and $25 late fee, no cancel fee, no waiting fee, and the 30-day free re-calibration. Drop the owner as a gate in front of account creation. Caleb reviews new shops after they exist, and can suspend one, instead of approving before a password exists.

### T1. One signup page

**Shop sees.** Shop name, contact name, mobile, email, password, and address. The address suggests as they type and the chosen suggestion is the confirmed address. No second submit. A short agreement (the current sections, plus Triple $185 if that price stays) sits on the same page with the signature checkbox. Submit once.

**Code.** Replace the 409 checkbox in `SignupPage.jsx` and `_checked_shop_address`: a `place_id` or a suggestion payload counts as confirmation. `POST /api/public/shop-requests` becomes `POST /api/public/shops` and creates `shops` (`requires_billing_setup: true`), `shop_users` (password, signature, IP, time, agreement version), and a portal JWT in one handler. Duplicate email returns 409 and points at login and forgot-password. Duplicate name is allowed only with an explicit "this is a second location" check, and it is flagged for the owner either way.

**Effort: M.**

### T2. Card and charge acceptance in the same sitting

**Shop sees.** Stripe Payment Element under the form, then the existing "I understand" line as the submit, not a later modal. One button: "Create my shop". Success lands on Book, not on an empty map.

**Code.** Create the Stripe Customer and SetupIntent in the same request as T1, or in a follow-up call that does not depend on an invite token. `CardSetup` and `portal_accept_charge` stay. Require the payment method and `accepted: true` before the handler returns the portal session. If Stripe is down, save the account, show the error, and keep booking closed. Do not burn a one-time link. Resume is `/portal/login` then Settings, and the signup page says that before they start.

**Effort: M.**

### T3. Owner review after the fact

**Owner sees.** `/requests` becomes "New shops" and lists accounts created this way, already active, with a Flag / Suspend action. The owner email still fires (`send_email`, kind `shop_request`) and includes the shop, the address, and a link to that row. No approve click is required before the shop can book. Suspend sets the shop inactive and `booking_gate` starts returning false.

**Code.** Stop calling `_issue_invite` from the public signup path. Keep `/invites` for the rare case Caleb adds a shop himself in `ShopNew.jsx`. Delete the held-invite copy problem for this path because there is no invite.

**Effort: M.**

### T4. Make the link real if any email remains

**Owner sees.** If an invite is still used for shops Caleb types in by hand, the approve or create screen shows the URL and a Copy button whenever `register_url` is set, including when `email_status` is `held`. Held is labeled "Held", not "Not delivered".

**Code.** `Requests.jsx` and `Invites.jsx` render `invite.register_url`. Default `FRONTEND_URL` to `PUBLIC_SITE_URL` when it is blank, so a missing env var does not store a null link. Production today has `FRONTEND_URL` unset (startup log, 2026-11-13 20:12 UTC). Set it on Render to `https://www.thecalibrationcrew.us` before any invite is sent. Turn `SHOP_EMAILS_ENABLED` on only when shop mail should really send. Until then, the copy button is the path.

**Effort: S.**

### T5. First job, fewer steps

**Shop sees.** Address (shop address already confirmed at signup, with an inline override), date and time on the same screen, vehicle and calibration with the price, and the invoice checkbox. One confirm.

**Code.** Collapse `PortalBook.jsx` steps 1–2 onto one screen and 3–4 onto the next. Reuse the signup geocode when they keep the shop address so `/geocode` is not a required extra call. Keep `POST /api/portal/book`, the approval rule for same-day and before 8:00 AM, and `payment_mode`. Put Triple $185 into the agreement before it stays on this screen.

**Effort: M.**

### What this removes

The shop no longer waits for Caleb, an email, a 14-day token, or a second address submit. Caleb still gets the email and a review queue. The card and the charge sentence still happen before the first booking. The invoice choice, the 7-day late fee, the trip fee, and the free 30-day re-calibration stay where they are: the agreement, the pop-up, and the booking checkbox.
