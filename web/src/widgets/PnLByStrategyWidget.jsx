/**
 * PnLByStrategyWidget — Phase 2.3
 *
 * Groups closed and open positions by strategy. Shows:
 *   - Strategy display name
 *   - Total realized P&L (closed positions) — green if positive, red if negative
 *   - Win rate: closed wins / total closed (e.g. "3/4")
 *   - "No trades yet" if no positions for that strategy
 *
 * Props: { config: { id, type, title, settings: {} }, isEditMode }
 */

import { useState, useEffect } from 'react';
import { getPositions } from '../api/client';

const STRATEGY_LABELS = {
  steady_paycheck: 'Steady Paycheck',
  weekly_grind:    'Weekly Grind',
  trend_rider:     'Trend Rider',
  lottery_ticket:  'Lottery Ticket',
};

function fmtPnl(val) {
  if (val == null) return '—';
  const abs = Math.abs(val).toFixed(2);
  return val >= 0 ? `+${abs}` : `-${abs}`;
}

function pnlColor(val) {
  if (val == null) return '#8b90a0';
  if (val > 0) return '#4ade80';
  if (val < 0) return '#f87171';
  return '#8b90a0';
}

export default function PnLByStrategyWidget({ config, isEditMode }) {
  const [stats, setStats]   = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await getPositions({});
        const positions = data?.positions ?? [];

        const byStrategy = {};
        for (const key of Object.keys(STRATEGY_LABELS)) {
          byStrategy[key] = { closed: [], wins: 0, totalPnl: 0 };
        }

        for (const pos of positions) {
          const key = pos.strategy_key;
          if (!byStrategy[key]) {
            byStrategy[key] = { closed: [], wins: 0, totalPnl: 0 };
          }
          if (pos.status === 'CLOSED' || pos.outcome_pnl != null) {
            const pnl = parseFloat(pos.outcome_pnl) || 0;
            byStrategy[key].closed.push(pnl);
            byStrategy[key].totalPnl += pnl;
            if (pnl > 0) byStrategy[key].wins++;
          }
        }

        const result = Object.entries(STRATEGY_LABELS).map(([key, label]) => ({
          key,
          label,
          totalPnl: byStrategy[key]?.totalPnl ?? null,
          wins:     byStrategy[key]?.wins ?? 0,
          total:    byStrategy[key]?.closed.length ?? 0,
        }));

        setStats(result);
      } catch {
        // silently fail
      } finally {
        setLoading(false);
      }
    }
    load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.id]);

  return (
    <div style={s.wrap}>
      <div style={s.header}>
        <span style={s.title}>{config.title}</span>
      </div>

      {loading ? (
        <p style={s.muted}>Loading…</p>
      ) : (
        <div style={s.rows}>
          {stats.map(row => (
            <div key={row.key} style={s.row}>
              <span style={s.stratLabel}>{row.label}</span>
              {row.total === 0 ? (
                <span style={s.muted}>No trades yet</span>
              ) : (
                <div style={s.rightGroup}>
                  <span style={{ ...s.pnl, color: pnlColor(row.totalPnl) }}>
                    {fmtPnl(row.totalPnl)}
                  </span>
                  <span style={s.winRate}>
                    {row.wins}/{row.total}
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const s = {
  wrap: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    padding: '12px 14px',
    overflow: 'hidden',
  },
  header: {
    marginBottom: 12,
    flexShrink: 0,
  },
  title: {
    fontSize: 11,
    fontWeight: 700,
    color: '#6b7280',
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
  },
  rows: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
    overflowY: 'auto',
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 12px',
    background: '#1a1d27',
    border: '1px solid #252a3a',
    borderRadius: 8,
  },
  stratLabel: {
    fontSize: 13,
    color: '#e4e7ef',
    fontWeight: 500,
  },
  rightGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: 16,
  },
  pnl: {
    fontSize: 13,
    fontFamily: 'monospace',
    fontWeight: 600,
  },
  winRate: {
    fontSize: 12,
    color: '#6b7280',
    fontFamily: 'monospace',
  },
  muted: {
    fontSize: 12,
    color: '#6b7280',
    margin: 0,
  },
};
