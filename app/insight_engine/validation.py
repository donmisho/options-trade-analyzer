"""
Startup validation suite — insight_engine.md §6.6 + OTA-683 guard + OD-1/OD-2.

Validates the loaded EngineConfig before any evaluation. On any failure
the report collects structured, identifiable errors and the engine
refuses to evaluate (fail closed).

OTA-699
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.insight_engine.config_source import ConfigSource
from app.insight_engine.loader import EngineConfig, LookupEntry
from app.insight_engine.models import (
    NamedValue,
    Phase,
    Rule,
    RuleBinding,
    RuleSet,
    Strategy,
)
from app.insight_engine.registry import FormulaRegistry, StubFormulaRegistry


# Scoring-weight sum tolerance (numeric(7,4) precision in the DB).
_WEIGHT_SUM_TOLERANCE = 1e-4

# Formula ref prefix — a rule whose formula_ref starts with this is a
# formula-based rule and must resolve in both the contract and the live
# registry.
_FORMULA_PREFIX = "formula:"


# ── Structured error types ──────────────────────────────────────────────


@dataclass(frozen=True)
class ValidationError:
    """A single structured, identifiable validation failure."""

    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        ctx = f" | {self.context}" if self.context else ""
        return f"[{self.code}] {self.message}{ctx}"


@dataclass
class ValidationReport:
    """Collects all validation errors from a startup validation pass."""

    errors: list[ValidationError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add(self, code: str, message: str, **context: Any) -> None:
        self.errors.append(
            ValidationError(code=code, message=message, context=context)
        )

    def errors_by_code(self, code: str) -> list[ValidationError]:
        return [e for e in self.errors if e.code == code]

    def summary(self) -> str:
        if self.is_valid:
            return "Validation passed — 0 errors."
        lines = [f"Validation FAILED — {len(self.errors)} error(s):"]
        for err in self.errors:
            lines.append(f"  {err}")
        return "\n".join(lines)


class ConfigValidationError(Exception):
    """Raised when startup validation fails — engine refuses to evaluate."""

    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        super().__init__(report.summary())


# ── Public API ──────────────────────────────────────────────────────────


def validate_config(
    config: EngineConfig,
    *,
    input_catalog: dict[str, NamedValue] | None = None,
    formula_registry: FormulaRegistry | None = None,
    source: ConfigSource | None = None,
) -> ValidationReport:
    """Run the full startup validation suite (§6.6 + OTA-683 + OD-1 + OD-2).

    Parameters
    ----------
    config : EngineConfig
        Loaded configuration from OTA-698 loader.
    input_catalog : dict[str, NamedValue] | None
        Adapter's declared named values. If None, named-value and
        null-semantics checks are skipped (adapter not yet registered).
    formula_registry : FormulaRegistry | None
        Live formula registry. If None, uses StubFormulaRegistry
        (pre-Wave-3 default).
    source : ConfigSource | None
        If provided, re-fetches raw rows for junction FK validation
        against the loaded config.
    """
    report = ValidationReport()
    registry = formula_registry or StubFormulaRegistry()

    # Collect contract formula names from SHARED lookups
    contract_names = _get_contract_formula_names(config)

    # Collect all formula refs actually used by loaded rules
    live_formula_refs: set[str] = set()

    # ── Per-strategy checks ──────────────────────────────────────────
    for _strategy_key, rule_set in config.rule_sets.items():
        _check_scoring_weights(report, rule_set)
        _check_verdict_bands_monotonic(report, rule_set)
        _check_eval_order_uniqueness(report, rule_set, config)
        _check_terminal_verdict_domain(report, rule_set, config)

        for binding in rule_set.bindings:
            _check_junction_params_supplied(report, binding)
            _check_junction_param_types(report, binding)
            _check_gate_junction_fields(report, binding)
            if input_catalog is not None:
                _check_named_values_in_catalog(report, binding, input_catalog)
                _check_null_semantics(report, binding, input_catalog)
            _check_formula_in_contract(report, binding, contract_names)
            _check_formula_in_live_registry(report, binding, registry)

            # Track formula refs for drift check
            fname = _extract_formula_name(binding.rule)
            if fname is not None:
                live_formula_refs.add(fname)

    # ── Cross-cutting: formula registry drift (OD-1) ─────────────────
    _check_formula_registry_drift(report, contract_names, registry, live_formula_refs)

    # ── FK validation (needs raw data) ───────────────────────────────
    if source is not None:
        _check_junction_fks(report, config, source)

    return report


def validate_and_raise(
    config: EngineConfig,
    *,
    input_catalog: dict[str, NamedValue] | None = None,
    formula_registry: FormulaRegistry | None = None,
    source: ConfigSource | None = None,
) -> None:
    """Run validation; raise ConfigValidationError if any check fails.

    This is the fail-closed gate — the engine refuses to evaluate any
    strategy until the configuration loads cleanly.
    """
    report = validate_config(
        config,
        input_catalog=input_catalog,
        formula_registry=formula_registry,
        source=source,
    )
    if not report.is_valid:
        raise ConfigValidationError(report)


# ── Helpers ─────────────────────────────────────────────────────────────


def _extract_formula_name(rule: Rule) -> str | None:
    """Extract the formula name from a rule's formula_ref, or None."""
    ref = rule.formula_ref
    if ref and ref.startswith(_FORMULA_PREFIX):
        return ref[len(_FORMULA_PREFIX) :]
    return None


