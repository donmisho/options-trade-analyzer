/**
 * Analysis Page — connects to the real FastAPI backend
 *
 * Three tabs:
 *   1. Vertical Spreads      — POST /analyze/verticals
 *   2. Long Calls            — POST /analyze/long-calls
 *   3. Directional Compare   — POST /analyze/directional
 *
 * Watchlist panel (right side):
 *   - Populated automatically when any analysis runs (uses underlying_price
 *     already in the response — no extra API call at that moment)
 *   - Refresh button calls GET /market/quote/{symbol} for every watched symbol
 *   - Persists for the life of the browser session
 *
 * Input focus fix:
 *   Sub-components (VerticalsTab, LongCallsTab, DirectionalTab) are defined
 *   OUTSIDE AnalysisPage so React sees stable component identities across
 *   renders. Defining them inside would cause unmount+remount on every
 *   keystroke, stealing input focus.
 */

import { useState, useCallback } from 'react';
import api from '../api/client';

// ─── Design tokens ─────────────────────────────────────────────────────
const C = {
  bg: '#0a0e17', surface: '#111827', surfaceHover: '#1a2234',
  border: '#1e293b', borderLight: '#2a3548',
  text: '#e2e8f0', textMuted: '#8896ab', textDim: '#4a5568',
  accent: '#3b82f6', accentDim: 'rgba(59,130,246,0.15)',
  green: '#22c55e', greenDim: 'rgba(34,197,94,0.12)',
  red: '#ef4444', redDim: 'rgba(239,68,68,0.12)',
  yellow: '#eab308', yellowDim: 'rgba(234,179,8,0.12)',
  purple: '#a855f7',
};
const font = "'JetBrains Mono','Fira Code','SF Mono',monospace";

const badge = (c) => ({
  fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 4,
  display: 'inline-block', letterSpacing: '0.04em',
  background: c === 'green' ? C.greenDim : c === 'red' ? C.redDim : c === 'yellow' ? C.yellowDim : c === 'blue' ? C.accentDim : 'rgba(168,85,247,0.12)',
  color: c === 'green' ? C.green : c === 'red' ? C.red : c === 'yellow' ? C.yellow : c === 'blue' ? C.accent : C.purple,
});

const btn = (v = 'default', sz = 'md') => ({
  padding: sz === 'sm' ? '4px 10px' : '6px 14px', borderRadius: 5,
  border: ['primary', 'success'].includes(v) ? 'none' : `1px solid ${C.borderLight}`,
  background: v === 'primary' ? C.accent : v === 'success' ? C.green : 'transparent',
  color: ['primary', 'success'].includes(v) ? '#fff' : C.textMuted,
  fontSize: sz === 'sm' ? 10 : 11, fontWeight: 600, cursor: 'pointer',
  fontFamily: font, display: 'inline-flex', alignItems: 'center', gap: 5,
});

const inpStyle = {
  background: C.bg, border: `1px solid ${C.borderLight}`, borderRadius: 4,
  padding: '6px 10px', color: C.text, fontSize: 12, fontFamily: font,
  outline: 'none', width: '100%', boxSizing: 'border-box',
};

const thS = {
  textAlign: 'left', padding: '7px 10px', color: C.textMuted, fontWeight: 500,
  fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em',
  borderBottom: `1px solid ${C.border}`, whiteSpace: 'nowrap',
};

const tdS = {
  padding: '8px 10px',
  borderBottom: '1px solid rgba(255,255,255,0.03)',
  whiteSpace: 'nowrap',
};

const tabBtn = (active) => ({
  padding: '8px 16px', fontSize: 11, fontWeight: active ? 600 : 400,
  color: active ? C.accent : C.textMuted,
  borderBottom: active ? `2px solid ${C.accent}` : '2px solid transparent',
  cursor: 'pointer', background: 'none', border: 'none',
  fontFamily: font,
});

const labelStyle = {
  fontSize: 10, color: C.textMuted, textTransform: 'uppercase',
  letterSpacing: '0.05em', display: 'block', marginBottom: 4,
};

// ─── Shared small components ───────────────────────────────────────────

