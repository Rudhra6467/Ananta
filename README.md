# Ananta.AI — Algorithmic Swing-Trading Dashboard

A scale-independent, multi-asset algorithmic swing-trading framework optimized for 24/7 capital
preservation. **PAPER mode by default** (no real money). Stack: **FastAPI + React + MongoDB**.

- **Backend:** FastAPI (Python 3.11), CCXT, Motor (async MongoDB). All API routes are prefixed with `/api`.
- **Frontend:** React (CRA + CRACO) + Tailwind + shadcn/ui.
- **Engine:** the pure-math "Hunter" scans setups; a Strategy Research Laboratory shadow-tracks competing
  strategies (VCP, Relative Strength, Bear Breakdown, Neutral Crab) and ranks them vs the Hunter benchmark.

---

## Repository layout

```
backend/    FastAPI app (entry point: server.py -> `app`)
frontend/   React app (CRACO; build output -> frontend/build)
```

---

## Self-hosting for ~free (recommended to avoid recurring deploy cost)

You will run **3 pieces**, each on a free/cheap tier:

| Piece     | Recommended host            | Free? |
|-----------|-----------------------------|-------|
| Database  | **MongoDB Atlas** (M0)      | Free (512MB — plenty for this app) |
| Backend   | **Railway** or **Render**   | Cheap/always-on (free tiers *sleep*, see note below) |
| Frontend  | **Vercel**                  | Free |

> ⚠️ **This is a 24/7 trading bot.** Free backend tiers on Render/Railway *sleep when idle*, which stops the
> background trading loops. For continuous operation use Railway's usage-based plan or Render's **Starter**
> (~$7/mo) — still far cheaper than the current setup. The frontend (Vercel) and database (Atlas) stay free.

---

### Step 1 — Database: MongoDB Atlas (free)
1. Create a free account at https://www.mongodb.com/atlas and create an **M0 (free)** cluster.
2. **Database Access** → add a user (username + password).
3. **Network Access** → allow access from anywhere (`0.0.0.0/0`) — or restrict to your backend host's IPs.
4. **Connect** → "Drivers" → copy the connection string. It looks like:
   `mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`
   Keep this for `MONGO_URL`.

### Step 2 — Backend: Railway or Render
**Railway (simplest):**
1. https://railway.app → New Project → **Deploy from GitHub repo** → pick this repo.
2. Set the service **Root Directory** to `backend`.
3. Railway auto-detects the `Procfile`. Start command (already in `backend/Procfile`):
   `uvicorn server:app --host 0.0.0.0 --port $PORT --workers 1`  ← **keep `--workers 1`** (the trading
   loops run in-process; multiple workers would duplicate them).
4. Add the environment variables from `backend/.env.example` (see Step 4). **Do NOT commit real secrets.**
5. Deploy. Note the public URL, e.g. `https://ananta-backend.up.railway.app`. Health check: open
   `https://<that-url>/api/` → should return JSON `200`.

**Render (alternative):** New + → **Blueprint** → select this repo (it reads `render.yaml`), or create a
Web Service with Root Directory `backend`, build `pip install -r requirements.txt`, start
`uvicorn server:app --host 0.0.0.0 --port $PORT --workers 1`, health check path `/api/`.

### Step 3 — Frontend: Vercel (free)
1. https://vercel.com → New Project → import this repo.
2. Set **Root Directory** to `frontend` (Vercel reads `frontend/vercel.json`).
   - Build command: `yarn build` · Output dir: `build` · Install: `yarn install`.
3. Add env var `REACT_APP_BACKEND_URL` = your backend public URL from Step 2 (no trailing slash).
4. Deploy. You'll get a URL like `https://ananta.vercel.app`.

### Step 4 — Wire them together (env vars)
**Backend** (set in Railway/Render dashboard — see `backend/.env.example` for the full list):
- `MONGO_URL` — from Step 1
- `DB_NAME` — e.g. `ananta`
- `CORS_ORIGINS` — your Vercel frontend URL (e.g. `https://ananta.vercel.app`). For a quick test you may use `*`.
- `JWT_SECRET` — a long random string
- `OWNER_EMAIL` / `OWNER_PASSWORD` — your owner login
- `EMERGENT_LLM_KEY` — (optional) macro reasoning; leave blank to skip LLM calls
- `FRED_API_KEY` — (optional) free key from https://fred.stlouisfed.org/docs/api/api_key.html
- `LIVE_TRADING_ENABLED=false` — keep PAPER mode

**Frontend** (set in Vercel dashboard — see `frontend/.env.example`):
- `REACT_APP_BACKEND_URL` — your backend public URL

> After changing `CORS_ORIGINS` on the backend, redeploy/restart the backend so it takes effect.

### Step 5 — First run
1. Open your Vercel URL → click **OWNER LOGIN** → sign in with `OWNER_EMAIL` / `OWNER_PASSWORD`.
2. On the **Cockpit**, confirm the Watchlist shows **10/10 · in sync** (click **VALIDATE** / **SYNC 10** if not).
3. Go to **DataLogs / Reports** → **FRESH START** to begin a clean $1,200 paper book at $75/trade.

---

## Local development
```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env        # fill in values
uvicorn server:app --host 0.0.0.0 --port 8001 --workers 1

# Frontend (separate terminal)
cd frontend
yarn install
cp .env.example .env        # set REACT_APP_BACKEND_URL=http://localhost:8001
yarn start
```

---

## Notes & gotchas
- **`--workers 1` is mandatory.** The trading loop, position watcher, and research resolver run as in-process
  background tasks with shared state. Running multiple workers would start duplicate loops.
- **Memory:** the backend is memory-bounded (capped/projected queries, heavy compute offloaded to threads),
  so it runs comfortably on small instances regardless of how large the database grows.
- **Secrets:** never commit real `.env` files. Set all secrets in the host dashboards. `.env` is gitignored.
- **PAPER vs LIVE:** the system ships in PAPER (simulated) mode. Live execution stays disabled unless you set
  `LIVE_TRADING_ENABLED=true` and provide exchange API keys (not recommended until your validation gates pass).