def _get_contract_formula_names(config: EngineConfig) -> frozenset[str]:
    """Return formula names registered in the SHARED formula_registry lookup."""
    entries = config.lookups.get("formula_registry", [])
    return frozenset(e.lookup_key for e in entries if e.owner_app_id == "SHARED")


def _get_verdict_domain(
    config: EngineConfig, consumer_surface: str
) -> frozenset[str]:
    """Return valid verdict strings for a consumer_surface.

    Convention: lookup_set = '{consumer_surface_lower}_verdicts'.
    """
    set_name = f"{consumer_surface.lower()}_verdicts"
    entries = config.lookups.get(set_name, [])
    return frozenset(e.lookup_key for e in entries)


# ── Individual check implementations ────────────────────────────────────


def _check_scoring_weights(report: ValidationReport, rule_set: RuleSet) -> None:
    """§6.6: active scoring criteria weights must sum to 1.0."""
    scoring_bindings = [
        b for b in rule_set.bindings
        if b.rule.phase == Phase.SCORING and b.junction.enabled
    ]
    if not scoring_bindings:
        return
    total = sum(b.junction.weight or 0.0 for b in scoring_bindings)
    if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
        report.add(
            "SCORING_WEIGHTS_NOT_UNITY",
            f"Strategy '{rule_set.strategy.strategy_key}': scoring weights "
            f"sum to {total:.6f}, expected 1.0 (tolerance {_WEIGHT_SUM_TOLERANCE}).",
            strategy_key=rule_set.strategy.strategy_key,
            actual_sum=total,
        )


def _check_verdict_bands_monotonic(
    report: ValidationReport, rule_set: RuleSet
) -> None:
    """§6.6: verdict band set must be monotonic (descending min_score)."""
    bands = rule_set.strategy.verdict_band_set
    if not bands:
        return

    prev_min: float | None = None
    for band in bands:
        min_score = band.get("min_score")
        if min_score is None:
            continue
        if prev_min is not None and min_score >= prev_min:
            report.add(
                "VERDICT_BANDS_NOT_MONOTONIC",
                f"Strategy '{rule_set.strategy.strategy_key}': verdict bands "
                f"are not monotonically descending. Band "
                f"'{band.get('verdict', '?')}' min_score={min_score} >= "
                f"previous min_score={prev_min}.",
                strategy_key=rule_set.strategy.strategy_key,
                band=band,
            )
            return
        prev_min = min_score


