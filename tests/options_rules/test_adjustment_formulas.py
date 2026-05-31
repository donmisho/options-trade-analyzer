"""
Tests for the post-scoring adjustment formulas.

OTA-728: cushion_penalty_moderate (bool-returning)
OTA-729: probability_asymmetry_penalty (numeric-returning)

Tests validate:
- Registration in the live registry
- Correct return types (bool vs float)
- Band boundary behavior
- Legacy parity with strategy_scorer.py and asymmetry.py
- Null/missing input handling
"""

from __future__ import annotations

import pytest

from app.options_rules.screening import get_registry


# ── Registration ─────────────────────────────────────────────────────────


class TestAdjustmentRegistration:
    def test_cushion_penalty_moderate_registered(self):
        reg = get_registry()
        assert reg.has("cushion_penalty_moderate")

    def test_probability_asymmetry_penalty_registered(self):
        reg = get_registry()
        assert reg.has("probability_asymmetry_penalty")


# ── OTA-728: cushion_penalty_moderate ─────────────────────────────────────


class TestCushionPenaltyModerate:
    """Bool-returning formula. False = in penalty band, True = pass."""

    def test_below_lower_threshold_passes(self):
        """cushion_pct < 1.0 is handled by the severe rule, not this one."""
        reg = get_registry()
        result = reg.invoke("cushion_penalty_moderate",
            {"cushion_pct": 0.5}, {"lower_threshold": 1.0, "upper_threshold": 2.0})
        assert result is True

    def test_at_lower_threshold_triggers(self):
        """cushion_pct == 1.0 is in the moderate band [1.0, 2.0)."""
        reg = get_registry()
        result = reg.invoke("cushion_penalty_moderate",
            {"cushion_pct": 1.0}, {"lower_threshold": 1.0, "upper_threshold": 2.0})
        assert result is False

    def test_mid_band_triggers(self):
        """cushion_pct == 1.5 is in the moderate band."""
        reg = get_registry()
        result = reg.invoke("cushion_penalty_moderate",
            {"cushion_pct": 1.5}, {"lower_threshold": 1.0, "upper_threshold": 2.0})
        assert result is False

    def test_at_upper_threshold_passes(self):
        """cushion_pct == 2.0 is outside [1.0, 2.0) — no penalty."""
        reg = get_registry()
        result = reg.invoke("cushion_penalty_moderate",
            {"cushion_pct": 2.0}, {"lower_threshold": 1.0, "upper_threshold": 2.0})
        assert result is True

    def test_above_upper_threshold_passes(self):
        reg = get_registry()
        result = reg.invoke("cushion_penalty_moderate",
            {"cushion_pct": 5.0}, {"lower_threshold": 1.0, "upper_threshold": 2.0})
        assert result is True

    def test_missing_cushion_pct_passes(self):
        """Null input → no penalty."""
        reg = get_registry()
        result = reg.invoke("cushion_penalty_moderate",
            {}, {"lower_threshold": 1.0, "upper_threshold": 2.0})
        assert result is True

    def test_returns_bool_type(self):
        """Engine checks isinstance(result, bool) — must be actual bool."""
        reg = get_registry()
        result = reg.invoke("cushion_penalty_moderate",
            {"cushion_pct": 1.5}, {"lower_threshold": 1.0, "upper_threshold": 2.0})
        assert isinstance(result, bool)

    def test_missing_params_raises(self):
        """Params are required from junction (OTA-770); missing raises KeyError."""
        reg = get_registry()
        with pytest.raises(KeyError):
            reg.invoke("cushion_penalty_moderate", {"cushion_pct": 1.5}, {})

    def test_custom_thresholds(self):
        """Params override the band boundaries."""
        reg = get_registry()
        result = reg.invoke("cushion_penalty_moderate",
            {"cushion_pct": 3.0}, {"lower_threshold": 2.5, "upper_threshold": 4.0})
        assert result is False

    def test_legacy_parity_band_mapping(self):
        """Legacy strategy_scorer.py:138-142 band mapping.

        pct < 1.0  → -20 (severe rule, not this formula)
        pct in [1.0, 2.0) → -10 (this formula returns False)
        pct >= 2.0 → 0 (this formula returns True)
        """
        reg = get_registry()
        params = {"lower_threshold": 1.0, "upper_threshold": 2.0}

        # Severe band — not our responsibility, we pass
        assert reg.invoke("cushion_penalty_moderate", {"cushion_pct": 0.5}, params) is True
        # Moderate band — we trigger
        assert reg.invoke("cushion_penalty_moderate", {"cushion_pct": 1.0}, params) is False
        assert reg.invoke("cushion_penalty_moderate", {"cushion_pct": 1.99}, params) is False
        # Safe — we pass
        assert reg.invoke("cushion_penalty_moderate", {"cushion_pct": 2.0}, params) is True


