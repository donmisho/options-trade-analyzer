/**
 * PositionDetailPanel — OTA-631
 *
 * Shared expanded-row panel for positions across StrategyPage, PositionsPage,
 * and PositionsScorecardWidget. Renders full position state from fields already
 * on the position object (no new API calls).
 *
 * Groups (each line omitted if source field is null/missing):
 *   1. Verdict block
 *   2. Trade structure block
 *   3. Entry context
 *   4. Current state
 *   5. Exit levels (collapsible)
 *   6. Probability matrix (collapsible)
 */

import { useState } from 'react';
import { formatDate, formatRelativeTime } from '../utils/formatDate';

const MUTED = '#8b949e';
const TEXT = '#e6edf3';
const SECTION_LABEL = {
  fontSize: 9,
  textTransform: 'uppercase',
  letterSpacing: '0.6px',
  color: MUTED,
  fontFamily: 'monospace',
  marginBottom: 6,
  marginTop: 14,
};

const VERDICT_STYLES = {
  EXECUTE: { bg: 'rgba(74,222,128,0.15)', color: '#4ade80' },
  WAIT:    { bg: 'rgba(245,158,11,0.15)',  color: '#f59e0b' },
  PASS:    { bg: 'rgba(248,113,113,0.15)', color: '#f87171' },
};

function scoreColor(score) {
  if (score >= 70) return '#4ade80';
  if (score >= 40) return '#f59e0b';
  return '#f87171';
}

function VerdictPill({ verdict }) {
  if (!verdict) return null;
  const upper = verdict.toUpperCase();
  const s = VERDICT_STYLES[upper] || { bg: 'rgba(255,255,255,0.06)', color: MUTED };
  return (
    <span style={{
      display: 'inline-block', padding: '2px 7px', borderRadius: 3,
      fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
      letterSpacing: '0.3px', color: s.color, background: s.bg,
      fontFamily: 'monospace',
    }}>
      {verdict}
    </span>
  );
}

function CollapsibleSection({ label, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <div
        onClick={() => setOpen(o => !o)}
        style={{ ...SECTION_LABEL, cursor: 'pointer', userSelect: 'none' }}
      >
        <span style={{ fontSize: 9, marginRight: 4 }}>{open ? '▼' : '▶'}</span>
        {label}
      </div>
      {open && children}
    </div>
  );
}

function DataRow({ label, value, color }) {
  if (value == null || value === '' || value === 'N/A') return null;
  return (
    <div style={{ display: 'flex', gap: 8, fontSize: 10, fontFamily: 'monospace', marginBottom: 3 }}>
      <span style={{ color: MUTED, minWidth: 120, flexShrink: 0 }}>{label}</span>
      <span style={{ color: color || '#c9d1d9' }}>{value}</span>
    </div>
  );
}

