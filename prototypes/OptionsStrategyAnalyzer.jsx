import { useState, useCallback } from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import {
  ChevronDown, ChevronRight, Zap, Brain, Bell,
  Loader2, Shield, BarChart3, Crosshair, Activity,
} from "lucide-react";

/* ═══════════════════════════════════════════
   TOKENS
   ═══════════════════════════════════════════ */
const T = {
  bg:       "#13161A",
  panel:    "#181C22",
  surface:  "#1D2128",
  raised:   "#242930",
  border:   "#2A2F38",
  borderLt: "#353B46",
  text:     "#E1E4EB",
  sub:      "#9CA3B0",
  dim:      "#5E6676",
  bull:     "#34D399",
  bullBg:   "#34D39914",
  bear:     "#F87171",
  bearBg:   "#F8717114",
  ai:       "#8A70FF",
  aiBg:     "#8A70FF14",
  aiGlow:   "#8A70FF50",
  green:    "#34D399",
  yellow:   "#FBBF24",
  red:      "#F87171",
  mono:     "'IBM Plex Mono', monospace",
  sans:     "'DM Sans', sans-serif",
};

/* ═══════════════════════════════════════════
   MOCK DATA — 20 trades with correct math
   ═══════════════════════════════════════════ */
const TICKERS = [
  "MSFT","AAPL","NVDA","AMZN","GOOG","META","TSLA","SPY","QQQ","AMD",
  "NFLX","CRM","AVGO","LLY","JPM","V","MA","ORCL","UNH","XOM",
];

const CLAUDE_REASONS = [
  "Testing 200DMA resistance.",
  "High IV Crush risk post-earnings.",
  "SMA alignment confirmed bullish.",
  "Sector rotation pressure noted.",
  "Low vol regime favors spreads.",
  "Breakout level approaching.",
  "Elevated put skew detected.",
  "Earnings catalyst in 3 sessions.",
  "Institutional flow is mixed.",
  "Support cluster at lower strike.",
];

function buildBreakdown(score) {
  const weights = [0.35, 0.25, 0.20, 0.15, 0.05];
  const rawVals = weights.map(() => 0.3 + Math.random() * 0.7);
  const rawContribs = rawVals.map((v, i) => v * weights[i]);
  const rawSum = rawContribs.reduce((a, b) => a + b, 0);
  const scale = score / rawSum;
  const contribs = rawContribs.map((c) => +(c * scale).toFixed(4));
  const drift = +(score - contribs.reduce((a, b) => a + b, 0)).toFixed(4);
  contribs[0] = +(contribs[0] + drift).toFixed(4);
  const scaledVals = rawVals.map((v, i) => +(v * scale).toFixed(2));

  return [
    { label: "Expected Value", val: scaledVals[0], w: "35%", c: contribs[0], formula: "(prob × maxP) − ((1−prob) × maxL)" },
    { label: "Reward : Risk",  val: scaledVals[1], w: "25%", c: contribs[1], formula: "maxP / maxL" },
    { label: "Probability",    val: `${(scaledVals[2] * 100).toFixed(0)}%`, w: "20%", c: contribs[2], formula: "≈ short leg delta" },
    { label: "Liquidity",      val: Math.round(1000 + Math.random() * 8000), w: "15%", c: contribs[3], formula: "Σ(Vol + OI)" },
    { label: "Theta Eff.",     val: +(0.001 + Math.random() * 0.008).toFixed(4), w: "5%", c: contribs[4], formula: "|net_θ / net_debit|" },
  ];
}

function pickPip() {
  return ["GREEN", "YELLOW", "RED"][Math.floor(Math.random() * 3)];
}

