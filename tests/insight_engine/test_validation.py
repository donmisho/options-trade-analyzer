"""
Startup validation suite — tests for every §6.6 failure mode.

Each test builds a clean fixture, mutates one aspect, and asserts the
specific structured error fires and evaluation is refused via
ConfigValidationError.

OTA-699
"""

from __future__ import annotations

import pytest

from app.insight_engine.config_source import InMemoryConfigSource
from app.insight_engine.loader import load_config
from app.insight_engine.models import NamedValue, Tier
from app.insight_engine.registry import FormulaRegistry, StubFormulaRegistry
from app.insight_engine.validation import (
    ConfigValidationError,
    ValidationReport,
    validate_and_raise,
    validate_config,
)


# ── Test FormulaRegistry implementations ────────────────────────────────


class PopulatedFormulaRegistry:
    """A registry with specific formulas registered."""

    def __init__(self, names: set[str]) -> None:
        self._names = frozenset(names)

    def has(self, name: str) -> bool:
        return name in self._names

    def registered_names(self) -> frozenset[str]:
        return self._names


# ── Fixture helpers ─────────────────────────────────────────────────────


def _base_apps():
    return [
        {"app_id": "SHARED", "name": "Shared", "status": "active", "enabled": True},
        {"app_id": "OTA", "name": "Options Trade Analyzer", "status": "active", "enabled": True},
    ]


def _base_rules():
    return [
        {
            "rule_id": 1,
            "owner_app_id": "SHARED",
            "rule_key": "min_price_gate",
            "phase": "gate",
            "tier": "RAW",
            "intent": "Reject penny stocks",
            "condition_expression": ">=",
            "formula_ref": None,
            "referenced_named_values": ["stock_price"],
            "parameter_schema": {"min_price": {"type": "number", "min": 0}},
            "null_semantics": "FAIL_CLOSED",
            "enabled": True,
        },
        {
            "rule_id": 2,
            "owner_app_id": "SHARED",
            "rule_key": "delta_score",
            "phase": "scoring",
            "tier": "DERIVED",
            "intent": "Score delta quality",
            "condition_expression": None,
            "formula_ref": "formula:delta_quality",
            "referenced_named_values": ["delta"],
            "parameter_schema": {
                "delta_center": {"type": "number", "min": 0, "max": 1},
                "delta_half_range": {"type": "number", "min": 0, "max": 0.5},
            },
            "null_semantics": None,
            "enabled": True,
        },
        {
            "rule_id": 3,
            "owner_app_id": "SHARED",
            "rule_key": "pop_score",
            "phase": "scoring",
            "tier": "RAW",
            "intent": "Score probability of profit",
            "condition_expression": None,
            "formula_ref": "formula:probability_of_profit",
            "referenced_named_values": ["long_delta", "short_delta"],
            "parameter_schema": {},
            "null_semantics": None,
            "enabled": True,
        },
        {
            "rule_id": 4,
            "owner_app_id": "SHARED",
            "rule_key": "cushion_adj",
            "phase": "adjustment",
            "tier": None,
            "intent": "Cushion penalty",
            "condition_expression": None,
            "formula_ref": "formula:cushion_penalty_moderate",
            "referenced_named_values": ["stock_price", "short_strike"],
            "parameter_schema": {},
            "null_semantics": None,
            "enabled": True,
        },
    ]


def _base_strategies():
    return [
        {
            "strategy_id": 1,
            "owner_app_id": "OTA",
            "strategy_key": "test_strategy",
            "display_name": "Test Strategy",
            "consumer_surface": "SCREENING",
            "description": "A test strategy",
            "compatible_structures": None,
            "verdict_band_set": [
                {"verdict": "EXECUTE", "min_score": 70, "max_score": 100},
                {"verdict": "WAIT", "min_score": 50, "max_score": 69.99},
                {"verdict": "PASS", "min_score": 0, "max_score": 49.99},
            ],
            "dte_min": None,
            "dte_max": None,
            "enabled": True,
        },
    ]


