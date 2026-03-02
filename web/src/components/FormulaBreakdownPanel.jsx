/**
 * FormulaBreakdownPanel — Slideout showing how a trade's composite score was calculated.
 *
 * For each of the 5 scoring metrics, it displays:
 *   1. The formula (human-readable)
 *   2. The math with actual numbers plugged in
 *   3. The normalization step (raw → 0-1 scale)
 *   4. A color-coded bar showing the normalized score × weight
 *
 * WHY a slideout instead of inline expand: The prototype originally expanded
 * formula details inline below each trade row. That made the results table
 * jump around and was hard to read. A slideout panel gives full vertical
 * space for the math and keeps the table stable. It matches the same
 * pattern as Ask Claude — click an icon on the row, panel slides open.
 *
 * Props:
 *   open     — boolean, whether the panel is visible
 *   onClose  — callback to close the panel
 *   trade    — the scored trade object (from analysis API)
 *   symbol   — the underlying symbol (e.g. "QQQ")
 *   weights  — current scoring weights object { expected_value, reward_risk, ... }
 */
import SlideoutPanel from "./SlideoutPanel";
import { C, mono, WEIGHT_COLORS, WEIGHT_LABELS } from "../styles/tokens";

/**
 * Compute the full scoring breakdown for a vertical spread trade.
 *
 * Each metric goes through three steps:
 *   1. RAW — calculate the metric from trade data
 *   2. NORM — min-max normalize to 0-1 range
 *   3. WEIGHTED — multiply normalized score by the weight
 *
 * The normalization ranges here match what the backend VerticalSpreadEngine uses.
 * If you change the engine's normalization, update these to match.
 */
function computeBreakdown(trade, weights) {
  // ── Expected Value ──
  const maxLoss = trade.net_debit;
  const maxProfit = trade.max_profit;
  const prob = trade.prob_of_profit;
  const ev = prob * maxProfit - (1 - prob) * maxLoss;
  // Normalization range: backend uses the min/max of the batch.
  // We approximate with reasonable bounds for display purposes.
  const evMin = -1.0;
  const evMax = 3.0;
  const evNorm = Math.max(0, Math.min(1, (ev - evMin) / (evMax - evMin)));

  // ── Reward : Risk ──
  const rr = trade.reward_risk_ratio;
  const rrMin = 0.5;
  const rrMax = 3.5;
  const rrNorm = Math.max(0, Math.min(1, (rr - rrMin) / (rrMax - rrMin)));

  // ── Probability of Profit ──
  const probMin = 0.35;
  const probMax = 0.75;
  const probNorm = Math.max(0, Math.min(1, (prob - probMin) / (probMax - probMin)));

  // ── Liquidity ──
  // Sum of volume + open interest for both legs
  const liq = (trade.long_volume || 0) + (trade.short_volume || 0) +
              (trade.long_oi || 0) + (trade.short_oi || 0);
  const liqMin = 100;
  const liqMax = 5000;
  const liqNorm = Math.max(0, Math.min(1, (liq - liqMin) / (liqMax - liqMin)));

  // ── Theta Efficiency ──
  // |net_theta / net_debit| — lower is better, so we invert
  const netTheta = trade.net_theta || 0;
  const thetaRatio = trade.net_debit > 0 ? Math.abs(netTheta / trade.net_debit) : 0;
  const thetaMax = 0.02; // anything above this normalizes to 0 (worst)
  const thetaNorm = Math.max(0, Math.min(1, 1 - (thetaRatio / thetaMax)));

  return [
    {
      key: "expected_value",
      formula: "(prob × maxProfit) − ((1−prob) × maxLoss)",
      math: `(${prob.toFixed(2)} × $${maxProfit.toFixed(2)}) − (${(1 - prob).toFixed(2)} × $${maxLoss.toFixed(2)}) = $${ev.toFixed(2)}`,
      norm: `(${ev.toFixed(2)} − ${evMin}) / (${evMax} − ${evMin}) = ${evNorm.toFixed(4)}`,
      normalized: evNorm,
      weighted: evNorm * (weights.expected_value || 0),
    },
    {
      key: "reward_risk",
      formula: "maxProfit / maxLoss",
      math: `$${maxProfit.toFixed(2)} / $${maxLoss.toFixed(2)} = ${rr.toFixed(2)} : 1`,
      norm: `(${rr.toFixed(2)} − ${rrMin}) / (${rrMax} − ${rrMin}) = ${rrNorm.toFixed(4)}`,
      normalized: rrNorm,
      weighted: rrNorm * (weights.reward_risk || 0),
    },
    {
      key: "probability",
      formula: "≈ short leg delta",
      math: `Short delta = ${prob.toFixed(2)} = ${(prob * 100).toFixed(0)}%`,
      norm: `(${prob.toFixed(2)} − ${probMin}) / (${probMax} − ${probMin}) = ${probNorm.toFixed(4)}`,
      normalized: probNorm,
      weighted: probNorm * (weights.probability || 0),
    },
    {
      key: "liquidity",
      formula: "longVol + shortVol + longOI + shortOI",
      math: `${trade.long_volume || 0} + ${trade.short_volume || 0} + ${trade.long_oi || 0} + ${trade.short_oi || 0} = ${liq}`,
      norm: `(${liq} − ${liqMin}) / (${liqMax} − ${liqMin}) = ${liqNorm.toFixed(4)}`,
      normalized: liqNorm,
      weighted: liqNorm * (weights.liquidity || 0),
    },
    {
      key: "theta_efficiency",
      formula: "|net_theta / net_debit| (lower = better)",
      math: `|${netTheta.toFixed(4)} / ${trade.net_debit.toFixed(2)}| = ${thetaRatio.toFixed(4)}`,
      norm: `inverted (lower scores higher) = ${thetaNorm.toFixed(4)}`,
      normalized: thetaNorm,
      weighted: thetaNorm * (weights.theta_efficiency || 0),
    },
  ];
}

