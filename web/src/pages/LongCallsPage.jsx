/**
 * LongCallsPage — Long Call analysis screen.
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
import './PageShared.css';
import './VerticalsPage.css';

export default function LongCallsPage() {
  const { activeSymbol } = useApp();

  const [calls, setCalls] = useState([]);
  const [underlyingPrice, setUnderlyingPrice] = useState(0);
  const [totalValid, setTotalValid] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showFormula, setShowFormula] = useState(false);
  const [showConfig, setShowConfig] = useState(false);

  const runAnalysis = useCallback(async (symbol) => {
    setLoading(true);
    setError(null);
    try {
      const data = await analyzeLongCalls({ symbol, max_results: 15 });
      setCalls(data.calls || []);
      setUnderlyingPrice(data.underlying_price || 0);
      setTotalValid(data.total_valid || 0);
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

  function buildFavTrade(c) {
    return {
      id: `lc-${activeSymbol}-${c.strike}-${c.expiration}`,
      symbol: activeSymbol,
      label: `$${c.strike} Call`,
      expiration: c.expiration,
      source: 'longcall',
      score: c.composite_score,
      originalPrice: `Premium: $${c.premium_dollars.toFixed(2)}`,
      premium: c.premium_dollars,
      delta: c.delta,
      iv: c.iv,
    };
  }

  return (
    <div className="page-card">
      <QuoteBar title="Vertical Spread Analysis" />

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

      {/* ═══ Formula Transparency ═══ */}
      <div className="collapsible-section">
        <button
          className={`collapsible-toggle ${showFormula ? 'open' : ''}`}
          onClick={() => setShowFormula(!showFormula)}
        >
          <span className="toggle-icon">{showFormula ? '▼' : '▶'}</span>
          Formula Transparency
        </button>
        {showFormula && (
          <div className="collapsible-body">
            <div className="formula-grid">
              <div className="formula-card">
                <h4>Core Calculations</h4>
                <code>premium = mid_price × 100</code>
                <code>mid = (bid + ask) ÷ 2</code>
                <code>breakeven = strike + mid_price</code>
                <code>B/E distance = (breakeven − price) ÷ price</code>
              </div>
              <div className="formula-card">
                <h4>Theta Runway</h4>
                <code>theta_per_day = |theta| × 100</code>
                <code>runway = premium ÷ theta_per_day</code>
                <p className="formula-note">
                  "Days until decay eats your premium." Higher runway = more
                  time for your thesis to play out before theta kills the trade.
                </p>
              </div>
              <div className="formula-card">
                <h4>Delta Alignment</h4>
                <code>ideal_delta = 0.45</code>
                <code>distance = |delta − 0.45| ÷ 0.45</code>
                <code>score = max(0, 1 − distance)</code>
                <p className="formula-note">
                  Peaks at 0.45 delta — the sweet spot between directional
                  exposure and cost. Drops symmetrically for deep ITM or far OTM.
                </p>
              </div>
              <div className="formula-card">
                <h4>Composite Score</h4>
                <code>
                  score = delta×0.30 + theta×0.25 + iv×0.20 + rr×0.15 + liq×0.10
                </code>
                <p className="formula-note">
                  IV is scored inversely — lower IV means cheaper options,
                  which is better for buying calls.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ═══ Configuration ═══ */}
      <div className="collapsible-section">
        <button
          className={`collapsible-toggle ${showConfig ? 'open' : ''}`}
          onClick={() => setShowConfig(!showConfig)}
        >
          <span className="toggle-icon">{showConfig ? '▼' : '▶'}</span>
          Configuration
        </button>
        {showConfig && (
          <div className="collapsible-body">
            <div className="config-grid">
              <div className="config-group">
                <h4>Call Selection Filters</h4>
                <div className="config-row"><label>Delta Range</label><span className="config-value mono">0.25 – 0.65</span></div>
                <div className="config-row"><label>Max Premium</label><span className="config-value mono">$1,500</span></div>
                <div className="config-row"><label>Min Open Interest</label><span className="config-value mono">100</span></div>
                <div className="config-row"><label>Min Volume</label><span className="config-value mono">10</span></div>
              </div>
              <div className="config-group">
                <h4>Scoring Weights</h4>
                <div className="weight-bar-display">
                  <div className="weight-segment" style={{ flex: 30, background: 'var(--accent-green)' }}>Δ 30%</div>
                  <div className="weight-segment" style={{ flex: 25, background: 'var(--accent-red)' }}>θ 25%</div>
                  <div className="weight-segment" style={{ flex: 20, background: 'var(--accent-cyan)' }}>IV 20%</div>
                  <div className="weight-segment" style={{ flex: 15, background: 'var(--accent-blue)' }}>R:R 15%</div>
                  <div className="weight-segment" style={{ flex: 10, background: 'var(--accent-purple)' }}>Liq 10%</div>
                </div>
                <p className="formula-note" style={{ marginTop: 8 }}>
                  Weights are read-only in this version.
                </p>
              </div>
              <div className="config-group">
                <h4>Chain Filters</h4>
                <div className="config-row"><label>DTE Range</label><span className="config-value mono">14 – 60 days</span></div>
                <div className="config-row"><label>Strike Range</label><span className="config-value mono">±10%</span></div>
                <div className="config-row"><label>Ideal Delta</label><span className="config-value mono">0.45</span></div>
                <div className="config-row"><label>Max Results</label><span className="config-value mono">15</span></div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
