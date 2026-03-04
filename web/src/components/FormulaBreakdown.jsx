/**
 * FormulaBreakdown — Expandable scoring math for a single trade.
 *
 * Shows the 4-step scoring pipeline for each metric:
 *   1. FORMULA — the equation used
 *   2. MATH   — actual numbers plugged in
 *   3. NORM   — how the raw score was normalized to 0-1
 *   4. SCORE  — normalized score × weight = weighted contribution
 *
 * Props:
 *   trade   — a scored trade object with _norm data
 *   weights — { expected_value, reward_risk, probability, liquidity, theta_efficiency }
 */
import { C, mono, WEIGHT_COLORS, WEIGHT_LABELS } from "../styles/tokens";

export default function FormulaBreakdown({ trade: t, weights: w }) {
  const formulas = [
    { key: "ev", name: WEIGHT_LABELS.expected_value, color: WEIGHT_COLORS.expected_value, wt: w.expected_value,
      formula: "(prob × maxProfit) − ((1−prob) × maxLoss)",
      comp: `(${t.prob_of_profit.toFixed(2)} × ${(t.max_profit * 100).toFixed(2)}) − (${(1 - t.prob_of_profit).toFixed(2)} × ${(t.max_loss * 100).toFixed(2)})`,
      raw: `${t.ev_raw.toFixed(2)}`,
      norm: `(${t.ev_raw.toFixed(0)} − ${t._norm.ev_min}) / (${t._norm.ev_max} − ${t._norm.ev_min})`,
      ns: t.ev_score, wc: t.ev_score * w.expected_value },
    { key: "rr", name: WEIGHT_LABELS.reward_risk, color: WEIGHT_COLORS.reward_risk, wt: w.reward_risk,
      formula: "maxProfit / maxLoss",
      comp: `${(t.max_profit * 100).toFixed(2)} / ${(t.max_loss * 100).toFixed(2)}`,
      raw: `${t.reward_risk_ratio.toFixed(2)} : 1`,
      norm: `(${t.reward_risk_ratio.toFixed(2)} − ${t._norm.rr_min}) / (${t._norm.rr_max} − ${t._norm.rr_min})`,
      ns: t.rr_score, wc: t.rr_score * w.reward_risk },
    { key: "prob", name: WEIGHT_LABELS.probability, color: WEIGHT_COLORS.probability, wt: w.probability,
      formula: "≈ short leg delta",
      comp: `Short delta = ${t.prob_of_profit.toFixed(2)}`,
      raw: `${(t.prob_of_profit * 100).toFixed(0)}%`,
      norm: `(${t.prob_of_profit.toFixed(2)} − ${t._norm.prob_min}) / (${t._norm.prob_max} − ${t._norm.prob_min})`,
      ns: t.prob_score, wc: t.prob_score * w.probability },
    { key: "liq", name: WEIGHT_LABELS.liquidity, color: WEIGHT_COLORS.liquidity, wt: w.liquidity,
      formula: "longVol + shortVol + longOI + shortOI",
      comp: `${t.long_volume} + ${t.short_volume} + ${t.long_oi} + ${t.short_oi}`,
      raw: `${t.long_volume + t.short_volume + t.long_oi + t.short_oi}`,
      norm: `(${t.long_volume + t.short_volume + t.long_oi + t.short_oi} − ${t._norm.liq_min}) / (${t._norm.liq_max} − ${t._norm.liq_min})`,
      ns: t.liquidity_score, wc: t.liquidity_score * w.liquidity },
    { key: "th", name: WEIGHT_LABELS.theta_efficiency, color: WEIGHT_COLORS.theta_efficiency, wt: w.theta_efficiency,
      formula: "|net_theta / net_debit| (lower = better)",
      comp: `|${t.net_theta.toFixed(4)} / ${t.net_debit.toFixed(2)}| = ${Math.abs(t.net_theta / t.net_debit).toFixed(4)}`,
      raw: `${Math.abs(t.net_theta / t.net_debit).toFixed(4)}`,
      norm: "inverted (lower scores higher)",
      ns: t.theta_score, wc: t.theta_score * w.theta_efficiency },
  ];
  const total = formulas.reduce((s, f) => s + f.wc, 0);

  return (
    <div style={{ padding: "14px 0 6px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span style={{ fontSize: 14 }}>🔬</span>
        <span style={{ color: C.text, fontSize: 13, fontWeight: 700 }}>Score Breakdown</span>
        <span style={{ color: C.textMuted, fontSize: 11, marginLeft: "auto" }}>
          {t.spread_type === "bull_call" ? "Bull Call" : "Bear Put"} {t.long_strike}/{t.short_strike} {t.expiration}
        </span>
      </div>

      {formulas.map(f => (
        <div key={f.key} style={{ marginBottom: 10, padding: "9px 11px", borderRadius: 7, backgroundColor: C.surfaceAlt, border: `1px solid ${C.borderSubtle}` }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 5 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", backgroundColor: f.color }} />
              <span style={{ color: C.text, fontSize: 12, fontWeight: 600 }}>{f.name}</span>
              <span style={{ color: C.textMuted, fontSize: 10, padding: "1px 5px", borderRadius: 3, backgroundColor: C.border }}>{Math.round(f.wt * 100)}%</span>
            </div>
            <span style={{ color: f.color, fontWeight: 700, fontSize: 13, fontFamily: mono }}>+{f.wc.toFixed(4)}</span>
          </div>
          <div style={{ marginBottom: 3 }}><span style={{ color: C.textMuted, fontSize: 10, fontWeight: 600, marginRight: 6 }}>FORMULA</span><span style={{ color: C.textDim, fontSize: 11, fontFamily: mono }}>{f.formula}</span></div>
          <div style={{ marginBottom: 3 }}><span style={{ color: C.textMuted, fontSize: 10, fontWeight: 600, marginRight: 6 }}>MATH</span><span style={{ color: C.text, fontSize: 11.5, fontFamily: mono }}>{f.comp}</span><span style={{ color: f.color, fontSize: 11.5, fontWeight: 600, marginLeft: 8, fontFamily: mono }}>= {f.raw}</span></div>
          <div style={{ marginBottom: 3 }}><span style={{ color: C.textMuted, fontSize: 10, fontWeight: 600, marginRight: 6 }}>NORM</span><span style={{ color: C.textDim, fontSize: 10.5, fontFamily: mono }}>{f.norm}</span><span style={{ color: C.text, fontSize: 11, fontWeight: 600, marginLeft: 8, fontFamily: mono }}>= {f.ns.toFixed(4)}</span></div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 5 }}>
            <span style={{ color: C.textMuted, fontSize: 10, fontWeight: 600, minWidth: 38 }}>SCORE</span>
            <div style={{ flex: 1, height: 5, borderRadius: 3, backgroundColor: C.border, position: "relative" }}>
              <div style={{ position: "absolute", left: 0, height: 5, borderRadius: 3, width: `${f.ns * 100}%`, backgroundColor: f.color, opacity: 0.2 }} />
              <div style={{ position: "absolute", left: 0, height: 5, borderRadius: 3, width: `${f.wc * 100}%`, backgroundColor: f.color, opacity: 0.8 }} />
            </div>
            <span style={{ color: C.textDim, fontSize: 10, fontFamily: mono, minWidth: 60, textAlign: "right" }}>{f.ns.toFixed(2)} × {Math.round(f.wt * 100)}%</span>
          </div>
        </div>
      ))}

      <div style={{ marginTop: 6, padding: "9px 11px", borderRadius: 7, border: `1px solid ${C.accent}40`, backgroundColor: C.accentGlow, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ color: C.text, fontSize: 13, fontWeight: 700 }}>Composite Score</span>
        <span style={{ color: C.accent, fontSize: 18, fontWeight: 800, fontFamily: mono }}>{total.toFixed(4)}</span>
      </div>
    </div>
  );
}
