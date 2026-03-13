/**
 * PositionHealthBadge — Letter grade indicator for position health.
 *
 * Grade → Color:
 *   A = green  (#22c55e) — On track, no levels threatened
 *   B = teal   (#14b8a6) — Slightly off but recoverable
 *   C = yellow (#eab308) — Warning level approaching
 *   D = orange (#f97316) — Warning level breached
 *   F = red    (#ef4444) — Hard stop hit / max loss
 *   null/undefined = gray dash
 */

const GRADE_CONFIG = {
  A: { color: '#22c55e', bg: 'rgba(34, 197, 94, 0.12)',  label: 'On track — no exit levels threatened' },
  B: { color: '#14b8a6', bg: 'rgba(20, 184, 166, 0.12)', label: 'Slightly off plan — monitor closely' },
  C: { color: '#eab308', bg: 'rgba(234, 179, 8, 0.12)',  label: 'Approaching warning level' },
  D: { color: '#f97316', bg: 'rgba(249, 115, 22, 0.12)', label: 'Warning level breached — consider exit' },
  F: { color: '#ef4444', bg: 'rgba(239, 68, 68, 0.12)',  label: 'Hard stop hit or max loss — exit immediately' },
};

export function PositionHealthBadge({ grade }) {
  if (!grade || !GRADE_CONFIG[grade]) {
    return (
      <span style={{ color: '#5a6070', fontSize: 13, fontFamily: 'monospace' }}>—</span>
    );
  }

  const { color, bg, label } = GRADE_CONFIG[grade];

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
