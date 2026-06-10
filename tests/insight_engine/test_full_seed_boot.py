"""Live mixed-surface boot check (OTA-836).

Hydrates the COMPLETE seed (all surfaces) the way the live
``init_engine_runtime`` does — ``build_all_rows`` → ``load_config`` →
``validate_config`` against the live SCREENING formula registry — and asserts
the config validates with zero errors.

Why this exists: the per-surface tests (e.g. ``test_directional_null_semantics``)
hydrate one surface in isolation and pass even when the *combined* live boot
would fail. This test reproduces the real, mixed-surface boot so a regression
that only shows up across surfaces (a drifted formula, a non-§6.3 carve-out, an
EVAL_ORDER_DUPLICATE from BETWEEN decomposition) is caught here rather than as a
null engine runtime in production.

OTA-836 Phase A invariants asserted:
  * the four SCREENING strategies load; the three DIRECTIONAL strategies are
    parked (enabled=0) and therefore NOT loaded;
  * the SHARED formula-registry contract and the live screening registry agree
    on exactly 26 formulas;
  * validate_config returns zero errors (so the OTA-830 safety net would not
    fire and the runtime would hydrate).
"""

from __future__ import annotations

import pytest

from app.insight_engine import InMemoryConfigSource, load_config, validate_config
from app.options_rules.screening import get_registry
from scripts.seed_engine_config import DEFAULT_XLSX, build_all_rows

pytestmark = pytest.mark.skipif(
    not DEFAULT_XLSX.exists(),
    reason=f"seed workbook not available at {DEFAULT_XLSX}",
)

SCREENING_STRATEGIES = {"steady_paycheck", "weekly_grind", "trend_rider", "lottery_ticket"}
DIRECTIONAL_STRATEGIES = {"directional_income", "directional_growth", "directional_longshot"}
EXPECTED_CONTRACT_COUNT = 26


def _hydrate():
    """Build the full seed row set and hydrate it via InMemoryConfigSource.

    Mirrors the live load: synthetic ids stand in for the DB IDENTITY columns
    the upsert assigns, exactly as the DIRECTIONAL hydration test does.
    """
    rules, strategies, junctions, lookups = build_all_rows(DEFAULT_XLSX)

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
    apps = [
        {"app_id": "SHARED", "name": "Shared", "enabled": True},
        {"app_id": "OTA", "name": "OTA", "enabled": True},
    ]
    source = InMemoryConfigSource(
        apps=apps, rules=rules, strategies=strategies, junction=junctions, lookups=lookups
    )
    return source, load_config(source)


def test_full_seed_validates_clean():
    """The live mixed-surface boot validates with zero errors."""
    source, config = _hydrate()
    report = validate_config(config, formula_registry=get_registry(), source=source)
    assert report.is_valid, report.summary()


def test_screening_loads_directional_parked():
    """SCREENING strategies load; DIRECTIONAL strategies are parked (not loaded)."""
    _source, config = _hydrate()
    loaded = set(config.rule_sets)
    assert SCREENING_STRATEGIES <= loaded
    assert not (DIRECTIONAL_STRATEGIES & loaded)


def test_contract_and_registry_agree_on_26():
    """SHARED formula contract == live screening registry == 26 formulas."""
    _source, config = _hydrate()
    contract = {
        e.lookup_key
        for e in config.lookups.get("formula_registry", [])
        if e.owner_app_id == "SHARED"
    }
    live = set(get_registry().registered_names())
    assert contract == live, f"drift: contract-only={contract - live}, live-only={live - contract}"
    assert len(contract) == EXPECTED_CONTRACT_COUNT
