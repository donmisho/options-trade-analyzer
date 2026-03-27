/**
 * ProbabilityMatrix — Renders a Black-Scholes probability grid.
 *
 * OTA-156 / OTA-157: Transposed layout — strikes as rows, dates as columns.
 * OTA-295: Zone color coding, cumulative probability column, time exit column,
 *          highlighted rows for breakeven / profit target / stop-loss.
 *
 * Columns: date snapshots (Exp-9, Exp-6, Exp-3, Expiration) + Time Exit + Cumulative
 * Rows:    price/strike levels (leftmost column = STRIKE)
 * Cells:   probability as %, red/amber/green gradient, white bold text
 *
 * Props:
 *   matrix          — { price_levels: number[], dates: string[], matrix: number[][] }
 *   tradeStructure  — optional { spread_type, short_strike, long_strike }
 *   currentPrice    — float
 *   breakeven       — optional number  (for zone classification & row highlight)
 *   profitTarget    — optional number  (row highlight)
 *   stopLoss        — optional number  (row highlight)
 *   timeExitProbs   — optional number[] (probabilities for the time-exit column)
 */

import { formatDate } from '../utils/formatDate';
import { C, mono } from '../styles/tokens';

// ─── Design system colors ─────────────────────────────────────────────────────

const EMERALD = '#00C896';
const AMBER   = '#F5A623';
const DANGER  = '#F85149';

// ─── Date snapshot labels ─────────────────────────────────────────────────────

const DATE_LABELS = ['Exp-9', 'Exp-6', 'Exp-3', 'Expiration'];

// ─── OTA-295: detailed zone classification (4 zones) ─────────────────────────

/**
 * Returns one of: 'profit-zone' | 'partial-profit' | 'loss-zone' | 'max-loss' | null
 * Uses direction derived from spread_type + breakeven to classify each price level.
 */
function getDetailedZone(price, spread_type, long_strike, short_strike, breakeven) {
  if (long_strike == null || short_strike == null || breakeven == null || !spread_type) return null;

  const st      = (spread_type ?? '').toUpperCase();
  const bearish = st.includes('BEAR');

  if (bearish) {
    // Profit when price FALLS
    const maxLossStrike   = Math.max(long_strike, short_strike);
    const maxProfitStrike = Math.min(long_strike, short_strike);

    if (price >= maxLossStrike)   return 'max-loss';
    if (price >= breakeven)       return 'loss-zone';
    if (price >= maxProfitStrike) return 'partial-profit';
    return 'profit-zone';
  } else {
    // Profit when price RISES
    const maxLossStrike   = Math.min(long_strike, short_strike);
    const maxProfitStrike = Math.max(long_strike, short_strike);

    if (price <= maxLossStrike)   return 'max-loss';
    if (price <= breakeven)       return 'loss-zone';
    if (price <= maxProfitStrike) return 'partial-profit';
    return 'profit-zone';
  }
}

// ─── Legacy zone classification (backward compat, no breakeven) ───────────────

function getLegacyZone(price, tradeStructure) {
  if (!tradeStructure) return null;
  const { spread_type, short_strike, long_strike } = tradeStructure;
  if (short_strike == null || long_strike == null) return null;

  switch ((spread_type ?? '').toLowerCase().replace(/_debit|_credit/gi, '')) {
    case 'bull_put':
    case 'bear_put': {
      const hi = Math.max(short_strike, long_strike);
      const lo = Math.min(short_strike, long_strike);
      if (price >= hi) return 'legacy-profit';
      if (price <= lo) return 'legacy-loss';
      return 'legacy-partial';
    }
    case 'bear_call':
    case 'bull_call': {
      const lo = Math.min(short_strike, long_strike);
      const hi = Math.max(short_strike, long_strike);
      if (price <= lo) return 'legacy-profit';
      if (price >= hi) return 'legacy-loss';
      return 'legacy-partial';
    }
    default:
      return null;
  }
}

// ─── Zone row styles ─────────────────────────────────────────────────────────

const ZONE_ROW_STYLE = {
  // OTA-295 detailed zones
  'profit-zone':    { backgroundColor: `rgba(0, 200, 150, 0.10)` },
  'partial-profit': { backgroundColor: `rgba(0, 200, 150, 0.04)` },
  'loss-zone':      { backgroundColor: `rgba(245, 166, 35, 0.07)` },
  'max-loss':       { backgroundColor: `rgba(248, 81, 73, 0.07)` },
  // Legacy zones (outline-based, for backward compat)
  'legacy-profit':  { outline: `1px solid ${C.green}44` },
  'legacy-loss':    { outline: `1px solid ${C.red}44` },
  'legacy-partial': { outline: `1px solid ${C.amber}33` },
};

