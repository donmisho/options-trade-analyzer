"""OTA-838 — gate eval honors the LHS named value's catalog null_semantics.

When a gate's LHS named value resolves to null, the engine consults that value's
catalog null semantics (supplied as a {named_value: semantics} map):

    SKIP        → skip the rule (third outcome: no pass/fail, no halt, no penalty)
    FAIL_OPEN   → treat the null as a pass
    FAIL_CLOSED → fail (de-facto behavior; halts if stop_if_fail) — unchanged
    (no map / unknown) → unchanged fail-closed

Scope: expression-based comparison/set/enum gates only. Explicit IS NULL /
IS NOT NULL operators and formula:<name> gates keep their own null handling.

Parity: the seven enumerated screening gates (OTA-838 Phase-0), exercised with a
null LHS using the REAL options_chain catalog semantics, are all confirmed
INTENDED CORRECTIONS — none halts a candidate on its declared-nullable LHS.

OTA-838
"""

from __future__ import annotations

import pytest

from app.api.engine_config_preview import _null_semantics_from_adapter
from app.insight_engine.config_source import InMemoryConfigSource
from app.insight_engine.loader import load_config
from app.insight_engine.models import Candidate
from app.insight_engine.pipeline import run_pipeline
from app.insight_engine.registry import DictFormulaRegistry
from app.ota_adapters.options_chain.adapter import OptionsChainAdapter


# ── Fixtures ─────────────────────────────────────────────────────────────


_VERDICT_BANDS = [
    {"verdict": "EXECUTE", "min_score": 70, "max_score": 100},
    {"verdict": "WAIT", "min_score": 50, "max_score": 69.99},
    {"verdict": "PASS", "min_score": 0, "max_score": 49.99},
]


def _apps():
    return [
        {"app_id": "SHARED", "name": "Shared", "status": "active", "enabled": True},
        {"app_id": "OTA", "name": "OTA", "status": "active", "enabled": True},
    ]


def _strategy():
    return [{
        "strategy_id": 1, "owner_app_id": "OTA", "strategy_key": "test_strat",
        "display_name": "Test Strategy", "consumer_surface": "SCREENING",
        "description": None, "compatible_structures": None,
        "verdict_band_set": _VERDICT_BANDS, "enabled": True,
    }]


def _gate_rule(rule_key, expr, lhs, *, formula_ref=None):
    return {
        "rule_id": 1, "owner_app_id": "OTA", "rule_key": rule_key,
        "phase": "gate", "tier": "RAW", "intent": None,
        "condition_expression": expr, "formula_ref": formula_ref,
        "referenced_named_values": [lhs],
        "parameter_schema": {}, "null_semantics": None, "enabled": True,
    }


def _scoring_rule():
    # A constant scoring criterion (weight 1.0) so a non-halted candidate reaches
    # a verdict — lets us assert the candidate survived the gate.
    return {
        "rule_id": 2, "owner_app_id": "OTA", "rule_key": "const_score",
        "phase": "scoring", "tier": None, "intent": None,
        "condition_expression": None, "formula_ref": "formula:const80",
        "referenced_named_values": [], "parameter_schema": {},
        "null_semantics": None, "enabled": True,
    }


def _junctions(*, gate_stop=True, gate_penalty=None, gate_params=None):
    return [
        {
            "junction_id": 1, "strategy_id": 1, "rule_id": 1,
            "evaluation_order": 1, "stop_if_fail": gate_stop,
            "score_penalty": gate_penalty, "weight": None,
            "parameters": gate_params or {"threshold": 0.30},
            "terminal_verdict": None, "rationale": None, "enabled": True,
        },
        {
            "junction_id": 2, "strategy_id": 1, "rule_id": 2,
            "evaluation_order": 1, "stop_if_fail": False,
            "score_penalty": None, "weight": 1.0, "parameters": {},
            "terminal_verdict": None, "rationale": None, "enabled": True,
        },
    ]


