/**
 * ProbabilityMatrix — Renders a Black-Scholes probability grid.
 *
 * OTA-156 / OTA-157: Transposed layout — strikes as rows, dates as columns.
 *
 * Columns: date snapshots (Exp-9, Exp-6, Exp-3, Expiration)
 * Rows:    price/strike levels (leftmost column = STRIKE)
 * Cells:   probability as %, red/amber/green gradient, white bold text
 *
 * For credit spreads the profitable zone (price outside the spread) gets a
 * subtle green border; the max-loss zone gets a subtle red border.
 *
 * Props:
 *   matrix         — { price_levels: number[], dates: string[], matrix: number[][] }
 *   tradeStructure — optional { spread_type, short_strike, long_strike }
 *   currentPrice   — float
 */

import { C, mono } from '../styles/tokens';

// ─── Date snapshot labels ─────────────────────────────────────────────────────

const DATE_LABELS = ['Exp-9', 'Exp-6', 'Exp-3', 'Expiration'];

/** mm-dd-yyyy (house rule). */
const formatDate = (dateStr) => {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const yyyy = d.getFullYear();
  return `${mm}-${dd}-${yyyy}`;
};

// ─── Zone classification (price-based, same as before) ────────────────────────

function getPriceZone(price, tradeStructure) {
  if (!tradeStructure) return null;
  const { spread_type, short_strike, long_strike } = tradeStructure;
  if (short_strike == null || long_strike == null) return null;

  switch (spread_type) {
    case 'bull_put':
    case 'bear_put': {
      const hi = Math.max(short_strike, long_strike);
      const lo = Math.min(short_strike, long_strike);
      if (price >= hi) return 'profit';
      if (price <= lo) return 'loss';
      return 'partial';
    }
    case 'bear_call':
    case 'bull_call': {
      const lo = Math.min(short_strike, long_strike);
      const hi = Math.max(short_strike, long_strike);
      if (price <= lo) return 'profit';
      if (price >= hi) return 'loss';
      return 'partial';
    }
    default:
      return null;
  }
}

// ─── OTA-157: Color gradient (red → amber → green) ───────────────────────────

function getProbabilityColor(prob) {
  if (prob >= 0.60) return 'rgba(0, 200, 150, 0.25)';    // emerald teal — high probability
  if (prob >= 0.30) return 'rgba(245, 166, 35, 0.15)';   // apricot amber — medium probability
  return 'transparent';                                   // low probability — no background
}

// ─── Zone overlay borders ─────────────────────────────────────────────────────

const ZONE_ROW_STYLE = {
  profit:  { outline: `1px solid ${C.green}44` },
  loss:    { outline: `1px solid ${C.red}44` },
  partial: { outline: `1px solid ${C.amber}33` },
};

// ─── Subcomponents ────────────────────────────────────────────────────────────

/** Date column header (Exp-9, Exp-6, Exp-3, Expiration) */
function DateHeaderCell({ label, date }) {
  return (
    <th
      style={{
        padding: '5px 8px',
        fontFamily: mono,
        fontSize: 9,
        fontWeight: 400,
        color: '#8b949e',
        textAlign: 'center',
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
        whiteSpace: 'nowrap',
        backgroundColor: '#21262d',
        borderBottom: '1px solid #30363d',
        borderLeft: '1px solid rgba(255,255,255,0.06)',
        minWidth: 70,
      }}
    >
      {date ? formatDate(date) : label}
      <div style={{ fontSize: 8, color: '#555b6e', marginTop: 1 }}>
        {label}
      </div>
    </th>
  );
}

/** Leftmost strike price cell (row label). */
function StrikeCell({ price, isCurrent }) {
  return (
    <td
      style={{
        padding: '4px 8px',
        fontFamily: mono,
        fontSize: 10,
        fontWeight: isCurrent ? 700 : 400,
        color: isCurrent ? '#2dd4bf' : '#c9d1d9',
        backgroundColor: '#161b22',
        borderRight: '1px solid #30363d',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        whiteSpace: 'nowrap',
        textAlign: 'right',
        position: 'sticky',
        left: 0,
        zIndex: 1,
        minWidth: 60,
      }}
    >
      {price % 1 === 0 ? price.toFixed(0) : price.toFixed(1)}
      {isCurrent && (
        <div style={{ fontSize: 7, color: '#2dd4bf', letterSpacing: '0.03em', marginTop: 1 }}>
          NOW
        </div>
      )}
    </td>
  );
}

