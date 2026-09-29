# Ananta Research Database v1

## Purpose

This is the evidence store for Ananta's market-research memory. It is separate from the operational portfolio/trade ledger and is designed around one invariant:

> A decision may use only information whose `available_at` is less than or equal to the decision timestamp. Future information belongs only to outcome/validation fields after the observation window closes.

The database must answer, reproducibly:

1. What did the market look like at time `t`?
2. Which strategy and exact parameterization produced the signal?
3. What did Ananta decide: `ENTER`, `EXIT`, `WAIT`, or `SKIP`?
4. What would have happened if the underlying signal had been fired blindly?
5. What happened after fees, slippage, funding and execution assumptions?
6. How did the trade behave internally (MFE/MAE/path/duration)?
7. Does the result survive nearby parameters, assets, periods and regimes?
8. Does the rule remain useful in a 30–40 day unseen forward period?

## Collections

| Collection | Role |
|---|---|
| `research_assets` | Point-in-time asset universe membership and metadata. |
| `research_market_bars` | Canonical OHLCV/trade-count bars by symbol/timeframe. |
| `research_market_features` | Technical/market microstructure features computed only from data available at `t`. |
| `research_market_context` | Asset and market regime, sentiment and cross-asset context at `t`. |
| `research_strategy_definitions` | Immutable identity and implementation version of each strategy. |
| `research_strategy_configs` | Exact parameter configurations and configuration hash. |
| `research_backtest_runs` | Reproducible experiment manifest and aggregate results. |
| `research_trade_observations` | One row per strategy opportunity, including WAIT/SKIP. |
| `research_equation_candidates` | Regression/symbolic-regression equations and validation statistics. |
| `research_validation_sessions` | 30–40 day out-of-sample experiment manifest. |
| `research_validation_observations` | Daily/live observations for each validation decision. |
| `research_strategy_rankings` | Time-stamped strategy/config rankings and confidence. |
| `research_decision_evidence` | Compact evidence packet consumed by Agent Ananta before acting. |

## Required decision record

Every candidate opportunity should contain:

```text
identity
  decision_id, run_id, validation_id
  symbol, timeframe
  strategy_id, strategy_version, config_hash

time
  decision_timestamp
  feature_available_at
  context_available_at
  outcome_close_at

action
  signal               # what the underlying strategy said
  decision             # ENTER / EXIT / WAIT / SKIP
  reason_codes
  evidence_score

point_in_time_state
  feature_snapshot_id
  market_context_id
  regime_id
  sentiment_state
  technical_state
  volatility_state
  market_structure_state

execution_assumptions
  position_side, intended_entry
  stop, target, horizon
  fee_bps, slippage_bps, funding_assumption

counterfactuals
  blind_signal_action
  blind_signal_net_return
  gated_action_net_return
  sit_out_net_return
  opportunity_cost

outcome
  outcome_status
  entry_price, exit_price
  gross_pnl, fees, slippage, funding, net_pnl, net_return
  win_loss
  mfe, mae, holding_seconds
```

The `outcome` section is populated only after the forward horizon has elapsed.

## Backtest run manifest

Each run records the full experiment identity: data snapshot/version, source revisions, universe definition, strategy implementation version, parameter search space, timeframe, cost model, execution model, train/test date ranges, random seeds, software version and aggregate metrics.

This prevents a later result from being mistaken for the original experiment.

## Equation candidates

An equation candidate stores both the human-readable expression and its machine representation:

```text
equation_id
expression
features[]
target                  # win_probability, net_return, expectancy, etc.
training_window
test_window
model_family            # symbolic_regression / logistic / tree / GAM / ...
complexity
coefficients
thresholds
fit_metrics             # R2/AUC/logloss/etc.
trading_metrics         # win_rate/expectancy/profit_factor/drawdown
robustness_metrics
multiple_testing_stats
status                  # candidate / rejected / forward_test / validated / retired
```

An equation is **not** promoted because it fits historical data. It must survive a held-out period, multiple-testing controls, perturbation/parameter tests and the live forward-validation gate.

## Ranking model

Rankings should be multidimensional rather than a single raw-profit sort. Store at minimum:

- win rate after cost
- expectancy after cost
- payoff ratio
- profit factor
- max drawdown
- drawdown duration
- Sharpe / Sortino / Calmar
- MFE / MAE
- turnover and exposure
- period consistency
- asset consistency
- regime consistency
- sit-out delta versus flat/baseline
- parameter-neighborhood robustness
- forward-test performance
- evidence sample size
- statistical confidence / uncertainty

A composite score may be added, but the underlying measurements must remain queryable.

## Critical anti-overfitting rules

1. Do not choose parameters using the future validation window.
2. Do not compute features with future bars.
3. Preserve the original point-in-time data version used by every run.
4. Separate discovery, selection, and final forward validation.
5. Treat every parameter combination as a multiple hypothesis, not an independent discovery.
6. Keep failed, neutral and skipped opportunities; deleting them creates survivorship bias.
7. Compare every gated rule with a blind-signal counterfactual and a sit-out baseline.
8. Never rank strategies on one metric alone.
9. Require stability across nearby parameter values rather than a single optimum.
10. Keep the 30–40 day validation set untouched until the rule is frozen.

## V1 indexes

The implementation in `backend/research_database.py` creates uniqueness/indexes for time-series lookup, strategy/config identity, run identity, decision audit trails, validation sessions and ranked evidence retrieval.

Initialize the indexes against the existing `MONGO_URL`/`DB_NAME` database before ingestion.
