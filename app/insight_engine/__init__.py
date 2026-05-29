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
- COMPUTED callback (OTA-702) — SHIPPED
- Result-record builder (OTA-703) — SHIPPED
- Bronze record contract (OTA-704) — SHIPPED
- Persistence sink interface (OTA-705) — SHIPPED
- source_app_id enforcement (OTA-706) — SHIPPED
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
        COMPUTED-value callback adapter (OTA-702).
    sink : PersistenceSink, optional
        Persistence sink (OTA-705). When provided, the engine drives it
        after each run with the bronze record streams.

    Returns
    -------
    list[ResultRecord]
        Per-candidate result records with full per-rule trace and provenance.

    Raises
    ------
    ValueError
        If source_app_id is missing or empty.
    KeyError
        If strategy_key is not in the loaded config.
    """
    if not source_app_id or not isinstance(source_app_id, str) or not source_app_id.strip():
        raise ValueError(
            "source_app_id is required and must be a non-empty string "
            "(e.g. 'OTA', 'FFL', 'STK'). The engine does not provide a default."
        )

    from app.insight_engine.bronze_contract import build_bronze_batch as _bronze
    from app.insight_engine.pipeline import run_batch as _run_batch
    from app.insight_engine.registry import StubFormulaRegistry as _Stub
    from app.insight_engine.result_builder import build_result_records as _build

    reg = registry or _Stub()
    candidate_list = list(candidates)
    rule_set = config.rule_sets[strategy_key]

    pipeline_results = _run_batch(candidate_list, rule_set, reg, adapter)

    result_records = _build(
        pipeline_results,
        source_app_id=source_app_id,
        strategy_key=strategy_key,
        config_version=config.config_version,
    )

    # Drive the injected sink with bronze record streams (OTA-705)
    if sink is not None:
        snapshots, decisions = _bronze(
            result_records, candidate_list, run_id=None,
        )
        sink.write_snapshots(snapshots)
        sink.write_decisions(decisions)

    return result_records


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
    run_batch,
    run_pipeline,
)

# ── Result-record builder (OTA-703) ──────────────────────────────────────
from app.insight_engine.result_builder import (  # noqa: E402
    ENGINE_VERSION,
    build_result_record,
    build_result_records,
)

# ── Bronze record contract (OTA-704) ────────────────────────────────────
from app.insight_engine.bronze_contract import (  # noqa: E402
    DECISION_PAYLOAD_VERSION,
    SNAPSHOT_PAYLOAD_VERSION,
    build_bronze_batch,
    build_bronze_streams,
)

# ── Persistence sink (OTA-705) ───────────────────────────────────────────
from app.insight_engine.sink import (  # noqa: E402
    InMemorySink,
    PersistenceSink,
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
    "run_batch",
    "run_pipeline",
    # Result-record builder (OTA-703)
    "ENGINE_VERSION",
    "build_result_record",
    "build_result_records",
    # Bronze record contract (OTA-704)
    "SNAPSHOT_PAYLOAD_VERSION",
    "DECISION_PAYLOAD_VERSION",
    "build_bronze_streams",
    "build_bronze_batch",
    # Persistence sink (OTA-705)
    "PersistenceSink",
    "InMemorySink",
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
