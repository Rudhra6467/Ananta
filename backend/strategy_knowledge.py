"""Wave A Strategy Knowledge Objects — implementation is authoritative.

DNA / thesis may disagree with router + Wave A allow-list. Contradictions are first-class.
Do not invent evidence. historical_evidence / paper_evidence stay empty until Lab/paper fill them.
"""
from __future__ import annotations

from router import _REGIME_MAP

WAVE_A_KEYS = ("hunter", "squeeze", "bollinger-mr")

# Implementation-authoritative objects. DNA is labeled as thesis, not as live policy.
_WAVE_A: dict[str, dict] = {
    "hunter": {
        "strategy_id": "hunter",
        "version": "1.0.0",
        "name": "Hunter",
        "purpose": "Buy fear at structural support",
        "thesis": (
            "DNA: trending/recovering markets. "
            "Implementation: three profiles (STABILIZED_REVERSAL, AGGRESSIVE_PULLBACK, "
            "DEEP_DISCOUNT) in primary_layer.py. Live router: REVERSAL only."
        ),
        "implementation_files": ["primary_layer.py", "strategy/definitions.py", "router.py", "exit_engine.py"],
        "timeframe": "1h",
        "indicators": ["historical support zones", "RSI(14)", "volume slope / exhaustion", "ATR zone", "VCP", "HTF EMA50/200"],
        "parameters": {
            "rsi_reset_min": 30.0,
            "rsi_reset_max": 35.0,
            "vol_exhaustion_ratio_max": 0.6,
            "vcp_enabled": True,
            "htf_trend_enabled": True,
            "level_proximity_pct": 1.5,
            "normal_lot_usd": 75.0,
        },
        "entry_conditions": [
            "nearest support zone within proximity",
            "STABILIZED_REVERSAL: ATR zone + pullback (not chase) + volume exhaustion + RSI 30-35 + VCP + HTF",
            "AGGRESSIVE_PULLBACK: first touch in strong uptrend, not chase, ATR zone (router currently blocks TREND_UP)",
            "DEEP_DISCOUNT: panic + ≥2 bars acceptance in demand zone",
        ],
        "exit_conditions": [
            "Universal Exit Engine: structural fail, profit protection, ATR trail, time (~72h), EMA-loss",
        ],
        "stop_logic": "structural stop below support/pullback low − 0.4×ATR",
        "position_sizing": "normal_lot_usd (default $75) + max_concurrent_positions + spread kill",
        "thesis_regimes": ["TREND_UP", "REVERSAL"],
        "allowed_regimes": ["REVERSAL"],
        "blocked_regimes": ["TREND_UP", "TREND_DOWN", "COMPRESSION", "RANGE", "NEUTRAL"],
        "actual_router_gates": {
            "source": "router._REGIME_MAP",
            "eligible_when": [reg for reg, mods in _REGIME_MAP.items() if "hunter" in mods],
            "note": "Wave A enable() also sets allowed_regimes=['REVERSAL']",
        },
        "profiles": ["STABILIZED_REVERSAL", "AGGRESSIVE_PULLBACK", "DEEP_DISCOUNT"],
        "strengths": ["explicit support + volume + RSI gates", "does not chase vertical green"],
        "weaknesses": ["silent in TREND_UP despite AGGRESSIVE_PULLBACK existing", "few TAKEs in NEUTRAL/COMPRESSION books"],
        "failure_modes": ["TREND_UP setup found then REGIME_FILTERED", "DNA vs router contradiction"],
        "data_requirements": {"ohlcv": "1h", "warmup_bars": 200, "zones": "daily/1h levels"},
        "contradictions": [
            {
                "dna": "works_best = Trending / recovering markets",
                "implementation": "AGGRESSIVE_PULLBACK exists for strong uptrend",
                "router_and_wave_a": "REVERSAL only — TREND_UP blocked",
                "agent_must_say": (
                    "Hunter contains AGGRESSIVE_PULLBACK for strong uptrends, but the current "
                    "Wave A router blocks TREND_UP. That profile is not eligible for execution."
                ),
            }
        ],
        "authoritative_truth": "implementation + router + Wave A allow-list, not DNA",
    },
    "squeeze": {
        "strategy_id": "squeeze",
        "version": "1.0.0",
        "name": "Volatility Squeeze",
        "purpose": "Catch expansion out of compression",
        "thesis": "Coil (BB inside Keltner) then confirmed breakout; never the first breakout candle.",
        "implementation_files": ["squeeze.py", "router.py", "exit_engine.py"],
        "timeframe": "1h",
        "indicators": ["Bollinger 20", "Keltner 20×1.5", "volume vs 20-bar avg", "20-MA basis"],
        "parameters": {"bb_period": 20, "kc_mult": 1.5, "vol_spike": "above 20-bar average"},
        "entry_conditions": [
            "squeeze coiled recently (BB inside KC)",
            "closed breakout above BB upper with volume spike, not current candle",
            "then CONTINUATION (inside bar then break high) OR RETEST (pull to 20-MA then reclaim)",
            "price still above 20-MA stop",
        ],
        "exit_conditions": ["Universal Exit Engine; EMA-loss prioritized; no fixed time while trend intact"],
        "stop_logic": "20-MA / Keltner basis at signal",
        "position_sizing": "normal_lot_usd + book caps",
        "thesis_regimes": ["COMPRESSION"],
        "allowed_regimes": ["COMPRESSION"],
        "blocked_regimes": ["TREND_UP", "TREND_DOWN", "REVERSAL", "RANGE", "NEUTRAL"],
        "actual_router_gates": {
            "source": "router._REGIME_MAP",
            "eligible_when": [reg for reg, mods in _REGIME_MAP.items() if "squeeze" in mods],
        },
        "profiles": ["CONTINUATION", "RETEST"],
        "strengths": ["refuses first-candle chase", "explicit coil requirement"],
        "weaknesses": ["0% win in 2026-07-26 matrix window", "rare confirmed setups"],
        "failure_modes": ["coil without expansion", "breakout without retest/continuation"],
        "data_requirements": {"ohlcv": "1h", "warmup_bars": 200},
        "contradictions": [],
        "authoritative_truth": "implementation + router",
    },
    "bollinger-mr": {
        "strategy_id": "bollinger-mr",
        "version": "1.0.0",
        "name": "Bollinger Mean Reversion",
        "purpose": "Fade range extremes to the mean",
        "thesis": "DNA: range-bound. Spec: close < lower band, exit at mid. Router RANGE has no executor — Wave A policy adds RANGE+COMPRESSION as a shadow/declarative experiment.",
        "implementation_files": ["strategy/declarative_defs.py", "declarative_engine.py", "router.py"],
        "timeframe": "1h",
        "indicators": ["bb_lower", "bb_mid", "period 20", "std 2.0"],
        "parameters": {"bb_period": 20, "bb_std": 2.0},
        "entry_conditions": ["close < Bollinger lower band"],
        "exit_conditions": ["close >= Bollinger mid (spec); Wave A enable currently sets fixed $5 / $3.5"],
        "stop_logic": "declarative + account fixed stop when profile exit_method=fixed",
        "position_sizing": "normal_lot_usd + book caps",
        "thesis_regimes": ["RANGE"],
        "allowed_regimes": ["RANGE", "COMPRESSION"],
        "blocked_regimes": ["TREND_UP", "TREND_DOWN", "REVERSAL", "NEUTRAL"],
        "actual_router_gates": {
            "source": "router._REGIME_MAP",
            "eligible_when": [reg for reg, mods in _REGIME_MAP.items() if "bollinger-mr" in mods],
            "note": "Router RANGE=[] — bollinger is NOT a core router executor. Wave A cycle observations evaluate it as declarative/shadow.",
        },
        "profiles": ["declarative fade"],
        "strengths": ["simple, explicit band fade"],
        "weaknesses": ["walks the band in trends", "2026-07-26 matrix negative every regime"],
        "failure_modes": ["TREND_UP close below lower band is a fade into a trend"],
        "data_requirements": {"ohlcv": "1h", "warmup_bars": 200},
        "contradictions": [
            {
                "dna": "works_best = Range-bound low-trend markets",
                "matrix_2026_07_26": "allowed_regimes=[] — benched, negative every regime",
                "wave_a_policy": "allowed_regimes=['RANGE','COMPRESSION'] (re-test)",
                "router": "RANGE has no eligible executor",
                "agent_must_say": (
                    "Bollinger-MR is a Wave A re-test. Router does not list it as an executor. "
                    "Matrix 2026-07-26 benched it. Do not treat DNA or matrix as KEEP/CUT."
                ),
            }
        ],
        "authoritative_truth": "declarative spec + Wave A allow-list; router does not own this model",
    },
}


