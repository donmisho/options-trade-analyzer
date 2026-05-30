"""
Position-health — strategy, rules, junction, and lookup configuration.

Two strategies, both on the POSITION_HEALTH consumer surface:

  position_health_full  — exit-level-dominant + P&L supplementary.
      Requires stored Claude warning/stop levels.
  position_health_basic — P&L-only.
      Fallback when exit levels are absent.

Verdict bands (shared, A–F letter grades):
    A ≥ 90, B ≥ 75, C ≥ 50, D ≥ 25, F < 25

Strategy selection is orchestration (Position Monitor Agent), not
engine logic: the agent checks position_exit_levels_complete and
picks _full or _basic accordingly.

This module provides InMemoryConfigSource-compatible row dicts.
The seed script can import these for DB upsert; tests use them
via InMemoryConfigSource.

OTA-743
"""

from __future__ import annotations

import json

# ── Shared constants ────────────────────────────────────────────────

CONSUMER_SURFACE = "POSITION_HEALTH"

VERDICT_BANDS = [
    {"verdict": "A", "min_score": 90,    "max_score": 100},
    {"verdict": "B", "min_score": 75,    "max_score": 89.99},
    {"verdict": "C", "min_score": 50,    "max_score": 74.99},
    {"verdict": "D", "min_score": 25,    "max_score": 49.99},
    {"verdict": "F", "min_score": 0,     "max_score": 24.99},
]

# Scan parameters — shared by both strategies.
# All open positions; daily after market close + on demand.
SCAN_PARAMS = {
    "scope": "all_open_positions",
    "trigger": "daily_post_close_and_on_demand",
}


# ── Strategy definitions ────────────────────────────────────────────

STRATEGY_FULL_KEY = "position_health_full"
STRATEGY_BASIC_KEY = "position_health_basic"


def get_strategy_rows() -> list[dict]:
    """Return engine_strategies rows for both position-health strategies."""
    return [
        {
            "owner_app_id": "OTA",
            "strategy_key": STRATEGY_FULL_KEY,
            "display_name": "Position Health (Full)",
            "consumer_surface": CONSUMER_SURFACE,
            "description": (
                "Exit-level-dominant grading for positions with stored "
                "Claude warning/stop levels. Weighted: exit_level_safety_score "
                "~70%, pnl_band_score ~30%. Post-scoring adjustments enforce "
                "categorical guarantees (stop→F, warning→D)."
            ),
            "compatible_structures": None,
            "verdict_band_set": json.dumps(VERDICT_BANDS),
            "dte_min": None,
            "dte_max": None,
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "strategy_key": STRATEGY_BASIC_KEY,
            "display_name": "Position Health (Basic)",
            "consumer_surface": CONSUMER_SURFACE,
            "description": (
                "P&L-only grading for positions without stored exit levels. "
                "Single criterion: pnl_band_score at weight 1.0. No exit-level "
                "formulas or adjustments."
            ),
            "compatible_structures": None,
            "verdict_band_set": json.dumps(VERDICT_BANDS),
            "dte_min": None,
            "dte_max": None,
            "enabled": True,
        },
    ]


# ── Rule definitions ────────────────────────────────────────────────
# Phase 1 (OTA-743): rule rows are declared here as placeholders.
# Formula implementations are registered in app/options_rules/position_health/
# by later stories (OTA-744 through OTA-747).


