# Ananta.AI — System Blueprint

*Algorithmic swing-trading research & execution cockpit — capital-preservation-first, explainable, defensive.*

**Production:** https://spot-trading-lab.emergent.host
**Stack:** FastAPI + MongoDB (shared backend) · React (web) · Expo/React Native (mobile, separate workspace) · SQLite (offline Research Lab market DB)

---

## 1. What Ananta is

Ananta is a technical-first algorithmic trading platform that decouples **research** from **live execution** while guaranteeing they run the *same code*. It scans a 10-asset crypto watchlist, qualifies setups through a multi-strategy Hunter, arbitrates exits through a deterministic Universal Exit Engine, and lets the operator validate parameter changes offline (walk-forward + sensitivity) before promoting them to production behind an approval gate.

Two environments, one logic base:
- **Live/Paper engine** — an async trading loop that scans, enters, and manages positions (paper simulation by default: simulated maker fills, fees, slippage, trailing stops).
- **Research Lab** — an offline, pure-compute backtester that calls the *identical* strategy/exit functions via an **injectable clock**, against a local 2-year OHLCV SQLite database — byte-for-byte parity with live.

---

## 2. Architectural layers

```
┌── Presentation ──────────────────────────────────────────────┐
│  Web (React)              Mobile (Expo, separate workspace)   │
│  Bottom-tab nav + swipe · dynamic context header              │
│  Cockpit · Portfolio · Datalogs · Research Lab                │
└───────────────┬───────────────────────────────────────────────┘
                │  REST /api/*  (shared, platform-agnostic contract)
┌───────────────▼───────────────────────────────────────────────┐
│  FastAPI (server.py) — routing, auth, settings, SSE-less poll  │
│  ├─ Warm snapshot cache (background loop, <150ms reads)        │
│  ├─ TradingLoop  (async scan→qualify→enter→manage)            │
│  ├─ Universal Exit Engine (exit_engine.py, Modules A–F)       │
│  ├─ Research cache loop / counterfactual resolver             │
│  └─ Lab subsystem (lab/*) — queue, backtester, optimizer      │
└───────────────┬───────────────────────────────┬───────────────┘
                │                                 │
        MongoDB (state)                  SQLite historical_candles.db
   users · portfolio · trades ·          (OHLCV 1d/4h, 2y, WAL mode,
   reasoning · research · lab_runs ·      idx_candles_key indexed)
   lab_param_proposals · settings
                │
        External data (keyless where possible)
   Kraken (tickers/orderbook) · CCXT + Binance public CSV (seed) ·
   DefiLlama · FRED · Gemini (Nano Banana / macro reasoning, Emergent LLM key)
```

---

## 3. Live engine — scan → qualify → enter → manage

**TradingLoop** (`trading_engine.py`) runs on an async cadence:

1. **Market regime** (`_market_regime`) from BTC closes → BULLISH / NEUTRAL / BEARISH; **relative strength** (`_rel_strength`) ranks assets vs BTC.
2. **Strategy qualification** — a setup must clear the active strategy profile's gates. Strategies (each with its own `StrategyProfile`):
   | Strategy | Profit-arm | ATR trail | Time limit | Notes |
   |---|---|---|---|---|
   | `hunter` | +5.0% | 2.0× | 72h | structural + 0.5 ATR stop (default) |
   | `squeeze` | +4.0% | 2.5× | none | EMA-loss prioritised, 2h settle |
   | `relative_strength` | +6.0% | 2.0× | 120h | swing-low stop |
   | `neutral_crab` | +2.5% | 1.5× | 24h | range-boundary stop, quick exit |
   | `bear_breakdown` | +5.0% | 1.5× | none | structure-above stop, EMA-prioritised |
3. **Entry** — `_execute_buy` (paper: simulated maker order, fee %, slippage). Position records entry, avg cost, structural stop, peak tracking.
4. **Management** — every cycle each open position is passed to the Universal Exit Engine; partial/full exits via `_execute_sell` / `_execute_partial_sell`.
5. **Telemetry** — trades log `exit_module`, `potential_best_exit`, `potential_worst_exit`, `mfe_pct`, `mae_pct` for counterfactual analysis.

---

## 4. Universal Exit Engine (Phase F) — `exit_engine.py`

Exit logic is fully decoupled from entry logic and arbitrated by a **deterministic single-pass priority sort — lowest priority number wins**:

| Priority | Module | Trigger | Action |
|---|---|---|---|
| 1 | **A · Structural** | price ≤ structural stop / invalidation level | EXIT_FULL |
| 2 | **KILL** | emergency manual kill-switch | EXIT_FULL |
| 3 | **F · Profit Protection** | MFE ≥ profit-arm % → lock a +1% profit floor | TIGHTEN |
| 4 | **B · Momentum Exhaustion** | momentum/RSI rollover | EXIT_PARTIAL |
| 5 | **D · EMA Trend Loss** | close lost key EMA (settle-gated) | EXIT_FULL |
| 6 | **C · ATR Trail** | price < peak − (ATR × trail mult) | EXIT_FULL |
| 7 | **E · Time** | hold exceeds strategy time limit | EXIT_FULL |

- Every module returns an `ExitSignal(priority, module, action, code, reason, …)`; `evaluate_exit_engine()` collects all, sorts, and executes the top one, recording full arbitration telemetry.
- **Injectable clock:** `_age_hours(entry, now)` takes an optional `now`. Live passes real time; the backtester passes the simulated bar time — so Module E and the EMA settle-gate age *identically* in sim and live. **This is the parity guarantee.**

---

## 5. Research Lab — offline validation & approval gate

