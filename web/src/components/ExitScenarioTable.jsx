/**
 * ExitScenarioTable — OTA-293
 *
 * Tabular view of exit scenarios with zone color coding and EV footer.
 * Stateless — pure display, all data via props.
 *
 * Props:
 *   rows     — ExitScenarioRow[]
 *   totalEV  — number  (sum of all EV column values)
 *
 * Row shape:
 *   { underlying_price, spread_value, pl_per_contract, pl_pct,
 *     probability, expected_value, exit_signal, zone }
 *
 * Zone values: 'profit-zone' | 'entry' | 'warning-zone' | 'max-loss'
 */

import { mono } from '../styles/tokens';

// ─── Design system colors ─────────────────────────────────────────────────────

const EMERALD = '#00C896';
const AMBER   = '#F5A623';
const DANGER  = '#F85149';

// ─── Zone styles ─────────────────────────────────────────────────────────────

const ZONE_ROW = {
  'profit-zone':  {
    bg:     'rgba(0, 200, 150, 0.07)',
    accent: `3px solid rgba(0, 200, 150, 0.30)`,
  },
  'entry':        { bg: 'transparent', accent: '3px solid transparent' },
  'warning-zone': {
    bg:     'rgba(245, 166, 35, 0.07)',
    accent: `3px solid rgba(245, 166, 35, 0.30)`,
  },
  'max-loss':     {
    bg:     'rgba(248, 81, 73, 0.07)',
    accent: `3px solid rgba(248, 81, 73, 0.30)`,
  },
};

// ─── Formatting helpers ───────────────────────────────────────────────────────

function fmtSigned(val, decimals = 2) {
  if (val == null) return '—';
  const sign = val >= 0 ? '+' : '';
  return `${sign}${Number(val).toFixed(decimals)}`;
}

function fmtPct(val) {
  if (val == null) return '—';
  const sign = val >= 0 ? '+' : '';
  return `${sign}${(val * 100).toFixed(2)}%`;
}

function fmtProb(val) {
  if (val == null) return '—';
  return `${(val * 100).toFixed(2)}%`;
}

// ─── Column definitions ───────────────────────────────────────────────────────

const COLS = [
  { key: 'underlying_price', label: 'Underlying Price', align: 'left' },
  { key: 'spread_value',     label: 'Spread Value',     align: 'right' },
  { key: 'pl_per_contract',  label: 'P&L / Contract',   align: 'right' },
  { key: 'pl_pct',           label: 'P&L %',            align: 'right' },
  { key: 'probability',      label: 'Probability',      align: 'right' },
  { key: 'expected_value',   label: 'Expected Value',   align: 'right' },
  { key: 'exit_signal',      label: 'Exit Signal',      align: 'right' },
];

const thBase = {
  padding: '6px 10px',
  color: '#8b949e',
  fontWeight: 400,
  fontSize: 9,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  borderBottom: '1px solid #30363d',
  backgroundColor: '#21262d',
  whiteSpace: 'nowrap',
  fontFamily: mono,
};

const tdBase = {
  padding: '5px 10px',
  borderBottom: '1px solid rgba(255,255,255,0.04)',
  fontSize: 11,
  fontFamily: mono,
  whiteSpace: 'nowrap',
};

// ─── Main component ───────────────────────────────────────────────────────────

export default function ExitScenarioTable({ rows = [], totalEV }) {
  return (
    <div style={{ overflowX: 'auto', border: '1px solid #30363d', borderRadius: 6, overflow: 'hidden' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 640 }}>
        <thead>
          <tr>
            {COLS.map(c => (
              <th key={c.key} style={{ ...thBase, textAlign: c.align }}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {rows.map((row, i) => {
            const zone   = ZONE_ROW[row.zone] ?? ZONE_ROW['entry'];
            const plPos  = row.pl_per_contract != null && row.pl_per_contract >= 0;
            const evPos  = row.expected_value  != null && row.expected_value  >= 0;
            const plPctPos = row.pl_pct != null && row.pl_pct >= 0;

            return (
              <tr key={i} style={{ backgroundColor: zone.bg }}>
                {/* Underlying price — left border carries zone accent */}
                <td style={{
                  ...tdBase,
                  textAlign: 'left',
                  color: '#c9d1d9',
                  borderLeft: zone.accent,
                }}>
                  {row.underlying_price != null ? Number(row.underlying_price).toFixed(2) : '—'}
                </td>

                <td style={{ ...tdBase, textAlign: 'right', color: '#c9d1d9' }}>
                  {row.spread_value != null ? Number(row.spread_value).toFixed(2) : '—'}
                </td>

                <td style={{ ...tdBase, textAlign: 'right', color: plPos ? EMERALD : DANGER }}>
                  {fmtSigned(row.pl_per_contract)}
                </td>

                <td style={{ ...tdBase, textAlign: 'right', color: plPctPos ? EMERALD : DANGER }}>
                  {fmtPct(row.pl_pct)}
                </td>

                <td style={{ ...tdBase, textAlign: 'right', color: '#c9d1d9' }}>
                  {fmtProb(row.probability)}
                </td>

                <td style={{ ...tdBase, textAlign: 'right', color: evPos ? EMERALD : DANGER }}>
                  {fmtSigned(row.expected_value)}
                </td>

                <td style={{
                  ...tdBase,
                  textAlign: 'right',
                  fontWeight: row.exit_signal ? 700 : 400,
                  color: row.exit_signal ? '#e4e7ef' : '#555b6e',
                }}>
                  {row.exit_signal ?? ''}
                </td>
              </tr>
            );
          })}
        </tbody>

        <tfoot>
          <tr style={{ borderTop: '1px solid #30363d', backgroundColor: '#21262d' }}>
            <td
              colSpan={5}
              style={{
                ...tdBase,
                textAlign: 'left',
                fontWeight: 700,
                fontSize: 9,
                color: '#8b90a0',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                borderBottom: 'none',
              }}
            >
              Total Expected Value
            </td>
            <td style={{
              ...tdBase,
              textAlign: 'right',
              fontWeight: 700,
              fontSize: 12,
              color: totalEV != null && totalEV >= 0 ? EMERALD : DANGER,
              borderBottom: 'none',
            }}>
              {fmtSigned(totalEV)}
            </td>
            <td style={{ ...tdBase, borderBottom: 'none' }} />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
