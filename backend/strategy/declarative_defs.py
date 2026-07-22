"""
strategy/declarative_defs.py — Phase B: register the wireable catalog strategies as
first-class ENGINE strategies backed by the generic declarative executor.

Each entry below carries a tunable ParamSpec list (→ Research Lab form + per-strategy
configs) and a declarative `spec` (→ declarative_engine.evaluate). Importing this module
registers the schemas, so these strategies immediately appear in /strategy/registry,
/strategy/metrics, get strategy_meta lifecycle states and per-strategy configs — full
parity with the built-in hunter/squeeze/continuation.

Their `key` == the Strategy Library entry `id` (engine_key), so the library catalog links
1:1 to the runnable engine strategy. Adding another indicator strategy = add one dict here.
"""
from __future__ import annotations

from strategy.core import ParamGroup, ParamSpec, ParamType, StrategyDNA, StrategySchema, register, unregister

_T = ParamType
_G = ParamGroup


def _risk_params() -> list[ParamSpec]:
    # shared engine-backed knobs (Phase A overlay uses these for lot + structural stop)
    return [
        ParamSpec(id="normal_lot_usd", label="Position Size ($)", type=_T.FLOAT, default=75.0,
                  min=10.0, max=100000.0, step=5.0, group=_G.RISK, unit="$", engine_backed=True,
                  help="Flat USD notional per trade."),
        ParamSpec(id="stop_loss_pct", label="Stop Loss (%)", type=_T.PERCENT, default=8.0,
                  min=1.0, max=40.0, step=0.5, group=_G.RISK, unit="%", engine_backed=True,
                  help="Hard structural stop distance below entry."),
    ]


def _p(id, label, default, lo, hi, step=1.0, t=_T.INT, group=_G.ENTRY, unit=None, help=""):
    return ParamSpec(id=id, label=label, type=t, default=default, min=lo, max=hi, step=step,
                     group=group, unit=unit, help=help, engine_backed=False)


