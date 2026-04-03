/**
 * Long Options (Puts & Calls) Column Configuration — v3 layout for ResultsTable.
 *
 * v3 column order (chevron handled by ResultsTable):
 *   Score · Strike · Type · Expiration · Delta · IV · Theta/Day · Premium · Breakeven · vs ITM · Strategies
 *
 * Field names verified against ScoredNakedOption in long_call_engine.py.
 * Row numbers and pip columns removed per UI-GUIDANCE v3.1.
 *
 * vs ITM: requires trade.vs_itm_dollars pre-computed by parent
 *   (call: price - strike, put: strike - price)
 */

import ScoreCell from '../components/ScoreCell';
import TradeTypeBadge from '../components/TradeTypeBadge';
import StrategyPill from '../components/StrategyPill';

export const longOptionsColumns = [
  {
    key: 'composite_score',
    label: 'Score',
    width: 90,
    align: 'left',
    sortable: true,
    render: (trade) => <ScoreCell score={trade.composite_score} />,
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
  {
    key: 'strike',
    label: 'Strike',
    width: 70,
    align: 'right',
    render: (trade) => trade.strike != null ? Math.round(trade.strike) : '—',
  },
  {
    key: 'option_type',
    label: 'Type',
    width: 100,
    align: 'center',
    render: (trade) => {
      const label = trade.option_type === 'call' ? 'LONG_CALL' : 'LONG_PUT';
      return <TradeTypeBadge type={label} />;
    },
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
    width: 65,
    align: 'right',
    render: (trade) => trade.iv != null ? `${(trade.iv * 100).toFixed(2)}%` : '—',
  },
  {
    key: 'theta_per_day_dollars',
    label: 'Theta/Day',
    width: 100,
    align: 'right',
    render: (trade, ctx) => {
      const theta = trade.theta_per_day_dollars;
      if (theta == null) return '—';
      const dollarDisplay = theta.toFixed(2);
      const premium = trade.mid_price;
      if (!premium || premium === 0) return dollarDisplay;
      const totalPremium = premium * 100;
      const thetaPct = (theta / totalPremium) * 100;
      const threshold = ctx?.thetaThreshold ?? 10;
      if (thetaPct <= threshold) {
        return `${dollarDisplay} / ${thetaPct.toFixed(2)}%`;
      }
      return dollarDisplay;
    },
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
    key: '_vs_itm',
    sortKey: 'vs_itm_dollars',
    label: 'vs ITM',
    width: 110,
    align: 'right',
    render: (trade, ctx) => {
      const price  = ctx?.currentPrice;
      const strike = trade.strike;
      if (!price || strike == null) return '—';
      const isCall   = trade.option_type === 'call';
      const distance = isCall ? price - strike : strike - price;
      const pct      = (distance / price) * 100;
      const color = distance > 0
        ? 'var(--green)'
        : Math.abs(pct) < 5 ? 'var(--amber)' : 'var(--muted)';
      const sign = distance > 0 ? '+' : '';
      return (
        <span style={{ color, fontFamily: 'monospace' }}>
          {sign}{distance.toFixed(2)} / {sign}{pct.toFixed(1)}%
        </span>
      );
    },
  },
];
