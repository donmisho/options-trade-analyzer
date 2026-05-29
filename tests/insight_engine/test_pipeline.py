"""
Pipeline orchestrator tests — 7-phase execution, gate mechanics,
halt-verdict path, scoring, adjustments, and band lookup.

OTA-701
"""

from __future__ import annotations

import pytest

from app.insight_engine.config_source import InMemoryConfigSource
from app.insight_engine.loader import load_config
from app.insight_engine.models import Candidate, Phase, Tier, VerdictSource
from app.insight_engine.pipeline import PipelineResult, run_pipeline
from app.insight_engine.registry import DictFormulaRegistry


# ── Fixture helpers ─────────────────────────────────────────────────────


def _apps():
    return [
        {"app_id": "SHARED", "name": "Shared", "status": "active", "enabled": True},
        {"app_id": "OTA", "name": "OTA", "status": "active", "enabled": True},
    ]


def _strategy(verdict_bands=None):
    return [{
        "strategy_id": 1,
        "owner_app_id": "OTA",
        "strategy_key": "test_strat",
        "display_name": "Test Strategy",
        "consumer_surface": "SCREENING",
        "description": None,
        "compatible_structures": None,
        "verdict_band_set": verdict_bands or [
            {"verdict": "EXECUTE", "min_score": 70, "max_score": 100},
            {"verdict": "WAIT", "min_score": 50, "max_score": 69.99},
            {"verdict": "PASS", "min_score": 0, "max_score": 49.99},
        ],
        "enabled": True,
    }]


def _build_config(rules, junction, lookups=None, verdict_bands=None):
    source = InMemoryConfigSource(
        apps=_apps(),
        rules=rules,
        strategies=_strategy(verdict_bands),
        junction=junction,
        lookups=lookups or [],
    )
    return load_config(source)


def _make_candidate(**named_values):
    return Candidate(
        candidate_id="c1",
        candidate_type="test",
        named_values=named_values,
    )


def _scoring_formula(name, fn):
    """Return (rule_dict, junction_dict, formula_name, formula_fn)."""
    return fn


# ── Test: full end-to-end through all 7 phases ─────────────────────────


