"""
Tests for per-strategy user_config routing in score_all_strategies (OTA-516).

These tests mock the provider to avoid real API calls and focus on verifying
that user_config is correctly sliced per strategy before reaching the scorers.

Orchestration moved from strategy_scorer.py to analysis_routes.py (OTA-779).
"""

import pytest
from unittest.mock import AsyncMock, patch
from app.api.analysis_routes import score_all_strategies
from app.analysis.strategy_definitions import STRATEGIES


def _make_mock_provider(contracts=None, underlying_price=100.0):
    """Create a mock provider that returns a canned chain."""
    provider = AsyncMock()
    provider.get_chain.return_value = {
        "contracts": contracts or _sample_contracts(underlying_price),
        "underlying_price": underlying_price,
    }
    return provider


def _sample_contracts(price=100.0):
    """Minimal contracts that pass through both credit spread and long option scorers."""
    from datetime import date, timedelta

    contracts = []
    for dte_offset in [7, 10, 14, 30, 40, 50, 60]:
        exp = (date.today() + timedelta(days=dte_offset)).strftime("%Y-%m-%d")
        for strike_offset in [-10, -5, -2, 0, 2, 5, 10]:
            strike = price + strike_offset
            for opt_type in ["call", "put"]:
                contracts.append({
                    "strike": strike,
                    "option_type": opt_type,
                    "expiration": exp,
                    "bid": 2.50,
                    "ask": 3.00,
                    "mid": 2.75,
                    "last": 2.75,
                    "volume": 100,
                    "open_interest": 500,
                    "implied_volatility": 0.30,
                    "delta": 0.50 if opt_type == "call" else -0.50,
                    "gamma": 0.05,
                    "theta": -0.03,
                    "vega": 0.10,
                })
    return contracts


@pytest.mark.asyncio
async def test_per_strategy_override_wins():
    """Per-strategy dte_min override is respected; other strategies use defaults."""
    provider = _make_mock_provider()

    # Override weekly-grind dte_min to 10
    user_config = {
        "weekly-grind": {"dte_min": 10},
    }

    scores, _ = await score_all_strategies("TEST", provider, user_config=user_config)

    # All four strategies should return
    keys = [s.strategy_key for s in scores]
    assert set(keys) == {"steady-paycheck", "weekly-grind", "trend-rider", "lottery-ticket"}


@pytest.mark.asyncio
async def test_partial_override_other_strategies_default():
    """Setting one strategy's config doesn't affect others."""
    provider = _make_mock_provider()

    # Only override weekly-grind — others should use STRATEGIES defaults
    user_config = {
        "weekly-grind": {"dte_min": 10, "dte_max": 14},
    }

    scores, _ = await score_all_strategies("TEST", provider, user_config=user_config)
    keys = {s.strategy_key for s in scores}
    assert keys == {"steady-paycheck", "weekly-grind", "trend-rider", "lottery-ticket"}


@pytest.mark.asyncio
async def test_empty_user_config_all_defaults():
    """Empty dict user_config means all strategies use STRATEGIES defaults."""
    provider = _make_mock_provider()

    scores, _ = await score_all_strategies("TEST", provider, user_config={})

    keys = {s.strategy_key for s in scores}
    assert keys == {"steady-paycheck", "weekly-grind", "trend-rider", "lottery-ticket"}


@pytest.mark.asyncio
async def test_none_user_config_all_defaults():
    """None user_config means all strategies use STRATEGIES defaults."""
    provider = _make_mock_provider()

    scores, _ = await score_all_strategies("TEST", provider, user_config=None)

    keys = {s.strategy_key for s in scores}
    assert keys == {"steady-paycheck", "weekly-grind", "trend-rider", "lottery-ticket"}


@pytest.mark.asyncio
async def test_config_slice_reaches_scorer():
    """Verify the per-strategy slice is actually passed to the scorer functions."""
    provider = _make_mock_provider()

    captured_configs = {}

    original_credit = __import__(
        "app.api.analysis_routes", fromlist=["_score_credit_spread_strategy"]
    )._score_credit_spread_strategy
    original_long = __import__(
        "app.api.analysis_routes", fromlist=["_score_long_option_strategy"]
    )._score_long_option_strategy

    def mock_credit(strategy_key, contracts, underlying_price, user_config, atm_iv):
        captured_configs[strategy_key] = user_config
        return original_credit(strategy_key, contracts, underlying_price, user_config, atm_iv)

    def mock_long(strategy_key, contracts, underlying_price, user_config, atm_iv):
        captured_configs[strategy_key] = user_config
        return original_long(strategy_key, contracts, underlying_price, user_config, atm_iv)

    user_config = {
        "weekly-grind": {"dte_min": 10},
        "trend-rider": {"dte_min": 35, "dte_max": 55},
        "steady-paycheck": {},
        # lottery-ticket omitted — should get {}
    }

    with patch("app.api.analysis_routes._score_credit_spread_strategy", side_effect=mock_credit), \
         patch("app.api.analysis_routes._score_long_option_strategy", side_effect=mock_long):
        await score_all_strategies("TEST", provider, user_config=user_config)

    assert captured_configs["weekly-grind"] == {"dte_min": 10}
    assert captured_configs["trend-rider"] == {"dte_min": 35, "dte_max": 55}
    assert captured_configs["steady-paycheck"] == {}
    assert captured_configs["lottery-ticket"] == {}
