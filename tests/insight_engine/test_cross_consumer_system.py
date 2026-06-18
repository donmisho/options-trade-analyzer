"""
OTA-795 — Cross-consumer end-to-end system suite.

Proves the WHOLE evaluation path composes for every consumer surface: each of
SCREENING, DIRECTIONAL, and POSITION_HEALTH runs adapter-built candidates through
the **real** engine + **real** rule libraries + **seeded** engine_* config to a
complete result record. It does not re-prove pieces already covered by the
per-feature unit tests (those own formula math, adapter DERIVED parity, etc.); it
proves they compose into one pipeline with one entry point.

What "real / not mocked" means here (see ``cross_consumer_harness``):
  * Engine: the real ``evaluate`` entry point and its 7-phase pipeline.
  * Config: the complete seed hydrated from the workbook the live boot reads,
    via the same ``build_all_rows`` → ``InMemoryConfigSource`` → ``load_config``
    path as ``test_full_seed_boot`` — all three surfaces, 40-formula registry.
  * Rule libraries: the real screening ∪ directional ∪ position-health registry.
  * Adapters: candidates are built with the real adapter DERIVED helpers and the
    real adapter instance is passed for the COMPUTED callback. Only the live
    Schwab/DB fetch inside ``produce_candidates`` is sidestepped (it cannot run
    offline), per the established offline convention.

Each surface asserts a complete, well-formed result record (gates, scoring,
adjustments, verdict + the mandatory full per-rule trace) for one PASSING
(reaches a verdict) and one HALTED (stops at a gate) candidate.

Shared seeded-config + candidate fixtures live in ``cross_consumer_harness`` and
are reused by OTA-798 (trace/bronze persistence) rather than re-seeded.
"""

from __future__ import annotations

import pytest

from app.insight_engine import Phase, VerdictSource, evaluate

from tests.insight_engine import cross_consumer_harness as harness
from tests.insight_engine.cross_consumer_harness import SURFACE_CASES

pytestmark = pytest.mark.skipif(
    not harness.SEED_WORKBOOK_AVAILABLE,
    reason=f"seed workbook not available at {harness.__name__}.DEFAULT_XLSX",
)

# Hydrate the complete seed + registry once for the whole module (the live
# mixed-surface boot, offline). Guarded by the module-level skip above.
_CONFIG = harness.build_seeded_config() if harness.SEED_WORKBOOK_AVAILABLE else None
_REGISTRY = harness.get_combined_registry() if harness.SEED_WORKBOOK_AVAILABLE else None

# Parametrize every surface test over the three consumer surfaces, ids = surface.
_CASE_PARAMS = [pytest.param(c, id=c.surface) for c in SURFACE_CASES]


def _phase_bindings(rule_set, phase):
    return [b for b in rule_set.bindings if b.rule.phase is phase]


def _run(case, candidate):
    """Run a single candidate through the real engine for ``case``'s surface."""
    return evaluate(
        candidates=[candidate],
        strategy_key=case.strategy_key,
        source_app_id=harness.SOURCE_APP_ID,
        config=_CONFIG,
        registry=_REGISTRY,
        adapter=case.make_adapter(),
        null_semantics=case.null_semantics,
    )[0]


# ── Seed/registry preconditions shared by every surface ───────────────────


class TestSeedPreconditions:
    """The combined seed exposes all three surfaces and the 40-formula registry."""

    def test_all_three_strategies_loaded(self):
        loaded = set(_CONFIG.rule_sets)
        assert {c.strategy_key for c in SURFACE_CASES} <= loaded

    def test_three_distinct_consumer_surfaces(self):
        surfaces = {
            _CONFIG.rule_sets[c.strategy_key].strategy.consumer_surface
            for c in SURFACE_CASES
        }
        assert surfaces == {"SCREENING", "DIRECTIONAL", "POSITION_HEALTH"}

    def test_combined_registry_is_40(self):
        assert len(_REGISTRY.registered_names()) == harness.EXPECTED_REGISTRY_COUNT


# ── Passing candidate: adapter → engine → complete verdict record ─────────


