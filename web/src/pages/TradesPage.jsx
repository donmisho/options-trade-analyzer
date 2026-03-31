/**
 * TradesPage — Trades screen (Screen 2 in UI-GUIDANCE.md).
 *
 * Routes: /trades, /trades?symbol=XXX, /trades?strategy=XXX
 *
 * Layout (top → bottom):
 *   1. Symbol search
 *   2. QuoteBar
 *   3. SMA chart (configurable)
 *   4. Collapsible trade structure sections:
 *      a. Vertical spreads (expanded by default)
 *      b. Puts & calls (collapsed by default)
 *      c. Iron condors (coming soon — not clickable)
 *
 * ResultsTable wiring happens in the integration session.
 */

import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import SymbolSearch from '../components/SymbolSearch';
import QuoteBar from '../components/QuoteBar';
import SmaPanel from '../components/SmaPanel';
import { searchSymbolsStatic } from '../api/client';

const MUTED  = '#8b949e';
const TEXT   = '#e6edf3';
const BORDER = '#30363d';

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
      {/* Chevron */}
      <span style={{ fontSize: 9, color: MUTED, width: 14, flexShrink: 0 }}>
        {comingSoon ? '▶' : expanded ? '▼' : '▶'}
      </span>

      {/* Title */}
      <span style={{ fontSize: 12, fontWeight: 700, color: TEXT, fontFamily: 'monospace' }}>
        {title}
      </span>

      {/* Count */}
      <span style={{ fontSize: 10, color: MUTED, fontFamily: 'monospace', fontStyle: comingSoon ? 'italic' : 'normal' }}>
        {count}
      </span>

      {/* Config button */}
      {showConfig && !comingSoon && (
        <button
          onClick={e => { e.stopPropagation(); }}
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

// ─── Main component ───────────────────────────────────────────────────────────
export default function TradesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { positionSymbols } = useApp();

  // Symbol derived from URL params — updating URL param drives symbol changes
  const symbol = searchParams.get('symbol') || '';

  const [smaPeriods, setSmaPeriods] = useState({ short: 8, mid: 21, long: 50 });
  // candles populated during integration session when analysis runs
  const [candles] = useState([]);

  // Section open state
  const [vertExpanded, setVertExpanded]   = useState(true);
  const [callsExpanded, setCallsExpanded] = useState(false);

  function handleSymbolSelect(sym) {
    const next = new URLSearchParams(searchParams);
    next.set('symbol', sym);
    setSearchParams(next, { replace: true });
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

      {/* SMA chart — wired in integration session when analysis provides candle data */}
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
            color: MUTED, fontSize: 10, fontFamily: 'monospace',
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
          count={`· ${vertExpanded ? 'loading' : 'collapsed'}`}
          expanded={vertExpanded}
          onToggle={() => setVertExpanded(v => !v)}
          showConfig
        />
        {vertExpanded && (
          <div style={{ padding: '12px 0', color: MUTED, fontSize: 11 }}>
            Loading vertical spreads…
          </div>
        )}

        {/* Puts & calls */}
        <div style={{ marginTop: 2 }}>
          <SectionHeader
            title="Puts & calls"
            count={`· ${callsExpanded ? 'loading' : 'collapsed'}`}
            expanded={callsExpanded}
            onToggle={() => setCallsExpanded(v => !v)}
            showConfig
          />
          {callsExpanded && (
            <div style={{ padding: '12px 0', color: MUTED, fontSize: 11 }}>
              Loading puts & calls…
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
