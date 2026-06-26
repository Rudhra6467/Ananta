"""Shared pytest configuration.

Adds /app/backend to sys.path so the test files can import flat modules
(`live_execution`, `risk_engine`, etc.) regardless of the cwd pytest is
invoked from. Without this, running `pytest /app/backend/tests/...` from
/app raises ModuleNotFoundError.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# --- Owner auth injection for HTTP integration tests (Phase 3.5) ---
# Mutating endpoints are now 403-guarded. This autouse fixture logs in as the
# owner once and attaches the Bearer token to MUTATING requests only (POST/PUT/
# DELETE/PATCH) targeting the backend. GETs stay unauthenticated so public-view
# and secret-redaction tests keep exercising the read-only path.
import os  # noqa: E402
import re  # noqa: E402

import pytest  # noqa: E402
import requests  # noqa: E402

_MUTATING = {"POST", "PUT", "DELETE", "PATCH"}


def _owner_creds():
    email = os.environ.get("OWNER_EMAIL")
    pw = os.environ.get("OWNER_PASSWORD")
    if not (email and pw):
        envp = BACKEND_DIR / ".env"
        txt = envp.read_text() if envp.exists() else ""
        me = re.search(r'^OWNER_EMAIL="?([^"\n]+)', txt, re.M)
        mp = re.search(r'^OWNER_PASSWORD="?([^"\n]+)', txt, re.M)
        email = email or (me.group(1) if me else None)
        pw = pw or (mp.group(1) if mp else None)
    return email, pw


@pytest.fixture(scope="session", autouse=True)
def _inject_owner_auth():
    base = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    token = None
    if base:
        email, pw = _owner_creds()
        if email and pw:
            try:
                r = requests.post(f"{base}/api/auth/login",
                                  json={"email": email, "password": pw}, timeout=15)
                if r.status_code == 200:
                    token = r.json().get("token")
            except Exception:
                token = None
    if not token:
        yield
        return

    original = requests.sessions.Session.request

    def patched(self, method, url, **kwargs):
        if (method.upper() in _MUTATING and base and str(url).startswith(base)
                and "auth/login" not in str(url)):
            headers = dict(kwargs.get("headers") or {})
            has_auth = "Authorization" in headers or "Authorization" in {
                k.title(): v for k, v in self.headers.items()
            }
            if not has_auth:
                headers["Authorization"] = f"Bearer {token}"
                kwargs["headers"] = headers
        return original(self, method, url, **kwargs)

    requests.sessions.Session.request = patched
    yield
    requests.sessions.Session.request = original
