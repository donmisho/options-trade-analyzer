/**
 * ConfigDrawer — Shared slide-out configuration panel used by both the
 * Vertical Spreads and Naked Puts/Calls pages.
 *
 * ROUND 4 CHANGES (additive to Round 3):
 * 1. MODE PROP: "verticals" shows Spread Types + Spread Width sections.
 *    "naked" hides them since naked options don't have spreads.
 * 2. SMA PERIODS: New section with three number inputs so you can change
 *    the moving average windows (e.g., 8/21/50 → 20/50/200).
 * 3. All Round 3 features preserved: draft/commit, DTE number inputs,
 *    spread type toggles, Greek filters.
 */
import { useState, useCallback, useEffect } from "react";
import { C, mono, WEIGHT_COLORS, WEIGHT_LABELS } from "../styles/tokens";

// --- Reusable form components (unchanged from Round 3) -------------

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
      <input type="range" min={0} max={100} step={5} value={pct} onChange={(e) => onChange(parseInt(e.target.value) / 100)}
        style={{ position: "absolute", left: 0, right: 0, width: "100%", height: 24, appearance: "none", WebkitAppearance: "none", background: "transparent", cursor: "pointer", margin: 0, zIndex: 2 }} />
    </div>
  </div>);
}

function WeightBar({ weights }) {
  const keys = Object.keys(weights); const total = keys.reduce((s, k) => s + weights[k], 0); const denom = total > 0 ? total : 1;
  return (<div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", marginBottom: 4, border: `1px solid ${C.border}` }}>
    {keys.map((k) => (<div key={k} style={{ width: `${(weights[k] / denom) * 100}%`, backgroundColor: WEIGHT_COLORS[k], transition: "width 0.2s", minWidth: weights[k] > 0 ? 2 : 0 }} />))}
  </div>);
}