// ─── Row highlight classification ─────────────────────────────────────────────

const HIGHLIGHT_TOL = 5; // within $5 of target → highlight that row

function getHighlightType(price, breakeven, profitTarget, stopLoss) {
  if (profitTarget != null && Math.abs(price - profitTarget) < HIGHLIGHT_TOL) return 'profitTarget';
  if (stopLoss    != null && Math.abs(price - stopLoss)    < HIGHLIGHT_TOL) return 'stopLoss';
  if (breakeven   != null && Math.abs(price - breakeven)   < HIGHLIGHT_TOL) return 'breakeven';
  return null;
}

const HIGHLIGHT_BORDER = {
  profitTarget: `3px solid ${EMERALD}`,
  stopLoss:     `3px solid ${DANGER}`,
  breakeven:    `3px solid ${AMBER}`,
};

// ─── OTA-157: Color gradient (red → amber → green) ────────────────────────────

function getProbabilityColor(prob) {
  if (prob >= 0.60) return 'rgba(0, 200, 150, 0.25)';   // emerald teal — high probability
  if (prob >= 0.30) return 'rgba(245, 166, 35, 0.15)';  // apricot amber — medium probability
  return 'transparent';                                  // low probability
}

// ─── Time exit date helper ────────────────────────────────────────────────────

/** Returns the ISO date string for expiry - 7 calendar days, or null. */
function computeTimeExitDate(expiryDateStr) {
  if (!expiryDateStr) return null;
  const d = new Date(expiryDateStr);
  if (isNaN(d.getTime())) return null;
  d.setDate(d.getDate() - 7);
  return d.toISOString();
}

// ─── Cumulative probability (profit direction) ────────────────────────────────

/**
 * Given price_levels and a probability array (one value per level, from expiry column),
 * compute the cumulative probability in the profit direction.
 *
 * For bearish spreads: cumulative = P(price ≤ level)  (sum from low to level)
 * For bullish spreads: cumulative = P(price ≥ level)  (sum from high to level)
 */
function computeCumulative(price_levels, expiryProbs, bearish) {
  const n = price_levels.length;
  if (!n || !expiryProbs) return new Array(n).fill(null);

  // Build sorted index pairs
  const pairs = price_levels.map((price, i) => ({ price, prob: expiryProbs[i] ?? 0, i }));
  pairs.sort((a, b) => a.price - b.price);   // low → high

  const cumulative = new Array(n).fill(0);

  if (bearish) {
    // Profit when price is low — cumulative from low end
    let sum = 0;
    for (const { prob, i } of pairs) {
      sum += prob;
      cumulative[i] = sum;
    }
  } else {
    // Profit when price is high — cumulative from high end
    let sum = 0;
    for (const { prob, i } of [...pairs].reverse()) {
      sum += prob;
      cumulative[i] = sum;
    }
  }

  return cumulative;
}

// ─── Subcomponents ────────────────────────────────────────────────────────────

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