**Data layer** (`lab/data_store.py`, `lab/seed_history.py`, `lab/backfill.py`):
- Local **SQLite `historical_candles.db`** (WAL mode, `idx_candles_key(symbol,timeframe,ts)`), seeded with ~2 years of 1d + 4h OHLCV from Binance public CSVs + CCXT — protects the live thread and API credits.
- `LabDataAppender` nightly-appends latest candles; `coverage()` reports data windows.

**Backtester** (`lab/backtest.py`): `run_backtest()` is pure-compute, driving the *same* `evaluate_exit_engine` + strategy functions through the injected clock. Produces equity curve, max drawdown, MFE/MAE, and a composite `_trade_quality` score.

**Optimizer** (`lab/optimize.py`):
- `grid_search` over parameter grids (metric e.g. `return_over_dd`),
- `sensitivity` sweeps a single parameter across values,
- `walk_forward` — chronological Train/Validate/Test folds (default 60/20/20 style) to measure out-of-sample robustness and prevent curve-fitting.

**Job queue & reporting** (`lab/runner.py`, `lab/lab_report.py`):
- `LabWorker` — async job queue; runs stamped with `git_hash()` for reproducibility.
- `build_lab_report()` — standalone PDF of each validation run.

**Approval gate** (`lab/proposals.py`):
- `best_params_from_run` → `build_diff` (proposed vs current settings) → operator reviews the diff → `apply_to_settings` promotes validated params to live. Nothing reaches production without passing the gate.

---

## 6. Frontend (web) — mobile-first cockpit

- **Navigation:** sticky **bottom tab bar** (Cockpit · Portfolio · Datalogs · Research Lab) with a filled active state; **Instagram-style horizontal swipe** between tabs; **hide-on-scroll dynamic top header** that shows per-tab context (account metrics on Cockpit, Invested/Current/P&L on Portfolio, titles elsewhere) + the Paper/Live switch.
- **Cockpit:** bot-brain strip (Scanned/Setups/Rejected/Qualified/Regime), condensed watchlist dropdown + sync dot, chart drawer, per-trade **Trade Life Cycle** (Entered → In Profit → Trail Armed → Exit Watch), a side-by-side **analytics slider** (Leaderboard & Analytics ⟷ Counterfactual Engine), and a single merged **Position Tracker** (open positions + full executions table).
- **Portfolio:** Zerodha-style — **Holdings** (Invested/Current/P&L + Today's P&L) and **Closed Trades** history.
- **Datalogs:** Strategy Research Lab, attrition funnel, breaker accuracy, rejection leaderboard, winner profile, RSI distribution, missed-opportunity & zone-effectiveness panels, **AI Reasoning Log** + **Confidence Distribution**.
- **Research Lab:** strategy validation runner, PDF export, kill-switch, and the promote-to-production approval flow.
- **Performance:** shared `AppDataContext` (single poller) + backend warm cache → sub-second fresh loads.

---

## 7. Data models (MongoDB)

- `users` — `{ email, password_hash, role }`
- `settings` — active strategy, risk config, symbols, fees/slippage, kill-switch
- `portfolio` / `positions` — `{ symbol, quantity, avg_cost, last_price, market_value, peak_price, structural_stop, unrealized_pnl, breakout_mode, day_start_equity }`
- `trades` — `{ side, symbol, price, notional, pnl, return_pct, hold_seconds, timestamp, entry_timestamp, exit_reason, exit_module, potential_best_exit, potential_worst_exit, mfe_pct, mae_pct }`
- `reasoning` — LLM/engine decisions `{ bias, confidence, note, timestamp }`
- research collections — funnel, rejections, confidence buckets, counterfactual resolutions
- `lab_runs` — `{ status, params, assets, window, git_hash, results }`
- `lab_param_proposals` — `{ status, diff, applied_at }`
- SQLite `historical_candles` — `{ symbol, timeframe, ts, o, h, l, c, v }`

---

## 8. API surface (selected, all under `/api`)

**Live/portfolio:** `GET /market/snapshots`, `GET /portfolio`, `GET /trades`, `GET /reasoning`, `POST /positions/{base}/close`, `GET /live/status`, `GET/POST /environment[/{mode}]`
**Research/analytics:** `GET /research/{summary,funnel,rejections,winner_profile,missed_opportunities,rsi_distribution,zone_effectiveness,strategy_lab,staged_exit,entry_quality}`, `GET /analytics/{performance,graduation}`
**Research Lab:** `POST /lab/runs`, `GET /lab/runs[/{id}]`, `GET /lab/runs/{id}/pdf`, `POST /lab/runs/{id}/propose`, `GET /lab/proposals`, `POST /lab/proposals/{id}/{apply,reject}`, `GET /lab/data/coverage`, `POST /backtest/{run,sweep}`
**Control/auth:** `POST /auth/{login,logout}`, `GET /auth/me`, `GET/PUT /settings`, `GET /watchlist/validate`, `POST /watchlist/sync`, `POST /cycle/run[/{base}]`, `GET /report/{full,trades,reasoning}.pdf`

---

## 9. Design principles

1. **Parity by construction** — the backtester never forks strategy logic; it injects a clock into the live functions.
2. **Capital preservation first** — structural stop (Priority 1) and the emergency kill (Priority 2) outrank every profit-taking rule.
3. **Explainability** — every exit records the winning module + full arbitration; every setup records why it was accepted/rejected (counterfactual telemetry).
4. **Data isolation** — offline SQLite (WAL) keeps validation off the live thread and off paid API quotas.
5. **Gated promotion** — validated parameters reach production only through a reviewed diff.
