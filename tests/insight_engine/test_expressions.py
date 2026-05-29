"""
Expression library tests — every operator, BETWEEN decomposition, formula
resolution, unsupported-form rejection, and no boolean-operator parsing.

OTA-700
"""

from __future__ import annotations

import pytest
from datetime import date

from app.insight_engine.config_source import InMemoryConfigSource
from app.insight_engine.expressions import (
    SUPPORTED_EXPRESSIONS,
    UnsupportedExpressionError,
    evaluate_expression,
    invoke_formula,
    is_formula_ref,
    validate_expression,
)
from app.insight_engine.loader import load_config
from app.insight_engine.registry import DictFormulaRegistry


# ── Comparison operators ────────────────────────────────────────────────


class TestComparisonOps:
    def test_gte_pass(self):
        assert evaluate_expression(">=", {"price": 10}, {"min": 5}, ("price",))

    def test_gte_fail(self):
        assert not evaluate_expression(">=", {"price": 3}, {"min": 5}, ("price",))

    def test_gte_equal(self):
        assert evaluate_expression(">=", {"price": 5}, {"min": 5}, ("price",))

    def test_lte_pass(self):
        assert evaluate_expression("<=", {"price": 3}, {"max": 5}, ("price",))

    def test_lte_fail(self):
        assert not evaluate_expression("<=", {"price": 10}, {"max": 5}, ("price",))

    def test_gt_pass(self):
        assert evaluate_expression(">", {"price": 10}, {"min": 5}, ("price",))

    def test_gt_equal_fails(self):
        assert not evaluate_expression(">", {"price": 5}, {"min": 5}, ("price",))

    def test_lt_pass(self):
        assert evaluate_expression("<", {"price": 3}, {"max": 5}, ("price",))

    def test_lt_equal_fails(self):
        assert not evaluate_expression("<", {"price": 5}, {"max": 5}, ("price",))

    def test_eq_pass(self):
        assert evaluate_expression("==", {"x": 42}, {"val": 42}, ("x",))

    def test_eq_fail(self):
        assert not evaluate_expression("==", {"x": 41}, {"val": 42}, ("x",))

    def test_neq_pass(self):
        assert evaluate_expression("!=", {"x": 41}, {"val": 42}, ("x",))

    def test_neq_fail(self):
        assert not evaluate_expression("!=", {"x": 42}, {"val": 42}, ("x",))

    def test_null_lhs_fails_comparison(self):
        assert not evaluate_expression(">=", {"price": None}, {"min": 5}, ("price",))

    def test_missing_lhs_fails_comparison(self):
        assert not evaluate_expression(">=", {}, {"min": 5}, ("price",))

    def test_null_rhs_fails_comparison(self):
        assert not evaluate_expression(">=", {"price": 10}, {}, ("price",))

    def test_float_comparison(self):
        assert evaluate_expression(">=", {"delta": 0.35}, {"min_delta": 0.25}, ("delta",))

    def test_date_comparison(self):
        assert evaluate_expression(
            ">",
            {"expiry": date(2026, 7, 1)},
            {"cutoff": date(2026, 6, 15)},
            ("expiry",),
        )


# ── Set operators ───────────────────────────────────────────────────────


class TestSetOps:
    def test_in_pass(self):
        assert evaluate_expression("IN", {"state": "BULLISH"}, {"allowed": ["BULLISH", "NEUTRAL"]}, ("state",))

    def test_in_fail(self):
        assert not evaluate_expression("IN", {"state": "BEARISH"}, {"allowed": ["BULLISH", "NEUTRAL"]}, ("state",))

    def test_not_in_pass(self):
        assert evaluate_expression("NOT IN", {"state": "BEARISH"}, {"excluded": ["BULLISH"]}, ("state",))

    def test_not_in_fail(self):
        assert not evaluate_expression("NOT IN", {"state": "BULLISH"}, {"excluded": ["BULLISH"]}, ("state",))

    def test_null_value_in_set(self):
        assert not evaluate_expression("IN", {"state": None}, {"allowed": ["BULLISH"]}, ("state",))


# ── Null operators ──────────────────────────────────────────────────────


