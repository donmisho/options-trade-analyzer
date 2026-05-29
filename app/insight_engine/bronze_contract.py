"""
Bronze record contract — maps ResultRecord into the two logical persistence streams.

The engine **owns the shape** of what gets persisted and **drives the write**,
but does not own write mechanics (insight_engine.md §4.3). This module produces:

1. CandidateSnapshot — one per candidate per run (full named-value set + summary)
2. EvaluationDecision — one per rule evaluation (per-gate, per-criterion, per-adjustment)

Both streams share correlation keys (snapshot_id, run_id) and provenance
(source_app_id, config_version, engine_version, evaluated_at).

The promote-to-column vs. payload_json split follows the §4.3 golden rule:
anything in a WHERE/JOIN/GROUP BY is a promoted column; everything else is
in payload_json.

This module references NO table name, NO DB driver, NO connection logic.

OTA-704
"""

from __future__ import annotations

import uuid
from typing import Any

from app.insight_engine.models import (
    AdjustmentResult,
    Candidate,
    CandidateSnapshot,
    EvaluationDecision,
    GateDecision,
    ResultRecord,
    ScoringBreakdown,
)

# Initial payload versions for the bronze contract.
SNAPSHOT_PAYLOAD_VERSION = 1
DECISION_PAYLOAD_VERSION = 1


def build_bronze_streams(
    result: ResultRecord,
    candidate: Candidate,
    *,
    run_id: str,
) -> tuple[CandidateSnapshot, list[EvaluationDecision]]:
    """Map a ResultRecord into the two bronze persistence streams.

    Parameters
    ----------
    result : ResultRecord
        Complete engine output for one candidate (from OTA-703 builder).
    candidate : Candidate
        The original candidate (carries named_values + metadata).
    run_id : str
        Shared run identifier for this batch (caller-supplied).

    Returns
    -------
    (CandidateSnapshot, list[EvaluationDecision])
        The snapshot and its correlated decision records.
    """
    snapshot_id = str(uuid.uuid4())

    snapshot = _build_snapshot(result, candidate, run_id=run_id, snapshot_id=snapshot_id)
    decisions = _build_decisions(result, run_id=run_id, snapshot_id=snapshot_id)

    return snapshot, decisions


def build_bronze_batch(
    results: list[ResultRecord],
    candidates: list[Candidate],
    *,
    run_id: str | None = None,
) -> tuple[list[CandidateSnapshot], list[EvaluationDecision]]:
    """Map a batch of ResultRecords into bronze streams.

    All records in a batch share the same run_id (generated if not supplied).

    Parameters
    ----------
    results : list[ResultRecord]
        One per candidate, from OTA-703 builder.
    candidates : list[Candidate]
        Original candidates (same order as results).
    run_id : str | None
        Shared run identifier. Generated if not provided.

    Returns
    -------
    (list[CandidateSnapshot], list[EvaluationDecision])
    """
    rid = run_id or str(uuid.uuid4())

    all_snapshots: list[CandidateSnapshot] = []
    all_decisions: list[EvaluationDecision] = []

    # Build a lookup for candidates by id for correlation
    candidate_map = {c.candidate_id: c for c in candidates}

    for result in results:
        candidate = candidate_map[result.candidate_id]
        snapshot, decisions = build_bronze_streams(result, candidate, run_id=rid)
        all_snapshots.append(snapshot)
        all_decisions.extend(decisions)

    return all_snapshots, all_decisions


# ── Internal builders ───────────────────────────────────────────────────


def _build_snapshot(
    result: ResultRecord,
    candidate: Candidate,
    *,
    run_id: str,
    snapshot_id: str,
) -> CandidateSnapshot:
    """Build a CandidateSnapshot with promoted/payload split."""
    # Payload: everything not promoted
    payload: dict[str, Any] = {
        "named_values": candidate.named_values,
        "raw_score": result.raw_score,
        "held_penalties_applied": result.held_penalties_applied,
        "verdict_source": result.verdict_source.value if result.verdict_source else None,
        "scoring_summary": [
            {
                "rule_key": s.rule_key,
                "raw_value": s.raw_value,
                "weight": s.weight,
                "weighted_contribution": s.weighted_contribution,
            }
            for s in result.scoring_breakdown
        ],
        "adjustment_summary": [
            {
                "rule_key": a.rule_key,
                "amount": a.amount,
                "condition_triggered": a.condition_triggered,
                "score_before": a.score_before,
                "score_after": a.score_after,
                "reason": a.reason,
            }
            for a in result.adjustment_results
        ],
        "gate_count": len(result.gate_decisions),
        "gate_pass_count": sum(1 for g in result.gate_decisions if g.passed),
    }

    return CandidateSnapshot(
        snapshot_id=snapshot_id,
        run_id=run_id,
        source_app_id=result.source_app_id,
        config_version=result.config_version,
        engine_version=result.engine_version,
        evaluated_at=result.run_timestamp,
        payload_version=SNAPSHOT_PAYLOAD_VERSION,
        candidate_type=result.candidate_type,
        strategy_key=result.strategy_key,
        symbol=candidate.symbol,
        user_id=candidate.user_id,
        subject_type=candidate.subject_type,
        subject_id=candidate.subject_id,
        final_score=result.final_score,
        verdict=result.verdict,
        terminal_phase=result.terminal_phase,
        payload_json=payload,
    )


