"""
Tests for the gate formulas (earnings routes + negative EV).

OTA-730: Earnings gate — four atomic route formulas.
OTA-731: Negative EV gate — consolidated formula.

Tests validate:
- Registration in the live registry
- Correct bool return types
- Route condition matching and mutual exclusivity
- Fail-soft on missing data
- Legacy parity with earnings_gate.py and negative_ev_gate.py
- Parameterized thresholds
"""

from __future__ import annotations

import pytest

from app.options_rules.screening import get_registry


# ── Registration ─────────────────────────────────────────────────────────


class TestGateRegistration:
    def test_all_earnings_routes_registered(self):
        reg = get_registry()
        assert reg.has("earnings_route1_no_viable_window")
        assert reg.has("earnings_route2_wait_post_window")
        assert reg.has("earnings_route3_post_entry_better")
        assert reg.has("earnings_route4_pre_momentum_play")

    def test_negative_ev_gate_registered(self):
        reg = get_registry()
        assert reg.has("negative_ev_gate")


# ── OTA-730: Earnings Route 1 — no viable window ────────────────────────


class TestEarningsRoute1:
    """dte_before <= 7 AND dte_after < 14 → gate fails (False)."""

    def test_condition_met_fails_gate(self):
        reg = get_registry()
        result = reg.invoke("earnings_route1_no_viable_window",
            {"dte_before_earnings": 5, "dte_after_earnings": 10}, {})
        assert result is False

    def test_condition_not_met_passes(self):
        reg = get_registry()
        # dte_after >= 14 → Route 2, not Route 1
        result = reg.invoke("earnings_route1_no_viable_window",
            {"dte_before_earnings": 5, "dte_after_earnings": 20}, {})
        assert result is True

    def test_boundary_dte_before_7(self):
        reg = get_registry()
        result = reg.invoke("earnings_route1_no_viable_window",
            {"dte_before_earnings": 7, "dte_after_earnings": 10}, {})
        assert result is False  # <= 7

    def test_boundary_dte_before_8_passes(self):
        reg = get_registry()
        result = reg.invoke("earnings_route1_no_viable_window",
            {"dte_before_earnings": 8, "dte_after_earnings": 10}, {})
        assert result is True  # > 7

    def test_boundary_dte_after_14_passes(self):
        reg = get_registry()
        result = reg.invoke("earnings_route1_no_viable_window",
            {"dte_before_earnings": 5, "dte_after_earnings": 14}, {})
        assert result is True  # not < 14

    def test_no_earnings_data_passes(self):
        reg = get_registry()
        assert reg.invoke("earnings_route1_no_viable_window", {}, {}) is True

    def test_partial_earnings_data_passes(self):
        reg = get_registry()
        assert reg.invoke("earnings_route1_no_viable_window",
            {"dte_before_earnings": 5}, {}) is True

    def test_returns_bool(self):
        reg = get_registry()
        result = reg.invoke("earnings_route1_no_viable_window",
            {"dte_before_earnings": 5, "dte_after_earnings": 10}, {})
        assert isinstance(result, bool)

    def test_custom_thresholds(self):
        reg = get_registry()
        params = {"dte_before_threshold": 5, "dte_after_threshold": 10}
        # 5 <= 5 and 10 < 10 → False (10 is not < 10), so condition not met → passes
        assert reg.invoke("earnings_route1_no_viable_window",
            {"dte_before_earnings": 5, "dte_after_earnings": 10}, params) is True
        # 5 <= 5 and 9 < 10 → True, condition met → gate fails
        assert reg.invoke("earnings_route1_no_viable_window",
            {"dte_before_earnings": 5, "dte_after_earnings": 9}, params) is False


# ── OTA-730: Earnings Route 2 — wait for post window ────────────────────


class TestEarningsRoute2:
    """dte_before <= 7 AND dte_after >= 14 → gate fails (False)."""

    def test_condition_met_fails_gate(self):
        reg = get_registry()
        result = reg.invoke("earnings_route2_wait_post_window",
            {"dte_before_earnings": 5, "dte_after_earnings": 20}, {})
        assert result is False

    def test_condition_not_met_passes(self):
        reg = get_registry()
        # dte_after < 14 → Route 1, not Route 2
        result = reg.invoke("earnings_route2_wait_post_window",
            {"dte_before_earnings": 5, "dte_after_earnings": 10}, {})
        assert result is True

    def test_boundary_dte_after_14(self):
        reg = get_registry()
        result = reg.invoke("earnings_route2_wait_post_window",
            {"dte_before_earnings": 5, "dte_after_earnings": 14}, {})
        assert result is False  # >= 14

    def test_no_earnings_data_passes(self):
        reg = get_registry()
        assert reg.invoke("earnings_route2_wait_post_window", {}, {}) is True


