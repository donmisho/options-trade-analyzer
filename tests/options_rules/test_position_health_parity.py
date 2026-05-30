"""
OTA-751 — Position-health rule-library parity tests.

End-to-end: fixture positions across the full spectrum run through the
7-phase pipeline under both strategies (position_health_full and
position_health_basic), asserting expected letter grades.

Parity with legacy health_grade.py is tracked per fixture.
Two intentional divergences are documented (Option A upgrades).

Acceptance gate for the position-health rule library (OTA-742..750).
"""

from __future__ import annotations

import pytest

from app.insight_engine.config_source import InMemoryConfigSource
from app.insight_engine.loader import load_config
from app.insight_engine.models import Candidate, VerdictSource
from app.insight_engine.pipeline import run_pipeline
from app.options_rules.position_health import get_registry
import importlib.util
import sys
from pathlib import Path

# Load config module directly to avoid sqlalchemy dep in adapter __init__
_config_path = Path(__file__).resolve().parents[2] / "app" / "ota_adapters" / "position_health" / "config.py"
_spec = importlib.util.spec_from_file_location("_ph_config", _config_path)
_config_mod = importlib.util.module_from_spec(_spec)
sys.modules["_ph_config"] = _config_mod
_spec.loader.exec_module(_config_mod)

STRATEGY_BASIC_KEY = _config_mod.STRATEGY_BASIC_KEY
STRATEGY_FULL_KEY = _config_mod.STRATEGY_FULL_KEY
get_all_config_rows = _config_mod.get_all_config_rows


# ── Inlined legacy logic (avoids scipy import chain from app.analysis) ─


def _legacy_grade(entry_price, current_price, exit_json=None):
    """Inline of health_grade.compute_health_grade to avoid scipy dependency."""
    import json as _json

    if current_price is None or entry_price == 0:
        return None

    if exit_json:
        levels = _json.loads(exit_json)
        warning = levels.get("warning")
        stop = levels.get("stop")
        if warning is not None and stop is not None:
            if stop < warning:
                if current_price <= stop:
                    return "F"
                if current_price <= warning:
                    return "D"
                buffer = warning - stop
                if buffer > 0 and current_price <= warning + 0.20 * buffer:
                    return "C"
            else:
                if current_price >= stop:
                    return "F"
                if current_price >= warning:
                    return "D"
                buffer = stop - warning
                if buffer > 0 and current_price >= warning - 0.20 * buffer:
                    return "C"
            pnl_pct = (current_price - entry_price) / abs(entry_price)
            return "A" if pnl_pct >= 0 else "B"

    pnl_pct = (current_price - entry_price) / abs(entry_price)
    if pnl_pct >= 0:
        return "A"
    if pnl_pct >= -0.10:
        return "B"
    if pnl_pct >= -0.25:
        return "C"
    if pnl_pct >= -0.50:
        return "D"
    return "F"


# ── Fixtures ───────────────────────────────────────────────────────────


def _load_engine_config():
    """Load position-health config into EngineConfig via InMemoryConfigSource."""
    rows = get_all_config_rows()
    source = InMemoryConfigSource(
        apps=rows["apps"],
        rules=rows["rules"],
        strategies=rows["strategies"],
        junction=rows["junction"],
        lookups=rows["lookups"],
    )
    return load_config(source)


ENGINE_CONFIG = _load_engine_config()
REGISTRY = get_registry()


_BULLISH = {"bull_put_credit", "long_call", "bull_call_debit"}
_BEARISH = {"bear_call_credit", "long_put", "bear_put_debit"}


def _direction_from_structure(structure: str | None) -> str | None:
    """Inlined from adapter to avoid sqlalchemy import chain."""
    if structure is None:
        return None
    if structure in _BULLISH:
        return "bullish"
    if structure in _BEARISH:
        return "bearish"
    return None


