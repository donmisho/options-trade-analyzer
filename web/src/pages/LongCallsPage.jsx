/**
 * LongCallsPage — Long Call analysis screen.
 *
 * ROUND 2: Added ✦ Ask Claude button per trade and SMA chart.
 *
 * API field names from ScoredLongCall dataclass:
 *   premium_dollars, theta_per_day_dollars, theta_runway_days,
 *   iv (not implied_volatility), delta, strike, expiration,
 *   breakeven, composite_score, bid_ask_spread_pct
 */

import { useState, useEffect, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import { analyzeLongCalls } from '../api/client';
import StarButton from '../components/StarButton';
import ScoreBar from '../components/ScoreBar';
import QuoteBar from '../components/QuoteBar';
import SmaPanel from '../components/SmaPanel';
import AskClaudePanel from '../components/AskClaudePanel';
import { C } from '../styles/tokens';
import './PageShared.css';
import './VerticalsPage.css';

function generateCandles(price, count = 120) {
  const candles = [];
  let p = price * 0.95;
  for (let i = 0; i < count; i++) {
    const change = (Math.random() - 0.48) * price * 0.012;
    const open = p;
    const close = p + change;
    const high = Math.max(open, close) + Math.random() * price * 0.005;
    const low = Math.min(open, close) - Math.random() * price * 0.005;
    candles.push({ open, high, low, close, day: `d${i}` });
    p = close;
  }
  const scale = price / candles[candles.length - 1].close;
  return candles.map(c => ({ open: c.open * scale, high: c.high * scale, low: c.low * scale, close: c.close * scale, day: c.day }));
}

export default function LongCallsPage() {
  const { activeSymbol } = useApp();

  const [calls, setCalls] = useState([]);
  const [underlyingPrice, setUnderlyingPrice] = useState(0);
  const [totalValid, setTotalValid] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showFormula, setShowFormula] = useState(false);
  const [showConfig, setShowConfig] = useState(false);

  // SMA chart
  const [smaPeriods, setSmaPeriods] = useState({ short: 8, mid: 21, long: 50 });
  const [candles, setCandles] = useState([]);

  // Ask Claude
  const [claudeOpen, setClaudeOpen] = useState(false);
  const [claudeTrade, setClaudeTrade] = useState(null);

  const runAnalysis = useCallback(async (symbol) => {
    setLoading(true);
    setError(null);
    try {
      const data = await analyzeLongCalls({ symbol, max_results: 15 });
      setCalls(data.calls || []);
      setUnderlyingPrice(data.underlying_price || 0);
      setTotalValid(data.total_valid || 0);
      if (data.underlying_price) setCandles(generateCandles(data.underlying_price));
    } catch (err) {
      setError(err.message || 'Failed to fetch analysis');
      setCalls([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeSymbol) runAnalysis(activeSymbol);
  }, [activeSymbol, runAnalysis]);

  function getSmaData() {
    if (!candles.length) return { price: underlyingPrice, smaShort: 0, smaMid: 0, smaLong: 0 };
    const sma = (period) => candles.slice(-period).reduce((s, c) => s + c.close, 0) / Math.min(period, candles.length);
    return { price: candles[candles.length - 1]?.close || underlyingPrice, smaShort: sma(smaPeriods.short), smaMid: sma(smaPeriods.mid), smaLong: sma(smaPeriods.long) };
  }

  function buildClaudeTrade(c) {
    return {
      symbol: activeSymbol, spread_type: 'long_call',
      long_strike: c.strike, short_strike: null,
      expiration: c.expiration, option_type: 'call',
      net_debit: c.premium_dollars / 100, max_profit: 999,
      max_loss: c.premium_dollars / 100,
      reward_risk_ratio: 0, prob_of_profit: c.delta,
      composite_score: c.composite_score,
    };
  }

  function buildFavTrade(c) {
    return {
      id: `lc-${activeSymbol}-${c.strike}-${c.expiration}`,
      symbol: activeSymbol, label: `$${c.strike} Call`,
      expiration: c.expiration, source: 'longcall',
      score: c.composite_score,
      originalPrice: `Premium: $${c.premium_dollars.toFixed(2)}`,
      premium: c.premium_dollars, delta: c.delta, iv: c.iv,
    };
  }

  return (
    <div className="page-card">
      <QuoteBar title="Long Call Analysis" />

      {candles.length > 0 && !loading && (
        <SmaPanel candles={candles} smaPeriods={smaPeriods} onPeriodsChange={setSmaPeriods} symbol={activeSymbol} />
      )}

      {!loading && !error && calls.length > 0 && (
        <p className="page-subtitle">
          Showing top {calls.length} of {totalValid} candidates, ranked by composite score.
        </p>
      )}

      {loading && (
        <div className="loading-state">
          <div className="spinner" />
          <span>Analyzing {activeSymbol} call options…</span>
        </div>
      )}

      {error && (
        <div className="error-state">
          <span className="error-icon">⚠</span>
          <span>{error}</span>
          <button className="retry-btn" onClick={() => runAnalysis(activeSymbol)}>Retry</button>
        </div>
      )}

      {!loading && !error && calls.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: 32 }}></th>
                <th>Strike</th>
                <th>Exp</th>
                <th>Premium</th>
                <th>Delta</th>
                <th>Theta $/day</th>
                <th>Runway</th>
                <th>IV</th>
                <th>Breakeven</th>
                <th>Score</th>
                <th style={{ width: 60 }}></th>
              </tr>
            </thead>
            <tbody>
              {calls.map((c, i) => (
                <tr key={i}>
                  <td><StarButton trade={buildFavTrade(c)} /></td>
                  <td className="mono text-cyan">${c.strike}</td>
                  <td className="mono text-muted">{c.expiration}</td>
                  <td className="mono">${c.premium_dollars.toFixed(0)}</td>
                  <td className="mono text-green">{c.delta.toFixed(2)}</td>
                  <td className="mono text-red">−${c.theta_per_day_dollars.toFixed(2)}</td>
                  <td className="mono">{c.theta_runway_days.toFixed(0)}d</td>
                  <td className="mono">{c.iv.toFixed(1)}%</td>
                  <td className="mono">${c.breakeven.toFixed(2)}</td>
                  <td><ScoreBar score={c.composite_score} /></td>
                  <td>
                    <button
                      onClick={(e) => { e.stopPropagation(); setClaudeTrade(buildClaudeTrade(c)); setClaudeOpen(true); }}
                      style={{
                        padding: '3px 8px', borderRadius: 4,
                        border: `1px solid ${C.claudeBorder}`,
                        backgroundColor: C.claudeDim, color: C.claudeAccent,
                        fontSize: 9, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap',
                      }}
                    >
                      ✦ Ask
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && !error && calls.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">📊</div>
          <h3>No call candidates found</h3>
          <p>No calls matched the current filters for {activeSymbol}.</p>
        </div>
      )}

      {/* Formula Transparency — same as before */}
      <div className="collapsible-section">
        <button className={`collapsible-toggle ${showFormula ? 'open' : ''}`} onClick={() => setShowFormula(!showFormula)}>
          <span className="toggle-icon">{showFormula ? '▼' : '▶'}</span> Formula Transparency
        </button>
        {showFormula && (
          <div className="collapsible-body">
            <div className="formula-grid">
              <div className="formula-card"><h4>Core Calculations</h4><code>premium = mid_price × 100</code><code>breakeven = strike + mid_price</code></div>
              <div className="formula-card"><h4>Theta Runway</h4><code>runway = premium ÷ theta_per_day</code><p className="formula-note">Higher runway = more time for your thesis.</p></div>
              <div className="formula-card"><h4>Delta Alignment</h4><code>ideal_delta = 0.45</code><code>score = max(0, 1 − |delta − 0.45| ÷ 0.45)</code></div>
              <div className="formula-card"><h4>Composite Score</h4><code>score = δ×30% + θ×25% + IV×20% + R:R×15% + Liq×10%</code></div>
            </div>
          </div>
        )}
      </div>

      {/* Ask Claude Panel */}
      <AskClaudePanel open={claudeOpen} onClose={() => setClaudeOpen(false)} trade={claudeTrade} smaData={getSmaData()} smaPeriods={smaPeriods} />
    </div>
  );
}
