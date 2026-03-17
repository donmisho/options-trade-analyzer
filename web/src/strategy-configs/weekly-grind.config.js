/**
 * Weekly Grind — Strategy config for SecurityDashboard scorecard and ConfigDrawer.
 *
 * 7-14 DTE credit spreads targeting high-frequency theta capture.
 * Key focus: Theta/Gamma ratio — Gamma explodes near expiry and must be managed.
 */

const config = {
  // ── Identity ──────────────────────────────────────────────────────────
  key: 'weekly-grind',
  label: 'Weekly Grind',
  tabLabel: 'Weekly Grind',
  description: '7-14 DTE credit spreads, Theta/Gamma efficiency focus',

  // ── Strategy classification ────────────────────────────────────────────
  scorecardStrategy: true,
  trade_structure: 'credit_spread',
  non_applicable_reason: 'requires credit spread structure',
  dte_min: 5,
  dte_max: 16,

  // ── Scoring weights ────────────────────────────────────────────────────
  scoring_weights: {
    theta_gamma_ratio:     0.35,
    probability_of_profit: 0.25,
    credit_width_pct:      0.20,
    expected_value:        0.15,
    liquidity:             0.05,
  },

  // ── ConfigDrawer schema ────────────────────────────────────────────────
  configSchema: [
    { key: 'dte_min',               label: 'Min DTE',              type: 'slider', min: 3,   max: 10,  default: 5,   step: 1,    unit: 'days' },
    { key: 'dte_max',               label: 'Max DTE',              type: 'slider', min: 7,   max: 21,  default: 14,  step: 1,    unit: 'days' },
    { key: 'delta_max',             label: 'Max Short Delta',      type: 'slider', min: 0.10, max: 0.35, default: 0.25, step: 0.01, unit: '\u0394' },
    { key: 'min_credit_width_pct',  label: 'Min Credit/Width',     type: 'slider', min: 15,  max: 40,  default: 25,  step: 1,    unit: '%' },
    { key: 'exit_profit_pct',       label: 'Take Profit At',       type: 'slider', min: 25,  max: 75,  default: 50,  step: 5,    unit: '%' },
  ],
};

export default config;
