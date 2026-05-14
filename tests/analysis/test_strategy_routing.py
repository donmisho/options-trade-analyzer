"""
Tests for strategy-structure compatibility routing — OTA-636

Coverage:
1. Compatibility matrix: 4 strategies × all known structures
2. Scorer null contract: incompatible pairs → None
3. Scanner request shape: derived from compatible_structures
4. best_fit non-null selection
"""

import pytest

from app.analysis.strategy_routing import (
    is_compatible,
    get_compatible_strategies,
    get_spread_types_for_strategy,
    get_option_types_for_strategy,
    uses_vertical_engine,
    uses_long_option_engine,
    normalize_to_structure,
)
from app.analysis.strategy_definitions import STRATEGIES
from app.analysis.strategy_classifier import classify_best_strategy
from app.analysis.strategy_scorer import StrategyScore


# ─── Canonical matrix from business-rules.md ─────────────────────────────────
# SP/WG → credit structures only
# TR   → debit structures only
# LT   → single-leg longs only

ALL_STRUCTURES = [
    "bull_put_credit",
    "bear_call_credit",
    "bull_call_debit",
    "bear_put_debit",
    "long_call",
    "long_put",
]

EXPECTED_MATRIX = {
    "steady-paycheck": {"bull_put_credit", "bear_call_credit"},
    "weekly-grind":    {"bull_put_credit", "bear_call_credit"},
    "trend-rider":     {"bull_call_debit", "bear_put_debit"},
    "lottery-ticket":  {"long_call", "long_put"},
}


class TestCompatibilityMatrix:
    """4 strategies × all known structures — each cell asserts is_compatible matches the matrix."""

    @pytest.mark.parametrize("strategy_key", list(EXPECTED_MATRIX.keys()))
    @pytest.mark.parametrize("structure", ALL_STRUCTURES)
    def test_compatibility_cell(self, strategy_key, structure):
        expected = structure in EXPECTED_MATRIX[strategy_key]
        actual = is_compatible(strategy_key, structure)
        assert actual == expected, (
            f"is_compatible('{strategy_key}', '{structure}') = {actual}, expected {expected}"
        )

    def test_definitions_match_matrix(self):
        """Verify strategy_definitions.py compatible_structures match the canonical matrix."""
        for key, expected_set in EXPECTED_MATRIX.items():
            actual_set = set(STRATEGIES[key].compatible_structures)
            assert actual_set == expected_set, (
                f"STRATEGIES['{key}'].compatible_structures = {actual_set}, "
                f"expected {expected_set}"
            )

    def test_unknown_strategy_returns_false(self):
        assert is_compatible("nonexistent-strategy", "bull_put_credit") is False


class TestInverseLookup:
    """get_compatible_strategies returns the correct strategy keys for each structure."""

    def test_credit_structures(self):
        for structure in ["bull_put_credit", "bear_call_credit"]:
            strategies = get_compatible_strategies(structure)
            assert set(strategies) == {"steady-paycheck", "weekly-grind"}, (
                f"get_compatible_strategies('{structure}') = {strategies}"
            )

    def test_debit_structures(self):
        for structure in ["bull_call_debit", "bear_put_debit"]:
            strategies = get_compatible_strategies(structure)
            assert set(strategies) == {"trend-rider"}, (
                f"get_compatible_strategies('{structure}') = {strategies}"
            )

    def test_single_long_structures(self):
        for structure in ["long_call", "long_put"]:
            strategies = get_compatible_strategies(structure)
            assert set(strategies) == {"lottery-ticket"}, (
                f"get_compatible_strategies('{structure}') = {strategies}"
            )

    def test_unknown_structure_returns_empty(self):
        assert get_compatible_strategies("iron_condor") == []