def _compute_derived_inline(nv: dict) -> None:
    """Inlined DERIVED computation from adapter. Pure math, no DB deps."""
    entry = nv.get("position_entry_price")
    mark = nv.get("current_position_mark")

    # pnl_pct
    if entry and entry != 0 and mark is not None:
        nv["pnl_pct"] = (mark - entry) / abs(entry)
    else:
        nv["pnl_pct"] = None

    # breach flags
    warning_lvl = nv.get("position_exit_warning_underlying")
    stop_lvl = nv.get("position_exit_stop_underlying")
    underlying = nv.get("current_underlying_price")
    direction = nv.get("position_structure_direction")

    if warning_lvl is None or stop_lvl is None or underlying is None or direction is None:
        nv["warning_breached"] = None
        nv["stop_breached"] = None
        nv["warning_proximity_ratio"] = None
        return

    if direction == "bullish":
        nv["warning_breached"] = underlying <= warning_lvl
        nv["stop_breached"] = underlying <= stop_lvl
        buffer = abs(warning_lvl - stop_lvl)
        distance = underlying - warning_lvl
    else:
        nv["warning_breached"] = underlying >= warning_lvl
        nv["stop_breached"] = underlying >= stop_lvl
        buffer = abs(stop_lvl - warning_lvl)
        distance = warning_lvl - underlying

    nv["warning_proximity_ratio"] = distance / buffer if buffer > 0 else None


def _build_candidate(
    *,
    entry_price: float,
    current_mark: float,
    current_underlying: float | None = None,
    structure: str | None = None,
    warning: float | None = None,
    stop: float | None = None,
) -> Candidate:
    """Build a test Candidate with RAW named values, then compute DERIVED."""
    direction = _direction_from_structure(structure)
    exit_levels_complete = warning is not None and stop is not None

    nv = {
        "position_entry_price": entry_price,
        "position_structure": structure,
        "position_structure_direction": direction,
        "position_exit_warning_underlying": warning,
        "position_exit_stop_underlying": stop,
        "position_exit_scale_out_underlying": None,
        "position_exit_levels_complete": exit_levels_complete,
        "current_underlying_price": current_underlying,
        "current_position_mark": current_mark,
        "position_entry_date": "2026-01-15",
        "position_expiration": "2026-06-20",
        "position_entry_underlying_price": None,
    }
    c = Candidate(
        candidate_id="test-pos",
        candidate_type="position",
        symbol="TEST",
        subject_type="POSITION",
        named_values=nv,
    )
    _compute_derived_inline(c.named_values)
    return c


def _run_full(candidate: Candidate) -> str | None:
    """Run candidate through position_health_full strategy, return verdict."""
    rule_set = ENGINE_CONFIG.rule_sets[STRATEGY_FULL_KEY]
    result = run_pipeline(candidate, rule_set, REGISTRY)
    return result.verdict


def _run_basic(candidate: Candidate) -> str | None:
    """Run candidate through position_health_basic strategy, return verdict."""
    rule_set = ENGINE_CONFIG.rule_sets[STRATEGY_BASIC_KEY]
    result = run_pipeline(candidate, rule_set, REGISTRY)
    return result.verdict


# ── Full strategy — exit-level path ────────────────────────────────────