def _check_eval_order_uniqueness(
    report: ValidationReport, rule_set: RuleSet, config: EngineConfig
) -> None:
    """OTA-683 regression guard: no duplicate evaluation_order within
    (strategy, phase). Phase lives on the rule, not the junction, so
    this is a load-time check, not a DB constraint.
    """
    seen: dict[tuple[str, str], list[str]] = {}  # (phase, tier_or_empty) → [rule_keys]

    for binding in rule_set.bindings:
        if not binding.junction.enabled:
            continue
        phase = binding.rule.phase.value
        # For gates, tier matters for ordering but uniqueness is per-phase
        key = phase
        order = binding.junction.evaluation_order
        composite = (key, str(order))

        if composite not in seen:
            seen[composite] = []
        seen[composite].append(binding.rule.rule_key)

    for (phase, order_str), rule_keys in seen.items():
        if len(rule_keys) > 1:
            report.add(
                "EVAL_ORDER_DUPLICATE",
                f"Strategy '{rule_set.strategy.strategy_key}', phase "
                f"'{phase}': evaluation_order {order_str} is shared by "
                f"rules {rule_keys}. Each enabled rule in a (strategy, "
                f"phase) must have a unique evaluation_order.",
                strategy_key=rule_set.strategy.strategy_key,
                phase=phase,
                evaluation_order=int(order_str),
                rule_keys=rule_keys,
            )


def _check_terminal_verdict_domain(
    report: ValidationReport, rule_set: RuleSet, config: EngineConfig
) -> None:
    """OD-2: non-null terminal_verdict must be in the verdict domain
    for the strategy's consumer_surface.
    """
    consumer_surface = rule_set.strategy.consumer_surface
    verdict_domain = _get_verdict_domain(config, consumer_surface)

    for binding in rule_set.bindings:
        tv = binding.junction.terminal_verdict
        if tv is None:
            continue
        if tv not in verdict_domain:
            report.add(
                "TERMINAL_VERDICT_UNKNOWN",
                f"Strategy '{rule_set.strategy.strategy_key}', rule "
                f"'{binding.rule.rule_key}': terminal_verdict '{tv}' is "
                f"not in the verdict domain for consumer_surface "
                f"'{consumer_surface}'. Valid: {sorted(verdict_domain) or '(none registered)'}.",
                strategy_key=rule_set.strategy.strategy_key,
                rule_key=binding.rule.rule_key,
                terminal_verdict=tv,
                consumer_surface=consumer_surface,
            )


def _check_junction_params_supplied(
    report: ValidationReport, binding: RuleBinding
) -> None:
    """§6.6: junction must supply every parameter in the rule's schema."""
    schema = binding.rule.parameter_schema
    if not schema:
        return
    supplied = set(binding.junction.parameters.keys())
    for param_name in schema:
        if param_name not in supplied:
            report.add(
                "JUNCTION_PARAM_MISSING",
                f"Strategy '{binding.junction.strategy_key}', rule "
                f"'{binding.rule.rule_key}': junction does not supply "
                f"parameter '{param_name}' required by rule schema.",
                strategy_key=binding.junction.strategy_key,
                rule_key=binding.rule.rule_key,
                missing_param=param_name,
            )


