/**
 * Long Options (Puts & Calls) Column Configuration — for use with ResultsTable.
 *
 * Field names verified against ScoredNakedOption in long_call_engine.py.
 *
 * Column set: TYPE · STRIKE · EXPIRATION · DELTA · THETA/DAY · PREMIUM · BREAKEVEN · vs ITM · SCORE · [Δ pip] · [IV pip] · [Run pip]
 * Default sort: composite_score descending.
 *
 * vs ITM column:
 *   Requires pre-computed trade.vs_itm_dollars field.
 *   Parent must add: trade.vs_itm_dollars = (call: price - strike, put: strike - price)
 *   before passing results to ResultsTable. See OptionsTerminal.jsx displayResults.
 *
 * Sorting by vs ITM uses vs_itm_dollars (positive = ITM, negative = OTM).
 */

import ScoreBar from '../components/ScoreBar';

function Pip({ color }) {
  return (
    <div style={{ width: 10, height: 10, borderRadius: '50%', backgroundColor: color, margin: '0 auto' }} />
  );
}

function pipColor(value, greenThresh, amberThresh, higherIsBetter = true) {
  if (higherIsBetter) {
    return value >= greenThresh ? '#26a69a' : value >= amberThresh ? '#f59e0b' : '#ef5350';
  }
  return value <= greenThresh ? '#26a69a' : value <= amberThresh ? '#f59e0b' : '#ef5350';
}

export const longOptionsColumns = [
  {
    key: 'option_type',
    label: 'Type',
    width: 100,
    align: 'center',
    sortable: false,
    render: (trade) => {
      const isCall = trade.option_type === 'call';
      const label  = isCall ? 'LONG CALL' : 'LONG PUT';
      const color  = isCall ? '#26a69a' : '#f59e0b';
      return (
        <span style={{
          display: 'inline-block', padding: '2px 7px', borderRadius: 4,
          fontSize: 10, fontWeight: 700, letterSpacing: '0.04em',
          color, backgroundColor: color + '20',
        }}>
          {label}
        </span>
      );
    },
  },
  {
    key: 'strike',
    label: 'Strike',
    width: 70,
    align: 'right',
    render: (trade) => trade.strike != null ? Math.round(trade.strike) : '—',
  },
  {
    key: 'expiration',
    label: 'Expiration',
    width: 90,
    align: 'center',
    render: (trade) => {
      if (!trade.expiration) return '—';
      const [yr, mo, dy] = trade.expiration.split('-');
      return `${mo}/${dy}/${yr.slice(2)}`;
    },
  },
  {
    key: 'delta',
    label: 'Delta',
    width: 65,
    align: 'right',
    render: (trade) => trade.delta != null ? trade.delta.toFixed(4) : '—',
  },
  {
    key: 'iv',
    label: 'IV',
    title: 'Implied volatility of this contract',
    width: 60,
    align: 'right',
    render: (trade) => trade.iv != null ? (trade.iv * 100).toFixed(1) + '%' : '—',
  },
  {
    key: 'theta_per_day_dollars',
    label: 'Theta/Day',
    width: 80,
    align: 'right',
    render: (trade) => trade.theta_per_day_dollars != null
      ? `${trade.theta_per_day_dollars.toFixed(2)}`
      : '—',
  },
  {
    key: 'mid_price',
    label: 'Premium',
    width: 70,
    align: 'right',
    render: (trade) => trade.mid_price != null ? trade.mid_price.toFixed(2) : '—',
  },
  {
    key: 'breakeven',
    label: 'Breakeven',
    width: 85,
    align: 'right',
    render: (trade) => trade.breakeven != null ? trade.breakeven.toFixed(2) : '—',
  },
  {
    // Computed column — requires trade.vs_itm_dollars to be pre-populated by parent
    key: '_vs_itm',
    sortKey: 'vs_itm_dollars',
    label: 'vs ITM',
    width: 110,
    align: 'right',
    render: (trade, ctx) => {
      const price    = ctx?.currentPrice;
      const strike   = trade.strike;
      if (!price || strike == null) return '—';

      const isCall   = trade.option_type === 'call';
      // For calls: ITM when price > strike. For puts: ITM when price < strike.
      const distance = isCall ? price - strike : strike - price;
      const pct      = (distance / price) * 100;

      const color = distance > 0
        ? '#4ade80'                              // green — ITM
        : Math.abs(pct) < 5
          ? '#f59e0b'                            // amber — close to money
          : '#8b949e';                           // muted — comfortably OTM

      const sign = distance > 0 ? '+' : '';
      return (
        <span style={{ color, fontFamily: 'monospace' }}>
          {sign}{distance.toFixed(2)} / {sign}{pct.toFixed(1)}%
        </span>
      );
    },
  },
  {
    key: 'composite_score',
    label: 'Score',
    width: 80,
    align: 'center',
    render: (trade) => <ScoreBar score={trade.composite_score} />,
  },
  {
    key: 'pip_delta',
    label: 'Δ',
    title: 'Delta — green 0.30–0.65, amber near edges, red outside',
    width: 36,
    align: 'center',
    sortable: false,
    render: (trade, ctx) => {
      const sv       = ctx?.systemVars || {};
      const delta    = trade.delta || 0;
      const lo       = sv.pip_delta_lo ?? 0.30;
      const hi       = sv.pip_delta_hi ?? 0.65;
      const edgeBand = 0.05;
      const ok   = delta >= lo && delta <= hi;
      const warn = (delta >= lo - edgeBand && delta < lo) || (delta > hi && delta <= hi + edgeBand);
      return <Pip color={ok ? '#26a69a' : warn ? '#f59e0b' : '#ef5350'} />;
    },
  },
  {
    key: 'pip_iv',
    label: 'IV',
    title: 'Implied Volatility — green ≤30%, amber ≤50%, red >50%',
    width: 36,
    align: 'center',
    sortable: false,
    render: (trade, ctx) => {
      const sv    = ctx?.systemVars || {};
      const iv    = trade.iv || 0;
      const green = sv.pip_iv_green ?? 0.30;
      const amber = sv.pip_iv_amber ?? 0.50;
      return <Pip color={pipColor(iv, green, amber, false)} />;
    },
  },
  {
    key: 'pip_runway',
    label: 'Run',
    title: 'Theta Runway — green ≥30d, amber ≥15d, red <15d',
    width: 36,
    align: 'center',
    sortable: false,
    render: (trade, ctx) => {
      const sv     = ctx?.systemVars || {};
      const runway = trade.theta_runway_days || 0;
      const green  = sv.pip_runway_green ?? 30;
      const amber  = sv.pip_runway_amber ?? 15;
      return <Pip color={pipColor(runway, green, amber)} />;
    },
  },
];