class TestNullOps:
    def test_is_null_true(self):
        assert evaluate_expression("IS NULL", {"x": None}, {}, ("x",))

    def test_is_null_false(self):
        assert not evaluate_expression("IS NULL", {"x": 5}, {}, ("x",))

    def test_is_null_missing_key(self):
        assert evaluate_expression("IS NULL", {}, {}, ("x",))

    def test_is_not_null_true(self):
        assert evaluate_expression("IS NOT NULL", {"x": 5}, {}, ("x",))

    def test_is_not_null_false(self):
        assert not evaluate_expression("IS NOT NULL", {"x": None}, {}, ("x",))

    def test_is_not_null_missing_key(self):
        assert not evaluate_expression("IS NOT NULL", {}, {}, ("x",))


# ── Enum operators ──────────────────────────────────────────────────────


class TestEnumOps:
    def test_equals_enum_pass(self):
        assert evaluate_expression("EQUALS_ENUM", {"state": "BULLISH"}, {"expected": "BULLISH"}, ("state",))

    def test_equals_enum_fail(self):
        assert not evaluate_expression("EQUALS_ENUM", {"state": "BEARISH"}, {"expected": "BULLISH"}, ("state",))

    def test_equals_enum_null(self):
        assert not evaluate_expression("EQUALS_ENUM", {"state": None}, {"expected": "BULLISH"}, ("state",))

    def test_equals_enum_coerces_to_string(self):
        assert evaluate_expression("EQUALS_ENUM", {"code": 42}, {"expected": "42"}, ("code",))


# ── Unsupported expressions ─────────────────────────────────────────────


class TestUnsupportedExpressions:
    def test_and_rejected(self):
        with pytest.raises(UnsupportedExpressionError):
            validate_expression("A AND B", None)

    def test_or_rejected(self):
        with pytest.raises(UnsupportedExpressionError):
            validate_expression("OR", None)

    def test_not_rejected(self):
        with pytest.raises(UnsupportedExpressionError):
            validate_expression("NOT", None)

    def test_random_string_rejected(self):
        with pytest.raises(UnsupportedExpressionError):
            validate_expression("XYZZY", None)

    def test_none_expression_allowed(self):
        validate_expression(None, None)  # no-op, no raise

    def test_between_allowed_at_load(self):
        validate_expression("BETWEEN", None)  # valid at load stage

    def test_runtime_rejects_between(self):
        with pytest.raises(UnsupportedExpressionError):
            evaluate_expression("BETWEEN", {"x": 5}, {"low": 1, "high": 10}, ("x",))

    def test_all_supported_ops_accepted(self):
        for op in SUPPORTED_EXPRESSIONS:
            validate_expression(op, None)


# ── BETWEEN decomposition at load ───────────────────────────────────────


