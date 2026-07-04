# Ananta.AI — CHANGELOG

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
