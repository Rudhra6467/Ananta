"""Point-in-time research warehouse schema and helpers for Ananta."""
from __future__ import annotations

from datetime import datetime
from typing import Any

RESEARCH_COLLECTIONS = (
    "research_assets",
    "research_asset_membership",
    "research_market_bars",
    "research_market_features",
    "research_market_context",
    "research_strategy_definitions",
    "research_strategy_configs",
    "research_backtest_runs",
    "research_trade_observations",
    "research_equation_candidates",
    "research_validation_sessions",
    "research_validation_observations",
    "research_strategy_rankings",
    "research_decision_evidence",
)

METRIC_DEFINITIONS = {
    "win_rate": "wins / resolved trades, after all modeled costs",
    "expectancy": "mean(net_return) per resolved trade",
    "payoff_ratio": "mean(winning net_return) / abs(mean(losing net_return))",
    "profit_factor": "sum(winning net_pnl) / abs(sum(losing net_pnl))",
    "max_drawdown": "maximum peak-to-trough decline of cumulative net equity",
    "mfe": "maximum favorable excursion during the trade window",
    "mae": "maximum adverse excursion during the trade window",
    "sit_out_delta": "strategy net return minus an equivalent always-flat baseline",
    "robustness": "performance stability across nearby parameter values and periods",
}


def _key(*parts: Any) -> str:
    return "|".join(str(x) for x in parts)


async def ensure_research_indexes(db) -> None:
    """Create research indexes; safe to run repeatedly at startup."""
    await db.research_assets.create_index([('symbol', 1)], unique=True)
    # Universe membership is point-in-time so historical top-N selection does not
    # introduce survivorship bias. The same asset can enter/leave the universe.
    await db.research_asset_membership.create_index(
        [('as_of', 1), ('symbol', 1)], unique=True)
    await db.research_asset_membership.create_index(
        [('symbol', 1), ('valid_from', 1), ('valid_to', 1)])
    await db.research_market_bars.create_index(
        [('symbol', 1), ('timeframe', 1), ('timestamp', 1)], unique=True)
    await db.research_market_bars.create_index(
        [('timestamp', 1), ('symbol', 1), ('timeframe', 1)])
    await db.research_market_features.create_index(
        [('symbol', 1), ('timeframe', 1), ('timestamp', 1), ('feature_version', 1)], unique=True)
    await db.research_market_features.create_index(
        [('feature_version', 1), ('timestamp', 1)])
    await db.research_market_context.create_index(
        [('scope', 1), ('timestamp', 1)], unique=True)
    await db.research_strategy_definitions.create_index(
        [('strategy_id', 1)], unique=True)
    await db.research_strategy_configs.create_index(
        [('strategy_id', 1), ('config_hash', 1)], unique=True)
    await db.research_backtest_runs.create_index(
        [('run_id', 1)], unique=True)
    await db.research_backtest_runs.create_index(
        [('strategy_id', 1), ('asset', 1), ('timeframe', 1), ('started_at', -1)])
    await db.research_trade_observations.create_index(
        [('run_id', 1), ('decision_id', 1)], unique=True)
    await db.research_trade_observations.create_index(
        [('symbol', 1), ('timeframe', 1), ('decision_timestamp', 1)])
    await db.research_trade_observations.create_index(
        [('decision', 1), ('outcome_status', 1), ('decision_timestamp', 1)])
    await db.research_equation_candidates.create_index(
        [('equation_id', 1)], unique=True)
    await db.research_equation_candidates.create_index(
        [('target', 1), ('status', 1), ('score.composite', -1)])
    await db.research_validation_sessions.create_index(
        [('validation_id', 1)], unique=True)
    await db.research_validation_sessions.create_index(
        [('status', 1), ('started_at', -1)])
    await db.research_validation_observations.create_index(
        [('validation_id', 1), ('observation_id', 1)], unique=True)
    await db.research_validation_observations.create_index(
        [('validation_id', 1), ('decision_timestamp', 1)])
    await db.research_strategy_rankings.create_index(
        [('as_of', -1), ('scope', 1), ('rank', 1)])
    await db.research_decision_evidence.create_index(
        [('decision_id', 1)], unique=True)
    await db.research_decision_evidence.create_index(
        [('symbol', 1), ('as_of', -1)])


