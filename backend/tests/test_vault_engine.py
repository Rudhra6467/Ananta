"""Tests for the Vault Engine (live capital sourcing) in trading_engine.apply_vault_sync.

The Vault Engine pulls the free USD/USDC balance from the exchange and caps the
bot's deployable cash at vault_max_override_usd. It must NEVER touch PAPER mode.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from models import Portfolio, RiskSettings
from trading_engine import apply_vault_sync


class _FakeExecutor:
    def __init__(self, free):
        self._free = free

    async def fetch_free_quote_balance(self):
        return self._free


@pytest.mark.asyncio
async def test_vault_disabled_leaves_paper_cash_untouched():
    portfolio = Portfolio(cash=100.0)
    settings = RiskSettings(vault_sync_enabled=False, trading_mode="PAPER")
    ev = await apply_vault_sync(portfolio, settings)
    assert ev["vault_sync"] is False
    assert portfolio.cash == 100.0


@pytest.mark.asyncio
async def test_vault_enabled_ignored_in_paper_mode():
    portfolio = Portfolio(cash=100.0)
    settings = RiskSettings(vault_sync_enabled=True, trading_mode="PAPER")
    ev = await apply_vault_sync(portfolio, settings)
    assert ev["vault_sync"] is False
    assert portfolio.cash == 100.0  # paper sandbox never touched


@pytest.mark.asyncio
async def test_vault_caps_at_override_when_balance_larger():
    portfolio = Portfolio(cash=999.0)
    settings = RiskSettings(vault_sync_enabled=True, trading_mode="DRY_RUN",
                            vault_max_override_usd=100.0)
    with patch("trading_engine.get_dry_run_executor",
               return_value=(_FakeExecutor(5000.0), None)):
        ev = await apply_vault_sync(portfolio, settings)
    assert ev["vault_sync"] is True
    assert ev["deployable_cash_usd"] == 100.0  # capped by override ceiling
    assert portfolio.cash == 100.0


@pytest.mark.asyncio
async def test_vault_uses_live_balance_when_smaller_than_cap():
    portfolio = Portfolio(cash=999.0)
    settings = RiskSettings(vault_sync_enabled=True, trading_mode="DRY_RUN",
                            vault_max_override_usd=100.0)
    with patch("trading_engine.get_dry_run_executor",
               return_value=(_FakeExecutor(42.0), None)):
        ev = await apply_vault_sync(portfolio, settings)
    assert ev["vault_sync"] is True
    assert portfolio.cash == 42.0  # smaller live balance wins


@pytest.mark.asyncio
async def test_vault_handles_unavailable_balance():
    portfolio = Portfolio(cash=100.0)
    settings = RiskSettings(vault_sync_enabled=True, trading_mode="LIVE",
                            vault_max_override_usd=100.0)
    with patch("trading_engine.get_default_executor",
               return_value=(_FakeExecutor(None), None)):
        ev = await apply_vault_sync(portfolio, settings)
    assert ev["vault_sync"] == "balance_unavailable"
    assert portfolio.cash == 100.0  # unchanged on failure


@pytest.mark.asyncio
async def test_vault_handles_missing_executor():
    portfolio = Portfolio(cash=100.0)
    settings = RiskSettings(vault_sync_enabled=True, trading_mode="LIVE",
                            vault_max_override_usd=100.0)
    with patch("trading_engine.get_default_executor",
               return_value=(None, "no keys")):
        ev = await apply_vault_sync(portfolio, settings)
    assert ev["vault_sync"] == "executor_unavailable"
    assert portfolio.cash == 100.0
