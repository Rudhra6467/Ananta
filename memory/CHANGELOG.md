## 2026-07-17 — Wire 4 catalog strategies + Exit Engine 3-tab restructure (iter58/59 GREEN, web+mobile+backend)

- **P0 — All catalog strategies now testable/deployable.** Wired the last 4 reference-only specs to the
  declarative engine so they get Deploy + Test buttons (web + mobile parity): `turtle`, `time-series-momentum`,
  `stochastic-momentum`, `vwap-mr`. Added indicator primitives to `backend/declarative_engine.py`
  (`roc`, `stoch_k`, `stoch_d`, `vwap`, `vwap_lower`/`vwap_upper`) + SUPPORTED_FNS entries; defs in
  `backend/strategy/declarative_defs.py`; wiring in `backend/library_seed.py` (WIRED_ENGINE_KEYS) + bootstrap
  backfill in `server.py` (_bootstrap_declarative). Verified: /api/library=16, registry/metrics include all 4,
  deploy→PAPER works, real declarative backtests produce metrics.
- **Pairs Trading kept REFERENCE-ONLY** (per owner decision): true 2-asset spread strategy the single-asset
  declarative engine can't run. Marked via `REFERENCE_ONLY` in library_seed → backend `reference_only=true`,
  `reference_note="Analysis only — requires 2-asset engine"`; web shows `card-reference-note-*`, mobile
  `library-reference-note-*`; NO deploy button on either surface.
- **What-If (counterfactual) FIX (web + mobile):** both TestResult views were reading the wrong path
  (`per_symbol[sym].exit_comparison`); backend returns it at `result.exit_comparison[symbol][timeframe]`.
  Now reads the correct nested block → the "What-If — same entries, different exit" comparison table renders.
- **Exit Engine UI polish (web + mobile) to match owner reference:** clean horizontal connecting-line step bar
  (1. Scope → 2. Method → 3. Configure → 4. Deploy), large scope cards with full "Modify Exit for a
  Strategy/Specific Coin/Global Exit" names + icons + chevrons; subtitle "Configure how your strategies exit
  trades".
- **Exit Engine 3-tab restructure (web + mobile, iter59):** tab now has 3 sub-tabs
  **Exit Engine → Risk Monitor → AI Analysis**. Removed the "Advanced Settings" button/modal. The former
  advanced content moved into the new **Risk Monitor** sub-tab, split to avoid duplication:
  * "Entry & Exit Engine" card = READ-ONLY summary (Active Exit Engine, Trail Multiplier, Breakeven Arm,
    Hard Stop-Loss); its CTA navigates to the Exit Engine sub-tab (no exit-config modal).
  * "Risk Monitor / Safeguards" = the only editor for risk/entry safeguards (min confidence, daily loss cap,
    max spread, max open positions, sizing, kill-switch, credentials). Exit stop/trail edited ONLY in the
    Exit Engine workflow — no duplicate editors across the two sub-tabs.
  * Web: `Settings.jsx` gained optional `onGotoExitEngine` prop (hides the exit-config modal + repoints the
    card CTA); `ExitEngine.jsx` renders `<SettingsPage onGotoExitEngine=...>` in the risk sub-tab.
  * Mobile: `workspace.tsx` Segmented → 3 options; new `RiskMonitor` component (rm-engine-summary +
    rm-safeguards); Advanced modal + button removed.


## 2026-07-15 — Launch Hardening: demo history seed + web onboarding + Resend (iter57 GREEN, backend+web 5/5)

- **P0 Backend — Demo account pre-seeded with paper-trade history** (`demo_seed.seed_demo_history`):
  generates ~21 closed PAPER trades over the last 3–7 days (hunter/squeeze/continuation, note='DEMO')
  + 2 open positions on a fresh capital book, so `review@ananta.ai` lands on a populated dashboard
  (non-zero realized P&L, trade ledger, live positions, analytics) instead of a blank $25k book.
  Wired two ways: (1) `auth.seed_demo` seeds it at startup ONLY if `trades` is empty (never clobbers
  real activity); (2) `onboarding_paper_setup` is now role-aware (`Depends(require_owner)` payload) and
  re-seeds the history at the chosen capital when role=='demo'. OWNER onboarding stays a clean fresh book.
- **P0 Web — First-login Paper Trading onboarding wizard ported to web** (`components/WebOnboarding.jsx`):
  full parity with mobile — Welcome → Research First → Capital → Allocation → Strategies → Summary,
  drives shared `/api/onboarding/paper-setup`, shown once per browser via localStorage `ananta_onboarded`.
  Wired into `AppShell` (renders when logged in + not onboarded); the guided-tour auto-open now waits
  until onboarding is complete. Added `api.onboardingPaperSetup`.
