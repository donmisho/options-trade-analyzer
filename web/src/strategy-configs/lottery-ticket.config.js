/**
 * Lottery Ticket — Strategy config for SecurityDashboard scorecard and ConfigDrawer.
 *
 * 1-7 DTE deep OTM options targeting asymmetric payout on a credible catalyst.
 * Scoring is inverted — optimizes for payout ratio, not probability.
 * Minimum 5:1 payout ratio required.
 */

const config = {
  // ── Identity ──────────────────────────────────────────────────────────
  key: 'lottery-ticket',
  label: 'Lottery Ticket',
  tabLabel: 'Lottery Ticket',
  description: '1-7 DTE deep OTM, asymmetric payout, catalyst required',

  // ── Strategy classification ────────────────────────────────────────────
  scorecardStrategy: true,
  enabled: true,
  trade_structure: 'long_option',
  dte_min: 1,
  dte_max: 8,

  // ── Scoring weights ────────────────────────────────────────────────────
  scoring_weights: {
    payout_ratio:      0.45,
    delta_otm_score:   0.25,
    bid_ask_tightness: 0.20,
    open_interest:     0.10,
  },

  // ── ConfigDrawer schema ────────────────────────────────────────────────
  configSchema: [
    { key: 'dte_max',             label: 'Max DTE',            type: 'slider', min: 1,  max: 14,  default: 7,   step: 1,   unit: 'days' },
    { key: 'delta_max',           label: 'Max Delta',          type: 'slider', min: 0.05, max: 0.25, default: 0.15, step: 0.01, unit: '\u0394' },
    { key: 'min_payout_ratio',    label: 'Min Payout Ratio',   type: 'slider', min: 3,  max: 15,  default: 5,   step: 0.5, unit: ':1' },
    { key: 'max_cost_per_contract', label: 'Max Cost/Contract', type: 'number', min: 10, max: 500, default: 100, step: 10,  unit: '$' },
  ],
};

export default config;
