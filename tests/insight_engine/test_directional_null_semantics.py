"""
OTA-833 — DIRECTIONAL seed hydration + OTA-838 SKIP null-semantics regression.

Two concerns, both standing regression coverage:

1. **Null-semantics at gate eval (OTA-838, exercised for the directional spread
   gate).** ``dir_bid_ask_spread_max`` is a ``stop_if_fail`` comparison gate whose
   LHS ``bid_ask_spread_pct`` is null-by-design for debit spreads (catalog
   null_semantics=SKIP). With the SKIP map supplied to ``run_pipeline`` the gate
   is *skipped* (no halt, no penalty), not failed. Without the map it fails
   closed and halts — proving the seed's reliance on OTA-838 is real. Covers
   SKIP×null, FAIL_OPEN×null, FAIL_CLOSED×null, and the non-null pass/fail paths.
   Live end-to-end (the consumer building the map from the adapter catalog) is
   OTA-765; this is the engine-level demonstration.

2. **Seed hydration.** The three DIRECTIONAL objectives seeded by
   ``build_directional_config`` load cleanly: each scoring-weight vector sums to
   1.00, every ``formula_ref`` resolves, the atomic gate set is the expected 9,
   and ``validate_config`` reports no errors. ``dir_budget_fit`` /
   ``dir_defined_risk`` remain bound by no strategy.
"""

from __future__ import annotations

import pytest

from app.insight_engine import InMemoryConfigSource, load_config, validate_config
from app.insight_engine.models import (
    Candidate,
    JunctionRow,
    Phase,
    Rule,
    RuleBinding,
    RuleSet,
    Strategy,
    Tier,
    VerdictSource,
)
from app.insight_engine.pipeline import run_pipeline
from app.insight_engine.registry import StubFormulaRegistry
from app.options_rules.directional import get_registry
from scripts.seed_engine_config import (
    _DIR_SCORING_WEIGHTS,
    build_directional_config,
)

DIR_REGISTRY = get_registry()
STRATEGY_KEYS = ("directional_income", "directional_growth", "directional_longshot")


# ── Part 1: OTA-838 SKIP null-semantics on the directional spread gate ──────
#
# A minimal one-gate RuleSet isolates the spread gate so the behavior is not
# entangled with the other eight directional gates. The gate mirrors exactly the
# seeded dir_bid_ask_spread_max rule: '<=' over bid_ask_spread_pct, stop_if_fail,
# catalog null_semantics=SKIP.


def _spread_gate_rule_set() -> RuleSet:
    rule = Rule(
        rule_key="dir_bid_ask_spread_max",
        phase=Phase.GATE,
        tier=Tier.DERIVED,
        intent="Liquidity: bid/ask spread ceiling (SKIP-null for spreads).",
        condition_expression="<=",
        formula_ref=None,
        referenced_named_values=("bid_ask_spread_pct",),
        parameter_schema={"max_spread_pct": {"type": "number"}},
        null_semantics="SKIP",
    )
    junction = JunctionRow(
        strategy_key="directional_income",
        rule_key="dir_bid_ask_spread_max",
        evaluation_order=5,
        stop_if_fail=True,
        score_penalty=None,
        weight=None,
        parameters={"max_spread_pct": 10.0},
        rationale=None,
        enabled=True,
        terminal_verdict=None,
    )
    strategy = Strategy(
        strategy_key="directional_income",
        display_name="Directional — Income",
        consumer_surface="DIRECTIONAL",
        description=None,
        compatible_structures=("bull_call", "bear_put", "long_call", "long_put"),
        verdict_band_set=[
            {"verdict": "EXECUTE", "min_score": 75, "max_score": 100},
            {"verdict": "WAIT", "min_score": 55, "max_score": 74.99},
            {"verdict": "PASS", "min_score": 0, "max_score": 54.99},
        ],
        dte_min=None,
        dte_max=None,
    )
    return RuleSet(strategy=strategy, bindings=(RuleBinding(rule=rule, junction=junction),))


def _candidate(spread_pct):
    """A debit-spread-shaped candidate; bid_ask_spread_pct is None for spreads."""
    return Candidate(
        candidate_id="dir-skip-test",
        candidate_type="directional",
        symbol="TEST",
        subject_type="THESIS_COMPARISON",
        named_values={
            "bid_ask_spread_pct": spread_pct,
            "structure_type": "vertical_spread",
        },
    )


_REG = StubFormulaRegistry()  # the spread gate is a generic predicate — no formulas


def test_skip_null_semantics_does_not_halt_spread_gate():
    """SKIP × null: null LHS + SKIP map → rule skipped, candidate survives."""
    rule_set = _spread_gate_rule_set()
    result = run_pipeline(
        _candidate(None), rule_set, _REG,
        null_semantics={"bid_ask_spread_pct": "SKIP"},
    )
    assert result.terminal_phase == "verdict"  # not halted
    decision = result.gate_decisions[0]
    assert decision.skipped is True
    assert decision.passed is True  # skipped sets passed=True (not a genuine pass)
    assert decision.held_penalty is None
    assert result.final_score is not None
    assert result.verdict == "PASS"  # score 0 lands in the PASS band


