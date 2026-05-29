"""
7-phase pipeline orchestrator — the engine's single execution path.

Fixed phase order (insight_engine.md §4):
    1. Gates (RAW)
    2. Gates (DERIVED)
       [adapter COMPUTED callback — OTA-702]
    3. Gates (COMPUTED)
    4. Scoring (weighted sum)
    5. Apply held gate penalties
    6. Adjustments (clamp [0,100] after each)
    7. Verdict band lookup

Gate mechanics driven entirely by junction fields:
    stop_if_fail=true  + fail → halt, record terminal decision
    stop_if_fail=false + fail → record, hold score_penalty, continue

COMPUTED callback (OTA-702): fires exactly once per batch between
Phase 2 (DERIVED gates) and Phase 3 (COMPUTED gates), with only
surviving candidates. The adapter populates COMPUTED named values
needed by remaining active rules (COMPUTED gates, scoring, adjustments).

OTA-701, OTA-702
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.insight_engine.expressions import (
    evaluate_expression,
    invoke_formula,
    is_formula_ref,
)
from app.insight_engine.models import (
    AdjustmentResult,
    Candidate,
    GateDecision,
    Phase,
    RuleBinding,
    RuleSet,
    ScoringBreakdown,
    Tier,
    VerdictSource,
)
from app.insight_engine.registry import FormulaRegistry


# ── Adapter callback contract (OTA-702) ──────────────────────────────


class ComputedAdapter(Protocol):
    """COMPUTED-value callback between Phase 2 and Phase 3.

    The engine calls ``populate_computed`` exactly once per batch run,
    passing only candidates that survived RAW and DERIVED gates, and
    the set of COMPUTED named-value names referenced by remaining
    active rules (COMPUTED gates, scoring criteria, adjustments).

    The adapter mutates candidates in-place, populating the requested
    COMPUTED values in each candidate's ``named_values`` dict.

    The engine defines this contract; it implements no COMPUTED math.
    """

    def populate_computed(
        self,
        candidates: list[Candidate],
        needed: set[str],
    ) -> None:
        """Populate COMPUTED named values on surviving candidates."""
        ...


# ── Pipeline result ─────────────────────────────────────────────────────


@dataclass
class PipelineResult:
    """Intermediate result from the orchestrator per candidate.

    OTA-703 assembles this into the full ResultRecord with provenance.
    """

    candidate_id: str
    candidate_type: str

    # Per-gate trace
    gate_decisions: list[GateDecision] = field(default_factory=list)

    # Per-criterion scoring
    scoring_breakdown: list[ScoringBreakdown] = field(default_factory=list)
    raw_score: float | None = None

    # Held penalties from non-stopping gate failures
    held_penalties_applied: float | None = None

    # Per-adjustment results
    adjustment_results: list[AdjustmentResult] = field(default_factory=list)

    # Final outcome
    final_score: float | None = None
    verdict: str | None = None
    verdict_source: VerdictSource | None = None
    terminal_phase: str = "verdict"  # where the candidate exited


# ── Public API ──────────────────────────────────────────────────────────


def run_batch(
    candidates: list[Candidate],
    rule_set: RuleSet,
    registry: FormulaRegistry,
    adapter: ComputedAdapter | None = None,
) -> list[PipelineResult]:
    """Evaluate a batch of candidates with once-only COMPUTED callback.

    This is the primary entry point for batch evaluation. The COMPUTED
    adapter callback fires exactly once between Phase 2 (DERIVED gates)
    and Phase 3 (COMPUTED gates), with only surviving candidates.

    Parameters
    ----------
    candidates : list[Candidate]
        Candidates to evaluate.
    rule_set : RuleSet
        The resolved strategy + bound rules (from OTA-698 loader).
    registry : FormulaRegistry
        Live formula registry for formula-based rules.
    adapter : ComputedAdapter | None
        COMPUTED-value callback adapter. When provided, the engine
        calls it once with survivors and the needed COMPUTED names.
    """
    # Partition bindings by phase and tier
    raw_derived_gates: list[RuleBinding] = []
    computed_gates: list[RuleBinding] = []
    scoring_bindings: list[RuleBinding] = []
    adjustment_bindings: list[RuleBinding] = []

    for binding in rule_set.bindings:
        if not binding.junction.enabled:
            continue
        phase = binding.rule.phase
        if phase == Phase.GATE:
            if binding.rule.tier == Tier.COMPUTED:
                computed_gates.append(binding)
            else:
                raw_derived_gates.append(binding)
        elif phase == Phase.SCORING:
            scoring_bindings.append(binding)
        elif phase == Phase.ADJUSTMENT:
            adjustment_bindings.append(binding)

    # ── Phases 1–2: RAW + DERIVED gates ──────────────────────────────
    survivors: list[tuple[Candidate, PipelineResult, list[float]]] = []
    all_results: list[PipelineResult] = []

    for candidate in candidates:
        result = PipelineResult(
            candidate_id=candidate.candidate_id,
            candidate_type=candidate.candidate_type,
        )
        held_penalties: list[float] = []
        halted = _run_gate_list(
            candidate, raw_derived_gates, registry, result, held_penalties
        )
        if halted:
            all_results.append(result)
        else:
            survivors.append((candidate, result, held_penalties))

    # ── COMPUTED callback — fires exactly once with survivors only ────
    if adapter is not None and survivors:
        needed = _collect_all_needed_computed_names(
            computed_gates, scoring_bindings, adjustment_bindings
        )
        if needed:
            survivor_candidates = [c for c, _, _ in survivors]
            adapter.populate_computed(survivor_candidates, needed)

    # ── Phases 3–7 on survivors ──────────────────────────────────────
    for candidate, result, held_penalties in survivors:
        # Phase 3: COMPUTED gates
        halted = _run_gate_list(
            candidate, computed_gates, registry, result, held_penalties
        )
        if halted:
            all_results.append(result)
            continue

        # Phase 4: Scoring (weighted sum)
        raw_score = _run_scoring(candidate, scoring_bindings, registry, result)
        result.raw_score = raw_score

        # Phase 5: Apply held gate penalties
        score = raw_score
        total_penalty = sum(held_penalties)
        if total_penalty != 0:
            score -= total_penalty
            score = max(0.0, min(100.0, score))
        result.held_penalties_applied = (
            total_penalty if total_penalty != 0 else None
        )

        # Phase 6: Adjustments
        score = _run_adjustments(
            candidate, adjustment_bindings, registry, result, score
        )
        result.final_score = score

        # Phase 7: Verdict band lookup
        verdict = _lookup_verdict_band(
            score, rule_set.strategy.verdict_band_set
        )
        result.verdict = verdict
        result.verdict_source = VerdictSource.BAND_LOOKUP
        result.terminal_phase = "verdict"

        all_results.append(result)

    return all_results


def run_pipeline(
    candidate: Candidate,
    rule_set: RuleSet,
    registry: FormulaRegistry,
    adapter: ComputedAdapter | None = None,
) -> PipelineResult:
    """Evaluate a single candidate through the 7-phase pipeline.

    Delegates to ``run_batch`` for proper COMPUTED callback semantics.

    Parameters
    ----------
    candidate : Candidate
        The candidate to evaluate.
    rule_set : RuleSet
        The resolved strategy + bound rules (from OTA-698 loader).
    registry : FormulaRegistry
        Live formula registry for formula-based rules.
    adapter : ComputedAdapter | None
        COMPUTED-value callback adapter.
    """
    results = run_batch([candidate], rule_set, registry, adapter)
    return results[0]


# ── Gate execution (Phases 1–3) ─────────────────────────────────────────


def _run_gate_list(
    candidate: Candidate,
    gate_bindings: list[RuleBinding],
    registry: FormulaRegistry,
    result: PipelineResult,
    held_penalties: list[float],
) -> bool:
    """Run a list of gate bindings. Returns True if candidate was halted."""
    for binding in gate_bindings:
        # Evaluate the gate
        passed = _evaluate_rule(candidate, binding, registry)

        decision = GateDecision(
            rule_key=binding.rule.rule_key,
            phase=binding.rule.phase,
            tier=binding.rule.tier,
            evaluation_order=binding.junction.evaluation_order,
            value_evaluated=_get_evaluated_value(candidate, binding),
            parameters_evaluated=binding.junction.parameters,
            passed=passed,
            stop_if_fail=binding.junction.stop_if_fail,
            was_terminal=False,
            held_penalty=None,
            decision_reason="",
        )

        if not passed:
            if binding.junction.stop_if_fail:
                # Halt — terminal decision
                decision.was_terminal = True
                decision.decision_reason = (
                    f"Gate '{binding.rule.rule_key}' failed with stop_if_fail=true"
                )
                result.gate_decisions.append(decision)

                # OD-2: halt-verdict path
                tv = binding.junction.terminal_verdict
                if tv is not None:
                    result.verdict = tv
                    result.verdict_source = VerdictSource.HALT_TERMINAL_VERDICT
                else:
                    result.verdict = None
                    result.verdict_source = VerdictSource.HALT_NO_VERDICT

                result.final_score = None
                result.terminal_phase = binding.rule.phase.value
                return True  # halted
            else:
                # Non-stopping failure: hold penalty, continue
                penalty = binding.junction.score_penalty or 0.0
                if penalty != 0:
                    held_penalties.append(penalty)
                    decision.held_penalty = penalty
                decision.decision_reason = (
                    f"Gate '{binding.rule.rule_key}' failed with "
                    f"stop_if_fail=false; penalty={penalty} held"
                )
        else:
            decision.decision_reason = f"Gate '{binding.rule.rule_key}' passed"

        result.gate_decisions.append(decision)

    return False  # not halted


def _collect_all_needed_computed_names(
    computed_gates: list[RuleBinding],
    scoring_bindings: list[RuleBinding],
    adjustment_bindings: list[RuleBinding],
) -> set[str]:
    """Collect COMPUTED named-value names referenced by remaining active rules.

    Includes names from:
    - COMPUTED-tier gate bindings (Phase 3)
    - Scoring criteria with tier=COMPUTED
    - Adjustments with tier=COMPUTED
    """
    needed: set[str] = set()
    for binding in computed_gates:
        for nv in binding.rule.referenced_named_values:
            needed.add(nv)
    for binding in scoring_bindings:
        if binding.rule.tier == Tier.COMPUTED:
            for nv in binding.rule.referenced_named_values:
                needed.add(nv)
    for binding in adjustment_bindings:
        if binding.rule.tier == Tier.COMPUTED:
            for nv in binding.rule.referenced_named_values:
                needed.add(nv)
    return needed


# ── Scoring (Phase 4) ──────────────────────────────────────────────────


def _run_scoring(
    candidate: Candidate,
    scoring_bindings: list[RuleBinding],
    registry: FormulaRegistry,
    result: PipelineResult,
) -> float:
    """Run scoring criteria. Returns the raw weighted score."""
    raw_score = 0.0

    for binding in scoring_bindings:
        weight = binding.junction.weight or 0.0
        raw_value = _evaluate_rule_numeric(candidate, binding, registry)

        weighted = raw_value * weight
        raw_score += weighted

        result.scoring_breakdown.append(ScoringBreakdown(
            rule_key=binding.rule.rule_key,
            raw_value=raw_value,
            weight=weight,
            weighted_contribution=weighted,
        ))

    return max(0.0, min(100.0, raw_score))


# ── Adjustments (Phase 6) ──────────────────────────────────────────────


def _run_adjustments(
    candidate: Candidate,
    adjustment_bindings: list[RuleBinding],
    registry: FormulaRegistry,
    result: PipelineResult,
    score: float,
) -> float:
    """Run adjustment rules. Returns the final adjusted score."""
    for binding in adjustment_bindings:
        score_before = score
        adj_result = _evaluate_rule_numeric(candidate, binding, registry)

        # If the formula returns a bool, convert: True → 0 (pass), False → penalty
        if isinstance(adj_result, bool):
            if not adj_result:
                amount = -(binding.junction.score_penalty or 0.0)
            else:
                amount = 0.0
            triggered = not adj_result
        else:
            amount = float(adj_result)
            triggered = amount != 0.0

        if triggered:
            score += amount
            score = max(0.0, min(100.0, score))

        result.adjustment_results.append(AdjustmentResult(
            rule_key=binding.rule.rule_key,
            amount=amount,
            condition_triggered=triggered,
            score_before=score_before,
            score_after=score,
            reason=(
                f"Adjustment '{binding.rule.rule_key}': "
                f"{'triggered' if triggered else 'not triggered'}, "
                f"amount={amount}"
            ),
        ))

    return score


# ── Verdict band lookup (Phase 7) ──────────────────────────────────────


def _lookup_verdict_band(
    score: float,
    verdict_band_set: list[dict[str, Any]],
) -> str | None:
    """Map a final score to a verdict string via the strategy's bands.

    Bands are expected in descending min_score order.
    """
    for band in verdict_band_set:
        min_score = band.get("min_score", 0)
        max_score = band.get("max_score", 100)
        if min_score <= score <= max_score:
            return band.get("verdict")
    return None


# ── Rule evaluation helpers ─────────────────────────────────────────────


def _evaluate_rule(
    candidate: Candidate,
    binding: RuleBinding,
    registry: FormulaRegistry,
) -> bool:
    """Evaluate a rule as a boolean (for gates)."""
    rule = binding.rule
    params = binding.junction.parameters

    if is_formula_ref(rule.formula_ref):
        result = invoke_formula(
            rule.formula_ref, registry, candidate.named_values, params
        )
        return bool(result)

    if rule.condition_expression:
        return evaluate_expression(
            rule.condition_expression,
            candidate.named_values,
            params,
            rule.referenced_named_values,
        )

    return True  # no expression and no formula → pass


def _evaluate_rule_numeric(
    candidate: Candidate,
    binding: RuleBinding,
    registry: FormulaRegistry,
) -> Any:
    """Evaluate a rule and return its numeric (or bool) result.

    For scoring criteria and adjustments.
    """
    rule = binding.rule
    params = binding.junction.parameters

    if is_formula_ref(rule.formula_ref):
        return invoke_formula(
            rule.formula_ref, registry, candidate.named_values, params
        )

    if rule.condition_expression:
        return evaluate_expression(
            rule.condition_expression,
            candidate.named_values,
            params,
            rule.referenced_named_values,
        )

    return 0.0


def _get_evaluated_value(
    candidate: Candidate,
    binding: RuleBinding,
) -> Any:
    """Extract the primary evaluated value for trace purposes."""
    refs = binding.rule.referenced_named_values
    if refs:
        return candidate.named_values.get(refs[0])
    return None