const ScoreBar = ({ value, max = 1, color = C.accent }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
    <div style={{ width: 60, height: 6, background: 'rgba(255,255,255,0.05)', borderRadius: 3, overflow: 'hidden' }}>
      <div style={{ width: `${(value / max) * 100}%`, height: '100%', background: color, borderRadius: 3 }} />
    </div>
    <span style={{ fontWeight: 700, fontSize: 11, color: value > 0.7 ? C.green : value > 0.4 ? C.yellow : C.textMuted }}>
      {value.toFixed(2)}
    </span>
  </div>
);

const Loading = () => (
  <div style={{ padding: 40, textAlign: 'center' }}>
    <div style={{ fontSize: 13, color: C.textMuted, marginBottom: 8 }}>Analyzing...</div>
    <div style={{ fontSize: 11, color: C.textDim }}>Fetching chain data and scoring spreads</div>
  </div>
);

const ErrorMsg = ({ error, onRetry }) => (
  <div style={{ padding: 20, background: C.redDim, border: `1px solid rgba(239,68,68,0.3)`, borderRadius: 6, margin: 16 }}>
    <div style={{ fontSize: 12, fontWeight: 600, color: C.red, marginBottom: 4 }}>Analysis Failed</div>
    <div style={{ fontSize: 11, color: C.textMuted, marginBottom: 8 }}>{error}</div>
    {onRetry && <button onClick={onRetry} style={btn('default', 'sm')}>Retry</button>}
  </div>
);

// ─── Watchlist Panel ───────────────────────────────────────────────────
//
// WHY a Map for watchlist state: gives O(1) deduplication — adding QQQ
// a second time just overwrites the existing entry with fresh data.
// We only convert to an array when we need to render or iterate.

function WatchlistPanel({ watchlist, onRefresh, refreshing }) {
  const items = Array.from(watchlist.values());

  return (
    <div style={{
      width: 180,
      flexShrink: 0,
      background: C.surface,
      border: `1px solid ${C.border}`,
      borderRadius: 8,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      alignSelf: 'flex-start',
      position: 'sticky',
      top: 0,
    }}>
      {/* Header */}
      <div style={{
        padding: '8px 12px',
        borderBottom: `1px solid ${C.border}`,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: C.textMuted }}>
          Watchlist
        </span>
        {items.length > 0 && (
          <button
            onClick={onRefresh}
            disabled={refreshing}
            title="Refresh all prices"
            style={{
              background: 'none', border: 'none', cursor: refreshing ? 'default' : 'pointer',
              color: refreshing ? C.textDim : C.accent, fontSize: 14, padding: 0, lineHeight: 1,
              opacity: refreshing ? 0.5 : 1, fontFamily: font,
            }}
          >
            ↻
          </button>
        )}
      </div>

      {/* Empty state */}
      {items.length === 0 && (
        <div style={{ padding: '20px 12px', textAlign: 'center', color: C.textDim, fontSize: 10, lineHeight: 1.6 }}>
          Symbols appear here after you run an analysis
        </div>
      )}

      {/* Quote cards */}
      {items.map((q) => {
        const isUp = (q.change ?? 0) >= 0;
        const changeColor = q.change == null ? C.textDim : isUp ? C.green : C.red;
        return (
          <div key={q.symbol} style={{
            padding: '10px 12px',
            borderBottom: `1px solid ${C.border}`,
          }}>
            {/* Symbol + price */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 3 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: C.text }}>{q.symbol}</span>
              <span style={{ fontSize: 12, fontWeight: 700, color: C.text }}>
                ${q.price?.toFixed(2) ?? '—'}
              </span>
            </div>

            {/* Change — shows dashes until first refresh */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 4 }}>
              {q.change == null ? (
                <span style={{ fontSize: 10, color: C.textDim }}>— refresh for Δ</span>
              ) : (
                <span style={{ fontSize: 10, color: changeColor, fontWeight: 600 }}>
                  {isUp ? '+' : ''}{q.change.toFixed(2)} ({isUp ? '+' : ''}{q.change_pct?.toFixed(2)}%)
                </span>
              )}
            </div>

            {/* Day range */}
            {q.day_low != null && (
              <div style={{ fontSize: 9, color: C.textDim, display: 'flex', justifyContent: 'space-between' }}>
                <span>L {q.day_low.toFixed(2)}</span>
                <span>H {q.day_high?.toFixed(2)}</span>
              </div>
            )}
          </div>
        );
      })}

      {/* Footer hint */}
      {items.length > 0 && (
        <div style={{ padding: '6px 12px', fontSize: 9, color: C.textDim, textAlign: 'center' }}>
          {refreshing ? 'Refreshing...' : 'Click ↻ to refresh prices'}
        </div>
      )}
    </div>
  );
}

