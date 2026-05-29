"""
Insight Engine — core dataclasses and enums.

Nine dataclasses forming the engine's runtime and result vocabulary:

Config/resolved-config (frozen):
    NamedValue, Rule, Strategy, JunctionRow, RuleSet

Candidate (mutable named-value map):
    Candidate

Result/persistence:
    ResultRecord, CandidateSnapshot, EvaluationDecision

Engine enums:
    Tier, Phase, VerdictSource

All shapes only — no loader, no pipeline, no population logic.
Domain terms (verdict labels, named-value names, candidate_type,
consumer_surface, strategy_key) are opaque ``str``.

OTA-697
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ── Engine enums ─────────────────────────────────────────────────────────


class Tier(enum.Enum):
    """Calculation tier — controls gate evaluation order (§3.5)."""
    RAW = "RAW"
    DERIVED = "DERIVED"
    COMPUTED = "COMPUTED"


class Phase(enum.Enum):
    """Pipeline phase — fixed execution order (§3.6, §4)."""
    GATE = "gate"
    SCORING = "scoring"
    ADJUSTMENT = "adjustment"
    VERDICT = "verdict"


class VerdictSource(enum.Enum):
    """How the verdict was determined (OTA-703, OTA-695 OD-2).

    Defined now; populated by downstream Stories.
    """
    BAND_LOOKUP = "BAND_LOOKUP"
    HALT_TERMINAL_VERDICT = "HALT_TERMINAL_VERDICT"
    HALT_NO_VERDICT = "HALT_NO_VERDICT"


# ── Config / resolved-config dataclasses (frozen) ────────────────────────


@dataclass(frozen=True)
class NamedValue:
    """A scalar value carried by a candidate (§3.2).

    The engine never invents named values — they come from the adapter.
    """
    name: str
    tier: Tier
    value_type: str  # "number", "enum", "date", "boolean"
    null_semantics: str | None = None  # FAIL_OPEN | FAIL_CLOSED | SKIP


@dataclass(frozen=True)
class Rule:
    """An independent, reusable evaluation atom (§3.3).

    Carries no per-strategy parameters, weights, or stop behaviour.
    """
    rule_key: str
    phase: Phase
    tier: Tier | None  # nullable for non-gate phases
    intent: str | None
    condition_expression: str | None
    formula_ref: str | None
    referenced_named_values: tuple[str, ...]
    parameter_schema: dict[str, Any]
    null_semantics: str | None = None  # FAIL_OPEN | FAIL_CLOSED | SKIP


@dataclass(frozen=True)
class Strategy:
    """A named evaluation strategy (§3.4).

    Carries no rule logic. Rule bindings live on JunctionRow.
    """
    strategy_key: str
    display_name: str
    consumer_surface: str  # opaque: SCREENING, POSITION_HEALTH, DIRECTIONAL, ...
    description: str | None
    compatible_structures: tuple[str, ...] | None  # screening only
    verdict_band_set: list[dict[str, Any]]  # parsed score→verdict bands
    dte_min: int | None = None
    dte_max: int | None = None


@dataclass(frozen=True)
class JunctionRow:
    """The single home of per-strategy config for a rule (§3.4).

    evaluation_order, stop_if_fail, score_penalty, weight are junction
    inputs. terminal_phase and was_terminal are computed outputs that
    live on ResultRecord / CandidateSnapshot / EvaluationDecision.
    """
    strategy_key: str
    rule_key: str
    evaluation_order: int
    stop_if_fail: bool
    score_penalty: float | None  # held penalty on non-stopping failure
    weight: float | None  # scoring criteria only
    parameters: dict[str, Any]
    rationale: str | None
    enabled: bool
    terminal_verdict: str | None = None  # per (strategy, rule) halt verdict


@dataclass(frozen=True)
class RuleSet:
    """Resolved runtime view — a strategy with its junction-bound rules (§3.4).

    Population and sorting is OTA-698; this Story defines the container.
    Supports phase-grouped access in evaluation_order.
    """
    strategy: Strategy
    bindings: tuple[RuleBinding, ...]  # ordered by (phase, evaluation_order)


@dataclass(frozen=True)
class RuleBinding:
    """A rule paired with its junction row within a RuleSet."""
    rule: Rule
    junction: JunctionRow


# ── Candidate (mutable) ─────────────────────────────────────────────────


@dataclass
class Candidate:
    """An opaque container of named values evaluated by the engine (§3.1).

    Mutable so the adapter can populate COMPUTED values between phases (§5.2).
    Optional metadata fields (symbol, user_id, subject_type, subject_id) are
    promoted to bronze columns for filtering; they are not evaluated by rules.
    """
    candidate_id: str
    candidate_type: str  # opaque: options_trade, position, directional, ...
    named_values: dict[str, Any] = field(default_factory=dict)
    symbol: str | None = None
    user_id: str | None = None
    subject_type: str | None = None  # POSITION | TRADE_CANDIDATE | ...
    subject_id: str | None = None


# ── Result dataclasses ───────────────────────────────────────────────────


@dataclass
class GateDecision:
    """Per-gate trace entry within a ResultRecord."""
    rule_key: str
    phase: Phase
    tier: Tier | None
    evaluation_order: int
    value_evaluated: Any
    parameters_evaluated: dict[str, Any]
    passed: bool
    stop_if_fail: bool
    was_terminal: bool
    held_penalty: float | None
    decision_reason: str


@dataclass
class ScoringBreakdown:
    """Per-criterion scoring entry within a ResultRecord."""
    rule_key: str
    raw_value: float
    weight: float
    weighted_contribution: float


@dataclass
class AdjustmentResult:
    """Per-adjustment entry within a ResultRecord."""
    rule_key: str
    amount: float
    condition_triggered: bool
    score_before: float
    score_after: float
    reason: str


@dataclass
class ResultRecord:
    """Complete engine output per candidate (§4.2).

    Carries the mandatory full per-rule trace — every decision, including
    non-stopping and zero-penalty failures.

    Allows non-null verdict with null final_score (halt-with-verdict case).
    """
    # Candidate identity
    candidate_id: str
    candidate_type: str  # opaque
    source_app_id: str
    strategy_key: str

    # Terminal phase
    terminal_phase: str  # where the candidate exited

    # Per-gate trace (full, mandatory)
    gate_decisions: list[GateDecision]

    # Per-criterion scoring breakdown
    scoring_breakdown: list[ScoringBreakdown]

    # Scores
    raw_score: float | None  # null if halted before scoring
    held_penalties_applied: float | None

    # Per-adjustment results
    adjustment_results: list[AdjustmentResult]

    # Final score and verdict
    final_score: float | None  # nullable: halt-with-verdict case
    verdict: str | None  # nullable opaque string; may be non-null even if final_score is null
    verdict_source: VerdictSource | None  # BAND_LOOKUP | HALT_TERMINAL_VERDICT | HALT_NO_VERDICT

    # Engine metadata
    engine_version: str
    config_version: str
    run_timestamp: datetime


@dataclass
class CandidateSnapshot:
    """One per candidate per run — persistence stream 1 (§4.3).

    Promoted columns are direct attributes (used in WHERE/JOIN/GROUP BY).
    Everything else (named values, result summary detail, verdict_source)
    lives in ``payload_json``. Provenance is stamped on every record.
    """
    # Correlation
    snapshot_id: str
    run_id: str

    # Provenance (stamped on every record)
    source_app_id: str
    config_version: str
    engine_version: str
    evaluated_at: datetime
    payload_version: int

    # Promoted columns (filter/group targets)
    candidate_type: str  # opaque
    strategy_key: str
    symbol: str | None
    user_id: str | None
    subject_type: str | None
    subject_id: str | None
    final_score: float | None  # null if halted before scoring
    verdict: str | None  # null if halted before verdict
    terminal_phase: str

    # Everything else — named values, raw_score, held_penalties,
    # verdict_source, scoring breakdown, adjustment summary
    payload_json: dict[str, Any]


@dataclass
class EvaluationDecision:
    """One per rule evaluation — persistence stream 2 (§4.3).

    Correlation to its snapshot via shared ``snapshot_id`` and ``run_id``.
    Promoted columns are direct attributes; value_evaluated, parameters,
    decision_reason, and formula trace live in ``payload_json``.
    """
    # Correlation
    snapshot_id: str
    run_id: str

    # Provenance (stamped on every record)
    source_app_id: str
    config_version: str
    engine_version: str
    evaluated_at: datetime
    payload_version: int

    # Promoted columns
    rule_key: str
    phase: str  # denormalized string: "gate", "scoring", "adjustment"
    tier: str | None  # "RAW", "DERIVED", "COMPUTED"
    evaluation_order: int
    passed: bool
    stop_if_fail: bool
    was_terminal: bool
    score_contribution: float | None

    # Everything else — value_evaluated, parameters, decision_reason, formula trace
    payload_json: dict[str, Any]
