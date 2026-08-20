# Ananta backend — independently runnable

**Updated:** 2026-08-20  
**Audience:** Agent Ananta lab, CLI tests, contract work.

The React UI is **one client** of this backend. Agent Ananta is another. You do not need the website to develop or test the agent.

Emergent hosting is expired. Do **not** redeploy the frontend (Vercel) just so the agent has a URL. Run this backend locally.

---

## What this service is

```text
Ananta Backend
    ├── Database (MongoDB)
    ├── Strategies (registry, profiles, enable/disable)
    └── Execution (paper orders, cycles, fills)
```

Entry point: `backend/server.py` → FastAPI `app`.  
All product routes are prefixed `/api`. Liveness is `GET /health` (no `/api`, no DB).

`--workers 1` is mandatory. Trading loops, position watcher, and research resolver run in-process.

---

## Local start (Option A — preferred for Agent work)

```bash
cd backend
cp .env.example .env        # fill MONGO_URL, JWT_SECRET, OWNER_EMAIL, OWNER_PASSWORD
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001 --workers 1
```

Health:

```bash
curl -sf http://127.0.0.1:8001/health
curl -sf http://127.0.0.1:8001/api/
```

Owner login (same contract Agent Ananta uses):

```bash
curl -s http://127.0.0.1:8001/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"<OWNER_EMAIL>","password":"<OWNER_PASSWORD>"}'
```

MongoDB is required (Atlas M0 is enough). The backend does not start as a useful API without `MONGO_URL`.

Keep `LIVE_TRADING_ENABLED=false`. Paper is the lab mode.

You do **not** need to start `frontend/` for Agent Ananta.

---

## Contract routes Agent Ananta uses

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/auth/login` | Owner JWT |
| `GET` | `/api/portfolio` | equity, cash, positions, `slots_used` |
| `POST` | `/api/orders/manual` | Paper BUY/SELL (not `/api/orders/paper`) |
| `GET` | `/api/trades` | Fills / history |
| `GET` | `/api/strategy/registry` | Strategy keys + names |
| `GET`/`PUT` | `/api/strategy/{key}/profile` | Enable/disable |
| `POST` | `/api/cycle/run` | Evaluation cycle |
| `POST` | `/api/cycle/run/{symbol}` | Per-symbol cycle |
| `GET` | `/health` | Process liveness |

Shared field language: [AGENT_CONTRACT_V0.md](./AGENT_CONTRACT_V0.md).

---

## Direct database use (Option B — fixtures only)

Seeding Mongo for a test (e.g. `ARB` position = 10) is fine.

Then the agent must still call the API (`SELL ARB 1.0` → `POST /api/orders/manual`).

Do not make Agent Ananta a Mongo client. That would collapse the contract boundary this phase exists to prove.

---

## Local harness (Option C — only if this backend cannot start)

If uvicorn + Mongo cannot be brought up, a temporary harness may expose the same routes above. It must speak Contract v0. It is not a second trading engine.

---

## What not to do in this phase

- Launch or polish the website so the agent “has somewhere to click”
- Deploy to Vercel for Agent traffic
- Weaken `/api/auth/login`
- Add agent-only backdoors into collections
- Treat Emergent Google session exchange as required for the lab (owner JWT is enough)

Full hosted deploy (Railway/Render + Vercel + Atlas) remains documented in the root README for later. It is not the current Agent unblocking path.
