/**
 * TradesPage — Trades screen (Screen 2 in UI-GUIDANCE.md v3.1).
 *
 * Routes: /trades, /trades?symbol=XXX, /trades?strategy=XXX
 *
 * Layout (top → bottom):
 *   1. Symbol search
 *   2. QuoteBar
 *   3. SMA chart (configurable moving averages)
 *   4. Collapsible sections: Vertical spreads · Puts & calls · Iron condors (soon)
 *      Each section fetches independently when expanded.
 *      Row click → inline Sections A-E trade detail expansion.
 */

import { useState, useMemo, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import SymbolSearch from '../components/SymbolSearch';
import QuoteBar from '../components/QuoteBar';
import SmaPanel, { computeSma } from '../components/SmaPanel';
import ResultsTable from '../components/ResultsTable';
import { SectionA, SectionB, SectionC, SectionE } from '../components/TradeDetail';
import { verticalsColumns } from '../config/verticals-columns';
import { longOptionsColumns } from '../config/long-options-columns';
import { analyzeVerticals, analyzeLongCalls, searchSymbolsStatic, searchInstruments, getQuote, evaluateStructured, followTrade, takeTrade, evaluateFollowUp } from '../api/client';
import { useToast } from '../components/Toast';
import { STRATEGY_CONFIGS, SCORECARD_STRATEGIES } from '../strategy-configs/index';

const MUTED  = '#8b949e';
const TEXT   = '#e6edf3';
const BORDER = '#30363d';

const ABBR_TO_KEY = {
  SP: 'steady-paycheck',
  WG: 'weekly-grind',
  TR: 'trend-rider',
  LT: 'lottery-ticket',
};

// Strategy keys shown in each section's Config drawer — derived from registry
const VERT_STRATEGY_KEYS  = SCORECARD_STRATEGIES.filter(cfg => cfg.trade_structure === 'credit_spread').map(cfg => cfg.key);
const CALLS_STRATEGY_KEYS = SCORECARD_STRATEGIES.filter(cfg => cfg.trade_structure === 'long_option').map(cfg => cfg.key);

// ─── Normal CDF (Abramowitz & Stegun approximation, max error 1.5×10⁻⁷) ──────
function normCdf(z) {
  const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741;
  const a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
  const sign = z < 0 ? -1 : 1;
  const x = Math.abs(z) / Math.SQRT2;
  const t = 1 / (1 + p * x);
  const erf = 1 - t * (a1 + t * (a2 + t * (a3 + t * (a4 + t * a5)))) * Math.exp(-x * x);
  return (1 + sign * erf) / 2;
}

// ─── Synthetic candlestick generator (same approach as DirectionalPage) ───────
function generateCandles(price, count = 120) {
  const candles = [];
  let p = price * 0.95;
  for (let i = 0; i < count; i++) {
    const change = (Math.random() - 0.48) * price * 0.012;
    const open = p, close = p + change;
    const high = Math.max(open, close) + Math.random() * price * 0.005;
    const low = Math.min(open, close) - Math.random() * price * 0.005;
    candles.push({ open, high, low, close, day: `d${i}` });
    p = close;
  }
  const scale = price / candles[candles.length - 1].close;
  return candles.map(c => ({
    open: c.open * scale, high: c.high * scale,
    low: c.low * scale, close: c.close * scale, day: c.day,
  }));
}

// ─── Strategy pill inference (stopgap until Phase 2.9 scoring is wired) ───────
function inferStrategies(spreadType, dte) {
  if (!spreadType) return [];
  const type = spreadType.toLowerCase();
  const isCredit = type.includes('credit');
  if (isCredit) {
    if (dte == null) return ['SP'];
    if (dte >= 5 && dte < 25) return ['WG'];
    return ['SP'];
  }
  // Debit spreads — directional
  if (dte != null && dte < 21) return ['LT'];
  return ['TR'];
}

// Config-driven: returns strategy keys where trade_structure === 'long_option'
// and DTE falls within the strategy's DTE window.
function inferLongOptionStrategies(optionType, dte) {
  return SCORECARD_STRATEGIES
    .filter(cfg => cfg.trade_structure === 'long_option')
    .filter(cfg => dte != null ? (dte >= cfg.dte_min && dte <= cfg.dte_max) : true)
    .map(cfg => cfg.key);
}

// ─── Exit scenario builder for vertical spreads ──────────────────────────────
function buildExitScenarios(spread, underlying) {
  const { long_strike, short_strike, net_debit, iv, expiration } = spread;
  if (!long_strike || !short_strike || net_debit == null || !underlying) {
    return { scenarios: [], totalEV: null };
  }

  const loStrike = Math.min(long_strike, short_strike);
  const hiStrike = Math.max(long_strike, short_strike);
  const width = hiStrike - loStrike;
  const spreadType = (spread.spread_type || '').toLowerCase().replace(/-/g, '_');
  const isCallSpread = ['bull_call', 'bear_call'].includes(spreadType);
  const isDebit = net_debit > 0;
  const creditAmt = Math.abs(net_debit);

  const dte = expiration
    ? Math.max(1, Math.round((new Date(expiration) - new Date()) / 86400000))
    : 30;
  const sigma = Math.max(1, (iv || 0.25) * underlying * Math.sqrt(dte / 365));

  function spreadValueAt(price) {
    if (isCallSpread) return Math.max(0, Math.min(price - loStrike, width));
    return Math.max(0, Math.min(hiStrike - price, width));
  }

  function pnlAt(price) {
    const sv = spreadValueAt(price);
    return isDebit ? (sv - net_debit) * 100 : (creditAmt - sv) * 100;
  }

  const maxPnl    = isDebit ? (width - net_debit) * 100 : creditAmt * 100;
  const maxLossAmt = isDebit ? net_debit * 100 : (width - creditAmt) * 100;
  const risk = isDebit ? net_debit * 100 : (width - creditAmt) * 100;

  const rangeStart = Math.max(1, Math.floor((Math.min(underlying - 3 * sigma, loStrike - width)) / 5) * 5);
  const rangeEnd   = Math.ceil((Math.max(underlying + 3 * sigma, hiStrike + width)) / 5) * 5;

  const scenarios = [];
  let totalEV = 0;

  for (let price = rangeStart; price <= rangeEnd; price += 5) {
    const zLo = (price - 2.5 - underlying) / sigma;
    const zHi = (price + 2.5 - underlying) / sigma;
    const probability = (normCdf(zHi) - normCdf(zLo)) * 100;
    const pnl = pnlAt(price);
    const pnlPct = risk > 0 ? (pnl / risk) * 100 : 0;
    const ev = pnl * probability / 100;
    totalEV += ev;
    scenarios.push({
      price,
      spreadValue: spreadValueAt(price),
      pnl,
      pnlPct,
      probability,
      expectedValue: ev,
      exitSignal: null,
    });
  }

  // ── Tag 5 key rows: STOP · MONITOR LOSS · BREAK EVEN · MONITOR PROFIT · MAX PROFIT
  if (scenarios.length >= 3) {
    // Returns index of nearest untagged row by score function (lower score = better match)
    const findIdx = (scoreFn) => {
      let bi = -1, bestScore = Infinity;
      for (let i = 0; i < scenarios.length; i++) {
        if (scenarios[i].exitSignal) continue;
        const s = scoreFn(scenarios[i]);
        if (s < bestScore) { bestScore = s; bi = i; }
      }
      return bi;
    };

    const stopIdx = findIdx(r => Math.abs(r.pnl + maxLossAmt));
    if (stopIdx >= 0) scenarios[stopIdx].exitSignal = 'STOP';

    const mpIdx = findIdx(r => Math.abs(r.pnl - maxPnl));
    if (mpIdx >= 0) scenarios[mpIdx].exitSignal = 'MAX PROFIT';

    const beIdx = findIdx(r => Math.abs(r.pnl));
    if (beIdx >= 0) scenarios[beIdx].exitSignal = 'BREAK EVEN';

    const stopPrice = stopIdx >= 0 ? scenarios[stopIdx].price : rangeStart;
    const bePrice   = beIdx   >= 0 ? scenarios[beIdx].price   : underlying;
    const mpPrice   = mpIdx   >= 0 ? scenarios[mpIdx].price   : rangeEnd;

    const mlPrice  = Math.round(((stopPrice + bePrice) / 2) / 5) * 5;
    const mmpPrice = Math.round(((bePrice   + mpPrice) / 2) / 5) * 5;

    const mlIdx = findIdx(r => Math.abs(r.price - mlPrice));
    if (mlIdx >= 0) scenarios[mlIdx].exitSignal = 'MONITOR LOSS';

    const mmpIdx = findIdx(r => Math.abs(r.price - mmpPrice));
    if (mmpIdx >= 0) scenarios[mmpIdx].exitSignal = 'MONITOR PROFIT';
  }

  return { scenarios, totalEV };
}

// ─── Outcome summary builder for Section C ────────────────────────────────────
function buildOutcome(spread, underlying, totalEV) {
  const { long_strike, short_strike, net_debit, iv, expiration } = spread;
  if (!long_strike || !short_strike || net_debit == null || !underlying) return null;

  const loStrike = Math.min(long_strike, short_strike);
  const hiStrike = Math.max(long_strike, short_strike);
  const width = hiStrike - loStrike;
  const isBull = (spread.spread_type || '').startsWith('bull');
  const isDebit = net_debit > 0;
  const creditAmt = Math.abs(net_debit);

  const dte = expiration
    ? Math.max(1, Math.round((new Date(expiration) - new Date()) / 86400000))
    : 30;
  const sigma = Math.max(1, (iv || 0.25) * underlying * Math.sqrt(dte / 365));

  const breakeven = isBull
    ? (isDebit ? loStrike + net_debit : hiStrike - creditAmt)
    : (isDebit ? hiStrike - net_debit : loStrike + creditAmt);

  // For bull spreads: profit if price above breakeven; max profit if above hiStrike
  // For bear spreads: profit if price below breakeven; max profit if below loStrike
  function pAbove(price) { return (1 - normCdf((price - underlying) / sigma)) * 100; }
  function pBelow(price) { return normCdf((price - underlying) / sigma) * 100; }

  const pMaxProfit = isBull ? pAbove(hiStrike) : pBelow(loStrike);
  const pBreakeven = isBull ? pAbove(breakeven) : pBelow(breakeven);
  const pMaxLoss   = isBull ? pBelow(loStrike)  : pAbove(hiStrike);
  const pPartial   = Math.max(0, pBreakeven - pMaxProfit);
  const maxRisk    = isDebit ? net_debit * 100 : (width - creditAmt) * 100;
  const evPctRisk  = maxRisk > 0 ? (totalEV / maxRisk) * 100 : 0;

  return { pMaxProfit, pBreakeven, pPartial, pMaxLoss, expectedValue: totalEV, evPctRisk };
}

// ─── Exit scenario builder — long options (OTA-385) ──────────────────────────
// P&L for calls: (price - strike - premium) * 100
// P&L for puts:  (strike - price - premium) * 100
function buildLongOptionExitScenarios(option, underlying) {
  const { strike, mid_price: premium, iv, expiration, option_type: optType } = option;
  if (!strike || premium == null || !underlying) return { scenarios: [], totalEV: null };

  const isCall  = optType === 'call';
  const dte     = expiration
    ? Math.max(1, Math.round((new Date(expiration) - new Date()) / 86400000))
    : 30;
  const sigma   = Math.max(1, (iv || 0.25) * underlying * Math.sqrt(dte / 365));
  const maxLoss = premium * 100;
  const breakeven = isCall ? strike + premium : strike - premium;

  function intrinsicAt(price) {
    return isCall ? Math.max(0, price - strike) : Math.max(0, strike - price);
  }

  function pnlAt(price) {
    return (intrinsicAt(price) - premium) * 100;
  }

  const rangeStart = Math.max(1, Math.floor((underlying - 3 * sigma) / 5) * 5);
  const rangeEnd   = Math.ceil((underlying + 3 * sigma) / 5) * 5;

  const scenarios = [];
  let totalEV = 0;

  for (let price = rangeStart; price <= rangeEnd; price += 5) {
    const zLo = (price - 2.5 - underlying) / sigma;
    const zHi = (price + 2.5 - underlying) / sigma;
    const probability = (normCdf(zHi) - normCdf(zLo)) * 100;
    const pnl = pnlAt(price);
    const pnlPct = maxLoss > 0 ? (pnl / maxLoss) * 100 : 0;
    const ev = pnl * probability / 100;
    totalEV += ev;
    scenarios.push({
      price,
      spreadValue: intrinsicAt(price),
      pnl,
      pnlPct,
      probability,
      expectedValue: ev,
      exitSignal: null,
    });
  }

  // ── Tag 5 key rows: STOP · MONITOR LOSS · BREAK EVEN · MONITOR PROFIT · MAX PROFIT
  if (scenarios.length >= 3) {
    const findIdx = (scoreFn) => {
      let bi = -1, bestScore = Infinity;
      for (let i = 0; i < scenarios.length; i++) {
        if (scenarios[i].exitSignal) continue;
        const s = scoreFn(scenarios[i]);
        if (s < bestScore) { bestScore = s; bi = i; }
      }
      return bi;
    };

    const stopIdx = findIdx(r => Math.abs(r.pnl + maxLoss));
    if (stopIdx >= 0) scenarios[stopIdx].exitSignal = 'STOP';

    const mpIdx = findIdx(r => -r.pnl);  // maximize pnl (unbounded for long options)
    if (mpIdx >= 0) scenarios[mpIdx].exitSignal = 'MAX PROFIT';

    const beIdx = findIdx(r => Math.abs(r.pnl));
    if (beIdx >= 0) scenarios[beIdx].exitSignal = 'BREAK EVEN';

    const stopPrice = stopIdx >= 0 ? scenarios[stopIdx].price : rangeStart;
    const bePrice   = beIdx   >= 0 ? scenarios[beIdx].price   : breakeven;
    const mpPrice   = mpIdx   >= 0 ? scenarios[mpIdx].price   : rangeEnd;

    const mlPrice  = Math.round(((stopPrice + bePrice) / 2) / 5) * 5;
    const mmpPrice = Math.round(((bePrice   + mpPrice) / 2) / 5) * 5;

    const mlIdx = findIdx(r => Math.abs(r.price - mlPrice));
    if (mlIdx >= 0) scenarios[mlIdx].exitSignal = 'MONITOR LOSS';

    const mmpIdx = findIdx(r => Math.abs(r.price - mmpPrice));
    if (mmpIdx >= 0) scenarios[mmpIdx].exitSignal = 'MONITOR PROFIT';
  }

  return { scenarios, totalEV };
}

// ─── Map ScoredSpread → SectionA trade object ────────────────────────────────
function mapSpreadToDetail(spread) {
  const spreadWidth = spread.long_strike != null && spread.short_strike != null
    ? Math.abs(spread.long_strike - spread.short_strike)
    : null;
  const debit = spread.net_debit;
  const isDebit = debit != null && debit > 0;
  const absDebit = debit != null ? Math.abs(debit) : null;
  const isBull = (spread.spread_type || '').startsWith('bull');
  const maxProfit = spreadWidth != null && absDebit != null
    ? (isDebit ? spreadWidth - absDebit : absDebit) * 100
    : null;
  const maxLoss = spreadWidth != null && absDebit != null
    ? (isDebit ? absDebit : spreadWidth - absDebit) * 100
    : null;
  const loStrike = spread.long_strike != null && spread.short_strike != null
    ? Math.min(spread.long_strike, spread.short_strike)
    : null;
  const hiStrike = spread.long_strike != null && spread.short_strike != null
    ? Math.max(spread.long_strike, spread.short_strike)
    : null;
  const breakeven = absDebit != null && loStrike != null
    ? (isBull
      ? (isDebit ? loStrike + absDebit : hiStrike - absDebit)
      : (isDebit ? hiStrike - absDebit : loStrike + absDebit))
    : null;
  const dte = spread.expiration
    ? Math.max(0, Math.round((new Date(spread.expiration) - new Date()) / 86400000))
    : null;
  return {
    type: spread.spread_type,
    strikes: spread.long_strike != null && spread.short_strike != null
      ? `${spread.long_strike}/${spread.short_strike}`
      : '—',
    expiry: spread.expiration,
    dte,
    entry: debit,
    maxProfit,
    maxLoss,
    breakeven,
    rewardRisk: spread.reward_risk_ratio,
    profitTrigger: null,
    stopTrigger: null,
    timeExit: null,
  };
}

// ─── Map ScoredNakedOption → SectionA trade object ───────────────────────────
function mapCallToDetail(call) {
  const dte = call.expiration
    ? Math.max(0, Math.round((new Date(call.expiration) - new Date()) / 86400000))
    : null;
  return {
    type: call.option_type === 'call' ? 'LONG_CALL' : 'LONG_PUT',
    strikes: call.strike != null ? String(Math.round(call.strike)) : '—',
    expiry: call.expiration,
    dte,
    entry: call.mid_price,
    maxProfit: null,
    maxLoss: call.mid_price != null ? call.mid_price * 100 : null,
    breakeven: call.breakeven,
    rewardRisk: null,
    profitTrigger: null,
    stopTrigger: null,
    timeExit: null,
  };
}

// ─── Collapsible section header ───────────────────────────────────────────────
function SectionHeader({ title, count, expanded, onToggle, showConfig, onConfig, comingSoon }) {
  return (
    <div
      onClick={comingSoon ? undefined : onToggle}
      style={{
        display: 'flex', alignItems: 'center',
        padding: '10px 0',
        cursor: comingSoon ? 'default' : 'pointer',
        borderBottom: `1px solid ${BORDER}`,
        gap: 8,
        opacity: comingSoon ? 0.5 : 1,
        userSelect: 'none',
      }}
    >
      <span style={{ fontSize: 9, color: MUTED, width: 14, flexShrink: 0 }}>
        {comingSoon ? '▶' : expanded ? '▼' : '▶'}
      </span>
      <span style={{ fontSize: 12, fontWeight: 700, color: TEXT, fontFamily: 'monospace' }}>
        {title}
      </span>
      <span style={{ fontSize: 10, color: MUTED, fontFamily: 'monospace', fontStyle: comingSoon ? 'italic' : 'normal' }}>
        {count}
      </span>
      {showConfig && !comingSoon && (
        <button
          onClick={e => { e.stopPropagation(); if (onConfig) onConfig(); }}
          style={{
            marginLeft: 'auto',
            background: 'transparent',
            border: `1px solid ${BORDER}`,
            color: MUTED,
            padding: '4px 10px',
            borderRadius: 4,
            fontSize: 10,
            fontFamily: 'monospace',
            cursor: 'pointer',
          }}
        >
          ⚙ Config
        </button>
      )}
    </div>
  );
}

// ─── Section Config Drawer (OTA-387) ─────────────────────────────────────────
// Slide-out config panel for a section. Shows strategy tabs when multiple
// strategy keys are provided. Apply saves to localStorage per strategy.
function SectionConfigDrawer({ open, onClose, strategyKeys = [], onApply }) {
  const [activeKey, setActiveKey] = useState(strategyKeys[0] || null);

  const keysStr = strategyKeys.join(',');
  useEffect(() => {
    if (strategyKeys.length && !strategyKeys.includes(activeKey)) {
      setActiveKey(strategyKeys[0]); // eslint-disable-line react-hooks/set-state-in-effect
    }
  }, [keysStr]); // eslint-disable-line react-hooks/exhaustive-deps

  const cfg    = activeKey ? STRATEGY_CONFIGS[activeKey] : null;
  const schema = cfg?.configSchema || [];

  function loadDraft(key) {
    if (!key || !STRATEGY_CONFIGS[key]?.configSchema) return {};
    try {
      const stored = JSON.parse(localStorage.getItem('analysisConfig') || '{}');
      const saved  = stored.strategyOverrides?.[key] || {};
      const result = {};
      for (const field of STRATEGY_CONFIGS[key].configSchema) {
        result[field.key] = field.key in saved ? saved[field.key] : field.default;
      }
      return result;
    } catch {
      const result = {};
      for (const field of STRATEGY_CONFIGS[key]?.configSchema || []) {
        result[field.key] = field.default;
      }
      return result;
    }
  }

  const [draft, setDraft] = useState(() => loadDraft(strategyKeys[0]));

  useEffect(() => { if (open && activeKey) setDraft(loadDraft(activeKey)); }, [open, activeKey]); // eslint-disable-line react-hooks/set-state-in-effect

  function handleApply() {
    try {
      const stored    = JSON.parse(localStorage.getItem('analysisConfig') || '{}');
      const overrides = stored.strategyOverrides || {};
      overrides[activeKey] = draft;
      localStorage.setItem('analysisConfig', JSON.stringify({ ...stored, strategyOverrides: overrides }));
    } catch { /* ignore storage errors */ }
    if (onApply) onApply(activeKey, draft);
    onClose();
  }

  function handleReset() {
    const result = {};
    for (const field of schema) result[field.key] = field.default;
    setDraft(result);
  }

  return (
    <>
      {open && (
        <div
          onClick={onClose}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 90 }}
        />
      )}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 380,
        background: '#161b22', borderLeft: `1px solid ${BORDER}`,
        zIndex: 100,
        transform: open ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform 0.25s cubic-bezier(0.4,0,0.2,1)',
        display: 'flex', flexDirection: 'column',
        boxShadow: open ? '-8px 0 30px rgba(0,0,0,0.4)' : 'none',
        fontFamily: 'monospace',
      }}>
        {/* Header */}
        <div style={{
          padding: '14px 18px', borderBottom: `1px solid ${BORDER}`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          flexShrink: 0,
        }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: TEXT }}>Configuration</div>
            <div style={{ fontSize: 11, color: MUTED, marginTop: 2 }}>
              {cfg?.label ? `${cfg.label} Parameters` : 'Strategy Parameters'}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: MUTED, fontSize: 20, cursor: 'pointer', padding: 4 }}
          >
            &times;
          </button>
        </div>

        {/* Strategy tabs — only shown when multiple strategies apply */}
        {strategyKeys.length > 1 && (
          <div style={{
            display: 'flex', gap: 6, padding: '10px 18px',
            borderBottom: `1px solid ${BORDER}`, flexShrink: 0,
          }}>
            {strategyKeys.map(key => {
              const s = STRATEGY_CONFIGS[key];
              if (!s) return null;
              const isActive = key === activeKey;
              return (
                <button
                  key={key}
                  onClick={() => setActiveKey(key)}
                  style={{
                    padding: '4px 12px', borderRadius: 4,
                    border: `1px solid ${isActive ? 'rgba(45,212,191,0.4)' : BORDER}`,
                    background: isActive ? 'rgba(45,212,191,0.1)' : 'transparent',
                    color: isActive ? '#2dd4bf' : MUTED,
                    fontSize: 11, cursor: 'pointer', fontFamily: 'monospace',
                  }}
                >
                  {s.label}
                </button>
              );
            })}
          </div>
        )}

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '14px 18px' }}>
          {cfg && (
            <div style={{
              marginBottom: 16, padding: '10px 14px', borderRadius: 6,
              background: '#21262d', border: `1px solid ${BORDER}`,
            }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#2dd4bf', marginBottom: 2 }}>
                {cfg.label}
              </div>
              <div style={{ fontSize: 11, color: MUTED, lineHeight: 1.4 }}>{cfg.description}</div>
            </div>
          )}

          {schema.map(field => {
            const value  = draft[field.key] ?? field.default;
            const update = (v) => setDraft(prev => ({ ...prev, [field.key]: v }));
            const unit   = field.unit || '';

            if (field.type === 'slider') {
              return (
                <div key={field.key} style={{ marginBottom: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                    <span style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.4px', color: MUTED }}>
                      {field.label}
                    </span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: TEXT }}>
                      {unit === '\u0394' ? value.toFixed(2) : `${value}${unit}`}
                    </span>
                  </div>
                  <input
                    type="range"
                    min={field.min} max={field.max} step={field.step || 1} value={value}
                    onChange={e => update(parseFloat(e.target.value))}
                    style={{ width: '100%', cursor: 'pointer' }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
                    <span style={{ fontSize: 9, color: MUTED }}>{field.min}{unit}</span>
                    <span style={{ fontSize: 9, color: MUTED }}>{field.max}{unit}</span>
                  </div>
                </div>
              );
            }

            if (field.type === 'number') {
              return (
                <div key={field.key} style={{ marginBottom: 16 }}>
                  <label style={{
                    display: 'block', fontSize: 10,
                    textTransform: 'uppercase', letterSpacing: '0.4px',
                    color: MUTED, marginBottom: 5,
                  }}>
                    {field.label}
                  </label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <input
                      type="number"
                      value={value} min={field.min} max={field.max} step={field.step || 1}
                      onChange={e => {
                        let v = parseFloat(e.target.value);
                        if (!isNaN(v)) {
                          if (field.min != null) v = Math.max(field.min, v);
                          if (field.max != null) v = Math.min(field.max, v);
                          update(v);
                        }
                      }}
                      style={{
                        width: 80, padding: '5px 8px', borderRadius: 4,
                        border: `1px solid ${BORDER}`, background: '#0d1117',
                        color: TEXT, fontSize: 12, fontFamily: 'monospace',
                        outline: 'none', textAlign: 'right',
                      }}
                    />
                    {unit && <span style={{ fontSize: 11, color: MUTED }}>{unit}</span>}
                  </div>
                </div>
              );
            }

            if (field.type === 'toggle') {
              return (
                <div key={field.key} style={{
                  marginBottom: 16, display: 'flex', alignItems: 'center',
                  justifyContent: 'space-between',
                }}>
                  <span style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.4px', color: MUTED }}>
                    {field.label}
                  </span>
                  <button
                    onClick={() => update(value ? 0 : 1)}
                    style={{
                      padding: '4px 12px', borderRadius: 4, fontSize: 11, cursor: 'pointer',
                      border: `1px solid ${value ? 'rgba(45,212,191,0.4)' : BORDER}`,
                      background: value ? 'rgba(45,212,191,0.1)' : 'transparent',
                      color: value ? '#2dd4bf' : MUTED,
                      fontFamily: 'monospace',
                    }}
                  >
                    {value ? 'On' : 'Off'}
                  </button>
                </div>
              );
            }

            return null;
          })}
        </div>

        {/* Footer */}
        <div style={{
          padding: '12px 18px', borderTop: `1px solid ${BORDER}`,
          display: 'flex', gap: 8, flexShrink: 0,
        }}>
          <button
            onClick={handleApply}
            style={{
              flex: 1, padding: '9px 0', borderRadius: 4, border: 'none',
              background: '#2dd4bf', color: '#0d1117',
              fontWeight: 700, fontSize: 12, cursor: 'pointer', fontFamily: 'monospace',
            }}
          >
            Apply
          </button>
          <button
            onClick={handleReset}
            style={{
              padding: '9px 14px', borderRadius: 4,
              border: `1px solid ${BORDER}`, background: 'transparent',
              color: MUTED, fontSize: 12, cursor: 'pointer', fontFamily: 'monospace',
            }}
          >
            Reset
          </button>
          <button
            onClick={onClose}
            style={{
              padding: '9px 14px', borderRadius: 4,
              border: `1px solid ${BORDER}`, background: 'transparent',
              color: MUTED, fontSize: 12, cursor: 'pointer', fontFamily: 'monospace',
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    </>
  );
}

// ─── Normalize evaluate API response to SectionE evaluation shape ────────────
function normalizeEvalResponse(result, fallbackStrategyKey) {
  const evals = result?.evaluations;
  const e = Array.isArray(evals) && evals.length > 0
    ? evals[0]
    : (result?.verdict ? result : null);
  if (!e) return null;
  return {
    verdict: e.verdict,
    bestStrategy: e.strategy || fallbackStrategyKey,
    analysis: e.claude_read,
    score: e.score ?? null,
    keyLevelPrice: e.key_level?.price ?? null,
    keyLevelExplanation: typeof e.key_level === 'string'
      ? e.key_level
      : (e.key_level?.explanation ?? null),
    autoPassReason: e.auto_pass_reason || null,
    _raw: e,
  };
}

// ─── Trade detail expansion panel ────────────────────────────────────────────
function TradeDetailExpansion({
  detailProps, rawTrade, symbol, underlying, tradeContext, evaluation,
  onEvaluate, onFollow, onTakePosition, onFollowUp, onDiscard,
  scenarios, totalEV, outcome,
}) {
  return (
    <div style={{
      borderTop: `2px solid rgba(45,212,191,0.35)`,
      padding: '16px 0',
      fontFamily: 'monospace',
    }}>
      <SectionA trade={detailProps} />
      <SectionB scenarios={scenarios || []} totalEV={totalEV ?? null} isSingleLeg={!!rawTrade?.option_type} />
      <SectionC outcome={outcome || null} />
      <SectionE
        evaluation={evaluation || null}
        tradeContext={tradeContext}
        canEvaluate={!!(underlying && underlying > 0)}
        onEvaluate={onEvaluate}
        onFollow={onFollow}
        onTakePosition={onTakePosition}
        onFollowUp={onFollowUp}
        onDiscard={onDiscard}
      />
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function TradesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { positionSymbols, addToWatchlist } = useApp();
  const { showToast } = useToast();

  const symbol        = searchParams.get('symbol')   || '';
  const strategyParam = searchParams.get('strategy') || '';

  // Derive initial section expansion from ?strategy= param
  const _stratCfg         = STRATEGY_CONFIGS[strategyParam];
  const _isLongOptStrat   = _stratCfg?.trade_structure === 'long_option';
  const _isCreditSpread   = _stratCfg?.trade_structure === 'credit_spread';

  // ── SMA chart state ──────────────────────────────────────────────────────
  const [smaPeriods, setSmaPeriods] = useState({ short: 8, mid: 21, long: 50 });
  const [candles, setCandles] = useState([]);

  // ── SMA alignment derived from chart candles ─────────────────────────────
  const smaAlignment = useMemo(() => {
    if (!candles.length) return { alignment: 'mixed', sma_8: 'N/A', sma_21: 'N/A', sma_50: 'N/A' };
    const sS = computeSma(candles, smaPeriods.short);
    const sM = computeSma(candles, smaPeriods.mid);
    const sL = computeSma(candles, smaPeriods.long);
    const lS = sS.filter(Boolean).pop() || 0;
    const lM = sM.filter(Boolean).pop() || 0;
    const lL = sL.filter(Boolean).pop() || 0;
    let alignment = 'mixed';
    if (lS > lM && lM > lL) alignment = 'bullish';
    else if (lS < lM && lM < lL) alignment = 'bearish';
    return {
      alignment,
      [`sma_${smaPeriods.short}`]: lS || 'N/A',
      [`sma_${smaPeriods.mid}`]:   lM || 'N/A',
      [`sma_${smaPeriods.long}`]:  lL || 'N/A',
    };
  }, [candles, smaPeriods]);

  // ── Vertical spreads state ───────────────────────────────────────────────
  // Default: expanded unless a long_option strategy is specified
  const [vertExpanded, setVertExpanded]     = useState(!_isLongOptStrat);
  const [vertSpreads, setVertSpreads]       = useState([]);
  const [vertLoading, setVertLoading]       = useState(false);
  const [vertError, setVertError]           = useState(null);
  const [vertUnderlying, setVertUnderlying] = useState(0);

  // ── Puts & calls state ───────────────────────────────────────────────────
  // Default: collapsed unless a long_option strategy is specified
  const [callsExpanded, setCallsExpanded]     = useState(_isLongOptStrat);
  const [callResults, setCallResults]         = useState([]);
  const [callsLoading, setCallsLoading]       = useState(false);
  const [callsError, setCallsError]           = useState(null);
  const [callsUnderlying, setCallsUnderlying] = useState(0);

  // ── Expansion state — one row expanded at a time across both sections ────
  const [expandedRowId, setExpandedRowId] = useState(null);
  const [evaluations, setEvaluations]     = useState({}); // rowId → evaluation object

  // ── Config drawer state ──────────────────────────────────────────────────
  const [vertConfigOpen, setVertConfigOpen]   = useState(false);
  const [callsConfigOpen, setCallsConfigOpen] = useState(false);

  function handleVertConfigApply(_strategyKey, config) {
    if (symbol) fetchVerticals(symbol, config);
  }

  function handleCallsConfigApply(_strategyKey, config) {
    if (symbol) fetchCalls(symbol, config);
  }

  // ── Auto-fetch on mount when symbol is pre-set from URL ──────────────────
  // Handles /trades?symbol=X (from scan card click) and /trades?strategy=X
  useEffect(() => {
    if (!symbol) return;
    if (!_isLongOptStrat) fetchVerticals(symbol);
    if (_isLongOptStrat)  fetchCalls(symbol);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Fetch verticals ──────────────────────────────────────────────────────
  async function fetchVerticals(sym, config = {}) {
    if (!sym) return;
    setVertLoading(true);
    setVertError(null);
    try {
      const data = await analyzeVerticals({
        symbol: sym,
        spread_types: ['bull_call', 'bear_put'],
        max_results: 20,
        ...config,
      });
      const underlying = data.underlying_price || 0;
      setVertUnderlying(underlying);
      // Use underlying price to seed chart if quote fetch hasn't already
      if (underlying > 0) {
        setCandles(prev => prev.length ? prev : generateCandles(underlying));
      }
      // Inject stopgap strategy pills
      const spreads = (data.spreads || []).map(s => {
        const dte = s.expiration
          ? Math.max(0, Math.round((new Date(s.expiration) - new Date()) / 86400000))
          : null;
        return { ...s, strategies: s.strategies?.length ? s.strategies : inferStrategies(s.spread_type, dte) };
      });
      setVertSpreads(spreads);
    } catch (err) {
      setVertError(err.message || 'Failed to fetch vertical spreads');
      setVertSpreads([]);
    } finally {
      setVertLoading(false);
    }
  }

  // ── Fetch puts & calls ───────────────────────────────────────────────────
  async function fetchCalls(sym, config = {}) {
    if (!sym) return;
    setCallsLoading(true);
    setCallsError(null);
    try {
      const data = await analyzeLongCalls({
        symbol: sym,
        max_results: 20,
        option_types: ['call', 'put'],
        ...config,
      });
      const underlying = data.underlying_price || 0;
      setCallsUnderlying(underlying);
      if (underlying > 0) {
        setCandles(prev => prev.length ? prev : generateCandles(underlying));
      }
      const calls = (data.calls || []).map(c => {
        const dte = c.expiration
          ? Math.max(0, Math.round((new Date(c.expiration) - new Date()) / 86400000))
          : null;
        return { ...c, strategies: c.strategies?.length ? c.strategies : inferLongOptionStrategies(c.option_type, dte) };
      });
      setCallResults(calls);
    } catch (err) {
      setCallsError(err.message || 'Failed to fetch puts & calls');
      setCallResults([]);
    } finally {
      setCallsLoading(false);
    }
  }

  // ── Symbol select ────────────────────────────────────────────────────────
  async function handleSymbolSelect(sym) {
    addToWatchlist(sym);
    const next = new URLSearchParams(searchParams);
    next.set('symbol', sym);
    setSearchParams(next, { replace: true });
    setVertSpreads([]);
    setCallResults([]);
    setExpandedRowId(null);
    setEvaluations({});
    setCandles([]);
    // Fetch quote immediately to seed SMA chart
    try {
      const q = await getQuote(sym);
      const price = q?.last || q?.close || q?.price;
      if (price) setCandles(generateCandles(price));
    } catch { /* chart will fall back to underlying price when analysis returns */ }
    if (vertExpanded) fetchVerticals(sym);
    if (callsExpanded) fetchCalls(sym);
  }

  // ── Section toggle handlers ──────────────────────────────────────────────
  function handleVertToggle() {
    const willOpen = !vertExpanded;
    setVertExpanded(willOpen);
    setExpandedRowId(null);
    if (willOpen && symbol && vertSpreads.length === 0 && !vertLoading) {
      fetchVerticals(symbol);
    }
  }

  function handleCallsToggle() {
    const willOpen = !callsExpanded;
    setCallsExpanded(willOpen);
    setExpandedRowId(null);
    if (willOpen && symbol && callResults.length === 0 && !callsLoading) {
      fetchCalls(symbol);
    }
  }

  // ── Row expansion handlers ───────────────────────────────────────────────
  function handleRowClick(id) {
    setExpandedRowId(id === expandedRowId ? null : id);
  }

  // ── Pre-computed display arrays ──────────────────────────────────────────
  const callsDisplay = useMemo(() => {
    if (!callResults.length) return [];
    return callResults.map(trade => ({
      ...trade,
      vs_itm_dollars: trade.option_type === 'call'
        ? callsUnderlying - trade.strike
        : trade.strike - callsUnderlying,
    }));
  }, [callResults, callsUnderlying]);

  // ── Shared handler factory (closes over symbol, showToast, setEvaluations) ─
  function makeTradeHandlers(trade, rowId, underlying, { defaultStrategy, getEntryPrice, tradeLabel, smaAlign }) {
    const strategyKeys = (trade.strategies || []).map(a => ABBR_TO_KEY[a] || a);
    if (!strategyKeys.length) strategyKeys.push(defaultStrategy);

    async function handleEvaluate() {
      try {
        const result = await evaluateStructured({
          symbol,
          current_price: underlying,
          iv: trade.iv || trade.mid_iv || 0.25,
          sma_alignment: smaAlign || { sma_8: 'N/A', sma_21: 'N/A', sma_50: 'N/A', alignment: 'mixed' },
          strategy_keys: strategyKeys,
          trade,
        });
        const normalized = normalizeEvalResponse(result, strategyKeys[0]);
        if (normalized) setEvaluations(prev => ({ ...prev, [rowId]: normalized }));
      } catch (err) {
        showToast({ type: 'error', message: `Evaluation failed: ${err.message}` });
      }
    }

    async function handleFollow() {
      try {
        await followTrade({
          symbol,
          strategy_key: strategyKeys[0],
          source: 'PAPER',
          trade_structure: JSON.stringify(trade),
          entry_price: getEntryPrice(trade),
          entry_date: new Date().toISOString(),
        });
        showToast({ type: 'success', message: `Position followed (Paper) — ${symbol} ${tradeLabel(trade)}`, link: { text: 'View Positions', to: '/positions' }, duration: 4000 });
      } catch (err) {
        showToast({ type: 'error', message: `Follow failed: ${err.message}` });
      }
    }

    async function handleTakePosition() {
      try {
        await takeTrade({
          symbol,
          strategy_key: strategyKeys[0],
          source: 'LIVE',
          trade_structure: JSON.stringify(trade),
          entry_price: getEntryPrice(trade),
          entry_date: new Date().toISOString(),
        });
        showToast({ type: 'success', message: `Position taken (Live) — ${symbol} ${tradeLabel(trade)}`, link: { text: 'View Positions', to: '/positions' }, duration: 4000 });
      } catch (err) {
        showToast({ type: 'error', message: `Take position failed: ${err.message}` });
      }
    }

    async function handleFollowUp(question, evaluation) {
      return evaluateFollowUp({
        symbol,
        trade_data: trade,
        original_evaluation: evaluation?._raw || evaluation,
        question,
      });
    }

    return { handleEvaluate, handleFollow, handleTakePosition, handleFollowUp };
  }

  // ── Expansion row renderers ──────────────────────────────────────────────
  function renderVertExpansion(trade) {
    const rowId = `vert-${vertSpreads.indexOf(trade)}`;
    const detailProps = mapSpreadToDetail(trade);
    const ctx = `${symbol} · ${detailProps.strikes} · ${detailProps.type} · ${detailProps.expiry || ''}`;
    const { scenarios, totalEV } = buildExitScenarios(trade, vertUnderlying);
    const outcome = buildOutcome(trade, vertUnderlying, totalEV);
    const { handleEvaluate, handleFollow, handleTakePosition, handleFollowUp } = makeTradeHandlers(
      trade, rowId, vertUnderlying, {
        defaultStrategy: 'steady-paycheck',
        getEntryPrice: t => Math.abs(t.net_debit || 0),
        tradeLabel: t => `${t.long_strike}/${t.short_strike}`,
        smaAlign: smaAlignment,
      }
    );
    return (
      <TradeDetailExpansion
        detailProps={detailProps}
        rawTrade={trade}
        symbol={symbol}
        underlying={vertUnderlying}
        tradeContext={ctx}
        evaluation={evaluations[rowId] || null}
        onEvaluate={handleEvaluate}
        onFollow={handleFollow}
        onTakePosition={handleTakePosition}
        onFollowUp={handleFollowUp}
        onDiscard={() => setExpandedRowId(null)}
        scenarios={scenarios}
        totalEV={totalEV}
        outcome={outcome}
      />
    );
  }

  function renderCallExpansion(trade) {
    const rowId = `calls-${callResults.indexOf(trade)}`;
    const detailProps = mapCallToDetail(trade);
    const ctx = `${symbol} · ${trade.option_type} · ${trade.strike} · ${trade.expiration || ''}`;
    const { scenarios, totalEV } = buildLongOptionExitScenarios(trade, callsUnderlying);
    const { handleEvaluate, handleFollow, handleTakePosition, handleFollowUp } = makeTradeHandlers(
      trade, rowId, callsUnderlying, {
        defaultStrategy: 'trend-rider',
        getEntryPrice: t => t.mid_price || 0,
        tradeLabel: t => `${t.option_type} ${t.strike}`,
        smaAlign: smaAlignment,
      }
    );
    return (
      <TradeDetailExpansion
        detailProps={detailProps}
        rawTrade={trade}
        symbol={symbol}
        underlying={callsUnderlying}
        tradeContext={ctx}
        evaluation={evaluations[rowId] || null}
        onEvaluate={handleEvaluate}
        onFollow={handleFollow}
        onTakePosition={handleTakePosition}
        onFollowUp={handleFollowUp}
        onDiscard={() => setExpandedRowId(null)}
        scenarios={scenarios}
        totalEV={totalEV}
        outcome={null}
      />
    );
  }

  // ── Row ID helpers ───────────────────────────────────────────────────────
  const getVertRowId  = (_, idx) => `vert-${idx}`;
  const getCallRowId  = (_, idx) => `calls-${idx}`;

  // ── Table context ────────────────────────────────────────────────────────
  const vertContext  = { currentPrice: vertUnderlying };
  const callsContext = { currentPrice: callsUnderlying, thetaThreshold: 10 };

  // ── Section count display ────────────────────────────────────────────────
  function countText(loading, error, results) {
    if (loading) return '· loading…';
    if (error)   return '· error';
    if (results.length) return `· ${results.length} results`;
    return symbol ? '· no results' : '· enter a symbol above';
  }

  return (
    <>
      <div style={{ padding: '16px 20px', fontFamily: 'monospace' }}>

        {/* Symbol search */}
        <div style={{ marginBottom: 10 }}>
          <SymbolSearch
            onSelect={handleSymbolSelect}
            searchFn={searchInstruments}
            positionSymbols={positionSymbols}
            initialValue={symbol || null}
            placeholder="Search symbol…"
          />
        </div>

        {/* QuoteBar */}
        <div style={{ marginBottom: 12 }}>
          <QuoteBar symbol={symbol || undefined} />
        </div>

        {/* SMA chart */}
        <div style={{ marginBottom: 16 }}>
          {candles.length > 0 ? (
            <SmaPanel
              candles={candles}
              smaPeriods={smaPeriods}
              onPeriodsChange={setSmaPeriods}
              symbol={symbol}
            />
          ) : (
            <div style={{
              height: 160,
              border: `1px solid ${BORDER}`,
              borderRadius: 4,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: MUTED, fontSize: 10,
            }}>
              SMA chart — configurable moving averages
            </div>
          )}
        </div>

        {/* Trade structure sections */}
        <div>

          {/* Vertical spreads */}
          <SectionHeader
            title="Vertical spreads"
            count={countText(vertLoading, vertError, vertSpreads)}
            expanded={vertExpanded}
            onToggle={handleVertToggle}
            showConfig
            onConfig={() => setVertConfigOpen(true)}
          />
          {vertExpanded && (
            <div style={{ paddingTop: 4 }}>
              {vertLoading && (
                <div style={{ padding: '12px 0', color: MUTED, fontSize: 11 }}>Loading vertical spreads…</div>
              )}
              {vertError && (
                <div style={{ padding: '12px 0', color: 'var(--red)', fontSize: 11 }}>{vertError}</div>
              )}
              {!vertLoading && !vertError && vertSpreads.length > 0 && (
                <ResultsTable
                  results={vertSpreads}
                  columns={verticalsColumns}
                  context={vertContext}
                  expandedRowId={expandedRowId}
                  onRowClick={handleRowClick}
                  renderExpansionRow={renderVertExpansion}
                  getRowId={getVertRowId}
                  defaultSortKey="composite_score"
                  defaultSortDir="desc"
                />
              )}
              {!vertLoading && !vertError && vertSpreads.length === 0 && symbol && (
                <div style={{ padding: '12px 0', color: MUTED, fontSize: 11 }}>No vertical spreads found.</div>
              )}
              {!symbol && (
                <div style={{ padding: '12px 0', color: MUTED, fontSize: 11 }}>Enter a symbol above to scan for trades.</div>
              )}
            </div>
          )}

          {/* Puts & calls */}
          <div style={{ marginTop: 2 }}>
            <SectionHeader
              title="Puts & calls"
              count={countText(callsLoading, callsError, callResults)}
              expanded={callsExpanded}
              onToggle={handleCallsToggle}
              showConfig
              onConfig={() => setCallsConfigOpen(true)}
            />
            {callsExpanded && (
              <div style={{ paddingTop: 4 }}>
                {callsLoading && (
                  <div style={{ padding: '12px 0', color: MUTED, fontSize: 10 }}>Analyzing long options…</div>
                )}
                {callsError && (
                  <div style={{ padding: '12px 0', color: 'var(--red)', fontSize: 11 }}>{callsError}</div>
                )}
                {!callsLoading && !callsError && callsDisplay.length > 0 && (
                  <ResultsTable
                    results={callsDisplay}
                    columns={longOptionsColumns}
                    context={callsContext}
                    expandedRowId={expandedRowId}
                    onRowClick={handleRowClick}
                    renderExpansionRow={renderCallExpansion}
                    getRowId={getCallRowId}
                    defaultSortKey="composite_score"
                    defaultSortDir="desc"
                  />
                )}
                {!callsLoading && !callsError && callResults.length === 0 && symbol && (
                  <div style={{ padding: '12px 0', color: MUTED, fontSize: 10, textAlign: 'center' }}>
                    No candidates matching Trend Rider / Lottery Ticket filters for {symbol}
                    {smaAlignment?.alignment && (
                      <span> — SMA signal is {smaAlignment.alignment.charAt(0).toUpperCase() + smaAlignment.alignment.slice(1)}{smaAlignment.alignment === 'mixed' ? ' (requires Bullish or Bearish alignment)' : ''}</span>
                    )}
                  </div>
                )}
                {!symbol && (
                  <div style={{ padding: '12px 0', color: MUTED, fontSize: 11 }}>Enter a symbol above to scan for trades.</div>
                )}
              </div>
            )}
          </div>

          {/* Iron condors — coming soon */}
          <div style={{ marginTop: 2 }}>
            <SectionHeader
              title="Iron condors"
              count="· coming soon"
              expanded={false}
              comingSoon
            />
          </div>

        </div>
      </div>

      {/* Section config drawers */}
      <SectionConfigDrawer
        open={vertConfigOpen}
        onClose={() => setVertConfigOpen(false)}
        onApply={handleVertConfigApply}
        strategyKeys={VERT_STRATEGY_KEYS}
      />
      <SectionConfigDrawer
        open={callsConfigOpen}
        onClose={() => setCallsConfigOpen(false)}
        onApply={handleCallsConfigApply}
        strategyKeys={CALLS_STRATEGY_KEYS}
      />
    </>
  );
}
