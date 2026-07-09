# Ananta — Unified Roadmap (VALIDATION-FIRST ARCHITECTURE)

> **P3 UPDATE (2026-07-09, iter37):** ✅ Phase A — per-strategy engine configs SHIPPED. Engine resolves each
> strategy's params from its active config (account-level risk stays global); activation no longer clobbers
> the global RiskSettings. Web + mobile activate/revert UI + backend tested (32/32). See CHANGELOG iter37.
> **NEXT — Phase B:** generic declarative executor to wire simple indicator catalog strategies (EMA Cross,
> Supertrend, RSI Momentum, Bollinger MR, MACD…) to the live/paper engine, gated by strategy_meta + shared
> risk budget; imported free-text strategies stay catalog-only until mapped to codeable rules.
> **P2 UPDATE (2026-07-09):** ✅ Strategy Import Pipeline SHIPPED (import Pine Script/Freqtrade/Jesse/JSON →
> AI-extract → validate → review/edit → approve into Library; web+mobile parity, owner-gated). See CHANGELOG iter36.
> **NEXT P2:** wire the remaining catalog library strategies (incl. imported ones) to the LIVE trading engine
> incrementally — their schema already carries entry/exit/params/direction. Then P3 per-strategy engine configs.


> **Foundational shift (2026-06-02):** This file has been PURGED and rebuilt around an
> institutional **validation-first** framework. The governing question is no longer
> *"How do we build more features?"* but **"How do we PROVE the existing system has a real edge?"**
> The biggest current risk is **feature accumulation**; the antidote is **instrumentation** —
> logging, auditing, counterfactual analysis, confidence-bucket tracking, and component-level
> validation — BEFORE any new complexity is added.

> **STATUS: READ-ONLY CONTEXT. DO NOT DEPLOY ACTIVE CODE. DO NOT EXECUTE LIVE TRADES.**
> No development work may bypass the linear phase order below.

---

## 0. FORWARD EXECUTION PLAN (next steps · authored 2026-06-16)
> Architecture is built (Phase 1.5 technical-first, Phase 2 layered Primary/Secondary engine,
> rejection leaderboard, counterfactual DB, Phase 3.1 Ananta cockpit). The remaining work is to
> **PROVE the edge, then tune, then gate, then (maybe) go live.** Strictly linear A → B → C → D.

- **🟢 Phase A — Data-Gathering Sprint (NOW → ~4 weeks) · ACTIVE.**
  Engine live in PAPER on a clean slate. RULE: **do NOT touch the logic** (changing gates mid-sample
  curve-fits to noise). 3-day review cadence via `Reports → Rejection Leaderboard` + `Counterfactual
  Engine`. **Exit criteria:** ≥ ~150–200 resolved counterfactuals AND ≥1 observed regime shift (a
  down-leg so the engine actually fires, not just rejects in an uptrend). Deliverable: baseline
  "what the bot would have done" dataset.
- **🟡 Phase B — Logic Tuning (data-driven, after A).** Adjust gates ONLY with Phase-A evidence
  (e.g. loosen RSI ≤35→≤40 if it blocks resolved Missed Winners; keep volume strict if it saves
  losses). Replace the catastrophe-veto PROXY (BEARISH ≥0.80) with a real crisis signal. Ship the
  **Settings UI** for all gate tunings (RSI/volume/pullback/stop-buffer/catastrophe). Confirmation
  sprint after each change.
- **🟠 Phase C — Validation Gate (Go/No-Go).** Hard quantitative checkpoint, NET OF SIMULATED
  FRICTION (fees+slippage): positive expectancy `(win%·avg_win) − (loss%·avg_loss) > 0`; healthy
  greenlit→win rate per confidence band with adequate N; beats a **null-model benchmark**
  (random/always-in). Build the execution-friction simulator + null-model suite here.
- **🔴 Phase D — Live Preparation (Execution Layer / Product C) — gated behind C.** Tiny fixed live
  size; independent per-capability kill-flags (default OFF); order reconciliation; real-fill vs
  expected-fill logging; daily-loss circuit breaker; manual arm/disarm.
- **Supporting UI/UX (parallel, low-risk):** S/R zone overlay + structural-stop line on the cockpit
  chart; Settings reskin (also needed in B); optional support-zone proximity alerts.
> Discipline: never skip to live; never tune during a gathering window.