# ── OTA-729: probability_asymmetry_penalty ────────────────────────────────


class TestProbabilityAsymmetryPenalty:
    """Numeric-returning formula. Returns negative penalty or 0.0."""

    def test_severe_band(self):
        """ratio >= 2.0 → -25."""
        reg = get_registry()
        result = reg.invoke("probability_asymmetry_penalty",
            {"p_max_loss": 80, "p_max_profit": 20}, {})
        assert result == -25

    def test_high_band(self):
        """ratio >= 1.5 and < 2.0 → -15."""
        reg = get_registry()
        result = reg.invoke("probability_asymmetry_penalty",
            {"p_max_loss": 75, "p_max_profit": 50}, {})
        assert result == -15

    def test_moderate_band(self):
        """ratio >= 1.25 and < 1.5 → -8."""
        reg = get_registry()
        result = reg.invoke("probability_asymmetry_penalty",
            {"p_max_loss": 50, "p_max_profit": 40}, {})
        assert result == -8

    def test_no_penalty(self):
        """ratio < 1.25 → 0."""
        reg = get_registry()
        result = reg.invoke("probability_asymmetry_penalty",
            {"p_max_loss": 45, "p_max_profit": 55}, {})
        assert result == 0.0

    def test_zero_profit_probability(self):
        """p_max_profit == 0 → max penalty."""
        reg = get_registry()
        result = reg.invoke("probability_asymmetry_penalty",
            {"p_max_loss": 50, "p_max_profit": 0}, {})
        assert result == -25

    def test_null_inputs_no_penalty(self):
        """Missing probability data → no penalty."""
        reg = get_registry()
        assert reg.invoke("probability_asymmetry_penalty",
            {"p_max_loss": None, "p_max_profit": 50}, {}) == 0.0
        assert reg.invoke("probability_asymmetry_penalty",
            {"p_max_loss": 50, "p_max_profit": None}, {}) == 0.0
        assert reg.invoke("probability_asymmetry_penalty", {}, {}) == 0.0

    def test_returns_float_type(self):
        """Engine expects numeric, not bool."""
        reg = get_registry()
        result = reg.invoke("probability_asymmetry_penalty",
            {"p_max_loss": 80, "p_max_profit": 20}, {})
        assert isinstance(result, float)
        assert not isinstance(result, bool)

    def test_custom_thresholds(self):
        """Params override the band boundaries."""
        reg = get_registry()
        params = {
            "band_severe": 3.0,
            "band_high": 2.0,
            "band_moderate": 1.5,
            "penalty_severe": -30,
            "penalty_high": -20,
            "penalty_moderate": -10,
        }
        # ratio = 2.5 → in high band (>= 2.0 but < 3.0)
        result = reg.invoke("probability_asymmetry_penalty",
            {"p_max_loss": 75, "p_max_profit": 30}, params)
        assert result == -20

    def test_boundary_at_exact_threshold(self):
        """Inclusive boundary: ratio == 2.0 → severe band."""
        reg = get_registry()
        result = reg.invoke("probability_asymmetry_penalty",
            {"p_max_loss": 60, "p_max_profit": 30}, {})
        assert result == -25

    def test_legacy_parity(self):
        """Parity with asymmetry.py bands — same thresholds, negated sign.

        Legacy asymmetry_penalty returns positive penalty (0-25).
        New formula returns negative delta (-25 to 0).
        """
        reg = get_registry()

        # Inline legacy logic to avoid scipy import from app.analysis
        def legacy_asymmetry_penalty(p_loss, p_profit):
            if p_loss is None or p_profit is None:
                return 0
            if p_profit == 0:
                return 25
            ratio = p_loss / p_profit
            if ratio >= 2.0:
                return 25
            elif ratio >= 1.5:
                return 15
            elif ratio >= 1.25:
                return 8
            return 0

        test_cases = [
            (80, 20),   # ratio 4.0 → severe
            (75, 50),   # ratio 1.5 → high
            (50, 40),   # ratio 1.25 → moderate
            (45, 55),   # ratio 0.818 → none
            (50, 0),    # zero profit → max
        ]
        for p_loss, p_profit in test_cases:
            legacy = legacy_asymmetry_penalty(p_loss, p_profit)
            new = reg.invoke("probability_asymmetry_penalty",
                {"p_max_loss": p_loss, "p_max_profit": p_profit}, {})
            assert new == -legacy, (
                f"Mismatch for ({p_loss}, {p_profit}): "
                f"legacy={legacy}, new={new}"
            )
