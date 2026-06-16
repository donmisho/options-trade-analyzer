"""
OTA-759 — structural unit tests for the engine-backed scan wiring.

No DB, no live engine config: ``evaluate`` is monkeypatched so the tests exercise
the route-layer ORCHESTRATION in app/api/analysis_routes.py — per-candidate
strategy routing, the per-strategy subset + best-by-(verdict tier, score) pick,
the fail-closed guard, the row builders, and the ScoringBreakdown → component
rebuild. The full engine pipeline is covered elsewhere (tests/insight_engine).
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.insight_engine.models import (
    Candidate,
    ResultRecord,
    ScoringBreakdown,
    VerdictSource,
)
from app.api import analysis_routes as ar


# ── builders ─────────────────────────────────────────────────────────────────


def _record(cid, strategy_key, verdict, final_score, breakdown=None):
    return ResultRecord(
        candidate_id=cid,
        candidate_type="options_trade",
        source_app_id="OTA",
        strategy_key=strategy_key,
        terminal_phase="verdict",
        gate_decisions=[],
        scoring_breakdown=breakdown or [],
        raw_score=final_score,
        held_penalties_applied=None,
        adjustment_results=[],
        final_score=final_score,
        verdict=verdict,
        verdict_source=VerdictSource.BAND_LOOKUP,
        engine_version="test",
        config_version="test",
        run_timestamp=datetime(2026, 6, 16, tzinfo=timezone.utc),
    )


def _cand(cid, **named_values):
    return Candidate(
        candidate_id=cid,
        candidate_type="options_trade",
        named_values=named_values,
        symbol="AMZN",
        subject_type="TRADE_CANDIDATE",
    )


class _StubAdapter:
    def input_catalog(self):
        return []

    def populate_computed(self, *a, **k):
        return None


def _runtime(rule_set_keys):
    return SimpleNamespace(
        config=SimpleNamespace(rule_sets={k: object() for k in rule_set_keys}),
        sink=object(),
        config_version="cfgv1",
    )


# ── per-candidate routing off compatible_structures ──────────────────────────


@pytest.mark.parametrize(
    "structure, expected",
    [
        ("bull_call", ["trend-rider"]),
        ("bear_put", ["trend-rider"]),
        ("bull_put", ["steady-paycheck", "weekly-grind"]),
        ("bear_call", ["steady-paycheck", "weekly-grind"]),
        ("long_call", ["lottery-ticket"]),
        ("long_put", ["lottery-ticket"]),
        ("iron_condor", []),   # unknown structure → no strategies
        (None, []),
    ],
)
def test_compatible_screening_strategies(structure, expected):
    c = _cand("c1", spread_type=structure)
    assert sorted(ar._compatible_screening_strategies(c)) == sorted(expected)


# ── verdict-tier ranking (tier first, then score) ────────────────────────────


def test_screening_rank_tier_beats_score():
    # EXECUTE with a low score outranks WAIT with a high score.
    assert ar._screening_rank("EXECUTE", 51.0) > ar._screening_rank("WAIT", 99.0)
    # None/halted score sorts to the floor.
    assert ar._screening_rank("PASS", None) < ar._screening_rank("PASS", 0.0)
    # WAIT_FOR_EARNINGS sits with WAIT.
    assert ar._screening_rank("WAIT_FOR_EARNINGS", 40.0)[0] == ar._screening_rank("WAIT", 40.0)[0]


# ── ScoringBreakdown → component rebuild (C-3) ───────────────────────────────


def test_score_components_from_record():
    rec = _record(
        "c1", "trend-rider", "EXECUTE", 82.0,
        breakdown=[
            ScoringBreakdown(rule_key="sma_alignment_score", raw_value=100.0, weight=0.30, weighted_contribution=30.0),
            ScoringBreakdown(rule_key="delta_quality", raw_value=64.0, weight=0.25, weighted_contribution=16.0),
        ],
    )
    comps = ar._score_components_from_record(rec)
    assert comps == [
        {"key": "sma_alignment_score", "label": "Sma Alignment Score", "score": 100, "weight": 0.30, "contribution": 30.0},
        {"key": "delta_quality", "label": "Delta Quality", "score": 64, "weight": 0.25, "contribution": 16.0},
    ]


def test_score_components_halted_is_empty():
    rec = _record("c1", "steady-paycheck", "PASS", None, breakdown=[])
    assert ar._score_components_from_record(rec) == []


# ── row builders: engine-owned score/verdict, display from named_values ──────


def test_vertical_engine_row_engine_owned():
    c = _cand(
        "v1", underlying_price=200.0, spread_type="bull_call", option_type="call",
        expiration="2026-07-17", long_strike=200.0, short_strike=205.0, spread_width=5.0,
        breakeven=202.0, long_delta=0.55, short_delta=0.35, net_theta=-0.1,
        prob_of_profit=0.55, reward_risk_ratio=1.5, ev_raw=12.0, net_debit=2.0,
        max_profit=300.0, max_loss=200.0, long_iv=0.30, short_iv=0.28,
        long_volume=10, short_volume=8, long_oi=100, short_oi=90,
    )
    rec = _record("v1", "trend-rider", "EXECUTE", 82.0,
                  breakdown=[ScoringBreakdown("expected_value", 60.0, 0.2, 12.0)])
    row = ar._vertical_engine_row(c, rec)
    assert row["composite_score"] == 82.0
    assert row["verdict"] == "EXECUTE"
    assert row["spread_type"] == "bull_call"
    assert row["long_strike"] == 200.0 and row["short_strike"] == 205.0
    assert row["net_delta"] == pytest.approx(0.20, abs=1e-9)   # |0.55| - |0.35|
    assert row["required_move_pct"] == pytest.approx(1.0)       # (202-200)/200*100, bull
    assert row["iv"] == 0.28                                    # short_iv preferred
    assert row["score_components"][0]["key"] == "expected_value"
    # No legacy min-max keys leaked.
    assert "ev_score" not in row and "score_breakdown" not in row


def test_long_option_engine_row_engine_owned():
    c = _cand(
        "l1", underlying_price=200.0, spread_type="long_call", option_type="call",
        expiration="2026-07-17", strike=210.0, dte=31, bid=1.0, ask=1.2,
        mid_price=1.1, premium_dollars=110.0, delta=0.30, theta=-0.05,
        theta_runway_days=22.0, breakeven=211.1, breakeven_distance_pct=5.5,
        iv=0.40, volume=12, open_interest=300,
    )
    rec = _record("l1", "lottery-ticket", "WAIT", 48.0)
    row = ar._long_option_engine_row(c, rec)
    assert row["composite_score"] == 48.0 and row["verdict"] == "WAIT"
    assert row["strike"] == 210.0 and row["days_to_exp"] == 31
    assert row["theta_per_day_dollars"] == pytest.approx(5.0)   # abs(-0.05)*100
    assert "delta_score" not in row


# ── _build_engine_rows: best-first ordering + scoring_strategy_key stamp ──────


def test_build_engine_rows_sorted_and_stamped():
    c_exec = _cand("a", spread_type="bull_call", underlying_price=100.0, breakeven=100.0)
    c_wait = _cand("b", spread_type="bull_call", underlying_price=100.0, breakeven=100.0)
    best = {
        "b": (_record("b", "trend-rider", "WAIT", 90.0), "trend-rider"),
        "a": (_record("a", "trend-rider", "EXECUTE", 51.0), "trend-rider"),
    }
    rows = ar._build_engine_rows([c_exec, c_wait], best, ar._vertical_engine_row)
    # EXECUTE/51 sorts ahead of WAIT/90 (tier first).
    assert [r["verdict"] for r in rows] == ["EXECUTE", "WAIT"]
    assert all(r["scoring_strategy_key"] == "trend-rider" for r in rows)


# ── _screen_candidates_through_engine: orchestration ─────────────────────────


def test_screen_engine_best_pick_and_subsets(monkeypatch):
    calls = []
    # canned (verdict, score) per (strategy_key, candidate_id)
    canned = {
        ("steady-paycheck", "credit1"): ("WAIT", 60.0),
        ("weekly-grind", "credit1"): ("EXECUTE", 55.0),   # tier wins despite lower score
        ("trend-rider", "debit1"): ("EXECUTE", 80.0),
    }

    def fake_evaluate(*, candidates, strategy_key, source_app_id, config,
                      registry, adapter, sink, null_semantics):
        calls.append({"strategy_key": strategy_key, "ids": [c.candidate_id for c in candidates],
                      "source_app_id": source_app_id, "sink": sink})
        return [_record(c.candidate_id, strategy_key, *canned[(strategy_key, c.candidate_id)])
                for c in candidates]

    monkeypatch.setattr(ar, "evaluate", fake_evaluate)

    candidates = [
        _cand("credit1", spread_type="bull_put"),   # → SP + WG
        _cand("debit1", spread_type="bull_call"),    # → TR
    ]
    rt = _runtime(["steady-paycheck", "weekly-grind", "trend-rider", "lottery-ticket"])
    best = ar._screen_candidates_through_engine(rt, _StubAdapter(), candidates)

    # credit1 picks weekly-grind (EXECUTE) over steady-paycheck (WAIT).
    assert best["credit1"][1] == "weekly-grind"
    assert best["credit1"][0].verdict == "EXECUTE"
    # debit1 picks trend-rider.
    assert best["debit1"][1] == "trend-rider"

    # Per-strategy subset filtering: TR only saw the debit candidate; SP/WG only the credit one.
    by_strategy = {c["strategy_key"]: c["ids"] for c in calls}
    assert by_strategy["trend-rider"] == ["debit1"]
    assert by_strategy["steady-paycheck"] == ["credit1"]
    assert by_strategy["weekly-grind"] == ["credit1"]
    # Sink + source_app_id propagated to every evaluate call (additive bronze).
    assert all(c["source_app_id"] == "OTA" and c["sink"] is rt.sink for c in calls)


def test_screen_engine_fail_closed_422(monkeypatch):
    monkeypatch.setattr(ar, "evaluate", lambda **k: pytest.fail("evaluate must not run when a strategy is missing"))
    candidates = [_cand("credit1", spread_type="bull_put")]   # needs SP + WG
    rt = _runtime(["steady-paycheck"])  # weekly-grind missing → fail-closed
    with pytest.raises(HTTPException) as exc:
        ar._screen_candidates_through_engine(rt, _StubAdapter(), candidates)
    assert exc.value.status_code == 422
    assert "weekly-grind" in str(exc.value.detail)


def test_screen_engine_no_applicable_short_circuits(monkeypatch):
    monkeypatch.setattr(ar, "evaluate", lambda **k: pytest.fail("evaluate must not run with no applicable strategy"))
    candidates = [_cand("x", spread_type="iron_condor")]  # unknown structure → no strategies
    rt = _runtime(["steady-paycheck", "weekly-grind", "trend-rider", "lottery-ticket"])
    assert ar._screen_candidates_through_engine(rt, _StubAdapter(), candidates) == {}
