# Deploying CalibrationOS (self-hosted)

Target layout:

| Piece    | Host           | URL                                   |
|----------|----------------|---------------------------------------|
| Database | MongoDB Atlas  | (private connection string)           |
| API      | Render (Docker)| `https://api.thecalibrationcrew.us`   |
| Web app  | Vercel         | `https://app.thecalibrationcrew.us`   |

All settings are listed in `backend/.env.example` and `frontend/.env.example`. Never commit real values.

## 1. MongoDB Atlas
1. Sign up at https://cloud.mongodb.com and create a project "CalibrationOS".
2. **Create cluster**: M0 (free) to start, AWS / `us-west-2` (Oregon, close to Render's Oregon region).
3. **Database Access** → add user `calibrationos` with a generated password, role *Read and write to any database*.
4. **Network Access** → add `0.0.0.0/0` (Render's free/starter IPs are not static). Tighten later with Render static outbound IPs if you upgrade.
5. **Connect → Drivers** → copy the `mongodb+srv://...` string and put the password in it. This is `MONGO_URL`. `DB_NAME=calibrationos`.
6. (Optional) Migrate existing Emergent data: `mongodump --uri "<emergent uri>"` then `mongorestore --uri "<atlas uri>"`.

## 2. Render (backend API)
1. Sign up at https://render.com with GitHub and grant access to `CalebC61/CalibrationOS`.
2. **New → Blueprint**, pick the repo. Render reads `render.yaml` and creates `calibrationos-api` (Docker, `backend/`).
3. Fill the prompted values (everything marked `sync: false`). Minimum to boot:
   `MONGO_URL`, `OWNER_EMAIL`, `OWNER_PASSWORD`, `CORS_ORIGINS=https://app.thecalibrationcrew.us`.
   `JWT_SECRET` is generated automatically. Add Stripe / Maps / Xero / Resend / Gemini keys as you turn each feature on.
4. Deploy. Check `https://calibrationos-api.onrender.com/api/health` returns `{"status":"ok"}`.
5. **Settings → Custom Domains** → add `api.thecalibrationcrew.us` and note the CNAME target Render shows.

The `starter` plan (~$7/mo) avoids free-tier sleep, which would make the field app slow on first open.

## 3. Vercel (frontend)
1. Sign up at https://vercel.com with GitHub, **Add New → Project**, import the repo.
2. **Root Directory**: `frontend`. Framework and build settings come from `frontend/vercel.json`.
3. **Environment Variables** (Production): `REACT_APP_BACKEND_URL=https://api.thecalibrationcrew.us`,
   `REACT_APP_ASSIST_MODULE_ENABLED=true`, `REACT_APP_GROWTH_MODULE_ENABLED=true`.
   These are baked in at build time; redeploy after changing them.
4. Deploy, then **Settings → Domains** → add `app.thecalibrationcrew.us` and note the CNAME target.

## 4. Domain (thecalibrationcrew.us)
At your DNS provider for `thecalibrationcrew.us` add:

| Type  | Name  | Value                                   |
|-------|-------|-----------------------------------------|
| CNAME | `api` | target shown by Render (`*.onrender.com`) |
| CNAME | `app` | `cname.vercel-dns.com`                  |

Don't touch existing MX/TXT records (they handle admin@ email). Both hosts issue HTTPS certificates automatically once DNS resolves (minutes to a few hours).

## 5. Third-party callbacks
- **Xero** (developer.xero.com → your app): redirect URI `https://api.thecalibrationcrew.us/api/auth/xero/callback`; set the same in `XERO_REDIRECT_URI`, and `XERO_POST_CONNECT_REDIRECT=https://app.thecalibrationcrew.us/settings`.
- **Google Maps**: restrict the API key to Geocoding + Distance Matrix APIs.
- **Resend**: verify `thecalibrationcrew.us` (adds DNS TXT/MX records) so `SENDER_EMAIL` can send.
- **Stripe**: use a live secret key (`sk_live_...`) only after testing with `sk_test_...`.

## 6. Smoke test
1. Open `https://app.thecalibrationcrew.us`, log in as the owner.
2. Create a test booking, dispatch it, complete it in the field view, confirm the invoice draft.

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
