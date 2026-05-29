"""
Config loader — hydrates the in-memory model from an injected ConfigSource.

Reads the five engine_* tables, filters to enabled rows, parses JSON
columns, and resolves each strategy into a RuleSet ordered by
evaluation_order within phase (gate phases sequenced RAW → DERIVED →
COMPUTED).

OTA-698
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from app.insight_engine.config_source import ConfigSource, RawRow
from app.insight_engine.expressions import UnsupportedExpressionError, validate_expression
from app.insight_engine.models import (
    JunctionRow,
    Phase,
    Rule,
    RuleBinding,
    RuleSet,
    Strategy,
    Tier,
)


# ── Phase ordering for gate tier sequencing ──────────────────────────────

# Gate phases run RAW → DERIVED → COMPUTED; then scoring, adjustment, verdict.
# This maps (phase, tier) to a sort key for binding ordering.
_TIER_ORDER = {Tier.RAW: 0, Tier.DERIVED: 1, Tier.COMPUTED: 2}

_PHASE_ORDER = {
    Phase.GATE: 0,
    Phase.SCORING: 1,
    Phase.ADJUSTMENT: 2,
    Phase.VERDICT: 3,
}


def _binding_sort_key(binding: RuleBinding) -> tuple[int, int, int]:
    """Sort key: (phase_order, tier_order_for_gates, evaluation_order)."""
    phase_ord = _PHASE_ORDER.get(binding.rule.phase, 99)
    tier_ord = _TIER_ORDER.get(binding.rule.tier, 99) if binding.rule.phase == Phase.GATE else 0
    return (phase_ord, tier_ord, binding.junction.evaluation_order)


# ── JSON parsing helpers ─────────────────────────────────────────────────

def _parse_json(value: Any, fallback: Any = None) -> Any:
    """Parse a JSON string; return fallback if None or empty."""
    if value is None:
        return fallback
    if isinstance(value, str):
        if not value.strip():
            return fallback
        return json.loads(value)
    # Already parsed (e.g. from InMemoryConfigSource)
    return value


def _parse_json_list(value: Any) -> list:
    result = _parse_json(value, [])
    return result if isinstance(result, list) else []


def _parse_json_dict(value: Any) -> dict:
    result = _parse_json(value, {})
    return result if isinstance(result, dict) else {}


# ── Row → dataclass mappers ─────────────────────────────────────────────

def _parse_phase(raw: str | None) -> Phase:
    if raw is None:
        raise ValueError("phase is required")
    return Phase(raw.lower().strip())


def _parse_tier(raw: str | None) -> Tier | None:
    if raw is None:
        return None
    return Tier(raw.upper().strip())


def _row_to_rule(row: RawRow) -> tuple[int, str, Rule]:
    """Returns (rule_id, owner_app_id, Rule)."""
    ref_nv = _parse_json_list(row.get("referenced_named_values"))
    param_schema = _parse_json_dict(row.get("parameter_schema"))

    rule = Rule(
        rule_key=row["rule_key"],
        phase=_parse_phase(row.get("phase")),
        tier=_parse_tier(row.get("tier")),
        intent=row.get("intent"),
        condition_expression=row.get("condition_expression"),
        formula_ref=row.get("formula_ref"),
        referenced_named_values=tuple(ref_nv),
        parameter_schema=param_schema,
        null_semantics=row.get("null_semantics"),
    )
    return row["rule_id"], row["owner_app_id"], rule


def _row_to_strategy(row: RawRow) -> tuple[int, str, Strategy]:
    """Returns (strategy_id, owner_app_id, Strategy)."""
    compat = _parse_json(row.get("compatible_structures"))
    compat_tuple = tuple(compat) if isinstance(compat, list) else None
    bands = _parse_json(row.get("verdict_band_set"), [])
    bands_list = bands if isinstance(bands, list) else [bands] if isinstance(bands, dict) else []

    strategy = Strategy(
        strategy_key=row["strategy_key"],
        display_name=row["display_name"],
        consumer_surface=row["consumer_surface"],
        description=row.get("description"),
        compatible_structures=compat_tuple,
        verdict_band_set=bands_list,
        dte_min=row.get("dte_min"),
        dte_max=row.get("dte_max"),
    )
    return row["strategy_id"], row["owner_app_id"], strategy


def _row_to_junction(row: RawRow, strategy_key: str, rule_key: str) -> JunctionRow:
    """Map a junction row dict to a JunctionRow dataclass."""
    params = _parse_json_dict(row.get("parameters"))

    score_penalty = row.get("score_penalty")
    weight = row.get("weight")

    return JunctionRow(
        strategy_key=strategy_key,
        rule_key=rule_key,
        evaluation_order=int(row["evaluation_order"]),
        stop_if_fail=bool(row["stop_if_fail"]),
        score_penalty=float(score_penalty) if score_penalty is not None else None,
        weight=float(weight) if weight is not None else None,
        parameters=params,
        rationale=row.get("rationale"),
        enabled=bool(row.get("enabled", True)),
        terminal_verdict=row.get("terminal_verdict"),
    )


# ── Lookup model ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LookupEntry:
    """A parsed engine_lookups row."""
    owner_app_id: str
    lookup_set: str
    lookup_key: str
    payload: Any  # parsed JSON
    sort_order: int | None


# ── Loaded config container ──────────────────────────────────────────────

@dataclass
class EngineConfig:
    """The fully loaded and resolved in-memory configuration."""
    rule_sets: dict[str, RuleSet]  # strategy_key → RuleSet
    rules: dict[str, Rule]  # rule_key → Rule
    strategies: dict[str, Strategy]  # strategy_key → Strategy
    lookups: dict[str, list[LookupEntry]]  # lookup_set → sorted entries
    apps: set[str]  # loaded app_ids
    config_version: str  # deterministic hash


# ── Loader ───────────────────────────────────────────────────────────────

def load_config(
    source: ConfigSource,
    *,
    app_ids: tuple[str, ...] = ("SHARED", "OTA"),
) -> EngineConfig:
    """Load engine_* tables from *source* and resolve into an EngineConfig.

    Parameters
    ----------
    source : ConfigSource
        Injected table reader.
    app_ids : tuple[str, ...]
        Which owner_app_id values to include. Defaults to SHARED + OTA.
    """
    scope = set(app_ids)

    # ── Apps ──────────────────────────────────────────────────────────
    raw_apps = source.fetch_apps()
    loaded_apps = {
        r["app_id"]
        for r in raw_apps
        if r["app_id"] in scope and _is_enabled(r)
    }

    # ── Rules ─────────────────────────────────────────────────────────
    raw_rules = source.fetch_rules()
    rules_by_id: dict[int, Rule] = {}
    rules_by_key: dict[str, Rule] = {}
    rule_key_by_id: dict[int, str] = {}

    for row in raw_rules:
        if row.get("owner_app_id") not in scope:
            continue
        if not _is_enabled(row):
            continue
        rule_id, _owner, rule = _row_to_rule(row)
        rules_by_id[rule_id] = rule
        rules_by_key[rule.rule_key] = rule
        rule_key_by_id[rule_id] = rule.rule_key

    # ── Strategies ────────────────────────────────────────────────────
    raw_strategies = source.fetch_strategies()
    strategies_by_id: dict[int, Strategy] = {}
    strategies_by_key: dict[str, Strategy] = {}
    strategy_key_by_id: dict[int, str] = {}

    for row in raw_strategies:
        if row.get("owner_app_id") not in scope:
            continue
        if not _is_enabled(row):
            continue
        strat_id, _owner, strategy = _row_to_strategy(row)
        strategies_by_id[strat_id] = strategy
        strategies_by_key[strategy.strategy_key] = strategy
        strategy_key_by_id[strat_id] = strategy.strategy_key

    # ── Junction → RuleBindings per strategy ──────────────────────────
    raw_junction = source.fetch_junction()
    bindings_by_strategy: dict[str, list[RuleBinding]] = {
        sk: [] for sk in strategies_by_key
    }

    for row in raw_junction:
        if not _is_enabled(row):
            continue
        strat_id = row["strategy_id"]
        rule_id = row["rule_id"]

        strat_key = strategy_key_by_id.get(strat_id)
        r_key = rule_key_by_id.get(rule_id)

        # Skip junction rows referencing disabled/out-of-scope rules or strategies
        if strat_key is None or r_key is None:
            continue
        if strat_key not in bindings_by_strategy:
            continue

        rule = rules_by_id[rule_id]
        junction = _row_to_junction(row, strat_key, r_key)
        bindings_by_strategy[strat_key].append(RuleBinding(rule=rule, junction=junction))

    # ── Validate expressions + decompose BETWEEN at load ─────────────
    for strat_key, bindings in bindings_by_strategy.items():
        _validate_expressions(bindings)
        bindings_by_strategy[strat_key] = _decompose_between(bindings)

    # ── Resolve RuleSets ──────────────────────────────────────────────
    rule_sets: dict[str, RuleSet] = {}
    for strat_key, bindings in bindings_by_strategy.items():
        sorted_bindings = sorted(bindings, key=_binding_sort_key)
        rule_sets[strat_key] = RuleSet(
            strategy=strategies_by_key[strat_key],
            bindings=tuple(sorted_bindings),
        )

    # ── Lookups ───────────────────────────────────────────────────────
    raw_lookups = source.fetch_lookups()
    lookups: dict[str, list[LookupEntry]] = {}

    for row in raw_lookups:
        if row.get("owner_app_id") not in scope:
            continue
        if not _is_enabled(row):
            continue
        entry = LookupEntry(
            owner_app_id=row["owner_app_id"],
            lookup_set=row["lookup_set"],
            lookup_key=row["lookup_key"],
            payload=_parse_json(row.get("payload")),
            sort_order=row.get("sort_order"),
        )
        lookups.setdefault(entry.lookup_set, []).append(entry)

    # Sort each lookup set by sort_order
    for entries in lookups.values():
        entries.sort(key=lambda e: (e.sort_order if e.sort_order is not None else 999999, e.lookup_key))

    # ── Config version hash ───────────────────────────────────────────
    config_version = _compute_config_version(
        raw_rules, raw_strategies, raw_junction, raw_lookups, scope
    )

    return EngineConfig(
        rule_sets=rule_sets,
        rules=rules_by_key,
        strategies=strategies_by_key,
        lookups=lookups,
        apps=loaded_apps,
        config_version=config_version,
    )


def _validate_expressions(bindings: list[RuleBinding]) -> None:
    """Reject any rule whose expression is not in the closed set (§6.3)."""
    for binding in bindings:
        validate_expression(
            binding.rule.condition_expression,
            binding.rule.formula_ref,
        )


def _decompose_between(bindings: list[RuleBinding]) -> list[RuleBinding]:
    """Replace BETWEEN bindings with two atomic comparison bindings (§6.3).

    A BETWEEN rule with two parameters becomes:
    - rule_key__gte with '>=' and the lower-valued parameter
    - rule_key__lte with '<=' and the higher-valued parameter

    The runtime evaluator never sees BETWEEN.
    """
    result: list[RuleBinding] = []
    for binding in bindings:
        if binding.rule.condition_expression != "BETWEEN":
            result.append(binding)
            continue

        params = binding.junction.parameters
        schema = binding.rule.parameter_schema
        if len(params) < 2:
            raise ValueError(
                f"BETWEEN rule '{binding.rule.rule_key}' requires exactly 2 "
                f"parameters, got {len(params)}: {list(params.keys())}"
            )

        # Sort parameter entries by value to identify low/high
        sorted_params = sorted(params.items(), key=lambda kv: kv[1])
        low_key, low_val = sorted_params[0]
        high_key, high_val = sorted_params[1]

        # Split schema entries
        low_schema = {low_key: schema.get(low_key, {})} if schema else {}
        high_schema = {high_key: schema.get(high_key, {})} if schema else {}

        # Create >= rule (lower bound)
        gte_rule = Rule(
            rule_key=f"{binding.rule.rule_key}__gte",
            phase=binding.rule.phase,
            tier=binding.rule.tier,
            intent=f"{binding.rule.intent} (lower bound)" if binding.rule.intent else None,
            condition_expression=">=",
            formula_ref=None,
            referenced_named_values=binding.rule.referenced_named_values,
            parameter_schema=low_schema,
            null_semantics=binding.rule.null_semantics,
        )
        gte_junction = JunctionRow(
            strategy_key=binding.junction.strategy_key,
            rule_key=gte_rule.rule_key,
            evaluation_order=binding.junction.evaluation_order,
            stop_if_fail=binding.junction.stop_if_fail,
            score_penalty=binding.junction.score_penalty,
            weight=binding.junction.weight,
            parameters={low_key: low_val},
            rationale=binding.junction.rationale,
            enabled=binding.junction.enabled,
            terminal_verdict=binding.junction.terminal_verdict,
        )

        # Create <= rule (upper bound)
        lte_rule = Rule(
            rule_key=f"{binding.rule.rule_key}__lte",
            phase=binding.rule.phase,
            tier=binding.rule.tier,
            intent=f"{binding.rule.intent} (upper bound)" if binding.rule.intent else None,
            condition_expression="<=",
            formula_ref=None,
            referenced_named_values=binding.rule.referenced_named_values,
            parameter_schema=high_schema,
            null_semantics=binding.rule.null_semantics,
        )
        lte_junction = JunctionRow(
            strategy_key=binding.junction.strategy_key,
            rule_key=lte_rule.rule_key,
            evaluation_order=binding.junction.evaluation_order + 1,
            stop_if_fail=binding.junction.stop_if_fail,
            score_penalty=binding.junction.score_penalty,
            weight=binding.junction.weight,
            parameters={high_key: high_val},
            rationale=binding.junction.rationale,
            enabled=binding.junction.enabled,
            terminal_verdict=binding.junction.terminal_verdict,
        )

        result.append(RuleBinding(rule=gte_rule, junction=gte_junction))
        result.append(RuleBinding(rule=lte_rule, junction=lte_junction))

    return result


def _is_enabled(row: RawRow) -> bool:
    """Check the enabled flag; treat missing as True."""
    val = row.get("enabled")
    if val is None:
        return True
    # Handle both bool and int (from DB bit columns)
    return bool(val)


def _compute_config_version(
    rules: list[RawRow],
    strategies: list[RawRow],
    junction: list[RawRow],
    lookups: list[RawRow],
    scope: set[str],
) -> str:
    """Deterministic SHA-256 over the loaded configuration rows."""
    hasher = hashlib.sha256()

    # Sort each table's rows by a stable key before hashing
    def _hash_rows(rows: list[RawRow], sort_keys: list[str]) -> None:
        filtered = [r for r in rows if r.get("owner_app_id") in scope or r.get("app_id") in scope]
        stable = sorted(filtered, key=lambda r: tuple(str(r.get(k, "")) for k in sort_keys))
        for row in stable:
            # Use json.dumps with sort_keys for determinism
            hasher.update(json.dumps(row, sort_keys=True, default=str).encode("utf-8"))

    _hash_rows(rules, ["owner_app_id", "rule_key"])
    _hash_rows(strategies, ["owner_app_id", "strategy_key"])
    _hash_rows(junction, ["strategy_id", "rule_id"])
    _hash_rows(lookups, ["owner_app_id", "lookup_set", "lookup_key"])

    return hasher.hexdigest()[:16]
