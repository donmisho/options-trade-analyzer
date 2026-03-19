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
    trade_structure: str    # 'credit_spread' | 'debit_spread' | 'long_option'
    dte_min: int
    dte_max: int
    scoring_weights: dict   # metric_name → weight (must sum to 1.0)
    config_schema: List[ConfigField] = field(default_factory=list)
    # Extended fields used by STRATEGY_DEFINITIONS (Phase 2.9 scorer)
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
        description='30-45 DTE credit spreads, high IV rank, income focus',
        trade_structure='credit_spread',
        dte_min=25,
        dte_max=50,
        scoring_weights={
            'theta_margin_ratio': 0.30,
            'probability_of_profit': 0.25,
            'expected_value': 0.20,
            'reward_risk': 0.15,
            'iv_rank': 0.10,
        },
        config_schema=[
            ConfigField('dte_min', 'Min DTE', 'slider', 15, 45, 25, 1, 'days'),
            ConfigField('dte_max', 'Max DTE', 'slider', 30, 60, 50, 1, 'days'),
            ConfigField('delta_max', 'Max Short Delta', 'slider', 0.10, 0.45, 0.30, 0.01, 'Δ'),
            ConfigField('iv_rank_min', 'Min IV Rank', 'slider', 0, 100, 40, 5, '%'),
            ConfigField('exit_profit_pct', 'Take Profit At', 'slider', 25, 90, 50, 5, '%'),
            ConfigField('stop_loss_multiple', 'Stop Loss (credit ×)', 'slider', 1.5, 4.0, 2.0, 0.5, '×'),
        ]
    ),
    'weekly-grind': StrategyDefinition(
        key='weekly-grind',
        label='Weekly Grind',
        description='7-14 DTE credit spreads, Theta/Gamma efficiency focus',
        trade_structure='credit_spread',
        dte_min=5,
        dte_max=16,
        scoring_weights={
            'theta_gamma_ratio': 0.35,
            'probability_of_profit': 0.25,
            'credit_width_pct': 0.20,
            'expected_value': 0.15,
            'liquidity': 0.05,
        },
        config_schema=[
            ConfigField('dte_min', 'Min DTE', 'slider', 3, 10, 5, 1, 'days'),
            ConfigField('dte_max', 'Max DTE', 'slider', 7, 21, 14, 1, 'days'),
            ConfigField('delta_max', 'Max Short Delta', 'slider', 0.10, 0.35, 0.25, 0.01, 'Δ'),
            ConfigField('min_credit_width_pct', 'Min Credit/Width', 'slider', 15, 40, 25, 1, '%'),
            ConfigField('exit_profit_pct', 'Take Profit At', 'slider', 25, 75, 50, 5, '%'),
        ]
    ),
    'trend-rider': StrategyDefinition(
        key='trend-rider',
        label='Trend Rider',
        description='30-60 DTE long calls on strong SMA-aligned stocks',
        trade_structure='long_option',
        dte_min=25,
        dte_max=65,
        scoring_weights={
            'sma_alignment_score': 0.30,
            'delta_quality': 0.25,
            'expected_value': 0.20,
            'iv_percentile_cost': 0.15,
            'runway_score': 0.10,
        },
        config_schema=[
            ConfigField('dte_min', 'Min DTE', 'slider', 20, 45, 30, 1, 'days'),
            ConfigField('dte_max', 'Max DTE', 'slider', 45, 90, 60, 1, 'days'),
            ConfigField('delta_min', 'Min Long Delta', 'slider', 0.40, 0.70, 0.50, 0.01, 'Δ'),
            ConfigField('delta_max', 'Max Long Delta', 'slider', 0.50, 0.85, 0.70, 0.01, 'Δ'),
            ConfigField('iv_rank_max', 'Max IV Rank (avoid overpaying)', 'slider', 40, 100, 60, 5, '%'),
            ConfigField('min_sma_alignment', 'Require SMA Alignment', 'toggle', 0, 1, 1),
        ]
    ),
    'lottery-ticket': StrategyDefinition(
        key='lottery-ticket',
        label='Lottery Ticket',
        description='1-7 DTE deep OTM, asymmetric payout, catalyst required',
        trade_structure='long_option',
        dte_min=1,
        dte_max=8,
        scoring_weights={
            'payout_ratio': 0.45,
            'delta_otm_score': 0.25,
            'bid_ask_tightness': 0.20,
            'open_interest': 0.10,
        },
        config_schema=[
            ConfigField('dte_max', 'Max DTE', 'slider', 1, 14, 7, 1, 'days'),
            ConfigField('delta_max', 'Max Delta', 'slider', 0.05, 0.25, 0.15, 0.01, 'Δ'),
            ConfigField('min_payout_ratio', 'Min Payout Ratio', 'slider', 3, 15, 5, 0.5, ':1'),
            ConfigField('max_cost_per_contract', 'Max Cost/Contract', 'number', 10, 500, 100, 10, '$'),
        ]
    ),
}


