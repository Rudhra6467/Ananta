# Ananta — Backend Architecture & Engineering Brief

> Grounded in the actual code (June 2026). File references are exact. Read this before
> proposing engine-level changes so you know what is hardcoded vs configurable, and what
> the declarative engine can/can't do.

---

## 1. Overall System Architecture

### Components & where they live
| Component | File(s) | Responsibility |
|---|---|---|
| Regime Classifier | `regime.py` | "What market is this?" — one label per asset from its own 4h bars |
| Strategy Router | `router.py` | Regime → which alpha models are *allowed* to act |
| Entry strategies (core) | `primary_layer.py` (Hunter), `squeeze.py`, `continuation.py` | Identify entries only; tag position with `strategy` + profile |
| Entry strategies (declarative) | `strategy/declarative_defs.py` + `declarative_engine.py` | Catalog/indicator strategies from JSON specs |
| Universal Exit Engine | `exit_engine.py` | Owns ALL risk after entry (modules A–F, S, D, KILL) |
| Live position watcher | `position_watcher.py` | ~15s loop; runs the exit engine on open positions |
| Live entry loop | `trading_engine.py` | ~90s cycle; regime → route → strategy eval → risk → order |
| Risk engine | `risk_engine.py` | Position sizing, caps, daily-loss ruin-line |
| Research Lab backtester | `lab/backtest.py` | Deterministic historical replay (PARITY with live) |
| Lab job queue | `lab/runner.py` | Async worker (process pool), progress %, multi-TF orchestration |
| Monte Carlo | `lab/monte_carlo.py` | Bootstrap risk-of-ruin over realised P&L |
| Config/schema | `strategy/core.py`, `strategy_runtime.py` | Versioned schemas, sparse+inherited configs |

### Data flow: signal → execution → exit
```
1h bars (market_data / lab.data_store)
        │
        ▼
classify_regime(bars_4h)  ──►  route(regime)  ──►  eligible core models
        │                                              │
        ▼                                              ▼
  [core] evaluate_primary / evaluate_squeeze / evaluate_continuation   (regime-gated)
  [decl] declarative_engine.evaluate(spec, bars, params)              (NOT regime-gated)
        │  (triggered? → strategy identity + structural_stop + entry_profile)
        ▼
  Risk check (risk_engine): lot sizing, max concurrent, daily-loss line, spread guard
        │
        ▼
  Order fill (live_execution: LIVE / DRY_RUN / PAPER)  →  Position created, tagged pos.strategy
        │
        ▼
  Universal Exit Engine (position_watcher, every ~15s) — modules A–F arbitrate → EXIT/TIGHTEN
```
**Key architectural principle:** entry strategies are *decoupled* from risk. A strategy's
only job is "is there an entry here?" + tag identity + set an initial structural stop.
Everything after that (stops, trailing, profit protection, time exits) is owned centrally
by the Universal Exit Engine. This is why exits can be A/B tested independently of entries.

---

## 2. Strategy Implementation

### Core strategies (hardcoded Python, bespoke logic)
- **Hunter** (`primary_layer.py::evaluate_primary`) — "buys fear." Regime-aware: picks one of
  3 entry profiles by regime:
  - `AGGRESSIVE_PULLBACK` (strong uptrend): first touch of support, no deep RSI reset needed.
  - `STABILIZED_REVERSAL` (default): classic 4 gates — support zone + pullback (not chasing) +
    volume exhaustion + RSI reset (30–35 band) + VCP base + HTF trend filter.
  - `DEEP_DISCOUNT` (panic): requires *acceptance* (≥2 bars inside the demand zone).
  - Every failed gate emits a `REJECTED_*` code (Rejection Leaderboard).
- **Squeeze** (`squeeze.py::evaluate_squeeze`) — "buys expansion." BB inside Keltner (coil) →
  wait for CONTINUATION (inside-bar break) or RETEST (pullback to 20MA then reclaim). Stop = 20MA.
- **Continuation** (`continuation.py::evaluate_continuation`) — "buys the dip in an uptrend."
  50-EMA rising + 20>50 + price>50EMA, controlled pullback to 20-EMA, volume dry-up, RSI 40–62,
  non-chasing candle. Structural stop below pullback low − 0.4×ATR.

These read tunables off `RiskSettings`/per-strategy config via `getattr(settings, ...)`.
Their thresholds are **configurable** (cont_ema_slow, rsi_reset_max, etc.) but their **logic
is hardcoded** — you cannot express Hunter as a declarative spec.

### Declarative strategies (data-defined, no bespoke Python)
- Defined in `strategy/declarative_defs.py::DECLARATIVE` (12 today: ema-cross, supertrend,
  rsi-momentum, macd-trend, bollinger-mr, donchian-breakout, atr-breakout, keltner-breakout,
  turtle, time-series-momentum, stochastic-momentum, vwap-mr).
