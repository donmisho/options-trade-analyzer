/**
 * PositionHealthBadge — Letter grade indicator for position health.
 *
 * Colors sourced from HEALTH_GRADE_COLORS design tokens.
 * The engine emits only the letter; all color mapping lives here in the UI layer.
 */

import { HEALTH_GRADE_COLORS } from '../styles/tokens';

const GRADE_LABELS = {
  A: 'On track — no exit levels threatened',
  B: 'Slightly off plan — monitor closely',
  C: 'Approaching warning level',
  D: 'Warning level breached — consider exit',
  F: 'Hard stop hit or max loss — exit immediately',
};

export function PositionHealthBadge({ grade }) {
  const tokens = HEALTH_GRADE_COLORS[grade];
  if (!grade || !tokens) {
    return (
      <span style={{ color: '#5a6070', fontSize: 13, fontFamily: 'monospace' }}>—</span>
    );
  }

  const { color, bg } = tokens;
  const label = GRADE_LABELS[grade];

  return (
    <span
      title={`Grade ${grade}: ${label}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 26,
        height: 26,
        borderRadius: 4,
        background: bg,
        border: `1px solid ${color}40`,
        color,
        fontFamily: 'monospace',
        fontWeight: 700,
        fontSize: 13,
        cursor: 'default',
        userSelect: 'none',
      }}
    >
      {grade}
    </span>
  );
}
