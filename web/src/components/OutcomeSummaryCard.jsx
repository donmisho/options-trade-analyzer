/**
 * OutcomeSummaryCard — OTA-294
 *
 * Compact card showing probability and EV metrics for a trade outcome.
 * Stateless — all values come as props.
 *
 * Props:
 *   p_max_profit           — number  0-1
 *   p_breakeven_or_better  — number  0-1
 *   p_max_loss             — number  0-1
 *   expected_value         — number  (with sign)
 *   ev_pct_of_risk         — number  0-1
 *
 * Computed client-side:
 *   p_partial_profit = p_breakeven_or_better - p_max_profit
 */

import { mono } from '../styles/tokens';

// ─── Design system colors ─────────────────────────────────────────────────────

const EMERALD = '#00C896';
const AMBER   = '#F5A623';
const DANGER  = '#F85149';

// ─── Formatting helpers ───────────────────────────────────────────────────────

function fmtPct(val) {
  if (val == null) return '—';
  return `${(val * 100).toFixed(2)}%`;
}

function fmtEV(val) {
  if (val == null) return '—';
  const sign = val >= 0 ? '+' : '';
  return `${sign}${Number(val).toFixed(2)}`;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function EVBadge({ negative }) {
  const color = negative ? AMBER : EMERALD;
  const label = negative ? 'Negative Expected Value' : 'Positive Expected Value';
  return (
    <span style={{
      fontFamily: mono,
      fontSize: 9,
      fontWeight: 700,
      color,
      border: `1px solid ${color}55`,
      borderRadius: 3,
      padding: '2px 8px',
      textTransform: 'uppercase',
      letterSpacing: '0.06em',
      whiteSpace: 'nowrap',
    }}>
      {label}
    </span>
  );
}

function Metric({ label, value, color }) {
  return (
    <div>
      <div style={{
        fontFamily: mono,
        fontSize: 8,
        color: '#555b6e',
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        marginBottom: 3,
      }}>
        {label}
      </div>
      <div style={{
        fontFamily: mono,
        fontSize: 14,
        fontWeight: 700,
        color: color ?? '#c9d1d9',
      }}>
        {value}
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function OutcomeSummaryCard({
  p_max_profit,
  p_breakeven_or_better,
  p_max_loss,
  expected_value,
  ev_pct_of_risk,
}) {
  const p_partial_profit =
    p_breakeven_or_better != null && p_max_profit != null
      ? p_breakeven_or_better - p_max_profit
      : null;

  const isNegEV = expected_value != null && expected_value < 0;

  return (
    <div style={{
      backgroundColor: '#0D1117',
      border: '1px solid #252a3a',
      borderRadius: 6,
      padding: '12px 16px',
    }}>
      {/* ── Header ──────────────────────────────────────────────── */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 14,
      }}>
        <span style={{
          fontFamily: mono,
          fontSize: 10,
          color: '#8b90a0',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
        }}>
          Outcome Summary
        </span>
        <EVBadge negative={isNegEV} />
      </div>

      {/* ── Metrics grid ────────────────────────────────────────── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '12px 20px',
      }}>
        <Metric
          label="P(Max Profit)"
          value={fmtPct(p_max_profit)}
          color={EMERALD}
        />
        <Metric
          label="P(Breakeven or Better)"
          value={fmtPct(p_breakeven_or_better)}
          color={EMERALD}
        />
        <Metric
          label="P(Partial Profit)"
          value={fmtPct(p_partial_profit)}
        />
        <Metric
          label="P(Max Loss)"
          value={fmtPct(p_max_loss)}
          color={DANGER}
        />
        <Metric
          label="Expected Value"
          value={fmtEV(expected_value)}
          color={isNegEV ? AMBER : EMERALD}
        />
        <Metric
          label="EV % of Risk"
          value={fmtPct(ev_pct_of_risk)}
          color={isNegEV ? AMBER : EMERALD}
        />
      </div>
    </div>
  );
}
