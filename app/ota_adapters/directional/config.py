"""
Directional comparison — strategy, rules, and junction configuration.

DESIGN DECISION: Single strategy ("directional_comparison").
Rationale: The directional surface answers one question — "given a thesis,
which structure best fits?" — and the scoring criteria (budget fit,
probability, buffer, defined risk preference) apply uniformly regardless
of bullish/bearish direction. The adapter already filters by direction;
the strategy doesn't need to branch on it. If future needs demand
direction-specific weighting, a second strategy can be added with
different junction weights without changing engine or adapter code.

This module provides InMemoryConfigSource-compatible row dicts for:
  - strategy row (engine_strategies)
  - rule rows (engine_rules) — placeholders until OTA-755 registers formulas
  - junction rows (engine_strategy_rule_junction)
  - lookup rows (engine_lookups) — verdict domain for DIRECTIONAL surface

The seed script (scripts/seed_engine_config.py) can import these and
merge them into the DB upsert. Tests use them via InMemoryConfigSource.

OTA-754
"""

from __future__ import annotations

import json

# ── Strategy definition ──────────────────────────────────────────────

STRATEGY_KEY = "directional_comparison"
CONSUMER_SURFACE = "DIRECTIONAL"

# Verdict bands — same EXECUTE / WAIT / PASS model as screening,
# calibrated for thesis-fit scoring
VERDICT_BANDS = [
    {"verdict": "EXECUTE", "min_score": 70, "max_score": 100},
    {"verdict": "WAIT",    "min_score": 50, "max_score": 69.99},
    {"verdict": "PASS",    "min_score": 0,  "max_score": 49.99},
]


def get_strategy_row() -> dict:
    """Return the engine_strategies row for the directional strategy."""
    return {
        "owner_app_id": "OTA",
        "strategy_key": STRATEGY_KEY,
        "display_name": "Directional Comparison",
        "consumer_surface": CONSUMER_SURFACE,
        "description": (
            "Given a directional thesis (ticker, direction, conviction, "
            "target price, timeframe, budget), rank all compatible trade "
            "structures by thesis fit. Single strategy — the adapter filters "
            "by direction; the engine scores uniformly."
        ),
        "compatible_structures": json.dumps([
            "bull_call", "bear_put", "long_call", "long_put",
        ]),
        "verdict_band_set": json.dumps(VERDICT_BANDS),
        "dte_min": None,
        "dte_max": None,
        "enabled": True,
    }


# ── Rule definitions ──────────────────────────────────────────────────
# These are the scoring criteria decomposed from fitness_score (OTA-755).
# The rule rows declare the shape; formula implementations are registered
# in app/options_rules/directional/ (OTA-755).

def get_rule_rows() -> list[dict]:
    """Return engine_rules rows for directional scoring criteria."""
    return [
        {
            "owner_app_id": "OTA",
            "rule_key": "dir_budget_fit",
            "phase": "scoring",
            "tier": None,
            "intent": "Score whether the trade cost fits within the thesis risk budget",
            "condition_expression": None,
            "formula_ref": "formula:dir_budget_fit",
            "referenced_named_values": json.dumps(["fits_budget"]),
            "parameter_schema": json.dumps({
                "fit_score": {"type": "number", "default": 100},
                "no_fit_score": {"type": "number", "default": 0},
            }),
            "null_semantics": None,
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "rule_key": "dir_probability",
            "phase": "scoring",
            "tier": None,
            "intent": "Score probability of profit — higher PoP = higher score",
            "condition_expression": None,
            "formula_ref": "formula:dir_probability",
            "referenced_named_values": json.dumps(["prob_of_profit"]),
            "parameter_schema": json.dumps({
                "scale": {"type": "number", "default": 100},
            }),
            "null_semantics": None,
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "rule_key": "dir_buffer",
            "phase": "scoring",
            "tier": None,
            "intent": (
                "Score the buffer between breakeven and thesis target — "
                "more buffer = more room for thesis imprecision"
            ),
            "condition_expression": None,
            "formula_ref": "formula:dir_buffer",
            "referenced_named_values": json.dumps(["buffer_pct"]),
            "parameter_schema": json.dumps({
                "cap": {"type": "number", "default": 10},
                "scale": {"type": "number", "default": 100},
            }),
            "null_semantics": None,
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "rule_key": "dir_defined_risk",
            "phase": "scoring",
            "tier": None,
            "intent": (
                "Slight preference for defined-risk structures (vertical spreads) "
                "over unlimited-risk (naked options)"
            ),
            "condition_expression": None,
            "formula_ref": "formula:dir_defined_risk",
            "referenced_named_values": json.dumps(["structure_type"]),
            "parameter_schema": json.dumps({
                "spread_score": {"type": "number", "default": 100},
                "naked_score": {"type": "number", "default": 0},
            }),
            "null_semantics": None,
            "enabled": True,
        },
    ]


# ── Junction rows ────────────────────────────────────────────────────
# Weights derived from fitness_score max contributions:
#   budget_fit:    20/85 ≈ 0.235
#   probability:   30/85 ≈ 0.353
#   buffer:        30/85 ≈ 0.353
#   defined_risk:   5/85 ≈ 0.059
# Normalised to sum = 1.0