# key -> {name, description, dna, params, spec, library_id, default_enabled}
DECLARATIVE: dict[str, dict] = {
    "ema-cross": {
        "name": "EMA Cross", "library_id": "ema-cross", "default_enabled": True,
        "description": "Dual-EMA crossover: long when the fast EMA crosses above the slow EMA, flat when it crosses back below.",
        "dna": StrategyDNA(purpose="Ride clean trends via EMA crossover", works_best="Persistent, directional trends",
                           avoid="Sideways / whipsaw ranges", risk="Medium", holding="Hours-days",
                           preferred_coins=["BTC/USD", "ETH/USD"], confidence=63, tags=["trend", "ema", "crossover"]),
        "params": [_p("ema_fast", "Fast EMA", 12, 2, 100), _p("ema_slow", "Slow EMA", 26, 3, 300)],
        "spec": {
            "indicators": {"ema_fast": {"fn": "ema", "period": "$ema_fast"},
                           "ema_slow": {"fn": "ema", "period": "$ema_slow"}},
            "entry": [{"lhs": "ema_fast", "op": "cross_above", "rhs": "ema_slow"}],
            "exit": [{"lhs": "ema_fast", "op": "cross_below", "rhs": "ema_slow"}],
            "entry_reason": "Fast EMA crossed above slow EMA",
        },
    },
    "supertrend": {
        "name": "Supertrend", "library_id": "supertrend", "default_enabled": True,
        "description": "ATR-based trend filter: long on a bullish Supertrend flip, flat on a bearish flip.",
        "dna": StrategyDNA(purpose="Follow volatile trends with ATR flips", works_best="Volatile trends",
                           avoid="Low-volatility chop", risk="Medium", holding="Hours-days",
                           preferred_coins=["SOL/USD", "ETH/USD"], confidence=71, tags=["trend", "atr", "supertrend"]),
        "params": [_p("st_atr_period", "ATR Period", 10, 2, 50),
                   _p("st_multiplier", "ATR Multiplier", 3.0, 1.0, 10.0, step=0.1, t=_T.FLOAT)],
        "spec": {
            "indicators": {"st_dir": {"fn": "supertrend_dir", "atr_period": "$st_atr_period", "multiplier": "$st_multiplier"}},
            "entry": [{"lhs": "st_dir", "op": "cross_above", "rhs": 0}],
            "exit": [{"lhs": "st_dir", "op": "cross_below", "rhs": 0}],
            "entry_reason": "Supertrend flipped bullish",
        },
    },
    "rsi-momentum": {
        "name": "RSI Momentum", "library_id": "rsi-momentum", "default_enabled": True,
        "description": "Buys momentum strength: RSI crossing above the entry level while price holds above a rising trend EMA.",
        "dna": StrategyDNA(purpose="Ride momentum breakouts", works_best="Strong momentum phases",
                           avoid="Mean-reverting chop", risk="High", holding="Hours",
                           preferred_coins=["SOL/USD", "ETH/USD"], confidence=64, tags=["momentum", "rsi"]),
        "params": [_p("rsi_period", "RSI Period", 14, 2, 50), _p("rsi_entry", "Entry RSI", 60, 50, 90),
                   _p("rsi_exit", "Exit RSI", 50, 20, 70), _p("trend_ema", "Trend EMA", 50, 5, 200)],
        "spec": {
            "indicators": {"rsi": {"fn": "rsi", "period": "$rsi_period"},
                           "trend": {"fn": "ema", "period": "$trend_ema"}},
            "entry": [{"lhs": "rsi", "op": "cross_above", "rhs": "$rsi_entry"},
                      {"lhs": "close", "op": "gt", "rhs": "trend"}],
            "exit": [{"lhs": "rsi", "op": "lt", "rhs": "$rsi_exit"}],
            "entry_reason": "RSI momentum breakout above trend EMA",
        },
    },
    "macd-trend": {
        "name": "MACD Trend", "library_id": "macd-trend", "default_enabled": False,
        "description": "MACD line crossing above its signal while the MACD histogram is above zero (bullish regime).",
        "dna": StrategyDNA(purpose="Momentum confirmation via MACD", works_best="Momentum trends",
                           avoid="Flat low-momentum ranges", risk="Medium", holding="Hours-days",
                           preferred_coins=["BTC/USD", "ETH/USD"], confidence=61, tags=["momentum", "macd"]),
        "params": [_p("macd_fast", "MACD Fast", 12, 2, 100), _p("macd_slow", "MACD Slow", 26, 3, 200),
                   _p("macd_signal", "Signal", 9, 2, 50)],
        "spec": {
            "indicators": {"macd": {"fn": "macd_line", "fast": "$macd_fast", "slow": "$macd_slow"},
                           "sig": {"fn": "macd_signal", "fast": "$macd_fast", "slow": "$macd_slow", "signal": "$macd_signal"}},
            "entry": [{"lhs": "macd", "op": "cross_above", "rhs": "sig"}, {"lhs": "macd", "op": "gt", "rhs": 0}],
            "exit": [{"lhs": "macd", "op": "cross_below", "rhs": "sig"}],
            "entry_reason": "MACD crossed above signal in bullish regime",
        },
    },
    "bollinger-mr": {
        "name": "Bollinger Mean Reversion", "library_id": "bollinger-mr", "default_enabled": False,
        "description": "Fades extremes: buys a close below the lower band, exits back at the middle band.",
        "dna": StrategyDNA(purpose="Fade range extremes to the mean", works_best="Range-bound low-trend markets",
                           avoid="Strong trends (price walks the band)", risk="Low", holding="Hours",
                           preferred_coins=["BTC/USD"], confidence=72, tags=["mean-reversion", "bollinger"]),
        "params": [_p("bb_period", "BB Period", 20, 5, 100),
                   _p("bb_std", "Std Dev", 2.0, 1.0, 4.0, step=0.1, t=_T.FLOAT)],
        "spec": {
            "indicators": {"lower": {"fn": "bb_lower", "period": "$bb_period", "std": "$bb_std"},
                           "mid": {"fn": "bb_mid", "period": "$bb_period"}},
            "entry": [{"lhs": "close", "op": "lt", "rhs": "lower"}],
            "exit": [{"lhs": "close", "op": "gte", "rhs": "mid"}],
            "entry_reason": "Price closed below the lower Bollinger band",
        },
    },
    "donchian-breakout": {
        "name": "Donchian Breakout", "library_id": "donchian-breakout", "default_enabled": False,
        "description": "Channel breakout: long on a new N-period high, flat on a new M-period low.",
        "dna": StrategyDNA(purpose="Capture channel breakouts", works_best="Breakout / expansion regimes",
                           avoid="Range-bound markets", risk="High", holding="Days",
                           preferred_coins=["BTC/USD", "ETH/USD"], confidence=68, tags=["breakout", "donchian"]),
        "params": [_p("dc_entry", "Entry Channel", 20, 5, 100), _p("dc_exit", "Exit Channel", 10, 3, 60)],
        "spec": {
            "indicators": {"hi": {"fn": "donchian_high", "period": "$dc_entry"},
                           "lo": {"fn": "donchian_low", "period": "$dc_exit"}},
            "entry": [{"lhs": "close", "op": "gt", "rhs": "hi"}],
            "exit": [{"lhs": "close", "op": "lt", "rhs": "lo"}],
            "entry_reason": "Price broke above the Donchian channel high",
        },
    },
    "atr-breakout": {
        "name": "ATR Breakout", "library_id": "atr-breakout", "default_enabled": False,
        "description": "Volatility-expansion entry: price breaks above previous close + k×ATR.",
        "dna": StrategyDNA(purpose="Enter on volatility expansion", works_best="Volatility regime shifts",
                           avoid="Compressed quiet markets", risk="High", holding="Hours-days",
                           preferred_coins=["SOL/USD"], confidence=65, tags=["volatility", "breakout", "atr"]),
        "params": [_p("atr_period", "ATR Period", 14, 2, 50),
                   _p("atr_k", "ATR Multiple", 1.5, 0.5, 5.0, step=0.1, t=_T.FLOAT)],
        "spec": {
            "indicators": {"lvl": {"fn": "atr_breakout_level", "period": "$atr_period", "k": "$atr_k"}},
            "entry": [{"lhs": "close", "op": "gt", "rhs": "lvl"}],
            "exit": [],
            "entry_reason": "Price broke previous close + k×ATR",
        },
    },
    "keltner-breakout": {
        "name": "Keltner Breakout", "library_id": "keltner-breakout", "default_enabled": False,
        "description": "Buys a close above the upper Keltner band, exits back below the EMA basis.",
        "dna": StrategyDNA(purpose="Trend breakout via ATR envelope", works_best="Trending volatility",
                           avoid="Rangebound consolidation", risk="Medium", holding="Hours-days",
                           preferred_coins=["BTC/USD", "ETH/USD"], confidence=67, tags=["volatility", "keltner", "breakout"]),
        "params": [_p("kc_ema", "EMA Period", 20, 5, 100), _p("kc_atr", "ATR Period", 10, 2, 50),
                   _p("kc_mult", "ATR Mult", 2.0, 0.5, 5.0, step=0.1, t=_T.FLOAT)],
        "spec": {
            "indicators": {"up": {"fn": "keltner_upper", "ema_period": "$kc_ema", "atr_period": "$kc_atr", "mult": "$kc_mult"},
                           "mid": {"fn": "keltner_mid", "ema_period": "$kc_ema"}},
            "entry": [{"lhs": "close", "op": "cross_above", "rhs": "up"}],
            "exit": [{"lhs": "close", "op": "cross_below", "rhs": "mid"}],
            "entry_reason": "Price closed above the upper Keltner band",
        },
    },
    "turtle": {
        "name": "Turtle Trading", "library_id": "turtle", "default_enabled": False,
        "description": "Classic Turtle System 1: enter on a 20-period Donchian breakout, exit on a 10-period low.",
        "dna": StrategyDNA(purpose="Ride sustained macro trends via channel breakouts", works_best="Long, persistent trends",
                           avoid="Whipsaw / mean-reverting markets", risk="High", holding="Days",
                           preferred_coins=["BTC/USD", "ETH/USD"], confidence=66, tags=["trend", "breakout", "donchian", "turtle"]),
        "params": [_p("entry_channel", "Entry Channel (System 1)", 20, 5, 100),
                   _p("exit_channel", "Exit Channel", 10, 3, 60)],
        "spec": {
            "indicators": {"hi": {"fn": "donchian_high", "period": "$entry_channel"},
                           "lo": {"fn": "donchian_low", "period": "$exit_channel"}},
            "entry": [{"lhs": "close", "op": "gt", "rhs": "hi"}],
            "exit": [{"lhs": "close", "op": "lt", "rhs": "lo"}],
            "entry_reason": "Price broke above the 20-period Donchian high (Turtle System 1)",
        },
    },
    "time-series-momentum": {
        "name": "Time Series Momentum", "library_id": "time-series-momentum", "default_enabled": False,
        "description": "Absolute momentum: go long when the trailing N-bar return turns positive, flat when it turns negative.",
        "dna": StrategyDNA(purpose="Capture durable absolute-momentum trends", works_best="Persistent macro trends",
                           avoid="Sharp regime reversals", risk="Medium", holding="Days",
                           preferred_coins=["BTC/USD", "ETH/USD"], confidence=70, tags=["momentum", "trend", "academic"]),
        "params": [_p("mom_lookback", "Momentum Lookback (bars)", 30, 5, 200)],
        "spec": {
            "indicators": {"mom": {"fn": "roc", "period": "$mom_lookback"}},
            "entry": [{"lhs": "mom", "op": "cross_above", "rhs": 0}],
            "exit": [{"lhs": "mom", "op": "cross_below", "rhs": 0}],
            "entry_reason": "Trailing momentum turned positive",
        },
    },
    "stochastic-momentum": {
        "name": "Stochastic Momentum", "library_id": "stochastic-momentum", "default_enabled": False,
        "description": "Times momentum turns with a stochastic %K/%D crossover out of oversold territory.",
        "dna": StrategyDNA(purpose="Time momentum reversals via stochastic crossovers", works_best="Oscillating momentum markets",
                           avoid="Strong one-way trends (stays pinned)", risk="High", holding="Hours",
                           preferred_coins=["SOL/USD", "ETH/USD"], confidence=60, tags=["momentum", "stochastic", "oscillator"]),
        "params": [_p("k_period", "%K Period", 14, 3, 50), _p("d_period", "%D Period", 3, 1, 20),
                   _p("smooth", "Smoothing", 3, 1, 10), _p("stoch_oversold", "Oversold Level", 25, 5, 50)],
        "spec": {
            "indicators": {"stoch_k": {"fn": "stoch_k", "k_period": "$k_period", "d_period": "$d_period", "smooth": "$smooth"},
                           "stoch_d": {"fn": "stoch_d", "k_period": "$k_period", "d_period": "$d_period", "smooth": "$smooth"}},
            "entry": [{"lhs": "stoch_k", "op": "cross_above", "rhs": "stoch_d"},
                      {"lhs": "stoch_k", "op": "lt", "rhs": "$stoch_oversold"}],
            "exit": [{"lhs": "stoch_k", "op": "cross_below", "rhs": "stoch_d"}],
            "entry_reason": "Stochastic %K crossed above %D from oversold",
        },
    },
    "vwap-mr": {
        "name": "VWAP Mean Reversion", "library_id": "vwap-mr", "default_enabled": False,
        "description": "Fades stretched deviations below a rolling VWAP band back toward the volume-weighted mean.",
        "dna": StrategyDNA(purpose="Fade deviations from the volume-weighted mean", works_best="Liquid, balanced ranges",
                           avoid="Trend / news-driven days", risk="Medium", holding="Hours",
                           preferred_coins=["BTC/USD", "ETH/USD"], confidence=68, tags=["mean-reversion", "vwap"]),
        "params": [_p("vwap_period", "VWAP Period", 20, 5, 100),
                   _p("deviation_sigma", "Deviation σ", 2.0, 0.5, 4.0, step=0.1, t=_T.FLOAT)],
        "spec": {
            "indicators": {"vwap": {"fn": "vwap", "period": "$vwap_period"},
                           "vlow": {"fn": "vwap_lower", "period": "$vwap_period", "sigma": "$deviation_sigma"}},
            "entry": [{"lhs": "close", "op": "lt", "rhs": "vlow"}],
            "exit": [{"lhs": "close", "op": "gte", "rhs": "vwap"}],
            "entry_reason": "Price stretched below the lower VWAP band",
        },
    },
}