### NEXT PHASE — OPPORTUNITY COVERAGE (user steer 2026-06-21, NOT YET BUILT — execution still FROZEN)
- User's biggest concern: bot may be idle because the Hunter is TOO restrictive, not because markets are quiet.
  The Strategy Sandbox is the measurement tool to answer this. Once ~30+ resolved signals exist per strategy:
  - Consider LOOSENING the Hunter (only after data says go): RSI ≤ 35 -> ≤ 45; "exactly at support" ->
    "near support zone"; "strong reaction candle" -> "moderate reaction".
  - Promote SHADOW strategies (VCP first) to Category A (EXECUTE) only after positive expectancy proven.
  - Add a "Trade Opportunity Coverage" metric (signals per strategy) to answer quiet-market vs over-restrictive.
- Do NOT add more hard filters. Focus next phase on finding MORE valid setups, not more reasons to wait.


### DEFERRED FIXES (queued 2026-06-18 — bundle with the Phase-B Settings reskin)
- **Owner-triggered production reset endpoint.** Add an owner-auth-gated endpoint/button that runs the
  `reset_sprint.py` logic against the live DB (wipes research_log/trades/reasoning, resets to flat
  $300 / $20 lot / 10-asset PAPER). Needed because reset is a manual script that only ran on PREVIEW —
  production still holds stale data + a stale watchlist. Default-safe; owner clicks once after deploy.
- **Watchlist is DB-sourced, not code-sourced.** Both the scan loop (`trading_engine.py` `enabled_symbols`)
  and the cockpit ribbon read `settings.enabled_symbols` from Mongo, NOT `DEFAULT_ASSETS`. Production's
  saved settings predate the 10-asset migration (UPDATED 2026-05-30) so it scans the old set. Fix via the
  reset endpoint above AND/OR make `enabled_symbols` an editable watchlist field in the Settings UI.
- **Settings UI is misaligned with the live Hunter (cosmetic, non-breaking).** The visible controls
  (MIN LLM CONFIDENCE, MIN/MAX POSITION SIZE %, STRONG ATR/ADX/conf) are LEGACY — the Hunter ignores them
  for entries (macro only feeds the dormant CAUTION breaker; % sizing unused while adaptive is ON). The
  params that ACTUALLY drive the Hunter (`level_proximity_pct`, `rsi_reset_max`, `volume_exhaustion_window`,
  `pullback_max_green_body_pct`, `structural_stop_buffer_pct`, catastrophe/existential plug) are NOT exposed
  in the UI — bot uses code defaults. Phase-B Settings reskin must: expose the real Hunter tunings + editable
  watchlist, and hide/remove the dead legacy controls to stop confusing the operator. (Does NOT affect
  performance today — Hunter logic is identical preview vs prod via code defaults.)
- **Set `FRED_API_KEY` in production env** (already set in preview) so PAXG macro grounding is live on prod.
- **Live unrealized-P&L badge on the PORTFOLIO tab label** (e.g. "PORTFOLIO +$4.20", green/red) so open-trade
  health is glanceable from any tab without switching. Pure frontend — reads the `unrealized_pnl` sum from the
  existing `/api/portfolio` response. Small, high-signal cockpit touch.


### EXPANSION TRACKS (long-horizon — ALL gated behind Phase C validation; each lives in Product C
### with its OWN independent kill-flag, default OFF). These are NOT dropped — they sit after the
### crypto edge is proven. Cross-referenced to the detailed phases in §4.
- **Track 1 — Indian Equities/Derivatives (Zerodha/Kite).** `Phase 4` Ananta India Portfolio Doctor
  (READ-ONLY Zerodha ranking — may begin in parallel since zero downside) → `Phase 6` Indian
  Execution Layer (Kite live routing — gated behind Doctor performance).
- **Track 2 — Asymmetric "Lottery Ticket" Sleeve.** `Phase 5.5` (NEW). Allocates a small, ISOLATED
  risk budget (~$20–30) to high-multiplier, long-shot setups. Validated in PAPER against its own
  expectancy first; isolated budget that can never touch core swing capital; own kill-flag, default
  OFF. (Promoted from the V2-deferred "$5 Speculative Sniper / Lottery Mode" idea.)
- **Track 3 — Short-Selling & Derivatives (bearish regimes).** `Phase 7` Intraday Sleeves
  (DISABLED by default) → `Phase 8` Short-Selling & Advanced Multi-Asset Allocation (incl. PAXG
  rotation, commodities). Active execution during prolonged bearish macro; quarantined behind C.

