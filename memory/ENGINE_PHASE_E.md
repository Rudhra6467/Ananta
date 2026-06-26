# Ananta.AI — Engine Phase E: Regime-First Multi-Model Architecture

> Status: **E1 SHIPPED (2026-06-26)** — regime classifier, entry-quality scoring,
> regime-aware Hunter entry profiles, ATR-structural stops, and Squeeze as an
> INDEPENDENT active paper trader. Pure-compute, pytest-covered (tests/test_phase_e.py, 11 pass).
> E2 remaining (see bottom). Mobile Phase 1 shipped before this.

## North Star
Move from a **Hunter-first** engine (Hunter is the sole entry driver; other strategies
are shadow classifiers) to a **regime-first router** where each strategy is an
**independent alpha model** with its own personality, entry rules, stops and trailing.

Hunter and Squeeze must remain COMPLETELY INDEPENDENT — never merged.
- Hunter = "I buy fear" (reversals)
- Squeeze = "I buy expansion" (volatility breakouts)

## New control flow (per symbol, each cycle)
```
Market Scan → Regime Classifier → Strategy Router → Independent Trader(s)
```
Regimes: TREND / RANGE / COMPRESSION / REVERSAL (extensible).
Router maps regime → eligible models. Multiple models can hold positions across
different assets simultaneously.

## 1. Regime-aware Hunter — THREE entry profiles (not one)
Hunter should not always enter the same way; behavior adapts to market structure.

- **Profile 1 — Aggressive Pullback Entry** (use only in STRONG UPTREND)
  - Requires: bullish EMA stack, higher-highs + higher-lows, strong relative strength.
  - Entry: FIRST touch of the support zone (buyers step in fast in strong trends).

- **Profile 2 — Stabilized Reversal Entry** (use in TRANSITION markets)
  - Requires: support zone + RSI reset + dead volume + mini-VCP + higher-low + breakout.
  - This is the current Hunter logic. Enter only after demand proves itself.

- **Profile 3 — Deep Discount Entry** (after PANIC)
  - Requires: massive liquidation, RSI extremely oversold, ATR expansion, historical demand zone.
  - Wait for ACCEPTANCE (price spends time inside the demand zone), NOT just an RSI bounce.

## 2. ATR-structural adaptive stops (replace lowest-wick / fixed %)
- Stop = (lowest wick) − (0.3–0.5 × ATR), placed BEYOND structure.
- Rationale: crypto hunts obvious stops; ATR encodes noise so the stop self-adapts.
- DO NOT just widen stops because trades got stopped out — that converts small losses
  into large ones. If stopped out often, first ask "did we enter too early?" and fix entry.

## 3. Support/Resistance as DYNAMIC zones (Price ± ATR buffer), not precise prices.

## 4. Volatility Squeeze — improve ENTRY TIMING (not indicators)
First breakout candle has the highest false-break rate. Prefer one of:
- Compression → Breakout → **Retest** → Buy, OR
- Compression → huge breakout candle → small inside candle → **continuation** → Buy.
Promote Squeeze to ACTIVE paper trading ($75 lot), independent of Hunter.
Hard stop at 20-MA, dynamic ATR trail.

## 5. Entry Quality Score (biggest research enhancement)
Every strategy outputs a graded entry score — for RESEARCH, not filtering.
Example (Hunter): support strength /10, volume exhaustion /10, RSI reset /10,
zone quality /10, trend alignment /10, structure /10 → e.g. 43/50 → Grade A.
Grades: A+ / A / B / C. Persist on every simulated/executed entry so we can later ask:
- Do A-grade setups outperform B-grade?
- Does waiting for a retest improve returns?
- Are weak support zones worth trading?
Answers come from our own dataset, not assumptions.

## 6. Reason Chain schema (Phase 2.4 from handoff — fold in here)
For every simulated/executed entry log: `market_state_snapshot` (OHLCV matrix),
`indicator_values`, `strategy_id` & `entry_rule_triggered`, `confidence_score`,
`entry_quality_score` + grade, `regime`, `entry_profile`, `competing_hypothesis_log`.
Update PDF layout to emit the strict matrix format for sandbox strategies.

## Leadership priorities (user, verbatim intent)
1. Regime-aware entries (different Hunter behavior in strong trends vs reversals).
2. Support/resistance as dynamic zones, not precise prices.
3. Structural confirmation (absorption, higher-low, mini-VCP) before reversal entries.
4. ATR-based adaptive stops beyond structure, not arbitrary percentages.
5. Entry Quality Scoring on every trade to learn what works from real data.
> None of these add dozens of new indicators — they improve market-structure interpretation.

