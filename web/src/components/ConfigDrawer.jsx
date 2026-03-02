/**
 * ConfigDrawer — Slide-out configuration panel with presets, auto-balancing
 * weight sliders, and filter controls.
 *
 * Props:
 *   open/onClose      — drawer visibility
 *   config            — { weights, dte, strikes, spreads, risk }
 *   onConfigChange    — callback with updated config
 *   presets           — array of preset objects
 *   activePresetId    — currently selected preset id
 *   onPresetSelect    — callback(id)
 *   onSavePreset      — callback(name) to save current config as new preset
 *   onOverwrite       — callback(id) to overwrite existing preset
 *   onDelete          — callback(id) to delete a preset
 *   onRename          — callback(id, newName) to rename
 */
import { useState, useCallback } from "react";
import { C, mono, WEIGHT_COLORS, WEIGHT_LABELS } from "../styles/tokens";

// ─── Small reusable form components ───────────────────────────────

function WeightSlider({ label, value, color, onChange }) {
  const pct = Math.round(value * 100);
  return (<div style={{ marginBottom: 14 }}>
    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
      <span style={{ color: C.text, fontSize: 12.5, fontWeight: 500 }}><span style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", backgroundColor: color, marginRight: 7, verticalAlign: "middle" }} />{label}</span>
      <span style={{ color, fontWeight: 600, fontSize: 13, fontFamily: mono, minWidth: 38, textAlign: "right" }}>{pct}%</span>
    </div>
    <div style={{ position: "relative", height: 24, display: "flex", alignItems: "center" }}>
      <div style={{ position: "absolute", left: 0, right: 0, height: 5, borderRadius: 3, backgroundColor: C.border }} />
      <div style={{ position: "absolute", left: 0, height: 5, borderRadius: 3, width: `${pct}%`, backgroundColor: color, opacity: 0.6, transition: "width 0.15s" }} />
      <input type="range" min={0} max={60} step={1} value={pct} onChange={(e) => onChange(parseInt(e.target.value) / 100)}
        style={{ position: "absolute", left: 0, right: 0, width: "100%", height: 24, appearance: "none", WebkitAppearance: "none", background: "transparent", cursor: "pointer", margin: 0, zIndex: 2 }} />
    </div>
  </div>);
}

function WeightBar({ weights }) {
  const keys = Object.keys(weights);
  const total = keys.reduce((s, k) => s + weights[k], 0);
  return (<div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", marginBottom: 16, border: `1px solid ${C.border}` }}>
    {keys.map((k) => (<div key={k} style={{ width: `${(weights[k] / total) * 100}%`, backgroundColor: WEIGHT_COLORS[k], transition: "width 0.2s", minWidth: weights[k] > 0 ? 2 : 0 }} />))}
  </div>);
}