---

## 1. MULTI-PRODUCT DECONSTRUCTION (3 independent modular pipelines)
Divide by **blast-radius / downside**, not by asset. The read-only research brain (A + B) may
evolve freely; every irreversible, capital-losing action is quarantined behind Product C.

- **Product A — Ananta Core:** Crypto swing-trading **edge validation**. Read-only research + PAPER.
- **Product B — Ananta India:** Portfolio Doctor intelligence. **Read-only, NO execution.**
- **Product C — Execution Layer:** ALL high-downside plumbing (live orders, intraday, short-selling).
  - Each capability inside C carries its OWN independent kill-flag, **default OFF**. Enabling
    crypto-live must NEVER accidentally arm intraday or shorting.

---

## 2. THE RESEARCH DATABASE  (Phase 2 — the most important addition in the project)
> ✅ STATUS (2026-06-04): **Slice 1 (logger) + Slice 2 (counterfactual resolver) SHIPPED** —
> `research.py`, `ResearchLog` model, `research_log` collection, additive logging in
> `evaluate_symbol`, `ResearchResolverLoop` (600s, CCXT-only), and `GET /api/research/log`,
> `GET /api/research/summary`, `POST /api/research/resolve`. 4-tier band + counterfactual cells live.
> Backend-only (no UI yet). Slice 3 (random BACKGROUND sampler) deferred (continuous all-symbol
> eval already gives unbiased coverage). Counterfactuals = RAW price (entry-quality proxy);
> friction-adjusted sim (§3.5c) + classification refinement still pending.

A permanent, append-only log of **every asset evaluation cycle — whether or not a trade occurs.**
Most retail bots only store entry/exit/PnL and fly blind. We store the full decision context so we
can later answer: *Was 0.80 better than 0.70? Did Gemini help or hurt? Were bearish calls accurate?
Did news add value?*

**Minimum schema per row:**
`Timestamp | Asset | Gemini_Confidence | News_Sentiment | Macro_Regime_Bias | Absolute_Decision (BUY/HOLD/REJECT)`

**Advisor-added enrichments (fold into the same schema / linked tables):**
- **Counterfactual P&L (HIGH VALUE):** for every REJECTED setup, resolve forward-only returns:
  `Asset | Confidence | Decision | 24h_Return | 72h_Return | 7d_Return`. Lets us classify each
  rejection as a **Saved Loss** (good filter) or a **Missed Winner** (over-filtered). FAR more
  informative than waiting for real trades. ⚠️ Hygiene: snapshot decision-time context; resolve
  returns forward-only — zero look-ahead leakage.
- **Signal Stability:** rolling per-asset confidence variance / flip-rate. A flapping
  0.81→0.32→0.88 signal is a red flag even when its average is high; a stable 0.81→0.83→0.82 is
  more trustworthy. Surface instability EARLY.
- **Decoupled thresholds (KEY DESIGN — resolves "dumb robot just sits there"):**
  LOG every evaluation **≥ 0.50**; only EXECUTE paper trades **≥ 0.80**. The DB fills fast while
  live discipline stays strict — the patient hunter trades rarely, the researcher sees everything.

> Cost note: we ALREADY compute confidence/sentiment/bias each cycle (Gemini is MD5-cached), so
> persisting it is cheap. The Research DB is low-credit instrumentation, not new compute.

---

## 3. DIAGNOSTIC VALIDATION METRICS (audit the "Patient-Hunter" WITHOUT arbitrary trade counts)
- **Decision Quality:** was rejecting during a choppy/bearish tape mathematically correct in
  protecting capital? (Driven by Counterfactual P&L above.)
- **Opportunity Capture funnel:** `Setups Detected → Failed Filters → Qualified Setups → Executed`.
  Audits whether the engine is too loose or too strict.
- **Near-Miss Analytics:** track outcomes of rejections strictly in the **0.70–0.79** band (and
  full buckets 0.70–0.74 / 0.75–0.79 / 0.80–0.84 / 0.85–0.89 / 0.90+) to empirically verify the
  entry floor. Maybe 0.72 performs identically to 0.84; maybe only 0.90+ is profitable — measure it.
- **Regime Accuracy:** do Bullish/Neutral/Bearish macro calls map to subsequent multi-day price
  action? ⚠️ Must be scored against a **null baseline** (buy-and-hold / coin-flip) over a FIXED
  horizon — in a drifting-up market everything looks "bullish-correct" otherwise.
