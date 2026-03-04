/**
 * DirectionalPage — Strategy comparison for a directional thesis.
 *
 * ROUND 2: Added ✦ Ask Claude button per strategy and SMA chart.
 */

import { useState, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import { analyzeDirectional } from '../api/client';
import StarButton from '../components/StarButton';
import ScoreBar from '../components/ScoreBar';
import QuoteBar from '../components/QuoteBar';
import SmaPanel from '../components/SmaPanel';
import AskClaudePanel from '../components/AskClaudePanel';
import { C } from '../styles/tokens';
import './PageShared.css';
import './VerticalsPage.css';
import './DirectionalPage.css';

function generateCandles(price, count = 120) {
  const candles = [];
  let p = price * 0.95;
  for (let i = 0; i < count; i++) {
    const change = (Math.random() - 0.48) * price * 0.012;
    const open = p; const close = p + change;
    const high = Math.max(open, close) + Math.random() * price * 0.005;
    const low = Math.min(open, close) - Math.random() * price * 0.005;
    candles.push({ open, high, low, close, day: `d${i}` });
    p = close;
  }
  const scale = price / candles[candles.length - 1].close;
  return candles.map(c => ({ open: c.open * scale, high: c.high * scale, low: c.low * scale, close: c.close * scale, day: c.day }));
}

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

  // SMA chart
  const [smaPeriods, setSmaPeriods] = useState({ short: 8, mid: 21, long: 50 });
  const [candles, setCandles] = useState([]);

  // Ask Claude
  const [claudeOpen, setClaudeOpen] = useState(false);
  const [claudeTrade, setClaudeTrade] = useState(null);

  const runAnalysis = useCallback(async () => {
    if (!targetPrice) return;
    setLoading(true);
    setError(null);
    try {
      const data = await analyzeDirectional({
        symbol: activeSymbol, direction,
        target_price: parseFloat(targetPrice),
        risk_budget: parseFloat(riskBudget),
        timeframe_days: parseInt(timeframeDays),
      });
      setStrategies(data.strategies || []);
      setThesis(data.thesis || null);
      setRecommended(data.recommended || null);
      if (data.thesis?.current_price) setCandles(generateCandles(data.thesis.current_price));
    } catch (err) {
      setError(err.message || 'Failed to fetch analysis');
      setStrategies([]);
    } finally {
      setLoading(false);
    }
  }, [activeSymbol, direction, targetPrice, riskBudget, timeframeDays]);

  function getSmaData() {
    if (!candles.length) return { price: 0, smaShort: 0, smaMid: 0, smaLong: 0 };
    const sma = (period) => candles.slice(-period).reduce((s, c) => s + c.close, 0) / Math.min(period, candles.length);
    return { price: candles[candles.length - 1]?.close || 0, smaShort: sma(smaPeriods.short), smaMid: sma(smaPeriods.mid), smaLong: sma(smaPeriods.long) };
  }

  function buildClaudeTrade(s) {
    return {
      symbol: activeSymbol, spread_type: s.strategy_name,
      long_strike: s.breakeven, short_strike: null,
      expiration: s.expiration, option_type: direction === 'bullish' ? 'call' : 'put',
      net_debit: s.cost / 100, max_profit: s.max_profit || 0,
      max_loss: s.cost / 100,
      reward_risk_ratio: s.max_profit && s.cost ? (s.max_profit / s.cost) : 0,
      prob_of_profit: s.prob_of_profit,
      composite_score: s.prob_of_profit,
    };
  }

  function buildFavTrade(s) {
    return {
      id: `dc-${activeSymbol}-${s.strategy_name}-${s.expiration}`,
      symbol: activeSymbol, label: s.strategy_name,
      expiration: s.expiration, source: 'directional',
      score: s.prob_of_profit,
      originalPrice: `Cost: ${s.cost.toFixed(2)}`,
      cost: s.cost, maxProfit: s.max_profit,
    };
  }

  function verdictStyle(s) {
    if (s.is_recommended) return 'verdict-best';
    if (s.prob_of_profit >= 0.5) return 'verdict-good';
    return 'verdict-risky';
  }

  const handleSubmit = (e) => { e.preventDefault(); runAnalysis(); };

  return (
    <div className="page-card">
      <QuoteBar title="Directional Strategy Compare" />

      {candles.length > 0 && !loading && (
        <SmaPanel candles={candles} smaPeriods={smaPeriods} onPeriodsChange={setSmaPeriods} symbol={activeSymbol} />
      )}

      {/* Thesis Form */}
      <form className="thesis-form" onSubmit={handleSubmit}>
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Direction</label>
            <div className="direction-toggle">
              <button type="button" className={`dir-btn ${direction === 'bullish' ? 'active bullish' : ''}`} onClick={() => setDirection('bullish')}>▲ Bullish</button>
              <button type="button" className={`dir-btn ${direction === 'bearish' ? 'active bearish' : ''}`} onClick={() => setDirection('bearish')}>▼ Bearish</button>
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Target Price</label>
            <input type="number" className="form-input" placeholder="e.g. 620" value={targetPrice} onChange={e => setTargetPrice(e.target.value)} step="0.01" required />
          </div>
          <div className="form-group">
            <label className="form-label">Risk Budget ($)</label>
            <input type="number" className="form-input" value={riskBudget} onChange={e => setRiskBudget(e.target.value)} step="100" required />
          </div>
          <div className="form-group">
            <label className="form-label">Timeframe (days)</label>
            <input type="number" className="form-input" value={timeframeDays} onChange={e => setTimeframeDays(e.target.value)} required />
          </div>
          <div className="form-group" style={{ alignSelf: 'flex-end' }}>
            <button type="submit" className="btn-primary" disabled={loading || !targetPrice}>
              {loading ? 'Analyzing…' : 'Compare Strategies'}
            </button>
          </div>
        </div>
      </form>

      {loading && (<div className="loading-state"><div className="spinner" /><span>Comparing strategies for {activeSymbol}…</span></div>)}
      {error && (<div className="error-state"><span className="error-icon">⚠</span><span>{error}</span><button className="retry-btn" onClick={runAnalysis}>Retry</button></div>)}

      {thesis && !loading && (
        <div className="thesis-summary">
          <span className={`thesis-dir ${direction}`}>{direction === 'bullish' ? '▲' : '▼'} {direction.toUpperCase()}</span>
          <span className="mono">{activeSymbol}</span>
          <span className="text-muted">→</span>
          <span className="mono text-cyan">{thesis.target_price}</span>
          <span className="text-muted">within</span>
          <span className="mono">{thesis.timeframe_days}d</span>
          <span className="text-muted">|</span>
          <span className="mono">Budget: {thesis.risk_budget}</span>
        </div>
      )}

      {!loading && !error && strategies.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: 32 }}></th>
                <th>Strategy</th>
                <th>Exp</th>
                <th style={{ textAlign: 'right' }}>Cost</th>
                <th style={{ textAlign: 'right' }}>Max Profit</th>
                <th style={{ textAlign: 'right' }}>Breakeven</th>
                <th style={{ textAlign: 'right' }}>Prob %</th>
                <th style={{ textAlign: 'right' }}>Buffer</th>
                <th>Verdict</th>
                <th style={{ width: 60 }}></th>
              </tr>
            </thead>
            <tbody>
              {strategies.map((s, i) => (
                <tr key={i} className={s.is_recommended ? 'recommended-row' : ''}>
                  <td><StarButton trade={buildFavTrade(s)} /></td>
                  <td className="mono">
                    {s.is_recommended && <span className="text-yellow">☆ </span>}
                    {s.strategy_name.replace(/\.0(?=\/|$)/g, '')}
                  </td>
                  <td className="mono text-muted">{s.expiration}</td>
                  <td className="mono">{s.cost.toFixed(2)}</td>
                  <td className={`mono ${s.max_profit_str === 'Unlimited' ? 'text-cyan' : 'text-green'}`}>
                    {s.max_profit_str === 'Unlimited' ? <em>Unlimited</em> : s.max_profit_str}
                  </td>
                  <td className="mono">{s.breakeven.toFixed(2)}</td>
                  <td className="mono">{(s.prob_of_profit * 100).toFixed(0)}%</td>
                  <td className={`mono ${s.buffer_pct >= 0 ? 'text-green' : 'text-red'}`}>{s.buffer_pct.toFixed(1)}%</td>
                  <td><span className={`verdict-badge ${verdictStyle(s)}`}>{s.verdict}</span></td>
                  <td>
                    <button
                      onClick={(e) => { e.stopPropagation(); setClaudeTrade(buildClaudeTrade(s)); setClaudeOpen(true); }}
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

      {/* Formula section */}
      {strategies.length > 0 && (
        <div className="collapsible-section">
          <button className={`collapsible-toggle ${showFormula ? 'open' : ''}`} onClick={() => setShowFormula(!showFormula)}>
            <span className="toggle-icon">{showFormula ? '▼' : '▶'}</span> Formula Transparency
          </button>
          {showFormula && (
            <div className="collapsible-body">
              <div className="formula-grid">
                <div className="formula-card"><h4>Strategy Construction</h4><code>contracts = floor(budget ÷ cost_per_contract)</code><code>total_cost = contracts × cost_per_contract</code></div>
                <div className="formula-card"><h4>Thesis Fit</h4><code>buffer = (target − breakeven) ÷ target</code><p className="formula-note">Higher buffer = more room for error.</p></div>
                <div className="formula-card"><h4>Recommendation</h4><p className="formula-note">Picks the strategy with highest probability that fits the budget, with most buffer. Cost efficiency breaks ties.</p></div>
              </div>
            </div>
          )}
        </div>
      )}

      <AskClaudePanel open={claudeOpen} onClose={() => setClaudeOpen(false)} trade={claudeTrade} smaData={getSmaData()} smaPeriods={smaPeriods} />
    </div>
  );
}
