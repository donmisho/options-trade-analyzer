"""
OTA-645: Regression coverage for verdict/narrative consistency.

Background: a pre-OTA-636 defect produced banner verdict WAIT and narrative
opener "PASS — structural mismatch" for BEAR_PUT_DEBIT scored against Steady
Paycheck. OTA-636 closed the structural leak; OTA-637 unified pill/prose.
This file locks in regression coverage so the contradiction cannot return.

Three test categories:
  2a. Structural-incompatibility short-circuit — 9 (structure, strategy)
      cells assert is_compatible returns False and classifier produces no best_fit.
  2b. Verdict consistency invariant — _assign_verdict matches score band,
      TradeEvaluationCard validates verdict enum, and 24 compatible
      (structure × strategy × score-band) cases produce consistent results.
  2c. MMM Bear Put canary — eligible_strategies=[trend-rider], no SP entry.

Depends on OTA-636 (structural gating) and OTA-637 (pill/prose unification).
"""

import pytest

from app.analysis.strategy_routing import is_compatible, get_compatible_strategies
from app.analysis.strategy_classifier import classify_best_strategy
from app.analysis.strategy_scorer import StrategyScore
from app.analysis.strategy_definitions import STRATEGIES
from app.api.evaluation_routes import _assign_verdict
from app.models.schemas import TradeEvaluationCard


# ─── Helpers ────────────────────────────────────────────────────────────────


