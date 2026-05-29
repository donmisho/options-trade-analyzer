"""
Tests for the screening formula registration mechanism.

Validates:
- Decorator registers a formula resolvable by the engine
- Purity contract enforced (return value in [0, 100])
- OTA-699 membership check passes for registered formulas
- OTA-699 drift detection fires for contract/registry mismatch

OTA-726

NOTE: Tests in this file must NOT use @screening_formula with test names,
as that pollutes the module-level _REGISTRY and causes drift errors in
other tests. Use DictFormulaRegistry directly for isolation.
"""

from __future__ import annotations

import functools

import pytest

from app.insight_engine.config_source import InMemoryConfigSource
from app.insight_engine.loader import load_config
from app.insight_engine.registry import DictFormulaRegistry
from app.insight_engine.validation import validate_config
from app.options_rules.screening import FormulaReturnValueError


# ── Helpers ────────────────────────────────────────────────────────────


def _wrap_with_validation(name: str, fn):
    """Apply the same return-value validation the decorator uses."""

    @functools.wraps(fn)
    def wrapper(named_values, params):
        result = fn(named_values, params)
        if not isinstance(result, (int, float)):
            raise FormulaReturnValueError(
                f"Formula '{name}' returned {type(result).__name__}, "
                f"expected a number in [0, 100]."
            )
        val = float(result)
        if val < 0.0 or val > 100.0:
            raise FormulaReturnValueError(
                f"Formula '{name}' returned {val}, "
                f"expected a value in [0, 100]."
            )
        return val

    return wrapper


def _make_fresh_registry() -> DictFormulaRegistry:
    """Build a fresh registry with a trivial stub formula for testing."""
    registry = DictFormulaRegistry()
    registry.register("test_stub", _wrap_with_validation(
        "test_stub", lambda nv, p: 50.0
    ))
    return registry


def _base_config_source(
    *,
    contract_formulas: list[str] | None = None,
):
    """Build a minimal InMemoryConfigSource with formula rules."""
    formulas = contract_formulas or ["test_stub"]

    rules = [
        {
            "rule_id": i + 1,
            "owner_app_id": "SHARED",
            "rule_key": f"{name}_score",
            "phase": "scoring",
            "tier": "RAW",
            "intent": f"Score {name}",
            "condition_expression": None,
            "formula_ref": f"formula:{name}",
            "referenced_named_values": [],
            "parameter_schema": {},
            "null_semantics": None,
            "enabled": True,
        }
        for i, name in enumerate(formulas)
    ]

    n = len(formulas)
    weight = 1.0 / n if n > 0 else 1.0
    junction = [
        {
            "junction_id": i + 1,
            "strategy_id": 1,
            "rule_id": i + 1,
            "evaluation_order": i + 1,
            "stop_if_fail": False,
            "score_penalty": None,
            "weight": weight,
            "parameters": {},
            "terminal_verdict": None,
            "rationale": f"{name} score",
            "enabled": True,
        }
        for i, name in enumerate(formulas)
    ]

    lookups = [
        {
            "owner_app_id": "SHARED",
            "lookup_set": "formula_registry",
            "lookup_key": name,
            "payload": f'{{"intent": "{name}"}}',
            "sort_order": i + 1,
            "enabled": True,
        }
        for i, name in enumerate(formulas)
    ]

    return InMemoryConfigSource(
        apps=[
            {"app_id": "SHARED", "name": "Shared", "status": "active", "enabled": True},
            {"app_id": "OTA", "name": "OTA", "status": "active", "enabled": True},
        ],
        rules=rules,
        strategies=[
            {
                "strategy_id": 1,
                "owner_app_id": "OTA",
                "strategy_key": "test_strat",
                "display_name": "Test",
                "consumer_surface": "SCREENING",
                "description": "Test",
                "compatible_structures": None,
                "verdict_band_set": [
                    {"verdict": "EXECUTE", "min_score": 70, "max_score": 100},
                    {"verdict": "PASS", "min_score": 0, "max_score": 69.99},
                ],
                "dte_min": None,
                "dte_max": None,
                "enabled": True,
            },
        ],
        junction=junction,
        lookups=lookups,
    )


# ── Tests: decorator registration ─────────────────────────────────────


class TestFormulaRegistration:
    def test_decorator_registers_into_dict_registry(self):
        """A DictFormulaRegistry can register and invoke a formula."""
        reg = DictFormulaRegistry()
        reg.register("my_test_formula", lambda nv, p: 75.0)

        assert reg.has("my_test_formula")
        assert "my_test_formula" in reg.registered_names()
        assert reg.invoke("my_test_formula", {}, {}) == 75.0

    def test_module_level_registry_has_scoring_formulas(self):
        """The module-level registry contains formulas from scoring_formulas.py."""
        from app.options_rules.screening import get_registry

        reg = get_registry()
        # At least one known scoring formula should be registered
        assert reg.has("theta_margin_ratio")
        assert reg.has("delta_quality")


