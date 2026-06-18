"""
Config-validation test matrix — one fixture per insight_engine.md §6.6 failure
mode (plus the OTA-797 explicit additions), each asserting the **live** loader /
validator rejects the bad config with its **specific structured error identity**.

This is a systematic companion to ``test_validation.py``: where that suite grew
case-by-case alongside OTA-699, this module lays the failure modes out as an
explicit matrix so coverage is auditable against §6.6 at a glance, and asserts
both (a) the specific ``ValidationError.code`` fires and (b) the engine actually
refuses the config (``validate_and_raise`` → ``ConfigValidationError``).

It reuses the **same** validation path under test (OTA-699 /
``app/insight_engine/validation.py``) — there is no parallel/divergent validator
here. A drift between this matrix and the live loader is a defect in one of them.

Self-contained: the fixture builders below are independent of ``test_validation``'s
helpers so this module can be read and reasoned about on its own.

§6.6 failure modes and the structured identity each maps to:

  | # | §6.6 failure mode                                   | identity                          |
  |---|------------------------------------------------------|-----------------------------------|
  | 1 | rule references a named value not in input catalog   | NAMED_VALUE_MISSING               |
  | 2 | junction references a missing rule_id / strategy_id  | JUNCTION_FK_RULE_MISSING /        |
  |   |                                                      | JUNCTION_FK_STRATEGY_MISSING      |
  | 3 | junction omits a parameter in the rule's schema      | JUNCTION_PARAM_MISSING            |
  | 4 | gate junction omits evaluation_order / stop_if_fail  | *loader-level* (see note below)   |
  | 5 | duplicate evaluation_order within (strategy, phase)  | EVAL_ORDER_DUPLICATE              |
  | 6 | active scoring weights don't sum to 1.0              | SCORING_WEIGHTS_NOT_UNITY         |
  | 7 | verdict band set not monotonic                       | VERDICT_BANDS_NOT_MONOTONIC       |
  | 8 | condition references a formula not in the library    | FORMULA_MISSING_FROM_CONTRACT /   |
  |   | (three registry states, exercised separately)        | FORMULA_MISSING_FROM_LIVE_REGISTRY|
  |   |                                                      | / FORMULA_REGISTRY_DRIFT          |
  | 9 | junction parameter violates the rule's type / bound  | JUNCTION_PARAM_TYPE_VIOLATION     |
  |10 | named value's null semantics incompatible w/ rule    | NULL_SEMANTICS_INCOMPATIBLE       |
  | + | terminal_verdict outside its domain (OTA-797)        | TERMINAL_VERDICT_UNKNOWN          |

NOTE on mode #4 (Phase-0 finding, OTA-797): the §6.6 "gate junction omits
evaluation_order / stop_if_fail" mode is enforced at the **loader** layer, not as
a structured ``ValidationError``. ``validation.py::_check_gate_junction_fields`` is
a deliberate no-op; ``loader._row_to_junction`` raises a raw ``KeyError`` /
``TypeError`` instead. The matrix asserts that loader-level rejection directly and
documents the one silent hole (``stop_if_fail=None`` coerces to ``False``) so the
behavior is recorded rather than assumed. No loader change is in scope here
(OTA-797 is test-only).

OTA-797
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pytest

from app.insight_engine.config_source import InMemoryConfigSource
from app.insight_engine.loader import load_config
from app.insight_engine.models import NamedValue, Tier
from app.insight_engine.validation import (
    ConfigValidationError,
    ValidationReport,
    validate_and_raise,
    validate_config,
)


# ── A live-shaped formula registry (membership only — §6.6 needs `has`
#    and `registered_names`) ─────────────────────────────────────────────


class _Registry:
    """Minimal live FormulaRegistry holding a fixed name set."""

    def __init__(self, names: set[str]) -> None:
        self._names = frozenset(names)

    def has(self, name: str) -> bool:
        return name in self._names

    def registered_names(self) -> frozenset[str]:
        return self._names


# ── A complete, clean fixture bundle (the negative control) ──────────────
#
# Every builder returns fresh mutable rows so a perturbation in one case can
# never leak into another.


def _apps() -> list[dict[str, Any]]:
    return [
        {"app_id": "SHARED", "name": "Shared", "status": "active", "enabled": True},
        {"app_id": "OTA", "name": "Options Trade Analyzer", "status": "active", "enabled": True},
    ]


def _rules() -> list[dict[str, Any]]:
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
    ]


def _strategies() -> list[dict[str, Any]]:
    return [
        {
            "strategy_id": 1,
            "owner_app_id": "OTA",
            "strategy_key": "test_strategy",
            "display_name": "Test Strategy",
            "consumer_surface": "SCREENING",
            "description": "A clean test strategy",
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


def _junction() -> list[dict[str, Any]]:
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
    ]


def _lookups() -> list[dict[str, Any]]:
    return [
        # Verdict domain for SCREENING (drives terminal_verdict checks).
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
        # Formula registry contract (SHARED) — must mirror the live registry.
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
    ]


def _catalog() -> dict[str, NamedValue]:
    return {
        "stock_price": NamedValue(
            name="stock_price", tier=Tier.RAW, value_type="number", null_semantics="FAIL_CLOSED"
        ),
        "delta": NamedValue(name="delta", tier=Tier.DERIVED, value_type="number"),
        "long_delta": NamedValue(name="long_delta", tier=Tier.RAW, value_type="number"),
        "short_delta": NamedValue(name="short_delta", tier=Tier.RAW, value_type="number"),
    }


def _registry() -> _Registry:
    return _Registry({"delta_quality", "probability_of_profit"})


@dataclass
class Fixtures:
    """A mutable bundle of every input to load + validate.

    A case mutates exactly one aspect; everything else stays the clean control.
    """

    apps: list[dict[str, Any]]
    rules: list[dict[str, Any]]
    strategies: list[dict[str, Any]]
    junction: list[dict[str, Any]]
    lookups: list[dict[str, Any]]
    catalog: dict[str, NamedValue]
    registry: _Registry

    @classmethod
    def clean(cls) -> "Fixtures":
        return cls(
            apps=_apps(),
            rules=_rules(),
            strategies=_strategies(),
            junction=_junction(),
            lookups=_lookups(),
            catalog=_catalog(),
            registry=_registry(),
        )

    def report(self) -> ValidationReport:
        """Load this config and run the FULL §6.6 suite (catalog + registry +
        FK source all active, so every check is reachable)."""
        source = InMemoryConfigSource(
            apps=self.apps,
            rules=self.rules,
            strategies=self.strategies,
            junction=self.junction,
            lookups=self.lookups,
        )
        config = load_config(source)
        return validate_config(
            config,
            input_catalog=self.catalog,
            formula_registry=self.registry,
            source=source,
        )

    def raise_if_invalid(self) -> None:
        """The fail-closed gate — raises ConfigValidationError on any failure."""
        source = InMemoryConfigSource(
            apps=self.apps,
            rules=self.rules,
            strategies=self.strategies,
            junction=self.junction,
            lookups=self.lookups,
        )
        config = load_config(source)
        validate_and_raise(
            config,
            input_catalog=self.catalog,
            formula_registry=self.registry,
            source=source,
        )


# ── Perturbations — each mutates the clean bundle to trip exactly one mode ─


def _perturb_named_value_missing(f: Fixtures) -> None:
    # Rule references a named value the catalog does not declare.
    f.rules[0]["referenced_named_values"] = ["nonexistent_value"]


def _perturb_fk_strategy_missing(f: Fixtures) -> None:
    # Enabled junction row points at a strategy_id with no row at all.
    f.junction.append({
        "junction_id": 99,
        "strategy_id": 999,
        "rule_id": 1,
        "evaluation_order": 10,
        "stop_if_fail": True,
        "score_penalty": None,
        "weight": None,
        "parameters": {"min_price": 5.0},
        "terminal_verdict": None,
        "rationale": "orphan strategy ref",
        "enabled": True,
    })


def _perturb_fk_rule_missing(f: Fixtures) -> None:
    # Enabled junction row points at a rule_id with no row at all.
    f.junction.append({
        "junction_id": 98,
        "strategy_id": 1,
        "rule_id": 888,
        "evaluation_order": 11,
        "stop_if_fail": True,
        "score_penalty": None,
        "weight": None,
        "parameters": {},
        "terminal_verdict": None,
        "rationale": "orphan rule ref",
        "enabled": True,
    })


def _perturb_param_missing(f: Fixtures) -> None:
    # Gate's required `min_price` parameter is not supplied by the junction.
    f.junction[0]["parameters"] = {}


def _perturb_param_type(f: Fixtures) -> None:
    # `min_price` declared number; a string violates the type.
    f.junction[0]["parameters"] = {"min_price": "not_a_number"}


def _perturb_param_below_min(f: Fixtures) -> None:
    # `min_price` has min=0; -5 is below bound.
    f.junction[0]["parameters"] = {"min_price": -5.0}


def _perturb_param_above_max(f: Fixtures) -> None:
    # `delta_center` has max=1; 1.5 is above bound (keep the other param valid).
    f.junction[1]["parameters"] = {"delta_center": 1.5, "delta_half_range": 0.15}


def _perturb_eval_order_duplicate(f: Fixtures) -> None:
    # Add a second gate rule sharing evaluation_order=1 within (strategy, gate).
    f.rules.append({
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
    f.junction.append({
        "junction_id": 5,
        "strategy_id": 1,
        "rule_id": 5,
        "evaluation_order": 1,  # collides with min_price_gate (also order 1)
        "stop_if_fail": True,
        "score_penalty": None,
        "weight": None,
        "parameters": {},
        "terminal_verdict": None,
        "rationale": "Liquidity",
        "enabled": True,
    })


def _perturb_weights_low(f: Fixtures) -> None:
    f.junction[1]["weight"] = 0.3  # 0.3 + 0.4 = 0.7 ≠ 1.0


def _perturb_weights_high(f: Fixtures) -> None:
    f.junction[1]["weight"] = 0.9  # 0.9 + 0.4 = 1.3 ≠ 1.0


def _perturb_bands_non_monotonic(f: Fixtures) -> None:
    f.strategies[0]["verdict_band_set"] = [
        {"verdict": "EXECUTE", "min_score": 70, "max_score": 100},
        {"verdict": "WAIT", "min_score": 80, "max_score": 90},  # 80 >= 70 → not descending
    ]


def _perturb_null_semantics(f: Fixtures) -> None:
    # FAIL_CLOSED rule (min_price_gate) referencing a FAIL_OPEN named value.
    f.catalog["stock_price"] = NamedValue(
        name="stock_price", tier=Tier.RAW, value_type="number", null_semantics="FAIL_OPEN"
    )


def _perturb_terminal_verdict_unknown(f: Fixtures) -> None:
    f.junction[0]["terminal_verdict"] = "BOGUS_VERDICT"


# (id, perturbation, expected_code) — each isolated to exactly one code.
_MATRIX: list[tuple[str, Callable[[Fixtures], None], str]] = [
    ("named_value_missing", _perturb_named_value_missing, "NAMED_VALUE_MISSING"),
    ("fk_strategy_missing", _perturb_fk_strategy_missing, "JUNCTION_FK_STRATEGY_MISSING"),
    ("fk_rule_missing", _perturb_fk_rule_missing, "JUNCTION_FK_RULE_MISSING"),
    ("junction_param_missing", _perturb_param_missing, "JUNCTION_PARAM_MISSING"),
    ("param_type_violation", _perturb_param_type, "JUNCTION_PARAM_TYPE_VIOLATION"),
    ("param_below_min", _perturb_param_below_min, "JUNCTION_PARAM_TYPE_VIOLATION"),
    ("param_above_max", _perturb_param_above_max, "JUNCTION_PARAM_TYPE_VIOLATION"),
    ("eval_order_duplicate", _perturb_eval_order_duplicate, "EVAL_ORDER_DUPLICATE"),
    ("weights_too_low", _perturb_weights_low, "SCORING_WEIGHTS_NOT_UNITY"),
    ("weights_too_high", _perturb_weights_high, "SCORING_WEIGHTS_NOT_UNITY"),
    ("bands_non_monotonic", _perturb_bands_non_monotonic, "VERDICT_BANDS_NOT_MONOTONIC"),
    ("null_semantics_incompatible", _perturb_null_semantics, "NULL_SEMANTICS_INCOMPATIBLE"),
    ("terminal_verdict_unknown", _perturb_terminal_verdict_unknown, "TERMINAL_VERDICT_UNKNOWN"),
]


# ── The matrix: each isolated mode trips its specific code, AND is refused ─


class TestValidationMatrix:
    @pytest.mark.parametrize(
        "perturb, expected_code",
        [(p, code) for _id, p, code in _MATRIX],
        ids=[i for i, _p, _c in _MATRIX],
    )
    def test_specific_code_fires(self, perturb, expected_code):
        f = Fixtures.clean()
        perturb(f)
        report = f.report()
        codes = report.errors_by_code(expected_code)
        assert codes, (
            f"expected at least one {expected_code}; got {report.summary()}"
        )

    @pytest.mark.parametrize(
        "perturb, expected_code",
        [(p, code) for _id, p, code in _MATRIX],
        ids=[i for i, _p, _c in _MATRIX],
    )
    def test_isolated_to_one_code(self, perturb, expected_code):
        """One perturbed field trips exactly one distinct code (isolation)."""
        f = Fixtures.clean()
        perturb(f)
        report = f.report()
        distinct = {e.code for e in report.errors}
        assert distinct == {expected_code}, (
            f"expected only {expected_code}; got {sorted(distinct)}\n{report.summary()}"
        )

    @pytest.mark.parametrize(
        "perturb, expected_code",
        [(p, code) for _id, p, code in _MATRIX],
        ids=[i for i, _p, _c in _MATRIX],
    )
    def test_engine_refuses_config(self, perturb, expected_code):
        """The fail-closed gate raises, and the identity is in the report."""
        f = Fixtures.clean()
        perturb(f)
        with pytest.raises(ConfigValidationError) as exc:
            f.raise_if_invalid()
        assert expected_code in str(exc.value)
        assert not exc.value.report.is_valid


# ── The three formula-registry states, exercised SEPARATELY (OTA-797) ─────
#
# §6.6 "a condition expression references a formula not in the registered rule
# library" splits into three reachable states. Contract-missing and
# registry-missing each ALSO surface a drift error by design (the contract and
# live registry genuinely disagree about a referenced formula); the standalone
# drift cases below prove DRIFT is reachable on its own, distinct from the two
# "missing" identities.


class TestFormulaRegistryStates:
    def test_missing_from_contract(self):
        # Drop delta_quality from the SHARED contract; the live registry keeps it.
        f = Fixtures.clean()
        f.lookups = [
            l for l in f.lookups
            if not (l["lookup_set"] == "formula_registry" and l["lookup_key"] == "delta_quality")
        ]
        report = f.report()
        errs = report.errors_by_code("FORMULA_MISSING_FROM_CONTRACT")
        assert errs and any("delta_quality" in e.message for e in errs), report.summary()

    def test_missing_from_live_registry(self):
        # Live registry lacks delta_quality; the contract keeps it.
        f = Fixtures.clean()
        f.registry = _Registry({"probability_of_profit"})
        report = f.report()
        errs = report.errors_by_code("FORMULA_MISSING_FROM_LIVE_REGISTRY")
        assert errs and any("delta_quality" in e.message for e in errs), report.summary()

    def test_drift_contract_only_is_standalone(self):
        # A phantom formula present only in the contract, referenced by no rule:
        # pure DRIFT, NOT a FORMULA_MISSING_FROM_CONTRACT (that check runs on
        # rule formula_refs, which never reference the phantom).
        f = Fixtures.clean()
        f.lookups.append({
            "owner_app_id": "SHARED",
            "lookup_set": "formula_registry",
            "lookup_key": "phantom_formula",
            "payload": '{"intent": "ghost in the contract"}',
            "sort_order": 99,
            "enabled": True,
        })
        report = f.report()
        drift = report.errors_by_code("FORMULA_REGISTRY_DRIFT")
        assert any("phantom_formula" in e.message for e in drift), report.summary()
        assert report.errors_by_code("FORMULA_MISSING_FROM_CONTRACT") == []

    def test_drift_live_only_is_standalone(self):
        # An extra formula present only in the live registry: pure DRIFT, NOT a
        # FORMULA_MISSING_FROM_LIVE_REGISTRY.
        f = Fixtures.clean()
        f.registry = _Registry({"delta_quality", "probability_of_profit", "extra_live_formula"})
        report = f.report()
        drift = report.errors_by_code("FORMULA_REGISTRY_DRIFT")
        assert any("extra_live_formula" in e.message for e in drift), report.summary()
        assert report.errors_by_code("FORMULA_MISSING_FROM_LIVE_REGISTRY") == []


# ── Mode #4: gate junction omits evaluation_order / stop_if_fail ──────────
#
# Phase-0 finding (OTA-797): this §6.6 mode is enforced at the LOADER layer, not
# as a structured ValidationError. `_check_gate_junction_fields` is a no-op;
# `loader._row_to_junction` raises raw KeyError / TypeError. These tests assert
# that loader-level rejection directly — and document the one silent hole.


class TestGateJunctionFieldOmission:
    def _load(self, junction: list[dict[str, Any]]):
        source = InMemoryConfigSource(
            apps=_apps(),
            rules=_rules(),
            strategies=_strategies(),
            junction=junction,
            lookups=_lookups(),
        )
        return load_config(source)

    def test_missing_evaluation_order_key_raises_at_load(self):
        junction = _junction()
        del junction[0]["evaluation_order"]
        with pytest.raises(KeyError):
            self._load(junction)

    def test_none_evaluation_order_raises_at_load(self):
        junction = _junction()
        junction[0]["evaluation_order"] = None  # int(None) → TypeError
        with pytest.raises(TypeError):
            self._load(junction)

    def test_missing_stop_if_fail_key_raises_at_load(self):
        junction = _junction()
        del junction[0]["stop_if_fail"]
        with pytest.raises(KeyError):
            self._load(junction)

    def test_none_stop_if_fail_silently_coerces_to_false(self):
        """DOCUMENTED GAP (OTA-797 Phase 0): an explicit stop_if_fail=None is
        coerced to False by `bool(None)` in the loader — it does NOT raise and is
        NOT flagged by any structured check. Recorded here so the behavior is a
        deliberate, visible contract rather than a silent surprise. If the loader
        is hardened later to reject None explicitly, update this test.
        """
        junction = _junction()
        junction[0]["stop_if_fail"] = None
        config = self._load(junction)  # must NOT raise
        rule_set = config.rule_sets["test_strategy"]
        gate = next(b for b in rule_set.bindings if b.rule.rule_key == "min_price_gate")
        assert gate.junction.stop_if_fail is False


# ── Negative control: a clean config loads and validates with zero errors ─


class TestValidConfigControl:
    def test_clean_config_is_valid(self):
        report = Fixtures.clean().report()
        assert report.is_valid, report.summary()

    def test_clean_config_is_not_refused(self):
        # The fail-closed gate must NOT raise on a clean config.
        Fixtures.clean().raise_if_invalid()