- **Exit-engine reality check (advisor):** counterfactuals validate ENTRIES only. Trailing stops,
  slippage, maker fills, and chase-risk only reveal on ACTUAL executions. Bank ~15–25 real PAPER
  round-trips so the exit path is exercised — a bot that NEVER trades proves patience but never
  proves it can manage a winner.

---

## 4. MASTER ROADMAP — STRICT LINEAR SEQUENCE (no phase may be bypassed)

- **Phase 3.1 — ANANTA COCKPIT REDESIGN (frontend).** ✅ SHIPPED (2026-06-16). Full rebrand
  CryptoAtlas → **Ananta** with a matte-silver identity (graphite #090A0C base, silver #C0C5CE accent,
  green/rose semantics) replacing the cyan theme; inline SVG trident brand mark with a faded/ghosted
  damaruka (`AnantaTrident.jsx`). Decluttered single-viewport cockpit (`Dashboard.jsx`): Executive
  header (portfolio + Bot-Brain strip Scanned/Setups/Rejected/Qualified/Regime), 10-asset watchlist
  ribbon (click→chart), wide 4H candlestick (`CandleChart.jsx`, lightweight-charts v5; `/market/candles`
  extended to 4h/1d), swipeable analytics carousel (Counterfactual ring + Confidence histogram via
  recharts), Trade-Lifecycle stepper, Today's-Executions table. New **DataLogs / Reports** tab
  (`Reports.jsx`, renamed from "AI Reasoning Log") now houses the Why-No-Trade gate checklist, Filter
  Attribution table, Rejection Leaderboard + the reasoning log. Theme remapped via existing `atlas-*`
  tokens so all legacy components reskinned cheaply. All widgets bound to real APIs (no mocks).
  Design blueprint: `/app/design_guidelines.json`.
  ⏳ FOLLOW-UPS: expose new Settings tunings in matte-silver Settings UI; level-zone overlay on chart;
  full frontend QA pass (testing_agent) deferred per credit-control.

- **Phase 2 — PRIMARY/SECONDARY LAYERED ARCHITECTURE.** ✅ SHIPPED (2026-06-15). 1-Month Paper
  Sprint started on a FULL clean reset. Separates decision-making into two layers:
  - **Primary Layer** (`primary_layer.py`) — the SOLE entry driver. BUY greenlit only when ALL align:
    (a) historical support zone, (b) pullback confirmation / no chasing green candles, (c) volume
    exhaustion (negative 4H volume linreg slope), (d) momentum reset (4H RSI-14 ≤ 35). RSI helper added
    to `setup_classifier.py`.
    Tunings: `rsi_reset_max=35`, `volume_exhaustion_window=6`, `pullback_max_green_body_pct=1.5`.
  - **Secondary Layer** (`secondary_veto.py`) — PASSIVE binary veto. PASS by default (neutral/quiet/
    missing data never penalizes). Vetoes only on catastrophe (proxy: macro BEARISH ≥ 0.80 until a
    dedicated crisis feed lands).
  - **Exit risk** — hard structural stop 2.0% below the zone's lowest wick; trailing take-profit on profit.
  - **Rejection Leaderboard** — `reason_codes[]` logged on EVERY evaluation; `GET /api/research/rejections`
    aggregates the distribution (per-code + per-symbol) for the 3-day iterative sprint reviews.
    Codes: GREENLIT, REJECTED_NO_SUPPORT_ZONE, REJECTED_CHASING_GREEN_CANDLE,
    REJECTED_VOLUME_NOT_EXHAUSTED, REJECTED_RSI_NOT_RESET, REJECTED_SECONDARY_VETO_CATASTROPHE,
    REJECTED_HARD_KILL, REJECTED_MAX_POSITIONS, REJECTED_COOLDOWN, REJECTED_LOW_LIQUIDITY, HOLD_NO_SIGNAL.
  - **Watchlist → 10 assets**: BTC, ETH, SOL, AVAX, XRP (L1) · LINK, AAVE (DeFi) · ARB (L2) ·
    RENDER (AI) · PAXG (Metal). Confirmed PAPER lock.
  - Tests: `tests/test_layered_architecture.py` + updated `test_adaptive_sizing.py`. `reset_sprint.py`
    performs the destructive blank-slate reset.
  - ⏳ FOLLOW-UPS: frontend Rejection-Leaderboard dashboard for the 3-day reviews; dedicated crisis
    detector to replace the bearish-macro veto proxy; Settings UI for the new gate tunings.

