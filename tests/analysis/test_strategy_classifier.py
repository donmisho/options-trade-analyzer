"""
Unit tests for app/analysis/strategy_classifier.py — OTA-506.

Tests verify that:
  - filter_strategies_by_effective_dte correctly applies inclusive DTE bounds
  - classify_best_strategy returns the highest-scoring viable strategy
  - "no viable strategy" is returned (not raised) when all strategies are filtered
  - AMZN warning-band regression: effective_dte=9 disqualifies TREND_RIDER
  - All boundary values (7, 14, 21, 45, 60) are treated as inclusive
"""

import pytest

from app.analysis.strategy_classifier import (
    StrategyClassification,
    classify_best_strategy,
    filter_strategies_by_effective_dte,
)
from app.analysis.strategy_definitions import STRATEGIES
from app.analysis.strategy_definitions import StrategyScore


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _score(key: str, score: int) -> StrategyScore:
    """Build a minimal StrategyScore for classifier tests."""
    labels = {
        "trend-rider":     "Trend Rider",
        "steady-paycheck": "Steady Paycheck",
        "weekly-grind":    "Weekly Grind",
        "lottery-ticket":  "Lottery Ticket",
    }
    return StrategyScore(
        strategy_key=key,
        label=labels.get(key, key),
        score=score,
        best_trade=None,
        signal_summary="",
        metric_scores={},
    )


def _all_four(
    tr_score: int = 71,
    sp_score: int = 60,
    wg_score: int = 55,
    lt_score: int = 40,
) -> list:
    """All four strategies with configurable scores. Default: TR wins."""
    return [
        _score("trend-rider",     tr_score),
        _score("steady-paycheck", sp_score),
        _score("weekly-grind",    wg_score),
        _score("lottery-ticket",  lt_score),
    ]


# ─── AMZN warning-band regression ─────────────────────────────────────────────
# Trade: AMZN, earnings 10 days from entry (warning band — not hard PASS).
# Earnings gate sets effective_DTE = 9.
# TREND_RIDER min=14 → disqualified.
# Expected best fit: LOTTERY_TICKET (only viable strategy at dte=9).

class TestAmznWarningBandRegression:
    """effective_dte=9: earnings in warning band, TR/SP/WG all disqualified."""

    def test_trend_rider_not_selected(self):
        """TREND_RIDER must be disqualified when effective_dte=9 (< min 14)."""
        result = classify_best_strategy(_all_four(), effective_dte=9)
        assert result.best_fit != "trend-rider", (
            f"TREND_RIDER must be disqualified at dte=9; got best_fit={result.best_fit!r}"
        )

    def test_lottery_ticket_wins(self):
        """LOTTERY_TICKET is the only viable strategy at effective_dte=9."""
        result = classify_best_strategy(_all_four(), effective_dte=9)
        assert result.best_fit == "lottery-ticket", (
            f"Expected lottery-ticket at dte=9; got {result.best_fit!r}"
        )

    def test_effective_dte_in_reason(self):
        """Reason string must include the effective DTE value."""
        result = classify_best_strategy(_all_four(), effective_dte=9)
        assert "9" in result.reason

    def test_dte_source_payload_fields(self):
        """Classifier result carries score of the winner."""
        result = classify_best_strategy(_all_four(lt_score=40), effective_dte=9)
        assert result.score == 40


# ─── Nominal DTE regression ───────────────────────────────────────────────────

class TestNominalDteRegression:
    """
    effective_dte=22: no earnings gate fired; TR/SP/LT viable, WG filtered (max=21).
    Key property: TREND_RIDER is still viable and can win.
    """

    def test_three_strategies_viable_at_22(self):
        """WG max=21 → filtered at dte=22. TR, SP, LT remain."""
        viable = filter_strategies_by_effective_dte(_all_four(), effective_dte=22)
        keys = {c.strategy_key for c in viable}
        assert keys == {"trend-rider", "steady-paycheck", "lottery-ticket"}

    def test_trend_rider_can_win(self):
        """With highest score and all strategies viable, TR must be selected."""
        result = classify_best_strategy(_all_four(tr_score=71), effective_dte=22)
        assert result.best_fit == "trend-rider"
        assert result.score == 71


# ─── Sub-7 DTE: no viable strategy ────────────────────────────────────────────

