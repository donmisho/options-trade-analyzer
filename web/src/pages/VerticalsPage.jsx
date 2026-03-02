/**
 * VerticalsPage — Vertical Spread analysis screen.
 *
 * ROUND 2 ENHANCEMENTS:
 *   - SmaPanel: candlestick chart with SMA overlay above results
 *   - ✦ Ask Claude: button per trade opens AI evaluation panel
 *   - ConfigDrawer: replaces the read-only config section
 *   - FormulaBreakdown: expandable per-trade scoring math
 *
 * The existing CSS (PageShared.css, VerticalsPage.css) is preserved.
 * New components use inline styles via tokens.js, so they blend in
 * without needing additional CSS.
 */

import { useState, useEffect, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import { analyzeVerticals } from '../api/client';
import StarButton from '../components/StarButton';
import ScoreBar from '../components/ScoreBar';
import QuoteBar from '../components/QuoteBar';
import SmaPanel from '../components/SmaPanel';
import AskClaudePanel from '../components/AskClaudePanel';
import FormulaBreakdownPanel from '../components/FormulaBreakdownPanel';
import ConfigDrawer from '../components/ConfigDrawer';
import { C, mono, DEFAULT_PRESETS } from '../styles/tokens';
import './PageShared.css';
import './VerticalsPage.css';

// Generate sample candle data from price (until we wire historical API)
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
  // Scale last candles so the final close matches current price
  const scale = price / candles[candles.length - 1].close;
  return candles.map(c => ({
    open: c.open * scale,
    high: c.high * scale,
    low: c.low * scale,
    close: c.close * scale,
    day: c.day,
  }));
}

