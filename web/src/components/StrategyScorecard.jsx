/**
 * StrategyScorecard — Displays all strategy scores for a symbol simultaneously.
 *
 * Used in two contexts:
 * 1. SecurityDashboard — symbol-level scorecard showing all 4 strategies
 * 2. OptionsTerminal Stage 2 expansion — trade-level strategy fit display
 *
 * Props:
 *   scores          — array of { key, label, score, best_trade?, signal_summary? }
 *   selectedKeys    — controlled array of selected strategy keys
 *   onSelectionChange — (keys: string[]) => void
 *   onEvaluate      — (keys: string[]) => void — called when Evaluate button clicked
 *   loading         — boolean, shows skeleton state when true
 */

import { C, mono } from '../styles/tokens';

function scoreColor(score) {
  if (score >= 65) return C.green;   // #26a69a
  if (score >= 35) return C.amber;   // #f59e0b
  return C.red;                      // #ef5350
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
  const color = scoreColor(item.score);
  // Support both API shape (strategy_key) and mock shape (key)
  const itemKey = item.key ?? item.strategy_key;

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
      title={item.signal_summary || ''}
    >
      {/* Checkbox */}
      <input
        type="checkbox"
        checked={selected}
        onChange={() => onToggle(itemKey)}
        onClick={(e) => e.stopPropagation()}
        style={{ width: 15, height: 15, cursor: 'pointer', accentColor: color, flexShrink: 0 }}
      />

      {/* Strategy name */}
      <span style={{
        color: C.text,
        fontSize: 13,
        fontWeight: 500,
        width: 130,
        flexShrink: 0,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}>
        {item.label}
      </span>

      {/* Score number */}
      <span style={{
        color,
        fontSize: 15,
        fontWeight: 700,
        fontFamily: mono,
        width: 34,
        textAlign: 'right',
        flexShrink: 0,
      }}>
        {item.score}
      </span>

      {/* Score bar */}
      <div style={{
        flex: 1,
        height: 8,
        borderRadius: 4,
        backgroundColor: C.border,
        overflow: 'hidden',
        minWidth: 60,
      }}>
        <div style={{
          height: '100%',
          width: `${item.score}%`,
          backgroundColor: color,
          borderRadius: 4,
          transition: 'width 0.4s ease',
        }} />
      </div>

      {/* Best trade summary (truncated) */}
      {item.best_trade && (
        <span style={{
          color: C.textDim,
          fontSize: 10.5,
          fontFamily: mono,
          maxWidth: 180,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          flexShrink: 0,
        }}>
          {formatBestTrade(item.best_trade)}
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
      <div style={{ width: 120, height: 13, borderRadius: 4, backgroundColor: C.border }} />
      <div style={{ width: 32, height: 15, borderRadius: 4, backgroundColor: C.border, marginLeft: 4 }} />
      <div style={{ flex: 1, height: 8, borderRadius: 4, backgroundColor: C.border }} />
      <div style={{ width: 120, height: 11, borderRadius: 4, backgroundColor: C.border }} />
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
            color: C.textMuted,
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
        )
        )}
      </div>

      {/* Evaluate button */}
      {!loading && scores.length > 0 && (
        <button
          onClick={() => onEvaluate && onEvaluate(selectedKeys)}
          disabled={!hasSelection}
          style={{
            marginTop: 10,
            width: '100%',
            padding: '10px 0',
            borderRadius: 6,
            border: 'none',
            backgroundColor: hasSelection ? C.accent : C.border,
            color: hasSelection ? '#fff' : C.textMuted,
            fontSize: 13,
            fontWeight: 700,
            fontFamily: mono,
            cursor: hasSelection ? 'pointer' : 'not-allowed',
            letterSpacing: '0.04em',
            transition: 'background-color 0.15s, color 0.15s',
          }}
        >
          {hasSelection
            ? `\u2726 Evaluate Selected (${selectedKeys.length})`
            : 'Select strategies to evaluate'}
        </button>
      )}
    </div>
  );
}
