"""Sanity checks for the exit-engine comparison (identical entries + multi-config replay)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lab import backtest, data_store  # noqa: E402


def _window(symbol="BTC/USD", tf="1h", months=3):
    cov = data_store.coverage(symbol, tf)
    end = cov["max_ts"]
    start = end - months * 30 * 86_400_000
    return symbol, start, end


def test_entries_identical_across_exit_methods():
    """PASS-1 is exit-agnostic → entry count must be identical for fixed vs atr vs native."""
    sym, start, end = _window()
    a = backtest.run_backtest(sym, start, end, exit_method="fixed", target_profit=2.0, target_loss=1.5)
    b = backtest.run_backtest(sym, start, end, exit_method="atr")
    c = backtest.run_backtest(sym, start, end, exit_method="native")
    assert "error" not in a, a
    assert a["entries"] == b["entries"] == c["entries"], (a["entries"], b["entries"], c["entries"])
    print(f"entries identical: {a['entries']} (fixed={a['trades']} atr={b['trades']} native={c['trades']})")


def test_multi_exit_shape_and_winner():
    sym, start, end = _window()
    out = backtest.run_multi_exit(sym, start, end, timeframe="1h")
    assert "error" not in out, out
    assert len(out["rows"]) == 5, out["rows"].keys()
    assert out["entries"] is not None
    for key, m in out["rows"].items():
        if "error" in m:
            continue
        assert "expectancy_usd" in m and "profit_factor" in m and "max_drawdown_pct" in m
    print(f"multi_exit entries={out['entries']} winner={out['winner_key']}")
    for k in [c["key"] for c in out["configs"]]:
        m = out["rows"][k]
        print(f"  {m.get('label'):24} ret={m.get('total_return_pct')}% pf={m.get('profit_factor')} "
              f"win={m.get('win_rate_pct')}% exp=${m.get('expectancy_usd')} dd={m.get('max_drawdown_pct')}%")


if __name__ == "__main__":
    test_entries_identical_across_exit_methods()
    test_multi_exit_shape_and_winner()
    print("OK")