def get_rule_rows() -> list[dict]:
    """Return engine_rules rows for position-health criteria and gates."""
    return [
        # ── Hard gates (OTA-744) ──
        {
            "owner_app_id": "OTA",
            "rule_key": "ph_entry_price_required",
            "phase": "gate",
            "tier": "RAW",
            "intent": "Position must have a non-null entry price to be graded",
            "condition_expression": "IS NOT NULL",
            "formula_ref": None,
            "referenced_named_values": json.dumps(["position_entry_price"]),
            "parameter_schema": json.dumps({}),
            "null_semantics": "FAIL_CLOSED",
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "rule_key": "ph_current_mark_required",
            "phase": "gate",
            "tier": "RAW",
            "intent": "Position must have a current mark price to be graded",
            "condition_expression": "IS NOT NULL",
            "formula_ref": None,
            "referenced_named_values": json.dumps(["current_position_mark"]),
            "parameter_schema": json.dumps({}),
            "null_semantics": "FAIL_CLOSED",
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "rule_key": "ph_exit_levels_complete",
            "phase": "gate",
            "tier": "RAW",
            "intent": (
                "Full strategy requires complete exit levels "
                "(warning + stop parsed successfully)"
            ),
            "condition_expression": "==",
            "formula_ref": None,
            "referenced_named_values": json.dumps(["position_exit_levels_complete"]),
            "parameter_schema": json.dumps({
                "expected": {"type": "boolean", "default": True},
            }),
            "null_semantics": "FAIL_CLOSED",
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "rule_key": "ph_direction_known",
            "phase": "gate",
            "tier": "RAW",
            "intent": (
                "Full strategy requires a known direction (bullish or bearish) "
                "to interpret exit-level breach semantics"
            ),
            "condition_expression": "IN",
            "formula_ref": None,
            "referenced_named_values": json.dumps(["position_structure_direction"]),
            "parameter_schema": json.dumps({
                "allowed_values": {"type": "array", "default": ["bullish", "bearish"]},
            }),
            "null_semantics": "FAIL_CLOSED",
            "enabled": True,
        },
        # ── Scoring criteria (OTA-745, OTA-746) ──
        {
            "owner_app_id": "OTA",
            "rule_key": "ph_exit_level_safety_score",
            "phase": "scoring",
            "tier": None,
            "intent": (
                "Score position safety relative to exit levels: "
                "0 if stop breached, graduated value approaching warning, "
                "100 when well clear"
            ),
            "condition_expression": None,
            "formula_ref": "formula:exit_level_safety_score",
            "referenced_named_values": json.dumps([
                "warning_breached", "stop_breached",
                "warning_proximity_ratio",
            ]),
            "parameter_schema": json.dumps({
                "proximity_buffer_fraction": {
                    "type": "number",
                    "description": (
                        "Fraction of warning-stop buffer that defines the "
                        "approaching-warning zone"
                    ),
                },
                "warning_breached_score": {
                    "type": "number",
                    "description": "Score when warning is breached but stop is not",
                },
            }),
            "null_semantics": None,
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "rule_key": "ph_pnl_band_score",
            "phase": "scoring",
            "tier": None,
            "intent": (
                "Score from P&L percentage bands — positive P&L scores high, "
                "increasingly negative P&L scores progressively lower"
            ),
            "condition_expression": None,
            "formula_ref": "formula:pnl_band_score",
            "referenced_named_values": json.dumps(["pnl_pct"]),
            "parameter_schema": json.dumps({
                "band_1_threshold": {
                    "type": "number",
                    "description": "P&L threshold between top and second band",
                },
                "band_2_threshold": {
                    "type": "number",
                    "description": "P&L threshold between second and third band",
                },
                "band_3_threshold": {
                    "type": "number",
                    "description": "P&L threshold between third and bottom band",
                },
            }),
            "null_semantics": None,
            "enabled": True,
        },
        # ── Post-scoring adjustments (OTA-747) ──
        {
            "owner_app_id": "OTA",
            "rule_key": "ph_stop_breached_floor",
            "phase": "adjustment",
            "tier": None,
            "intent": (
                "When stop is breached, force final score to a floor value "
                "(default 0 → F band). Categorical guarantee: stop→F."
            ),
            "condition_expression": None,
            "formula_ref": "formula:stop_breached_floor",
            "referenced_named_values": json.dumps(["stop_breached"]),
            "parameter_schema": json.dumps({
                "floor_score": {
                    "type": "number",
                    "description": "Score floor when stop is breached",
                },
            }),
            "null_semantics": None,
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "rule_key": "ph_warning_breached_cap",
            "phase": "adjustment",
            "tier": None,
            "intent": (
                "When warning is breached (and stop is not), cap final score "
                "at a ceiling value (default 24 → D band). "
                "Categorical guarantee: warning→D."
            ),
            "condition_expression": None,
            "formula_ref": "formula:warning_breached_cap",
            "referenced_named_values": json.dumps([
                "warning_breached", "stop_breached",
            ]),
            "parameter_schema": json.dumps({
                "cap_score": {
                    "type": "number",
                    "description": "Score ceiling when warning is breached",
                },
            }),
            "null_semantics": None,
            "enabled": True,
        },
    ]


# ── Junction rows ────────────────────────────────────────────────

