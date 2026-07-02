# CryptoAtlas AI Trading Dashboard - PRD

## Original Problem Statement
Build a full-stack "CryptoAtlas AI Trading Dashboard" - an Ontario-compliant, spot-only,
low-capital ($100 simulation) AI-assisted crypto trading bot system for a technical competition.
Emphasis on explainable AI, layered signal fusion, defensive architecture, and engineering discipline.
Not about "guaranteed profits" - about robustness and capital preservation.


### 2026-06-25 — Phase 0 (stability) + Phase 1 (UI) of the platform overhaul
**Phase 0 — Backend stability (fixes the "platform freezes"):** offloaded all heavy SYNC compute off the
single-worker event loop via `asyncio.to_thread`: `compute_levels()` (levels.py), all 3 PDF builds
(server.py), and the research summaries in `compute_research_cache`. Verified: during a 2.6s PDF build,
5 concurrent health pings all returned 200 in <1ms (loop no longer blocks). Also hardened `admin/fresh-start`
to use collection `drop()` instead of `delete_many({})` (the MongoDB NetworkTimeout source on prod's large DB).
**Phase 1 — UI/UX:**
- Watchlist sync controls (status badge + VALIDATE + owner-only SYNC 10) moved out of Portfolio onto the
  Cockpit, beside the Watchlist (new shared `components/WatchlistControl.jsx`).
- Portfolio rebuilt into 3 tabs: ACTIVE (Asset/Entry/Current/Unrealized PnL/Duration/Stop),
  OPEN (Asset/Entry Date/Entry/Current/PnL/Status), CLOSED (Asset/Entry Date/Exit Date/PnL/Return%/Duration/
  Exit Reason + Today/7D/30D/All-Time filters). Legacy Today's/Rest grouping + Holdings view removed.
- Backend: added `entry_price/entry_timestamp/return_pct/hold_seconds` to TradeLog + `compute_return_and_hold()`
  helper; populated on PAPER watcher exits, MACRO_BEARISH engine exits, and manual exits.
**STILL PENDING (approved):** Phase 2 (Reason Chain schema + PDF 12-col sandbox matrix), Phase 3 (decoupled
arbitration + Hunter v2 + Volatility Squeeze promoted to ACTIVE $75/trade; roles realigned). ⚠️ Production 520
is an infra issue (with Emergent Support) — redeploy required for these code fixes to reach livetrading247.com.


### 2026-06-22 — PHASE-B Strategy Research Laboratory + Fresh Start (COMPLETE, tested 9/9 + FE 100%)
- Transformed the Strategy Sandbox from a signal-counter into a full research pipeline.
  Each of 5 strategies now has its OWN qualification framework (no Hunter filters forced):
  Hunter (support→RSI reset+vol exhaustion), Volatility Squeeze/VCP (ATR+BBWidth compression+vol expansion),
  Relative Strength (beats BTC→trend+sector proxy), Bear Breakdown (below+falling 50EMA+support break+momentum),
  Neutral Crab (low ADX+range+≥2 S/R touches). `scan_strategies()` now emits {detected, qualified, evidence}.
- Lifecycle: Detected → Qualified → Breaker Pass → Resolved → Wins. Outcomes resolve on a forward
  7d counterfactual return (credit-free CCXT) via `resolve_strategy_lab()`; max-drawdown from cached 4h OHLC.
- NEW queryable collection `strategy_lab_log` (one first-class row per detected opportunity; NOT JSON-buried),
  indexed + 30-day TTL (prevents OOM recurrence). Written from trading_engine each cycle.
- NEW `summarize_strategy_lab()` streaming aggregator (memory-safe): funnel + Qualification/Conversion/Execution
  rates, Expected Value, Profit Factor, Max DD, + win-rate/avg-return/EV/PF DELTAS vs the Hunter benchmark.
  Sorted by Expected Value. Endpoints: `GET /api/research/strategy_lab` (+ `/strategy_sandbox` alias).
- Frontend Reports.jsx: new "Strategy Research Laboratory" table + "Signal Attrition Funnel" bars.
- PDF report updated to the lab metrics table.
- FRESH START (user request): `POST /api/admin/fresh-start` (owner-only) wipes all trade/research/strategy
  collections, resets paper book to **$1200**, sets flat **$75/trade** (normal/strong/breakout lots).
  Model defaults also updated ($1200 / $75). Owner-gated FRESH START button added to Reports header.
  Preview was reset; ⚠️ production must run fresh-start separately after redeploy.


### 2026-06-21 — P0 Production OOM crash-loop fix (COMPLETE, redeploy required)
- Root cause: 3 on-demand endpoints loaded **full** research_log docs (incl. heavy nested
  `evidence`/`sector_data`/`level`) into memory, ballooning RAM on the 25k+ row production DB:
  `/research/summary` (`.to_list(50000)`), `/research/funnel?since_hours=` (8000),
  `/research/missed_opportunities?since_hours=` (12000). Previous fork only fixed the background cache loop.
- Fix: all three now use the existing `_RESEARCH_PROJECTION` (drops heavy nested fields) + capped
  windows (`/research/summary` now 14-day window @ 8000; since_hours paths @ 8000 projected).
  Results unchanged — the 60s cache loop already feeds the same summarize_* fns with this projection.
- Verified in preview: all heavy endpoints 200 OK, backend worker steady ~390MB, no crash-loop.
- ⚠️ User MUST redeploy to apply on production (`livetrading247.com`); preview cannot push to prod.

## 🧭 ARCHITECTURE OVERRIDE — VALIDATION-FIRST (2026-06-02, governs everything below)
**Foundational shift: prove the edge before adding features.** The governing question is now
*"How do we PROVE the system works?"* not *"How do we build more?"* Full sequenced plan in
`/app/memory/ROADMAP.md`. Key locks:
- **3 independent products (divided by downside, not asset):** Product A = Ananta Core (crypto
  swing edge validation, read-only/PAPER); Product B = Ananta India (Portfolio Doctor, read-only,
  NO execution); Product C = Execution Layer (ALL high-downside plumbing — live orders, intraday,
  shorts — each behind its OWN default-OFF kill-flag).
- **Research Database (Phase 2, highest-value addition):** append-only log of EVERY evaluation
  cycle (trade or not): `Timestamp | Asset | Gemini_Confidence | News_Sentiment | Macro_Bias |
  Decision(BUY/HOLD/REJECT)` + **Counterfactual P&L** (forward 24h/72h/7d returns on REJECTED
  setups → Saved-Loss vs Missed-Winner) + **Signal Stability** (confidence variance/flip-rate).
- **KEY DESIGN — decouple thresholds:** LOG everything ≥0.50, EXECUTE only ≥0.80. Research DB fills
  fast while live discipline stays strict. This is the fix for the "dumb robot just sits there" risk.
- **Diagnostic metrics (no arbitrary trade counts):** Decision Quality, Opportunity-Capture funnel,
  Near-Miss Analytics (0.70–0.79 band + full buckets), Regime Accuracy (vs a null baseline).
- **Strict linear phases:** 1 Crypto Paper Validation (EVIDENCE-gated, not calendar/"60-90 days") →
  2 Research DB → **2.5 Model Audit (ablation: does Gemini/news/confidence each add value?)** →
  3 Crypto Explainability → 4 India Portfolio Doctor → 5 Live Crypto Exec → 6 India Exec → 7 Intraday
  (default OFF) → 8 Shorts & multi-asset/PAXG rotation. No phase may be bypassed.
- **Advisor cautions:** counterfactuals validate ENTRIES only — still bank ~15–25 real PAPER
  round-trips to exercise the EXIT engine (trailing stops/slippage/chase); resolve counterfactuals
  forward-only (no look-ahead leak); score regime accuracy against a benchmark, not in isolation.
- The prior A→E roadmap is SUPERSEDED as sequencing but its safety/UX items survive as DOWNSTREAM
  supporting work — no feature/UI work precedes the Research Database.

## 🔱 PROJECT NORTH STAR — REALIGNED (2026-05-29)
**Rebrand: CryptoAtlas → `Ananta.AI` (The Infinite Sentinel)** — chosen per the owner's Phase-5 directive
(Ananta Shesha = sleepless 24/7 guardian; ties to continuous market vigilance).

> Construct **Ananta.AI**: a *scale-independent*, multi-asset algorithmic **swing-trading** framework
> optimized for **24/7 capital preservation and strategic trend exploitation**. It must enforce a strict
> separation of concerns between a **secure read-only public monitoring dashboard** and an
> **authenticated Owner admin panel**. Core execution scales via **Risk-Unit ($R) sizing**, adapts to
> **market regimes** via volatility analysis, validates entries with **multi-timeframe horizontal S&R
> overlays**, and enforces automated **portfolio-heat + systemic ruin-line circuit breakers**.

**The game (unchanged):** maximize risk-adjusted expectancy while minimizing probability of ruin.
The edge comes from risk management, sizing, regime awareness, and avoiding bad trades — NOT from
predicting more good trades. Prove a *repeatable edge that survives fees, slippage and regime shifts*
(the 10-gate Graduation scorecard) BEFORE any live capital.

**Locked decisions (best-judgment defaults, 2026-05-29):**
- Name = **Ananta.AI**.
- Auth = **custom Owner password → JWT**, public defaults to READ_ONLY (needs an owner password + auth playbook).
- Build order = **Phase A quick-wins/safety → B security → C core engine → D homepage+rebrand → E live-gate/pilot**.
- Settings "Validation Interlock": owner re-confirmed BOTH rules in v1.1 (Max_Spread≥Trail_Arm reject +
  Account_DD≤Stop_Loss reject) — implemented as specified, with extra sound guards added; the Max_Spread vs
  Trail_Arm rule is flagged as advisory (unrelated quantities) but kept per owner request.
- Settings UI becomes an EXCLUSIVE 4-category accordion (Risk & Account Survival / Volatility & Trailing Exits
  / AI Macro & Confidence Gates / Exchange API & Connectivity) in Phase A.
- "$5 Speculative Sniper / Lottery Mode" is OUT of Version 1 (deferred to V2) — no files/phases for it now.
- NEW V1 add-on: **Intraday Companion Module** (Phase C.6) — a capped (≤2/day = CAP not quota, flat-by-EOD)
  news-driven intraday sleeve running parallel to the swing core; shares the SAME heat + ruin-line budget.
  Adds a **Daily Intraday Loss Lock (1.0% equity)** that disables ONLY the intraday sleeve (swing unaffected),
  a `strategy` trade tag (SWING|INTRADAY) feeding the Graduation scorecard per-sleeve, an Opportunity-Capture
  funnel metric, and a MANDATORY **2–4 week Shadow Mode** before any live intraday capital. Needs an RSS news
  source (decision pending). Sequenced AFTER the swing core proves a 10/10 graduation edge.
- v1.2 design shifts (backlog): (a) KEEP hardcoded 10% SL on $300 baseline; ATR/structural stop scaling
  deferred to $1,500+ tiers. (b) Add tokenized commodities (PAXG/gold) to the watchlist so the heat engine can
  rotate crypto→defensive on correlation breach (true diversification). (c) [PARKED] Two-way directional /
  Downside Profiling — shelved per owner; bot stays long-only spot, "bearish" = rotate to cash/PAXG. (d) Log a
  `confidence_bucket` (0.80–0.84 / 0.85–0.89 / 0.90+) per trade → feed Graduation scorecard for per-tier
  expectancy.
- NEW **Phase 6 — Ananta.India** (SEPARATE product, archived in ROADMAP): read-only Indian-equity Portfolio
  Intelligence via Kite Connect (V1 = analysis/Doctor/health/transparency/reco-simulation, NO execution; V2 =
  live orders + rebalancing + fenced intraday/short toggles). Fully isolated from crypto; sequenced AFTER the
  crypto core graduates. Flags: second-product scope, daily Kite token re-login, SEBI advisory risk if shared.
- New homepage hero (equity curve / regime type / portfolio heat) depends on backend pieces built in Phase C,
  so those land before/with the homepage redesign (no placeholder widgets).

➡️ Full sequenced build plan lives in `/app/memory/ROADMAP.md`.

## User Choices (from clarifying questions)
- **LLM**: Emergent Universal Key + Gemini 3 Pro (`gemini-3.1-pro-preview`)
- **Exchanges**: Kraken (primary) + Coinbase (fallback) via CCXT
- **Trading Mode**: Paper + optional Live toggle (Live stubbed for safety)
- **Assets**: BTC/USD, ETH/USD, SOL/USD, XRP/USD, ADA/USD
- **Risk defaults**: 2% daily loss, 0.5% spread, 0.6 min confidence, 1-3% position size

## Architecture
6-layer modular design:
1. **Layer 1 - Market Aggregation** (`market_data.py`): CCXT, Kraken primary, Coinbase fallback, 5s TTL cache.
2. **Layer 2/3 - Microstructure** (`market_data.py`): Bid/ask spread %, orderbook imbalance over top-10 levels.
3. **Layer 4 - AI Macro Context** (`ai_reasoning.py`): Gemini 3 Pro via `emergentintegrations.LlmChat`, structured JSON output (BIAS/CONFIDENCE/REASON).
4. **Layer 5 - Fusion** (`risk_engine.fuse_signals`): Combines macro bias + orderbook imbalance, requires agreement.
5. **Layer 6 - Risk Controls** (`risk_engine.compute_kill_switches`): 4 kill-switches (spread, daily-loss, low-confidence, manual).
6. **Trading Engine** (`trading_engine.py`): Background loop every 90s; persists reasoning + trades to MongoDB.

## What's Been Implemented (2026-05-25)
### Backend (FastAPI + MongoDB + CCXT + Gemini + reportlab)- `/api/` health
- `/api/market/snapshots` and `/api/market/snapshot/{symbol}` - live CCXT data
- `/api/portfolio` (with day-rollover) and `/api/portfolio/reset`
- `/api/trades` (paginated)
- `/api/reasoning` (with symbol filter)
- `/api/risk/status` - 4 kill-switches with detailed thresholds
- `/api/settings` GET/PUT - clamped numeric inputs, masked secrets
- `/api/cycle/run` and `/api/cycle/run/{symbol}` - manual evaluation trigger
- `/api/news/current` - mock news rotating per UTC minute
- `/api/public/snapshot` - sanitized whole-state snapshot for the Judge View (no API keys, no ids)
- `/api/report/full.pdf` - judge-ready full report (portfolio + risk + reasoning + trades)
- `/api/report/reasoning.pdf?limit=N` - reasoning-only PDF
- Background `TradingLoop` polling every 90s.

### Frontend (React + Tailwind + shadcn, Bloomberg-terminal aesthetic)
- **Operator** (`/`):
  - **Dashboard tab**: $100 simulated portfolio, kill-switch panel (Green/Red), live price tickers for 5 symbols with flash animation, run-cycle button, recent trade history table.
  - **AI Reasoning Log tab**: Timeline of evaluations, drill-down detail (LLM output + fusion summary + blocked reasons + news input + evidence snapshot), symbol filter pills, Download PDF button.
  - **Settings tab**: Risk-threshold sliders, paper/live mode selector, symbol toggles, API key inputs (masked), manual kill-switch hero, sticky save bar.
  - **Header**: "SHARE JUDGE VIEW" (copies `/judge` link to clipboard) and "DOWNLOAD PDF" (full report) buttons.
- **Judge View** (`/judge`): public read-only mode.
  - Cyan "JUDGE VIEW · READ ONLY" banner.
  - Same Dashboard + AI Reasoning Log tabs (no Settings, no Reset, no Run-Cycle, no Manual-Kill toggle).
  - Top-right "Download PDF" + per-tab "Reasoning-Only PDF" download buttons.
  - Uses sanitized `/api/public/snapshot` (no API keys ever leave the server).

### Testing
- 20/20 backend pytest cases passing (covered all endpoints + Gemini LLM + CCXT + kill-switches + simulated trade execution).
- Test suite at `/app/backend/tests/backend_test.py`.

### Tech Stack
- Backend: Python 3.11, FastAPI, motor (async MongoDB), CCXT 4.5, emergentintegrations.
- Frontend: React 19, Tailwind 3, shadcn-ui, lucide-react, sonner, recharts (available).
- Data: MongoDB (collections: `portfolio`, `settings`, `trades`, `reasoning`).
- Fonts: Chivo (headings), IBM Plex Sans (body), JetBrains Mono (data).

## Personas
- **Competition Judge**: needs to see Explainable AI, risk discipline, real live data, end-to-end working flow.
- **Operator (the user)**: needs ability to tweak thresholds, engage manual kill, monitor PAPER simulation.

## Prioritized Backlog
### P1 (next up)
- Encrypt-at-rest for exchange API secrets (currently plaintext in DB for demo).
- Real news feed integration (CryptoPanic, Twitter, or RSS) replacing the mock rotator.
- Sparkline/candlestick chart per asset on Dashboard (Layer-2 visual support).

### P2 (engineering polish)
- Parallelize `evaluate_all` via `asyncio.gather` (currently ~30s for 5 symbols sequentially).
- TTL index on `reasoning.timestamp` to cap DB growth.
- Migrate from `@app.on_event("startup")` to FastAPI `lifespan` context manager.
- Backtesting engine with metrics (Sharpe, drawdown, win rate, profit factor).

### P3 (nice-to-haves)
- WebSocket push for real-time price updates (currently 8s polling).
- Strategy explanation page + architecture diagram for judges.
- Trade export (CSV) and PDF report for competition submission.

## Risk Management Explanation
- **Kill-switches** evaluated every cycle (hard stops marked *):
  - *Spread breach* (bid/ask spread > max_spread_pct, default 0.5%) - blocks all new orders, current positions held.
  - *Daily-loss breach* (equity drop from day-start > max_daily_loss_pct, default 2%) - blocks all new orders.
  - Confidence breach (LLM confidence < min_confidence, default 0.6) - soft block, prevents new entries but doesn't terminate.
  - *Manual kill* - operator override switch.
- **Position sizing**: ADAPTIVE (default) uses fixed USD lots — $5 NORMAL, $10 STRONG; legacy 1-3% of equity path remains as fallback.
- **Setup classifier (Layer 5b)**: STRONG = LLM macro confidence ≥ 0.75 AND 1h close > EMA50 > EMA200 AND (1h ATR percentile ≥ 60% over 30 days OR 1h ADX ≥ 20). Else NORMAL. NONE if macro not bullish.
- **Concurrent-position cap**: max 5 open positions. Excess BUY signals are queued (HOLD with `MAX_POSITIONS_REACHED`) and re-evaluated next cycle.
- **Fusion logic**: BUY only when (macro BULLISH AND imbalance > +0.15 AND no kill-switch AND slot available); SELL when (macro BEARISH AND imbalance < -0.15 AND position open); else HOLD.
- **Capital preservation > opportunism**: Default reasoning is HOLD; engine takes action only when both layers agree.

## Changelog
### 2026-06-21 - Performance fix: slow tab loads (NOT a credits issue)
- Root cause: DataLogs fired ~8 endpoints each scanning up to 12,000 unindexed research_log docs and
  re-aggregating in Python on every open; no client caching; cold-cache CCXT calls.
- **DB indexes** added on research_log (timestamp, symbol+timestamp, rsi_4h, support_zone), trades
  (timestamp, side), reasoning, stop_loss_simulation_logs, strategy_sandbox_logs (server.py startup).
- **Precomputed research cache** (`compute_research_cache` + `research_cache_loop`, 60s): one capped scan
  (last 30 days / 20k rows) computes ALL 8 aggregations into memory; endpoints + PDF read it instantly.
  Verified: 8 research endpoints now ~0.09-0.13s (was multi-second). `since_hours` still computes live.
- **Client SWR cache** in `api.js` (`cget`): stale-while-revalidate + in-flight dedup. Research TTL 8s,
  portfolio/snapshots 4s, levels/candles 60s, watchlist-validate 10s (busted on sync). Reports tab revisit
  measured at 0.18s. No trading-logic or LLM-credit impact.


### 2026-06-21 - Phase B sprint: Strategy Sandbox + staged-exit + credit fix + UI refactor
- **CREDIT FIX** (answers "credits used while idle"): `trading_engine.evaluate_symbol` now computes the
  Hunter (pure math) FIRST and only calls Gemini when `Hunter.triggered` (or hard-kill fail-open). Idle
  scans set macro=`no-setup-skip`. Verified ~8/12 recent scans skip Gemini. Zero change to live-trade
  decisions (Gemini only feeds the dormant breaker + soft sizing).
- **Strategy Sandbox** (`strategies.py`, credit-free, NO LLM): 5 regime classifiers scored per asset each
  cycle — Hunter=EXECUTE, VCP/Trend-Rider/Bear-Breakdown/Neutral-Crab=SHADOW (logged, never traded). Stored
  in research_log `strategy_signals` + mirror collection `strategy_sandbox_logs`. Endpoint
  `GET /research/strategy_sandbox` → scoreboard (signals/active/win%/expectancy/verdict, promotion at N≥30).
  Verified live (VCP 32 sig/7 active, Crab 31/6).
- **Structure-based staged-exit** ("33/66/99" but level-driven, NOT round %): Tier-1 trim 33% @ support-zone
  low, Tier-2 33% @ structural stop, Tier-3 34% @ deep hard stop. Computed at position close in
  position_watcher → `stop_loss_simulation_logs`. Endpoint `GET /research/staged_exit` → Actual vs Theoretical.
  Math unit-tested (loser preserved −5.68 vs −7).
- **Frontend**: Filter Attribution → **Strategy Sandbox Scoreboard** + **33/66/99 card** in DataLogs.
  Portfolio split into **Today's Positions** vs **Rest of the Positions** + Days Held / R-multiple / P&L.
  Cockpit "Today's Executions" **collapsed** (not removed) into a `<details>` strip. **Sync/Validate
  Watchlist** owner buttons in Portfolio header (validate=public, sync=owner; shows "10/10 · in sync").
- **PDF**: Research section now embeds Strategy Sandbox Scoreboard + Staged-Exit analysis (pulls from both
  collections); empty sections auto-omitted. Verified via text extraction (Strategy Sandbox present, no
  CryptoAtlas leaks).
- New endpoints: `/research/strategy_sandbox`, `/research/staged_exit`, `/watchlist/validate`,
  `/watchlist/sync` (owner). Engine still executes (PAXG position live, funnel Executed:1).
- ROADMAP next-phase note (NOT built, per freeze): user wants to improve OPPORTUNITY COVERAGE (loosen Hunter:
  RSI≤45, near-support, moderate reaction) rather than add filters — Sandbox data will guide which to promote.


### 2026-06-20 - Phase B: Research-First Enhancement (NO new gates) + PDF rebrand
- **ENTRY LOGIC FROZEN** — no new filters/thresholds. All additions are diagnostic instrumentation,
  credit-free (pure CCXT compute + Mongo aggregation, zero LLM).
- **50% Rule as a METRIC only** (`primary_layer.fifty_pct_metric`): per evaluation computes recent swing
  low/high, `midpoint_50`, `distance_from_midpoint_pct`, `above_or_below_midpoint` → stored in `research_log`.
  Never gates a trade. Verified logging real data (BTC midpoint $64k, −1.07% = BELOW/discount).
- **Winner/Loser attribution on trades**: `entry_attribution` snapshot (rsi_at_entry, volume_score,
  support_zone_score, distance_from_midpoint_pct, relative_strength_btc, market_regime, breaker_state,
  rr_estimate) captured at entry and carried through all fill paths (live/breakout-market/maker-pending) onto
  the closed SELL trade. **MFE/MAE** tracked live in `position_watcher` (peak/trough → mfe_pct/mae_pct).
  Verified MFE live-tracking on the real PAXG position.
- **4 new aggregation endpoints** (public read-only, verified correct via seeded data):
  `GET /api/research/winner_profile`, `/missed_opportunities`, `/rsi_distribution`, `/zone_effectiveness`.
  RSI/zone/missed use resolved counterfactuals (A-i); winner-profile uses closed trades.
- **Frontend**: 4 panels added to DataLogs/Reports under "PHASE B · RESEARCH-FIRST ANALYTICS" — Winning Trade
  Profile, RSI Distribution Study, Missed-Opportunity Analysis, Support-Zone Effectiveness. Clean
  "Accumulating data…" zero-states until the sprint resolves data (B-yes).
- **PDF rebrand + metrics**: `pdf_report.py` + `server.py` rebranded CryptoAtlas→**Ananta** (titles, headers,
  author, filenames now `ananta-research-*.pdf`). DataLogs PDF now embeds a Research & Analytics section
  (funnel, rejection leaderboard, winner profile, RSI distribution, missed-opportunity, zone effectiveness).
  Verified: PDF builds (200, valid, "Ananta" present, no "CryptoAtlas").
- Note: PAXG hedge enters via its own rotation path so its `entry_attribution` is empty by design (it's not a
  Hunter setup); the 9 crypto assets carry full attribution through the Hunter path.


### 2026-06-19 - Mobile-first cockpit overhaul + Portfolio tab + Manual Emergency Exit
- **4-tab nav** (`AppShell.jsx`): added **PORTFOLIO** as the 2nd tab (COCKPIT · PORTFOLIO · DATALOGS/REPORTS
  · SETTINGS); TabsList now horizontally scrollable on mobile.
- **New `Portfolio.jsx`** with two sub-tabs: **Positions** (open trades: instrument, lot $, avg entry, live
  price, P&L green/red, structural stop, trail peak, + owner Emergency Exit) and **Holdings** (PAXG safety
  allocation card + closed-trade ledger). Both have the specified clean zero-states ("You have no open
  positions right now. The Hunter is evaluating support zones.").
- **Cockpit redesign** (`Dashboard.jsx`): brighter cyan active border on the horizontal watchlist; removed the
  large embedded 4H chart → replaced with a low-profile **"CLICK HERE FOR CHARTS"** button that opens a
  bottom **Drawer** (vaul) rendering the 4H candles for the selected asset; new **Open Positions Snapshot**
  panel with per-row Manual Emergency Exit.
- **Manual Emergency Exit** (`ManualExitButton.jsx`): owner-only (hidden for public), confirm dialog →
  `POST /api/positions/{base}/close`. New backend endpoint (owner-gated) market-closes one position via the
  same `_execute_sell`/`_record_live_sell` path, tags `exit_reason=MANUAL_EXIT`, sets a cooldown. `/portfolio`
  now also returns `structural_stop`, `peak_price`, `breakout_mode`, `sector`.
- Verified: frontend compiles; all 4 tabs + drawer + zero-states render (mobile 430px screenshot); close
  endpoint 403 without auth; end-to-end seeded-position close → MANUAL_EXIT +$0.83 net, position removed,
  clean slate restored.


### 2026-06-18 - Reports widgets finished + FRED activated + fresh Phase-A reset
- **Reports tab (P0, finished):** Added the **Setup Funnel** (Detected → Qualified → Breaker
  PASS/CAUTION/VETO → Executed) and **Circuit Breaker Accuracy** (per-state resolved 7d outcomes:
  Protected vs Over-Restrictive) widgets to `frontend/src/pages/Reports.jsx`, bound to the existing
  `GET /api/research/funnel` (`api.researchFunnel`). Verified rendering in matte-silver theme via
  screenshot (funnel + breaker table populate with real data).
- **FRED activated:** User-provided `FRED_API_KEY` written to `backend/.env` (was empty). Verified
  against live St. Louis Fed API (CPI 333.979). PAXG macro grounding now real instead of NEUTRAL.
- **Fresh Phase-A reset:** Ran `reset_sprint.py` (added explicit `normal_lot_usd = 20.0`). Clean slate:
  $300 flat / **$20 lot** / 10-asset PAPER, wiped research_log(819)/reasoning(278)/trades(1). Funnel
  confirmed all-zeros post-reset. **Preview DB only** — production DB untouched.
- **Login "bug" — NOT a code bug:** User was logging in on PRODUCTION (`livetrading247.com`), which has
  a separate DB + separate env vars. Preview password doesn't apply there. Fix = set production
  `OWNER_PASSWORD`/`OWNER_EMAIL`/`FRED_API_KEY` in deployment env settings + redeploy (seed re-syncs).
  DNS issue appears resolved (prod site now loads). Documented in `test_credentials.md`.


### 2026-06-11 - PHASE 2.1 (SHADOW Simulator) + PHASE 3.5 (Auth Gate) SHIPPED
**SHADOW Simulator (2.1):**
- `shadow_sim.py` — virtual trades for the 0.70-0.79 bullish near-miss band, managed by the SAME
  `evaluate_exit` engine (incl. PAXG per-class params) with ZERO capital. Validates the EXIT engine
  on setups we didn't execute. Collections: `shadow_positions` (open) / `shadow_trades` (closed).
- Entry hook in `trading_engine.evaluate_symbol` (suppressed/additive); `ShadowWatcherLoop` (30s).
- Endpoints: `GET /api/research/shadow` (open + closed + win-rate/expectancy by confidence bucket),
  `POST /api/research/shadow/tick`. Verified open→manage→SL_HIT close end-to-end.

**Auth Gate (3.5) — single owner + public read-only:**
- `auth.py` — bcrypt + PyJWT (HS256, 12h Bearer), `require_owner` (→403), idempotent owner seeding
  from env, brute-force lockout (5/15min). Owner: `owner@ananta.ai` (creds in test_credentials.md).
- `server.py` — `/api/auth/login|logout|me`; **11 mutating routes 403-guarded**; exchange secrets
  redacted in `GET /settings` for non-owners; owner seeded on startup.
- `.env` — added `JWT_SECRET`, `OWNER_EMAIL`, `OWNER_PASSWORD`.
- Frontend — `AuthContext`, `OwnerAuthControl` (login dialog + owner badge/logout), read-only banner,
  gated `EnvironmentToggle` + Settings (save/run/clear) when not owner. Bearer token in localStorage.
- Tests: `test_shadow.py` (4) + `test_auth.py` (6); HTTP tests auto-authenticate via `conftest.py`
  (mutating requests only). **Full suite 282 passed / 2 skipped.** Verified via curl (401/403/200 +
  redaction) and screenshot (login→owner→read-only banner toggle). PAPER only; no real capital.


### 2026-06-06 - DIVERSIFIED 6-ASSET KRAKEN-NATIVE MATRIX (Active PAPER trading) SHIPPED
- **Watchlist re-mapped** to 6 Kraken-native assets: BTC/USD, ETH/USD, SOL/USD (L1), LINK/USD,
  AAVE/USD (DeFi), PAXG/USD (gold — the only true uncorrelated hedge). Clean-slate reset
  (`reset_six_asset.py`) flushed `reasoning` + `research_log`, kept the $300 baseline.
- **`asset_profiles.py`** — sector mapping (L1/DEFI/METAL) + staggered scan cadence (majors every
  cycle, DeFi+gold every 3rd → ~6→4 Gemini calls/cycle, on top of MD5 news cache) + per-class exit
  overrides. **PAXG profile**: SL 2.5% / trail-arm 1.0% / trail-dist 0.7% (vs crypto 10/5/3) so gold
  can react to 1-2% macro moves. PAXG also gets a **reserved portfolio slot + dedicated $30 lot** so
  the hedge is never crowded out by correlated crypto longs.
- **`market_context.py`** — DefiLlama (keyless: chain TVL + protocol TVL/30d trend) + FRED (CPI,
  Fed Funds, 10Y, breakeven, USD index) feeds, cached (10 min / 6 h), injected into adaptive,
  sector-specific Gemini prompts. **FRED degrades gracefully** when `FRED_API_KEY` is unset — the
  PAXG prompt then states "macro data unavailable" so Gemini cannot hallucinate (verified live).
- **`ai_reasoning.py`** — system prompt rewritten to multi-asset / asset-class-aware; sector context
  folded into the MD5 cache key. **`research_log`** now tags `asset_class` + `sector_data` snapshot.
- **Frontend bug fixed (latent):** `Dashboard.refreshAll` used `await Promise.all([...])` so a slow
  `/market/snapshots` froze the WHOLE dashboard (stuck "LOADING", empty watchlist). Decoupled so each
  call applies state independently. Verified: $300 portfolio + 6-asset watchlist + BTC chart render.
- Verified: all 6 assets live on Kraken; DefiLlama real TVL flowing (ETH $36B, AAVE $11.8B/-17% 30d);
  full backend suite 266 passed + new `test_diversified.py` (6) + `test_research.py` (7). Lint clean.
- Still PAPER — no real capital. Goal: prove multi-asset expectancy to lift Graduation 3/10 → 10/10.
- ⚠️ ACTION NEEDED: user to provide free FRED_API_KEY to activate PAXG macro grounding. NOTE: per-row
  watchlist prices can briefly show "—" during a trading cycle (CCXT contention); self-heals next tick.


### 2026-06-04 - PHASE 2 (Research Database) — Slice 1 (logger) + Slice 2 (counterfactual resolver) SHIPPED
- **New `research.py` + `ResearchLog` model + `research_log` collection** — permanent, append-only
  diagnostic row for EVERY evaluation cycle (trade or not). Captures the core schema
  (timestamp · symbol · macro_confidence · macro_bias · news_source · decision · absolute_decision
  EXECUTE/REJECT/HOLD) + the **4-tier confidence band** (EXECUTE ≥ min_confidence / SHADOW 0.70–0.79 /
  LOG_ONLY 0.50–0.69 / IGNORE) + context (setup_strength, breakout, htf_trend_aligned, blocked_reasons,
  price anchor) + **counterfactual cells** (cf_ret_24h/72h/7d).
- **Wiring is additive + suppressed** in `trading_engine.evaluate_symbol` (logs right after the
  reasoning insert; `contextlib.suppress` so it can NEVER disrupt the trading cycle). Survives portfolio
  resets (permanent record). No execution-logic change.
- **Counterfactual resolver** (`ResearchResolverLoop`, 600s; CCXT-only, **zero LLM credits**) fills
  forward returns once each horizon elapses; classification (CORRECT_REJECTION / MISSED_OPPORTUNITY /
  NEUTRAL via ±1.5% band) applied at QUERY time so the rule can be refined without data migration.
  RAW-price proxy → validates ENTRY quality only (NOT the exit engine), per roadmap caveat.
- **New endpoints:** `GET /api/research/log` (filters: symbol/tier/row_type/unresolved),
  `GET /api/research/summary` (decision + tier distribution, per-confidence-bucket CF returns,
  **Near-Miss 0.70–0.79 BULLISH** analytics), `POST /api/research/resolve` (manual trigger).
- Verified live: 40+ rows logged within minutes; summary + buckets render; resolver loop running.
  Early signal already visible — 11 EXECUTE-tier (≥0.80) reads with 0 executions = high-conviction
  BEARISH calls (confidence = conviction in the BIAS, not bullishness) → correctly no long entries.
- Tests: `tests/test_research.py` (7) — tier bands, CF classification, summary aggregation, resolver.
  Full backend suite green (266 passed / 2 skipped). Backend-only; no frontend yet (Phase 3).
- NOTE: Slice 3 (random BACKGROUND sampler) deferred — continuous all-symbol evaluation already gives
  unbiased time-coverage; the formal BACKGROUND control tag can be added later. PREVIEW only.


### 2026-05-29 - Graduation Readiness scorecard (objective paper→live gate) + chase-risk capture
- **10-gate Graduation Scorecard** (`analytics.graduation_readiness`, `GET /api/analytics/graduation`, `GraduationScorecard.jsx` in Settings). Headline verdict **"X/10 PASSED — READY/NOT READY"**. Proves a repeatable edge that survives fees/slippage/regimes, not mere profit.
  - Gates: (1) ≥50 round-trips (2) positive expectancy (3) profit factor >1.3 (4) max DD <15% (5) ≥2 positive regimes & top regime ≤60% of profit (6) fees+slippage accounted (7) no sideways overtrading: chop expectancy ≥0 & rate ≤1.5× overall (8) ≥30 days observation & 2/3 recent weeks positive (9) **account survival**: equity DD never ≥20% ruin line (new `account_max_drawdown_pct` setting) (10) **risk consistency**: no single trade >20% of gross profit.
  - Transparent metrics surfaced: stop-loss frequency, trail-exit quality (count + win%), friction ($ + % of gross), per-regime net P&L, weekly windows, observation days, and **entry-extension (chase-risk)**.
- **Chase-risk capture**: new optional `entry_extension_pct` (how far above the 4h EMA50 price sat at entry) threaded through Position/PendingOrder/TradeLog — mirrors `atr_percentile_at_entry`, NO execution-logic change. Surfaces avg/max entry extension so the operator can detect late chasing (the $100-signal→$140-entry→$150-top problem).
- Tests: +10 graduation cases (`tests/test_graduation.py`); full suite **259 passed / 2 skipped**. Testing agent iteration_12 = 100% backend + frontend, 0 bugs. On the clean $300 baseline it correctly reads 3/10 NOT READY.
- Note: PREVIEW only — redeploy to push to production (livetrading247.com).


- **Performance Analytics moved off the home** → now lives on the **Settings** page (`settings-analytics`). Renamed from "Statistical Survivability / Quant Metrics" to plain **"Performance Analytics"** with a one-line explainer. Keeps the ALL DATA / LIVE ONLY + window toggles.
- **Header PDF control**: removed the large inline "Export Trade History" section from the home and the old full-report `download-pdf-header` button. Added a compact **top-right `header-pdf-button`** (visible on mobile) that opens a popup (`trade-pdf-dialog`) with quick presets (Last 7 / Last 30 / All time) + FROM/TO date inputs → downloads `GET /api/report/trades.pdf?start=&end=`.
- **PDF performance summary**: the trade-history PDF now leads with a **PERFORMANCE SUMMARY** block (closed trades, win rate, loss rate, expectancy/trade, net realized P&L) computed via `analytics.compute_performance` and passed into `build_trades_report`.
- Dashboard now shows only: HighBeta safety banner, PortfolioCard ($300), Resting Maker Orders, Live Spot Markets, Recent Activity. Deleted `ExportTradeHistory.jsx`.
- Verified: testing agent iteration_11 = 100% on 6 criteria across desktop (1920) + mobile (390), 0 console errors; backend trades.pdf 200 + %PDF with summary; 32 PDF/analytics pytest pass. Note: these changes are on PREVIEW — user must redeploy to push to production (livetrading247.com).


- **Frontend nav** reordered to Dashboard → Settings → AI Reasoning Log (reasoning last). Removed the legacy "SHARE JUDGE VIEW" button from the header.
- **AI Reasoning Log** now loads max 15 records on mount (`GET /api/reasoning?limit=15`) inside a fixed-height scroll container (`reasoning-scroll-container`, max-h-[70vh], overflow-y-scroll).
- **Export Trade History** (NEW `ExportTradeHistory.jsx` on Dashboard): calendar date-range filter → `GET /api/report/trades.pdf?start=&end=` → clean chronological printout of FILLED trades (new `build_trades_report` in `pdf_report.py`).
- **Settings tooltips**: every field title now has a hover `Info` tooltip with a plain-English definition (`TitleLabel` + shadcn Tooltip). Added an "Adaptive Trail Envelope" control block.
- **Engine baseline**: Portfolio default $100 → **$300** (`models.py`); `reset_baseline.py` wipes trades/reasoning/pending, resets portfolio to $300, and restores the operational spec (SL 10% / arm 5% / dist 3%, lots $20/$30/$50, 8 slots, all 5 symbols BTC/ETH/SOL/XRP/ADA, min_conf 0.80) preserving API keys + trading_mode. `PortfolioCard` copy now sourced from `portfolio.starting_balance`.
- **Volatility-adaptive trailing stop** (`position_watcher.trail_distance_for`): `dynamic_trail = clamp(k × ATR_percentile, 2%, 6%)` (k=0.06 default), used in `evaluate_exit` + `watch_once`; falls back to static `trail_distance_pct` when disabled or ATR percentile unknown. New `RiskSettings`: `dynamic_trail_enabled/k/min_pct/max_pct`.
- Symbol scan confirmed unrestricted: `evaluate_all` iterates `settings.enabled_symbols` (all 5 incl. ADA/XRP).
- Tests: +9 dynamic-trail cases; full suite **249 passed / 2 skipped**. Testing agent iteration_10 = 100% on 8 acceptance criteria (1 cosmetic $100 label found & fixed).


- **New source toggle** on the Analytics Panel (`analytics-source-all` = ALL DATA / `analytics-source-organic` = LIVE ONLY). Lets the operator filter out the 15 seeded `DEMO_SEED` trades to isolate organic paper performance during the dry run.
- Backend `GET /api/analytics/performance?exclude_synthetic=true` applies `{"note": {"$ne": "DEMO_SEED"}}` across all three windows (rolling_24h, calendar_day, all-time insight); response now also returns `synthetic_count`. Verified: ALL → 15 closed/ready/best=HIGH_PANIC; LIVE ONLY → 0 closed/not-ready, `synthetic_count`=15.
- Frontend: `Dashboard` holds `excludeSynthetic` state (drives re-fetch); `AnalyticsPanel` shows a "Showing ORGANIC trades only — N synthetic demo trades hidden" note in LIVE ONLY mode.
- Verified recent work: strict-AND STRONG classifier (`setup_classifier.py` L190), one-click LIVE/PAPER header toggle + confirm dialog (gate stays CLOSED, no real orders), window toggle + regime breakdown table.
- Moved Sonner toast to `top-right` (was overlapping the regime table on 1080p).
- Tests: 241 backend pass (228 unit + 13 HTTP); testing agent iteration_9 = 100% backend + frontend, 0 issues.


- **Regime Insight engine** (`analytics.regime_insight`): ranks volatility regimes (LOW_COMPRESSION/NORMAL/HIGH_PANIC) by statistical expectancy across all closed trades; returns `ready=False` with a graceful "Analyzing Market Regimes… (Accumulating Trade Data Base — n/5)" placeholder until ≥5 round-trips (no div-by-zero). Surfaced via `GET /api/analytics/performance.regime_insight`.
- Per-regime stats upgraded to full block (expectancy, profit_factor, avg win/loss, win rate, net_pnl) via `_regime_stats`. Frontend `AnalyticsPanel`: prominent Brain insight card (placeholder + populated states) + Expectancy column in the regime table.
- **Exchange Friction settings UI**: `taker_fee_pct`, `maker_fee_pct`, `breakout_paper_slippage_pct` now exposed as clean numeric inputs in Settings (no longer hardcoded); persistence verified.
- **Demo data tool**: `seed_demo_trades.py` (idempotent; `--clear` flag) seeds 15 synthetic round-trips across the 3 regimes for stress-testing the panel. Currently seeded (best regime = HIGH_PANIC, expectancy +$1.25/trade).
- Tests: 5 new regime_insight tests in `test_analytics.py`; full suite 238 passed / 2 skipped.


### 2026-05-29 - Phase B: Execution Friction Mitigation Layer
- **Post-Only MAKER entries**: Normal/Strong buys now route as maker LIMIT orders at the best bid. LIVE uses CCXT `postOnly` (would-cross → ABORTED, retry next cycle). PAPER simulates a resting order resolved by the watcher: fills on price crossing our bid OR flat for 2 consecutive 15s ticks; else cancels as `MISSED_FILL_PRICE_RUN`. Maker fills pay `maker_fee_pct` (0.25%).
- **Breakout = MARKET taker**: breakout buys use a true MARKET order in LIVE; PAPER fills at ask + `breakout_paper_slippage_pct` (0.10%) synthetic slippage.
- **Per-tier pre-fire spread gate**: BUY blocked when bid-based spread > 0.20% (breakout) / 0.50% (standard) with exact log "Execution blocked due to insufficient liquidity"; `spread_pct_bid_based` added to reasoning evidence.
- **Realized slippage + friction tally**: `slippage_usd` computed on every exit ((expected_trigger − actual_fill)·qty); rolling 24h "Total Friction Cost" (fees+slippage) logged to console via `log_friction_tally`. New `PendingOrder` model + `pending_orders` collection + `GET /api/pending_orders`. Frontend: "Resting Maker Orders" panel (hidden when empty).
- New settings: `maker_fee_pct`, `breakout_paper_slippage_pct`. Concurrent-position cap now counts resting maker orders.
- Tests: `test_phase_b.py` (8) covering maker fill/miss/cash + executor order styles; updated live_execution/adaptive/exits tests for new semantics. Full suite 235 passed / 2 skipped. Testing agent: 100% backend + frontend, 0 issues. Verified live watcher maker-fill→position→SL-exit→slippage chain end-to-end.


### 2026-05-29 - Phase A: Quantitative Metrics Tracking Update (analytics/research layer)
- New `analytics.py`: sector taxonomy (BTC=Store of Value; ETH/SOL/ADA=Layer 1 High Beta; XRP=Payments; PAXG/other=Altcoin/Commodity High Beta), volatility-regime tagging (LOW_COMPRESSION <40 / NORMAL / HIGH_PANIC >=70 by ATR percentile), and `compute_performance()` (Statistical Expectancy, Profit Factor, win/loss asymmetry, max drawdown, fees+slippage friction, per-regime breakdown).
- Every entry now tags `sector`, `atr_at_entry`, `atr_percentile_at_entry`, `volatility_regime` on the Position + BUY TradeLog; SELL legs inherit the entry regime for attribution. TradeLog gained `slippage_usd` (0 until Phase B).
- New `GET /api/analytics/performance` → both rolling-24h (primary) + calendar-day windows, plus current `sector_exposure` and `high_beta_warning` (fires at >=3 Layer-1 High Beta open positions).
- Frontend: `AnalyticsPanel` ("Statistical Survivability") with window toggle + regime table, and a prominent `HighBetaWarning` banner on the Dashboard. Fixed a Watchlist nested-<button> hydration error (row is now a div role=button).
- Tests: 12 new in `test_analytics.py`; full suite 218 passed / 2 skipped. Validated via testing agent (100% backend + frontend, 0 issues).
- NOTE: Phase B (post-only maker limits, breakout market orders, realized slippage tracking, per-tier spread gate logs) is NOT yet implemented — deferred per user's strict phased rollout.

### 2026-05-29 - Patient Breakout & Swing Trading pivot + Vault Engine
- Strategy overhaul: swing entry = macro BULLISH + 4h EMA stack (Price>EMA50>EMA200) replacing orderbook-imbalance entry; SL=10%, trail arm=5%, trail distance=3%; lots $20/$30/$50; min_confidence 0.80 (breakout 0.85); max_daily_loss 10%.
- **MICRO_FLIP exit logic deleted entirely** (backend + UI + tests). Position watcher now exits on SL or trailing TP only.
- **Vault Engine** (`trading_engine.apply_vault_sync` + `LiveExecutor.fetch_free_quote_balance`): when `vault_sync_enabled` and mode is LIVE/DRY_RUN, pulls free USD/USDC from Kraken and caps deployable cash at `vault_max_override_usd` (ceiling only; smaller live balance wins). PAPER untouched.
- Fixed a NameError crash in `risk_engine.fuse_signals` (leftover `imb`). Settings UI: new VAULT ENGINE section (sync toggle, max override, 4h trend toggle); removed obsolete ENTRY GATE imbalance + MICRO-FLIP panels.


### 2026-05-28 - Exits Overhaul + Relaxed Entry Gate (P0)
- New `position_watcher.py` background loop runs every 15s (configurable). Does NOT call Gemini. Per open position it checks:
  * **SL_HIT** — drawdown ≥ `stop_loss_pct` (default 1.5%)
  * **TRAIL_HIT** — armed at +`trail_arm_pct` (default 3%); exits when price pulls back `trail_distance_pct` (default 1%) from peak
  * **MICRO_FLIP** — orderbook imbalance ≤ -`entry_strict_imbalance`
- Position state now persists `peak_price` + `entry_timestamp` so restarts don't reset the trailing stop.
- Main-engine SELLs tagged `MACRO_BEARISH`; watcher SELLs tagged `SL_HIT` / `TRAIL_HIT` / `MICRO_FLIP`. TradeLog has new `exit_reason` field.
- **Relaxed entry gate**: `fuse_signals` now uses a lower orderbook-imbalance threshold (`entry_relaxed_imbalance`, default 0.10) when macro confidence ≥ `entry_relaxed_confidence_floor` (default 0.70). Avoids being late to high-conviction trends.
- **Decoupled STRONG**: classifier now fires STRONG on (confidence) AND (trend OR volatility) — was AND of all three.
- `max_concurrent_positions` default bumped 5 → 8.
- Settings UI: new panels "Entry Gate Thresholds" and "Exits · Position Watcher" with all knobs configurable.
- Tests: 12 new cases in `test_exits_and_relaxed_entries.py` covering gate, classifier, all 3 exit branches, and PAPER watcher end-to-end.

### 2026-05-27 - Adaptive Lot Sizing (P0)
- Added `setup_classifier.py` with EMA, ATR, ADX, percentile math + `classify_setup()` returning STRONG/NORMAL/NONE.
- Added `market_data.fetch_ohlcv_1h(symbol, limit=750)` (Kraken→Coinbase fallback, 5-min TTL cache).
- Wired classifier into `trading_engine.evaluate_symbol` so every BUY decision is sized via $5/$10 USD lots.
- Added concurrent-position cap (default 5); excess BUY signals downgraded to HOLD with `MAX_POSITIONS_REACHED` reason and re-evaluated next cycle.
- `RiskSettings` gained `adaptive_sizing_enabled`, `normal_lot_usd`, `strong_lot_usd`, `strong_min_confidence`, `strong_min_atr_percentile`, `strong_min_adx`, `max_concurrent_positions`.
- `/api/portfolio` now returns `slots_used` + `max_concurrent_positions`; Dashboard PortfolioCard shows `SLOTS X/5` cell.
- Settings UI has a new "Adaptive Lot Sizing · Layer 5b" panel (toggle, USD lots, classifier thresholds, concurrent cap).
- `/api/public/snapshot` whitelists the new adaptive fields (still no secret leakage).
- Tests: 16 new unit tests in `tests/test_adaptive_sizing.py` + 9 external HTTP integration tests; full suite 147 passed.

---

## Mobile App — Phase 1 (Added 2026-06-26)

Cross-platform expansion: native **Expo / React Native** operator cockpit (`/app/mobile`),
sharing the existing FastAPI backend via `EXPO_PUBLIC_BACKEND_URL + /api`. Owner JWT bearer
auth (token in `expo-secure-store` on native, `localStorage` on web). Dark-only Ananta identity
(#0A0E17 bg, #121824 cards, electric teal #14E0C9, gold branding, red losses).

**Shipped (tested — iteration_14, all green):**
- 5-tab navigation (expo-router): Cockpit · Portfolio · Reports · Settings (+ Login, asset/[symbol], strategy/[id])
- Auth: login + biometric (FaceID/fingerprint) unlock gate (expo-local-authentication)
- Cockpit: portfolio hero, today P&L, PAPER/LIVE pill, horizontal market rail, engine status, AI decision timeline, open-positions preview, pull-to-refresh
- Portfolio: Active / Closed / Performance segmented tabs; native SVG equity curve + win rate/profit factor/avg win/avg loss/expectancy; manual-close confirm sheet
- Reports: strategy cards w/ attrition funnel + drilldown (vs-Hunter comparison)
- Settings: Trading/Risk/Strategies/Notifications/Account/Developer sections; env + kill-switch + biometric + notif toggles
- Asset detail: native SVG candlestick + engine read + current reasoning
- Charts built with `react-native-svg` (no WebView) per requirement
- Push notification INFRA: mobile `expo-notifications` registration + backend `push_service.py`
  (`POST /api/notifications/register`, `/api/notifications/test`) + kill-switch & manual-close
  broadcast hooks. NOTE: push delivery only works on a published build with Firebase
  `google-services.json` (user to provide) — no-op in Expo Go/web preview.

**Backlog (mobile):**
- Wire remaining push event hooks (trade_opened, stop_loss, trailing_stop) into engine during Phase E
- Pause polling when app backgrounded (battery)
- Server-side respect of per-event notification opt-out

## NEXT MAJOR PHASE → Engine Phase E (see /app/memory/ENGINE_PHASE_E.md)
Regime-first multi-model router; Hunter (3 regime-aware entry profiles) & Squeeze fully
independent active traders; ATR-structural stops; Squeeze retest timing; Entry Quality Scoring;
Reason Chain schema. User approved sequencing: mobile first (DONE), engine next.

## Engine Phase E1 — SHIPPED (2026-06-26)
Regime-first, multi-model engine upgrade (all pure-compute, ZERO LLM credits; credit guard preserved):
- `regime.py` market regime classifier (TREND_UP/DOWN, RANGE, COMPRESSION, REVERSAL, NEUTRAL)
- `entry_quality.py` A+/A/B/C entry-quality scoring (research-only) on every Hunter & Squeeze entry
- `squeeze.py` Volatility Squeeze as an INDEPENDENT active paper trader (Bollinger-in-Keltner coil →
  retest/continuation entry, never chases first candle; $75 lot; 20-MA hard stop; ATR trail)
- Hunter now regime-aware: 3 entry profiles (Aggressive Pullback / Stabilized Reversal / Deep Discount)
- ATR-structural stop (structure low − 0.4×ATR) replaces fixed % buffer
- Squeeze promoted to EXECUTE (shows ACTIVE in Reports); Hunter & Squeeze fully independent
- Tested: 11/11 pytest (tests/test_phase_e.py), lint clean, backend boots clean, live cycles no errors
Details + E2 backlog in /app/memory/ENGINE_PHASE_E.md

## Engine Phase E3 — SHIPPED (2026-06-26)
- PDF Reason-Chain decision matrix for graded entries (`pdf_report._reason_chain_block`): regime+routing,
  indicator matrix, competing hypotheses, 4H OHLCV market-state snapshot. Wired into /api/report/full.pdf.
- Mobile: polling pauses on app background, refreshes + resumes on foreground (`useFetch` AppState) — battery.
- Server-side per-event notification opt-out: push tokens store `prefs`; `send_push_event` only targets
  devices opted into that event. Mobile syncs toggles to backend on change + on register. Verified.
Verified: PDF builds (200, valid), opt-out filter unit-checked, mobile cockpit renders, engine opened a
live AAVE paper position (engine path healthy). Pending only: user provides google-services.json + Publish.

## Production 520 / OOM Root Cause + Fix (2026-06-26)
ROOT CAUSE: Cloudflare 520 on livetrading247.com is the recurring production OOM crash. Lightweight
endpoints (/api/, /portfolio, /market/snapshots) return 200, but data-HEAVY endpoints (/settings,
/research/*, /analytics/*, /trades?limit=200, /reasoning, /news) consistently 520 — they load large
in-memory aggregations that exceed the production container's memory, OOM-killing it and cascading the
whole API into a 520 crash loop. The mobile app's "mock data" is a downstream SYMPTOM (it falls back
when these calls fail). Backend is healthy in preview; CORS is open (*); not a routing/CORS/offline issue.
FIX (code, preview — needs REDEPLOY to take effect on prod): right-sized every heavy query
(research_log 8000->2000, sells 2000->800, sl_logs 3000->800, analytics 2000->800/5000->1000,
graduation 10000->1500, on-demand research 8000->2000, entry_quality 1000->600), window 14d->10d,
research cache loop 60s->180s. Verified: all heavy endpoints 200 in preview, lint clean, no accuracy
loss at current data volume (~45 trades). Production may ALSO need a higher memory tier (Resources tab).
SEPARATE: production OWNER password != preview password (prod login 401) — mobile login needs prod creds.

## Phase F — Universal Exit Engine (2026-06-28)
ARCHITECTURE: Exit logic decoupled from entry strategies into a centralized Trade Manager
(`backend/exit_engine.py`, pure compute, zero LLM). Entry strategies only tag the position
(`pos.strategy`) + initial profile; the engine owns ALL risk management thereafter.

Strategy profiles (profit-arm %, ATR trail mult, time cap, EMA priority): hunter(5%/2.0x/72h),
squeeze(4%/2.5x/none/EMA-priority), relative_strength(6%/2.0x/120h), neutral_crab(2.5%/1.5x/24h),
bear_breakdown(5%/1.5x/none/EMA-priority).

Modules + deterministic single-pass priority arbitration (lowest number wins):
  P1 A Structural Failure  -> EXIT_FULL  (structural / % / locked-floor breach)
  P2 KILL emergency stop   -> EXIT_FULL  (settings.manual_kill_switch)
  P3 F Profit Protection   -> TIGHTEN    (MFE>=arm -> lock +1% floor, upgrade-only)
  P4 B Momentum Exhaustion -> EXIT_PARTIAL 50% (overbought ZONE 70+/80+ + vol climax + exhaustion candle, one-time)
  P5 D EMA Trend Loss      -> EXIT_FULL  (close<20EMA; squeeze=single close, hunter=needs dead-cross; 6h settle gate)
  P6 C ATR Trail           -> EXIT_FULL  (armed peak - X*ATR)
  P7 E Time Exit           -> EXIT_FULL  (48h stagnation OR profile hard cap)

TELEMETRY: TradeLog gained exit_module, potential_best_exit (price@MFE), potential_worst_exit (price@MAE);
MFE/MAE % already tracked. Position gained locked_profit_floor + momentum_partial_taken. New PAPER
partial-sell path (_execute_partial_sell). PDF gained Exit-Engine Research section (module distribution +
MFE capture efficiency).

EXIT REASON CODES (changed): SL_HIT->STOP_LOSS, plus STRUCTURAL_STOP, PROFIT_FLOOR, ATR_TRAIL,
EMA_TREND_LOSS, TIME_EXIT, MOMENTUM_EXHAUSTION, EMERGENCY_STOP.

TESTING: 16 new unit tests (tests/test_exit_engine.py) + watch_once regression pass; live PositionWatcher
running clean against real paper portfolio. (test_judge_and_pdf 3 failures are PRE-EXISTING owner-auth
integration issues, unrelated.)

BASELINE RESET: reuse existing owner endpoint POST /api/admin/fresh-start (drops trades/reasoning/
research_log/shadow*/sim_logs/strategy_lab/cooldowns/pending_orders, resets $1200 book). Run on PROD
after redeploy for a clean Phase-F forward-test baseline.

ROADMAP (P2): surface MFE/MAE + exit-module telemetry in the MOBILE app UI (separate change in mobile
workspace; backend contract already returns the fields). Squeeze retest-depth tuning after live trades.

## Research Lab — Increment 1: Simulator Foundation (2026-06-28)
GOAL: Offline, credit-free strategy validation. Convert legacy settings into a "Research Lab"
with a "Strategy Validation" engine. Build order agreed: data store -> reusable replay engine ->
injectable clock -> realistic fills -> reporting/WFA -> UI -> approval gate.

SHIPPED (foundation):
- `backend/lab/data_store.py` — SQLite (WAL) at /app/backend/data/historical_candles.db,
  table candles(symbol,timeframe,ts,o,h,l,c,v) UNIQUE(symbol,timeframe,ts); idempotent
  INSERT OR IGNORE; CCXT paginated backfill (Kraken->Coinbase); append_latest for daily cron.
- `backend/lab/backtest.py` — deterministic replay that REUSES live functions (classify_regime,
  route, evaluate_primary, evaluate_squeeze, evaluate_exit_engine) = parity guaranteed. Entry at
  next-bar OPEN (no look-ahead), pessimistic intrabar exits (LOW pass for stop/trail, CLOSE pass
  for F/B/D/E), taker fee + 0.05% slippage, 200-bar warmup. Reports: total return, win rate,
  max DD, avg MFE/MAE, exit-module (A-F) breakdown, regime breakdown, per-trade Trade Quality
  Score v1 (0.5*capture + 0.3*mae_term + 0.2*hold_eff).
- `backend/lab/backfill.py` — CLI: `python -m lab.backfill` (watchlist, 4h+1d, ~2y).
- INJECTABLE CLOCK: exit_engine.evaluate_exit_engine gained `now` + `profile_override` params
  (BACKWARD-COMPATIBLE; live/prod behaviour unchanged when omitted). Fixes Module E / EMA-settle
  aging in historical replay. Tests prove no false time-exit.
- Tests: tests/test_lab_backtest.py (6) + full suite 56 pass; live path unaffected.

DATA LIMITATION (flagged): Kraken/Coinbase free OHLCV cap 4h history at ~720 candles (~120 days).
Daily (1d) goes back ~2y fine. Options: accept 120d 4h + 2y daily, accumulate 4h forward via the
daily-append job, or source deeper 4h from another provider later.

USER REFINEMENTS TO IMPLEMENT NEXT (agreed): 60/20/20 Train/Validation/Test, Walk-Forward Analysis,
regime-segmented Sharpe/DD, parameter sensitivity sweeps (plateau not peak), git-hash + full inputs
per run, async job queue (QUEUED->RUNNING->%->DONE) via worker/ProcessPool, manual approval gate
(lab_param_proposals -> owner "Apply to Production"), standalone PDF, Research Lab UI.

## Research Lab — Deep history seeding via Binance (2026-06-28)
- `backend/lab/seed_history.py`: FREE/keyless deep-history seeder.
  * seed_from_binance() — pulls monthly 4h/1d kline CSVs from data.binance.vision
    (USD->USDT map; RENDER falls back to RNDR). Normalises ms/micro/sec timestamps.
  * seed_from_csv() — parses uploaded CryptoDataDownload / generic OHLCV CSVs.
- SEEDED: all 10 watchlist symbols, ~2 years each: 4h ~4200-4385 bars, 1d ~675-731 bars,
  into /app/backend/data/historical_candles.db. Detaches us from Kraken's 120-day 4h cap.
- CCXT lab.data_store.append_latest() verified to top up the current-month tail (nightly).
- Validated: 1-yr replays BTC(112 trades)/ETH(108) with full A-F + regime breakdowns.
- Run manually to (re)seed: `python -m lab.seed_history`  (idempotent).
- Tests: tests/test_lab_seed.py (3) pass.

## Research Lab — Increment: Walk-Forward + Parameter Sensitivity (2026-06-28)
- `backend/lab/optimize.py` (pure compute, credit-free):
  * grid_search(symbols,start,end,grid,metric) — Cartesian sweep, ranked combos (see plateau).
  * sensitivity(target,values) — vary ONE param; verdict ROBUST(plateau)/FRAGILE(cliff) via CV.
  * walk_forward(grid,folds) — rolling IS-optimize -> OOS-test; reports wfa_efficiency (OOS/IS),
    oos_positive_folds, verdict (ROBUST / WEAK-OVERFIT / NO-IN-SAMPLE-EDGE / INCONCLUSIVE).
  * Grid keys are prefixed: "set:<field>" (RiskSettings) or "prof:<strategy>:<field>" (exit profile),
    so sweeps can target Hunter/Squeeze exit profiles or entry/risk settings independently.
- PERF/PARITY: run_backtest now uses a bounded ANALYSIS_LOOKBACK=540 trailing window (matches the
  live ~540-bar fetch limit) -> full 2y BTC replay ~12s (was O(N^2)/timeout). Also bounded zone calc.
- run_backtest signature: profile_override -> profile_overrides {strategy:{field:val}} (per-strategy).
- Validated on real seeded data (sensitivity + 3-fold WFA on BTC). Tests: test_lab_optimize.py (5) pass;
  full lab+exit suites green.

## Research Lab — Increment: Async Job Queue + PDF Export (2026-07-01)
- `backend/lab/runner.py`: LabWorker (background asyncio task, single-worker ThreadPool)
  polls `lab_runs` for QUEUED jobs, runs ONE at a time off the request path, streams
  progress_pct to Mongo, stores result. create_run() validates + persists with git_hash +
  resolved window. Recovers stuck RUNNING->QUEUED on boot. Kinds: backtest/grid_search/
  sensitivity/walk_forward. Period dropdown (1m/2m/3m/quarter/6m/1y/2y/custom) -> window.
- `backend/lab/lab_report.py`: standalone PDF (reuses pdf_report styling) — config+git
  provenance, then kind-specific section (backtest metrics + exit-module A-F + regime;
  grid ranking; sensitivity curve+verdict; walk-forward folds + WFA efficiency + verdict).
- optimize.grid_search/sensitivity/walk_forward gained progress_cb.
- server.py endpoints (owner-gated): GET /api/lab/data/coverage, POST /api/lab/runs,
  GET /api/lab/runs, GET /api/lab/runs/{id}, GET /api/lab/runs/{id}/pdf. LabWorker started/
  stopped in lifecycle.
- VERIFIED e2e via curl: create walk_forward -> progress 33->67->100 -> DONE (git recorded)
  -> valid PDF (4KB). Tests: test_lab_runner.py (7) + full lab suite 37 pass. No live regression.
- REMAINING: Research Lab UI (config -> queue -> progress -> download; dual-track Validate
  Current/Fresh Values) + manual approval gate (lab_param_proposals -> Apply to Production).

## Research Lab UI + Cockpit Leaderboard (2026-07-02, web frontend)
- NAV/PAGE: "SETTINGS" tab renamed to "RESEARCH LAB" (FlaskConical icon, AppShell.jsx).
  Settings.jsx now shows a "Research Lab" title + StrategyValidationPanel FIRST, existing
  risk/engine config moved below.
- `components/StrategyValidationPanel.jsx`: owner control panel wired to /api/lab/*.
  Asset chips (from /lab/data/coverage), period dropdown, RUN VALIDATION -> dual-track dialog:
  Track A "Current Scenario" (backtest, live params) / Track B "Fresh Values" (param sweep ->
  walk_forward, rolling IS->OOS). Runs list with live progress polling + Download PDF (blob).
- api.js: labCoverage/labCreateRun/labRuns/labRun/labRunPdf.
- COCKPIT (Dashboard.jsx): two existing charts (AnalyticsCarousel) kept in place; added
  LeaderboardAnalytics section — dynamic recharts pie + property dropdown (Strategy/Model,
  Crypto Asset, Exit Module A-F, Win/Loss, Drawdown by Asset) computed client-side from
  SELL trades, with a net-P&L ranked leaderboard; Today's Executions moved to the very bottom.
- Tested: testing_agent web frontend 6/6 pass (iteration_15). Lint clean. No live-path regression.
- BACKLOG (from testing agent): split Dashboard.jsx/Settings.jsx into smaller files;
  leaderboard currently slices last 100 trades. Manual approval gate (lab_param_proposals ->
  Apply to Production) still pending.