def _build_decisions(
    result: ResultRecord,
    *,
    run_id: str,
    snapshot_id: str,
) -> list[EvaluationDecision]:
    """Build EvaluationDecision records for all rule evaluations."""
    decisions: list[EvaluationDecision] = []

    # Gate decisions
    for gate in result.gate_decisions:
        decisions.append(_gate_to_decision(gate, result, run_id, snapshot_id))

    # Scoring criteria
    for scoring in result.scoring_breakdown:
        decisions.append(_scoring_to_decision(scoring, result, run_id, snapshot_id))

    # Adjustments
    for adj in result.adjustment_results:
        decisions.append(_adjustment_to_decision(adj, result, run_id, snapshot_id))

    return decisions


def _gate_to_decision(
    gate: GateDecision,
    result: ResultRecord,
    run_id: str,
    snapshot_id: str,
) -> EvaluationDecision:
    # Score contribution: negative held_penalty if one was applied
    score_contribution = (
        -gate.held_penalty if gate.held_penalty is not None and gate.held_penalty != 0
        else None
    )

    return EvaluationDecision(
        snapshot_id=snapshot_id,
        run_id=run_id,
        source_app_id=result.source_app_id,
        config_version=result.config_version,
        engine_version=result.engine_version,
        evaluated_at=result.run_timestamp,
        payload_version=DECISION_PAYLOAD_VERSION,
        rule_key=gate.rule_key,
        phase=gate.phase.value if hasattr(gate.phase, "value") else str(gate.phase),
        tier=gate.tier.value if gate.tier is not None and hasattr(gate.tier, "value") else None,
        evaluation_order=gate.evaluation_order,
        passed=gate.passed,
        stop_if_fail=gate.stop_if_fail,
        was_terminal=gate.was_terminal,
        score_contribution=score_contribution,
        payload_json={
            "value_evaluated": gate.value_evaluated,
            "parameters_evaluated": gate.parameters_evaluated,
            "decision_reason": gate.decision_reason,
            "held_penalty": gate.held_penalty,
        },
    )


def _scoring_to_decision(
    scoring: ScoringBreakdown,
    result: ResultRecord,
    run_id: str,
    snapshot_id: str,
) -> EvaluationDecision:
    return EvaluationDecision(
        snapshot_id=snapshot_id,
        run_id=run_id,
        source_app_id=result.source_app_id,
        config_version=result.config_version,
        engine_version=result.engine_version,
        evaluated_at=result.run_timestamp,
        payload_version=DECISION_PAYLOAD_VERSION,
        rule_key=scoring.rule_key,
        phase="scoring",
        tier=None,
        evaluation_order=0,  # scoring criteria don't carry per-decision order
        passed=True,  # scoring criteria always "pass" (they contribute a value)
        stop_if_fail=False,
        was_terminal=False,
        score_contribution=scoring.weighted_contribution,
        payload_json={
            "raw_value": scoring.raw_value,
            "weight": scoring.weight,
            "weighted_contribution": scoring.weighted_contribution,
        },
    )


def _adjustment_to_decision(
    adj: AdjustmentResult,
    result: ResultRecord,
    run_id: str,
    snapshot_id: str,
) -> EvaluationDecision:
    return EvaluationDecision(
        snapshot_id=snapshot_id,
        run_id=run_id,
        source_app_id=result.source_app_id,
        config_version=result.config_version,
        engine_version=result.engine_version,
        evaluated_at=result.run_timestamp,
        payload_version=DECISION_PAYLOAD_VERSION,
        rule_key=adj.rule_key,
        phase="adjustment",
        tier=None,
        evaluation_order=0,
        passed=not adj.condition_triggered,  # "passed" = condition not triggered
        stop_if_fail=False,
        was_terminal=False,
        score_contribution=adj.amount if adj.condition_triggered else None,
        payload_json={
            "amount": adj.amount,
            "condition_triggered": adj.condition_triggered,
            "score_before": adj.score_before,
            "score_after": adj.score_after,
            "reason": adj.reason,
        },
    )
