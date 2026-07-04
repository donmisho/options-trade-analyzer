"""OTA-847 — screening seed ↔ options-chain adapter named-value parity.

Regression guard for the three seed-only mismatches OTA-847 reconciled against
the options-chain adapter catalog (insight_engine.md §6.6 / §5.1 — the adapter
catalog is the sole source of truth for screening named-value names + units; the
seed conforms to it, never the reverse):

  #2  the ``cushion_vs_atr`` gate references the adapter's ``cushion_vs_atr``
      (not the OTA-832 ``cushion_vs_atr_ratio`` phantom, which no producer emits);
  #3  the ``cushion_of_price`` gate bounds are in PERCENT (the adapter emits
      ``cushion_pct`` ×100), so SP={1.0, 100.0} / WG={1.5, 100.0};
  #4  ``earnings_buffer_past_expiry`` (which references the unproduced
      ``earnings_days_past_expiry``) is disabled — descoped to OTA-849.

Mismatch #1 (data_completeness_delta / delta_quality) is carved to a follow-up
and is deliberately NOT asserted here: ``delta`` IS in the adapter catalog, so it
is not name-drift. The #1 defect is that the adapter does not populate ``delta``
for spread candidates at runtime (it emits long_delta/short_delta) — out of scope
for this seed-only parity guard.

This lives in its own file (per the OTA-847 prompt) to avoid colliding with
OTA-843's edits to ``test_options_chain_adapter.py``.
"""

from __future__ import annotations

import pytest

from app.ota_adapters.options_chain.adapter import _CATALOG
from scripts.seed_engine_config import DEFAULT_XLSX, build_all_rows

pytestmark = pytest.mark.skipif(
    not DEFAULT_XLSX.exists(),
    reason=f"seed workbook not available at {DEFAULT_XLSX}",
)

# Named values referenced by ENABLED screening rules that the options-chain
# adapter does not catalog, and that OTA-847 does NOT address (pre-existing,
# tracked separately): the stock-extension adjustment input and the LT
# theta-load gate input. Listed so the parity test below is precise rather than
# brittle — it asserts the missing set is EXACTLY these, so a regression of #2 or
# #4 (which would re-introduce cushion_vs_atr_ratio / earnings_days_past_expiry)
# fails loudly while these known out-of-scope gaps don't mask it.
KNOWN_OUT_OF_SCOPE_GAPS = {"stock_extension_pct", "theta_load_fraction"}


@pytest.fixture(scope="module")
def seed():
    rules, strategies, junctions, _lookups, _ = build_all_rows(DEFAULT_XLSX)
    screening = {
        s["strategy_key"] for s in strategies
        if s.get("consumer_surface") == "SCREENING"
    }
    return {
        "rules": rules,
        "junctions": junctions,
        "screening": screening,
        "rule_by_key": {r["rule_key"]: r for r in rules},
    }


def _enabled_screening_rule_keys(seed) -> set[str]:
    """Rule keys bound by an enabled junction to an enabled screening strategy rule."""
    return {
        j["rule_key"]
        for j in seed["junctions"]
        if j["strategy_key"] in seed["screening"] and j.get("enabled", True)
        and seed["rule_by_key"].get(j["rule_key"], {}).get("enabled", True)
    }


# ── #2: cushion_vs_atr gate name ─────────────────────────────────────────


def test_cushion_vs_atr_gate_references_adapter_name(seed):
    rule = seed["rule_by_key"]["cushion_vs_atr"]
    assert rule["referenced_named_values"] == ["cushion_vs_atr"]
    assert "cushion_vs_atr" in _CATALOG


def test_cushion_vs_atr_ratio_phantom_unreferenced(seed):
    """The OTA-832 phantom is gone from every enabled screening rule + the catalog."""
    assert "cushion_vs_atr_ratio" not in _CATALOG
    for rk in _enabled_screening_rule_keys(seed):
        refs = seed["rule_by_key"][rk].get("referenced_named_values") or []
        assert "cushion_vs_atr_ratio" not in refs, rk


# ── #3: cushion_of_price bounds in percent ───────────────────────────────


def test_cushion_of_price_bounds_are_percent(seed):
    """Gate bounds match the adapter's percent ``cushion_pct`` (was fraction)."""
    expected = {
        "steady-paycheck": {"low": 1.0, "high": 100.0},
        "weekly-grind": {"low": 1.5, "high": 100.0},
    }
    seen = {}
    for j in seed["junctions"]:
        if j["rule_key"] != "cushion_of_price":
            continue
        seen[j["strategy_key"]] = {
            "low": j["parameters"]["low"], "high": j["parameters"]["high"]
        }
    assert seen == expected


# ── #4: earnings_days_past_expiry descoped ───────────────────────────────


def test_earnings_buffer_gate_disabled(seed):
    rule = seed["rule_by_key"]["earnings_buffer_past_expiry"]
    assert rule["enabled"] is False
    junc = [j for j in seed["junctions"] if j["rule_key"] == "earnings_buffer_past_expiry"]
    assert junc, "expected earnings_buffer_past_expiry junctions to still exist (disabled)"
    assert all(j["enabled"] is False for j in junc)


def test_earnings_days_past_expiry_unreferenced_by_enabled(seed):
    assert "earnings_days_past_expiry" not in _CATALOG
    for rk in _enabled_screening_rule_keys(seed):
        refs = seed["rule_by_key"][rk].get("referenced_named_values") or []
        assert "earnings_days_past_expiry" not in refs, rk


# ── Parity: enabled screening rules reference only catalogued names ───────
# (except the documented, out-of-scope gaps — #1 `delta` IS catalogued)


def test_enabled_screening_names_in_catalog_except_known_gaps(seed):
    catalog = set(_CATALOG)
    missing: set[str] = set()
    for rk in _enabled_screening_rule_keys(seed):
        for nv in seed["rule_by_key"][rk].get("referenced_named_values") or []:
            if nv not in catalog:
                missing.add(nv)
    # A regression of #2 / #4 would re-introduce cushion_vs_atr_ratio /
    # earnings_days_past_expiry here; #1 `delta` must NOT appear (it is catalogued).
    assert "delta" not in missing
    assert missing == KNOWN_OUT_OF_SCOPE_GAPS, (
        f"unexpected seed↔catalog name drift: {missing - KNOWN_OUT_OF_SCOPE_GAPS}"
    )