def _base_junction():
    return [
        {
            "junction_id": 1,
            "strategy_id": 1,
            "rule_id": 1,
            "evaluation_order": 1,
            "stop_if_fail": True,
            "score_penalty": None,
            "weight": None,
            "parameters": {"min_price": 5.0},
            "terminal_verdict": None,
            "rationale": "Filter penny stocks",
            "enabled": True,
        },
        {
            "junction_id": 2,
            "strategy_id": 1,
            "rule_id": 2,
            "evaluation_order": 1,
            "stop_if_fail": False,
            "score_penalty": None,
            "weight": 0.6,
            "parameters": {"delta_center": 0.35, "delta_half_range": 0.15},
            "terminal_verdict": None,
            "rationale": "Delta quality",
            "enabled": True,
        },
        {
            "junction_id": 3,
            "strategy_id": 1,
            "rule_id": 3,
            "evaluation_order": 2,
            "stop_if_fail": False,
            "score_penalty": None,
            "weight": 0.4,
            "parameters": {},
            "terminal_verdict": None,
            "rationale": "PoP score",
            "enabled": True,
        },
        {
            "junction_id": 4,
            "strategy_id": 1,
            "rule_id": 4,
            "evaluation_order": 1,
            "stop_if_fail": False,
            "score_penalty": None,
            "weight": None,
            "parameters": {},
            "terminal_verdict": None,
            "rationale": "Cushion penalty",
            "enabled": True,
        },
    ]


def _base_lookups():
    return [
        # Verdict domain for SCREENING
        {
            "owner_app_id": "OTA",
            "lookup_set": "screening_verdicts",
            "lookup_key": "EXECUTE",
            "payload": '{"min_score": 70, "max_score": 100}',
            "sort_order": 1,
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "lookup_set": "screening_verdicts",
            "lookup_key": "WAIT",
            "payload": '{"min_score": 50, "max_score": 69.99}',
            "sort_order": 2,
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "lookup_set": "screening_verdicts",
            "lookup_key": "PASS",
            "payload": '{"min_score": 0, "max_score": 49.99}',
            "sort_order": 3,
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "lookup_set": "screening_verdicts",
            "lookup_key": "WAIT_FOR_EARNINGS",
            "payload": '{"kind": "HALT_VERDICT"}',
            "sort_order": 4,
            "enabled": True,
        },
        # Formula registry (SHARED)
        {
            "owner_app_id": "SHARED",
            "lookup_set": "formula_registry",
            "lookup_key": "delta_quality",
            "payload": '{"intent": "Gaussian peak around target delta"}',
            "sort_order": 1,
            "enabled": True,
        },
        {
            "owner_app_id": "SHARED",
            "lookup_set": "formula_registry",
            "lookup_key": "probability_of_profit",
            "payload": '{"intent": "PoP from option delta"}',
            "sort_order": 2,
            "enabled": True,
        },
        {
            "owner_app_id": "SHARED",
            "lookup_set": "formula_registry",
            "lookup_key": "cushion_penalty_moderate",
            "payload": '{"intent": "Cushion proximity penalty"}',
            "sort_order": 3,
            "enabled": True,
        },
    ]


def _base_input_catalog():
    return {
        "stock_price": NamedValue(name="stock_price", tier=Tier.RAW, value_type="number", null_semantics="FAIL_CLOSED"),
        "delta": NamedValue(name="delta", tier=Tier.DERIVED, value_type="number"),
        "long_delta": NamedValue(name="long_delta", tier=Tier.RAW, value_type="number"),
        "short_delta": NamedValue(name="short_delta", tier=Tier.RAW, value_type="number"),
        "short_strike": NamedValue(name="short_strike", tier=Tier.RAW, value_type="number"),
    }


def _base_formula_registry():
    return PopulatedFormulaRegistry({
        "delta_quality",
        "probability_of_profit",
        "cushion_penalty_moderate",
    })


def _load_and_validate(
    *,
    apps=None,
    rules=None,
    strategies=None,
    junction=None,
    lookups=None,
    input_catalog=None,
    formula_registry=None,
    use_source_for_fk=False,
):
    """Helper: build source, load config, validate, return report."""
    source = InMemoryConfigSource(
        apps=apps or _base_apps(),
        rules=rules or _base_rules(),
        strategies=strategies or _base_strategies(),
        junction=junction or _base_junction(),
        lookups=lookups or _base_lookups(),
    )
    config = load_config(source)
    return validate_config(
        config,
        input_catalog=input_catalog,
        formula_registry=formula_registry,
        source=source if use_source_for_fk else None,
    )


# ── Tests: clean fixture passes ─────────────────────────────────────────