class TestPurityContract:
    def test_return_value_in_range(self):
        """Formula returning valid value succeeds."""
        reg = DictFormulaRegistry()
        reg.register("good", _wrap_with_validation("good", lambda nv, p: 50.0))
        assert reg.invoke("good", {}, {}) == 50.0

    def test_return_value_below_zero_raises(self):
        """Formula returning < 0 raises FormulaReturnValueError."""
        reg = DictFormulaRegistry()
        reg.register("negative", _wrap_with_validation("negative", lambda nv, p: -5.0))
        with pytest.raises(FormulaReturnValueError, match=r"expected a value in \[0, 100\]"):
            reg.invoke("negative", {}, {})

    def test_return_value_above_100_raises(self):
        """Formula returning > 100 raises FormulaReturnValueError."""
        reg = DictFormulaRegistry()
        reg.register("over100", _wrap_with_validation("over100", lambda nv, p: 150.0))
        with pytest.raises(FormulaReturnValueError, match=r"expected a value in \[0, 100\]"):
            reg.invoke("over100", {}, {})

    def test_return_non_numeric_raises(self):
        """Formula returning a non-numeric type raises FormulaReturnValueError."""
        reg = DictFormulaRegistry()
        reg.register("stringy", _wrap_with_validation("stringy", lambda nv, p: "not a number"))
        with pytest.raises(FormulaReturnValueError, match="expected a number"):
            reg.invoke("stringy", {}, {})

    def test_boundary_values_accepted(self):
        """Formula returning 0.0 and 100.0 are both valid."""
        reg = DictFormulaRegistry()
        reg.register("zero", _wrap_with_validation("zero", lambda nv, p: 0.0))
        reg.register("hundred", _wrap_with_validation("hundred", lambda nv, p: 100.0))
        assert reg.invoke("zero", {}, {}) == 0.0
        assert reg.invoke("hundred", {}, {}) == 100.0


# ── Tests: OTA-699 membership check ───────────────────────────────────


class TestFormulaLookup:
    def test_engine_resolves_registered_formula(self):
        """A formula registered in the live registry passes OTA-700 invoke."""
        from app.insight_engine.expressions import invoke_formula

        reg = DictFormulaRegistry()
        reg.register("test_invoke", lambda nv, p: 60.0)

        result = invoke_formula("formula:test_invoke", reg, {"x": 1}, {"y": 2})
        assert result == 60.0

    def test_engine_rejects_unregistered_formula(self):
        """Invoking an unregistered formula raises KeyError."""
        from app.insight_engine.expressions import invoke_formula

        reg = DictFormulaRegistry()
        with pytest.raises(KeyError):
            invoke_formula("formula:nonexistent", reg, {}, {})


class TestValidationMembership:
    def test_registered_formula_passes_validation(self):
        """OTA-699 membership check passes when formula is in both
        contract and live registry."""
        source = _base_config_source(contract_formulas=["test_stub"])
        config = load_config(source)
        registry = _make_fresh_registry()

        report = validate_config(config, formula_registry=registry)

        contract_errors = report.errors_by_code("FORMULA_MISSING_FROM_CONTRACT")
        live_errors = report.errors_by_code("FORMULA_MISSING_FROM_LIVE_REGISTRY")
        drift_errors = report.errors_by_code("FORMULA_REGISTRY_DRIFT")

        assert len(contract_errors) == 0
        assert len(live_errors) == 0
        assert len(drift_errors) == 0

    def test_missing_from_live_registry_detected(self):
        """OTA-699 reports FORMULA_MISSING_FROM_LIVE_REGISTRY when
        the contract names a formula the live registry lacks."""
        source = _base_config_source(contract_formulas=["test_stub"])
        config = load_config(source)
        empty_registry = DictFormulaRegistry()

        report = validate_config(config, formula_registry=empty_registry)

        errors = report.errors_by_code("FORMULA_MISSING_FROM_LIVE_REGISTRY")
        assert len(errors) >= 1
        assert any("test_stub" in e.message for e in errors)


# ── Tests: registry drift (OD-1 path 3) ──────────────────────────────


class TestRegistryDrift:
    def test_drift_live_has_extra(self):
        """A formula in the live registry but NOT in the SHARED contract
        triggers FORMULA_REGISTRY_DRIFT."""
        source = _base_config_source(contract_formulas=["test_stub"])
        config = load_config(source)

        # Registry has test_stub (matching contract) + drift_formula (extra)
        registry = DictFormulaRegistry()
        registry.register("test_stub", lambda nv, p: 50.0)
        registry.register("drift_formula", lambda nv, p: 50.0)

        report = validate_config(config, formula_registry=registry)
        drift_errors = report.errors_by_code("FORMULA_REGISTRY_DRIFT")
        assert any("drift_formula" in e.message for e in drift_errors)

    def test_drift_contract_has_extra(self):
        """A formula in the SHARED contract but NOT in the live registry
        triggers FORMULA_REGISTRY_DRIFT."""
        source = _base_config_source(
            contract_formulas=["test_stub", "phantom"]
        )
        config = load_config(source)

        # Registry only has test_stub — missing phantom
        registry = DictFormulaRegistry()
        registry.register("test_stub", lambda nv, p: 50.0)

        report = validate_config(config, formula_registry=registry)
        drift_errors = report.errors_by_code("FORMULA_REGISTRY_DRIFT")
        assert any("phantom" in e.message for e in drift_errors)

    def test_no_drift_when_aligned(self):
        """No drift error when contract and live registry match exactly."""
        source = _base_config_source(contract_formulas=["test_stub"])
        config = load_config(source)

        registry = _make_fresh_registry()

        report = validate_config(config, formula_registry=registry)
        drift_errors = report.errors_by_code("FORMULA_REGISTRY_DRIFT")
        assert len(drift_errors) == 0
