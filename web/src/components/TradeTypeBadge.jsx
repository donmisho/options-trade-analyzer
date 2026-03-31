/**
 * TradeTypeBadge — Renders a trade type enum as a clean, human-readable badge.
 *
 * Props:
 *   type — raw enum string ("BEAR_PUT_DEBIT", "bull_call", etc.)
 *
 * Transform: replace underscores with spaces, apply title case.
 * Color: first word determines direction — BULL=green, BEAR=red.
 *
 * Font: 9px bold. Padding: 2px 6px. Border-radius: 3px.
 */

function toTitleCase(str) {
  return str
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

function getColor(type) {
  const first = (type || '').toUpperCase().split(/[_ ]/)[0];
  if (first === 'BULL' || first === 'LONG') {
    return { bg: 'rgba(74,222,128,0.15)', text: 'var(--green, #4ade80)' };
  }
  if (first === 'BEAR' || first === 'SHORT') {
    return { bg: 'rgba(248,113,113,0.15)', text: 'var(--red, #f87171)' };
  }
  return { bg: 'rgba(139,148,158,0.15)', text: 'var(--muted, #8b949e)' };
}

export default function TradeTypeBadge({ type }) {
  if (!type) return null;
  const { bg, text } = getColor(type);
  const label = toTitleCase(type);

  return (
    <span style={{
      display: 'inline-block',
      fontSize: 9,
      fontWeight: 700,
      padding: '2px 6px',
      borderRadius: 3,
      whiteSpace: 'nowrap',
      backgroundColor: bg,
      color: text,
      fontFamily: 'monospace',
    }}>
      {label}
    </span>
  );
}
