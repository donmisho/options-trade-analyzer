"""OTA-850 — structure-aware delta-completeness regression anchor.

Locks in the SP/TR half of the "Trades returns no recommendations" fix so the
delta-completeness gate can never silently re-close on spread candidates. Before
OTA-850 the shared ``data_completeness_delta`` gate (``IS NOT NULL`` over
``delta``, ``stop_if_fail``) halted every steady-paycheck and trend-rider spread
at order 140 — the options-chain adapter emits ``long_delta``/``short_delta`` for
spreads and never ``delta`` — so no spread ever reached a verdict.

OTA-850 rebinds the gate structure-aware (keyed off ``compatible_structures``, no
strategy-id branch):
  * steady-paycheck (pure credit spread) → ``short_delta`` sibling;
  * trend-rider (pure debit spread) → ``long_delta`` sibling + ``delta_quality``
    reads ``long_delta`` via its ``delta_source`` junction param;
  * weekly-grind (mixed) → delta-completeness dropped;
  * lottery-ticket (naked-bearing) → keeps the ``delta`` gate unchanged.

These run the **real** engine + rule libraries + seeded config through the same
offline ``build_all_rows`` boot as ``test_full_seed_boot`` / the cross-consumer
suite. A faithful spread supplies only its leg deltas (no ``delta``), proving the
fix rather than papering over it.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from app.insight_engine import Candidate, Phase, VerdictSource, evaluate
from app.ota_adapters.options_chain.adapter import (
    OptionsChainAdapter,
    _compute_derived as _screening_compute_derived,
    _compute_post_context_derived as _screening_post_context_derived,
)

from tests.insight_engine import cross_consumer_harness as harness

pytestmark = pytest.mark.skipif(
    not harness.SEED_WORKBOOK_AVAILABLE,
    reason=f"seed workbook not available at {harness.__name__}.DEFAULT_XLSX",
)

# Hydrate the complete seed + registry once (the live mixed-surface boot, offline).
_CONFIG = harness.build_seeded_config() if harness.SEED_WORKBOOK_AVAILABLE else None
_REGISTRY = harness.get_combined_registry() if harness.SEED_WORKBOOK_AVAILABLE else None

_DELTA_GATES = {
    "data_completeness_delta",
    "data_completeness_long_delta",
    "data_completeness_short_delta",
}


def _run(strategy_key: str, candidate: Candidate):
    """Run one candidate through the real engine for a screening strategy."""
    return evaluate(
        candidates=[candidate],
        strategy_key=strategy_key,
        source_app_id=harness.SOURCE_APP_ID,
        config=_CONFIG,
        registry=_REGISTRY,
        adapter=OptionsChainAdapter(),
        null_semantics=harness.SCREENING_NULL_SEMANTICS,
    )[0]


def _trend_rider_debit_candidate() -> Candidate:
    """A healthy bull_call debit spread that flows through every trend-rider gate.

    Real RAW + DERIVED from ``_compute_derived``; market context mirrors what
    ``_fetch_market_context`` would stamp (BULLISH alignment → chart_state matches
    the bullish trade direction). Deliberately supplies only ``long_delta`` /
    ``short_delta`` — never ``delta`` — so passing data-completeness proves the
    ``long_delta`` sibling reads the adapter's real leg delta.
    """
    exp = (date.today() + timedelta(days=35)).isoformat()  # DTE inside 30–45
    nv: dict[str, Any] = {
        "underlying_price": 200.0,
        "spread_type": "bull_call",
        "option_type": "call",
        "expiration": exp,
        "long_strike": 200.0,
        "short_strike": 210.0,
        "spread_width": 10.0,
        "long_bid": 3.10, "long_ask": 3.20,
        "short_bid": 1.15, "short_ask": 1.25,
        "long_delta": 0.55, "short_delta": 0.35,
        "long_theta": -0.03, "short_theta": 0.02,
        "long_gamma": 0.01, "short_gamma": 0.02,
        "long_vega": 0.10, "short_vega": 0.12,
        "long_volume": 800, "short_volume": 800,
        "long_oi": 4000, "short_oi": 4000,
        "long_iv": 0.28, "short_iv": 0.30,
        "next_earnings_date": None,
    }
    candidate = Candidate(
        candidate_id="tr-debit-pass",
        candidate_type="options_trade",
        symbol="TEST",
        subject_type="TRADE_CANDIDATE",
        named_values=nv,
    )
    _screening_compute_derived(candidate)
    nv.update({
        "sma_8": 205.0, "sma_21": 203.0, "sma_50": 198.0,
        "sma_alignment": "BULLISH", "chart_state": "Bullish",
        "atr_14": 2.0, "atm_iv": 0.28, "iv_percentile": 55.0,
        "is_etf": False,
    })
    _screening_post_context_derived([candidate])
    return candidate


# ── SP: credit spread reaches a verdict via short_delta ───────────────────


def test_sp_credit_spread_reaches_verdict_via_short_delta():
    candidate = harness.screening_passing_candidate()
    # A faithful spread carries long_delta/short_delta but never plain `delta`.
    assert "delta" not in candidate.named_values
    assert candidate.named_values.get("short_delta") is not None

    r = _run(harness.SCREENING_STRATEGY, candidate)

    assert r.terminal_phase == "verdict"
    assert isinstance(r.verdict, str) and r.verdict
    assert r.verdict_source == VerdictSource.BAND_LOOKUP
    assert all(not g.was_terminal for g in r.gate_decisions)

    gate_keys = {g.rule_key for g in r.gate_decisions}
    assert "data_completeness_short_delta" in gate_keys
    assert "data_completeness_delta" not in gate_keys
    sd = next(g for g in r.gate_decisions if g.rule_key == "data_completeness_short_delta")
    assert sd.passed and not sd.was_terminal


# ── TR: debit spread reaches a verdict via long_delta + scored delta_quality ─


def test_tr_debit_spread_reaches_verdict_via_long_delta():
    candidate = _trend_rider_debit_candidate()
    assert "delta" not in candidate.named_values
    assert candidate.named_values.get("long_delta") is not None

    r = _run("trend-rider", candidate)

    assert r.terminal_phase == "verdict"
    assert isinstance(r.verdict, str) and r.verdict
    assert r.verdict_source == VerdictSource.BAND_LOOKUP
    assert all(not g.was_terminal for g in r.gate_decisions)

    gate_keys = {g.rule_key for g in r.gate_decisions}
    assert "data_completeness_long_delta" in gate_keys
    assert "data_completeness_delta" not in gate_keys
    ld = next(g for g in r.gate_decisions if g.rule_key == "data_completeness_long_delta")
    assert ld.passed and not ld.was_terminal


def test_tr_delta_quality_scores_from_long_delta_not_null():
    """delta_quality reads long_delta via delta_source → a real, non-zero score
    (a null→0 collapse would score 0 against the 0.60 center)."""
    r = _run("trend-rider", _trend_rider_debit_candidate())
    dq = next(s for s in r.scoring_breakdown if s.rule_key == "delta_quality")
    assert dq.raw_value > 0.0


# ── Config-shape invariants: WG dropped, LT unchanged ─────────────────────


def _gate_rule_keys(strategy_key: str) -> set[str]:
    rule_set = _CONFIG.rule_sets[strategy_key]
    return {b.rule.rule_key for b in rule_set.bindings if b.rule.phase is Phase.GATE}


def test_wg_mixed_drops_delta_completeness():
    assert not (_gate_rule_keys("weekly-grind") & _DELTA_GATES)


def test_lt_naked_keeps_plain_delta_completeness():
    keys = _gate_rule_keys("lottery-ticket")
    assert "data_completeness_delta" in keys
    assert "data_completeness_long_delta" not in keys
    assert "data_completeness_short_delta" not in keys
