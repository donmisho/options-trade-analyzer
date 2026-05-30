"""
OTA-741 — Position-health adapter parity tests vs health_grade.py.

Fixtures cover the spectrum:
  1. Just-entered, positive P&L → A
  2. Mid-life, slightly negative → B
  3. Within 20% of warning (exit-level path) → C
  4. Warning breached (exit-level path) → D
  5. Stop breached (exit-level path) → F
  6. No exit levels, positive P&L → A
  7. No exit levels, moderate loss → C
  8. No exit levels, large loss → D
  9. No exit levels, max loss → F
  10. Credit spread (negative entry_price) positive P&L → A
  11. Bearish direction — warning breached → D
  12. Bearish direction — stop breached → F

The adapter produces DERIVED named values; the rule library (OTA-742)
maps them to letter grades. Since OTA-742 is not yet committed, this
test validates the DERIVED values directly against what health_grade.py
would compute — the parity harness for the rule library to un-skip
its grade-level assertions later.
"""

import json

import pytest

from app.analysis.health_grade import compute_health_grade
from app.insight_engine import Candidate
from app.ota_adapters.position_health.adapter import (
    PositionHealthAdapter,
    _compute_derived,
    _direction_from_structure,
)


def _build_candidate(
    *,
    entry_price: float,
    current_mark: float,
    current_underlying: float | None = None,
    structure: str | None = None,
    warning: float | None = None,
    stop: float | None = None,
    scale_out: float | None = None,
    entry_date: str | None = "2026-01-15",
    expiration: str | None = "2026-06-20",
    entry_underlying: float | None = None,
) -> Candidate:
    """Build a test Candidate with RAW named values pre-populated."""
    direction = _direction_from_structure(structure)
    exit_levels_complete = warning is not None and stop is not None

    nv = {
        "position_entry_price": entry_price,
        "position_structure": structure,
        "position_structure_direction": direction,
        "position_exit_warning_underlying": warning,
        "position_exit_stop_underlying": stop,
        "position_exit_scale_out_underlying": scale_out,
        "position_exit_levels_complete": exit_levels_complete,
        "current_underlying_price": current_underlying,
        "current_position_mark": current_mark,
        "position_entry_date": entry_date,
        "position_expiration": expiration,
        "position_entry_underlying_price": entry_underlying,
    }
    return Candidate(
        candidate_id="test-pos-1",
        candidate_type="position",
        symbol="AAPL",
        subject_type="POSITION",
        named_values=nv,
    )


def _health_grade_exit_levels_json(warning, stop, scale_out=None):
    """Build the JSON string health_grade.py expects."""
    levels = {"warning": warning, "stop": stop}
    if scale_out is not None:
        levels["scale_out"] = scale_out
    return json.dumps(levels)


# ── pnl_pct parity ──────────────────────────────────────────────────


class TestPnlPctParity:
    """Verify pnl_pct matches health_grade.py:_pnl_pct including abs() denominator."""

    def test_positive_pnl(self):
        c = _build_candidate(entry_price=2.50, current_mark=3.00)
        _compute_derived(c)
        # (3.00 - 2.50) / abs(2.50) = 0.20
        assert c.named_values["pnl_pct"] == pytest.approx(0.20)

    def test_negative_pnl(self):
        c = _build_candidate(entry_price=2.50, current_mark=1.50)
        _compute_derived(c)
        # (1.50 - 2.50) / abs(2.50) = -0.40
        assert c.named_values["pnl_pct"] == pytest.approx(-0.40)

    def test_credit_spread_positive(self):
        """Credit spread: negative entry_price moving toward zero is a win."""
        c = _build_candidate(entry_price=-1.50, current_mark=-0.50)
        _compute_derived(c)
        # (-0.50 - -1.50) / abs(-1.50) = 1.0 / 1.50 = 0.6667
        assert c.named_values["pnl_pct"] == pytest.approx(0.6667, rel=1e-3)

    def test_credit_spread_negative(self):
        """Credit spread: negative entry_price moving further negative is a loss."""
        c = _build_candidate(entry_price=-1.50, current_mark=-2.50)
        _compute_derived(c)
        # (-2.50 - -1.50) / abs(-1.50) = -1.0 / 1.50 = -0.6667
        assert c.named_values["pnl_pct"] == pytest.approx(-0.6667, rel=1e-3)

    def test_zero_entry_price(self):
        c = _build_candidate(entry_price=0.0, current_mark=1.00)
        _compute_derived(c)
        assert c.named_values["pnl_pct"] is None


