"""Tests for the single-owner auth gate (Phase 3.5)."""
from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-32b+long")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import auth  # noqa: E402


def test_password_hash_roundtrip():
    h = auth.hash_password("S3cret!pw")
    assert h.startswith("$2b$")
    assert auth.verify_password("S3cret!pw", h) is True
    assert auth.verify_password("wrong", h) is False


def test_token_create_and_validate():
    tok = auth.create_access_token("owner@ananta.ai")
    p = auth._valid_owner_payload(tok)
    assert p is not None
    assert p["sub"] == "owner@ananta.ai"
    assert p["role"] == "owner"
    assert p["type"] == "access"


def test_tampered_token_rejected():
    assert auth._valid_owner_payload("not.a.jwt") is None
    assert auth._valid_owner_payload(auth.create_access_token("x") + "tamper") is None


class _FakeReq:
    def __init__(self, headers=None, cookies=None):
        self.headers = headers or {}
        self.cookies = cookies or {}


def test_is_owner_request():
    tok = auth.create_access_token("owner@ananta.ai")
    assert auth.is_owner_request(_FakeReq(headers={"Authorization": f"Bearer {tok}"})) is True
    assert auth.is_owner_request(_FakeReq()) is False
    assert auth.is_owner_request(_FakeReq(headers={"Authorization": "Bearer garbage"})) is False


@pytest.mark.asyncio
async def test_require_owner_403_without_token():
    with pytest.raises(HTTPException) as ei:
        await auth.require_owner(_FakeReq())
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_require_owner_401_on_expired_token():
    import jwt as _jwt
    from datetime import UTC, datetime, timedelta
    expired = _jwt.encode(
        {"sub": "owner@ananta.ai", "role": "owner", "type": "access",
         "exp": datetime.now(UTC) - timedelta(minutes=1)},
        auth._secret(), algorithm=auth.JWT_ALG)
    with pytest.raises(HTTPException) as ei:
        await auth.require_owner(_FakeReq(headers={"Authorization": f"Bearer {expired}"}))
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_require_owner_401_on_tampered_token():
    tok = auth.create_access_token("owner@ananta.ai") + "tamper"
    with pytest.raises(HTTPException) as ei:
        await auth.require_owner(_FakeReq(headers={"Authorization": f"Bearer {tok}"}))
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_require_owner_ok_with_token():
    tok = auth.create_access_token("owner@ananta.ai")
    p = await auth.require_owner(_FakeReq(headers={"Authorization": f"Bearer {tok}"}))
    assert p["role"] == "owner"
