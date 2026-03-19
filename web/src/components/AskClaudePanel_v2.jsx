import { useState } from "react";
import { ChevronDown, ChevronRight, Plus, Clock, AlertTriangle, TrendingDown, Zap, ArrowRight } from "lucide-react";

const THESIS_INSIGHTS = [
  { group: "Directional Thesis", items: [
    { id: 1, label: "Overall Verdict", status: "WAIT", text: "Setup has merit but timing is premature" },
    { id: 2, label: "SMA Alignment", status: "YELLOW", text: "SMAs compressed in 3.47 range — indecision" },
    { id: 3, label: "Target Feasibility", status: "YELLOW", text: "Requires 1.27% drop; SMA 8 at 604.78 is support" },
    { id: 4, label: "Timing Signal", status: "RED", text: "Consolidation phase — no directional confirmation" },
  ]},
  { group: "Trade Structure", items: [
    { id: 5, label: "R:R Ratio", status: "GREEN", text: "1.94:1 — meets 1.5:1 minimum" },
    { id: 6, label: "Premium / Width", status: "RED", text: "Paying 34% of width (3.41 on 10) — expensive" },
    { id: 7, label: "Budget Use", status: "GREEN", text: "341 of 500 (68%) — appropriate sizing" },
    { id: 8, label: "Breakeven", status: "YELLOW", text: "609.59 breakeven — tight margin (1.90 above price)" },
  ]},
  { group: "Probability & Vol", items: [
    { id: 9, label: "Prob. Assessment", status: "YELLOW", text: "55.5% PoP likely overstated due to theta drag" },
    { id: 10, label: "Volatility Env.", status: "GRAY", text: "No VIX provided — premium value unknown" },
  ]},
  { group: "Risk Flags", items: [
    { id: 11, label: "Top Risk", status: "RED", text: "Theta burning while waiting for confirmation" },
    { id: 12, label: "Time Decay", status: "RED", text: "19 DTE — consider April (49 DTE) for window" },
  ]},
  { group: "Alternatives", items: [
    { id: 13, label: "Alternative", status: "PURPLE", text: "Sell 595/590 put credit spread instead" },
    { id: 14, label: "Re-entry", status: "PURPLE", text: "Re-evaluate if QQQ closes below 604.78 for 2 days" },
  ]},
];

const EXECUTION_WAIT = {
  verdict: "WAIT",
  criteria: [
    { label: "What We're Waiting For", val: "QQQ closes below SMA 8 (604.78) for 2 consecutive days" },
    { label: "Secondary Confirmation", val: "SMA 8 crosses below SMA 21 — momentum shift confirmed" },
  ],
  alerts: [
    { label: "Watch Alert", val: "604.78 — SMA 8 Break", type: "PRICE" },
    { label: "Invalidation", val: "612.00 — Thesis Void", type: "PRICE" },
    { label: "Expiry Deadline", val: "Mar 12 — Roll to April", type: "DATE" },
  ],
  planning: "Current Mar 21 expiry becomes unusable after Mar 12. If setup hasn't triggered by then, switch to April expiration and widen spread to 615/600.",
};

const EXECUTION_GO = {
  verdict: "EXECUTE",
  entry: { price: 3.41, strategy: "Bear Put 610/600", contracts: 1, expiry: "Mar 21" },
  ladder: [
    { type: "Entry", price: 3.41, action: "Enter limit order at debit", color: "#8A70FF", icon: "→" },
    { type: "Target 1", price: 5.00, action: "Close 1st contract — 50% profit locked", color: "#20C997", icon: "↑" },
    { type: "Target 2", price: 6.59, action: "Close remainder — 75% of max profit", color: "#20C997", icon: "↑" },
    { type: "Hard Stop", price: 1.71, action: "Close all — 50% loss limit reached", color: "#FF5A5A", icon: "↓" },
  ],
};