# ── Breach flag parity ───────────────────────────────────────────────


class TestBreachFlags:
    """Verify structure-aware breach flags match health_grade.py exit-level logic."""

    def test_bullish_no_breach(self):
        """Bull put: price above warning → neither breached."""
        c = _build_candidate(
            entry_price=1.50, current_mark=1.60,
            structure="bull_put_credit",
            current_underlying=185.0,
            warning=180.0, stop=175.0,
        )
        _compute_derived(c)
        assert c.named_values["warning_breached"] is False
        assert c.named_values["stop_breached"] is False

    def test_bullish_warning_breached(self):
        """Bull put: price at warning → warning breached, not stop."""
        c = _build_candidate(
            entry_price=1.50, current_mark=0.80,
            structure="bull_put_credit",
            current_underlying=180.0,
            warning=180.0, stop=175.0,
        )
        _compute_derived(c)
        assert c.named_values["warning_breached"] is True
        assert c.named_values["stop_breached"] is False

    def test_bullish_stop_breached(self):
        """Bull put: price at stop → both breached."""
        c = _build_candidate(
            entry_price=1.50, current_mark=0.20,
            structure="bull_put_credit",
            current_underlying=175.0,
            warning=180.0, stop=175.0,
        )
        _compute_derived(c)
        assert c.named_values["warning_breached"] is True
        assert c.named_values["stop_breached"] is True

    def test_bearish_no_breach(self):
        """Bear call: price below warning → neither breached."""
        c = _build_candidate(
            entry_price=1.50, current_mark=1.60,
            structure="bear_call_credit",
            current_underlying=195.0,
            warning=200.0, stop=205.0,
        )
        _compute_derived(c)
        assert c.named_values["warning_breached"] is False
        assert c.named_values["stop_breached"] is False

    def test_bearish_warning_breached(self):
        """Bear call: price at warning → warning breached."""
        c = _build_candidate(
            entry_price=1.50, current_mark=0.80,
            structure="bear_call_credit",
            current_underlying=200.0,
            warning=200.0, stop=205.0,
        )
        _compute_derived(c)
        assert c.named_values["warning_breached"] is True
        assert c.named_values["stop_breached"] is False

    def test_bearish_stop_breached(self):
        """Bear call: price at stop → both breached."""
        c = _build_candidate(
            entry_price=1.50, current_mark=0.20,
            structure="bear_call_credit",
            current_underlying=205.0,
            warning=200.0, stop=205.0,
        )
        _compute_derived(c)
        assert c.named_values["warning_breached"] is True
        assert c.named_values["stop_breached"] is True

    def test_no_exit_levels(self):
        """No exit levels → breach flags are None."""
        c = _build_candidate(
            entry_price=1.50, current_mark=1.00,
            structure="bull_put_credit",
            current_underlying=185.0,
        )
        _compute_derived(c)
        assert c.named_values["warning_breached"] is None
        assert c.named_values["stop_breached"] is None


# ── Warning proximity ratio ─────────────────────────────────────────


