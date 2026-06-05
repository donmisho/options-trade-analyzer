"""
OTA-791 — loader ``include_draft_key`` flag + restart-only invariant.

The preview path admits exactly ONE named ``status=draft`` (``enabled=0``)
strategy into a LOCAL config via ``load_config(include_draft_key=...)``. This
must (a) admit only that one key — never a blanket include-disabled, and (b)
never mutate the running engine runtime (insight_engine.md §6.5 restart-only).
"""

from __future__ import annotations

import json

from app.insight_engine import InMemoryConfigSource, load_config
from app.ota_adapters import engine_runtime


_BANDS = json.dumps([{"verdict": "PASS", "min_score": 0, "max_score": 100}])


def _strategy_row(strategy_id: int, key: str, *, enabled: bool) -> dict:
    return {
        "strategy_id": strategy_id,
        "owner_app_id": "OTA",
        "strategy_key": key,
        "display_name": key.replace("_", " ").title(),
        "consumer_surface": "SCREENING",
        "description": None,
        "compatible_structures": None,
        "verdict_band_set": _BANDS,
        "dte_min": None,
        "dte_max": None,
        "status": "draft" if not enabled else "active",
        "enabled": enabled,
    }


def _source() -> InMemoryConfigSource:
    return InMemoryConfigSource(
        apps=[{"app_id": "OTA", "name": "OTA", "status": "active"}],
        strategies=[
            _strategy_row(1, "steady_paycheck", enabled=True),
            _strategy_row(2, "steady_paycheck__draft", enabled=False),
            _strategy_row(3, "other_disabled", enabled=False),
        ],
    )


def test_default_load_excludes_all_disabled():
    config = load_config(_source())
    assert "steady_paycheck" in config.rule_sets
    assert "steady_paycheck__draft" not in config.rule_sets
    assert "other_disabled" not in config.rule_sets


def test_include_draft_key_admits_only_the_named_draft():
    config = load_config(_source(), include_draft_key="steady_paycheck__draft")
    # The named draft is admitted...
    assert "steady_paycheck__draft" in config.rule_sets
    assert "steady_paycheck__draft" in config.strategies
    # ...the live strategy still loads...
    assert "steady_paycheck" in config.rule_sets
    # ...but NO other disabled strategy leaks in (not a blanket include-disabled).
    assert "other_disabled" not in config.rule_sets


def test_include_draft_key_for_absent_draft_is_noop():
    config = load_config(_source(), include_draft_key="does_not_exist__draft")
    assert "does_not_exist__draft" not in config.rule_sets
    assert "other_disabled" not in config.rule_sets


def test_preview_load_does_not_mutate_running_runtime():
    """A draft-inclusive load must not touch the hydrated runtime (restart-only)."""
    sentinel = object()
    engine_runtime._runtime = sentinel  # stand in for a hydrated runtime
    try:
        config = load_config(_source(), include_draft_key="steady_paycheck__draft")
        # The local preview config exists...
        assert config.config_version
        # ...and the runtime holder is byte-identical (no set_engine_runtime call).
        assert engine_runtime.get_engine_runtime() is sentinel
    finally:
        engine_runtime._reset_engine_runtime()
