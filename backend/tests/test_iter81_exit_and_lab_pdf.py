"""
Iteration 81 — verify:
  (A) /api/settings roundtrip for per-strategy (profile_overrides) and per-coin (asset_exit_overrides) exit overrides,
      plus deployed-exit-label precedence (coin > strategy > global).
  (B) Lab backtest PDF contains the 5 new Phase-1 sections + Strategy column in trade log.
"""
import io
import os
import time
import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
OWNER_EMAIL = os.environ["OWNER_EMAIL"]
OWNER_PASSWORD = os.environ["OWNER_PASSWORD"]


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_hdr(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def baseline_settings(auth_hdr):
    """Snapshot settings before mutation + restore after."""
    r = requests.get(f"{BASE_URL}/api/settings", headers=auth_hdr, timeout=15)
    assert r.status_code == 200
    snap = r.json()
    yield snap
    # Restore only the keys we touch
    restore = {
        "exit_method_pref": snap.get("exit_method_pref", "native"),
        "profile_overrides": snap.get("profile_overrides") or {},
        "asset_exit_overrides": snap.get("asset_exit_overrides") or {},
        "fixed_target_pct": snap.get("fixed_target_pct", 3.0),
        "stop_loss_pct": snap.get("stop_loss_pct", 2.2),
        "trail_arm_pct": snap.get("trail_arm_pct", 1.6),
        "trail_distance_pct": snap.get("trail_distance_pct", 0.9),
    }
    requests.put(f"{BASE_URL}/api/settings", headers=auth_hdr, json=restore, timeout=15)


# ── describeActiveExit (mirrors frontend/src/lib/exitConfig.js precedence) ───
_METHOD_NAMES = {
    "fixed_pct": "Fixed-% Stop", "atr_trailing": "ATR Trailing Stop",
    "chandelier": "Chandelier Exit", "breakeven_trail": "Breakeven Trail",
    "structural_trail": "Structural Trail", "native": "Universal Exit Engine",
}


def _first_exit_override(m):
    for k, v in (m or {}).items():
        if isinstance(v, dict) and v.get("method"):
            return k, v
    return None


def describe_active_exit(s):
    coin = _first_exit_override(s.get("asset_exit_overrides"))
    strat = _first_exit_override(s.get("profile_overrides"))
    method = s.get("exit_method_pref") or "native"
    scope, scope_label = "global", "Global (all markets)"
    if coin:
        method, scope, scope_label = coin[1]["method"], "coin", f"Per-coin · {coin[0]}"
    elif strat:
        method, scope, scope_label = strat[1]["method"], "strategy", f"Per-strategy · {strat[0]}"
    return {"method": method, "type_label": _METHOD_NAMES.get(method, "Universal Exit Engine"),
            "scope": scope, "scope_label": scope_label}


# ─────────────────────────── (A) Settings tests ──────────────────────────────
class TestExitOverridesRoundtrip:
    def test_global_only(self, auth_hdr, baseline_settings):
        payload = {"exit_method_pref": "fixed_pct", "fixed_target_pct": 4.2, "stop_loss_pct": 1.8,
                   "profile_overrides": {}, "asset_exit_overrides": {}}
        r = requests.put(f"{BASE_URL}/api/settings", headers=auth_hdr, json=payload, timeout=15)
        assert r.status_code == 200, r.text
        s = requests.get(f"{BASE_URL}/api/settings", headers=auth_hdr, timeout=15).json()
        assert s["exit_method_pref"] == "fixed_pct"
        assert s["fixed_target_pct"] == 4.2
        assert s["stop_loss_pct"] == 1.8
        d = describe_active_exit(s)
        assert d["method"] == "fixed_pct"
        assert d["scope"] == "global"
        assert d["type_label"] == "Fixed-% Stop"

    def test_per_strategy_override_wins_over_global(self, auth_hdr, baseline_settings):
        payload = {
            "exit_method_pref": "native",  # global is native
            "profile_overrides": {"hunter": {"method": "atr_trailing", "trail_arm": 2.1,
                                             "trail_dist": 1.2, "stop_pct": 3.3}},
            "asset_exit_overrides": {},
        }
        r = requests.put(f"{BASE_URL}/api/settings", headers=auth_hdr, json=payload, timeout=15)
        assert r.status_code == 200, r.text
        s = requests.get(f"{BASE_URL}/api/settings", headers=auth_hdr, timeout=15).json()
        po = (s.get("profile_overrides") or {}).get("hunter") or {}
        assert po.get("method") == "atr_trailing"
        assert po.get("trail_arm") == 2.1
        assert po.get("stop_pct") == 3.3
        d = describe_active_exit(s)
        assert d["method"] == "atr_trailing"
        assert d["scope"] == "strategy"
        assert d["scope_label"] == "Per-strategy · hunter"
        assert d["type_label"] == "ATR Trailing Stop"

    def test_per_coin_override_wins_over_strategy(self, auth_hdr, baseline_settings):
        payload = {
            "exit_method_pref": "native",
            "profile_overrides": {"hunter": {"method": "atr_trailing", "trail_arm": 2.1}},
            "asset_exit_overrides": {"BTC/USD": {"method": "fixed_pct",
                                                 "target_pct": 6.6, "stop_pct": 2.4}},
        }
        r = requests.put(f"{BASE_URL}/api/settings", headers=auth_hdr, json=payload, timeout=15)
        assert r.status_code == 200, r.text
        s = requests.get(f"{BASE_URL}/api/settings", headers=auth_hdr, timeout=15).json()
        ao = (s.get("asset_exit_overrides") or {}).get("BTC/USD") or {}
        assert ao.get("method") == "fixed_pct"
        assert ao.get("target_pct") == 6.6
        d = describe_active_exit(s)
        assert d["method"] == "fixed_pct"
        assert d["scope"] == "coin"
        assert d["scope_label"] == "Per-coin · BTC/USD"
        assert d["type_label"] == "Fixed-% Stop"

    def test_plain_profile_tuning_without_method_stays_global(self, auth_hdr, baseline_settings):
        # profile_overrides without a `method` key should NOT be treated as an exit override.
        payload = {
            "exit_method_pref": "native",
            "profile_overrides": {"hunter": {"trail_atr_mult": 2.5}},  # no `method`
            "asset_exit_overrides": {},
        }
        r = requests.put(f"{BASE_URL}/api/settings", headers=auth_hdr, json=payload, timeout=15)
        assert r.status_code == 200, r.text
        s = requests.get(f"{BASE_URL}/api/settings", headers=auth_hdr, timeout=15).json()
        d = describe_active_exit(s)
        assert d["scope"] == "global", f"expected global, got {d}"
        assert d["method"] == "native"


# ────────────────────────── (B) Lab PDF sections ─────────────────────────────
_EXPECTED_SECTIONS = [
    "Strategy-wise Performance Summary",
    "Regime × Strategy Performance Matrix",
    "Exit Type Performance per Strategy",
    "Top Winning",  # "Top Winning & Losing Setups" (ampersand is escaped in reportlab)
    "Losing Setups",
]


def _extract_pdf_text(data: bytes) -> str:
    """Extract text from a PDF using pdfminer.six (pre-installed on the container)."""
    from pdfminer.high_level import extract_text
    return extract_text(io.BytesIO(data)) or ""


def _find_or_create_done_backtest(auth_hdr) -> str:
    """Reuse an existing DONE backtest with all 3 strategies, else create a fresh one."""
    # Try the rid stashed by the main agent first.
    try:
        with open("/tmp/rid.txt") as f:
            rid = f.read().strip()
        r = requests.get(f"{BASE_URL}/api/lab/runs/{rid}", headers=auth_hdr, timeout=15)
        if r.status_code == 200:
            j = r.json()
            if j.get("status") == "DONE" and j.get("kind") == "backtest":
                return rid
    except Exception:
        pass

    # Fallback: list runs and pick most-recent DONE backtest.
    r = requests.get(f"{BASE_URL}/api/lab/runs", headers=auth_hdr, timeout=20)
    if r.status_code == 200:
        for run in r.json().get("runs") or r.json() or []:
            if run.get("status") == "DONE" and run.get("kind") == "backtest":
                return run["id"]

    # Last resort: create one (may take 2-3 min).
    body = {"kind": "backtest",
            "symbols": ["BTC/USD", "ETH/USD", "SOL/USD"],
            "strategies": ["hunter", "squeeze", "continuation"],
            "exit_method": "fixed", "target_profit": 5, "target_loss": 4,
            "period": "1m", "metric": "sharpe"}
    r = requests.post(f"{BASE_URL}/api/lab/runs", headers=auth_hdr, json=body, timeout=30)
    assert r.status_code in (200, 201), r.text
    rid = r.json()["id"]
    deadline = time.time() + 300
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/api/lab/runs/{rid}", headers=auth_hdr, timeout=15)
        assert r.status_code == 200
        st = r.json().get("status")
        if st == "DONE":
            return rid
        if st in ("ERROR", "FAILED", "FAILURE"):
            pytest.fail(f"lab run {rid} ended with status {st}")
        time.sleep(10)
    pytest.fail(f"lab run {rid} did not reach DONE within 300s")


class TestLabBacktestPdf:
    def test_done_run_pdf_has_new_sections_and_strategy_column(self, auth_hdr):
        rid = _find_or_create_done_backtest(auth_hdr)
        r = requests.get(f"{BASE_URL}/api/lab/runs/{rid}/pdf", headers=auth_hdr, timeout=60)
        assert r.status_code == 200, r.text[:400]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF", "response is not a PDF"
        text = _extract_pdf_text(r.content)
        assert text, "PDF text extraction produced empty output"
        missing = [s for s in _EXPECTED_SECTIONS if s not in text]
        assert not missing, f"missing PDF sections: {missing}\n--- PDF text sample ---\n{text[:1200]}"
        # Strategy column in the Full trade log — table header row includes 'Strategy' + 'Entry (UTC)'.
        assert "Full trade log" in text, "'Full trade log' section header not found"
        # Look for the Strategy header near the trade-log table.
        idx = text.find("Full trade log")
        window = text[idx: idx + 2000]
        assert "Strategy" in window, f"'Strategy' column header missing near trade log:\n{window[:500]}"