class TestWarningProximityRatio:
    """Verify normalised distance has no 20% literal embedded."""

    def test_bullish_above_warning(self):
        """Price above warning → positive ratio."""
        c = _build_candidate(
            entry_price=1.50, current_mark=1.50,
            structure="bull_put_credit",
            current_underlying=181.0,
            warning=180.0, stop=175.0,
        )
        _compute_derived(c)
        # distance = 181 - 180 = 1, buffer = |180 - 175| = 5, ratio = 0.20
        assert c.named_values["warning_proximity_ratio"] == pytest.approx(0.20)

    def test_bullish_at_warning(self):
        """Price at warning → ratio = 0."""
        c = _build_candidate(
            entry_price=1.50, current_mark=0.80,
            structure="bull_put_credit",
            current_underlying=180.0,
            warning=180.0, stop=175.0,
        )
        _compute_derived(c)
        assert c.named_values["warning_proximity_ratio"] == pytest.approx(0.0)

    def test_bullish_below_warning(self):
        """Price below warning → negative ratio."""
        c = _build_candidate(
            entry_price=1.50, current_mark=0.50,
            structure="bull_put_credit",
            current_underlying=178.0,
            warning=180.0, stop=175.0,
        )
        _compute_derived(c)
        # distance = 178 - 180 = -2, buffer = 5, ratio = -0.40
        assert c.named_values["warning_proximity_ratio"] == pytest.approx(-0.40)

    def test_bearish_below_warning(self):
        """Bearish: price below warning → positive ratio (safe)."""
        c = _build_candidate(
            entry_price=1.50, current_mark=1.50,
            structure="bear_call_credit",
            current_underlying=199.0,
            warning=200.0, stop=205.0,
        )
        _compute_derived(c)
        # distance = 200 - 199 = 1, buffer = |200 - 205| = 5, ratio = 0.20
        assert c.named_values["warning_proximity_ratio"] == pytest.approx(0.20)


# ── health_grade.py parity — exit-level path ────────────────────────


class TestExitLevelPathParity:
    """
    Verify the adapter's DERIVED values would produce the same grade
    as health_grade.py for the exit-level path.

    Since the rule library (OTA-742) is not yet committed, we compare
    the adapter's DERIVED values against what health_grade.py computes,
    verifying the inputs are correct for the future rules.
    """

    def _legacy_grade(self, entry_price, current_price, warning, stop):
        """Compute grade via legacy health_grade.py for comparison."""
        levels_json = _health_grade_exit_levels_json(warning, stop)
        return compute_health_grade(entry_price, current_price, levels_json)

    def test_bullish_safe_positive_pnl(self):
        """Price well above warning, positive P&L → A."""
        grade = self._legacy_grade(1.50, 185.0, 180.0, 175.0)
        c = _build_candidate(
            entry_price=1.50, current_mark=1.80,
            structure="bull_put_credit",
            current_underlying=185.0,
            warning=180.0, stop=175.0,
        )
        _compute_derived(c)
        nv = c.named_values
        assert grade == "A"
        assert nv["warning_breached"] is False
        assert nv["stop_breached"] is False
        assert nv["pnl_pct"] > 0

    def test_bullish_near_warning(self):
        """Price within 20% buffer of warning → C in legacy."""
        # warning=180, stop=175, buffer=5, 20% of buffer = 1
        # price = 180.5 → within warning + 0.20 * 5 = 181
        grade = self._legacy_grade(1.50, 180.5, 180.0, 175.0)
        c = _build_candidate(
            entry_price=1.50, current_mark=1.00,
            structure="bull_put_credit",
            current_underlying=180.5,
            warning=180.0, stop=175.0,
        )
        _compute_derived(c)
        nv = c.named_values
        assert grade == "C"
        assert nv["warning_breached"] is False
        # proximity ratio: (180.5 - 180) / 5 = 0.10 → within [0, 0.20]
        assert 0 <= nv["warning_proximity_ratio"] <= 0.20

    def test_bullish_warning_breached(self):
        """Price at warning → D in legacy."""
        grade = self._legacy_grade(1.50, 180.0, 180.0, 175.0)
        c = _build_candidate(
            entry_price=1.50, current_mark=0.50,
            structure="bull_put_credit",
            current_underlying=180.0,
            warning=180.0, stop=175.0,
        )
        _compute_derived(c)
        nv = c.named_values
        assert grade == "D"
        assert nv["warning_breached"] is True
        assert nv["stop_breached"] is False

    def test_bullish_stop_breached(self):
        """Price at stop → F in legacy."""
        grade = self._legacy_grade(1.50, 175.0, 180.0, 175.0)
        c = _build_candidate(
            entry_price=1.50, current_mark=0.10,
            structure="bull_put_credit",
            current_underlying=175.0,
            warning=180.0, stop=175.0,
        )
        _compute_derived(c)
        nv = c.named_values
        assert grade == "F"
        assert nv["stop_breached"] is True

    def test_bearish_stop_breached(self):
        """Bearish: price at stop → F in legacy."""
        grade = self._legacy_grade(1.50, 205.0, 200.0, 205.0)
        c = _build_candidate(
            entry_price=1.50, current_mark=0.10,
            structure="bear_call_credit",
            current_underlying=205.0,
            warning=200.0, stop=205.0,
        )
        _compute_derived(c)
        nv = c.named_values
        assert grade == "F"
        assert nv["stop_breached"] is True


