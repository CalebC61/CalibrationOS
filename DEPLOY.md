# Deploying CalibrationOS (self-hosted)

Target layout:

| Piece    | Host           | URL                                      |
|----------|----------------|------------------------------------------|
| Database | MongoDB Atlas  | (private connection string)              |
| API      | Render (Docker)| `https://api.thecalibrationcrew.us`      |
| Web app  | Vercel         | `https://thecalibrationcrew.us` and `www` |

All settings are listed in `backend/.env.example` and `frontend/.env.example`. Never commit real values.

Business dates are America/Phoenix in code (`backend/business_time.py`). There is no timezone env var. The Docker image checks that `America/Phoenix` resolves (`tzdata` in `requirements.txt`, because `python:3.13-slim` has no system timezone database).

## 1. MongoDB Atlas
The cluster already exists: M0 on AWS Oregon (`us-west-2`), network access `0.0.0.0/0`. Do not create a second one.

Any database user with read and write works, including permission to create indexes (startup creates a TTL index on `drive_time_cache`). The username does not have to be `calibrationos`. The existing user `admin_db_user` is fine.

1. Atlas → Database → Connect → Drivers. Copy the `mongodb+srv://...` string.
2. Put `admin_db_user` and its password in that string. This is `MONGO_URL`. If the password contains `@`, `:`, `/`, or `#`, URL-encode it.
3. `DB_NAME=calibrationos` (this is the database name, not the username). The blueprint sets it.
4. (Optional) Migrate existing Emergent data: `mongodump --uri "<emergent uri>"` then `mongorestore --uri "<atlas uri>"`.

## 2. Render (backend API)
1. Sign up at https://render.com with GitHub and grant access to `CalebC61/CalibrationOS`.
2. **New → Blueprint**, pick the repo. Render reads `render.yaml` and creates `calibrationos-api` (Docker, context `backend/`, Dockerfile `backend/Dockerfile`).
3. Fill the prompted values (`sync: false`). Leave an optional key blank; a blank value is treated as unset.

   **Minimum for the process to boot** and for `GET /api/health` to return `{"status":"ok"}`:
   - `MONGO_URL` — the Atlas string from step 1.
   - The blueprint already sets `APP_ENV=production`, `DB_NAME=calibrationos`, and generates `JWT_SECRET`. Do not paste the dev secret. In production the process refuses to start if `JWT_SECRET` is still that public default.

   **Minimum for a real owner login and for the website to call the API:**
   - `OWNER_PASSWORD` — the owner account is not created without it. On later restarts, a changed value rotates the stored password.
   - `CORS_ORIGINS=https://thecalibrationcrew.us,https://www.thecalibrationcrew.us`
   - `OWNER_EMAIL` only if it should not be `caleb@thecalibrationcrew.us` (that is the default when the key is blank).

   **Optional — the app boots and the matching feature stays mocked or off until set:**
   - `ADMIN_EMAIL` (default `admin@thecalibrationcrew.us`)
   - `CONTRACTOR_EMAIL` (default `contractor@thecalibrationcrew.us`), `CONTRACTOR_PASSWORD` (no contractor account in production until this or demo seed is on)
   - `RESEND_API_KEY`, `SENDER_EMAIL` — email
   - `STRIPE_API_KEY` — card capture and the charge queue. Use `sk_test_...` before `sk_live_...`
   - `GOOGLE_MAPS_API_KEY` — geocoding and drive time. Restrict the key to the Geocoding API and the Distance Matrix API. Do not restrict it by HTTP referrer; the backend calls Google, not the browser. The starter plan has no static outbound IP, so an IP restriction will fail until you add one.
   - `XERO_CLIENT_ID`, `XERO_CLIENT_SECRET`, `XERO_REDIRECT_URI`, `XERO_POST_CONNECT_REDIRECT`, `XERO_SALES_ACCOUNT_CODE` (default `200`)
   - `GOOGLE_API_KEY` — Admin Assist. Without it the module is off even though `ASSIST_MODULE_ENABLED=true`.
   - `ASSIST_MODEL` (default `gemini-2.5-flash`), `ASSIST_PENDING_TTL_SECONDS` (default `300`)
   - `ASSIST_SELF_BASE_URL` — leave blank. Assist then calls `http://127.0.0.1:$PORT`, which matches the port Render assigns. Set it only if that loopback call cannot work.

