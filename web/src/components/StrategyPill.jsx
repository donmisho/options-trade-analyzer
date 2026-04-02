/**
 * StrategyPill — Abbreviated strategy badge with hover tooltip.
 *
 * Props:
 *   strategy — key string ("steady_paycheck", "SP", etc.) or abbr
 *
 * Accepts both key formats ("steady_paycheck" and "SP") — normalizes on input.
 *
 * STRATEGY_COLORS constant: import from web/src/utils/strategyColors.js
 */

import { STRATEGY_COLORS, ABBR_TO_STRATEGY_KEY } from '../utils/strategyColors';

function normalize(strategy) {
  if (!strategy) return null;
  const upper = strategy.toUpperCase();
  if (ABBR_TO_STRATEGY_KEY[upper]) return ABBR_TO_STRATEGY_KEY[upper];
  const lower = strategy.toLowerCase().replace(/-/g, '_');
  if (STRATEGY_COLORS[lower]) return lower;
  return null;
}

export default function StrategyPill({ strategy }) {
  const key = normalize(strategy);
  const cfg = key ? STRATEGY_COLORS[key] : null;
  if (!cfg) return null;

  return (
    <span
      className="strategy-pill"
      style={{
        display: 'inline-block',
        fontSize: 9,
        fontWeight: 700,
        padding: '2px 5px',
        borderRadius: 3,
        margin: '0 1px',
        cursor: 'default',
        position: 'relative',
        backgroundColor: cfg.bg,
        color: cfg.text,
        fontFamily: 'monospace',
      }}
    >
      {cfg.abbr}
      <span
        className="pill-tooltip"
        style={{
          display: 'none',
          position: 'absolute',
          bottom: '100%',
          left: '50%',
          transform: 'translateX(-50%)',
          backgroundColor: 'var(--bg3, #21262d)',
          border: '1px solid var(--border, #30363d)',
          fontSize: 9,
          fontWeight: 400,
          padding: '3px 8px',
          borderRadius: 3,
          whiteSpace: 'nowrap',
          marginBottom: 4,
          zIndex: 10,
          color: 'var(--text, #e6edf3)',
          pointerEvents: 'none',
        }}
      >
        {cfg.fullName}
      </span>
      <style>{`
        .strategy-pill:hover .pill-tooltip { display: block !important; }
      `}</style>
    </span>
  );
}
