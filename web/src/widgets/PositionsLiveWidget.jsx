/**
 * PositionsLiveWidget — OTA-310 / OTA-311
 *
 * Shows real-time price data for every symbol with an active position.
 * One row per unique symbol: Symbol | Price | Change | Change %
 *
 * Symbols are fetched from GET /api/v1/positions/symbols (active positions only).
 * Prices refresh every 60 seconds via getQuotes().
 *
 * Props: { config: { id, type, title, settings: {} }, isEditMode }
 */

import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { getPositionSymbols, getQuotes } from '../api/client';

const REFRESH_MS = 60_000;

export default function PositionsLiveWidget({ config }) {
  const navigate                = useNavigate();
  const [rows, setRows]         = useState([]);
  const [loading, setLoading]   = useState(true);

  const load = useCallback(async () => {
    try {
      const symbolsData = await getPositionSymbols();
      // getPositionSymbols returns [{ symbol, position_count }] or { symbols: [] }
      let symbols;
      if (Array.isArray(symbolsData)) {
        symbols = symbolsData.map(item => (typeof item === 'string' ? item : item.symbol));
      } else {
        symbols = symbolsData?.symbols ?? [];
      }

      if (symbols.length === 0) {
        setRows([]);
        return;
      }

      const quotes = await getQuotes(symbols);
      setRows(symbols.map(sym => ({
        symbol:    sym,
        price:     quotes[sym]?.price      ?? null,
        change:    quotes[sym]?.change     ?? null,
        changePct: quotes[sym]?.change_pct ?? null,
      })));
    } catch {
      // silently fail — widget shows stale data
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

  function fmtPrice(val) {
    if (val == null) return '—';
    return val.toFixed(2);
  }

  function fmtChange(val) {
    if (val == null) return '—';
    return `${val >= 0 ? '+' : ''}${val.toFixed(2)}`;
  }

  function fmtChangePct(val) {
    if (val == null) return '—';
    return `${val >= 0 ? '+' : ''}${val.toFixed(2)}%`;
  }

  function tickColor(val) {
    if (val == null) return '#8b90a0';
    if (val > 0) return '#00C896';
    if (val < 0) return '#F85149';
    return '#8b90a0';
  }

  return (
    <div style={s.wrap}>
      <div style={s.header}>
        <span style={s.title}>{config.title}</span>
      </div>

      {loading ? (
        <p style={s.muted}>Loading…</p>
      ) : rows.length === 0 ? (
        <p style={s.muted}>No active positions</p>
      ) : (
        <div style={s.rows}>
          {rows.map(row => (
            <div key={row.symbol} style={s.row}>
              <button
                style={s.symbol}
                onClick={() => navigate(`/security-strategies/${row.symbol}`)}
              >
                {row.symbol}
              </button>
              <div style={s.dataGroup}>
                <span style={s.price}>{fmtPrice(row.price)}</span>
                <span style={{ ...s.tick, color: tickColor(row.change) }}>
                  {fmtChange(row.change)}
                </span>
                <span style={{ ...s.tick, color: tickColor(row.changePct) }}>
                  {fmtChangePct(row.changePct)}
                </span>
              </div>
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
    background: '#0D1117',
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
    padding: '8px 10px',
    background: '#1a1d27',
    border: '1px solid #252a3a',
    borderRadius: 8,
  },
  symbol: {
    fontSize: 13,
    fontWeight: 700,
    color: '#00C896',
    background: 'none',
    border: 'none',
    padding: 0,
    cursor: 'pointer',
    fontFamily: 'inherit',
    letterSpacing: '0.03em',
  },
  dataGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: 14,
  },
  price: {
    fontSize: 13,
    color: '#e4e7ef',
    fontFamily: 'monospace',
    fontWeight: 500,
    minWidth: 52,
    textAlign: 'right',
  },
  tick: {
    fontSize: 12,
    fontFamily: 'monospace',
    fontWeight: 600,
    minWidth: 52,
    textAlign: 'right',
  },
  muted: {
    fontSize: 12,
    color: '#6b7280',
    margin: 0,
  },
};