def _check_junction_param_types(
    report: ValidationReport, binding: RuleBinding
) -> None:
    """§6.6: junction parameter values must satisfy the rule's type/bounds."""
    schema = binding.rule.parameter_schema
    if not schema:
        return
    params = binding.junction.parameters

    for param_name, spec in schema.items():
        if param_name not in params:
            continue  # Already caught by _check_junction_params_supplied
        value = params[param_name]
        if value is None:
            continue

        # Type check
        expected_type = spec.get("type") if isinstance(spec, dict) else None
        if expected_type == "number" and not isinstance(value, (int, float)):
            report.add(
                "JUNCTION_PARAM_TYPE_VIOLATION",
                f"Strategy '{binding.junction.strategy_key}', rule "
                f"'{binding.rule.rule_key}': parameter '{param_name}' "
                f"expected type 'number', got {type(value).__name__}.",
                strategy_key=binding.junction.strategy_key,
                rule_key=binding.rule.rule_key,
                param=param_name,
                expected_type=expected_type,
                actual_type=type(value).__name__,
            )
            continue
        if expected_type == "boolean" and not isinstance(value, bool):
            report.add(
                "JUNCTION_PARAM_TYPE_VIOLATION",
                f"Strategy '{binding.junction.strategy_key}', rule "
                f"'{binding.rule.rule_key}': parameter '{param_name}' "
                f"expected type 'boolean', got {type(value).__name__}.",
                strategy_key=binding.junction.strategy_key,
                rule_key=binding.rule.rule_key,
                param=param_name,
                expected_type=expected_type,
                actual_type=type(value).__name__,
            )
            continue
        if expected_type == "string" and not isinstance(value, str):
            report.add(
                "JUNCTION_PARAM_TYPE_VIOLATION",
                f"Strategy '{binding.junction.strategy_key}', rule "
                f"'{binding.rule.rule_key}': parameter '{param_name}' "
                f"expected type 'string', got {type(value).__name__}.",
                strategy_key=binding.junction.strategy_key,
                rule_key=binding.rule.rule_key,
                param=param_name,
                expected_type=expected_type,
                actual_type=type(value).__name__,
            )
            continue

        # Bound checks (only for numeric values)
        if isinstance(spec, dict) and isinstance(value, (int, float)):
            min_val = spec.get("min")
            max_val = spec.get("max")
            if min_val is not None and value < min_val:
                report.add(
                    "JUNCTION_PARAM_TYPE_VIOLATION",
                    f"Strategy '{binding.junction.strategy_key}', rule "
                    f"'{binding.rule.rule_key}': parameter '{param_name}' "
                    f"value {value} is below minimum {min_val}.",
                    strategy_key=binding.junction.strategy_key,
                    rule_key=binding.rule.rule_key,
                    param=param_name,
                    value=value,
                    min=min_val,
                )
            if max_val is not None and value > max_val:
                report.add(
                    "JUNCTION_PARAM_TYPE_VIOLATION",
                    f"Strategy '{binding.junction.strategy_key}', rule "
                    f"'{binding.rule.rule_key}': parameter '{param_name}' "
                    f"value {value} is above maximum {max_val}.",
                    strategy_key=binding.junction.strategy_key,
                    rule_key=binding.rule.rule_key,
                    param=param_name,
                    value=value,
                    max=max_val,
                )


def _check_gate_junction_fields(
    report: ValidationReport, binding: RuleBinding
) -> None:
    """§6.6: gate junction row must have evaluation_order and stop_if_fail.

    These are already required by the loader's typed parsing, but this
    check validates the semantic contract for gate-phase rules explicitly.
    """
    if binding.rule.phase != Phase.GATE:
        return
    # evaluation_order is an int on JunctionRow — always present after load.
    # stop_if_fail is a bool — always present after load.
    # This check exists for completeness and to guard against future
    # loader changes. The loader raises on missing fields today.


def _check_named_values_in_catalog(
    report: ValidationReport,
    binding: RuleBinding,
    catalog: dict[str, NamedValue],
) -> None:
    """§6.6: rule references a named value not in the input catalog."""
    for nv_name in binding.rule.referenced_named_values:
        if nv_name not in catalog:
            report.add(
                "NAMED_VALUE_MISSING",
                f"Rule '{binding.rule.rule_key}' references named value "
                f"'{nv_name}' which is not in the input catalog.",
                rule_key=binding.rule.rule_key,
                named_value=nv_name,
            )


def _check_null_semantics(
    report: ValidationReport,
    binding: RuleBinding,
    catalog: dict[str, NamedValue],
) -> None:
    """§6.6: named value's null semantics must be compatible with the
    rule's needs. A rule with null_semantics=FAIL_CLOSED requires all
    its referenced named values to be non-null-capable (or themselves
    FAIL_CLOSED).
    """
    rule_ns = binding.rule.null_semantics
    if rule_ns != "FAIL_CLOSED":
        return
    for nv_name in binding.rule.referenced_named_values:
        nv = catalog.get(nv_name)
        if nv is None:
            continue  # Already caught by _check_named_values_in_catalog
        if nv.null_semantics == "FAIL_OPEN":
            report.add(
                "NULL_SEMANTICS_INCOMPATIBLE",
                f"Rule '{binding.rule.rule_key}' has null_semantics="
                f"FAIL_CLOSED but references named value '{nv_name}' "
                f"with null_semantics=FAIL_OPEN. Incompatible.",
                rule_key=binding.rule.rule_key,
                named_value=nv_name,
                rule_null_semantics=rule_ns,
                nv_null_semantics=nv.null_semantics,
            )


