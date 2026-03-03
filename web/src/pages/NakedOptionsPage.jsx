/**
 * NakedOptionsPage — Puts & Calls analysis screen.
 *
 * Built from the UPDATED VerticalsPage pattern (Round 4), not the old
 * LongCallsPage. Key features:
 *   - Call/Put toggle chips (always visible)
 *   - ConfigDrawer with mode="naked" (hides spread sections)
 *   - FormulaBreakdownPanel slideout (not the old inline Formula Transparency)
 *   - Sortable table columns
 *   - Draft/commit config pattern with configRef
 *   - SMA periods driven from config
 *   - Type-aware trade builders (call vs put)
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useApp } from '../context/AppContext';
import { analyzeLongCalls } from '../api/client';
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

function generateCandles(price, count = 120) {
  const candles = [];
  let p = price * 0.95;
  for (let i = 0; i < count; i++) {
    const change = (Math.random() - 0.48) * price * 0.012;
    const open = p; const close = p + change;
    const high = Math.max(open, close) + Math.random() * price * 0.005;
    const low = Math.min(open, close) - Math.random() * price * 0.005;
    candles.push({ open, high, low, close, day: `d${i}` }); p = close;
  }
  const scale = price / candles[candles.length - 1].close;
  return candles.map(c => ({ open: c.open * scale, high: c.high * scale, low: c.low * scale, close: c.close * scale, day: c.day }));
}

function computeAlignment(price, smaShort, smaMid, smaLong) {
  if (!price || !smaShort || !smaMid || !smaLong) return "mixed";
  if (price > smaShort && price > smaMid && price > smaLong) return "bullish";
  if (price < smaShort && price < smaMid && price < smaLong) return "bearish";
  return "mixed";
}

// --- Sortable header ---
function SortTh({ label, sortKey, currentSort, onSort, style }) {
  const isActive = currentSort.key === sortKey;
  const arrow = isActive ? (currentSort.dir === 'asc' ? ' ▲' : ' ▼') : '';
  return (
    <th onClick={() => onSort(sortKey)} style={{ cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap', ...style }}>
      {label}{arrow && <span style={{ fontSize: 9, opacity: 0.7 }}>{arrow}</span>}
    </th>
  );
}

export default function NakedOptionsPage() {
  const { activeSymbol, configOpen, setConfigOpen } = useApp();

  const [results, setResults] = useState([]);
  const [underlyingPrice, setUnderlyingPrice] = useState(0);
  const [totalValid, setTotalValid] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Option type toggles
  const [showCalls, setShowCalls] = useState(true);
  const [showPuts, setShowPuts] = useState(false);

  // SMA chart
  const [candles, setCandles] = useState([]);

  // Ask Claude
  const [claudeOpen, setClaudeOpen] = useState(false);
  const [claudeTrade, setClaudeTrade] = useState(null);

  // Formula breakdown slideout
  const [formulaOpen, setFormulaOpen] = useState(false);
  const [formulaTrade, setFormulaTrade] = useState(null);

  // Sort state
  const [sort, setSort] = useState({ key: null, dir: 'desc' });

  // Config
  const [presets, setPresets] = useState(DEFAULT_PRESETS);
  const [activePresetId, setActivePresetId] = useState('balanced');
  const activePreset = presets.find(p => p.id === activePresetId) || presets[0];
  const [config, setConfig] = useState({
    weights: { ...activePreset.weights },
    dte: { min: 7, max: 90 },
    strikes: { range_pct: 10, min_open_interest: 50, min_volume: 5 },
    spreads: { min_width: 1, max_width: 10 },
    risk: { max_risk_per_trade: 500, profit_target_pct: 75, stop_loss_pct: 50 },
    spreadTypes: { bull_call: true, bear_put: true },
    greeks: { min_short_delta: 0.25, max_short_delta: 0.65, min_net_delta: 0, max_net_theta: 0 },
    smaPeriods: { short: 8, mid: 21, long: 50 },
  });

  const configRef = useRef(config);

  // ─── SMA data and alignment ──────────────────────────────────
  const smaPeriods = config.smaPeriods || { short: 8, mid: 21, long: 50 };

  function getSmaData() {
    if (!candles.length) return { price: underlyingPrice, smaShort: 0, smaMid: 0, smaLong: 0 };
    const sma = (period) => {
      const slice = candles.slice(-period);
      return slice.reduce((s, c) => s + c.close, 0) / slice.length;
    };
    return {
      price: candles[candles.length - 1]?.close || underlyingPrice,
      smaShort: sma(smaPeriods.short), smaMid: sma(smaPeriods.mid), smaLong: sma(smaPeriods.long),
    };
  }

  const smaData = getSmaData();
  const alignment = computeAlignment(smaData.price, smaData.smaShort, smaData.smaMid, smaData.smaLong);

  // ─── Fetch analysis ──────────────────────────────────────────
  const runAnalysis = useCallback(async (symbol) => {
    const cfg = configRef.current;
    setLoading(true);
    setError(null);
    try {
      const option_types = [];
      if (showCalls) option_types.push('call');
      if (showPuts) option_types.push('put');
      if (option_types.length === 0) option_types.push('call');

      const data = await analyzeLongCalls({ symbol, max_results: 20, option_types });
      setResults(data.calls || data.options || []);
      setUnderlyingPrice(data.underlying_price || 0);
      setTotalValid(data.total_valid || 0);
      if (data.underlying_price) setCandles(generateCandles(data.underlying_price));
    } catch (err) {
      setError(err.message || 'Failed to fetch analysis');
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [showCalls, showPuts]);

  useEffect(() => {
    if (activeSymbol) runAnalysis(activeSymbol);
  }, [activeSymbol, runAnalysis]);

  // ─── Sorting ─────────────────────────────────────────────────
  const handleSort = (key) => {
    setSort(prev => {
      if (prev.key === key) {
        if (prev.dir === 'desc') return { key, dir: 'asc' };
        return { key: null, dir: 'desc' };
      }
      return { key, dir: 'desc' };
    });
  };

  const sortedResults = useMemo(() => {
    if (!sort.key) return results;
    return [...results].sort((a, b) => {
      let av = a[sort.key]; let bv = b[sort.key];
      if (typeof av === 'string') return sort.dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      return sort.dir === 'asc' ? av - bv : bv - av;
    });
  }, [results, sort]);

  // ─── Trade builders (type-aware) ─────────────────────────────
  function buildClaudeTrade(c) {
    const type = c.option_type || 'call';
    return {
      symbol: activeSymbol, spread_type: type === 'put' ? 'long_put' : 'long_call',
      long_strike: c.strike, short_strike: null,
      expiration: c.expiration, option_type: type,
      net_debit: c.premium_dollars / 100, max_profit: 999,
      max_loss: c.premium_dollars / 100,
      reward_risk_ratio: 0, prob_of_profit: c.delta,
      composite_score: c.composite_score,
    };
  }

  function buildFormulaTrade(c) {
    const type = c.option_type || 'call';
    return {
      symbol: activeSymbol, spread_type: type === 'put' ? 'long_put' : 'long_call',
      long_strike: c.strike, short_strike: null,
      expiration: c.expiration, option_type: type,
      net_debit: c.premium_dollars / 100,
      max_profit: 999, max_loss: c.premium_dollars / 100,
      reward_risk_ratio: 0, prob_of_profit: c.delta,
      composite_score: c.composite_score,
      delta: c.delta, theta: c.theta, iv: c.iv,
      premium_dollars: c.premium_dollars,
      theta_runway_days: c.theta_runway_days,
      volume: c.volume, open_interest: c.open_interest,
    };
  }

  function buildFavTrade(c) {
    const type = c.option_type || 'call';
    const typeLabel = type === 'put' ? 'Put' : 'Call';
    return {
      id: `nc-${activeSymbol}-${c.strike}-${c.expiration}-${type}`,
      symbol: activeSymbol, label: `$${c.strike} ${typeLabel}`,
      expiration: c.expiration, source: 'naked',
      score: c.composite_score,
      originalPrice: `Premium: $${c.premium_dollars.toFixed(2)}`,
      premium: c.premium_dollars, delta: c.delta, iv: c.iv,
    };
  }

  // ─── Config handlers ─────────────────────────────────────────
  const handlePresetSelect = (id) => {
    setActivePresetId(id);
    const preset = presets.find(p => p.id === id);
    if (preset) {
      setConfig(prev => ({
        ...prev,
        weights: { ...preset.weights },
        dte: { min: preset.dte?.min || 7, max: preset.dte?.max || 90 },
      }));
    }
  };

  const handleConfigApply = useCallback((newConfig) => {
    setConfig(newConfig);
    setConfigOpen(false);
    configRef.current = newConfig;
    runAnalysis(activeSymbol);
  }, [activeSymbol, runAnalysis, setConfigOpen]);

  // ─── Dynamic title ───────────────────────────────────────────
  const pageTitle = showCalls && showPuts
    ? "Puts & Calls Analysis"
    : showPuts ? "Long Put Analysis" : "Long Call Analysis";

  // ─── Render ──────────────────────────────────────────────────
  return (
    <div className="page-card">
      <QuoteBar title={pageTitle} />

      {candles.length > 0 && !loading && (
        <SmaPanel candles={candles} smaPeriods={smaPeriods} onPeriodsChange={(p) => setConfig(prev => ({ ...prev, smaPeriods: p }))} symbol={activeSymbol} />
      )}

      {/* Toggles + config — always visible */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {!loading && !error && results.length > 0 && (
            <p className="page-subtitle" style={{ margin: 0 }}>
              Showing top {results.length} of {totalValid} candidates.
            </p>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button onClick={() => { if (showPuts || !showCalls) setShowCalls(!showCalls); }}
            style={{
              padding: '4px 10px', borderRadius: 5, fontSize: 11, fontWeight: 600, cursor: 'pointer',
              border: `1.5px solid ${showCalls ? C.green : C.border}`,
              backgroundColor: showCalls ? `${C.green}18` : 'transparent',
              color: showCalls ? C.green : C.textMuted,
            }}>
            {showCalls ? '✓ ' : ''}Calls
          </button>
          <button onClick={() => { if (showCalls || !showPuts) setShowPuts(!showPuts); }}
            style={{
              padding: '4px 10px', borderRadius: 5, fontSize: 11, fontWeight: 600, cursor: 'pointer',
              border: `1.5px solid ${showPuts ? C.red : C.border}`,
              backgroundColor: showPuts ? `${C.red}18` : 'transparent',
              color: showPuts ? C.red : C.textMuted,
            }}>
            {showPuts ? '✓ ' : ''}Puts
          </button>
          <button onClick={() => setConfigOpen(true)}
            style={{ padding: '5px 12px', borderRadius: 6, border: `1px solid ${C.border}`, backgroundColor: 'transparent', color: C.textDim, fontSize: 12, cursor: 'pointer' }}>
            ⚙ Config
          </button>
        </div>
      </div>

      {loading && (
        <div className="loading-state"><div className="spinner" /><span>Analyzing {activeSymbol} options…</span></div>
      )}

      {error && (
        <div className="error-state">
          <span className="error-icon">⚠</span><span>{error}</span>
          <button className="retry-btn" onClick={() => runAnalysis(activeSymbol)}>Retry</button>
        </div>
      )}

      {!loading && !error && sortedResults.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: 32 }}></th>
                <SortTh label="Type" sortKey="option_type" currentSort={sort} onSort={handleSort} />
                <SortTh label="Strike" sortKey="strike" currentSort={sort} onSort={handleSort} />
                <SortTh label="Exp" sortKey="expiration" currentSort={sort} onSort={handleSort} />
                <SortTh label="Premium" sortKey="premium_dollars" currentSort={sort} onSort={handleSort} />
                <SortTh label="Delta" sortKey="delta" currentSort={sort} onSort={handleSort} />
                <SortTh label="Theta $/day" sortKey="theta_per_day_dollars" currentSort={sort} onSort={handleSort} />
                <SortTh label="Runway" sortKey="theta_runway_days" currentSort={sort} onSort={handleSort} />
                <SortTh label="IV" sortKey="iv" currentSort={sort} onSort={handleSort} />
                <SortTh label="Breakeven" sortKey="breakeven" currentSort={sort} onSort={handleSort} />
                <SortTh label="Score" sortKey="composite_score" currentSort={sort} onSort={handleSort} />
                <th style={{ width: 70 }}></th>
              </tr>
            </thead>
            <tbody>
              {sortedResults.map((c, i) => (
                <tr key={i}>
                  <td><StarButton trade={buildFavTrade(c)} /></td>
                  <td><span className={`type-badge ${(c.option_type || 'call') === 'call' ? 'type-bull' : 'type-bear'}`}>{(c.option_type || 'call') === 'call' ? 'Call' : 'Put'}</span></td>
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
                    <div style={{ display: 'flex', gap: 3 }}>
                      <button onClick={(e) => { e.stopPropagation(); setClaudeTrade(buildClaudeTrade(c)); setClaudeOpen(true); setFormulaOpen(false); }}
                        title="Ask Claude" style={{ padding: '3px 7px', borderRadius: 4, border: `1px solid ${C.claudeBorder}`, backgroundColor: C.claudeDim, color: C.claudeAccent, fontSize: 12, fontWeight: 700, cursor: 'pointer', lineHeight: 1 }}>✦</button>
                      <button onClick={(e) => { e.stopPropagation(); setFormulaTrade(buildFormulaTrade(c)); setFormulaOpen(true); setClaudeOpen(false); }}
                        title="View scoring formula" style={{ padding: '3px 7px', borderRadius: 4, border: `1px solid ${C.accent}30`, backgroundColor: `${C.accent}10`, color: C.accent, fontSize: 10, fontWeight: 600, cursor: 'pointer', fontFamily: mono, lineHeight: 1 }}>ƒx</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && !error && results.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">📊</div>
          <h3>No candidates found</h3>
          <p>No options matched the current filters for {activeSymbol}.</p>
        </div>
      )}

      {/* Formula Breakdown slideout */}
      <FormulaBreakdownPanel open={formulaOpen} onClose={() => setFormulaOpen(false)} trade={formulaTrade} symbol={activeSymbol} weights={config.weights} />

      {/* Ask Claude Panel */}
      <AskClaudePanel open={claudeOpen} onClose={() => setClaudeOpen(false)} trade={claudeTrade} smaData={smaData} smaPeriods={smaPeriods} />

      {/* Config Drawer — mode="naked" hides spread sections */}
      <ConfigDrawer
        mode="naked"
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        config={config}
        onApply={handleConfigApply}
        alignment={alignment}
        presets={presets}
        activePresetId={activePresetId}
        onPresetSelect={handlePresetSelect}
        onSavePreset={(name) => {
          const id = name.toLowerCase().replace(/\s+/g, '_');
          setPresets(prev => [...prev, { id, name, icon: '📌', desc: 'Custom preset', ...config }]);
          setActivePresetId(id);
        }}
        onOverwrite={(id) => { setPresets(prev => prev.map(p => p.id === id ? { ...p, ...config } : p)); }}
        onDelete={(id) => { setPresets(prev => prev.filter(p => p.id !== id)); if (activePresetId === id) setActivePresetId('balanced'); }}
        onRename={(id, newName) => { setPresets(prev => prev.map(p => p.id === id ? { ...p, name: newName } : p)); }}
      />
    </div>
  );
}
