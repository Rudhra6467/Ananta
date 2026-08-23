# Ananta — Platform work against the locked Agent roadmap

**Updated:** 2026-08-23

Ananta’s current obligation for Agent Ananta:

1. Prove ~1 year of 1h candles in Mongo `historical_candles` (the collection Lab + `/api/lab/data/coverage` read). **Done.**
2. Expose Wave A Strategy Knowledge Objects at `GET /api/strategy/knowledge` (implementation + router, not DNA-as-policy). **Done.**
3. Lab JSON replay of the **same** engines. Tag `source=BACKTEST`. Never auto-KEEP. **Done** (context, not promotion).
4. **Stage 4:** `GET /api/lab/observation-replay` — same `observation_v0` as live `lab watch`, on 1y Lab candles, real `classify_regime` / `evaluate_primary` / `evaluate_squeeze` / declarative bollinger-mr. Historical TAKE-equivalent is not KEEP.

Wave A stays hunter / squeeze / bollinger-mr. Do not enable the other 12 from Ananta defaults for this lab.


---

## Current Ananta obligation

Emergent hosting expired. Agent Ananta cannot log in because the **backend** is unreachable, not because the agent is wrong.

Ananta’s job for this phase:

1. Be independently runnable (no frontend required).
2. Keep owner JWT auth on the contract.
3. Expose Contract v0 facts the agent already consumes.
4. Execute paper orders the agent places.

UI, Vercel, and “launch the website again” are **out of scope** until Wave A + Contract + ledgers can produce an auditable dataset through the API.

---

## Status

| Item | Status |
|------|--------|
| Backend code (`backend/server.py`) | Intact |
| Owner JWT `POST /api/auth/login` | Intact |
| Paper execution `POST /api/orders/manual` | Intact |
| Portfolio / trades / strategy registry | Intact |
| Hosted Emergent / livetrading247.com | **Dead** |
| Frontend as a requirement for Agent work | **Removed** |
| Local backend runbook | [LOCAL_BACKEND.md](./LOCAL_BACKEND.md) |

---

## Phase map (Ananta slice)

| Agent phase | Ananta work | Status |
|-------------|-------------|--------|
| 3 Wave A | Live paper book + enable/disable via API | Blocked on a running backend |
| 3.5 Contract v0 | Stable fields + HTTP surface | In progress — see [AGENT_CONTRACT_V0.md](./AGENT_CONTRACT_V0.md) |
| **3.6 Backend independence** | Local uvicorn + Mongo; Agent points at it | **Current unblocking work** |
| 4 Ledgers | Keep execution/outcome facts on the API; agent owns JSONL ledgers for now | In progress on agent side |
| 5 Evaluation | Outcome fields the agent can join | Not started |
| 12 Agent cockpit | UI later — not a dependency | Not started |
| 17 India | Gate: after Trust + Personal Proof | Not started |

---

## Preference order (do not skip ahead)

**A.** Start the existing backend locally.  
**B.** Direct Mongo only as test fixtures, then still hit the API.  
**C.** Contract-faithful harness only if A cannot start.

Do not:

- Rebuild Ananta to unblock the agent
- Let Agent Ananta write collections directly
- Weaken auth
- Treat Railway/Vercel as the next Agent milestone

---

## Next concrete Ananta step

1. `cd backend` → `.env` with Atlas (or local) `MONGO_URL`, `OWNER_EMAIL` / `OWNER_PASSWORD`, `JWT_SECRET`
2. `uvicorn server:app --host 0.0.0.0 --port 8001 --workers 1`
3. Prove `GET /health` and `POST /api/auth/login`
4. Hand `http://127.0.0.1:8001` to Agent Ananta as `ANANTA_BASE_URL`