const statusConfig = {
  GREEN:  { bg: "#20C99720", border: "#20C997", dot: "#20C997", label: "✓" },
  YELLOW: { bg: "#FF9E4320", border: "#FF9E43", dot: "#FF9E43", label: "⚠" },
  RED:    { bg: "#FF5A5A20", border: "#FF5A5A", dot: "#FF5A5A", label: "✕" },
  GRAY:   { bg: "#55606D20", border: "#55606D", dot: "#55606D", label: "?" },
  PURPLE: { bg: "#8A70FF20", border: "#8A70FF", dot: "#8A70FF", label: "◆" },
  WAIT:   { bg: "#FF9E4330", border: "#FF9E43", dot: "#FF9E43", label: "⏸" },
  EXECUTE:{ bg: "#20C99730", border: "#20C997", dot: "#20C997", label: "⚡" },
};

function StatusPip({ status }) {
  const cfg = statusConfig[status] || statusConfig.GRAY;
  return (
    <div style={{
      width: 22, height: 22, borderRadius: 4,
      background: cfg.bg, border: `1px solid ${cfg.border}`,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 10, color: cfg.dot, fontWeight: 700, flexShrink: 0,
    }}>
      {cfg.label}
    </div>
  );
}

function CollapsibleGroup({ group, items, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  const redCount = items.filter(i => i.status === "RED").length;

  return (
    <div style={{ marginBottom: 2 }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          width: "100%", display: "flex", alignItems: "center", gap: 8,
          padding: "7px 12px", background: "#1C2028",
          border: "none", borderBottom: "1px solid #2C313B",
          cursor: "pointer", color: "#A0A8B4", fontSize: 10,
          fontFamily: "monospace", fontWeight: 700, letterSpacing: "0.08em",
          textTransform: "uppercase", textAlign: "left",
        }}
      >
        {open
          ? <ChevronDown size={12} color="#55606D" />
          : <ChevronRight size={12} color="#55606D" />}
        <span style={{ flex: 1 }}>{group}</span>
        {redCount > 0 && (
          <span style={{
            background: "#FF5A5A20", border: "1px solid #FF5A5A",
            color: "#FF5A5A", borderRadius: 3, padding: "1px 6px",
            fontSize: 9, fontWeight: 700,
          }}>
            {redCount} FLAG{redCount > 1 ? "S" : ""}
          </span>
        )}
        <span style={{ color: "#55606D", fontSize: 9 }}>{items.length} metrics</span>
      </button>

      {open && (
        <div>
          {items.map((item, i) => {
            const cfg = statusConfig[item.status] || statusConfig.GRAY;
            return (
              <div key={item.id} style={{
                display: "grid", gridTemplateColumns: "140px 28px 1fr",
                alignItems: "start", gap: 10,
                padding: "8px 12px",
                background: i % 2 === 0 ? "#13161A" : "#161A20",
                borderBottom: "1px solid #1E2330",
                transition: "background 0.15s",
              }}>
                <span style={{ fontSize: 11, color: "#8A919E", fontFamily: "monospace", paddingTop: 2 }}>
                  {item.label}
                </span>
                <div style={{ paddingTop: 1 }}>
                  <StatusPip status={item.status} />
                </div>
                <span style={{ fontSize: 11.5, color: "#D0D6E0", lineHeight: 1.5 }}>
                  {item.text}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function WaitView() {
  return (
    <div style={{ padding: "16px 14px" }}>
      {/* Criteria Cards */}
      <div style={{ marginBottom: 16 }}>
        <div style={{
          fontSize: 9, color: "#55606D", fontFamily: "monospace",
          letterSpacing: "0.1em", textTransform: "uppercase",
          marginBottom: 8, paddingLeft: 2,
        }}>
          Wait Criteria
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {EXECUTION_WAIT.criteria.map((c, i) => (
            <div key={i} style={{
              background: "#FF9E430D",
              border: "1px solid #FF9E4340",
              borderLeft: "3px solid #FF9E43",
              borderRadius: 6, padding: "10px 14px",
            }}>
              <div style={{ fontSize: 9, color: "#FF9E43", fontFamily: "monospace", fontWeight: 700, marginBottom: 4, letterSpacing: "0.06em" }}>
                {c.label.toUpperCase()}
              </div>
              <div style={{ fontSize: 12, color: "#E8EDF3", lineHeight: 1.5 }}>{c.val}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Monitoring Alerts */}
      <div style={{ marginBottom: 16 }}>
        <div style={{
          fontSize: 9, color: "#55606D", fontFamily: "monospace",
          letterSpacing: "0.1em", textTransform: "uppercase",
          marginBottom: 8, paddingLeft: 2,
        }}>
          Monitoring Alerts
        </div>
        <div style={{
          background: "#8A70FF0D", border: "1px solid #8A70FF30",
          borderRadius: 6, overflow: "hidden",
        }}>
          {EXECUTION_WAIT.alerts.map((a, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "9px 12px",
              borderBottom: i < EXECUTION_WAIT.alerts.length - 1 ? "1px solid #8A70FF20" : "none",
            }}>
              <div style={{
                background: "#8A70FF20", border: "1px solid #8A70FF50",
                borderRadius: 3, padding: "2px 6px",
                fontSize: 8, color: "#8A70FF", fontFamily: "monospace", fontWeight: 700,
              }}>
                {a.type}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 9, color: "#8A919E", marginBottom: 1 }}>{a.label}</div>
                <div style={{ fontSize: 11.5, color: "#D0D6E0", fontFamily: "monospace" }}>{a.val}</div>
              </div>
              <button style={{
                width: 24, height: 24, borderRadius: 4,
                background: "#8A70FF20", border: "1px solid #8A70FF50",
                color: "#8A70FF", cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 16, fontWeight: 300, lineHeight: 1,
              }}>+</button>
            </div>
          ))}
        </div>
      </div>

      {/* Planning Note */}
      <div style={{
        background: "#1C2028", border: "1px solid #2C313B",
        borderRadius: 6, padding: "10px 14px",
        display: "flex", gap: 10, alignItems: "flex-start",
      }}>
        <Clock size={13} color="#55606D" style={{ marginTop: 1, flexShrink: 0 }} />
        <div style={{ fontSize: 11, color: "#8A919E", lineHeight: 1.6 }}>
          {EXECUTION_WAIT.planning}
        </div>
      </div>
    </div>
  );
}

function ExecuteView() {
  return (
    <div style={{ padding: "16px 14px" }}>
      {/* Entry Summary */}
      <div style={{
        background: "#20C9970D", border: "1px solid #20C99730",
        borderRadius: 6, padding: "10px 14px", marginBottom: 14,
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div>
          <div style={{ fontSize: 9, color: "#20C997", fontFamily: "monospace", fontWeight: 700, letterSpacing: "0.06em", marginBottom: 3 }}>ENTRY — {EXECUTION_GO.entry.strategy}</div>
          <div style={{ fontSize: 10, color: "#8A919E" }}>
            {EXECUTION_GO.entry.contracts} contract · Exp {EXECUTION_GO.entry.expiry}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 20, fontFamily: "monospace", color: "#20C997", fontWeight: 700 }}>
            {EXECUTION_GO.entry.price.toFixed(2)}
          </div>
          <div style={{ fontSize: 9, color: "#55606D" }}>LIMIT DEBIT</div>
        </div>
      </div>

      {/* Trade Ladder */}
      <div style={{ marginBottom: 16 }}>
        <div style={{
          fontSize: 9, color: "#55606D", fontFamily: "monospace",
          letterSpacing: "0.1em", textTransform: "uppercase",
          marginBottom: 8, paddingLeft: 2,
        }}>
          Trade Ladder
        </div>
        <div style={{
          background: "#1C2028", border: "1px solid #2C313B",
          borderRadius: 6, overflow: "hidden", position: "relative",
        }}>
          {/* Vertical connector line */}
          <div style={{
            position: "absolute", left: 38, top: 0, bottom: 0, width: 1,
            background: "linear-gradient(to bottom, #8A70FF50, #20C99750, #20C99750, #FF5A5A50)",
          }} />

          {EXECUTION_GO.ladder.map((rung, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 12,
              padding: "10px 14px",
              borderBottom: i < EXECUTION_GO.ladder.length - 1 ? "1px solid #2C313B" : "none",
              background: i % 2 === 0 ? "#1C2028" : "#161A20",
            }}>
              {/* Dot on the line */}
              <div style={{
                width: 8, height: 8, borderRadius: "50%",
                background: rung.color, border: `2px solid ${rung.color}40`,
                flexShrink: 0, marginLeft: 2, position: "relative", zIndex: 1,
                boxShadow: `0 0 6px ${rung.color}60`,
              }} />

              {/* Type tag */}
              <div style={{
                background: rung.color + "20", border: `1px solid ${rung.color}50`,
                borderRadius: 3, padding: "2px 7px",
                fontSize: 8, color: rung.color, fontFamily: "monospace", fontWeight: 700,
                minWidth: 60, textAlign: "center",
              }}>
                {rung.type.toUpperCase()}
              </div>

              {/* Price */}
              <div style={{
                fontSize: 14, fontFamily: "monospace", color: rung.color,
                fontWeight: 700, minWidth: 36,
              }}>
                {rung.price.toFixed(2)}
              </div>

              {/* Action */}
              <div style={{ fontSize: 11, color: "#8A919E", flex: 1 }}>{rung.action}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Draft Order Button */}
      <button style={{
        width: "100%", padding: "11px 0",
        background: "linear-gradient(135deg, #20C997, #1AAF84)",
        border: "none", borderRadius: 6,
        color: "#0A1A14", fontSize: 12, fontWeight: 800,
        fontFamily: "monospace", letterSpacing: "0.08em",
        cursor: "pointer", display: "flex", alignItems: "center",
        justifyContent: "center", gap: 8,
        boxShadow: "0 4px 16px #20C99740",
      }}>
        <Zap size={14} />
        DRAFT ORDER
        <ArrowRight size={14} />
      </button>
    </div>
  );
}

export default function AskClaudePanel() {
  const [verdict, setVerdict] = useState("WAIT");
  const [openGroups, setOpenGroups] = useState({});

  const isWait = verdict === "WAIT";

  return (
    <div style={{
      width: 520, minHeight: "100vh",
      background: "#13161A",
      fontFamily: "'IBM Plex Mono', 'Fira Code', monospace",
      display: "flex", flexDirection: "column",
      borderLeft: "1px solid #2C313B",
    }}>
      {/* ── Verdict Banner ── */}
      <div style={{
        background: isWait
          ? "linear-gradient(135deg, #FF9E43, #E8892A)"
          : "linear-gradient(135deg, #20C997, #17A882)",
        padding: "14px 18px",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        position: "sticky", top: 0, zIndex: 10,
        boxShadow: isWait ? "0 4px 20px #FF9E4350" : "0 4px 20px #20C99750",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {isWait ? <Clock size={18} color="#1A0F00" /> : <Zap size={18} color="#001A12" />}
          <div>
            <div style={{ fontSize: 18, fontWeight: 900, color: "#0D0800", letterSpacing: "0.04em" }}>
              {isWait ? "⏸  WAIT" : "⚡  EXECUTE"}
            </div>
            <div style={{ fontSize: 10, color: "#1A0F0099", marginTop: 1 }}>
              {isWait
                ? "Setup has merit — timing is premature"
                : "Conditions met — enter with discipline"}
            </div>
          </div>
        </div>

        {/* Trade context */}
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#0D0800" }}>QQQ · Bear Put</div>
          <div style={{ fontSize: 10, color: "#1A0F0099" }}>610/600 · Mar 21</div>
        </div>
      </div>

      {/* ── Toggle ── */}
      <div style={{
        display: "flex", background: "#1C2028",
        borderBottom: "1px solid #2C313B", padding: "8px 14px", gap: 8,
      }}>
        <div style={{ fontSize: 9, color: "#55606D", alignSelf: "center", marginRight: 4, fontFamily: "monospace" }}>
          PREVIEW:
        </div>
        {["WAIT", "EXECUTE"].map(v => (
          <button
            key={v}
            onClick={() => setVerdict(v)}
            style={{
              padding: "5px 14px", borderRadius: 4, fontSize: 10, fontWeight: 700,
              fontFamily: "monospace", cursor: "pointer", letterSpacing: "0.06em",
              border: verdict === v
                ? `1px solid ${v === "WAIT" ? "#FF9E43" : "#20C997"}`
                : "1px solid #2C313B",
              background: verdict === v
                ? (v === "WAIT" ? "#FF9E4320" : "#20C99720")
                : "#13161A",
              color: verdict === v
                ? (v === "WAIT" ? "#FF9E43" : "#20C997")
                : "#55606D",
            }}
          >
            {v === "WAIT" ? "⏸ WAIT" : "⚡ EXECUTE"}
          </button>
        ))}
      </div>

      {/* ── Table 1: Thesis Matrix ── */}
      <div style={{ borderBottom: "2px solid #2C313B" }}>
        <div style={{
          padding: "8px 12px 6px",
          fontSize: 9, color: "#55606D", fontFamily: "monospace",
          letterSpacing: "0.12em", textTransform: "uppercase",
          background: "#13161A", borderBottom: "1px solid #2C313B",
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <span>Thesis Matrix</span>
          <div style={{ display: "flex", gap: 10 }}>
            {[["GREEN","✓"],["YELLOW","⚠"],["RED","✕"],["PURPLE","◆"]].map(([s,l]) => (
              <span key={s} style={{ color: statusConfig[s].dot, fontSize: 9 }}>{l} {s.charAt(0)+s.slice(1).toLowerCase()}</span>
            ))}
          </div>
        </div>

        {/* Column headers */}
        <div style={{
          display: "grid", gridTemplateColumns: "140px 28px 1fr",
          gap: 10, padding: "5px 12px",
          background: "#161A20", borderBottom: "1px solid #1E2330",
        }}>
          {["Metric", "Sig", "Insight"].map(h => (
            <div key={h} style={{ fontSize: 8, color: "#3D4452", fontFamily: "monospace", letterSpacing: "0.1em", textTransform: "uppercase" }}>{h}</div>
          ))}
        </div>

        {THESIS_INSIGHTS.map((section, i) => (
          <CollapsibleGroup
            key={section.group}
            group={section.group}
            items={section.items}
            defaultOpen={i < 2}
          />
        ))}
      </div>

      {/* ── Table 2: Action Command Center ── */}
      <div style={{ flex: 1 }}>
        <div style={{
          padding: "8px 12px 6px",
          fontSize: 9, color: "#55606D", fontFamily: "monospace",
          letterSpacing: "0.12em", textTransform: "uppercase",
          background: "#13161A", borderBottom: "1px solid #2C313B",
          display: "flex", justifyContent: "space-between",
        }}>
          <span>Action Command Center</span>
          <span style={{
            color: isWait ? "#FF9E43" : "#20C997",
            border: `1px solid ${isWait ? "#FF9E4340" : "#20C99740"}`,
            padding: "1px 6px", borderRadius: 3, fontSize: 8,
          }}>
            {isWait ? "WAIT MODE" : "EXECUTE MODE"}
          </span>
        </div>

        {isWait ? <WaitView /> : <ExecuteView />}
      </div>
    </div>
  );
}