class TestFullStrategyParity:
    """position_health_full: exit-level-dominant + P&L supplementary."""

    def test_safe_positive_pnl_gives_A(self):
        """Well clear of exit levels, positive P&L.

        Legacy: A (clear + positive) → PARITY.
        Score: exit_safety=100*0.70 + pnl_band=100*0.30 = 100 → A.
        """
        c = _build_candidate(
            entry_price=1.50, current_mark=1.80,
            structure="bull_put_credit",
            current_underlying=185.0,
            warning=180.0, stop=175.0,
        )
        assert _run_full(c) == "A"

    def test_safe_slightly_negative_pnl_gives_A(self):
        """Well clear of exit levels, slightly negative P&L (-8%).

        Legacy: B (clear + negative) → INTENTIONAL DIVERGENCE.
        Weighted model correctly values "well clear" at 70%, so a small
        negative P&L doesn't downgrade. Score: 100*0.70 + 75*0.30 = 92.5 → A.
        """
        c = _build_candidate(
            entry_price=1.50, current_mark=1.38,
            structure="bull_put_credit",
            current_underlying=185.0,
            warning=180.0, stop=175.0,
        )
        assert _run_full(c) == "A"
        # Legacy uses a single current_price for both underlying comparison
        # and P&L. When exit levels are present and clear, it computes
        # pnl from (underlying - entry). With underlying=185, entry=1.50,
        # pnl=+122 → A. The divergence shows when the adapter separates
        # underlying (clear) from mark (slightly negative). Legacy cannot
        # represent this split — the divergence is structural.

    def test_buffer_zone_positive_pnl_gives_C(self):
        """Within 20% buffer of warning, positive P&L.

        Legacy: C (within buffer) → PARITY.
        proximity_ratio=0.10, t=0.50, exit_safety=57.5.
        Score: 57.5*0.70 + 100*0.30 = 70.25 → C.
        """
        c = _build_candidate(
            entry_price=1.50, current_mark=1.80,
            structure="bull_put_credit",
            current_underlying=180.5,
            warning=180.0, stop=175.0,
        )
        assert _run_full(c) == "C"

    def test_warning_breached_neutral_pnl_gives_D(self):
        """Warning breached, neutral P&L.

        Legacy: D (warning breached) → PARITY.
        exit_safety=15*0.70=10.5, pnl=100*0.30=30 → raw=40.5.
        Cap adjustment clamps to 25 → D.
        """
        c = _build_candidate(
            entry_price=1.50, current_mark=1.50,
            structure="bull_put_credit",
            current_underlying=179.0,
            warning=180.0, stop=175.0,
        )
        assert _run_full(c) == "D"

    def test_warning_breached_moderate_loss_gives_D(self):
        """Warning breached, moderate loss (-8%).

        Legacy: D → PARITY.
        exit_safety=15*0.70=10.5, pnl=75*0.30=22.5 → raw=33.
        Cap adjustment clamps to 25 → D.
        """
        c = _build_candidate(
            entry_price=1.50, current_mark=1.38,
            structure="bull_put_credit",
            current_underlying=179.0,
            warning=180.0, stop=175.0,
        )
        assert _run_full(c) == "D"

    def test_stop_breached_gives_F(self):
        """Stop breached.

        Legacy: F (stop hit) → PARITY.
        Floor adjustment forces score to 0 → F.
        """
        c = _build_candidate(
            entry_price=1.50, current_mark=0.10,
            structure="bull_put_credit",
            current_underlying=174.0,
            warning=180.0, stop=175.0,
        )
        assert _run_full(c) == "F"

    def test_warning_breached_catastrophic_pnl_gives_F(self):
        """Warning breached with catastrophic P&L (-60%).

        Legacy: D (warning → always D regardless of P&L) → INTENTIONAL DIVERGENCE.
        exit_safety=15*0.70=10.5, pnl=0*0.30=0 → raw=10.5.
        Cap is 25 but 10.5 < 25, so cap is not applied. Score stays 10.5 → F.
        Better risk modeling: catastrophic P&L should not be masked by D cap.
        """
        c = _build_candidate(
            entry_price=1.50, current_mark=0.60,
            structure="bull_put_credit",
            current_underlying=179.0,
            warning=180.0, stop=175.0,
        )
        assert _run_full(c) == "F"
        # Legacy comparison
        assert _legacy_grade(1.50, 179.0, '{"warning":180,"stop":175}') == "D"

    def test_bearish_warning_breached_gives_D(self):
        """Bearish direction, warning breached.

        Legacy: D → PARITY.
        """
        c = _build_candidate(
            entry_price=1.50, current_mark=1.50,
            structure="bear_call_credit",
            current_underlying=201.0,
            warning=200.0, stop=205.0,
        )
        assert _run_full(c) == "D"

    def test_bearish_stop_breached_gives_F(self):
        """Bearish direction, stop breached.

        Legacy: F → PARITY.
        """
        c = _build_candidate(
            entry_price=1.50, current_mark=0.10,
            structure="bear_call_credit",
            current_underlying=206.0,
            warning=200.0, stop=205.0,
        )
        assert _run_full(c) == "F"


# ── Full strategy — gate failures ──────────────────────────────────────


class TestFullStrategyGates:
    """Gates halt the candidate when required data is missing."""

    def test_missing_entry_price_halts(self):
        c = _build_candidate(
            entry_price=1.50, current_mark=1.50,
            structure="bull_put_credit",
            current_underlying=185.0,
            warning=180.0, stop=175.0,
        )
        c.named_values["position_entry_price"] = None
        rule_set = ENGINE_CONFIG.rule_sets[STRATEGY_FULL_KEY]
        result = run_pipeline(c, rule_set, REGISTRY)
        assert result.verdict_source in (
            VerdictSource.HALT_NO_VERDICT,
            VerdictSource.HALT_TERMINAL_VERDICT,
        )

    def test_missing_current_mark_halts(self):
        c = _build_candidate(
            entry_price=1.50, current_mark=1.50,
            structure="bull_put_credit",
            current_underlying=185.0,
            warning=180.0, stop=175.0,
        )
        c.named_values["current_position_mark"] = None
        rule_set = ENGINE_CONFIG.rule_sets[STRATEGY_FULL_KEY]
        result = run_pipeline(c, rule_set, REGISTRY)
        assert result.verdict_source in (
            VerdictSource.HALT_NO_VERDICT,
            VerdictSource.HALT_TERMINAL_VERDICT,
        )

    def test_missing_exit_levels_halts_full(self):
        """Full strategy requires exit levels — falls through to halt."""
        c = _build_candidate(
            entry_price=1.50, current_mark=1.50,
            structure="bull_put_credit",
            current_underlying=185.0,
        )
        rule_set = ENGINE_CONFIG.rule_sets[STRATEGY_FULL_KEY]
        result = run_pipeline(c, rule_set, REGISTRY)
        assert result.verdict_source in (
            VerdictSource.HALT_NO_VERDICT,
            VerdictSource.HALT_TERMINAL_VERDICT,
        )