class TestScannerRequestShape:
    """Derived engine parameters match compatible_structures."""

    def test_sp_spread_types(self):
        types = get_spread_types_for_strategy("steady-paycheck")
        assert set(types) == {"bull_put", "bear_call"}

    def test_wg_spread_types(self):
        types = get_spread_types_for_strategy("weekly-grind")
        assert set(types) == {"bull_put", "bear_call"}

    def test_tr_spread_types(self):
        types = get_spread_types_for_strategy("trend-rider")
        assert set(types) == {"bull_call", "bear_put"}

    def test_lt_has_no_spread_types(self):
        types = get_spread_types_for_strategy("lottery-ticket")
        assert types == []

    def test_tr_has_no_option_types(self):
        types = get_option_types_for_strategy("trend-rider")
        assert types == []

    def test_lt_option_types(self):
        types = get_option_types_for_strategy("lottery-ticket")
        assert set(types) == {"call", "put"}

    def test_sp_uses_vertical_engine(self):
        assert uses_vertical_engine("steady-paycheck") is True
        assert uses_long_option_engine("steady-paycheck") is False

    def test_lt_uses_long_option_engine(self):
        assert uses_long_option_engine("lottery-ticket") is True
        assert uses_vertical_engine("lottery-ticket") is False

    def test_tr_uses_vertical_engine(self):
        """TR uses debit verticals, not single-leg longs."""
        assert uses_vertical_engine("trend-rider") is True
        assert uses_long_option_engine("trend-rider") is False


class TestNormalizeToStructure:
    """Engine-level types map back to compatible_structures values."""

    def test_spread_type_mappings(self):
        assert normalize_to_structure(spread_type="bull_put") == "bull_put_credit"
        assert normalize_to_structure(spread_type="bear_call") == "bear_call_credit"
        assert normalize_to_structure(spread_type="bull_call") == "bull_call_debit"
        assert normalize_to_structure(spread_type="bear_put") == "bear_put_debit"

    def test_option_type_mappings(self):
        assert normalize_to_structure(option_type="call") == "long_call"
        assert normalize_to_structure(option_type="put") == "long_put"

    def test_unknown_returns_none(self):
        assert normalize_to_structure(spread_type="iron_condor") is None
        assert normalize_to_structure() is None


class TestBestFitNonNullSelection:
    """best_fit selects highest-scoring among non-null; None with reason when all-None."""

    def _make_score(self, key, score):
        return StrategyScore(
            strategy_key=key,
            label=key.replace("-", " ").title(),
            score=score,
            best_trade=None,
            signal_summary="",
            metric_scores={},
        )

    def test_best_fit_picks_highest_compatible(self):
        """Given TR=78, others None-equivalent (not in candidates), best_fit = trend-rider."""
        candidates = [self._make_score("trend-rider", 78)]
        result = classify_best_strategy(
            candidates, effective_dte=30, trade_structure="bear_put_debit",
        )
        assert result.best_fit == "trend-rider"
        assert result.score == 78

    def test_best_fit_filters_incompatible(self):
        """SP scores 90 but is incompatible with bear_put_debit; TR at 78 wins."""
        candidates = [
            self._make_score("steady-paycheck", 90),
            self._make_score("weekly-grind", 85),
            self._make_score("trend-rider", 78),
            self._make_score("lottery-ticket", 60),
        ]
        result = classify_best_strategy(
            candidates, effective_dte=30, trade_structure="bear_put_debit",
        )
        assert result.best_fit == "trend-rider"
        assert result.score == 78

    def test_all_incompatible_returns_none(self):
        """No strategy is compatible with 'iron_condor' → best_fit = None."""
        candidates = [
            self._make_score("steady-paycheck", 90),
            self._make_score("trend-rider", 78),
        ]
        result = classify_best_strategy(
            candidates, effective_dte=30, trade_structure="iron_condor",
        )
        assert result.best_fit is None
        assert "iron_condor" in result.reason

    def test_no_trade_structure_skips_structural_filter(self):
        """When trade_structure is None, all candidates are eligible (backward compat)."""
        candidates = [
            self._make_score("steady-paycheck", 90),
            self._make_score("trend-rider", 78),
        ]
        result = classify_best_strategy(candidates, effective_dte=30)
        assert result.best_fit == "steady-paycheck"

    def test_structural_plus_dte_filter(self):
        """TR compatible with bear_put_debit but DTE=5 is outside TR's range → None."""
        candidates = [
            self._make_score("trend-rider", 78),
            self._make_score("lottery-ticket", 60),
        ]
        result = classify_best_strategy(
            candidates, effective_dte=5, trade_structure="bear_put_debit",
        )
        # TR has min DTE 14, so it's filtered by DTE. LT is incompatible with bear_put_debit.
        assert result.best_fit is None
