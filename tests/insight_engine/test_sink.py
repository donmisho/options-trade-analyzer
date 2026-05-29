"""
Persistence sink tests — interface, in-memory sink, and engine-driven wiring.

OTA-705
"""

from __future__ import annotations

import pytest

from app.insight_engine import evaluate
from app.insight_engine.config_source import InMemoryConfigSource
from app.insight_engine.loader import load_config
from app.insight_engine.models import Candidate
from app.insight_engine.registry import DictFormulaRegistry
from app.insight_engine.sink import InMemorySink


# ── Fixture helpers ─────────────────────────────────────────────────────


def _apps():
    return [
        {"app_id": "SHARED", "name": "Shared", "status": "active", "enabled": True},
        {"app_id": "OTA", "name": "OTA", "status": "active", "enabled": True},
    ]


def _simple_config():
    rules = [
        {
            "rule_id": 1, "owner_app_id": "SHARED", "rule_key": "gate1",
            "phase": "gate", "tier": "RAW", "intent": None,
            "condition_expression": ">=", "formula_ref": None,
            "referenced_named_values": ["price"],
            "parameter_schema": {"min": {"type": "number"}},
            "null_semantics": None, "enabled": True,
        },
        {
            "rule_id": 2, "owner_app_id": "SHARED", "rule_key": "score1",
            "phase": "scoring", "tier": None, "intent": None,
            "condition_expression": None, "formula_ref": "formula:f1",
            "referenced_named_values": [],
            "parameter_schema": {}, "null_semantics": None, "enabled": True,
        },
    ]
    strategies = [{
        "strategy_id": 1, "owner_app_id": "OTA", "strategy_key": "test_strat",
        "display_name": "Test", "consumer_surface": "SCREENING",
        "description": None, "compatible_structures": None,
        "verdict_band_set": [
            {"verdict": "EXECUTE", "min_score": 70, "max_score": 100},
            {"verdict": "PASS", "min_score": 0, "max_score": 69.99},
        ],
        "enabled": True,
    }]
    junction = [
        {
            "junction_id": 1, "strategy_id": 1, "rule_id": 1,
            "evaluation_order": 1, "stop_if_fail": True,
            "score_penalty": None, "weight": None,
            "parameters": {"min": 5.0}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
        {
            "junction_id": 2, "strategy_id": 1, "rule_id": 2,
            "evaluation_order": 1, "stop_if_fail": False,
            "score_penalty": None, "weight": 1.0,
            "parameters": {}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
    ]
    source = InMemoryConfigSource(
        apps=_apps(), rules=rules, strategies=strategies,
        junction=junction, lookups=[],
    )
    return load_config(source)


# ── Tests ───────────────────────────────────────────────────────────────


class TestInMemorySink:
    def test_sink_captures_both_streams(self):
        """Inject in-memory sink; assert both write methods called."""
        config = _simple_config()
        registry = DictFormulaRegistry({"f1": lambda nv, p: 80.0})
        sink = InMemorySink()

        candidates = [
            Candidate("c1", "test", {"price": 10.0}, symbol="AAPL"),
            Candidate("c2", "test", {"price": 20.0}, symbol="MSFT"),
        ]

        results = evaluate(
            candidates=candidates,
            strategy_key="test_strat",
            source_app_id="OTA",
            config=config,
            registry=registry,
            sink=sink,
        )

        # Both candidates scored
        assert len(results) == 2

        # Sink received snapshots (one per candidate)
        assert len(sink.snapshots) == 2

        # Sink received decisions (1 gate + 1 scoring = 2 per candidate = 4 total)
        assert len(sink.decisions) == 4

    def test_sink_snapshots_match_results(self):
        config = _simple_config()
        registry = DictFormulaRegistry({"f1": lambda nv, p: 80.0})
        sink = InMemorySink()

        results = evaluate(
            candidates=[Candidate("c1", "test", {"price": 10.0}, symbol="AAPL")],
            strategy_key="test_strat",
            source_app_id="OTA",
            config=config,
            registry=registry,
            sink=sink,
        )

        snapshot = sink.snapshots[0]
        assert snapshot.source_app_id == "OTA"
        assert snapshot.strategy_key == "test_strat"
        assert snapshot.symbol == "AAPL"
        assert snapshot.verdict == results[0].verdict
        assert snapshot.final_score == results[0].final_score

    def test_sink_decisions_correlate_to_snapshot(self):
        config = _simple_config()
        registry = DictFormulaRegistry({"f1": lambda nv, p: 80.0})
        sink = InMemorySink()

        evaluate(
            candidates=[Candidate("c1", "test", {"price": 10.0})],
            strategy_key="test_strat",
            source_app_id="OTA",
            config=config,
            registry=registry,
            sink=sink,
        )

        snapshot = sink.snapshots[0]
        for decision in sink.decisions:
            assert decision.snapshot_id == snapshot.snapshot_id
            assert decision.run_id == snapshot.run_id

    def test_no_sink_no_error(self):
        """Engine works fine without a sink — sink is optional."""
        config = _simple_config()
        registry = DictFormulaRegistry({"f1": lambda nv, p: 80.0})

        results = evaluate(
            candidates=[Candidate("c1", "test", {"price": 10.0})],
            strategy_key="test_strat",
            source_app_id="OTA",
            config=config,
            registry=registry,
            sink=None,
        )

        assert len(results) == 1
        assert results[0].verdict is not None

    def test_sink_clear(self):
        sink = InMemorySink()
        sink.snapshots.append("dummy")
        sink.decisions.append("dummy")
        sink.clear()
        assert sink.snapshots == []
        assert sink.decisions == []

    def test_halted_candidate_written_to_sink(self):
        """Halted candidates also produce sink records."""
        config = _simple_config()
        registry = DictFormulaRegistry({"f1": lambda nv, p: 80.0})
        sink = InMemorySink()

        # price=1 fails gate (min=5)
        evaluate(
            candidates=[Candidate("c1", "test", {"price": 1.0})],
            strategy_key="test_strat",
            source_app_id="OTA",
            config=config,
            registry=registry,
            sink=sink,
        )

        assert len(sink.snapshots) == 1
        assert sink.snapshots[0].final_score is None
        assert sink.snapshots[0].terminal_phase == "gate"
        # 1 gate decision (halted)
        assert len(sink.decisions) == 1
        assert sink.decisions[0].was_terminal is True