// ─── Tab components (defined OUTSIDE AnalysisPage) ────────────────────

function VerticalsTab({ loading, error, results, onRetry }) {
  return (
    <>
      {loading && <Loading />}
      {error && <ErrorMsg error={error} onRetry={onRetry} />}
      {results && !loading && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'hidden' }}>
          <div style={{ padding: '10px 16px', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 600, fontSize: 12 }}>
              {results.symbol} Vertical Spreads — {results.total_valid} scored
            </span>
            <span style={{ fontSize: 10, color: C.textMuted }}>
              Underlying: ${results.underlying_price?.toFixed(2)}
            </span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr>
                  {['#', 'Type', 'Strikes', 'Exp', 'Debit', 'Max Profit', 'BE', 'Req. Move', 'R:R', 'Prob %', 'EV', 'Score'].map(h => (
                    <th key={h} style={thS}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {results.spreads?.slice(0, 20).map((s, i) => (
                  <tr key={i} style={{ cursor: 'pointer' }}
                    onMouseEnter={e => e.currentTarget.style.background = C.surfaceHover}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                    <td style={{ ...tdS, fontWeight: 700, color: i === 0 ? C.green : C.textMuted }}>
                      {i === 0 ? '★ ' : ''}{i + 1}
                    </td>
                    <td style={tdS}>
                      <span style={badge(s.spread_type === 'bull_call' ? 'green' : 'red')}>
                        {s.spread_type === 'bull_call' ? 'Bull Call' : 'Bear Put'}
                      </span>
                    </td>
                    <td style={{ ...tdS, fontWeight: 600 }}>{s.long_strike}/{s.short_strike}</td>
                    <td style={{ ...tdS, color: C.textMuted }}>{s.expiration}</td>
                    <td style={tdS}>${s.net_debit?.toFixed(2)}</td>
                    <td style={{ ...tdS, color: C.green }}>${s.max_profit?.toFixed(2)}</td>
                    <td style={tdS}>${s.breakeven?.toFixed(2)}</td>
                    <td style={{ ...tdS, color: Math.abs(s.required_move_pct) < 2 ? C.green : C.textMuted }}>
                      {s.required_move_pct > 0 ? '+' : ''}{s.required_move_pct?.toFixed(1)}%
                    </td>
                    <td style={{ ...tdS, fontWeight: 600 }}>{s.reward_risk_ratio?.toFixed(1)}:1</td>
                    <td style={tdS}>{(s.prob_of_profit * 100)?.toFixed(0)}%</td>
                    <td style={{ ...tdS, color: s.ev_raw > 0 ? C.green : C.red }}>${s.ev_raw?.toFixed(2)}</td>
                    <td style={tdS}>
                      <ScoreBar value={s.composite_score} color={s.composite_score > 0.7 ? C.green : s.composite_score > 0.4 ? C.yellow : C.red} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {!results && !loading && !error && (
        <div style={{ padding: 40, textAlign: 'center', color: C.textDim, fontSize: 12 }}>
          Enter a symbol and click "Analyze" to score vertical spreads
        </div>
      )}
    </>
  );
}

function LongCallsTab({ loading, error, results, onRetry }) {
  return (
    <>
      {loading && <Loading />}
      {error && <ErrorMsg error={error} onRetry={onRetry} />}
      {results && !loading && (
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'hidden' }}>
          <div style={{ padding: '10px 16px', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ fontWeight: 600, fontSize: 12 }}>
              {results.symbol} Long Call Candidates — {results.total_valid} scored
            </span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr>
                  {['#', 'Strike', 'Exp', 'DTE', 'Bid/Ask', 'Premium', 'Delta', 'Theta/Day', 'Runway', 'BE Dist.', 'IV %', 'Score'].map(h => (
                    <th key={h} style={thS}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {results.calls?.slice(0, 15).map((c, i) => (
                  <tr key={i} style={{ cursor: 'pointer' }}
                    onMouseEnter={e => e.currentTarget.style.background = C.surfaceHover}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                    <td style={{ ...tdS, fontWeight: 700, color: i === 0 ? C.green : C.textMuted }}>
                      {i === 0 ? '★ ' : ''}{i + 1}
                    </td>
                    <td style={{ ...tdS, fontWeight: 600 }}>${c.strike}</td>
                    <td style={{ ...tdS, color: C.textMuted }}>{c.expiration}</td>
                    <td style={{ ...tdS, color: c.days_to_exp < 14 ? C.yellow : C.textMuted }}>{c.days_to_exp}d</td>
                    <td style={tdS}>${c.bid}/{c.ask}</td>
                    <td style={tdS}>${c.premium_dollars?.toFixed(0)}</td>
                    <td style={{ ...tdS, color: C.green }}>{c.delta?.toFixed(2)}</td>
                    <td style={{ ...tdS, color: C.yellow }}>-${c.theta_per_day_dollars?.toFixed(2)}</td>
                    <td style={tdS}>{c.theta_runway_days?.toFixed(0)}d</td>
                    <td style={{ ...tdS, color: C.accent }}>{c.breakeven_distance_pct > 0 ? '+' : ''}{c.breakeven_distance_pct?.toFixed(1)}%</td>
                    <td style={tdS}>{c.iv?.toFixed(1)}%</td>
                    <td style={tdS}>
                      <ScoreBar value={c.composite_score} color={c.composite_score > 0.7 ? C.green : C.yellow} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {!results && !loading && !error && (
        <div style={{ padding: 40, textAlign: 'center', color: C.textDim, fontSize: 12 }}>
          Enter a symbol and click "Analyze" to score long call candidates
        </div>
      )}
    </>
  );
}

function DirectionalTab({ symbol, setSymbol, thesis, setThesis, loading, error, results, onRun }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 12 }}>
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'hidden' }}>
        <div style={{ padding: '10px 16px', borderBottom: `1px solid ${C.border}` }}>
          <span style={{ fontWeight: 600, fontSize: 12 }}>Your Thesis</span>
        </div>
        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div>
            <label style={labelStyle}>Symbol</label>
            <input value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} style={inpStyle} />
          </div>
          <div>
            <label style={labelStyle}>Direction</label>
            <select value={thesis.direction} onChange={e => setThesis(t => ({ ...t, direction: e.target.value }))}
              style={{ ...inpStyle, appearance: 'auto' }}>
              <option value="bullish">Bullish</option>
              <option value="bearish">Bearish</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>Target Price</label>
            <input type="number" value={thesis.targetPrice}
              onChange={e => setThesis(t => ({ ...t, targetPrice: e.target.value }))}
              placeholder="e.g., 520" style={inpStyle} />
          </div>
          <div>
            <label style={labelStyle}>Timeframe (days)</label>
            <input type="number" value={thesis.timeframeDays}
              onChange={e => setThesis(t => ({ ...t, timeframeDays: e.target.value }))}
              placeholder="e.g., 30" style={inpStyle} />
          </div>
          <div>
            <label style={labelStyle}>Risk Budget ($)</label>
            <input type="number" value={thesis.riskBudget}
              onChange={e => setThesis(t => ({ ...t, riskBudget: e.target.value }))}
              placeholder="e.g., 1000" style={inpStyle} />
          </div>
          <button onClick={onRun} disabled={loading || !thesis.targetPrice}
            style={{
              ...btn('primary'), width: '100%', justifyContent: 'center',
              padding: '10px 0', marginTop: 4, opacity: !thesis.targetPrice ? 0.5 : 1,
            }}>
            {loading ? 'Analyzing...' : 'Compare Strategies'}
          </button>
        </div>
      </div>

      <div>
        {loading && <Loading />}
        {error && <ErrorMsg error={error} onRetry={onRun} />}
        {results && !loading && (
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'hidden' }}>
            <div style={{ padding: '10px 16px', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 600, fontSize: 12 }}>
                Strategy Comparison — {results.thesis?.symbol} {results.thesis?.direction} to ${results.thesis?.target_price}
              </span>
              {results.recommended && (
                <span style={badge('green')}>Recommended: {results.recommended}</span>
              )}
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                <thead>
                  <tr>
                    {['Strategy', 'Cost', 'Max Profit', 'Breakeven', 'Req. Move', 'Prob %', 'Buffer', 'Verdict'].map(h => (
                      <th key={h} style={thS}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {results.strategies?.map((s, i) => (
                    <tr key={i} style={{ background: s.is_recommended ? 'rgba(34,197,94,0.04)' : 'transparent' }}>
                      <td style={{ ...tdS, fontWeight: 600 }}>{s.is_recommended ? '★ ' : ''}{s.strategy_name}</td>
                      <td style={tdS}>${s.cost?.toFixed(0)}</td>
                      <td style={{ ...tdS, color: C.green }}>{s.max_profit_str}</td>
                      <td style={tdS}>${s.breakeven?.toFixed(2)}</td>
                      <td style={tdS}>{s.required_move_pct?.toFixed(1)}%</td>
                      <td style={tdS}>{(s.prob_of_profit * 100)?.toFixed(0)}%</td>
                      <td style={{ ...tdS, color: s.buffer_pct > 0 ? C.accent : C.red }}>
                        {s.buffer_pct > 0 ? '±' : ''}{s.buffer_pct?.toFixed(1)}%
                      </td>
                      <td style={tdS}>
                        <span style={badge(
                          s.verdict === 'Best match' ? 'green' :
                          s.verdict === 'Over budget' || s.verdict === 'Needs bigger move' ? 'red' : 'yellow'
                        )}>
                          {s.verdict}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        {!results && !loading && !error && (
          <div style={{ padding: 40, textAlign: 'center', color: C.textDim, fontSize: 12, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8 }}>
            Fill in your thesis and click "Compare Strategies"
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════

export default function AnalysisPage() {
  const [tab, setTab] = useState('verticals');
  const [symbol, setSymbol] = useState('QQQ');

  // Vertical spreads state
  const [vLoading, setVLoading] = useState(false);
  const [vError, setVError] = useState(null);
  const [vResults, setVResults] = useState(null);

  // Long calls state
  const [lcLoading, setLcLoading] = useState(false);
  const [lcError, setLcError] = useState(null);
  const [lcResults, setLcResults] = useState(null);

  // Directional state
  const [dLoading, setDLoading] = useState(false);
  const [dError, setDError] = useState(null);
  const [dResults, setDResults] = useState(null);
  const [thesis, setThesis] = useState({
    direction: 'bearish',
    targetPrice: '',
    timeframeDays: '',
    riskBudget: '',
  });

  // Watchlist — Map of symbol (string) → quote object
  // WHY Map: O(1) deduplication. Adding QQQ a second time just overwrites
  // the existing entry with the latest price instead of creating a duplicate.
  const [watchlist, setWatchlist] = useState(new Map());
  const [watchRefreshing, setWatchRefreshing] = useState(false);

  // ─── Watchlist helpers ─────────────────────────────────────────────

  // Called after every successful analysis. Uses the underlying_price
  // already in the response — no extra network request needed.
  const upsertWatch = useCallback((sym, underlyingPrice) => {
    setWatchlist(prev => {
      const next = new Map(prev);
      const existing = next.get(sym) || {};
      next.set(sym, {
        ...existing,
        symbol: sym,
        price: underlyingPrice,
        // Preserve change/range from last real quote refresh if available.
        // null means "not yet fetched" — the panel renders a hint to refresh.
        change: existing.change ?? null,
        change_pct: existing.change_pct ?? null,
        day_high: existing.day_high ?? null,
        day_low: existing.day_low ?? null,
      });
      return next;
    });
  }, []);

  // Hits /market/quote for every watched symbol in parallel.
  // WHY Promise.allSettled: if one symbol fails the others still update.
  const refreshWatchlist = useCallback(async () => {
    if (watchlist.size === 0) return;
    setWatchRefreshing(true);
    try {
      const symbols = Array.from(watchlist.keys());
      const settled = await Promise.allSettled(
        symbols.map(s => api.getQuote(s))
      );
      setWatchlist(prev => {
        const next = new Map(prev);
        settled.forEach((result, i) => {
          if (result.status === 'fulfilled') {
            next.set(symbols[i], result.value);
          }
        });
        return next;
      });
    } finally {
      setWatchRefreshing(false);
    }
  }, [watchlist]);

  // ─── API Calls ─────────────────────────────────────────────────────

  const runVerticals = useCallback(async () => {
    setVLoading(true);
    setVError(null);
    try {
      const data = await api.analyzeVerticals({ symbol, maxResults: 20 });
      setVResults(data);
      if (data.underlying_price) upsertWatch(symbol, data.underlying_price);
    } catch (err) {
      setVError(err.message);
    } finally {
      setVLoading(false);
    }
  }, [symbol, upsertWatch]);

  const runLongCalls = useCallback(async () => {
    setLcLoading(true);
    setLcError(null);
    try {
      const data = await api.analyzeLongCalls({ symbol, maxResults: 15 });
      setLcResults(data);
      if (data.underlying_price) upsertWatch(symbol, data.underlying_price);
    } catch (err) {
      setLcError(err.message);
    } finally {
      setLcLoading(false);
    }
  }, [symbol, upsertWatch]);

  const runDirectional = useCallback(async () => {
    if (!thesis.targetPrice) return;
    setDLoading(true);
    setDError(null);
    try {
      const data = await api.analyzeDirectional({
        symbol,
        direction: thesis.direction,
        targetPrice: parseFloat(thesis.targetPrice),
        timeframeDays: parseInt(thesis.timeframeDays) || 30,
        riskBudget: parseInt(thesis.riskBudget) || 500,
      });
      setDResults(data);
      if (data.underlying_price) upsertWatch(symbol, data.underlying_price);
    } catch (err) {
      setDError(err.message);
    } finally {
      setDLoading(false);
    }
  }, [symbol, thesis, upsertWatch]);

  const handleAnalyze = () => {
    if (tab === 'verticals') runVerticals();
    else if (tab === 'longcalls') runLongCalls();
  };

  // ─── Render ────────────────────────────────────────────────────────

  return (
    <div style={{ display: 'flex', gap: 12, fontFamily: font, color: C.text, alignItems: 'flex-start' }}>

      {/* Main content column */}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>

        {/* Tab bar + symbol input */}
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, display: 'flex', alignItems: 'center', padding: '0 8px' }}>
          {[
            { id: 'verticals', label: 'Vertical Spreads' },
            { id: 'longcalls', label: 'Long Calls' },
            { id: 'directional', label: 'Directional Compare' },
          ].map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={tabBtn(tab === t.id)}>
              {t.label}
            </button>
          ))}
          <div style={{ flex: 1 }} />
          {tab !== 'directional' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0' }}>
              <input
                value={symbol}
                onChange={e => setSymbol(e.target.value.toUpperCase())}
                style={{ ...inpStyle, width: 80 }}
              />
              <button onClick={handleAnalyze} style={btn('primary')}>
                {vLoading || lcLoading ? 'Analyzing...' : `Analyze ${symbol}`}
              </button>
            </div>
          )}
        </div>

        {/* Active tab content */}
        {tab === 'verticals' && (
          <VerticalsTab loading={vLoading} error={vError} results={vResults} onRetry={runVerticals} />
        )}
        {tab === 'longcalls' && (
          <LongCallsTab loading={lcLoading} error={lcError} results={lcResults} onRetry={runLongCalls} />
        )}
        {tab === 'directional' && (
          <DirectionalTab
            symbol={symbol} setSymbol={setSymbol}
            thesis={thesis} setThesis={setThesis}
            loading={dLoading} error={dError} results={dResults}
            onRun={runDirectional}
          />
        )}
      </div>

      {/* Watchlist panel — always visible on the right */}
      <WatchlistPanel
        watchlist={watchlist}
        onRefresh={refreshWatchlist}
        refreshing={watchRefreshing}
      />
    </div>
  );
}
