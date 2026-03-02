import { useState, useEffect, useRef } from "react";
import { C, mono } from "../styles/tokens";
import { evaluateTrade, followUpQuestion } from "../api/client";

// Inject spin animation
if (typeof document !== "undefined" && !document.getElementById("claude-spin")) {
  const s = document.createElement("style");
  s.id = "claude-spin";
  s.textContent = `@keyframes spin{to{transform:rotate(360deg)}}`;
  document.head.appendChild(s);
}

function preScreenTrade(trade, thesis) {
  const flags = [];
  if (trade.reward_risk_ratio < 1.5) flags.push({ level: "warn", msg: `R:R is ${trade.reward_risk_ratio.toFixed(2)} — below 1.5 minimum` });
  if (trade.net_debit * 100 > (thesis.risk_budget || 500)) flags.push({ level: "warn", msg: "Total cost exceeds risk budget" });
  if (thesis.direction === "Bullish" && thesis.target && thesis.target < trade.short_strike) flags.push({ level: "alert", msg: `Target $${thesis.target} doesn't reach short strike $${trade.short_strike}` });
  if (thesis.direction === "Bearish" && thesis.target && thesis.target > trade.long_strike) flags.push({ level: "alert", msg: `Target $${thesis.target} doesn't reach long strike $${trade.long_strike}` });
  if (trade.prob_of_profit < 0.45) flags.push({ level: "warn", msg: `Low probability (${(trade.prob_of_profit * 100).toFixed(0)}%) — consider wider spread` });
  return flags;
}

const VC = {
  EXECUTE: { bg: C.greenBg, border: C.green, text: C.green, icon: "✅" },
  WAIT: { bg: C.amberBg, border: C.amber, text: C.amber, icon: "⏳" },
  PASS: { bg: C.redBg, border: C.red, text: C.red, icon: "🚫" },
};

