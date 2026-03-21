/**
 * ProbabilityMatrix — Renders a Black-Scholes probability grid.
 *
 * Columns: price levels (left = lowest, right = highest; current price column highlighted)
 * Rows:    snapshot dates (Exp-9, Exp-6, Exp-3, Expiration)
 * Cells:   probability as %, colored by intensity (higher = deeper green)
 *
 * For credit spreads the profitable zone (price outside the spread) gets a
 * subtle green background overlay; the max-loss zone (price inside/past long
 * strike) gets a subtle red background overlay.
 *
 * Props:
 *   matrix         — { price_levels: number[], dates: string[], matrix: number[][] }
 *   tradeStructure — optional { spread_type, short_strike, long_strike }
 *   currentPrice   — float
 */

import { C, mono } from '../styles/tokens';

// ─── Date label helpers ───────────────────────────────────────────────────────

const DATE_LABELS = ['Exp-9', 'Exp-6', 'Exp-3', 'Expiration'];

/** Convert yyyy-mm-dd → mm-dd-yyyy (house rule: never show ISO order to users). */
function formatDateMMDDYYYY(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  if (!y || !m || !d) return iso;
  return `${m}-${d}-${y}`;
}

// ─── Profitable zone logic ────────────────────────────────────────────────────

/**
 * Returns a zone classification for a given price column.
 *  'profit'  — full max profit (outside the spread)
 *  'loss'    — full max loss   (inside spread, past long strike)
 *  'partial' — between short and long strike (partial loss)
 *  null      — no trade structure provided
 */