def _config(gate_rule, *, gate_stop=True, gate_penalty=None, gate_params=None):
    source = InMemoryConfigSource(
        apps=_apps(),
        rules=[gate_rule, _scoring_rule()],
        strategies=_strategy(),
        junction=_junctions(
            gate_stop=gate_stop, gate_penalty=gate_penalty, gate_params=gate_params
        ),
        lookups=[],
    )
    return load_config(source)


_REGISTRY = DictFormulaRegistry({"const80": lambda nv, p: 80.0})


def _run(config, named_values, null_semantics):
    cand = Candidate(candidate_id="c1", candidate_type="test", named_values=named_values)
    return run_pipeline(cand, config.rule_sets["test_strat"], _REGISTRY,
                        adapter=None, null_semantics=null_semantics)


def _gate(result):
    return result.gate_decisions[0]


# ── The four unit cases (representative operator: <=) ─────────────────────


class TestFourUnitCases:
    def test_skip_x_null_skips_rule(self):
        cfg = _config(_gate_rule("g", "<=", "x"))
        res = _run(cfg, {}, {"x": "SKIP"})  # x absent → null
        g = _gate(res)
        assert g.skipped is True
        assert g.passed is True            # passed=True but NOT a genuine pass
        assert g.was_terminal is False
        assert g.held_penalty is None
        # No halt: candidate flowed through to a verdict.
        assert res.terminal_phase == "verdict"
        assert res.final_score == 80.0
        assert res.verdict == "EXECUTE"

    def test_fail_open_x_null_passes(self):
        cfg = _config(_gate_rule("g", "<=", "x"))
        res = _run(cfg, {}, {"x": "FAIL_OPEN"})
        g = _gate(res)
        assert g.skipped is False
        assert g.passed is True
        assert g.was_terminal is False
        assert res.terminal_phase == "verdict"
        assert res.verdict == "EXECUTE"

    def test_fail_closed_x_null_fails_and_halts(self):
        cfg = _config(_gate_rule("g", "<=", "x"))   # stop_if_fail=True
        res = _run(cfg, {}, {"x": "FAIL_CLOSED"})
        g = _gate(res)
        assert g.skipped is False
        assert g.passed is False
        assert g.was_terminal is True
        assert res.terminal_phase == "gate"
        assert res.final_score is None

    def test_non_null_unchanged(self):
        cfg = _config(_gate_rule("g", "<=", "x"), gate_params={"threshold": 5.0})
        # Non-null LHS that satisfies <= 5.0 → genuine pass, semantics irrelevant.
        res = _run(cfg, {"x": 3.0}, {"x": "SKIP"})
        g = _gate(res)
        assert g.skipped is False
        assert g.passed is True
        assert res.verdict == "EXECUTE"
        # Non-null LHS that violates → genuine fail/halt, not skipped.
        res2 = _run(cfg, {"x": 9.0}, {"x": "SKIP"})
        g2 = _gate(res2)
        assert g2.skipped is False
        assert g2.passed is False
        assert g2.was_terminal is True


# ── No map / unknown semantics → unchanged fail-closed ───────────────────


class TestDefaultUnchanged:
    def test_no_map_fails_closed(self):
        cfg = _config(_gate_rule("g", "<=", "x"))
        res = _run(cfg, {}, None)
        assert _gate(res).passed is False
        assert _gate(res).was_terminal is True

    def test_unknown_semantics_fails_closed(self):
        cfg = _config(_gate_rule("g", "<=", "x"))
        res = _run(cfg, {}, {"x": "WHATEVER"})
        assert _gate(res).skipped is False
        assert _gate(res).passed is False


# ── Scoping guards: explicit null ops + formula gates NOT overridden ──────


