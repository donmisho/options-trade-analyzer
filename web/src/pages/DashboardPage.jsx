/**
 * DashboardPage — Home screen shown after login.
 *
 * Sections:
 *  1. Welcome — time-based greeting + user's first name from MSAL
 *  2. Market Overview — SPY, QQQ, DIA, IWM, VIX with day change and YTD %
 *  3. Recent Favorites — last 5 saved trades with link to full favorites page
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useMsal } from '@azure/msal-react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { getQuote, getHistoricalClose, getInsights, dismissInsight, actOnInsight } from '../api/client';
import { InsightCard } from '../components/InsightCard';
import { formatDate } from '../utils/formatDate';

// ─── Index definitions ────────────────────────────────────────────

// symbol     = display label shown in the UI (no $ per house style)
// apiSymbol  = actual symbol sent to Tradier (may differ — e.g. indices need $ prefix)
const INDICES = [
  { symbol: '.DJI', apiSymbol: '$DJI', name: 'Dow Jones'         },
  { symbol: '.INX', apiSymbol: '$SPX', name: 'S&P 500'           },
  { symbol: 'NDX',  apiSymbol: '$NDX', name: 'Nasdaq 100'        },
  { symbol: 'RUT',  apiSymbol: '$RUT', name: 'Russell 2000'      },
  { symbol: 'SPY',                     name: 'S&P 500 ETF'       },
  { symbol: 'QQQ',                     name: 'Nasdaq 100 ETF'    },
  { symbol: 'DIA',                     name: 'Dow Jones ETF'     },
  { symbol: 'IWM',                     name: 'Russell 2000 ETF'  },
  { symbol: 'VIX',  apiSymbol: '$VIX', name: 'VIX', noYtd: true },
];

// First trading day of 2026 — used as YTD baseline
const YTD_REF = '2026-01-02';

// ─── Helpers ──────────────────────────────────────────────────────

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

function getFirstName(fullName) {
  return fullName ? fullName.split(' ')[0] : 'Trader';
}

function formatToday() {
  return formatDate(new Date());
}

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

function strategyLabel(source) {
  const map = { vertical: 'Vertical', longcall: 'Long Call', directional: 'Directional' };
  return map[source] || source || '—';
}

function fmtSavedDate(savedDate, savedAt) {
  const raw = savedDate || savedAt;
  if (!raw) return '—';
  return formatDate(raw);
}

// ─── Component ────────────────────────────────────────────────────

export default function DashboardPage() {
  const { accounts } = useMsal();
  const { favorites, setActiveSymbol } = useApp();
  const navigate = useNavigate();

  const name = getFirstName(accounts[0]?.name);

  const [indexQuotes, setIndexQuotes] = useState({});
  const [ytdRefs, setYtdRefs]         = useState({});
  const [loading, setLoading]         = useState(true);
  const [insights, setInsights]       = useState([]);
  const pollTimerRef                  = useRef(null);

  const loadInsights = useCallback(async () => {
    try {
      const data = await getInsights('options', 'ACTIVE');
      setInsights(data || []);
    } catch {
      // silently fail — dashboard should not break if insights are unavailable
    }
  }, []);

  // Poll insights every 60s while page is active
  useEffect(() => {
    loadInsights();
    pollTimerRef.current = setInterval(loadInsights, 60_000);
    return () => clearInterval(pollTimerRef.current);
  }, [loadInsights]);

  const handleDismiss = useCallback(async (insightId) => {
    // Optimistic update
    setInsights(prev => prev.filter(i => i.insight_id !== insightId));
    try {
      await dismissInsight(insightId);
    } catch {
      // Re-fetch to restore if API call fails
      loadInsights();
    }
  }, [loadInsights]);

  const handleViewEntity = useCallback(async (route, insightId) => {
    try {
      await actOnInsight(insightId);
    } catch { /* best-effort */ }
    navigate(route);
  }, [navigate]);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        // Fetch current quotes — use apiSymbol for the API call (e.g. $DJIA),
        // but key results by the display symbol (DJIA) for rendering.
        const [quoteResults, ...ytdResults] = await Promise.all([
          Promise.all(
            INDICES.map(async (idx) => {
              try {
                const q = await getQuote(idx.apiSymbol || idx.symbol);
                return { sym: idx.symbol, data: q };
              } catch {
                return { sym: idx.symbol, data: null };
              }
            })
          ),
          ...INDICES
            .filter(i => !i.noYtd)
            .map(i =>
              getHistoricalClose(i.apiSymbol || i.symbol, YTD_REF)
                .then(d => ({ sym: i.symbol, close: d?.close ?? null }))
                .catch(() => ({ sym: i.symbol, close: null }))
            ),
        ]);

        const quotes = {};
        for (const { sym, data } of quoteResults) quotes[sym] = data;
        setIndexQuotes(quotes);

        const ytd = {};
        for (const { sym, close } of ytdResults) ytd[sym] = close;
        setYtdRefs(ytd);
      } catch {
        // silently fail — stale or missing data is fine
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const recentFavorites = [...favorites]
    .sort((a, b) => (b.savedAt || 0) - (a.savedAt || 0))
    .slice(0, 5);

  return (
    <div style={s.page}>

      {/* ── Welcome ── */}
      <div style={s.welcome}>
        <h1 style={s.greeting}>{getGreeting()}, {name}.</h1>
        <p style={s.date}>{formatToday()}</p>
      </div>

      {/* ── Market Overview ── */}
      <section style={s.section}>
        <h2 style={s.sectionTitle}>Market Overview</h2>
        <div style={s.indexGrid}>
          {INDICES.map(idx => {
            const q       = indexQuotes[idx.symbol];
            const ytdBase = ytdRefs[idx.symbol];
            const ytdPct  = (!idx.noYtd && q?.price != null && ytdBase)
              ? ((q.price - ytdBase) / ytdBase) * 100
              : null;

            return (
              <div key={idx.symbol} style={s.indexCard}>
                <div style={s.indexTicker}>{idx.symbol}</div>
                <div style={s.indexName}>{idx.name}</div>
                <div style={s.indexPrice}>
                  {q?.price != null ? fmtPrice(q.price) : (loading ? '…' : '—')}
                </div>
                <div style={{ ...s.indexChange, color: changeColor(q?.change) }}>
                  {fmtChange(q?.change)}
                  <span style={s.indexChangePct}>
                    {q?.change_pct != null ? ` (${fmtPct(q.change_pct)})` : ''}
                  </span>
                </div>
                {!idx.noYtd && (
                  <div style={{ ...s.indexYtd, color: changeColor(ytdPct) }}>
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
      </section>

      {/* ── Insights Feed ── */}
      {insights.length > 0 && (
        <section style={s.section}>
          <div style={s.sectionHeader}>
            <h2 style={s.sectionTitle}>
              Insights
              <span style={{ marginLeft: 8, color: '#ef4444', fontVariantNumeric: 'tabular-nums' }}>
                ({insights.length} active)
              </span>
            </h2>
            <button style={s.seeAll} onClick={loadInsights}>
              ↻ Refresh
            </button>
          </div>
          {insights.slice(0, 3).map(insight => (
            <InsightCard
              key={insight.insight_id}
              insight={insight}
              onDismiss={handleDismiss}
              onViewEntity={handleViewEntity}
            />
          ))}
          {insights.length > 3 && (
            <p style={{ fontSize: 12, color: '#6b7280', marginTop: 8 }}>
              +{insights.length - 3} more — view from Positions page
            </p>
          )}
        </section>
      )}

      {/* ── Recent Favorites ── */}
      <section style={s.section}>
        <div style={s.sectionHeader}>
          <h2 style={s.sectionTitle}>Your Most Recent Favorites</h2>
          {favorites.length > 0 && (
            <button style={s.seeAll} onClick={() => navigate('/favorites')}>
              View all {favorites.length} →
            </button>
          )}
        </div>

        {recentFavorites.length === 0 ? (
          <p style={s.empty}>
            No favorites saved yet. Star a trade from any analysis screen to save it here.
          </p>
        ) : (
          <div style={s.tableWrap}>
            <table style={s.table}>
              <thead>
                <tr>
                  {['Symbol', 'Trade', 'Strategy', 'Score', 'Saved'].map(h => (
                    <th key={h} style={s.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recentFavorites.map((fav, i) => (
                  <tr
                    key={fav.id}
                    style={{
                      ...s.tr,
                      borderBottom: i < recentFavorites.length - 1
                        ? '1px solid #252a3a'
                        : 'none',
                    }}
                    onClick={() => {
                      setActiveSymbol(fav.symbol);
                      navigate('/favorites');
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = '#1f2232'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <td style={{ ...s.td, color: '#38bdf8', fontFamily: 'monospace', fontWeight: 600 }}>
                      {fav.symbol}
                    </td>
                    <td style={{ ...s.td, fontFamily: 'monospace' }}>
                      {fav.label || '—'}
                      {fav.expiration && (
                        <span style={{ color: '#6b7280', marginLeft: 6, fontSize: 11 }}>
                          {fav.expiration}
                        </span>
                      )}
                    </td>
                    <td style={s.td}>{strategyLabel(fav.source)}</td>
                    <td style={{
                      ...s.td,
                      fontFamily: 'monospace',
                      color: fav.score >= 70 ? '#4ade80' : fav.score >= 50 ? '#facc15' : '#f87171',
                    }}>
                      {fav.score ? Math.round(fav.score) : '—'}
                    </td>
                    <td style={{ ...s.td, color: '#6b7280' }}>
                      {fmtSavedDate(fav.savedDate, fav.savedAt)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

    </div>
  );
}

// ─── Styles ───────────────────────────────────────────────────────

const s = {
  page: {
    padding: '36px 40px',
    maxWidth: 1100,
    margin: '0 auto',
    color: '#e4e7ef',
  },
  welcome: {
    marginBottom: 40,
    paddingBottom: 28,
    borderBottom: '1px solid #252a3a',
  },
  greeting: {
    margin: 0,
    fontSize: 28,
    fontWeight: 700,
    color: '#e8eaf0',
    letterSpacing: '-0.3px',
  },
  date: {
    margin: '6px 0 0',
    fontSize: 13,
    color: '#6b7280',
  },
  section: {
    marginBottom: 48,
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    marginBottom: 16,
  },
  sectionTitle: {
    margin: 0,
    fontSize: 11,
    fontWeight: 700,
    color: '#6b7280',
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
  },
  seeAll: {
    background: 'none',
    border: 'none',
    color: '#38bdf8',
    fontSize: 12,
    cursor: 'pointer',
    padding: 0,
  },
  indexGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))',
    gap: 14,
  },
  indexCard: {
    background: '#1a1d27',
    border: '1px solid #252a3a',
    borderRadius: 10,
    padding: '18px 16px',
  },
  indexTicker: {
    fontSize: 13,
    fontWeight: 700,
    color: '#38bdf8',
    fontFamily: 'monospace',
    marginBottom: 2,
  },
  indexName: {
    fontSize: 11,
    color: '#6b7280',
    marginBottom: 14,
  },
  indexPrice: {
    fontSize: 22,
    fontWeight: 700,
    color: '#e4e7ef',
    fontFamily: 'monospace',
    marginBottom: 4,
  },
  indexChange: {
    fontSize: 13,
    fontFamily: 'monospace',
  },
  indexChangePct: {
    fontSize: 11,
    opacity: 0.85,
  },
  indexYtd: {
    fontSize: 12,
    marginTop: 10,
    paddingTop: 10,
    borderTop: '1px solid #252a3a',
    fontFamily: 'monospace',
  },
  tableWrap: {
    background: '#1a1d27',
    border: '1px solid #252a3a',
    borderRadius: 10,
    overflow: 'hidden',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
  },
  th: {
    padding: '10px 16px',
    textAlign: 'left',
    fontSize: 11,
    color: '#6b7280',
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.07em',
    background: '#14161f',
    borderBottom: '1px solid #252a3a',
  },
  tr: {
    cursor: 'pointer',
    transition: 'background 0.1s',
  },
  td: {
    padding: '13px 16px',
    fontSize: 13,
    color: '#e4e7ef',
    verticalAlign: 'middle',
  },
  empty: {
    color: '#6b7280',
    fontSize: 14,
    margin: 0,
    padding: '20px 0',
  },
};
