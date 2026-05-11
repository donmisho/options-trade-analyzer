/**
 * Steady Paycheck — Strategy config for SecurityDashboard scorecard and ConfigDrawer.
 *
 * 30-45 DTE credit spreads targeting consistent income via theta decay.
 * Short strike at 0.20-0.30 delta. Exit at 50% of max profit.
 */

const config = {
  // ── Identity ──────────────────────────────────────────────────────────
  key: 'steady-paycheck',
  short_code: 'SP',
  label: 'Steady Paycheck',
  tabLabel: 'Steady Paycheck',
  description: '30-45 DTE credit spreads, high IV rank, income focus',
  color_bg: 'rgba(245,158,11,0.12)',
  color_text: 'var(--strategy-sp)',

  // ── Strategy classification ────────────────────────────────────────────
  scorecardStrategy: true,        // Routed to SecurityDashboard, not OptionsTerminal
  enabled: true,                  // Visible in nav and scoring (can be overridden via strategyAdmin)
  compatible_structures: ['bull_put_credit', 'bear_call_credit'],
  non_applicable_reason: 'requires credit spread structure',
  dte_min: 14,
  dte_max: 45,

  // ── Scoring weights (used by strategy_scorer.py backend) ──────────────
  scoring_weights: {
    theta_margin_ratio:    0.30,
    probability_of_profit: 0.25,
    expected_value:        0.20,
    reward_risk:           0.15,
    iv_rank:               0.10,
  },

  // ── ConfigDrawer schema — rendered when this strategy is active ────────
  configSchema: [
    { key: 'dte_min',            label: 'Min DTE',                type: 'slider', min: 7,   max: 30,  default: 14,  step: 1,    unit: 'days' },
    { key: 'dte_max',            label: 'Max DTE',                type: 'slider', min: 21,  max: 60,  default: 45,  step: 1,    unit: 'days' },
    { key: 'delta_max',          label: 'Max Short Delta',        type: 'slider', min: 0.10, max: 0.45, default: 0.30, step: 0.01, unit: '\u0394' },
    { key: 'iv_rank_min',        label: 'Min IV Rank',            type: 'slider', min: 0,   max: 100, default: 40,  step: 5,    unit: '%' },
    { key: 'exit_profit_pct',    label: 'Take Profit At',         type: 'slider', min: 25,  max: 90,  default: 50,  step: 5,    unit: '%' },
    { key: 'stop_loss_multiple', label: 'Stop Loss (credit \xd7)', type: 'slider', min: 1.5, max: 4.0, default: 2.0, step: 0.5,  unit: '\xd7' },
  ],
};

export default config;
