"""
Built-in strategy schemas + DNA (Phase 1). Importing this module registers the strategies.

Param ids map to real `RiskSettings` fields wherever `engine_backed=True`, so a resolved config
can drive the live/backtest engine 1:1 in Phase 2 without a rewrite. A few forward-looking knobs
(marked engine_backed=False) are declared now so the schema/marketplace/optimizer are destination-ready.
"""
from __future__ import annotations

from strategy.core import (
    ParamGroup,
    ParamSpec,
    ParamType,
    StrategyDNA,
    StrategySchema,
    Visibility,
    register,
)

_P = ParamGroup
_V = Visibility
_T = ParamType


# Shared exit knobs (the modular exit framework already in the Research Lab).
def _exit_params() -> list[ParamSpec]:
    return [
        ParamSpec(id="exit_method", label="Exit Method", type=_T.ENUM, default="fixed",
                  options=["native", "atr", "fixed"], group=_P.EXIT, visibility=_V.BEGINNER,
                  help="native = strategy's own Universal Exit Engine; atr = volatility trailing stop; "
                       "fixed = hard $ take-profit / stop.", engine_backed=False),
        ParamSpec(id="target_profit", label="Target PnL ($)", type=_T.FLOAT, default=5.0,
                  min=0.5, max=100.0, step=0.25, grid=[2.0, 3.0, 4.0, 5.0], group=_P.EXIT,
                  visibility=_V.BEGINNER, unit="$", help="Fixed-dollar take-profit.",
                  depends_on={"param": "exit_method", "equals": "fixed"}, engine_backed=False),
        ParamSpec(id="target_loss", label="Stop Loss ($)", type=_T.FLOAT, default=4.0,
                  min=0.5, max=100.0, step=0.25, grid=[1.5, 2.25, 3.0, 4.0], group=_P.EXIT,
                  visibility=_V.BEGINNER, unit="$", help="Fixed-dollar hard stop.",
                  depends_on={"param": "exit_method", "equals": "fixed"}, engine_backed=False),
        ParamSpec(id="atr_multiplier", label="ATR Multiplier", type=_T.FLOAT, default=2.5,
                  min=0.5, max=6.0, step=0.25, grid=[1.5, 2.0, 2.5, 3.0], group=_P.EXIT,
                  visibility=_V.INTERMEDIATE, help="Initial ATR stop distance.",
                  depends_on={"param": "exit_method", "equals": "atr"}, engine_backed=False),
        ParamSpec(id="stop_loss_pct", label="Stop Loss %", type=_T.PERCENT, default=10.0,
                  min=1.0, max=25.0, step=0.5, group=_P.EXIT, visibility=_V.INTERMEDIATE, unit="%",
                  help="Native hard stop as % below entry."),
        ParamSpec(id="trail_arm_pct", label="Trail Arm %", type=_T.PERCENT, default=5.0,
                  min=0.5, max=20.0, step=0.5, group=_P.EXIT, visibility=_V.PROFESSIONAL, unit="%",
                  help="Profit at which the trailing stop arms."),
        ParamSpec(id="trail_distance_pct", label="Trail Distance %", type=_T.PERCENT, default=3.0,
                  min=0.5, max=20.0, step=0.5, group=_P.EXIT, visibility=_V.PROFESSIONAL, unit="%",
                  help="Trailing stop leash once armed."),
    ]


def _risk_params() -> list[ParamSpec]:
    return [
        ParamSpec(id="normal_lot_usd", label="Lot Size ($)", type=_T.FLOAT, default=75.0,
                  min=10.0, max=5000.0, step=5.0, group=_P.RISK, visibility=_V.BEGINNER, unit="$",
                  help="USD deployed per trade."),
        ParamSpec(id="max_concurrent_positions", label="Max Open Positions", type=_T.INT, default=8,
                  min=1, max=30, step=1, group=_P.RISK, visibility=_V.INTERMEDIATE,
                  help="Cap on simultaneous open positions."),
        ParamSpec(id="max_spread_pct", label="Max Spread %", type=_T.PERCENT, default=0.5,
                  min=0.05, max=2.0, step=0.05, grid=[0.2, 0.4, 0.6], group=_P.FILTERS,
                  visibility=_V.PROFESSIONAL, unit="%", help="Reject entries when book spread exceeds this."),
    ]


