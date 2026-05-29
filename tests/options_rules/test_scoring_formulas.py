"""
Unit tests for the 16 screening scoring criteria formulas.

Each formula is tested against its business-rules.md / audit §4
canonical definition. For the 4 legacy-implemented criteria, parity
with the old strategy_scorer.py implementation is asserted.

OTA-727
"""

from __future__ import annotations

import pytest

from app.insight_engine.config_source import InMemoryConfigSource
from app.insight_engine.loader import load_config
from app.insight_engine.registry import DictFormulaRegistry
from app.insight_engine.validation import validate_config
from app.options_rules.screening import get_registry


# ── Fixture: the 16 scoring formula names ──────────────────────────────

SCORING_FORMULA_NAMES = frozenset({
    "theta_margin_ratio",
    "probability_of_profit",
    "expected_value",
    "reward_risk",
    "iv_rank",
    "theta_gamma_ratio",
    "credit_width",
    "liquidity",
    "sma_alignment_score",
    "delta_quality",
    "iv_percentile_cost",
    "runway_score",
    "payout_ratio",
    "delta_otm_score",
    "bid_ask_tightness",
    "open_interest",
})


# ── Registration and membership ────────────────────────────────────────


class TestScoringFormulasRegistration:
    def test_all_16_names_registered(self):
        """All 16 scoring formula names are in the live registry."""
        reg = get_registry()
        registered = reg.registered_names()
        for name in SCORING_FORMULA_NAMES:
            assert name in registered, f"Formula '{name}' not registered"

    def test_formula_membership_with_validation(self):
        """OTA-699 membership check passes when all 16 formulas are
        in both the SHARED contract and the live registry."""
        lookups = [
            {
                "owner_app_id": "SHARED",
                "lookup_set": "formula_registry",
                "lookup_key": name,
                "payload": f'{{"intent": "{name}"}}',
                "sort_order": i + 1,
                "enabled": True,
            }
            for i, name in enumerate(sorted(SCORING_FORMULA_NAMES))
        ]

        # Build a minimal config with one scoring rule per formula
        rules = [
            {
                "rule_id": i + 1,
                "owner_app_id": "SHARED",
                "rule_key": f"{name}_score",
                "phase": "scoring",
                "tier": "RAW",
                "intent": f"Score {name}",
                "condition_expression": None,
                "formula_ref": f"formula:{name}",
                "referenced_named_values": [],
                "parameter_schema": {},
                "null_semantics": None,
                "enabled": True,
            }
            for i, name in enumerate(sorted(SCORING_FORMULA_NAMES))
        ]

        n = len(SCORING_FORMULA_NAMES)
        weight = 1.0 / n
        junction = [
            {
                "junction_id": i + 1,
                "strategy_id": 1,
                "rule_id": i + 1,
                "evaluation_order": i + 1,
                "stop_if_fail": False,
                "score_penalty": None,
                "weight": weight,
                "parameters": {},
                "terminal_verdict": None,
                "rationale": f"{name}",
                "enabled": True,
            }
            for i, name in enumerate(sorted(SCORING_FORMULA_NAMES))
        ]

        source = InMemoryConfigSource(
            apps=[
                {"app_id": "SHARED", "name": "Shared", "status": "active", "enabled": True},
                {"app_id": "OTA", "name": "OTA", "status": "active", "enabled": True},
            ],
            rules=rules,
            strategies=[
                {
                    "strategy_id": 1,
                    "owner_app_id": "OTA",
                    "strategy_key": "test",
                    "display_name": "Test",
                    "consumer_surface": "SCREENING",
                    "description": "Test",
                    "compatible_structures": None,
                    "verdict_band_set": [
                        {"verdict": "EXECUTE", "min_score": 70, "max_score": 100},
                        {"verdict": "PASS", "min_score": 0, "max_score": 69.99},
                    ],
                    "dte_min": None,
                    "dte_max": None,
                    "enabled": True,
                },
            ],
            junction=junction,
            lookups=lookups,
        )
        config = load_config(source)
        report = validate_config(config, formula_registry=get_registry())

        contract_errors = report.errors_by_code("FORMULA_MISSING_FROM_CONTRACT")
        live_errors = report.errors_by_code("FORMULA_MISSING_FROM_LIVE_REGISTRY")
        drift_errors = report.errors_by_code("FORMULA_REGISTRY_DRIFT")

        assert len(contract_errors) == 0, f"Contract errors: {contract_errors}"
        assert len(live_errors) == 0, f"Live errors: {live_errors}"
        assert len(drift_errors) == 0, f"Drift errors: {drift_errors}"


# ── Unit tests: each formula ───────────────────────────────────────────


class TestThetaMarginRatio:
    def test_basic(self):
        reg = get_registry()
        result = reg.invoke("theta_margin_ratio", {"net_theta": -0.50, "max_loss": 100}, {"scale": 100.0})
        assert result == pytest.approx(0.50, abs=0.01)

    def test_zero_max_loss(self):
        reg = get_registry()
        assert reg.invoke("theta_margin_ratio", {"net_theta": -1, "max_loss": 0}, {"scale": 100.0}) == 0.0

    def test_legacy_parity(self):
        """Legacy: abs(net_theta) / max_loss"""
        reg = get_registry()
        nv = {"net_theta": -0.30, "max_loss": 200}
        legacy = abs(-0.30) / 200  # 0.0015
        result = reg.invoke("theta_margin_ratio", nv, {"scale": 100.0})
        assert result == pytest.approx(legacy * 100, abs=0.01)