- **Phase 1.5 — TECHNICAL-FIRST RE-ARCHITECTURE.** ✅ SHIPPED (2026-06-15). Owner-directed pivot from
  Gemini-confidence-dominant fusion (which froze the bot — e.g. the SOL bull run: macro dropped to 0.10
  because on-chain lagged + news was BTC-centric, blocking a clean technical setup) to a "clean
  chance-taking" model:
  - **Historical Horizontal Level Engine** (`levels.py`): fractal swing-pivot detection + price
    clustering over ~18mo Daily + ~90d 4h candles → durable multi-touch S/R zones. Credit-free
    (CCXT-only, 6h cache). `GET /api/levels/{symbol}`. Verified: SOL maps a 23-touch $82–85 zone.
  - **Technical-First fusion** (`risk_engine.fuse_signals` rewrite): price testing a clean historical
    support zone is *sufficient alone* to BUY. Macro/news DEMOTED to a one-way CATASTROPHIC veto
    (BEARISH ≥ `catastrophe_veto_confidence` 0.80); the old low-confidence HOLD that froze the bot is
    REMOVED. Neutral/quiet macro never blocks a clean technical trade.
  - **Structural exit risk** (`Position.structural_stop`, `position_watcher`): on a level entry a hard
    stop is placed just below the zone (`zone_low × (1 − structural_stop_buffer_pct)`); the market
    trading through it confirms the break. Trailing take-profit unchanged (arms on profit).
  - New `RiskSettings`: `level_entry_enabled`, `level_proximity_pct`, `level_zone_tol_pct`,
    `level_min_touches`, `level_lookback_days`, `structural_stop_buffer_pct`, `catastrophe_veto_confidence`.
  - Tests: `tests/test_levels.py`, `tests/test_technical_first.py` (incl. the exact SOL-freeze fix).
  - ⏳ FOLLOW-UPS (not yet built): Settings UI exposure of the new fields; a frontend levels overlay on
    the chart; optional "structural take-profit at overhead resistance".
- **Phase 1 — Crypto Paper Validation.** Continuous diagnostic logging.
  - ⚠️ EVIDENCE-GATED, not calendar-gated. Advance when **statistically meaningful** thresholds are
    hit (e.g. ≥150 qualified setups AND ≥30 counterfactual-resolved rejections per confidence
    bucket), NOT after a fixed "60–90 days." 5,000 obs in 30 days > 12 setups in 90 days.
- **Phase 2 — Research Database Integration.** Structured logging of ALL decisions (section 2).
- **Phase 2.5 — MODEL AUDIT (advisor-inserted; component-level ablation).** Before trusting the
  stack, prove each component earns its place:
  1. Does **Gemini** add value?  Technicals-only vs Technicals+Gemini.
  2. Does **news** add value?  Technicals-only vs Technicals+News (maybe only in breakouts).
  3. Does **confidence** add value?  Confidence-gated vs confidence-ignored.
  Possible discoveries: Gemini is huge / Gemini is noise / news helps only on breakouts /
  confidence doesn't correlate with returns. ⚠️ Costs extra Gemini calls (runs variants) — batch it.
- **Phase 3 — Crypto Explainability Layer.** "Why Buy" vs "Why NOT Buy" audit outputs per cycle.
- **Phase 3.2 — Analytics & Validation Dashboard (FRONTEND-ONLY).** Standalone, decoupled visual
  layer that renders ONLY data already collected in `research_log` + `shadow_trades`. No backend
  core-logic changes, no new compute, no extra API calls. Full spec in §4.6. Sits AFTER Phase 3 and
  BEFORE Phase 4 to keep visual rendering isolated from backend core-logic generation.
- **Phase 4 — Ananta India Portfolio Doctor.** Read-only Zerodha asset ranking & health scores.
- **Phase 5 — Live Crypto Execution.** Kraken deployment — GATED behind positive paper expectancy.
- **Phase 5.5 — Asymmetric "Lottery Ticket" Sleeve.** Small ISOLATED risk budget (~$20–30) toward
  high-multiplier long-shot setups. PAPER-validated against its OWN expectancy first; isolated budget
  (never touches core swing capital); independent kill-flag, default OFF. (Promoted from the
  V2-deferred Speculative Sniper note.)