class TestSubSevenDte:
    """effective_dte=3: all strategies filtered — return no viable strategy."""

    def test_no_viable_strategy_returned(self):
        result = classify_best_strategy(_all_four(), effective_dte=3)
        assert result.best_fit is None

    def test_no_viable_reason_string(self):
        result = classify_best_strategy(_all_four(), effective_dte=3)
        assert "No viable strategy" in result.reason
        assert "3" in result.reason

    def test_no_viable_score_is_none(self):
        result = classify_best_strategy(_all_four(), effective_dte=3)
        assert result.score is None


# ─── Boundary: effective_dte=14 ───────────────────────────────────────────────

class TestBoundary14:
    """
    effective_dte=14 is the inclusive minimum for TR, SP, WG.
    LOTTERY_TICKET min=7 → also viable.
    All four strategies must qualify.
    """

    def test_all_four_viable(self):
        viable = filter_strategies_by_effective_dte(_all_four(), effective_dte=14)
        keys = {c.strategy_key for c in viable}
        assert keys == {"trend-rider", "steady-paycheck", "weekly-grind", "lottery-ticket"}, (
            f"Expected all four at dte=14; got {keys}"
        )

    def test_dte_13_filters_tr_sp_wg(self):
        """One below the boundary: TR, SP, WG drop out; only LT remains."""
        viable = filter_strategies_by_effective_dte(_all_four(), effective_dte=13)
        keys = {c.strategy_key for c in viable}
        assert keys == {"lottery-ticket"}, (
            f"Only lottery-ticket viable at dte=13; got {keys}"
        )


# ─── Boundary: effective_dte=21 ───────────────────────────────────────────────

class TestBoundary21:
    """
    effective_dte=21 is the inclusive maximum for weekly-grind.
    WG must still be viable; all four viable.
    """

    def test_weekly_grind_still_viable(self):
        viable = filter_strategies_by_effective_dte(_all_four(), effective_dte=21)
        keys = {c.strategy_key for c in viable}
        assert "weekly-grind" in keys, f"WG must be viable at dte=21; got {keys}"

    def test_all_four_viable(self):
        viable = filter_strategies_by_effective_dte(_all_four(), effective_dte=21)
        keys = {c.strategy_key for c in viable}
        assert keys == {"trend-rider", "steady-paycheck", "weekly-grind", "lottery-ticket"}

    def test_dte_22_filters_weekly_grind(self):
        """One above WG max: WG drops out, remaining three viable."""
        viable = filter_strategies_by_effective_dte(_all_four(), effective_dte=22)
        keys = {c.strategy_key for c in viable}
        assert "weekly-grind" not in keys, (
            f"WG must be filtered at dte=22; got {keys}"
        )
        assert {"trend-rider", "steady-paycheck", "lottery-ticket"}.issubset(keys)


# ─── Boundary: effective_dte=45 ───────────────────────────────────────────────

class TestBoundary45:
    """
    effective_dte=45 is the inclusive maximum for steady-paycheck.
    SP viable; TR viable; LT viable; WG (max=21) filtered.
    """

    def test_steady_paycheck_still_viable(self):
        viable = filter_strategies_by_effective_dte(_all_four(), effective_dte=45)
        keys = {c.strategy_key for c in viable}
        assert "steady-paycheck" in keys

    def test_weekly_grind_filtered(self):
        viable = filter_strategies_by_effective_dte(_all_four(), effective_dte=45)
        keys = {c.strategy_key for c in viable}
        assert "weekly-grind" not in keys

    def test_viable_set(self):
        viable = filter_strategies_by_effective_dte(_all_four(), effective_dte=45)
        keys = {c.strategy_key for c in viable}
        assert keys == {"trend-rider", "steady-paycheck", "lottery-ticket"}

    def test_dte_46_filters_steady_paycheck(self):
        """One above SP max: SP drops out, TR and LT remain."""
        viable = filter_strategies_by_effective_dte(_all_four(), effective_dte=46)
        keys = {c.strategy_key for c in viable}
        assert "steady-paycheck" not in keys
        assert {"trend-rider", "lottery-ticket"}.issubset(keys)


# ─── Boundary: effective_dte=60 ───────────────────────────────────────────────

