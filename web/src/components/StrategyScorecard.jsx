/**
 * StrategyScorecard — Displays all strategy scores for a symbol simultaneously.
 *
 * Used in two contexts:
 * 1. SecurityStrategiesPage — symbol-level scorecard showing all 4 strategies
 * 2. OptionsTerminal Stage 2 expansion — trade-level strategy fit display
 *
 * Props:
 *   scores          — array of { key, label, score, best_trade?, signal_summary? }
 *   selectedKeys    — controlled array of selected strategy keys
 *   onSelectionChange — (keys: string[]) => void
 *   onEvaluate      — (keys: string[]) => void — called when Evaluate button clicked
 *   loading         — boolean, shows skeleton state when true
 */

import { STRATEGY_CONFIGS } from '../strategy-configs/index';
import { C, mono } from '../styles/tokens';

// Score color per UI-DECISIONS: green ≥70, amber 40–69, red <40
function scoreColor(score) {
  if (score >= 70) return '#4ade80';  // var(--green)
  if (score >= 40) return '#f59e0b';  // var(--amber)
  return '#f87171';                   // var(--red)
}

/**
 * Format best_trade for display — handles both string (mock) and dict (API) shapes.
 * API returns the raw engine output dict; we extract a short readable summary.
 */
function formatBestTrade(best_trade) {
  if (!best_trade) return null;
  if (typeof best_trade === 'string') return best_trade;

  // Credit spread (has spread_type)
  const st = best_trade.spread_type;
  if (st) {
    const label = st.replace(/_/g, ' ');
    const short = best_trade.short_strike ?? '';
    const exp = (best_trade.expiration ?? '').slice(0, 7);
    const pop = best_trade.prob_of_profit != null
      ? ` · PoP ${Math.round(best_trade.prob_of_profit * 100)}%` : '';
    return `${label} ${short} exp ${exp}${pop}`;
  }

  // Long option
  const optType = best_trade.option_type ?? 'call';
  const strike = best_trade.strike ?? '';
  const exp = (best_trade.expiration ?? '').slice(0, 7);
  const delta = best_trade.delta != null ? ` Δ${best_trade.delta.toFixed(2)}` : '';
  return `Long ${optType} ${strike} exp ${exp}${delta}`;
}

