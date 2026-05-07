/**
 * SmaPanel — Collapsible candlestick chart with SMA overlay.
 *
 * Props:
 *   candles        — array of { open, high, low, close, datetime }
 *   smaPeriods     — { short, mid, long } e.g. { short: 8, mid: 21, long: 50 }
 *   onPeriodsChange — callback when user edits SMA periods
 *   rangeDays      — current chart range (7|14|30|60|90|180|365)
 *   onRangeChange  — callback(newRange) when user picks a new range
 *   requestedRange — the range that was requested (to detect truncation)
 *   symbol         — optional, displayed in header (default "QQQ")
 */
import { useState, useCallback, useMemo } from "react";
import { C, mono } from "../styles/tokens";
import { formatDate } from "../utils/formatDate";

const RANGE_OPTIONS = [7, 14, 30, 60, 90, 180, 365];

// Label density: how many bars between date labels per range
const LABEL_STEP = { 7: 'day', 14: 'day', 30: 2, 60: 5, 90: 7, 180: 14, 365: 4 };

function computeSma(candles, period) {
  return candles.map((_, i) => i < period - 1 ? null : candles.slice(i - period + 1, i + 1).reduce((s, c) => s + c.close, 0) / period);
}

// ─── SVG Candlestick Chart ────────────────────────────────────────
function CandlestickChart({ candles, smaPeriods, rangeDays = 90, height = 280 }) {
  const [w, setW] = useState(760);
  const ref = useCallback(n => { if (n) { const ro = new ResizeObserver(e => setW(e[0].contentRect.width)); ro.observe(n); } }, []);

  const xAxisHeight = 22;
  const pad = { top: 10, right: 52, bottom: xAxisHeight + 4, left: 6 };
  const cW = w - pad.left - pad.right, cH = height - pad.top - pad.bottom;

  const sS = useMemo(() => computeSma(candles, smaPeriods.short), [candles, smaPeriods.short]);
  const sM = useMemo(() => computeSma(candles, smaPeriods.mid), [candles, smaPeriods.mid]);
  const sL = useMemo(() => computeSma(candles, smaPeriods.long), [candles, smaPeriods.long]);

  const vc = candles.length, si = 0;
  const vis = candles, vS = sS, vM = sM, vL = sL;
  const all = [...vis.flatMap(c => [c.high, c.low]), ...vS.filter(Boolean), ...vM.filter(Boolean), ...vL.filter(Boolean)];
  const mn = Math.min(...all) - 1, mx = Math.max(...all) + 1, rng = mx - mn || 1;
  const yS = (p) => pad.top + cH - ((p - mn) / rng) * cH;
  const gap = vc > 0 ? cW / vc : cW;
  const cw = Math.max(2, gap * 0.6);

  const sPath = (vals) => { const pts = vals.map((v, i) => v ? `${pad.left + i * gap + gap / 2},${yS(v)}` : null).filter(Boolean); return pts.length > 1 ? `M${pts.join("L")}` : ""; };
  const steps = 6;
  const pLabels = Array.from({ length: steps }, (_, i) => { const p = mn + (rng / (steps - 1)) * i; return { p, y: yS(p) }; });
  const lc = vis[vis.length - 1]?.close || 0;
  const pc = vis[vis.length - 2]?.close || lc;

  // X-axis date labels
  const dateLabels = useMemo(() => {
    if (!vis.length) return [];
    const step = LABEL_STEP[rangeDays] || 7;
    const labels = [];
    const minLabelGap = 72; // minimum px between labels to avoid overlap

    if (step === 'day') {
      // Intraday ranges: one label per trading day (at the session-open bar)
      let lastDay = null;
      for (let i = 0; i < vis.length; i++) {
        const dt = vis[i].datetime;
        if (!dt) continue;
        const d = new Date(dt);
        const dayKey = `${d.getUTCFullYear()}-${d.getUTCMonth()}-${d.getUTCDate()}`;
        if (dayKey !== lastDay) {
          const x = pad.left + i * gap + gap / 2;
          // Check for overlap with previous label
          if (labels.length === 0 || x - labels[labels.length - 1].x >= minLabelGap) {
            labels.push({ x, text: formatDate(d) });
          }
          lastDay = dayKey;
        }
      }
    } else {
      // Daily/weekly ranges: every Nth bar
      for (let i = 0; i < vis.length; i += step) {
        const dt = vis[i].datetime;
        if (!dt) continue;
        const x = pad.left + i * gap + gap / 2;
        if (labels.length === 0 || x - labels[labels.length - 1].x >= minLabelGap) {
          labels.push({ x, text: formatDate(new Date(dt)) });
        }
      }
    }
    return labels;
  }, [vis, rangeDays, gap, pad.left]);

  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg width={w} height={height} style={{ display: "block" }}>
        <rect x={0} y={0} width={w} height={height} fill={C.bg} />
        {pLabels.map((pl, i) => (<g key={i}><line x1={pad.left} y1={pl.y} x2={w - pad.right} y2={pl.y} stroke={C.border} strokeWidth={0.5} strokeDasharray="2,4" /><text x={w - pad.right + 5} y={pl.y + 3.5} fill={C.textMuted} fontSize={9} fontFamily={mono}>{pl.p.toFixed(0)}</text></g>))}
        {vis.map((c, i) => { const x = pad.left + i * gap + gap / 2, ig = c.close >= c.open, col = ig ? C.candleGreen : C.candleRed, bt = yS(Math.max(c.open, c.close)), bb = yS(Math.min(c.open, c.close)), bh = Math.max(1, bb - bt); return (<g key={i}><line x1={x} y1={yS(c.high)} x2={x} y2={yS(c.low)} stroke={col} strokeWidth={1} opacity={0.7} /><rect x={x - cw / 2} y={bt} width={cw} height={bh} fill={col} opacity={0.85} rx={0.5} /></g>); })}
        <path d={sPath(vL)} fill="none" stroke={C.smaRed} strokeWidth={1.8} opacity={0.75} />
        <path d={sPath(vM)} fill="none" stroke={C.smaOrange} strokeWidth={1.8} opacity={0.8} />
        <path d={sPath(vS)} fill="none" stroke={C.smaCyan} strokeWidth={1.8} opacity={0.85} />
        <line x1={pad.left} y1={yS(lc)} x2={w - pad.right} y2={yS(lc)} stroke={C.text} strokeWidth={0.6} strokeDasharray="4,4" opacity={0.2} />
        <rect x={w - pad.right + 1} y={yS(lc) - 9} width={48} height={18} rx={3} fill={lc >= pc ? C.candleGreen : C.candleRed} opacity={0.9} />
        <text x={w - pad.right + 5} y={yS(lc) + 4} fill="#fff" fontSize={10} fontFamily={mono} fontWeight={600}>{lc.toFixed(1)}</text>
        {/* X-axis date labels */}
        {dateLabels.map((dl, i) => (
          <text key={i} x={dl.x} y={height - 4} fill={C.textMuted} fontSize={10} fontFamily={mono} textAnchor="middle">{dl.text}</text>
        ))}
      </svg>
    </div>
  );
}

