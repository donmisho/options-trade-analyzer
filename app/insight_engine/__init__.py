"""
Insight Engine — generic evaluation framework.

The engine takes a stream of candidates and a strategy, runs them through a
deterministic pipeline (gates → scoring → adjustments → verdict), and emits
per-candidate result records with a full per-rule decision trace.

The engine has no built-in knowledge of any domain. It does not know what a
delta is, what a credit spread is, or what IV rank means. Domain terms appear
only in (a) rule formula implementations registered with the engine, and
(b) the consumer-specific input adapter.

See ``insight_engine.md`` for the full specification.

Public API
----------
evaluate(...)
    Single public entry point for running the pipeline. Stub — implemented
    in OTA-701 (pipeline orchestrator).

Extension points (added by downstream Stories)
----------------------------------------------
- Dataclass exports (OTA-697)
- Config loader (OTA-698)
- Startup validation (OTA-699)
- Expression library (OTA-700)
- Pipeline orchestrator (OTA-701)
- COMPUTED callback (OTA-702)
- Result-record builder (OTA-703)
- Bronze record contract (OTA-704)
- Persistence sink interface (OTA-705)
- source_app_id enforcement (OTA-706)
"""

from app.insight_engine._guard import enforce_domain_boundary

# Run the domain-decoupling guard at import time (insight_engine.md §2.5).
# Raises EngineDomainLeakError if any module in this package imports a
# forbidden domain package, LLM client, or DB driver.
enforce_domain_boundary()


def evaluate(
    *,
    candidates,
    strategy_key: str,
    source_app_id: str,
    adapter,
    sink,
):
    """Run the engine pipeline on a stream of candidates.

    Parameters
    ----------
    candidates : iterable
        Stream of candidate records produced by the consumer's input adapter.
    strategy_key : str
        The strategy to evaluate against (looked up from engine_strategies).
    source_app_id : str
        Consuming application identifier (e.g. 'OTA', 'STK', 'FFL').
        Stamped on every emitted record.
    adapter
        Consumer-specific input adapter implementing the §5 contract.
    sink
        Persistence sink implementing write_snapshots / write_decisions.

    Returns
    -------
    list
        Per-candidate result records.

    Raises
    ------
    NotImplementedError
        Until OTA-701 (pipeline orchestrator) ships.
    """
    raise NotImplementedError(
        "evaluate() is a stub. Implementation arrives with OTA-701 "
        "(pipeline orchestrator)."
    )


# ── Dataclass and enum exports (OTA-697) ─────────────────────────────────
from app.insight_engine.models import (  # noqa: E402
    Tier,
    Phase,
    VerdictSource,
    NamedValue,
    Rule,
    Strategy,
    JunctionRow,
    RuleBinding,
    RuleSet,
    Candidate,
    GateDecision,
    ScoringBreakdown,
    AdjustmentResult,
    ResultRecord,
    CandidateSnapshot,
    EvaluationDecision,
)

__all__ = [
    "evaluate",
    # Enums
    "Tier",
    "Phase",
    "VerdictSource",
    # Config dataclasses
    "NamedValue",
    "Rule",
    "Strategy",
    "JunctionRow",
    "RuleBinding",
    "RuleSet",
    # Candidate
    "Candidate",
    # Result dataclasses
    "GateDecision",
    "ScoringBreakdown",
    "AdjustmentResult",
    "ResultRecord",
    "CandidateSnapshot",
    "EvaluationDecision",
]