def test_no_map_null_semantics_halts_spread_gate():
    """FAIL_CLOSED (de-facto) × null: no map → comparison fails → stop halts."""
    rule_set = _spread_gate_rule_set()
    result = run_pipeline(_candidate(None), rule_set, _REG, null_semantics=None)
    assert result.terminal_phase == "gate"  # halted
    decision = result.gate_decisions[0]
    assert decision.skipped is False
    assert decision.passed is False
    assert result.final_score is None
    assert result.verdict_source == VerdictSource.HALT_NO_VERDICT


def test_explicit_fail_closed_null_semantics_halts_spread_gate():
    """FAIL_CLOSED × null: explicit FAIL_CLOSED behaves like no map (halt)."""
    rule_set = _spread_gate_rule_set()
    result = run_pipeline(
        _candidate(None), rule_set, _REG,
        null_semantics={"bid_ask_spread_pct": "FAIL_CLOSED"},
    )
    assert result.terminal_phase == "gate"
    assert result.gate_decisions[0].skipped is False
    assert result.gate_decisions[0].passed is False


def test_fail_open_null_semantics_passes_spread_gate():
    """FAIL_OPEN × null: null LHS + FAIL_OPEN map → treated as pass, not skip."""
    rule_set = _spread_gate_rule_set()
    result = run_pipeline(
        _candidate(None), rule_set, _REG,
        null_semantics={"bid_ask_spread_pct": "FAIL_OPEN"},
    )
    assert result.terminal_phase == "verdict"  # not halted
    decision = result.gate_decisions[0]
    assert decision.skipped is False  # fail-open is a pass, not a skip
    assert decision.passed is True


def test_non_null_within_ceiling_passes():
    """Non-null pass: 5.0 <= 10.0 → passes; SKIP map is not consulted."""
    rule_set = _spread_gate_rule_set()
    result = run_pipeline(
        _candidate(5.0), rule_set, _REG,
        null_semantics={"bid_ask_spread_pct": "SKIP"},
    )
    assert result.terminal_phase == "verdict"
    decision = result.gate_decisions[0]
    assert decision.skipped is False
    assert decision.passed is True


def test_non_null_exceeds_ceiling_halts():
    """Non-null fail: 15.0 <= 10.0 is False → stop_if_fail halts even with SKIP map."""
    rule_set = _spread_gate_rule_set()
    result = run_pipeline(
        _candidate(15.0), rule_set, _REG,
        null_semantics={"bid_ask_spread_pct": "SKIP"},
    )
    assert result.terminal_phase == "gate"
    decision = result.gate_decisions[0]
    assert decision.skipped is False
    assert decision.passed is False


# ── Part 2: DIRECTIONAL seed hydration ──────────────────────────────────────


def _load_directional_config():
    """Hydrate the seeded DIRECTIONAL block via InMemoryConfigSource.

    Assigns synthetic ids (the DB does this at upsert) and supplies a
    formula_registry contract lookup mirroring the live directional registry so
    validate_config's contract/drift checks are exercised cleanly.
    """
    rules, strategies, junctions, lookups = build_directional_config()
    rule_id = {r["rule_key"]: 1000 + i for i, r in enumerate(rules)}
    strat_id = {s["strategy_key"]: 100 + i for i, s in enumerate(strategies)}
    rules = [{**r, "rule_id": rule_id[r["rule_key"]]} for r in rules]
    strategies = [{**s, "strategy_id": strat_id[s["strategy_key"]]} for s in strategies]
    junctions = [
        {**j, "rule_id": rule_id[j["rule_key"]], "strategy_id": strat_id[j["strategy_key"]]}
        for j in junctions
    ]
    contract = [
        {
            "owner_app_id": "SHARED",
            "lookup_set": "formula_registry",
            "lookup_key": name,
            "payload": {"status": "pending"},
            "sort_order": i,
        }
        for i, name in enumerate(sorted(DIR_REGISTRY.registered_names()), 1)
    ]
    apps = [
        {"app_id": "SHARED", "name": "Shared", "enabled": True},
        {"app_id": "OTA", "name": "OTA", "enabled": True},
    ]
    source = InMemoryConfigSource(
        apps=apps,
        rules=rules,
        strategies=strategies,
        junction=junctions,
        lookups=lookups + contract,
    )
    return load_config(source)


DIR_CONFIG = _load_directional_config()


def test_all_three_objectives_hydrate():
    for key in STRATEGY_KEYS:
        assert key in DIR_CONFIG.rule_sets


@pytest.mark.parametrize("strategy_key", STRATEGY_KEYS)
def test_scoring_weights_sum_to_one(strategy_key):
    rule_set = DIR_CONFIG.rule_sets[strategy_key]
    scoring = [b for b in rule_set.bindings if b.rule.phase == Phase.SCORING]
    assert len(scoring) == 6
    total = sum(b.junction.weight or 0.0 for b in scoring)
    assert total == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("strategy_key", STRATEGY_KEYS)
