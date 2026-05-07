"""
Hard-gate scaffolding for the trade evaluation pipeline.

Hard gates are pre-scoring filters that run before any Claude API call or
scoring math. A gate can either:

  1. Hard-block a trade (triggered=True, verdict="PASS") — the pipeline
     short-circuits immediately and returns PASS without calling Claude.

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

logger = logging.getLogger(__name__)


# ─── Trade context ────────────────────────────────────────────────────────────


@dataclass
class GateTradeContext:
    """
    Lightweight snapshot of a trade passed to every gate.

    Decouples gate logic from the route's StructuredEvaluationRequest schema
    so gates remain portable and independently testable.
    """
    symbol: str
    entry_date: date                  # date.today() at evaluation time
    expiry_date: Optional[date]       # parsed from trade["expiration"]; None if missing/unparseable
    dte: int                          # already computed by evaluate_structured()
    trade: Optional[dict] = None      # raw trade dict for gate-specific field access
    db: Optional[Any] = None          # AsyncSession from the request; gates use for ContextStore reads
    expected_value: Optional[float] = None  # pre-computed EV in dollars; required by NegativeEVGate, populated from scoring pipeline's total_ev


# ─── Gate result ──────────────────────────────────────────────────────────────


@dataclass
class GateResult:
    """
    Result returned by a single gate's evaluate() call.

    triggered=True  → hard-block: pipeline short-circuits, verdict forced to
                       the value in `verdict` (typically "PASS" or "WAIT_FOR_EARNINGS").
    triggered=False → pass-through: pipeline continues, but may apply
                       penalty_points and/or effective_dte_override.
    """
    triggered: bool
    verdict: Optional[str] = None               # "PASS" or "WAIT_FOR_EARNINGS" when triggered
    reason: Optional[str] = None                # human-readable explanation
    penalty_points: int = 0                     # deducted from score post-parse
    effective_dte_override: Optional[int] = None  # replaces nominal DTE for scoring
    gate_id: str = ""                           # for audit trail
    # OTA-515: earnings routing metadata (only set by EarningsInWindowGate)
    _dte_after_earnings: Optional[int] = None
    _reevaluate_on: Optional[str] = None        # mm-dd-yyyy


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
      - The first GateResult with triggered=True (short-circuits immediately).
      - The last GateResult with non-zero modifiers if no gate triggered hard.
      - None if no gates are registered or no gate produced any output.

    Never raises. Individual gate failures are logged and skipped.
    """
    last_modifier: Optional[GateResult] = None

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
            logger.info(
                f"Hard gate triggered: gate={gate.gate_id} symbol={ctx.symbol} "
                f"verdict={result.verdict} reason={result.reason!r:.80}"
            )
            return result

        if result.penalty_points or result.effective_dte_override is not None:
            logger.info(
                f"Hard gate modifier: gate={gate.gate_id} symbol={ctx.symbol} "
                f"penalty={result.penalty_points} "
                f"effective_dte={result.effective_dte_override}"
            )
            last_modifier = result

    return last_modifier
