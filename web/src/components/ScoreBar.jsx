/**
 * ScoreBar — Visual indicator for 0–1 composite scores.
 *
 * WHY color-coded?
 * At a glance you can tell good (green, >0.7) from okay
 * (cyan/yellow, 0.5–0.7) from weak (orange/red, <0.5).
 * The numeric value is always visible for precision.
 */

import './ScoreBar.css';

function getBarColor(score) {
  if (score >= 0.75) return 'var(--accent-green)';
  if (score >= 0.55) return 'var(--accent-cyan)';
  if (score >= 0.40) return 'var(--accent-yellow)';
  return 'var(--accent-orange)';
}

export default function ScoreBar({ score }) {
  const pct = Math.round(score * 100);
  return (
    <div className="score-bar-wrap">
      <div className="score-bar-track">
        <div
          className="score-bar-fill"
          style={{ width: `${pct}%`, background: getBarColor(score) }}
        />
      </div>
      <span className="score-bar-val">{score.toFixed(2)}</span>
    </div>
  );
}