export default function VerticalsPage() {
  const { activeSymbol } = useApp();

  // API results
  const [spreads, setSpreads] = useState([]);
  const [underlyingPrice, setUnderlyingPrice] = useState(0);
  const [totalValid, setTotalValid] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // SMA chart
  const [smaPeriods, setSmaPeriods] = useState({ short: 8, mid: 21, long: 50 });
  const [candles, setCandles] = useState([]);

  // Ask Claude
  const [claudeOpen, setClaudeOpen] = useState(false);
  const [claudeTrade, setClaudeTrade] = useState(null);

 // Formula breakdown slideout
  const [formulaOpen, setFormulaOpen] = useState(false);
  const [formulaTrade, setFormulaTrade] = useState(null);

  // Config drawer
  const [configOpen, setConfigOpen] = useState(false);
  const [presets, setPresets] = useState(DEFAULT_PRESETS);
  const [activePresetId, setActivePresetId] = useState('balanced');
  const activePreset = presets.find(p => p.id === activePresetId) || presets[0];
  const [config, setConfig] = useState({
    weights: { ...activePreset.weights },
    dte: { min: activePreset.dte?.min || 14, max: activePreset.dte?.max || 60 },
    strikes: { range_pct: activePreset.strikes?.range_pct || 10, min_open_interest: 50, min_volume: 5 },
    spreads: { min_width: activePreset.spreads?.min_width || 1, max_width: activePreset.spreads?.max_width || 10 },
    risk: { max_risk_per_trade: activePreset.risk?.max_risk || 500, profit_target_pct: 75, stop_loss_pct: 50 },
  });


  // ─── Fetch analysis ──────────────────────────────────────────

  const runAnalysis = useCallback(async (symbol) => {
    setLoading(true);
    setError(null);
    try {
      const data = await analyzeVerticals({
        symbol,
        spread_types: ['bull_call', 'bear_put'],
        max_results: 20,
        // Pass config weights
        ev_weight: config.weights.expected_value,
        rr_weight: config.weights.reward_risk,
        prob_weight: config.weights.probability,
        liq_weight: config.weights.liquidity,
        theta_weight: config.weights.theta_efficiency,
        min_dte: config.dte.min,
        max_dte: config.dte.max,
        strike_range_pct: config.strikes.range_pct,
      });
      setSpreads(data.spreads || []);
      setUnderlyingPrice(data.underlying_price || 0);
      setTotalValid(data.total_valid || 0);
      // Generate chart candles from the underlying price
      if (data.underlying_price) {
        setCandles(generateCandles(data.underlying_price));
      }
    } catch (err) {
      setError(err.message || 'Failed to fetch analysis');
      setSpreads([]);
    } finally {
      setLoading(false);
    }
  }, [config]);

  // Auto-run when symbol changes
  useEffect(() => {
    if (activeSymbol) {
      runAnalysis(activeSymbol);
    }
  }, [activeSymbol, runAnalysis]);

  // Compute SMA data for Ask Claude panel
  function getSmaData() {
    if (!candles.length) return { price: underlyingPrice, smaShort: 0, smaMid: 0, smaLong: 0 };
    const sma = (period) => {
      const slice = candles.slice(-period);
      return slice.reduce((s, c) => s + c.close, 0) / slice.length;
    };
    return {
      price: candles[candles.length - 1]?.close || underlyingPrice,
      smaShort: sma(smaPeriods.short),
      smaMid: sma(smaPeriods.mid),
      smaLong: sma(smaPeriods.long),
    };
  }

  // Build trade object for Ask Claude
  function buildClaudeTrade(s) {
    return {
      symbol: activeSymbol,
      spread_type: s.spread_type,
      long_strike: s.long_strike,
      short_strike: s.short_strike,
      expiration: s.expiration,
      option_type: s.spread_type === 'bull_call' ? 'call' : 'put',
      net_debit: s.net_debit,
      max_profit: s.max_profit,
      max_loss: s.net_debit,
      reward_risk_ratio: s.reward_risk_ratio,
      prob_of_profit: s.prob_of_profit,
      composite_score: s.composite_score,
    };
  }

  // Build trade object for Formula Breakdown panel
  function buildFormulaTrade(s) {
    return {
      symbol: activeSymbol,
      spread_type: s.spread_type,
      long_strike: s.long_strike,
      short_strike: s.short_strike,
      expiration: s.expiration,
      net_debit: s.net_debit,
      max_profit: s.max_profit,
      reward_risk_ratio: s.reward_risk_ratio,
      prob_of_profit: s.prob_of_profit,
      composite_score: s.composite_score,
      // Liquidity fields (may be 0 if not in API response yet)
      long_volume: s.long_volume || 0,
      short_volume: s.short_volume || 0,
      long_oi: s.long_oi || 0,
      short_oi: s.short_oi || 0,
      // Theta
      net_theta: s.net_theta || 0,
    };
  }
  
  // ─── Build favorite trade object ─────────────────────────────

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

  // ─── Config handlers ─────────────────────────────────────────

  const handlePresetSelect = (id) => {
    setActivePresetId(id);
    const preset = presets.find(p => p.id === id);
    if (preset) {
      setConfig({
        weights: { ...preset.weights },
        dte: { min: preset.dte?.min || 14, max: preset.dte?.max || 60 },
        strikes: { range_pct: preset.strikes?.range_pct || 10, min_open_interest: 50, min_volume: 5 },
        spreads: { min_width: preset.spreads?.min_width || 1, max_width: preset.spreads?.max_width || 10 },
        risk: { max_risk_per_trade: preset.risk?.max_risk || 500, profit_target_pct: 75, stop_loss_pct: 50 },
      });
    }
  };

  // ─── Render ──────────────────────────────────────────────────

  return (
    <div className="page-card">
      <QuoteBar title="Vertical Spread Analysis" />

      {/* SMA Chart — shows above results when we have data */}
      {candles.length > 0 && !loading && (
        <SmaPanel
          candles={candles}
          smaPeriods={smaPeriods}
          onPeriodsChange={setSmaPeriods}
          symbol={activeSymbol}
        />
      )}

      {/* Status bar with config button */}
      {!loading && !error && spreads.length > 0 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <p className="page-subtitle" style={{ margin: 0 }}>
            Showing top {spreads.length} of {totalValid} valid spreads, ranked by composite score.
          </p>
          <button
            onClick={() => setConfigOpen(true)}
            style={{
              padding: '5px 12px', borderRadius: 6,
              border: `1px solid ${C.border}`, backgroundColor: 'transparent',
              color: C.textDim, fontSize: 12, cursor: 'pointer',
            }}
          >
            ⚙ Config
          </button>
        </div>
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
                <th style={{ width: 60 }}></th>
              </tr>
            </thead>
            <tbody>
              {spreads.map((s, i) => {
                const isBull = s.spread_type === 'bull_call';
                return (
                  <tr key={i}
                    style={{ borderLeft: '2px solid transparent' }}
                  >
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
                  <td>
                      <div style={{ display: 'flex', gap: 3 }}>
                        <button
                          onClick={(e) => { e.stopPropagation(); setClaudeTrade(buildClaudeTrade(s)); setClaudeOpen(true); setFormulaOpen(false); }}
                          title="Ask Claude to evaluate this trade"
                          style={{
                            padding: '3px 7px', borderRadius: 4,
                            border: `1px solid ${C.claudeBorder}`,
                            backgroundColor: C.claudeDim, color: C.claudeAccent,
                            fontSize: 12, fontWeight: 700, cursor: 'pointer',
                            lineHeight: 1,
                          }}
                        >
                          ✦
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); setFormulaTrade(buildFormulaTrade(s)); setFormulaOpen(true); setClaudeOpen(false); }}
                          title="View scoring formula breakdown"
                          style={{
                            padding: '3px 7px', borderRadius: 4,
                            border: `1px solid ${C.accent}30`,
                            backgroundColor: `${C.accent}10`, color: C.accent,
                            fontSize: 10, fontWeight: 600, cursor: 'pointer',
                            fontFamily: mono,
                            lineHeight: 1,
                          }}
                        >
                          ƒx
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && spreads.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">📊</div>
          <h3>No spreads found</h3>
          <p>
            No valid vertical spreads matched the current filters for {activeSymbol}.
            Try a different symbol or adjust the filter settings.
          </p>
        </div>
      )}

       {/* ═══ Formula Breakdown Panel ═══ */}
      <FormulaBreakdownPanel
        open={formulaOpen}
        onClose={() => setFormulaOpen(false)}
        trade={formulaTrade}
        symbol={activeSymbol}
        weights={config.weights}
      />
              
      {/* ═══ Ask Claude Panel ═══ */}
      <AskClaudePanel
        open={claudeOpen}
        onClose={() => setClaudeOpen(false)}
        trade={claudeTrade}
        smaData={getSmaData()}
        smaPeriods={smaPeriods}
      />

      {/* ═══ Config Drawer ═══ */}
      <ConfigDrawer
        open={configOpen}
        onClose={() => { setConfigOpen(false); runAnalysis(activeSymbol); }}
        config={config}
        onConfigChange={setConfig}
        presets={presets}
        activePresetId={activePresetId}
        onPresetSelect={handlePresetSelect}
        onSavePreset={(name) => {
          const id = name.toLowerCase().replace(/\s+/g, '_');
          setPresets(prev => [...prev, { id, name, icon: '📌', desc: 'Custom preset', ...config }]);
          setActivePresetId(id);
        }}
        onOverwrite={(id) => {
          setPresets(prev => prev.map(p => p.id === id ? { ...p, ...config } : p));
        }}
        onDelete={(id) => {
          setPresets(prev => prev.filter(p => p.id !== id));
          if (activePresetId === id) setActivePresetId('balanced');
        }}
        onRename={(id, newName) => {
          setPresets(prev => prev.map(p => p.id === id ? { ...p, name: newName } : p));
        }}
      />
    </div>
  );
}
