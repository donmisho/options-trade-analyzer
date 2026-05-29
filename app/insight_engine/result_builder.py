"""
Result-record builder — assembles the full ResultRecord from pipeline output.

Takes the orchestrator's accumulated PipelineResult and stamps provenance
(source_app_id, strategy_key, engine_version, config_version, run_timestamp)
to produce the mandatory full per-rule trace (insight_engine.md §4.2).

Every candidate produces a ResultRecord, whether halted at a gate or
completed through verdict band lookup. The verdict_source discriminator
records which of the three paths produced the verdict:

    BAND_LOOKUP              — completed scoring + adjustments; verdict from bands
    HALT_TERMINAL_VERDICT    — stopping gate failed; verdict from junction column
    HALT_NO_VERDICT          — stopping gate failed; no terminal_verdict configured

OTA-703
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.insight_engine.models import ResultRecord, VerdictSource
from app.insight_engine.pipeline import PipelineResult

ENGINE_VERSION = "1.0.0"


def build_result_record(
    pipeline_result: PipelineResult,
    *,
    source_app_id: str,
    strategy_key: str,
    config_version: str,
    engine_version: str = ENGINE_VERSION,
    run_timestamp: datetime | None = None,
) -> ResultRecord:
    """Assemble a ResultRecord from a PipelineResult with provenance.

    Parameters
    ----------
    pipeline_result : PipelineResult
        The orchestrator's accumulated trace for one candidate.
    source_app_id : str
        Consuming application identifier (e.g. 'OTA').
    strategy_key : str
        The strategy evaluated against.
    config_version : str
        Deterministic hash of the loaded configuration.
    engine_version : str
        Engine version string. Defaults to ENGINE_VERSION.
    run_timestamp : datetime | None
        Evaluation timestamp. Defaults to current UTC time.
    """
    ts = run_timestamp or datetime.now(timezone.utc)

    return ResultRecord(
        candidate_id=pipeline_result.candidate_id,
        candidate_type=pipeline_result.candidate_type,
        source_app_id=source_app_id,
        strategy_key=strategy_key,
        terminal_phase=pipeline_result.terminal_phase,
        gate_decisions=pipeline_result.gate_decisions,
        scoring_breakdown=pipeline_result.scoring_breakdown,
        raw_score=pipeline_result.raw_score,
        held_penalties_applied=pipeline_result.held_penalties_applied,
        adjustment_results=pipeline_result.adjustment_results,
        final_score=pipeline_result.final_score,
        verdict=pipeline_result.verdict,
        verdict_source=pipeline_result.verdict_source,
        engine_version=engine_version,
        config_version=config_version,
        run_timestamp=ts,
    )


def build_result_records(
    pipeline_results: list[PipelineResult],
    *,
    source_app_id: str,
    strategy_key: str,
    config_version: str,
    engine_version: str = ENGINE_VERSION,
    run_timestamp: datetime | None = None,
) -> list[ResultRecord]:
    """Assemble ResultRecords for a batch of PipelineResults.

    All records in a batch share the same provenance (source_app_id,
    strategy_key, config_version, engine_version, run_timestamp).
    """
    ts = run_timestamp or datetime.now(timezone.utc)

    return [
        build_result_record(
            pr,
            source_app_id=source_app_id,
            strategy_key=strategy_key,
            config_version=config_version,
            engine_version=engine_version,
            run_timestamp=ts,
        )
        for pr in pipeline_results
    ]