export default function PositionDetailPanel({ pos }) {
  const [showFullRead, setShowFullRead] = useState(false);

  if (!pos) return null;

  const verdict = pos.claude_verdict;
  const verdictStr = verdict?.verdict || null;
  const score = pos.claude_score;
  const claudeRead = verdict?.claude_read || null;
  const synopsis = verdict?.synopsis || null;
  const exitLevels = pos.claude_exit_levels || null;
  const probMatrix = pos.claude_probability_matrix || null;
  const ts = pos.trade_structure || null;
  const legs = ts && Array.isArray(ts.legs) ? ts.legs : [];

  const readText = claudeRead || '';
  const truncated = readText.length > 200 && !showFullRead;
  const displayRead = truncated ? readText.slice(0, 200) + '…' : readText;

  // Current P&L formatting
  const pnlAmount = pos.pnl_amount;
  const pnlPct = pos.pnl_pct;
  let pnlDisplay = null;
  if (pnlAmount != null) {
    const sign = pnlAmount >= 0 ? '+' : '';
    const pctStr = pnlPct != null ? ` (${pnlAmount >= 0 ? '+' : ''}${Number(pnlPct).toFixed(2)}%)` : '';
    const color = pnlAmount >= 0 ? '#4ade80' : '#f87171';
    pnlDisplay = <span style={{ color }}>{sign}{Number(pnlAmount).toFixed(2)}{pctStr}</span>;
  }

  return (
    <div style={{
      padding: '10px 16px 14px 40px',
      borderTop: '2px solid rgba(45,212,191,0.35)',
      borderBottom: '1px solid var(--border, #30363d)',
      background: 'transparent',
      fontFamily: 'monospace',
    }}>

      {/* 1. Verdict block */}
      {(verdictStr || score != null || synopsis || readText) && (
        <div>
          <div style={SECTION_LABEL}>Verdict</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
            {verdictStr && <VerdictPill verdict={verdictStr} />}
            {score != null && (
              <span style={{ fontSize: 11, fontWeight: 700, color: scoreColor(score) }}>
                {Number(score).toFixed(2)}
              </span>
            )}
            {synopsis && (
              <span style={{
                display: 'inline-block', fontSize: 9, fontWeight: 700,
                padding: '3px 10px', borderRadius: 3,
                background: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(255,255,255,0.35)',
                color: TEXT,
              }}>
                {synopsis}
              </span>
            )}
          </div>
          {readText && (
            <div style={{
              borderLeft: '2px solid var(--border, #30363d)',
              padding: '6px 12px',
              margin: '4px 0 4px 0',
              fontSize: 10,
              color: '#c9d1d9',
              lineHeight: 1.65,
            }}>
              {displayRead}
              {readText.length > 200 && (
                <span
                  onClick={() => setShowFullRead(v => !v)}
                  style={{ color: '#2dd4bf', cursor: 'pointer', marginLeft: 4, fontSize: 9 }}
                >
                  {showFullRead ? 'show less' : 'show more'}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* 2. Trade structure block */}
      {legs.length > 0 && (
        <div>
          <div style={SECTION_LABEL}>Trade Structure</div>
          {legs.map((leg, i) => (
            <div key={i} style={{ display: 'flex', gap: 12, fontSize: 10, color: '#c9d1d9', marginBottom: 2 }}>
              <span style={{ color: MUTED, minWidth: 40 }}>{leg.side || '—'}</span>
              <span>{leg.type || leg.option_type || '—'}</span>
              <span>{leg.strike != null ? Number(leg.strike).toFixed(2) : '—'}</span>
              <span>{leg.expiration ? formatDate(leg.expiration) : '—'}</span>
              {leg.qty != null && <span>×{leg.qty}</span>}
            </div>
          ))}
          {(pos.dte_at_entry != null || pos.dte != null) && (
            <div style={{ display: 'flex', gap: 12, fontSize: 10, color: MUTED, marginTop: 4 }}>
              {pos.dte_at_entry != null && <span>DTE at entry: {pos.dte_at_entry}d</span>}
              {pos.dte != null && <span>DTE remaining: {pos.dte}d</span>}
            </div>
          )}
        </div>
      )}

      {/* 3. Entry context */}
      {(pos.entry_underlying_price || pos.entry_iv_rank != null || pos.entry_sma_alignment) && (
        <div>
          <div style={SECTION_LABEL}>Entry Context</div>
          <DataRow label="Underlying Price" value={pos.entry_underlying_price != null ? Number(pos.entry_underlying_price).toFixed(2) : null} />
          <DataRow label="IV Rank" value={pos.entry_iv_rank != null ? `${Number(pos.entry_iv_rank).toFixed(2)}%` : null} />
          {pos.entry_sma_alignment && (
            <DataRow
              label="SMA Alignment"
              value={typeof pos.entry_sma_alignment === 'object'
                ? (pos.entry_sma_alignment.alignment || JSON.stringify(pos.entry_sma_alignment))
                : String(pos.entry_sma_alignment)}
            />
          )}
        </div>
      )}

      {/* 4. Current state */}
      {(pos.current_price != null || pnlDisplay || pos.last_monitored_at) && (
        <div>
          <div style={SECTION_LABEL}>Current State</div>
          <DataRow label="Current Price" value={pos.current_price != null ? Number(pos.current_price).toFixed(2) : null} />
          {pnlDisplay && (
            <div style={{ display: 'flex', gap: 8, fontSize: 10, fontFamily: 'monospace', marginBottom: 3 }}>
              <span style={{ color: MUTED, minWidth: 120, flexShrink: 0 }}>P&L</span>
              {pnlDisplay}
            </div>
          )}
          <DataRow label="Last Monitored" value={pos.last_monitored_at ? formatRelativeTime(pos.last_monitored_at) : null} />
        </div>
      )}

      {/* 5. Exit levels (collapsible) */}
      {exitLevels && Object.keys(exitLevels).length > 0 && (
        <CollapsibleSection label="Exit Levels">
          <div style={{ paddingLeft: 14 }}>
            {exitLevels.take_profit != null && (
              <DataRow label="Take Profit" value={Number(exitLevels.take_profit).toFixed(2)} color="#4ade80" />
            )}
            {exitLevels.warning_level != null && (
              <DataRow label="Warning Level" value={Number(exitLevels.warning_level).toFixed(2)} color="#f59e0b" />
            )}
            {exitLevels.hard_stop != null && (
              <DataRow label="Hard Stop" value={Number(exitLevels.hard_stop).toFixed(2)} color="#f87171" />
            )}
            {exitLevels.calendar_exit != null && (
              <DataRow label="Calendar Exit" value={typeof exitLevels.calendar_exit === 'string' ? exitLevels.calendar_exit : formatDate(exitLevels.calendar_exit)} />
            )}
            {/* Show delta from current price */}
            {pos.current_price != null && exitLevels.take_profit != null && (
              <DataRow
                label="Δ to Take Profit"
                value={`${(exitLevels.take_profit - pos.current_price) >= 0 ? '+' : ''}${(exitLevels.take_profit - pos.current_price).toFixed(2)}`}
                color={MUTED}
              />
            )}
            {pos.current_price != null && exitLevels.hard_stop != null && (
              <DataRow
                label="Δ to Hard Stop"
                value={`${(exitLevels.hard_stop - pos.current_price) >= 0 ? '+' : ''}${(exitLevels.hard_stop - pos.current_price).toFixed(2)}`}
                color={MUTED}
              />
            )}
          </div>
        </CollapsibleSection>
      )}

      {/* 6. Probability matrix (collapsible) */}
      {probMatrix && Object.keys(probMatrix).length > 0 && (
        <CollapsibleSection label="Probability Matrix">
          <div style={{ paddingLeft: 14, fontSize: 10, color: '#c9d1d9', lineHeight: 1.6 }}>
            {probMatrix.scenarios ? (
              probMatrix.scenarios.map((s, i) => (
                <div key={i} style={{ marginBottom: 2 }}>
                  <span style={{ color: MUTED }}>{Number(s.probability * 100).toFixed(0)}%</span>
                  {' '}
                  <span>{s.label || `Scenario ${i + 1}`}: </span>
                  <span style={{ color: s.pnl >= 0 ? '#4ade80' : '#f87171' }}>
                    {s.pnl >= 0 ? '+' : ''}{Number(s.pnl).toFixed(2)}
                  </span>
                </div>
              ))
            ) : (
              <pre style={{ margin: 0, fontSize: 9, color: '#c9d1d9', whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(probMatrix, null, 2)}
              </pre>
            )}
          </div>
        </CollapsibleSection>
      )}
    </div>
  );
}