class TestBetweenDecomposition:
    def _load_with_between_rule(self):
        source = InMemoryConfigSource(
            apps=[
                {"app_id": "SHARED", "name": "Shared", "status": "active", "enabled": True},
                {"app_id": "OTA", "name": "OTA", "status": "active", "enabled": True},
            ],
            rules=[
                {
                    "rule_id": 1,
                    "owner_app_id": "SHARED",
                    "rule_key": "dte_range",
                    "phase": "gate",
                    "tier": "RAW",
                    "intent": "DTE must be in range",
                    "condition_expression": "BETWEEN",
                    "formula_ref": None,
                    "referenced_named_values": ["dte"],
                    "parameter_schema": {
                        "dte_min": {"type": "number"},
                        "dte_max": {"type": "number"},
                    },
                    "null_semantics": None,
                    "enabled": True,
                },
            ],
            strategies=[
                {
                    "strategy_id": 1,
                    "owner_app_id": "OTA",
                    "strategy_key": "test_strat",
                    "display_name": "Test",
                    "consumer_surface": "SCREENING",
                    "description": None,
                    "compatible_structures": None,
                    "verdict_band_set": [
                        {"verdict": "EXECUTE", "min_score": 70, "max_score": 100},
                        {"verdict": "PASS", "min_score": 0, "max_score": 69.99},
                    ],
                    "enabled": True,
                },
            ],
            junction=[
                {
                    "junction_id": 1,
                    "strategy_id": 1,
                    "rule_id": 1,
                    "evaluation_order": 1,
                    "stop_if_fail": True,
                    "score_penalty": None,
                    "weight": None,
                    "parameters": {"dte_min": 14, "dte_max": 45},
                    "terminal_verdict": None,
                    "rationale": "DTE range",
                    "enabled": True,
                },
            ],
            lookups=[],
        )
        return load_config(source)

    def test_between_produces_two_rules(self):
        config = self._load_with_between_rule()
        rs = config.rule_sets["test_strat"]
        assert len(rs.bindings) == 2

    def test_no_between_in_runtime(self):
        config = self._load_with_between_rule()
        rs = config.rule_sets["test_strat"]
        for binding in rs.bindings:
            assert binding.rule.condition_expression != "BETWEEN"

    def test_decomposed_keys(self):
        config = self._load_with_between_rule()
        rs = config.rule_sets["test_strat"]
        keys = {b.rule.rule_key for b in rs.bindings}
        assert "dte_range__gte" in keys
        assert "dte_range__lte" in keys

    def test_decomposed_operators(self):
        config = self._load_with_between_rule()
        rs = config.rule_sets["test_strat"]
        ops = {b.rule.condition_expression for b in rs.bindings}
        assert ops == {">=", "<="}

    def test_decomposed_parameters(self):
        config = self._load_with_between_rule()
        rs = config.rule_sets["test_strat"]
        bindings_by_key = {b.rule.rule_key: b for b in rs.bindings}

        gte = bindings_by_key["dte_range__gte"]
        lte = bindings_by_key["dte_range__lte"]

        # Lower bound gets the smaller value
        assert list(gte.junction.parameters.values()) == [14]
        # Upper bound gets the larger value
        assert list(lte.junction.parameters.values()) == [45]

    def test_decomposed_inherits_phase_and_tier(self):
        config = self._load_with_between_rule()
        rs = config.rule_sets["test_strat"]
        for binding in rs.bindings:
            assert binding.rule.phase.value == "gate"
            assert binding.rule.tier.value == "RAW"

    def test_decomposed_inherits_named_values(self):
        config = self._load_with_between_rule()
        rs = config.rule_sets["test_strat"]
        for binding in rs.bindings:
            assert binding.rule.referenced_named_values == ("dte",)


# ── Formula resolution and invocation ───────────────────────────────────


class TestFormulaInvocation:
    def test_invoke_formula_calls_implementation(self):
        def my_formula(named_values, params):
            return named_values["delta"] * params["scale"]

        registry = DictFormulaRegistry({"my_formula": my_formula})
        result = invoke_formula(
            "formula:my_formula",
            registry,
            named_values={"delta": 0.35},
            parameters={"scale": 100},
        )
        assert result == 35.0

    def test_invoke_formula_gate_returns_bool(self):
        def gate_formula(named_values, params):
            return named_values["chart_state"] == params["expected"]

        registry = DictFormulaRegistry({"chart_check": gate_formula})
        result = invoke_formula(
            "formula:chart_check",
            registry,
            named_values={"chart_state": "BULLISH"},
            parameters={"expected": "BULLISH"},
        )
        assert result is True

    def test_invoke_missing_formula_raises(self):
        registry = DictFormulaRegistry()
        with pytest.raises(KeyError, match="nonexistent"):
            invoke_formula(
                "formula:nonexistent",
                registry,
                named_values={},
                parameters={},
            )

    def test_invoke_invalid_ref_raises(self):
        registry = DictFormulaRegistry()
        with pytest.raises(ValueError, match="Invalid formula_ref"):
            invoke_formula("not_a_formula", registry, {}, {})

    def test_is_formula_ref(self):
        assert is_formula_ref("formula:delta_quality")
        assert not is_formula_ref(">=")
        assert not is_formula_ref(None)
        assert not is_formula_ref("")

    def test_dict_registry_register_and_invoke(self):
        registry = DictFormulaRegistry()
        registry.register("add", lambda nv, p: nv["a"] + p["b"])
        assert registry.has("add")
        assert registry.invoke("add", {"a": 3}, {"b": 7}) == 10

    def test_stub_registry_invoke_raises(self):
        from app.insight_engine.registry import StubFormulaRegistry

        stub = StubFormulaRegistry()
        with pytest.raises(KeyError):
            stub.invoke("anything", {}, {})


# ── Domain boundary ─────────────────────────────────────────────────────


class TestDomainBoundary:
    def test_guard_passes(self):
        from app.insight_engine._guard import scan_package
        violations = scan_package()
        assert violations == [], f"Domain leaks: {violations}"
