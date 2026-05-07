"""
Regression test for OTA-558: naked option evaluation user message construction.

Verifies that _build_structured_user_message handles both vertical spread and
naked option (put/call) trade dicts without serialization failure, including
edge cases with NaN/Infinity values from scoring.

Repro symbols: GOOG calls, GOOG puts.
"""

import math
import pytest

from app.api.evaluation_routes import _build_structured_user_message


# ─── Fixtures ────────────────────────────────────────────────────────────────

VERTICAL_TRADE = {
    "long_strike": 180.0,
    "short_strike": 185.0,
    "expiration": "2026-06-20",
    "net_debit": -1.85,
    "spread_width": 5.0,
    "max_profit": 185.0,
    "max_loss": 315.0,
    "prob_of_profit": 0.62,
    "reward_risk_ratio": 0.59,
    "composite_score": 72.5,
    "spread_label": "180/185 Put Spread",
    "spread_type": "bear_put_debit",
}

NAKED_PUT_TRADE = {
    "strike": 175.0,
    "expiration": "2026-06-20",
    "days_to_exp": 45,
    "option_type": "put",
    "bid": 3.10,
    "ask": 3.30,
    "mid_price": 3.20,
    "premium_dollars": 320.0,
    "delta": -0.32,
    "gamma": 0.015,
    "theta": -0.04,
    "vega": 0.18,
    "iv": 0.28,
    "volume": 1500,
    "open_interest": 8000,
    "bid_ask_spread_pct": 6.45,
    "breakeven": 171.80,
    "breakeven_distance_pct": 1.68,
    "theta_per_day_dollars": 4.0,
    "theta_runway_days": 80.0,
    "composite_score": 78.4,
}

NAKED_CALL_TRADE = {
    "strike": 195.0,
    "expiration": "2026-06-20",
    "days_to_exp": 45,
    "option_type": "call",
    "bid": 2.80,
    "ask": 3.05,
    "mid_price": 2.93,
    "premium_dollars": 293.0,
    "delta": 0.35,
    "gamma": 0.012,
    "theta": -0.035,
    "vega": 0.16,
    "iv": 0.26,
    "volume": 2200,
    "open_interest": 12000,
    "bid_ask_spread_pct": 8.53,
    "breakeven": 197.93,
    "breakeven_distance_pct": 4.07,
    "theta_per_day_dollars": 3.5,
    "theta_runway_days": 83.7,
    "composite_score": 81.2,
}

# Edge case: NaN/Infinity values that can appear from division-by-zero in scoring
NAKED_TRADE_WITH_NAN = {
    **NAKED_PUT_TRADE,
    "theta_runway_days": float("inf"),
    "bid_ask_spread_pct": float("nan"),
}


# ─── Tests ───────────────────────────────────────────────────────────────────

def test_vertical_trade_builds_message():
    """Vertical spread trade dict produces a valid user message string."""
    msg = _build_structured_user_message(
        symbol="GOOG",
        current_price=185.0,
        iv=0.28,
        sma_alignment={"sma_8": 186.0, "sma_21": 183.5, "sma_50": 180.0, "alignment": "bullish"},
        strategy_keys=["steady-paycheck"],
        scores={"steady-paycheck": 72},
        trade=VERTICAL_TRADE,
        current_date="2026-05-06",
    )
    assert "GOOG" in msg
    assert "steady-paycheck" in msg
    assert "Trade data:" in msg


def test_naked_put_builds_message():
    """OTA-558 regression: naked put trade dict produces a valid user message."""
    msg = _build_structured_user_message(
        symbol="GOOG",
        current_price=185.0,
        iv=0.28,
        sma_alignment={"sma_8": 186.0, "sma_21": 183.5, "sma_50": 180.0, "alignment": "bullish"},
        strategy_keys=["trend-rider"],
        scores={"trend-rider": 78},
        trade=NAKED_PUT_TRADE,
        current_date="2026-05-06",
    )
    assert "GOOG" in msg
    assert "trend-rider" in msg
    assert "Trade data:" in msg
    assert '"option_type": "put"' in msg


def test_naked_call_builds_message():
    """OTA-558 regression: naked call trade dict produces a valid user message."""
    msg = _build_structured_user_message(
        symbol="GOOG",
        current_price=185.0,
        iv=0.28,
        sma_alignment={"sma_8": 186.0, "sma_21": 183.5, "sma_50": 180.0, "alignment": "bullish"},
        strategy_keys=["trend-rider"],
        scores={"trend-rider": 81},
        trade=NAKED_CALL_TRADE,
        current_date="2026-05-06",
    )
    assert "GOOG" in msg
    assert "trend-rider" in msg
    assert "Trade data:" in msg
    assert '"option_type": "call"' in msg


def test_trade_with_nan_infinity_builds_message():
    """OTA-558 regression: NaN/Infinity in trade dict doesn't crash serialization."""
    msg = _build_structured_user_message(
        symbol="GOOG",
        current_price=185.0,
        iv=0.28,
        sma_alignment={"sma_8": 186.0, "sma_21": 183.5, "sma_50": 180.0, "alignment": "bullish"},
        strategy_keys=["trend-rider"],
        scores={},
        trade=NAKED_TRADE_WITH_NAN,
        current_date="2026-05-06",
    )
    assert "GOOG" in msg
    assert "Trade data:" in msg
    # NaN/Infinity should NOT appear as literal values in the JSON
    assert "Infinity" not in msg
    assert "NaN" not in msg


def test_empty_sma_alignment_builds_message():
    """Empty sma_alignment dict doesn't crash the message builder."""
    msg = _build_structured_user_message(
        symbol="GOOG",
        current_price=185.0,
        iv=0.28,
        sma_alignment={},
        strategy_keys=["trend-rider"],
        scores={},
        trade=NAKED_CALL_TRADE,
        current_date="2026-05-06",
    )
    assert "N/A" in msg  # defaults to N/A for missing SMAs


def test_none_trade_builds_message():
    """None trade dict doesn't crash the message builder."""
    msg = _build_structured_user_message(
        symbol="GOOG",
        current_price=185.0,
        iv=0.28,
        sma_alignment={"sma_8": 186.0, "sma_21": 183.5, "sma_50": 180.0, "alignment": "bullish"},
        strategy_keys=["steady-paycheck"],
        scores={},
        trade=None,
        current_date="2026-05-06",
    )
    assert "GOOG" in msg
    assert "Trade data:" not in msg
