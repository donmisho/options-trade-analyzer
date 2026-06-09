"""
Tests for the directional gate formulas (OTA-837).

Covers:
- Registration in the live directional registry + strict bool return
- dir_negative_ev: naked vs spread EV coalesce, None-EV non-halt,
  both-null defer, threshold param
- dir_earnings: in-window vs out-of-window, unknown earnings fail-open,
  missing expiration fail-open, buffer_days param
- build_formula_registry() emits both names from synthetic rule rows
  (the rows OTA-833 will add — no DB reseed here)
"""

from __future__ import annotations

import pytest

from app.options_rules.directional import get_registry
from app.options_rules.directional.gate_formulas import (
    dir_earnings,
    dir_negative_ev,
)


# ── Registration ─────────────────────────────────────────────────────────


class TestRegistration:
    def test_both_gates_registered(self):
        reg = get_registry()
        assert reg.has("dir_earnings")
        assert reg.has("dir_negative_ev")

    def test_gates_coexist_with_scoring_formulas(self):
        # Same registry holds the OTA-755/834 scoring formulas.
        reg = get_registry()
        assert reg.has("dir_budget_fit")
        assert reg.has("dir_expected_value")

    def test_dir_negative_ev_returns_strict_bool_via_registry(self):
        reg = get_registry()
        result = reg.invoke("dir_negative_ev", {"ev_raw": 5.0}, {})
        assert result is True
        assert isinstance(result, bool)

    def test_dir_earnings_returns_strict_bool_via_registry(self):
        reg = get_registry()
        result = reg.invoke("dir_earnings", {}, {})
        assert result is True
        assert isinstance(result, bool)


# ── dir_negative_ev ─────────────────────────────────────────────────────


class TestDirNegativeEv:
    def test_spread_positive_ev_passes(self):
        assert dir_negative_ev({"ev_raw": 12.5}, {}) is True

    def test_spread_negative_ev_fails(self):
        assert dir_negative_ev({"ev_raw": -3.0}, {}) is False

    def test_spread_zero_ev_passes_at_default_threshold(self):
        assert dir_negative_ev({"ev_raw": 0.0}, {}) is True

    def test_naked_coalesces_to_total_ev_positive(self):
        # ev_raw is None for naked longs → read total_ev.
        nv = {"ev_raw": None, "total_ev": 8.0}
        assert dir_negative_ev(nv, {}) is True

    def test_naked_coalesces_to_total_ev_negative(self):
        nv = {"ev_raw": None, "total_ev": -1.0}
        assert dir_negative_ev(nv, {}) is False

    def test_naked_ev_raw_none_not_false_halted_when_total_ev_absent(self):
        # ev_raw None AND total_ev absent → defer, never halt on None.
        assert dir_negative_ev({"ev_raw": None}, {}) is True

    def test_both_null_defers_does_not_halt(self):
        assert dir_negative_ev({"ev_raw": None, "total_ev": None}, {}) is True

    def test_both_absent_keys_defers(self):
        assert dir_negative_ev({}, {}) is True

    def test_ev_raw_takes_precedence_over_total_ev(self):
        # When ev_raw present, total_ev is ignored even if it disagrees.
        nv = {"ev_raw": 4.0, "total_ev": -100.0}
        assert dir_negative_ev(nv, {}) is True

    def test_threshold_param_raises_bar(self):
        # EV 2.0 fails when junction threshold is 5.0.
        assert dir_negative_ev({"ev_raw": 2.0}, {"threshold": 5.0}) is False
        assert dir_negative_ev({"ev_raw": 6.0}, {"threshold": 5.0}) is True

    def test_numpy_total_ev_returns_python_bool(self):
        np = pytest.importorskip("numpy")
        nv = {"ev_raw": None, "total_ev": np.float64(-2.5)}
        result = dir_negative_ev(nv, {})
        assert result is False
        assert isinstance(result, bool)


# ── dir_earnings ────────────────────────────────────────────────────────


class TestDirEarnings:
    def test_earnings_in_window_fails(self):
        # Earnings before expiration → in window → gate fails.
        nv = {"next_earnings_date": "2026-07-10", "expiration": "2026-07-17"}
        assert dir_earnings(nv, {}) is False

    def test_earnings_after_expiration_passes(self):
        nv = {"next_earnings_date": "2026-07-25", "expiration": "2026-07-17"}
        assert dir_earnings(nv, {}) is True

    def test_earnings_exactly_on_expiration_fails_at_zero_buffer(self):
        nv = {"next_earnings_date": "2026-07-17", "expiration": "2026-07-17"}
        assert dir_earnings(nv, {}) is False

    def test_unknown_earnings_fail_open(self):
        # next_earnings_date null → never false-fail.
        nv = {"next_earnings_date": None, "expiration": "2026-07-17"}
        assert dir_earnings(nv, {}) is True

    def test_missing_earnings_key_fail_open(self):
        assert dir_earnings({"expiration": "2026-07-17"}, {}) is True

    def test_missing_expiration_passes(self):
        # Cannot evaluate the window → pass, never false-fail.
        nv = {"next_earnings_date": "2026-07-10", "expiration": None}
        assert dir_earnings(nv, {}) is True

    def test_buffer_days_extends_window(self):
        # Earnings 3 days after expiration: passes at buffer 0, fails at buffer 5.
        nv = {"next_earnings_date": "2026-07-20", "expiration": "2026-07-17"}
        assert dir_earnings(nv, {"buffer_days": 0}) is True
        assert dir_earnings(nv, {"buffer_days": 5}) is False

    def test_accepts_date_objects(self):
        from datetime import date

        nv = {
            "next_earnings_date": date(2026, 7, 10),
            "expiration": date(2026, 7, 17),
        }
        assert dir_earnings(nv, {}) is False

    def test_unparseable_earnings_fail_open(self):
        nv = {"next_earnings_date": "not-a-date", "expiration": "2026-07-17"}
        assert dir_earnings(nv, {}) is True


# ── build_formula_registry() emits both names (no DB reseed) ─────────────


class TestFormulaRegistrySeed:
    def test_builder_emits_both_directional_gate_names(self):
        # Synthetic rule rows standing in for the engine_rules OTA-833 will add.
        # Proves the two formulas auto-land in the SHARED formula_registry seed
        # via build_formula_registry() scanning formula_ref — no DB write.
        from scripts.seed_engine_config import build_formula_registry

        synthetic_rules = [
            {"rule_key": "dir_earnings", "formula_ref": "formula:dir_earnings",
             "referenced_named_values": ["next_earnings_date", "expiration"]},
            {"rule_key": "dir_negative_ev", "formula_ref": "formula:dir_negative_ev",
             "referenced_named_values": ["ev_raw", "total_ev"]},
        ]
        lookups = build_formula_registry(synthetic_rules)
        keys = {row["lookup_key"] for row in lookups}
        assert "dir_earnings" in keys
        assert "dir_negative_ev" in keys
        # All registry rows are SHARED-owned under the formula_registry set.
        for row in lookups:
            assert row["owner_app_id"] == "SHARED"
            assert row["lookup_set"] == "formula_registry"
