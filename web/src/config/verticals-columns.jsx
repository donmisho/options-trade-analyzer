/**
 * Verticals Column Configuration — v3 layout for ResultsTable.
 *
 * v3 column order (chevron handled by ResultsTable):
 *   Score · Spread · Type · Expiration · Delta · IV · Theta · Net · R:R · Prob · Strategies
 *
 * Field names verified against ScoredSpread in vertical_engine.py.
 * Row numbers removed per UI-GUIDANCE v3.1.
 * Pip columns removed — score thresholds communicated via ScoreCell color.
 */

import ScoreCell from '../components/ScoreCell';
import TradeTypeBadge from '../components/TradeTypeBadge';
import StrategyPill from '../components/StrategyPill';

export const verticalsColumns = [
  {
    key: 'composite_score',
    label: 'Score',
    width: 90,
    align: 'left',
    sortable: true,
    render: (trade) => <ScoreCell score={trade.composite_score} />,
  },
  {
    key: 'long_strike',
    label: 'Spread',
    width: 90,
    align: 'center',
    sortable: true,
    render: (trade) => trade.long_strike != null && trade.short_strike != null
      ? `${trade.long_strike}/${trade.short_strike}`
      : '—',
  },
  {
    key: 'spread_type',
    label: 'Type',
    width: 110,
    align: 'center',
    sortable: true,
    render: (trade) => <TradeTypeBadge type={trade.spread_type} />,
  },
  {
    key: 'expiration',
    label: 'Expiration',
    width: 90,
    align: 'center',
    render: (trade) => {
      if (!trade.expiration) return '—';
      const [yr, mo, dy] = trade.expiration.split('-');
      return `${mo}-${dy}-${yr}`;
    },
  },
  {
    key: 'net_delta',
    label: 'Delta',
    width: 65,
    align: 'right',
    render: (trade) => trade.net_delta != null ? trade.net_delta.toFixed(4) : '—',
  },
  {
    key: 'iv',
    label: 'IV',
    title: 'Implied volatility of the short leg',
    width: 65,
    align: 'right',
    render: (trade) => trade.iv != null ? `${(trade.iv * 100).toFixed(2)}%` : '—',
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
    width: 60,
    align: 'right',
    render: (trade) => trade.reward_risk_ratio != null
      ? `${trade.reward_risk_ratio.toFixed(2)}:1`
      : '—',
  },
  {
    key: 'prob_of_profit',
    label: 'Prob',
    width: 65,
    align: 'right',
    render: (trade) => trade.prob_of_profit != null
      ? `${(trade.prob_of_profit * 100).toFixed(2)}%`
      : '—',
  },
  {
    key: 'strategies',
    label: 'Strategies',
    width: 90,
    align: 'left',
    sortable: false,
    render: (trade) => {
      const pills = trade.strategies || trade.strategy_pills || [];
      if (!pills.length) return null;
      return (
        <span>
          {pills.map((s, i) => <StrategyPill key={i} strategy={s} />)}
        </span>
      );
    },
  },
];