# --------------------------------------------------------------------------- #
# HUNTER
# --------------------------------------------------------------------------- #
register(StrategySchema(
    key="hunter",
    version="1.0.0",
    name="Hunter",
    description="Buys clean historical support zones on a momentum reset (buy fear, not falling knives).",
    dna=StrategyDNA(
        purpose="Buy fear at structural support",
        works_best="Trending / recovering markets",
        avoid="Sideways chop, low-volume reversals",
        risk="Medium", holding="2-10 days",
        preferred_coins=["BTC/USD", "ETH/USD", "SOL/USD"], confidence=87,
        tags=["reversal", "support", "swing"],
    ),
    params=[
        ParamSpec(id="rsi_reset_min", label="RSI Band Min", type=_T.FLOAT, default=30.0,
                  min=10.0, max=50.0, step=1.0, grid=[25.0, 30.0, 35.0], group=_P.ENTRY,
                  visibility=_V.INTERMEDIATE, help="Lower bound of the healthy oversold band (avoid knives)."),
        ParamSpec(id="rsi_reset_max", label="RSI Band Max", type=_T.FLOAT, default=35.0,
                  min=20.0, max=60.0, step=1.0, grid=[35.0, 40.0], group=_P.ENTRY,
                  visibility=_V.INTERMEDIATE, help="Upper bound of the momentum-reset band."),
        ParamSpec(id="vol_exhaustion_ratio_max", label="Volume Exhaustion Ratio", type=_T.FLOAT,
                  default=0.6, min=0.2, max=1.0, step=0.05, grid=[0.5, 0.6, 0.7], group=_P.FILTERS,
                  visibility=_V.PROFESSIONAL, help="Entry volume must be ≤ this × the selling-climax volume."),
        ParamSpec(id="atr_zone_below_mult", label="Zone Width Below (ATR)", type=_T.FLOAT, default=0.3,
                  min=0.0, max=2.0, step=0.05, grid=[0.25, 0.5, 1.0], group=_P.ENTRY,
                  visibility=_V.PROFESSIONAL, unit="ATR", help="Entry band extends this ×ATR below the zone low."),
        ParamSpec(id="atr_zone_above_mult", label="Zone Width Above (ATR)", type=_T.FLOAT, default=0.5,
                  min=0.0, max=2.0, step=0.05, group=_P.ENTRY, visibility=_V.PROFESSIONAL, unit="ATR",
                  help="Entry band extends this ×ATR above the zone high."),
        ParamSpec(id="vcp_enabled", label="Require VCP Base", type=_T.BOOL, default=True,
                  group=_P.FILTERS, visibility=_V.PROFESSIONAL,
                  help="Require a volatility-contraction base before entry."),
        ParamSpec(id="level_proximity_pct", label="Zone Proximity %", type=_T.PERCENT, default=1.5,
                  min=0.25, max=5.0, step=0.25, group=_P.ENTRY, visibility=_V.PROFESSIONAL, unit="%",
                  help="How close to a support zone counts as testing it."),
        ParamSpec(id="level_min_touches", label="Min Zone Touches", type=_T.INT, default=2,
                  min=1, max=6, step=1, group=_P.FILTERS, visibility=_V.PROFESSIONAL,
                  help="A zone must be tested this many times to be tradable."),
        ParamSpec(id="pullback_max_green_body_pct", label="Max Entry Candle Body %", type=_T.PERCENT,
                  default=1.5, min=0.5, max=5.0, step=0.25, group=_P.FILTERS, visibility=_V.PROFESSIONAL,
                  unit="%", help="Anti-chase: reject if the entry candle's green body is larger than this."),
        ParamSpec(id="structural_stop_buffer_pct", label="Structural Stop Buffer %", type=_T.PERCENT,
                  default=2.0, min=0.5, max=8.0, step=0.25, group=_P.RISK, visibility=_V.INTERMEDIATE,
                  unit="%", help="Hard stop placed this % below the support zone low."),
        ParamSpec(id="htf_trend_enabled", label="HTF Trend Filter", type=_T.BOOL, default=True,
                  group=_P.FILTERS, visibility=_V.INTERMEDIATE,
                  help="Require Price > 4h EMA50 > 4h EMA200 for entries."),
        ParamSpec(id="time_exit_hours", label="Time Exit (hours)", type=_T.INT, default=0,
                  min=0, max=168, step=6, grid=[0, 24, 48], group=_P.TIME, visibility=_V.PROFESSIONAL,
                  unit="h", help="Force-close after N hours (0 = disabled). Forward-looking knob.",
                  engine_backed=False),
        *_risk_params(),
        *_exit_params(),
    ],
))


