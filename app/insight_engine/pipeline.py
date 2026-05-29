"""
7-phase pipeline orchestrator — the engine's single execution path.

Fixed phase order (insight_engine.md §4):
    1. Gates (RAW)
    2. Gates (DERIVED)
       [adapter COMPUTED callback seam — OTA-702]
    3. Gates (COMPUTED)
    4. Scoring (weighted sum)
    5. Apply held gate penalties
    6. Adjustments (clamp [0,100] after each)
    7. Verdict band lookup

Gate mechanics driven entirely by junction fields:
    stop_if_fail=true  + fail → halt, record terminal decision
    stop_if_fail=false + fail → record, hold score_penalty, continue

OTA-701
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


# ── Adapter callback seam (OTA-702 owns the contract) ──────────────────


class ComputedAdapter(Protocol):
    """Seam for the COMPUTED-value callback between Phase 2 and Phase 3.

    OTA-702 defines the full contract. The orchestrator calls this
    between DERIVED and COMPUTED gate phases.
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


def run_pipeline(
    candidate: Candidate,
    rule_set: RuleSet,
    registry: FormulaRegistry,
    adapter: ComputedAdapter | None = None,
) -> PipelineResult:
    """Evaluate a single candidate through the 7-phase pipeline.

    Parameters
    ----------
    candidate : Candidate
        The candidate to evaluate.
    rule_set : RuleSet
        The resolved strategy + bound rules (from OTA-698 loader).
    registry : FormulaRegistry
        Live formula registry for formula-based rules.
    adapter : ComputedAdapter | None
        COMPUTED-value callback adapter. Seam only — OTA-702 owns
        the full contract.
    """
    result = PipelineResult(
        candidate_id=candidate.candidate_id,
        candidate_type=candidate.candidate_type,
    )

    # Partition bindings by phase
    gate_bindings: list[RuleBinding] = []
    scoring_bindings: list[RuleBinding] = []
    adjustment_bindings: list[RuleBinding] = []

    for binding in rule_set.bindings:
        if not binding.junction.enabled:
            continue
        phase = binding.rule.phase
        if phase == Phase.GATE:
            gate_bindings.append(binding)
        elif phase == Phase.SCORING:
            scoring_bindings.append(binding)
        elif phase == Phase.ADJUSTMENT:
            adjustment_bindings.append(binding)

    # ── Phases 1–3: Gates (RAW → DERIVED → [callback] → COMPUTED) ────
    held_penalties: list[float] = []
    halted = _run_gates(
        candidate, gate_bindings, registry, adapter, result, held_penalties
    )
    if halted:
        return result

    # ── Phase 4: Scoring (weighted sum) ──────────────────────────────
    raw_score = _run_scoring(candidate, scoring_bindings, registry, result)
    result.raw_score = raw_score

    # ── Phase 5: Apply held gate penalties ───────────────────────────
    score = raw_score
    total_penalty = sum(held_penalties)
    if total_penalty != 0:
        score -= total_penalty
        score = max(0.0, min(100.0, score))
    result.held_penalties_applied = total_penalty if total_penalty != 0 else None

    # ── Phase 6: Adjustments ─────────────────────────────────────────
    score = _run_adjustments(candidate, adjustment_bindings, registry, result, score)
    result.final_score = score

    # ── Phase 7: Verdict band lookup ─────────────────────────────────
    verdict = _lookup_verdict_band(score, rule_set.strategy.verdict_band_set)
    result.verdict = verdict
    result.verdict_source = VerdictSource.BAND_LOOKUP
    result.terminal_phase = "verdict"

    return result


# ── Gate execution (Phases 1–3) ─────────────────────────────────────────


def _run_gates(
    candidate: Candidate,
    gate_bindings: list[RuleBinding],
    registry: FormulaRegistry,
    adapter: ComputedAdapter | None,
    result: PipelineResult,
    held_penalties: list[float],
) -> bool:
    """Run gate phases. Returns True if candidate was halted."""
    callback_fired = False

    for binding in gate_bindings:
        tier = binding.rule.tier

        # COMPUTED callback seam: fire once between DERIVED and COMPUTED
        if (
            not callback_fired
            and tier == Tier.COMPUTED
            and adapter is not None
        ):
            callback_fired = True
            needed = _collect_needed_computed_names(gate_bindings, binding)
            adapter.populate_computed([candidate], needed)

        # Evaluate the gate
        passed = _evaluate_rule(candidate, binding, registry)

        decision = GateDecision(
            rule_key=binding.rule.rule_key,
            phase=binding.rule.phase,
            tier=tier,
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


def _collect_needed_computed_names(
    gate_bindings: list[RuleBinding],
    from_binding: RuleBinding,
) -> set[str]:
    """Collect COMPUTED named values needed by remaining rules."""
    needed: set[str] = set()
    found = False
    for binding in gate_bindings:
        if binding is from_binding:
            found = True
        if found and binding.rule.tier == Tier.COMPUTED:
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