class TestScopingExclusions:
    def test_is_not_null_not_overridden_by_skip(self):
        # Data-completeness gate: null LHS must still FAIL even with SKIP semantics.
        cfg = _config(_gate_rule("g", "IS NOT NULL", "x"))
        res = _run(cfg, {}, {"x": "SKIP"})
        g = _gate(res)
        assert g.skipped is False
        assert g.passed is False
        assert g.was_terminal is True

    def test_is_null_not_overridden(self):
        # IS NULL on a null LHS is a genuine pass — not a skip.
        cfg = _config(_gate_rule("g", "IS NULL", "x"))
        res = _run(cfg, {}, {"x": "SKIP"})
        g = _gate(res)
        assert g.skipped is False
        assert g.passed is True
        assert res.verdict == "EXECUTE"

    def test_formula_gate_not_skipped(self):
        # formula:<name> governs evaluation; the catalog-null override must not
        # apply. A formula returning False on null → genuine fail, not skip.
        rule = _gate_rule("g", None, "x", formula_ref="formula:needs_x")
        cfg = _config(rule)
        reg = DictFormulaRegistry({
            "needs_x": lambda nv, p: nv.get("x") is not None,
            "const80": lambda nv, p: 80.0,
        })
        cand = Candidate(candidate_id="c1", candidate_type="test", named_values={})
        res = run_pipeline(cand, cfg.rule_sets["test_strat"], reg,
                           adapter=None, null_semantics={"x": "SKIP"})
        g = res.gate_decisions[0]
        assert g.skipped is False
        assert g.passed is False
        assert g.was_terminal is True


# ── Parity: the seven enumerated gates, real options_chain semantics ─────


# (gate_key, expr, lhs_named_value, expected_catalog_semantics)
# The final row exercises an IN gate over the SKIP-nullable chart_state LHS for
# null-semantics parity only — this is a synthetic in-memory gate, not the
# seeded config. OTA-839 retired the real chart_state_valid_alignment rule (its
# IN-list literals were outside the adapter domain), so the label here is a
# generic synthetic name; the engine-level null-LHS-never-halts coverage stands.
_SEVEN_GATES = [
    ("credit_pct_of_width_floor",   ">=", "credit_width_pct",       "SKIP"),
    ("debit_pct_of_width_ceiling",  "<=", "debit_width_pct",        "SKIP"),
    ("per_leg_bid_ask_spread",      "<=", "bid_ask_spread",         "SKIP"),
    ("per_leg_open_interest_floor", ">=", "min_leg_open_interest",  "FAIL_OPEN"),
    ("per_leg_volume_floor",        ">=", "min_leg_volume",         "FAIL_OPEN"),
    ("total_expected_value",        ">=", "total_ev",               "SKIP"),
    ("chart_state_in_gate",         "IN", "chart_state",            "SKIP"),
]


@pytest.fixture(scope="module")
def opt_null_semantics():
    """The real options_chain catalog flattened via the production helper."""
    return _null_semantics_from_adapter(OptionsChainAdapter())


class TestSevenGateParity:
    @pytest.mark.parametrize("gate_key,expr,lhs,expected", _SEVEN_GATES)
    def test_declared_catalog_semantics(self, opt_null_semantics, gate_key, expr, lhs, expected):
        # The LHS named value carries exactly the declared semantics asserted in
        # Phase 0 — the intent basis for every "intended correction".
        assert opt_null_semantics.get(lhs) == expected

    @pytest.mark.parametrize("gate_key,expr,lhs,expected", _SEVEN_GATES)
    def test_null_lhs_never_halts(self, opt_null_semantics, gate_key, expr, lhs, expected):
        params = {"allowed_values": ["Bullish", "Bearish"]} if expr == "IN" else {"threshold": 0.30}
        cfg = _config(_gate_rule(gate_key, expr, lhs), gate_params=params)
        res = _run(cfg, {}, opt_null_semantics)  # lhs absent → null
        g = _gate(res)
        # stop_if_fail=True, yet the candidate is NOT halted on its declared-
        # nullable LHS — the intended correction.
        assert g.was_terminal is False
        assert res.terminal_phase == "verdict"
        assert res.held_penalties_applied in (None, 0.0)
        if expected == "SKIP":
            assert g.skipped is True
            assert g.passed is True
        elif expected == "FAIL_OPEN":
            assert g.skipped is False
            assert g.passed is True
