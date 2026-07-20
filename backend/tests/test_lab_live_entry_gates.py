"""
Verify Lab validation Live-Exit-Settings applies allowed_regimes + min_confidence.

APPROACH: run the backtest IN-PROCESS (importing lab.backtest.run_backtest) rather
than via the LabWorker queue — the queue was previously starved by a long-running
health_sweep at test time, and the in-process path exercises the exact same code
path (`_scan_entry` with `live_entry_gates=True`).

Scenarios:
  A. Baseline (analytical, live_entry_gates=False) → contains TREND_UP entries.
  B. Gated   (live_entry_gates=True, allowed_regimes=[COMPRESSION,REVERSAL])
             → ZERO TREND_UP entries; all trades are in allowed regimes.
  C. PDF     → build_lab_report() renders "ENTRY GATES (THIS RUN)" with
             "Live Risk Monitor settings applied: YES" for a live-source run
             and "NO — analytical run" for a manual-source run.
"""
import io
import os
import sys
import pytest

# Ensure the backend package is importable
sys.path.insert(0, "/app/backend")

from lab import backtest as bt  # noqa: E402
from lab.lab_report import build_lab_report  # noqa: E402
from models import RiskSettings  # noqa: E402


CORE = ["hunter", "squeeze", "continuation"]
SYMBOL = "BTC/USD"

# Wider window (6 months) so we DEFINITELY hit some TREND_UP bars in the baseline.
_ONE_MONTH_MS = 30 * 86_400_000


@pytest.fixture(scope="module")
def window():
    """Anchor window off the newest local 1h candle so it works in any env."""
    from lab import data_store
    cov = data_store.coverage(SYMBOL, "1h")
    assert cov["max_ts"], "no local 1h history for BTC/USD"
    end = cov["max_ts"]
    start = end - 6 * _ONE_MONTH_MS
    # Ensure we have enough warmup bars behind `start`
    return start, end


def _regime_counts(result: dict) -> dict:
    return {k: v.get("n", 0) for k, v in (result.get("regime_breakdown") or {}).items()}


def test_A_baseline_analytical_contains_trend_up(window):
    """Analytical run (live_entry_gates=False) must NOT filter regimes."""
    start, end = window
    s = RiskSettings()
    # Even if these are set, they must NOT be enforced when live_entry_gates=False
    s.allowed_regimes = ["COMPRESSION", "REVERSAL"]
    s.min_confidence = 0.7

    r = bt.run_backtest(SYMBOL, start, end, settings=s, strategies=CORE,
                        timeframe="1h", exit_method="native",
                        live_entry_gates=False)
    assert "error" not in r, r
    counts = _regime_counts(r)
    print(f"BASELINE trades={r['trades']} entries={r['entries']} regimes={counts}")
    assert r["trades"] > 0, "baseline produced no trades — window too short?"
    # We expect regimes OTHER than the allowed set to appear (filter not enforced).
    # In BTC 6-month windows TREND_UP is almost always present.
    trend_up_n = counts.get("TREND_UP", 0)
    non_allowed = sum(n for k, n in counts.items() if k not in ("COMPRESSION", "REVERSAL"))
    print(f"baseline TREND_UP={trend_up_n} non_allowed_total={non_allowed}")
    # invariant: filter is off → we should see regimes outside the allowed set
    assert non_allowed > 0, (
        f"analytical run appears to be filtered — expected regimes outside "
        f"COMPRESSION/REVERSAL, got: {counts}"
    )


def test_B_live_gated_run_excludes_trend_up(window):
    """live_entry_gates=True + allowed_regimes=[COMPRESSION,REVERSAL] must skip TREND_UP."""
    start, end = window
    s = RiskSettings()
    s.allowed_regimes = ["COMPRESSION", "REVERSAL"]
    s.min_confidence = 0.7

    r = bt.run_backtest(SYMBOL, start, end, settings=s, strategies=CORE,
                        timeframe="1h", exit_method="native",
                        live_entry_gates=True)
    assert "error" not in r, r
    counts = _regime_counts(r)
    print(f"GATED trades={r['trades']} entries={r['entries']} regimes={counts}")

    # Assertion 1: zero TREND_UP
    assert counts.get("TREND_UP", 0) == 0, (
        f"expected ZERO TREND_UP under live gate, got: {counts}"
    )
    # Assertion 2: every regime seen is in the allowed set (allow '—' for unlabeled)
    illegal = [k for k, n in counts.items()
               if n > 0 and k not in ("COMPRESSION", "REVERSAL", "—")]
    assert not illegal, f"illegal regimes present under live gate: {illegal} (counts={counts})"


