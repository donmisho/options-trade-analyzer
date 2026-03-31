/**
 * TradesPage — Trades screen (Screen 2 in UI-GUIDANCE.md v3.1).
 *
 * Routes: /trades, /trades?symbol=XXX, /trades?strategy=XXX
 *
 * Layout (top → bottom):
 *   1. Symbol search
 *   2. QuoteBar
 *   3. SMA chart (placeholder until analysis data available)
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
import { analyzeVerticals, analyzeLongCalls, searchSymbolsStatic } from '../api/client';

const MUTED  = '#8b949e';
const TEXT   = '#e6edf3';
const BORDER = '#30363d';
const TEAL   = '#2dd4bf';

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
  const breakeven = debit != null && spread.long_strike != null
    ? isBull ? spread.long_strike + debit : spread.long_strike - debit
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
function TradeDetailExpansion({ detailProps, tradeContext, evaluation, onEvaluate, onDiscard }) {
  return (
    <div style={{
      borderTop: `2px solid rgba(45,212,191,0.35)`,
      padding: '16px 0',
      fontFamily: 'monospace',
    }}>
      <SectionA trade={detailProps} />
      <SectionB scenarios={[]} totalEV={null} />
      <SectionC outcome={null} />
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
  const [candles] = useState([]); // populated by integration session when analysis data arrives

  // ── Vertical spreads state ───────────────────────────────────────────────
  const [vertExpanded, setVertExpanded]   = useState(true);
  const [vertSpreads, setVertSpreads]     = useState([]);
  const [vertLoading, setVertLoading]     = useState(false);
  const [vertError, setVertError]         = useState(null);
  const [vertUnderlying, setVertUnderlying] = useState(0);

  // ── Puts & calls state ───────────────────────────────────────────────────
  const [callsExpanded, setCallsExpanded] = useState(false);
  const [callResults, setCallResults]     = useState([]);
  const [callsLoading, setCallsLoading]   = useState(false);
  const [callsError, setCallsError]       = useState(null);
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
      setVertSpreads(data.spreads || []);
      setVertUnderlying(data.underlying_price || 0);
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
      setCallResults(data.calls || []);
      setCallsUnderlying(data.underlying_price || 0);
    } catch (err) {
      setCallsError(err.message || 'Failed to fetch puts & calls');
      setCallResults([]);
    } finally {
      setCallsLoading(false);
    }
  }

  // ── Symbol select ────────────────────────────────────────────────────────
  function handleSymbolSelect(sym) {
    const next = new URLSearchParams(searchParams);
    next.set('symbol', sym);
    setSearchParams(next, { replace: true });
    // Reset results
    setVertSpreads([]);
    setCallResults([]);
    setExpandedRowId(null);
    setEvaluations({});
    // Auto-fetch expanded sections
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

  // ── Expansion row renderer ───────────────────────────────────────────────
  function renderVertExpansion(trade) {
    const rowId = `vert-${vertSpreads.indexOf(trade)}`;
    const detailProps = mapSpreadToDetail(trade);
    const ctx = `${symbol} · ${detailProps.strikes} · ${detailProps.type} · ${detailProps.expiry || ''}`;
    return (
      <TradeDetailExpansion
        trade={trade}
        detailProps={detailProps}
        tradeContext={ctx}
        evaluation={evaluations[rowId] || null}
        onEvaluate={() => console.log('Evaluate', trade)}
        onDiscard={() => setExpandedRowId(null)}
      />
    );
  }

  function renderCallExpansion(trade) {
    const rowId = `calls-${callResults.indexOf(trade)}`;
    const detailProps = mapCallToDetail(trade);
    const ctx = `${symbol} · ${trade.option_type} · ${trade.strike} · ${trade.expiration || ''}`;
    return (
      <TradeDetailExpansion
        trade={trade}
        detailProps={detailProps}
        tradeContext={ctx}
        evaluation={evaluations[rowId] || null}
        onEvaluate={() => console.log('Evaluate', trade)}
        onDiscard={() => setExpandedRowId(null)}
      />
    );
  }

  // ── Row ID helpers ───────────────────────────────────────────────────────
  const getVertRowId = (trade, idx) => `vert-${idx}`;
  const getCallRowId = (trade, idx) => `calls-${idx}`;

  // ── Table context ────────────────────────────────────────────────────────
  const vertContext   = { currentPrice: vertUnderlying };
  const callsContext  = { currentPrice: callsUnderlying, thetaThreshold: 10 };

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
