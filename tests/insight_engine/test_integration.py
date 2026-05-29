"""
Engine end-to-end integration tests on synthetic config + regression guards.

Two synthetic domains prove domain-agnosticism:
  - Domain A: "Evaluate apples by sweetness and price" (app_id="FRUIT")
  - Domain B: "Evaluate movies by rating and length" (app_id="CINEMA")

NO options-domain imports or terms appear in this file.

OTA-707
"""

from __future__ import annotations

import pytest

from app.insight_engine import evaluate
from app.insight_engine.config_source import InMemoryConfigSource
from app.insight_engine.loader import load_config
from app.insight_engine.models import Candidate, VerdictSource
from app.insight_engine.registry import DictFormulaRegistry
from app.insight_engine.sink import InMemorySink
from app.insight_engine.validation import validate_config


# ── Formula implementations (synthetic, no domain imports) ────────────


def _sweetness_score(nv: dict, params: dict) -> float:
    """Score apples by sweetness (0-100)."""
    sweetness = nv.get("sweetness", 0)
    return min(100.0, max(0.0, float(sweetness)))


def _price_score(nv: dict, params: dict) -> float:
    """Score apples by price — cheaper is better."""
    price = nv.get("price", 10)
    max_price = params.get("max_price", 10)
    if max_price == 0:
        return 0.0
    return max(0.0, min(100.0, (1 - price / max_price) * 100))


def _computed_freshness(nv: dict, params: dict) -> float:
    """A COMPUTED-tier formula — requires adapter callback to populate freshness."""
    return min(100.0, max(0.0, float(nv.get("freshness", 0))))


def _movie_rating_score(nv: dict, params: dict) -> float:
    """Score movies by rating (0-10 mapped to 0-100)."""
    return min(100.0, max(0.0, float(nv.get("rating", 0)) * 10))


def _movie_length_score(nv: dict, params: dict) -> float:
    """Score movies by length — closer to ideal is better."""
    length = nv.get("length_min", 0)
    ideal = params.get("ideal_length", 120)
    diff = abs(length - ideal)
    return max(0.0, 100.0 - diff)


# ── Shared fixture builders ──────────────────────────────────────────


def _fruit_apps():
    return [
        {"app_id": "SHARED", "name": "Shared", "status": "active", "enabled": True},
        {"app_id": "FRUIT", "name": "Fruit", "status": "active", "enabled": True},
    ]


def _fruit_lookups():
    """Seed SHARED formula_registry lookup set (OD-1 dual-source sync)."""
    return [
        {"owner_app_id": "SHARED", "lookup_set": "formula_registry",
         "lookup_key": "sweetness_score", "payload": None, "sort_order": 1, "enabled": True},
        {"owner_app_id": "SHARED", "lookup_set": "formula_registry",
         "lookup_key": "price_score", "payload": None, "sort_order": 2, "enabled": True},
        {"owner_app_id": "SHARED", "lookup_set": "formula_registry",
         "lookup_key": "computed_freshness", "payload": None, "sort_order": 3, "enabled": True},
    ]


def _fruit_registry():
    """Live registry matching the contract lookup set."""
    return DictFormulaRegistry({
        "sweetness_score": _sweetness_score,
        "price_score": _price_score,
        "computed_freshness": _computed_freshness,
    })


