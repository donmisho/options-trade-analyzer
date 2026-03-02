/**
 * FavoritesTab — Saved trades grouped by symbol with mini charts.
 *
 * Props:
 *   favorites   — Set of favorited trade ids
 *   trades      — full array of trade objects
 *   candles     — candle data (for mini chart)
 *   smaPeriods  — { short, mid, long }
 *   onRemoveFav — callback(id) to un-favorite
 *   onEvaluate  — callback(trade) to open Ask Claude
 */
import { useState, useCallback, useMemo } from "react";
import { C, mono } from "../styles/tokens";

// Lightweight mini chart for favorites (smaller than the full SmaPanel chart)
function MiniCandleChart({ candles, smaPeriods, height = 180 }) {
  const [w, setW] = useState(700);
  const ref = useCallback(n => { if (n) { const ro = new ResizeObserver(e => setW(e[0].contentRect.width)); ro.observe(n); } }, []);
  const pad = { top: 8, right: 48, bottom: 4, left: 4 };
  const cW = w - pad.left - pad.right, cH = height - pad.top - pad.bottom;

  function computeSma(data, period) { return data.map((_, i) => i < period - 1 ? null : data.slice(i - period + 1, i + 1).reduce((s, c) => s + c.close, 0) / period); }

  const sS = useMemo(() => computeSma(candles, smaPeriods.short), [candles, smaPeriods.short]);
  const sM = useMemo(() => computeSma(candles, smaPeriods.mid), [candles, smaPeriods.mid]);
  const sL = useMemo(() => computeSma(candles, smaPeriods.long), [candles, smaPeriods.long]);
  const vc = Math.min(80, candles.length), si = candles.length - vc;
  const vis = candles.slice(si), vS = sS.slice(si), vM = sM.slice(si), vL = sL.slice(si);
  const all = [...vis.flatMap(c => [c.high, c.low]), ...vS.filter(Boolean), ...vM.filter(Boolean), ...vL.filter(Boolean)];
  const mn = Math.min(...all) - 1, mx = Math.max(...all) + 1, rng = mx - mn || 1;
  const yS = (p) => pad.top + cH - ((p - mn) / rng) * cH;
  const gap = cW / vc, cw = Math.max(2, gap * 0.6);
  const sPath = (vals) => { const pts = vals.map((v, i) => v ? `${pad.left + i * gap + gap / 2},${yS(v)}` : null).filter(Boolean); return pts.length > 1 ? `M${pts.join("L")}` : ""; };
  const lc = vis[vis.length - 1]?.close || 0;

  return (<div ref={ref} style={{ width: "100%" }}><svg width={w} height={height} style={{ display: "block" }}>
    <rect x={0} y={0} width={w} height={height} fill={C.bg} />
    {vis.map((c, i) => { const x = pad.left + i * gap + gap / 2, ig = c.close >= c.open, col = ig ? C.candleGreen : C.candleRed, bt = yS(Math.max(c.open, c.close)), bb = yS(Math.min(c.open, c.close)), bh = Math.max(1, bb - bt); return (<g key={i}><line x1={x} y1={yS(c.high)} x2={x} y2={yS(c.low)} stroke={col} strokeWidth={1} opacity={0.7} /><rect x={x - cw / 2} y={bt} width={cw} height={bh} fill={col} opacity={0.85} rx={0.5} /></g>); })}
    <path d={sPath(vL)} fill="none" stroke={C.smaRed} strokeWidth={1.6} opacity={0.75} />
    <path d={sPath(vM)} fill="none" stroke={C.smaOrange} strokeWidth={1.6} opacity={0.8} />
    <path d={sPath(vS)} fill="none" stroke={C.smaCyan} strokeWidth={1.6} opacity={0.85} />
    <rect x={w - pad.right + 1} y={yS(lc) - 9} width={44} height={18} rx={3} fill={lc >= (vis[vis.length - 2]?.close || lc) ? C.candleGreen : C.candleRed} opacity={0.9} />
    <text x={w - pad.right + 5} y={yS(lc) + 4} fill="#fff" fontSize={10} fontFamily={mono} fontWeight={600}>{lc.toFixed(1)}</text>
  </svg></div>);
}