# --------------------------------------------------------------------------- #
# VOLATILITY SQUEEZE
# --------------------------------------------------------------------------- #
register(StrategySchema(
    key="squeeze",
    version="1.0.0",
    name="Volatility Squeeze",
    description="Enters as a compression phase ends and volume-backed expansion begins.",
    dna=StrategyDNA(
        purpose="Catch the expansion out of compression",
        works_best="Post-consolidation breakouts",
        avoid="Prolonged squeezes with no volume expansion",
        risk="Medium", holding="1-5 days",
        preferred_coins=["BTC/USD", "ETH/USD", "SOL/USD"], confidence=78,
        tags=["breakout", "compression", "volatility"],
    ),
    params=[
        ParamSpec(id="squeeze_vol_expansion_min", label="Breakout Volume Expansion", type=_T.FLOAT,
                  default=1.5, min=1.0, max=3.0, step=0.1, grid=[1.5, 1.8, 2.0], group=_P.ENTRY,
                  visibility=_V.INTERMEDIATE, help="Breakout volume must be ≥ this × trailing average."),
        ParamSpec(id="htf_trend_enabled", label="HTF Trend Filter", type=_T.BOOL, default=True,
                  group=_P.FILTERS, visibility=_V.INTERMEDIATE,
                  help="Require higher-timeframe trend alignment for entries."),
        *_risk_params(),
        *_exit_params(),
    ],
))


# --------------------------------------------------------------------------- #
# CONTINUATION
# --------------------------------------------------------------------------- #
register(StrategySchema(
    key="continuation",
    version="1.0.0",
    name="Continuation",
    description="Buys healthy pullbacks within an established uptrend (not structural reversals).",
    dna=StrategyDNA(
        purpose="Buy dips inside a confirmed uptrend",
        works_best="Strong, orderly trends",
        avoid="Deep pullbacks / trend breaks (falling knives)",
        risk="Medium", holding="2-8 days",
        preferred_coins=["BTC/USD", "ETH/USD", "SOL/USD"], confidence=80,
        tags=["trend", "pullback", "continuation"],
    ),
    params=[
        ParamSpec(id="cont_ema_fast", label="Fast EMA", type=_T.INT, default=20, min=5, max=100, step=1,
                  group=_P.ENTRY, visibility=_V.PROFESSIONAL, help="Fast EMA of the trend grid."),
        ParamSpec(id="cont_ema_slow", label="Slow EMA", type=_T.INT, default=50, min=20, max=200, step=1,
                  group=_P.ENTRY, visibility=_V.PROFESSIONAL, help="Slow EMA of the trend grid."),
        ParamSpec(id="cont_pullback_min_pct", label="Min Pullback %", type=_T.PERCENT, default=1.0,
                  min=0.25, max=10.0, step=0.25, group=_P.ENTRY, visibility=_V.INTERMEDIATE, unit="%",
                  help="Minimum dip from the recent swing high to qualify."),
        ParamSpec(id="cont_pullback_max_pct", label="Max Pullback %", type=_T.PERCENT, default=12.0,
                  min=2.0, max=30.0, step=0.5, group=_P.ENTRY, visibility=_V.INTERMEDIATE, unit="%",
                  help="Deeper than this is a reversal, not a continuation."),
        ParamSpec(id="cont_rsi_min", label="RSI Min", type=_T.FLOAT, default=40.0, min=20.0, max=60.0,
                  step=1.0, group=_P.FILTERS, visibility=_V.PROFESSIONAL,
                  help="Healthy-pullback RSI floor (NOT oversold reversal territory)."),
        ParamSpec(id="cont_rsi_max", label="RSI Max", type=_T.FLOAT, default=62.0, min=40.0, max=80.0,
                  step=1.0, group=_P.FILTERS, visibility=_V.PROFESSIONAL, help="Healthy-pullback RSI ceiling."),
        ParamSpec(id="cont_vol_dryup_ratio", label="Volume Dry-Up Ratio", type=_T.FLOAT, default=0.9,
                  min=0.4, max=1.2, step=0.05, group=_P.FILTERS, visibility=_V.PROFESSIONAL,
                  help="Recent 3-bar avg volume ≤ this × prior 7-bar avg (dry-up confirms a pullback)."),
        ParamSpec(id="cont_support_atr_mult", label="Support Distance (ATR)", type=_T.FLOAT, default=0.6,
                  min=0.1, max=2.0, step=0.05, group=_P.ENTRY, visibility=_V.PROFESSIONAL, unit="ATR",
                  help="Price must sit within this ×ATR of the dynamic EMA support."),
        *_risk_params(),
        *_exit_params(),
    ],
))
