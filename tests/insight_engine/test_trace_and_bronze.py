"""
OTA-798 — Full per-rule trace + bronze persistence assertions.

Second of the OTA-794 validation set (OTA-795 → OTA-798 → OTA-797). Reuses the
OTA-795 seeded-config + candidate fixtures (``cross_consumer_harness``); it does
NOT re-seed.

Two things are proven:

1. **Trace completeness** (in-memory sink / result-record inspection) — every rule
   evaluation in a run appears in the result-record trace, *including* a
   non-stopping gate failure and zero-penalty (record-only) decisions. Without the
   full trace the engine is unauditable against the tables (insight_engine.md §4.2).

2. **Persisted bronze shape** (the real OTA-758 ``BronzeSqlSink``) — records land in
   the single ``dbo.bronze_evaluations`` table discriminated by ``record_type``,
   with a ``dbo.bronze_payload_contract`` entry per
   ``(record_type, discriminator_value, payload_version)``, provenance stamped on
   every record, and snapshot↔decision correlation by shared ``snapshot_id`` /
   ``run_id`` (no FKs). This asserts conformance to ``insight_engine-schema-ddl.md``
   §3 (the authoritative SINGLE-table physical shape), NOT the two-table §4.3 sketch.

Offline read-back (Azure SQL is unreachable from dev and the sink emits T-SQL):
the real ``BronzeSqlSink`` is driven with a capturing fake ``session_factory`` on a
background event loop, waited on deterministically via a ``commit``-released
semaphore. The sink itself is unchanged — only its physical store is captured.

The fixture exercising the non-stopping/zero-penalty clauses is the directional
budget-overrun candidate (``fits_budget`` False → non-stopping ``dir_budget_flag``
gate fails but the candidate continues to a verdict). See
``cross_consumer_harness.directional_nonstopping_failure_candidate``.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Any

import pytest

from app.insight_engine import Phase, evaluate
from app.insight_engine.bronze_contract import (
    DECISION_PAYLOAD_VERSION,
    SNAPSHOT_PAYLOAD_VERSION,
)
from app.ota_adapters.engine_runtime import BronzeSqlSink

from tests.insight_engine import cross_consumer_harness as harness

pytestmark = pytest.mark.skipif(
    not harness.SEED_WORKBOOK_AVAILABLE,
    reason="seed workbook not available; bronze/trace suite needs the seeded config",
)

# Hydrate the complete seed + registry once for the module (guarded by the skip).
_CONFIG = harness.build_seeded_config() if harness.SEED_WORKBOOK_AVAILABLE else None
_REGISTRY = harness.get_combined_registry() if harness.SEED_WORKBOOK_AVAILABLE else None

# The directional surface owns the non-stopping fixture (the one seeded
# non-stopping gate that we can deterministically trip and still reach a verdict).
_DIR = next(c for c in harness.SURFACE_CASES if c.surface == "DIRECTIONAL")
# Position-health adds a DECISION/adjustment phase, so it covers the adjustment
# contract entry the directional run does not produce.
_PH = next(c for c in harness.SURFACE_CASES if c.surface == "POSITION_HEALTH")


def _phase_bindings(strategy_key, phase):
    return [b for b in _CONFIG.rule_sets[strategy_key].bindings if b.rule.phase is phase]


def _evaluate(strategy_key, candidate, null_semantics, *, sink=None, adapter=None):
    return evaluate(
        candidates=[candidate],
        strategy_key=strategy_key,
        source_app_id=harness.SOURCE_APP_ID,
        config=_CONFIG,
        registry=_REGISTRY,
        adapter=adapter,
        sink=sink,
        null_semantics=null_semantics,
    )[0]


# ── 1. Trace completeness (in-memory sink / result record) ────────────────


class TestTraceCompleteness:
    """Every rule evaluation appears in the trace, including non-stopping failures
    and zero-penalty decisions."""

    def _run(self):
        from app.insight_engine import InMemorySink
        sink = InMemorySink()
        candidate = harness.directional_nonstopping_failure_candidate()
        record = _evaluate(
            _DIR.strategy_key, candidate, _DIR.null_semantics,
            sink=sink, adapter=_DIR.make_adapter(),
        )
        return record, sink, candidate

    def test_reaches_verdict_so_the_full_trace_exists(self):
        record, _sink, _c = self._run()
        # A non-stopping failure must NOT halt the candidate — the whole pipeline
        # runs, so the trace is complete (gates + scoring + verdict).
        assert record.terminal_phase == "verdict"
        assert record.verdict is not None

    def test_non_stopping_gate_failure_is_recorded(self):
        record, _sink, _c = self._run()
        non_stopping = [
            g for g in record.gate_decisions
            if not g.passed and not g.skipped and not g.stop_if_fail
        ]
        assert non_stopping, "expected at least one non-stopping gate failure"
        flag = next(
            g for g in non_stopping
            if g.rule_key == harness.DIRECTIONAL_NONSTOPPING_GATE
        )
        # Recorded, not terminal: the candidate kept going.
        assert flag.passed is False
        assert flag.was_terminal is False
        assert flag.stop_if_fail is False

    def test_zero_penalty_decision_is_recorded(self):
        """A record-only failure (zero/None penalty) is still in the trace."""
        record, _sink, _c = self._run()
        zero_penalty = [
            g for g in record.gate_decisions
            if not g.passed and not g.skipped and not g.stop_if_fail
            and not g.held_penalty  # None or 0 → record-only, no score reduction
        ]
        assert zero_penalty, "expected at least one zero-penalty (record-only) decision"

    def test_every_rule_evaluation_appears_in_the_trace(self):
        """The trace holds exactly one entry per enabled binding in each phase."""
        record, sink, _c = self._run()
        gate_n = len(_phase_bindings(_DIR.strategy_key, Phase.GATE))
        scoring_n = len(_phase_bindings(_DIR.strategy_key, Phase.SCORING))
        adjustment_n = len(_phase_bindings(_DIR.strategy_key, Phase.ADJUSTMENT))

        assert len(record.gate_decisions) == gate_n
        assert len(record.scoring_breakdown) == scoring_n
        assert len(record.adjustment_results) == adjustment_n

        # The in-memory sink received one snapshot and one decision per evaluation.
        assert len(sink.snapshots) == 1
        assert len(sink.decisions) == gate_n + scoring_n + adjustment_n

    def test_decisions_carry_provenance_and_correlation(self):
        record, sink, _c = self._run()
        snap = sink.snapshots[0]
        assert snap.source_app_id == harness.SOURCE_APP_ID
        assert snap.config_version
        assert snap.evaluated_at is not None
        # Every decision shares the snapshot's id + run id (bronze has no FKs).
        assert sink.decisions, "expected decision records"
        for d in sink.decisions:
            assert d.snapshot_id == snap.snapshot_id
            assert d.run_id == snap.run_id
            assert d.source_app_id == harness.SOURCE_APP_ID
            assert d.config_version == snap.config_version


# ── 2. Persisted bronze shape (the real OTA-758 sink, captured offline) ────


@dataclass
class _Captured:
    """One captured DB statement: the SQL text and its bound parameters."""
    sql: str
    params: Any


class _FakeSession:
    """Async session stand-in that records statements instead of hitting a DB."""

    def __init__(self, calls: list[_Captured], on_commit: threading.Semaphore) -> None:
        self._calls = calls
        self._on_commit = on_commit

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def execute(self, statement: Any, params: Any = None) -> None:
        self._calls.append(_Captured(str(statement), params))

    async def commit(self) -> None:
        # Released after the inserts for one write() call → deterministic wait.
        self._on_commit.release()


class _CapturingSessionFactory:
    """Hands out recording sessions; collects every statement across writes."""

    def __init__(self) -> None:
        self.calls: list[_Captured] = []
        self.commits = threading.Semaphore(0)

    def __call__(self) -> _FakeSession:
        return _FakeSession(self.calls, self.commits)


@dataclass
class _BronzeWrite:
    """Parsed capture of one real-sink run: the evaluation rows + contract rows."""
    snapshot_rows: list[dict]
    decision_rows: list[dict]
    contracts: list[dict]


def _run_through_real_sink(case, candidate, *, expected_commits: int = 2) -> _BronzeWrite:
    """Drive the REAL BronzeSqlSink offline and return the captured bronze rows.

    A background event loop hosts the sink's fire-and-forget coroutines; the
    capturing session releases a semaphore per ``commit`` so we wait on exactly
    ``expected_commits`` (one per write_snapshots / write_decisions) with no sleeps.
    """
    loop = asyncio.new_event_loop()
    thread = threading.Thread(
        target=lambda: (asyncio.set_event_loop(loop), loop.run_forever()),
        daemon=True,
    )
    thread.start()
    try:
        factory = _CapturingSessionFactory()
        sink = BronzeSqlSink(session_factory=factory, loop=loop)
        _evaluate(
            case.strategy_key, candidate, case.null_semantics,
            sink=sink, adapter=case.make_adapter(),
        )
        for _ in range(expected_commits):
            assert factory.commits.acquire(timeout=10), "bronze write did not complete"
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)

    snapshot_rows: list[dict] = []
    decision_rows: list[dict] = []
    contracts: list[dict] = []
    for call in factory.calls:
        if "bronze_evaluations" in call.sql:
            for row in call.params:  # executemany: params is a list of row dicts
                (snapshot_rows if row["record_type"] == "SNAPSHOT" else decision_rows).append(row)
        elif "bronze_payload_contract" in call.sql:
            contracts.append(call.params)
    return _BronzeWrite(snapshot_rows, decision_rows, contracts)


class TestPersistedBronzeShape:
    """The real OTA-758 sink lands schema-ddl §3 single-table bronze records."""

    def test_lands_single_table_discriminated_by_record_type(self):
        write = _run_through_real_sink(
            _DIR, harness.directional_nonstopping_failure_candidate()
        )
        # One SNAPSHOT per candidate; one DECISION per rule evaluation.
        assert len(write.snapshot_rows) == 1
        gate_n = len(_phase_bindings(_DIR.strategy_key, Phase.GATE))
        scoring_n = len(_phase_bindings(_DIR.strategy_key, Phase.SCORING))
        adjustment_n = len(_phase_bindings(_DIR.strategy_key, Phase.ADJUSTMENT))
        assert len(write.decision_rows) == gate_n + scoring_n + adjustment_n
        # record_type is the single-table discriminator (schema-ddl §3).
        assert {r["record_type"] for r in write.snapshot_rows} == {"SNAPSHOT"}
        assert {r["record_type"] for r in write.decision_rows} == {"DECISION"}

    def test_contract_entry_per_record_type_discriminator_version(self):
        write = _run_through_real_sink(
            _DIR, harness.directional_nonstopping_failure_candidate()
        )
        # Every (record_type, discriminator_value, payload_version) actually written
        # must have a matching bronze_payload_contract registration — and nothing
        # extra. Discriminator = candidate_type (SNAPSHOT) / phase (DECISION).
        written_combos = {
            (r["record_type"], r["candidate_type"], r["payload_version"])
            for r in write.snapshot_rows
        } | {
            (r["record_type"], r["phase"], r["payload_version"])
            for r in write.decision_rows
        }
        contract_combos = {
            (c["record_type"], c["discriminator_value"], c["payload_version"])
            for c in write.contracts
        }
        assert contract_combos == written_combos
        # Payload versions match the engine contract constants.
        for r in write.snapshot_rows:
            assert r["payload_version"] == SNAPSHOT_PAYLOAD_VERSION
        for r in write.decision_rows:
            assert r["payload_version"] == DECISION_PAYLOAD_VERSION

    def test_provenance_stamped_on_every_record(self):
        write = _run_through_real_sink(
            _DIR, harness.directional_nonstopping_failure_candidate()
        )
        for row in write.snapshot_rows + write.decision_rows:
            assert row["source_app_id"] == harness.SOURCE_APP_ID
            assert row["config_version"]
            assert row["evaluated_at"] is not None

    def test_snapshot_decision_correlation_by_shared_id(self):
        write = _run_through_real_sink(
            _DIR, harness.directional_nonstopping_failure_candidate()
        )
        snap = write.snapshot_rows[0]
        assert write.decision_rows  # the run produced decisions
        for d in write.decision_rows:
            assert d["snapshot_id"] == snap["snapshot_id"]
            assert d["run_id"] == snap["run_id"]
        # SNAPSHOT-only columns are NULL on DECISION rows and vice versa.
        assert all(d["candidate_type"] is None for d in write.decision_rows)
        assert all(s["rule_key"] is None for s in write.snapshot_rows)

    def test_adjustment_phase_contract_is_registered(self):
        """A surface WITH adjustments registers a DECISION/adjustment contract too
        (directional has none; position-health does)."""
        write = _run_through_real_sink(
            _PH, harness.position_health_passing_candidate()
        )
        decision_phases = {r["phase"] for r in write.decision_rows}
        assert "adjustment" in decision_phases
        contract_combos = {
            (c["record_type"], c["discriminator_value"]) for c in write.contracts
        }
        assert ("DECISION", "adjustment") in contract_combos
        assert ("DECISION", "gate") in contract_combos
        assert ("DECISION", "scoring") in contract_combos
        assert ("SNAPSHOT", "position") in contract_combos
