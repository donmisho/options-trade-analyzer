/**
 * Vertical Spreads — Strategy config for OptionsTerminal.
 *
 * Field names verified against ScoredSpread dataclass in vertical_engine.py
 * and the /analyze/verticals API response.
 */

import { WEIGHT_COLORS, WEIGHT_LABELS } from '../styles/tokens';

const config = {
  // ── Identity ──────────────────────────────────────────────────────────
  key: 'verticals',
  label: 'Vertical Spreads',
  tabLabel: 'Verticals',

  // ── API ───────────────────────────────────────────────────────────────
  apiEndpoint: '/analyze/verticals',
  tradesKey: 'spreads',

  buildApiParams: (symbol, cfg) => {
    const spreadTypes = [];
    if (cfg?.spreadTypes?.bull_call !== false) spreadTypes.push('bull_call');
    if (cfg?.spreadTypes?.bear_put  !== false) spreadTypes.push('bear_put');
    if (cfg?.spreadTypes?.bull_put)  spreadTypes.push('bull_put');
    if (cfg?.spreadTypes?.bear_call) spreadTypes.push('bear_call');
    if (spreadTypes.length === 0) spreadTypes.push('bull_call', 'bear_put');

    return {
      symbol,
      spread_types: spreadTypes,
      max_results: 20,
      ev_weight:    cfg?.weights?.expected_value  ?? 0.35,
      rr_weight:    cfg?.weights?.reward_risk     ?? 0.25,
      prob_weight:  cfg?.weights?.probability     ?? 0.20,
      liq_weight:   cfg?.weights?.liquidity       ?? 0.15,
      theta_weight: cfg?.weights?.theta_efficiency ?? 0.05,
      min_dte:          cfg?.dte?.min              ?? 14,
      max_dte:          cfg?.dte?.max              ?? 60,
      strike_range_pct: cfg?.strikes?.range_pct   ?? 10,
      min_spread_width: cfg?.spreads?.min_width   ?? 1,
      max_spread_width: cfg?.spreads?.max_width   ?? 10,
      min_short_delta:    cfg?.greeks?.min_short_delta        ?? 0.15,
      max_short_delta:    cfg?.greeks?.max_short_delta        ?? 0.45,
      min_net_delta:      cfg?.greeks?.min_net_delta          ?? 0,
      max_net_theta:      cfg?.greeks?.max_net_theta          ?? 0,
      min_open_interest:  cfg?.strikes?.min_open_interest     ?? 50,
      min_volume:         cfg?.strikes?.min_volume            ?? 5,
      min_reward_risk:    cfg?.systemVars?.min_reward_risk    ?? 0.5,
      min_ev_threshold:   cfg?.systemVars?.min_ev_threshold   ?? 0,
    };
  },

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
      key: 'badge',
      label: 'Type',
      width: 100,
      align: 'center',
      format: null, // rendered via getBadge
    },
    {
      key: 'long_strike',
      label: 'Spread',
      width: 90,
      align: 'center',
      format: (v, trade) => `${trade.long_strike}/${trade.short_strike}`,
    },
    {
      key: 'expiration',
      label: 'Expiration',
      width: 90,
      align: 'center',
      format: (v) => v ? `${v.slice(5)}-${v.slice(0, 4)}` : '—',
    },
    {
      key: 'net_delta',
      label: 'Delta',
      width: 65,
      align: 'right',
      format: (v) => v != null ? v.toFixed(4) : '—',
    },
    {
      key: 'net_theta',
      label: 'Theta',
      width: 65,
      align: 'right',
      format: (v) => v != null ? v.toFixed(4) : '—',
    },
    {
      key: 'net_debit',
      label: 'Net',
      width: 65,
      align: 'right',
      format: (v) => {
        if (v == null) return '—';
        return v < 0 ? `(${Math.abs(v).toFixed(2)})` : v.toFixed(2);
      },
    },
    {
      key: 'reward_risk_ratio',
      label: 'R:R',
      width: 55,
      align: 'right',
      format: (v) => v != null ? v.toFixed(2) : '—',
    },
    {
      key: 'prob_of_profit',
      label: 'Prob',
      width: 55,
      align: 'right',
      format: (v) => v != null ? `${(v * 100).toFixed(0)}%` : '—',
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
      label: 'R:R',
      title: 'Reward:Risk — green ≥1.5, amber ≥1.0, red <1.0',
      width: 36,
      align: 'center',
      format: null, // rendered as single pip
    },
    {
      key: 'pip_prob',
      label: 'Prob',
      title: 'Probability of Profit — green ≥55%, amber ≥45%, red <45%',
      width: 36,
      align: 'center',
      format: null,
    },
    {
      key: 'pip_score',
      label: 'Scr',
      title: 'Composite Score — green ≥0.65, amber ≥0.45, red <0.45',
      width: 36,
      align: 'center',
      format: null,
    },
  ],

  // ── Type badge ────────────────────────────────────────────────────────
  getBadge: (trade) => {
    const MAP = {
      bull_call: { label: 'BULL CALL', color: '#26a69a', bg: '#26a69a20' },
      bear_put:  { label: 'BEAR PUT',  color: '#f59e0b', bg: '#f59e0b20' },
      bear_call: { label: 'BEAR CALL', color: '#a855f7', bg: '#a855f720' },
      bull_put:  { label: 'BULL PUT',  color: '#4f8ef7', bg: '#4f8ef720' },
    };
    return MAP[trade.spread_type] || { label: trade.spread_type || '—', color: '#8b90a0', bg: '#8b90a020' };
  },

  // ── Health pips ───────────────────────────────────────────────────────
  getHealthPips: (trade, systemVars) => {
    const rr    = trade.reward_risk_ratio || 0;
    const prob  = trade.prob_of_profit    || 0;
    const score = trade.composite_score   || 0;
    const rrG   = systemVars?.pip_rr_green    ?? 1.5;
    const rrA   = systemVars?.pip_rr_amber    ?? 1.0;
    const prG   = systemVars?.pip_prob_green  ?? 0.55;
    const prA   = systemVars?.pip_prob_amber  ?? 0.45;
    const scG   = systemVars?.pip_score_green ?? 65;
    const scA   = systemVars?.pip_score_amber ?? 45;
    return [
      { color: rr    >= rrG ? '#26a69a' : rr    >= rrA ? '#f59e0b' : '#ef5350' },
      { color: prob  >= prG ? '#26a69a' : prob  >= prA ? '#f59e0b' : '#ef5350' },
      { color: score >= scG ? '#26a69a' : score >= scA ? '#f59e0b' : '#ef5350' },
    ];
  },

  // ── Payoff diagram ────────────────────────────────────────────────────
  payoffType: 'spread',

  payoffFn: (trade, currentPrice) => {
    const { long_strike, short_strike, net_debit, max_profit, max_loss, spread_type } = trade;
    if (!long_strike || !short_strike || net_debit == null) return [];

    const absDebit = Math.abs(net_debit);
    const absLoss  = max_loss  || absDebit;
    const absProfit = max_profit || 0;

    const priceMin = currentPrice * 0.88;
    const priceMax = currentPrice * 1.12;
    const step = (priceMax - priceMin) / 60;
    const points = [];

    const isBull = spread_type === 'bull_call' || spread_type === 'bull_put';

    for (let i = 0; i <= 60; i++) {
      const price = priceMin + i * step;
      let pnl;

      if (isBull) {
        // Bull: profit above — long_strike < short_strike
        const lo = Math.min(long_strike, short_strike);
        const hi = Math.max(long_strike, short_strike);
        if (price <= lo) {
          pnl = -(absLoss * 100);
        } else if (price >= hi) {
          pnl = absProfit * 100;
        } else {
          const t = (price - lo) / (hi - lo);
          pnl = (-absLoss + t * (absLoss + absProfit)) * 100;
        }
      } else {
        // Bear: profit below — long_strike > short_strike
        const lo = Math.min(long_strike, short_strike);
        const hi = Math.max(long_strike, short_strike);
        if (price >= hi) {
          pnl = -(absLoss * 100);
        } else if (price <= lo) {
          pnl = absProfit * 100;
        } else {
          const t = (hi - price) / (hi - lo);
          pnl = (-absLoss + t * (absLoss + absProfit)) * 100;
        }
      }

      points.push({ price: parseFloat(price.toFixed(2)), pnl: parseFloat(pnl.toFixed(2)) });
    }

    return points;
  },

  // ── Score metrics (for inline Math Matrix in Stage 2) ─────────────────
  scoreMetrics: [
    {
      key: 'expected_value',
      label: WEIGHT_LABELS.expected_value,
      weightPct: 35,
      field: 'ev_score',
      formula: '(prob × maxProfit) − (1−prob) × maxLoss',
      color: WEIGHT_COLORS.expected_value,
    },
    {
      key: 'reward_risk',
      label: WEIGHT_LABELS.reward_risk,
      weightPct: 25,
      field: 'rr_score',
      formula: 'maxProfit / maxLoss',
      color: WEIGHT_COLORS.reward_risk,
    },
    {
      key: 'probability',
      label: WEIGHT_LABELS.probability,
      weightPct: 20,
      field: 'prob_score',
      formula: '≈ long leg delta',
      color: WEIGHT_COLORS.probability,
    },
    {
      key: 'liquidity',
      label: WEIGHT_LABELS.liquidity,
      weightPct: 15,
      field: 'liquidity_score',
      formula: 'volume + open interest (both legs)',
      color: WEIGHT_COLORS.liquidity,
    },
    {
      key: 'theta_efficiency',
      label: WEIGHT_LABELS.theta_efficiency,
      weightPct: 5,
      field: 'theta_score',
      formula: 'net_theta / max_loss (inverted)',
      color: WEIGHT_COLORS.theta_efficiency,
    },
  ],
};

export default config;
