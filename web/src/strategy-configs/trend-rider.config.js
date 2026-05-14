/**
 * Trend Rider — Strategy config for SecurityDashboard scorecard and ConfigDrawer.
 *
 * 30-60 DTE long calls on SMA-aligned stocks. Entry requires 8 > 21 > 50 alignment.
 * Long strike delta 0.50-0.70. Avoids high IV rank (paying too much premium).
 */

const config = {
  // ── Identity ──────────────────────────────────────────────────────────
  key: 'trend-rider',
  short_code: 'TR',
  label: 'Trend Rider',
  tabLabel: 'Trend Rider',
  description: '30-60 DTE long calls on strong SMA-aligned stocks',
  color_bg: 'rgba(96,165,250,0.12)',
  color_text: 'var(--strategy-tr)',

  // ── Strategy classification ────────────────────────────────────────────
  scorecardStrategy: true,
  enabled: true,
  compatible_structures: ['bull_call_debit', 'bear_put_debit'],
  dte_min: 14,
  dte_max: 60,

  // ── Scoring weights ────────────────────────────────────────────────────
  scoring_weights: {
    sma_alignment_score:  0.30,
    delta_quality:        0.25,
    expected_value:       0.20,
    iv_percentile_cost:   0.15,
    runway_score:         0.10,
  },

  // ── ConfigDrawer schema ────────────────────────────────────────────────
  configSchema: [
    { key: 'dte_min',           label: 'Min DTE',                       type: 'slider', min: 7,   max: 30,  default: 14,  step: 1,    unit: 'days' },
    { key: 'dte_max',           label: 'Max DTE',                       type: 'slider', min: 30,  max: 90,  default: 60,  step: 1,    unit: 'days' },
    { key: 'delta_min',         label: 'Min Long Delta',                type: 'slider', min: 0.40, max: 0.70, default: 0.50, step: 0.01, unit: '\u0394' },
    { key: 'delta_max',         label: 'Max Long Delta',                type: 'slider', min: 0.50, max: 0.85, default: 0.70, step: 0.01, unit: '\u0394' },
    { key: 'iv_rank_max',       label: 'Max IV Rank (avoid overpaying)', type: 'slider', min: 40,  max: 100, default: 60,  step: 5,    unit: '%' },
    { key: 'min_sma_alignment', label: 'Require SMA Alignment',         type: 'toggle', min: 0,   max: 1,   default: 1 },
  ],
};

export default config;