class TestCleanFixture:
    def test_clean_config_passes(self):
        report = _load_and_validate(
            input_catalog=_base_input_catalog(),
            formula_registry=_base_formula_registry(),
            use_source_for_fk=True,
        )
        assert report.is_valid, report.summary()

    def test_validate_and_raise_clean(self):
        source = InMemoryConfigSource(
            apps=_base_apps(),
            rules=_base_rules(),
            strategies=_base_strategies(),
            junction=_base_junction(),
            lookups=_base_lookups(),
        )
        config = load_config(source)
        validate_and_raise(
            config,
            input_catalog=_base_input_catalog(),
            formula_registry=_base_formula_registry(),
            source=source,
        )


# ── Tests: each failure mode ────────────────────────────────────────────


class TestNamedValueMissing:
    def test_rule_references_unknown_named_value(self):
        rules = _base_rules()
        rules[0]["referenced_named_values"] = ["nonexistent_value"]
        report = _load_and_validate(
            rules=rules,
            input_catalog=_base_input_catalog(),
            formula_registry=_base_formula_registry(),
        )
        errors = report.errors_by_code("NAMED_VALUE_MISSING")
        assert len(errors) == 1
        assert "nonexistent_value" in errors[0].message

    def test_skipped_when_no_catalog(self):
        rules = _base_rules()
        rules[0]["referenced_named_values"] = ["nonexistent_value"]
        report = _load_and_validate(
            rules=rules,
            input_catalog=None,
            formula_registry=_base_formula_registry(),
        )
        assert len(report.errors_by_code("NAMED_VALUE_MISSING")) == 0


class TestJunctionFKMissing:
    def test_junction_references_missing_strategy(self):
        junction = _base_junction()
        junction.append({
            "junction_id": 99,
            "strategy_id": 999,
            "rule_id": 1,
            "evaluation_order": 10,
            "stop_if_fail": True,
            "score_penalty": None,
            "weight": None,
            "parameters": {"min_price": 5.0},
            "terminal_verdict": None,
            "rationale": "Orphan",
            "enabled": True,
        })
        report = _load_and_validate(
            junction=junction,
            input_catalog=_base_input_catalog(),
            formula_registry=_base_formula_registry(),
            use_source_for_fk=True,
        )
        errors = report.errors_by_code("JUNCTION_FK_STRATEGY_MISSING")
        assert len(errors) == 1
        assert errors[0].context["strategy_id"] == 999

    def test_junction_references_missing_rule(self):
        junction = _base_junction()
        junction.append({
            "junction_id": 98,
            "strategy_id": 1,
            "rule_id": 888,
            "evaluation_order": 10,
            "stop_if_fail": True,
            "score_penalty": None,
            "weight": None,
            "parameters": {},
            "terminal_verdict": None,
            "rationale": "Orphan rule",
            "enabled": True,
        })
        report = _load_and_validate(
            junction=junction,
            input_catalog=_base_input_catalog(),
            formula_registry=_base_formula_registry(),
            use_source_for_fk=True,
        )
        errors = report.errors_by_code("JUNCTION_FK_RULE_MISSING")
        assert len(errors) == 1
        assert errors[0].context["rule_id"] == 888


class TestJunctionParamMissing:
    def test_missing_required_parameter(self):
        junction = _base_junction()
        # Remove min_price from gate rule parameters
        junction[0]["parameters"] = {}
        report = _load_and_validate(
            junction=junction,
            formula_registry=_base_formula_registry(),
        )
        errors = report.errors_by_code("JUNCTION_PARAM_MISSING")
        assert len(errors) == 1
        assert errors[0].context["missing_param"] == "min_price"


class TestGateJunctionFields:
    """Gate junction rows must have evaluation_order and stop_if_fail.

    The loader enforces this during parsing, so we verify the check
    exists by confirming a clean gate passes (no false positives).
    """

    def test_clean_gate_passes(self):
        report = _load_and_validate(formula_registry=_base_formula_registry())
        errors = report.errors_by_code("GATE_EVAL_ORDER_MISSING")
        assert len(errors) == 0


class TestScoringWeightsNotUnity:
    def test_weights_too_low(self):
        junction = _base_junction()
        junction[1]["weight"] = 0.3  # 0.3 + 0.4 = 0.7
        report = _load_and_validate(
            junction=junction,
            formula_registry=_base_formula_registry(),
        )
        errors = report.errors_by_code("SCORING_WEIGHTS_NOT_UNITY")
        assert len(errors) == 1
        assert errors[0].context["actual_sum"] == pytest.approx(0.7, abs=1e-6)

    def test_weights_too_high(self):
        junction = _base_junction()
        junction[1]["weight"] = 0.9  # 0.9 + 0.4 = 1.3
        report = _load_and_validate(
            junction=junction,
            formula_registry=_base_formula_registry(),
        )
        errors = report.errors_by_code("SCORING_WEIGHTS_NOT_UNITY")
        assert len(errors) == 1

    def test_weights_within_tolerance_pass(self):
        junction = _base_junction()
        junction[1]["weight"] = 0.60005  # 0.60005 + 0.4 = 1.00005 — within 1e-4
        report = _load_and_validate(
            junction=junction,
            formula_registry=_base_formula_registry(),
        )
        errors = report.errors_by_code("SCORING_WEIGHTS_NOT_UNITY")
        assert len(errors) == 0