def test_C_gated_run_has_fewer_or_equal_trades_than_baseline(window):
    """Gate can only REMOVE trades, never add them."""
    start, end = window
    s = RiskSettings()
    s.allowed_regimes = ["COMPRESSION", "REVERSAL"]
    s.min_confidence = 0.7

    r_base = bt.run_backtest(SYMBOL, start, end, settings=s, strategies=CORE,
                             timeframe="1h", exit_method="native",
                             live_entry_gates=False)
    r_gate = bt.run_backtest(SYMBOL, start, end, settings=s, strategies=CORE,
                             timeframe="1h", exit_method="native",
                             live_entry_gates=True)
    print(f"baseline entries={r_base['entries']} gated entries={r_gate['entries']}")
    assert r_gate["entries"] <= r_base["entries"], (
        f"gated entries ({r_gate['entries']}) exceed baseline ({r_base['entries']})"
    )


def _pdf_text(pdf_bytes: bytes) -> str:
    from pdfminer.high_level import extract_text  # type: ignore
    return extract_text(io.BytesIO(pdf_bytes))


def _stub_run(exit_source: str, setting_overrides: dict) -> dict:
    return {
        "id": "test-" + exit_source,
        "kind": "backtest",
        "symbols": [SYMBOL],
        "period": "3m",
        "start_ms": 1_700_000_000_000,
        "end_ms": 1_710_000_000_000,
        "strategies": CORE,
        "exit_method": "native",
        "exit_source": exit_source,
        "target_profit": 5.0,
        "target_loss": 4.0,
        "atr_params": None,
        "setting_overrides": setting_overrides,
        "git_hash": "test",
        "created_at": "2026-06-20T00:00:00+00:00",
        "status": "DONE",
        "progress_pct": 100.0,
        "metric": "return_over_dd",
        "timeframe": "1h",
        "result": {
            "per_symbol": {SYMBOL: {
                "symbol": SYMBOL, "timeframe": "1h", "trades": 0, "entries": 0,
                "starting_capital": 1200, "ending_capital": 1200,
                "total_return_pct": 0.0, "net_pnl": 0.0, "win_rate_pct": 0.0,
                "max_drawdown_pct": 0.0, "profit_factor": None, "sharpe": None, "sortino": None,
                "regime_breakdown": {}, "strategy_breakdown": {}, "exit_module_breakdown": {},
                "capture_stats": {"capture_rate_pct": None, "total_mfe_usd": 0,
                                  "total_captured_usd": 0, "total_profit_left_usd": 0,
                                  "avg_mfe_pct": None, "avg_mae_pct": None,
                                  "avg_profit_left_usd": None},
                "trade_log": [], "recommendation": "INSUFFICIENT SAMPLE",
                "avg_return_pct": 0, "avg_mfe_pct": None, "avg_mae_pct": None,
                "avg_trade_quality": None,
                "avg_profit_left_usd": None, "total_profit_left_usd": 0,
                "avg_mfe_usd": None, "avg_mae_usd": None,
                "exit_method": "native", "exit_method_label": "Native Strategy Exit",
                "target_profit": 5.0, "target_loss": 4.0, "position_size_usd": 75,
                "target_profit_pct": None, "target_loss_pct": None, "atr_params": None,
                "expectancy_usd": 0.0,
            }},
            "multi_timeframe": {},
            "exit_comparison": {},
            "exit_method": "native",
            "exit_method_label": "Native Strategy Exit",
            "exit_source": exit_source,
            "target_profit": 5.0, "target_loss": 4.0, "atr_params": None,
        },
    }


def test_D_pdf_live_run_shows_yes_and_regimes():
    run = _stub_run("live", {"allowed_regimes": ["COMPRESSION", "REVERSAL"],
                             "min_confidence": 0.7, "htf_trend_enabled": True,
                             "level_entry_enabled": False,
                             "breakout_min_confidence": 0.6})
    pdf = build_lab_report(run)
    assert pdf[:4] == b"%PDF", "not a PDF"
    text = _pdf_text(pdf)
    assert "ENTRY GATES (THIS RUN)" in text, "section missing"
    assert "YES" in text, "live YES marker missing"
    assert "Live Risk Monitor" in text
    assert "COMPRESSION" in text and "REVERSAL" in text, "allowed regimes not listed"
    assert "0.7" in text, "min_confidence value not rendered"


def test_E_pdf_manual_run_shows_analytical_marker():
    run = _stub_run("manual", None)
    pdf = build_lab_report(run)
    text = _pdf_text(pdf)
    assert "ENTRY GATES (THIS RUN)" in text
    assert "NO" in text and "analytical run" in text, (
        "manual run should say NO — analytical run"
    )
    assert "Not enforced" in text
