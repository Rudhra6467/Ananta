"""
Stage 4 — Historical Observation replay on Lab candles.

Same observation_v0 schema as live `lab watch`. Uses the REAL live functions:

  classify_regime          regime.py
  evaluate_primary         primary_layer.py   (Hunter)
  evaluate_squeeze         squeeze.py
  declarative bollinger-mr declarative_engine.py + DECLARATIVE spec
  evaluate_continuation    continuation.py    (UNIVERSE v1.2 research shadow — NOT Wave A, NOT live watch)

Evaluate-then-filter (live cycle observation contract), NOT backtest's
"only evaluate if router allows". That is required so we can count
qualifying setups that were REGIME_FILTERED.

Historical TAKE = TAKE-equivalent (setup AND policy gate).
Wave A TAKE-eq uses WAVE_A_REGIMES. Continuation TAKE-eq uses RESEARCH_REGIMES (TREND_UP).
Continuation MUST NOT change Wave A agent_decision, live watch, or KEEP.
It is NOT a paper fill, NOT KEEP, NOT a production mutation.

Independent Market Truth is computed from the same Lab candles at t0
(no look-ahead, Ananta regime is not used as proof). Forward +15m/+1h/+4h
come from subsequent candles (15m omitted when that series is absent).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone

from continuation import evaluate_continuation
from declarative_engine import evaluate as decl_evaluate
from lab.data_store import coverage_report, load_candles
from levels import compute_levels
from models import RiskSettings
from primary_layer import evaluate_primary
from regime import classify_regime
from router import hunter_allowed, squeeze_allowed, _REGIME_MAP
from setup_classifier import ema
from squeeze import evaluate_squeeze
from strategy.declarative_defs import DECLARATIVE

SCHEMA = "observation_v0"
SOURCE = "historical_lab"
WAVE_A = ("hunter", "squeeze", "bollinger-mr")
RESEARCH_SHADOW = ("continuation",)  # Universe v1.2 — hist observation only
WARMUP_BARS = 200
ANALYSIS_LOOKBACK = 750
HORIZONS_MS = {"+15m": 900_000, "+1h": 3_600_000, "+4h": 14_400_000}

# Wave A policy (Knowledge Object). Router may disagree — that contradiction is first-class.
WAVE_A_REGIMES = {
    "hunter": frozenset({"REVERSAL"}),
    "squeeze": frozenset({"COMPRESSION"}),
    "bollinger-mr": frozenset({"RANGE", "COMPRESSION"}),
}

# Research-shadow policy (not Wave A, not live enable). Mirrors router TREND_UP.
RESEARCH_REGIMES = {
    "continuation": frozenset({"TREND_UP"}),
}

_O, _H, _L, _C, _V = 1, 2, 3, 4, 5


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def _market_regime(closes: list[float]) -> str:
    """BTC structural label used live (trading_engine._market_regime): BULL / NEUTRAL / BEAR.

    Soft metric, logged not gating. Duplicated here so this worker does not import
    trading_engine (Mongo / async).
    """
    if len(closes) < 200:
        return "NEUTRAL"
    e50 = ema(closes, 50)[-1]
    e200 = ema(closes, 200)[-1]
    price = closes[-1]
    if price > e50 > e200:
        return "BULL"
    if price < e50 < e200:
        return "BEAR"
    return "NEUTRAL"


def _independent_flags(bars: list, i: int) -> dict:
    """Point-in-time flags from candles[:i+1]. Same formulas as Agent market_truth._ohlc_metrics."""
    window = bars[max(0, i + 1 - 720): i + 1]
    if len(window) < 5:
        return {}
    closes = [b[_C] for b in window]
    highs = [b[_H] for b in window]
    lows = [b[_L] for b in window]
    last = closes[-1]

    def ret(n: int):
        if len(closes) <= n or closes[-1 - n] == 0:
            return None
        return round((last / closes[-1 - n] - 1.0) * 100.0, 4)

    rets = []
    w = closes[-25:] if len(closes) >= 25 else closes
    for k in range(1, len(w)):
        if w[k - 1]:
            rets.append((w[k] / w[k - 1]) - 1.0)
    vol = None
    if len(rets) >= 5:
        mean = sum(rets) / len(rets)
        var = sum((x - mean) ** 2 for x in rets) / len(rets)
        vol = round((var ** 0.5) * 100.0, 4)

    sma_n = 20 if len(closes) >= 20 else max(5, len(closes) // 2)
    sma = sum(closes[-sma_n:]) / sma_n
    trend = "UP" if last > sma * 1.002 else ("DOWN" if last < sma * 0.998 else "FLAT")

    def span(hs, ls):
        return (max(hs) - min(ls)) / last * 100.0 if last else 0.0

    recent = span(highs[-6:], lows[-6:]) if len(highs) >= 6 else None
    longer = span(highs[-30:], lows[-30:]) if len(highs) >= 30 else None
    compression = None
    if recent is not None and longer and longer > 0:
        ratio = recent / longer
        compression = "COMPRESSION" if ratio < 0.45 else ("EXPANSION" if ratio > 0.9 else "NORMAL")

    return {
        "price": last,
        "ret_1h_pct": ret(1),
        "ret_4h_pct": ret(4),
        "ret_24h_pct": ret(24),
        "vol_proxy_1h_pct": vol,
        "trend_flag": trend,
        "compression_flag": compression,
        "sma_ref": round(sma, 4),
        "bars_used": len(closes),
    }


def _forward_close(bars: list, i: int, horizon_ms: int):
    target = int(bars[i][0]) + int(horizon_ms)
    for j in range(i + 1, len(bars)):
        if int(bars[j][0]) >= target:
            return float(bars[j][_C]), int(bars[j][0])
    return None, None


def _m15_close(m15: list, pointer: list[int], target_ts: int):
    """Advance a monotonic pointer; return (close, ts, new_pointer) of first bar >= target."""
    j = pointer[0]
    n = len(m15)
    while j < n and int(m15[j][0]) < target_ts:
        j += 1
    pointer[0] = j
    if j < n:
        return float(m15[j][_C]), int(m15[j][0])
    return None, None


def _outcome_cell(base: float, px, bar_ts: int | None, due_ms: int, method: str):
    if px is None:
        return None
    ret = round((float(px) / float(base) - 1.0) * 100.0, 4) if base else None
    return {
        "ts": _iso(bar_ts) if bar_ts else None,
        "price": float(px),
        "ret_pct": ret,
        "due_at": _iso(due_ms),
        "method": method,
    }


def _router_eligible(key: str, regime: str) -> bool:
    return key in (_REGIME_MAP.get(regime) or [])


def _wave_a_ok(key: str, regime: str) -> bool:
    return regime in WAVE_A_REGIMES.get(key, frozenset())


def _research_ok(key: str, regime: str) -> bool:
    return regime in RESEARCH_REGIMES.get(key, frozenset())


def _decision(setup, regime_ok: bool) -> tuple[str, str, str]:
    """Return (TAKE|SKIP|WAIT|UNKNOWN, skip_reason, execution_state)."""
    if setup is None:
        return "UNKNOWN", "DATA_GAP", "RUN_UNKNOWN"
    if setup and regime_ok:
        return "TAKE", None, "TAKE_EQUIVALENT"
    if setup and not regime_ok:
        return "SKIP", "REGIME_FILTERED", "RUN_REGIME_SKIPPED"
    return "WAIT", "no_qualifying_setup", "RUN_NO_SETUP"


def _empty_strategy_stats() -> dict:
    return {
        "bars": 0,
        "setups": 0,
        "take_equivalent": 0,
        "skip": 0,
        "wait": 0,
        "unknown": 0,
        "skip_regime_filtered": 0,
        "by_regime": {},
    }


def _bump(stats: dict, regime: str, decision: str, setup, skip_reason: str | None) -> None:
    stats["bars"] += 1
    if setup:
        stats["setups"] += 1
    if decision == "TAKE":
        stats["take_equivalent"] += 1
    elif decision == "SKIP":
        stats["skip"] += 1
        if skip_reason == "REGIME_FILTERED":
            stats["skip_regime_filtered"] += 1
    elif decision == "WAIT":
        stats["wait"] += 1
    else:
        stats["unknown"] += 1
    bucket = stats["by_regime"].setdefault(
        regime or "?",
        {"bars": 0, "setups": 0, "take_equivalent": 0, "skip": 0, "wait": 0, "unknown": 0},
    )
    bucket["bars"] += 1
    if setup:
        bucket["setups"] += 1
    key = {"TAKE": "take_equivalent", "SKIP": "skip", "WAIT": "wait"}.get(decision, "unknown")
    bucket[key] += 1


def replay(
    symbol: str = "BTC/USD",
    timeframe: str = "1h",
    start_ms: int | None = None,
    end_ms: int | None = None,
    stride: int = 4,
    include_observations: bool = True,
    max_bars: int | None = None,
) -> dict:
    """Replay Wave A observations on Lab candles. Pure compute. Never KEEP."""
    stride = max(1, int(stride or 1))
    settings = RiskSettings()
    cov = coverage_report(symbol, timeframe)
    bars = load_candles(symbol, timeframe, start_ms, end_ms)
    daily = load_candles(symbol, "1d")
    m15 = load_candles(symbol, "15m") if timeframe != "15m" else []
    btc_bars = bars if symbol == "BTC/USD" else load_candles("BTC/USD", timeframe, start_ms, end_ms)

    implementations = {
        "classify_regime": "regime.classify_regime",
        "hunter": "primary_layer.evaluate_primary",
        "squeeze": "squeeze.evaluate_squeeze",
        "bollinger_mr": "declarative_engine.evaluate(DECLARATIVE['bollinger-mr'])",
        "continuation": "continuation.evaluate_continuation (research shadow, not Wave A, not live watch)",
        "market_regime": "trading_engine._market_regime (EMA50/200, duplicated)",
        "independent_flags": "Agent market_truth._ohlc_metrics formulas on Lab candles",
        "note": "Not an Agent-side reimplementation. Not lab.backtest (that only logs TAKEs).",
    }

    if len(bars) < WARMUP_BARS + 5:
        return {
            "ok": False,
            "error": "insufficient_candles",
            "symbol": symbol,
            "have": len(bars),
            "need_warmup": WARMUP_BARS,
            "coverage": cov,
            "implementations": implementations,
            "observations": [],
            "summary": {},
        }

    bb_pack = DECLARATIVE.get("bollinger-mr") or {}
    bb_spec = bb_pack.get("spec") or {}
    bb_params = {p.id: p.default for p in (bb_pack.get("params") or [])}

    btc_by_ts = {int(b[0]): b for b in btc_bars} if btc_bars is not bars else None
    zone_cache: dict[int, list] = {}

    def zones_at(ts_ms: int, hwin: list) -> list:
        day = ts_ms // 86_400_000
        if day not in zone_cache:
            d_bars = [d for d in daily if d[0] <= ts_ms][-ANALYSIS_LOOKBACK:]
            zone_cache[day] = compute_levels(d_bars, hwin) if d_bars else []
        return zone_cache[day]

    stats = {k: _empty_strategy_stats() for k in WAVE_A + RESEARCH_SHADOW}
    decision_c = Counter()
    regime_c = Counter()
    market_c = Counter()
    fwd_by_decision = defaultdict(list)
    observations: list[dict] = []
    m15_ptr = [0]
    sampled = 0
    errors = 0

    start_idx = WARMUP_BARS
    if start_ms is not None:
        for i, b in enumerate(bars):
            if int(b[0]) >= int(start_ms) and i >= WARMUP_BARS:
                start_idx = i
                break

    last_idx = len(bars) - 1
    # Need +4h of future bars to complete +4h outcome; still emit partials near the tail.
    for i in range(start_idx, last_idx, stride):
        if max_bars is not None and sampled >= int(max_bars):
            break
        bar = bars[i]
        ts_ms = int(bar[0])
        px = float(bar[_C])
        window = bars[max(0, i + 1 - ANALYSIS_LOOKBACK): i + 1]
        try:
            asset_reg_obj = classify_regime(window)
            asset_reg = asset_reg_obj.regime
        except Exception:
            errors += 1
            continue

        if symbol == "BTC/USD":
            btc_closes = [b[_C] for b in window]
        else:
            btc_win = [btc_by_ts[int(b[0])] for b in window if btc_by_ts and int(b[0]) in btc_by_ts]
            btc_closes = [b[_C] for b in btc_win] if btc_win else [b[_C] for b in window]
        market_reg = _market_regime(btc_closes)
        regime_c[asset_reg] += 1
        market_c[market_reg] += 1

        htf = None
        if settings.htf_trend_enabled:
            wc = [b[_C] for b in window]
            if len(wc) >= 200:
                htf = wc[-1] > ema(wc, 50)[-1] > ema(wc, 200)[-1]
            else:
                htf = False

        # --- Hunter: evaluate then filter ---
        h_setup = None
        h_codes: list[str] = []
        h_profile = None
        try:
            zones = zones_at(ts_ms, window)
            sig = evaluate_primary(
                symbol, px, window, zones, settings,
                regime=asset_reg_obj, htf_trend_aligned=htf,
            )
            h_setup = bool(sig.triggered)
            h_codes = list(sig.reason_codes or [])[:8]
            h_profile = sig.entry_profile
        except Exception:
            h_setup = None
            h_codes = ["DATA_GAP"]
        h_reg = _wave_a_ok("hunter", asset_reg)
        h_dec, h_skip, h_state = _decision(h_setup, h_reg)

        # --- Squeeze: evaluate then filter ---
        sq_setup = None
        sq_reason = ""
        sq_profile = None
        try:
            sq = evaluate_squeeze(window, vol_expansion_min=getattr(settings, "squeeze_vol_expansion_min", None))
            sq_setup = bool(sq.triggered)
            sq_reason = str((sq.evidence or {}).get("reason") or "")[:200]
            sq_profile = sq.entry_profile
        except Exception:
            sq_setup = None
            sq_reason = "DATA_GAP"
        sq_reg = _wave_a_ok("squeeze", asset_reg)
        sq_dec, sq_skip, sq_state = _decision(sq_setup, sq_reg)

        # --- Bollinger-MR: declarative evaluate then Wave A filter (router RANGE=[]) ---
        bb_setup = None
        bb_reason = ""
        try:
            dsig = decl_evaluate(bb_spec, window, bb_params) if bb_spec else None
            if dsig is None:
                bb_setup = None
                bb_reason = "no_spec"
            else:
                bb_setup = bool(dsig.entry)
                bb_reason = str(dsig.reason or "")[:200]
        except Exception:
            bb_setup = None
            bb_reason = "DATA_GAP"
        bb_reg = _wave_a_ok("bollinger-mr", asset_reg)
        bb_dec, bb_skip, bb_state = _decision(bb_setup, bb_reg)

        # --- Continuation: research shadow. Evaluate-then-filter. NOT Wave A. NOT live watch. ---
        ct_setup = None
        ct_codes: list[str] = []
        ct_profile = None
        try:
            ct = evaluate_continuation(window, settings, regime=asset_reg_obj)
            ct_setup = bool(ct.triggered)
            ct_codes = list(ct.reason_codes or [])[:8]
            ct_profile = ct.entry_profile
        except Exception:
            ct_setup = None
            ct_codes = ["DATA_GAP"]
        ct_reg = _research_ok("continuation", asset_reg)
        ct_dec, ct_skip, ct_state = _decision(ct_setup, ct_reg)

        wave_obs = [
            {
                "strategy": "hunter",
                "symbol": symbol,
                "enabled": True,
                "ran": True,
                "regime": asset_reg,
                "setup_detected": h_setup,
                "decision": h_dec,
                "skip_reason": h_skip,
                "execution_state": h_state,
                "take_kind": "equivalent" if h_dec == "TAKE" else None,
                "router_eligible": _router_eligible("hunter", asset_reg),
                "wave_a_regime_ok": h_reg,
                "entry_profile": h_profile,
                "reason_codes": h_codes,
                "rationale": ",".join(h_codes) if h_codes else ("hunter setup" if h_setup else "no_qualifying_setup"),
            },
            {
                "strategy": "squeeze",
                "symbol": symbol,
                "enabled": True,
                "ran": True,
                "regime": asset_reg,
                "setup_detected": sq_setup,
                "decision": sq_dec,
                "skip_reason": sq_skip,
                "execution_state": sq_state,
                "take_kind": "equivalent" if sq_dec == "TAKE" else None,
                "router_eligible": _router_eligible("squeeze", asset_reg),
                "wave_a_regime_ok": sq_reg,
                "entry_profile": sq_profile,
                "rationale": sq_reason or ("squeeze setup" if sq_setup else "no_qualifying_setup"),
            },
            {
                "strategy": "bollinger-mr",
                "symbol": symbol,
                "enabled": True,
                "ran": True,
                "regime": asset_reg,
                "setup_detected": bb_setup,
                "decision": bb_dec,
                "skip_reason": bb_skip,
                "execution_state": bb_state,
                "take_kind": "equivalent" if bb_dec == "TAKE" else None,
                "router_eligible": _router_eligible("bollinger-mr", asset_reg),
                "wave_a_regime_ok": bb_reg,
                "entry_profile": "declarative",
                "rationale": bb_reason or "declarative bollinger-mr",
                "router_note": "Router RANGE=[] — Wave A re-test, not a core executor",
            },
        ]
        ct_obs = {
            "strategy": "continuation",
            "symbol": symbol,
            "enabled": False,
            "live_watch": False,
            "research_shadow": True,
            "ran": True,
            "regime": asset_reg,
            "setup_detected": ct_setup,
            "decision": ct_dec,
            "skip_reason": ct_skip,
            "execution_state": ct_state,
            "take_kind": "equivalent" if ct_dec == "TAKE" else None,
            "router_eligible": _router_eligible("continuation", asset_reg),
            "wave_a_regime_ok": False,
            "research_regime_ok": ct_reg,
            "entry_profile": ct_profile,
            "reason_codes": ct_codes,
            "rationale": ",".join(ct_codes) if ct_codes else ("continuation setup" if ct_setup else "no_qualifying_setup"),
            "note": "Universe v1.2 research shadow. Not Wave A. Not live watch. TAKE-eq ≠ KEEP.",
        }
        strat_obs = wave_obs + [ct_obs]

        n_take = sum(1 for o in wave_obs if o["decision"] == "TAKE")
        n_skip = sum(1 for o in wave_obs if o["decision"] == "SKIP")
        n_setup = sum(1 for o in wave_obs if o["setup_detected"])
        if n_take:
            agent_decision = "TAKE"
        elif n_setup and n_skip:
            agent_decision = "SKIP"
        elif n_setup:
            agent_decision = "SKIP"
        else:
            agent_decision = "WAIT"
        decision_c[agent_decision] += 1

        _bump(stats["hunter"], asset_reg, h_dec, h_setup, h_skip)
        _bump(stats["squeeze"], asset_reg, sq_dec, sq_setup, sq_skip)
        _bump(stats["bollinger-mr"], asset_reg, bb_dec, bb_setup, bb_skip)
        _bump(stats["continuation"], asset_reg, ct_dec, ct_setup, ct_skip)

        flags = _independent_flags(bars, i)
        btc_flags = flags if symbol == "BTC/USD" else _independent_flags(btc_bars, min(i, len(btc_bars) - 1)) if btc_bars else {}

        # Outcomes from subsequent Lab candles (independent of Ananta).
        cells = {}
        px15, ts15 = _m15_close(m15, m15_ptr, ts_ms + HORIZONS_MS["+15m"]) if m15 else (None, None)
        cells["+15m"] = _outcome_cell(px, px15, ts15, ts_ms + HORIZONS_MS["+15m"], "lab_15m") if m15 else None
        px1, ts1 = _forward_close(bars, i, HORIZONS_MS["+1h"])
        cells["+1h"] = _outcome_cell(px, px1, ts1, ts_ms + HORIZONS_MS["+1h"], "lab_1h")
        px4, ts4 = _forward_close(bars, i, HORIZONS_MS["+4h"])
        cells["+4h"] = _outcome_cell(px, px4, ts4, ts_ms + HORIZONS_MS["+4h"], "lab_1h")
        filled = sum(1 for k in ("+15m", "+1h", "+4h") if isinstance(cells.get(k), dict))
        if filled == 3:
            ot_status = "complete"
        elif filled:
            ot_status = "partial"
        else:
            ot_status = "pending"

        r1 = cells["+1h"]["ret_pct"] if isinstance(cells.get("+1h"), dict) else None
        if r1 is not None:
            fwd_by_decision[agent_decision].append(r1)

        ts_iso = _iso(ts_ms)
        obs_id = f"hist_{symbol.replace('/', '')}_{ts_ms}_{sampled}"
        record = {
            "schema": SCHEMA,
            "ts": ts_iso,
            "source": SOURCE,
            "obs_id": obs_id,
            "bar_ts_ms": ts_ms,
            "system_truth": {
                "obs_id": obs_id,
                "ts": ts_iso,
                "ananta_ok": True,
                "ananta_error": None,
                "cycle_id": f"hist_{symbol.replace('/', '')}_{ts_ms}",
                "ran_at": ts_iso,
                "agent_decision": agent_decision,
                "take_kind": "equivalent" if agent_decision == "TAKE" else None,
                "regimes_by_symbol": {
                    symbol: {"market": market_reg, "asset": asset_reg},
                },
                "strategy_observations": strat_obs,
                "n_symbols": 1,
                "n_setups": n_setup,
                "wave_a": list(WAVE_A),
                "research_shadow": list(RESEARCH_SHADOW),
                "note": (
                    "Ananta regime is a hypothesis. Wave A TAKE-eq uses WAVE_A gates. "
                    "Continuation is research shadow (TREND_UP), not Wave A, not live watch, not KEEP. "
                    "agent_decision is Wave A only."
                ),
            },
            "market_truth": {
                "source": "historical_candles",
                "ts": ts_iso,
                "ok": bool(flags),
                "error": None if flags else "insufficient_window",
                "btc": btc_flags or None,
                "eth": flags if symbol == "ETH/USD" else None,
                "assets": {symbol: flags} if flags else {},
                "breadth_1h_pct_positive": None,
                "notes": "Independent of Ananta regime. Point-in-time Lab candles, no look-ahead.",
            },
            "outcome_truth": {
                "schema": "outcome_v0",
                "method": "ohlc_close_at_or_after_horizon",
                "horizons_min": [15, 60, 240],
                "assets": {symbol: {"price_at_obs": px, **cells}},
                "status": ot_status,
                "note": "From subsequent Lab candles. BTC path ≠ strategy PnL. Not KEEP.",
            },
            "laws": {
                "ananta_regime_is_hypothesis": True,
                "ananta_output_not_proof": True,
                "historical_take_is_not_keep": True,
                "historical_take_is_not_paper_take": True,
                "continuation_is_not_wave_a": True,
                "continuation_is_not_live_watch": True,
                "strategy_evidence_ne_decision_evidence": True,
                "no_auto_mutation": True,
            },
        }
        if include_observations:
            observations.append(record)
        sampled += 1

    def _mean(xs):
        return round(sum(xs) / len(xs), 4) if xs else None

    summary = {
        "symbol": symbol,
        "timeframe": timeframe,
        "stride": stride,
        "warmup_bars": WARMUP_BARS,
        "lookback": ANALYSIS_LOOKBACK,
        "candles_loaded": len(bars),
        "bars_sampled": sampled,
        "errors": errors,
        "has_15m": bool(m15),
        "coverage": cov,
        "usable_1y": bool(cov.get("usable_1y")),
        "asset_regime_distribution": dict(regime_c),
        "market_regime_distribution": dict(market_c),
        "agent_decisions": dict(decision_c),
        "strategy_evidence": stats,
        "decision_evidence": {
            "note": "BTC/asset path after the Agent-style aggregate decision. Not strategy PnL.",
            "mean_fwd_1h_after_TAKE": _mean(fwd_by_decision.get("TAKE")),
            "mean_fwd_1h_after_SKIP": _mean(fwd_by_decision.get("SKIP")),
            "mean_fwd_1h_after_WAIT": _mean(fwd_by_decision.get("WAIT")),
            "n_fwd_1h": {k: len(v) for k, v in fwd_by_decision.items()},
        },
        "wave_a_gates": {k: sorted(v) for k, v in WAVE_A_REGIMES.items()},
        "research_shadow_gates": {k: sorted(v) for k, v in RESEARCH_REGIMES.items()},
        "router_map": {k: list(v) for k, v in _REGIME_MAP.items()},
        "contradictions": [
            "Hunter: AGGRESSIVE_PULLBACK exists for TREND_UP; Wave A + router allow REVERSAL only.",
            "Bollinger-MR: Wave A allow-list RANGE+COMPRESSION; router RANGE=[] (not a core executor).",
            "Continuation: router TREND_UP; hist research shadow only — not Wave A live watch.",
        ],
        "wave_a_status": {"hunter": "WATCH", "squeeze": "WATCH", "bollinger-mr": "WATCH"},
        "research_shadow_status": {"continuation": "HIST_ONLY"},
        "laws": {
            "historical_take_is_not_keep": True,
            "historical_take_is_not_paper_take": True,
            "enough_to_evaluate_ne_enough_to_promote": True,
            "no_auto_mutation": True,
            "continuation_is_not_wave_a": True,
            "continuation_is_not_live_watch": True,
        },
    }

    return {
        "ok": True,
        "schema": SCHEMA,
        "source": SOURCE,
        "symbol": symbol,
        "timeframe": timeframe,
        "implementations": implementations,
        "n_observations": len(observations) if include_observations else sampled,
        "summary": summary,
        "observations": observations if include_observations else [],
        "note": (
            "Stage 4 historical replay. Same observation_v0 as live_paper. "
            "Continuation is research shadow only. TAKE-equivalent cannot silently become KEEP. Wave A stays WATCH."
        ),
    }