export default function FavoritesTab({ favorites, trades, candles, smaPeriods, onRemoveFav, onEvaluate }) {
  const [expandedChart, setExpandedChart] = useState(null);
  const favTrades = trades.filter(t => favorites.has(t.id));
  const grouped = {};
  favTrades.forEach(t => { if (!grouped[t.symbol]) grouped[t.symbol] = []; grouped[t.symbol].push(t); });

  if (favTrades.length === 0) return (
    <div style={{ textAlign: "center", padding: "60px 20px" }}>
      <div style={{ fontSize: 32, marginBottom: 12 }}>⭐</div>
      <div style={{ fontSize: 14, color: C.textDim, marginBottom: 6 }}>No favorites yet</div>
      <div style={{ fontSize: 12, color: C.textMuted }}>Click the star icon on any trade to save it here.</div>
    </div>
  );

  return (<div>
    {Object.entries(grouped).map(([sym, symTrades]) => (
      <div key={sym} style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: C.text }}>{sym}</span>
            <span style={{ fontSize: 11, color: C.textDim }}>{symTrades.length} saved</span>
          </div>
          <button onClick={() => setExpandedChart(expandedChart === sym ? null : sym)}
            style={{ padding: "4px 10px", borderRadius: 5, border: `1px solid ${C.border}`, backgroundColor: expandedChart === sym ? C.surfaceAlt : "transparent", color: expandedChart === sym ? C.accent : C.textMuted, fontSize: 11, cursor: "pointer" }}>
            {expandedChart === sym ? "Hide Chart" : "📈 Chart"}
          </button>
        </div>
        {expandedChart === sym && (<div style={{ marginBottom: 10, borderRadius: 8, border: `1px solid ${C.border}`, overflow: "hidden" }}><MiniCandleChart candles={candles} smaPeriods={smaPeriods} height={180} /></div>)}
        {symTrades.map(t => (
          <div key={t.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 7, border: `1px solid ${C.border}`, backgroundColor: C.card, marginBottom: 4 }}>
            <button onClick={() => onRemoveFav(t.id)} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 14, padding: 2, color: C.amber }}>★</button>
            <span style={{ color: t.spread_type === "bull_call" ? C.green : C.red, fontSize: 10, fontWeight: 800 }}>{t.spread_type === "bull_call" ? "▲" : "▼"}</span>
            <span style={{ color: C.text, fontSize: 12, fontWeight: 600, minWidth: 70 }}>{t.long_strike}/{t.short_strike}</span>
            <span style={{ color: C.textDim, fontSize: 11, minWidth: 60 }}>{t.expiration.slice(5)}</span>
            <span style={{ color: C.text, fontSize: 11, fontFamily: mono, minWidth: 45 }}>${t.net_debit.toFixed(2)}</span>
            <span style={{ color: C.text, fontSize: 11, fontFamily: mono, minWidth: 40 }}>{t.reward_risk_ratio.toFixed(2)}</span>
            <span style={{ color: C.text, fontSize: 11, fontFamily: mono, minWidth: 35 }}>{(t.prob_of_profit * 100).toFixed(0)}%</span>
            <div style={{ flex: 1 }} />
            <span style={{ fontSize: 12, fontWeight: 700, fontFamily: mono, color: t.composite_score > 0.7 ? C.green : t.composite_score > 0.5 ? C.amber : C.red }}>{t.composite_score.toFixed(2)}</span>
            <button onClick={() => onEvaluate(t)} style={{ padding: "4px 10px", borderRadius: 5, border: `1px solid ${C.claudeBorder}`, backgroundColor: C.claudeDim, color: C.claudeAccent, fontSize: 10, fontWeight: 600, cursor: "pointer" }}>✦ Evaluate</button>
          </div>
        ))}
      </div>
    ))}
  </div>);
}