class TestProbabilityOfProfit:
    def test_passthrough(self):
        reg = get_registry()
        assert reg.invoke("probability_of_profit", {"prob_of_profit": 72.5}, {}) == pytest.approx(72.5)

    def test_clamp_high(self):
        reg = get_registry()
        assert reg.invoke("probability_of_profit", {"prob_of_profit": 150}, {}) == 100.0

    def test_clamp_low(self):
        reg = get_registry()
        assert reg.invoke("probability_of_profit", {"prob_of_profit": -5}, {}) == 0.0


class TestExpectedValue:
    def test_credit_spread_path(self):
        reg = get_registry()
        result = reg.invoke("expected_value", {"ev_raw": 45.0}, {"scale": 1.0})
        assert result == pytest.approx(45.0)

    def test_long_option_path(self):
        reg = get_registry()
        nv = {"delta": 0.50, "underlying_price": 200, "mid_price": 5.0}
        # EV = 0.50 * 200 * 0.05 - 5.0 = 5.0 - 5.0 = 0.0
        result = reg.invoke("expected_value", nv, {"move_pct": 0.05, "scale": 1.0})
        assert result == pytest.approx(0.0)

    def test_legacy_parity_credit(self):
        """Legacy: ev_raw passthrough."""
        reg = get_registry()
        assert reg.invoke("expected_value", {"ev_raw": 30.0}, {"scale": 1.0}) == pytest.approx(30.0)


class TestRewardRisk:
    def test_from_ratio(self):
        reg = get_registry()
        assert reg.invoke("reward_risk", {"reward_risk_ratio": 0.5}, {"scale": 100.0}) == pytest.approx(50.0)

    def test_from_components(self):
        reg = get_registry()
        nv = {"max_profit": 200, "max_loss": 400}
        assert reg.invoke("reward_risk", nv, {"scale": 100.0}) == pytest.approx(50.0)

    def test_zero_loss(self):
        reg = get_registry()
        assert reg.invoke("reward_risk", {"max_profit": 100, "max_loss": 0}, {"scale": 100.0}) == 0.0


class TestIVRank:
    def test_proxy_path(self):
        """Legacy: min(1.0, atm_iv / 0.60) * 100"""
        reg = get_registry()
        result = reg.invoke("iv_rank", {"atm_iv": 0.30}, {"divisor": 0.60})
        assert result == pytest.approx(50.0)

    def test_proxy_clamped(self):
        reg = get_registry()
        result = reg.invoke("iv_rank", {"atm_iv": 0.90}, {"divisor": 0.60})
        assert result == pytest.approx(100.0)

    def test_true_iv_rank(self):
        reg = get_registry()
        result = reg.invoke("iv_rank", {"iv_rank": 65.0}, {})
        assert result == pytest.approx(65.0)


class TestThetaGammaRatio:
    def test_proxy(self):
        """Same as theta_margin_ratio (proxy)."""
        reg = get_registry()
        result = reg.invoke("theta_gamma_ratio", {"net_theta": -0.50, "max_loss": 100}, {"scale": 100.0})
        assert result == pytest.approx(0.50, abs=0.01)


class TestCreditWidth:
    def test_basic(self):
        reg = get_registry()
        # credit = abs(-1.50) = 1.50, width = 5.0 → 30%
        result = reg.invoke("credit_width", {"net_debit": -1.50, "spread_width": 5.0}, {})
        assert result == pytest.approx(30.0)

    def test_zero_width(self):
        reg = get_registry()
        assert reg.invoke("credit_width", {"net_debit": -1, "spread_width": 0}, {}) == 0.0


class TestLiquidity:
    def test_basic(self):
        reg = get_registry()
        nv = {"long_volume": 500, "short_volume": 300, "long_oi": 2000, "short_oi": 1000}
        # total = 3800, default scale = 10000 → 3800/10000 * 100 = 38.0
        result = reg.invoke("liquidity", nv, {"scale": 10000.0})
        assert result == pytest.approx(38.0)


class TestSMAAlignmentScore:
    def test_bullish(self):
        reg = get_registry()
        nv = {"sma_alignment_classification": "BULLISH"}
        result = reg.invoke("sma_alignment_score", nv, {"bullish_score": 100.0})
        assert result == pytest.approx(100.0)

    def test_bearish(self):
        reg = get_registry()
        nv = {"sma_alignment_classification": "BEARISH"}
        result = reg.invoke("sma_alignment_score", nv, {"bearish_score": 0.0})
        assert result == pytest.approx(0.0)

    def test_default_when_no_classification(self):
        reg = get_registry()
        result = reg.invoke("sma_alignment_score", {}, {"default_score": 50.0})
        assert result == pytest.approx(50.0)


