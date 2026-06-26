"""
Pydantic models for CryptoAtlas AI Trading Dashboard.
All persisted documents use string ids (no MongoDB ObjectId) for JSON safety.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def compute_return_and_hold(entry_price, entry_ts, exit_price):
    """Helper for closed-trade reporting: (return_pct, hold_seconds)."""
    rp = ((exit_price - entry_price) / entry_price * 100.0) if entry_price and entry_price > 0 else None
    hs = None
    if entry_ts:
        try:
            hs = max(0.0, (datetime.now(UTC) - datetime.fromisoformat(entry_ts)).total_seconds())
        except Exception:
            hs = None
    return rp, hs



# ---------- AI Reasoning ----------
class AIReasoning(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=_new_id)
    timestamp: str = Field(default_factory=_utc_now_iso)
    symbol: str
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float  # 0..1
    reason: str
    news_summary: str
    model: str = "gemini-3.1-pro-preview"
    # snapshot of microstructure / risk evidence
    evidence: dict = Field(default_factory=dict)
    # final decision after fusion
    decision: Literal["BUY", "SELL", "HOLD", "BLOCKED"] = "HOLD"
    blocked_reasons: List[str] = Field(default_factory=list)


# ---------- Research Database (Phase 2: validation-first decision log) ----------
class ResearchLog(BaseModel):
    """Permanent, append-only diagnostic row for EVERY evaluation cycle, whether
    or not a trade occurs. Core schema + 4-tier confidence band + forward-looking
    Counterfactual P&L cells (resolved later by the ResearchResolverLoop)."""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=_new_id)
    timestamp: str = Field(default_factory=_utc_now_iso)
    symbol: str
    row_type: Literal["SETUP", "BACKGROUND"] = "SETUP"
    asset_class: str | None = None  # L1 / DEFI / METAL (sector testing)
    # --- core decision schema ---
    macro_confidence: float  # Gemini macro confidence 0..1
    macro_bias: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "NEUTRAL"
    news_sentiment: float | None = None  # separate numeric news score (not yet wired; Phase 2.5 input)
    news_source: str | None = None  # which feed/source produced the macro context
    decision: Literal["BUY", "SELL", "HOLD", "BLOCKED"] = "HOLD"
    absolute_decision: Literal["EXECUTE", "REJECT", "HOLD"] = "HOLD"
    confidence_tier: Literal["EXECUTE", "SHADOW", "LOG_ONLY", "IGNORE", "BACKGROUND"] = "IGNORE"
    blocked_reasons: List[str] = Field(default_factory=list)
    reason_codes: List[str] = Field(default_factory=list)  # Phase 2 rejection-leaderboard codes
    # --- context ---
    price: float  # decision-time price (anchor for counterfactual returns)
    setup_strength: str | None = None  # NONE / NORMAL / STRONG
    breakout: bool = False
    htf_trend_aligned: bool | None = None
    reasoning_id: str | None = None
    # --- Phase 2.x: first-class Hunter features + Circuit Breaker (SOFT metrics — logged, NOT gating) ---
    support_zone: float | None = None  # mid price of the support zone in play
    resistance_zone: float | None = None  # mid price of nearest overhead resistance
    rsi_4h: float | None = None
    volume_status: str | None = None  # EXHAUSTED / RISING
    market_regime: str | None = None  # BULL / NEUTRAL / BEAR (BTC structural)
    breaker_state: Literal["PASS", "CAUTION", "VETO"] = "PASS"
    relative_strength_btc: float | None = None  # asset return − BTC return (%) over window
    rr_estimate: float | None = None  # reward(to resistance) / risk(to structural stop)
    sector_data: dict = Field(default_factory=dict)  # snapshot of DefiLlama/FRED grounding used this cycle
    # --- Phase B research: 50% Rule / Fair-Value midpoint (DIAGNOSTIC ONLY — never gates) ---
    swing_low: float | None = None
    swing_high: float | None = None
    midpoint_50: float | None = None
    distance_from_midpoint_pct: float | None = None  # (price - midpoint)/midpoint * 100
    above_or_below_midpoint: str | None = None  # ABOVE (premium) / BELOW (discount)
    strategy_signals: dict = Field(default_factory=dict)  # Phase B sandbox: per-strategy {active, evidence}
    # --- counterfactual forward returns (%, resolved asynchronously) ---
    cf_ret_24h: float | None = None
    cf_ret_72h: float | None = None
    cf_ret_7d: float | None = None
    cf_resolved_24h: bool = False
    cf_resolved_72h: bool = False
    cf_resolved_7d: bool = False


# ---------- Trade Log ----------
class TradeLog(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=_new_id)
    timestamp: str = Field(default_factory=_utc_now_iso)
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float
    price: float
    notional: float  # quantity * price
    mode: Literal["PAPER", "DRY_RUN", "LIVE"] = "PAPER"
    confidence: float
    reasoning_id: str | None = None
    pnl: float = 0.0  # realized P&L for SELL (net of fees)
    fee_usd: float = 0.0  # exchange/taker fee charged on this leg
    status: Literal["FILLED", "REJECTED"] = "FILLED"
    note: str = ""
    exit_reason: str | None = None  # SL_HIT / TRAIL_HIT / MACRO_BEARISH
    # --- analytics / research layer (Phase A) ---
    sector: str | None = None  # asset sector taxonomy at trade time
    atr_at_entry: float | None = None  # ATR(14) snapshot at entry (carried onto the exit leg)
    atr_percentile_at_entry: float | None = None  # 0..100 percentile vs trailing ATR window
    volatility_regime: str | None = None  # LOW_COMPRESSION / NORMAL / HIGH_PANIC / UNKNOWN
    entry_extension_pct: float | None = None  # how far above 4h EMA50 price was at entry (chase-risk)
    slippage_usd: float = 0.0  # realized execution slippage (Phase B populates on exits)
    # --- Phase B research attribution (carried onto the SELL leg from the Position) ---
    trade_result: str | None = None  # WIN / LOSS / BREAKEVEN
    mfe_pct: float | None = None  # max favorable excursion % over the trade's life
    mae_pct: float | None = None  # max adverse excursion % over the trade's life
    # --- closed-position reporting (carried onto the SELL leg from the Position) ---
    entry_price: float | None = None  # avg entry price of the closed position
    entry_timestamp: str | None = None  # when the position was opened
    return_pct: float | None = None  # (exit-entry)/entry * 100
    hold_seconds: float | None = None  # exit_ts - entry_ts in seconds (trade duration)
    entry_attribution: dict = Field(default_factory=dict)  # rsi/volume/zone/midpoint/rel-strength/regime/breaker at entry


# ---------- Portfolio State ----------
class Position(BaseModel):
    symbol: str
    quantity: float = 0.0
    avg_cost: float = 0.0  # average entry price (also SL reference)
    peak_price: float = 0.0  # highest price seen since entry; powers trailing stop
    entry_timestamp: str = Field(default_factory=_utc_now_iso)
    fee_paid_buy: float = 0.0  # cumulative fees paid on entries (for net realized P&L on exit)
    breakout_mode: bool = False  # entered as a Systemic Breakout — watcher uses wider trail params
    # --- analytics / research layer (Phase A) ---
    sector: str | None = None  # asset sector taxonomy captured at entry
    atr_at_entry: float | None = None  # ATR(14) at the moment of entry
    atr_percentile_at_entry: float | None = None  # 0..100 percentile at entry
    volatility_regime: str | None = None  # market regime tag at entry
    entry_extension_pct: float | None = None  # % above 4h EMA50 at entry (chase-risk proxy)
    structural_stop: float | None = None  # Phase 1.5: hard stop price just below the entry support zone

    # --- Phase B research attribution (DIAGNOSTIC; populated live by the watcher) ---
    trough_price: float = 0.0  # lowest price seen since entry -> powers Max Adverse Excursion
    mfe_pct: float = 0.0  # max favorable excursion % from avg_cost
    mae_pct: float = 0.0  # max adverse excursion % from avg_cost (negative)
    entry_attribution: dict = Field(default_factory=dict)  # entry-feature snapshot for winner/loser analytics

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_cost


class Portfolio(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = "singleton"
    starting_balance: float = 1200.0
    cash: float = 1200.0
    positions: List[Position] = Field(default_factory=list)
    realized_pnl: float = 0.0
    day_start_equity: float = 1200.0
    day_start_date: str = Field(default_factory=lambda: datetime.now(UTC).date().isoformat())
    updated_at: str = Field(default_factory=_utc_now_iso)


# ---------- Pending maker order (PAPER post-only simulation) ----------
class PendingOrder(BaseModel):
    """A resting Post-Only maker BUY order in PAPER mode. Filled by the position
    watcher only when price crosses our bid OR stays flat at our bid for 2
    consecutive 15s ticks; otherwise cancelled as MISSED_FILL_PRICE_RUN."""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=_new_id)
    symbol: str
    side: str = "BUY"
    quantity: float
    limit_price: float  # our resting maker bid
    placed_at: str = Field(default_factory=_utc_now_iso)
    ticks_flat: int = 0
    mode: str = "PAPER"
    reasoning_id: str | None = None
    breakout: bool = False
    # analytics tags captured at decision time
    sector: str | None = None
    atr_at_entry: float | None = None
    atr_percentile_at_entry: float | None = None
    volatility_regime: str | None = None
    entry_extension_pct: float | None = None  # % above 4h EMA50 at decision time (chase-risk)
    structural_stop: float | None = None  # Phase 1.5: hard stop below the entry support zone (carried to Position on fill)
    entry_attribution: dict = Field(default_factory=dict)  # Phase B: entry-feature snapshot carried to Position on fill


# ---------- Settings ----------
class RiskSettings(BaseModel):
    """User-configurable risk thresholds and operational settings."""
    model_config = ConfigDict(extra="ignore")

    id: str = "singleton"
    # kill-switch thresholds
    max_spread_pct: float = 0.5  # widens beyond this -> kill (in %)
    max_daily_loss_pct: float = 10.0  # SWING PIVOT: drop more than 10% from day start -> kill
    account_max_drawdown_pct: float = 20.0  # RUIN LINE: peak-to-trough equity drawdown that defines account failure (graduation gate 9)
    min_confidence: float = 0.80  # SWING PIVOT: high-conviction macro floor
    # position sizing (legacy: % of equity, scaled by confidence)
    position_size_pct_min: float = 1.0
    position_size_pct_max: float = 3.0
    # adaptive sizing (preferred): fixed USD lot per setup strength
    adaptive_sizing_enabled: bool = True
    normal_lot_usd: float = 75.0   # flat $75 per trade (fresh-start sizing)
    strong_lot_usd: float = 75.0  # flat $75 per trade
    breakout_lot_usd: float = 75.0  # flat $75 per trade
    # breakout filter (3-condition simultaneous trigger)
    breakout_min_confidence: float = 0.85
    breakout_volume_percentile: float = 95.0  # last 14h volume percentile floor
    breakout_max_spread_pct: float = 0.20  # tight spread required for explosive fills
    # breakout-mode exit overrides (position-level when entered as breakout)
    breakout_trail_arm_pct: float = 5.0  # SWING PIVOT: unified with standard trail
    breakout_trail_distance_pct: float = 3.0  # SWING PIVOT: wide leash for trend rides
    # symmetric per-symbol cooldowns after exits
    sl_cooldown_seconds: int = 7200  # 2h after SL_HIT (no revenge trades)
    trail_cooldown_seconds: int = 1800  # 30m after TRAIL_HIT (momentum reset)
    # vault engine (capital sourcing)
    vault_max_override_usd: float = 100.0  # hard cap on capital the bot can deploy
    vault_sync_enabled: bool = False  # when True (LIVE/DRY_RUN) pull free USD+USDC from Kraken each cycle
    # higher-timeframe swing entry filter
    htf_trend_enabled: bool = True  # require Price > 4h EMA50 > 4h EMA200 for BUY entries
    # --- Phase 1.5: Technical-First horizontal level engine ---
    level_entry_enabled: bool = True  # buy when price tests a clean historical horizontal support zone
    level_proximity_pct: float = 1.5  # how close (%) to a zone counts as "testing" it
    level_zone_tol_pct: float = 0.75  # cluster band width (%) when grouping pivots into a zone
    level_min_touches: int = 2  # a zone must be tested this many times to be tradable
    level_lookback_days: int = 540  # daily-candle lookback (~18 months of structure)
    structural_stop_buffer_pct: float = 2.0  # hard stop placed this % below the support zone low (Phase 2: 1.5-2%)
    catastrophe_veto_confidence: float = 0.80  # macro BEARISH at/above this conf is the only macro block
    # --- Phase 2: Primary technical layer gates ---
    rsi_reset_max: float = 35.0  # 4H RSI(14) must be <= this (momentum reset / oversold)
    volume_exhaustion_window: int = 6  # last N 4H bars whose volume linreg slope must be negative
    pullback_max_green_body_pct: float = 1.5  # reject entry candle if green body exceeds this % (anti-chase)
    strong_min_confidence: float = 0.80   # confidence gate for STRONG (strict AND with trend + volatility)
    strong_min_atr_percentile: float = 60.0  # ATR pct rank floor for STRONG
    strong_min_adx: float = 20.0  # 1h ADX floor for STRONG
    max_concurrent_positions: int = 8  # max open positions across symbols
    # exits (per-position, evaluated by the position watcher every 15s)
    stop_loss_pct: float = 10.0  # SWING PIVOT: wide stop for patient holds
    trail_arm_pct: float = 5.0  # SWING PIVOT: lets trends breathe before locking
    trail_distance_pct: float = 3.0  # SWING PIVOT: wide leash prevents shakeouts (static fallback)
    # volatility-adaptive trailing envelope: dynamic_trail = clamp(k * ATR_percentile, min, max)
    dynamic_trail_enabled: bool = True  # when True (and ATR percentile known) the trail distance flexes with volatility
    dynamic_trail_k: float = 0.06  # slope: ATR percentile 0-100 -> ~0-6% before clamping
    dynamic_trail_min_pct: float = 2.0  # floor for the adaptive trailing distance
    dynamic_trail_max_pct: float = 6.0  # ceiling for the adaptive trailing distance
    position_watcher_interval_seconds: int = 15
    # exchange friction (paper/dry-run only; LIVE uses real exchange fees)
    taker_fee_pct: float = 0.40  # % per leg; Kraken Pro base tier 0.40% taker
    maker_fee_pct: float = 0.25  # % per leg; Kraken Pro base tier 0.25% maker (post-only entries)
    breakout_paper_slippage_pct: float = 0.10  # synthetic taker slippage on PAPER breakout market fills
    # operational
    trading_mode: Literal["PAPER", "DRY_RUN", "LIVE"] = "PAPER"
    manual_kill_switch: bool = False  # explicit halt
    enabled_symbols: List[str] = Field(default_factory=lambda: ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "XRP/USD", "PAXG/USD", "LINK/USD", "AAVE/USD", "ARB/USD", "RENDER/USD"])
    # exchange API keys (stored encrypted-at-rest in real prod; here plain for demo)
    coinbase_api_key: str = ""
    coinbase_api_secret: str = ""
    kraken_api_key: str = ""
    kraken_api_secret: str = ""
    updated_at: str = Field(default_factory=_utc_now_iso)


# ---------- Kill-Switch Status ----------
class KillSwitchStatus(BaseModel):
    """Snapshot of active kill-switches at a moment in time."""
    spread_breach: bool = False
    daily_loss_breach: bool = False
    confidence_breach: bool = False
    manual_kill: bool = False
    overall_safe: bool = True
    details: dict = Field(default_factory=dict)


# ---------- Market Snapshot ----------
class MarketSnapshot(BaseModel):
    symbol: str
    price: float
    bid: float
    ask: float
    spread_pct: float
    orderbook_imbalance: float  # -1..1, positive = buy pressure
    volume_24h: float = 0.0
    change_24h_pct: float = 0.0
    timestamp: str = Field(default_factory=_utc_now_iso)
    exchange: str = "kraken"
