"""
OTA-818 + OTA-758 — engine runtime wiring tests.

Covers the app-layer bridge in ``app/ota_adapters/engine_runtime.py`` without
touching Azure SQL:

  - AzureSqlConfigSource serves buffered rows through the sync ConfigSource
    Protocol (the loader's contract).
  - BronzeSqlSink maps CandidateSnapshot / EvaluationDecision to the correct
    bronze_evaluations columns, discriminated by record_type, with the
    opposite stream's promoted columns NULL and payload_json a JSON string.
  - bronze_payload_contract registration uses the right discriminator
    (candidate_type for SNAPSHOT, phase for DECISION) and dedupes per process.
  - The sink is fire-and-forget: a failing session factory is logged, not
    raised, and never breaks the caller.
  - The runtime accessor raises before init and returns the stash after.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

from app.insight_engine import CandidateSnapshot, EvaluationDecision
from app.ota_adapters.engine_runtime import (
    _BRONZE_COLUMNS,
    AzureSqlConfigSource,
    BronzeSqlSink,
    EngineRuntime,
    _reset_engine_runtime,
    get_engine_runtime,
    set_engine_runtime,
)


_TS = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)


def _snapshot(**over) -> CandidateSnapshot:
    base = dict(
        snapshot_id="snap-1",
        run_id="run-1",
        source_app_id="OTA",
        config_version="cfgver123",
        engine_version="1.0.0",
        evaluated_at=_TS,
        payload_version=1,
        candidate_type="options_trade",
        strategy_key="steady_paycheck",
        symbol="AMZN",
        user_id="user-1",
        subject_type="TRADE_CANDIDATE",
        subject_id="trade-1",
        final_score=82.5,
        verdict="EXECUTE",
        terminal_phase="verdict",
        payload_json={"named_values": {"delta": 0.3}, "raw_score": 80.0},
    )
    base.update(over)
    return CandidateSnapshot(**base)


def _decision(**over) -> EvaluationDecision:
    base = dict(
        snapshot_id="snap-1",
        run_id="run-1",
        source_app_id="OTA",
        config_version="cfgver123",
        engine_version="1.0.0",
        evaluated_at=_TS,
        payload_version=1,
        rule_key="delta_band",
        phase="gate",
        tier="RAW",
        evaluation_order=1,
        passed=True,
        stop_if_fail=True,
        was_terminal=False,
        score_contribution=None,
        payload_json={"decision_reason": "in band"},
    )
    base.update(over)
    return EvaluationDecision(**base)


# ── AzureSqlConfigSource (sync Protocol over buffered rows) ───────────────


def test_config_source_serves_buffers_verbatim():
    src = AzureSqlConfigSource(
        apps=[{"app_id": "OTA"}],
        rules=[{"rule_id": 1}],
        strategies=[{"strategy_id": 1}],
        junction=[{"junction_id": 1}],
        lookups=[{"lookup_id": 1}],
    )
    assert src.fetch_apps() == [{"app_id": "OTA"}]
    assert src.fetch_rules() == [{"rule_id": 1}]
    assert src.fetch_strategies() == [{"strategy_id": 1}]
    assert src.fetch_junction() == [{"junction_id": 1}]
    assert src.fetch_lookups() == [{"lookup_id": 1}]
    # Returns copies — callers can't mutate the buffer through the result.
    src.fetch_apps().append({"app_id": "X"})
    assert src.fetch_apps() == [{"app_id": "OTA"}]


# ── BronzeSqlSink column mapping ──────────────────────────────────────────


def _sink() -> BronzeSqlSink:
    return BronzeSqlSink(session_factory=None, loop=asyncio.new_event_loop())


def test_snapshot_row_has_all_columns_and_correct_discrimination():
    row = BronzeSqlSink._snapshot_to_row(_snapshot())
    assert set(row.keys()) == set(_BRONZE_COLUMNS)
    assert row["record_type"] == "SNAPSHOT"
    # SNAPSHOT promoted columns populated
    assert row["candidate_type"] == "options_trade"
    assert row["final_score"] == 82.5
    assert row["verdict"] == "EXECUTE"
    # DECISION-only columns NULL on a snapshot row
    for col in ("rule_key", "phase", "tier", "evaluation_order",
                "passed", "stop_if_fail", "was_terminal", "score_contribution"):
        assert row[col] is None
    # payload_json serialized to a JSON string (ISJSON-safe)
    assert isinstance(row["payload_json"], str)
    assert json.loads(row["payload_json"])["raw_score"] == 80.0


def test_decision_row_has_all_columns_and_correct_discrimination():
    row = BronzeSqlSink._decision_to_row(_decision())
    assert set(row.keys()) == set(_BRONZE_COLUMNS)
    assert row["record_type"] == "DECISION"
    # DECISION promoted columns populated
    assert row["rule_key"] == "delta_band"
    assert row["phase"] == "gate"
    assert row["tier"] == "RAW"
    assert row["passed"] is True
    # SNAPSHOT-only columns NULL on a decision row
    for col in ("candidate_type", "strategy_key", "symbol", "user_id",
                "subject_type", "subject_id", "final_score", "verdict",
                "terminal_phase"):
        assert row[col] is None
    assert isinstance(row["payload_json"], str)


def test_payload_json_none_stays_none():
    row = BronzeSqlSink._snapshot_to_row(_snapshot(payload_json=None))
    assert row["payload_json"] is None


# ── bronze_payload_contract registration ──────────────────────────────────


def test_contract_discriminator_and_dedup():
    sink = _sink()
    # SNAPSHOT discriminator = candidate_type
    c1 = sink._collect_contracts([("OTA", "SNAPSHOT", "options_trade", 1)])
    assert len(c1) == 1
    assert c1[0]["record_type"] == "SNAPSHOT"
    assert c1[0]["discriminator_value"] == "options_trade"
    assert c1[0]["payload_version"] == 1
    assert c1[0]["source_app_id"] == "OTA"
    # Same combo again → already registered this process → no row
    c2 = sink._collect_contracts([("OTA", "SNAPSHOT", "options_trade", 1)])
    assert c2 == []
    # DECISION discriminator = phase; distinct combo registers
    c3 = sink._collect_contracts([("OTA", "DECISION", "gate", 1)])
    assert len(c3) == 1
    assert c3[0]["discriminator_value"] == "gate"


# ── Fire-and-forget semantics ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_write_failure_is_swallowed_not_raised(caplog):
    """A failing session factory must not break the caller (insight_engine §4.3)."""
    caplog.set_level("ERROR", logger="app.ota_adapters.engine_runtime")

    def boom_factory():
        raise RuntimeError("db unreachable")

    sink = BronzeSqlSink(
        session_factory=boom_factory, loop=asyncio.get_running_loop()
    )

    # The Protocol calls return synchronously and never raise.
    sink.write_snapshots([_snapshot()])
    sink.write_decisions([_decision()])

    # Let the scheduled coroutines run; the failure is logged, not raised.
    await asyncio.sleep(0.05)
    assert any("write failed" in rec.getMessage() for rec in caplog.records), (
        "expected the swallowed write failure to be logged"
    )


@pytest.mark.asyncio
async def test_empty_streams_are_noops():
    sink = BronzeSqlSink(
        session_factory=lambda: (_ for _ in ()).throw(AssertionError("should not open")),
        loop=asyncio.get_running_loop(),
    )
    # No records → no scheduling, factory never touched.
    sink.write_snapshots([])
    sink.write_decisions([])
    await asyncio.sleep(0.01)


# ── Runtime accessor ──────────────────────────────────────────────────────


def test_accessor_raises_before_init_and_returns_after():
    _reset_engine_runtime()
    with pytest.raises(RuntimeError, match="not initialized"):
        get_engine_runtime()

    rt = EngineRuntime(
        config=object(),  # opaque; accessor doesn't introspect
        sink=_sink(),
        source=AzureSqlConfigSource(
            apps=[], rules=[], strategies=[], junction=[], lookups=[]
        ),
        config_version="abc123",
        # OTA-843: loadable_version is now a required field (OTA-790 startup
        # stamp). Distinct from config_version; the accessor does not introspect.
        loadable_version="loadable123",
    )
    set_engine_runtime(rt)
    assert get_engine_runtime() is rt
    assert get_engine_runtime().config_version == "abc123"
    _reset_engine_runtime()