function TimeExitHeaderCell({ date }) {
  return (
    <th
      style={{
        padding: '5px 8px',
        fontFamily: mono,
        fontSize: 9,
        fontWeight: 400,
        color: AMBER,
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
      {date ? formatDate(date) : '—'}
      <div style={{ fontSize: 8, color: `${AMBER}99`, marginTop: 1 }}>
        Time Exit
      </div>
    </th>
  );
}

function CumulativeHeaderCell() {
  return (
    <th
      style={{
        padding: '5px 8px',
        fontFamily: mono,
        fontSize: 9,
        fontWeight: 400,
        color: EMERALD,
        textAlign: 'center',
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
        whiteSpace: 'nowrap',
        backgroundColor: '#21262d',
        borderBottom: '1px solid #30363d',
        borderLeft: '1px solid rgba(255,255,255,0.10)',
        minWidth: 70,
      }}
    >
      Cum. Prob
      <div style={{ fontSize: 8, color: `${EMERALD}99`, marginTop: 1 }}>
        Profit Dir.
      </div>
    </th>
  );
}

function StrikeCell({ price, isCurrent, highlightType }) {
  const leftBorder = highlightType ? HIGHLIGHT_BORDER[highlightType] : undefined;
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
        borderLeft: leftBorder ?? '3px solid transparent',
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
      {highlightType === 'breakeven' && !isCurrent && (
        <div style={{ fontSize: 7, color: AMBER, letterSpacing: '0.03em', marginTop: 1 }}>
          BE
        </div>
      )}
      {highlightType === 'profitTarget' && !isCurrent && (
        <div style={{ fontSize: 7, color: EMERALD, letterSpacing: '0.03em', marginTop: 1 }}>
          TARGET
        </div>
      )}
      {highlightType === 'stopLoss' && !isCurrent && (
        <div style={{ fontSize: 7, color: DANGER, letterSpacing: '0.03em', marginTop: 1 }}>
          STOP
        </div>
      )}
    </td>
  );
}

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

function CumulativeCell({ prob }) {
  if (prob == null) {
    return (
      <td style={{
        padding: '4px 6px',
        textAlign: 'center',
        fontFamily: mono,
        fontSize: 10,
        color: '#555b6e',
        border: '1px solid rgba(255,255,255,0.06)',
        borderLeft: '1px solid rgba(255,255,255,0.10)',
      }}>—</td>
    );
  }
  const pct = (prob * 100).toFixed(1) + '%';
  const color = prob >= 0.50 ? EMERALD : prob >= 0.30 ? AMBER : '#8b90a0';
  return (
    <td
      style={{
        padding: '4px 6px',
        textAlign: 'center',
        fontFamily: mono,
        fontSize: 10,
        fontWeight: 700,
        color,
        backgroundColor: prob >= 0.50
          ? 'rgba(0, 200, 150, 0.08)'
          : prob >= 0.30
          ? 'rgba(245, 166, 35, 0.06)'
          : 'transparent',
        border: '1px solid rgba(255,255,255,0.06)',
        borderLeft: '1px solid rgba(255,255,255,0.10)',
        whiteSpace: 'nowrap',
      }}
    >
      {pct}
    </td>
  );
}

// ─── Legend ───────────────────────────────────────────────────────────────────

function Legend({ hasDetailedZones, hasLegacyZones, showTimeExit, showCumulative }) {
  return (
    <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap', marginTop: 8 }}>
      <LegendItem color='rgba(0,200,150,1)'   label="≥60% probability" />
      <LegendItem color='rgba(245,166,35,1)'  label="30–59% probability" />
      <LegendItem color={C.textDim}           label="<30% probability" dim />
      {hasDetailedZones && (
        <>
          <LegendItem color={EMERALD}  label="Profit zone"    fill />
          <LegendItem color={AMBER}    label="Partial profit" fill dim />
          <LegendItem color={AMBER}    label="Loss zone"      fill />
          <LegendItem color={DANGER}   label="Max loss"       fill />
        </>
      )}
      {hasLegacyZones && !hasDetailedZones && (
        <>
          <LegendItem color={C.green}  label="Profit zone"  border />
          <LegendItem color={C.amber}  label="Partial loss" border />
          <LegendItem color={C.red}    label="Max loss zone" border />
        </>
      )}
      <LegendItem color='#2dd4bf'  label="Current price" accent />
      {showCumulative && (
        <LegendItem color={EMERALD} label="Cumulative (profit dir.)" />
      )}
      {showTimeExit && (
        <LegendItem color={AMBER} label="Time exit col." />
      )}
    </div>
  );
}

function LegendItem({ color, label, dim, border, accent, fill }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <div style={{
        width: 12,
        height: 12,
        borderRadius: 2,
        backgroundColor: fill
          ? `${color}25`
          : dim
          ? 'transparent'
          : accent
          ? `${color}20`
          : `${color}30`,
        border: `2px solid ${color}${border || accent ? '88' : fill ? '60' : '60'}`,
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

export default function ProbabilityMatrix({
  matrix,
  tradeStructure = null,
  currentPrice,
  breakeven     = null,
  profitTarget  = null,
  stopLoss      = null,
  timeExitProbs = null,
}) {
  if (!matrix || !matrix.price_levels || !matrix.matrix) {
    return <Placeholder message="No probability data" />;
  }

  const { price_levels, dates, matrix: rows } = matrix;

  if (price_levels.length === 0 || rows.length === 0) {
    return <Placeholder message="Probability matrix is empty" />;
  }

  // ── Date snapshot labels ───────────────────────────────────────────────────

  const numDates  = rows.length;
  const dateLabels = rows.map((_, i) => {
    const labelIdx = i + (4 - numDates);
    return DATE_LABELS[Math.max(0, labelIdx)] ?? `T${i}`;
  });

  // ── Current price index ───────────────────────────────────────────────────

  const currentIdx = price_levels.reduce(
    (best, p, i) =>
      Math.abs(p - currentPrice) < Math.abs(price_levels[best] - currentPrice) ? i : best,
    0
  );

  // ── Zone classification ───────────────────────────────────────────────────

  const useDetailedZones = !!(
    tradeStructure?.spread_type &&
    tradeStructure?.long_strike != null &&
    tradeStructure?.short_strike != null &&
    breakeven != null
  );

  const zones = price_levels.map(p =>
    useDetailedZones
      ? getDetailedZone(
          p,
          tradeStructure.spread_type,
          tradeStructure.long_strike,
          tradeStructure.short_strike,
          breakeven
        )
      : getLegacyZone(p, tradeStructure)
  );

  const hasDetailedZones = useDetailedZones && zones.some(z => z !== null);
  const hasLegacyZones   = !useDetailedZones && zones.some(z => z !== null);

  // ── Time exit column ──────────────────────────────────────────────────────

  const expiryDate     = dates?.[dates.length - 1] ?? null;
  const timeExitDate   = computeTimeExitDate(expiryDate);
  const showTimeExit   = !!(timeExitDate);

  // ── Cumulative probability column ─────────────────────────────────────────

  const st       = (tradeStructure?.spread_type ?? '').toUpperCase();
  const bearish  = st.includes('BEAR');
  const expiryProbs   = rows[rows.length - 1] ?? null;
  const cumulative    = expiryProbs
    ? computeCumulative(price_levels, expiryProbs, bearish)
    : new Array(price_levels.length).fill(null);

  const showCumulative = !!(tradeStructure?.spread_type);

  // ── Table min-width ───────────────────────────────────────────────────────

  const extraCols = (showTimeExit ? 1 : 0) + (showCumulative ? 1 : 0);
  const tableMinWidth = `${70 * (numDates + extraCols) + 68}px`;

  return (
    <div>
      <div style={{
        overflowX: 'auto',
        border: '1px solid #30363d',
        borderRadius: 4,
        overflow: 'hidden',
      }}>
        <table style={{
          borderCollapse: 'collapse',
          width: '100%',
          minWidth: tableMinWidth,
        }}>
          <thead>
            <tr>
              {/* Strike column header */}
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

              {/* Date snapshot columns */}
              {dateLabels.map((label, di) => (
                <DateHeaderCell key={di} label={label} date={dates?.[di]} />
              ))}

              {/* Time exit column header (OTA-295c) */}
              {showTimeExit && <TimeExitHeaderCell date={timeExitDate} />}

              {/* Cumulative probability column header (OTA-295b) */}
              {showCumulative && <CumulativeHeaderCell />}
            </tr>
          </thead>

          <tbody>
            {price_levels.map((price, pi) => {
              const isCurrent    = pi === currentIdx;
              const zone         = zones[pi];
              const highlightType = getHighlightType(price, breakeven, profitTarget, stopLoss);

              return (
                <tr
                  key={pi}
                  style={zone ? ZONE_ROW_STYLE[zone] : undefined}
                >
                  <StrikeCell
                    price={price}
                    isCurrent={isCurrent}
                    highlightType={highlightType}
                  />

                  {/* Date snapshot probability cells */}
                  {rows.map((dateRow, di) => (
                    <ProbCell key={di} prob={dateRow[pi] ?? 0} />
                  ))}

                  {/* Time exit cell (OTA-295c) */}
                  {showTimeExit && (
                    <ProbCell prob={timeExitProbs?.[pi] ?? 0} />
                  )}

                  {/* Cumulative cell (OTA-295b) */}
                  {showCumulative && (
                    <CumulativeCell prob={cumulative[pi]} />
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <Legend
        hasDetailedZones={hasDetailedZones}
        hasLegacyZones={hasLegacyZones}
        showTimeExit={showTimeExit}
        showCumulative={showCumulative}
      />
    </div>
  );
}
