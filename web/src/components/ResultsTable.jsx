/**
 * ResultsTable — Scored trades with ☆ favorite and ✦ Ask Claude buttons.
 *
 * Props:
 *   trades      — array of scored trade objects
 *   weights     — current weight config (passed to FormulaBreakdown)
 *   selectedId  — currently expanded trade id (or null)
 *   onSelect    — callback(id) to expand/collapse formula breakdown
 *   favorites   — Set of favorited trade ids
 *   onToggleFav — callback(id) to toggle favorite
 *   onEvaluate  — callback(trade) to open Ask Claude panel
 */
import { C, mono } from "../styles/tokens";
import FormulaBreakdown from "./FormulaBreakdown";

export default function ResultsTable({ trades, weights, selectedId, onSelect, favorites, onToggleFav, onEvaluate }) {
  return (
    <div>
      {/* Header row */}
      <div style={{ display: "grid", gridTemplateColumns: "28px 28px 84px 72px 50px 54px 52px 46px 68px 60px", padding: "8px 10px", fontSize: 9.5, fontWeight: 600, color: C.textMuted, textTransform: "uppercase", letterSpacing: "0.03em", borderBottom: `1px solid ${C.border}` }}>
        <span></span><span>#</span><span>Spread</span><span>Exp</span><span>Debit</span><span>Max $</span><span>R:R</span><span>Prob</span><span style={{ textAlign: "right" }}>Score</span><span></span>
      </div>

      {trades.map((t, i) => (
        <div key={t.id}>
          {/* Trade row */}
          <div
            style={{
              display: "grid", gridTemplateColumns: "28px 28px 84px 72px 50px 54px 52px 46px 68px 60px",
              padding: "8px 10px", alignItems: "center",
              borderBottom: `1px solid ${C.borderSubtle}`,
              backgroundColor: selectedId === t.id ? C.surfaceAlt : "transparent",
              borderLeft: selectedId === t.id ? `2px solid ${C.accent}` : "2px solid transparent",
              cursor: "pointer",
            }}
            onClick={() => onSelect(selectedId === t.id ? null : t.id)}
            onMouseEnter={(e) => { if (selectedId !== t.id) e.currentTarget.style.backgroundColor = C.cardHover; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = selectedId === t.id ? C.surfaceAlt : "transparent"; }}
          >
            {/* Star */}
            <button onClick={(e) => { e.stopPropagation(); onToggleFav(t.id); }}
              style={{ background: "none", border: "none", cursor: "pointer", fontSize: 13, padding: 0, color: favorites.has(t.id) ? C.amber : C.textMuted }}>
              {favorites.has(t.id) ? "★" : "☆"}
            </button>
            {/* Row number */}
            <span style={{ color: C.textMuted, fontSize: 11 }}>{i + 1}</span>
            {/* Spread */}
            <span style={{ fontSize: 12, fontWeight: 600 }}>
              <span style={{ color: t.spread_type === "bull_call" ? C.green : C.red, fontSize: 10, marginRight: 3 }}>{t.spread_type === "bull_call" ? "▲" : "▼"}</span>
              <span style={{ color: C.text }}>{t.long_strike}/{t.short_strike}</span>
            </span>
            {/* Expiration */}
            <span style={{ color: C.textDim, fontSize: 11 }}>{t.expiration.slice(5)}</span>
            {/* Debit */}
            <span style={{ color: C.text, fontSize: 11, fontFamily: mono }}>${t.net_debit.toFixed(2)}</span>
            {/* Max profit */}
            <span style={{ color: C.green, fontSize: 11, fontFamily: mono }}>${(t.max_profit * 100).toFixed(0)}</span>
            {/* R:R */}
            <span style={{ color: C.text, fontSize: 11, fontFamily: mono }}>{t.reward_risk_ratio.toFixed(2)}</span>
            {/* Probability */}
            <span style={{ color: C.text, fontSize: 11, fontFamily: mono }}>{(t.prob_of_profit * 100).toFixed(0)}%</span>
            {/* Composite score with bar */}
            <div style={{ textAlign: "right", display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 4 }}>
              <div style={{ width: 30, height: 4, borderRadius: 2, backgroundColor: C.border, overflow: "hidden" }}>
                <div style={{ width: `${t.composite_score * 100}%`, height: "100%", borderRadius: 2, backgroundColor: t.composite_score > 0.7 ? C.green : t.composite_score > 0.5 ? C.amber : C.red }} />
              </div>
              <span style={{ color: C.text, fontSize: 12, fontWeight: 700, fontFamily: mono }}>{t.composite_score.toFixed(2)}</span>
            </div>
            {/* Ask Claude button */}
            <button onClick={(e) => { e.stopPropagation(); onEvaluate(t); }}
              style={{ padding: "3px 8px", borderRadius: 4, border: `1px solid ${C.claudeBorder}`, backgroundColor: C.claudeDim, color: C.claudeAccent, fontSize: 9, fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap" }}>
              ✦ Ask
            </button>
          </div>

          {/* Expanded formula breakdown */}
          {selectedId === t.id && (
            <div style={{ padding: "0 12px 12px", backgroundColor: C.surfaceAlt, borderBottom: `1px solid ${C.border}`, borderLeft: `2px solid ${C.accent}` }}>
              <FormulaBreakdown trade={t} weights={weights} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
