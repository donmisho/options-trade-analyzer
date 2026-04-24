"""
AMZN asymmetry penalty pipeline regression tests (OTA-505 Phase 4).

Tests the penalty application logic against TradeEvaluationCard objects — the
same pattern used for gate regression tests (tests/test_amzn_regression.py):
test the layer that matters without mocking Claude or spinning up an HTTP server.

AMZN 260/270 May 15 fixture:
  p_max_loss   = 0.5666  (56.66% probability of max loss)
  p_max_profit = 0.2985  (29.85% probability of max profit)
  ratio        ≈ 1.898   → tier 1.5–2.0 → 15-point penalty
"""

import pytest
from app.models.schemas import TradeEvaluationCard
from app.analysis.scoring_factors.asymmetry import (
    asymmetry_penalty,
    asymmetry_ratio,
)


# ─── AMZN fixture constants ────────────────────────────────────────────────────

AMZN_P_MAX_LOSS   = 0.5666
AMZN_P_MAX_PROFIT = 0.2985
AMZN_EXPECTED_PENALTY = 15
AMZN_EXPECTED_RATIO   = 0.5666 / 0.2985   # ≈ 1.898


def _make_card(score: int, verdict: str = "EXECUTE") -> TradeEvaluationCard:
    """Minimal TradeEvaluationCard with a known base score."""
    return TradeEvaluationCard(
        strategy_key="bull-call-spread",
        strategy_label="Bull Call Spread",
        trade_structure="Buy 260C / Sell 270C, May 15",
        score=score,
        verdict=verdict,
        claude_read="Test narrative.",
        key_risks=["Risk one under fifteen words", "Risk two under fifteen words"],
        thesis_invalidators=["Invalidator one", "Invalidator two"],
    )


def _apply_asymmetry(card: TradeEvaluationCard, p_max_loss, p_max_profit) -> TradeEvaluationCard:
    """
    Mirror the pipeline loop's asymmetry application from evaluation_routes.py.
    Keeps the regression test independent of the route's HTTP machinery.
    """
    penalty = asymmetry_penalty(p_max_loss, p_max_profit)
    ratio   = asymmetry_ratio(p_max_loss, p_max_profit)
    if penalty:
        card.score = max(0, card.score - penalty)
    card.asymmetry_penalty = penalty
    card.asymmetry_ratio   = ratio
    return card


# ─── AMZN regression ──────────────────────────────────────────────────────────


def test_amzn_regression_penalty_is_15():
    """AMZN probabilities must produce a 15-point penalty."""
    assert asymmetry_penalty(AMZN_P_MAX_LOSS, AMZN_P_MAX_PROFIT) == AMZN_EXPECTED_PENALTY


def test_amzn_regression_ratio_approx_1898():
    """AMZN ratio must be approximately 1.898 ± 0.01."""
    ratio = asymmetry_ratio(AMZN_P_MAX_LOSS, AMZN_P_MAX_PROFIT)
    assert ratio is not None
    assert abs(ratio - AMZN_EXPECTED_RATIO) < 0.01


def test_amzn_regression_score_reduced_by_15():
    """
    Card with base score 70 + AMZN probabilities → final score 55.
    Assert: final_score == base_score - 15.
    """
    base_score = 70
    card = _make_card(base_score)
    _apply_asymmetry(card, AMZN_P_MAX_LOSS, AMZN_P_MAX_PROFIT)

    assert card.score == base_score - AMZN_EXPECTED_PENALTY


def test_amzn_regression_diagnostic_fields_populated():
    """
    After applying asymmetry, card.asymmetry_penalty and card.asymmetry_ratio
    must be set for diagnostic visibility.
    """
    card = _make_card(70)
    _apply_asymmetry(card, AMZN_P_MAX_LOSS, AMZN_P_MAX_PROFIT)

    assert card.asymmetry_penalty == AMZN_EXPECTED_PENALTY
    assert card.asymmetry_ratio is not None
    assert abs(card.asymmetry_ratio - AMZN_EXPECTED_RATIO) < 0.01


def test_amzn_regression_score_clamped_at_zero():
    """
    Card with base score 10 + 15-point penalty → final score 0 (not negative).
    """
    card = _make_card(10)
    _apply_asymmetry(card, AMZN_P_MAX_LOSS, AMZN_P_MAX_PROFIT)

    assert card.score == 0


def test_amzn_regression_penalty_independent_of_ev_gate():
    """
    Asymmetry penalty applies regardless of whether the EV gate blocked.
    (OTA-503 hard-blocks → no card is returned; OTA-505 only applies post-score.)
    Both penalties are additive when both conditions are present.
    """
    base_score = 70
    gate_penalty = 10       # simulate a non-triggering gate modifier
    card = _make_card(base_score)

    # Simulate gate penalty first (as the pipeline does)
    card.score = max(0, card.score - gate_penalty)

    # Then apply asymmetry
    _apply_asymmetry(card, AMZN_P_MAX_LOSS, AMZN_P_MAX_PROFIT)

    assert card.score == base_score - gate_penalty - AMZN_EXPECTED_PENALTY


# ─── Favorable skew (golden path) ─────────────────────────────────────────────


def test_favorable_skew_no_penalty():
    """
    p_max_loss < p_max_profit → penalty = 0 → base score unchanged.
    """
    base_score = 72
    card = _make_card(base_score)
    _apply_asymmetry(card, p_max_loss=0.30, p_max_profit=0.50)

    assert card.score == base_score
    assert card.asymmetry_penalty == 0
    assert card.asymmetry_ratio is not None
    assert card.asymmetry_ratio < 1.0


def test_missing_probabilities_no_penalty():
    """
    Trade dict without p_max_loss / p_max_profit → 0 penalty → score unchanged.
    Mirrors the None-input path in the pipeline (fields absent from request.trade).
    """
    base_score = 65
    card = _make_card(base_score)
    _apply_asymmetry(card, p_max_loss=None, p_max_profit=None)

    assert card.score == base_score
    assert card.asymmetry_penalty == 0
    assert card.asymmetry_ratio is None