def _fruit_rules():
    return [
        # Gate: minimum weight (comparison-based, RAW tier)
        {
            "rule_id": 1, "owner_app_id": "SHARED", "rule_key": "min_weight_gate",
            "phase": "gate", "tier": "RAW", "intent": "Reject underweight apples",
            "condition_expression": ">=", "formula_ref": None,
            "referenced_named_values": ["weight_g"],
            "parameter_schema": {"min": {"type": "number"}},
            "null_semantics": None, "enabled": True,
        },
        # Gate: COMPUTED freshness gate (needs adapter callback)
        {
            "rule_id": 2, "owner_app_id": "SHARED", "rule_key": "freshness_gate",
            "phase": "gate", "tier": "COMPUTED", "intent": "Reject stale apples",
            "condition_expression": ">=", "formula_ref": None,
            "referenced_named_values": ["freshness"],
            "parameter_schema": {"min": {"type": "number"}},
            "null_semantics": None, "enabled": True,
        },
        # Scoring: sweetness (formula-based)
        {
            "rule_id": 3, "owner_app_id": "SHARED", "rule_key": "sweetness_criterion",
            "phase": "scoring", "tier": None, "intent": None,
            "condition_expression": None, "formula_ref": "formula:sweetness_score",
            "referenced_named_values": ["sweetness"],
            "parameter_schema": {}, "null_semantics": None, "enabled": True,
        },
        # Scoring: price (formula-based)
        {
            "rule_id": 4, "owner_app_id": "SHARED", "rule_key": "price_criterion",
            "phase": "scoring", "tier": None, "intent": None,
            "condition_expression": None, "formula_ref": "formula:price_score",
            "referenced_named_values": ["price"],
            "parameter_schema": {"max_price": {"type": "number"}},
            "null_semantics": None, "enabled": True,
        },
        # Adjustment: bruise penalty (formula-based)
        {
            "rule_id": 5, "owner_app_id": "SHARED", "rule_key": "bruise_adjustment",
            "phase": "adjustment", "tier": None, "intent": None,
            "condition_expression": None, "formula_ref": "formula:computed_freshness",
            "referenced_named_values": ["freshness"],
            "parameter_schema": {}, "null_semantics": None, "enabled": True,
        },
        # Non-stopping gate for Test 3
        {
            "rule_id": 6, "owner_app_id": "SHARED", "rule_key": "color_gate",
            "phase": "gate", "tier": "RAW", "intent": "Penalize wrong color",
            "condition_expression": ">=", "formula_ref": None,
            "referenced_named_values": ["redness"],
            "parameter_schema": {"min": {"type": "number"}},
            "null_semantics": None, "enabled": True,
        },
    ]


def _fruit_strategies():
    return [{
        "strategy_id": 1, "owner_app_id": "FRUIT",
        "strategy_key": "best_apple",
        "display_name": "Best Apple Selector", "consumer_surface": "SCREENING",
        "description": None, "compatible_structures": None,
        "verdict_band_set": [
            {"verdict": "BUY", "min_score": 60, "max_score": 100},
            {"verdict": "SKIP", "min_score": 0, "max_score": 59.99},
        ],
        "enabled": True,
    }]