// ─── Main SMA Panel ───────────────────────────────────────────────
export default function SmaPanel({ candles, smaPeriods, onPeriodsChange, rangeDays = 90, onRangeChange, requestedRange, symbol = "QQQ" }) {
  const [expanded, setExpanded] = useState(true);
  const [showCfg, setShowCfg] = useState(false);

  const sS = useMemo(() => computeSma(candles, smaPeriods.short), [candles, smaPeriods.short]);
  const sM = useMemo(() => computeSma(candles, smaPeriods.mid), [candles, smaPeriods.mid]);
  const sL = useMemo(() => computeSma(candles, smaPeriods.long), [candles, smaPeriods.long]);
  const lS = sS.filter(Boolean).pop() || 0, lM = sM.filter(Boolean).pop() || 0, lL = sL.filter(Boolean).pop() || 0;
  const lc = candles[candles.length - 1]?.close || 0;

  // Detect truncation: backend returned fewer days than requested
  const actualDays = useMemo(() => {
    if (!candles.length || !candles[0]?.datetime || !candles[candles.length - 1]?.datetime) return null;
    const first = candles[0].datetime;
    const last = candles[candles.length - 1].datetime;
    return Math.round((last - first) / (1000 * 60 * 60 * 24));
  }, [candles]);
  const isTruncated = requestedRange && actualDays !== null && actualDays < requestedRange * 0.8;

  let al, aLabel, aCol, aIcon;
  if (lS > lM && lM > lL) { al = "bullish"; aLabel = "Bullish Alignment"; aCol = C.green; aIcon = "▲"; }
  else if (lS < lM && lM < lL) { al = "bearish"; aLabel = "Bearish Alignment"; aCol = C.red; aIcon = "▼"; }
  else { al = "mixed"; aLabel = "Mixed — No Signal"; aCol = C.amber; aIcon = "◆"; }

  const smaRows = [{ l: `SMA ${smaPeriods.short}`, v: lS, c: C.smaCyan }, { l: `SMA ${smaPeriods.mid}`, v: lM, c: C.smaOrange }, { l: `SMA ${smaPeriods.long}`, v: lL, c: C.smaRed }];
  const bgC = al === "bullish" ? "#081a15" : al === "bearish" ? "#1a0808" : "#1a1508";

  const controlStyle = {
    padding: "5px 10px",
    borderRadius: 5,
    border: `1px solid ${C.border}`,
    backgroundColor: "transparent",
    color: C.textMuted,
    fontSize: 11,
    cursor: "pointer",
    fontFamily: mono,
  };

  return (
    <div style={{ marginBottom: 14, borderRadius: 10, border: `1px solid ${aCol}20`, backgroundColor: bgC, overflow: "hidden" }}>
      <button onClick={() => setExpanded(!expanded)} style={{ width: "100%", padding: "10px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", background: "none", border: "none", cursor: "pointer", borderBottom: expanded ? `1px solid ${aCol}15` : "none" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 16, color: aCol, fontWeight: 800 }}>{aIcon}</span>
          <span style={{ fontSize: 13, fontWeight: 700, color: aCol }}>{aLabel}</span>
          <span style={{ color: C.textMuted, fontSize: 11 }}>·</span>
          <span style={{ color: C.textDim, fontSize: 11, fontFamily: mono }}>{symbol} {lc.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {!expanded && smaRows.map(s => (<span key={s.l} style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 2, borderRadius: 1, backgroundColor: s.c, display: "inline-block" }} /><span style={{ fontSize: 10.5, color: s.c, fontFamily: mono, fontWeight: 600 }}>{s.v.toFixed(1)}</span></span>))}
          <span style={{ color: C.textMuted, fontSize: 16, transition: "transform 0.2s", transform: expanded ? "rotate(180deg)" : "rotate(0)", display: "inline-block" }}>▾</span>
        </div>
      </button>
      {expanded && (<div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 16px", borderBottom: `1px solid ${C.border}20` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
            <div><div style={{ fontSize: 9, color: C.textMuted, textTransform: "uppercase" }}>Price</div><div style={{ fontSize: 18, fontWeight: 700, color: C.text, fontFamily: mono }}>{lc.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div></div>
            {smaRows.map(s => (<div key={s.l}><div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 1 }}><div style={{ width: 12, height: 2.5, borderRadius: 1, backgroundColor: s.c }} /><span style={{ fontSize: 9.5, color: C.textMuted }}>{s.l}</span></div><div style={{ fontSize: 14, fontWeight: 600, color: s.c, fontFamily: mono }}>{s.v.toFixed(2)}</div></div>))}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {isTruncated && (
              <span style={{ fontSize: 9, fontFamily: mono, color: C.textMuted }}>
                Showing {actualDays}d (max available)
              </span>
            )}
            {onRangeChange && (
              <select
                value={rangeDays}
                onChange={(e) => onRangeChange(Number(e.target.value))}
                onClick={(e) => e.stopPropagation()}
                style={{ ...controlStyle, appearance: "auto" }}
              >
                {RANGE_OPTIONS.map(r => (
                  <option key={r} value={r}>{r}d</option>
                ))}
              </select>
            )}
            <button onClick={(e) => { e.stopPropagation(); setShowCfg(!showCfg); }} style={{ ...controlStyle, backgroundColor: showCfg ? C.surfaceAlt : "transparent" }}>⚙ Periods</button>
          </div>
        </div>
        {showCfg && (<div style={{ padding: "6px 16px 8px", borderBottom: `1px solid ${C.border}20`, backgroundColor: `${C.card}80` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            {[{ k: "short", l: "Fast", c: C.smaCyan }, { k: "mid", l: "Medium", c: C.smaOrange }, { k: "long", l: "Slow", c: C.smaRed }].map(({ k, l, c }) => (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <div style={{ width: 10, height: 2.5, borderRadius: 1, backgroundColor: c }} />
                <span style={{ fontSize: 10, color: C.textDim }}>{l}</span>
                <input type="number" value={smaPeriods[k]} onChange={(e) => { const v = parseInt(e.target.value); if (!isNaN(v)) onPeriodsChange({ ...smaPeriods, [k]: v }); }}
                  style={{ width: 48, padding: "3px 5px", borderRadius: 4, border: `1px solid ${C.border}`, backgroundColor: C.bg, color: c, fontSize: 12, fontFamily: mono, outline: "none", textAlign: "center" }} />
              </div>))}
            <span style={{ fontSize: 10, color: C.textMuted }}>Common: 8/21/50 · 10/50/200</span>
          </div>
        </div>)}
        <CandlestickChart candles={candles} smaPeriods={smaPeriods} rangeDays={rangeDays} height={304} />
      </div>)}
    </div>
  );
}

// Helper: compute SMA data for external use (AskClaudePanel, etc.)
export { computeSma };
