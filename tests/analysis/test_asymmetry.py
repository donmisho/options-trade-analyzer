"""
Unit tests for app/analysis/scoring_factors/asymmetry.py (OTA-505)

Covers asymmetry_penalty() boundary conditions, edge cases, and the AMZN
regression case that motivated this factor.
"""

import pytest
from app.analysis.scoring_factors.asymmetry import asymmetry_penalty, asymmetry_ratio


# ─── asymmetry_penalty ────────────────────────────────────────────────────────

class TestAsymmetryPenalty:

    def test_amzn_regression(self):
        """AMZN 260/270 May 15: ratio ≈ 1.898 → penalty = 15."""
        assert asymmetry_penalty(0.5666, 0.2985) == 15

    def test_favorable_skew(self):
        """Loss prob < profit prob → no penalty."""
        assert asymmetry_penalty(0.30, 0.50) == 0

    def test_boundary_exactly_1_25(self):
        """ratio == 1.25 → 8 (inclusive lower bound of second tier)."""
        # p_max_loss / p_max_profit = 1.25 exactly
        assert asymmetry_penalty(0.25, 0.20) == 8

    def test_boundary_just_below_1_25(self):
        """ratio < 1.25 → 0."""
        # 0.249 / 0.200 = 1.245
        assert asymmetry_penalty(0.249, 0.200) == 0

    def test_boundary_exactly_1_5(self):
        """ratio == 1.5 → 15 (inclusive lower bound of third tier).
        Use 3.0/2.0 which is exactly 1.5 in IEEE 754 (0.30/0.20 is 1.4999... due to fp)."""
        assert asymmetry_penalty(3.0, 2.0) == 15

    def test_boundary_just_below_1_5(self):
        """ratio just under 1.5 → 8 (stays in second tier)."""
        # 0.2999 / 0.2001 ≈ 1.4988 < 1.5
        assert asymmetry_penalty(0.2999, 0.2001) == 8

    def test_boundary_exactly_2_0(self):
        """ratio == 2.0 → 25 (inclusive lower bound of max tier)."""
        assert asymmetry_penalty(0.40, 0.20) == 25

    def test_boundary_just_above_2_0(self):
        """ratio > 2.0 → 25 (max tier)."""
        assert asymmetry_penalty(0.4002, 0.2001) == 25

    def test_zero_profit_probability(self):
        """p_max_profit == 0 → max penalty 25 (explicit early return, no division)."""
        assert asymmetry_penalty(0.50, 0.0) == 25

    def test_null_p_max_loss(self):
        """Missing p_max_loss → 0 penalty (don't punish for missing data)."""
        assert asymmetry_penalty(None, 0.30) == 0

    def test_null_p_max_profit(self):
        """Missing p_max_profit → 0 penalty."""
        assert asymmetry_penalty(0.50, None) == 0

    def test_both_null(self):
        """Both None → 0 penalty."""
        assert asymmetry_penalty(None, None) == 0

    def test_equal_probabilities(self):
        """Equal loss and profit probability → ratio 1.0 → 0 penalty."""
        assert asymmetry_penalty(0.30, 0.30) == 0

    def test_returns_int(self):
        """Return type must be int, not float."""
        result = asymmetry_penalty(0.5666, 0.2985)
        assert isinstance(result, int)


# ─── asymmetry_ratio ──────────────────────────────────────────────────────────

class TestAsymmetryRatio:

    def test_amzn_regression(self):
        """AMZN case: ratio ≈ 1.898."""
        result = asymmetry_ratio(0.5666, 0.2985)
        assert result is not None
        assert abs(result - 1.898) < 0.01

    def test_null_p_max_loss(self):
        assert asymmetry_ratio(None, 0.30) is None

    def test_null_p_max_profit(self):
        assert asymmetry_ratio(0.50, None) is None

    def test_both_null(self):
        assert asymmetry_ratio(None, None) is None

    def test_zero_profit_probability(self):
        """p_max_profit == 0 → None (ratio undefined)."""
        assert asymmetry_ratio(0.50, 0.0) is None

    def test_favorable_skew(self):
        """Loss < profit → ratio < 1.0."""
        result = asymmetry_ratio(0.30, 0.50)
        assert result is not None
        assert abs(result - 0.60) < 0.001