function SingleSlider({ label, value, min, max, step = 1, unit = "", color = C.accent, onChange }) {
  const pct = ((value - min) / (max - min)) * 100;
  return (<div style={{ marginBottom: 14 }}>
    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
      <span style={{ color: C.textDim, fontSize: 10.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</span>
      <span style={{ color: C.text, fontWeight: 600, fontSize: 13, fontFamily: mono }}>{value}{unit}</span>
    </div>
    <div style={{ position: "relative", height: 24, display: "flex", alignItems: "center" }}>
      <div style={{ position: "absolute", left: 0, right: 0, height: 5, borderRadius: 3, backgroundColor: C.border }} />
      <div style={{ position: "absolute", left: 0, height: 5, borderRadius: 3, width: `${pct}%`, backgroundColor: color, opacity: 0.6, transition: "width 0.15s" }} />
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(parseFloat(e.target.value))}
        style={{ position: "absolute", left: 0, right: 0, width: "100%", height: 24, appearance: "none", WebkitAppearance: "none", background: "transparent", cursor: "pointer", margin: 0, zIndex: 2 }} />
    </div>
    <div style={{ display: "flex", justifyContent: "space-between", marginTop: 1 }}>
      <span style={{ color: C.textMuted, fontSize: 9.5 }}>{min}{unit}</span><span style={{ color: C.textMuted, fontSize: 9.5 }}>{max}{unit}</span>
    </div>
  </div>);
}

function DualRangeSlider({ label, minVal, maxVal, min, max, step = 1, unit = "", color = C.accent, onChange }) {
  const leftPct = ((minVal - min) / (max - min)) * 100; const rightPct = ((maxVal - min) / (max - min)) * 100;
  return (<div style={{ marginBottom: 14 }}>
    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
      <span style={{ color: C.textDim, fontSize: 10.5, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</span>
      <span style={{ color: C.text, fontWeight: 600, fontSize: 13, fontFamily: mono }}>{minVal}{unit} - {maxVal}{unit}</span>
    </div>
    <div style={{ position: "relative", height: 28, display: "flex", alignItems: "center" }}>
      <div style={{ position: "absolute", left: 0, right: 0, height: 5, borderRadius: 3, backgroundColor: C.border }} />
      <div style={{ position: "absolute", left: `${leftPct}%`, width: `${rightPct - leftPct}%`, height: 5, borderRadius: 3, backgroundColor: color, opacity: 0.6 }} />
      <input type="range" min={min} max={max} step={step} value={minVal} onChange={(e) => { const v = parseFloat(e.target.value); if (v <= maxVal - step) onChange(v, maxVal); }}
        style={{ position: "absolute", width: "100%", height: 24, appearance: "none", WebkitAppearance: "none", background: "transparent", cursor: "pointer", margin: 0, pointerEvents: "none", zIndex: minVal > max * 0.9 ? 5 : 3 }} className="ota-dual-thumb" />
      <input type="range" min={min} max={max} step={step} value={maxVal} onChange={(e) => { const v = parseFloat(e.target.value); if (v >= minVal + step) onChange(minVal, v); }}
        style={{ position: "absolute", width: "100%", height: 24, appearance: "none", WebkitAppearance: "none", background: "transparent", cursor: "pointer", margin: 0, pointerEvents: "none", zIndex: 4 }} className="ota-dual-thumb" />
    </div>
    <div style={{ display: "flex", justifyContent: "space-between", marginTop: 1 }}>
      <span style={{ color: C.textMuted, fontSize: 9.5 }}>{min}{unit}</span><span style={{ color: C.textMuted, fontSize: 9.5 }}>{max}{unit}</span>
    </div>
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

function ToggleChip({ label, checked, onChange, color }) {
  return (<button onClick={() => onChange(!checked)} style={{ padding: "5px 12px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer", transition: "all 0.15s", border: `1.5px solid ${checked ? color : C.border}`, backgroundColor: checked ? `${color}18` : "transparent", color: checked ? color : C.textMuted }}>{checked ? "\u2713 " : ""}{label}</button>);
}

function Sect({ title, icon, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (<div style={{ marginBottom: 10, borderRadius: 8, border: `1px solid ${C.border}`, backgroundColor: C.card }}>
    <button onClick={() => setOpen(!open)} style={{ width: "100%", padding: "10px 14px", display: "flex", alignItems: "center", justifyContent: "space-between", background: "none", border: "none", cursor: "pointer" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}><span style={{ fontSize: 14 }}>{icon}</span><span style={{ color: C.text, fontSize: 13, fontWeight: 600 }}>{title}</span></div>
      <span style={{ color: C.textMuted, fontSize: 16, transition: "transform 0.2s", transform: open ? "rotate(180deg)" : "rotate(0)", display: "inline-block" }}>&#9662;</span>
    </button>
    {open && <div style={{ padding: "2px 14px 14px", borderTop: `1px solid ${C.border}` }}>{children}</div>}
  </div>);
}

function PresetSelector({ presets, activePresetId, onSelect, onSaveNew, onOverwrite, onDelete, onRename }) {
  const [showSaveNew, setShowSaveNew] = useState(false); const [newName, setNewName] = useState(""); const [renamingId, setRenamingId] = useState(null); const [renameValue, setRenameValue] = useState(""); const [deleteConfirmId, setDeleteConfirmId] = useState(null);
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
        <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Name your preset..." autoFocus onKeyDown={(e) => e.key === "Enter" && handleSave()} style={{ flex: 1, padding: "6px 8px", borderRadius: 5, border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text, fontSize: 13, outline: "none" }} />
        <button onClick={handleSave} disabled={!newName.trim()} style={{ padding: "6px 14px", borderRadius: 5, border: "none", backgroundColor: newName.trim() ? C.accent : C.border, color: newName.trim() ? "#fff" : C.textMuted, fontSize: 12, fontWeight: 600, cursor: newName.trim() ? "pointer" : "default" }}>Save</button>
        <button onClick={() => { setShowSaveNew(false); setNewName(""); }} style={{ padding: "6px 10px", borderRadius: 5, border: `1px solid ${C.border}`, backgroundColor: "transparent", color: C.textDim, fontSize: 12, cursor: "pointer" }}>Cancel</button>
      </div>
    </div>)}
    {deleteConfirmId && (<div style={{ marginBottom: 10, padding: 10, borderRadius: 8, border: `1px solid ${C.red}40`, backgroundColor: C.redDim }}>
      <p style={{ fontSize: 12, color: C.text, margin: "0 0 8px", fontWeight: 500 }}>Delete &ldquo;{presets.find(p => p.id === deleteConfirmId)?.name}&rdquo;?</p>
      <div style={{ display: "flex", gap: 6 }}>
        <button onClick={() => { onDelete(deleteConfirmId); setDeleteConfirmId(null); }} style={{ padding: "6px 14px", borderRadius: 5, border: "none", backgroundColor: C.red, color: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>Yes, Delete</button>
        <button onClick={() => setDeleteConfirmId(null)} style={{ padding: "6px 14px", borderRadius: 5, border: `1px solid ${C.border}`, backgroundColor: "transparent", color: C.textDim, fontSize: 12, cursor: "pointer" }}>Cancel</button>
      </div>
    </div>)}
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {presets.map((p) => { const isA = p.id === activePresetId; return (
        <div key={p.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 7, border: `1.5px solid ${isA ? C.accent : C.border}`, backgroundColor: isA ? C.accentGlow : C.card, cursor: "pointer" }} onClick={() => { if (renamingId !== p.id) onSelect(p.id); }}>
          <span style={{ fontSize: 15, flexShrink: 0 }}>{p.icon}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            {renamingId === p.id ? (
              <div style={{ display: "flex", gap: 4 }} onClick={(e) => e.stopPropagation()}>
                <input type="text" value={renameValue} onChange={(e) => setRenameValue(e.target.value)} autoFocus onKeyDown={(e) => { if (e.key === "Enter") handleRename(p.id); if (e.key === "Escape") setRenamingId(null); }} style={{ flex: 1, padding: "3px 6px", borderRadius: 4, border: `1px solid ${C.borderFocus}`, backgroundColor: C.bg, color: C.text, fontSize: 12, outline: "none" }} />
                <button onClick={() => handleRename(p.id)} style={{ padding: "2px 8px", borderRadius: 4, border: "none", backgroundColor: C.accent, color: "#fff", fontSize: 10, cursor: "pointer" }}>&#10003;</button>
              </div>
            ) : (<><div style={{ color: isA ? C.accent : C.text, fontSize: 12, fontWeight: 600 }}>{p.name}</div><div style={{ color: C.textMuted, fontSize: 10 }}>{p.desc}</div></>)}
          </div>
          {renamingId !== p.id && (<div style={{ display: "flex", gap: 2, flexShrink: 0 }} onClick={(e) => e.stopPropagation()}>
            <button onClick={() => { setRenamingId(p.id); setRenameValue(p.name); }} title="Rename" style={{ width: 26, height: 26, borderRadius: 5, border: "none", backgroundColor: "transparent", color: C.textMuted, fontSize: 12, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>&#9998;</button>
            {isA && <button onClick={() => onOverwrite(p.id)} title="Update" style={{ width: 26, height: 26, borderRadius: 5, border: "none", backgroundColor: "transparent", color: C.textMuted, fontSize: 12, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>&#128190;</button>}
            {!p.builtIn && <button onClick={() => setDeleteConfirmId(p.id)} title="Delete" style={{ width: 26, height: 26, borderRadius: 5, border: "none", backgroundColor: "transparent", color: C.textMuted, fontSize: 13, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>&times;</button>}
          </div>)}
        </div>); })}
    </div>
  </div>);
}

const SLIDER_STYLES = `input[type=number]::-webkit-inner-spin-button,input[type=number]::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}input[type=number]{-moz-appearance:textfield}.ota-dual-thumb::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:16px;height:16px;border-radius:50%;background:#e2e8f0;border:2px solid #3b82f6;cursor:pointer;pointer-events:auto;box-shadow:0 0 4px rgba(0,0,0,0.3)}.ota-dual-thumb::-moz-range-thumb{width:16px;height:16px;border-radius:50%;background:#e2e8f0;border:2px solid #3b82f6;cursor:pointer;pointer-events:auto;box-shadow:0 0 4px rgba(0,0,0,0.3)}.ota-dual-thumb::-webkit-slider-runnable-track{background:transparent}.ota-dual-thumb::-moz-range-track{background:transparent}`;

// --- Main ConfigDrawer --------------------------------------------

export default function ConfigDrawer({ mode = "verticals", open, onClose, config, onApply, alignment, presets, activePresetId, onPresetSelect, onSavePreset, onOverwrite, onDelete, onRename }) {
  const [draft, setDraft] = useState(config);
  useEffect(() => { if (open) setDraft(config); }, [open, config]);

  const { weights, dte, strikes, spreads, risk, spreadTypes, greeks, smaPeriods } = draft;
  const st = spreadTypes || { bull_call: true, bear_put: true };
  const gk = greeks || { min_short_delta: 0.15, max_short_delta: 0.45, min_net_delta: 0, max_net_theta: 0 };
  const sma = smaPeriods || { short: 8, mid: 21, long: 50 };

  const ws = Object.values(weights).reduce((s, v) => s + v, 0);
  const wPct = Math.round(ws * 100);
  const wv = Math.abs(ws - 1.0) < 0.02;
  const [validationError, setValidationError] = useState(null);

  const hwc = useCallback((key, nv) => { setDraft(prev => ({ ...prev, weights: { ...prev.weights, [key]: nv } })); setValidationError(null); }, []);
  const sd = (u) => setDraft(prev => ({ ...prev, ...u }));

  const handleApply = useCallback(() => {
    const total = Object.values(draft.weights).reduce((s, v) => s + v, 0);
    if (Math.abs(total - 1.0) > 0.02) { setValidationError(`Scoring weights must total 100% (currently ${Math.round(total * 100)}%).`); return; }
    const sp = draft.smaPeriods || { short: 8, mid: 21, long: 50 };
    if (sp.short >= sp.mid || sp.mid >= sp.long) { setValidationError(`SMA periods must be in order: Short (${sp.short}) < Mid (${sp.mid}) < Long (${sp.long}).`); return; }
    if (draft.dte.min < 1) { setValidationError("Min DTE must be at least 1 day."); return; }
    if (draft.dte.max >= 730) { setValidationError("Max DTE must be less than 730 days."); return; }
    if (draft.dte.max <= draft.dte.min) { setValidationError(`Max DTE (${draft.dte.max}) must be greater than Min DTE (${draft.dte.min}).`); return; }
    setValidationError(null);
    onApply(draft);
  }, [draft, onApply]);

  const handleCancel = useCallback(() => { setDraft(config); onClose(); }, [config, onClose]);

  const isV = mode === "verticals";
  const subtitle = isV ? "Vertical Spread Settings" : "Naked Puts & Calls Settings";
  const alignLabel = alignment === "bullish" ? "Bullish" : alignment === "bearish" ? "Bearish" : "Mixed";
  const alignColor = alignment === "bullish" ? C.green : alignment === "bearish" ? C.red : C.yellow;
  const recType = alignment === "bullish" ? "bull_call" : alignment === "bearish" ? "bear_put" : null;

  return (<>
    {open && <div onClick={handleCancel} style={{ position: "fixed", inset: 0, backgroundColor: C.overlay, zIndex: 90 }} />}
    <div style={{ position: "fixed", top: 0, right: 0, bottom: 0, width: 400, backgroundColor: C.surface, borderLeft: `1px solid ${C.border}`, zIndex: 100, transform: open ? "translateX(0)" : "translateX(100%)", transition: "transform 0.25s cubic-bezier(0.4,0,0.2,1)", display: "flex", flexDirection: "column", boxShadow: open ? "-8px 0 30px rgba(0,0,0,0.4)" : "none" }}>
      <style>{SLIDER_STYLES}</style>

      {/* Header */}
      <div style={{ padding: "14px 18px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "center", flexShrink: 0 }}>
        <div><h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: C.text }}>Configuration</h2><p style={{ margin: "2px 0 0", fontSize: 11, color: C.textDim }}>{subtitle}</p></div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 10.5, padding: "2px 8px", borderRadius: 12, fontWeight: 600, fontFamily: mono, backgroundColor: wv ? C.greenDim : C.redDim, color: wv ? C.green : C.red }}>&Sigma; {wPct}%</span>
          <button onClick={handleCancel} style={{ background: "none", border: "none", color: C.textMuted, fontSize: 20, cursor: "pointer", padding: 4 }}>&times;</button>
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflowY: "auto", padding: "14px 18px" }}>
        <PresetSelector presets={presets} activePresetId={activePresetId} onSelect={onPresetSelect} onSaveNew={onSavePreset} onOverwrite={onOverwrite} onDelete={onDelete} onRename={onRename} />

        <Sect title="Scoring Weights" icon="&#9878;&#65039;" defaultOpen={true}>
          <p style={{ fontSize: 11, color: C.textDim, margin: "6px 0 8px", lineHeight: 1.4 }}>Drag each slider independently — total must equal 100%.</p>
          <WeightBar weights={weights} />
          <div style={{ textAlign: "right", marginBottom: 10 }}><span style={{ fontSize: 10, fontWeight: 600, fontFamily: mono, color: wv ? C.green : C.red }}>Total: {wPct}%{wv ? " \u2713" : ""}</span></div>
          {Object.keys(weights).map(k => <WeightSlider key={k} label={WEIGHT_LABELS[k]} value={weights[k]} color={WEIGHT_COLORS[k]} onChange={v => hwc(k, v)} />)}
        </Sect>

        {/* Spread Types — verticals only */}
        {isV && (<Sect title="Spread Types" icon="&#8693;" defaultOpen={true}>
          <div style={{ marginBottom: 8 }}>
            <span style={{ fontSize: 11, color: C.textDim }}>SMA Signal: </span>
            <span style={{ fontSize: 11, fontWeight: 600, color: alignColor }}>{alignLabel}</span>
            {recType && <span style={{ fontSize: 10, color: C.textMuted, marginLeft: 6 }}>— suggests {recType === "bull_call" ? "Bull Calls" : "Bear Puts"}</span>}
          </div>
          <div style={{ display: "flex", gap: 8, marginBottom: 6 }}>
            <ToggleChip label="Bull Call" checked={st.bull_call} onChange={(v) => sd({ spreadTypes: { ...st, bull_call: v } })} color={C.green} />
            <ToggleChip label="Bear Put" checked={st.bear_put} onChange={(v) => sd({ spreadTypes: { ...st, bear_put: v } })} color={C.red} />
          </div>
          {!st.bull_call && !st.bear_put && <p style={{ fontSize: 11, color: C.red, margin: "4px 0 0" }}>Select at least one spread type.</p>}
        </Sect>)}

        {/* SMA Periods — NEW */}
        <Sect title="SMA Periods" icon="&#128200;">
          <p style={{ fontSize: 11, color: C.textDim, margin: "4px 0 10px", lineHeight: 1.4 }}>Moving average windows for alignment detection and chart overlay. Common: 8/21/50 (swing), 20/50/200 (position).</p>
          <div style={{ display: "flex", gap: 12 }}>
            <NumInput label="Short" value={sma.short} onChange={v => sd({ smaPeriods: { ...sma, short: v } })} min={2} max={499} step={1} w={60} />
            <NumInput label="Mid" value={sma.mid} onChange={v => sd({ smaPeriods: { ...sma, mid: v } })} min={2} max={499} step={1} w={60} />
            <NumInput label="Long" value={sma.long} onChange={v => sd({ smaPeriods: { ...sma, long: v } })} min={2} max={500} step={1} w={60} />
          </div>
        </Sect>

        <Sect title="Days to Expiration" icon="&#128197;">
          <div style={{ display: "flex", gap: 12, alignItems: "flex-end" }}>
            <NumInput label="Min DTE" value={dte.min} onChange={v => sd({ dte: { ...dte, min: v } })} min={1} max={729} step={1} unit="days" w={70} />
            <NumInput label="Max DTE" value={dte.max} onChange={v => sd({ dte: { ...dte, max: v } })} min={1} max={730} step={1} unit="days" w={70} />
          </div>
        </Sect>

        <Sect title="Greek Filters" icon="&#916;">
          <p style={{ fontSize: 11, color: C.textDim, margin: "4px 0 10px", lineHeight: 1.4 }}>
            {isV ? "Short delta range filters individual legs; net delta filters the completed spread." : "Controls the delta range for option selection and time decay limits."}
          </p>
          <SingleSlider label="Min Delta" value={parseFloat(gk.min_short_delta.toFixed(2))} min={0.05} max={gk.max_short_delta - 0.05} step={0.05} color={C.accent} onChange={v => sd({ greeks: { ...gk, min_short_delta: parseFloat(v.toFixed(2)) } })} />
          <SingleSlider label="Max Delta" value={parseFloat(gk.max_short_delta.toFixed(2))} min={gk.min_short_delta + 0.05} max={0.80} step={0.05} color={C.accent} onChange={v => sd({ greeks: { ...gk, max_short_delta: parseFloat(v.toFixed(2)) } })} />
          <SingleSlider label="Min Net Delta" value={parseFloat(gk.min_net_delta.toFixed(2))} min={0} max={0.50} step={0.05} color={C.yellow} onChange={v => sd({ greeks: { ...gk, min_net_delta: parseFloat(v.toFixed(2)) } })} />
          <SingleSlider label="Max Net Theta" value={parseFloat(gk.max_net_theta.toFixed(2))} min={0} max={2.0} step={0.05} unit="/day" color={C.red} onChange={v => sd({ greeks: { ...gk, max_net_theta: parseFloat(v.toFixed(2)) } })} />
          <p style={{ fontSize: 10, color: C.textMuted, margin: "2px 0 0" }}>0 = no filter</p>
        </Sect>

        <Sect title={isV ? "Strike & Spread Filters" : "Strike Filters"} icon="&#127919;">
          <NumInput label="Strike Range" value={strikes.range_pct} onChange={v => sd({ strikes: { ...strikes, range_pct: v } })} min={1} max={50} step={0.5} unit="%" />
          <SingleSlider label="Min Open Interest" value={strikes.min_open_interest} min={0} max={1000} step={10} color={C.accent} onChange={v => sd({ strikes: { ...strikes, min_open_interest: v } })} />
          <SingleSlider label="Min Volume" value={strikes.min_volume} min={0} max={500} step={5} color={C.accent} onChange={v => sd({ strikes: { ...strikes, min_volume: v } })} />
          {isV && <DualRangeSlider label="Spread Width" minVal={spreads.min_width} maxVal={spreads.max_width} min={1} max={40} step={1} color={C.accent} onChange={(a, b) => sd({ spreads: { ...spreads, min_width: a, max_width: b } })} />}
        </Sect>

        <Sect title="Risk Management" icon="&#128737;&#65039;">
          <SingleSlider label="Max Risk Per Trade" value={risk.max_risk_per_trade} min={50} max={5000} step={50} color={C.accent} onChange={v => sd({ risk: { ...risk, max_risk_per_trade: v } })} />
          <SingleSlider label="Profit Target" value={risk.profit_target_pct} min={0} max={500} step={5} unit="%" color={C.green} onChange={v => sd({ risk: { ...risk, profit_target_pct: v } })} />
          <SingleSlider label="Stop Loss" value={risk.stop_loss_pct} min={0} max={100} step={5} unit="%" color={C.red} onChange={v => sd({ risk: { ...risk, stop_loss_pct: v } })} />
        </Sect>
      </div>

      {/* Footer */}
      <div style={{ padding: "12px 18px", borderTop: `1px solid ${C.border}`, flexShrink: 0 }}>
        {validationError && <div style={{ padding: "8px 12px", marginBottom: 8, borderRadius: 6, border: `1px solid ${C.red}40`, backgroundColor: C.redDim, color: C.red, fontSize: 11.5, lineHeight: 1.4 }}>{validationError}</div>}
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={handleApply} style={{ flex: 1, padding: "10px 0", borderRadius: 8, border: "none", fontWeight: 600, fontSize: 13, cursor: wv ? "pointer" : "not-allowed", backgroundColor: wv ? C.accent : C.border, color: wv ? "#fff" : C.textMuted, opacity: wv ? 1 : 0.7 }}>Apply & Re-analyze</button>
          <button onClick={handleCancel} style={{ padding: "10px 16px", borderRadius: 8, border: `1px solid ${C.border}`, backgroundColor: "transparent", color: C.textDim, fontSize: 13, cursor: "pointer" }}>Cancel</button>
        </div>
      </div>
    </div>
  </>);
}
