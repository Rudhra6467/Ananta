"""Iter 24 regression — AI Quant Analyst + Saved Configs schema-driven editor.

Focus: prove the two NEW features work end-to-end via HTTP against the shared backend.
Conftest auto-injects owner Bearer on mutating requests, so we don't manage tokens here.
"""
import os
import time
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


# ---------- SAVED CONFIGS ----------

def test_strategy_registry_returns_all_three_strategies():
    r = requests.get(f"{BASE}/api/strategy/registry", timeout=15)
    assert r.status_code == 200
    strats = r.json().get("strategies") or []
    keys = {s["key"] for s in strats}
    assert {"hunter", "squeeze", "continuation"}.issubset(keys), f"missing keys, got: {keys}"
    # Each strategy exposes a params schema list used by the dynamic editor
    for s in strats:
        assert isinstance(s.get("params"), list) and len(s["params"]) > 0
        for p in s["params"]:
            for f in ("id", "type", "default", "group", "label"):
                assert f in p, f"strategy {s['key']} param missing {f}: {p}"


def test_strategy_configs_list_ok():
    r = requests.get(f"{BASE}/api/strategy/configs", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "configs" in body and isinstance(body["configs"], list)


def _find_param_with_range(schema_params):
    """Pick a numeric param with clear min/max we can violate."""
    for p in schema_params:
        if p["type"] in ("int", "float") and p.get("min") is not None and p.get("max") is not None:
            return p
    return None


def test_create_update_rating_and_delete_config_flow():
    # discover a strategy
    reg = requests.get(f"{BASE}/api/strategy/registry", timeout=15).json()["strategies"]
    hunter = next(s for s in reg if s["key"] == "hunter")
    num_param = _find_param_with_range(hunter["params"])
    assert num_param, "expected at least one bounded numeric param on hunter"

    # CREATE
    create_payload = {
        "strategy_key": "hunter",
        "params": {},
        "origin": "user",
        "name": "TEST_iter24_user_cfg",
    }
    c = requests.post(f"{BASE}/api/strategy/configs", json=create_payload, timeout=15)
    assert c.status_code == 200, c.text
    cfg = c.json()["config"]
    cfg_id = cfg["id"]
    assert cfg["origin"] == "user"
    assert cfg["strategy_key"] == "hunter"
    assert cfg["name"] == "TEST_iter24_user_cfg"

    try:
        # UPDATE params — valid override within range
        mid = (num_param["min"] + num_param["max"]) / 2
        if num_param["type"] == "int":
            mid = int(mid)
        valid_val = mid if mid != num_param["default"] else num_param["max"]
        u = requests.put(f"{BASE}/api/strategy/configs/{cfg_id}",
                         json={"params": {num_param["id"]: valid_val}}, timeout=15)
        assert u.status_code == 200, u.text
        assert u.json()["config"]["params"].get(num_param["id"]) == valid_val

        # UPDATE — out-of-range param -> 422
        bad_val = num_param["max"] + 1000 if num_param["type"] == "int" else num_param["max"] + 1e6
        b = requests.put(f"{BASE}/api/strategy/configs/{cfg_id}",
                        json={"params": {num_param["id"]: bad_val}}, timeout=15)
        assert b.status_code == 422, f"expected 422 for out-of-range, got {b.status_code}: {b.text}"
        assert "errors" in (b.json().get("detail") or {})

        # UPDATE rating + name (accepted as separate fields)
        rr = requests.put(f"{BASE}/api/strategy/configs/{cfg_id}",
                         json={"rating": {"stars": 4}, "name": "TEST_iter24_renamed"}, timeout=15)
        assert rr.status_code == 200, rr.text
        got = rr.json()["config"]
        assert got.get("rating", {}).get("stars") == 4
        assert got.get("name") == "TEST_iter24_renamed"

        # GET verifies persistence
        g = requests.get(f"{BASE}/api/strategy/configs", timeout=15).json()
        mine = next((x for x in g["configs"] if x["id"] == cfg_id), None)
        assert mine is not None
        assert mine["name"] == "TEST_iter24_renamed"
        assert mine["rating"]["stars"] == 4
    finally:
        # DELETE
        d = requests.delete(f"{BASE}/api/strategy/configs/{cfg_id}", timeout=15)
        assert d.status_code == 200, d.text
        # confirm gone
        g2 = requests.get(f"{BASE}/api/strategy/configs", timeout=15).json()
        assert not any(x["id"] == cfg_id for x in g2["configs"])


def test_delete_builtin_config_is_400():
    # find any builtin; seed if missing
    listing = requests.get(f"{BASE}/api/strategy/configs", timeout=15).json()["configs"]
    builtin = next((c for c in listing if c.get("origin") == "builtin"), None)
    if not builtin:
        # seed defaults (idempotent, owner-gated)
        seed = requests.post(f"{BASE}/api/strategy/seed-defaults", timeout=15)
        assert seed.status_code == 200, seed.text
        listing = requests.get(f"{BASE}/api/strategy/configs", timeout=15).json()["configs"]
        builtin = next((c for c in listing if c.get("origin") == "builtin"), None)
    assert builtin, "no builtin config found even after seed"
    d = requests.delete(f"{BASE}/api/strategy/configs/{builtin['id']}", timeout=15)
    assert d.status_code == 400, f"expected 400 for builtin delete, got {d.status_code}: {d.text}"


# ---------- AI QUANT ANALYST ----------

def test_ai_query_empty_question_400():
    r = requests.post(f"{BASE}/api/analytics/ai_query", json={"question": "   "}, timeout=30)
    assert r.status_code == 400, r.text


def test_ai_query_returns_session_id_and_grounded_answer():
    q = "In one short sentence, what is my current win rate based on the data snapshot?"
    r = requests.post(f"{BASE}/api/analytics/ai_query", json={"question": q}, timeout=90)
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body.get("session_id"), str) and body["session_id"]
    assert isinstance(body.get("answer"), str) and len(body["answer"]) > 5
    # sanity: answer shouldn't be a raw error dump
    assert "traceback" not in body["answer"].lower()


def test_ai_query_multi_turn_reuses_session_context():
    # turn 1
    r1 = requests.post(f"{BASE}/api/analytics/ai_query",
                       json={"question": "Give me one number: how many closed trades are in the snapshot? Just the number."},
                       timeout=90)
    assert r1.status_code == 200, r1.text
    sid = r1.json()["session_id"]
    # small pause to avoid overlapping ts inserts confusing ordering (defensive)
    time.sleep(1)
    # turn 2 reuses session_id — question is deliberately dependent on prior context
    r2 = requests.post(f"{BASE}/api/analytics/ai_query",
                       json={"question": "Now double that number and reply with only the doubled integer.",
                             "session_id": sid},
                       timeout=90)
    assert r2.status_code == 200, r2.text
    assert r2.json()["session_id"] == sid  # same session preserved
    assert isinstance(r2.json().get("answer"), str) and len(r2.json()["answer"]) > 0


def test_ai_query_requires_owner_when_no_auth_header():
    """Direct urllib to bypass conftest's auto-auth patch (which only patches requests.Session)."""
    import urllib.request as ur
    import urllib.error as ue
    import json as _json
    req = ur.Request(
        f"{BASE}/api/analytics/ai_query",
        data=_json.dumps({"question": "hi"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        ur.urlopen(req, timeout=15)
        assert False, "expected 401/403 without owner token"
    except ue.HTTPError as e:
        assert e.code in (401, 403), f"expected 401/403, got {e.code}"