- **Phase 6 — Indian Execution Layer.** Kite trade routing — GATED behind Doctor performance.
- **Phase 7 — Intraday Sleeves.** Speculative day-trading modules — DISABLED by default.
- **Phase 8 — Short-Selling & Advanced Multi-Asset Allocation.** Commodities/PAXG rotation.

---

## 3.5 VALIDITY SAFEGUARDS (mandatory — prevent the dataset from lying to us)
Three structural upgrades without which "clean" data is still misleading. These are NOT optional.

- **(a) Random Market Sampling Layer (anti-selection-bias):** every **30–60 min**, randomly sample
  1–2 assets and log the FULL feature state (confidence, sentiment, regime, structure) **even when
  NO setup exists.** Tag rows `BACKGROUND`. Purpose: build the **true-negative / null distribution**
  so the system can't circularly "discover" that interesting moments predict moves. Keep BACKGROUND
  rows OUT of setup-expectancy stats — they are the control group, not the experiment.
- **(b) Null Model Benchmark Suite (edge vs randomness):** every config must beat baselines or it
  has no edge. Baselines: **buy-and-hold BTC/ETH**, **random entry at matched frequency**, **simple
  EMA crossover.** ⚠️ CRITICAL GRADING RULE: in a crypto bull market raw buy-and-hold is nearly
  unbeatable, and the bot's thesis is **capital preservation, not max return** — so grade on
  **RISK-ADJUSTED** terms (**Sortino / max-drawdown / return-per-unit-drawdown**), NOT raw %. A bot
  capturing 55% of upside with 30% of drawdown is WINNING even at lower raw return. Grading on raw
  return is itself a trap that would wrongly kill a good defensive system.
- **(c) Execution Friction Simulator (economically realistic counterfactuals):** model
  fill-probability = f(spread, volatility, distance-from-touch, time-in-book) + slippage band
  (ATR/bps proxy) + maker/taker toggle. ⚠️ Must model **ADVERSE SELECTION** on maker/POST_ONLY
  orders: you are disproportionately filled right before price runs THROUGH you (queue-position
  loss). A friction sim that ignores this overstates maker performance — i.e. it lies in the bot's
  favor. This is what separates academic backtests from tradable systems.

## 3.6 FOUR-TIER CONFIDENCE ARCHITECTURE (each tier answers a different question)
Replaces the simple dual-threshold with a 4-tier band — accelerates evidence while preserving
discipline AND exercising the exit engine without spending the paper book:

| Tier | Band | Behavior | Validates |
|------|------|----------|-----------|
| **EXECUTE** | ≥ 0.80 | Real PAPER fills | True execution + exit reality (real slippage/fills) |
| **SHADOW** | 0.70–0.79 | FULL simulated trade-management (SL + trail) through the friction sim | Exit-engine behavior WITHOUT touching the book |
| **LOG-ONLY** | 0.50–0.69 | Entry context + counterfactual P&L only | Entry-filter calibration / near-miss analytics |
| **BACKGROUND** | random sample | Full state, no trade | Null/true-negative distribution (anti-bias) |

> The **Shadow Activation Band (0.70–0.79)** is the key bridge: it runs the FULL exit engine in
> simulation, partially solving the exit-validation bottleneck (counterfactuals validate ENTRIES
> only). SHADOW must run through Friction Sim (3.5c) to stay honest.