function genTrades() {
  const msft = {
    id: "msft_bear_410",
    type: "BEAR PUT",
    ticker: "MSFT",
    strategy: "MSFT 410/400",
    score: 0.5003,
    net: 4.25,
    maxProfit: 5.75,
    rr: 1.35,
    delta: 0.5528,
    idealEntry: 3.90,
    breakdown: [
      { label: "Expected Value", val: 1.21,   w: "35%", c: 0.1935, formula: "(prob × maxP) − ((1−prob) × maxL)" },
      { label: "Reward : Risk",  val: 1.35,   w: "25%", c: 0.0708, formula: "maxP / maxL" },
      { label: "Probability",    val: "55%",   w: "20%", c: 0.0981, formula: "≈ short leg delta" },
      { label: "Liquidity",      val: 3334,    w: "15%", c: 0.0990, formula: "Σ(Vol + OI)" },
      { label: "Theta Eff.",     val: 0.0044,  w: "5%",  c: 0.0389, formula: "|net_θ / net_debit|" },
    ],
    claudeScorecard: [
      { cat: "Monetary",  pip: "GREEN",  note: "Positive EV; Risk scaled." },
      { cat: "Market",    pip: "YELLOW", note: "Testing 200DMA resistance." },
      { cat: "Timing",    pip: "RED",    note: "High IV Crush risk." },
      { cat: "Execution", pip: "GREEN",  note: "Narrow Bid/Ask spread." },
    ],
    payoffData: [
      { price: 390, pl: 5.75 }, { price: 400, pl: 5.75 },
      { price: 410, pl: -4.25 }, { price: 420, pl: -4.25 },
    ],
  };

  const rest = TICKERS.slice(1).map((tk, i) => {
    const isBull = Math.random() > 0.45;
    const base = 80 + Math.round(Math.random() * 500);
    const w = [5, 10][Math.floor(Math.random() * 2)];
    const longS = base;
    const shortS = isBull ? base + w : base - w;
    const net = +(1 + Math.random() * 5).toFixed(2);
    const maxP = +(w - net).toFixed(2) > 0 ? +(w - net).toFixed(2) : +(1 + Math.random() * 4).toFixed(2);
    const rr = +(maxP / net).toFixed(2);
    const score = +(0.35 + Math.random() * 0.55).toFixed(4);
    const delta = +(0.28 + Math.random() * 0.40).toFixed(4);
    const ideal = +(net * (0.82 + Math.random() * 0.12)).toFixed(2);

    const breakdown = buildBreakdown(score);

    const payoffData = isBull
      ? [
          { price: longS - 15, pl: -net },
          { price: longS, pl: -net },
          { price: shortS, pl: maxP },
          { price: shortS + 15, pl: maxP },
        ]
      : [
          { price: shortS - 15, pl: maxP },
          { price: shortS, pl: maxP },
          { price: longS, pl: -net },
          { price: longS + 15, pl: -net },
        ];

    return {
      id: `${tk.toLowerCase()}_${i}`,
      type: isBull ? "BULL CALL" : "BEAR PUT",
      ticker: tk,
      strategy: `${tk} ${longS}/${shortS}`,
      score,
      net,
      maxProfit: maxP,
      rr,
      delta,
      idealEntry: ideal,
      breakdown,
      claudeScorecard: [
        { cat: "Monetary",  pip: pickPip(), note: maxP > net ? "Positive EV; Risk scaled." : "Marginal EV ratio." },
        { cat: "Market",    pip: pickPip(), note: CLAUDE_REASONS[Math.floor(Math.random() * CLAUDE_REASONS.length)] },
        { cat: "Timing",    pip: pickPip(), note: CLAUDE_REASONS[Math.floor(Math.random() * CLAUDE_REASONS.length)] },
        { cat: "Execution", pip: pickPip(), note: rr > 1.2 ? "Narrow Bid/Ask spread." : "Wide spread — size carefully." },
      ],
      payoffData,
    };
  });

  return [msft, ...rest].sort((a, b) => b.score - a.score);
}

/* ═══════════════════════════════════════════
   COMPONENTS
   ═══════════════════════════════════════════ */

