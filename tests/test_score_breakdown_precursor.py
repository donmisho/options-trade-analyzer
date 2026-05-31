"""
Tests for OTA-643 precursor: component_breakdown on StrategyScore
and COMPONENT_DISPLAY_NAMES mapping.
"""

import pytest
from app.analysis.strategy_definitions import StrategyScore
from app.api.display_names import COMPONENT_DISPLAY_NAMES


class TestStrategyScoreDataclass:
    def test_component_breakdown_field_exists(self):
        s = StrategyScore(
            strategy_key="test",
            label="Test",
            score=75,
            best_trade=None,
            signal_summary="test",
            metric_scores={},
            component_breakdown=[
                {"key": "ev", "score": 80, "weight": 0.20, "contribution": 16.0},
            ],
        )
        assert len(s.component_breakdown) == 1
        assert s.component_breakdown[0]["score"] == 80

    def test_raw_score_and_penalty(self):
        s = StrategyScore(
            strategy_key="test",
            label="Test",
            score=55,
            best_trade=None,
            signal_summary="test",
            metric_scores={},
            raw_score=75,
            penalty_reason="cushion penalty",
        )
        assert s.raw_score == 75
        assert s.score == 55
        assert s.penalty_reason == "cushion penalty"

    def test_no_penalty_raw_is_none(self):
        s = StrategyScore(
            strategy_key="test",
            label="Test",
            score=75,
            best_trade=None,
            signal_summary="test",
            metric_scores={},
        )
        assert s.raw_score is None
        assert s.penalty_reason is None


class TestComponentDisplayNames:
    def test_expected_value_mapped(self):
        assert COMPONENT_DISPLAY_NAMES["expected_value"] == "Expected value (EV)"

    def test_iv_rank_mapped(self):
        assert COMPONENT_DISPLAY_NAMES["iv_rank"] == "IV environment"

    def test_sma_alignment_mapped(self):
        assert COMPONENT_DISPLAY_NAMES["sma_alignment_score"] == "Technical alignment (SMAs)"

    def test_liquidity_mapped(self):
        assert COMPONENT_DISPLAY_NAMES["liquidity"] == "Liquidity (bid-ask, volume)"

    def test_all_credit_weights_mapped(self):
        """All weights from Steady Paycheck strategy have display names."""
        sp_weights = ["theta_margin_ratio", "probability_of_profit", "expected_value", "reward_risk", "iv_rank"]
        for w in sp_weights:
            assert w in COMPONENT_DISPLAY_NAMES, f"Missing display name for {w}"

    def test_all_long_option_weights_mapped(self):
        """All weights from Trend Rider strategy have display names."""
        tr_weights = ["sma_alignment_score", "delta_quality", "expected_value", "iv_percentile_cost", "runway_score"]
        for w in tr_weights:
            assert w in COMPONENT_DISPLAY_NAMES, f"Missing display name for {w}"