def test_atomic_gate_set_is_nine(strategy_key):
    """3 data-completeness + earnings + 3 liquidity + budget + negative-EV = 9."""
    rule_set = DIR_CONFIG.rule_sets[strategy_key]
    gates = [b for b in rule_set.bindings if b.rule.phase == Phase.GATE]
    assert len(gates) == 9
    keys = {b.rule.rule_key for b in gates}
    assert keys == {
        "dir_data_completeness_underlying_price",
        "dir_data_completeness_expiration",
        "dir_data_completeness_structure_type",
        "dir_earnings",
        "dir_bid_ask_spread_max",
        "dir_open_interest_floor",
        "dir_volume_floor",
        "dir_budget_flag",
        "dir_negative_ev",
    }


@pytest.mark.parametrize("strategy_key", STRATEGY_KEYS)
def test_data_completeness_gates_are_fail_closed_stops(strategy_key):
    rule_set = DIR_CONFIG.rule_sets[strategy_key]
    for b in rule_set.bindings:
        if b.rule.rule_key.startswith("dir_data_completeness_"):
            assert b.rule.condition_expression == "IS NOT NULL"
            assert b.rule.null_semantics == "FAIL_CLOSED"
            assert b.junction.stop_if_fail is True
            assert b.junction.evaluation_order in (1, 2, 3)


def test_earnings_hard_stop_income_record_only_others():
    """Income halts on earnings; Growth/Longshot record-only (junction-driven)."""
    income = _gate(DIR_CONFIG, "directional_income", "dir_earnings")
    assert income.junction.stop_if_fail is True
    for key in ("directional_growth", "directional_longshot"):
        g = _gate(DIR_CONFIG, key, "dir_earnings")
        assert g.junction.stop_if_fail is False
        assert g.junction.score_penalty == 0.0


def test_budget_flag_never_rejects():
    for key in STRATEGY_KEYS:
        g = _gate(DIR_CONFIG, key, "dir_budget_flag")
        assert g.junction.stop_if_fail is False
        assert g.junction.score_penalty == 0.0


def test_formula_ref_gates_carry_no_condition_expression():
    """dir_earnings / dir_negative_ev are formula-backed (no condition_expression)."""
    for key in STRATEGY_KEYS:
        for rk in ("dir_earnings", "dir_negative_ev"):
            g = _gate(DIR_CONFIG, key, rk)
            assert g.rule.condition_expression is None
            assert g.rule.formula_ref == f"formula:{rk}"


def test_negative_ev_is_computed_tier_and_stops():
    for key in STRATEGY_KEYS:
        g = _gate(DIR_CONFIG, key, "dir_negative_ev")
        assert g.rule.tier == Tier.COMPUTED
        assert g.junction.stop_if_fail is True


def test_all_formula_refs_resolve_in_live_registry():
    for rule_set in DIR_CONFIG.rule_sets.values():
        for b in rule_set.bindings:
            ref = b.rule.formula_ref
            if ref and ref.startswith("formula:"):
                name = ref[len("formula:"):]
                assert DIR_REGISTRY.has(name), f"unresolved formula '{name}'"


def test_unbound_formulas_not_referenced():
    """dir_budget_fit / dir_defined_risk are registered but bound by no strategy."""
    bound = {
        b.rule.formula_ref
        for rule_set in DIR_CONFIG.rule_sets.values()
        for b in rule_set.bindings
        if b.rule.formula_ref
    }
    assert "formula:dir_budget_fit" not in bound
    assert "formula:dir_defined_risk" not in bound


@pytest.mark.parametrize(
    "strategy_key,execute_min",
    [("directional_income", 75), ("directional_growth", 70), ("directional_longshot", 62)],
)
def test_verdict_bands_per_strategy(strategy_key, execute_min):
    bands = DIR_CONFIG.rule_sets[strategy_key].strategy.verdict_band_set
    assert [b["verdict"] for b in bands] == ["EXECUTE", "WAIT", "PASS"]
    assert bands[0]["min_score"] == execute_min
    # Monotonically descending min_score, full [0,100] coverage.
    mins = [b["min_score"] for b in bands]
    assert mins == sorted(mins, reverse=True)
    assert bands[-1]["min_score"] == 0
    assert bands[0]["max_score"] == 100


def test_validate_config_reports_no_errors():
    """Full §6.6 startup validation against the live directional registry."""
    report = validate_config(DIR_CONFIG, formula_registry=DIR_REGISTRY)
    assert report.is_valid, report.summary()


def test_scoring_weight_table_matches_seed_constant():
    """The hydrated weights match the declared per-objective vectors."""
    for key in STRATEGY_KEYS:
        rule_set = DIR_CONFIG.rule_sets[key]
        hydrated = {
            b.rule.rule_key: b.junction.weight
            for b in rule_set.bindings
            if b.rule.phase == Phase.SCORING
        }
        assert hydrated == pytest.approx(_DIR_SCORING_WEIGHTS[key])


# ── helpers ─────────────────────────────────────────────────────────────────


def _gate(config, strategy_key, rule_key) -> RuleBinding:
    for b in config.rule_sets[strategy_key].bindings:
        if b.rule.rule_key == rule_key:
            return b
    raise AssertionError(f"{rule_key} not bound to {strategy_key}")
