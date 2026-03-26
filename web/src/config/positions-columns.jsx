/**
 * Positions Column Configuration — for use with PositionsTable.
 *
 * Columns: _chevron · symbol · pos_type · strategy_key · structure · trade_type
 *          · analysis_date · strike_spread · expiration · entry_price
 *          · current_premium · pnl · dte · perf_status · _actions
 *
 * Default sort: perf_status descending (green → amber → red).
 */

import { formatDate } from '../utils/formatDate';

function PerfDot({ status }) {
  const colorMap = {
    green: { bg: '#4ade80', shadow: 'rgba(74,222,128,0.4)' },
    amber: { bg: '#f59e0b', shadow: 'rgba(245,158,11,0.4)' },
    red:   { bg: '#f87171', shadow: 'rgba(248,113,113,0.4)' },
  };
  const c = colorMap[status] ?? colorMap.red;
  return (
    <div style={{
      width: 10, height: 10, borderRadius: '50%',
      backgroundColor: c.bg,
      boxShadow: `0 0 4px ${c.shadow}`,
      display: 'inline-block',
      margin: '0 auto',
    }} />
  );
}

function Pill({ label, color, bg }) {
  return (
    <span style={{
      display: 'inline-block', padding: '2px 7px', borderRadius: 3,
      fontSize: 10, fontWeight: 600, letterSpacing: '0.2px',
      color, backgroundColor: bg,
      border: `1px solid ${color}40`,
    }}>
      {label}
    </span>
  );
}

const TRADE_TYPE_MAP = {
  bear_put:  { label: 'Bear Put',  color: '#f87171', bg: 'rgba(248,113,113,0.10)' },
  bear_call: { label: 'Bear Call', color: '#f87171', bg: 'rgba(248,113,113,0.10)' },
  bull_put:  { label: 'Bull Put',  color: '#4ade80', bg: 'rgba(74,222,128,0.10)' },
  bull_call: { label: 'Bull Call', color: '#4ade80', bg: 'rgba(74,222,128,0.10)' },
};

const STRATEGY_LABELS = {
  'steady-paycheck': 'Steady Paycheck',
  'weekly-grind':    'Weekly Grind',
  'trend-rider':     'Trend Rider',
  'lottery-ticket':  'Lottery Ticket',
  'verticals':       'Vertical Spreads',
  'long-calls':      'Long Calls',
};

// Numeric sort weight for perf_status: green=2, amber=1, red=0
function perfWeight(status) {
  return status === 'green' ? 2 : status === 'amber' ? 1 : 0;
}

export const positionsColumns = [
  {
    key: '_chevron',
    label: '',
    width: 22,
    align: 'left',
    sortable: false,
    render: (pos, ctx) => (
      <span style={{ color: 'var(--text-muted)', fontSize: 9, lineHeight: 1 }}>
        {ctx?.isExpanded ? '▼' : '▶'}
      </span>
    ),
  },
  {
    key: 'symbol',
    label: 'Symbol',
    width: 80,
    align: 'left',
    sortable: true,
    render: (pos) => (
      <span style={{ color: '#2dd4bf', fontWeight: 600 }}>{pos.symbol}</span>
    ),
  },
  {
    key: 'pos_type',
    label: 'Pos Type',
    width: 80,
    align: 'center',
    sortable: true,
    render: (pos) => {
      const isLive = pos.source === 'LIVE';
      return (
        <Pill
          label={isLive ? 'Live' : 'Paper'}
          color={isLive ? '#4ade80' : '#60a5fa'}
          bg={isLive ? 'rgba(74,222,128,0.12)' : 'rgba(96,165,250,0.12)'}
        />
      );
    },
    sortKey: 'source',
  },
  {
    key: 'strategy_key',
    label: 'Strategy',
    width: 120,
    align: 'center',
    sortable: true,
    render: (pos) => (
      <Pill
        label={STRATEGY_LABELS[pos.strategy_key] ?? pos.strategy_key}
        color="#2dd4bf"
        bg="rgba(45,212,191,0.08)"
      />
    ),
  },
  {
    key: 'structure',
    label: 'Structure',
    width: 80,
    align: 'center',
    sortable: true,
    render: (pos) => pos.structure ?? '—',
  },
  {
    key: 'trade_type',
    label: 'Type',
    width: 90,
    align: 'center',
    sortable: true,
    render: (pos) => {
      const t = TRADE_TYPE_MAP[pos.trade_type];
      if (!t) return <span style={{ color: 'var(--text-muted)' }}>{pos.trade_type ?? '—'}</span>;
      return <Pill label={t.label} color={t.color} bg={t.bg} />;
    },
  },
  {
    key: 'analysis_date',
    label: 'Analysis Date',
    width: 130,
    align: 'center',
    sortable: true,
    render: (pos) => pos.analysis_date ? formatDate(pos.analysis_date, true) : '—',
  },
  {
    key: 'strike_spread',
    label: 'Strike/Spread',
    width: 90,
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
    width: 100,
    align: 'right',
    sortable: true,
    render: (pos) => {
      const amt = pos.pnl_amount;
      const pct = pos.pnl_pct;
      if (amt == null) return '—';
      const color = amt >= 0 ? '#4ade80' : '#f87171';
      const sign  = amt >= 0 ? '+' : '';
      return (
        <span style={{ color }}>
          {sign}{Number(amt).toFixed(0)}{' '}
          {pct != null && (
            <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>
              ({sign}{Number(pct).toFixed(1)}%)
            </span>
          )}
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
    key: 'perf_status',
    label: 'Perf',
    width: 50,
    align: 'center',
    sortable: true,
    sortValue: (pos) => perfWeight(pos.perf_status),
    render: (pos) => <PerfDot status={pos.perf_status ?? 'red'} />,
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

export const POSITIONS_DEFAULT_SORT = { key: 'perf_status', dir: 'desc' };