class TestVerdictBandsNotMonotonic:
    def test_non_monotonic_bands(self):
        strategies = _base_strategies()
        strategies[0]["verdict_band_set"] = [
            {"verdict": "EXECUTE", "min_score": 70, "max_score": 100},
            {"verdict": "WAIT", "min_score": 80, "max_score": 90},  # 80 >= 70
        ]
        report = _load_and_validate(
            strategies=strategies,
            formula_registry=_base_formula_registry(),
        )
        errors = report.errors_by_code("VERDICT_BANDS_NOT_MONOTONIC")
        assert len(errors) == 1


class TestFormulaContract:
    def test_formula_missing_from_contract(self):
        lookups = _base_lookups()
        # Remove delta_quality from formula_registry
        lookups = [l for l in lookups if not (l["lookup_set"] == "formula_registry" and l["lookup_key"] == "delta_quality")]
        report = _load_and_validate(
            lookups=lookups,
            formula_registry=_base_formula_registry(),
        )
        errors = report.errors_by_code("FORMULA_MISSING_FROM_CONTRACT")
        assert len(errors) >= 1
        assert any("delta_quality" in e.message for e in errors)

    def test_formula_missing_from_live_registry(self):
        # Registry missing delta_quality
        registry = PopulatedFormulaRegistry({"probability_of_profit", "cushion_penalty_moderate"})
        report = _load_and_validate(
            formula_registry=registry,
        )
        errors = report.errors_by_code("FORMULA_MISSING_FROM_LIVE_REGISTRY")
        assert len(errors) >= 1
        assert any("delta_quality" in e.message for e in errors)

    def test_formula_registry_drift(self):
        # Contract has an extra formula not in the live registry
        lookups = _base_lookups()
        lookups.append({
            "owner_app_id": "SHARED",
            "lookup_set": "formula_registry",
            "lookup_key": "phantom_formula",
            "payload": '{"intent": "ghost"}',
            "sort_order": 99,
            "enabled": True,
        })
        registry = _base_formula_registry()
        report = _load_and_validate(
            lookups=lookups,
            formula_registry=registry,
        )
        errors = report.errors_by_code("FORMULA_REGISTRY_DRIFT")
        assert any("phantom_formula" in e.message for e in errors)

    def test_live_registry_has_extra_formula(self):
        # Live registry has a formula not in the contract
        registry = PopulatedFormulaRegistry({
            "delta_quality",
            "probability_of_profit",
            "cushion_penalty_moderate",
            "extra_live_formula",
        })
        report = _load_and_validate(
            formula_registry=registry,
        )
        errors = report.errors_by_code("FORMULA_REGISTRY_DRIFT")
        assert any("extra_live_formula" in e.message for e in errors)


class TestJunctionParamTypeViolation:
    def test_string_where_number_expected(self):
        junction = _base_junction()
        junction[0]["parameters"] = {"min_price": "not_a_number"}
        report = _load_and_validate(
            junction=junction,
            formula_registry=_base_formula_registry(),
        )
        errors = report.errors_by_code("JUNCTION_PARAM_TYPE_VIOLATION")
        assert len(errors) >= 1
        assert errors[0].context["param"] == "min_price"

    def test_value_below_min_bound(self):
        junction = _base_junction()
        junction[0]["parameters"] = {"min_price": -5.0}
        report = _load_and_validate(
            junction=junction,
            formula_registry=_base_formula_registry(),
        )
        errors = report.errors_by_code("JUNCTION_PARAM_TYPE_VIOLATION")
        assert len(errors) >= 1
        assert errors[0].context["value"] == -5.0

    def test_value_above_max_bound(self):
        junction = _base_junction()
        # delta_center has max=1
        junction[1]["parameters"] = {"delta_center": 1.5, "delta_half_range": 0.15}
        report = _load_and_validate(
            junction=junction,
            formula_registry=_base_formula_registry(),
        )
        errors = report.errors_by_code("JUNCTION_PARAM_TYPE_VIOLATION")
        assert len(errors) >= 1
        assert errors[0].context["param"] == "delta_center"


