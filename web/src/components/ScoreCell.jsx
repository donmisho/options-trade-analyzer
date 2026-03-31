/**
 * ScoreCell — Score bar + number in a flex row.
 *
 * Props:
 *   score — number 0-100
 *
 * Bar: 50px wide, 4px tall. Fill color and number color by threshold:
 *   70-100: var(--green)
 *   40-69:  var(--amber)
 *   0-39:   var(--red)
 *
 * Format: always ##.00 via .toFixed(2)
 */

function scoreColor(score) {
  if (score >= 70) return 'var(--green, #4ade80)';
  if (score >= 40) return 'var(--amber, #f59e0b)';
  return 'var(--red, #f87171)';
}

export default function ScoreCell({ score }) {
  const s = score ?? 0;
  const color = scoreColor(s);
  const clampedPct = Math.min(100, Math.max(0, s));

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{
        width: 50, height: 4,
        backgroundColor: 'var(--bg3, #21262d)',
        borderRadius: 2, overflow: 'hidden', flexShrink: 0,
      }}>
        <div style={{
          height: '100%',
          width: `${clampedPct}%`,
          backgroundColor: color,
          borderRadius: 2,
        }} />
      </div>
      <span style={{
        fontSize: 11, fontWeight: 700,
        minWidth: 36, color,
        fontFamily: 'monospace',
      }}>
        {s.toFixed(2)}
      </span>
    </div>
  );
}