## Files to touch when Phase E starts
- `backend/strategies.py` (STRATEGY_DEFS modes, per-strategy scan + entry profiles, scoring)
- `backend/primary_layer.py` (Hunter entry-profile logic, dynamic zones, ATR stop)
- `backend/trading_engine.py` (regime classifier, router, independent execution paths, Reason Chain logging)
- `backend/models.py` (entry_quality_score, entry_profile, regime, reason_chain fields)
- `backend/pdf_report.py` (matrix layout for sandbox strategies)
- `backend/tests/` (regime classifier + entry-profile + scoring unit tests)

---

## E1 — SHIPPED 2026-06-26 (what's live now)
New modules (pure compute, zero LLM credits):
- `regime.py` — `classify_regime(bars_4h)` → TREND_UP/TREND_DOWN/RANGE/COMPRESSION/REVERSAL/NEUTRAL
  + flags `strong_uptrend`, `panic`, `compression`, structure (HH/HL, LH/LL), EMA stack.
- `entry_quality.py` — `score_hunter()` / `score_squeeze()` → 0-100 score + A+/A/B/C grade + component breakdown (research-only, never gates).
- `squeeze.py` — `evaluate_squeeze(bars_4h)` independent model: Bollinger-inside-Keltner coil →
  CONTINUATION (breakout → inside candle → break) or RETEST (breakout → pullback to 20-MA → reclaim).
  Never chases the first breakout candle. Hard stop = 20-MA.

Integration (`trading_engine.py`):
- Asset regime classified each cycle, passed to Hunter; logged in entry_attribution.
- Hunter (`primary_layer.evaluate_primary`) now regime-aware with 3 profiles:
  AGGRESSIVE_PULLBACK (strong uptrend, first touch), STABILIZED_REVERSAL (default 4-gate),
  DEEP_DISCOUNT (panic, requires acceptance inside demand zone).
- ATR-structural stop: structure low − 0.4×ATR (replaces fixed % buffer).
- **Squeeze promoted to EXECUTE** — independent paper trader, $75 lot, runs only when Hunter
  did NOT take the symbol; 20-MA hard stop via Position.structural_stop; ATR trail via watcher.
  PAPER/DRY_RUN only (LIVE intentionally excluded for safety).
- Entry-quality grade + entry_profile + regime persisted on Position & flow to closed TradeLog via entry_attribution.

`models.py`: Position/TradeLog gained `strategy`, `entry_profile`, `entry_quality_grade/score`, `regime_at_entry`.

Verified: 11/11 pytest, lint clean, backend boots clean, live manual cycles (BTC/SOL/ETH) run with no errors.
NOTE: Squeeze live-execution branch reuses the proven breakout PAPER executor; it had not yet fired in
preview (no confirmed coil-breakout present at build time) — will trigger on real setups.

## E2 — SHIPPED 2026-06-26
- **Regime router** (`router.py`): formal regime → eligible-models map + rationale; Squeeze gated off in
  TREND_DOWN; routing decision logged in the Reason Chain. (Hunter keeps its own gates.)
- **Full Reason Chain** on every cycle/entry (`entry_attribution.reason_chain`, schema v1):
  regime + evidence, routing, 12-bar OHLCV `market_state_snapshot`, `indicator_values`
  (rsi/adx/atr%/bbw%/ema-stack/rel-strength/btc-macro/volume-slope), `competing_hypotheses`
  (per-strategy detected/qualified), breaker_state. Flows onto Position → closed TradeLog.
- **Push event hooks** wired: `trade_opened` (Hunter maker fill + Squeeze fill), `stop_loss` (watcher SL_HIT),
  `trailing_stop` (watcher TRAIL_HIT) — best-effort, both PAPER & live exit paths. (Delivery still needs a build + google-services.json.)
- **Edge Discovery**: backend `GET /api/research/entry_quality` aggregates graded closed trades →
  grade / regime / profile distributions (count, win-rate, avg-return, net-pnl). Mobile Reports shows the
  grade win-rate breakdown with an accumulating empty-state.
- Hunter positions now stamped with strategy/entry_profile/grade/regime on maker fill.

Verified: 12/12 pytest, lint clean, backend boots clean, live manual cycles run with no errors,
endpoint returns, mobile Reports renders Edge Discovery + Squeeze ACTIVE.

## E3 — REMAINING (future)
- PDF matrix layout for sandbox strategies (strict OHLCV/indicator matrix output).
- Squeeze retest-depth tuning + competing_hypothesis_log richness once trades accumulate.
- Replace Hunter-first ordering with a true single-pass router loop (cosmetic; behavior already routed).