# ── OTA-730: Earnings Route 3 — post entry better ───────────────────────


class TestEarningsRoute3:
    """dte_before >= 8 AND dte_after >= 21 → gate fails (False)."""

    def test_condition_met_fails_gate(self):
        reg = get_registry()
        result = reg.invoke("earnings_route3_post_entry_better",
            {"dte_before_earnings": 10, "dte_after_earnings": 25}, {})
        assert result is False

    def test_condition_not_met_passes(self):
        reg = get_registry()
        # dte_after < 21 → Route 4, not Route 3
        result = reg.invoke("earnings_route3_post_entry_better",
            {"dte_before_earnings": 10, "dte_after_earnings": 15}, {})
        assert result is True

    def test_boundary_dte_before_8(self):
        reg = get_registry()
        result = reg.invoke("earnings_route3_post_entry_better",
            {"dte_before_earnings": 8, "dte_after_earnings": 25}, {})
        assert result is False  # >= 8

    def test_boundary_dte_after_21(self):
        reg = get_registry()
        result = reg.invoke("earnings_route3_post_entry_better",
            {"dte_before_earnings": 10, "dte_after_earnings": 21}, {})
        assert result is False  # >= 21

    def test_no_earnings_data_passes(self):
        reg = get_registry()
        assert reg.invoke("earnings_route3_post_entry_better", {}, {}) is True


# ── OTA-730: Earnings Route 4 — pre-earnings momentum play ──────────────


class TestEarningsRoute4:
    """dte_before >= 8 AND dte_after < 21 → gate fails (False), non-stopping."""

    def test_condition_met_fails_gate(self):
        reg = get_registry()
        result = reg.invoke("earnings_route4_pre_momentum_play",
            {"dte_before_earnings": 10, "dte_after_earnings": 15}, {})
        assert result is False

    def test_condition_not_met_passes(self):
        reg = get_registry()
        # dte_after >= 21 → Route 3, not Route 4
        result = reg.invoke("earnings_route4_pre_momentum_play",
            {"dte_before_earnings": 10, "dte_after_earnings": 25}, {})
        assert result is True

    def test_boundary_dte_after_20(self):
        reg = get_registry()
        result = reg.invoke("earnings_route4_pre_momentum_play",
            {"dte_before_earnings": 10, "dte_after_earnings": 20}, {})
        assert result is False  # < 21

    def test_no_earnings_data_passes(self):
        reg = get_registry()
        assert reg.invoke("earnings_route4_pre_momentum_play", {}, {}) is True


# ── OTA-730: Mutual exclusivity ──────────────────────────────────────────


class TestEarningsRouteExclusivity:
    """At most one route should fire for any given (dte_before, dte_after)."""

    @pytest.mark.parametrize("dte_before,dte_after,expected_route", [
        (5, 10, 1),    # Route 1: <= 7 and < 14
        (5, 20, 2),    # Route 2: <= 7 and >= 14
        (10, 25, 3),   # Route 3: >= 8 and >= 21
        (10, 15, 4),   # Route 4: >= 8 and < 21
        (7, 13, 1),    # Boundary: exactly Route 1
        (7, 14, 2),    # Boundary: exactly Route 2
        (8, 21, 3),    # Boundary: exactly Route 3
        (8, 20, 4),    # Boundary: exactly Route 4
    ])
    def test_exactly_one_route_fires(self, dte_before, dte_after, expected_route):
        reg = get_registry()
        nv = {"dte_before_earnings": dte_before, "dte_after_earnings": dte_after}

        results = {
            1: reg.invoke("earnings_route1_no_viable_window", nv, {}),
            2: reg.invoke("earnings_route2_wait_post_window", nv, {}),
            3: reg.invoke("earnings_route3_post_entry_better", nv, {}),
            4: reg.invoke("earnings_route4_pre_momentum_play", nv, {}),
        }

        # The expected route should fail (False), all others pass (True)
        for route, passed in results.items():
            if route == expected_route:
                assert passed is False, f"Route {route} should fail for ({dte_before}, {dte_after})"
            else:
                assert passed is True, f"Route {route} should pass for ({dte_before}, {dte_after})"

    def test_no_earnings_all_pass(self):
        """When no earnings in window, all routes pass."""
        reg = get_registry()
        nv = {}
        for name in [
            "earnings_route1_no_viable_window",
            "earnings_route2_wait_post_window",
            "earnings_route3_post_entry_better",
            "earnings_route4_pre_momentum_play",
        ]:
            assert reg.invoke(name, nv, {}) is True


# ── OTA-730: Legacy parity ───────────────────────────────────────────────