def get_junction_rows() -> list[dict]:
    """Return engine_strategy_rule_junction rows for both strategies.

    position_health_full:
        Gates: entry_price, current_mark, exit_levels_complete, direction_known
        Scoring: exit_level_safety_score (0.70), pnl_band_score (0.30)
        Adjustments: stop_breached_floor, warning_breached_cap

    position_health_basic:
        Gates: entry_price, current_mark (no exit-level or direction gates)
        Scoring: pnl_band_score (1.00)
        Adjustments: none
    """
    return [
        # ── position_health_full ─────────────────────────────────
        # Gates
        {
            "strategy_key": STRATEGY_FULL_KEY,
            "rule_key": "ph_entry_price_required",
            "evaluation_order": 1,
            "stop_if_fail": True,
            "score_penalty": None,
            "weight": None,
            "parameters": json.dumps({}),
            "rationale": "Cannot grade without entry price",
            "enabled": True,
            "terminal_verdict": None,
        },
        {
            "strategy_key": STRATEGY_FULL_KEY,
            "rule_key": "ph_current_mark_required",
            "evaluation_order": 2,
            "stop_if_fail": True,
            "score_penalty": None,
            "weight": None,
            "parameters": json.dumps({}),
            "rationale": "Cannot grade without current mark",
            "enabled": True,
            "terminal_verdict": None,
        },
        {
            "strategy_key": STRATEGY_FULL_KEY,
            "rule_key": "ph_exit_levels_complete",
            "evaluation_order": 3,
            "stop_if_fail": True,
            "score_penalty": None,
            "weight": None,
            "parameters": json.dumps({"expected": True}),
            "rationale": (
                "Full strategy requires exit levels. Agent re-runs under "
                "_basic if this gate fails."
            ),
            "enabled": True,
            "terminal_verdict": None,
        },
        {
            "strategy_key": STRATEGY_FULL_KEY,
            "rule_key": "ph_direction_known",
            "evaluation_order": 4,
            "stop_if_fail": True,
            "score_penalty": None,
            "weight": None,
            "parameters": json.dumps({
                "allowed_values": ["bullish", "bearish"],
            }),
            "rationale": (
                "Direction is required to interpret exit-level breach semantics. "
                "Agent re-runs under _basic if this gate fails."
            ),
            "enabled": True,
            "terminal_verdict": None,
        },
        # Scoring
        {
            "strategy_key": STRATEGY_FULL_KEY,
            "rule_key": "ph_exit_level_safety_score",
            "evaluation_order": 10,
            "stop_if_fail": False,
            "score_penalty": None,
            "weight": 0.70,
            "parameters": json.dumps({
                "proximity_buffer_fraction": 0.20,
                "warning_breached_score": 15.0,
            }),
            "rationale": (
                "Exit-level proximity is the dominant signal (~70%) when "
                "exit levels are available. The 20% buffer fraction matches "
                "the legacy health_grade.py:69,79 literal."
            ),
            "enabled": True,
            "terminal_verdict": None,
        },
        {
            "strategy_key": STRATEGY_FULL_KEY,
            "rule_key": "ph_pnl_band_score",
            "evaluation_order": 11,
            "stop_if_fail": False,
            "score_penalty": None,
            "weight": 0.30,
            "parameters": json.dumps({
                "band_1_threshold": -0.10,
                "band_2_threshold": -0.25,
                "band_3_threshold": -0.50,
            }),
            "rationale": (
                "P&L is supplementary (~30%) in the full strategy. Band "
                "thresholds match legacy health_grade.py:106-112."
            ),
            "enabled": True,
            "terminal_verdict": None,
        },
        # Adjustments
        {
            "strategy_key": STRATEGY_FULL_KEY,
            "rule_key": "ph_stop_breached_floor",
            "evaluation_order": 20,
            "stop_if_fail": False,
            "score_penalty": None,
            "weight": None,
            "parameters": json.dumps({
                "floor_score": 0.0,
            }),
            "rationale": (
                "Categorical guarantee: stop breached → F, regardless of "
                "other contributions. Matches health_grade.py:60-61,71-72."
            ),
            "enabled": True,
            "terminal_verdict": None,
        },
        {
            "strategy_key": STRATEGY_FULL_KEY,
            "rule_key": "ph_warning_breached_cap",
            "evaluation_order": 21,
            "stop_if_fail": False,
            "score_penalty": None,
            "weight": None,
            "parameters": json.dumps({
                "cap_score": 25.0,
            }),
            "rationale": (
                "Categorical guarantee: warning breached (not stopped) → D "
                "at best. Cap at 25 (D band floor) ensures score lands in D "
                "or below. When P&L is also catastrophic, raw score may already "
                "be below 25 → F; this is an intentional Option A improvement "
                "over legacy (which always returned D regardless of P&L). "
                "Matches health_grade.py:62-63,73-74 intent."
            ),
            "enabled": True,
            "terminal_verdict": None,
        },
        # ── position_health_basic ────────────────────────────────
        # Gates (fewer — no exit-level or direction requirements)
        {
            "strategy_key": STRATEGY_BASIC_KEY,
            "rule_key": "ph_entry_price_required",
            "evaluation_order": 1,
            "stop_if_fail": True,
            "score_penalty": None,
            "weight": None,
            "parameters": json.dumps({}),
            "rationale": "Cannot grade without entry price",
            "enabled": True,
            "terminal_verdict": None,
        },
        {
            "strategy_key": STRATEGY_BASIC_KEY,
            "rule_key": "ph_current_mark_required",
            "evaluation_order": 2,
            "stop_if_fail": True,
            "score_penalty": None,
            "weight": None,
            "parameters": json.dumps({}),
            "rationale": "Cannot grade without current mark",
            "enabled": True,
            "terminal_verdict": None,
        },
        # Scoring — P&L only, weight 1.0
        {
            "strategy_key": STRATEGY_BASIC_KEY,
            "rule_key": "ph_pnl_band_score",
            "evaluation_order": 10,
            "stop_if_fail": False,
            "score_penalty": None,
            "weight": 1.00,
            "parameters": json.dumps({
                "band_1_threshold": -0.10,
                "band_2_threshold": -0.25,
                "band_3_threshold": -0.50,
            }),
            "rationale": (
                "P&L is the sole criterion (100%) in the basic strategy. "
                "Same band thresholds as _full."
            ),
            "enabled": True,
            "terminal_verdict": None,
        },
        # No adjustments — basic has no exit levels to check
    ]