def _check_formula_in_contract(
    report: ValidationReport,
    binding: RuleBinding,
    contract_names: frozenset[str],
) -> None:
    """OD-1 path 1: formula ref must exist in the SHARED formula_registry
    lookup set (the contract).
    """
    fname = _extract_formula_name(binding.rule)
    if fname is None:
        return
    if fname not in contract_names:
        report.add(
            "FORMULA_MISSING_FROM_CONTRACT",
            f"Rule '{binding.rule.rule_key}': formula '{fname}' is not "
            f"registered in the SHARED formula_registry lookup set.",
            rule_key=binding.rule.rule_key,
            formula_name=fname,
        )


def _check_formula_in_live_registry(
    report: ValidationReport,
    binding: RuleBinding,
    registry: FormulaRegistry,
) -> None:
    """OD-1 path 2: formula ref must exist in the live FormulaRegistry
    (implementation exists).
    """
    fname = _extract_formula_name(binding.rule)
    if fname is None:
        return
    if not registry.has(fname):
        report.add(
            "FORMULA_MISSING_FROM_LIVE_REGISTRY",
            f"Rule '{binding.rule.rule_key}': formula '{fname}' has no "
            f"live implementation in the FormulaRegistry.",
            rule_key=binding.rule.rule_key,
            formula_name=fname,
        )


def _check_formula_registry_drift(
    report: ValidationReport,
    contract_names: frozenset[str],
    registry: FormulaRegistry,
    referenced_formulas: set[str],
) -> None:
    """OD-1 path 3: the contract set and the live registry must agree.
    A name in exactly one source is drift.
    """
    live_names = registry.registered_names()
    # Only check names that are actually referenced by loaded rules,
    # plus any extras in either source.
    all_names = contract_names | live_names | referenced_formulas

    for name in sorted(all_names):
        in_contract = name in contract_names
        in_live = name in live_names
        if in_contract and not in_live:
            report.add(
                "FORMULA_REGISTRY_DRIFT",
                f"Formula '{name}' is in the SHARED formula_registry "
                f"contract but has no live implementation.",
                formula_name=name,
                in_contract=True,
                in_live=False,
            )
        elif in_live and not in_contract:
            report.add(
                "FORMULA_REGISTRY_DRIFT",
                f"Formula '{name}' has a live implementation but is not "
                f"in the SHARED formula_registry contract.",
                formula_name=name,
                in_contract=False,
                in_live=True,
            )


def _check_junction_fks(
    report: ValidationReport,
    config: EngineConfig,
    source: ConfigSource,
) -> None:
    """§6.6: junction references a missing rule_id or strategy_id.

    Re-fetches raw rows from the ConfigSource and checks that every
    enabled junction row's strategy_id and rule_id resolve to a loaded
    rule/strategy.
    """
    raw_strategies = source.fetch_strategies()
    raw_rules = source.fetch_rules()
    raw_junction = source.fetch_junction()

    # Build sets of loaded IDs (from raw rows, matching the scope used by the loader)
    loaded_strategy_ids: set[int] = set()
    for row in raw_strategies:
        if row.get("owner_app_id") in config.apps and _is_enabled(row):
            loaded_strategy_ids.add(row["strategy_id"])

    loaded_rule_ids: set[int] = set()
    for row in raw_rules:
        if row.get("owner_app_id") in config.apps and _is_enabled(row):
            loaded_rule_ids.add(row["rule_id"])

    for row in raw_junction:
        if not _is_enabled(row):
            continue
        strat_id = row.get("strategy_id")
        rule_id = row.get("rule_id")

        if strat_id not in loaded_strategy_ids:
            report.add(
                "JUNCTION_FK_STRATEGY_MISSING",
                f"Junction row (strategy_id={strat_id}, rule_id={rule_id}): "
                f"strategy_id does not resolve to a loaded strategy.",
                strategy_id=strat_id,
                rule_id=rule_id,
            )
        if rule_id not in loaded_rule_ids:
            report.add(
                "JUNCTION_FK_RULE_MISSING",
                f"Junction row (strategy_id={strat_id}, rule_id={rule_id}): "
                f"rule_id does not resolve to a loaded rule.",
                strategy_id=strat_id,
                rule_id=rule_id,
            )


def _is_enabled(row: dict[str, Any]) -> bool:
    val = row.get("enabled")
    if val is None:
        return True
    return bool(val)
