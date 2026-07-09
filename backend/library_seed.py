"""
Strategy Library — curated, institutional-grade strategy catalog (Phase 1 / P1).

Each entry is a standardized JSON document (see SCHEMA_FIELDS) with rich metadata for
filtering, seeded historical results, and a pre-computed AI summary + health score.
The three internal strategies (hunter/squeeze/continuation) are flagged `internal=True`
with an `engine_key` so the library links to the live-executable engine strategy; all
others are catalog entries that get wired to the engine incrementally (Option A).

Seeded results are realistic placeholders so the library UX, filtering and leaderboard
work immediately; a real Research-Lab backtest can refresh them on demand.
"""
from __future__ import annotations

from datetime import UTC, datetime


def _grade(score: int) -> str:
    return "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D" if score >= 40 else "E"


def _entry(
    *, id, name, description, source, category, style, timeframe, risk,
    market_regimes, ideal_market, recommended_market,
    entry_rules, exit_rules, risk_management, parameters,
    ideal_conditions, avoid_conditions, results, ai_summary,
    ai_health_score, ai_confidence, rating,
    timeframes=None, market_type=None, internal=False, engine_key=None, wireable=False,
) -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "id": id,
        "name": name,
        "description": description,
        "source": source,
        "category": category,
        "market_type": market_type or ["Crypto"],
        "style": style,
        "ideal_market": ideal_market,
        "timeframe": timeframe,
        "timeframes": timeframes or [timeframe],
        "risk": risk,
        "market_regimes": market_regimes,
        "entry_rules": entry_rules,
        "exit_rules": exit_rules,
        "risk_management": risk_management,
        "parameters": parameters,
        "ideal_conditions": ideal_conditions,
        "avoid_conditions": avoid_conditions,
        "historical_results": results,
        "ai_summary": ai_summary,
        "ai_health_score": ai_health_score,
        "ai_grade": _grade(ai_health_score),
        "ai_confidence": ai_confidence,
        "recommended_market": recommended_market,
        "rating": rating,
        "favorite": False,
        "internal": internal,
        "engine_key": engine_key,
        "wireable": wireable,
        "created_at": now,
        "updated_at": now,
    }


# Catalog strategies wired to the live/paper engine via the declarative executor (Phase B).
# id -> engine key (identical). Used to backfill engine_key/wireable on existing library docs.
WIRED_ENGINE_KEYS = {
    "ema-cross": "ema-cross", "supertrend": "supertrend", "rsi-momentum": "rsi-momentum",
    "macd-trend": "macd-trend", "bollinger-mr": "bollinger-mr", "donchian-breakout": "donchian-breakout",
    "atr-breakout": "atr-breakout", "keltner-breakout": "keltner-breakout",
}


def library() -> list[dict]:
    entries = _library_entries()
    for e in entries:
        if e["id"] in WIRED_ENGINE_KEYS:
            e["engine_key"] = WIRED_ENGINE_KEYS[e["id"]]
            e["wireable"] = True
    return entries