def knowledge_object(key: str, *, live_profile: dict | None = None,
                     historical_evidence: dict | None = None,
                     paper_evidence: dict | None = None) -> dict | None:
    base = _WAVE_A.get(key)
    if not base:
        return None
    out = dict(base)
    out["historical_evidence"] = historical_evidence or {
        "source": None,
        "available": False,
        "note": "Lab 1y not verified yet",
    }
    out["paper_evidence"] = paper_evidence or {
        "source": "PAPER",
        "available": False,
        "take_outcomes": 0,
        "note": "WAIT/SKIP process only until TAKE marks exist",
    }
    out["live_profile"] = live_profile or {}
    if live_profile:
        out["current_status"] = "enabled" if live_profile.get("enabled") else "disabled"
        if live_profile.get("allowed_regimes"):
            out["allowed_regimes"] = list(live_profile["allowed_regimes"])
    else:
        out["current_status"] = "unknown"
    out["evidence_confidence"] = "LOW"
    out["understanding_confidence"] = "HIGH"  # object is implementation-complete; Agent still PARTIAL until it consumes this
    out["decision_confidence"] = None  # per-opportunity, not strategy-level
    return out


def wave_a_knowledge(**kwargs) -> list[dict]:
    return [knowledge_object(k, **kwargs) for k in WAVE_A_KEYS if knowledge_object(k)]