class TestBoundary60:
    """
    effective_dte=60 is the inclusive maximum for both trend-rider and lottery-ticket.
    TR viable; LT viable; SP (max=45) filtered; WG (max=21) filtered.
    """

    def test_trend_rider_still_viable(self):
        viable = filter_strategies_by_effective_dte(_all_four(), effective_dte=60)
        keys = {c.strategy_key for c in viable}
        assert "trend-rider" in keys

    def test_lottery_ticket_still_viable(self):
        viable = filter_strategies_by_effective_dte(_all_four(), effective_dte=60)
        keys = {c.strategy_key for c in viable}
        assert "lottery-ticket" in keys

    def test_sp_and_wg_filtered(self):
        viable = filter_strategies_by_effective_dte(_all_four(), effective_dte=60)
        keys = {c.strategy_key for c in viable}
        assert "steady-paycheck" not in keys
        assert "weekly-grind" not in keys

    def test_viable_set(self):
        viable = filter_strategies_by_effective_dte(_all_four(), effective_dte=60)
        keys = {c.strategy_key for c in viable}
        assert keys == {"trend-rider", "lottery-ticket"}


# ─── Over 60: no viable strategy ──────────────────────────────────────────────

class TestOver60:
    """effective_dte=90: all strategies exceed their max → no viable strategy."""

    def test_no_viable_strategy(self):
        result = classify_best_strategy(_all_four(), effective_dte=90)
        assert result.best_fit is None

    def test_reason_contains_dte(self):
        result = classify_best_strategy(_all_four(), effective_dte=90)
        assert "90" in result.reason
        assert "No viable strategy" in result.reason


# ─── No viable strategy path — explicit test ──────────────────────────────────

class TestNoViableStrategyPath:
    """Confirm no-viable-strategy is a valid output, not an exception."""

    def test_returns_classification_not_exception(self):
        result = classify_best_strategy(_all_four(), effective_dte=3)
        assert isinstance(result, StrategyClassification)

    def test_best_fit_is_none(self):
        result = classify_best_strategy([], effective_dte=22)
        assert result.best_fit is None

    def test_empty_candidates_no_viable(self):
        result = classify_best_strategy([], effective_dte=22)
        assert "No viable strategy" in result.reason


# ─── Tie-breaking: highest score wins ─────────────────────────────────────────

class TestHighestScoreWins:
    """When multiple strategies are viable, the one with highest score wins."""

    def test_highest_score_selected(self):
        candidates = [
            _score("trend-rider",     50),
            _score("steady-paycheck", 85),  # highest
            _score("lottery-ticket",  40),
        ]
        result = classify_best_strategy(candidates, effective_dte=30)
        assert result.best_fit == "steady-paycheck"
        assert result.score == 85

    def test_lottery_ticket_wins_when_highest(self):
        candidates = [
            _score("trend-rider",     30),
            _score("lottery-ticket",  90),  # highest
        ]
        result = classify_best_strategy(candidates, effective_dte=30)
        assert result.best_fit == "lottery-ticket"


# ─── STRATEGIES DTE integrity (OTA-772: consolidated from STRATEGY_DTE_REQUIREMENTS)

class TestStrategiesDteIntegrity:
    """Sanity-check the canonical STRATEGIES DTE fields."""

    def test_all_four_keys_present(self):
        assert {"trend-rider", "steady-paycheck", "weekly-grind", "lottery-ticket"}.issubset(
            STRATEGIES.keys()
        )

    def test_all_have_valid_dte_range(self):
        for key in ("trend-rider", "steady-paycheck", "weekly-grind", "lottery-ticket"):
            s = STRATEGIES[key]
            assert s.dte_min <= s.dte_max, f"{key}: dte_min > dte_max"

    def test_trend_rider_values(self):
        s = STRATEGIES["trend-rider"]
        assert (s.dte_min, s.dte_max) == (14, 60)

    def test_steady_paycheck_values(self):
        s = STRATEGIES["steady-paycheck"]
        assert (s.dte_min, s.dte_max) == (14, 45)

    def test_weekly_grind_values(self):
        s = STRATEGIES["weekly-grind"]
        assert (s.dte_min, s.dte_max) == (14, 21)

    def test_lottery_ticket_values(self):
        s = STRATEGIES["lottery-ticket"]
        assert (s.dte_min, s.dte_max) == (7, 60)