# ── health_grade.py parity — P&L fallback path ──────────────────────


class TestPnlFallbackParity:
    """Verify P&L fallback grades match health_grade.py:_grade_from_pnl_pct."""

    @pytest.mark.parametrize("entry,mark,expected_grade,expected_pnl_range", [
        (2.50, 3.00, "A", (0.0, None)),       # pnl = +0.20 → A
        (2.50, 2.30, "B", (-0.10, 0.0)),       # pnl = -0.08 → B
        (2.50, 1.90, "C", (-0.25, -0.10)),     # pnl = -0.24 → C
        (2.50, 1.50, "D", (-0.50, -0.25)),     # pnl = -0.40 → D
        (2.50, 0.50, "F", (None, -0.50)),       # pnl = -0.80 → F
    ])
    def test_pnl_fallback(self, entry, mark, expected_grade, expected_pnl_range):
        """P&L fallback path — no exit levels."""
        # Legacy grade
        legacy = compute_health_grade(entry, mark)
        assert legacy == expected_grade

        # Adapter DERIVED values
        c = _build_candidate(entry_price=entry, current_mark=mark)
        _compute_derived(c)
        pnl = c.named_values["pnl_pct"]
        assert pnl is not None

        lo, hi = expected_pnl_range
        if lo is not None:
            assert pnl >= lo
        if hi is not None:
            assert pnl < hi


# ── Catalog completeness ─────────────────────────────────────────────


class TestCatalog:
    """Verify the §5.1 input catalog is complete and consistent."""

    def test_catalog_not_empty(self):
        adapter = PositionHealthAdapter()
        catalog = adapter.input_catalog()
        assert len(catalog) > 0

    def test_all_produced_values_in_catalog(self):
        """Every value the adapter produces should be in the catalog."""
        adapter = PositionHealthAdapter()
        catalog_names = {e.name for e in adapter.input_catalog()}

        c = _build_candidate(
            entry_price=1.50, current_mark=1.60,
            structure="bull_put_credit",
            current_underlying=185.0,
            warning=180.0, stop=175.0,
            entry_underlying=190.0,
        )
        _compute_derived(c)

        for key in c.named_values:
            assert key in catalog_names, f"Named value '{key}' not in catalog"

    def test_catalog_tiers(self):
        """Verify tier assignments are correct."""
        from app.insight_engine import Tier
        adapter = PositionHealthAdapter()
        catalog = {e.name: e for e in adapter.input_catalog()}

        # RAW values
        for name in [
            "position_entry_price", "position_structure",
            "current_underlying_price", "current_position_mark",
        ]:
            assert catalog[name].tier == Tier.RAW, f"{name} should be RAW"

        # DERIVED values
        for name in [
            "pnl_pct", "warning_breached", "stop_breached",
            "warning_proximity_ratio", "days_since_entry",
        ]:
            assert catalog[name].tier == Tier.DERIVED, f"{name} should be DERIVED"

        # COMPUTED values
        for name in [
            "current_prob_of_profit", "current_ev",
            "probability_of_max_loss_now",
        ]:
            assert catalog[name].tier == Tier.COMPUTED, f"{name} should be COMPUTED"


# ── COMPUTED feature flag ────────────────────────────────────────────


class TestComputedFeatureFlag:
    """Verify COMPUTED producers respect the feature flag."""

    def test_computed_off_by_default(self):
        adapter = PositionHealthAdapter()
        assert adapter.ENABLE_COMPUTED is False

    def test_computed_noop_when_off(self):
        adapter = PositionHealthAdapter()
        c = _build_candidate(
            entry_price=1.50, current_mark=1.50,
            structure="bull_put_credit",
            current_underlying=185.0,
            warning=180.0, stop=175.0,
        )
        _compute_derived(c)
        adapter.populate_computed([c], {"current_prob_of_profit"})
        assert "current_prob_of_profit" not in c.named_values