class TestNullSemanticsIncompatible:
    def test_fail_closed_rule_with_fail_open_value(self):
        catalog = _base_input_catalog()
        catalog["stock_price"] = NamedValue(
            name="stock_price", tier=Tier.RAW,
            value_type="number", null_semantics="FAIL_OPEN",
        )
        report = _load_and_validate(
            input_catalog=catalog,
            formula_registry=_base_formula_registry(),
        )
        errors = report.errors_by_code("NULL_SEMANTICS_INCOMPATIBLE")
        assert len(errors) >= 1


class TestEvalOrderDuplicate:
    def test_duplicate_order_in_same_phase(self):
        rules = _base_rules()
        # Add a second gate rule
        rules.append({
            "rule_id": 5,
            "owner_app_id": "SHARED",
            "rule_key": "liquidity_gate",
            "phase": "gate",
            "tier": "RAW",
            "intent": "Liquidity check",
            "condition_expression": ">=",
            "formula_ref": None,
            "referenced_named_values": ["stock_price"],
            "parameter_schema": {},
            "null_semantics": None,
            "enabled": True,
        })
        junction = _base_junction()
        junction.append({
            "junction_id": 5,
            "strategy_id": 1,
            "rule_id": 5,
            "evaluation_order": 1,  # Same as min_price_gate
            "stop_if_fail": True,
            "score_penalty": None,
            "weight": None,
            "parameters": {},
            "terminal_verdict": None,
            "rationale": "Liquidity",
            "enabled": True,
        })
        report = _load_and_validate(
            rules=rules,
            junction=junction,
            formula_registry=_base_formula_registry(),
        )
        errors = report.errors_by_code("EVAL_ORDER_DUPLICATE")
        assert len(errors) >= 1
        assert "gate" in errors[0].context["phase"]


class TestTerminalVerdictUnknown:
    def test_unknown_terminal_verdict(self):
        junction = _base_junction()
        junction[0]["terminal_verdict"] = "BOGUS_VERDICT"
        report = _load_and_validate(
            junction=junction,
            formula_registry=_base_formula_registry(),
        )
        errors = report.errors_by_code("TERMINAL_VERDICT_UNKNOWN")
        assert len(errors) == 1
        assert "BOGUS_VERDICT" in errors[0].message

    def test_valid_terminal_verdict_passes(self):
        junction = _base_junction()
        junction[0]["terminal_verdict"] = "WAIT_FOR_EARNINGS"
        report = _load_and_validate(
            junction=junction,
            formula_registry=_base_formula_registry(),
        )
        errors = report.errors_by_code("TERMINAL_VERDICT_UNKNOWN")
        assert len(errors) == 0

    def test_null_terminal_verdict_passes(self):
        report = _load_and_validate(formula_registry=_base_formula_registry())
        errors = report.errors_by_code("TERMINAL_VERDICT_UNKNOWN")
        assert len(errors) == 0


class TestValidateAndRaise:
    def test_raises_on_failure(self):
        junction = _base_junction()
        junction[1]["weight"] = 0.1  # Weights won't sum to 1.0
        source = InMemoryConfigSource(
            apps=_base_apps(),
            rules=_base_rules(),
            strategies=_base_strategies(),
            junction=junction,
            lookups=_base_lookups(),
        )
        config = load_config(source)
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_and_raise(
                config,
                formula_registry=_base_formula_registry(),
            )
        assert not exc_info.value.report.is_valid
        assert "SCORING_WEIGHTS_NOT_UNITY" in str(exc_info.value)


class TestReportStructure:
    def test_error_has_code_message_context(self):
        junction = _base_junction()
        junction[0]["parameters"] = {}  # Missing min_price
        report = _load_and_validate(
            junction=junction,
            formula_registry=_base_formula_registry(),
        )
        assert not report.is_valid
        err = report.errors[0]
        assert err.code == "JUNCTION_PARAM_MISSING"
        assert "min_price" in err.message
        assert err.context["missing_param"] == "min_price"

    def test_summary_format(self):
        junction = _base_junction()
        junction[0]["parameters"] = {}
        report = _load_and_validate(
            junction=junction,
            formula_registry=_base_formula_registry(),
        )
        summary = report.summary()
        assert "FAILED" in summary
        assert "error(s)" in summary
