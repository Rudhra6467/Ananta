"""Phase A analytics endpoint regression tests (review_request driven).

Validates:
- GET /api/analytics/performance shape + self-consistent math
- Regression: /api/trades, /api/settings, /api/public/snapshot, POST /api/cycle/run/BTC
"""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hunter-squeeze-labs.preview.emergentagent.com").rstrip("/")

WINDOW_KEYS = [
    "closed_trades", "expectancy_usd", "profit_factor", "win_rate_pct",
    "avg_win_usd", "avg_loss_usd", "net_pnl_usd", "total_fees_usd",
    "total_slippage_usd", "total_friction_usd", "max_drawdown_usd",
    "regime_breakdown",
]


def _get(path, **kw):
    return requests.get(f"{BASE_URL}{path}", timeout=30, **kw)


def test_analytics_performance_shape():
    r = _get("/api/analytics/performance")
    assert r.status_code == 200, r.text
    data = r.json()
    for top in ("rolling_24h", "calendar_day", "sector_exposure", "high_beta_warning", "open_positions"):
        assert top in data, f"missing {top}"
    assert isinstance(data["high_beta_warning"], bool)
    assert isinstance(data["open_positions"], list)
    for win in ("rolling_24h", "calendar_day"):
        block = data[win]
        for k in WINDOW_KEYS:
            assert k in block, f"{win} missing {k}"
        assert isinstance(block["regime_breakdown"], dict)


def test_analytics_math_self_consistent():
    r = _get("/api/analytics/performance")
    assert r.status_code == 200
    data = r.json()
    for win in ("rolling_24h", "calendar_day"):
        b = data[win]
        # expectancy = win_rate*avg_win - loss_rate*avg_loss
        wr = b["win_rate_pct"] / 100.0
        lr = b.get("loss_rate_pct", 100 - b["win_rate_pct"]) / 100.0 if "loss_rate_pct" in b else (
            1 - wr if b["closed_trades"] else 0
        )
        expected_expectancy = wr * b["avg_win_usd"] - lr * b["avg_loss_usd"]
        assert abs(expected_expectancy - b["expectancy_usd"]) < 0.05, (
            f"{win}: expectancy mismatch expected~{expected_expectancy:.4f} got {b['expectancy_usd']}"
        )
        # profit factor null when gross_loss==0
        gp = b.get("gross_profit_usd", 0.0)
        gl = b.get("gross_loss_usd", 0.0)
        if gl > 0:
            assert b["profit_factor"] is not None
            assert abs(b["profit_factor"] - gp / gl) < 0.05
        else:
            assert b["profit_factor"] is None
        # friction == fees + slippage
        assert abs(b["total_friction_usd"] - (b["total_fees_usd"] + b["total_slippage_usd"])) < 0.01


def test_high_beta_warning_off_when_no_open_positions():
    r = _get("/api/analytics/performance")
    data = r.json()
    open_pos = data["open_positions"]
    # current state: should be 0 open positions per problem statement, so warning off
    high_beta_count = data["sector_exposure"]["high_beta_count"]
    if high_beta_count < 3:
        assert data["high_beta_warning"] is False
    # if 0 open, list empty
    if len(open_pos) == 0:
        assert data["high_beta_warning"] is False


def test_trades_endpoint():
    r = _get("/api/trades")
    assert r.status_code == 200
    d = r.json()
    assert "items" in d and "count" in d
    assert isinstance(d["items"], list)


def test_settings_endpoint():
    r = _get("/api/settings")
    assert r.status_code == 200
    s = r.json()
    assert "trading_mode" in s
    # SAFETY: per agent context, trading_mode should remain PAPER
    assert s["trading_mode"] == "PAPER", f"UNSAFE: trading_mode is {s['trading_mode']}"


def test_public_snapshot():
    r = _get("/api/public/snapshot")
    assert r.status_code == 200
    d = r.json()
    for k in ("portfolio", "risk", "settings", "snapshots", "trades", "reasoning"):
        assert k in d


def test_cycle_run_btc():
    r = requests.post(f"{BASE_URL}/api/cycle/run/BTC", timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "decision" in d
    assert "reasoning_id" in d or "reasoning" in d or d.get("decision") is not None
