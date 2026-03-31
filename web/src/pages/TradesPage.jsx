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

import { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import SymbolSearch from '../components/SymbolSearch';
import QuoteBar from '../components/QuoteBar';
import SmaPanel from '../components/SmaPanel';
import ResultsTable from '../components/ResultsTable';
import { SectionA, SectionB, SectionC, SectionD, SectionE } from '../components/TradeDetail';
import { verticalsColumns } from '../config/verticals-columns';
import { longOptionsColumns } from '../config/long-options-columns';
import { analyzeVerticals, analyzeLongCalls, searchSymbolsStatic, getQuote } from '../api/client';

const MUTED  = '#8b949e';
const TEXT   = '#e6edf3';
const BORDER = '#30363d';

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

function inferLongOptionStrategies(optionType, dte) {
  if (dte != null && dte < 21) return ['LT'];
  return ['TR'];
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
  const isBull = (spread.spread_type || '').startsWith('bull');
  const isDebit = net_debit > 0;
  const creditAmt = Math.abs(net_debit);

  const dte = expiration
    ? Math.max(1, Math.round((new Date(expiration) - new Date()) / 86400000))
    : 30;
  const sigma = Math.max(1, (iv || 0.25) * underlying * Math.sqrt(dte / 365));

  function spreadValueAt(price) {
    if (isBull) return Math.max(0, Math.min(price - loStrike, width));
    return Math.max(0, Math.min(hiStrike - price, width));
  }

  function pnlAt(price) {
    const sv = spreadValueAt(price);
    return isDebit ? (sv - net_debit) * 100 : (creditAmt - sv) * 100;
  }

  const maxPnl    = isDebit ? (width - net_debit) * 100 : creditAmt * 100;
  const maxLossAmt = isDebit ? net_debit * 100 : (width - creditAmt) * 100;
  const risk = isDebit ? net_debit * 100 : (width - creditAmt) * 100;

  function exitSignalFor(pnl) {
    if (pnl >= maxPnl * 0.95) return 'MAX PROFIT';
    if (Math.abs(pnl) < 0.5) return 'BREAKEVEN';
    if (maxLossAmt > 0 && pnl <= -maxLossAmt * 0.95) return 'STOP';
    return null;
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
      exitSignal: exitSignalFor(pnl),
    });
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

// ─── Map ScoredSpread → SectionA trade object ────────────────────────────────
function mapSpreadToDetail(spread) {
  const spreadWidth = spread.long_strike != null && spread.short_strike != null
    ? Math.abs(spread.long_strike - spread.short_strike)
    : null;
  const debit = spread.net_debit;
  const isDebit = debit != null && debit > 0;
  const isBull = (spread.spread_type || '').startsWith('bull');
  const maxProfit = spreadWidth != null && debit != null
    ? (isDebit ? spreadWidth - debit : debit) * 100
    : null;
  const maxLoss = spreadWidth != null && debit != null
    ? (isDebit ? debit : spreadWidth - debit) * 100
    : null;
  const loStrike = spread.long_strike != null && spread.short_strike != null
    ? Math.min(spread.long_strike, spread.short_strike)
    : null;
  const hiStrike = spread.long_strike != null && spread.short_strike != null
    ? Math.max(spread.long_strike, spread.short_strike)
    : null;
  const breakeven = debit != null && loStrike != null
    ? (isBull
      ? (isDebit ? loStrike + debit : hiStrike - Math.abs(debit))
      : (isDebit ? hiStrike - debit : loStrike + Math.abs(debit)))
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
function SectionHeader({ title, count, expanded, onToggle, showConfig, comingSoon }) {
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
          onClick={e => e.stopPropagation()}
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

// ─── Trade detail expansion panel ────────────────────────────────────────────
function TradeDetailExpansion({
  detailProps, tradeContext, evaluation, onEvaluate, onDiscard,
  scenarios, totalEV, outcome,
}) {
  return (
    <div style={{
      borderTop: `2px solid rgba(45,212,191,0.35)`,
      padding: '16px 0',
      fontFamily: 'monospace',
    }}>
      <SectionA trade={detailProps} />
      <SectionB scenarios={scenarios || []} totalEV={totalEV ?? null} />
      <SectionC outcome={outcome || null} />
      <SectionD />
      <SectionE
        evaluation={evaluation || null}
        tradeContext={tradeContext}
        onEvaluate={onEvaluate}
        onFollow={() => {}}
        onTakePosition={() => {}}
        onFollowUp={() => {}}
        onDiscard={onDiscard}
      />
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function TradesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { positionSymbols } = useApp();

  const symbol = searchParams.get('symbol') || '';

  // ── SMA chart state ──────────────────────────────────────────────────────
  const [smaPeriods, setSmaPeriods] = useState({ short: 8, mid: 21, long: 50 });
  const [candles, setCandles] = useState([]);

  // ── Vertical spreads state ───────────────────────────────────────────────
  const [vertExpanded, setVertExpanded]     = useState(true);
  const [vertSpreads, setVertSpreads]       = useState([]);
  const [vertLoading, setVertLoading]       = useState(false);
  const [vertError, setVertError]           = useState(null);
  const [vertUnderlying, setVertUnderlying] = useState(0);

  // ── Puts & calls state ───────────────────────────────────────────────────
  const [callsExpanded, setCallsExpanded]     = useState(false);
  const [callResults, setCallResults]         = useState([]);
  const [callsLoading, setCallsLoading]       = useState(false);
  const [callsError, setCallsError]           = useState(null);
  const [callsUnderlying, setCallsUnderlying] = useState(0);

  // ── Expansion state — one row expanded at a time across both sections ────
  const [expandedRowId, setExpandedRowId] = useState(null);
  const [evaluations, setEvaluations]     = useState({}); // rowId → evaluation object

  // ── Fetch verticals ──────────────────────────────────────────────────────
  async function fetchVerticals(sym) {
    if (!sym) return;
    setVertLoading(true);
    setVertError(null);
    try {
      const data = await analyzeVerticals({
        symbol: sym,
        spread_types: ['bull_call', 'bear_put'],
        max_results: 20,
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
  async function fetchCalls(sym) {
    if (!sym) return;
    setCallsLoading(true);
    setCallsError(null);
    try {
      const data = await analyzeLongCalls({
        symbol: sym,
        max_results: 20,
        option_types: ['call', 'put'],
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

  // ── Expansion row renderers ──────────────────────────────────────────────
  function renderVertExpansion(trade) {
    const rowId = `vert-${vertSpreads.indexOf(trade)}`;
    const detailProps = mapSpreadToDetail(trade);
    const ctx = `${symbol} · ${detailProps.strikes} · ${detailProps.type} · ${detailProps.expiry || ''}`;
    const { scenarios, totalEV } = buildExitScenarios(trade, vertUnderlying);
    const outcome = buildOutcome(trade, vertUnderlying, totalEV);
    return (
      <TradeDetailExpansion
        detailProps={detailProps}
        tradeContext={ctx}
        evaluation={evaluations[rowId] || null}
        onEvaluate={() => console.log('Evaluate', trade)}
        onDiscard={() => setExpandedRowId(null)}
        scenarios={scenarios}
        totalEV={totalEV}
        outcome={outcome}
      />
    );
  }

  function renderCallExpansion(trade) {
    const detailProps = mapCallToDetail(trade);
    const ctx = `${symbol} · ${trade.option_type} · ${trade.strike} · ${trade.expiration || ''}`;
    const rowId = `calls-${callResults.indexOf(trade)}`;
    return (
      <TradeDetailExpansion
        detailProps={detailProps}
        tradeContext={ctx}
        evaluation={evaluations[rowId] || null}
        onEvaluate={() => console.log('Evaluate', trade)}
        onDiscard={() => setExpandedRowId(null)}
        scenarios={[]}
        totalEV={null}
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
    <div style={{ padding: '16px 20px', fontFamily: 'monospace' }}>

      {/* Symbol search */}
      <div style={{ marginBottom: 10 }}>
        <SymbolSearch
          onSelect={handleSymbolSelect}
          searchFn={searchSymbolsStatic}
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
          />
          {callsExpanded && (
            <div style={{ paddingTop: 4 }}>
              {callsLoading && (
                <div style={{ padding: '12px 0', color: MUTED, fontSize: 11 }}>Loading puts & calls…</div>
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
                <div style={{ padding: '12px 0', color: MUTED, fontSize: 11 }}>No puts & calls found.</div>
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
  );
}