- Each entry = `{name, dna, params:[ParamSpec], spec}`. The `spec` is
  `{indicators:{}, entry:[conds], exit:[conds]}`. `$param` placeholders resolve from params.
- Executed by `declarative_engine.py::evaluate(spec, bars, params)`. Entry conds are **AND-ed**,
  exit conds are **OR-ed**, evaluated on the latest closed bar.
- Registering a def auto-creates the schema → it appears in registry/metrics/configs/backtest/live
  with full parity. **Adding a new indicator strategy = add one dict, no engine change.**
- Imported strategies (AI import pipeline) register at runtime via `register_imported()`.

### Declarative engine — capabilities & LIMITATIONS
Supported indicator fns (`declarative_engine.SUPPORTED_FNS`): ema, sma, rsi, atr, macd_line/
signal/hist, bb_lower/mid/upper, donchian_high/low, atr_breakout_level, keltner_upper/mid,
supertrend_dir/line, roc, stoch_k/d, vwap, vwap_lower/upper.
Supported ops (`SUPPORTED_OPS`): cross_above, cross_below, gt, lt, gte, lte, rising, falling.

**Cannot currently express:**
- OR-groups within entry (entry is strictly AND-ed; only exit is OR-ed).
- Multi-timeframe conditions in one spec (single bar series only).
- Stateful logic: "inside bar then break", acceptance counting, VCP contraction, swing-structure,
  volume-vs-climax ratios — i.e. anything the 3 core strategies do.
- Position/PnL-aware entries, look-back windows beyond the indicator primitives, custom math ops.
- No parameterised comparison other than the fixed op set; no arithmetic between operands.

### How params load & apply (UI edit → engine)
`strategy/core.py` defines: **Schema** (versioned, static, `key@version`) → **Config** (sparse
overrides, tenant-scoped, inheritable via `parent_config_id`) → resolved param set.
- `resolve_config()` = schema defaults ← parent chain (root→leaf) ← self (leaf wins).
- `resolve_active_params()` (`strategy_runtime.py`) resolves the ACTIVE config per strategy,
  filters to `engine_backed` params, clamps, and **strips ACCOUNT_LEVEL_FIELDS** (those stay
  global). `overlay_settings(base, params)` returns a per-strategy COPY of RiskSettings.
- `resolve_full_params()` keeps EVERY param (incl. non-engine indicator knobs) — used to drive
  the declarative executor live.
- Net effect: editing a strategy's params in the UI writes a `strategy_configs` row; activating it
  sets `strategy_meta.active_config_id`; the live loop overlays it for THAT strategy only, in
  isolation from others. Account risk (max positions, daily-loss) is never touched.

---

## 3. Universal Exit Engine (`exit_engine.py`) — MOST IMPORTANT

### Modules & priority (lower number wins)
| P | Module | Action | Trigger |
|---|---|---|---|
| 1 | A Structural/Hard-stop | EXIT_FULL | %-stop, structural stop, or locked profit floor breached (tightest breached level wins) |
| 2 | KILL | EXIT_FULL | Emergency/kill-switch injected by caller |
| 3 | F Profit Protection | TIGHTEN | Stage 1: MFE≥`breakeven_r` → lock stop to breakeven. Stage 2: MFE≥`profit_arm_pct` → lock +1% floor |
| 4 | B Momentum Exhaustion | EXIT_PARTIAL (50%) | Overbought zone (RSI≥70/80) + volume climax + exhaustion candle (one-time) |
| 5 | S Structure Failure | EXIT_FULL | Fresh lower-low + momentum dead (RSI<50 & below 20-EMA), guarded to protect gains |
| 5 | D EMA Trend Loss | EXIT_FULL | Close below 20-EMA / 20-50 dead-cross (squeeze/bear: single close below 20EMA) |
| 6 | C ATR Trail | EXIT_FULL | Armed trailing stop = peak − `trail_atr_mult`×ATR; arms at +`trail_arm_r`R or %-arm |
| 7 | E Time Exit | EXIT_FULL | Stagnation (≥48h flat PnL) or hard time cap (`time_exit_hours`) |

### Priority arbitration
`evaluate_exit_engine()` runs ALL modules, collects raised `ExitSignal`s, then does a
**single-pass sort by priority number; lowest wins**. Deterministic, no cross-mutation between
modules. All raised signals are returned as telemetry even though only one executes.

