"""
OTA-790 — EngineConfig.loadable_version semantics.

``loadable_version`` is the hash OTA-790 compares (startup stamp vs. on-demand
recompute) to decide ``restart_pending``. It must hash ONLY what the engine
actually loads, so:

  - a transient draft (status=draft ⇒ enabled=0) must NOT move it (else the
    banner false-positives whenever a draft exists), while ``config_version``
    (raw-row hash) DOES move — the two are deliberately different populations;
  - a real live change (a junction parameter, a header field) MUST move it.
"""

from __future__ import annotations

import json

from app.insight_engine import InMemoryConfigSource, load_config

_BANDS = json.dumps([{"verdict": "PASS", "min_score": 0, "max_score": 100}])


def _strategy(strategy_id: int, key: str, *, enabled: bool, dte_min=None) -> dict:
    return {
        "strategy_id": strategy_id,
        "owner_app_id": "OTA",
        "strategy_key": key,
        "display_name": key.replace("_", " ").title(),
        "consumer_surface": "SCREENING",
        "description": None,
        "compatible_structures": None,
        "verdict_band_set": _BANDS,
        "dte_min": dte_min,
        "dte_max": None,
        "status": "draft" if not enabled else "active",
        "enabled": enabled,
    }


def _rule(rule_id: int = 10) -> dict:
    return {
        "rule_id": rule_id,
        "owner_app_id": "OTA",
        "rule_key": "delta_band",
        "phase": "gate",
        "tier": "RAW",
        "intent": "Delta floor",
        "condition_expression": ">=",
        "formula_ref": None,
        "referenced_named_values": json.dumps(["delta"]),
        "parameter_schema": json.dumps({"threshold": {"type": "number"}}),
        "null_semantics": None,
        "enabled": True,
    }


def _junction(strategy_id: int, *, threshold: float, enabled: bool = True) -> dict:
    return {
        "strategy_id": strategy_id,
        "rule_id": 10,
        "evaluation_order": 1,
        "stop_if_fail": True,
        "score_penalty": None,
        "weight": None,
        "parameters": json.dumps({"threshold": threshold}),
        "terminal_verdict": None,
        "rationale": None,
        "enabled": enabled,
    }


def _source(strategies, junction) -> InMemoryConfigSource:
    return InMemoryConfigSource(
        apps=[{"app_id": "OTA", "name": "OTA", "status": "active"}],
        rules=[_rule()],
        strategies=strategies,
        junction=junction,
    )


def test_draft_does_not_move_loadable_version_but_moves_config_version():
    live_only = _source(
        [_strategy(1, "steady_paycheck", enabled=True)],
        [_junction(1, threshold=0.2)],
    )
    with_draft = _source(
        [
            _strategy(1, "steady_paycheck", enabled=True),
            _strategy(2, "steady_paycheck__draft", enabled=False),
        ],
        [
            _junction(1, threshold=0.2),
            _junction(2, threshold=0.9),  # draft edit — not loaded
        ],
    )

    base = load_config(live_only)
    drafted = load_config(with_draft)

    # The draft + its junction are excluded from the loadable set → no change.
    assert drafted.loadable_version == base.loadable_version
    # …but config_version hashes raw rows incl. the draft → it DOES change. This
    # is exactly why OTA-790 compares loadable_version, not config_version.
    assert drafted.config_version != base.config_version


def test_live_junction_change_moves_loadable_version():
    base = load_config(
        _source([_strategy(1, "steady_paycheck", enabled=True)], [_junction(1, threshold=0.2)])
    )
    changed = load_config(
        _source([_strategy(1, "steady_paycheck", enabled=True)], [_junction(1, threshold=0.5)])
    )
    assert changed.loadable_version != base.loadable_version


def test_live_header_change_moves_loadable_version():
    base = load_config(
        _source([_strategy(1, "steady_paycheck", enabled=True)], [_junction(1, threshold=0.2)])
    )
    changed = load_config(
        _source(
            [_strategy(1, "steady_paycheck", enabled=True, dte_min=21)],
            [_junction(1, threshold=0.2)],
        )
    )
    assert changed.loadable_version != base.loadable_version
