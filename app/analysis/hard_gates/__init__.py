"""
Hard-gate scaffolding for the trade evaluation pipeline.

Hard gates are pre-scoring filters that run before any Claude API call or
scoring math. A gate can either:

  1. Hard-block a trade (triggered=True, action=BLOCK/DEFER) — the pipeline
     short-circuits immediately. The domain layer maps the action code to
     its own verdict string.

  2. Inject scoring modifiers without blocking (triggered=False with
     penalty_points and/or effective_dte_override set) — the pipeline
     applies the modifiers after Claude returns its score.

Registration:
    Call register_gate(gate) once at app startup (app/main.py lifespan).
    Gates are evaluated in registration order. First triggered gate wins.

Extending:
    1. Create a new file under app/analysis/hard_gates/
    2. Subclass HardGate and implement evaluate()
    3. Register in app/main.py

OTA-502 — EarningsInWindowGate (earnings_gate.py)
OTA-503 — NegativeEVGate will follow the same pattern
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any, List, Optional

from app.insight_engine.models import Candidate

logger = logging.getLogger(__name__)


# ─── Trade context ────────────────────────────────────────────────────────────


@dataclass
class GateTradeContext:
    """
    Lightweight snapshot of a trade passed to every gate.

    Decouples gate logic from the route's StructuredEvaluationRequest schema
    so gates remain portable and independently testable.

    OTA-775: Domain-specific fields (expected_value, expiry_date, dte) removed.
    Gates access those values through the generic `candidate` reference, keyed
    by named value (e.g. candidate.named_values["expected_value"]).
    """
    symbol: str
    entry_date: date                  # date.today() at evaluation time
    candidate: Optional[Candidate] = None  # generic candidate; gates read named values by key
    trade: Optional[dict] = None      # raw trade dict for gate-specific field access
    db: Optional[Any] = None          # AsyncSession from the request; gates use for ContextStore reads


# ─── Gate result ──────────────────────────────────────────────────────────────


# OTA-776: Generic action codes — the framework knows no domain verdict strings.
# The consuming domain layer maps action codes to its own verdict vocabulary.
ACTION_BLOCK = "BLOCK"    # hard-block: pipeline short-circuits, candidate rejected
ACTION_DEFER = "DEFER"    # terminal halt: candidate deferred (e.g. wait for catalyst)
ACTION_MODIFY = "MODIFY"  # pass-through with modifiers (penalty, DTE override)
ACTION_OK = "OK"          # gate passed, no effect


@dataclass
class GateResult:
    """
    Result returned by a single gate's evaluate() call.

    triggered=True  → hard-block or defer: pipeline short-circuits.
                       `action` is BLOCK or DEFER.
    triggered=False → pass-through: pipeline continues, but may apply
                       penalty_points and/or effective_dte_override.
                       `action` is MODIFY (with modifiers) or OK.

    OTA-776: `action` replaces the former `verdict` field. Action codes are
    generic (BLOCK/DEFER/MODIFY/OK); domain verdict strings are mapped by
    the consuming domain layer.

    OTA-777: Gate-specific metadata (e.g. dte_after_earnings, reevaluate_on)
    lives in the generic `metadata` dict, not as named fields on GateResult.
    """
    triggered: bool
    action: Optional[str] = None                # BLOCK | DEFER | MODIFY | OK
    reason: Optional[str] = None                # human-readable explanation
    penalty_points: int = 0                     # deducted from score post-parse
    effective_dte_override: Optional[int] = None  # replaces nominal DTE for scoring
    gate_id: str = ""                           # for audit trail
    metadata: dict = field(default_factory=dict)  # gate-specific data (OTA-777)


# ─── Abstract gate ────────────────────────────────────────────────────────────


class HardGate(ABC):
    """
    Abstract base class for all hard gates.

    Subclasses must define the class-level `gate_id` string and implement
    the async `evaluate()` method. Gates must be stateless per evaluation —
    any I/O (DB reads, cache lookups) should be performed inside evaluate()
    using injected dependencies stored as instance attributes.
    """

    gate_id: str

    @abstractmethod
    async def evaluate(self, ctx: GateTradeContext) -> GateResult:
        """
        Evaluate the gate against the trade context.

        Must never raise — return GateResult(triggered=False) on any
        unexpected error to keep the pipeline fail-soft.
        """
        ...


# ─── Registry ─────────────────────────────────────────────────────────────────


_registered_gates: List[HardGate] = []


def register_gate(gate: HardGate) -> None:
    """
    Register a gate. Call once per gate at app startup.

    Gates are evaluated in registration order. Register forced-verdict
    (hard-block) gates before modifier-only gates so they short-circuit
    early and avoid unnecessary I/O in later gates.
    """
    _registered_gates.append(gate)
    logger.info(f"Hard gate registered: {gate.gate_id}")


def _clear_gates() -> None:
    """Remove all registered gates. For use in tests only."""
    _registered_gates.clear()


async def evaluate_hard_gates(ctx: GateTradeContext) -> Optional[GateResult]:
    """
    Run all registered gates in order.

    Returns:
      - The first GateResult with triggered=True (short-circuits immediately,
        carrying forward accumulated penalties from prior modifiers).
      - A merged GateResult if one or more non-triggered modifiers fired.
      - None if no gates are registered or no gate produced any output.

    DTE override propagation: when a gate sets effective_dte_override, the
    candidate's named_values["dte"] is updated so downstream gates see the
    modified DTE value.

    Penalty accumulation: penalties from multiple non-triggered gates stack
    additively. OTA-780.

    Never raises. Individual gate failures are logged and skipped.
    """
    modifiers: List[GateResult] = []

    for gate in _registered_gates:
        try:
            result = await gate.evaluate(ctx)
        except Exception as exc:
            logger.error(
                f"Hard gate {gate.gate_id!r} raised unexpectedly for "
                f"{ctx.symbol}: {exc}. Skipping gate (fail-soft).",
                exc_info=True,
            )
            continue

        if result.triggered:
            # Carry forward accumulated penalties from prior modifiers
            for mod in modifiers:
                result.penalty_points += mod.penalty_points
            logger.info(
                f"Hard gate triggered: gate={gate.gate_id} symbol={ctx.symbol} "
                f"action={result.action} reason={result.reason!r:.80}"
            )
            return result

        # Propagate DTE override to candidate for downstream gates
        if result.effective_dte_override is not None:
            if ctx.candidate and ctx.candidate.named_values is not None:
                ctx.candidate.named_values["dte"] = result.effective_dte_override

        if result.penalty_points or result.effective_dte_override is not None or result.metadata:
            logger.info(
                f"Hard gate modifier: gate={gate.gate_id} symbol={ctx.symbol} "
                f"penalty={result.penalty_points} "
                f"effective_dte={result.effective_dte_override}"
            )
            modifiers.append(result)

    if not modifiers:
        return None

    if len(modifiers) == 1:
        return modifiers[0]

    # Merge multiple modifiers
    total_penalty = sum(m.penalty_points for m in modifiers)
    dte_override = next(
        (m.effective_dte_override for m in modifiers
         if m.effective_dte_override is not None),
        None,
    )
    merged_metadata: dict = {}
    reasons: List[str] = []
    for m in modifiers:
        merged_metadata.update(m.metadata)
        if m.reason:
            reasons.append(m.reason)

    return GateResult(
        triggered=False,
        penalty_points=total_penalty,
        effective_dte_override=dte_override,
        reason="; ".join(reasons),
        gate_id=modifiers[-1].gate_id,
        metadata=merged_metadata,
    )