## 4.5 SUPPORTING UI WORK — SETTINGS 4-GROUP REFACTOR (recovered from prior roadmap; DOWNSTREAM)
> Owner-requested: ALL settings options shown in **4 exclusive accordion groups** (expanding one
> collapses the others). DOWNSTREAM of the Research DB — supporting work, not a gate. Includes the
> prior Phase-A items: float-zero input fix (parse on blur), per-category "Reset to Defaults",
> Validation Interlock (backend 400 on conflicting configs), enriched plain-English tooltips.
>
> **Precise field → group mapping (from current `RiskSettings`):**
> - **GROUP 1 · Risk & Account Survival:** `max_daily_loss_pct`, `account_max_drawdown_pct`,
>   `stop_loss_pct`, `position_size_pct_min/max`, `adaptive_sizing_enabled`,
>   `normal_lot_usd`/`strong_lot_usd`/`breakout_lot_usd`, `max_concurrent_positions`,
>   `vault_sync_enabled`/`vault_max_override_usd`, `manual_kill_switch`.
> - **GROUP 2 · Volatility & Trailing Exits:** `trail_arm_pct`/`trail_distance_pct`,
>   `dynamic_trail_enabled`/`_k`/`_min_pct`/`_max_pct`,
>   `breakout_trail_arm_pct`/`breakout_trail_distance_pct`, `position_watcher_interval_seconds`,
>   `sl_cooldown_seconds`/`trail_cooldown_seconds`, `strong_min_atr_percentile`/`strong_min_adx`,
>   `breakout_volume_percentile`.
> - **GROUP 3 · AI Macro & Confidence Gates:** `min_confidence`, `strong_min_confidence`,
>   `breakout_min_confidence`, `htf_trend_enabled`, `enabled_symbols` (editable watchlist).
> - **GROUP 4 · Exchange API, Execution & Connectivity:** `kraken_api_key/secret`,
>   `coinbase_api_key/secret`, `trading_mode` (PAPER/LIVE), `max_spread_pct`/`breakout_max_spread_pct`,
>   `taker_fee_pct`/`maker_fee_pct`/`breakout_paper_slippage_pct`.
> (Confirm mapping before build; watchlist could alternatively be promoted to a header element.)

## 4.6 PHASE 3.2 — ANALYTICS & VALIDATION DASHBOARD (FRONTEND-ONLY · EXISTING DATA ONLY)
> **Status:** PLANNED (architecture-only; no code yet). **Constraint:** strictly a read-only visual
> layer over data we ALREADY persist. ZERO new backend logic, ZERO new compute, ZERO new API calls,
> ZERO new Gemini credits. Decoupled from Phase 3 so visual rendering never touches core logic.
> **Data sources (verified fields):** `research_log` (`symbol`, `asset_class`, `macro_confidence`,
> `macro_bias`, `decision`, `tier`, `setup_strength`, `breakout`, `htf_trend_aligned`,
> `news_sentiment`, `reason`/`reasoning_id`, `price`, `cf_ret_24h/72h/7d`, `cf_resolved_*`) and
> `shadow_trades`/closed PAPER trades (`confidence`, `pnl`, `exit_reason`, `notional`, `fee_usd`,
> `slippage_usd`, `volatility_regime`, `entry_extension_pct`). The existing `GET /api/research/summary`
> already aggregates decision/tier distributions + per-confidence buckets + near-miss band — Phase 3.2
> CONSUMES these endpoints; it does not add new ones unless a pure read-aggregation is unavoidable.

### Widget Architecture (4 widgets, existing rows only)
- **Widget 1 · Trade Outcomes.** Win / Loss / Breakeven distribution from resolved SHADOW + PAPER
  exits. Source: closed-trade `pnl` (sign → W/L/BE via small ε band) + `exit_reason` breakdown
  (SL_HIT / TRAIL_HIT / MACRO_BEARISH). Render: donut + a small "exit-reason" stacked bar.
- **Widget 2 · Missed-Opportunity Funnel.** Classification of REJECT/HOLD rows using existing
  counterfactual cells: `classify_cf(cf_ret_*)` → **Correct Rejection** (rejected + forward return ≤
  band) vs **Missed Winner** (rejected + forward return > band). Render: funnel
  `Setups Detected → Failed Filters → Qualified → Executed` + a Correct-vs-Missed split bar. Only
  count `cf_resolved_*=true` rows so unresolved cells don't distort the ratio.
- **Widget 3 · Strategy Attribution.** Contribution ranking of the four signal factors —
  **Technical** (`setup_strength`/`breakout`), **Gemini Confidence** (`macro_confidence` bucket),
  **News Sentiment** (`news_sentiment` sign), **Market Regime** (`macro_bias`/`volatility_regime`) —
  by win-rate lift of winning trades that carried each factor "on" vs the base rate. Pure descriptive
  attribution (frequency among winners), NOT a model fit → no compute. Render: horizontal ranked bars.
- **Widget 4 · Confidence-Bucket Performance.** Win rate · sample size · avg counterfactual/realized
  return across the 4 tier bands **0.50–0.59 / 0.60–0.69 / 0.70–0.79 / 0.80+** (already produced by
  `/api/research/summary` buckets). Render: table + sparkline of win-rate by bucket, with sample-size
  badge that greys out buckets below an N-threshold (e.g. N<10) to discourage over-reading thin data.

