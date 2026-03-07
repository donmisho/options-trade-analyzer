/**
 * VerticalsPage — Vertical Spread analysis screen.
 *
 * ROUND 4: Added sortable table columns and smaPeriods in config
 * (so ConfigDrawer's SMA Periods section feeds back here).
 * All Round 3 features preserved: draft/commit, configRef, spread types.
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useApp } from '../context/AppContext';
import { analyzeVerticals } from '../api/client';
import StarButton from '../components/StarButton';
import ScoreBar from '../components/ScoreBar';
import QuoteBar from '../components/QuoteBar';
import SmaPanel from '../components/SmaPanel';
import FormulaBreakdownPanel from '../components/FormulaBreakdownPanel';
import RecommendationBadge from '../components/RecommendationBadge';
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

// --- Sortable header helper (shared pattern with NakedOptionsPage) ---
function SortTh({ label, sortKey, currentSort, onSort, style, num }) {
  const isActive = currentSort.key === sortKey;
  const arrow = isActive ? (currentSort.dir === 'asc' ? ' ▲' : ' ▼') : '';
  return (
    <th onClick={() => onSort(sortKey)} style={{ cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap', ...(num ? { textAlign: 'right' } : {}), ...style }}>
      {label}{arrow && <span style={{ fontSize: 9, opacity: 0.7 }}>{arrow}</span>}
    </th>
  );
}

export default function VerticalsPage() {
  const { activeSymbol, configOpen, setConfigOpen, openAgent } = useApp();

  const [spreads, setSpreads] = useState([]);
  const [underlyingPrice, setUnderlyingPrice] = useState(0);
  const [totalValid, setTotalValid] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [candles, setCandles] = useState([]);

  const [selectedIds, setSelectedIds] = useState(new Set());
  const [formulaOpen, setFormulaOpen] = useState(false);
  const [formulaTrade, setFormulaTrade] = useState(null);

  // Sort state — NEW
  const [sort, setSort] = useState({ key: null, dir: 'desc' });

  // Config
  const [presets, setPresets] = useState(DEFAULT_PRESETS);
  const [activePresetId, setActivePresetId] = useState('balanced');
  const activePreset = presets.find(p => p.id === activePresetId) || presets[0];
  const [config, setConfig] = useState({
    weights: { ...activePreset.weights },
    dte: { min: activePreset.dte?.min || 14, max: activePreset.dte?.max || 60 },
    strikes: { range_pct: activePreset.strikes?.range_pct || 10, min_open_interest: 50, min_volume: 5 },
    spreads: { min_width: activePreset.spreads?.min_width || 1, max_width: activePreset.spreads?.max_width || 10 },
    risk: { max_risk_per_trade: activePreset.risk?.max_risk || 500, profit_target_pct: 75, stop_loss_pct: 50 },
    spreadTypes: { bull_call: true, bear_put: true },
    greeks: { min_short_delta: 0.15, max_short_delta: 0.45, min_net_delta: 0, max_net_theta: 0 },
    smaPeriods: { short: 8, mid: 21, long: 50 },
  });

  const configRef = useRef(config);
  configRef.current = config;

  // ─── SMA data (reads from config.smaPeriods) ─────────────────
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

    const spreadTypesArr = [];
    if (cfg.spreadTypes?.bull_call) spreadTypesArr.push('bull_call');
    if (cfg.spreadTypes?.bear_put) spreadTypesArr.push('bear_put');
    if (spreadTypesArr.length === 0) spreadTypesArr.push('bull_call', 'bear_put');

    try {
      const data = await analyzeVerticals({
        symbol,
        spread_types: spreadTypesArr,
        max_results: 20,
        ev_weight: cfg.weights.expected_value,
        rr_weight: cfg.weights.reward_risk,
        prob_weight: cfg.weights.probability,
        liq_weight: cfg.weights.liquidity,
        theta_weight: cfg.weights.theta_efficiency,
        min_dte: cfg.dte.min,
        max_dte: cfg.dte.max,
        strike_range_pct: cfg.strikes.range_pct,
      });
      setSpreads(data.spreads || []);
      setUnderlyingPrice(data.underlying_price || 0);
      setTotalValid(data.total_valid || 0);
      if (data.underlying_price) setCandles(generateCandles(data.underlying_price));
    } catch (err) {
      setError(err.message || 'Failed to fetch analysis');
      setSpreads([]);
    } finally {
      setLoading(false);
    }
  }, []);

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

  const sortedSpreads = useMemo(() => {
    if (!sort.key) return spreads;
    return [...spreads].sort((a, b) => {
      let av = a[sort.key]; let bv = b[sort.key];
      if (typeof av === 'string') return sort.dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      return sort.dir === 'asc' ? av - bv : bv - av;
    });
  }, [spreads, sort]);

  // ─── Trade builders ──────────────────────────────────────────
  function buildClaudeTrade(s) {
    return { symbol: activeSymbol, spread_type: s.spread_type, long_strike: s.long_strike, short_strike: s.short_strike, expiration: s.expiration, option_type: s.spread_type === 'bull_call' ? 'call' : 'put', net_debit: s.net_debit, max_profit: s.max_profit, max_loss: s.net_debit, reward_risk_ratio: s.reward_risk_ratio, prob_of_profit: s.prob_of_profit, composite_score: s.composite_score };
  }

  function buildAgentTrade(s) {
    const dte = Math.max(0, Math.round((new Date(s.expiration) - new Date()) / 86400000));
    return {
      trade_id: `${activeSymbol}-${s.long_strike}-${s.short_strike}-${s.expiration}`,
      symbol: activeSymbol,
      spread_type: s.spread_type,
      spread_label: `${s.long_strike}/${s.short_strike} ${s.spread_type === 'bull_call' ? 'Call' : 'Put'} Spread`,
      expiration: s.expiration,
      dte,
      net_debit: s.net_debit,
      max_profit: s.max_profit,
      reward_risk_ratio: s.reward_risk_ratio,
      prob_of_profit: s.prob_of_profit,
      composite_score: s.composite_score,
      direction: s.spread_type === 'bull_call' ? 'bullish' : 'bearish',
    };
  }

  function getMarketContext() {
    return {
      symbol: activeSymbol,
      underlying_price: smaData.price || underlyingPrice,
      sma_8: smaData.smaShort,
      sma_21: smaData.smaMid,
      sma_50: smaData.smaLong,
      ma_alignment: alignment,
      vix: null,
    };
  }

  function buildFormulaTrade(s) {
    return { symbol: activeSymbol, spread_type: s.spread_type, long_strike: s.long_strike, short_strike: s.short_strike, expiration: s.expiration, net_debit: s.net_debit, max_profit: s.max_profit, reward_risk_ratio: s.reward_risk_ratio, prob_of_profit: s.prob_of_profit, composite_score: s.composite_score, long_volume: s.long_volume || 0, short_volume: s.short_volume || 0, long_oi: s.long_oi || 0, short_oi: s.short_oi || 0, net_theta: s.net_theta || 0 };
  }

  function buildFavTrade(spread) {
    const typeLabel = spread.spread_type === 'bull_call' ? 'Bull Call' : 'Bear Put';
    const strikes = `${spread.long_strike}/${spread.short_strike}`;
    return { id: `vs-${activeSymbol}-${spread.spread_type}-${strikes}-${spread.expiration}`, symbol: activeSymbol, label: `${typeLabel} ${strikes}`, expiration: spread.expiration, source: 'vertical', score: spread.composite_score, originalPrice: `Debit: ${spread.net_debit.toFixed(2)}`, originalDebit: spread.net_debit, maxProfit: spread.max_profit, rewardRisk: spread.reward_risk_ratio, probOfProfit: spread.prob_of_profit };
  }

  // ─── Config handlers ─────────────────────────────────────────
  const handlePresetSelect = (id) => {
    setActivePresetId(id);
    const preset = presets.find(p => p.id === id);
    if (preset) {
      setConfig(prev => ({
        ...prev,
        weights: { ...preset.weights },
        dte: { min: preset.dte?.min || 14, max: preset.dte?.max || 60 },
        strikes: { range_pct: preset.strikes?.range_pct || 10, min_open_interest: 50, min_volume: 5 },
        spreads: { min_width: preset.spreads?.min_width || 1, max_width: preset.spreads?.max_width || 10 },
      }));
    }
  };

  const handleConfigApply = useCallback((newConfig) => {
    setConfig(newConfig);
    setConfigOpen(false);
    configRef.current = newConfig;
    runAnalysis(activeSymbol);
  }, [activeSymbol, runAnalysis, setConfigOpen]);

  // ─── Render ──────────────────────────────────────────────────
  return (
    <div className="page-card">
      <QuoteBar title="Vertical Spread Analysis" />

      {candles.length > 0 && !loading && (
        <SmaPanel candles={candles} smaPeriods={smaPeriods} onPeriodsChange={(p) => setConfig(prev => ({ ...prev, smaPeriods: p }))} symbol={activeSymbol} />
      )}

      {!loading && !error && spreads.length > 0 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <p className="page-subtitle" style={{ margin: 0 }}>
            Showing top {spreads.length} of {totalValid} valid spreads, ranked by composite score.
          </p>
          <button onClick={() => setConfigOpen(true)}
            style={{ padding: '5px 12px', borderRadius: 6, border: `1px solid ${C.border}`, backgroundColor: 'transparent', color: C.textDim, fontSize: 12, cursor: 'pointer' }}>
            ⚙ Config
          </button>
        </div>
      )}

      {loading && (
        <div className="loading-state"><div className="spinner" /><span>Analyzing {activeSymbol} options chain…</span></div>
      )}

      {error && (
        <div className="error-state">
          <span className="error-icon">⚠</span><span>{error}</span>
          <button className="retry-btn" onClick={() => runAnalysis(activeSymbol)}>Retry</button>
        </div>
      )}

      {!loading && !error && sortedSpreads.length > 0 && (
        <div className="table-wrap">
          {selectedIds.size > 0 && (
            <div style={{ padding: '6px 0 8px', display: 'flex', alignItems: 'center', gap: 10 }}>
              <button
                onClick={() => openAgent(
                  sortedSpreads.filter(s => selectedIds.has(`${s.long_strike}-${s.short_strike}-${s.expiration}`)).map(buildAgentTrade),
                  getMarketContext()
                )}
                style={{
                  padding: '6px 14px', borderRadius: 6, fontSize: 12.5, fontWeight: 700,
                  cursor: 'pointer', border: `1px solid ${C.claudeBorder}`,
                  backgroundColor: C.claudeDim, color: C.claudeAccent,
                }}>
                ✦ Ask Claude ({selectedIds.size})
              </button>
              <button onClick={() => setSelectedIds(new Set())}
                style={{ background: 'none', border: 'none', color: C.textDim, fontSize: 11, cursor: 'pointer' }}>
                Clear
              </button>
            </div>
          )}
          <table>
            <thead>
              <tr>
                <th style={{ width: 28 }}></th>
                <th style={{ width: 32 }}></th>
                <SortTh label="Type" sortKey="spread_type" currentSort={sort} onSort={handleSort} />
                <SortTh label="Long / Short" sortKey="long_strike" currentSort={sort} onSort={handleSort} style={{ textAlign: 'center' }} />
                <SortTh label="Exp" sortKey="expiration" currentSort={sort} onSort={handleSort} style={{ textAlign: 'center' }} />
                <th style={{ textAlign: 'right', cursor: 'default', whiteSpace: 'nowrap' }}>DTE</th>
                <SortTh label="Debit" sortKey="net_debit" currentSort={sort} onSort={handleSort} num />
                <SortTh label="Max Profit" sortKey="max_profit" currentSort={sort} onSort={handleSort} num />
                <SortTh label="R:R" sortKey="reward_risk_ratio" currentSort={sort} onSort={handleSort} num />
                <SortTh label="Breakeven" sortKey="breakeven" currentSort={sort} onSort={handleSort} num />
                <SortTh label="Prob %" sortKey="prob_of_profit" currentSort={sort} onSort={handleSort} num />
                <SortTh label="EV" sortKey="ev_raw" currentSort={sort} onSort={handleSort} num />
                <SortTh label="Score" sortKey="composite_score" currentSort={sort} onSort={handleSort} />
                <th style={{ width: 60 }}></th>
              </tr>
            </thead>
            <tbody>
              {sortedSpreads.map((s, i) => {
                const isBull = s.spread_type === 'bull_call';
                const rowId = `${s.long_strike}-${s.short_strike}-${s.expiration}`;
                const isChecked = selectedIds.has(rowId);
                return (
                  <tr key={i} style={{ borderLeft: `2px solid ${isChecked ? C.claudeAccent : 'transparent'}` }}>
                    <td>
                      <input type="checkbox" checked={isChecked}
                        onChange={() => setSelectedIds(prev => {
                          const next = new Set(prev);
                          if (next.has(rowId)) next.delete(rowId); else next.add(rowId);
                          return next;
                        })}
                        style={{ cursor: 'pointer', accentColor: C.claudeAccent }}
                      />
                    </td>
                    <td><StarButton trade={buildFavTrade(s)} /></td>
                    <td><span className={`type-badge ${isBull ? 'type-bull' : 'type-bear'}`}>{isBull ? 'Bull Call' : 'Bear Put'}</span></td>
                    <td className="mono" style={{ textAlign: 'center' }}>{s.long_strike} / {s.short_strike}</td>
                    <td className="mono text-muted" style={{ textAlign: 'center' }}>{s.expiration}</td>
                    <td className="mono">{Math.max(0, Math.round((new Date(s.expiration) - new Date()) / 86400000))}</td>
                    <td className="mono">{s.net_debit.toFixed(2)}</td>
                    <td className="mono text-green">{s.max_profit.toFixed(2)}</td>
                    <td className="mono">{s.reward_risk_ratio.toFixed(2)}</td>
                    <td className="mono">{s.breakeven.toFixed(2)}</td>
                    <td className="mono">{(s.prob_of_profit * 100).toFixed(0)}%</td>
                    <td className={`mono ${s.ev_raw >= 0 ? 'text-green' : 'text-red'}`}>{s.ev_raw.toFixed(2)}</td>
                    <td><ScoreBar score={s.composite_score} /></td>
                    <td>
                      <div style={{ display: 'flex', gap: 3, alignItems: 'center' }}>
                        <button onClick={(e) => { e.stopPropagation(); openAgent([buildAgentTrade(s)], getMarketContext()); }}
                          title="Ask Claude" style={{ padding: '3px 7px', borderRadius: 4, border: `1px solid ${C.claudeBorder}`, backgroundColor: C.claudeDim, color: C.claudeAccent, fontSize: 12, fontWeight: 700, cursor: 'pointer', lineHeight: 1 }}>✦</button>
                        <button onClick={(e) => { e.stopPropagation(); setFormulaTrade(buildFormulaTrade(s)); setFormulaOpen(true); }}
                          title="View scoring formula" style={{ padding: '3px 7px', borderRadius: 4, border: `1px solid ${C.accent}30`, backgroundColor: `${C.accent}10`, color: C.accent, fontSize: 10, fontWeight: 600, cursor: 'pointer', fontFamily: mono, lineHeight: 1 }}>ƒx</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {!loading && !error && spreads.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">📊</div>
          <h3>No spreads found</h3>
          <p>No valid vertical spreads matched the current filters for {activeSymbol}. Try a different symbol or adjust the filter settings.</p>
        </div>
      )}

      <FormulaBreakdownPanel open={formulaOpen} onClose={() => setFormulaOpen(false)} trade={formulaTrade} symbol={activeSymbol} weights={config.weights} />

      <ConfigDrawer
        mode="verticals"
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
