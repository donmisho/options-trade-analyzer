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


# ── OTA-771: Normalization isolation parity tests ─────────────────────


def _wg_only_contracts(price=100.0):
    """Contracts that only fit Weekly Grind DTE (14-21d), not Steady Paycheck."""
    from datetime import date, timedelta

    contracts = []
    for dte_offset in [15, 18, 20]:
        exp = (date.today() + timedelta(days=dte_offset)).strftime("%Y-%m-%d")
        for strike_offset in [-8, -3, 0, 3, 8]:
            strike = price + strike_offset
            for opt_type in ["call", "put"]:
                contracts.append({
                    "strike": strike,
                    "option_type": opt_type,
                    "expiration": exp,
                    "bid": 1.80,
                    "ask": 2.20,
                    "mid": 2.00,
                    "last": 2.00,
                    "volume": 200,
                    "open_interest": 1000,
                    "implied_volatility": 0.45,
                    "delta": 0.40 if opt_type == "call" else -0.40,
                    "gamma": 0.06,
                    "theta": -0.04,
                    "vega": 0.12,
                })
    return contracts


def _sp_only_contracts(price=100.0):
    """Contracts that only fit Steady Paycheck DTE (14-45d)."""
    from datetime import date, timedelta

    contracts = []
    for dte_offset in [25, 35, 42]:
        exp = (date.today() + timedelta(days=dte_offset)).strftime("%Y-%m-%d")
        for strike_offset in [-10, -5, 0, 5, 10]:
            strike = price + strike_offset
            for opt_type in ["call", "put"]:
                contracts.append({
                    "strike": strike,
                    "option_type": opt_type,
                    "expiration": exp,
                    "bid": 3.00,
                    "ask": 3.50,
                    "mid": 3.25,
                    "last": 3.25,
                    "volume": 150,
                    "open_interest": 800,
                    "implied_volatility": 0.35,
                    "delta": 0.55 if opt_type == "call" else -0.55,
                    "gamma": 0.04,
                    "theta": -0.02,
                    "vega": 0.08,
                })
    return contracts


@pytest.mark.asyncio
async def test_sp_normalization_independent_of_wg_candidates():
    """OTA-771: SP normalized scores must be identical whether WG-eligible
    candidates are present or absent in the same chain.

    Run 1: SP contracts only.
    Run 2: SP contracts + WG-only contracts mixed together.
    SP scores must be byte-identical across both runs.
    """
    price = 100.0
    sp_contracts = _sp_only_contracts(price)
    wg_contracts = _wg_only_contracts(price)
    combined = sp_contracts + wg_contracts

    # Run 1: SP contracts only
    provider1 = AsyncMock()
    provider1.get_chain.return_value = {
        "contracts": sp_contracts,
        "underlying_price": price,
    }
    scores1, _ = await score_all_strategies("TEST", provider1)
    sp_score1 = next(s for s in scores1 if s.strategy_key == "steady-paycheck")

    # Run 2: SP + WG contracts combined
    provider2 = AsyncMock()
    provider2.get_chain.return_value = {
        "contracts": combined,
        "underlying_price": price,
    }
    scores2, _ = await score_all_strategies("TEST", provider2)
    sp_score2 = next(s for s in scores2 if s.strategy_key == "steady-paycheck")

    # SP scores must be identical — normalization is per-strategy
    assert sp_score1.score == sp_score2.score, (
        f"SP score changed: {sp_score1.score} (alone) vs {sp_score2.score} (with WG)"
    )
    assert sp_score1.metric_scores == sp_score2.metric_scores, (
        "SP metric_scores changed when WG candidates were added"
    )
    if sp_score1.component_breakdown and sp_score2.component_breakdown:
        assert sp_score1.component_breakdown == sp_score2.component_breakdown, (
            "SP component_breakdown changed when WG candidates were added"
        )