- **P1 Backend — Resend transactional email** (`email_service.py`, playbook-based, non-blocking via
  `asyncio.to_thread`): owner notified (`WAITLIST_NOTIFY_EMAIL`) on every new `/access/request`; user
  notified on approve/reject. All sends are fire-and-forget with errors swallowed so the waitlist flow
  never breaks. Owner email delivery verified; user delivery requires a **verified Resend domain**
  (test-mode only delivers to the account's own verified address). Env: `RESEND_API_KEY`, `SENDER_EMAIL`,
  `WAITLIST_NOTIFY_EMAIL`.


## 2026-07-12b — Header-action consolidation + PDF download fix (web, iter49 GREEN)

- **Per-tab actions moved into the shared scroll-through TOP header** (frees a full row):
  Research "Start Research", Workspace "Stop Ananta", Strategy "Search" + "+ Add" now render in
  `#header-action-slot` (AppShell context row) via a new `components/HeaderActionPortal.jsx`.
  Removed the separate secondary header rows (research-header / workspace-header / strategy title card).
- **FIX — "Owner authentication required" on PDF download:** lab-run PDFs require a Bearer token that
  `window.open` can't send. Added `downloadPdf()` (in `lib/pdfRegistry.js`) — authenticated `fetch`
  → streamed blob → triggers a download; Workspace "Ananta PDFs" now uses it.
- **Download progress %:** each Ananta PDF row shows a live progress bar ("Preparing…" → % → Done)
  driven by the streamed Content-Length.
- **Removed the duplicate Stop Ananta** (Settings/Engine&Risk `emergency-kill-btn` deleted; the header
  control is now the single global one).
- **QuadrantCard CTA moved to the title row** ("Open Engine" / "Open Risk Monitor" now sit next to the
  card title instead of a full-width bottom bar).


## 2026-07-12 — 5-Tab UI Sprint + Production P0 (validation/PDF) — web

### P0 (production blockers) — fixed & verified (backend 5/5 pytest, iter48)
- **Research validation failing on production**: fresh deploy containers have an EMPTY local
  SQLite candle store (`/app/backend/data/historical_candles.db`), so every backtest cell returned
  `insufficient_history`. Added `ensure_history()` on-demand CCXT backfill in the lab worker
  (`lab/runner.py`) + a now-anchored `resolve_window` fallback. Validation now works in ANY env.
- Added **30m/15m timeframe** support (`data_store.TF_MS`) + a `timeframe` field on lab runs
  (default 1h). Verified: 15m/30m/1h runs all reach DONE with trades; lab PDF builds.
- Report PDFs (`/report/full.pdf`, `/report/trades.pdf`) confirmed valid & public.
  (The "red toast" was the validation PDF, blocked by the validation failure above.)

### Phase 1 — Cockpit
- SystemHealthChip moved into the header row next to Daily P&L (freed a row).
- Regime full-width row removed → compact "(Market · Neutral/Bull/Bear)" tag next to Trade Life Cycle title.
- "Active Watchlist" → "Watchlist"; row split 80/20 with a compact Charts button.
- Leaderboard "Ranked by Net P&L" shows 2 rows + Show more.

### Phase 2 — Trade
- Removed Execution-Mode section. Added a persistent toolbar: Fresh Start / PDF / Refresh (left) +
  Stop Ananta pinned top-right (renamed from Emergency Stop; same manual_kill_switch).
- Orders subtab now opens with a single Start Order button → reveals the order form (with Back).

### Phase 3 — Strategy
- Compact "Strategy Center" title card with Search + "+ Add" pinned top-right (freed 2 rows).
- Search opens a full-screen list of strategies by name (leaderboard-style).
- Strategy leaderboard shows 2 + Show more.
- Detail: rating/grade moved top-right by the name; Edit + Analyse buttons top; full-width
  "Analyse this Strategy" bottom → params-choice modal (current vs edit) → StrategyValidationPanel.
- Detail subtabs reduced to Overview / Parameters / AI / History (removed Validation/Research/Timeline).

### Phase 4 — Research Lab
- Persistent "Start Research" button top-right (remounts a fresh wizard).
- Wizard: added a Timeframe step (1h default / 30m / 15m) after Period; strategy step shows 3 + load more.
- On run completion the run's PDF is registered to Workspace › Ananta PDFs + a toast tells the user.
- AI Analysis: TradingCoach tagline now just "Get a 7 day performance review"; AI Quant Analyst shows
  1 suggestion + Load more; removed the Fresh/PDF/Refresh (Reports) block (now lives in Trade).

### Phase 5 — Workspace
- Persistent header with Stop Ananta top-right (freed a row).
- New "Ananta PDFs" section (localStorage registry, `lib/pdfRegistry.js`) after Closed Trades:
  open / Ask-Ananta-to-analyse / delete. Trade + Research PDFs auto-register with a "check Workspace" toast.
- Competition Demo shows inline load output (trades/configs/strategies) + a "How to use Ananta" button.

### Deferred within Phase 5 (backlog)
- "Open Engine" button reposition next to the "Entry & Exit Engine" title lives inside Settings.jsx — needs its own pass.
- "How to use Ananta" is currently the guided tour; a true downloadable how-to PDF needs a backend doc endpoint.


## 2026-07-11f — Launch Page refit + Sign Up funnel + Dashboard status toast (web)

- **Launch Page** (`pages/LaunchPage.jsx`): refit to a single screen (`h-screen overflow-hidden`,
  tightened spacing) so header + hero + 2 CTAs + 3 feature cards + tagline fit without scroll.
  "Skip to homepage" moved to a fixed **bottom-right** pill (`data-testid=skip-to-homepage`).
  All CTAs (Start Free Trial, Watch Video, feature cards, top-right profile) now route a PUBLIC
  visitor to `/signup`; the owner goes straight to `/`.
- **Sign Up page** (new `pages/SignUp.jsx`, route `/signup` in `App.js`): single-screen name+email
  form that funnels into the existing Waitlist Access-Gate — submit calls `POST /api/access/request`,
  shows a success toast, then routes to `/`. Owner bypasses to `/`. Includes a bottom-right skip link.
- **Dashboard status toast** (`pages/Dashboard.jsx`): one-time-per-session toast (4s) reading
  "Ananta Status: 4 paper trading strategies are currently live and monitoring the markets." with a
  "View Active Strategies" action that switches to the Strategy tab. Fixed a React.StrictMode
  double-mount issue by stamping the `ananta_status_toast_seen` sessionStorage flag INSIDE the
  timeout (with a re-check guard) so the toast reliably fires exactly once.
- Verified: iter47 testing agent — backend 6/6 pass; SignUp submit navigates home in ~0.07s (real
  browser); launch single-screen + CTA funnel confirmed; Dashboard toast confirmed firing after fix.
- Note: the screenshot (Playwright) tool intermittently showed app-initiated POSTs hanging in this
  Cloudflare-fronted preview — NOT reproducible in normal browser automation; backend healthy.


## 2026-07-11e — Research validate multi-select + Workspace "AI Analytics" compact copilot (web)

- **Research › Validate › step 1** (`components/lab/ResearchWizard.jsx`): "Choose a strategy" → **"Choose strategies"**.
  Removed the per-card pencil/edit button; each strategy is now a **tick-box (multi-select)** — pick several engines
  to validate together. Clicking a card toggles its checkbox (ticked = selected). `strat` is now an array; the run
  passes `strategies: strat` (backend `labCreateRun` already accepts an array). Verified 1→3→2 selection.
- **Workspace tab rename**: "ALL AI INFO" → **"AI ANALYTICS"**.
- **AI Copilot compacted** (`pages/Workspace.jsx` → `AiCopilotCompact`): replaced the large descriptive card with a
  chip-sized "Ask Ananta" pill + on/off toggle (matches the floating bottom-left chip) **plus a small inline chat bar**.
  Typing a question + send dispatches `ananta:ask`; the floating AskAnanta panel opens and answers (AskAnanta now
  listens for that event; `send` refactored to a stable `useCallback`). Saves vertical space.
- These target the web app (responsive, incl. mobile-width bottom nav) — the surface in the shared screenshots.

---


## 2026-07-11d — Ask Ananta ON + public Launch/Landing page (web)

- **Ask Ananta enabled** (`settings.ask_ananta_enabled = true`) so the owner can test the copilot before launch.
- **New marketing launch page** at web route `/launch` (`frontend/src/pages/LaunchPage.jsx`), modeled on the
  shared reference: hamburger menu (left), centered Ananta brand (logo + wordmark sized ~50% larger than the
  reference), top-right "Skip to homepage" link + profile/owner-login icon. Hero "Your 24/7 AI Trading Assistant"
  + subtitle, teal "Start Free Trial" and outlined "Watch Video 3min" CTAs, and 3 clickable feature cards
  (Strategies / AI Assistant / Research Lab) with themed colored icons on a dark grid + teal-glow backdrop.
- Everything is clickable and on-brand (teal #14E0C9 accent = logo/mobile brand color, atlas dark theme):
  Start Free Trial / Watch Video / feature cards / menu items → owner goes straight into the app, public opens
  the "Request early access" waitlist modal. Skip-to-homepage + profile icon → app homepage "/".
- Verified on desktop (1280) and mobile portrait (430) viewports; owner vs public branching confirmed.
- Note: launch page lives at `/launch` (share this link with new customers); can be promoted to site root later
  without disrupting the owner app or existing tests.

---


## 2026-07-11c (iter46) — Phase 3/4 + Access-Gate Waitlist MVP + System Health self-check (web + mobile)

### Enhancement — System Health self-check chip (Phase 3 client health strip)
- Backend `GET /api/health/selfcheck` (fast, credit-free, ~0.17s): backend, MongoDB (bounded ping),
  market-data freshness (warm cache, no network), trading-engine loop status + last activity age.
- Compact Cockpit chip that expands into a popover (web) / bottom sheet (mobile) — low-footprint per
  owner's "use a dropdown if it eats screen space" note. Rows: Backend, Database, Market Data, Engine, Session.
- Added `trading_loop.is_running` + `market_data.cache_stats()`.

### Access-Gate / Waitlist MVP (Option A — lead capture, no public accounts yet)
- New `access_requests` collection + endpoints: `POST /api/access/request` (PUBLIC, idempotent per email,
  400 on bad email/empty name); `GET /api/access/requests` (owner); `POST /api/access/requests/{id}/{approve|reject}` (owner).
  Deliberately separate from the auth layer so we can upgrade to real accounts later without refactoring.
- Web: `AccessGateProvider` + `useAccessGate` + Waitlist modal wrap the app. `gate(feature)` → owner passes,
  public opens the Waitlist modal. Wired: Ask Ananta (chip visible, open gated), System Health (pill visible,
  expand gated), MetricExplainer (i) gated, onboarding tour gated.
- Owner: all info UI always available; onboarding auto-shows once per SESSION (not a permanent "don't show
  again") and is always re-launchable; no waitlist ever shown to owner.
- Mobile is login-first → added a "Request early access" CTA on the login screen → same Waitlist modal;
  gate infra also wired into mobile Ask Ananta / System Health for future parity.
- a11y: added `DialogDescription` to the web Waitlist modal.

### Phase 2/3 hardening recap (iter45, same push): web double-submit coalescing; session-expiry (auth
  returns 401 for expired/invalid tokens, 403 for public → FE auto-logout + toast); `/risk/status` warm-cache
  fix (~2.2s→0.09s).

### Testing / Deployment
- Testing agent iter46: GREEN across shared backend + web + mobile; no owner-flow regressions.
- `conftest.bind_loop_local_db()` fixes cross-file asyncio event-loop rebinding — full direct-DB suite
  order-independent (23 passed together). New tests: test_iter46_access_waitlist.py, test_iter46_http_access_and_health.py.
- `deployment_agent` pre-launch scan: PASS, no blockers.

### Launch (Phase 4 — owner-driven)
- Ask Ananta left OFF by default; owner flips on when ready. Deploy (web + mobile build) via the Emergent Publish button.

---


## 2026-07-09 (iter39) — Phase B COMPLETION: declarative exits + real backtest + Deploy/Backtest UI (tested, no LLM cost)

Rounded out Phase B so wired catalog strategies trade their own logic end-to-end and carry real metrics.

- **Declarative EXIT signals (`position_watcher.py`):** for positions opened by a declarative strategy, the watcher now honors the strategy's OWN exit rule as a SECONDARY trigger — universal safety exits (stops/kill/floors) keep top priority; only when the engine says "hold" does it consult the declarative exit spec (full exit on trigger).
- **Real declarative backtest (`declarative_backtest.py` + `POST /api/library/{id}/backtest`):** replays a wireable strategy's spec over historical 1H OHLCV (ccxt via `fetch_history`, long-only, one position, spec exit + hard stop) and computes roi/win-rate/profit-factor/Sharpe/Sortino/max-DD/avg-trade/trade-count. Persists onto the library doc (`historical_results` + `backtested=true` + `backtest_meta`), replacing seeded numbers. Pure CPU, NO LLM credits. ~4s for 720 bars.
- **UI (web CatalogDetail + mobile library detail):** wireable strategies get an engine panel — **Deploy(Paper)/Disable** toggle (arms the strategy to the paper engine in one tap), **Run Backtest** (updates the displayed metrics), **Manage in Engine**, and a live status pill.
- **Tests:** testing-agent iter39 — backend 10/10 pytest (`tests/test_iter39_phase_b.py`), web + mobile parity verified (deploy toggle, backtest, manage routing); baseline restored; no LLM endpoints hit. All prior suites (iter36/37/38) still green.
- **Remaining (cosmetic, non-blocking):** mobile RN-web `shadow*` deprecation warning (false positive on native — left to avoid breaking native shadows); web leaderboard `<span> in <option>` hydration warning (visual-editing tooling artifact).


## 2026-07-09 (iter38) — P2/P3 Phase B: DECLARATIVE ENGINE — catalog strategies wired to the engine (backend + web + mobile, tested)

Wired the catalog Strategy Library strategies into the live/paper trading engine via a GENERIC declarative indicator/rule executor — no bespoke Python per strategy. Adding another indicator strategy = add one spec dict.

- **`declarative_engine.py` (NEW):** pure OHLCV executor. Indicators: EMA, SMA, RSI, ATR, MACD (line/signal/hist), Bollinger (upper/mid/lower), Donchian (prior-N high/low), Supertrend (line+dir), Keltner (upper/mid), ATR-breakout level. Condition ops: cross_above/below, gt/lt/gte/lte, rising/falling. Operands: indicator ids, price fields, prev_close, numbers, `$param` refs. `evaluate(spec, bars, params)` → entry/exit/reason/indicators. Safe on insufficient bars.
- **`strategy/declarative_defs.py` (NEW):** 8 single-asset strategies registered as first-class engine strategies (params schema + declarative spec + DNA): **ema-cross, supertrend, rsi-momentum** (default PAPER+enabled) and **macd-trend, bollinger-mr, donchian-breakout, atr-breakout, keltner-breakout** (default DISABLED). key == Strategy Library id (engine_key), so catalog ↔ runnable engine strategy are 1:1. They appear in /strategy/registry (now 11), /strategy/metrics, get lifecycle states + per-strategy configs — full parity with hunter/squeeze/continuation.
- **Engine (`trading_engine.evaluate_symbol`):** new declarative block after the built-in strategies — iterates enabled declarative keys, resolves full params via `strategy_runtime.resolve_full_params` (schema defaults ← active config), evaluates the spec on 1H bars, and on a signal opens a PAPER position sharing the SAME book budget/slot/spread/cooldown/kill-switch guards. Lot + structural stop come from the per-strategy config overlay (Phase A). Exits handled by the universal exit engine (get_profile returns a safe default for declarative keys).
- **Bootstrap (`_bootstrap_declarative`):** idempotently seeds strategy_meta (only the 3 default-enabled trade; owner changes preserved) and backfills engine_key/wireable on existing library docs.
- **UI:** web — wireable catalog cards show the live engine status pill (PAPER) instead of CATALOG, and CatalogDetail has a "Manage in Engine" button → engine StrategyDetail (states + configs). Mobile — wireable cards show a WIRED pill; library detail has a "Manage in engine" button → /strategy/{engine_key}.
- **Also fixed** (from iter38 testing): PUT /strategy/{key}/state now enforces the enabled↔status invariant (DISABLED/ERROR ⇒ not enabled; enabling an off strategy ⇒ promoted to PAPER) and returns the full merged state doc.
- **Tests:** `tests/test_iter38_declarative_engine.py` (8 unit, synthetic OHLCV) + testing-agent `tests/test_iter38_declarative_engine_http.py` (9 HTTP). Backend 26/26 green; web + mobile verified (status pills, Manage-in-Engine routing). Everything PAPER-only; imported free-text strategies stay catalog-only.
- **Follow-ups:** honor declarative EXIT signals in the position watcher (currently universal exits only); backtest declarative strategies in the Research Lab so their catalog metrics reflect real numbers; wire the remaining 5 (enable from UI when ready).


## 2026-07-09 (iter37) — P3 Phase A: PER-STRATEGY ENGINE CONFIGS (backend + web + mobile, tested)

Migrated the live/paper trading engine from a single GLOBAL `RiskSettings` singleton to PER-STRATEGY config resolution. Fully backward-compatible + PAPER-only — zero behaviour change until an owner activates a config. Fixes the historical bug where activating one strategy's config clobbered fields shared by all strategies.

- **`backend/strategy_runtime.py` (NEW):** `resolve_active_params(db)` → {strategy_key: clamped engine params} for strategies with an active config; `overlay_settings(base, params)` returns a per-strategy COPY of RiskSettings with strategy-level params applied. `ACCOUNT_LEVEL_FIELDS` set enforces the config split — per-strategy configs can NEVER override account-level risk (max_concurrent_positions, max_daily_loss_pct, max_spread_pct, fees, slippage, vault ceiling, min_confidence).
- **Engine wiring (`trading_engine.evaluate_symbol`):** resolves per-strategy effective settings once per cycle; hunter→`evaluate_primary`, squeeze→`evaluate_squeeze`, continuation→`evaluate_continuation` each get their own overlaid settings + per-strategy lot size. `squeeze.evaluate_squeeze()` extended to accept a config-driven `vol_expansion_min` (was a hardcoded constant).
- **Endpoints:** `POST /strategy/configs/{id}/activate` NO LONGER writes to global RiskSettings — it records the active config per strategy (returns applied/applied_params/ignored_account_level). NEW `POST /strategy/{key}/deactivate` (revert to global baseline) and `GET /strategy/{key}/effective` (shows exactly what the engine uses now). `/strategy/metrics` now also exposes `active_config_name`.
- **UI:** web Research Lab → Saved Configs panel: ACTIVATE + LIVE badge + new REVERT button, accurate toast ("N strategy params now live · M account-level ignored"). Mobile strategy detail: ACTIVATE + REVERT with a platform-aware `confirmAction` (window.confirm on RN-web, Alert on native — fixes multi-button Alert no-op on web).
- **Tests:** `tests/test_iter37_per_strategy_configs.py` (6 unit) + testing-agent `tests/test_iter37_per_strategy_configs_http.py` (9 HTTP integration). Backend 32/32 green (incl. iter36 regression). Verified: activating hunter config w/ normal_lot_usd=150 left global settings at 75 & max_concurrent_positions at 8 (no clobber); effective flips on activate/deactivate; activate blocked when not validated.
- **Next (P3 leftover, low priority):** the Research Lab backtest still reads global settings (not per-strategy) — could unify later. **Phase B (next):** generic declarative executor to wire simple indicator catalog strategies (EMA Cross, Supertrend, RSI Momentum…) to the engine.


## 2026-07-09 (iter36) — P2 Strategy Import Pipeline SHIPPED (backend + web + mobile, tested all-green)

Full "Strategy Import Pipeline" — import external strategies, AI-extract into Ananta's schema, validate, review/edit, approve into the Strategy Library. Cross-platform parity (web + mobile), all mutations owner-gated, AI via Emergent LLM key (Claude sonnet-4-6).

- **Pluggable adapters** (`backend/strategy_import.py`): FrameworkAdapter registry with detectors for Pine Script, Freqtrade, Jesse, generic JSON. Add a new framework = register ONE adapter (detector + ai_hint), no pipeline/UI refactor. `detect_format()` is credit-free auto-detect.
- **AI extractor** (`backend/import_ai.py`): one strict-JSON Claude call extracts entry/exit rules, risk management, position sizing, indicators+params, timeframes, direction (long/short/both), regimes, volatility pref, holding period, strengths/weaknesses, tags, ai_summary/health/confidence, PLUS a conversion report (confidence_score, unsupported_features, missing_logic, warnings, notes).
- **Deterministic validation** (`validate_extraction`): layered guardrails → issues [{severity, message}], status ready|review|blocked. Flags no-entry (error → blocks approve), missing exits/params/risk (warning), short-selling (warning — engine is long-only spot today), non-crypto market type, exotic indicators.
- **Draft lifecycle**: `strategy_imports` collection (draft → approved). On approve → projected into `strategy_library` as a first-class catalog entry (`imported=true`, filterable, AI-gradeable, leaderboard-eligible).
- **Endpoints** (owner-gated except detect/formats): GET `/library/import/formats`, POST `/library/import/detect`, POST `/library/import/analyze`, GET `/library/imports`, GET/PUT/DELETE `/library/imports/{id}`, POST `/library/imports/{id}/approve`. Declared BEFORE `/library/{strategy_id}` to avoid route shadowing.
- **Web** (`components/ImportStrategyModal.jsx` + StrategyCenter): "Import Strategy" button/card → 2-step modal (paste w/ live format detect → review: confidence ring, color-coded validation, conversion report, editable metadata → Save to Library). CatalogDetail shows Imported badge + conversion report + indicators + strengths/weaknesses. Added a separate "Build with AI" card (existing StrategyArchitect, web-only).
- **Mobile** (`app/library/import.tsx` + strategy tab + library/[id]): owner-only Import button → full-screen import screen (same 2-step flow, RN components) → library detail shows imported badge + conversion report + indicators.
- **Tests**: `backend/tests/test_strategy_import.py` (9 pure-logic) + testing agent iter36 `test_iter36_strategy_import_e2e.py` (17 e2e). Backend 100%, web 100%, mobile 95% (only gap: Build-with-AI is web-only, out of scope for import). a11y: added DialogTitle/Description to the web modal.
- **Note**: imported strategies are catalog-level today (like the other 13 non-internal library strategies); wiring them to the LIVE trading engine is the next P2 task (their schema already carries entry/exit/params/direction for that).


## 2026-07-09 (iter31) — MOBILE full parity rebuild (Expo/React Native, tested all-green)

Rebuilt the mobile app (/app/mobile) to match the web 5-tab "workspaces" model against the SAME shared FastAPI
backend. Old tabs (portfolio/reports/settings) removed; new expo-router screens added.

- **Navigation** ((tabs)/_layout.tsx): 5 tabs — Cockpit, Trade, Strategy, Research, Workspace — each with a
  "one question per page" header (src/components/PageHeader.tsx).
- **Cockpit** (index.tsx, existing): portfolio, watchlist, engine status, AI decisions.
- **Trade** (trade.tsx, NEW): Paper/Live mode segmented + Emergency Stop; Positions / Orders / History sub-tabs.
  Fixed the `{items}` response shape (was crashing on `.filter`).
- **Strategy** (strategy.tsx + strategy/[id].tsx rewrite): cards from /strategy/metrics → detail with health score +
  breakdown bars, lifecycle timeline, and an owner status editor (LIVE/PAPER/DISABLED via PUT /strategy/{key}/state).
- **Research** (research.tsx, NEW): Validate wizard (BTC + period → real /lab/runs backtest → results), AI Coach
  (credits switch + weekly review + 1-tap apply), Closed Trades (paper/live → AI review + open PDF via Linking).
- **Workspace** (workspace.tsx, NEW): editable engine/risk settings, Competition Demo load/reset, Academy (10 lessons
  in a modal), System health, Replay Guided Tour, logout.
- **Onboarding** (onboarding.tsx, NEW): animated first-launch pipeline gated by AsyncStorage 'ananta_onboarded';
  root _layout.tsx redirects owner→/onboarding on first launch, re-launchable from Workspace.
- **API client** (src/api.ts): added strategyMetrics/registry/setState, lab coverage/runs/monteCarlo, coach
  review/apply/trades-review, demo status/load/reset, tradesPdfUrl. Uses EXPO_PUBLIC_BACKEND_URL + '/api'.
- Tested: testing_agent iter31 (mobile, Expo web preview) — login, onboarding, all 5 tabs, strategy status round-trip,
  wizard/coach/closed wiring, demo, academy, logout — ALL GREEN, no red screens. Backend left clean (demo loaded).
- Non-blocking: RN-web `pointerEvents` deprecation warning; expo-notifications web warning (harmless).
- NOTE: mobile is validated on Expo web preview; features needing a native build (push) require Publish + a build.


## 2026-07-08 (iter30) — Strategy Edit + Closed-Trades Analysis + wizard speed (web, tested green; 1 race fixed)

- **Strategy "Edit Strategy" FAB** (`StrategyCenter`): owner-only floating bottom-right button on the strategy detail;
  jumps to the Parameters editor. Hidden for non-owners. Metric explainers added to the Health card (Win Rate / ROI).
- **Closed-Trades Analysis** (`components/lab/ClosedTradesAnalysis.jsx`) as a new **Research → Closed Trades** sub-tab:
  two boxes — **Closed Paper Trades** & **Closed Live Trades** — each listing trades with an **Analyse Trades** button
  that opens a report modal: an **AI-written review** (`POST /api/coach/trades-review`, Claude) + **Download PDF** +
  **Open on Web** (`/api/report/trades.pdf?mode=paper|live&inline=`). Backend PDF endpoint gained `mode` + `inline` params.
- **Workspace → Closed Trades History** section with an **Analyse** button that deep-links to the Research Closed-Trades
  sub-tab (via `ananta:navigate` + a persisted `ananta_research_sub` flag — fixes a mount race the tester caught).
- **Research wizard** now defaults to **BTC + 1-month** so a judge's backtest finishes in seconds.
- Tested: testing_agent iter30 — backend 7/7, frontend all flows; the deep-link race was fixed and self-verified
  (`research-subtab-closed[data-state=active]`).


## 2026-07-08 (iter29) — Phase 2 "judge wow" + Phase 3 "depth & delight" (web, tested all-green 12/12 backend + full frontend)

Competition-focused feature wave. Web only. Every AI surface has a visible credits switch.

### Phase 2 — the judge wow
- **Interactive onboarding pipeline** (`components/OnboardingPipeline.jsx`): CI/CD-style animated first-login gate
  (Account→Connect Exchange→Verify→Import→Choose Strategy→Validate→AI Review→Paper→Ready for Live) ending with a
  "trading OS is ready · 4-minute setup" finale. Shows once (localStorage `ananta_onboarded`); re-launchable from
  Workspace "Replay Tour" via the `ananta:tour` window event.
- **Competition Demo Workspace** (`backend/demo_seed.py` + `/api/admin/demo/{load,reset,status}`, owner-only):
  one click seeds a curated preview across the 3 REAL strategies — 42 trades, 5 saved configs, 2 completed lab runs,
  varied statuses (hunter LIVE / squeeze PAPER / continuation DISABLED). Deterministic; hunter is the healthiest
  (health 78, 55.6% wr), continuation weakest. Wired in Workspace (`ws-demo` Load/Reset + status).

### Phase 3 — depth & delight
- **AI Trading Coach** (`backend/coach.py` + `/api/coach/weekly-review` & `/api/coach/apply`, owner, Claude Sonnet):
  proactive 7-day review (summary, best/worst strategy, common mistake, ONE applyable tweak, estimated impact,
  confidence). `apply` clamps to a safe whitelist (min_confidence, max_daily_loss_pct, max_concurrent_positions,
  max_spread_pct, squeeze_vol_expansion_min, rsi_reset_max). UI (`components/lab/TradingCoach.jsx`) in Research →
  AI Analysis with a credits switch + 1-click Apply.
- **Visual Research Lab wizard** (`components/lab/ResearchWizard.jsx`): guided Strategy→Dataset→Period→Validation→Run
  stepper on the Research Validate tab, driving a real `/api/lab/runs` backtest (+ optional Monte Carlo), with a
  progress animation and a per-symbol results dashboard + verdict. Legacy panels tucked behind "Show advanced tools".
- **Academy** (`components/Academy.jsx`): education hub modal with 10 curated lessons (Getting Started, Trading Basics,
  Risk Management, How Hunter/Squeeze work, How AI Thinks, Walk-Forward, Monte Carlo, Paper vs Live, FAQ). Opens from
  Workspace `ws-academy`.
- **Clickable metric explainers** (`components/MetricExplainer.jsx`): tap the (i) on Health / Win Rate / ROI to see a
  definition + quality bands + where your value lands. Wired into the Strategy Health card.
- Tested: testing_agent iter29 — backend 12/12 (tests/test_iter29_demo_coach.py), frontend 100% of spec. No bugs.
  Note: full hunter backtest is slow in preview (>60s); wizard shows progress and is spec-permitted to time out.


## 2026-07-08 (iter28) — 5-tab "Workspaces" navigation restructure (web, tested all-green)

Adopted the user's workspaces-not-pages model. Navigation is now the monitor → create → validate → trade → manage journey:
**Cockpit · Trade · Strategy · Research · Workspace** (was Cockpit · Portfolio · Strategies · Logs · Research Lab).

- **Trade** (NEW `pages/Trade.jsx`): Paper/Live toggle + Emergency Stop workspace bar; sub-tabs Positions / Orders /
  History / Performance. Absorbs the old Portfolio page (deleted `pages/Portfolio.jsx`) + pending orders + analytics.
- **Research** (NEW `pages/Research.jsx`): strategy-first validation lab. Sub-tabs Validate (strategy dropdown →
  Saved Configs / Monte Carlo / Strategy Validation) and AI Analysis (AI Analyst terminal + the former Logs/Reports
  page — reasoning timeline, counterfactual engine, attrition funnel, analytics).
- **Workspace** (NEW `pages/Workspace.jsx`): Engine & Risk (the settings page, now Exit-Engine + Risk-Monitor only),
  Learn & Compete (Academy + Competition Demo as "coming soon" placeholders — built in Phase 2/3), System Health
  (Backend/Mode/Gate), About + owner logout.
- **Settings.jsx** stripped: removed the Strategy-Validation (Q2) and Analytics (Q4) quadrants + `deriveValidation`/
  `diversify` (moved to Research), leaving a clean engine/risk config consumed inside Workspace.
- **Cockpit** unchanged (Dashboard); **Strategy** unchanged (Strategy Center with health + timeline from iter27).
- Every page keeps its cyan "one question per page" line.
- Tested: testing_agent iter28 web frontend — all nav/pages/sub-tabs/owner flows green; backend unchanged (iter27).
  Lint clean. Non-blocking: a dev-console hydration warning on MonteCarloPanel; Emergent widget overlaps the
  rightmost tab hit-area at desktop width (JS clicks fine).


## 2026-07-08 (iter27) — Phase 1 "The Spine": OS-workflow framing + Strategy Center as the heart (web+backend, tested all-green)

Competition-focused UX transformation (web only; /app/mobile untouched). Turned Ananta's deep engine
into a coherent, guided AI-native trading OS narrative.

- **Strategy lifecycle gate wired into the live engine** (carried-over task): `trading_engine.load_strategy_states`
  + `strategy_entry_allowed`; a strategy set to DISABLED/ERROR (or toggled off) in the Strategy Center opens
  NO new entries — gated at all 3 executors (hunter primary BUY, squeeze, continuation). Open positions still
  managed by the exit engine. Hunter block emits reason `STRATEGY_DISABLED`. Unit tests: tests/test_strategy_gate.py (5).
- **Transparent Strategy Health Score** (`server._health_breakdown`): headline 0-100 = rounded mean of 6
  component scores (Win Rate, Risk-Adjusted, Recent Form, Consistency, Sample Confidence, Owner Rating). No
  "magic" number. Frontend radial gauge + component bars in StrategyCenter Overview (HealthCard).
- **Per-strategy Lifecycle Timeline** (`server._strategy_timeline`): Created → Last Optimized → Validation
  → First Paper Trade → Live → Latest Trade, derived from configs + validation gate + trade ledger. New
  Timeline tab + TimelinePanel in StrategyCenter.
- **"One question per page"** framing (AppShell.ContextInfo `page-question`): Cockpit "What is happening now?",
  Portfolio "How much am I making?", Strategies "What strategies do I own?", Logs "Why am I winning or losing?",
  Research Lab "Does my strategy actually work?".
- **Post-deployment test scenarios** for the user: /app/memory/POST_DEPLOYMENT_TESTS.md (3 e2e scenarios).
- Tested: testing_agent iter27 — backend 23/23 pytest (18 new HTTP in tests/test_iter27_spine.py + 5 gate unit),
  web frontend all UI spec items pass. All strategies reset to PAPER+enabled post-test. Lint clean.
- BACKLOG (agreed roadmap, not yet built): Phase 2 = interactive onboarding pipeline + Demo/Competition Workspace;
  Phase 3 = visual Research Lab wizard, AI Trading Coach (weekly review), Academy, clickable metric explainers,
  per-page AI assistant. Every AI surface must ship with a visible credits switch (user directive).


## 2026-07-08 (batch 2) — Strategy Architect: AI-designed strategies from the "+" (web, tested iter26 all-green)

The Strategy Center "+" is now the **Strategy Architect** — an AI quant strategist that interviews the
user in plain English and produces a deployable, schema-validated strategy, saved to Strategy Manager and
auto-registered in the Research Lab. Gated behind a **credits switch** per the user's request.

- **Backend** `architect.py` + `POST /api/strategy/architect/chat` (owner-gated, Claude via Emergent LLM key).
  Injects the REAL built-in ParameterSchemas into the system prompt so the model maps the goal to the
  best-fit family (hunter/squeeze/continuation) and emits ONLY valid params; server re-validates/clamps
  every design against the schema → always runnable. Returns `phase:"question"` (with quick_replies) or
  `phase:"design"` (strategy_key + params + a rich Strategy Card: category, risk, confidence, win-rate/PF/DD,
  strengths/weaknesses, per-param reasons). Validation (403/400/422) short-circuits BEFORE any LLM call.
- **Frontend** `pages/StrategyArchitect.jsx`: full-screen experience with an **AI Architect switch**
  (persists to localStorage) + a "burns LLM credits" warning when ON. AI ON → conversational interview →
  Strategy Card with Save-to-Strategy-Manager / Refine. AI OFF → zero-credit manual flow (Copy Existing /
  Import JSON; Git/Python/Pine/Marketplace shown as SOON). Save persists via `POST /api/strategy/configs`
  (origin=architect, card stored in new `meta` field on StrategyConfig) and appears instantly in the grid +
  Research Lab.
- **Contextual help** icon changed from "?" to a circled **info (i)** (enterprise style) + fade-and-scale
  animation. Applied across the parameter editor.
- `StrategyConfig` model gained a free-form `meta` dict (carries the Architect card + param reasons).

**Tested:** iter26 — backend 12/12, web 100%, zero extra LLM credits (manual + switch + help + regression
all no-credit; AI happy path verified once via screenshot ~22s). Backend tests:
`backend/tests/test_iter26_architect.py`. Web-only; mobile untouched.

**Note:** the Architect maps goals onto the existing built-in families (safe, deployable) rather than
generating/executing arbitrary new indicator code — true code-generating strategies (Python/Pine) still
require the deferred sandbox.


## 2026-07-08 — Strategy Center + Research Lab 2.0 · PHASE 1 (web, tested iter25 all-green)

Strategies are now first-class objects. New **"Strategies"** bottom-nav tab (nav is now 5 tabs).

- **Strategy Center** (`pages/StrategyCenter.jsx`): strategy cards **2-per-row** (Hunter / Volatility Squeeze /
  Continuation) with status badge, star rating, ROI / win-rate / health / trades — all real, from the new
  `GET /api/strategy/metrics` (derived from the closed-trade ledger + config ratings + state). Search box +
  status filter chips (LIVE/PAPER/DISABLED) + sort chips (Most Profitable / Highest Win Rate / Healthiest /
  Top Rated). An `+ Add Strategy` card opens a wizard.
- **Strategy Detail** page with tabs: **Overview** (How-it-works + Strategy DNA + Live Snapshot),
  **Parameters** (schema-driven editor filtered to that strategy, with contextual help), **Validation**
  (Monte Carlo + lab), **AI** (analyst scoped to the strategy via the new `strategy` field on `ai_query`),
  **Research**, **History**. Status selector persists via `PUT /api/strategy/{key}/state` (enum-validated;
  new `strategy_meta` collection).
- **Add Strategy wizard**: safe sources ENABLED — Copy Existing (clone a built-in as a tunable config
  variant) and Import JSON (validated). Git / Python / Pine / Marketplace / Built-in shown as disabled
  "SOON" — deliberately NOT built (executing uploaded code / external import needs security + arch design).
- **Contextual Help** (`components/lab/HelpHint.jsx`): minimalist (?) → non-blocking floating card,
  click-away close; wired onto every parameter label in the editor.
- **New logo** (`components/AnantaLogo.jsx`): scalable SVG emblem — ring + trident tines + sharp central
  "A" + upward chart arrow + constellation nodes; replaces the PNG in the header.

**Backend:** `GET /api/strategy/metrics`, `PUT /api/strategy/{key}/state`, `strategy` scope on
`POST /api/analytics/ai_query`. Tests: `backend/tests/test_iter25_strategy_center.py` (9/9). Regression
iter23+iter24 still green (18/18).

**DEFERRED (need product/security decisions before building):** sandboxed Python/Pine/Git/URL/ZIP strategy
import, community marketplace, full version-control (branch/merge/rollback/compare), per-strategy run-history
timeline with version tags, auto Research-Lab registration of imported strategies.


## 2026-07-07 (batch 2) — AI Quant Analyst + Saved Configs (dynamic schema editor) + Monte Carlo (web, tested)

Three backlog features shipped autonomously on top of the 2×2 cockpit.

### AI Quant Analyst (Q4 Analytics modal) — tested green (iter24)
- New `backend/ai_analyst.py` + `POST /api/analytics/ai_query` (owner-gated). Uses the Emergent LLM key
  with **claude-sonnet-4-6** via emergentintegrations. Grounded: assembles a compact snapshot of the real
  reasoning log + closed-trade ledger + aggregate win/PnL so answers are factual, not hallucinated.
  Multi-turn via `ai_analyst_messages` (session_id replay).
- Frontend `components/lab/AIAnalystTerminal.jsx`: chat terminal with suggested prompts, embedded above
  the Analytics panel. Verified: grounded answers + multi-turn context in-browser.

### Saved Configs + schema-driven editor (Q2 Validation modal) — tested green (iter24)
- Surfaces the versioned `strategy_configs` (created by the lab bridge or by hand). Grouped by strategy,
  with 1–5★ rating (persists), delete (builtin protected), and per-strategy "NEW".
- `components/lab/SavedConfigsPanel.jsx` renders a **dynamic parameter editor from the ParameterSchema**
  (Phase 2 goal: tuning = configuration, not code). Sparse-diff save (only non-default overrides), schema
  validation → 422 on out-of-range. New api methods: strategyConfigGet/Create/Update/Delete.

### Monte Carlo risk-of-ruin engine (Q2 Validation modal) — self-tested (curl + UI + 4 unit tests)
- New `backend/lab/monte_carlo.py` + `POST /api/lab/monte_carlo`. Bootstraps (resample-with-replacement)
  the realised per-trade P&L over N paths → risk-of-ruin %, prob-of-profit %, P5–P95 final-return band,
  max-drawdown distribution, 12-bin histogram, and a ROBUST/ACCEPTABLE/FRAGILE verdict. Source = live
  closed trades or a lab run. Pure numpy, credit-free, seeded/deterministic.
- Frontend `components/lab/MonteCarloPanel.jsx`: iterations + ruin-threshold controls, run button, stat
  cards, percentile band, histogram. The Q2 face **"Monte Carlo" tile now shows the real verdict** (was
  "Soon"), computed on mount via a lightweight 1500-path run.
- Regression: `backend/tests/test_monte_carlo.py` (4 passed).


## 2026-07-07 — Research Lab + Logs redesigned into 2×2 Executive Cockpit (web, DONE + tested iter23)

Reworked both the Research Lab (Settings.jsx) and Logs/Reports (Reports.jsx) pages from long vertical
accordion scrolls into a rigid **2×2 quadrant grid** (always 2 columns at every width, per user). Each
quadrant card shows REAL face-metrics on its face and opens a full-screen sub-page modal; face updates
the instant the modal dismisses (localized state store).

**New shared components:** `components/lab/QuadrantCard.jsx` (accent-themed card: icon, headline stats,
metric rows, CTA), `components/lab/LabModal.jsx` (full-screen sticky-header + scroll-body + optional
sticky footer), `components/lab/ExitEngineModal.jsx` (Q1).

**Research Lab quadrants:**
- Q1 Entry & Exit Engine (cyan) — face: Active Exit Engine (ATR/Fixed), trail multiplier, arm, stop.
  Modal: Step-1 strategy multi-select (Global/Hunter/Squeeze/Continuation) → Step-2 ATR trailing vs
  Fixed-% stop. **Save writes to LIVE settings** (profile_overrides per strategy + dynamic_trail_enabled
  + stop/arm/trail). Face flips instantly on save.
- Q2 Strategy Validation (violet) — face: Model Readiness % + Overfitting Risk + Walk-Forward/Monte
  Carlo(soon)/Sensitivity, DERIVED from the latest lab runs (real, defensive; "—/Soon" where no data).
  Modal: existing StrategyValidationPanel (incl. the Save-Winning-Config flow).
- Q3 Risk Monitor (amber) — face: Risk Status + max positions + daily-loss cap + min conf + max spread.
  Modal: Risk Thresholds sliders + Adaptive Sizing + KillSwitch + Manual Cycle + Exchange Credentials.
- Q4 Analytics Engine (green) — face: Portfolio Health + Diversification (Herfindahl index) + win/PF/
  expectancy/open-positions. Modal: AnalyticsPanel.
- **Emergency Stop** button top-right under the header toggles manual_kill_switch (moved out of a section).
- REMOVED per user: Exchange Friction, Operations (Mode & Symbols), Exit Cooldowns sections.

**Logs quadrants:** Q1 Strategy Distributions (StrategyLab/Funnel/RSI/Confidence), Q2 Diagnosis
(Winner/Breaker/Staged/Missed/Zone/Rejections), Q3 Why-No-Trade, Q4 AI Log (ReasoningTimeline). Header
keeps PDF / Refresh / Fresh-Start.

**Backend fix (blocker):** `SettingsUpdate` was missing `dynamic_trail_enabled` and `profile_overrides`,
so Q1 Save silently no-op'd. Added both fields → PUT /api/settings now persists them (verified via re-GET).

**Tested:** testing_agent iter23 — 10/10 backend GREEN, all quadrant/modal testIDs present, exit-engine
save→instant-face-update confirmed, no runtime crashes. No mobile changes (separate workspace).


## 2026-07-07 — Save Winning Config: Research Lab → Strategy Config engine (backend + web, DONE + tested)

Wired the last-session bridge endpoint (`POST /api/strategy/configs/from-lab-run`) into the web UI so an
optimized exit configuration from a Research Lab backtest can be saved into the `strategy_configs` layer.

**Prerequisite BUG FIX (blocker):** `lab/runner.py::_run_backtest` computed the 5-config `exit_comparison`
(A/B/C exit test) each run but **never included it in the returned result dict** — so `result.exit_comparison`
was always absent. This silently broke BOTH the PDF exit-comparison table AND the bridge endpoint (always 400).
Fixed by returning `"exit_comparison": exit_cmp`. Verified: fresh run now persists it (winner `fixed_4_3` for BTC 1h).

**Backend:**
- `runner.py`: persist `exit_comparison` in result; also store a lightweight top-level `exit_winner`
  hint `{symbol, timeframe, winner_key, winner_label}` on the run doc (via new `_first_exit_winner`) so the
  runs LIST endpoint (which strips heavy `result`) can offer one-click save without re-fetching.

**Web frontend (`StrategyValidationPanel.jsx`):**
- New `api.js` methods: `strategyRegistry`, `strategyConfigs`, `strategyConfigFromLabRun`.
- Run DETAIL now renders an **Exit-Config Comparison (A/B/C)** table per symbol (winner row highlighted with
  trophy) + a per-symbol **SAVE WINNING** button.
- Completed backtest run ROWS with an `exit_winner` hint show a compact **SAVE CONFIG** button.
- Both open a **SAVE WINNING CONFIG** dialog (winner summary + attach-to-strategy dropdown [Hunter/Squeeze/
  Continuation] + optional name) → calls the bridge → toast "CONFIG SAVED (N★)".

**Tested:** curl e2e (create run → DONE → `exit_comparison` present → bridge saves optimizer config, 2★) +
UI screenshots (row button, comparison table, dialog, successful save toast). Lint clean (JS + Py).
No mobile changes (mobile lives in the separate workspace; backend contract unchanged for it).


## 2026-07-06 — Platform Phase 1: Strategy Registry + Parameter Schema + Strategy Configs (backend, DONE + tested)

**Foundation for the AI-native platform vision** (see `ARCHITECTURE_PLATFORM.md`). Additive + non-breaking —
existing Hunter/Squeeze/Continuation logic + backtest engine untouched; this is a new configuration layer.

**New package `/app/backend/strategy/`:**
- `core.py`: `ParamSpec` (type/min/max/step/grid/options/group/visibility/depends_on/engine_backed),
  `StrategyDNA`, `StrategySchema`; `StrategyConfig` (tenant-aware, SPARSE overrides, `parent_config_id`
  inheritance, `strategy_version`, `origin`, `rating`+`validation_status` hooks for Phase 3); versioned
  REGISTRY (`key@version`); `validate_params`; `resolve_config` (defaults ← parent chain ← self, cycle-safe).
- `definitions.py`: built-in schemas + DNA for hunter@1.0.0 (22 params), squeeze@1.0.0 (12), continuation@1.0.0 (18).
  Param ids map to real `RiskSettings` fields (`engine_backed=True`) so Phase 2 can drive the engine 1:1.

**API (`/api/strategy/*`, tenant="owner"):** GET registry, GET {key}/schema, GET/POST/PUT/DELETE configs
(owner-gated writes; validates against schema; blocks deleting builtins or configs with children),
POST seed-defaults (idempotent builtin roots). Mongo collection `strategy_configs`.

**Verified:** `tests/test_strategy_foundation.py` (registry, validation ok/errors, enum, inheritance
resolution, cycle-safety) all pass. Live curl E2E: registry lists 3 strategies w/ DNA; seed created 3
builtins; parent→child inheritance resolved correctly (child inherits parent's rsi/target_profit, applies
own lot, schema default exit_method); validation rejects out-of-range + unknown params. Python lint clean.

**Platform:** backend only (this workspace = backend+web source of truth; sync to Workspace 2 via GitHub).
**Next (Phase 2):** Research Lab reads schemas / edits configs; AI Optimization Engine (grid search over
`grid`/ranges → rank by PF/Sharpe/DD/stability + overfitting/confidence scoring).

---


## 2026-07-06 — Logs/Reports rename, 3-group Datalogs layout, naming cleanup, accordion data-render fix (web)

**Requests (web frontend only):**
1. Header/nav rename: "DataLogs / Reports" → **"Logs / Reports"**; subtitle → **"Reasons, Reports, &
   Reasoning Analytics"** (rendered via `.label-tag`, 0.2em tracking); bottom-nav tab "Datalogs" → **"Logs"**.
2. Datalogs 3-group layout: stripped per-card category labels; added three static group headers
   **Research / Diagnostic / Log** (`.label-tag` tracking). Phase-B cards (Winning Trade Profile, RSI
   Distribution, Missed-Opportunity, Support-Zone) merged into **Diagnostic**. Strategy Research
   Laboratory **auto-expands** on load.
3. Research Lab naming cleanup: dropped "· LAYER 6" and "· LAYER 5b" from section labels.

**Files:** `AppShell.jsx` (title/subtitle/nav label), `pages/Reports.jsx` (3-group return, defaultOpen,
per-card labels removed), `pages/Settings.jsx` (LAYER labels), `components/CollapsibleSection.jsx`.

**CollapsibleSection fix (root-cause for "sections not drawing / stalling"):** rewrote to a React-
controlled `<details>` (`open` synced via `onToggle`, `defaultOpen` prop) that **mounts children only
when open**. This (a) makes charts measure a real width on expand (Recharts inside a collapsed
`display:none` details previously computed 0-width), and (b) stops the 20s data-polling re-render from
fighting the auto-expanded section. Single-open accordion preserved via shared `name`.

**"Not loading data" / Counterfactual Engine — diagnosed, NOT a code bug:** curl'd all `/api/research/*`
endpoints — they return HTTP 200 with valid structure but **empty data** because the paper book has only
~9 closed trades and forward-resolution windows (24h/72h/7d) haven't produced resolved counterfactuals
yet (`counterfactuals_resolved: {24h:0,72h:0,7d:0}`; RSI/zone/missed buckets all 0). Winner Profile
(which has data) renders correctly. Components show correct empty states; charts populate once data exists.

**Exit Configuration Panel (requested):** ALREADY EXISTS in `StrategyValidationPanel` (native / ATR /
Fixed toggle with ATR multiplier+period+trail params and Target-PnL $ profit/loss fields + live %
hints). No new build needed.

**Verified (preview, playwright DOM + screenshots + curl):** both tabs render; group headers present;
auto-expand + single-open confirmed; Winner Profile data table renders on expand; LAYER labels gone;
ESLint clean; no console errors. FRESH START / PDF / REFRESH buttons already share identical `rounded-md`.

---


## 2026-07-05 — Datalogs + Research Lab: in-place accordion sections (web) + 2 removals

**Request:** In the Datalogs and Research Lab tabs, every section should behave like Cockpit's
Position Tracker / Trade Life Cycle — collapsed by default, expanding IN PLACE (downward) on click,
no dialog/modal. Single-open (opening one closes the others). Also remove two Research Lab sections.

**User decisions:** single-open accordion; all sections collapsed by default; remove
"LAYER 5C · SYSTEMIC BREAKOUT · High-Velocity Override" and "HOUSEKEEPING · Clear Old Logs & Trade History".

**Implementation (web frontend only):**
- New `components/CollapsibleSection.jsx` — native `<details>`/`<summary>` accordion with a shared
  `name` per tab so only ONE section is open at a time (single-open, zero-JS). Header shows label +
  title + chevron (rotates via `group-open`), body expands downward. testIds: `<id>` on the details,
  `<id>-toggle` on the summary.
- `pages/Settings.jsx` (Research Lab): converted all sections (Strategy Validation, Manual Kill, Risk
  Monitor, Analytics, Risk Thresholds, Adaptive Sizing, Exits, Friction, Operations, Cooldowns, API
  Keys) to `CollapsibleSection` in a single-column stack (was a 2-col grid + always-open panels).
  Removed the Systemic Breakout + Housekeeping sections and the now-unused `clearHistory` handler and
  `SectionHeader` helper.
- `pages/Reports.jsx` (Datalogs): wrapped all 12 cards in `CollapsibleSection`; stripped each child's
  own outer `panel` class + duplicate big title (kept dynamic subtitles) to avoid double borders/titles.

**Verification (preview, playwright DOM assertions + screenshots):**
- Both tabs render; all sections collapsed by default (no `open` attr).
- Click expands in place; opening a second section auto-collapses the first (single-open confirmed:
  `risk-thresholds → None, exits → open`).
- `settings-breakout` and `settings-history` count = 0 (removed). No console errors. ESLint clean.
- Note: web only — user maintains mobile in a separate workspace.

---


## 2026-07-05 — Research Lab: automatic multi-config exit-engine comparison in PDF (P0, DONE + tested)

**Request:** Every validation should automatically replay the identical entry set under multiple exit
configs ($2.00/$1.50, $3.00/$2.25, $4.00/$3.00, $5.00/$4.00, ATR baseline) and generate a comparison
table (Profit factor, Win rate, Expectancy, Net return, Max drawdown) with a best-engine verdict.

**User decisions:** (1a) runs automatically on every backtest; (2) comparison runs on the run's active
timeframes — 1h by default, +15m/30m only when Compare Timeframes is on; (3) best engine ranked by
return-over-drawdown, percentage columns show `%` symbols in the PDF; (4) Expectancy = avg net P&L per
trade ($); (5) PDF/backend only — no mobile UI change (mobile downloads the same PDF).

**Implementation (backend only):**
- `lab/backtest.py`: added `expectancy_usd` + `entries` to `_summarize`; new thin `run_multi_exit()`
  wrapper + `EXIT_COMPARISON_CONFIGS` (5 presets). It calls `run_backtest()` per config — safe because
  PASS-1 entry scan is deterministic & exit-agnostic, so entries are provably identical across configs
  (no risky engine refactor). Returns per-config headline metrics + winner_key (return/drawdown).
- `lab/runner.py`: `LabWorker._run_backtest` now runs a 2nd process task per symbol×timeframe cell
  (`_run_multi_exit_one`, 900s budget) and stores results under `result.exit_comparison`. Progress total
  doubled to account for the extra pass.
- `lab/lab_report.py`: new `_exit_comparison_block` renders one table per symbol×timeframe with `%` on
  Win rate / Net return / Max DD, `$` expectancy, `★ best` row marker, and a "Best engine
  (return/drawdown)" verdict line. Appended after the multi-timeframe block for `kind=backtest`.

**Verification:**
- `tests/test_exit_comparison.py`: entries identical across fixed/atr/native (58/58/58; native shows 59
  trade rows only due to a partial-exit leg). Multi-exit returns 5 rows + winner.
- PDF built end-to-end and content-extracted: "EXIT ENGINE COMPARISON" table shows all 5 configs, `%`
  symbols on percentage columns, ★ best on the winner, and the verdict line. Lint (Python) clean.

**Mobile sync:** `/app/memory/MOBILE_LAUNCH_SYNC_PROMPT.md` — full launch-ready prompt for the separate
Expo workspace covering Account/Privacy overlay + Research Lab modular-exit parity + auto-comparison PDF
(table is server-generated, so mobile only triggers runs and downloads the PDF).

---


# Ananta.AI — CHANGELOG

## 2026-07-05 — Validation: selectable exit logic (Universal Engine vs Fixed $ Target) + full trade logs

- **Fixed $ Target exit (backtest):** `run_backtest(..., exit_method, target_profit, target_loss)` — when `fixed`, exits the full position at exact limit-style fills netting **+$target_profit / -$target_loss** after fees (loss checked first per bar); exit modules `FIXED_TP`/`FIXED_SL`. Verified: TP nets exactly +$5, SL exactly -$4.
- **Selectable in the UI:** RUN VALIDATION dialog (Tracks A/C) now has an **EXIT LOGIC** selector (Universal Engine | Fixed $ Target) with **collapsed-by-default** sub-options Target Profit ($) / Target Loss ($), defaults 5 & 4 (`exit-targets-toggle` expands them; inputs enabled only for Fixed).
- **Report states the exit method:** each completed run shows an exit badge (`Fixed $5/$4` / `Engine exit`), the detail view shows an "Exit method used: …" banner, and the PDF includes it in config + a per-symbol **Full trade log** table (timestamps, entry/exit prices, size, P&L, exit module). New `TradeLog` component with a "Show full trade log (N)" toggle.
- Backend: `LabRunCreate` + `create_run` persist `exit_method`/`target_profit`/`target_loss`; `_run_backtest` passes them through and adds run-level `exit_method_label`.
- Verified by testing agent (iteration_21): backend 4/4 pytest (`test_lab_exit_logic.py`) + frontend 9/9, all PASS.


## 2026-07-05 — WEB: Ananta logo button + Account/Privacy overlay (parity with mobile)

- The web Ananta logo (header, `AppShell.jsx` TopHeader) is now an interactive **button** (`ananta-logo-btn`) with hover (`hover:border-atlas-border hover:bg-atlas-panelHover`) + active (`active:scale-95`) states.
- Clicking it opens `AccountOverlay.jsx` (shadcn Dialog): Profile header (avatar + real email + auth-status badge), Login & Auth card (real email + masked password + JWT type), invite banner, Features + Settings placeholder sections ("Soon"), an in-app **privacy statement** (for App Store privacy info), and a real **Log out** (owner only). Only real data this sprint = email + auth status.
- Added `DialogDescription` for a11y. Verified by web testing agent (iteration_20, 11/11 PASS, both logged-out READ-ONLY and logged-in AUTHENTICATED states; password never leaked to DOM).
- Created `/app/memory/MOBILE_ACCOUNT_PROMPT.md`: compiled mobile-workspace prompt (background, privacy info, logo-button click + features, corrections, parity).


## 2026-07-05 — Mobile: Account overlay (App Store privacy workaround) + parity pack

- **New feature (mobile `/app/mobile`):** tapping the Ananta logo in the Cockpit header (now `Pressable`, testID `account-logo-btn`) opens an **Account overlay** modal route `app/account.tsx`, registered in `app/_layout.tsx` with `presentation:"modal"`. Mirrors the reference layout — **Profile header** (avatar initials + real email), a **Login Credentials** card (real email + masked password `••••••••` + "Secure token (JWT)"), an **invite banner**, a **Features** section (Exchange/Referrals/Offers/Earn/Tax — placeholders, "Soon" pills), a **Settings** section (Payment methods/Notifications/Security — placeholders), and a real **Log out** action. Only real login credentials populated this sprint (dynamic profile fields deferred). Built with theme tokens so it inherits the app theme. Verified by mobile testing agent (iteration_19, 10/10 PASS).
- **Mobile dependency/connection check:** deps installed (Expo SDK 54, expo-font present), Metro RUNNING, backend reachable via `EXPO_PUBLIC_BACKEND_URL` (`/health`, `/api/public/snapshot`, `/api/auth/login` all 200). Only gap = feature-coverage (new `/lab/*` endpoints), documented in the parity pack.
- **Created `/app/memory/MOBILE_PARITY_PACK.md`:** canonical web design tokens (matte-black/matte-silver, Chivo/IBM Plex/JetBrains Mono), full backend endpoint contract incl. new `POST /lab/runs` fields (`strategies[]`, `compare_timeframes`), and a ready-to-run prompt for the external mobile workspace.


## 2026-07-05 — HOTFIX: production crash-loop on MongoDB Atlas timeout

- **Symptom (production):** `pymongo NetworkTimeout` to Atlas + repeated `/health` `connection refused`/`upstream timed out` → total outage (no login, no data). K8s was crash-looping the backend container.
- **Root cause:** the FastAPI `@app.on_event("startup")` `await`ed several MongoDB calls (`load_settings`, `load_portfolio`, `seed_owner`, `create_index`). Uvicorn does not serve ANY request (incl. the `/health` probe) until startup returns — so when Atlas was slow/unreachable, startup hung (30s default server-selection × multiple ops), the probe failed, and the container was killed and restarted in a loop. The Mongo client also had **no timeouts** (30s default).
- **Fix (server.py):**
  1. Added fast client timeouts: `serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=20000` so a slow Atlas fails fast instead of hanging.
  2. Made startup **non-blocking**: `on_startup` now only schedules `_deferred_startup()` and returns immediately → "Application startup complete" fires instantly and `/health` serves (~1ms). `_deferred_startup` runs the DB bootstrap + background loops with a retry loop, so a transient Atlas outage degrades gracefully (app stays up, self-heals when Mongo returns) instead of crash-looping.
- Verified: `/health` returns 200 in ~1ms during boot; "startup complete" precedes "Deferred DB bootstrap complete"; login works once bootstrap finishes.
- NOTE: if the Atlas cluster itself remains unreachable that is a production infra issue (contact Emergent Support) — this fix prevents the *total crash-loop outage* and auto-recovers, but data requires Atlas to be reachable. **Requires redeploy.**


## 2026-07-05 — Research Lab: stuck-run/login fix, strategy+asset dropdowns, Datalogs caching

- **Root cause of "stuck at 11%" + login stalls (FIXED):** the CPU-bound backtest ran in a `ThreadPoolExecutor`, holding Python's GIL and starving the FastAPI event loop → other API calls (login/portfolio) stalled, and multi-asset × 15m/30m runs over long windows crawled for hours. Rewrote `LabWorker` to a **`ProcessPoolExecutor`** (compute in a separate process, event loop stays free) and orchestrate `backtest` runs cell-by-cell in the parent for accurate progress. Added a 300s per-backtest wall-clock budget + pool recycling so a run can never hang forever. Verified: login stays ~0.3s during a heavy 4-asset compare-ON run.
- **Backtest strategy filter:** `run_backtest(..., strategies=[...])` gates which of Hunter/Squeeze/Continuation are evaluated; `LabRunCreate` + `create_run` persist `strategies` and `compare_timeframes`.
- **15m/30m comparison now OPT-IN:** `compare_timeframes` defaults **off** → 1h-only (live-parity, ~3× faster). Checkbox in the RUN VALIDATION dialog turns on the multi-timeframe report.
- **Validation UI redesign (`StrategyValidationPanel.jsx`):** replaced the screen-filling asset chip grid with two compact Popover multi-select dropdowns — **Strategy** (with "Select all", default all three) and **Assets** (with "Select all") — plus the unchanged **Period** dropdown, in a 3-column config row. New `compare-tf-checkbox` (default off).
- **Datalogs instant load (`Reports.jsx`):** added a module-level `_reportsCache` so re-opening the tab renders instantly from cache with a silent background refresh (was re-fetching 10 endpoints with an empty gate on every visit).
- Verified end-to-end by testing agent (iteration_18): backend 7/7 pytest + full web UI flow, all PASS.


## 2026-07-04 — Deployment fix (/health probe) + Trade Life Cycle "Show N more"

- **Deployment blocker RESOLVED:** production deploy was failing because the K8s liveness/readiness probe hits top-level `GET /health` but the backend only exposed `/api/*` routes → 404 → container marked unhealthy (nginx `upstream timed out` / `connection refused`). Added a lightweight top-level `@app.get("/health")` in `server.py` returning `{"status":"ok"}` instantly (no DB/external calls). Verified 200 locally. `deployment_agent` re-scan → PASS.
- **.gitignore fix:** removed rules ignoring `backend/.env`, `frontend/.env`, `.env`, `.env.*` so required env files are committable for deployment (only `.env.local` / `.env.*.local` stay ignored).
- **Trade Life Cycle "Show N more" (Dashboard.jsx):** replaced the accordion drill-down with the Position Tracker pattern — only the first live trade's full lifecycle stepper renders; a `lifecycle-show-more` button ("Show N more trades" / "Show less") expands the rest. Verified via screenshot.


## 2026-07-04 — UI polish: duplicate headers, drill-downs, Research Lab caching

- **Duplicate header fix:** removed the in-page headers from `Reports.jsx` (Datalogs) and `Settings.jsx` (Research Lab) — the AppShell dynamic header is now the single source. Cockpit/Portfolio were already correct. (verified by testing agent iter 17)
- **Trade Life Cycle drill-down** (`Dashboard.jsx`): only the first open position renders its full lifecycle stepper; the rest are collapsed clickable rows (`lifecycle-toggle-<BASE>`) that expand on click.
- **Position Tracker drill-down**: shows 1 position by default + a `tracker-show-more` toggle ("Show N more positions" / "Show less").
- **Research Lab reload fix (caching):** module-level `_labCache` in `StrategyValidationPanel` (coverage/presets/runs/asset+period selection) and `_settingsCache` in `Settings.jsx` — re-opening the Research Lab tab now renders INSTANTLY from cache with a silent background refresh, instead of a full re-fetch/loading gate on every visit. Fixes coverage filter to `bars_1h`.
- Validation "QUEUE FAILED / stuck download": traced to a transient Cloudflare edge 502 (endpoints verified healthy in iter 16); the 30s client timeout prevents infinite hangs and the caching removes the redundant heavy re-fetches that made it feel stuck.


## 2026-07-04 — WS2 Hunter Continuation + WS3 Research Lab redesign

### WS2 — Hunter Continuation strategy (new independent executor)
Buys shallow pullbacks in an ESTABLISHED uptrend (distinct from Hunter reversals + Squeeze expansion).
- `continuation.py` `evaluate_continuation()` — gates: 50-EMA rising + 20-EMA>50-EMA + price above 50-EMA; controlled pullback (1–12%) from a recent swing high; price at the 20-EMA dynamic support; volume dry-up (recent 3-bar avg ≤ 0.9× prior 7-bar); healthy 40–62 RSI band (NOT the 30–35 reversal zone); anti-chase + turning-up candle. Structural stop below the pullback low / 50-EMA − 0.4×ATR.
- Routed via `router.py` — eligible in TREND_UP + NEUTRAL; added `continuation_allowed()`; ACTIVE_EXECUTORS now (hunter, squeeze, continuation).
- Wired LIVE (`trading_engine` — PAPER/DRY_RUN executor, fires when Hunter+Squeeze didn't take the symbol) and in the BACKTESTER (`lab/backtest.py`) for full parity. All thresholds in `RiskSettings` (`cont_*`).
- Tests: `tests/test_continuation.py` (6 cases) pass. Continuation now shows in backtest `strategy_breakdown`.

### WS3 — Research Lab validation redesign (Modes A/B/C + institutional metrics)
- **Modes:** A = Current Prod backtest, B = Parameter Opt (walk-forward sweep), **C = Presets** (new). `lab/presets.py` ships 4 named presets (conservative, aggressive, high_volatility, reversal_purist); `GET /api/lab/presets`; `POST /api/lab/runs` expands `preset` → `setting_overrides` and runs as a backtest.
- **Ranges:** 3/6/12-month (existing 3m/6m/1y) now backed by real 1h data.
- **Metrics:** added **Sharpe, Sortino, profit factor** (per-trade) + `strategy_breakdown` to backtest results; **auto-recommendation** verdict (DEPLOY-READY / PROMISING / TOO RISKY / UNDERPERFORMING / INSUFFICIENT SAMPLE) via `_recommend()`.
- **Multi-TF:** 15m/30m/1h comparison + best-TF verdict (from prior work) surfaced in PDF and UI.
- **Frontend** (`StrategyValidationPanel.jsx`): 3-mode chooser (track-current/fresh/presets), Mode C preset picker + description, coverage filter fixed to `bars_1h`, and an **expandable run-detail** per row that lazy-loads full metrics grid, strategy-breakdown chips, the 15m/30m/1h table, best-TF verdict and recommendation. `api.labPresets()` added.
- Verified end-to-end by the testing agent (web + backend, iteration 16): all 5 UI scenarios + 4 backend pytest cases pass; PDF builds with the new sections.


## 2026-07-04 — Lab PDF: multi-timeframe comparison (15m / 30m / 1h)

Backtest Lab reports now include a **MULTI-TIMEFRAME COMPARISON** section: the same window, settings and exit rules are replayed on **15m, 30m and the 1h live baseline**, per symbol, so the operator can see which candle size the edge favours (trades, return, win%, max DD, avg MFE/MAE).

- `lab/backtest.run_backtest(..., timeframe="1h")` — now timeframe-parametrized (loads that TF's candles; result tagged with `timeframe`).
- `lab/runner._run_job` (backtest kind): runs the 1h baseline + `COMPARE_TIMEFRAMES=["30m","15m"]` per symbol, storing headline metrics under `result["multi_timeframe"][symbol]["by_tf"][tf]` plus a `["verdict"]` (best timeframe by return-over-drawdown). Progress bar accounts for all TF runs.
- `lab/lab_report._multi_tf_block`: renders the per-symbol comparison table (15m/30m/1h) with a **"Best timeframe" verdict** headline underneath.
- Nightly `LabDataAppender` now refreshes `15m/30m` too.
- **Data:** backfilled **420 days of 15m (~40,320 bars) + 30m (~20,160 bars)** for all 10 assets via `scripts/backfill_tf.py`.
- Validated end-to-end: 90-day BTC/SOL multi-TF run + PDF build. Example insight — lower TFs trade more but showed lower win-rate/return on the sample window (exactly what the comparison surfaces). Lab runner/backtest/PDF tests pass.


## 2026-07-04 — Execution timeframe migration: 4h → 1h (all strategies + exits)

Per owner request, moved every execution + exit signal path from 4h to **1h candles**, with 1h-native parameters ("change things to suit 1h across all").

**Timeframe audit (before):** Hunter, Volatility Squeeze, Strategy Sandbox, Regime classifier, HTF trend filter, Exit engine, Backtester all ran on **4h**; S/R levels on daily+4h; sizing/breakout/entry-vol already on 1h.

**Changes (live + backtester in parity):**
- `trading_engine.evaluate_symbol`: now fetches `bars_1h` once (`EXEC_BARS_LIMIT=750`, ~31d) and feeds it to Hunter (`evaluate_primary`), `classify_regime`, `scan_strategies`, `evaluate_squeeze`, `fifty_pct_metric`, BTC regime/relative-strength, and the reason-chain snapshot. HTF trend filter now uses the **1h EMA50>EMA200** stack. Removed all `fetch_ohlcv_4h` calls + import.
- `position_watcher`: exit engine (Modules B/C/D/S) now fed **1h** bars.
- `levels.py`: intraday pivot leg switched 4h → **1h** (`DEFAULT_1H_LOOKBACK=720`), daily structural anchor retained.
- `lab/backtest.py`: replays **1h** candles (`ANALYSIS_LOOKBACK=750`, matches live); `lab/runner.resolve_window`, nightly appender, and `lab/optimize._usable_window` all keyed to 1h.
- `server.py /api/lab/data/coverage`: now reports `bars_1h`.

**Data:** backfilled **420 days of 1h** for all 10 assets (`scripts/backfill_1h.py`, via Binance US pagination — Kraken ignores `since`), ~10,080 bars/symbol.

**Note:** on 1h, EMA200 ≈ 8 days (vs 33 days on 4h) — the trend filter and all indicators are intentionally shorter-term/faster now. Indicator period counts unchanged (standard on 1h); WS1 gates react ~4× faster.

- Tests: 342 pass (lab/backtest fixtures reseeded to 1h; adaptive-sizing 4h mock removed). Real 90-day 1h backtest on BTC/USD: 22 trades, clean. Live cycle not run to preserve LLM credits. 15 remaining suite failures are PRE-EXISTING/unrelated (lot-size defaults, HTTP live-server, news-cascade LLM).


## 2026-07-04 — WS1 entry-side upgrades (Hunter) — LIVE + backtest parity

**`primary_layer.py` (`evaluate_primary`, the sole entry driver) — new gates (STABILIZED_REVERSAL):**
- **ATR-based demand zone:** entry band now = `[zone_low − 0.3×ATR, zone_high + 0.5×ATR]` (replaces flat %-proximity as the acceptance test). New code `REJECTED_OUTSIDE_ATR_ZONE`. Applied to AGGRESSIVE_PULLBACK too.
- **VCP stabilization base:** requires a 2–4 candle contracting base with a higher low (`vcp_contraction` + `vcp_higher_low`). New code `REJECTED_NO_VCP_BASE`.
- **Strict 30–35 RSI band:** RSI must be `>= rsi_reset_min (30)` AND `<= rsi_reset_max (35)`. Falling knives now rejected via `REJECTED_RSI_TOO_DEEP` (in addition to the existing `REJECTED_RSI_NOT_RESET` when hot).
- **Volume exhaustion ratio:** current 4H volume must be `<= 0.6×` the recent selling-climax (>=40% below), in addition to the negative volume slope.
- **Multi-timeframe trend filter:** 4h EMA50 > EMA200 now a HARD gate for reversals (`REJECTED_HTF_TREND_MISALIGNED`); fail-open when the signal is unknown (`None`). Wired into live (`trading_engine.evaluate_symbol`) and backtest (`lab/backtest.py`).

**`strategies.py` — Volatility Squeeze:** breakout now requires volume expansion `>= 1.5×` trailing avg (`SQUEEZE_VOL_EXPANSION_MIN`) to qualify.

**`models.py`:** all thresholds added to `RiskSettings` (`atr_zone_below_mult`, `atr_zone_above_mult`, `vcp_enabled/min/max_candles`, `vol_exhaustion_ratio_max`, `rsi_reset_min`, `squeeze_vol_expansion_min`) so the Research Lab can tune them.

- Tests: 73/73 pass across `test_layered_architecture` (6 new WS1 tests), `test_phase_e`, `test_backtest`, `test_lab_backtest`, `test_technical_first`. Backend-only change; no web/mobile UI impact.


## 2026-07-03 — WS1 exit-side trade management (LIVE) + Lab record delete

**Exit engine (`exit_engine.py`) — shared by live + backtester (parity preserved):**
- **R-based staged profit protection (Module F):** now locks stop to **breakeven at +1R** (Stage 1), then the existing **+1% floor at profit_arm_pct** (Stage 2); highest floor wins, upgrade-only. New `_risk_per_unit()` = entry − initial structural stop (falls back to %-stop).
- **ATR trail arms at +2R (Module C):** trailing stop now arms on EITHER +2R (`trail_arm_r`) OR the legacy %-arm, whichever comes first.
- **Structure-failure exit (new Module S, P5):** exits full when the higher-low structure breaks (fresh lower-low) AND momentum dies (RSI<50 + close below 20-EMA), guarded to protect gains/breakeven — "don't wait for the stop." Enabled by default.
- New `StrategyProfile` fields: `breakeven_r=1.0`, `trail_arm_r=2.0`, `structure_exit=True` (defaults apply to all strategies; live behavior updated per owner's go-live decision). Telemetry context extended.
- Tests: 17/17 exit-engine (incl. new breakeven-at-1R) + 6/6 backtest-parity pass.

**Research Lab — delete run record:**
- Backend `DELETE /api/lab/runs/{id}` (owner-gated) removes a single validation-run record.
- Frontend: a trash button at the right end of each **terminal (DONE/FAILED)** run record → optimistic remove + toast, so records can be cleared after download to save space.

*Pending (per agreed plan): WS1 entry-side (ATR S/R zones, VCP confirm, volume gate, MTF filter) → WS3 Research Lab validation redesign → WS2 Hunter Continuation strategy.*

## 2026-07-02 (d) — Cockpit density pass (web)

- **Side-by-side analytics slider**: Leaderboard & Analytics + Counterfactual Engine now sit in a horizontal snap-scroll slider (`analytics-slider`) — side-by-side on desktop, swipe-between on mobile. Touch events are isolated (stopPropagation) so sliding never triggers a tab change.
- **Consolidated diagnostics**: removed the AI Reasoning log from the Cockpit, and moved the **Confidence Distribution** chart to the Datalogs tab, placed beside the existing AI Reasoning Log (all model diagnostics in one tab). Counterfactual on Cockpit is now the correct-vs-missed pie only.
- **Merged Position Tracker**: dropped the separate collapsible "Today's Executions" block; the single Position Tracker now shows open positions + an always-visible EXECUTIONS table (Time/Symbol/Side/Price/Total/Net P&L/Exit, last 30, newest first) so no granularity is lost.
- Verified on mobile (414px); lint clean.

## 2026-07-02 (c) — Mobile layout bug-fixes (web)

- **Top header de-cluttered + hide-on-scroll**: fixed the clipped "Ananta" wordmark — owner login/logout is now icon-only on mobile (`hidden sm:inline` text) and the PDF button is slimmer, so brand + Paper/Live + Download + auth all fit. Header now uses native-feed physics (`useHideOnScroll`): slides up off-screen on scroll-down (verified top:-152), glides back on scroll-up. Bottom nav stays fixed.
- **Prominent active bottom tab**: active tab now shows a filled cyan pill behind a larger icon + cyan bold label + top accent bar (Zerodha/Instagram style); inactive tabs dimmed grey.
- **Analytics rollback**: removed the broken chevron/expand tiles — Leaderboard & Analytics, Counterfactual Engine, and AI Reasoning now render as **3 solid, always-visible panels** stacked in the Cockpit.
- **Portfolio**: renamed the "POSITIONS" tab → **"CLOSED TRADES"** (and its section header).
- Verified on mobile (414px): header hide/show, active-tab highlight, all 3 analytics panels present, lint clean.

## 2026-07-02 (b) — Bottom-nav + swipe navigation overhaul (web)

- **Bottom tab bar** (`AppShell.jsx`, `data-testid=bottom-nav`): moved the 4 main tabs (Cockpit · Portfolio · Datalogs · Research Lab) out of the top header into a fixed, thumb-reachable bottom bar with minimalist icon + label and an active cyan indicator. Removed the old top nav + hide-on-scroll floating nav.
- **Instagram-style swipe** (`swipe-container`): horizontal touch-swipe between tabs (dx>60px, horizontal-dominant) advances/retreats the active tab with an elastic slide animation (`page-enter-right/left` keyframes in `index.css`). Only the active page mounts (no height/perf issues). Tapping a bottom tab animates the same transition.
- **Dynamic context top header** (`context-header`): no longer switches tabs; adapts per active tab —
  - Cockpit → Account Value · Deployed · Daily P&L + Paper/Live switch
  - Portfolio → Invested · Current · Overall P&L (above the Holdings/Positions sub-tabs)
  - Datalogs / Research Lab → clean title + subtitle
- **De-dup:** removed the Cockpit in-page account hero (kept the bot-brain strip) and the Portfolio Invested/Current/P&L summary card — those metrics now live only in the dynamic header.
- Verified on mobile (430px) + desktop (1440px): bottom-nav tap, dynamic header swap, and simulated swipe all switch tabs correctly. Lint clean.
- Note: in preview, the platform "Made with Emergent" badge overlaps the 4th (Research Lab) bottom tab in the corner — cosmetic, preview-only, absent in the published build.

## 2026-07-02 (a) — UI polish + load-time optimization (web)

### ⚡ Performance (fresh-load latency)
- **Root cause:** `/market/snapshots` (~2.3s) and `/portfolio` (~1.4s) fetched live Kraken ticker+orderbook on every request (ccxt `enableRateLimit` serialized the calls). The SQLite `historical_candles.db` is NOT touched on page load.
- **Fix (backend):** added a warm in-memory snapshot cache refreshed by a background loop every ~5s (`_snapshot_warm_loop` in `server.py`); endpoints now serve from cache via `fetch_snapshots_cached()` (stale-tolerant, cold-load falls back to live). Result: `/portfolio` 1.37s→0.13s, `/market/snapshots` 2.28s→0.10s (~15–20×).
- SQLite already had `idx_candles_key(symbol,timeframe,ts)` — no change needed.
- **Fix (frontend):** new `context/AppDataContext.jsx` — single shared poller for portfolio/snapshots/settings/trades/reasoning; Cockpit + Portfolio consume it (removed duplicate per-page fetch loops). Template paints instantly, data streams in.

### 🎨 Global chrome
- **Sticky-smart nav (`AppShell.jsx`):** header + tabs now scroll away naturally on scroll-down; a floating nav bar (`data-testid=floating-nav`, testids `float-nav-tab-*`) slides down over content on any scroll-up, tucks away otherwise. In-flow nav keeps `nav-tab-*` testids.
- **Watchlist condense (`WatchlistControl.jsx` + Cockpit ribbon):** removed the "Watchlist 10/10 · in sync" text pill → green/red status dot next to VALIDATE/SYNC. Big asset-card row replaced by a single-line dropdown selector (`watchlist-select`) showing selected asset + price + 24h %.

### 🎨 Cockpit (`Dashboard.jsx`)
- Removed the mid-page "Open Positions Snapshot" and Footer "Today's Executions"; merged into one **Position Tracker** (`consolidated-positions`) pinned at the very bottom (open rows + collapsible today's executions).
- New **Trade Life Cycle** panel (`trade-lifecycle`) in that freed slot: one live progress line per open trade (Entered → In Profit → Trail Armed → Exit Watch) with a stop↔peak range bar.
- New **Analytics group** (`analytics-group`): three expandable preview tiles — Leaderboard & Analytics (pie + lens dropdown), Counterfactual Engine (pie + confidence distribution), AI Reasoning (regime + timeline). Tap to expand/collapse.

### 🎨 Datalogs (`Reports.jsx`)
- Removed the "Setup Funnel" block (component + render). WhyNoTrade now spans full width.

### 🎨 Research Lab (`Settings.jsx`)
- Removed the "Graduation Readiness ($300→Live) scorecard" and the entire "Vault Engine" config block (incl. its 4H trend filter switch).

### 🎨 Portfolio (`Portfolio.jsx`) — Zerodha-style rebuild
- Collapsed 3 tabs (Active/Open/Closed) → **2 tabs**: **HOLDINGS** (open positions) + **POSITIONS** (closed-trade history, retained with the TODAY/7D/30D/ALL window filters).
- HOLDINGS: Invested / Current / P&L summary card, per-holding rows (Qty·Avg / symbol / Invested / LTP / %), sticky "Today's P&L" footer.

### Verification
- Backend curl: both hot endpoints <200ms, HTTP 200.
- Screenshots: Cockpit, Portfolio, Datalogs, Research Lab, and floating-nav scroll behavior all confirmed rendering correctly.
- Lint (JS + Python) clean.
- Note: 6 failures in `tests/test_live_status_iter4.py` are PRE-EXISTING stale expectations (old "CryptoAtlas" name / $300 baseline) + auth-token setup in that file — not caused by these changes.

---

## 2026-07-09 — Final Mobile UI Polish (Competition Parity, iter 32)
Ported the last web polish items to the Expo mobile app; verified by mobile testing agent (all passed).
- **AI Coach headline banner** on mobile Cockpit (`app/(tabs)/index.tsx`, `coach-banner`): credit-free `GET /api/coach/headline`; tap → `/research?sub=ai`.
- **Strategy Health radial ring** (`src/components/HealthRing.tsx`) on strategy detail — SVG gauge (score + band label) replacing the plain number.
- **Mobile Metric Explainers** (`src/components/MetricExplainer.tsx`): tap-to-explain (i) modals for health / win_rate / roi, mirroring web bands.
- **Academy deep-link from a strategy** (`strategy-academy-link` → lesson modal); shared lesson data extracted to `src/academy.ts` (reused by Workspace Academy).
- **Regression fix:** Cockpit "See all positions" + PositionCard now route to `/trade` (previously the non-existent `/portfolio` route → dead link).
- Research tab now honours a `?sub=` deep-link param (validate|ai|closed).

### P1 Settings-architecture finding (investigation, no code change yet)
- Live engine source of truth = **`RiskSettings`** singleton (read by trading/exit/risk engines).
- `profile_overrides` is a **nested field inside RiskSettings** (Lab-promoted per-strategy exit overrides) — not a separate store.
- `strategy_configs` collection = Architect-authored, versioned, validated/rated per-strategy param bundles that are **NOT yet wired to the engine** (server.py:1651 "Engine wiring = Phase 2"). Awaiting a direction decision before rewiring the live core.

### P1 Settings Unification — Option A DONE (2026-07-09, backend-only)
- **Single clamp registry** `backend/settings_spec.py` (`FLOAT_CLAMPS`/`INT_CLAMPS`/`PROFILE_CLAMPS` + `clamp_value`/`clamp_profile_value`/`clamp_settings_dict`). Now the ONE definition of tunable RiskSettings fields + hard bounds.
- Refactored all three write-paths to use it: `PUT /api/settings` (update_settings), Lab promotion (`lab.proposals.apply_to_settings`), AI Coach apply (`coach.validate_apply`, advisory band + defense-in-depth hard clamp).
- Removed duplicate clamp tables (inline list in update_settings, `_SET_CLAMP`/`_PROF_CLAMP` + dead `_clamp` in proposals).
- Authoritative docs: `backend/CONFIG_ARCHITECTURE.md` (ownership map + promotion flow + Phase-2 migration path) and docstrings on `RiskSettings`, `load_settings`, and the strategy_configs section header.
- Guard test `tests/test_config_architecture.py` (11 pass): clamp registry ↔ real fields, clamp bounds, and engine modules never access the `strategy_configs` collection.
- Verified: PUT clamps out-of-range values (min_confidence 5→1.0, daily_loss 999→50); settings restored to defaults; lab proposals suite green. Backend-only, zero web/mobile impact.
- NOTE: 4 pre-existing `*_requires_owner` failures in `test_iter29_demo_coach.py` are a test-harness quirk (shared authenticated session) — auth gating verified correct via curl (403). Not a regression.

## 2026-07-09 — Phase-2: Strategy configs drive the engine + JSON import/export + leaderboard (iter 33, web+mobile+backend)
Turned the Strategy Architect into a real end-to-end loop (author → validate → **activate → drives live trading**), kept 100% compatible with the single-source-of-truth invariant.
- **Activate** `POST /api/strategy/configs/{id}/activate` (owner): resolves config (defaults←parent←self) → keeps only `engine_backed` params (`strategy.core.engine_backed_params`) → clamps via `settings_spec` → writes into the RiskSettings singleton; records `active_config_id`/`activated_at` on `strategy_meta`; returns `{applied, changes[]}`. Gated on `validation_status=='passed'` (400 otherwise). Engine STILL reads only RiskSettings — no engine changes.
- **Import (safe)** `POST /api/strategy/configs/import` (owner): strategy imported as STRUCTURED JSON, schema-validated (422 on unknown/out-of-range), `origin='imported'`. NO code execution (RCE-free by design).
- **Export** `GET /api/strategy/configs/{id}/export`: portable `{ananta_config:1, strategy_key, params, ...}` blob.
- **Leaderboard** `GET /api/analytics/leaderboard`: ranked (health, roi) aggregate; `/api/strategy/metrics` now surfaces `active_config_id`.
- **Web** (`SavedConfigsPanel.jsx`): Import (paste JSON) + per-config ACTIVATE (disabled until validated) + LIVE badge + Export-to-clipboard.
- **Mobile** (`app/strategy/[id].tsx`): CONFIGS card with Import modal + ACTIVATE (dimmed+guarded until validated) + LIVE badge — parity with web.
- Guard test `tests/test_config_architecture.py` extended (engine_backed_params filters forward-looking knobs); new `tests/test_iter33_configs_engine.py`. Testing agent: web+mobile+backend green (2 pytest `*_requires_owner` are the known shared-session artifact; auth verified 403 via curl).
- DEFERRED (consciously, to protect competition stability): the large `server.py` / `Dashboard.jsx` file-splitting refactor — high churn/regression risk mid-submission, low user-visible value. Leaderboard endpoint from item C delivered.

## 2026-07-09 — P1 Phase 1: Strategy Library + Filtering + Multi-metric Leaderboard + Active Watchlist (iter 34, web+mobile+backend)
Turned the Strategy Center into an "App Store for trading strategies" (catalog-first, Option A).
- **Strategy Library backend**: `library_seed.py` seeds 16 curated strategies (3 internal live-executable + 13 catalog: EMA Cross, Supertrend, Donchian, Turtle, MACD, RSI/Stochastic Momentum, Bollinger/VWAP MR, ATR/Keltner breakout, Pairs Trading, Time-Series Momentum) with rich JSON schema, seeded backtest results + AI summary/health/grade. Auto-seeds on startup.
  - `GET /api/library` (multi-select filters: market_regime/market_type/style/timeframe/risk/ai_grade/source + favorite/min_health/q + chips top_rated|top_internal|healthiest|trending + sort), `GET /api/library/{id}`, `GET /api/library/facets`, `POST /api/library/{id}/favorite`, `POST /api/library/{id}/ai-grade` (Claude via `library_ai.py`).
- **Multi-metric leaderboard**: `GET /api/analytics/leaderboard?sort=&source=` — 11 sort metrics (net_pnl/roi/win_rate/ai_health_score/sharpe/sortino/profit_factor/max_drawdown/avg_trade/trades/rating), ranks library overlaid with live metrics.
- **Active Watchlist** (Cockpit): renamed; `GET /api/watchlist/search`, `POST /api/watchlist/add` (validates tradable, adds to enabled_symbols → bot tracks + shows on Trade), `POST /api/watchlist/remove` (keeps >=1).
- **Web** (`StrategyCenter.jsx`): library grid + chips (Top Rated/Top Internal/Healthiest/Trending) + Filter drawer (multi-select) + StrategyLeaderboard sort dropdown + CatalogDetail (AI summary/perf/rules/favorite/re-grade). Cockpit `Watchlist` ribbon → "Active Watchlist" + add-asset search modal.
- **Mobile** parity (`app/(tabs)/strategy.tsx`, `app/library/[id].tsx`, `app/(tabs)/index.tsx`): chips + filter modal + leaderboard sort chips + catalog detail + Active Watchlist add modal.
- Testing agent iter 34: backend 34/34 pytest pass; web 100% (agent fixed a CatalogDetail `useEffect(load,[id])` → `useEffect(()=>{load();},[id])` Promise-cleanup crash); mobile 100% functional. Addressed nits: mobile `catalog-detail`/`add-asset-modal` testIDs, add-asset-option naming aligned to web, and `chip=top_internal` now filters to internal-only.
- NOT in this iteration: Phase 2 (mobile interactive YouTube-style paging, Parts 7-10) + Pine/Freqtrade converters (backlog).

## 2026-07-12 — Research persistence + Strategy chip cleanup (web)
- **Research Wizard persistence** (`components/lab/ResearchWizard.jsx` + new `lib/researchStore.js`): moved wizard state + polling loop into a Zustand store so an in-flight validation run (step/progress/result/mc) survives tab navigation / unmount. Added "New Run" (`wizard-new-run`) button in the running view. Setters handle both raw values and function-updater callbacks.
- **Strategy Center** (`pages/StrategyCenter.jsx`): removed the filter chips row (Top Rated / Top Internal / Healthiest / Trending) and the main "Filter" button per user request. Search-screen filter drawer retained. Cleaned up `chip` state + `CHIPS` const + unused `Flame` import.
- Testing agent iter 50 caught a setter regression (function-updater not handled) → fixed; iter 51 all green (web-only). NOTE: persistence is in-memory only; a hard page reload still resets the run (sessionStorage persistence is optional backlog).

## 2026-07-13 — Research/Trade/Header batch (web + partial mobile parity)
WEB (/app/frontend):
- Header: split Ananta logo (→ Account overlay) vs wordmark (→ Cockpit from anywhere). Page title on Strategy/Research/Workspace now acts as a HOME button (dispatches `ananta:tab-home`; each page resets to its home view).
- Research: `Start Research` now guides to Validate → Choose Strategies (step 0); if already on Validate with no strategies it toasts + device-vibrates. Added inline NEXT beside the Choose-Strategies list. Added EXIT STRATEGY tickboxes (ATR default, Fixed; both allowed → runs & reports each exit separately). Longer poll window (240×2s) fixes the prod bug where >2 strategies exceeded the old ~90s frontend timeout ("can't load data"). Inline DOWNLOAD PDF in the results view; toast points to Workspace.
- Trade: order form now has CANCEL ORDER beside the submit (one row). Toolbar PDF switched from trades-only (/report/trades.pdf) back to the full report (/report/full.pdf) = trades + analysis.
MOBILE (/app/mobile) parity:
- Research Validate: added EXIT STRATEGY segmented (ATR default / Fixed), haptic feedback on run, longer poll (200×2s), success alert.
- Trade: CANCEL ORDER button beside submit (resets the form).
NOTES:
- Counterfactual Engine "empty" on production is a data-maturity state (needs resolved counterfactuals over 24h/72h/7d), not a code bug — the panel renders correctly once data resolves.
- Parity gap: mobile Exit Strategy is single-select (web is multi-select tickboxes with "both"). Flagged for follow-up.
- Testing agent iter 52: web 8/8 + mobile 2/2 green.

## 2026-07-13 (b) — Mobile exit-strategy full parity
- Mobile Research Validate: replaced single-select exit Segmented with multi-select TICKBOXES (ATR default, Fixed; both allowed, min-1 guard). Runs one backtest per selected exit and renders a separate result block + exit tag per method — matches web. Testing agent iter 53 green (both + single + min-1 + Trade regression).
- Mobile Research "1 · STRATEGY" selector converted from overflowing Segmented to a wrapping, tappable chip grid (all 11 engines reachable).

## 2026-07-14 — Strategy split, AI Analysis redesign, health→account, network-toast fix (web + mobile)
WEB (/app/frontend):
- Strategy Center split into DEPLOYED (leaderboard + strategy cards) and EDIT (Import / Write / Describe&Build AI) sub-tabs.
- Research: NO strategy pre-selected by default; Start Research routes to Validate step 0 / prompts to pick.
- Research AI Analysis subtab redesigned → "Ask Ananta" (general, NOT Hunter-scoped) + "Weekly Review" + "Reports" (shared AnantaPdfs, extracted to components/AnantaPdfs.jsx). Fixed AI Quant Analyst scoping (was passing strategy=sel=hunter; now none → answers across all).
- Workspace › Engine & Risk: System Health section removed → moved into Account overlay (AccountOverlay.jsx now fetches riskStatus + environment).
- Network-error fix: lab-run poll GET marked {silent:true} in api.js (interceptor skips toast on silent); researchStore poll loop tolerates up to 15 consecutive transient failures instead of aborting — stops the "Network issue" toast spam during a research run (root cause of user's prod report).
MOBILE (/app/mobile) parity:
- Strategy tab: DEPLOYED / EDIT segmented; Edit tools open Add sheet.
- Research: no chip pre-selected; RUN guarded with Warning alert.
- Workspace SYSTEM card removed; Account screen shows System Health (Backend API / Trading Mode / Live Gate).
- Note: RN Alert.alert is a no-op on Expo WEB preview (works on native) — candidate for a toast wrapper later.
Testing agent iter 54: web 5/5 + mobile 3/3 green; Ask Ananta E2E LLM response verified.

## 2026-07-14 (b) — Edit-existing → Test this strategy flow (web + mobile)
- Strategy Center EDIT sub-tab: added a dropdown (web) / tappable list (mobile) of existing strategies. Selecting opens that strategy's editable detail page.
- Strategy detail page: added "TEST THIS STRATEGY" button at the bottom (below Analyse). Navigates into the Research Lab Validate flow (dataset → period → timeframe → exit) with the strategy pre-selected.
  - Web: research store strat=[sKey] + step=1, dispatch ananta:navigate→research, localStorage ananta_research_sub=validate.
  - Mobile: router param ?strat=<key> read by research Validate via useLocalSearchParams → pre-selects the chip.
- Testing agent iter 55: web 4/4 + mobile 3/3 green, cross-platform parity confirmed.

## 2026-07-14 (c) — AI Analysis tab cleanup (web)
- Removed the "AI Quant Analyst" header block inside Ask Ananta (kept the chat + input).
- Removed the "AI Trading Coach" card + AI/credits toggle + description entirely; Weekly Review now shows ONLY the "Generate Weekly Review" button (results still render on generate).
- Taglines: Ask Ananta → "About Trading/Strategy/Market"; Weekly Review → "What/How did you do this week?".

## 2026-07-15 — Support / Contact Us page (web)
- New public route /support (Support URL: https://spot-trading-lab.emergent.host/support) — no auth. Shows the support email vamsimadhavyakasiri@gmail.com (mailto + copy) and a message form that opens the user's mail client pre-filled to that address.
- Added "Contact Us" row in the Account overlay under SETTINGS (Privacy & Security group) → opens /support in a new tab.
- Delivery is mailto-based (no email keys). Server-side delivery via Resend can be added later if desired.

## 2026-07-15 (b) — Apple App Review demo account + first-time onboarding (mobile-first, Option A)
- Auth: added table-driven demo role. auth.py PRIVILEGED_ROLES={owner,demo}, seed_demo() (idempotent), authenticate() now verifies any privileged user in db.users. .env: DEMO_EMAIL=review@ananta.ai / DEMO_PASSWORD=AnantaDemo123!. /auth/login response now returns the ACTUAL authenticated email+role (was hardcoded owner). Clean seam for future multi-user.
- Backend: POST /api/onboarding/paper-setup (owner/demo) drives the existing paper engine — sets portfolio starting balance (virtual capital), position sizing (fixed USD lot or % of portfolio), enables selected strategies, mode=PAPER. Tests: /app/backend/tests/test_iter56_demo_onboarding.py.
- Mobile: rebuilt app/onboarding.tsx into the guided first-run flow: Welcome → Research First → Paper wizard (Capital → Allocation → Strategies [built-in + My Strategies + Create Strategy → /library/import, refetch on focus] → Summary → Start Paper Trading → dashboard). Skip-for-now supported. Completion persisted (storage 'ananta_onboarded'); Replay via Account › Guided Setup. zustand added to mobile (available; onboarding uses local state + Stack-preserved mount).
- Testing agent iter 56: backend 7/7 (after login-body fix), mobile 100%, web regression ok.
- Apple privacy Q: answer "Yes, we collect data" (Contact Info/email, User Content, User ID; App Functionality; NOT tracking, no ad SDKs).
- Emails: Option B (no automated approval emails yet; owner reviews waitlist in-app; support page → vamsimadhavyakasiri@gmail.com via mailto).