class TestDeltaQuality:
    def test_at_center(self):
        """Delta exactly at center should score 100."""
        reg = get_registry()
        result = reg.invoke("delta_quality",
            {"delta": 0.35},
            {"delta_center": 0.35, "delta_half_range": 0.15, "smoothing": 0.05})
        assert result == pytest.approx(100.0)

    def test_at_edge(self):
        """Delta at center + half_range + smoothing should score 0."""
        reg = get_registry()
        result = reg.invoke("delta_quality",
            {"delta": 0.55},  # 0.35 + 0.15 + 0.05
            {"delta_center": 0.35, "delta_half_range": 0.15, "smoothing": 0.05})
        assert result == pytest.approx(0.0)

    def test_legacy_parity(self):
        """Legacy: max(0, 1 - |delta - center| / (half_range + 0.05)) * 100"""
        reg = get_registry()
        delta = 0.45
        center = 0.35
        half_range = 0.15
        legacy = max(0, 1 - abs(delta - center) / (half_range + 0.05)) * 100
        result = reg.invoke("delta_quality", {"delta": delta},
            {"delta_center": center, "delta_half_range": half_range, "smoothing": 0.05})
        assert result == pytest.approx(legacy, abs=0.01)


class TestIVPercentileCost:
    def test_low_iv(self):
        """Low IV should score high."""
        reg = get_registry()
        result = reg.invoke("iv_percentile_cost", {"iv": 20}, {"max_iv": 1.0})
        # iv_decimal = 20/100 = 0.20, score = (1 - 0.20) * 100 = 80
        assert result == pytest.approx(80.0)

    def test_high_iv(self):
        reg = get_registry()
        result = reg.invoke("iv_percentile_cost", {"iv": 80}, {"max_iv": 1.0})
        assert result == pytest.approx(20.0)

    def test_legacy_parity(self):
        """Legacy: max(0, 1 - iv_decimal) * 100"""
        reg = get_registry()
        iv_pct = 35
        iv_decimal = iv_pct / 100.0
        legacy = max(0, 1 - iv_decimal) * 100
        result = reg.invoke("iv_percentile_cost", {"iv": iv_pct}, {"max_iv": 1.0})
        assert result == pytest.approx(legacy, abs=0.01)


class TestRunwayScore:
    def test_basic(self):
        reg = get_registry()
        result = reg.invoke("runway_score", {"theta_runway_days": 45}, {"scale": 100.0})
        assert result == pytest.approx(45.0)

    def test_capped(self):
        reg = get_registry()
        result = reg.invoke("runway_score", {"theta_runway_days": 200}, {"scale": 100.0})
        assert result == 100.0


class TestPayoutRatio:
    def test_basic(self):
        reg = get_registry()
        nv = {"delta": 0.30, "underlying_price": 100.0, "premium_dollars": 2.0}
        # raw = (0.30 * 100 * 0.10 * 100) / 2.0 = 300 / 2 = 150
        # score = 150 / 10 * 100 = capped at 100
        result = reg.invoke("payout_ratio", nv,
            {"move_pct": 0.10, "multiplier": 100.0, "scale": 10.0})
        assert result == 100.0

    def test_zero_premium(self):
        reg = get_registry()
        nv = {"delta": 0.30, "underlying_price": 100, "premium_dollars": 0}
        assert reg.invoke("payout_ratio", nv, {"scale": 10.0}) == 0.0


class TestDeltaOTMScore:
    def test_zero_delta(self):
        """Delta 0 = max OTM = 100."""
        reg = get_registry()
        result = reg.invoke("delta_otm_score", {"delta": 0}, {"max_delta": 0.25})
        assert result == pytest.approx(100.0)

    def test_at_max(self):
        """Delta at max_delta = 0."""
        reg = get_registry()
        result = reg.invoke("delta_otm_score", {"delta": 0.25}, {"max_delta": 0.25})
        assert result == pytest.approx(0.0)

    def test_legacy_parity(self):
        """Legacy: max(0, 1 - delta/0.25) * 100"""
        reg = get_registry()
        delta = 0.10
        legacy = max(0, 1 - delta / 0.25) * 100
        result = reg.invoke("delta_otm_score", {"delta": delta}, {"max_delta": 0.25})
        assert result == pytest.approx(legacy, abs=0.01)


class TestBidAskTightness:
    def test_tight(self):
        reg = get_registry()
        result = reg.invoke("bid_ask_tightness", {"bid_ask_spread_pct": 5}, {"max_spread_pct": 100.0})
        assert result == pytest.approx(95.0)

    def test_wide(self):
        reg = get_registry()
        result = reg.invoke("bid_ask_tightness", {"bid_ask_spread_pct": 100}, {"max_spread_pct": 100.0})
        assert result == pytest.approx(0.0)


class TestOpenInterest:
    def test_basic(self):
        reg = get_registry()
        result = reg.invoke("open_interest", {"open_interest": 5000}, {"scale": 10000.0})
        assert result == pytest.approx(50.0)

    def test_capped(self):
        reg = get_registry()
        result = reg.invoke("open_interest", {"open_interest": 20000}, {"scale": 10000.0})
        assert result == 100.0
