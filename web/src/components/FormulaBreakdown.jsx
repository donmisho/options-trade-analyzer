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
 *   trade   — a scored trade object (with score_breakdown from API when available)
 *   weights — { expected_value, reward_risk, probability, liquidity, theta_efficiency }
 */
import { C, mono, WEIGHT_COLORS, WEIGHT_LABELS } from "../styles/tokens";

export default function FormulaBreakdown({ trade: t, weights: w }) {
  // Use score_breakdown from API when available for accurate norm bounds
  const sb = t.score_breakdown || {};

  function normStr(metricKey, rawVal, rawFmt) {
    const m = sb[metricKey];
    if (m && m.norm_min != null && m.norm_max != null && m.norm_min !== m.norm_max) {
      return `(${rawFmt} − ${m.norm_min}) / (${m.norm_max} − ${m.norm_min})`;
    }
    return 'normalized (min-max scaling)';
  }

  const liqRaw = t.long_volume + t.short_volume + t.long_oi + t.short_oi;
  const thRaw  = t.net_theta && t.max_loss ? Math.abs(t.net_theta / (t.max_loss * 100)) : 0;

  const formulas = [
    { key: "ev", sbKey: "expected_value", name: WEIGHT_LABELS.expected_value, color: WEIGHT_COLORS.expected_value, wt: w.expected_value,
      formula: sb.expected_value?.formula ?? "(prob × maxProfit) − ((1−prob) × maxLoss)",
      comp: `(${t.prob_of_profit?.toFixed(2)} × ${((t.max_profit ?? 0) * 100).toFixed(2)}) − (${(1 - (t.prob_of_profit ?? 0)).toFixed(2)} × ${((t.max_loss ?? 0) * 100).toFixed(2)})`,
      raw: `${(sb.expected_value?.raw ?? t.ev_raw ?? 0).toFixed(2)}`,
      norm: normStr('expected_value', t.ev_raw, (t.ev_raw ?? 0).toFixed(0)),
      ns: sb.expected_value?.normalized ?? t.ev_score ?? 0,
      wc: sb.expected_value?.contribution ?? (t.ev_score ?? 0) * w.expected_value * 100 },
    { key: "rr", sbKey: "reward_risk", name: WEIGHT_LABELS.reward_risk, color: WEIGHT_COLORS.reward_risk, wt: w.reward_risk,
      formula: sb.reward_risk?.formula ?? "maxProfit / maxLoss",
      comp: `${((t.max_profit ?? 0) * 100).toFixed(2)} / ${((t.max_loss ?? 0) * 100).toFixed(2)}`,
      raw: `${(sb.reward_risk?.raw ?? t.reward_risk_ratio ?? 0).toFixed(2)} : 1`,
      norm: normStr('reward_risk', t.reward_risk_ratio, (t.reward_risk_ratio ?? 0).toFixed(2)),
      ns: sb.reward_risk?.normalized ?? t.rr_score ?? 0,
      wc: sb.reward_risk?.contribution ?? (t.rr_score ?? 0) * w.reward_risk * 100 },
    { key: "prob", sbKey: "probability", name: WEIGHT_LABELS.probability, color: WEIGHT_COLORS.probability, wt: w.probability,
      formula: sb.probability?.formula ?? "≈ short leg delta",
      comp: `Short delta = ${(t.prob_of_profit ?? 0).toFixed(2)}`,
      raw: `${((sb.probability?.raw ?? t.prob_of_profit ?? 0) * 100).toFixed(0)}%`,
      norm: normStr('probability', t.prob_of_profit, (t.prob_of_profit ?? 0).toFixed(2)),
      ns: sb.probability?.normalized ?? t.prob_score ?? 0,
      wc: sb.probability?.contribution ?? (t.prob_score ?? 0) * w.probability * 100 },
    { key: "liq", sbKey: "liquidity", name: WEIGHT_LABELS.liquidity, color: WEIGHT_COLORS.liquidity, wt: w.liquidity,
      formula: sb.liquidity?.formula ?? "longVol + shortVol + longOI + shortOI",
      comp: `${t.long_volume ?? 0} + ${t.short_volume ?? 0} + ${t.long_oi ?? 0} + ${t.short_oi ?? 0}`,
      raw: `${sb.liquidity?.raw ?? liqRaw}`,
      norm: normStr('liquidity', liqRaw, String(liqRaw)),
      ns: sb.liquidity?.normalized ?? t.liquidity_score ?? 0,
      wc: sb.liquidity?.contribution ?? (t.liquidity_score ?? 0) * w.liquidity * 100 },
    { key: "th", sbKey: "theta_efficiency", name: WEIGHT_LABELS.theta_efficiency, color: WEIGHT_COLORS.theta_efficiency, wt: w.theta_efficiency,
      formula: sb.theta_efficiency?.formula ?? "net_theta / max_loss (higher = better)",
      comp: `|${(t.net_theta ?? 0).toFixed(4)} / ${(t.net_debit ?? 0).toFixed(2)}| = ${thRaw.toFixed(4)}`,
      raw: `${(sb.theta_efficiency?.raw ?? thRaw).toFixed(4)}`,
      norm: normStr('theta_efficiency', thRaw, thRaw.toFixed(4)),
      ns: sb.theta_efficiency?.normalized ?? t.theta_score ?? 0,
      wc: sb.theta_efficiency?.contribution ?? (t.theta_score ?? 0) * w.theta_efficiency * 100 },
  ];
  const total = formulas.reduce((s, f) => s + f.wc, 0);
  const compositeScore = t.composite_score ?? total;

  return (
    <div style={{ padding: "14px 0 6px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span style={{ fontSize: 14 }}>🔬</span>
        <span style={{ color: C.text, fontSize: 13, fontWeight: 700 }}>Score Breakdown</span>
        <span style={{ color: C.textMuted, fontSize: 11, marginLeft: "auto" }}>
          {t.spread_type ? (t.spread_type === "bull_call" ? "Bull Call" : "Bear Put") : (t.option_type === "put" ? "Long Put" : "Long Call")}
          {" "}{t.long_strike && t.short_strike ? `${t.long_strike}/${t.short_strike}` : t.strike ?? ''} {t.expiration}
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
            <span style={{ color: f.color, fontWeight: 700, fontSize: 13, fontFamily: mono }}>+{f.wc.toFixed(2)}</span>
          </div>
          <div style={{ marginBottom: 3 }}><span style={{ color: C.textMuted, fontSize: 10, fontWeight: 600, marginRight: 6 }}>FORMULA</span><span style={{ color: C.textDim, fontSize: 11, fontFamily: mono }}>{f.formula}</span></div>
          <div style={{ marginBottom: 3 }}><span style={{ color: C.textMuted, fontSize: 10, fontWeight: 600, marginRight: 6 }}>MATH</span><span style={{ color: C.text, fontSize: 11.5, fontFamily: mono }}>{f.comp}</span><span style={{ color: f.color, fontSize: 11.5, fontWeight: 600, marginLeft: 8, fontFamily: mono }}>= {f.raw}</span></div>
          <div style={{ marginBottom: 3 }}><span style={{ color: C.textMuted, fontSize: 10, fontWeight: 600, marginRight: 6 }}>NORM</span><span style={{ color: C.textDim, fontSize: 10.5, fontFamily: mono }}>{f.norm}</span><span style={{ color: C.text, fontSize: 11, fontWeight: 600, marginLeft: 8, fontFamily: mono }}>= {f.ns.toFixed(4)}</span></div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 5 }}>
            <span style={{ color: C.textMuted, fontSize: 10, fontWeight: 600, minWidth: 38 }}>SCORE</span>
            <div style={{ flex: 1, height: 5, borderRadius: 3, backgroundColor: C.border, position: "relative" }}>
              <div style={{ position: "absolute", left: 0, height: 5, borderRadius: 3, width: `${f.ns * 100}%`, backgroundColor: f.color, opacity: 0.2 }} />
              <div style={{ position: "absolute", left: 0, height: 5, borderRadius: 3, width: `${Math.min(f.wc, 100)}%`, backgroundColor: f.color, opacity: 0.8 }} />
            </div>
            <span style={{ color: C.textDim, fontSize: 10, fontFamily: mono, minWidth: 60, textAlign: "right" }}>{f.ns.toFixed(2)} × {Math.round(f.wt * 100)}%</span>
          </div>
        </div>
      ))}

      <div style={{ marginTop: 6, padding: "9px 11px", borderRadius: 7, border: `1px solid ${C.accent}40`, backgroundColor: C.accentGlow, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ color: C.text, fontSize: 13, fontWeight: 700 }}>Composite Score</span>
        <span style={{ color: C.accent, fontSize: 18, fontWeight: 800, fontFamily: mono }}>{compositeScore.toFixed(2)}</span>
      </div>
    </div>
  );
}
