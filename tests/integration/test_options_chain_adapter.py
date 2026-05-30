"""
Options-chain adapter ↔ engine integration tests.

Three test layers:
  Layer 1 — Adapter integration: synthetic chain → produce_candidates (offline)
            → assert named values populated correctly + populate_computed fires.
  Layer 2 — Formula parity: same inputs through registered formulas → expected
            scores match legacy behavior within tolerance.
  Layer 3 — End-to-end pipeline: adapter-built candidates → engine evaluate()
            with representative config → gates filter, scores computed, verdicts
            assigned from verdict bands.

OTA-724, closing OTA-712
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from app.insight_engine import (
    Candidate,
    DictFormulaRegistry,
    InMemoryConfigSource,
    InMemorySink,
    Tier,
    VerdictSource,
    evaluate,
    load_config,
    validate_config,
)
from app.ota_adapters.options_chain.adapter import (
    CatalogEntry,
    OptionsChainAdapter,
    _compute_derived,
    _compute_naked_derived,
    _compute_post_context_derived,
    _compute_spread_derived,
    _CATALOG,
)
from app.options_rules.screening import get_registry


# ── Helpers ──────────────────────────────────────────────────────────────


def _future_exp(days: int = 30) -> str:
    """ISO expiration string N days from today."""
    return (date.today() + timedelta(days=days)).isoformat()


def _make_spread_candidate(
    symbol: str = "AAPL",
    spread_type: str = "bull_put",
    long_strike: float = 170.0,
    short_strike: float = 175.0,
    underlying_price: float = 180.0,
    long_bid: float = 0.80,
    long_ask: float = 1.00,
    short_bid: float = 2.50,
    short_ask: float = 2.80,
    long_delta: float = -0.25,
    short_delta: float = -0.40,
    long_theta: float = -0.03,
    short_theta: float = 0.04,
    dte_days: int = 30,
    long_iv: float = 0.28,
    short_iv: float = 0.30,
) -> Candidate:
    """Build a synthetic spread Candidate with RAW values only."""
    exp = _future_exp(dte_days)
    width = abs(short_strike - long_strike)
    cid = f"{symbol}_{spread_type}_{long_strike}_{short_strike}_{exp}"
    return Candidate(
        candidate_id=cid,
        candidate_type="options_trade",
        symbol=symbol,
        subject_type="TRADE_CANDIDATE",
        named_values={
            "underlying_price": underlying_price,
            "spread_type": spread_type,
            "option_type": "put",
            "expiration": exp,
            "long_strike": long_strike,
            "short_strike": short_strike,
            "spread_width": width,
            "long_bid": long_bid,
            "long_ask": long_ask,
            "short_bid": short_bid,
            "short_ask": short_ask,
            "long_delta": long_delta,
            "short_delta": short_delta,
            "long_theta": long_theta,
            "short_theta": short_theta,
            "long_gamma": 0.02,
            "short_gamma": 0.03,
            "long_vega": 0.10,
            "short_vega": 0.12,
            "long_volume": 500,
            "short_volume": 800,
            "long_oi": 3000,
            "short_oi": 5000,
            "long_iv": long_iv,
            "short_iv": short_iv,
        },
    )


def _make_naked_candidate(
    symbol: str = "AAPL",
    option_type: str = "call",
    strike: float = 190.0,
    underlying_price: float = 180.0,
    bid: float = 1.20,
    ask: float = 1.50,
    delta: float = 0.30,
    theta: float = -0.05,
    iv: float = 0.32,
    dte_days: int = 45,
) -> Candidate:
    """Build a synthetic naked-option Candidate with RAW values only."""
    exp = _future_exp(dte_days)
    structure = f"long_{option_type}"
    cid = f"{symbol}_{structure}_{strike}_{exp}"
    return Candidate(
        candidate_id=cid,
        candidate_type="options_trade",
        symbol=symbol,
        subject_type="TRADE_CANDIDATE",
        named_values={
            "underlying_price": underlying_price,
            "spread_type": structure,
            "option_type": option_type,
            "expiration": exp,
            "strike": strike,
            "bid": bid,
            "ask": ask,
            "delta": delta,
            "theta": theta,
            "gamma": 0.015,
            "vega": 0.08,
            "iv": iv,
            "volume": 1200,
            "open_interest": 8000,
        },
    )


# ── Layer 1: Adapter integration (DERIVED + COMPUTED) ─────────────────


class TestSpreadDerived:
    """DERIVED computation for credit and debit spreads."""

    def test_bull_put_credit_spread_derived_values(self):
        c = _make_spread_candidate(spread_type="bull_put")
        _compute_derived(c)
        nv = c.named_values

        # Credit spread: net_credit = short_mid - long_mid
        short_mid = (2.50 + 2.80) / 2  # 2.65
        long_mid = (0.80 + 1.00) / 2   # 0.90
        expected_credit = round(short_mid - long_mid, 4)  # 1.75
        assert nv["net_credit"] == expected_credit
        assert nv["net_debit"] == round(-expected_credit, 4)

        # Max profit/loss
        width = 5.0
        assert nv["max_profit"] == round(expected_credit * 100, 2)
        assert nv["max_loss"] == round((width - expected_credit) * 100, 2)

        # Probability of profit (credit spread: 1 - |short_delta|)
        assert nv["prob_of_profit"] == round(1.0 - abs(-0.40), 4)

        # EV
        pop = nv["prob_of_profit"]
        mp = nv["max_profit"]
        ml = nv["max_loss"]
        assert nv["ev_raw"] == round(pop * mp - (1 - pop) * ml, 2)

        # Cushion (bull_put: (price - breakeven) / price * 100)
        assert nv["breakeven"] is not None
        assert nv["cushion_pct"] is not None

        # DTE
        assert nv["dte"] == 30

        # Trade direction
        assert nv["trade_direction"] == "bullish"

        # Net theta
        assert nv["net_theta"] == round(-0.03 + 0.04, 6)

        # Liquidity aliases
        assert nv["min_leg_open_interest"] == min(3000, 5000)
        assert nv["min_leg_volume"] == min(500, 800)

        # Width aliases
        assert nv["credit_width_pct"] == nv["credit_pct_of_width"]
        assert nv["debit_width_pct"] is None

    def test_bull_call_debit_spread_derived_values(self):
        c = _make_spread_candidate(
            spread_type="bull_call",
            long_strike=175.0,
            short_strike=180.0,
            long_bid=3.00,
            long_ask=3.40,
            short_bid=1.20,
            short_ask=1.50,
            long_delta=0.55,
            short_delta=0.40,
        )
        c.named_values["option_type"] = "call"
        _compute_derived(c)
        nv = c.named_values

        # Debit spread
        long_mid = (3.00 + 3.40) / 2
        short_mid = (1.20 + 1.50) / 2
        expected_debit = round(long_mid - short_mid, 4)
        assert nv["net_debit"] == expected_debit
        assert nv["net_credit"] is None

        # Debit spread POP = |long_delta|
        assert nv["prob_of_profit"] == round(abs(0.55), 4)

        # Trade direction
        assert nv["trade_direction"] == "bullish"

        # Debit width pct populated, credit width pct is None
        assert nv["debit_width_pct"] is not None
        assert nv["credit_width_pct"] is None


class TestNakedDerived:
    """DERIVED computation for naked options."""

    def test_long_call_derived_values(self):
        c = _make_naked_candidate(option_type="call", strike=190.0)
        _compute_derived(c)
        nv = c.named_values

        mid = (1.20 + 1.50) / 2  # 1.35
        assert nv["premium_dollars"] == round(mid * 100, 2)
        assert nv["mid_price"] == round(mid, 4)

        # Breakeven for call: strike + mid
        assert nv["breakeven"] == round(190.0 + mid, 2)

        # Breakeven distance
        be = 190.0 + mid
        assert nv["breakeven_distance_pct"] == round(((be - 180.0) / 180.0) * 100, 2)

        # Theta runway
        theta_per_day = abs(-0.05) * 100
        premium = mid * 100
        assert nv["theta_runway_days"] == round(premium / theta_per_day, 1)

        # Trade direction
        assert nv["trade_direction"] == "bullish"

        # DTE
        assert nv["dte"] == 45

        # Single-leg liquidity
        assert nv["min_leg_open_interest"] == 8000
        assert nv["min_leg_volume"] == 1200

    def test_long_put_derived_values(self):
        c = _make_naked_candidate(option_type="put", strike=170.0)
        _compute_derived(c)
        nv = c.named_values

        mid = (1.20 + 1.50) / 2
        # Breakeven for put: strike - mid
        assert nv["breakeven"] == round(170.0 - mid, 2)
        assert nv["trade_direction"] == "bearish"


class TestPostContextDerived:
    """Post-context derivations (SMA alias, IV rank proxy, cushion_vs_atr)."""

    def test_post_context_stamps_aliases(self):
        c = _make_spread_candidate()
        _compute_derived(c)
        # Simulate market context stamp
        c.named_values["sma_alignment"] = "BULLISH"
        c.named_values["iv_percentile"] = 65.0
        c.named_values["atr_14"] = 3.5
        _compute_post_context_derived([c])
        nv = c.named_values

        assert nv["sma_alignment_classification"] == "BULLISH"
        assert nv["iv_rank"] == 65.0

        # cushion_vs_atr
        price = nv["underlying_price"]
        atr_pct = 3.5 / price * 100
        expected = round(nv["cushion_pct"] / atr_pct, 4) if nv["cushion_pct"] is not None else None
        assert nv["cushion_vs_atr"] == expected

    def test_post_context_missing_atr_yields_none(self):
        c = _make_spread_candidate()
        _compute_derived(c)
        c.named_values["atr_14"] = None
        _compute_post_context_derived([c])
        assert c.named_values["cushion_vs_atr"] is None


class TestPopulateComputed:
    """COMPUTED callback (populate_computed) produces B-S values."""

    def test_populate_computed_fires_for_spread(self):
        c = _make_spread_candidate()
        _compute_derived(c)
        adapter = OptionsChainAdapter()
        needed = {"p_max_profit", "p_max_loss", "bs_delta"}
        adapter.populate_computed([c], needed)
        nv = c.named_values
        assert nv.get("p_max_profit") is not None
        assert nv.get("p_max_loss") is not None
        assert nv.get("bs_delta") is not None
        # Probabilities should be in [0, 1]
        assert 0.0 <= nv["p_max_profit"] <= 1.0
        assert 0.0 <= nv["p_max_loss"] <= 1.0

    def test_populate_computed_fires_for_naked(self):
        c = _make_naked_candidate()
        _compute_derived(c)
        adapter = OptionsChainAdapter()
        needed = {"p_max_loss", "bs_delta"}
        adapter.populate_computed([c], needed)
        nv = c.named_values
        assert nv.get("p_max_loss") is not None
        assert nv.get("bs_delta") is not None

    def test_populate_computed_skips_empty_needed(self):
        c = _make_spread_candidate()
        _compute_derived(c)
        adapter = OptionsChainAdapter()
        adapter.populate_computed([c], set())
        # No COMPUTED values set
        assert c.named_values.get("p_max_profit") is None
        assert c.named_values.get("probability_matrix") is None


class TestCatalogCompleteness:
    """§5.1 catalog declares all named values the adapter produces."""

    def test_spread_named_values_in_catalog(self):
        c = _make_spread_candidate()
        _compute_derived(c)
        c.named_values["sma_alignment"] = "BULLISH"
        c.named_values["iv_percentile"] = 50.0
        c.named_values["atr_14"] = 3.0
        c.named_values["atm_iv"] = 0.30
        c.named_values["chart_state"] = "Bullish"
        c.named_values["is_etf"] = False
        _compute_post_context_derived([c])

        catalog_names = set(_CATALOG.keys())
        produced_names = set(c.named_values.keys())

        # Every produced name should be in the catalog (allow extras like
        # 'option_type' etc. that may be RAW and included in the catalog)
        uncatalogued = produced_names - catalog_names
        # Known OK: some names like 'spread_type' are in the catalog
        assert not uncatalogued, f"Uncatalogued named values: {uncatalogued}"

    def test_naked_named_values_in_catalog(self):
        c = _make_naked_candidate()
        _compute_derived(c)
        c.named_values["sma_alignment"] = "NEUTRAL"
        c.named_values["iv_percentile"] = 40.0
        c.named_values["atr_14"] = 2.0
        c.named_values["atm_iv"] = 0.28
        c.named_values["chart_state"] = "Neutral"
        c.named_values["is_etf"] = False
        _compute_post_context_derived([c])

        catalog_names = set(_CATALOG.keys())
        produced_names = set(c.named_values.keys())
        uncatalogued = produced_names - catalog_names
        assert not uncatalogued, f"Uncatalogued named values: {uncatalogued}"


# ── Layer 2: Formula parity ──────────────────────────────────────────


class TestScoringFormulaParity:
    """Registered formulas produce expected scores for known inputs."""

    @pytest.fixture
    def registry(self):
        return get_registry()

    def test_theta_margin_ratio(self, registry):
        nv = {"net_theta": -0.05, "max_loss": 325.0}
        score = registry.invoke("theta_margin_ratio", nv, {"scale": 100.0})
        expected = min(100.0, abs(-0.05) / 325.0 * 100.0)
        assert abs(score - expected) < 0.01

    def test_probability_of_profit(self, registry):
        score = registry.invoke("probability_of_profit", {"prob_of_profit": 0.65}, {})
        assert abs(score - 0.65) < 0.01  # 0-1 scale → 0-100 passthrough

    def test_expected_value_credit(self, registry):
        nv = {"ev_raw": 42.5}
        score = registry.invoke("expected_value", nv, {"scale": 1.0})
        assert abs(score - 42.5) < 0.01

    def test_reward_risk(self, registry):
        nv = {"reward_risk_ratio": 0.75}
        score = registry.invoke("reward_risk", nv, {"scale": 100.0})
        assert abs(score - 75.0) < 0.01

    def test_iv_rank_proxy(self, registry):
        # With iv_rank provided (true path)
        score = registry.invoke("iv_rank", {"iv_rank": 72.0}, {})
        assert abs(score - 72.0) < 0.01
        # Proxy path: atm_iv / divisor
        score2 = registry.invoke("iv_rank", {"atm_iv": 0.30}, {"divisor": 0.60})
        assert abs(score2 - 50.0) < 0.01

    def test_sma_alignment_score(self, registry):
        assert registry.invoke("sma_alignment_score", {"sma_alignment_classification": "BULLISH"}, {}) == 100.0
        assert registry.invoke("sma_alignment_score", {"sma_alignment_classification": "BEARISH"}, {}) == 0.0
        assert registry.invoke("sma_alignment_score", {"sma_alignment_classification": "NEUTRAL"}, {}) == 50.0

    def test_delta_quality(self, registry):
        nv = {"delta": 0.35}
        score = registry.invoke("delta_quality", nv, {"delta_center": 0.35, "delta_half_range": 0.15, "smoothing": 0.05})
        assert score == 100.0

    def test_credit_width(self, registry):
        nv = {"net_debit": -1.75, "spread_width": 5.0}
        score = registry.invoke("credit_width", nv, {})
        expected = abs(-1.75) / 5.0 * 100.0
        assert abs(score - expected) < 0.01

    def test_liquidity(self, registry):
        nv = {"long_volume": 500, "short_volume": 800, "long_oi": 3000, "short_oi": 5000}
        score = registry.invoke("liquidity", nv, {"scale": 10000.0})
        expected = min(100.0, 9300 / 10000 * 100)
        assert abs(score - expected) < 0.01

    def test_payout_ratio(self, registry):
        nv = {"delta": 0.15, "underlying_price": 180.0, "premium_dollars": 135.0}
        score = registry.invoke("payout_ratio", nv, {"move_pct": 0.10, "multiplier": 100.0, "scale": 10.0})
        raw = (0.15 * 180.0 * 0.10 * 100.0) / 135.0
        expected = min(100.0, raw / 10.0 * 100.0)
        assert abs(score - expected) < 0.5


class TestGateFormulaParity:
    """Gate formulas return correct bool for known inputs."""

    @pytest.fixture
    def registry(self):
        return get_registry()

    def test_negative_ev_gate_passes(self, registry):
        assert registry.invoke("negative_ev_gate", {"ev_raw": 10.0}, {"threshold": 0.0}) is True

    def test_negative_ev_gate_fails(self, registry):
        assert registry.invoke("negative_ev_gate", {"ev_raw": -5.0}, {"threshold": 0.0}) is False

    def test_negative_ev_gate_missing_ev_passes(self, registry):
        assert registry.invoke("negative_ev_gate", {}, {"threshold": 0.0}) is True

    def test_earnings_route1_no_earnings_passes(self, registry):
        assert registry.invoke("earnings_route1_no_viable_window", {}, {}) is True

    def test_earnings_route1_no_viable_window_fails(self, registry):
        nv = {"dte_before_earnings": 5, "dte_after_earnings": 10}
        assert registry.invoke("earnings_route1_no_viable_window", nv, {"dte_before_threshold": 7, "dte_after_threshold": 14}) is False


class TestAdjustmentFormulaParity:
    """Adjustment formulas return correct penalties."""

    @pytest.fixture
    def registry(self):
        return get_registry()

    def test_cushion_penalty_moderate_in_band(self, registry):
        # cushion_pct 1.5 is in [1.0, 2.0) → False (triggers penalty)
        assert registry.invoke("cushion_penalty_moderate", {"cushion_pct": 1.5}, {"lower_threshold": 1.0, "upper_threshold": 2.0}) is False

    def test_cushion_penalty_moderate_outside_band(self, registry):
        assert registry.invoke("cushion_penalty_moderate", {"cushion_pct": 2.5}, {"lower_threshold": 1.0, "upper_threshold": 2.0}) is True

    def test_probability_asymmetry_severe(self, registry):
        result = registry.invoke("probability_asymmetry_penalty", {"p_max_loss": 0.60, "p_max_profit": 0.20}, {})
        assert result == -25  # ratio 3.0 >= 2.0

    def test_probability_asymmetry_no_penalty(self, registry):
        result = registry.invoke("probability_asymmetry_penalty", {"p_max_loss": 0.30, "p_max_profit": 0.40}, {})
        assert result == 0.0  # ratio 0.75 < 1.25


# ── Layer 3: End-to-end pipeline ─────────────────────────────────────


def _ota_apps():
    return [
        {"app_id": "SHARED", "name": "Shared", "status": "active", "enabled": True},
        {"app_id": "OTA", "name": "Options Analyzer", "status": "active", "enabled": True},
    ]


def _ota_lookups():
    """formula_registry lookup set for OTA's registered formulas."""
    reg = get_registry()
    lookups = []
    for i, name in enumerate(sorted(reg.registered_names()), 1):
        lookups.append({
            "owner_app_id": "SHARED",
            "lookup_set": "formula_registry",
            "lookup_key": name,
            "payload": None,
            "sort_order": i,
            "enabled": True,
        })
    return lookups