class TestEndToEnd:
    def test_full_pipeline_to_verdict(self):
        rules = [
            {
                "rule_id": 1, "owner_app_id": "SHARED", "rule_key": "price_gate",
                "phase": "gate", "tier": "RAW", "intent": None,
                "condition_expression": ">=", "formula_ref": None,
                "referenced_named_values": ["price"],
                "parameter_schema": {"min": {"type": "number"}},
                "null_semantics": None, "enabled": True,
            },
            {
                "rule_id": 2, "owner_app_id": "SHARED", "rule_key": "quality_score",
                "phase": "scoring", "tier": None, "intent": None,
                "condition_expression": None, "formula_ref": "formula:quality",
                "referenced_named_values": ["quality"],
                "parameter_schema": {}, "null_semantics": None, "enabled": True,
            },
            {
                "rule_id": 3, "owner_app_id": "SHARED", "rule_key": "penalty_adj",
                "phase": "adjustment", "tier": None, "intent": None,
                "condition_expression": None, "formula_ref": "formula:penalty",
                "referenced_named_values": ["risk"],
                "parameter_schema": {}, "null_semantics": None, "enabled": True,
            },
        ]
        junction = [
            {
                "junction_id": 1, "strategy_id": 1, "rule_id": 1,
                "evaluation_order": 1, "stop_if_fail": True,
                "score_penalty": None, "weight": None,
                "parameters": {"min": 5.0}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
            {
                "junction_id": 2, "strategy_id": 1, "rule_id": 2,
                "evaluation_order": 1, "stop_if_fail": False,
                "score_penalty": None, "weight": 1.0,
                "parameters": {}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
            {
                "junction_id": 3, "strategy_id": 1, "rule_id": 3,
                "evaluation_order": 1, "stop_if_fail": False,
                "score_penalty": None, "weight": None,
                "parameters": {}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
        ]

        config = _build_config(rules, junction)
        registry = DictFormulaRegistry({
            "quality": lambda nv, p: nv.get("quality", 0),
            "penalty": lambda nv, p: -5.0 if nv.get("risk", 0) > 0.5 else 0.0,
        })
        candidate = _make_candidate(price=10.0, quality=80.0, risk=0.3)

        result = run_pipeline(candidate, config.rule_sets["test_strat"], registry)

        assert len(result.gate_decisions) == 1
        assert result.gate_decisions[0].passed is True
        assert result.raw_score == 80.0
        assert result.final_score == 80.0
        assert result.verdict == "EXECUTE"
        assert result.verdict_source == VerdictSource.BAND_LOOKUP
        assert result.terminal_phase == "verdict"

    def test_phase_order_gate_before_scoring(self):
        rules = [
            {
                "rule_id": 1, "owner_app_id": "SHARED", "rule_key": "gate1",
                "phase": "gate", "tier": "RAW", "intent": None,
                "condition_expression": ">=", "formula_ref": None,
                "referenced_named_values": ["x"],
                "parameter_schema": {"min": {"type": "number"}},
                "null_semantics": None, "enabled": True,
            },
            {
                "rule_id": 2, "owner_app_id": "SHARED", "rule_key": "score1",
                "phase": "scoring", "tier": None, "intent": None,
                "condition_expression": None, "formula_ref": "formula:s",
                "referenced_named_values": ["x"],
                "parameter_schema": {}, "null_semantics": None, "enabled": True,
            },
        ]
        junction = [
            {
                "junction_id": 1, "strategy_id": 1, "rule_id": 1,
                "evaluation_order": 1, "stop_if_fail": True,
                "score_penalty": None, "weight": None,
                "parameters": {"min": 0}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
            {
                "junction_id": 2, "strategy_id": 1, "rule_id": 2,
                "evaluation_order": 1, "stop_if_fail": False,
                "score_penalty": None, "weight": 1.0,
                "parameters": {}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
        ]
        config = _build_config(rules, junction)
        registry = DictFormulaRegistry({"s": lambda nv, p: 75.0})
        candidate = _make_candidate(x=5)
        result = run_pipeline(candidate, config.rule_sets["test_strat"], registry)

        assert len(result.gate_decisions) == 1
        assert result.gate_decisions[0].rule_key == "gate1"
        assert len(result.scoring_breakdown) == 1
        assert result.scoring_breakdown[0].rule_key == "score1"


# ── Test: gate mechanics ───────────────────────────────────────────────


class TestGateMechanics:
    def _gate_config(self, stop_if_fail, score_penalty=None, terminal_verdict=None):
        rules = [{
            "rule_id": 1, "owner_app_id": "SHARED", "rule_key": "g1",
            "phase": "gate", "tier": "RAW", "intent": None,
            "condition_expression": ">=", "formula_ref": None,
            "referenced_named_values": ["val"],
            "parameter_schema": {"min": {"type": "number"}},
            "null_semantics": None, "enabled": True,
        }, {
            "rule_id": 2, "owner_app_id": "SHARED", "rule_key": "sc1",
            "phase": "scoring", "tier": None, "intent": None,
            "condition_expression": None, "formula_ref": "formula:sc",
            "referenced_named_values": [],
            "parameter_schema": {}, "null_semantics": None, "enabled": True,
        }]
        junction = [{
            "junction_id": 1, "strategy_id": 1, "rule_id": 1,
            "evaluation_order": 1, "stop_if_fail": stop_if_fail,
            "score_penalty": score_penalty, "weight": None,
            "parameters": {"min": 10.0}, "terminal_verdict": terminal_verdict,
            "rationale": None, "enabled": True,
        }, {
            "junction_id": 2, "strategy_id": 1, "rule_id": 2,
            "evaluation_order": 1, "stop_if_fail": False,
            "score_penalty": None, "weight": 1.0,
            "parameters": {}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        }]
        return _build_config(rules, junction)

    def test_stopping_gate_halts(self):
        config = self._gate_config(stop_if_fail=True)
        registry = DictFormulaRegistry({"sc": lambda nv, p: 80.0})
        candidate = _make_candidate(val=5.0)  # fails >= 10
        result = run_pipeline(candidate, config.rule_sets["test_strat"], registry)

        assert len(result.gate_decisions) == 1
        assert result.gate_decisions[0].passed is False
        assert result.gate_decisions[0].was_terminal is True
        assert result.final_score is None
        assert result.scoring_breakdown == []
        assert result.terminal_phase == "gate"

    def test_non_stopping_gate_continues_with_penalty(self):
        config = self._gate_config(stop_if_fail=False, score_penalty=15.0)
        registry = DictFormulaRegistry({"sc": lambda nv, p: 80.0})
        candidate = _make_candidate(val=5.0)
        result = run_pipeline(candidate, config.rule_sets["test_strat"], registry)

        assert len(result.gate_decisions) == 1
        assert result.gate_decisions[0].passed is False
        assert result.gate_decisions[0].was_terminal is False
        assert result.gate_decisions[0].held_penalty == 15.0
        assert result.held_penalties_applied == 15.0
        assert result.raw_score == 80.0
        # 80 - 15 = 65
        assert result.final_score == pytest.approx(65.0, abs=0.01)
        assert result.verdict == "WAIT"  # 50–69.99

    def test_non_stopping_gate_zero_penalty(self):
        config = self._gate_config(stop_if_fail=False, score_penalty=0)
        registry = DictFormulaRegistry({"sc": lambda nv, p: 80.0})
        candidate = _make_candidate(val=5.0)
        result = run_pipeline(candidate, config.rule_sets["test_strat"], registry)

        assert result.gate_decisions[0].passed is False
        assert result.gate_decisions[0].held_penalty is None
        assert result.final_score == 80.0


# ── Test: halt-verdict path (OD-2) ─────────────────────────────────────


class TestHaltVerdictPath:
    def _halt_config(self, terminal_verdict):
        rules = [{
            "rule_id": 1, "owner_app_id": "SHARED", "rule_key": "earnings_gate",
            "phase": "gate", "tier": "RAW", "intent": None,
            "condition_expression": ">=", "formula_ref": None,
            "referenced_named_values": ["dte"],
            "parameter_schema": {"min": {"type": "number"}},
            "null_semantics": None, "enabled": True,
        }]
        junction = [{
            "junction_id": 1, "strategy_id": 1, "rule_id": 1,
            "evaluation_order": 1, "stop_if_fail": True,
            "score_penalty": None, "weight": None,
            "parameters": {"min": 14},
            "terminal_verdict": terminal_verdict,
            "rationale": None, "enabled": True,
        }]
        return _build_config(rules, junction)

    def test_halt_with_terminal_verdict(self):
        config = self._halt_config("WAIT_FOR_EARNINGS")
        registry = DictFormulaRegistry()
        candidate = _make_candidate(dte=7)  # fails >= 14
        result = run_pipeline(candidate, config.rule_sets["test_strat"], registry)

        assert result.verdict == "WAIT_FOR_EARNINGS"
        assert result.verdict_source == VerdictSource.HALT_TERMINAL_VERDICT
        assert result.final_score is None
        assert result.terminal_phase == "gate"

    def test_halt_without_terminal_verdict(self):
        config = self._halt_config(None)
        registry = DictFormulaRegistry()
        candidate = _make_candidate(dte=7)
        result = run_pipeline(candidate, config.rule_sets["test_strat"], registry)

        assert result.verdict is None
        assert result.verdict_source == VerdictSource.HALT_NO_VERDICT
        assert result.final_score is None
        assert result.terminal_phase == "gate"

    def test_halt_bypasses_scoring_and_verdict_band(self):
        config = self._halt_config("PASS")
        registry = DictFormulaRegistry()
        candidate = _make_candidate(dte=7)
        result = run_pipeline(candidate, config.rule_sets["test_strat"], registry)

        assert result.scoring_breakdown == []
        assert result.adjustment_results == []
        assert result.raw_score is None
        assert result.verdict == "PASS"
        assert result.verdict_source == VerdictSource.HALT_TERMINAL_VERDICT


# ── Test: scoring ──────────────────────────────────────────────────────


class TestScoring:
    def test_weighted_sum(self):
        rules = [
            {
                "rule_id": 1, "owner_app_id": "SHARED", "rule_key": "s1",
                "phase": "scoring", "tier": None, "intent": None,
                "condition_expression": None, "formula_ref": "formula:f1",
                "referenced_named_values": [],
                "parameter_schema": {}, "null_semantics": None, "enabled": True,
            },
            {
                "rule_id": 2, "owner_app_id": "SHARED", "rule_key": "s2",
                "phase": "scoring", "tier": None, "intent": None,
                "condition_expression": None, "formula_ref": "formula:f2",
                "referenced_named_values": [],
                "parameter_schema": {}, "null_semantics": None, "enabled": True,
            },
        ]
        junction = [
            {
                "junction_id": 1, "strategy_id": 1, "rule_id": 1,
                "evaluation_order": 1, "stop_if_fail": False,
                "score_penalty": None, "weight": 0.6,
                "parameters": {}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
            {
                "junction_id": 2, "strategy_id": 1, "rule_id": 2,
                "evaluation_order": 2, "stop_if_fail": False,
                "score_penalty": None, "weight": 0.4,
                "parameters": {}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
        ]
        config = _build_config(rules, junction)
        registry = DictFormulaRegistry({
            "f1": lambda nv, p: 90.0,
            "f2": lambda nv, p: 60.0,
        })
        candidate = _make_candidate()
        result = run_pipeline(candidate, config.rule_sets["test_strat"], registry)

        # 90*0.6 + 60*0.4 = 54 + 24 = 78
        assert result.raw_score == pytest.approx(78.0)
        assert result.final_score == pytest.approx(78.0)
        assert result.verdict == "EXECUTE"

    def test_score_clamped_to_100(self):
        rules = [{
            "rule_id": 1, "owner_app_id": "SHARED", "rule_key": "s1",
            "phase": "scoring", "tier": None, "intent": None,
            "condition_expression": None, "formula_ref": "formula:f1",
            "referenced_named_values": [],
            "parameter_schema": {}, "null_semantics": None, "enabled": True,
        }]
        junction = [{
            "junction_id": 1, "strategy_id": 1, "rule_id": 1,
            "evaluation_order": 1, "stop_if_fail": False,
            "score_penalty": None, "weight": 1.0,
            "parameters": {}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        }]
        config = _build_config(rules, junction)
        registry = DictFormulaRegistry({"f1": lambda nv, p: 150.0})
        result = run_pipeline(_make_candidate(), config.rule_sets["test_strat"], registry)
        assert result.raw_score == 100.0


# ── Test: adjustments ──────────────────────────────────────────────────


class TestAdjustments:
    def test_adjustment_applies_and_clamps(self):
        rules = [
            {
                "rule_id": 1, "owner_app_id": "SHARED", "rule_key": "s1",
                "phase": "scoring", "tier": None, "intent": None,
                "condition_expression": None, "formula_ref": "formula:f1",
                "referenced_named_values": [],
                "parameter_schema": {}, "null_semantics": None, "enabled": True,
            },
            {
                "rule_id": 2, "owner_app_id": "SHARED", "rule_key": "adj1",
                "phase": "adjustment", "tier": None, "intent": None,
                "condition_expression": None, "formula_ref": "formula:adj",
                "referenced_named_values": [],
                "parameter_schema": {}, "null_semantics": None, "enabled": True,
            },
        ]
        junction = [
            {
                "junction_id": 1, "strategy_id": 1, "rule_id": 1,
                "evaluation_order": 1, "stop_if_fail": False,
                "score_penalty": None, "weight": 1.0,
                "parameters": {}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
            {
                "junction_id": 2, "strategy_id": 1, "rule_id": 2,
                "evaluation_order": 1, "stop_if_fail": False,
                "score_penalty": None, "weight": None,
                "parameters": {}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
        ]
        config = _build_config(rules, junction)
        registry = DictFormulaRegistry({
            "f1": lambda nv, p: 30.0,
            "adj": lambda nv, p: -10.0,
        })
        result = run_pipeline(_make_candidate(), config.rule_sets["test_strat"], registry)

        assert result.raw_score == 30.0
        assert result.final_score == 20.0
        assert result.adjustment_results[0].amount == -10.0
        assert result.adjustment_results[0].condition_triggered is True
        assert result.verdict == "PASS"

    def test_adjustment_floor_clamp(self):
        rules = [
            {
                "rule_id": 1, "owner_app_id": "SHARED", "rule_key": "s1",
                "phase": "scoring", "tier": None, "intent": None,
                "condition_expression": None, "formula_ref": "formula:f1",
                "referenced_named_values": [],
                "parameter_schema": {}, "null_semantics": None, "enabled": True,
            },
            {
                "rule_id": 2, "owner_app_id": "SHARED", "rule_key": "adj1",
                "phase": "adjustment", "tier": None, "intent": None,
                "condition_expression": None, "formula_ref": "formula:adj",
                "referenced_named_values": [],
                "parameter_schema": {}, "null_semantics": None, "enabled": True,
            },
        ]
        junction = [
            {
                "junction_id": 1, "strategy_id": 1, "rule_id": 1,
                "evaluation_order": 1, "stop_if_fail": False,
                "score_penalty": None, "weight": 1.0,
                "parameters": {}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
            {
                "junction_id": 2, "strategy_id": 1, "rule_id": 2,
                "evaluation_order": 1, "stop_if_fail": False,
                "score_penalty": None, "weight": None,
                "parameters": {}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
        ]
        config = _build_config(rules, junction)
        registry = DictFormulaRegistry({
            "f1": lambda nv, p: 10.0,
            "adj": lambda nv, p: -999.0,  # massive penalty
        })
        result = run_pipeline(_make_candidate(), config.rule_sets["test_strat"], registry)

        assert result.final_score == 0.0  # clamped to floor

    def test_adjustment_cap_clamp(self):
        rules = [
            {
                "rule_id": 1, "owner_app_id": "SHARED", "rule_key": "s1",
                "phase": "scoring", "tier": None, "intent": None,
                "condition_expression": None, "formula_ref": "formula:f1",
                "referenced_named_values": [],
                "parameter_schema": {}, "null_semantics": None, "enabled": True,
            },
            {
                "rule_id": 2, "owner_app_id": "SHARED", "rule_key": "adj1",
                "phase": "adjustment", "tier": None, "intent": None,
                "condition_expression": None, "formula_ref": "formula:adj",
                "referenced_named_values": [],
                "parameter_schema": {}, "null_semantics": None, "enabled": True,
            },
        ]
        junction = [
            {
                "junction_id": 1, "strategy_id": 1, "rule_id": 1,
                "evaluation_order": 1, "stop_if_fail": False,
                "score_penalty": None, "weight": 1.0,
                "parameters": {}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
            {
                "junction_id": 2, "strategy_id": 1, "rule_id": 2,
                "evaluation_order": 1, "stop_if_fail": False,
                "score_penalty": None, "weight": None,
                "parameters": {}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
        ]
        config = _build_config(rules, junction)
        registry = DictFormulaRegistry({
            "f1": lambda nv, p: 95.0,
            "adj": lambda nv, p: 999.0,  # massive bonus
        })
        result = run_pipeline(_make_candidate(), config.rule_sets["test_strat"], registry)

        assert result.final_score == 100.0  # clamped to cap


# ── Test: evaluate() top-level ─────────────────────────────────────────


class TestEvaluateTopLevel:
    def test_evaluate_multiple_candidates(self):
        from app.insight_engine import evaluate

        rules = [{
            "rule_id": 1, "owner_app_id": "SHARED", "rule_key": "s1",
            "phase": "scoring", "tier": None, "intent": None,
            "condition_expression": None, "formula_ref": "formula:f1",
            "referenced_named_values": ["val"],
            "parameter_schema": {}, "null_semantics": None, "enabled": True,
        }]
        junction = [{
            "junction_id": 1, "strategy_id": 1, "rule_id": 1,
            "evaluation_order": 1, "stop_if_fail": False,
            "score_penalty": None, "weight": 1.0,
            "parameters": {}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        }]
        config = _build_config(rules, junction)
        registry = DictFormulaRegistry({"f1": lambda nv, p: nv.get("val", 0)})

        candidates = [
            _make_candidate(val=80.0),
            Candidate(candidate_id="c2", candidate_type="test", named_values={"val": 40.0}),
        ]
        results = evaluate(
            candidates=candidates,
            strategy_key="test_strat",
            source_app_id="OTA",
            config=config,
            registry=registry,
        )
        assert len(results) == 2
        assert results[0].verdict == "EXECUTE"
        assert results[1].verdict == "PASS"


# ── Test: gate tier ordering (RAW before DERIVED) ──────────────────────


class TestGateTierOrdering:
    def test_raw_gate_before_derived_gate(self):
        rules = [
            {
                "rule_id": 1, "owner_app_id": "SHARED", "rule_key": "derived_gate",
                "phase": "gate", "tier": "DERIVED", "intent": None,
                "condition_expression": ">=", "formula_ref": None,
                "referenced_named_values": ["derived_val"],
                "parameter_schema": {"min": {"type": "number"}},
                "null_semantics": None, "enabled": True,
            },
            {
                "rule_id": 2, "owner_app_id": "SHARED", "rule_key": "raw_gate",
                "phase": "gate", "tier": "RAW", "intent": None,
                "condition_expression": ">=", "formula_ref": None,
                "referenced_named_values": ["raw_val"],
                "parameter_schema": {"min": {"type": "number"}},
                "null_semantics": None, "enabled": True,
            },
        ]
        junction = [
            {
                "junction_id": 1, "strategy_id": 1, "rule_id": 1,
                "evaluation_order": 1, "stop_if_fail": True,
                "score_penalty": None, "weight": None,
                "parameters": {"min": 0}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
            {
                "junction_id": 2, "strategy_id": 1, "rule_id": 2,
                "evaluation_order": 1, "stop_if_fail": True,
                "score_penalty": None, "weight": None,
                "parameters": {"min": 0}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
        ]
        config = _build_config(rules, junction)
        candidate = _make_candidate(raw_val=5, derived_val=5)
        result = run_pipeline(candidate, config.rule_sets["test_strat"], DictFormulaRegistry())

        # RAW gate should be evaluated before DERIVED
        assert result.gate_decisions[0].rule_key == "raw_gate"
        assert result.gate_decisions[1].rule_key == "derived_gate"


# ── Test: domain boundary ──────────────────────────────────────────────


class TestDomainBoundary:
    def test_guard_passes(self):
        from app.insight_engine._guard import scan_package
        assert scan_package() == []