function ScoreRow({ item, selected, onToggle }) {
  const itemKey = item.key ?? item.strategy_key;
  const score = Number(item.score ?? 0);
  const color = scoreColor(score);

  // Subtitle from strategy config description, or fall back to signal_summary for backwards compat
  const strategyCfg = STRATEGY_CONFIGS[itemKey];
  const subtitle = strategyCfg?.description ?? null;
  // Signal summary: dynamic signal info (IV rank, SMA alignment)
  const signalSummary = item.signal_summary ?? (item.best_trade ? formatBestTrade(item.best_trade) : null);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '10px 12px',
        borderRadius: 6,
        border: `1px solid ${selected ? color + '60' : C.border}`,
        backgroundColor: selected ? color + '08' : C.card,
        cursor: 'pointer',
        transition: 'background-color 0.15s, border-color 0.15s',
        marginBottom: 6,
      }}
      onClick={() => onToggle(itemKey)}
    >
      {/* Checkbox */}
      <input
        type="checkbox"
        checked={selected}
        onChange={() => onToggle(itemKey)}
        onClick={(e) => e.stopPropagation()}
        style={{ width: 15, height: 15, cursor: 'pointer', accentColor: color, flexShrink: 0 }}
      />

      {/* Strategy name + subtitle (stacked) */}
      <div style={{ width: 140, flexShrink: 0 }}>
        <div style={{
          color: C.text,
          fontSize: 12,
          fontWeight: 700,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {item.label}
        </div>
        {subtitle && (
          <div style={{
            color: '#8b949e',
            fontSize: 9,
            marginTop: 2,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {subtitle}
          </div>
        )}
      </div>

      {/* Score bar (full width) */}
      <div style={{
        flex: 1,
        height: 6,
        borderRadius: 3,
        backgroundColor: C.border,
        overflow: 'hidden',
        minWidth: 50,
      }}>
        <div style={{
          height: '100%',
          width: `${Math.min(score, 100)}%`,
          backgroundColor: color,
          borderRadius: 3,
          transition: 'width 0.4s ease',
        }} />
      </div>

      {/* Score number — ##.00 format */}
      <span style={{
        color,
        fontSize: 13,
        fontWeight: 700,
        fontFamily: mono,
        width: 40,
        textAlign: 'right',
        flexShrink: 0,
      }}>
        {score.toFixed(2)}
      </span>

      {/* Signal summary — right-aligned muted */}
      {signalSummary && (
        <span style={{
          color: '#8b949e',
          fontSize: 9,
          fontFamily: mono,
          maxWidth: 170,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          flexShrink: 0,
          textAlign: 'right',
        }}>
          {signalSummary}
        </span>
      )}
    </div>
  );
}

function SkeletonRow() {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      padding: '10px 12px',
      borderRadius: 6,
      border: `1px solid ${C.border}`,
      backgroundColor: C.card,
      marginBottom: 6,
    }}>
      <div style={{ width: 15, height: 15, borderRadius: 3, backgroundColor: C.border }} />
      <div style={{ width: 140, flexShrink: 0 }}>
        <div style={{ height: 12, borderRadius: 4, backgroundColor: C.border, marginBottom: 4 }} />
        <div style={{ height: 9, width: '80%', borderRadius: 3, backgroundColor: C.border }} />
      </div>
      <div style={{ flex: 1, height: 6, borderRadius: 3, backgroundColor: C.border }} />
      <div style={{ width: 38, height: 13, borderRadius: 4, backgroundColor: C.border }} />
      <div style={{ width: 100, height: 9, borderRadius: 3, backgroundColor: C.border }} />
    </div>
  );
}

export default function StrategyScorecard({
  scores = [],
  selectedKeys = [],
  onSelectionChange,
  onEvaluate,
  loading = false,
}) {
  const hasSelection = selectedKeys.length > 0;

  const handleToggle = (key) => {
    if (!onSelectionChange) return;
    if (selectedKeys.includes(key)) {
      onSelectionChange(selectedKeys.filter(k => k !== key));
    } else {
      onSelectionChange([...selectedKeys, key]);
    }
  };

  return (
    <div>
      {/* Score rows */}
      <div>
        {loading ? (
          <>
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </>
        ) : scores.length === 0 ? (
          <div style={{
            padding: '20px',
            textAlign: 'center',
            color: '#8b949e',
            fontSize: 12,
            borderRadius: 6,
            border: `1px dashed ${C.border}`,
          }}>
            No strategy scores available
          </div>
        ) : (
          scores.map(item => {
            const itemKey = item.key ?? item.strategy_key;
            return (
              <ScoreRow
                key={itemKey}
                item={item}
                selected={selectedKeys.includes(itemKey)}
                onToggle={handleToggle}
              />
            );
          })
        )}
      </div>

      {/* Evaluate button + selected count */}
      {!loading && scores.length > 0 && (
        <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            onClick={() => onEvaluate && onEvaluate(selectedKeys)}
            disabled={!hasSelection}
            style={{
              background: 'rgba(45,212,191,0.1)',
              border: '1px solid rgba(45,212,191,0.4)',
              color: '#2dd4bf',
              padding: '7px 16px',
              borderRadius: 4,
              fontSize: 11,
              fontFamily: mono,
              cursor: hasSelection ? 'pointer' : 'default',
              width: 'auto',
              opacity: hasSelection ? 1 : 0.35,
              pointerEvents: hasSelection ? 'auto' : 'none',
            }}
          >
            Evaluate Selected
          </button>
          {hasSelection && (
            <span style={{ fontSize: 9, color: '#8b949e', fontFamily: mono }}>
              {selectedKeys.length} {selectedKeys.length === 1 ? 'strategy' : 'strategies'} selected
            </span>
          )}
        </div>
      )}
    </div>
  );
}