export default function AskClaudePanel({ open, onClose, trade, smaData, smaPeriods }) {
  const [thesis, setThesis] = useState({ direction: "Bullish", timeframe: 30, target: "", conviction: "Medium", risk_budget: 500 });
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [followUp, setFollowUp] = useState("");
  const scrollRef = useRef(null);

 // BUG FIX: Reset ALL evaluation state when a different trade is selected.
  // WHY trade?.id alone wasn't enough: the id is constructed dynamically and
  // might not change between two different trades in some edge cases.
  // Watching strike + expiration guarantees we catch every trade switch.
  useEffect(() => {
    if (trade) {
      setMessages([]);
      setError(null);
      setFollowUp("");
      setThesis(t => ({ ...t, target: "" }));
    }
  }, [trade?.long_strike, trade?.short_strike, trade?.expiration]);
  // Auto-scroll only for follow-up messages (2+ assistant responses).
  // WHY: The first evaluation result should show from the top (verdict first).
  // Follow-ups should scroll to the bottom so you see the latest reply.
  useEffect(() => {
    if (scrollRef.current) {
      const assistantCount = messages.filter(m => m.role === "assistant").length;
      if (assistantCount > 1) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      } else {
        scrollRef.current.scrollTop = 0;
      }
    }
  }, [messages]);

  if (!trade) return null;

  const lastClose = smaData?.price || 0;
  const smaS = smaData?.smaShort || 0, smaM = smaData?.smaMid || 0, smaL = smaData?.smaLong || 0;
  const alignment = smaS > smaM && smaM > smaL ? "Bullish - price above all 3 SMAs" : smaS < smaM && smaM < smaL ? "Bearish - price below all 3 SMAs" : "Mixed - SMAs not aligned";
  const targetNum = parseFloat(thesis.target) || 0;
  const flags = preScreenTrade(trade, { ...thesis, target: targetNum });

  const handleEvaluate = async () => {
    setLoading(true); setError(null);
    try {
      const res = await evaluateTrade({
        symbol: trade.symbol, current_price: lastClose,
        sma_short: smaS, sma_mid: smaM, sma_long: smaL, sma_periods: smaPeriods, vix: 19.5,
        strategy_type: "Vertical Spread",
        spread: `${trade.long_strike}/${trade.short_strike} ${trade.option_type === "call" ? "Call" : "Put"} Debit Spread`,
        expiration: trade.expiration, debit_paid: trade.net_debit, max_profit: trade.max_profit,
        rr_ratio: trade.reward_risk_ratio, prob_of_profit: trade.prob_of_profit,
        composite_score: trade.composite_score, num_contracts: 1,
        thesis: { direction: thesis.direction, timeframe_days: thesis.timeframe, expected_move_target: targetNum || null, conviction: thesis.conviction, risk_budget: thesis.risk_budget },
      });
      setMessages(prev => [...prev,
        { role: "user", type: "evaluation", content: `Evaluated ${trade.symbol} ${trade.long_strike}/${trade.short_strike}` },
        { role: "assistant", verdict: res.verdict, content: res.analysis, exitLevels: res.exit_levels, preScreenFlags: res.pre_screen_flags, model: res.model_used, provider: res.provider, tokens: { input: res.input_tokens, output: res.output_tokens }, timestamp: new Date().toISOString() },
      ]);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  };

  const handleFollowUp = async () => {
    if (!followUp.trim()) return;
    const q = followUp; setFollowUp(""); setLoading(true); setError(null);
    const history = messages.map(m => ({ role: m.role, content: m.content || "" }));
    setMessages(prev => [...prev, { role: "user", content: q }]);
    try {
      const res = await followUpQuestion(q, history);
      setMessages(prev => [...prev, { role: "assistant", content: res.response, model: res.model_used, provider: res.provider, timestamp: new Date().toISOString() }]);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  };

  const ThesisBtn = ({ items, value, onChange, colorFn }) => (
    <div style={{ display: "flex", gap: 4 }}>{items.map(d => {
      const active = value === d; const col = colorFn ? colorFn(d, active) : {};
      return <button key={d} onClick={() => onChange(d)} style={{ flex: 1, padding: "5px 0", borderRadius: 5, fontSize: 11, fontWeight: 600, cursor: "pointer", border: active ? `1.5px solid ${col.border || C.accent}` : `1px solid ${C.border}`, backgroundColor: active ? (col.bg || C.accentGlow) : "transparent", color: active ? (col.text || C.accent) : C.textMuted }}>{d}</button>;
    })}</div>
  );

  const dirColors = (d, a) => ({ Bullish: { border: C.green, bg: C.greenBg, text: C.green }, Bearish: { border: C.red, bg: C.redBg, text: C.red }, Neutral: { border: C.amber, bg: C.amberBg, text: C.amber } }[d] || {});

  const ExitRow = ({ icon, label, val, action }) => (
    <div style={{ display: "grid", gridTemplateColumns: "24px 80px 60px 1fr", gap: 6, alignItems: "center", padding: "4px 6px", borderRadius: 4, backgroundColor: C.surfaceAlt }}>
      <span style={{ fontSize: 12 }}>{icon}</span>
      <span style={{ fontSize: 11, color: C.textDim }}>{label}</span>
      <span style={{ fontSize: 11, color: C.text, fontFamily: mono, fontWeight: 600 }}>{val}</span>
      <span style={{ fontSize: 10, color: C.textMuted }}>{action}</span>
    </div>
  );

  return (<>
    {open && <div onClick={onClose} style={{ position: "fixed", inset: 0, backgroundColor: C.overlay, zIndex: 90 }} />}
    <div style={{ position: "fixed", top: 0, right: 0, bottom: 0, width: 480, backgroundColor: C.surface, borderLeft: `1px solid ${C.claudeBorder}`, zIndex: 100, transform: open ? "translateX(0)" : "translateX(100%)", transition: "transform 0.25s cubic-bezier(0.4,0,0.2,1)", display: "flex", flexDirection: "column", boxShadow: open ? "-8px 0 30px rgba(0,0,0,0.4)" : "none" }}>
      {/* Header */}
      <div style={{ padding: "12px 18px", borderBottom: `1px solid ${C.border}`, flexShrink: 0, display: "flex", justifyContent: "space-between", alignItems: "center", background: `linear-gradient(135deg, ${C.claudeDim}, ${C.surface})` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}><span style={{ fontSize: 18 }}>✦</span><div><h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: C.claudeAccent }}>Ask Claude</h2><p style={{ margin: "1px 0 0", fontSize: 10.5, color: C.textDim }}>Trade Evaluation</p></div></div>
        <button onClick={onClose} style={{ background: "none", border: "none", color: C.textMuted, fontSize: 20, cursor: "pointer", padding: 4 }}>✕</button>
      </div>

      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "14px 18px" }}>
        {/* Trade context */}
        <div style={{ padding: 12, borderRadius: 8, border: `1px solid ${C.border}`, backgroundColor: C.card, marginBottom: 12 }}>
          <div style={{ fontSize: 10, color: C.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>Selected Trade</div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span style={{ color: trade.spread_type === "bull_call" ? C.green : C.red, fontWeight: 800 }}>{trade.spread_type === "bull_call" ? "▲" : "▼"}</span>
            <span style={{ color: C.text, fontSize: 14, fontWeight: 700 }}>{trade.symbol} {trade.long_strike}/{trade.short_strike}</span>
            <span style={{ color: C.textDim, fontSize: 11 }}>{trade.spread_type === "bull_call" ? "Call" : "Put"} Spread · Exp {trade.expiration}</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8 }}>
            {[{ l: "Debit", v: `$${trade.net_debit.toFixed(2)}` }, { l: "Max Profit", v: `$${(trade.max_profit * 100).toFixed(0)}` }, { l: "R:R", v: trade.reward_risk_ratio.toFixed(2) }, { l: "Prob", v: `${(trade.prob_of_profit * 100).toFixed(0)}%` }].map(({ l, v }) => (
              <div key={l}><div style={{ fontSize: 9, color: C.textMuted, textTransform: "uppercase" }}>{l}</div><div style={{ fontSize: 13, fontWeight: 600, color: C.text, fontFamily: mono }}>{v}</div></div>
            ))}
          </div>
        </div>

        {/* Market context */}
        <div style={{ padding: 12, borderRadius: 8, border: `1px solid ${C.border}`, backgroundColor: C.card, marginBottom: 12 }}>
          <div style={{ fontSize: 10, color: C.textMuted, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>Market Context</div>
          <div style={{ display: "flex", gap: 16, fontSize: 11 }}>
            <span style={{ color: C.text }}>${lastClose.toFixed(2)}</span>
            <span style={{ color: C.smaCyan }}>SMA{smaPeriods.short} {smaS.toFixed(1)}</span>
            <span style={{ color: C.smaOrange }}>SMA{smaPeriods.mid} {smaM.toFixed(1)}</span>
            <span style={{ color: C.smaRed }}>SMA{smaPeriods.long} {smaL.toFixed(1)}</span>
          </div>
          <div style={{ marginTop: 4, fontSize: 11, color: C.textDim }}>{alignment}</div>
        </div>

        {/* Thesis inputs */}
        {messages.length === 0 && (<div style={{ padding: 12, borderRadius: 8, border: `1px solid ${C.claudeBorder}`, backgroundColor: C.claudeDim, marginBottom: 12 }}>
          <div style={{ fontSize: 10, color: C.claudeAccent, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 10, fontWeight: 600 }}>Your Thesis</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
            <div><label style={{ display: "block", fontSize: 10, color: C.textDim, marginBottom: 3 }}>Direction</label><ThesisBtn items={["Bullish","Bearish","Neutral"]} value={thesis.direction} onChange={d => setThesis({...thesis, direction: d})} colorFn={dirColors} /></div>
            <div><label style={{ display: "block", fontSize: 10, color: C.textDim, marginBottom: 3 }}>Conviction</label><ThesisBtn items={["Low","Medium","High"]} value={thesis.conviction} onChange={c => setThesis({...thesis, conviction: c})} /></div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
            <div><label style={{ display: "block", fontSize: 10, color: C.textDim, marginBottom: 3 }}>Price Target</label><input type="number" value={thesis.target} placeholder={`e.g. ${(lastClose*1.02).toFixed(0)}`} onChange={e => setThesis({...thesis, target: e.target.value})} style={{ width: "100%", padding: "5px 7px", borderRadius: 5, border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text, fontSize: 12, fontFamily: mono, outline: "none" }} /></div>
            <div><label style={{ display: "block", fontSize: 10, color: C.textDim, marginBottom: 3 }}>Timeframe</label><div style={{ display: "flex", alignItems: "center", gap: 4 }}><input type="number" value={thesis.timeframe} min={1} max={365} onChange={e => setThesis({...thesis, timeframe: parseInt(e.target.value)||30})} style={{ width: "100%", padding: "5px 7px", borderRadius: 5, border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text, fontSize: 12, fontFamily: mono, outline: "none" }} /><span style={{ fontSize: 10, color: C.textMuted }}>days</span></div></div>
            <div><label style={{ display: "block", fontSize: 10, color: C.textDim, marginBottom: 3 }}>Risk Budget</label><div style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ fontSize: 11, color: C.textMuted }}>$</span><input type="number" value={thesis.risk_budget} min={50} step={50} onChange={e => setThesis({...thesis, risk_budget: parseInt(e.target.value)||500})} style={{ width: "100%", padding: "5px 7px", borderRadius: 5, border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text, fontSize: 12, fontFamily: mono, outline: "none" }} /></div></div>
          </div>
          {flags.length > 0 && (<div style={{ marginTop: 10, padding: 8, borderRadius: 6, backgroundColor: C.amberBg, border: `1px solid ${C.amber}20` }}><div style={{ fontSize: 10, color: C.amber, fontWeight: 600, marginBottom: 4 }}>PRE-SCREEN FLAGS</div>{flags.map((f, i) => <div key={i} style={{ fontSize: 11, color: f.level === "alert" ? C.red : C.amber, marginBottom: 2 }}>{f.level === "alert" ? "🚨" : "⚠️"} {f.msg}</div>)}</div>)}
          {error && <div style={{ marginTop: 10, padding: 8, borderRadius: 6, backgroundColor: C.redBg, border: `1px solid ${C.red}30` }}><div style={{ fontSize: 11, color: C.red }}>{error}</div></div>}
          <button onClick={handleEvaluate} disabled={loading} style={{ width: "100%", marginTop: 12, padding: "10px 0", borderRadius: 8, border: "none", fontWeight: 700, fontSize: 13, cursor: loading ? "wait" : "pointer", backgroundColor: C.claudeAccent, color: "#000", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
            {loading ? <><span style={{ display: "inline-block", width: 14, height: 14, border: "2px solid #00000040", borderTopColor: "#000", borderRadius: "50%", animation: "spin 0.6s linear infinite" }} />Evaluating...</> : <>✦ Evaluate This Trade</>}
          </button>
        </div>)}

        {/* Responses */}
        {messages.filter(m => m.role === "assistant").map((msg, i) => {
          const vc = msg.verdict ? VC[msg.verdict] : null;
          return (<div key={i} style={{ marginBottom: 12 }}>
            {vc && <div style={{ padding: "10px 14px", borderRadius: 8, border: `1px solid ${vc.border}30`, backgroundColor: vc.bg, marginBottom: 10, display: "flex", alignItems: "center", gap: 10 }}><span style={{ fontSize: 20 }}>{vc.icon}</span><div><div style={{ fontSize: 16, fontWeight: 800, color: vc.text }}>VERDICT: {msg.verdict}</div><div style={{ fontSize: 11, color: C.textDim, marginTop: 2 }}>{msg.verdict === "EXECUTE" ? "Thesis aligns, enter now" : msg.verdict === "WAIT" ? "Setup has merit but timing/strikes off" : "Poor risk/reward or misaligned thesis"}</div></div></div>} 
            <div style={{ padding: 12, borderRadius: 8, border: `1px solid ${C.border}`, backgroundColor: C.card, fontSize: 12, color: C.text, lineHeight: 1.7 }}>
              {msg.content.split("\n").map((line, li) => {
                const trimmed = line.trim();
                if (!trimmed || trimmed === "---" || trimmed === "——") return <div key={li} style={{ height: 4 }} />;
                if (trimmed.match(/^(⚡\s*)?VERDICT\s*:/i)) return null;
                if (trimmed.startsWith("## ")) {
                  const raw = trimmed.replace(/^##\s*/, "").replace(/^\d+[\.\)]\s*/, "").replace(/\*\*/g, "");
                  const emojiMatch = raw.match(/(\p{Emoji_Presentation}|\p{Extended_Pictographic})/u);
                  let icon = "", text = raw;
                  if (emojiMatch) { icon = emojiMatch[1]; text = raw.replace(emojiMatch[1], "").trim(); }
                  return <div key={li}>{li > 0 && <div style={{ borderTop: `1px solid ${C.textMuted}`, margin: "14px 0" }} />}<div style={{ display: "flex", alignItems: "center", gap: 8 }}>{icon && <span style={{ fontSize: 15 }}>{icon}</span>}<span style={{ color: C.accent, fontSize: 14, fontWeight: 700 }}>{text}</span></div></div>;
                }
                if (trimmed.startsWith("### ")) {
                  const raw = trimmed.replace(/^###\s*/, "").replace(/\*\*/g, "");
                  const emojiMatch = raw.match(/(\p{Emoji_Presentation}|\p{Extended_Pictographic})/u);
                  let icon = "", text = raw;
                  if (emojiMatch) { icon = emojiMatch[1]; text = raw.replace(emojiMatch[1], "").trim(); }
                  return <div key={li} style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8, marginBottom: 4 }}>{icon && <span style={{ fontSize: 13 }}>{icon}</span>}<span style={{ color: C.claudeAccent, fontSize: 12, fontWeight: 700 }}>{text}</span></div>;
                }
                if (trimmed.startsWith("- ") || trimmed.match(/^\d+[\.\)]\s/)) {
                  const text = trimmed.replace(/^-\s*/, "").replace(/^\d+[\.\)]\s*/, "");
                  const emojiMatch = text.match(/^(\p{Emoji_Presentation}|\p{Extended_Pictographic})\s*/u);
                  const bullet = emojiMatch ? emojiMatch[1] : "›";
                  const rest = emojiMatch ? text.slice(emojiMatch[0].length) : text;
                  return <div key={li} style={{ display: "flex", gap: 6, marginBottom: 3, paddingLeft: 2 }}><span style={{ flexShrink: 0, width: 16, textAlign: "center", color: emojiMatch ? undefined : C.accent, fontSize: emojiMatch ? 12 : 11 }}>{bullet}</span><span style={{ flex: 1 }}>{rest.split(/\*\*/).map((seg, si) => si % 2 === 1 ? <span key={si} style={{ color: C.claudeAccent, fontWeight: 600 }}>{seg}</span> : seg)}</span></div>;
                }
                const cleaned = trimmed.replace(/^#+\s*/, "");
                return <div key={li} style={{ marginBottom: 2 }}>{cleaned.split(/\*\*/).map((seg, si) => si % 2 === 1 ? <span key={si} style={{ color: C.claudeAccent, fontWeight: 600 }}>{seg}</span> : seg)}</div>;
              })}
            </div>









            {msg.exitLevels && <div style={{ marginTop: 10, padding: 12, borderRadius: 8, border: `1px solid ${C.accent}20`, backgroundColor: C.accentGlow }}>
              <div style={{ fontSize: 10, color: C.accent, fontWeight: 700, textTransform: "uppercase", marginBottom: 8 }}>Exit Plan & Alerts</div>
              <div style={{ fontSize: 10, color: C.textDim, fontWeight: 600, marginBottom: 4, textTransform: "uppercase" }}>Spread Value</div>
              <div style={{ display: "grid", gap: 4, marginBottom: 10 }}>
                <ExitRow icon="🏆" label="Scale out" val={`$${msg.exitLevels.scale_out_target}`} action="Close 50-75%" />
                <ExitRow icon="🏆" label="Full exit" val={`$${msg.exitLevels.full_profit_target}`} action="Close 100%" />
                <ExitRow icon="⚠️" label="Warning" val={`$${msg.exitLevels.warning_level}`} action="Tighten stop" />
                <ExitRow icon="🛑" label="Hard stop" val={`$${msg.exitLevels.stop_loss}`} action="Close position" />
              </div>
              <div style={{ fontSize: 10, color: C.textDim, fontWeight: 600, marginBottom: 4, textTransform: "uppercase" }}>Underlying Price</div>
              <div style={{ display: "grid", gap: 4, marginBottom: 10 }}>
                <ExitRow icon="🎯" label="Target" val={`$${msg.exitLevels.underlying_target}`} action="Take profit" />
                <ExitRow icon="🔴" label="Stop" val={`$${msg.exitLevels.underlying_stop}`} action="Close immediately" />
              </div>
              <div style={{ fontSize: 10, color: C.textDim, fontWeight: 600, marginBottom: 4, textTransform: "uppercase" }}>Time Rules</div>
              <div style={{ fontSize: 11, color: C.textDim, lineHeight: 1.5 }}>• Flat after 10 days → reassess{"\n"}• Never hold final 7 days unless deep ITM{"\n"}• VIX spike 20%+ → evaluate early close</div>
            </div>}
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: C.textMuted, marginTop: 6 }}><span>{msg.model && `${msg.provider} · ${(msg.tokens?.input||0)+(msg.tokens?.output||0)} tokens`}</span><span>{new Date(msg.timestamp).toLocaleString()}</span></div>
          </div>);
        })}
        {messages.filter(m => m.role === "user" && !m.type).map((m, i) => <div key={`fu-${i}`} style={{ marginBottom: 8, padding: 10, borderRadius: 8, backgroundColor: C.accentGlow, border: `1px solid ${C.accent}20`, fontSize: 12, color: C.text, marginLeft: 40 }}>{m.content}</div>)}
        {error && messages.length > 0 && <div style={{ padding: 8, borderRadius: 6, backgroundColor: C.redBg, border: `1px solid ${C.red}30`, marginBottom: 8 }}><div style={{ fontSize: 11, color: C.red }}>{error}</div></div>}
      </div>

      {messages.length > 0 && <div style={{ padding: "10px 18px", borderTop: `1px solid ${C.border}`, flexShrink: 0 }}>
        <div style={{ display: "flex", gap: 6 }}>
          <input type="text" value={followUp} onChange={e => setFollowUp(e.target.value)} placeholder="Ask a follow-up…" onKeyDown={e => e.key === "Enter" && !loading && handleFollowUp()} disabled={loading} style={{ flex: 1, padding: "8px 10px", borderRadius: 6, border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text, fontSize: 12, outline: "none" }} onFocus={e => e.target.style.borderColor = C.claudeAccent} onBlur={e => e.target.style.borderColor = C.border} />
          <button onClick={handleFollowUp} disabled={loading} style={{ padding: "8px 14px", borderRadius: 6, border: "none", backgroundColor: C.claudeAccent, color: "#000", fontSize: 12, fontWeight: 600, cursor: loading ? "wait" : "pointer", opacity: loading ? 0.6 : 1 }}>{loading ? "..." : "Send"}</button>
        </div>
      </div>}
    </div>
  </>);
}