def _make_score(strategy_key: str, score: int) -> StrategyScore:
    return StrategyScore(
        strategy_key=strategy_key,
        label=STRATEGIES[strategy_key].label,
        score=score,
        best_trade=None,
        signal_summary="test fixture",
        metric_scores={},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 2a: Structural-incompatibility short-circuit
# ═══════════════════════════════════════════════════════════════════════════════

INCOMPATIBLE_PAIRS = [
    ("bear_put_debit",   "steady-paycheck"),   # original reproducer
    ("bear_put_debit",   "weekly-grind"),
    ("bull_call_debit",  "steady-paycheck"),
    ("bull_call_debit",  "weekly-grind"),
    ("bull_put_credit",  "trend-rider"),
    ("bear_call_credit", "trend-rider"),
    ("bull_put_credit",  "lottery-ticket"),
    ("long_call",        "steady-paycheck"),    # SINGLE_LONG_CALL
    ("long_put",         "trend-rider"),         # SINGLE_LONG_PUT
]


class TestStructuralIncompatibilityShortCircuit:
    """2a: Incompatible (structure, strategy) pairs produce no scorer result."""

    @pytest.mark.parametrize("structure,strategy_key", INCOMPATIBLE_PAIRS)
    def test_is_compatible_returns_false(self, structure, strategy_key):
        """is_compatible gates at the predicate level."""
        assert is_compatible(strategy_key, structure) is False

    @pytest.mark.parametrize("structure,strategy_key", INCOMPATIBLE_PAIRS)
    def test_classifier_returns_none_best_fit(self, structure, strategy_key):
        """classify_best_strategy filters out incompatible strategies regardless of score."""
        candidate = _make_score(strategy_key, 95)  # artificially high — still filtered
        result = classify_best_strategy(
            [candidate], effective_dte=30, trade_structure=structure,
        )
        assert result.best_fit is None, (
            f"Expected best_fit=None for ({structure}, {strategy_key}), "
            f"got {result.best_fit}"
        )

    @pytest.mark.parametrize("structure,strategy_key", INCOMPATIBLE_PAIRS)
    def test_strategy_not_in_eligible_list(self, structure, strategy_key):
        """get_compatible_strategies inverse lookup excludes the incompatible strategy."""
        eligible = get_compatible_strategies(structure)
        assert strategy_key not in eligible, (
            f"{strategy_key} should not be eligible for structure {structure}, "
            f"but found in {eligible}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 2b: Verdict consistency invariant
# ═══════════════════════════════════════════════════════════════════════════════

# All 8 structurally-compatible (structure, strategy) pairs
COMPATIBLE_PAIRS = [
    ("bull_put_credit",  "steady-paycheck"),
    ("bear_call_credit", "steady-paycheck"),
    ("bull_put_credit",  "weekly-grind"),
    ("bear_call_credit", "weekly-grind"),
    ("bull_call_debit",  "trend-rider"),
    ("bear_put_debit",   "trend-rider"),
    ("long_call",        "lottery-ticket"),
    ("long_put",         "lottery-ticket"),
]

# Score bands: {score_range: expected_verdict}
SCORE_BAND_SAMPLES = [
    (0,   "PASS"),
    (25,  "PASS"),
    (49,  "PASS"),
    (50,  "WAIT"),
    (55,  "WAIT"),
    (69,  "WAIT"),
    (70,  "EXECUTE"),
    (85,  "EXECUTE"),
    (100, "EXECUTE"),
]


class TestAssignVerdictScoreBands:
    """_assign_verdict deterministically maps scores to verdict strings."""

    @pytest.mark.parametrize("score,expected", SCORE_BAND_SAMPLES)
    def test_score_to_verdict_mapping(self, score, expected):
        assert _assign_verdict(score) == expected

    def test_boundary_49_is_pass(self):
        assert _assign_verdict(49) == "PASS"

    def test_boundary_50_is_wait(self):
        assert _assign_verdict(50) == "WAIT"

    def test_boundary_69_is_wait(self):
        assert _assign_verdict(69) == "WAIT"

    def test_boundary_70_is_execute(self):
        assert _assign_verdict(70) == "EXECUTE"


class TestTradeEvaluationCardVerdictValidator:
    """TradeEvaluationCard Pydantic validator rejects invalid verdict values."""

    def _make_card_kwargs(self, verdict: str) -> dict:
        return dict(
            strategy_key="steady-paycheck",
            strategy_label="Steady Paycheck",
            trade_structure="Sell 415P / Buy 410P",
            score=70,
            verdict=verdict,
            claude_read="Test narrative.",
            key_risks=["Risk 1", "Risk 2"],
            thesis_invalidators=["Invalidator 1", "Invalidator 2"],
        )

    @pytest.mark.parametrize("verdict", ["EXECUTE", "WAIT", "PASS", "WAIT_FOR_EARNINGS"])
    def test_valid_verdicts_accepted(self, verdict):
        card = TradeEvaluationCard(**self._make_card_kwargs(verdict))
        assert card.verdict == verdict

    @pytest.mark.parametrize("verdict", ["HOLD", "BUY", "SELL", "execute", "wait", "pass", ""])
    def test_invalid_verdicts_rejected(self, verdict):
        with pytest.raises(Exception):  # Pydantic ValidationError
            TradeEvaluationCard(**self._make_card_kwargs(verdict))


# DTE that falls within each strategy's classifier eligibility range
# (from strategy_classifier.STRATEGY_DTE_REQUIREMENTS)
STRATEGY_TEST_DTE = {
    "steady-paycheck": 30,   # range: 14-45
    "weekly-grind":    18,   # range: 14-21
    "trend-rider":     30,   # range: 14-60
    "lottery-ticket":  30,   # range: 7-60
}

# 8 compatible pairs × 3 score bands = 24 test cases (exceeds 20 requirement)
VERDICT_INVARIANT_CASES = [
    (structure, strategy, score, expected_verdict, STRATEGY_TEST_DTE[strategy])
    for structure, strategy in COMPATIBLE_PAIRS
    for score, expected_verdict in [(30, "PASS"), (55, "WAIT"), (85, "EXECUTE")]
]


class TestVerdictConsistencyInvariant:
    """For every compatible (structure, strategy) pair, the verdict produced by
    _assign_verdict matches the score band, and the classifier accepts the pair."""

    @pytest.mark.parametrize(
        "structure,strategy_key,score,expected_verdict,dte",
        VERDICT_INVARIANT_CASES,
        ids=[
            f"{strat}+{struct}@{score}"
            for struct, strat, score, _, _ in VERDICT_INVARIANT_CASES
        ],
    )
    def test_compatible_pair_verdict_matches_score_band(
        self, structure, strategy_key, score, expected_verdict, dte
    ):
        # Compatibility holds
        assert is_compatible(strategy_key, structure) is True

        # Verdict deterministically follows score
        verdict = _assign_verdict(score)
        assert verdict == expected_verdict, (
            f"_assign_verdict({score}) = {verdict}, expected {expected_verdict} "
            f"for ({structure}, {strategy_key})"
        )

        # Classifier accepts the compatible pair with strategy-appropriate DTE
        candidate = _make_score(strategy_key, score)
        result = classify_best_strategy(
            [candidate], effective_dte=dte, trade_structure=structure,
        )
        assert result.best_fit == strategy_key, (
            f"Classifier rejected compatible pair ({structure}, {strategy_key}) "
            f"at DTE={dte}"
        )
        assert result.score == score


# ═══════════════════════════════════════════════════════════════════════════════
# 2c: MMM Bear Put canary fixture
# ═══════════════════════════════════════════════════════════════════════════════


class TestMMMBearPutCanary:
    """End-to-end fixture for the originally-reported MMM 146/136 Bear Put defect.

    The original screenshots showed a BEAR_PUT_DEBIT evaluated through Steady
    Paycheck producing contradictory verdict (WAIT) and narrative (PASS).

    Post-OTA-636, BEAR_PUT_DEBIT is only compatible with Trend Rider.
    Steady Paycheck must never appear in eligible strategies for this structure.
    """

    STRUCTURE = "bear_put_debit"

    def test_eligible_strategies_for_bear_put_debit(self):
        eligible = get_compatible_strategies(self.STRUCTURE)
        assert eligible == ["trend-rider"], (
            f"Expected eligible=['trend-rider'] for {self.STRUCTURE}, got {eligible}"
        )

    def test_steady_paycheck_not_eligible(self):
        eligible = get_compatible_strategies(self.STRUCTURE)
        assert "steady-paycheck" not in eligible

    def test_weekly_grind_not_eligible(self):
        eligible = get_compatible_strategies(self.STRUCTURE)
        assert "weekly-grind" not in eligible

    def test_lottery_ticket_not_eligible(self):
        eligible = get_compatible_strategies(self.STRUCTURE)
        assert "lottery-ticket" not in eligible

    def test_best_fit_is_trend_rider(self):
        """With only TR as eligible and a valid score, best_fit = trend-rider."""
        candidates = [
            _make_score("steady-paycheck", 90),
            _make_score("weekly-grind", 85),
            _make_score("trend-rider", 72),
            _make_score("lottery-ticket", 60),
        ]
        result = classify_best_strategy(
            candidates, effective_dte=30, trade_structure=self.STRUCTURE,
        )
        assert result.best_fit == "trend-rider"
        assert result.score == 72

    def test_no_sp_verdict_produced_for_bear_put(self):
        """Even when SP has the highest score, it is filtered for bear_put_debit."""
        candidates = [
            _make_score("steady-paycheck", 95),
            _make_score("trend-rider", 40),
        ]
        result = classify_best_strategy(
            candidates, effective_dte=30, trade_structure=self.STRUCTURE,
        )
        # TR at 40 is still the only compatible option
        assert result.best_fit == "trend-rider"
        assert result.score == 40

    def test_full_scorecard_filters_to_tr_only(self):
        """Simulate a full scorecard response — only TR survives structural filter."""
        all_scores = [
            _make_score("steady-paycheck", 88),
            _make_score("weekly-grind", 82),
            _make_score("trend-rider", 65),
            _make_score("lottery-ticket", 55),
        ]
        eligible = [
            s for s in all_scores
            if is_compatible(s.strategy_key, self.STRUCTURE)
        ]
        eligible_keys = [s.strategy_key for s in eligible]
        assert eligible_keys == ["trend-rider"]
        assert "steady-paycheck" not in eligible_keys