DECLARATIVE_KEYS = list(DECLARATIVE.keys())

# ---- runtime registry for IMPORTED declarative strategies (Import Pipeline P2) ----
# Approved imports that compile to the declarative engine are registered here so they gain
# full parity with catalog strategies (registry, metrics, configs, backtest, live loop).
_IMPORTED: dict[str, dict] = {}


def register_imported(key: str, name: str, description: str, spec: dict,
                      params: dict, dna: StrategyDNA | None = None) -> None:
    """Register (or replace) an imported declarative strategy at runtime.
    `params` is a flat {id: number} of the spec's tunables; each becomes a ParamSpec so the
    Research Lab form + per-strategy configs + resolve_full_params all work unchanged."""
    _IMPORTED[key] = {"name": name, "description": description, "spec": spec, "params": params}
    pspecs: list[ParamSpec] = []
    for pid, val in (params or {}).items():
        try:
            fval = float(val)
        except (TypeError, ValueError):
            continue
        is_int = float(fval).is_integer() and abs(fval) < 1000
        pspecs.append(ParamSpec(
            id=pid, label=pid.replace("_", " ").title(),
            type=_T.INT if is_int else _T.FLOAT, default=(int(fval) if is_int else fval),
            min=(0 if fval >= 0 else fval * 4), max=(max(fval * 4, 10) if fval >= 0 else 0),
            step=(1.0 if is_int else 0.1), group=_G.ENTRY, engine_backed=False,
            help="Imported strategy parameter."))
    register(StrategySchema(
        key=key, version="1.0.0", name=name, description=description,
        dna=dna or StrategyDNA(purpose=description or "Imported strategy", works_best="—", avoid="—",
                               risk="Moderate", holding="Hours-days", preferred_coins=["BTC/USD"],
                               confidence=55, tags=["imported"]),
        params=pspecs + _risk_params(),
    ))


def unregister_imported(key: str) -> None:
    _IMPORTED.pop(key, None)
    unregister(key)  # also drop the schema from the registry so it leaves /strategy/registry


def imported_keys() -> list[str]:
    return list(_IMPORTED.keys())


def all_declarative_keys() -> list[str]:
    return DECLARATIVE_KEYS + list(_IMPORTED.keys())


def imported_default_params(key: str) -> dict:
    d = _IMPORTED.get(key)
    return dict(d["params"]) if d else {}


def is_declarative(key: str) -> bool:
    return key in DECLARATIVE or key in _IMPORTED


def get_declarative_spec(key: str) -> dict | None:
    d = DECLARATIVE.get(key) or _IMPORTED.get(key)
    return d["spec"] if d else None


# register schemas on import
for _key, _d in DECLARATIVE.items():
    register(StrategySchema(
        key=_key, version="1.0.0", name=_d["name"], description=_d["description"],
        dna=_d["dna"], params=_d["params"] + _risk_params(),
    ))