export default function FormulaBreakdownPanel({ open, onClose, trade, symbol, weights }) {
  if (!trade) return null;

  const breakdown = computeBreakdown(trade, weights);
  const compositeScore = breakdown.reduce((sum, m) => sum + m.weighted, 0);

  const isBull = trade.spread_type === "bull_call";
  const typeLabel = isBull ? "Bull Call" : "Bear Put";
  const expFormatted = trade.expiration; // Already in API format, display as-is

  return (
    <SlideoutPanel
      open={open}
      onClose={onClose}
      title="Score Breakdown"
      subtitle={`${typeLabel} ${trade.long_strike}/${trade.short_strike} ${expFormatted}`}
      icon="ƒx"
      width={520}
    >
      {/* Trade identity badge */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "10px 14px",
          backgroundColor: C.card,
          borderRadius: 8,
          border: `1px solid ${C.border}`,
          marginBottom: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              color: isBull ? C.green : C.red,
              fontWeight: 800,
              fontSize: 14,
            }}
          >
            {isBull ? "▲" : "▼"}
          </span>
          <span
            style={{
              color: C.text,
              fontWeight: 700,
              fontFamily: mono,
              fontSize: 14,
            }}
          >
            {symbol} {trade.long_strike}/{trade.short_strike}
          </span>
        </div>
        <span style={{ color: C.textDim, fontSize: 12 }}>{expFormatted}</span>
      </div>

      {/* Each metric breakdown */}
      {breakdown.map((m, idx) => {
        const color = WEIGHT_COLORS[m.key];
        const label = WEIGHT_LABELS[m.key];
        const weightPct = ((weights[m.key] || 0) * 100).toFixed(0);

        return (
          <div
            key={m.key}
            style={{
              marginBottom: 16,
              paddingBottom: idx < breakdown.length - 1 ? 16 : 0,
              borderBottom:
                idx < breakdown.length - 1
                  ? `1px solid ${C.borderSubtle}`
                  : "none",
            }}
          >
            {/* Metric header row */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 8,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    backgroundColor: color,
                  }}
                />
                <span
                  style={{ color: C.text, fontWeight: 600, fontSize: 13 }}
                >
                  {label}
                </span>
                <span
                  style={{
                    padding: "1px 7px",
                    borderRadius: 4,
                    fontSize: 10,
                    fontWeight: 600,
                    backgroundColor: `${color}20`,
                    color: color,
                  }}
                >
                  {weightPct}%
                </span>
              </div>
              <span
                style={{
                  color: color,
                  fontWeight: 700,
                  fontFamily: mono,
                  fontSize: 13,
                }}
              >
                +{m.weighted.toFixed(4)}
              </span>
            </div>

            {/* Formula / Math / Norm lines */}
            <div
              style={{
                marginLeft: 18,
                display: "flex",
                flexDirection: "column",
                gap: 3,
              }}
            >
              <div>
                <span
                  style={{
                    color: C.textMuted,
                    fontSize: 9.5,
                    fontWeight: 600,
                    letterSpacing: "0.04em",
                    textTransform: "uppercase",
                  }}
                >
                  FORMULA{" "}
                </span>
                <span
                  style={{
                    color: C.textDim,
                    fontSize: 11.5,
                    fontFamily: mono,
                  }}
                >
                  {m.formula}
                </span>
              </div>
              <div>
                <span
                  style={{
                    color: C.textMuted,
                    fontSize: 9.5,
                    fontWeight: 600,
                    letterSpacing: "0.04em",
                    textTransform: "uppercase",
                  }}
                >
                  MATH{" "}
                </span>
                <span
                  style={{
                    color: C.text,
                    fontSize: 11.5,
                    fontFamily: mono,
                  }}
                >
                  {m.math}
                </span>
              </div>
              <div>
                <span
                  style={{
                    color: C.textMuted,
                    fontSize: 9.5,
                    fontWeight: 600,
                    letterSpacing: "0.04em",
                    textTransform: "uppercase",
                  }}
                >
                  NORM{" "}
                </span>
                <span
                  style={{
                    color: C.textDim,
                    fontSize: 11.5,
                    fontFamily: mono,
                  }}
                >
                  {m.norm}
                </span>
              </div>
            </div>

            {/* Score bar */}
            <div
              style={{
                marginTop: 8,
                marginLeft: 18,
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <span
                style={{
                  color: C.textMuted,
                  fontSize: 9.5,
                  fontWeight: 600,
                  textTransform: "uppercase",
                }}
              >
                SCORE
              </span>
              <div
                style={{
                  flex: 1,
                  height: 5,
                  backgroundColor: C.border,
                  borderRadius: 3,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${m.normalized * 100}%`,
                    backgroundColor: color,
                    borderRadius: 3,
                    transition: "width 0.4s ease",
                  }}
                />
              </div>
              <span
                style={{
                  color: C.textDim,
                  fontSize: 11,
                  fontFamily: mono,
                  minWidth: 80,
                  textAlign: "right",
                }}
              >
                {m.normalized.toFixed(2)} × {weightPct}%
              </span>
            </div>
          </div>
        );
      })}

      {/* Composite Score */}
      <div
        style={{
          backgroundColor: C.surfaceAlt,
          borderRadius: 8,
          padding: "12px 16px",
          border: `1px solid ${C.border}`,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: 8,
        }}
      >
        <span style={{ color: C.text, fontWeight: 700, fontSize: 14 }}>
          Composite Score
        </span>
        <span
          style={{
            color:
              compositeScore > 0.7
                ? C.green
                : compositeScore > 0.5
                ? C.amber
                : C.red,
            fontWeight: 800,
            fontSize: 20,
            fontFamily: mono,
          }}
        >
          {compositeScore.toFixed(4)}
        </span>
      </div>
    </SlideoutPanel>
  );
}