/** Probability cell — red/amber/green gradient, white bold text. */
function ProbCell({ prob }) {
  const pct = (prob * 100).toFixed(1) + '%';
  const bg  = getProbabilityColor(prob);

  return (
    <td
      style={{
        padding: '4px 6px',
        textAlign: 'center',
        fontFamily: mono,
        fontSize: 10,
        fontWeight: 700,
        color: '#c9d1d9',
        backgroundColor: bg,
        border: '1px solid rgba(255,255,255,0.06)',
        whiteSpace: 'nowrap',
      }}
    >
      {pct}
    </td>
  );
}

// ─── Legend ───────────────────────────────────────────────────────────────────

function Legend({ hasZones }) {
  return (
    <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap', marginTop: 8 }}>
      <LegendItem color='rgba(0,200,150,1)' label="≥60% probability" />
      <LegendItem color='rgba(245,166,35,1)' label="30–59% probability" />
      <LegendItem color={C.textDim} label="<30% probability" dim />
      {hasZones && (
        <>
          <LegendItem color={C.green} label="Profit zone" border />
          <LegendItem color={C.amber} label="Partial loss" border />
          <LegendItem color={C.red}   label="Max loss zone" border />
        </>
      )}
      <LegendItem color='#2dd4bf' label="Current price" accent />
    </div>
  );
}

function LegendItem({ color, label, dim, border, accent }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <div style={{
        width: 12,
        height: 12,
        borderRadius: 2,
        backgroundColor: dim ? 'transparent' : (accent ? `${color}20` : `${color}30`),
        border: `2px solid ${color}${border || accent ? '88' : '60'}`,
        flexShrink: 0,
      }} />
      <span style={{ fontSize: 10.5, color: C.textDim }}>{label}</span>
    </div>
  );
}

// ─── Empty / loading state ────────────────────────────────────────────────────

function Placeholder({ message }) {
  return (
    <div style={{
      padding: '24px 16px',
      textAlign: 'center',
      color: C.textMuted,
      fontSize: 12,
      border: `1px dashed ${C.border}`,
      borderRadius: 6,
      fontFamily: mono,
    }}>
      {message}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function ProbabilityMatrix({ matrix, tradeStructure = null, currentPrice }) {
  if (!matrix || !matrix.price_levels || !matrix.matrix) {
    return <Placeholder message="No probability data" />;
  }

  const { price_levels, dates, matrix: rows } = matrix;

  if (price_levels.length === 0 || rows.length === 0) {
    return <Placeholder message="Probability matrix is empty" />;
  }

  // Compute date snapshot labels (align to end so last = Expiration)
  const numDates = rows.length;
  const dateLabels = rows.map((_, i) => {
    const labelIdx = i + (4 - numDates);
    return DATE_LABELS[Math.max(0, labelIdx)] ?? `T${i}`;
  });

  // Find the price level index closest to currentPrice
  const currentIdx = price_levels.reduce(
    (best, p, i) =>
      Math.abs(p - currentPrice) < Math.abs(price_levels[best] - currentPrice) ? i : best,
    0
  );

  // Pre-compute zones and check if any zones are active
  const zones    = price_levels.map(p => getPriceZone(p, tradeStructure));
  const hasZones = zones.some(z => z !== null);

  return (
    <div>
      {/* Scrollable grid — OTA-157: border, border-radius, overflow hidden */}
      <div style={{
        overflowX: 'auto',
        border: '1px solid #30363d',
        borderRadius: 4,
        overflow: 'hidden',
      }}>
        <table style={{
          borderCollapse: 'collapse',
          width: '100%',
          minWidth: `${70 * numDates + 68}px`,
        }}>
          <thead>
            <tr>
              {/* Top-left corner — OTA-157: label "STRIKE" */}
              <th
                style={{
                  padding: '5px 8px',
                  textAlign: 'right',
                  fontSize: 9,
                  fontWeight: 400,
                  color: '#8b949e',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  fontFamily: mono,
                  borderBottom: '1px solid #30363d',
                  borderRight: '1px solid #30363d',
                  backgroundColor: '#21262d',
                  position: 'sticky',
                  left: 0,
                  zIndex: 2,
                  minWidth: 60,
                }}
              >
                Strike
              </th>
              {dateLabels.map((label, di) => (
                <DateHeaderCell
                  key={di}
                  label={label}
                  date={dates?.[di]}
                />
              ))}
            </tr>
          </thead>
          <tbody>
            {/* OTA-157 transposed: each ROW = a price level (strike) */}
            {price_levels.map((price, pi) => {
              const isCurrent = pi === currentIdx;
              const zone      = zones[pi];
              return (
                <tr
                  key={pi}
                  style={zone ? ZONE_ROW_STYLE[zone] : undefined}
                >
                  <StrikeCell price={price} isCurrent={isCurrent} />
                  {rows.map((dateRow, di) => (
                    <ProbCell
                      key={di}
                      prob={dateRow[pi] ?? 0}
                    />
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <Legend hasZones={hasZones} />
    </div>
  );
}