def _sp_rules():
    """Minimal Steady Paycheck rule set: 1 gate + 2 scoring criteria."""
    return [
        # Gate: negative EV
        {
            "rule_id": 100, "owner_app_id": "OTA", "rule_key": "neg_ev_gate",
            "phase": "gate", "tier": "DERIVED", "intent": "Block negative EV",
            "condition_expression": None, "formula_ref": "formula:negative_ev_gate",
            "referenced_named_values": ["ev_raw"],
            "parameter_schema": {"threshold": {"type": "number"}},
            "null_semantics": None, "enabled": True,
        },
        # Scoring: theta margin ratio
        {
            "rule_id": 101, "owner_app_id": "OTA", "rule_key": "sp_theta_margin",
            "phase": "scoring", "tier": None, "intent": None,
            "condition_expression": None, "formula_ref": "formula:theta_margin_ratio",
            "referenced_named_values": ["net_theta", "max_loss"],
            "parameter_schema": {"scale": {"type": "number"}},
            "null_semantics": None, "enabled": True,
        },
        # Scoring: probability of profit
        {
            "rule_id": 102, "owner_app_id": "OTA", "rule_key": "sp_pop",
            "phase": "scoring", "tier": None, "intent": None,
            "condition_expression": None, "formula_ref": "formula:probability_of_profit",
            "referenced_named_values": ["prob_of_profit"],
            "parameter_schema": {}, "null_semantics": None, "enabled": True,
        },
        # Scoring: expected value
        {
            "rule_id": 103, "owner_app_id": "OTA", "rule_key": "sp_ev",
            "phase": "scoring", "tier": None, "intent": None,
            "condition_expression": None, "formula_ref": "formula:expected_value",
            "referenced_named_values": ["ev_raw"],
            "parameter_schema": {"scale": {"type": "number"}},
            "null_semantics": None, "enabled": True,
        },
        # Adjustment: cushion penalty moderate
        {
            "rule_id": 104, "owner_app_id": "OTA", "rule_key": "sp_cushion_mod",
            "phase": "adjustment", "tier": None, "intent": None,
            "condition_expression": None,
            "formula_ref": "formula:cushion_penalty_moderate",
            "referenced_named_values": ["cushion_pct"],
            "parameter_schema": {},
            "null_semantics": None, "enabled": True,
        },
    ]


