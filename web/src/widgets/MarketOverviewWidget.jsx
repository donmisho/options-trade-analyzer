/**
 * MarketOverviewWidget — OTA-177
 *
 * Renders the market index card grid. Loads cached values immediately on mount
 * (zero flicker), then fires live quote calls and replaces values once live data
 * returns. Shows "Last Updated mm-dd-yyyy hh:mm" below the cards.
 *
 * Props: { config: { id, type, title, settings: { symbols: [{ticker, apiSymbol, label, noYtd}] } }, isEditMode }
 */

import { useState, useEffect, useCallback } from 'react';
import { getQuote, getHistoricalClose } from '../api/client';
import { formatDate } from '../utils/formatDate';

const CACHE_KEY = 'market_overview_cache';

// First trading day of 2026 — used as YTD baseline
const YTD_REF = '2026-01-02';

function fmtPrice(val) {
  if (val == null) return '—';
  return val.toFixed(2);
}

function fmtChange(val) {
  if (val == null) return '—';
  const abs = Math.abs(val).toFixed(2);
  return val >= 0 ? `+${abs}` : `-${abs}`;
}

function fmtPct(val, decimals = 2) {
  if (val == null) return '—';
  const sign = val >= 0 ? '+' : '';
  return `${sign}${val.toFixed(decimals)}%`;
}

function changeColor(val) {
  if (val == null) return '#8b90a0';
  if (val > 0) return '#4ade80';
  if (val < 0) return '#f87171';
  return '#8b90a0';
}

export default function MarketOverviewWidget({ config }) {
  const symbols = config.settings?.symbols ?? [];

  const [quotes, setQuotes]       = useState({});
  const [ytdRefs, setYtdRefs]     = useState({});
  const [updatedAt, setUpdatedAt] = useState(null);
  const [loading, setLoading]     = useState(true);

  // Load cached values immediately on mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem(CACHE_KEY);
      if (raw) {
        const { quotes: q, ytdRefs: y, timestamp } = JSON.parse(raw);
        if (q) setQuotes(q);
        if (y) setYtdRefs(y);
        if (timestamp) setUpdatedAt(new Date(timestamp));
        setLoading(false);
      }
    } catch (_) { /* ignore corrupt cache */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchLive = useCallback(async () => {
    if (!symbols.length) return;
    try {
      const [quoteResults, ...ytdResults] = await Promise.all([
        Promise.all(
          symbols.map(async (s) => {
            try {
              const q = await getQuote(s.apiSymbol || s.ticker);
              return { ticker: s.ticker, data: q };
            } catch {
              return { ticker: s.ticker, data: null };
            }
          })
        ),
        ...symbols
          .filter(s => !s.noYtd)
          .map(s =>
            getHistoricalClose(s.apiSymbol || s.ticker, YTD_REF)
              .then(d => ({ ticker: s.ticker, close: d?.close ?? null }))
              .catch(() => ({ ticker: s.ticker, close: null }))
          ),
      ]);

      const q = {};
      for (const { ticker, data } of quoteResults) q[ticker] = data;

      const ytd = {};
      for (const { ticker, close } of ytdResults) ytd[ticker] = close;

      const now = new Date();
      setQuotes(q);
      setYtdRefs(ytd);
      setUpdatedAt(now);
      setLoading(false);

      // Update cache
      try {
        localStorage.setItem(CACHE_KEY, JSON.stringify({
          quotes: q,
          ytdRefs: ytd,
          timestamp: now.toISOString(),
        }));
      } catch (_) { /* storage full — ignore */ }
    } catch {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.id]);

  // Fire live fetch on mount (runs alongside cached render)
  useEffect(() => {
    fetchLive();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.id]);

  return (
    <div style={s.wrap}>
      <div style={s.header}>
        <span style={s.title}>{config.title}</span>
        <button style={s.refreshBtn} onClick={fetchLive} title="Refresh">↺</button>
      </div>
      <div style={s.grid}>
        {symbols.map(sym => {
          const q       = quotes[sym.ticker];
          const ytdBase = ytdRefs[sym.ticker];
          const ytdPct  = (!sym.noYtd && q?.price != null && ytdBase)
            ? ((q.price - ytdBase) / ytdBase) * 100
            : null;

          return (
            <div key={sym.ticker} style={s.card}>
              <div style={s.ticker}>{sym.ticker}</div>
              <div style={s.name}>{sym.label}</div>
              <div style={s.price}>
                {q?.price != null ? fmtPrice(q.price) : (loading ? '…' : '—')}
              </div>
              <div style={{ ...s.change, color: changeColor(q?.change) }}>
                {fmtChange(q?.change)}
                <span style={s.changePct}>
                  {q?.change_pct != null ? ` (${fmtPct(q.change_pct)})` : ''}
                </span>
              </div>
              {!sym.noYtd && (
                <div style={{ ...s.ytd, color: changeColor(ytdPct) }}>
                  YTD&nbsp;
                  {ytdPct != null
                    ? fmtPct(ytdPct, 1)
                    : (loading ? '…' : '—')}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {updatedAt && (
        <div style={s.lastUpdated}>
          Last Updated {formatDate(updatedAt, true)}
        </div>
      )}
    </div>
  );
}

const s = {
  wrap: {
    height: '100%',
    overflow: 'auto',
    padding: '12px 14px',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
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
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
    gap: 10,
  },
  card: {
    background: '#1a1d27',
    border: '1px solid #252a3a',
    borderRadius: 10,
    padding: '14px 12px',
  },
  ticker: {
    fontSize: 13,
    fontWeight: 700,
    color: '#38bdf8',
    fontFamily: 'monospace',
    marginBottom: 2,
  },
  name: {
    fontSize: 11,
    color: '#6b7280',
    marginBottom: 10,
  },
  price: {
    fontSize: 20,
    fontWeight: 700,
    color: '#e4e7ef',
    fontFamily: 'monospace',
    marginBottom: 4,
  },
  change: {
    fontSize: 13,
    fontFamily: 'monospace',
  },
  changePct: {
    fontSize: 11,
    opacity: 0.85,
  },
  ytd: {
    fontSize: 12,
    marginTop: 8,
    paddingTop: 8,
    borderTop: '1px solid #252a3a',
    fontFamily: 'monospace',
  },
  lastUpdated: {
    marginTop: 10,
    fontSize: 11,
    color: '#6b7280',
  },
};
