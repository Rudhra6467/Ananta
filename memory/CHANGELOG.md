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
