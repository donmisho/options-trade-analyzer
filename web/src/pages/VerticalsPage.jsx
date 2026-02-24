/**
 * VerticalsPage — Vertical Spread analysis screen.
 *
 * HOW IT WORKS:
 * 1. When the page loads (or the active symbol changes), it
 *    automatically calls POST /api/v1/analyze/verticals
 * 2. The API fetches the options chain from Tradier, builds
 *    every valid bull call and bear put spread, scores them,
 *    and returns the top results ranked by composite score
 * 3. We render those results in a table with star buttons
 *
 * WHY auto-run instead of a manual "Analyze" button?
 * The watchlist click already signals intent ("I want to look at SPY").
 * Requiring a second click to run analysis adds friction. Auto-run
 * means you click SPY → results appear. You can still adjust filters
 * and re-run manually via the "Run Analysis" button.
 */

import { useState, useEffect, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import { analyzeVerticals } from '../api/client';
import StarButton from '../components/StarButton';
import ScoreBar from '../components/ScoreBar';
import './PageShared.css';
import './VerticalsPage.css';

export default function VerticalsPage() {
  const { activeSymbol } = useApp();

  // API results
  const [spreads, setSpreads] = useState([]);
  const [underlyingPrice, setUnderlyingPrice] = useState(0);
  const [totalValid, setTotalValid] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Collapsible panels
  const [showFormula, setShowFormula] = useState(false);
  const [showConfig, setShowConfig] = useState(false);

  // ─── Fetch analysis ──────────────────────────────────────

  const runAnalysis = useCallback(async (symbol) => {
    setLoading(true);
    setError(null);
    try {
      const data = await analyzeVerticals({
        symbol,
        spread_types: ['bull_call', 'bear_put'],
        max_results: 20,
      });
      setSpreads(data.spreads || []);
      setUnderlyingPrice(data.underlying_price || 0);
      setTotalValid(data.total_valid || 0);
    } catch (err) {
      setError(err.message || 'Failed to fetch analysis');
      setSpreads([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-run when symbol changes
  useEffect(() => {
    if (activeSymbol) {
      runAnalysis(activeSymbol);
    }
  }, [activeSymbol, runAnalysis]);

  // ─── Build favorite trade object ─────────────────────────

  function buildFavTrade(spread) {
    const typeLabel = spread.spread_type === 'bull_call' ? 'Bull Call' : 'Bear Put';
    const strikes = `${spread.long_strike}/${spread.short_strike}`;
    return {
      id: `vs-${activeSymbol}-${spread.spread_type}-${strikes}-${spread.expiration}`,
      symbol: activeSymbol,
      label: `${typeLabel} ${strikes}`,
      expiration: spread.expiration,
      source: 'vertical',
      score: spread.composite_score,
      originalPrice: `Debit: $${spread.net_debit.toFixed(2)}`,
      originalDebit: spread.net_debit,
      maxProfit: spread.max_profit,
      rewardRisk: spread.reward_risk_ratio,
      probOfProfit: spread.prob_of_profit,
    };
  }

  // ─── Render ──────────────────────────────────────────────

  return (
    <div className="page-card">
      <h2 className="page-title">
        Vertical Spread Analysis —{' '}
        <span className="symbol-highlight">{activeSymbol}</span>
        {underlyingPrice > 0 && (
          <span className="underlying-price">${underlyingPrice.toFixed(2)}</span>
        )}
      </h2>

      {/* Status bar */}
      {!loading && !error && spreads.length > 0 && (
        <p className="page-subtitle">
          Showing top {spreads.length} of {totalValid} valid spreads, ranked by composite score.
        </p>
      )}

      {/* Loading */}
      {loading && (
        <div className="loading-state">
          <div className="spinner" />
          <span>Analyzing {activeSymbol} options chain…</span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="error-state">
          <span className="error-icon">⚠</span>
          <span>{error}</span>
          <button className="retry-btn" onClick={() => runAnalysis(activeSymbol)}>
            Retry
          </button>
        </div>
      )}

      {/* Results table */}
      {!loading && !error && spreads.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: 32 }}></th>
                <th>Type</th>
                <th>Long / Short</th>
                <th>Exp</th>
                <th>Debit</th>
                <th>Max Profit</th>
                <th>R:R</th>
                <th>Breakeven</th>
                <th>Prob %</th>
                <th>EV</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {spreads.map((s, i) => {
                const isBull = s.spread_type === 'bull_call';
                return (
                  <tr key={i}>
                    <td>
                      <StarButton trade={buildFavTrade(s)} />
                    </td>
                    <td>
                      <span className={`type-badge ${isBull ? 'type-bull' : 'type-bear'}`}>
                        {isBull ? 'Bull Call' : 'Bear Put'}
                      </span>
                    </td>
                    <td className="mono">
                      {s.long_strike} / {s.short_strike}
                    </td>
                    <td className="mono text-muted">{s.expiration}</td>
                    <td className="mono">${s.net_debit.toFixed(2)}</td>
                    <td className="mono text-green">${s.max_profit.toFixed(2)}</td>
                    <td className="mono">{s.reward_risk_ratio.toFixed(2)}</td>
                    <td className="mono">${s.breakeven.toFixed(2)}</td>
                    <td className="mono">{(s.prob_of_profit * 100).toFixed(0)}%</td>
                    <td className={`mono ${s.ev_raw >= 0 ? 'text-green' : 'text-red'}`}>
                      ${s.ev_raw.toFixed(2)}
                    </td>
                    <td>
                      <ScoreBar score={s.composite_score} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && spreads.length === 0 && !loading && (
        <div className="empty-state">
          <div className="empty-icon">📊</div>
          <h3>No spreads found</h3>
          <p>
            No valid vertical spreads matched the current filters for {activeSymbol}.
            Try a different symbol or adjust the filter settings.
          </p>
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
                <h4>Spread Construction</h4>
                <code>net_debit = long_mid − short_mid</code>
                <code>max_profit = width − debit</code>
                <code>max_loss = debit</code>
                <code>R:R = max_profit ÷ max_loss</code>
                <code>breakeven (bull) = long_strike + debit</code>
                <code>breakeven (bear) = long_strike − debit</code>
              </div>
              <div className="formula-card">
                <h4>Probability &amp; EV</h4>
                <code>prob ≈ 1 − |short_delta|</code>
                <code>EV = (prob × max_profit) − ((1−prob) × max_loss)</code>
                <p className="formula-note">
                  Delta-based probability is an approximation. It works well
                  for OTM spreads but is less accurate near ATM.
                </p>
              </div>
              <div className="formula-card">
                <h4>Composite Score</h4>
                <code>
                  score = ev×0.35 + rr×0.25 + prob×0.20 + liq×0.15 + theta×0.05
                </code>
                <p className="formula-note">
                  Each raw metric is min-max normalized to 0–1 before weighting.
                  This lets you compare a $500 EV to a 3.0 R:R on the same scale.
                </p>
              </div>
              <div className="formula-card">
                <h4>Theta Efficiency</h4>
                <code>theta_eff = |net_theta| ÷ net_debit</code>
                <p className="formula-note">
                  Scored inversely — lower decay relative to cost is better.
                  A spread losing $0.02/day on a $2 debit scores higher than
                  one losing $0.10/day on a $3 debit.
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
                <h4>Spread Filters</h4>
                <div className="config-row">
                  <label>Short Delta Range</label>
                  <span className="config-value mono">0.15 – 0.45</span>
                </div>
                <div className="config-row">
                  <label>Max Spread Width</label>
                  <span className="config-value mono">$10</span>
                </div>
                <div className="config-row">
                  <label>Min Open Interest</label>
                  <span className="config-value mono">50</span>
                </div>
                <div className="config-row">
                  <label>Min Volume</label>
                  <span className="config-value mono">5</span>
                </div>
                <div className="config-row">
                  <label>Min R:R</label>
                  <span className="config-value mono">0.50</span>
                </div>
              </div>
              <div className="config-group">
                <h4>Scoring Weights</h4>
                <div className="weight-bar-display">
                  <div className="weight-segment" style={{ flex: 35, background: 'var(--accent-green)' }} title="EV 35%">EV 35%</div>
                  <div className="weight-segment" style={{ flex: 25, background: 'var(--accent-blue)' }} title="R:R 25%">R:R 25%</div>
                  <div className="weight-segment" style={{ flex: 20, background: 'var(--accent-cyan)' }} title="Prob 20%">Prob 20%</div>
                  <div className="weight-segment" style={{ flex: 15, background: 'var(--accent-purple)' }} title="Liq 15%">Liq 15%</div>
                  <div className="weight-segment" style={{ flex: 5, background: 'var(--accent-orange)' }} title="Theta 5%">θ</div>
                </div>
                <p className="formula-note" style={{ marginTop: 8 }}>
                  Weights are read-only in this version. Editable sliders
                  will be wired to the /config API in a future update.
                </p>
              </div>
              <div className="config-group">
                <h4>Chain Filters</h4>
                <div className="config-row">
                  <label>DTE Range</label>
                  <span className="config-value mono">14 – 60 days</span>
                </div>
                <div className="config-row">
                  <label>Strike Range</label>
                  <span className="config-value mono">±10%</span>
                </div>
                <div className="config-row">
                  <label>Max Results</label>
                  <span className="config-value mono">20</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
