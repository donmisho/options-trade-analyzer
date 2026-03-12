/**
 * Puts & Calls (Long Calls) — Strategy config for OptionsTerminal.
 *
 * Field names verified against ScoredNakedOption dataclass in long_call_engine.py
 * and the /analyze/long-calls API response.
 *
 * NakedOptionEngine scores: delta_alignment (30%), theta_efficiency (25%),
 * iv_value (20%), reward_risk (15%), liquidity (10%).
 */

const SCORE_COLORS = {
  delta:   '#4f8ef7',
  theta:   '#26a69a',
  iv:      '#f59e0b',
  rr:      '#a855f7',
  liq:     '#ec4899',
};

const config = {
  // ── Identity ──────────────────────────────────────────────────────────
  key: 'long_calls',
  label: 'Puts & Calls',
  tabLabel: 'Puts & Calls',

  // ── API ───────────────────────────────────────────────────────────────
  apiEndpoint: '/analyze/long-calls',
  tradesKey: 'calls',

  buildApiParams: (symbol, cfg) => ({
    symbol,
    max_results: 20,
    option_types: ['call'],
    min_dte: cfg?.dte?.min ?? 7,
    max_dte: cfg?.dte?.max ?? 90,
    strike_range_pct: cfg?.strikes?.range_pct ?? 10,
  }),

  // ── Grid columns ──────────────────────────────────────────────────────
  columns: [
    {
      key: '#',
      label: '#',
      width: 30,
      align: 'center',
      format: (_, __, idx) => idx + 1,
    },
    {
      key: 'strike',
      label: 'Strike',
      width: 70,
      align: 'right',
      format: (v) => v != null ? Math.round(v) : '—',
    },
    {
      key: 'expiration',
      label: 'Expiration',
      width: 95,
      align: 'center',
      format: (v) => {
        if (!v) return '—';
        const [yr, mo, dy] = v.split('-');
        return `${dy}-${mo}-${yr}`;
      },
    },
    {
      key: 'delta',
      label: 'Delta',
      width: 65,
      align: 'right',
      format: (v) => v != null ? v.toFixed(4) : '—',
    },
    {
      key: 'iv',
      label: 'IV',
      width: 65,
      align: 'right',
      format: (v) => v != null ? `${v.toFixed(1)}%` : '—',
    },
    {
      key: 'mid_price',
      label: 'Premium',
      width: 70,
      align: 'right',
      format: (v) => v != null ? v.toFixed(2) : '—',
    },
    {
      key: 'breakeven',
      label: 'Breakeven',
      width: 85,
      align: 'right',
      format: (v) => v != null ? v.toFixed(2) : '—',
    },
    {
      key: 'theta_runway_days',
      label: 'Runway',
      width: 80,
      align: 'right',
      format: (v) => v != null ? `${Math.round(v)}d` : '—',
    },
    {
      key: 'composite_score',
      label: 'Score',
      width: 80,
      align: 'center',
      format: null, // rendered as ScoreBar
    },
    {
      key: 'pip_rr',
      label: 'Δ',
      title: 'Delta — green 0.30–0.65, amber near edges, red outside',
      width: 36,
      align: 'center',
      format: null,
    },
    {
      key: 'pip_prob',
      label: 'IV',
      title: 'Implied Volatility — green ≤30%, amber ≤50%, red >50%',
      width: 36,
      align: 'center',
      format: null,
    },
    {
      key: 'pip_score',
      label: 'Run',
      title: 'Theta Runway — green ≥30d, amber ≥15d, red <15d',
      width: 36,
      align: 'center',
      format: null,
    },
  ],

  // ── Type badge ────────────────────────────────────────────────────────
  getBadge: (trade) => {
    if (trade.option_type === 'put') {
      return { label: 'LONG PUT', color: '#f59e0b', bg: '#f59e0b20' };
    }
    return { label: 'LONG CALL', color: '#26a69a', bg: '#26a69a20' };
  },

  // ── Health pips ───────────────────────────────────────────────────────
  getHealthPips: (trade, systemVars) => {
    const delta  = trade.delta             || 0;
    const iv     = trade.iv                || 0;
    const runway = trade.theta_runway_days || 0;

    const deltaLo      = systemVars?.pip_delta_lo      ?? 0.30;
    const deltaHi      = systemVars?.pip_delta_hi      ?? 0.65;
    const ivGreen      = systemVars?.pip_iv_green      ?? 30;
    const ivAmber      = systemVars?.pip_iv_amber      ?? 50;
    const runwayGreen  = systemVars?.pip_runway_green  ?? 30;
    const runwayAmber  = systemVars?.pip_runway_amber  ?? 15;

    const edgeBand = 0.05;
    const deltaOk   = delta >= deltaLo && delta <= deltaHi;
    const deltaWarn = (delta >= deltaLo - edgeBand && delta < deltaLo) ||
                      (delta > deltaHi && delta <= deltaHi + edgeBand);

    return [
      { color: deltaOk ? '#26a69a' : deltaWarn ? '#f59e0b' : '#ef5350' },
      { color: iv <= ivGreen ? '#26a69a' : iv <= ivAmber ? '#f59e0b' : '#ef5350' },
      { color: runway >= runwayGreen ? '#26a69a' : runway >= runwayAmber ? '#f59e0b' : '#ef5350' },
    ];
  },

  // ── Payoff diagram ────────────────────────────────────────────────────
  payoffType: 'single_leg',
  payoffFn: null,

  // ── Score metrics (for inline Math Matrix in Stage 2) ─────────────────
  scoreMetrics: [
    {
      key: 'delta_alignment',
      label: 'Delta Alignment',
      weightPct: 30,
      field: 'delta_score',
      formula: 'sweet spot at 0.45, scores fall off on either side',
      color: SCORE_COLORS.delta,
    },
    {
      key: 'theta_efficiency',
      label: 'Theta Efficiency',
      weightPct: 25,
      field: 'theta_score',
      formula: 'premium / |daily theta| → days of runway',
      color: SCORE_COLORS.theta,
    },
    {
      key: 'iv_value',
      label: 'IV Value',
      weightPct: 20,
      field: 'iv_score',
      formula: 'lower IV = cheaper premium = better entry',
      color: SCORE_COLORS.iv,
    },
    {
      key: 'reward_risk',
      label: 'Reward : Risk',
      weightPct: 15,
      field: 'rr_score',
      formula: '(delta × 100) / premium_dollars',
      color: SCORE_COLORS.rr,
    },
    {
      key: 'liquidity',
      label: 'Liquidity',
      weightPct: 10,
      field: 'liquidity_score',
      formula: 'volume + open interest',
      color: SCORE_COLORS.liq,
    },
  ],
};

export default config;
