"""
Bronze record contract tests — two logical streams with promote/payload split.

OTA-704
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.insight_engine.bronze_contract import (
    DECISION_PAYLOAD_VERSION,
    SNAPSHOT_PAYLOAD_VERSION,
    build_bronze_batch,
    build_bronze_streams,
)
from app.insight_engine.models import (
    AdjustmentResult,
    Candidate,
    GateDecision,
    Phase,
    ResultRecord,
    ScoringBreakdown,
    Tier,
    VerdictSource,
)


# ── Fixture helpers ─────────────────────────────────────────────────────


def _completed_result(*, candidate_id="c1") -> ResultRecord:
    """A completed candidate with gate + scoring + adjustment trace."""
    return ResultRecord(
        candidate_id=candidate_id,
        candidate_type="options_trade",
        source_app_id="OTA",
        strategy_key="steady_paycheck",
        terminal_phase="verdict",
        gate_decisions=[
            GateDecision(
                rule_key="dte_gate",
                phase=Phase.GATE,
                tier=Tier.RAW,
                evaluation_order=1,
                value_evaluated=30,
                parameters_evaluated={"min": 14},
                passed=True,
                stop_if_fail=True,
                was_terminal=False,
                held_penalty=None,
                decision_reason="Gate 'dte_gate' passed",
            ),
            GateDecision(
                rule_key="soft_gate",
                phase=Phase.GATE,
                tier=Tier.RAW,
                evaluation_order=2,
                value_evaluated=5,
                parameters_evaluated={"min": 10},
                passed=False,
                stop_if_fail=False,
                was_terminal=False,
                held_penalty=5.0,
                decision_reason="Gate 'soft_gate' failed; penalty=5.0 held",
            ),
        ],
        scoring_breakdown=[
            ScoringBreakdown(
                rule_key="quality_score",
                raw_value=80.0,
                weight=0.6,
                weighted_contribution=48.0,
            ),
            ScoringBreakdown(
                rule_key="momentum_score",
                raw_value=70.0,
                weight=0.4,
                weighted_contribution=28.0,
            ),
        ],
        raw_score=76.0,
        held_penalties_applied=5.0,
        adjustment_results=[
            AdjustmentResult(
                rule_key="vol_bonus",
                amount=3.0,
                condition_triggered=True,
                score_before=71.0,
                score_after=74.0,
                reason="Adjustment 'vol_bonus': triggered, amount=3.0",
            ),
        ],
        final_score=74.0,
        verdict="EXECUTE",
        verdict_source=VerdictSource.BAND_LOOKUP,
        engine_version="1.0.0",
        config_version="abc123",
        run_timestamp=datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc),
    )


def _halted_result(*, terminal_verdict="WAIT_FOR_EARNINGS") -> ResultRecord:
    """A candidate halted at a gate with terminal_verdict."""
    return ResultRecord(
        candidate_id="c2",
        candidate_type="options_trade",
        source_app_id="OTA",
        strategy_key="steady_paycheck",
        terminal_phase="gate",
        gate_decisions=[
            GateDecision(
                rule_key="earnings_gate",
                phase=Phase.GATE,
                tier=Tier.RAW,
                evaluation_order=1,
                value_evaluated=5,
                parameters_evaluated={"min": 14},
                passed=False,
                stop_if_fail=True,
                was_terminal=True,
                held_penalty=None,
                decision_reason="Gate 'earnings_gate' failed with stop_if_fail=true",
            ),
        ],
        scoring_breakdown=[],
        raw_score=None,
        held_penalties_applied=None,
        adjustment_results=[],
        final_score=None,
        verdict=terminal_verdict,
        verdict_source=VerdictSource.HALT_TERMINAL_VERDICT,
        engine_version="1.0.0",
        config_version="abc123",
        run_timestamp=datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc),
    )


def _candidate(candidate_id="c1", **extra) -> Candidate:
    return Candidate(
        candidate_id=candidate_id,
        candidate_type="options_trade",
        named_values={"price": 150.0, "dte": 30, "quality": 80.0},
        symbol="AAPL",
        user_id="user-123",
        subject_type="TRADE_CANDIDATE",
        subject_id="tc-456",
        **extra,
    )


# ── Test: completed candidate produces both streams ─────────────────────


class TestCompletedCandidate:
    def test_one_snapshot_and_n_decisions(self):
        result = _completed_result()
        candidate = _candidate()
        snapshot, decisions = build_bronze_streams(result, candidate, run_id="run-1")

        assert snapshot is not None
        # 2 gates + 2 scoring + 1 adjustment = 5 decisions
        assert len(decisions) == 5

    def test_snapshot_provenance_stamped(self):
        result = _completed_result()
        candidate = _candidate()
        snapshot, _ = build_bronze_streams(result, candidate, run_id="run-1")

        assert snapshot.source_app_id == "OTA"
        assert snapshot.config_version == "abc123"
        assert snapshot.engine_version == "1.0.0"
        assert snapshot.evaluated_at == result.run_timestamp
        assert snapshot.run_id == "run-1"
        assert snapshot.snapshot_id  # non-empty

    def test_decision_provenance_stamped(self):
        result = _completed_result()
        candidate = _candidate()
        _, decisions = build_bronze_streams(result, candidate, run_id="run-1")

        for d in decisions:
            assert d.source_app_id == "OTA"
            assert d.config_version == "abc123"
            assert d.engine_version == "1.0.0"
            assert d.evaluated_at == result.run_timestamp
            assert d.run_id == "run-1"

    def test_decisions_correlate_to_snapshot(self):
        result = _completed_result()
        candidate = _candidate()
        snapshot, decisions = build_bronze_streams(result, candidate, run_id="run-1")

        for d in decisions:
            assert d.snapshot_id == snapshot.snapshot_id
            assert d.run_id == snapshot.run_id

    def test_snapshot_promoted_columns(self):
        result = _completed_result()
        candidate = _candidate()
        snapshot, _ = build_bronze_streams(result, candidate, run_id="run-1")

        assert snapshot.candidate_type == "options_trade"
        assert snapshot.strategy_key == "steady_paycheck"
        assert snapshot.symbol == "AAPL"
        assert snapshot.user_id == "user-123"
        assert snapshot.subject_type == "TRADE_CANDIDATE"
        assert snapshot.subject_id == "tc-456"
        assert snapshot.final_score == 74.0
        assert snapshot.verdict == "EXECUTE"
        assert snapshot.terminal_phase == "verdict"

    def test_snapshot_payload_has_named_values(self):
        result = _completed_result()
        candidate = _candidate()
        snapshot, _ = build_bronze_streams(result, candidate, run_id="run-1")

        assert "named_values" in snapshot.payload_json
        assert snapshot.payload_json["named_values"]["price"] == 150.0

    def test_snapshot_payload_has_verdict_source(self):
        result = _completed_result()
        candidate = _candidate()
        snapshot, _ = build_bronze_streams(result, candidate, run_id="run-1")

        assert snapshot.payload_json["verdict_source"] == "BAND_LOOKUP"

    def test_decision_promoted_filter_fields(self):
        """rule_key is a promoted attribute (filter field)."""
        result = _completed_result()
        candidate = _candidate()
        _, decisions = build_bronze_streams(result, candidate, run_id="run-1")

        rule_keys = [d.rule_key for d in decisions]
        assert "dte_gate" in rule_keys
        assert "quality_score" in rule_keys
        assert "vol_bonus" in rule_keys

    def test_decision_payload_has_decision_reason(self):
        """Decision reason lives in payload_json, not promoted."""
        result = _completed_result()
        candidate = _candidate()
        _, decisions = build_bronze_streams(result, candidate, run_id="run-1")

        gate_decision = [d for d in decisions if d.rule_key == "dte_gate"][0]
        assert "decision_reason" in gate_decision.payload_json
        assert "parameters_evaluated" in gate_decision.payload_json

    def test_non_stopping_failure_in_decisions(self):
        """Non-stopping gate failure appears in decisions with penalty."""
        result = _completed_result()
        candidate = _candidate()
        _, decisions = build_bronze_streams(result, candidate, run_id="run-1")

        soft = [d for d in decisions if d.rule_key == "soft_gate"][0]
        assert soft.passed is False
        assert soft.was_terminal is False
        assert soft.score_contribution == -5.0
        assert soft.payload_json["held_penalty"] == 5.0

    def test_payload_version(self):
        result = _completed_result()
        candidate = _candidate()
        snapshot, decisions = build_bronze_streams(result, candidate, run_id="run-1")

        assert snapshot.payload_version == SNAPSHOT_PAYLOAD_VERSION
        for d in decisions:
            assert d.payload_version == DECISION_PAYLOAD_VERSION


# ── Test: halted candidate ──────────────────────────────────────────────


class TestHaltedCandidate:
    def test_halted_snapshot(self):
        result = _halted_result()
        candidate = _candidate(candidate_id="c2")
        snapshot, decisions = build_bronze_streams(result, candidate, run_id="run-1")

        assert snapshot.final_score is None
        assert snapshot.verdict == "WAIT_FOR_EARNINGS"
        assert snapshot.terminal_phase == "gate"
        assert len(decisions) == 1
        assert decisions[0].was_terminal is True


# ── Test: batch ─────────────────────────────────────────────────────────


class TestBatch:
    def test_batch_shared_run_id(self):
        results = [_completed_result(candidate_id="c1"), _halted_result()]
        candidates = [_candidate(candidate_id="c1"), _candidate(candidate_id="c2")]

        snapshots, decisions = build_bronze_batch(
            results, candidates, run_id="batch-run"
        )

        assert len(snapshots) == 2
        assert all(s.run_id == "batch-run" for s in snapshots)
        assert all(d.run_id == "batch-run" for d in decisions)

    def test_batch_generates_run_id(self):
        results = [_completed_result()]
        candidates = [_candidate()]

        snapshots, decisions = build_bronze_batch(results, candidates)

        assert snapshots[0].run_id  # non-empty, auto-generated


# ── Test: no DB references in engine package ─────────────────────────────


class TestNoDatabaseReferences:
    def test_no_db_imports_in_engine(self):
        """grep-equivalent: engine package references no table name or DB driver."""
        import pathlib

        engine_dir = pathlib.Path("app/insight_engine")
        forbidden = {"bronze_evaluations", "pyodbc", "import azure"}
        # _guard.py legitimately references "sqlalchemy" as a forbidden-import
        # pattern to detect — exclude it from this scan.
        skip_files = {"_guard.py"}

        for py_file in engine_dir.glob("*.py"):
            if py_file.name in skip_files:
                continue
            source = py_file.read_text(encoding="utf-8")
            for term in forbidden:
                assert term not in source, (
                    f"Forbidden term '{term}' found in {py_file.name}"
                )
