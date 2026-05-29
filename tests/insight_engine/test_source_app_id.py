"""
source_app_id enforcement tests — fail-fast validation and stamping verification.

OTA-706
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


def _base_kwargs():
    """Shared kwargs for evaluate() — caller supplies source_app_id."""
    return dict(
        candidates=[Candidate("c1", "test", {"price": 10.0}, symbol="AAPL")],
        strategy_key="test_strat",
        config=_simple_config(),
        registry=DictFormulaRegistry({"f1": lambda nv, p: 80.0}),
    )


# ── Tests: fail-fast on missing/empty source_app_id ─────────────────────


class TestSourceAppIdValidation:
    def test_missing_source_app_id_raises(self):
        """Calling evaluate without source_app_id fails fast."""
        with pytest.raises(TypeError):
            evaluate(**_base_kwargs())  # source_app_id not passed at all

    @pytest.mark.parametrize("bad_value", [None, "", "   "])
    def test_empty_source_app_id_raises(self, bad_value):
        """Empty or whitespace-only source_app_id fails fast with ValueError."""
        with pytest.raises(ValueError, match="source_app_id is required"):
            evaluate(**_base_kwargs(), source_app_id=bad_value)

    def test_non_string_source_app_id_raises(self):
        with pytest.raises(ValueError, match="source_app_id is required"):
            evaluate(**_base_kwargs(), source_app_id=123)


# ── Tests: stamping through all emitted records ─────────────────────────


class TestSourceAppIdStamping:
    def test_result_record_stamped(self):
        results = evaluate(**_base_kwargs(), source_app_id="OTA")
        assert results[0].source_app_id == "OTA"

    def test_snapshot_stamped(self):
        sink = InMemorySink()
        evaluate(**_base_kwargs(), source_app_id="OTA", sink=sink)
        assert sink.snapshots[0].source_app_id == "OTA"

    def test_decisions_stamped(self):
        sink = InMemorySink()
        evaluate(**_base_kwargs(), source_app_id="OTA", sink=sink)
        for decision in sink.decisions:
            assert decision.source_app_id == "OTA"

    def test_different_app_id_stamped(self):
        """Non-OTA app ids are stamped correctly too."""
        sink = InMemorySink()
        evaluate(**_base_kwargs(), source_app_id="FFL", sink=sink)
        results = evaluate(**_base_kwargs(), source_app_id="FFL", sink=sink)
        assert results[0].source_app_id == "FFL"
        assert sink.snapshots[0].source_app_id == "FFL"
        for decision in sink.decisions:
            assert decision.source_app_id == "FFL"