def _fruit_junction_e2e():
    """Junction for Test 1 (full end-to-end pass)."""
    return [
        {
            "junction_id": 1, "strategy_id": 1, "rule_id": 1,
            "evaluation_order": 1, "stop_if_fail": True,
            "score_penalty": None, "weight": None,
            "parameters": {"min": 100.0}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
        {
            "junction_id": 2, "strategy_id": 1, "rule_id": 2,
            "evaluation_order": 2, "stop_if_fail": True,
            "score_penalty": None, "weight": None,
            "parameters": {"min": 50.0}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
        {
            "junction_id": 3, "strategy_id": 1, "rule_id": 3,
            "evaluation_order": 1, "stop_if_fail": False,
            "score_penalty": None, "weight": 0.6,
            "parameters": {}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
        {
            "junction_id": 4, "strategy_id": 1, "rule_id": 4,
            "evaluation_order": 2, "stop_if_fail": False,
            "score_penalty": None, "weight": 0.4,
            "parameters": {"max_price": 5.0}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
        {
            "junction_id": 5, "strategy_id": 1, "rule_id": 5,
            "evaluation_order": 1, "stop_if_fail": False,
            "score_penalty": None, "weight": None,
            "parameters": {}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
    ]


def _build_fruit_config(junction=None, extra_rules=None, extra_junction=None):
    """Build a fruit-domain config from the standard fixtures."""
    rules = _fruit_rules()
    if extra_rules:
        rules.extend(extra_rules)
    junc = junction if junction is not None else _fruit_junction_e2e()
    if extra_junction:
        junc = list(junc) + list(extra_junction)
    source = InMemoryConfigSource(
        apps=_fruit_apps(),
        rules=rules,
        strategies=_fruit_strategies(),
        junction=junc,
        lookups=_fruit_lookups(),
    )
    return load_config(source, app_ids=("SHARED", "FRUIT"))


class _FruitAdapter:
    """Synthetic COMPUTED adapter — populates freshness on surviving candidates."""

    def __init__(self, freshness_value: float = 80.0):
        self.freshness_value = freshness_value
        self.call_count = 0
        self.candidates_seen: list[str] = []

    def populate_computed(self, candidates, needed):
        self.call_count += 1
        for c in candidates:
            self.candidates_seen.append(c.candidate_id)
            if "freshness" in needed:
                c.named_values["freshness"] = self.freshness_value


# ── Domain B: Movies (for swap test) ────────────────────────────────


def _cinema_apps():
    return [
        {"app_id": "SHARED", "name": "Shared", "status": "active", "enabled": True},
        {"app_id": "CINEMA", "name": "Cinema", "status": "active", "enabled": True},
    ]


def _cinema_lookups():
    return [
        {"owner_app_id": "SHARED", "lookup_set": "formula_registry",
         "lookup_key": "movie_rating_score", "payload": None, "sort_order": 1, "enabled": True},
        {"owner_app_id": "SHARED", "lookup_set": "formula_registry",
         "lookup_key": "movie_length_score", "payload": None, "sort_order": 2, "enabled": True},
    ]


def _cinema_registry():
    return DictFormulaRegistry({
        "movie_rating_score": _movie_rating_score,
        "movie_length_score": _movie_length_score,
    })


def _build_cinema_config():
    rules = [
        {
            "rule_id": 10, "owner_app_id": "SHARED", "rule_key": "min_rating_gate",
            "phase": "gate", "tier": "RAW", "intent": "Reject low-rated movies",
            "condition_expression": ">=", "formula_ref": None,
            "referenced_named_values": ["rating"],
            "parameter_schema": {"min": {"type": "number"}},
            "null_semantics": None, "enabled": True,
        },
        {
            "rule_id": 11, "owner_app_id": "SHARED", "rule_key": "rating_criterion",
            "phase": "scoring", "tier": None, "intent": None,
            "condition_expression": None, "formula_ref": "formula:movie_rating_score",
            "referenced_named_values": ["rating"],
            "parameter_schema": {}, "null_semantics": None, "enabled": True,
        },
        {
            "rule_id": 12, "owner_app_id": "SHARED", "rule_key": "length_criterion",
            "phase": "scoring", "tier": None, "intent": None,
            "condition_expression": None, "formula_ref": "formula:movie_length_score",
            "referenced_named_values": ["length_min"],
            "parameter_schema": {"ideal_length": {"type": "number"}},
            "null_semantics": None, "enabled": True,
        },
    ]
    strategies = [{
        "strategy_id": 10, "owner_app_id": "CINEMA",
        "strategy_key": "best_movie",
        "display_name": "Best Movie Picker", "consumer_surface": "SCREENING",
        "description": None, "compatible_structures": None,
        "verdict_band_set": [
            {"verdict": "WATCH", "min_score": 50, "max_score": 100},
            {"verdict": "PASS", "min_score": 0, "max_score": 49.99},
        ],
        "enabled": True,
    }]
    junction = [
        {
            "junction_id": 10, "strategy_id": 10, "rule_id": 10,
            "evaluation_order": 1, "stop_if_fail": True,
            "score_penalty": None, "weight": None,
            "parameters": {"min": 5.0}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
        {
            "junction_id": 11, "strategy_id": 10, "rule_id": 11,
            "evaluation_order": 1, "stop_if_fail": False,
            "score_penalty": None, "weight": 0.5,
            "parameters": {}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
        {
            "junction_id": 12, "strategy_id": 10, "rule_id": 12,
            "evaluation_order": 2, "stop_if_fail": False,
            "score_penalty": None, "weight": 0.5,
            "parameters": {"ideal_length": 120}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
    ]
    source = InMemoryConfigSource(
        apps=_cinema_apps(), rules=rules, strategies=strategies,
        junction=junction, lookups=_cinema_lookups(),
    )
    return load_config(source, app_ids=("SHARED", "CINEMA"))


# ── Test 1: End-to-end pass ──────────────────────────────────────────


class TestEndToEndPass:
    """Candidates flow through all 7 phases to a verdict with full trace
    and bronze records emitted."""

    def test_full_pipeline_with_bronze(self):
        config = _build_fruit_config()
        registry = _fruit_registry()
        adapter = _FruitAdapter(freshness_value=90.0)
        sink = InMemorySink()

        apple = Candidate(
            "apple-1", "fruit",
            {"weight_g": 200, "sweetness": 85, "price": 2.0,
             "redness": 80},
            symbol="GALA", user_id="farmer-1",
        )

        results = evaluate(
            candidates=[apple],
            strategy_key="best_apple",
            source_app_id="FRUIT",
            config=config,
            registry=registry,
            adapter=adapter,
            sink=sink,
        )

        assert len(results) == 1
        r = results[0]

        # Verdict reached
        assert r.terminal_phase == "verdict"
        assert r.verdict in ("BUY", "SKIP")
        assert r.verdict_source == VerdictSource.BAND_LOOKUP
        assert r.final_score is not None

        # Full trace present
        assert len(r.gate_decisions) >= 1
        assert len(r.scoring_breakdown) == 2
        assert r.raw_score is not None

        # Provenance stamped
        assert r.source_app_id == "FRUIT"
        assert r.config_version is not None
        assert r.engine_version is not None

        # Bronze records emitted
        assert len(sink.snapshots) == 1
        assert len(sink.decisions) >= 4  # gates + scoring + adjustments
        assert sink.snapshots[0].source_app_id == "FRUIT"
        assert sink.snapshots[0].strategy_key == "best_apple"

        # COMPUTED adapter was called
        assert adapter.call_count == 1

    def test_validation_passes_with_synced_sources(self):
        """OD-1: both formula sources are in sync → validation passes."""
        config = _build_fruit_config()
        registry = _fruit_registry()
        report = validate_config(config, formula_registry=registry)
        assert report.is_valid, report.summary()


# ── Test 2: Swap domain + source_app_id ──────────────────────────────


class TestSwapDomainAgnosticism:
    """Re-run with a different adapter, strategy, and source_app_id.
    Proves the engine is domain-agnostic."""

    def test_cinema_domain_different_app_id(self):
        config = _build_cinema_config()
        registry = _cinema_registry()
        sink = InMemorySink()

        movie = Candidate(
            "movie-1", "film",
            {"rating": 8.5, "length_min": 110},
            symbol="INCEPTION",
        )

        results = evaluate(
            candidates=[movie],
            strategy_key="best_movie",
            source_app_id="CINEMA",
            config=config,
            registry=registry,
            sink=sink,
        )

        assert len(results) == 1
        r = results[0]

        # Different domain, still works
        assert r.terminal_phase == "verdict"
        assert r.verdict in ("WATCH", "PASS")
        assert r.source_app_id == "CINEMA"

        # Bronze stamped with CINEMA
        assert sink.snapshots[0].source_app_id == "CINEMA"
        assert sink.snapshots[0].strategy_key == "best_movie"
        for d in sink.decisions:
            assert d.source_app_id == "CINEMA"

    def test_cinema_validation_passes(self):
        config = _build_cinema_config()
        registry = _cinema_registry()
        report = validate_config(config, formula_registry=registry)
        assert report.is_valid, report.summary()


# ── Test 3: Non-stopping gate failure ────────────────────────────────


class TestNonStoppingGateFailure:
    """A stop_if_fail=false failure retains the candidate through scoring
    and emits both the failed-gate decision and the final verdict."""

    def test_soft_gate_failure_reaches_verdict(self):
        # Add color_gate as non-stopping to the junction
        junction = list(_fruit_junction_e2e())
        junction.append({
            "junction_id": 6, "strategy_id": 1, "rule_id": 6,
            "evaluation_order": 3, "stop_if_fail": False,
            "score_penalty": 10.0, "weight": None,
            "parameters": {"min": 90.0}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        })

        config = _build_fruit_config(junction=junction)
        registry = _fruit_registry()
        adapter = _FruitAdapter(freshness_value=80.0)
        sink = InMemorySink()

        # redness=50 fails the color_gate (min=90), but stop_if_fail=false
        apple = Candidate(
            "apple-soft", "fruit",
            {"weight_g": 200, "sweetness": 70, "price": 2.0,
             "redness": 50},
        )

        results = evaluate(
            candidates=[apple],
            strategy_key="best_apple",
            source_app_id="FRUIT",
            config=config,
            registry=registry,
            adapter=adapter,
            sink=sink,
        )

        assert len(results) == 1
        r = results[0]

        # Candidate reached verdict despite gate failure
        assert r.terminal_phase == "verdict"
        assert r.verdict is not None
        assert r.verdict_source == VerdictSource.BAND_LOOKUP

        # The failed gate decision is in the trace
        color_gate = [g for g in r.gate_decisions if g.rule_key == "color_gate"]
        assert len(color_gate) == 1
        assert color_gate[0].passed is False
        assert color_gate[0].was_terminal is False
        assert color_gate[0].held_penalty == 10.0

        # Penalty was applied to score
        assert r.held_penalties_applied == 10.0

        # Bronze decisions include the failed gate
        failed_decisions = [
            d for d in sink.decisions if d.rule_key == "color_gate"
        ]
        assert len(failed_decisions) == 1
        assert failed_decisions[0].passed is False


# ── Test 4: Halt-verdict path ────────────────────────────────────────


class TestHaltVerdictPath:
    """A stopping gate with terminal_verdict halts the candidate and
    emits that verdict, bypassing band lookup."""

    def test_terminal_verdict_on_halt(self):
        # Modify junction: min_weight_gate has terminal_verdict="REJECTED"
        junction = [
            {
                "junction_id": 1, "strategy_id": 1, "rule_id": 1,
                "evaluation_order": 1, "stop_if_fail": True,
                "score_penalty": None, "weight": None,
                "parameters": {"min": 100.0},
                "terminal_verdict": "REJECTED",
                "rationale": None, "enabled": True,
            },
            # Keep scoring so we can verify it's bypassed
            {
                "junction_id": 3, "strategy_id": 1, "rule_id": 3,
                "evaluation_order": 1, "stop_if_fail": False,
                "score_penalty": None, "weight": 1.0,
                "parameters": {}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
        ]

        config = _build_fruit_config(junction=junction)
        registry = _fruit_registry()
        adapter = _FruitAdapter()
        sink = InMemorySink()

        # weight_g=50 fails the min_weight_gate (min=100)
        apple = Candidate(
            "apple-halt", "fruit",
            {"weight_g": 50, "sweetness": 90, "price": 1.0},
        )

        results = evaluate(
            candidates=[apple],
            strategy_key="best_apple",
            source_app_id="FRUIT",
            config=config,
            registry=registry,
            adapter=adapter,
            sink=sink,
        )

        assert len(results) == 1
        r = results[0]

        # Halted at gate with terminal verdict
        assert r.terminal_phase == "gate"
        assert r.verdict == "REJECTED"
        assert r.verdict_source == VerdictSource.HALT_TERMINAL_VERDICT
        assert r.final_score is None

        # Scoring was bypassed
        assert r.scoring_breakdown == []

        # Bronze snapshot reflects halt
        assert sink.snapshots[0].terminal_phase == "gate"
        assert sink.snapshots[0].verdict == "REJECTED"
        assert sink.snapshots[0].final_score is None

        # Only the halting gate decision was emitted
        assert len(sink.decisions) == 1
        assert sink.decisions[0].was_terminal is True


# ── Test 5: evaluation_order collision rejection ─────────────────────


class TestEvalOrderCollisionRejection:
    """A config with two enabled rules sharing an evaluation_order within
    a (strategy, phase) is rejected at validation (OTA-683 guard)."""

    def test_duplicate_order_rejected_at_validation(self):
        # Two scoring rules with the same evaluation_order
        junction = [
            {
                "junction_id": 1, "strategy_id": 1, "rule_id": 1,
                "evaluation_order": 1, "stop_if_fail": True,
                "score_penalty": None, "weight": None,
                "parameters": {"min": 100.0}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
            {
                "junction_id": 3, "strategy_id": 1, "rule_id": 3,
                "evaluation_order": 1, "stop_if_fail": False,
                "score_penalty": None, "weight": 0.5,
                "parameters": {}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
            {
                "junction_id": 4, "strategy_id": 1, "rule_id": 4,
                "evaluation_order": 1, "stop_if_fail": False,
                "score_penalty": None, "weight": 0.5,
                "parameters": {"max_price": 5.0}, "terminal_verdict": None,
                "rationale": None, "enabled": True,
            },
        ]

        config = _build_fruit_config(junction=junction)
        registry = _fruit_registry()
        report = validate_config(config, formula_registry=registry)

        # Should have EVAL_ORDER_DUPLICATE error
        dups = report.errors_by_code("EVAL_ORDER_DUPLICATE")
        assert len(dups) >= 1, f"Expected EVAL_ORDER_DUPLICATE, got: {report.summary()}"
        assert "scoring" in dups[0].message.lower() or dups[0].context.get("phase") == "scoring"


# ── Test 6: Formula drift detection (OD-1) ──────────────────────────


class TestFormulaDrift:
    """Desync the two formula sources → OTA-699 drift error fires."""

    def test_drift_detected_when_live_has_extra(self):
        config = _build_fruit_config()
        # Add an extra formula to live registry not in the contract
        registry = _fruit_registry()
        registry.register("phantom_formula", lambda nv, p: 0.0)

        report = validate_config(config, formula_registry=registry)
        drift = report.errors_by_code("FORMULA_REGISTRY_DRIFT")
        assert len(drift) >= 1
        assert any("phantom_formula" in e.message for e in drift)

    def test_no_drift_when_synced(self):
        config = _build_fruit_config()
        registry = _fruit_registry()
        report = validate_config(config, formula_registry=registry)
        drift = report.errors_by_code("FORMULA_REGISTRY_DRIFT")
        assert len(drift) == 0, f"Unexpected drift: {[str(e) for e in drift]}"
