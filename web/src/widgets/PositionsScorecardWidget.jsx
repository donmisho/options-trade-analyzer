/**
 * PositionsScorecardWidget — OTA-179
 *
 * Dashboard scorecard of all open positions.
 * Columns: Symbol | Strategy | Entry Date | P&L | DTE Remaining | Status
 *
 * Status is derived from health_grade on the position:
 *   A or B → Active (green)
 *   C       → Watch  (amber)
 *   D or F  → Critical (red)
 *   null    → Active (green, default)
 *
 * Refreshes every 60 seconds. Row click navigates to /positions and sets activeSymbol.
 *
 * Props: { config: { id, type, title, settings: {} }, isEditMode }
 */

import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { getPositions } from '../api/client';
import { formatDate } from '../utils/formatDate';

const REFRESH_MS = 60_000;

function deriveStatus(healthGrade) {
  if (!healthGrade) return 'Active';
  const g = healthGrade.toUpperCase();
  if (g === 'A' || g === 'B') return 'Active';
  if (g === 'C') return 'Watch';
  return 'Critical';
}

function statusColor(status) {
  if (status === 'Active')   return 'var(--green, #4ade80)';
  if (status === 'Watch')    return 'var(--amber, #fbbf24)';
  if (status === 'Critical') return 'var(--red,   #f87171)';
  return '#6b7280';
}

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

function computeDte(tradeStructure) {
  if (!tradeStructure) return null;
  let expiry = tradeStructure.expiration;
  if (!expiry && Array.isArray(tradeStructure.legs) && tradeStructure.legs.length) {
    expiry = tradeStructure.legs[0].expiration || tradeStructure.legs[0].expiry;
  }
  if (!expiry) return null;
  const diff = new Date(expiry) - new Date();
  return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
}

function fmtStrategy(strategyKey) {
  if (!strategyKey) return '—';
  return strategyKey
    .split('-')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

export default function PositionsScorecardWidget({ config }) {
  const navigate = useNavigate();
  const { setActiveSymbol } = useApp();

  const [positions, setPositions] = useState([]);
  const [loading, setLoading]     = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await getPositions({ status: 'FOLLOWING,LIVE' });
      const list = Array.isArray(res) ? res : (res?.positions ?? []);
      setPositions(list);
    } catch {
      // silently fail — keep stale data visible
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, REFRESH_MS);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.id]);

  function handleRowClick(symbol) {
    setActiveSymbol(symbol);
    navigate('/positions');
  }

  return (
    <div style={s.wrap}>
      <div style={s.header}>
        <span style={s.title}>{config.title}</span>
        <button style={s.refreshBtn} onClick={load} title="Refresh">↺</button>
      </div>

      {loading ? (
        <p style={s.muted}>Loading…</p>
      ) : positions.length === 0 ? (
        <p style={s.muted}>No open positions</p>
      ) : (
        <div style={s.tableWrap}>
          <table style={s.table}>
            <thead>
              <tr>
                <th style={s.th}>Symbol</th>
                <th style={s.th}>Strategy</th>
                <th style={s.th}>Entry Date</th>
                <th style={{ ...s.th, textAlign: 'right' }}>P&amp;L</th>
                <th style={{ ...s.th, textAlign: 'right' }}>DTE</th>
                <th style={{ ...s.th, textAlign: 'center' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {positions.map(pos => {
                const status = deriveStatus(pos.health_grade);
                const dte    = computeDte(pos.trade_structure);
                return (
                  <tr
                    key={pos.position_id}
                    style={s.row}
                    onClick={() => handleRowClick(pos.symbol)}
                  >
                    <td style={s.tdSymbol}>{pos.symbol}</td>
                    <td style={s.td}>
                      {pos.strategy_label || fmtStrategy(pos.strategy_key)}
                    </td>
                    <td style={s.td}>{formatDate(pos.entry_date)}</td>
                    <td style={{ ...s.td, textAlign: 'right', color: pnlColor(pos.current_pnl) }}>
                      {fmtPnl(pos.current_pnl)}
                    </td>
                    <td style={{ ...s.td, textAlign: 'right' }}>
                      {dte != null ? dte : '—'}
                    </td>
                    <td style={{ ...s.td, textAlign: 'center' }}>
                      <span style={{ ...s.pill, background: `${statusColor(status)}22`, color: statusColor(status) }}>
                        {status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
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
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
    flexShrink: 0,
  },
  title: {
    fontSize: 11,
    fontWeight: 700,
    color: '#6b7280',
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
  },
  refreshBtn: {
    background: 'none',
    border: 'none',
    color: '#6b7280',
    fontSize: 16,
    cursor: 'pointer',
    padding: '0 4px',
    lineHeight: 1,
  },
  muted: {
    fontSize: 12,
    color: '#6b7280',
    margin: 0,
  },
  tableWrap: {
    flex: 1,
    overflowY: 'auto',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: 12,
  },
  th: {
    padding: '4px 8px',
    textAlign: 'left',
    fontSize: 10,
    fontWeight: 700,
    color: '#6b7280',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    borderBottom: '1px solid #252a3a',
    whiteSpace: 'nowrap',
  },
  row: {
    cursor: 'pointer',
    borderBottom: '1px solid #1a1d27',
  },
  td: {
    padding: '7px 8px',
    color: '#c4c8d8',
    whiteSpace: 'nowrap',
  },
  tdSymbol: {
    padding: '7px 8px',
    color: '#38bdf8',
    fontWeight: 700,
    fontFamily: 'monospace',
    whiteSpace: 'nowrap',
  },
  pill: {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 99,
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: '0.04em',
  },
};