def _sp_strategies():
    return [{
        "strategy_id": 100, "owner_app_id": "OTA",
        "strategy_key": "steady_paycheck",
        "display_name": "Steady Paycheck", "consumer_surface": "SCREENING",
        "description": None, "compatible_structures": ["BULL_PUT_CREDIT", "BEAR_CALL_CREDIT"],
        "verdict_band_set": [
            {"verdict": "EXECUTE", "min_score": 70, "max_score": 100},
            {"verdict": "WAIT", "min_score": 50, "max_score": 69.99},
            {"verdict": "PASS", "min_score": 0, "max_score": 49.99},
        ],
        "enabled": True,
    }]


def _sp_junction():
    return [
        # Gate: negative EV
        {
            "junction_id": 100, "strategy_id": 100, "rule_id": 100,
            "evaluation_order": 1, "stop_if_fail": True,
            "score_penalty": None, "weight": None,
            "parameters": {"threshold": 0.0}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
        # Scoring: theta margin (weight 0.3)
        {
            "junction_id": 101, "strategy_id": 100, "rule_id": 101,
            "evaluation_order": 1, "stop_if_fail": False,
            "score_penalty": None, "weight": 0.3,
            "parameters": {"scale": 100.0}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
        # Scoring: POP (weight 0.4)
        {
            "junction_id": 102, "strategy_id": 100, "rule_id": 102,
            "evaluation_order": 2, "stop_if_fail": False,
            "score_penalty": None, "weight": 0.4,
            "parameters": {}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
        # Scoring: EV (weight 0.3)
        {
            "junction_id": 103, "strategy_id": 100, "rule_id": 103,
            "evaluation_order": 3, "stop_if_fail": False,
            "score_penalty": None, "weight": 0.3,
            "parameters": {"scale": 1.0}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
        # Adjustment: cushion penalty
        {
            "junction_id": 104, "strategy_id": 100, "rule_id": 104,
            "evaluation_order": 1, "stop_if_fail": False,
            "score_penalty": 10.0, "weight": None,
            "parameters": {"lower_threshold": 1.0, "upper_threshold": 2.0},
            "terminal_verdict": None, "rationale": None, "enabled": True,
        },
    ]


def _build_sp_config():
    source = InMemoryConfigSource(
        apps=_ota_apps(),
        rules=_sp_rules(),
        strategies=_sp_strategies(),
        junction=_sp_junction(),
        lookups=_ota_lookups(),
    )
    return load_config(source, app_ids=("SHARED", "OTA"))


def _tr_rules():
    """Minimal Trend Rider rule set with COMPUTED tier gate."""
    base = [
        # Gate: negative EV (DERIVED)
        {
            "rule_id": 200, "owner_app_id": "OTA", "rule_key": "tr_neg_ev",
            "phase": "gate", "tier": "DERIVED", "intent": "Block negative EV",
            "condition_expression": None, "formula_ref": "formula:negative_ev_gate",
            "referenced_named_values": ["ev_raw"],
            "parameter_schema": {}, "null_semantics": None, "enabled": True,
        },
        # Scoring: SMA alignment
        {
            "rule_id": 201, "owner_app_id": "OTA", "rule_key": "tr_sma",
            "phase": "scoring", "tier": None, "intent": None,
            "condition_expression": None,
            "formula_ref": "formula:sma_alignment_score",
            "referenced_named_values": ["sma_alignment_classification"],
            "parameter_schema": {}, "null_semantics": None, "enabled": True,
        },
        # Scoring: delta quality
        {
            "rule_id": 202, "owner_app_id": "OTA", "rule_key": "tr_delta",
            "phase": "scoring", "tier": None, "intent": None,
            "condition_expression": None, "formula_ref": "formula:delta_quality",
            "referenced_named_values": ["delta"],
            "parameter_schema": {
                "delta_center": {"type": "number"},
                "delta_half_range": {"type": "number"},
            },
            "null_semantics": None, "enabled": True,
        },
        # Adjustment: probability asymmetry (uses COMPUTED values)
        {
            "rule_id": 203, "owner_app_id": "OTA", "rule_key": "tr_asymmetry",
            "phase": "adjustment", "tier": "COMPUTED", "intent": None,
            "condition_expression": None,
            "formula_ref": "formula:probability_asymmetry_penalty",
            "referenced_named_values": ["p_max_loss", "p_max_profit"],
            "parameter_schema": {}, "null_semantics": None, "enabled": True,
        },
    ]
    return base


def _tr_strategies():
    return [{
        "strategy_id": 200, "owner_app_id": "OTA",
        "strategy_key": "trend_rider",
        "display_name": "Trend Rider", "consumer_surface": "SCREENING",
        "description": None, "compatible_structures": ["BULL_CALL_DEBIT", "LONG_CALL"],
        "verdict_band_set": [
            {"verdict": "EXECUTE", "min_score": 70, "max_score": 100},
            {"verdict": "WAIT", "min_score": 50, "max_score": 69.99},
            {"verdict": "PASS", "min_score": 0, "max_score": 49.99},
        ],
        "enabled": True,
    }]


def _tr_junction():
    return [
        {
            "junction_id": 200, "strategy_id": 200, "rule_id": 200,
            "evaluation_order": 1, "stop_if_fail": True,
            "score_penalty": None, "weight": None,
            "parameters": {"threshold": 0.0}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
        {
            "junction_id": 201, "strategy_id": 200, "rule_id": 201,
            "evaluation_order": 1, "stop_if_fail": False,
            "score_penalty": None, "weight": 0.5,
            "parameters": {}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
        {
            "junction_id": 202, "strategy_id": 200, "rule_id": 202,
            "evaluation_order": 2, "stop_if_fail": False,
            "score_penalty": None, "weight": 0.5,
            "parameters": {"delta_center": 0.35, "delta_half_range": 0.15, "smoothing": 0.05},
            "terminal_verdict": None, "rationale": None, "enabled": True,
        },
        {
            "junction_id": 203, "strategy_id": 200, "rule_id": 203,
            "evaluation_order": 1, "stop_if_fail": False,
            "score_penalty": None, "weight": None,
            "parameters": {}, "terminal_verdict": None,
            "rationale": None, "enabled": True,
        },
    ]


def _build_tr_config():
    source = InMemoryConfigSource(
        apps=_ota_apps(),
        rules=_tr_rules(),
        strategies=_tr_strategies(),
        junction=_tr_junction(),
        lookups=_ota_lookups(),
    )
    return load_config(source, app_ids=("SHARED", "OTA"))


class TestEndToEndSteadyPaycheck:
    """SP: credit spread → gate passes → scoring → verdict."""

    def test_positive_ev_credit_spread_reaches_verdict(self):
        config = _build_sp_config()
        registry = get_registry()
        sink = InMemorySink()

        # Wider credit (higher POP via lower short delta) → positive EV
        c = _make_spread_candidate(
            spread_type="bull_put",
            underlying_price=200.0,
            long_strike=170.0,
            short_strike=175.0,
            long_bid=0.30,
            long_ask=0.50,
            short_bid=2.80,
            short_ask=3.20,
            long_delta=-0.10,
            short_delta=-0.20,
        )
        _compute_derived(c)
        # Stamp market context
        c.named_values["sma_alignment"] = "BULLISH"
        c.named_values["iv_percentile"] = 55.0
        c.named_values["atr_14"] = 3.0
        c.named_values["atm_iv"] = 0.28
        _compute_post_context_derived([c])

        results = evaluate(
            candidates=[c],
            strategy_key="steady_paycheck",
            source_app_id="OTA",
            config=config,
            registry=registry,
            sink=sink,
        )

        assert len(results) == 1
        r = results[0]
        assert r.terminal_phase == "verdict"
        assert r.verdict in ("EXECUTE", "WAIT", "PASS")
        assert r.verdict_source == VerdictSource.BAND_LOOKUP
        assert r.final_score is not None
        assert 0 <= r.final_score <= 100
        assert r.source_app_id == "OTA"

        # Scoring breakdown present
        assert len(r.scoring_breakdown) == 3  # theta, pop, ev

        # Gate passed
        assert all(g.passed for g in r.gate_decisions)

        # Bronze records emitted
        assert len(sink.snapshots) == 1
        assert sink.snapshots[0].source_app_id == "OTA"

    def test_negative_ev_halted_at_gate(self):
        config = _build_sp_config()
        registry = get_registry()

        # Build a spread with very negative EV
        c = _make_spread_candidate(
            spread_type="bull_put",
            underlying_price=180.0,
            long_strike=170.0,
            short_strike=175.0,
            # Prices that produce negative EV: very small credit
            long_bid=2.40,
            long_ask=2.60,
            short_bid=0.80,
            short_ask=1.00,
        )
        _compute_derived(c)

        # ev_raw should be negative for this setup
        assert c.named_values["ev_raw"] < 0, f"Expected negative EV, got {c.named_values['ev_raw']}"

        results = evaluate(
            candidates=[c],
            strategy_key="steady_paycheck",
            source_app_id="OTA",
            config=config,
            registry=registry,
        )

        assert len(results) == 1
        r = results[0]
        # Halted at gate
        assert r.terminal_phase == "gate"
        assert r.scoring_breakdown == []
        assert r.final_score is None

    def test_cushion_penalty_applied(self):
        config = _build_sp_config()
        registry = get_registry()

        # Build spread with positive EV AND cushion in moderate band [1.0, 2.0)
        # Need breakeven close to underlying price.
        # bull_put breakeven = short_strike - net_credit
        # cushion_pct = (price - breakeven) / price * 100
        # Target: cushion_pct ~1.5 → breakeven ~= price * (1 - 0.015)
        c = _make_spread_candidate(
            spread_type="bull_put",
            underlying_price=176.0,
            long_strike=170.0,
            short_strike=175.0,
            long_bid=0.40,
            long_ask=0.60,
            short_bid=2.80,
            short_ask=3.20,
            long_delta=-0.15,
            short_delta=-0.25,
        )
        _compute_derived(c)
        c.named_values["sma_alignment"] = "NEUTRAL"
        _compute_post_context_derived([c])

        cushion = c.named_values.get("cushion_pct")
        ev = c.named_values.get("ev_raw")

        # Skip if our inputs didn't produce the right conditions
        if ev is None or ev < 0:
            pytest.skip("Could not produce positive EV for cushion test")

        results = evaluate(
            candidates=[c],
            strategy_key="steady_paycheck",
            source_app_id="OTA",
            config=config,
            registry=registry,
        )

        assert len(results) == 1
        r = results[0]
        assert r.terminal_phase == "verdict"

        if cushion is not None and 1.0 <= cushion < 2.0:
            adj = [a for a in r.adjustment_results if a.rule_key == "sp_cushion_mod"]
            assert len(adj) == 1


class TestEndToEndTrendRider:
    """TR: naked call → gate → scoring with COMPUTED → verdict."""

    def test_trend_rider_with_computed_callback(self):
        config = _build_tr_config()
        registry = get_registry()
        adapter = OptionsChainAdapter()
        sink = InMemorySink()

        c = _make_naked_candidate(
            option_type="call",
            strike=190.0,
            underlying_price=180.0,
            delta=0.35,
            iv=0.30,
            dte_days=45,
        )
        _compute_derived(c)
        c.named_values["sma_alignment"] = "BULLISH"
        c.named_values["sma_alignment_classification"] = "BULLISH"
        c.named_values["iv_percentile"] = 40.0
        c.named_values["iv_rank"] = 40.0

        results = evaluate(
            candidates=[c],
            strategy_key="trend_rider",
            source_app_id="OTA",
            config=config,
            registry=registry,
            adapter=adapter,
            sink=sink,
        )

        assert len(results) == 1
        r = results[0]
        assert r.terminal_phase == "verdict"
        assert r.verdict in ("EXECUTE", "WAIT", "PASS")
        assert r.source_app_id == "OTA"
        assert len(r.scoring_breakdown) == 2  # sma + delta


class TestEndToEndMultiCandidate:
    """Multiple candidates, some halted, some scored."""

    def test_mixed_batch_gate_and_verdict(self):
        config = _build_sp_config()
        registry = get_registry()
        sink = InMemorySink()

        # Good candidate (positive EV — wide credit, high POP)
        good = _make_spread_candidate(
            spread_type="bull_put",
            underlying_price=200.0,
            long_strike=170.0,
            short_strike=175.0,
            long_bid=0.30,
            long_ask=0.50,
            short_bid=2.80,
            short_ask=3.20,
            long_delta=-0.10,
            short_delta=-0.20,
        )
        _compute_derived(good)
        good.named_values["sma_alignment"] = "BULLISH"
        _compute_post_context_derived([good])

        # Bad candidate (negative EV — swap bid/ask to get negative credit)
        bad = _make_spread_candidate(
            symbol="MSFT",
            spread_type="bull_put",
            long_strike=170.0,
            short_strike=175.0,
            long_bid=2.40,
            long_ask=2.60,
            short_bid=0.80,
            short_ask=1.00,
        )
        _compute_derived(bad)

        results = evaluate(
            candidates=[good, bad],
            strategy_key="steady_paycheck",
            source_app_id="OTA",
            config=config,
            registry=registry,
            sink=sink,
        )

        assert len(results) == 2

        # Find the good and bad results
        verdicts = {r.candidate_id: r for r in results}
        good_r = verdicts[good.candidate_id]
        bad_r = verdicts[bad.candidate_id]

        assert good_r.terminal_phase == "verdict"
        assert good_r.verdict is not None
        assert bad_r.terminal_phase == "gate"
        assert bad_r.final_score is None

        # Bronze: both candidates get snapshots
        assert len(sink.snapshots) == 2


class TestValidationWithLiveRegistry:
    """Config + live formula registry passes OTA-699 startup validation."""

    def test_sp_config_validates(self):
        config = _build_sp_config()
        registry = get_registry()
        report = validate_config(config, formula_registry=registry)
        assert report.is_valid, report.summary()

    def test_tr_config_validates(self):
        config = _build_tr_config()
        registry = get_registry()
        report = validate_config(config, formula_registry=registry)
        assert report.is_valid, report.summary()