def _library_entries() -> list[dict]:
    return [
        # ---------- Internal (live-executable) ----------
        _entry(
            id="hunter", name="Hunter", source="Ananta (Internal)", internal=True, engine_key="hunter",
            description="Buys clean historical support zones on a momentum reset — buy fear, not falling knives.",
            category="Mean Reversion", style="Mean Reversion", timeframe="4H", timeframes=["1H", "4H", "Daily"],
            risk="Moderate", market_regimes=["Bull Market", "Trending", "Low Volatility"],
            ideal_market="Trending / recovering markets", recommended_market="Crypto majors (BTC, ETH, SOL)",
            entry_rules=["Price tests a proven horizontal support zone", "4H RSI in the 30–35 reset band",
                         "Volatility-contraction (VCP) base forms", "Higher-timeframe trend aligned (Price > EMA50 > EMA200)"],
            exit_rules=["ATR trailing stop", "Profit-lock floors", "Structural stop below the zone low"],
            risk_management={"stop_loss_pct": 10.0, "trail_arm_pct": 5.0, "max_positions": 8, "sizing": "flat $ lot"},
            parameters={"rsi_reset_min": 30, "rsi_reset_max": 35, "level_min_touches": 2},
            ideal_conditions=["Sustained uptrend", "Orderly pullbacks to support"],
            avoid_conditions=["Sideways chop", "Low-volume capitulation"],
            results={"roi": 24.6, "win_rate": 58.0, "profit_factor": 1.9, "sharpe": 1.6, "sortino": 2.2,
                     "max_drawdown": 9.4, "avg_trade": 1.8, "trade_count": 142},
            ai_summary="Performs exceptionally well during sustained bullish trends with moderate volatility. "
                       "Strong risk-adjusted returns; avoid during sideways ranging markets.",
            ai_health_score=87, ai_confidence=88, rating=5,
        ),
        _entry(
            id="squeeze", name="Volatility Squeeze", source="Ananta (Internal)", internal=True, engine_key="squeeze",
            description="Enters as a compression phase ends and volume-backed expansion begins.",
            category="Volatility", style="Breakout", timeframe="4H", timeframes=["1H", "4H"],
            risk="Moderate", market_regimes=["High Volatility", "Trending", "Bull Market"],
            ideal_market="Post-consolidation breakouts", recommended_market="High-beta alts + majors",
            entry_rules=["Price coils into a tight, low-volatility range", "Volume expands ≥ 1.5× trailing avg",
                         "Breakout in the trend direction", "HTF trend aligned"],
            exit_rules=["ATR trailing stop", "Profit floors", "Time-based fail-safe"],
            risk_management={"stop_loss_pct": 10.0, "trail_arm_pct": 5.0, "max_positions": 8},
            parameters={"squeeze_vol_expansion_min": 1.5},
            ideal_conditions=["Compression → expansion regimes", "Rising volume"],
            avoid_conditions=["Prolonged squeezes with no volume", "Choppy conditions"],
            results={"roi": 19.2, "win_rate": 51.0, "profit_factor": 1.6, "sharpe": 1.3, "sortino": 1.8,
                     "max_drawdown": 12.1, "avg_trade": 1.4, "trade_count": 96},
            ai_summary="Thrives when volatility expands out of tight consolidations. Sharpe is solid but "
                       "drawdowns rise in fakeouts — best gated to volume-confirmed breakouts.",
            ai_health_score=78, ai_confidence=80, rating=4,
        ),
        _entry(
            id="continuation", name="Continuation", source="Ananta (Internal)", internal=True, engine_key="continuation",
            description="Buys healthy pullbacks within an established uptrend (not structural reversals).",
            category="Trend Following", style="Trend Following", timeframe="4H", timeframes=["4H", "Daily"],
            risk="Moderate", market_regimes=["Bull Market", "Trending"],
            ideal_market="Strong, orderly trends", recommended_market="Trending majors",
            entry_rules=["EMA20 > EMA50 and EMA50 rising", "Shallow pullback (1–12%) from swing high",
                         "RSI in a healthy 40–62 band", "Volume dry-up on the dip"],
            exit_rules=["ATR trailing stop", "Trend-structure break stop"],
            risk_management={"stop_loss_pct": 10.0, "trail_arm_pct": 5.0, "max_positions": 8},
            parameters={"cont_ema_fast": 20, "cont_ema_slow": 50},
            ideal_conditions=["Confirmed uptrend", "Shallow orderly dips"],
            avoid_conditions=["Deep pullbacks", "Trend breaks / reversals"],
            results={"roi": 21.0, "win_rate": 55.0, "profit_factor": 1.75, "sharpe": 1.45, "sortino": 2.0,
                     "max_drawdown": 10.2, "avg_trade": 1.6, "trade_count": 118},
            ai_summary="A dependable trend-rider in strong, orderly markets. Loses edge in choppy or "
                       "reversal-heavy regimes — pair with a regime filter.",
            ai_health_score=81, ai_confidence=83, rating=4,
        ),
        # ---------- Trend Following ----------
        _entry(
            id="ema-cross", name="EMA Cross", source="Freqtrade", category="Trend Following", style="Trend Following",
            description="Classic dual-EMA crossover: go long when the fast EMA crosses above the slow EMA.",
            timeframe="1H", timeframes=["15m", "1H", "4H"], risk="Moderate",
            market_regimes=["Trending", "Bull Market"], ideal_market="Clean, persistent trends",
            recommended_market="BTC/ETH on 1H–4H",
            entry_rules=["Fast EMA (e.g. 12) crosses above slow EMA (e.g. 26)"],
            exit_rules=["Fast EMA crosses back below slow EMA", "Fixed stop-loss"],
            risk_management={"stop_loss_pct": 6.0, "position_pct": 2.0},
            parameters={"ema_fast": 12, "ema_slow": 26},
            ideal_conditions=["Directional trends"], avoid_conditions=["Sideways/whipsaw markets"],
            results={"roi": 14.3, "win_rate": 44.0, "profit_factor": 1.35, "sharpe": 0.9, "sortino": 1.2,
                     "max_drawdown": 16.5, "avg_trade": 0.9, "trade_count": 210},
            ai_summary="Simple and robust in trends but whipsaws heavily in ranges. Best with a trend/ADX filter.",
            ai_health_score=63, ai_confidence=72, rating=3,
        ),
        _entry(
            id="supertrend", name="Supertrend", source="TradingView / GitHub", category="Trend Following", style="Trend Following",
            description="ATR-based trend filter that flips long/flat as price closes beyond the Supertrend band.",
            timeframe="1H", timeframes=["15m", "1H", "4H"], risk="Moderate",
            market_regimes=["Trending", "Bull Market", "High Volatility"], ideal_market="Volatile trends",
            recommended_market="High-beta alts",
            entry_rules=["Price closes above the Supertrend line (bullish flip)"],
            exit_rules=["Price closes below the Supertrend line"],
            risk_management={"atr_period": 10, "multiplier": 3.0},
            parameters={"atr_period": 10, "multiplier": 3.0},
            ideal_conditions=["Strong momentum trends"], avoid_conditions=["Low-volatility chop"],
            results={"roi": 17.8, "win_rate": 47.0, "profit_factor": 1.5, "sharpe": 1.1, "sortino": 1.5,
                     "max_drawdown": 14.0, "avg_trade": 1.1, "trade_count": 175},
            ai_summary="Great trend capture with clear flips; tune the ATR multiplier to your asset's volatility "
                       "to cut false signals in quiet markets.",
            ai_health_score=71, ai_confidence=76, rating=4,
        ),
        _entry(
            id="donchian-breakout", name="Donchian Breakout", source="QuantConnect", category="Trend Following", style="Breakout",
            description="Buys N-period highs (channel breakout) — the core of classic trend systems.",
            timeframe="Daily", timeframes=["4H", "Daily"], risk="Aggressive",
            market_regimes=["Trending", "High Volatility", "Bull Market"], ideal_market="Breakout regimes",
            recommended_market="Majors + liquid alts, Daily",
            entry_rules=["Price makes a new 20-period high"],
            exit_rules=["Price makes a new 10-period low", "ATR trailing stop"],
            risk_management={"entry_channel": 20, "exit_channel": 10},
            parameters={"entry_channel": 20, "exit_channel": 10},
            ideal_conditions=["Strong expansions / new highs"], avoid_conditions=["Range-bound markets"],
            results={"roi": 22.5, "win_rate": 40.0, "profit_factor": 1.6, "sharpe": 1.05, "sortino": 1.6,
                     "max_drawdown": 19.0, "avg_trade": 1.9, "trade_count": 88},
            ai_summary="Big-winner, low-win-rate breakout system. Positive expectancy from fat tails; needs "
                       "discipline through drawdowns and choppy false breakouts.",
            ai_health_score=68, ai_confidence=74, rating=3,
        ),
        _entry(
            id="turtle", name="Turtle Trading", source="Academic / Classic", category="Trend Following", style="Breakout",
            description="The legendary Turtle system: Donchian breakouts with pyramiding and ATR (N) position sizing.",
            timeframe="Daily", timeframes=["Daily"], risk="Aggressive",
            market_regimes=["Trending", "Bull Market", "Bear Market"], ideal_market="Sustained macro trends",
            recommended_market="Diversified liquid markets",
            entry_rules=["20-day breakout (System 1)", "55-day breakout (System 2)"],
            exit_rules=["10-day / 20-day opposite breakout", "2N stop"],
            risk_management={"unit_risk_pct": 1.0, "max_units": 4, "n_stop_mult": 2.0},
            parameters={"system1": 20, "system2": 55, "n_period": 20},
            ideal_conditions=["Long, persistent trends"], avoid_conditions=["Whipsaw / mean-reverting markets"],
            results={"roi": 26.0, "win_rate": 38.0, "profit_factor": 1.7, "sharpe": 1.1, "sortino": 1.7,
                     "max_drawdown": 22.0, "avg_trade": 2.4, "trade_count": 64},
            ai_summary="A proven, diversification-hungry trend machine. High drawdowns and low hit-rate demand "
                       "strict risk-per-unit sizing and patience.",
            ai_health_score=66, ai_confidence=70, rating=3,
        ),
        _entry(
            id="macd-trend", name="MACD Trend", source="Freqtrade", category="Trend Following", style="Momentum",
            description="Trades MACD line/signal crossovers filtered by the zero line for trend direction.",
            timeframe="1H", timeframes=["1H", "4H"], risk="Moderate",
            market_regimes=["Trending", "Bull Market"], ideal_market="Momentum trends",
            recommended_market="BTC/ETH 1H–4H",
            entry_rules=["MACD crosses above signal", "MACD > 0 (bullish regime)"],
            exit_rules=["MACD crosses below signal"],
            risk_management={"stop_loss_pct": 6.0},
            parameters={"fast": 12, "slow": 26, "signal": 9},
            ideal_conditions=["Momentum expansion"], avoid_conditions=["Flat, low-momentum ranges"],
            results={"roi": 13.0, "win_rate": 46.0, "profit_factor": 1.3, "sharpe": 0.85, "sortino": 1.15,
                     "max_drawdown": 15.0, "avg_trade": 0.8, "trade_count": 190},
            ai_summary="Reliable momentum confirmation with lag. The zero-line filter reduces chop; still fades "
                       "in tight ranges.",
            ai_health_score=61, ai_confidence=71, rating=3,
        ),
        # ---------- Momentum ----------
        _entry(
            id="rsi-momentum", name="RSI Momentum", source="Jesse", category="Momentum", style="Momentum",
            description="Rides momentum by buying RSI strength breakouts (RSI crossing above 60) in an uptrend.",
            timeframe="1H", timeframes=["15m", "1H"], risk="Aggressive",
            market_regimes=["Bull Market", "Trending", "High Volatility"], ideal_market="Strong momentum phases",
            recommended_market="High-momentum alts",
            entry_rules=["RSI crosses above 60", "Price above rising EMA"],
            exit_rules=["RSI falls below 50", "Trailing stop"],
            risk_management={"stop_loss_pct": 5.0},
            parameters={"rsi_period": 14, "entry_level": 60, "exit_level": 50},
            ideal_conditions=["Momentum surges"], avoid_conditions=["Mean-reverting chop"],
            results={"roi": 18.5, "win_rate": 49.0, "profit_factor": 1.45, "sharpe": 1.0, "sortino": 1.4,
                     "max_drawdown": 17.5, "avg_trade": 1.2, "trade_count": 160},
            ai_summary="Captures explosive momentum well but gives back gains in reversals. Tight trailing stops "
                       "are essential.",
            ai_health_score=64, ai_confidence=73, rating=3,
        ),
        _entry(
            id="stochastic-momentum", name="Stochastic Momentum", source="GitHub", category="Momentum", style="Momentum",
            description="Uses stochastic %K/%D crossovers out of oversold to time momentum entries.",
            timeframe="15m", timeframes=["5m", "15m", "1H"], risk="Aggressive",
            market_regimes=["Trending", "High Volatility"], ideal_market="Fast momentum markets",
            recommended_market="Liquid alts, intraday",
            entry_rules=["%K crosses above %D below 20 (oversold reversal)"],
            exit_rules=["%K crosses below %D above 80"],
            risk_management={"stop_loss_pct": 4.0},
            parameters={"k_period": 14, "d_period": 3, "smooth": 3},
            ideal_conditions=["Oscillating momentum"], avoid_conditions=["Strong one-way trends (stays pinned)"],
            results={"roi": 11.0, "win_rate": 52.0, "profit_factor": 1.25, "sharpe": 0.8, "sortino": 1.05,
                     "max_drawdown": 14.5, "avg_trade": 0.6, "trade_count": 240},
            ai_summary="Good in oscillating markets; whipsaws when trends stay overbought/oversold. Combine with a "
                       "regime filter.",
            ai_health_score=57, ai_confidence=68, rating=3,
        ),
        # ---------- Mean Reversion ----------
        _entry(
            id="bollinger-mr", name="Bollinger Bands Mean Reversion", source="QuantConnect", category="Mean Reversion", style="Mean Reversion",
            description="Fades extremes: buys the lower band, exits at the mean (middle band).",
            timeframe="15m", timeframes=["15m", "1H"], risk="Conservative",
            market_regimes=["Sideways", "Low Volatility", "Choppy"], ideal_market="Range-bound markets",
            recommended_market="Stable majors in ranges",
            entry_rules=["Price closes below the lower band (2σ)"],
            exit_rules=["Price reverts to the middle band (SMA20)"],
            risk_management={"stop_loss_pct": 4.0},
            parameters={"period": 20, "std_dev": 2.0},
            ideal_conditions=["Range-bound, low-trend markets"], avoid_conditions=["Strong trends (bands ride)"],
            results={"roi": 12.5, "win_rate": 62.0, "profit_factor": 1.5, "sharpe": 1.2, "sortino": 1.55,
                     "max_drawdown": 8.5, "avg_trade": 0.7, "trade_count": 280},
            ai_summary="High win-rate range trader with tidy drawdowns. Dangerous in trends when price walks the "
                       "band — gate off when ADX is high.",
            ai_health_score=72, ai_confidence=78, rating=4,
        ),
        _entry(
            id="vwap-mr", name="VWAP Mean Reversion", source="GitHub", category="Mean Reversion", style="Mean Reversion",
            description="Fades intraday deviations from VWAP back toward the volume-weighted mean.",
            timeframe="5m", timeframes=["1m", "5m", "15m"], risk="Moderate",
            market_regimes=["Sideways", "Low Volatility"], ideal_market="Liquid intraday ranges",
            recommended_market="High-liquidity majors, intraday",
            entry_rules=["Price stretches N σ below VWAP"],
            exit_rules=["Price reverts to VWAP"],
            risk_management={"stop_loss_pct": 3.0},
            parameters={"deviation_sigma": 2.0},
            ideal_conditions=["Liquid, balanced sessions"], avoid_conditions=["Trend/news-driven days"],
            results={"roi": 9.8, "win_rate": 64.0, "profit_factor": 1.4, "sharpe": 1.15, "sortino": 1.5,
                     "max_drawdown": 7.0, "avg_trade": 0.4, "trade_count": 420},
            ai_summary="A steady intraday scalper of VWAP reversions. Thin per-trade edge means fees/slippage "
                       "matter — needs deep liquidity.",
            ai_health_score=69, ai_confidence=75, rating=3,
        ),
        # ---------- Volatility ----------
        _entry(
            id="atr-breakout", name="ATR Breakout", source="Jesse", category="Volatility", style="Breakout",
            description="Enters on volatility expansion: price breaks prior close ± k×ATR.",
            timeframe="1H", timeframes=["1H", "4H"], risk="Aggressive",
            market_regimes=["High Volatility", "Trending"], ideal_market="Volatility expansions",
            recommended_market="High-beta alts",
            entry_rules=["Price > previous close + k×ATR"],
            exit_rules=["ATR trailing stop", "Opposite ATR band"],
            risk_management={"atr_period": 14, "k": 1.5},
            parameters={"atr_period": 14, "k": 1.5},
            ideal_conditions=["Volatility regime shifts"], avoid_conditions=["Compressed, quiet markets"],
            results={"roi": 20.1, "win_rate": 43.0, "profit_factor": 1.55, "sharpe": 1.05, "sortino": 1.5,
                     "max_drawdown": 18.0, "avg_trade": 1.5, "trade_count": 130},
            ai_summary="Catches regime shifts early; false breakouts in low-vol chop hurt. Pair with a volatility "
                       "percentile filter.",
            ai_health_score=65, ai_confidence=72, rating=3,
        ),
        _entry(
            id="keltner-breakout", name="Keltner Channel Breakout", source="QuantConnect", category="Volatility", style="Breakout",
            description="Buys closes above the upper Keltner channel (EMA ± ATR envelope).",
            timeframe="1H", timeframes=["1H", "4H"], risk="Moderate",
            market_regimes=["Trending", "High Volatility"], ideal_market="Trending breakouts",
            recommended_market="Majors + liquid alts",
            entry_rules=["Close above upper Keltner band"],
            exit_rules=["Close back below the EMA basis"],
            risk_management={"ema_period": 20, "atr_mult": 2.0},
            parameters={"ema_period": 20, "atr_period": 10, "atr_mult": 2.0},
            ideal_conditions=["Directional expansions"], avoid_conditions=["Rangebound consolidation"],
            results={"roi": 16.4, "win_rate": 45.0, "profit_factor": 1.45, "sharpe": 1.0, "sortino": 1.35,
                     "max_drawdown": 15.5, "avg_trade": 1.1, "trade_count": 150},
            ai_summary="Cleaner than raw price breakouts thanks to the ATR envelope. Solid all-rounder in trending "
                       "volatility.",
            ai_health_score=67, ai_confidence=74, rating=3,
        ),
        # ---------- Statistical / Academic ----------
        _entry(
            id="pairs-trading", name="Pairs Trading", source="Academic", category="Statistical / Quantitative", style="Statistical Arbitrage",
            description="Market-neutral: trade the spread between two correlated assets back to its mean.",
            timeframe="1H", timeframes=["1H", "4H", "Daily"], risk="Conservative",
            market_regimes=["Sideways", "Low Volatility", "Choppy"], ideal_market="Stable correlations",
            recommended_market="Correlated pairs (e.g. ETH/BTC)",
            entry_rules=["Z-score of the spread > +2 → short spread", "Z-score < −2 → long spread"],
            exit_rules=["Spread reverts to mean (|Z| < 0.5)"],
            risk_management={"z_entry": 2.0, "z_exit": 0.5, "market_neutral": True},
            parameters={"lookback": 60, "z_entry": 2.0, "z_exit": 0.5},
            ideal_conditions=["Stable cointegration"], avoid_conditions=["Correlation breakdown / regime change"],
            results={"roi": 10.5, "win_rate": 66.0, "profit_factor": 1.6, "sharpe": 1.4, "sortino": 1.8,
                     "max_drawdown": 6.5, "avg_trade": 0.5, "trade_count": 300},
            ai_summary="Low-drawdown, market-neutral income when correlations hold. The tail risk is a correlation "
                       "break — monitor cointegration stability.",
            ai_health_score=74, ai_confidence=79, rating=4,
        ),
        _entry(
            id="time-series-momentum", name="Time Series Momentum", source="Academic (Moskowitz et al.)", category="Academic / Institutional", style="Momentum",
            description="Goes long assets with positive trailing 12-month returns (absolute momentum).",
            timeframe="Daily", timeframes=["Daily"], risk="Moderate",
            market_regimes=["Bull Market", "Bear Market", "Trending"], ideal_market="Persistent macro trends",
            recommended_market="Diversified portfolio rotation",
            entry_rules=["Trailing 12-period return > 0 → long"],
            exit_rules=["Trailing return turns negative → flat"],
            risk_management={"vol_target": True, "rebalance": "monthly"},
            parameters={"lookback_months": 12},
            ideal_conditions=["Durable macro trends"], avoid_conditions=["Sharp regime reversals"],
            results={"roi": 15.5, "win_rate": 53.0, "profit_factor": 1.65, "sharpe": 1.3, "sortino": 1.7,
                     "max_drawdown": 11.0, "avg_trade": 2.0, "trade_count": 48},
            ai_summary="A well-documented, robust institutional factor. Smooth risk-adjusted returns; expect "
                       "shallow but persistent edge and monthly turnover.",
            ai_health_score=76, ai_confidence=82, rating=4,
        ),
    ]