# ─── Phase 2.9 — Richer strategy definitions used by the A2 scorer ───────────
# These instances carry the full parameter set (delta ranges, iv_rank gates,
# exit rules, scoring weights) that the strategy scoring engine needs.
# strategy_scorer.py continues to use STRATEGIES above; this dict is consumed
# by the new strategy_scorer_v2 and Claude evaluation prompts.

STRATEGY_DEFINITIONS = {
    "steady-paycheck": StrategyDefinition(
        key="steady-paycheck",
        name="Steady Paycheck",
        label="Steady Paycheck",
        description="30-45 DTE credit spreads, high IV rank, income focus",
        trade_structure="credit_spread",
        dte_min=30,
        dte_max=45,
        delta_min=0.20,
        delta_max=0.30,
        iv_rank_min=0.40,
        credit_pct_min=0.30,
        credit_pct_max=1.0,
        exit_profit_pct=0.50,
        exit_loss_multiplier=2.0,
        scoring_weights={
            "theta_margin_ratio": 0.30,
            "iv_rank": 0.20,
            "probability_of_profit": 0.25,
            "credit_pct_of_width": 0.15,
            "dte_fit": 0.10,
        },
    ),
    "weekly-grind": StrategyDefinition(
        key="weekly-grind",
        name="Weekly Grind",
        label="Weekly Grind",
        description="7-14 DTE credit spreads, Theta/Gamma efficiency focus",
        trade_structure="credit_spread",
        dte_min=7,
        dte_max=14,
        delta_min=0.20,
        delta_max=0.25,
        iv_rank_min=0.30,
        credit_pct_min=0.30,
        credit_pct_max=1.0,
        exit_profit_pct=0.50,
        exit_loss_multiplier=2.0,
        scoring_weights={
            "theta_gamma_ratio": 0.35,
            "credit_pct_of_width": 0.25,
            "probability_of_profit": 0.20,
            "iv_rank": 0.10,
            "dte_fit": 0.10,
        },
    ),
    "trend-rider": StrategyDefinition(
        key="trend-rider",
        name="Trend Rider",
        label="Trend Rider",
        description="30-60 DTE long calls on strong SMA-aligned stocks",
        trade_structure="long_option",
        dte_min=30,
        dte_max=60,
        delta_min=0.50,
        delta_max=0.70,
        iv_rank_min=0.0,
        credit_pct_min=0.0,
        credit_pct_max=0.40,
        exit_profit_pct=0.75,
        exit_loss_multiplier=1.0,
        scoring_weights={
            "delta_fit": 0.25,
            "sma_alignment": 0.35,
            "dte_fit": 0.20,
            "iv_rank_inverse": 0.20,
        },
    ),
    "lottery-ticket": StrategyDefinition(
        key="lottery-ticket",
        name="Lottery Ticket",
        label="Lottery Ticket",
        description="1-7 DTE deep OTM, asymmetric payout, catalyst required",
        trade_structure="long_option",
        dte_min=1,
        dte_max=7,
        delta_min=0.05,
        delta_max=0.15,
        iv_rank_min=0.0,
        credit_pct_min=0.0,
        credit_pct_max=0.40,
        exit_profit_pct=0.80,
        exit_loss_multiplier=1.0,
        scoring_weights={
            "payout_ratio": 0.45,
            "delta_fit": 0.25,
            "dte_fit": 0.20,
            "cost_pct_of_max": 0.10,
        },
    ),
}
