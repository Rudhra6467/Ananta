# Stage 4 — Observation replay (Ananta side)

Agent Ananta consumes this. Ananta **owns** the compute.

## Endpoint

`GET /api/lab/observation-replay` (owner JWT)

Query: `symbol` (default BTC/USD), `timeframe` (1h), `stride` (4), `include_observations` (true), `max_bars` (optional).

Runs in the same spawn process pool as `/api/lab/regime-audit` so it does not block the API.

## Contract

Module: `backend/lab/observation_replay.py`

Uses **live** functions on Lab Mongo candles:

- `classify_regime`
- `evaluate_primary` (Hunter)
- `evaluate_squeeze`
- `declarative_engine.evaluate` for bollinger-mr

Evaluate-then-filter. Per-bar SKIP / WAIT / TAKE-equivalent. Independent flags from the candle window (no look-ahead). Forward +15m/+1h/+4h from subsequent bars.

Historical TAKE is **TAKE-equivalent** (setup AND Wave A gate). Not a fill. Not KEEP.

Same `observation_v0` the Agent writes from `lab watch`. Agent persists rows to `observation_replay.jsonl`, never into the live ledger.

Wave A stays WATCH. This endpoint must not enable, disable, or mutate strategy profiles.
