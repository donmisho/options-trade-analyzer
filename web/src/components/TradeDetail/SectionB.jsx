const sectionLabelStyle = {
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: '0.6px',
  color: 'var(--muted)',
  fontFamily: 'monospace',
  margin: '16px 0 8px',
};

const thStyle = {
  fontSize: 9,
  textTransform: 'uppercase',
  letterSpacing: '0.4px',
  color: 'var(--muted)',
  padding: '6px 8px',
  textAlign: 'right',
  fontWeight: 400,
  borderBottom: '1px solid var(--border)',
  fontFamily: 'monospace',
};

const thLeftStyle = { ...thStyle, textAlign: 'left' };

const tdStyle = {
  fontSize: 11,
  padding: '6px 8px',
  textAlign: 'right',
  borderBottom: '1px solid rgba(48,54,61,0.3)',
  fontFamily: 'monospace',
};

const tdLeftStyle = { ...tdStyle, textAlign: 'left' };

function formatPnl(value) {
  if (value == null) return '—';
  const n = Number(value);
  const sign = n >= 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}`;
}

function formatPnlPct(value) {
  if (value == null) return '—';
  const n = Number(value);
  const sign = n >= 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}%`;
}

function ExitSignalBadge({ signal }) {
  if (!signal) return null;
  const map = {
    'MAX PROFIT': 'var(--green)',
    BREAKEVEN: 'var(--amber)',
    STOP: 'var(--red)',
    'TIME EXIT': 'var(--muted)',
  };
  const upper = signal.toUpperCase();
  const color = map[upper] || 'var(--muted)';
  return (
    <span
      style={{
        fontSize: 9,
        fontWeight: 700,
        letterSpacing: '0.3px',
        color,
        fontFamily: 'monospace',
      }}
    >
      {upper}
    </span>
  );
}

import { useState } from 'react';

export default function SectionB({ scenarios = [], totalEV }) {
  const [showFullTable, setShowFullTable] = useState(false);
  const keyRows = scenarios.filter(r => r.exitSignal);
  const displayRows = showFullTable ? scenarios : keyRows;

  return (
    <div>
      <div style={sectionLabelStyle}>EXIT SCENARIO ANALYSIS</div>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={thLeftStyle}>Underlying Price</th>
            <th style={thStyle}>Spread Value</th>
            <th style={thStyle}>P&amp;L / Contract</th>
            <th style={thStyle}>P&amp;L %</th>
            <th style={thStyle}>Probability</th>
            <th style={thStyle}>Expected Value</th>
            <th style={thStyle}>Exit Signal</th>
          </tr>
        </thead>
        <tbody>
          {displayRows.map((row, i) => {
            const pnl = Number(row.pnl ?? 0);
            const ev = Number(row.expectedValue ?? 0);
            const isLoss = pnl < 0;
            const pnlColor = pnl >= 0 ? 'var(--green)' : 'var(--red)';
            const evColor = ev >= 0 ? 'var(--green)' : 'var(--red)';
            return (
              <tr
                key={i}
                style={isLoss ? { background: 'rgba(248,113,113,0.03)' } : {}}
              >
                <td style={tdLeftStyle}>
                  {row.price != null ? Number(row.price).toFixed(2) : '—'}
                </td>
                <td style={tdStyle}>
                  {row.spreadValue != null ? Number(row.spreadValue).toFixed(2) : '—'}
                </td>
                <td style={{ ...tdStyle, color: pnlColor }}>{formatPnl(row.pnl)}</td>
                <td style={{ ...tdStyle, color: pnlColor }}>{formatPnlPct(row.pnlPct)}</td>
                <td style={tdStyle}>
                  {row.probability != null ? `${Number(row.probability).toFixed(2)}%` : '—'}
                </td>
                <td style={{ ...tdStyle, color: evColor }}>
                  {row.expectedValue != null ? Number(row.expectedValue).toFixed(2) : '—'}
                </td>
                <td style={{ ...tdStyle, textAlign: 'right' }}>
                  <ExitSignalBadge signal={row.exitSignal} />
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <td
              colSpan={5}
              style={{
                ...tdLeftStyle,
                fontWeight: 700,
                borderBottom: 'none',
              }}
            >
              Total expected value
            </td>
            <td
              style={{
                ...tdStyle,
                fontWeight: 700,
                color: totalEV != null && Number(totalEV) >= 0 ? 'var(--green)' : 'var(--red)',
                borderBottom: 'none',
              }}
            >
              {totalEV != null ? Number(totalEV).toFixed(2) : '—'}
            </td>
            <td style={{ ...tdStyle, borderBottom: 'none' }} />
          </tr>
        </tfoot>
      </table>
      {scenarios.length > keyRows.length && (
        <button
          onClick={() => setShowFullTable(p => !p)}
          style={{
            marginTop: 6,
            background: 'transparent',
            border: '1px solid #30363d',
            color: '#8b949e',
            padding: '4px 10px',
            borderRadius: 4,
            fontSize: 10,
            fontFamily: 'monospace',
            cursor: 'pointer',
          }}
        >
          {showFullTable ? 'Show key exits ▲' : 'Show full analysis ▼'}
        </button>
      )}
    </div>
  );
}