def market_bar(*, symbol: str, timeframe: str, timestamp: datetime, o: float,
               h: float, l: float, c: float, volume: float,
               trades: int | None = None, source: str = 'unknown',
               data_version: str = 'v1') -> dict[str, Any]:
    return {
        'key': _key(symbol, timeframe, timestamp.isoformat()),
        'symbol': symbol, 'timeframe': timeframe, 'timestamp': timestamp,
        'ohlcv': {'open': o, 'high': h, 'low': l, 'close': c, 'volume': volume},
        'trades': trades, 'source': source, 'data_version': data_version,
    }


def asset_membership(*, symbol: str, as_of: datetime, rank: int,
                     market_cap: float | None = None, universe: str = 'top10_crypto',
                     source: str = 'unknown', methodology_version: str = 'membership-v1') -> dict[str, Any]:
    """Create a point-in-time universe membership observation.

    ``as_of`` is the ranking timestamp, not the future backtest period. This prevents
    selecting today's winners and replaying them across history.
    """
    return {
        'key': _key(universe, as_of.isoformat(), symbol.upper()),
        'symbol': symbol.upper(), 'as_of': as_of, 'rank': int(rank),
        'market_cap': market_cap, 'universe': universe,
        'source': source, 'methodology_version': methodology_version,
    }


def decision_observation(*, decision_id: str, run_id: str, symbol: str,
                         timeframe: str, decision_timestamp: datetime,
                         decision: str, signal: str | None,
                         feature_snapshot_id: str, strategy_id: str | None,
                         config_hash: str | None, market_context_id: str,
                         costs_bps: float, evidence_score: float | None = None,
                         reason_codes: list[str] | None = None) -> dict[str, Any]:
    """Create only point-in-time fields; future outcome fields are added later."""
    return {
        'decision_id': decision_id, 'run_id': run_id, 'symbol': symbol,
        'timeframe': timeframe, 'decision_timestamp': decision_timestamp,
        'decision': decision, 'signal': signal, 'strategy_id': strategy_id,
        'config_hash': config_hash, 'feature_snapshot_id': feature_snapshot_id,
        'market_context_id': market_context_id, 'costs_bps': costs_bps,
        'evidence_score': evidence_score, 'reason_codes': reason_codes or [],
        'outcome_status': 'PENDING',
    }


def trade_outcome(*, entry_price: float, exit_price: float,
                  position_side: str, quantity: float, fees: float,
                  slippage: float, funding: float = 0.0,
                  max_favorable_excursion: float | None = None,
                  max_adverse_excursion: float | None = None,
                  holding_seconds: int | None = None) -> dict[str, Any]:
    gross = (exit_price - entry_price) * quantity
    if position_side.upper() == 'SHORT':
        gross = -gross
    net = gross - fees - slippage - funding
    return {
        'entry_price': entry_price, 'exit_price': exit_price,
        'position_side': position_side, 'quantity': quantity,
        'gross_pnl': gross, 'fees': fees, 'slippage': slippage,
        'funding': funding, 'net_pnl': net,
        'net_return': net / max(abs(entry_price * quantity), 1e-12),
        'mfe': max_favorable_excursion, 'mae': max_adverse_excursion,
        'holding_seconds': holding_seconds,
    }


__all__ = [
    'RESEARCH_COLLECTIONS', 'METRIC_DEFINITIONS', 'ensure_research_indexes',
    'market_bar', 'asset_membership', 'decision_observation', 'trade_outcome',
]