function NumInput({ label, value, onChange, min, max, step = 1, unit = "", w = 80 }) {
  return (<div style={{ marginBottom: 12 }}>
    <label style={{ display: "block", color: C.textDim, fontSize: 10.5, fontWeight: 600, marginBottom: 3, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</label>
    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
      <input type="number" value={value} min={min} max={max} step={step}
        onChange={(e) => { let v = parseFloat(e.target.value); if (!isNaN(v)) { if (min !== undefined) v = Math.max(min, v); if (max !== undefined) v = Math.min(max, v); onChange(v); } }}
        style={{ width: w, padding: "5px 7px", borderRadius: 5, border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text, fontSize: 13, fontFamily: mono, outline: "none", textAlign: "right" }}
        onFocus={(e) => e.target.style.borderColor = C.borderFocus} onBlur={(e) => e.target.style.borderColor = C.border} />
      {unit && <span style={{ color: C.textMuted, fontSize: 11 }}>{unit}</span>}
    </div>
  </div>);
}

function RangePair({ label, minVal, maxVal, onMinChange, onMaxChange, minLimit, maxLimit, step = 1, unit = "" }) {
  return (<div style={{ marginBottom: 12 }}>
    <label style={{ display: "block", color: C.textDim, fontSize: 10.5, fontWeight: 600, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</label>
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <input type="number" value={minVal} min={minLimit} max={maxVal - step} step={step} onChange={(e) => { const v = parseFloat(e.target.value); if (!isNaN(v) && v < maxVal) onMinChange(v); }}
        style={{ width: 64, padding: "5px 7px", borderRadius: 5, border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text, fontSize: 13, fontFamily: mono, outline: "none", textAlign: "right" }}
        onFocus={(e) => e.target.style.borderColor = C.borderFocus} onBlur={(e) => e.target.style.borderColor = C.border} />
      <span style={{ color: C.textMuted, fontSize: 11 }}>to</span>
      <input type="number" value={maxVal} min={minVal + step} max={maxLimit} step={step} onChange={(e) => { const v = parseFloat(e.target.value); if (!isNaN(v) && v > minVal) onMaxChange(v); }}
        style={{ width: 64, padding: "5px 7px", borderRadius: 5, border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text, fontSize: 13, fontFamily: mono, outline: "none", textAlign: "right" }}
        onFocus={(e) => e.target.style.borderColor = C.borderFocus} onBlur={(e) => e.target.style.borderColor = C.border} />
      {unit && <span style={{ color: C.textMuted, fontSize: 11 }}>{unit}</span>}
    </div>
  </div>);
}

function Sect({ title, icon, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (<div style={{ marginBottom: 10, borderRadius: 8, border: `1px solid ${C.border}`, backgroundColor: C.card }}>
    <button onClick={() => setOpen(!open)} style={{ width: "100%", padding: "10px 14px", display: "flex", alignItems: "center", justifyContent: "space-between", background: "none", border: "none", cursor: "pointer" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}><span style={{ fontSize: 14 }}>{icon}</span><span style={{ color: C.text, fontSize: 13, fontWeight: 600 }}>{title}</span></div>
      <span style={{ color: C.textMuted, fontSize: 16, transition: "transform 0.2s", transform: open ? "rotate(180deg)" : "rotate(0)", display: "inline-block" }}>▾</span>
    </button>
    {open && <div style={{ padding: "2px 14px 14px", borderTop: `1px solid ${C.border}` }}>{children}</div>}
  </div>);
}

// ─── Preset Selector ──────────────────────────────────────────────

function PresetSelector({ presets, activePresetId, onSelect, onSaveNew, onOverwrite, onDelete, onRename }) {
  const [showSaveNew, setShowSaveNew] = useState(false);
  const [newName, setNewName] = useState("");
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState("");
  const [deleteConfirmId, setDeleteConfirmId] = useState(null);

  const handleSave = () => { if (newName.trim()) { onSaveNew(newName.trim()); setNewName(""); setShowSaveNew(false); } };
  const handleRename = (id) => { if (renameValue.trim()) { onRename(id, renameValue.trim()); setRenamingId(null); } };

  return (<div style={{ marginBottom: 18 }}>
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
      <label style={{ color: C.textDim, fontSize: 10.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>Config Presets</label>
      <button onClick={() => setShowSaveNew(true)} style={{ padding: "4px 10px", borderRadius: 5, border: `1px solid ${C.accent}40`, backgroundColor: C.accentGlow, color: C.accent, fontSize: 11, fontWeight: 600, cursor: "pointer" }}>+ Save Current</button>
    </div>

    {showSaveNew && (<div style={{ marginBottom: 10, padding: 10, borderRadius: 8, border: `1px solid ${C.accent}40`, backgroundColor: C.surfaceAlt }}>
      <p style={{ fontSize: 11, color: C.textDim, margin: "0 0 8px" }}>Saves current settings as a new preset.</p>
      <div style={{ display: "flex", gap: 6 }}>
        <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Name your preset…" autoFocus onKeyDown={(e) => e.key === "Enter" && handleSave()}
          style={{ flex: 1, padding: "6px 8px", borderRadius: 5, border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text, fontSize: 13, outline: "none" }} />
        <button onClick={handleSave} disabled={!newName.trim()} style={{ padding: "6px 14px", borderRadius: 5, border: "none", backgroundColor: newName.trim() ? C.accent : C.border, color: newName.trim() ? "#fff" : C.textMuted, fontSize: 12, fontWeight: 600, cursor: newName.trim() ? "pointer" : "default" }}>Save</button>
        <button onClick={() => { setShowSaveNew(false); setNewName(""); }} style={{ padding: "6px 10px", borderRadius: 5, border: `1px solid ${C.border}`, backgroundColor: "transparent", color: C.textDim, fontSize: 12, cursor: "pointer" }}>Cancel</button>
      </div>
    </div>)}

    {deleteConfirmId && (<div style={{ marginBottom: 10, padding: 10, borderRadius: 8, border: `1px solid ${C.red}40`, backgroundColor: C.redDim }}>
      <p style={{ fontSize: 12, color: C.text, margin: "0 0 8px", fontWeight: 500 }}>Delete "{presets.find(p => p.id === deleteConfirmId)?.name}"?</p>
      <div style={{ display: "flex", gap: 6 }}>
        <button onClick={() => { onDelete(deleteConfirmId); setDeleteConfirmId(null); }} style={{ padding: "6px 14px", borderRadius: 5, border: "none", backgroundColor: C.red, color: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>Yes, Delete</button>
        <button onClick={() => setDeleteConfirmId(null)} style={{ padding: "6px 14px", borderRadius: 5, border: `1px solid ${C.border}`, backgroundColor: "transparent", color: C.textDim, fontSize: 12, cursor: "pointer" }}>Cancel</button>
      </div>
    </div>)}

    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {presets.map((p) => { const isA = p.id === activePresetId; return (
        <div key={p.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 7, border: `1.5px solid ${isA ? C.accent : C.border}`, backgroundColor: isA ? C.accentGlow : C.card, cursor: "pointer" }}
          onClick={() => { if (renamingId !== p.id) onSelect(p.id); }}>
          <span style={{ fontSize: 15, flexShrink: 0 }}>{p.icon}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            {renamingId === p.id ? (
              <div style={{ display: "flex", gap: 4 }} onClick={(e) => e.stopPropagation()}>
                <input type="text" value={renameValue} onChange={(e) => setRenameValue(e.target.value)} autoFocus
                  onKeyDown={(e) => { if (e.key === "Enter") handleRename(p.id); if (e.key === "Escape") setRenamingId(null); }}
                  style={{ flex: 1, padding: "3px 6px", borderRadius: 4, border: `1px solid ${C.borderFocus}`, backgroundColor: C.bg, color: C.text, fontSize: 12, outline: "none" }} />
                <button onClick={() => handleRename(p.id)} style={{ padding: "2px 8px", borderRadius: 4, border: "none", backgroundColor: C.accent, color: "#fff", fontSize: 10, cursor: "pointer" }}>✓</button>
              </div>
            ) : (<><div style={{ color: isA ? C.accent : C.text, fontSize: 12, fontWeight: 600 }}>{p.name}</div><div style={{ color: C.textMuted, fontSize: 10 }}>{p.desc}</div></>)}
          </div>
          {renamingId !== p.id && (<div style={{ display: "flex", gap: 2, flexShrink: 0 }} onClick={(e) => e.stopPropagation()}>
            <button onClick={() => { setRenamingId(p.id); setRenameValue(p.name); }} title="Rename" style={{ width: 26, height: 26, borderRadius: 5, border: "none", backgroundColor: "transparent", color: C.textMuted, fontSize: 12, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>✎</button>
            {isA && <button onClick={() => onOverwrite(p.id)} title="Update" style={{ width: 26, height: 26, borderRadius: 5, border: "none", backgroundColor: "transparent", color: C.textMuted, fontSize: 12, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>💾</button>}
            {!p.builtIn && <button onClick={() => setDeleteConfirmId(p.id)} title="Delete" style={{ width: 26, height: 26, borderRadius: 5, border: "none", backgroundColor: "transparent", color: C.textMuted, fontSize: 13, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>×</button>}
          </div>)}
        </div>); })}
    </div>
  </div>);
}

// ─── Main ConfigDrawer ────────────────────────────────────────────

export default function ConfigDrawer({ open, onClose, config, onConfigChange, presets, activePresetId, onPresetSelect, onSavePreset, onOverwrite, onDelete, onRename }) {
  const { weights, dte, strikes, spreads, risk } = config;
  const ws = Object.values(weights).reduce((s, v) => s + v, 0);
  const wv = Math.abs(ws - 1.0) < 0.02;

  // Auto-balance: when one weight changes, redistribute the remainder proportionally
  const hwc = useCallback((key, nv) => {
    const prev = { ...weights };
    const ok = Object.keys(prev).filter(k => k !== key);
    const os = ok.reduce((s, k) => s + prev[k], 0);
    const rem = 1.0 - nv;
    if (rem < 0) return;
    if (os === 0) { const e = rem / ok.length; const n = { ...prev, [key]: nv }; ok.forEach(k => n[k] = Math.round(e * 100) / 100); onConfigChange({ ...config, weights: n }); return; }
    const sc = rem / os;
    const n = { [key]: nv };
    ok.forEach(k => n[k] = Math.round(prev[k] * sc * 100) / 100);
    const t = Object.values(n).reduce((s, v) => s + v, 0);
    const d = 1.0 - t;
    if (Math.abs(d) > 0.001) { const l = ok.reduce((a, b) => n[a] >= n[b] ? a : b); n[l] = Math.round((n[l] + d) * 100) / 100; }
    onConfigChange({ ...config, weights: n });
  }, [weights, config, onConfigChange]);

  const sw = (u) => onConfigChange({ ...config, ...u });

  return (<>
    {open && <div onClick={onClose} style={{ position: "fixed", inset: 0, backgroundColor: C.overlay, zIndex: 90 }} />}
    <div style={{ position: "fixed", top: 0, right: 0, bottom: 0, width: 400, backgroundColor: C.surface, borderLeft: `1px solid ${C.border}`, zIndex: 100, transform: open ? "translateX(0)" : "translateX(100%)", transition: "transform 0.25s cubic-bezier(0.4,0,0.2,1)", display: "flex", flexDirection: "column", boxShadow: open ? "-8px 0 30px rgba(0,0,0,0.4)" : "none" }}>
      {/* Header */}
      <div style={{ padding: "14px 18px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center", flexShrink: 0 }}>
        <div><h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: C.text }}>Configuration</h2><p style={{ margin: "2px 0 0", fontSize: 11, color: C.textDim }}>Vertical Spread Settings</p></div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 10.5, padding: "2px 8px", borderRadius: 12, backgroundColor: wv ? C.greenDim : C.redDim, color: wv ? C.green : C.red, fontWeight: 600 }}>Σ {Math.round(ws * 100)}%</span>
          <button onClick={onClose} style={{ background: "none", border: "none", color: C.textMuted, fontSize: 20, cursor: "pointer", padding: 4 }}>✕</button>
        </div>
      </div>

      {/* Scrollable body */}
      <div style={{ flex: 1, overflowY: "auto", padding: "14px 18px" }}>
        <PresetSelector presets={presets} activePresetId={activePresetId} onSelect={onPresetSelect} onSaveNew={onSavePreset} onOverwrite={onOverwrite} onDelete={onDelete} onRename={onRename} />
        <Sect title="Scoring Weights" icon="⚖️" defaultOpen={true}>
          <p style={{ fontSize: 11, color: C.textDim, margin: "6px 0 12px", lineHeight: 1.4 }}>Drag a slider — others auto-adjust to keep total at 100%.</p>
          <WeightBar weights={weights} />
          {Object.keys(weights).map(k => <WeightSlider key={k} label={WEIGHT_LABELS[k]} value={weights[k]} color={WEIGHT_COLORS[k]} onChange={v => hwc(k, v)} />)}
        </Sect>
        <Sect title="Days to Expiration" icon="📅">
          <RangePair label="DTE Range" minVal={dte.min} maxVal={dte.max} onMinChange={v => sw({ dte: { ...dte, min: v } })} onMaxChange={v => sw({ dte: { ...dte, max: v } })} minLimit={1} maxLimit={365} unit="days" />
        </Sect>
        <Sect title="Strike & Spread Filters" icon="🎯">
          <NumInput label="Strike Range" value={strikes.range_pct} onChange={v => sw({ strikes: { ...strikes, range_pct: v } })} min={1} max={50} step={0.5} unit="%" />
          <div style={{ display: "flex", gap: 12 }}>
            <NumInput label="Min OI" value={strikes.min_open_interest} onChange={v => sw({ strikes: { ...strikes, min_open_interest: v } })} min={0} max={10000} step={5} />
            <NumInput label="Min Vol" value={strikes.min_volume} onChange={v => sw({ strikes: { ...strikes, min_volume: v } })} min={0} max={10000} />
          </div>
          <RangePair label="Spread Width" minVal={spreads.min_width} maxVal={spreads.max_width} onMinChange={v => sw({ spreads: { ...spreads, min_width: v } })} onMaxChange={v => sw({ spreads: { ...spreads, max_width: v } })} minLimit={0.5} maxLimit={50} step={0.5} unit="$" />
        </Sect>
        <Sect title="Risk Management" icon="🛡️">
          <NumInput label="Max Risk" value={risk.max_risk_per_trade} onChange={v => sw({ risk: { ...risk, max_risk_per_trade: v } })} min={50} max={50000} step={50} unit="$" w={90} />
          <div style={{ display: "flex", gap: 12 }}>
            <NumInput label="Profit Target" value={risk.profit_target_pct} onChange={v => sw({ risk: { ...risk, profit_target_pct: v } })} min={10} max={100} step={5} unit="%" />
            <NumInput label="Stop Loss" value={risk.stop_loss_pct} onChange={v => sw({ risk: { ...risk, stop_loss_pct: v } })} min={25} max={200} step={5} unit="%" />
          </div>
        </Sect>
      </div>

      {/* Footer */}
      <div style={{ padding: "12px 18px", borderTop: `1px solid ${C.border}`, flexShrink: 0, display: "flex", gap: 8 }}>
        <button onClick={onClose} disabled={!wv} style={{ flex: 1, padding: "10px 0", borderRadius: 8, border: "none", fontWeight: 600, fontSize: 13, cursor: wv ? "pointer" : "not-allowed", backgroundColor: wv ? C.accent : C.border, color: wv ? "#fff" : C.textMuted }}>Apply & Re-analyze</button>
        <button onClick={onClose} style={{ padding: "10px 16px", borderRadius: 8, border: `1px solid ${C.border}`, backgroundColor: "transparent", color: C.textDim, fontSize: 13, cursor: "pointer" }}>Cancel</button>
      </div>
    </div>
  </>);
}
