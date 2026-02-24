/**
 * DirectionalPage — Strategy comparison for a directional thesis.
 *
 * DIFFERENT from the other two screens:
 * Verticals and Long Calls auto-run on symbol change because they
 * only need a symbol. Directional Compare needs more input: direction
 * (bullish/bearish), target price, and risk budget. So this screen
 * shows a thesis form first, and runs analysis on submit.
 */

import { useState, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import { analyzeDirectional } from '../api/client';
import StarButton from '../components/StarButton';
import ScoreBar from '../components/ScoreBar';
import './PageShared.css';
import './VerticalsPage.css'; // Reuse shared styles
import './DirectionalPage.css';

export default function DirectionalPage() {
  const { activeSymbol } = useApp();

  // Form state
  const [direction, setDirection] = useState('bullish');
  const [targetPrice, setTargetPrice] = useState('');
  const [riskBudget, setRiskBudget] = useState('1000');
  const [timeframeDays, setTimeframeDays] = useState('30');

  // Results
  const [strategies, setStrategies] = useState([]);
  const [thesis, setThesis] = useState(null);
  const [recommended, setRecommended] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showFormula, setShowFormula] = useState(false);

  const runAnalysis = useCallback(async () => {
    if (!targetPrice) return;
    setLoading(true);
    setError(null);
    try {
      const data = await analyzeDirectional({
        symbol: activeSymbol,
        direction,
        target_price: parseFloat(targetPrice),
        risk_budget: parseFloat(riskBudget),
        timeframe_days: parseInt(timeframeDays),
      });
      setStrategies(data.strategies || []);
      setThesis(data.thesis || null);
      setRecommended(data.recommended || null);
    } catch (err) {
      setError(err.message || 'Failed to fetch analysis');
      setStrategies([]);
    } finally {
      setLoading(false);
    }
  }, [activeSymbol, direction, targetPrice, riskBudget, timeframeDays]);

  function buildFavTrade(s) {
    return {
      id: `dc-${activeSymbol}-${s.strategy_name}-${s.expiration}`,
      symbol: activeSymbol,
      label: s.strategy_name,
      expiration: s.expiration,
      source: 'directional',
      score: s.prob_of_profit,
      originalPrice: `Cost: $${s.cost.toFixed(0)}`,
      cost: s.cost,
      maxProfit: s.max_profit,
    };
  }

  function verdictStyle(s) {
    if (s.is_recommended) return 'verdict-best';
    if (s.prob_of_profit >= 0.5) return 'verdict-good';
    return 'verdict-risky';
  }

  const handleSubmit = (e) => {
    e.preventDefault();
    runAnalysis();
  };

  return (
    <div className="page-card">
      <h2 className="page-title">
        Directional Compare —{' '}
        <span className="symbol-highlight">{activeSymbol}</span>
      </h2>

      {/* ═══ Thesis Form ═══ */}
      <form className="thesis-form" onSubmit={handleSubmit}>
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Direction</label>
            <div className="direction-toggle">
              <button
                type="button"
                className={`dir-btn ${direction === 'bullish' ? 'active bullish' : ''}`}
                onClick={() => setDirection('bullish')}
              >
                ▲ Bullish
              </button>
              <button
                type="button"
                className={`dir-btn ${direction === 'bearish' ? 'active bearish' : ''}`}
                onClick={() => setDirection('bearish')}
              >
                ▼ Bearish
              </button>
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Target Price</label>
            <input
              type="number"
              className="form-input"
              placeholder="e.g. 620"
              value={targetPrice}
              onChange={e => setTargetPrice(e.target.value)}
              step="0.01"
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label">Risk Budget ($)</label>
            <input
              type="number"
              className="form-input"
              value={riskBudget}
              onChange={e => setRiskBudget(e.target.value)}
              step="100"
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label">Timeframe (days)</label>
            <input
              type="number"
              className="form-input"
              value={timeframeDays}
              onChange={e => setTimeframeDays(e.target.value)}
              required
            />
          </div>
          <div className="form-group" style={{ alignSelf: 'flex-end' }}>
            <button type="submit" className="btn-primary" disabled={loading || !targetPrice}>
              {loading ? 'Analyzing…' : 'Compare Strategies'}
            </button>
          </div>
        </div>
      </form>

      {/* Loading */}
      {loading && (
        <div className="loading-state">
          <div className="spinner" />
          <span>Comparing strategies for {activeSymbol}…</span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="error-state">
          <span className="error-icon">⚠</span>
          <span>{error}</span>
          <button className="retry-btn" onClick={runAnalysis}>Retry</button>
        </div>
      )}

      {/* Thesis summary */}
      {thesis && !loading && (
        <div className="thesis-summary">
          <span className={`thesis-dir ${direction}`}>
            {direction === 'bullish' ? '▲' : '▼'} {direction.toUpperCase()}
          </span>
          <span className="mono">{activeSymbol}</span>
          <span className="text-muted">→</span>
          <span className="mono text-cyan">${thesis.target_price}</span>
          <span className="text-muted">within</span>
          <span className="mono">{thesis.timeframe_days}d</span>
          <span className="text-muted">|</span>
          <span className="mono">Budget: ${thesis.risk_budget}</span>
        </div>
      )}

      {/* Results */}
      {!loading && !error && strategies.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: 32 }}></th>
                <th>Strategy</th>
                <th>Exp</th>
                <th>Cost</th>
                <th>Max Profit</th>
                <th>Breakeven</th>
                <th>Prob %</th>
                <th>Buffer</th>
                <th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {strategies.map((s, i) => (
                <tr key={i} className={s.is_recommended ? 'recommended-row' : ''}>
                  <td><StarButton trade={buildFavTrade(s)} /></td>
                  <td className="mono">
                    {s.is_recommended && <span className="text-yellow">★ </span>}
                    {s.strategy_name.replace(/\.0(?=\/|$)/g, '')}
                  </td>
                  <td className="mono text-muted">{s.expiration}</td>
                  <td className="mono">${s.cost.toFixed(2)}</td>
                  <td className={`mono ${s.max_profit_str === 'Unlimited' ? 'text-cyan' : 'text-green'}`}>
                    {s.max_profit_str === 'Unlimited' ? (
                      <em>Unlimited</em>
                    ) : (
                      s.max_profit_str
                    )}
                  </td>
                  <td className="mono">${s.breakeven.toFixed(2)}</td>
                  <td className="mono">{(s.prob_of_profit * 100).toFixed(0)}%</td>
                  <td className={`mono ${s.buffer_pct >= 0 ? 'text-green' : 'text-red'}`}>
                    {s.buffer_pct.toFixed(1)}%
                  </td>
                  <td>
                    <span className={`verdict-badge ${verdictStyle(s)}`}>
                      {s.verdict}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Formula */}
      {strategies.length > 0 && (
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
                  <h4>Strategy Construction</h4>
                  <code>contracts = floor(budget ÷ cost_per_contract)</code>
                  <code>total_cost = contracts × cost_per_contract</code>
                  <code>total_max_profit = contracts × max_profit_per</code>
                </div>
                <div className="formula-card">
                  <h4>Thesis Fit</h4>
                  <code>required_move = (breakeven − price) ÷ price</code>
                  <code>buffer = (target − breakeven) ÷ target</code>
                  <p className="formula-note">
                    Buffer measures margin for error. Higher buffer = more room
                    for the thesis to be partially right and still profit.
                  </p>
                </div>
                <div className="formula-card">
                  <h4>Recommendation Logic</h4>
                  <p className="formula-note">
                    The engine picks the strategy that fits the budget,
                    has the highest probability of profit, and leaves
                    the most buffer. Cost efficiency (profit per dollar
                    risked) breaks ties.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
