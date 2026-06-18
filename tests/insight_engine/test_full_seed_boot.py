"""Live mixed-surface boot check (OTA-836 → OTA-840 → OTA-844).

Hydrates the COMPLETE seed (all surfaces) the way the live
``init_engine_runtime`` does — ``build_all_rows`` → ``load_config`` →
``validate_by_surface`` against the COMBINED screening ∪ directional ∪
position-health registry — and asserts every surface validates.

Why this exists: the per-surface tests (e.g. ``test_directional_null_semantics``)
hydrate one surface in isolation and pass even when the *combined* live boot
would fail. This test reproduces the real, mixed-surface boot so a regression
that only shows up across surfaces (a drifted formula, a non-§6.3 carve-out, an
EVAL_ORDER_DUPLICATE from BETWEEN decomposition) is caught here rather than as a
dead engine runtime in production.

Invariants asserted:
  * the four SCREENING, three DIRECTIONAL, and two POSITION_HEALTH strategies load;
  * the SHARED formula-registry contract and the combined live registry agree on
    exactly 40 formulas (26 screening + 10 directional + 4 position-health);
  * ``validate_by_surface`` returns zero global errors and zero per-surface
    errors (so hydration stamps all three surfaces);
  * surface isolation: a directional-only config fault leaves SCREENING valid.
"""

from __future__ import annotations

import pytest

from app.insight_engine import (
    InMemoryConfigSource,
    load_config,
    validate_by_surface,
)
from app.ota_adapters.engine_runtime import build_combined_registry
from scripts.seed_engine_config import DEFAULT_XLSX, build_all_rows

pytestmark = pytest.mark.skipif(
    not DEFAULT_XLSX.exists(),
    reason=f"seed workbook not available at {DEFAULT_XLSX}",
)

# OTA-841: SCREENING strategy keys are the system-canonical hyphen form (the
# engine seed was the lone underscore outlier). DIRECTIONAL keys stay underscore
# — a separate surface with no canonical hyphen form.
SCREENING_STRATEGIES = {"steady-paycheck", "weekly-grind", "trend-rider", "lottery-ticket"}
DIRECTIONAL_STRATEGIES = {"directional_income", "directional_growth", "directional_longshot"}
# OTA-844: POSITION_HEALTH keys are underscore — a third surface, like DIRECTIONAL,
# with no canonical hyphen form.
POSITION_HEALTH_STRATEGIES = {"position_health_full", "position_health_basic"}
EXPECTED_CONTRACT_COUNT = 40


def _build_rows():
    """Build the full seed row set with synthetic ids (DB IDENTITY stand-ins)."""
    rules, strategies, junctions, lookups, _ = build_all_rows(DEFAULT_XLSX)

    rule_id = {r["rule_key"]: 1000 + i for i, r in enumerate(rules)}
    strat_id = {s["strategy_key"]: 100 + i for i, s in enumerate(strategies)}
    assert len(rule_id) == len(rules), "duplicate rule_key in seed rows"
    assert len(strat_id) == len(strategies), "duplicate strategy_key in seed rows"

    rules = [{**r, "rule_id": rule_id[r["rule_key"]]} for r in rules]
    strategies = [{**s, "strategy_id": strat_id[s["strategy_key"]]} for s in strategies]
    junctions = [
        {**j, "rule_id": rule_id[j["rule_key"]], "strategy_id": strat_id[j["strategy_key"]]}
        for j in junctions
    ]
    return rules, strategies, junctions, lookups


def _source_from(rules, strategies, junctions, lookups):
    apps = [
        {"app_id": "SHARED", "name": "Shared", "enabled": True},
        {"app_id": "OTA", "name": "OTA", "enabled": True},
    ]
    return InMemoryConfigSource(
        apps=apps, rules=rules, strategies=strategies, junction=junctions, lookups=lookups
    )


def _hydrate():
    """Build the full seed and hydrate it via InMemoryConfigSource."""
    rules, strategies, junctions, lookups = _build_rows()
    source = _source_from(rules, strategies, junctions, lookups)
    return source, load_config(source)


def test_full_seed_validates_clean():
    """The live mixed-surface boot validates with zero errors on every surface."""
    source, config = _hydrate()
    result = validate_by_surface(
        config, formula_registry=build_combined_registry(), source=source
    )
    assert result.global_valid, result.global_report.summary()
    assert not result.invalid_surfaces(), {
        s: r.summary() for s, r in result.per_surface.items() if not r.is_valid
    }
    assert {"SCREENING", "DIRECTIONAL", "POSITION_HEALTH"} <= set(result.per_surface)


def test_all_surfaces_load():
    """SCREENING, DIRECTIONAL, and POSITION_HEALTH strategies all load (OTA-844)."""
    _source, config = _hydrate()
    loaded = set(config.rule_sets)
    assert SCREENING_STRATEGIES <= loaded
    assert DIRECTIONAL_STRATEGIES <= loaded
    assert POSITION_HEALTH_STRATEGIES <= loaded


def test_contract_and_registry_agree_on_40():
    """SHARED formula contract == combined live registry == 40 formulas (OTA-844)."""
    _source, config = _hydrate()
    contract = {
        e.lookup_key
        for e in config.lookups.get("formula_registry", [])
        if e.owner_app_id == "SHARED"
    }
    live = set(build_combined_registry().registered_names())
    assert contract == live, f"drift: contract-only={contract - live}, live-only={live - contract}"
    assert len(contract) == EXPECTED_CONTRACT_COUNT


def test_directional_fault_isolates_screening():
    """A directional-only config fault degrades DIRECTIONAL; SCREENING stays valid."""
    rules, strategies, junctions, lookups = _build_rows()
    # Inject a directional-only fault: make one directional strategy's verdict
    # bands non-monotonic (a per-surface check, not a global invariant).
    for s in strategies:
        if s["strategy_key"] == "directional_income":
            s["verdict_band_set"] = [
                {"verdict": "PASS", "min_score": 0, "max_score": 54.99},
                {"verdict": "EXECUTE", "min_score": 75, "max_score": 100},
            ]
    source = _source_from(rules, strategies, junctions, lookups)
    config = load_config(source)

    result = validate_by_surface(
        config, formula_registry=build_combined_registry(), source=source
    )
    # Global invariants unaffected; SCREENING valid; DIRECTIONAL degraded.
    assert result.global_valid, result.global_report.summary()
    assert "SCREENING" in result.valid_surfaces()
    assert "DIRECTIONAL" in result.invalid_surfaces()
