const sectionLabelStyle = {
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: '0.6px',
  color: 'var(--muted)',
  fontFamily: 'monospace',
  margin: '16px 0 8px',
};

function OutcomeCell({ label, value, valueColor, badge }) {
  return (
    <div
      style={{
        flex: 1,
        padding: '12px 14px',
        borderLeft: '1px solid var(--border)',
        fontFamily: 'monospace',
      }}
    >
      <div
        style={{
          fontSize: 9,
          textTransform: 'uppercase',
          letterSpacing: '0.3px',
          color: 'var(--muted)',
          marginBottom: 4,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 16,
          fontWeight: 700,
          color: valueColor || 'var(--text)',
        }}
      >
        {value}
      </div>
      {badge && (
        <div
          style={{
            fontSize: 9,
            fontWeight: 700,
            padding: '3px 8px',
            borderRadius: 3,
            display: 'inline-block',
            marginTop: 4,
            background: badge.bg,
            color: badge.color,
          }}
        >
          {badge.text}
        </div>
      )}
    </div>
  );
}

export default function SectionC({ outcome }) {
  if (!outcome) return null;

  const {
    pMaxProfit,
    pBreakeven,
    pPartial,
    pMaxLoss,
    expectedValue,
    evPctRisk,
  } = outcome;

  const ev = Number(expectedValue ?? 0);
  const evPct = Number(evPctRisk ?? 0);
  const evColor = ev >= 0 ? 'var(--green)' : 'var(--red)';
  const evSign = ev >= 0 ? '+' : '';
  const evBadge =
    evPct > 0
      ? { text: 'POSITIVE EV', bg: 'rgba(74,222,128,0.1)', color: 'var(--green)' }
      : { text: 'NEGATIVE EV', bg: 'rgba(248,113,113,0.1)', color: 'var(--red)' };

  function pct(v) {
    return v != null ? `${Number(v).toFixed(2)}%` : '—';
  }

  return (
    <div>
      <div style={sectionLabelStyle}>OUTCOME SUMMARY</div>
      <div
        style={{
          display: 'flex',
          gap: 1,
          border: '1px solid var(--border)',
          borderRadius: 4,
          overflow: 'hidden',
          marginBottom: 12,
        }}
      >
        {/* First cell has no border-left */}
        <div
          style={{
            flex: 1,
            padding: '12px 14px',
            fontFamily: 'monospace',
          }}
        >
          <div
            style={{
              fontSize: 9,
              textTransform: 'uppercase',
              letterSpacing: '0.3px',
              color: 'var(--muted)',
              marginBottom: 4,
            }}
          >
            P(MAX PROFIT)
          </div>
          <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--green)' }}>
            {pct(pMaxProfit)}
          </div>
        </div>

        <OutcomeCell
          label="P(BREAKEVEN OR BETTER)"
          value={pct(pBreakeven)}
          valueColor="var(--green)"
        />
        <OutcomeCell label="P(PARTIAL PROFIT)" value={pct(pPartial)} />
        <OutcomeCell
          label="P(MAX LOSS)"
          value={pct(pMaxLoss)}
          valueColor="var(--red)"
        />
        <OutcomeCell
          label="EXPECTED VALUE"
          value={expectedValue != null ? `${evSign}${ev.toFixed(2)}` : '—'}
          valueColor={evColor}
        />
        <OutcomeCell
          label="EV % OF RISK"
          value={evPctRisk != null ? `${Number(evPctRisk).toFixed(2)}%` : '—'}
          badge={evBadge}
        />
      </div>
    </div>
  );
}