### Per-strategy exit profiles (`PROFILES` dict)
Each core strategy has a `StrategyProfile`: `profit_arm_pct`, `trail_atr_mult`, `time_exit_hours`,
`ema_priority`, `breakeven_r`, `trail_arm_r`, `structure_exit`. e.g. Hunter (5%, 2.0×ATR, 72h);
Squeeze (4%, 2.5×ATR, no time cap, ema_priority). `profile_for(strategy, settings)` patches the
base profile with any Research-Lab-promoted `profile_overrides`.

### ATR Trailing (Module C) — internals
- Peak tracked as `max(peak_price, last)`. Arms on EITHER `run_up_r ≥ trail_arm_r` (default +2R)
  OR legacy `%-arm` (`trail_arm_pct`), whichever first.
- Once armed: `trail_stop = peak − trail_atr_mult × ATR`. Falls back to a static `%` trail
  (`trail_distance_pct`) when ATR unavailable. Exit when `last ≤ trail_stop`.
- Live watcher (`position_watcher.trail_distance_for`) additionally supports a **volatility-adaptive**
  trail: `clamp(dynamic_trail_k × ATR_percentile, min, max)` when `dynamic_trail_enabled`.

### Fixed Target/Stop vs ATR (backtest, `lab/backtest.py`)
The Lab supports 3 exit MODES chosen per run (`exit_method`):
- `fixed`: exact limit-style fills netting +`target_profit` / −`target_loss` **after fees**
  (`_close_fixed`). Loss checked before profit (pessimistic) if a bar spans both.
- `atr`: standalone ATR stop/trail (initial = entry−mult×ATR, trail = peak−dist×ATR once past
  activation %). Independent of the full engine.
- `native`/`engine`: the FULL Universal Exit Engine (modules A–F) as live.

### Breakeven / Profit Protection & Partial — status
- **Breakeven + profit floor**: IMPLEMENTED (Module F, staged, upgrade-only, gated by
  `profit_protection_enabled`).
- **Partial profit taking**: IMPLEMENTED but only as a momentum-exhaustion 50% trim (Module B),
  NOT a user-configurable "take X% at +Y%" ladder. That ladder is a Phase-3 gap.

### Where exits are evaluated
- **Live**: `position_watcher.py::watch_once` every ~15s calls `evaluate_exit_engine` per open
  position (separate watcher, NOT inside the entry strategy). For declarative strategies, the
  strategy's own OR-ed exit spec is consulted only when the universal engine says NONE.
- **Backtest**: `lab/backtest.py` PASS 2 — a pessimistic intrabar LOW pass (catch stop/trail
  first) then a bar-CLOSE pass (tighten/partial/EMA/time). Uses the SAME `evaluate_exit_engine`.

---

## 4. Research Lab / Backtesting

### Parity with live
`lab/backtest.py` reuses the EXACT live functions: `classify_regime`, `route`, `evaluate_primary`,
`evaluate_squeeze`, `evaluate_continuation`, `evaluate_exit_engine`. No forked "backtest_*" logic —
only the data source (`lab.data_store` SQLite candles) and the clock differ.

Execution model (no look-ahead): signals evaluated on CLOSED bar i, entry fills at bar **i+1 OPEN**;
taker fee + `SLIPPAGE_PCT` (0.05%) on every leg; Module E / EMA settle-gate age off the SIMULATED
bar clock (injected `now`). `WARMUP_BARS=200`, `ANALYSIS_LOOKBACK=750` (matches live EXEC_BARS_LIMIT).

### Two-pass design (why exit A/B testing is valid)
- **PASS 1** `_scan_entry`: exit-agnostic rising-edge entry scan → fixed entry set.
- **PASS 2**: replay each entry as an independent trade under the selected exit engine.
- `run_multi_exit()` reruns PASS 2 with 5 exit configs on the SAME entries → a true A/B/C test.

### Why only some strategies produced trades earlier
Before the fix, `_scan_entry` only wired the 3 core strategies. Declarative catalog strategies
(turtle, TSM, VWAP-MR, stochastic-momentum, …) had no entry path in the Lab so they produced ZERO
trades. Fix: the loop at `lab/backtest.py:247` now builds `decl_specs` from `DECLARATIVE` and calls
`declarative_engine.evaluate` for any selected declarative strategy (no regime gate) — parity with
the live deploy path.

### Multi-timeframe (current state)
- `runner.py` already orchestrates multiple TFs: `timeframes = ["1h"] + COMPARE_TIMEFRAMES(30m,15m)`
  when `compare_timeframes` is set. Result carries `multi_timeframe[symbol] = {by_tf, verdict}` and
  `_tf_verdict` picks the best TF by return-over-drawdown.
- Gap = FRONTEND: `researchStore.js` doesn't send `compare_timeframes` nor render per-TF sections.
  Backend is ready; this is Phase 2 UI work.