### Drill-Down Interaction Schema (frontend-only, client-side filter)
- Clicking ANY widget element (a donut slice, a funnel segment, an attribution bar, a bucket row)
  sets a client-side filter `{factor?, decision?, tier?, confidence_band?, outcome?}` and renders a
  **sub-table** of the underlying decisions with columns:
  `Asset | Confidence | Bias/Regime | Why-Buy / Why-Not (reason metadata) | Decision/Tier | Resulting P&L (or cf_ret_24h proxy if no execution)`.
  Sub-table is paginated, sortable, CSV-exportable client-side. All filtering happens on rows already
  fetched from `/api/research/log` + closed trades — no per-click backend round-trips beyond the
  initial page fetch. "Why-Buy / Why-Not" cell links to the Phase-3 explainability metadata via
  `reasoning_id` (reuses Phase 3 output; no new generation).

### Credit-Free Over/Under-Filtering Metrics (ZERO extra API calls / compute)
Both derive purely from rows already in `research_log` (counterfactuals already resolved by the
existing 600s resolver) — no new Gemini calls, no new market fetches:
1. **Over-Filter Cost Index (are we too scared?).** Among REJECT/HOLD rows with resolved
   counterfactuals, % classified **Missed Winner** weighted by `cf_ret_72h`. A rising index in a
   bearish tape = the filter is leaving money on the table (too conservative). Pairs with its inverse
   **Saved-Loss Credit** (rejections whose forward return was negative = correctly dodged) so the net
   tells us if rejection discipline is actually net-positive right now.
2. **Selectivity / Conviction Drift Ratio (are we too loose?).** Ratio of
   `EXECUTE+SHADOW tier rows ÷ total evaluated rows` over a rolling window, cross-plotted against the
   realized win-rate of those taken trades. If the taken-fraction climbs while win-rate falls, the
   system is under-filtering (taking marginal setups in a hostile regime); if taken-fraction is near
   zero with healthy would-be counterfactuals, it's over-filtering. Both numerator/denominator are
   already-stored counts → a pure division, no compute.

> **Build note:** Phase 3.2 ships as new frontend route/tab + components consuming existing endpoints;
> if any aggregation isn't already in `/api/research/summary`, add it as a pure read-only projection
> (no writes, no model calls). It remains DOWNSTREAM of Phase 3 and a NON-GATE supporting layer.


---

## 5. GOVERNING PRINCIPLE
> The biggest trap now is adding more features. What Ananta needs most is **instrumentation**:
> logging, auditing, counterfactual analysis, confidence-bucket tracking, and component-level
> validation. Those teach us whether an edge exists far better than six more indicators or three
> more modules. **Measure first. Build second. Risk capital last.**

## 6. WHAT TO DO RIGHT NOW (zero credits)
Let the bot run in PAPER. The dry run is already accumulating the raw cycles the Research DB will
formalize. Bring observations (near-misses, regime calls vs reality, signal flapping) to the next
session so Phase 2 logging is designed against real patterns. Phase 1 build begins ONLY on owner's
explicit "go".

---

### ⚠️ Carry-over note from prior roadmap (superseded but retained for context)
The previous A→E phase plan (Settings 4-group accordion [now detailed in §4.5] / ruin-line
enforcement / read-only public + Owner JWT / regime-driven sizing / homepage redesign) is NOT
deleted as ideas — those quick-wins/safety items fold into Phases 1–3 and 5 of THIS framework as
supporting work, but they are explicitly DOWNSTREAM of validation. No UI/feature work precedes the
Research Database.

---
## P1 "App Store for Strategies" — status (2026-07-09)
- ✅ **Phase 1 DONE** (iter 34): Strategy Library (16 seeded, rich schema, AI grade) · chips + multi-select Filter drawer · CatalogDetail w/ AI summary + re-grade · multi-metric Leaderboard sort · Cockpit "Active Watchlist" + add-any-crypto. Web + mobile + backend, tested.
- 🟡 **Phase 2 NEXT**: Mobile interactive YouTube-style paging (Parts 7-10) — finger-follows-drag main-tab pager + Research subtab pager + nested boundary swipe transfer + premium motion (Part 13). Web: smooth animated tab transitions.
- ⚪ **Backlog**: Pine Script / Freqtrade / Jesse → JSON import converters (Part 6). Wire more library strategies to the live engine incrementally. Split `StrategyCenter.jsx` / `server.py` as they approach size limits.
