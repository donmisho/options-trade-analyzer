from dataclasses import dataclass
from typing import List, Optional


@dataclass
class StrategyConfig:
    """
    Generic strategy configuration — engine-level.

    Contains only structural/routing fields the engine needs:
    key, label, compatible structures, DTE bounds, and scoring weights.
    No options-domain vocabulary (delta, IV, credit, exit levels).

    Split from the former StrategyDefinition (OTA-778).
    """
    key: str
    label: str
    compatible_structures: List[str]    # e.g. ['bull_put_credit', 'bear_call_credit']
    # dte_min / dte_max: interim in-code canonical source for both the scorer
    # and the classifier. Pending engine_strategies read-side repoint (OTA-757 / OTA-779).
    dte_min: int
    dte_max: int
    scoring_weights: dict   # metric_name → weight (must sum to 1.0)


@dataclass
class OptionsStrategyParams:
    """
    Options-domain parameters for a strategy.

    These are options-specific values that the engine does not reference.
    Sourced from junction rows / adapter once the engine tables exist;
    interim in-code values until then.

    Split from the former StrategyDefinition (OTA-778).
    Dead fields dropped: name, delta_min, delta_max, iv_rank_min,
    credit_pct_min, credit_pct_max, exit_profit_pct, exit_loss_multiplier,
    description, config_schema (and ConfigField).
    """
    cushion_severe_threshold: float = 1.0   # cushion_pct below this → severe penalty
    cushion_moderate_threshold: float = 2.0 # cushion_pct below this → moderate penalty


STRATEGIES = {
    'steady-paycheck': StrategyConfig(
        key='steady-paycheck',
        label='Steady Paycheck',
        compatible_structures=['bull_put_credit', 'bear_call_credit'],
        dte_min=14,
        dte_max=45,
        scoring_weights={
            'theta_margin_ratio': 0.30,
            'probability_of_profit': 0.25,
            'expected_value': 0.20,
            'reward_risk': 0.15,
            'iv_rank': 0.10,
        },
    ),
    'weekly-grind': StrategyConfig(
        key='weekly-grind',
        label='Weekly Grind',
        compatible_structures=['bull_put_credit', 'bear_call_credit'],
        dte_min=14,
        dte_max=21,
        scoring_weights={
            'theta_gamma_ratio': 0.35,
            'probability_of_profit': 0.25,
            'credit_width_pct': 0.20,
            'expected_value': 0.15,
            'liquidity': 0.05,
        },
    ),
    'trend-rider': StrategyConfig(
        key='trend-rider',
        label='Trend Rider',
        compatible_structures=['bull_call_debit', 'bear_put_debit'],
        dte_min=14,
        dte_max=60,
        scoring_weights={
            'sma_alignment_score': 0.30,
            'delta_quality': 0.25,
            'expected_value': 0.20,
            'iv_percentile_cost': 0.15,
            'runway_score': 0.10,
        },
    ),
    'lottery-ticket': StrategyConfig(
        key='lottery-ticket',
        label='Lottery Ticket',
        compatible_structures=['long_call', 'long_put'],
        dte_min=7,
        dte_max=60,
        scoring_weights={
            'payout_ratio': 0.45,
            'delta_otm_score': 0.25,
            'bid_ask_tightness': 0.20,
            'open_interest': 0.10,
        },
    ),
}


# Options-domain params keyed by strategy.
# Only credit-spread strategies use cushion thresholds; entries here
# carry the per-strategy values.  Strategies without an entry get
# the OptionsStrategyParams defaults if looked up via .get().
OPTIONS_STRATEGY_PARAMS = {
    'steady-paycheck': OptionsStrategyParams(
        cushion_severe_threshold=1.0,
        cushion_moderate_threshold=2.0,
    ),
    'weekly-grind': OptionsStrategyParams(
        cushion_severe_threshold=1.0,
        cushion_moderate_threshold=2.0,
    ),
}


@dataclass
class StrategyScore:
    strategy_key: str
    label: str
    score: int                    # 0-100 (post-penalty)
    best_trade: Optional[dict]    # top-scoring candidate for this strategy
    signal_summary: str           # brief human-readable summary
    metric_scores: dict           # individual metric values for transparency
    raw_score: Optional[int] = None  # 0-100 pre-penalty; None when no penalty
    component_breakdown: Optional[list] = None  # [{key, score, weight, contribution}, ...]
    penalty_reason: Optional[str] = None  # e.g. "cushion penalty" when raw != score


# Display-name mapping: internal metric key -> v2 export label.
# Order matches the QQQ v2 sample row order (OTA-643).
COMPONENT_DISPLAY_NAMES = {
    "expected_value":        "Expected value (EV)",
    "probability_of_profit": "Expected value (EV)",   # folds into EV for display
    "reward_risk":           "Structure fit (vs profile)",
    "credit_width_pct":      "Structure fit (vs profile)",
    "theta_margin_ratio":    "Structure fit (vs profile)",
    "theta_gamma_ratio":     "Structure fit (vs profile)",
    "delta_quality":         "Structure fit (vs profile)",
    "cushion_strike":        "Cushion / strike placement",
    "sma_alignment_score":   "Technical alignment (SMAs)",
    "iv_rank":               "IV environment",
    "iv_percentile_cost":    "IV environment",
    "runway_score":          "DTE fit",
    "payout_ratio":          "DTE fit",
    "delta_otm_score":       "DTE fit",
    "liquidity":             "Liquidity (bid-ask, volume)",
    "bid_ask_tightness":     "Liquidity (bid-ask, volume)",
    "open_interest":         "Liquidity (bid-ask, volume)",
}