class TestPassingCandidatePerSurface:
    """One passing candidate per surface flows through all 7 phases to a verdict."""

    @pytest.mark.parametrize("case", _CASE_PARAMS)
    def test_reaches_verdict_with_complete_record(self, case):
        rule_set = _CONFIG.rule_sets[case.strategy_key]
        gate_bindings = _phase_bindings(rule_set, Phase.GATE)
        scoring_bindings = _phase_bindings(rule_set, Phase.SCORING)
        adjustment_bindings = _phase_bindings(rule_set, Phase.ADJUSTMENT)

        r = _run(case, case.passing_builder())

        # Terminal state: completed through verdict via band lookup.
        assert r.terminal_phase == "verdict"
        assert isinstance(r.verdict, str) and r.verdict
        assert r.verdict_source == VerdictSource.BAND_LOOKUP

        # Scores present and in range.
        assert r.raw_score is not None
        assert r.final_score is not None
        assert 0.0 <= r.final_score <= 100.0

        # Provenance stamped on the record.
        assert r.source_app_id == harness.SOURCE_APP_ID
        assert r.strategy_key == case.strategy_key
        assert r.candidate_type
        assert r.engine_version
        assert r.config_version
        assert r.run_timestamp is not None

        # The result record's trace matches the seeded config's binding counts:
        # every gate decided, every scoring criterion scored, every adjustment run.
        assert len(r.gate_decisions) == len(gate_bindings)
        assert len(r.scoring_breakdown) == len(scoring_bindings)
        assert len(r.adjustment_results) == len(adjustment_bindings)

        # A passing candidate halts nowhere.
        assert all(not g.was_terminal for g in r.gate_decisions)

    @pytest.mark.parametrize("case", _CASE_PARAMS)
    def test_full_per_rule_gate_trace_is_well_formed(self, case):
        """Every gate decision in the mandatory trace is fully populated, including
        non-stopping and skipped decisions (skipped ⇒ passed-as-not-failed)."""
        r = _run(case, case.passing_builder())
        assert r.gate_decisions  # at least one gate on every surface
        for g in r.gate_decisions:
            assert g.rule_key
            assert isinstance(g.phase, Phase) and g.phase is Phase.GATE
            assert isinstance(g.evaluation_order, int)
            assert isinstance(g.passed, bool)
            assert isinstance(g.stop_if_fail, bool)
            assert isinstance(g.was_terminal, bool)
            assert isinstance(g.decision_reason, str) and g.decision_reason
            # OTA-838 invariant: a skipped gate is recorded as not-failed.
            if g.skipped:
                assert g.passed is True

    @pytest.mark.parametrize("case", _CASE_PARAMS)
    def test_scoring_breakdown_is_well_formed(self, case):
        """Each scoring criterion contributes weight × raw_value; weights sum to 1.0."""
        r = _run(case, case.passing_builder())
        assert r.scoring_breakdown
        for s in r.scoring_breakdown:
            assert s.rule_key
            assert s.weighted_contribution == pytest.approx(s.raw_value * s.weight)
        total_weight = sum(s.weight for s in r.scoring_breakdown)
        assert total_weight == pytest.approx(1.0)
        # Weighted sum of contributions reconstructs the raw score.
        contribution_sum = sum(s.weighted_contribution for s in r.scoring_breakdown)
        assert r.raw_score == pytest.approx(contribution_sum)

    @pytest.mark.parametrize("case", _CASE_PARAMS)
    def test_adjustments_are_well_formed(self, case):
        """Each adjustment entry carries before/after scores and an amount."""
        r = _run(case, case.passing_builder())
        for a in r.adjustment_results:
            assert a.rule_key
            assert a.score_before is not None
            assert a.score_after is not None
            assert isinstance(a.condition_triggered, bool)


# ── Halted candidate: adapter → engine → gate-halt record ─────────────────


class TestHaltedCandidatePerSurface:
    """One halted candidate per surface stops at a stopping gate, no verdict."""

    @pytest.mark.parametrize("case", _CASE_PARAMS)
    def test_halts_at_gate_with_complete_record(self, case):
        r = _run(case, case.halted_builder())

        # Halted before any score exists.
        assert r.terminal_phase == "gate"
        assert r.verdict is None
        assert r.verdict_source == VerdictSource.HALT_NO_VERDICT
        assert r.raw_score is None
        assert r.final_score is None
        assert r.scoring_breakdown == []
        assert r.adjustment_results == []

        # Provenance is still stamped on a halted record.
        assert r.source_app_id == harness.SOURCE_APP_ID
        assert r.strategy_key == case.strategy_key
        assert r.engine_version
        assert r.config_version

        # Exactly one decision is terminal, and it is a genuine stopping failure.
        terminal = [g for g in r.gate_decisions if g.was_terminal]
        assert len(terminal) == 1
        halt_gate = terminal[0]
        assert halt_gate.passed is False
        assert halt_gate.skipped is False
        assert halt_gate.stop_if_fail is True
        assert halt_gate.rule_key == case.expected_halt_gate

    @pytest.mark.parametrize("case", _CASE_PARAMS)
    def test_halt_trace_records_the_failing_gate(self, case):
        """The mandatory trace includes the halting gate's full decision detail."""
        r = _run(case, case.halted_builder())
        halt = next(g for g in r.gate_decisions if g.was_terminal)
        assert halt.rule_key == case.expected_halt_gate
        assert isinstance(halt.decision_reason, str) and halt.decision_reason