function PayoffChart({ data, isBull }) {
  const accent = isBull ? T.bull : T.bear;
  const gradId = isBull ? "gBull" : "gBear";
  return (
    <ResponsiveContainer width="100%" height={170}>
      <AreaChart data={data} margin={{ top: 8, right: 16, left: 4, bottom: 0 }}>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={accent} stopOpacity={0.30} />
            <stop offset="100%" stopColor={accent} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={T.border} vertical={false} />
        <XAxis dataKey="price" tick={{ fill: T.dim, fontSize: 10, fontFamily: T.mono }} axisLine={{ stroke: T.border }} tickLine={false} />
        <YAxis tick={{ fill: T.dim, fontSize: 10, fontFamily: T.mono }} axisLine={false} tickLine={false} width={36} />
        <ReferenceLine y={0} stroke={T.borderLt} strokeDasharray="4 2" />
        <Tooltip
          contentStyle={{ background: T.raised, border: `1px solid ${T.borderLt}`, borderRadius: 6, fontSize: 11, fontFamily: T.mono, color: T.text }}
          formatter={(v) => [v.toFixed(2), "P/L"]}
          labelFormatter={(l) => `Price: ${l}`}
        />
        <Area type="linear" dataKey="pl" stroke={accent} strokeWidth={2} fill={`url(#${gradId})`} dot={false} activeDot={{ r: 3, fill: accent, strokeWidth: 0 }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function Pip({ color }) {
  const c = color === "GREEN" ? T.green : color === "YELLOW" ? T.yellow : T.red;
  return (
    <span style={{
      display: "inline-block", width: 8, height: 8, borderRadius: "50%",
      background: c, boxShadow: `0 0 6px ${c}60`, flexShrink: 0,
    }} />
  );
}

function ScoreBreakdown({ breakdown, totalScore }) {
  const sum = breakdown.reduce((a, r) => a + r.c, 0);
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
        <BarChart3 size={13} color={T.dim} />
        <span style={{ fontSize: 10, fontWeight: 600, color: T.dim, letterSpacing: "0.08em", textTransform: "uppercase", fontFamily: T.sans }}>
          Score Breakdown
        </span>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: T.mono }}>
        <thead>
          <tr>
            {["Metric", "Value", "Weight", "Contrib."].map((h) => (
              <th key={h} style={{ textAlign: "left", padding: "4px 6px", color: T.dim, fontWeight: 500, fontSize: 9, letterSpacing: "0.06em", borderBottom: `1px solid ${T.border}`, textTransform: "uppercase" }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {breakdown.map((r, i) => (
            <tr key={i} style={{ borderBottom: `1px solid ${T.border}22` }}>
              <td style={{ padding: "5px 6px", color: T.sub, fontFamily: T.sans, fontSize: 11 }}>{r.label}</td>
              <td style={{ padding: "5px 6px", color: T.text, fontWeight: 600 }}>{typeof r.val === "number" ? (r.val < 1 ? r.val.toFixed(4) : r.val.toFixed(2)) : r.val}</td>
              <td style={{ padding: "5px 6px", color: T.dim }}>{r.w}</td>
              <td style={{ padding: "5px 6px", color: T.bull, fontWeight: 600 }}>+{r.c.toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr style={{ borderTop: `1px solid ${T.borderLt}` }}>
            <td colSpan={3} style={{ padding: "6px 6px", color: T.sub, fontWeight: 700, fontFamily: T.sans, fontSize: 11 }}>Composite Score</td>
            <td style={{ padding: "6px 6px", color: T.text, fontWeight: 800, fontSize: 13 }}>{sum.toFixed(4)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function ClaudeScorecard({ scorecard }) {
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
        <Brain size={13} color={T.ai} />
        <span style={{ fontSize: 10, fontWeight: 600, color: T.ai, letterSpacing: "0.08em", textTransform: "uppercase", fontFamily: T.sans }}>
          Claude Scorecard
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
        {scorecard.map((row, i) => (
          <div key={i} style={{
            display: "grid", gridTemplateColumns: "80px 14px 1fr",
            alignItems: "center", gap: 8, padding: "7px 0",
            borderBottom: i < scorecard.length - 1 ? `1px solid ${T.border}22` : "none",
          }}>
            <span style={{ fontSize: 11, color: T.sub, fontFamily: T.sans, fontWeight: 500 }}>{row.cat}</span>
            <Pip color={row.pip} />
            <span style={{ fontSize: 11, color: T.dim, fontFamily: T.sans }}>{row.note}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ExecutionPanel({ idealEntry, net }) {
  const pctSave = (((net - idealEntry) / net) * 100).toFixed(1);
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
        <Crosshair size={13} color={T.ai} />
        <span style={{ fontSize: 10, fontWeight: 600, color: T.ai, letterSpacing: "0.08em", textTransform: "uppercase", fontFamily: T.sans }}>
          Execution
        </span>
      </div>
      <div style={{ background: T.raised, borderRadius: 8, padding: "12px 14px", border: `1px solid ${T.border}` }}>
        <div style={{ fontSize: 10, color: T.dim, marginBottom: 4 }}>Ideal Entry</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
          <span style={{ fontSize: 22, fontWeight: 800, color: T.text, fontFamily: T.mono }}>{idealEntry.toFixed(2)}</span>
          <span style={{ fontSize: 11, color: T.bull, fontWeight: 600, fontFamily: T.mono }}>−{pctSave}% vs ask</span>
        </div>
      </div>
      <button
        style={{
          display: "flex", alignItems: "center", gap: 6, marginTop: 10,
          padding: "8px 16px", borderRadius: 6, border: `1px solid ${T.ai}30`,
          background: T.aiBg, color: T.ai, fontSize: 12, fontWeight: 600,
          cursor: "pointer", fontFamily: T.sans, transition: "all 0.15s", width: "100%", justifyContent: "center",
        }}
        onMouseEnter={(e) => { e.currentTarget.style.background = T.ai + "28"; e.currentTarget.style.borderColor = T.ai + "60"; }}
        onMouseLeave={(e) => { e.currentTarget.style.background = T.aiBg; e.currentTarget.style.borderColor = T.ai + "30"; }}
      >
        <Bell size={13} /> Set Alert at {idealEntry.toFixed(2)}
      </button>
    </div>
  );
}

function TradeRow({ trade, expanded, onToggle, validated, idx }) {
  const isBull = trade.type === "BULL CALL";
  const accent = isBull ? T.bull : T.bear;
  const badgeBg = isBull ? T.bullBg : T.bearBg;

  return (
    <div style={{ borderBottom: `1px solid ${T.border}`, animation: `rowIn 0.3s ease ${idx * 20}ms both` }}>
      <div
        onClick={onToggle}
        role="button"
        tabIndex={0}
        style={{
          display: "grid",
          gridTemplateColumns: "24px 88px 52px 72px 92px 60px 60px 64px 60px 1fr",
          alignItems: "center", padding: "9px 14px", cursor: "pointer", gap: 2, minHeight: 40,
          transition: "background 0.12s",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = T.surface)}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      >
        <div style={{ color: T.dim, display: "flex" }}>
          {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </div>

        <span style={{
          fontSize: 8.5, fontWeight: 700, letterSpacing: "0.05em", padding: "2px 6px",
          borderRadius: 3, background: badgeBg, color: accent, fontFamily: T.mono, whiteSpace: "nowrap",
          border: `1px solid ${accent}20`,
        }}>
          {trade.type}
        </span>

        <span style={{ fontWeight: 700, color: T.text, fontSize: 12, fontFamily: T.mono }}>{trade.ticker}</span>

        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ fontWeight: 800, fontSize: 15, color: T.text, fontFamily: T.mono }}>
            {trade.score.toFixed(2)}
          </span>
          {validated && (
            <span style={{
              fontSize: 8, fontWeight: 700, color: T.ai, background: T.aiBg,
              padding: "1px 4px", borderRadius: 3, fontFamily: T.mono, letterSpacing: "0.04em",
              border: `1px solid ${T.ai}25`,
            }}>
              AI+
            </span>
          )}
        </div>

        <span style={{ color: T.sub, fontSize: 11, fontFamily: T.mono }}>{trade.strategy.split(" ").pop()}</span>
        <span style={{ color: T.sub, fontSize: 11, fontFamily: T.mono }}>{trade.net.toFixed(2)}</span>
        <span style={{ color: accent, fontWeight: 600, fontSize: 11, fontFamily: T.mono }}>{trade.rr.toFixed(2)}</span>
        <span style={{ color: T.dim, fontSize: 10, fontFamily: T.mono }}>{trade.delta.toFixed(4)}</span>
        <span style={{ color: T.sub, fontSize: 11, fontFamily: T.mono }}>{trade.maxProfit.toFixed(2)}</span>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 4, alignItems: "center" }}>
          {validated && trade.claudeScorecard.map((s, j) => (
            <Pip key={j} color={s.pip} />
          ))}
        </div>
      </div>

      {expanded && (
        <div style={{
          background: T.panel, borderTop: `1px solid ${T.border}`,
          padding: "20px 18px",
          display: "grid", gridTemplateColumns: "1.1fr 1.3fr 1fr 0.8fr", gap: 20,
          animation: "xrayIn 0.25s ease",
        }}>
          <ScoreBreakdown breakdown={trade.breakdown} totalScore={trade.score} />
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
              <Activity size={13} color={T.dim} />
              <span style={{ fontSize: 10, fontWeight: 600, color: T.dim, letterSpacing: "0.08em", textTransform: "uppercase", fontFamily: T.sans }}>Payoff Diagram</span>
            </div>
            <PayoffChart data={trade.payoffData} isBull={isBull} />
          </div>
          <ClaudeScorecard scorecard={trade.claudeScorecard} />
          <ExecutionPanel idealEntry={trade.idealEntry} net={trade.net} />
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════
   MAIN
   ═══════════════════════════════════════════ */
export default function App() {
  const [trades, setTrades] = useState(() => genTrades());
  const [expandedId, setExpandedId] = useState(null);
  const [validated, setValidated] = useState(false);
  const [validating, setValidating] = useState(false);
  const [progress, setProgress] = useState(0);

  const handleValidate = useCallback(() => {
    if (validating || validated) return;
    setValidating(true);
    setProgress(0);
    const start = Date.now();
    const dur = 2000;
    const tick = () => {
      const pct = Math.min((Date.now() - start) / dur, 1);
      setProgress(pct);
      if (pct < 1) { requestAnimationFrame(tick); }
      else {
        setTrades((prev) =>
          prev.map((t) => ({ ...t, score: +(t.score + (Math.random() * 0.06 - 0.03)).toFixed(4) }))
              .sort((a, b) => b.score - a.score)
        );
        setValidated(true);
        setValidating(false);
      }
    };
    requestAnimationFrame(tick);
  }, [validating, validated]);

  const toggleRow = useCallback((id) => {
    setExpandedId((prev) => (prev === id ? null : id));
  }, []);

  const bullCount = trades.filter((t) => t.type === "BULL CALL").length;
  const bearCount = trades.length - bullCount;

  return (
    <div style={{ background: T.bg, minHeight: "100vh", color: T.text, fontFamily: T.sans }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=DM+Sans:wght@400;500;600;700;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: ${T.bg}; }
        ::-webkit-scrollbar-thumb { background: ${T.border}; border-radius: 3px; }
        @keyframes rowIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes xrayIn { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulseGlow { 0%,100% { box-shadow: 0 0 8px ${T.aiGlow}; } 50% { box-shadow: 0 0 20px ${T.aiGlow}; } }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
      `}</style>

      {/* HEADER */}
      <div style={{
        padding: "16px 22px", borderBottom: `1px solid ${T.border}`,
        display: "flex", alignItems: "center", justifyContent: "space-between", background: T.panel,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 7,
            background: `linear-gradient(135deg, ${T.ai}22, ${T.bull}15)`,
            border: `1px solid ${T.ai}25`, display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <Shield size={16} color={T.ai} />
          </div>
          <div>
            <h1 style={{ fontSize: 15, fontWeight: 700, letterSpacing: "-0.01em" }}>Options Strategy Analyzer</h1>
            <span style={{ fontSize: 10, color: T.dim }}>Algorithm → AI Validation Pipeline</span>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ display: "flex", gap: 8 }}>
            <span style={{ fontSize: 10, color: T.bull, background: T.bullBg, padding: "3px 8px", borderRadius: 4, fontFamily: T.mono, fontWeight: 600, border: `1px solid ${T.bull}18` }}>
              {bullCount} Bull
            </span>
            <span style={{ fontSize: 10, color: T.bear, background: T.bearBg, padding: "3px 8px", borderRadius: 4, fontFamily: T.mono, fontWeight: 600, border: `1px solid ${T.bear}18` }}>
              {bearCount} Bear
            </span>
          </div>

          <button
            onClick={handleValidate}
            disabled={validating || validated}
            style={{
              display: "flex", alignItems: "center", gap: 7,
              padding: "9px 18px", borderRadius: 7, border: "none",
              background: validated ? T.aiBg : `linear-gradient(135deg, ${T.ai}, ${T.ai}DD)`,
              color: validated ? T.ai : "#fff",
              fontSize: 12, fontWeight: 700, fontFamily: T.sans,
              cursor: validating || validated ? "default" : "pointer",
              opacity: validating ? 0.7 : 1, transition: "all 0.2s", letterSpacing: "0.02em",
              ...(validated ? { border: `1px solid ${T.ai}30` } : {}),
            }}
          >
            {validating ? (
              <span style={{ display: "flex", alignItems: "center", gap: 7 }}><Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> Analyzing...</span>
            ) : validated ? (
              <span style={{ display: "flex", alignItems: "center", gap: 7 }}><Brain size={14} /> Validated ✓</span>
            ) : (
              <span style={{ display: "flex", alignItems: "center", gap: 7 }}><Zap size={14} /> Validate &amp; Rerank</span>
            )}
          </button>
        </div>
      </div>

      {validating && (
        <div style={{ height: 2, background: T.border }}>
          <div style={{
            height: "100%", width: `${progress * 100}%`,
            background: `linear-gradient(90deg, ${T.ai}, ${T.bull})`,
            transition: "width 0.08s linear", boxShadow: `0 0 10px ${T.aiGlow}`,
          }} />
        </div>
      )}

      {/* COLUMN HEADERS */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "24px 88px 52px 72px 92px 60px 60px 64px 60px 1fr",
        alignItems: "center", padding: "7px 14px", gap: 2,
        borderBottom: `1px solid ${T.border}`, background: T.panel,
        position: "sticky", top: 0, zIndex: 10,
      }}>
        <div />
        {["Type", "Ticker", "Score", "Spread", "Net", "R:R", "Delta", "MaxP", validated ? "Health" : ""].map((h, i) => (
          <span key={i} style={{
            fontSize: 9, fontWeight: 600, color: T.dim, letterSpacing: "0.08em",
            textTransform: "uppercase", fontFamily: T.sans,
            textAlign: i === 9 ? "right" : "left", paddingRight: i === 9 ? 6 : 0,
          }}>
            {h}
          </span>
        ))}
      </div>

      {/* LIST */}
      <div>
        {trades.map((t, i) => (
          <TradeRow
            key={t.id} trade={t} idx={i}
            expanded={expandedId === t.id}
            onToggle={() => toggleRow(t.id)}
            validated={validated}
          />
        ))}
      </div>

      {/* OVERLAY */}
      {validating && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(13,15,19,0.80)",
          backdropFilter: "blur(6px)", display: "flex", alignItems: "center",
          justifyContent: "center", zIndex: 100, animation: "fadeIn 0.2s ease",
        }}>
          <div style={{
            background: T.panel, border: `1px solid ${T.ai}25`, borderRadius: 14,
            padding: "32px 44px", textAlign: "center",
            animation: "pulseGlow 2s ease infinite",
          }}>
            <Brain size={32} color={T.ai} style={{ marginBottom: 14 }} />
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 5 }}>
              Validating {trades.length} trades...
            </div>
            <div style={{ fontSize: 12, color: T.sub, marginBottom: 18 }}>
              Evaluating EV, market structure &amp; execution quality
            </div>
            <div style={{ width: 200, height: 3, background: T.border, borderRadius: 2, margin: "0 auto", overflow: "hidden" }}>
              <div style={{
                height: "100%", width: `${progress * 100}%`,
                background: `linear-gradient(90deg, ${T.ai}, ${T.bull})`,
                borderRadius: 2, transition: "width 0.08s linear",
              }} />
            </div>
            <div style={{ fontSize: 11, color: T.dim, marginTop: 8, fontFamily: T.mono }}>
              {Math.round(progress * 100)}%
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
