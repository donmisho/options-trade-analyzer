/**
 * Verticals Column Configuration — for use with ResultsTable.
 *
 * Exact replica of the columns previously hardcoded in OptionsTerminal.
 * Field names verified against ScoredSpread in vertical_engine.py.
 *
 * Column set: # · TYPE · SPREAD · EXPIRATION · DELTA · THETA · NET · R:R · PROB · SCORE · [R:R pip] · [PROB pip] · [SCR pip]
 * Default sort: composite_score descending.
 */

import ScoreBar from '../components/ScoreBar';

const BADGE_MAP = {
  bull_call: { label: 'BULL CALL', color: '#26a69a', bg: '#26a69a20' },
  bear_put:  { label: 'BEAR PUT',  color: '#f59e0b', bg: '#f59e0b20' },
  bear_call: { label: 'BEAR CALL', color: '#a855f7', bg: '#a855f720' },
  bull_put:  { label: 'BULL PUT',  color: '#4f8ef7', bg: '#4f8ef720' },
};

function getBadge(trade) {
  return BADGE_MAP[trade.spread_type] || { label: trade.spread_type || '—', color: '#8b90a0', bg: '#8b90a020' };
}

function pipColor(value, greenThresh, amberThresh, higherIsBetter = true) {
  if (higherIsBetter) {
    return value >= greenThresh ? '#26a69a' : value >= amberThresh ? '#f59e0b' : '#ef5350';
  }
  return value <= greenThresh ? '#26a69a' : value <= amberThresh ? '#f59e0b' : '#ef5350';
}

function Pip({ color }) {
  return (
    <div style={{ width: 10, height: 10, borderRadius: '50%', backgroundColor: color, margin: '0 auto' }} />
  );
}

export const verticalsColumns = [
  {
    key: '#',
    label: '#',
    width: 30,
    align: 'center',
    sortable: false,
    render: (trade, ctx) => (
      <span style={{ color: '#555b6e' }}>{ctx.idx + 1}</span>
    ),
  },
  {
    key: 'spread_type',
    label: 'Type',
    width: 100,
    align: 'center',
    sortable: false,
    render: (trade) => {
      const badge = getBadge(trade);
      return (
        <span style={{
          display: 'inline-block', padding: '2px 7px', borderRadius: 4,
          fontSize: 10, fontWeight: 700, letterSpacing: '0.04em',
          color: badge.color, backgroundColor: badge.bg,
        }}>
          {badge.label}
        </span>
      );
    },
  },
  {
    key: 'long_strike',
    label: 'Spread',
    width: 90,
    align: 'center',
    render: (trade) => `${trade.long_strike}/${trade.short_strike}`,
  },
  {
    key: 'expiration',
    label: 'Expiration',
    width: 90,
    align: 'center',
    render: (trade) => trade.expiration
      ? `${trade.expiration.slice(5)}-${trade.expiration.slice(0, 4)}`
      : '—',
  },
  {
    key: 'net_delta',
    label: 'Delta',
    width: 65,
    align: 'right',
    render: (trade) => trade.net_delta != null ? trade.net_delta.toFixed(4) : '—',
  },
  {
    key: 'net_theta',
    label: 'Theta',
    width: 65,
    align: 'right',
    render: (trade) => trade.net_theta != null ? trade.net_theta.toFixed(4) : '—',
  },
  {
    key: 'net_debit',
    label: 'Net',
    width: 65,
    align: 'right',
    render: (trade) => {
      const v = trade.net_debit;
      if (v == null) return '—';
      return v < 0 ? `(${Math.abs(v).toFixed(2)})` : v.toFixed(2);
    },
  },
  {
    key: 'reward_risk_ratio',
    label: 'R:R',
    width: 55,
    align: 'right',
    render: (trade) => trade.reward_risk_ratio != null ? trade.reward_risk_ratio.toFixed(2) : '—',
  },
  {
    key: 'prob_of_profit',
    label: 'Prob',
    width: 55,
    align: 'right',
    render: (trade) => trade.prob_of_profit != null
      ? `${(trade.prob_of_profit * 100).toFixed(0)}%`
      : '—',
  },
  {
    key: 'composite_score',
    label: 'Score',
    width: 80,
    align: 'center',
    render: (trade) => <ScoreBar score={trade.composite_score} />,
  },
  {
    key: 'pip_rr',
    label: 'R:R',
    title: 'Reward:Risk — green ≥1.5, amber ≥1.0, red <1.0',
    width: 36,
    align: 'center',
    sortable: false,
    render: (trade, ctx) => {
      const sv     = ctx?.systemVars || {};
      const rr     = trade.reward_risk_ratio || 0;
      const green  = sv.pip_rr_green ?? 1.5;
      const amber  = sv.pip_rr_amber ?? 1.0;
      return <Pip color={pipColor(rr, green, amber)} />;
    },
  },
  {
    key: 'pip_prob',
    label: 'Prob',
    title: 'Probability of Profit — green ≥55%, amber ≥45%, red <45%',
    width: 36,
    align: 'center',
    sortable: false,
    render: (trade, ctx) => {
      const sv    = ctx?.systemVars || {};
      const prob  = trade.prob_of_profit || 0;
      const green = sv.pip_prob_green ?? 0.55;
      const amber = sv.pip_prob_amber ?? 0.45;
      return <Pip color={pipColor(prob, green, amber)} />;
    },
  },
  {
    key: 'pip_score',
    label: 'Scr',
    title: 'Composite Score — green ≥0.65, amber ≥0.45, red <0.45',
    width: 36,
    align: 'center',
    sortable: false,
    render: (trade, ctx) => {
      const sv    = ctx?.systemVars || {};
      const score = trade.composite_score || 0;
      const green = sv.pip_score_green ?? 0.65;
      const amber = sv.pip_score_amber ?? 0.45;
      return <Pip color={pipColor(score, green, amber)} />;
    },
  },
];