# ── Lookup rows ──────────────────────────────────────────────────

def get_lookup_rows() -> list[dict]:
    """Return engine_lookups rows for the POSITION_HEALTH verdict domain."""
    return [
        {
            "owner_app_id": "OTA",
            "lookup_set": "position_health_verdicts",
            "lookup_key": "A",
            "payload": json.dumps({"label": "A", "kind": "BAND_VERDICT"}),
            "sort_order": 1,
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "lookup_set": "position_health_verdicts",
            "lookup_key": "B",
            "payload": json.dumps({"label": "B", "kind": "BAND_VERDICT"}),
            "sort_order": 2,
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "lookup_set": "position_health_verdicts",
            "lookup_key": "C",
            "payload": json.dumps({"label": "C", "kind": "BAND_VERDICT"}),
            "sort_order": 3,
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "lookup_set": "position_health_verdicts",
            "lookup_key": "D",
            "payload": json.dumps({"label": "D", "kind": "BAND_VERDICT"}),
            "sort_order": 4,
            "enabled": True,
        },
        {
            "owner_app_id": "OTA",
            "lookup_set": "position_health_verdicts",
            "lookup_key": "F",
            "payload": json.dumps({"label": "F", "kind": "BAND_VERDICT"}),
            "sort_order": 5,
            "enabled": True,
        },
    ]


# ── Convenience: all rows for InMemoryConfigSource ──────────────

def get_all_config_rows() -> dict:
    """Return all config rows grouped by table name.

    Usage with InMemoryConfigSource::

        from app.ota_adapters.position_health.config import get_all_config_rows
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
    strategies = get_strategy_rows()
    rules = get_rule_rows()
    junctions = get_junction_rows()
    lookups = get_lookup_rows()

    # Assign synthetic IDs for InMemoryConfigSource (DB assigns real ones)
    strat_id_start = 200
    rule_id_start = 600

    strategies_with_ids = []
    strat_id_map = {}
    for i, s in enumerate(strategies):
        sid = strat_id_start + i
        strategies_with_ids.append({**s, "strategy_id": sid})
        strat_id_map[s["strategy_key"]] = sid

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
            "strategy_id": strat_id_map[j["strategy_key"]],
            "rule_id": rule_id_map[j["rule_key"]],
        })

    return {
        "apps": [
            {"app_id": "SHARED", "name": "Shared", "enabled": True},
            {"app_id": "OTA", "name": "OTA", "enabled": True},
        ],
        "rules": rules_with_ids,
        "strategies": strategies_with_ids,
        "junction": junctions_with_ids,
        "lookups": lookups,
    }