### Monte Carlo (`lab/monte_carlo.py`)
Bootstrap (resample-with-replacement) the realised per-trade P&L multiset `iterations` times, walk
an equity curve each time. Reports risk-of-ruin (equity ≤ start×(1−threshold) at ANY point),
prob-of-profit, final-return percentile bands, max-DD distribution, histogram, and a verdict
(ROBUST / ACCEPTABLE / FRAGILE). Needs ≥5 closed trades. Pure numpy, seed=42 (deterministic).

### Regime labels in backtest
`regime_at_entry` is stored on every trade (computed from the point-in-time window at entry).
`_summarize._bucket("regime_at_entry")` produces the per-regime breakdown in results/PDF.

---

## 5. Regime Detection & Filtering

- **Computed** in `regime.py::classify_regime(bars_4h)` from the asset's OWN 4h bars using
  RSI, EMA20/50/200 stack, ADX, ATR percentile, Bollinger-width percentile, swing structure.
- **Labels**: TREND_UP / TREND_DOWN / RANGE / COMPRESSION / REVERSAL / NEUTRAL.
  Priority: compression > reversal(panic) > strong trend > range > neutral.
- **Filtering is applied at ENTRY** (not just analysis). `router.py::_REGIME_MAP`:
  - TREND_UP → `continuation` only (further gated by 4H trend filter `htf_trend_enabled`)
  - REVERSAL → `hunter`
  - COMPRESSION → `squeeze`
  - RANGE / NEUTRAL / TREND_DOWN → **NO trading** (stand aside)
- Live loop calls `hunter_allowed/squeeze_allowed/continuation_allowed` before evaluating each
  core model. **Declarative strategies are NOT regime-gated** — they fire purely on their spec.
- **Limitation**: regime is per-asset from 4h bars; no cross-asset/market-breadth regime; NEUTRAL
  blocks everything (can feel over-conservative). The deploy-time regime warning UI (P1 backlog)
  surfaces when a user deploys a core strategy out of its regime.

---

## 6. Data & Configuration

- **Config storage**: `strategy_configs` (Mongo) — sparse overrides, `tenant_id`, `strategy_version`,
  `parent_config_id`, `origin`, `validation_status`, `rating`. `strategy_meta.active_config_id`
  marks the live one per strategy.
- **Versioning**: schemas are `key@version` in a REGISTRY; `_LATEST` tracks newest. Configs pin a
  `strategy_version` so old configs resolve against the schema they were built for.
- **Catalog default vs user-edited**: `resolve_config` layers schema defaults → parent chain →
  user overrides. Unset params always fall back to catalog defaults. Engine consumes only
  `engine_backed` params; account-level fields stay global (never overridable per strategy).
- **Per-candle / trade-log data** available for analysis (`lab/backtest.py` trade dict):
  entry/exit price, qty, pnl, return_pct, **mfe_pct/mae_pct**, potential_best/worst_exit,
  hold_hours, exit_module, exit_reason, regime_at_entry, entry_profile, strategy,
  **trade_quality_score**, position_size_usd, mfe_usd/mae_usd, captured_pnl, profit_left_usd,
  confidence. Summary adds Sharpe/Sortino (per-trade), profit factor, capture_rate, and
  breakdowns by exit_module / regime / strategy.

---

## 7. Known Limitations & Technical Debt

**Stable:** Universal Exit Engine (modules + priority), regime classifier + router, core 3
strategies, Lab backtester parity, Monte Carlo, config schema/versioning/inheritance.

**Evolving / gaps:**
- Declarative engine: entry is AND-only (no OR-groups), single-timeframe, stateless — can't
  express the core strategies or acceptance/structure logic.
- Exit selection in the Lab UI currently exposes only ATR + Fixed (backlog: Breakeven+Trail,
  Partial ladder, Structural, Momentum Exhaustion, Time-Based as first-class selectable exits).
- Multi-timeframe is backend-ready but not wired in the Lab UI (Phase 2).
- Partial profit is momentum-triggered only; no user-defined take-profit ladder.
- Regime is per-asset 4h only; NEUTRAL/RANGE/TREND_DOWN block trading entirely.
- Pairs Trading strategy = "Reference Only" (mocked, not wired).
- Auth is single-owner today; multi-tenant fields exist (`tenant_id`) but full multi-tenant accounts
  are a future task.
- Strategy Import pipeline UX is developer-focused (needs simplification — P1 backlog).

**Constraints when suggesting improvements:**
- Anything requiring stateful/multi-TF/OR-group entry logic = engine change (not just a spec).
- Live vs Lab parity is a hard invariant — don't fork exit/entry logic; extend the shared functions.
- Backtest is pure-compute in a worker process (CPU-bound, single worker); heavy new logic affects
  run time (budgets: 300s/backtest, 900s/exit-comparison in `runner.py`).
