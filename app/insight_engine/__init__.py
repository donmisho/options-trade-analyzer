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
    Single public entry point for running the pipeline (OTA-701).

Extension points (added by downstream Stories)
----------------------------------------------
- Dataclass exports (OTA-697)
- Config loader (OTA-698)
- Startup validation (OTA-699)
- Expression library (OTA-700)
- Pipeline orchestrator (OTA-701) — SHIPPED
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
    config,
    registry=None,
    adapter=None,
    sink=None,
):
    """Run the engine pipeline on a stream of candidates.

    Parameters
    ----------
    candidates : iterable
        Stream of Candidate records produced by the consumer's input adapter.
    strategy_key : str
        The strategy to evaluate against (looked up from engine_strategies).
    source_app_id : str
        Consuming application identifier (e.g. 'OTA', 'STK', 'FFL').
        Stamped on every emitted record.
    config : EngineConfig
        Loaded and validated engine configuration.
    registry : FormulaRegistry, optional
        Live formula registry. Uses StubFormulaRegistry if not provided.
    adapter : ComputedAdapter, optional
        COMPUTED-value callback adapter (OTA-702 seam).
    sink : optional
        Persistence sink (OTA-705 seam).

    Returns
    -------
    list[PipelineResult]
        Per-candidate pipeline results.

    Raises
    ------
    KeyError
        If strategy_key is not in the loaded config.
    """
    from app.insight_engine.pipeline import run_pipeline as _run_pipeline
    from app.insight_engine.registry import StubFormulaRegistry as _Stub

    reg = registry or _Stub()
    rule_set = config.rule_sets[strategy_key]

    results = []
    for candidate in candidates:
        result = _run_pipeline(candidate, rule_set, reg, adapter)
        results.append(result)

    return results


# ── Config loader exports (OTA-698) ──────────────────────────────────────
from app.insight_engine.config_source import (  # noqa: E402
    ConfigSource,
    InMemoryConfigSource,
)
from app.insight_engine.loader import (  # noqa: E402
    EngineConfig,
    LookupEntry,
    load_config,
)

# ── Formula registry (OTA-699, OTA-700) ──────────────────────────────────
from app.insight_engine.registry import (  # noqa: E402
    DictFormulaRegistry,
    FormulaFn,
    FormulaRegistry,
    StubFormulaRegistry,
)

# ── Expression library (OTA-700) ─────────────────────────────────────────
from app.insight_engine.expressions import (  # noqa: E402
    SUPPORTED_EXPRESSIONS,
    UnsupportedExpressionError,
    evaluate_expression,
    extract_formula_name,
    invoke_formula,
    is_formula_ref,
    validate_expression,
)

# ── Pipeline orchestrator (OTA-701) ──────────────────────────────────────
from app.insight_engine.pipeline import (  # noqa: E402
    ComputedAdapter,
    PipelineResult,
    run_pipeline,
)

# ── Startup validation (OTA-699) ─────────────────────────────────────────
from app.insight_engine.validation import (  # noqa: E402
    ConfigValidationError,
    ValidationError,
    ValidationReport,
    validate_and_raise,
    validate_config,
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
    # Config loader (OTA-698)
    "ConfigSource",
    "InMemoryConfigSource",
    "EngineConfig",
    "LookupEntry",
    "load_config",
    # Formula registry (OTA-699, OTA-700)
    "FormulaFn",
    "FormulaRegistry",
    "StubFormulaRegistry",
    "DictFormulaRegistry",
    # Pipeline orchestrator (OTA-701)
    "ComputedAdapter",
    "PipelineResult",
    "run_pipeline",
    # Expression library (OTA-700)
    "SUPPORTED_EXPRESSIONS",
    "UnsupportedExpressionError",
    "evaluate_expression",
    "extract_formula_name",
    "invoke_formula",
    "is_formula_ref",
    "validate_expression",
    # Startup validation (OTA-699)
    "ConfigValidationError",
    "ValidationError",
    "ValidationReport",
    "validate_and_raise",
    "validate_config",
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
