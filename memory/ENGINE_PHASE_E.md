# Ananta.AI — Engine Phase E: Regime-First Multi-Model Architecture

> Status: PLANNED (to start after Mobile Phase 1 ships). Captured from user briefs
> (2026-06). This is the backend trading-engine redesign. Mobile app is being built first.

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