class TestEarningsLegacyParity:
    """Match legacy EarningsInWindowGate route assignment."""

    @pytest.mark.parametrize("dte_before,dte_after,legacy_verdict", [
        # Route 1 → PASS
        (3, 5, "PASS"),
        (7, 13, "PASS"),
        # Route 2 → WAIT_FOR_EARNINGS
        (5, 20, "WAIT_FOR_EARNINGS"),
        (7, 14, "WAIT_FOR_EARNINGS"),
        # Route 3 → WAIT_FOR_EARNINGS
        (10, 25, "WAIT_FOR_EARNINGS"),
        (8, 21, "WAIT_FOR_EARNINGS"),
        # Route 4 → score with penalty (not halted)
        (10, 15, "SCORE_WITH_PENALTY"),
        (8, 20, "SCORE_WITH_PENALTY"),
    ])
    def test_route_matches_legacy(self, dte_before, dte_after, legacy_verdict):
        """Verify our formulas match the legacy gate's routing logic."""
        reg = get_registry()
        nv = {"dte_before_earnings": dte_before, "dte_after_earnings": dte_after}

        r1 = reg.invoke("earnings_route1_no_viable_window", nv, {})
        r2 = reg.invoke("earnings_route2_wait_post_window", nv, {})
        r3 = reg.invoke("earnings_route3_post_entry_better", nv, {})
        r4 = reg.invoke("earnings_route4_pre_momentum_play", nv, {})

        if legacy_verdict == "PASS":
            assert r1 is False  # Route 1 fires
        elif legacy_verdict == "WAIT_FOR_EARNINGS":
            assert r2 is False or r3 is False  # Route 2 or 3 fires
        elif legacy_verdict == "SCORE_WITH_PENALTY":
            assert r4 is False  # Route 4 fires (non-stopping, -15 penalty)


# ── OTA-731: Negative EV gate ────────────────────────────────────────────


class TestNegativeEVGate:
    """Bool-returning gate. False = negative EV = gate fails."""

    def test_negative_ev_fails(self):
        reg = get_registry()
        result = reg.invoke("negative_ev_gate", {"ev_raw": -5.0}, {})
        assert result is False

    def test_positive_ev_passes(self):
        reg = get_registry()
        result = reg.invoke("negative_ev_gate", {"ev_raw": 10.0}, {})
        assert result is True

    def test_zero_ev_passes(self):
        """EV == 0 → not negative (strict <, not <=)."""
        reg = get_registry()
        result = reg.invoke("negative_ev_gate", {"ev_raw": 0.0}, {})
        assert result is True

    def test_missing_ev_passes(self):
        """Fail-soft: missing EV → pass."""
        reg = get_registry()
        assert reg.invoke("negative_ev_gate", {}, {}) is True
        assert reg.invoke("negative_ev_gate", {"ev_raw": None}, {}) is True

    def test_returns_bool(self):
        reg = get_registry()
        result = reg.invoke("negative_ev_gate", {"ev_raw": -1.0}, {})
        assert isinstance(result, bool)

    def test_custom_threshold(self):
        """Junction can raise the EV floor above 0."""
        reg = get_registry()
        # threshold=5.0 → EV must be >= 5.0
        assert reg.invoke("negative_ev_gate", {"ev_raw": 3.0}, {"threshold": 5.0}) is False
        assert reg.invoke("negative_ev_gate", {"ev_raw": 5.0}, {"threshold": 5.0}) is True

    def test_legacy_parity(self):
        """Match NegativeEVGate: EV < 0 → triggered, else not."""
        reg = get_registry()
        test_cases = [
            (-10.0, False),   # negative → fail
            (-0.01, False),   # slightly negative → fail
            (0.0, True),      # zero → pass (strict <)
            (0.01, True),     # slightly positive → pass
            (50.0, True),     # positive → pass
        ]
        for ev, expected in test_cases:
            result = reg.invoke("negative_ev_gate", {"ev_raw": ev}, {})
            assert result is expected, f"EV={ev}: expected {expected}, got {result}"

    def test_consolidation_with_vertical_engine_filter(self):
        """The vertical_engine.py:265 filter uses ev_raw >= min_ev_threshold.

        Our formula uses ev_raw >= threshold (default 0.0).
        With threshold=0.0, this matches the legacy filter's default behavior
        (min_ev_threshold=0 → only positive EV survives).
        """
        reg = get_registry()
        # Default threshold=0.0 matches legacy min_ev_threshold=0
        assert reg.invoke("negative_ev_gate", {"ev_raw": -1.0}, {}) is False
        assert reg.invoke("negative_ev_gate", {"ev_raw": 0.0}, {}) is True
        assert reg.invoke("negative_ev_gate", {"ev_raw": 1.0}, {}) is True