4. Deploy. Check `https://<service>.onrender.com/api/health` returns `{"status":"ok"}`. `/api/health` does not check Mongo; a failed startup (bad `MONGO_URL`, or the dev `JWT_SECRET`) never serves that route.
5. **Settings → Custom Domains** → add `api.thecalibrationcrew.us` and copy the CNAME target Render shows.

The `starter` plan (~$7/mo) avoids free-tier sleep, which would make the field app slow on first open. `render.yaml` selects it.

## 3. Vercel (frontend)
1. Sign up at https://vercel.com with GitHub, **Add New → Project**, import the repo.
2. **Root Directory**: `frontend`. Framework, install, and build come from `frontend/vercel.json` (`yarn install --frozen-lockfile`, then `yarn build`).
3. **Environment Variables** (Production), then redeploy. These are baked in at build time.
   - `REACT_APP_BACKEND_URL=https://api.thecalibrationcrew.us` — required. The UI calls `${REACT_APP_BACKEND_URL}/api`.
   - `REACT_APP_GROWTH_MODULE_ENABLED=true` — optional. The Growth page renders only when this is the string `true`. The nav link stays visible unless the value is `false`.
   - `REACT_APP_ASSIST_MODULE_ENABLED` — optional. Leave unset (the widget shows when the API has `GOOGLE_API_KEY`). Set `false` to hide it.
4. Deploy, then **Settings → Domains** → add `thecalibrationcrew.us` and `www.thecalibrationcrew.us`. Set the apex as the primary domain so `www` redirects to it. Copy the DNS records Vercel shows for this project. Do not reuse another project's CNAME. Vercel's apex record is an A record (their docs use `76.76.21.21`); `www` is a CNAME to a project-specific `*.vercel-dns-*.com` host.

## 4. Domain (thecalibrationcrew.us)
DNS is at domain.com (`ns1.domain.com` / `ns2.domain.com`). Today the apex, `www`, `api`, and `app` are A records to `208.91.197.27`, which serves a registrar placeholder ("Error. Page cannot be displayed."), not a Calendly site or any other app. `book.` and `calendly.` point at that same address. Mail is Google Workspace (`MX` → `smtp.google.com`).

**Do not change the nameservers.** Moving DNS to Vercel without copying the Google MX records would break `admin@` mail. Change only the website and API records, and leave MX alone.

Replace the existing A records (do not add a second record on the same name):

| Type  | Name | Value                                              |
|-------|------|----------------------------------------------------|
| A     | `@`  | the A record Vercel shows for the apex             |
| CNAME | `www`| the CNAME target Vercel shows for this project     |
| CNAME | `api`| the CNAME target Render shows (`*.onrender.com`)   |

`app.thecalibrationcrew.us` is unused. Leave it or delete it. Both hosts issue HTTPS certificates once DNS resolves (minutes to a few hours).

Pointing the apex at Vercel replaces the registrar placeholder at `thecalibrationcrew.us` and `www`. It does not change a Calendly page hosted on `calendly.com`.

## 5. Third-party callbacks
- **Xero** (developer.xero.com → your app): redirect URI `https://api.thecalibrationcrew.us/api/auth/xero/callback`; set the same in `XERO_REDIRECT_URI`, and `XERO_POST_CONNECT_REDIRECT=https://thecalibrationcrew.us/settings`.
- **Google Maps**: see the optional key notes above.
- **Resend**: verify `thecalibrationcrew.us` (adds DNS TXT/MX records) so `SENDER_EMAIL` can send. Don't remove the existing Google MX; add Resend's records beside it only as Resend instructs.
- **Stripe**: use a live secret key (`sk_live_...`) only after testing with `sk_test_...`.

## 6. Smoke test
1. Open `https://thecalibrationcrew.us` (and confirm `www` redirects to it). Log in as the owner. The form is blank; the dev password is not shown.
2. Create a test booking, dispatch it, complete it in the field view, confirm the invoice draft.
3. `https://api.thecalibrationcrew.us/api/health` returns `{"status":"ok"}`.

## Local development / CI
```bash
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt pytest
cp .env.example .env   # fill MONGO_URL etc.
uvicorn server:app --port 8001 --reload
python -m pytest -q                      # unit tests; live-server tests skipped
RUN_INTEGRATION=1 REACT_APP_BACKEND_URL=http://localhost:8001 python -m pytest -q   # include integration
cd ../frontend && cp .env.example .env && yarn install && yarn start
```
GitHub Actions (`.github/workflows/ci.yml`) runs backend unit tests and the frontend build on every push/PR.