function getPriceZone(price, tradeStructure) {
  if (!tradeStructure) return null;
  const { spread_type, short_strike, long_strike } = tradeStructure;
  if (short_strike == null || long_strike == null) return null;

  switch (spread_type) {
    case 'bull_put':
    case 'bear_put': {
      // Sold higher put, bought lower put.
      // Max profit:  price >= short_strike
      // Partial loss: long_strike < price < short_strike
      // Max loss:    price <= long_strike
      const hi = Math.max(short_strike, long_strike);
      const lo = Math.min(short_strike, long_strike);
      if (price >= hi) return 'profit';
      if (price <= lo) return 'loss';
      return 'partial';
    }
    case 'bear_call':
    case 'bull_call': {
      // Sold lower call, bought higher call.
      // Max profit:  price <= short_strike
      // Partial loss: short_strike < price < long_strike
      // Max loss:    price >= long_strike
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

// ─── Cell color ───────────────────────────────────────────────────────────────

/**
 * Maps a probability (0–1) to an RGBA green with opacity scaled by intensity.
 * The scale is non-linear so low probs aren't invisible.
 */
function probToGreen(prob) {
  if (prob <= 0) return 'transparent';
  // sqrt scale so small probabilities are still somewhat visible
  const intensity = Math.sqrt(prob);
  const alpha = Math.min(0.85, intensity * 0.9);
  return `rgba(38, 166, 154, ${alpha.toFixed(3)})`; // C.green = #26a69a
}

/**
 * Text color — white when cell is dark (high prob), dimmed when light.
 */
function probToTextColor(prob) {
  return prob > 0.12 ? '#fff' : C.textMuted;
}

// ─── Zone overlay color ───────────────────────────────────────────────────────

const ZONE_STYLE = {
  profit:  { borderTop: `2px solid ${C.green}44`,  borderBottom: `2px solid ${C.green}44` },
  loss:    { borderTop: `2px solid ${C.red}44`,    borderBottom: `2px solid ${C.red}44` },
  partial: { borderTop: `2px solid ${C.amber}33`,  borderBottom: `2px solid ${C.amber}33` },
};

const ZONE_BG = {
  profit:  `${C.green}08`,
  loss:    `${C.red}08`,
  partial: `${C.amber}06`,
};

// ─── Subcomponents ────────────────────────────────────────────────────────────

function HeaderCell({ price, isCurrent, zone }) {
  return (
    <th
      style={{
        padding: '5px 6px',
        fontFamily: mono,
        fontSize: 10.5,
        fontWeight: isCurrent ? 700 : 400,
        color: isCurrent ? C.accent : C.textDim,
        textAlign: 'center',
        whiteSpace: 'nowrap',
        backgroundColor: isCurrent ? `${C.accent}18` : (zone ? ZONE_BG[zone] : 'transparent'),
        borderBottom: `1px solid ${C.border}`,
        borderLeft: isCurrent ? `1px solid ${C.accent}40` : `1px solid transparent`,
        borderRight: isCurrent ? `1px solid ${C.accent}40` : `1px solid transparent`,
        position: 'sticky',
        top: 0,
        zIndex: 1,
        minWidth: 52,
        ...(zone ? ZONE_STYLE[zone] : {}),
      }}
    >
      {price % 1 === 0 ? price.toFixed(0) : price.toFixed(1)}
      {isCurrent && (
        <div style={{ fontSize: 8, color: C.accent, letterSpacing: '0.03em', marginTop: 1 }}>
          NOW
        </div>
      )}
    </th>
  );
}

function ProbCell({ prob, isCurrent, zone }) {
  const pct = (prob * 100).toFixed(1);
  const bg = probToGreen(prob);
  const textColor = probToTextColor(prob);

  return (
    <td
      style={{
        padding: '6px 4px',
        textAlign: 'center',
        fontFamily: mono,
        fontSize: 11,
        fontWeight: prob > 0.15 ? 600 : 400,
        color: textColor,
        backgroundColor: isCurrent ? `${C.accent}12` : (zone ? ZONE_BG[zone] : 'transparent'),
        backgroundImage: bg !== 'transparent' ? `linear-gradient(${bg}, ${bg})` : 'none',
        backgroundBlendMode: 'overlay',
        borderLeft: isCurrent ? `1px solid ${C.accent}30` : `1px solid transparent`,
        borderRight: isCurrent ? `1px solid ${C.accent}30` : `1px solid transparent`,
        borderBottom: `1px solid ${C.borderSubtle}`,
        whiteSpace: 'nowrap',
        ...(zone ? ZONE_STYLE[zone] : {}),
      }}
    >
      {pct}%
    </td>
  );
}

// ─── Legend ───────────────────────────────────────────────────────────────────

function Legend({ hasZones }) {
  return (
    <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap', marginTop: 8 }}>
      <LegendItem color={C.green} label="Higher probability" />
      <LegendItem color={C.textMuted} label="Lower probability" dim />
      {hasZones && (
        <>
          <LegendItem color={C.green} label="Profit zone" border />
          <LegendItem color={C.amber} label="Partial loss" border />
          <LegendItem color={C.red} label="Max loss zone" border />
        </>
      )}
      <LegendItem color={C.accent} label="Current price" accent />
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

// ─── Empty / loading states ───────────────────────────────────────────────────

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

  // Find the column index closest to currentPrice
  const currentIdx = price_levels.reduce(
    (best, p, i) =>
      Math.abs(p - currentPrice) < Math.abs(price_levels[best] - currentPrice) ? i : best,
    0
  );

  // Pre-compute zones for each price column (same for every row — zone is price-based)
  const zones = price_levels.map(p => getPriceZone(p, tradeStructure));
  const hasZones = zones.some(z => z !== null);

  // Row labels: use DATE_LABELS by position (Exp-9, Exp-6, Exp-3, Expiration)
  // Clamp to available rows if fewer than 4
  const rowLabels = rows.map((_, i) => {
    const labelIdx = i + (4 - rows.length); // align to end
    return DATE_LABELS[Math.max(0, labelIdx)] ?? `T${i}`;
  });

  return (
    <div>
      {/* Scrollable grid */}
      <div style={{
        overflowX: 'auto',
        borderRadius: 6,
        border: `1px solid ${C.border}`,
        backgroundColor: C.card,
      }}>
        <table style={{
          borderCollapse: 'collapse',
          width: '100%',
          minWidth: `${52 * price_levels.length + 72}px`,
        }}>
          <thead>
            <tr>
              {/* Row label header (top-left corner) */}
              <th style={{
                padding: '5px 10px',
                textAlign: 'left',
                fontSize: 10,
                color: C.textMuted,
                fontFamily: mono,
                borderBottom: `1px solid ${C.border}`,
                backgroundColor: C.surface,
                position: 'sticky',
                left: 0,
                zIndex: 2,
                minWidth: 72,
              }}>
                Date / Price
              </th>
              {price_levels.map((price, ci) => (
                <HeaderCell
                  key={ci}
                  price={price}
                  isCurrent={ci === currentIdx}
                  zone={zones[ci]}
                />
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((rowProbs, ri) => (
              <tr key={ri}>
                {/* Date label (sticky left) */}
                <td style={{
                  padding: '6px 10px',
                  fontFamily: mono,
                  fontSize: 11,
                  fontWeight: ri === rows.length - 1 ? 700 : 400,
                  color: ri === rows.length - 1 ? C.text : C.textDim,
                  backgroundColor: C.surface,
                  borderRight: `1px solid ${C.border}`,
                  borderBottom: `1px solid ${C.borderSubtle}`,
                  position: 'sticky',
                  left: 0,
                  zIndex: 1,
                  whiteSpace: 'nowrap',
                }}>
                  {rowLabels[ri]}
                  {dates?.[ri] && (
                    <div style={{ fontSize: 9, color: C.textMuted, marginTop: 1 }}>
                      {formatDateMMDDYYYY(dates[ri])}
                    </div>
                  )}
                </td>
                {rowProbs.map((prob, ci) => (
                  <ProbCell
                    key={ci}
                    prob={prob}
                    isCurrent={ci === currentIdx}
                    zone={zones[ci]}
                  />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Legend hasZones={hasZones} />
    </div>
  );
}
