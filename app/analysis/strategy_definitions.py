from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ConfigField:
    key: str
    label: str
    type: str           # 'slider' | 'toggle' | 'number'
    min: float = 0
    max: float = 100
    default: float = 50
    step: float = 1
    unit: str = ''      # '%', 'days', 'delta', etc.


@dataclass
class StrategyDefinition:
    key: str
    label: str
    description: str
    compatible_structures: List[str]    # e.g. ['bull_put_credit', 'bear_call_credit']
    dte_min: int
    dte_max: int
    scoring_weights: dict   # metric_name → weight (must sum to 1.0)
    config_schema: List[ConfigField] = field(default_factory=list)
    # Extended fields for scoring parameters
    name: Optional[str] = None          # same as label; preferred by A2 scorer
    delta_min: float = 0.0
    delta_max: float = 1.0
    iv_rank_min: float = 0.0            # 0.0–1.0 decimal
    credit_pct_min: float = 0.0         # min credit as % of spread width
    credit_pct_max: float = 1.0         # max credit as % of spread width
    exit_profit_pct: float = 0.50       # take profit target as % of max profit
    exit_loss_multiplier: float = 2.0   # stop loss as multiple of credit received


STRATEGIES = {
    'steady-paycheck': StrategyDefinition(
        key='steady-paycheck',
        label='Steady Paycheck',
        description='14-45 DTE credit spreads, high IV rank, income focus',
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
        config_schema=[
            ConfigField('dte_min', 'Min DTE', 'slider', 7, 30, 14, 1, 'days'),
            ConfigField('dte_max', 'Max DTE', 'slider', 21, 60, 45, 1, 'days'),
            ConfigField('delta_max', 'Max Short Delta', 'slider', 0.10, 0.45, 0.30, 0.01, 'Δ'),
            ConfigField('iv_rank_min', 'Min IV Rank', 'slider', 0, 100, 40, 5, '%'),
            ConfigField('exit_profit_pct', 'Take Profit At', 'slider', 25, 90, 50, 5, '%'),
            ConfigField('stop_loss_multiple', 'Stop Loss (credit ×)', 'slider', 1.5, 4.0, 2.0, 0.5, '×'),
        ]
    ),
    'weekly-grind': StrategyDefinition(
        key='weekly-grind',
        label='Weekly Grind',
        description='14-21 DTE credit spreads, Theta/Gamma efficiency focus',
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
        config_schema=[
            ConfigField('dte_min', 'Min DTE', 'slider', 7, 18, 14, 1, 'days'),
            ConfigField('dte_max', 'Max DTE', 'slider', 14, 30, 21, 1, 'days'),
            ConfigField('delta_max', 'Max Short Delta', 'slider', 0.10, 0.35, 0.25, 0.01, 'Δ'),
            ConfigField('min_credit_width_pct', 'Min Credit/Width', 'slider', 15, 40, 25, 1, '%'),
            ConfigField('exit_profit_pct', 'Take Profit At', 'slider', 25, 75, 50, 5, '%'),
        ]
    ),
    'trend-rider': StrategyDefinition(
        key='trend-rider',
        label='Trend Rider',
        description='14-60 DTE long calls on strong SMA-aligned stocks',
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
        config_schema=[
            ConfigField('dte_min', 'Min DTE', 'slider', 7, 30, 14, 1, 'days'),
            ConfigField('dte_max', 'Max DTE', 'slider', 30, 90, 60, 1, 'days'),
            ConfigField('delta_min', 'Min Long Delta', 'slider', 0.40, 0.70, 0.50, 0.01, 'Δ'),
            ConfigField('delta_max', 'Max Long Delta', 'slider', 0.50, 0.85, 0.70, 0.01, 'Δ'),
            ConfigField('iv_rank_max', 'Max IV Rank (avoid overpaying)', 'slider', 40, 100, 60, 5, '%'),
            ConfigField('min_sma_alignment', 'Require SMA Alignment', 'toggle', 0, 1, 1),
        ]
    ),
    'lottery-ticket': StrategyDefinition(
        key='lottery-ticket',
        label='Lottery Ticket',
        description='7-60 DTE deep OTM, asymmetric payout, catalyst required',
        compatible_structures=['long_call', 'long_put'],
        dte_min=7,
        dte_max=60,
        scoring_weights={
            'payout_ratio': 0.45,
            'delta_otm_score': 0.25,
            'bid_ask_tightness': 0.20,
            'open_interest': 0.10,
        },
        config_schema=[
            ConfigField('dte_max', 'Max DTE', 'slider', 14, 90, 60, 1, 'days'),
            ConfigField('delta_max', 'Max Delta', 'slider', 0.05, 0.25, 0.15, 0.01, 'Δ'),
            ConfigField('min_payout_ratio', 'Min Payout Ratio', 'slider', 3, 15, 5, 0.5, ':1'),
            ConfigField('max_cost_per_contract', 'Max Cost/Contract', 'number', 10, 500, 100, 10, '$'),
        ]
    ),
}
