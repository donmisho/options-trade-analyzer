/**
 * Positions Column Configuration — v3 redesign.
 *
 * Column order: chevron · score · symbol · pos_type · strategy_key
 *               · strike_spread · expiration · entry_price · current_premium
 *               · pnl · dte · health · _actions
 *
 * OTA-362
 */

import StrategyPill from '../components/StrategyPill';
import ScoreCell from '../components/ScoreCell';
import { PositionHealthBadge } from '../components/PositionHealthBadge';
import { formatDate } from '../utils/formatDate';

function PositionTypeBadge({ source }) {
  const isLive = source === 'LIVE';
  return (
    <span style={{
      display: 'inline-block',
      fontSize: 9, fontWeight: 700,
      padding: '2px 6px', borderRadius: 3,
      backgroundColor: isLive ? 'rgba(74,222,128,0.12)' : 'rgba(96,165,250,0.12)',
      color: isLive ? 'var(--green, #4ade80)' : 'var(--blue, #60a5fa)',
      fontFamily: 'monospace',
    }}>
      {isLive ? 'Live' : 'Paper'}
    </span>
  );
}

// strategy_key uses hyphens; StrategyPill expects underscores
function toUnderscoreKey(key) {
  return (key || '').replace(/-/g, '_');
}

// Numeric sort weight for health grade (A=best)
function healthSortWeight(grade) {
  return { A: 5, B: 4, C: 3, D: 2, F: 1 }[grade] ?? 0;
}

export const positionsColumns = [
  {
    key: '_chevron',
    label: '',
    width: 22,
    align: 'left',
    sortable: false,
    render: (pos, ctx) => (
      <span style={{ color: 'var(--muted, #8b949e)', fontSize: 9, lineHeight: 1 }}>
        {ctx?.isExpanded ? '▼' : '▶'}
      </span>
    ),
  },
  {
    key: 'score',
    label: 'Score',
    width: 100,
    align: 'left',
    sortable: true,
    sortValue: (pos) => pos.score ?? 0,
    render: (pos) => <ScoreCell score={pos.score ?? 0} />,
  },
  {
    key: 'symbol',
    label: 'Symbol',
    width: 80,
    align: 'left',
    sortable: true,
    render: (pos) => (
      <span style={{ color: '#2dd4bf', fontWeight: 700 }}>{pos.symbol}</span>
    ),
  },
  {
    key: 'pos_type',
    label: 'Type',
    width: 70,
    align: 'center',
    sortable: true,
    sortKey: 'source',
    render: (pos) => <PositionTypeBadge source={pos.source} />,
  },
  {
    key: 'strategy_key',
    label: 'Strategy',
    width: 60,
    align: 'center',
    sortable: true,
    render: (pos) => <StrategyPill strategy={toUnderscoreKey(pos.strategy_key)} />,
  },
  {
    key: 'strike_spread',
    label: 'Strike/Spread',
    width: 100,
    align: 'center',
    sortable: false,
    render: (pos) => {
      if (pos.short_strike && pos.long_strike) return `${pos.short_strike}/${pos.long_strike}`;
      if (pos.strike) return String(pos.strike);
      return pos.strike_spread ?? '—';
    },
  },
  {
    key: 'expiration',
    label: 'Expiration',
    width: 95,
    align: 'center',
    sortable: true,
    render: (pos) => pos.expiration ? formatDate(pos.expiration) : '—',
  },
  {
    key: 'entry_price',
    label: 'Premium',
    width: 70,
    align: 'right',
    sortable: true,
    render: (pos) => pos.entry_price != null ? Number(pos.entry_price).toFixed(2) : '—',
  },
  {
    key: 'current_premium',
    label: 'Current',
    width: 70,
    align: 'right',
    sortable: true,
    render: (pos) => pos.current_premium != null ? Number(pos.current_premium).toFixed(2) : '—',
  },
  {
    key: 'pnl',
    label: 'P&L',
    width: 130,
    align: 'right',
    sortable: true,
    sortValue: (pos) => pos.pnl_amount ?? -Infinity,
    render: (pos) => {
      const amt = pos.pnl_amount;
      const pct = pos.pnl_pct;
      if (amt == null) return '—';
      const color = amt >= 0 ? 'var(--green, #4ade80)' : 'var(--red, #f87171)';
      const sign  = amt >= 0 ? '+' : '';
      return (
        <span style={{ color, fontFamily: 'monospace' }}>
          {sign}{Number(amt).toFixed(2)}
          {pct != null && ` (${sign}${Number(pct).toFixed(2)}%)`}
        </span>
      );
    },
  },
  {
    key: 'dte',
    label: 'DTE',
    width: 50,
    align: 'center',
    sortable: true,
    render: (pos) => pos.dte != null ? String(pos.dte) : '—',
  },
  {
    key: 'health',
    label: 'Health',
    width: 60,
    align: 'center',
    sortable: true,
    sortValue: (pos) => healthSortWeight(pos.health_grade),
    render: (pos) => <PositionHealthBadge grade={pos.health_grade} />,
  },
  {
    key: '_actions',
    label: '',
    width: 56,
    align: 'center',
    sortable: false,
    render: (pos, ctx) => (
      <span className="row-actions" onClick={e => e.stopPropagation()}>
        <button
          className="icon-btn"
          title="Refresh analysis"
          onClick={() => ctx?.onRefresh?.(pos)}
          disabled={ctx?.isRefreshing}
          style={ctx?.isRefreshing ? { opacity: 0.5 } : undefined}
        >
          {ctx?.isRefreshing ? '…' : '↻'}
        </button>
        <button
          className="icon-btn archive"
          title="Archive position"
          onClick={() => ctx?.onArchive?.(pos)}
        >
          ⊘
        </button>
      </span>
    ),
  },
];

export const POSITIONS_DEFAULT_SORT = { key: 'score', dir: 'desc' };