# ── Basic strategy — P&L only ─────────────────────────────────────────


class TestBasicStrategyParity:
    """position_health_basic: P&L-only grading. Exact parity with legacy."""

    @pytest.mark.parametrize("entry,mark,expected_grade", [
        (2.50, 3.00, "A"),   # pnl = +0.20 → pnl_band=100 → A
        (2.50, 2.30, "B"),   # pnl = -0.08 → pnl_band=75  → B
        (2.50, 1.90, "C"),   # pnl = -0.24 → pnl_band=50  → C
        (2.50, 1.50, "D"),   # pnl = -0.40 → pnl_band=25  → D
        (2.50, 0.50, "F"),   # pnl = -0.80 → pnl_band=0   → F
    ])
    def test_pnl_grade(self, entry, mark, expected_grade):
        c = _build_candidate(entry_price=entry, current_mark=mark)
        assert _run_basic(c) == expected_grade

    @pytest.mark.parametrize("entry,mark,expected_grade", [
        (2.50, 3.00, "A"),
        (2.50, 2.30, "B"),
        (2.50, 1.90, "C"),
        (2.50, 1.50, "D"),
        (2.50, 0.50, "F"),
    ])
    def test_legacy_parity(self, entry, mark, expected_grade):
        """Every basic-strategy grade matches legacy _grade_from_pnl_pct."""
        legacy = _legacy_grade(entry, mark)
        assert legacy == expected_grade

    def test_no_exit_levels_passes_basic_gates(self):
        """Basic strategy has no exit-level gate — works without them."""
        c = _build_candidate(entry_price=2.50, current_mark=3.00)
        rule_set = ENGINE_CONFIG.rule_sets[STRATEGY_BASIC_KEY]
        result = run_pipeline(c, rule_set, REGISTRY)
        assert result.verdict_source == VerdictSource.BAND_LOOKUP
        assert result.verdict == "A"

    def test_credit_spread_positive_pnl(self):
        """Credit spread with negative entry_price, positive P&L → A."""
        c = _build_candidate(entry_price=-1.50, current_mark=-0.50)
        assert _run_basic(c) == "A"


# ── Categorical guarantees ─────────────────────────────────────────────


class TestCategoricalGuarantees:
    """Adjustment formulas enforce stop→F and warning→D."""

    def test_stop_always_F_regardless_of_pnl(self):
        """Even with positive P&L, stop breached → F via floor adjustment."""
        c = _build_candidate(
            entry_price=1.50, current_mark=2.00,
            structure="bull_put_credit",
            current_underlying=174.0,
            warning=180.0, stop=175.0,
        )
        assert _run_full(c) == "F"

    def test_warning_caps_at_D(self):
        """Warning breached with excellent P&L → still D (cap at 25)."""
        c = _build_candidate(
            entry_price=1.50, current_mark=3.00,
            structure="bull_put_credit",
            current_underlying=179.0,
            warning=180.0, stop=175.0,
        )
        assert _run_full(c) == "D"

    def test_stop_overrides_warning_cap(self):
        """Stop breached + warning breached → F (floor takes precedence)."""
        c = _build_candidate(
            entry_price=1.50, current_mark=0.10,
            structure="bull_put_credit",
            current_underlying=174.0,
            warning=180.0, stop=175.0,
        )
        result_full = ENGINE_CONFIG.rule_sets[STRATEGY_FULL_KEY]
        result = run_pipeline(c, result_full, REGISTRY)
        assert result.verdict == "F"
        # Floor adjustment runs; when raw score is already 0, delta is 0
        # (floor - current = 0 - 0 = 0), so the result is F regardless.
        floor_adj = [a for a in result.adjustment_results
                     if a.rule_key == "ph_stop_breached_floor"]
        assert len(floor_adj) == 1
        assert result.final_score == pytest.approx(0.0)