def get_junction_rows() -> list[dict]:
    """Return engine_strategy_rule_junction rows binding rules to the strategy."""
    return [
        {
            "strategy_key": STRATEGY_KEY,
            "rule_key": "dir_budget_fit",
            "evaluation_order": 1,
            "stop_if_fail": False,
            "score_penalty": None,
            "weight": 0.235,
            "parameters": json.dumps({
                "fit_score": 100,
                "no_fit_score": 0,
            }),
            "rationale": (
                "Budget fit is a binary pass/fail contributing ~24% of "
                "the total score. Legacy: +20 out of 85 max."
            ),
            "enabled": True,
            "terminal_verdict": None,
        },
        {
            "strategy_key": STRATEGY_KEY,
            "rule_key": "dir_probability",
            "evaluation_order": 2,
            "stop_if_fail": False,
            "score_penalty": None,
            "weight": 0.353,
            "parameters": json.dumps({
                "scale": 100,
            }),
            "rationale": (
                "Probability of profit is the largest single scoring factor, "
                "contributing ~35%. Linear: prob * scale. Legacy: prob * 30."
            ),
            "enabled": True,
            "terminal_verdict": None,
        },
        {
            "strategy_key": STRATEGY_KEY,
            "rule_key": "dir_buffer",
            "evaluation_order": 3,
            "stop_if_fail": False,
            "score_penalty": None,
            "weight": 0.353,
            "parameters": json.dumps({
                "cap": 10,
                "scale": 100,
            }),
            "rationale": (
                "Buffer — room between breakeven and thesis target — also ~35%. "
                "Capped at 10% buffer (beyond that, diminishing returns). "
                "Legacy: min(buffer_pct, 10) * 3."
            ),
            "enabled": True,
            "terminal_verdict": None,
        },
        {
            "strategy_key": STRATEGY_KEY,
            "rule_key": "dir_defined_risk",
            "evaluation_order": 4,
            "stop_if_fail": False,
            "score_penalty": None,
            "weight": 0.059,
            "parameters": json.dumps({
                "spread_score": 100,
                "naked_score": 0,
            }),
            "rationale": (
                "Small tiebreaker preference (~6%) for vertical spreads "
                "(defined risk) over naked options. Legacy: +5 for spreads."
            ),
            "enabled": True,
            "terminal_verdict": None,
        },
    ]


# ── Lookup rows ──────────────────────────────────────────────────────

def get_lookup_rows() -> list[dict]:
    """Return engine_lookups rows for the DIRECTIONAL verdict domain."""
    return [
        {
            "owner_app_id": "OTA",
            "lookup_set": "directional_verdicts",
            "lookup_key": "EXECUTE",
            "payload": json.dumps({"label": "EXECUTE", "kind": "BAND_VERDICT"}),
            "sort_order": 1,
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "lookup_set": "directional_verdicts",
            "lookup_key": "WAIT",
            "payload": json.dumps({"label": "WAIT", "kind": "BAND_VERDICT"}),
            "sort_order": 2,
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "lookup_set": "directional_verdicts",
            "lookup_key": "PASS",
            "payload": json.dumps({"label": "PASS", "kind": "BAND_VERDICT"}),
            "sort_order": 3,
            "enabled": True,
        },
    ]


# ── Convenience: all rows for InMemoryConfigSource ────────────────────

def get_all_config_rows() -> dict:
    """Return all config rows grouped by table name.

    Usage with InMemoryConfigSource::

        from app.ota_adapters.directional.config import get_all_config_rows
        from app.insight_engine import InMemoryConfigSource, load_config

        rows = get_all_config_rows()
        source = InMemoryConfigSource(
            apps=rows["apps"],
            rules=rows["rules"],
            strategies=rows["strategies"],
            junction=rows["junction"],
            lookups=rows["lookups"],
        )
        config = load_config(source)
    """
    strat = get_strategy_row()
    rules = get_rule_rows()
    junctions = get_junction_rows()
    lookups = get_lookup_rows()

    # Assign synthetic IDs for InMemoryConfigSource (DB assigns real ones)
    strat_id = 100
    rule_id_start = 500

    strat_with_id = {**strat, "strategy_id": strat_id}

    rules_with_ids = []
    rule_id_map = {}
    for i, r in enumerate(rules):
        rid = rule_id_start + i
        rules_with_ids.append({**r, "rule_id": rid})
        rule_id_map[r["rule_key"]] = rid

    junctions_with_ids = []
    for j in junctions:
        junctions_with_ids.append({
            **j,
            "strategy_id": strat_id,
            "rule_id": rule_id_map[j["rule_key"]],
        })

    return {
        "apps": [
            {"app_id": "SHARED", "name": "Shared", "enabled": True},
            {"app_id": "OTA", "name": "OTA", "enabled": True},
        ],
        "rules": rules_with_ids,
        "strategies": [strat_with_id],
        "junction": junctions_with_ids,
        "lookups": lookups,
    }