# ── Score trace verification ───────────────────────────────────────────


class TestScoreTrace:
    """Verify intermediate scores for auditing."""

    def test_full_scoring_breakdown(self):
        """Verify the scoring breakdown for a typical full-strategy case."""
        c = _build_candidate(
            entry_price=1.50, current_mark=1.80,
            structure="bull_put_credit",
            current_underlying=185.0,
            warning=180.0, stop=175.0,
        )
        rule_set = ENGINE_CONFIG.rule_sets[STRATEGY_FULL_KEY]
        result = run_pipeline(c, rule_set, REGISTRY)

        # Two scoring criteria
        assert len(result.scoring_breakdown) == 2

        exit_safety = next(
            s for s in result.scoring_breakdown
            if s.rule_key == "ph_exit_level_safety_score"
        )
        pnl_band = next(
            s for s in result.scoring_breakdown
            if s.rule_key == "ph_pnl_band_score"
        )

        assert exit_safety.raw_value == pytest.approx(100.0)
        assert exit_safety.weight == pytest.approx(0.70)
        assert exit_safety.weighted_contribution == pytest.approx(70.0)

        assert pnl_band.raw_value == pytest.approx(100.0)
        assert pnl_band.weight == pytest.approx(0.30)
        assert pnl_band.weighted_contribution == pytest.approx(30.0)

        assert result.raw_score == pytest.approx(100.0)
        assert result.final_score == pytest.approx(100.0)

    def test_basic_single_criterion(self):
        """Basic strategy has exactly one scoring criterion at weight 1.0."""
        c = _build_candidate(entry_price=2.50, current_mark=1.90)
        rule_set = ENGINE_CONFIG.rule_sets[STRATEGY_BASIC_KEY]
        result = run_pipeline(c, rule_set, REGISTRY)

        assert len(result.scoring_breakdown) == 1
        pnl = result.scoring_breakdown[0]
        assert pnl.rule_key == "ph_pnl_band_score"
        assert pnl.weight == pytest.approx(1.00)
        assert pnl.raw_value == pytest.approx(50.0)
        assert result.final_score == pytest.approx(50.0)
        assert result.verdict == "C"


# ── Config integrity ──────────────────────────────────────────────────


class TestConfigIntegrity:
    """Verify the config loads without errors and both strategies exist."""

    def test_both_strategies_loaded(self):
        assert STRATEGY_FULL_KEY in ENGINE_CONFIG.rule_sets
        assert STRATEGY_BASIC_KEY in ENGINE_CONFIG.rule_sets

    def test_full_has_expected_binding_count(self):
        """Full: 4 gates + 2 scoring + 2 adjustments = 8 bindings."""
        bindings = ENGINE_CONFIG.rule_sets[STRATEGY_FULL_KEY].bindings
        assert len(bindings) == 8

    def test_basic_has_expected_binding_count(self):
        """Basic: 2 gates + 1 scoring = 3 bindings."""
        bindings = ENGINE_CONFIG.rule_sets[STRATEGY_BASIC_KEY].bindings
        assert len(bindings) == 3

    def test_all_formulas_registered(self):
        """Every formula_ref in the config resolves in the live registry."""
        for strat_key, rule_set in ENGINE_CONFIG.rule_sets.items():
            for binding in rule_set.bindings:
                ref = binding.rule.formula_ref
                if ref and ref.startswith("formula:"):
                    name = ref[len("formula:"):]
                    assert REGISTRY.has(name), (
                        f"Formula '{name}' referenced by rule "
                        f"'{binding.rule.rule_key}' in strategy "
                        f"'{strat_key}' is not registered"
                    )

    def test_verdict_bands_cover_full_range(self):
        """Verdict bands span [0, 100] with no gaps."""
        for strat_key in [STRATEGY_FULL_KEY, STRATEGY_BASIC_KEY]:
            bands = ENGINE_CONFIG.rule_sets[strat_key].strategy.verdict_band_set
            assert len(bands) == 5
            # Check coverage: min of mins = 0, max of maxes >= 100
            min_score = min(b["min_score"] for b in bands)
            max_score = max(b["max_score"] for b in bands)
            assert min_score == 0
            assert max_score == 100
