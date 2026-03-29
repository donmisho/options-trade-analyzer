/**
 * SystemVarsPanel — Right-side slide-out drawer for application-wide settings.
 *
 * Contains fields previously under "System Variables" in ConfigDrawer.
 * These are app-level defaults (exit levels, stop buffers, health thresholds)
 * that apply across all strategies and pages.
 *
 * Apply  → saves to AppContext systemVars + persists to localStorage
 * Reset  → restores hardcoded defaults without auto-saving
 */
import { useState, useEffect } from 'react';
import { C, mono } from '../styles/tokens';
import { useApp } from '../context/AppContext';

// ─── Default values ──────────────────────────────────────────────────────────

const DEFAULT_SV = {
  exit_warning_pct: 67,
  exit_scale_out_pct: 160,
  exit_underlying_stop_pct: 1.5,
  exit_time_stop_days: 10,
  min_reward_risk: 0.5,
  min_ev_threshold: 0,
  pip_rr_green: 1.5,
  pip_rr_amber: 1.0,
  pip_prob_green: 0.55,
  pip_prob_amber: 0.45,
  pip_score_green: 0.65,
  pip_score_amber: 0.45,
  pip_delta_lo: 0.30,
  pip_delta_hi: 0.65,
  pip_iv_green: 30,
  pip_iv_amber: 50,
  pip_runway_green: 30,
  pip_runway_amber: 15,
};

// ─── Form primitives (self-contained) ────────────────────────────────────────

function SingleSlider({ label, value, min, max, step = 1, unit = '', color = C.accent, onChange }) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
        <span style={{ color: C.textDim, fontSize: 10.5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</span>
        <span style={{ color: C.text, fontWeight: 600, fontSize: 13, fontFamily: mono }}>{value}{unit}</span>
      </div>
      <div style={{ position: 'relative', height: 24, display: 'flex', alignItems: 'center' }}>
        <div style={{ position: 'absolute', left: 0, right: 0, height: 5, borderRadius: 3, backgroundColor: C.border }} />
        <div style={{ position: 'absolute', left: 0, height: 5, borderRadius: 3, width: `${pct}%`, backgroundColor: color, opacity: 0.6, transition: 'width 0.15s' }} />
        <input type="range" min={min} max={max} step={step} value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          style={{ position: 'absolute', left: 0, right: 0, width: '100%', height: 24, appearance: 'none', WebkitAppearance: 'none', background: 'transparent', cursor: 'pointer', margin: 0, zIndex: 2 }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 1 }}>
        <span style={{ color: C.textMuted, fontSize: 9.5 }}>{min}{unit}</span>
        <span style={{ color: C.textMuted, fontSize: 9.5 }}>{max}{unit}</span>
      </div>
    </div>
  );
}

function DualRangeSlider({ label, minVal, maxVal, min, max, step = 1, unit = '', color = C.accent, onChange }) {
  const leftPct = ((minVal - min) / (max - min)) * 100;
  const rightPct = ((maxVal - min) / (max - min)) * 100;
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
        <span style={{ color: C.textDim, fontSize: 10.5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</span>
        <span style={{ color: C.text, fontWeight: 600, fontSize: 13, fontFamily: mono }}>{minVal}{unit} – {maxVal}{unit}</span>
      </div>
      <div style={{ position: 'relative', height: 28, display: 'flex', alignItems: 'center' }}>
        <div style={{ position: 'absolute', left: 0, right: 0, height: 5, borderRadius: 3, backgroundColor: C.border }} />
        <div style={{ position: 'absolute', left: `${leftPct}%`, width: `${rightPct - leftPct}%`, height: 5, borderRadius: 3, backgroundColor: color, opacity: 0.6 }} />
        <input type="range" min={min} max={max} step={step} value={minVal}
          onChange={(e) => { const v = parseFloat(e.target.value); if (v <= maxVal - step) onChange(v, maxVal); }}
          style={{ position: 'absolute', width: '100%', height: 24, appearance: 'none', WebkitAppearance: 'none', background: 'transparent', cursor: 'pointer', margin: 0, pointerEvents: 'none', zIndex: minVal > max * 0.9 ? 5 : 3 }} className="ota-dual-thumb" />
        <input type="range" min={min} max={max} step={step} value={maxVal}
          onChange={(e) => { const v = parseFloat(e.target.value); if (v >= minVal + step) onChange(minVal, v); }}
          style={{ position: 'absolute', width: '100%', height: 24, appearance: 'none', WebkitAppearance: 'none', background: 'transparent', cursor: 'pointer', margin: 0, pointerEvents: 'none', zIndex: 4 }} className="ota-dual-thumb" />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 1 }}>
        <span style={{ color: C.textMuted, fontSize: 9.5 }}>{min}{unit}</span>
        <span style={{ color: C.textMuted, fontSize: 9.5 }}>{max}{unit}</span>
      </div>
    </div>
  );
}

function NumInput({ label, value, onChange, min, max, step = 1, unit = '', w = 80 }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <label style={{ display: 'block', color: C.textDim, fontSize: 10.5, fontWeight: 600, marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</label>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <input type="number" value={value} min={min} max={max} step={step}
          onChange={(e) => { let v = parseFloat(e.target.value); if (!isNaN(v)) { if (min !== undefined) v = Math.max(min, v); if (max !== undefined) v = Math.min(max, v); onChange(v); } }}
          style={{ width: w, padding: '5px 7px', borderRadius: 5, border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text, fontSize: 13, fontFamily: mono, outline: 'none', textAlign: 'right' }}
          onFocus={(e) => e.target.style.borderColor = C.borderFocus}
          onBlur={(e) => e.target.style.borderColor = C.border} />
        {unit && <span style={{ color: C.textMuted, fontSize: 11 }}>{unit}</span>}
      </div>
    </div>
  );
}

function SectionHeading({ title }) {
  return (
    <p style={{ fontSize: 10.5, color: C.textDim, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 10px', paddingTop: 14, borderTop: `1px solid ${C.border}` }}>
      {title}
    </p>
  );
}

const SLIDER_STYLES = `
  input[type=number]::-webkit-inner-spin-button,
  input[type=number]::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0 }
  input[type=number] { -moz-appearance: textfield }
  .ota-dual-thumb::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 16px; height: 16px; border-radius: 50%; background: #e2e8f0; border: 2px solid #3b82f6; cursor: pointer; pointer-events: auto; box-shadow: 0 0 4px rgba(0,0,0,0.3) }
  .ota-dual-thumb::-moz-range-thumb { width: 16px; height: 16px; border-radius: 50%; background: #e2e8f0; border: 2px solid #3b82f6; cursor: pointer; pointer-events: auto; box-shadow: 0 0 4px rgba(0,0,0,0.3) }
  .ota-dual-thumb::-webkit-slider-runnable-track { background: transparent }
  .ota-dual-thumb::-moz-range-track { background: transparent }
`;

// ─── Main component ───────────────────────────────────────────────────────────

export default function SystemVarsPanel({ open, onClose }) {
  const { systemVars, setSystemVars } = useApp();
  const [draft, setDraft] = useState({ ...DEFAULT_SV });

  // Sync draft when panel opens
  useEffect(() => {
    if (open) setDraft({ ...DEFAULT_SV, ...systemVars });
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const upd = (key, val) => setDraft(prev => ({ ...prev, [key]: val }));

  const handleApply = () => {
    setSystemVars(draft);
    try {
      const stored = JSON.parse(localStorage.getItem('analysisConfig') || '{}');
      localStorage.setItem('analysisConfig', JSON.stringify({ ...stored, systemVars: draft }));
    } catch { /* silently ignore */ }
    onClose();
  };

  const handleReset = () => {
    setDraft({ ...DEFAULT_SV });
  };

  return (
    <>
      <style>{SLIDER_STYLES}</style>
      {open && (
        <div
          onClick={onClose}
          style={{ position: 'fixed', inset: 0, backgroundColor: C.overlay, zIndex: 90 }}
        />
      )}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 400,
        backgroundColor: C.surface, borderLeft: `1px solid ${C.border}`,
        zIndex: 100,
        transform: open ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform 0.25s cubic-bezier(0.4,0,0.2,1)',
        display: 'flex', flexDirection: 'column',
        boxShadow: open ? '-8px 0 30px rgba(0,0,0,0.4)' : 'none',
      }}>

        {/* Header */}
        <div style={{ padding: '14px 18px', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: C.text }}>System Settings</h2>
            <p style={{ margin: '2px 0 0', fontSize: 11, color: C.textDim }}>Application-wide behavior defaults</p>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: C.textMuted, fontSize: 20, cursor: 'pointer', padding: 4 }}>&times;</button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '14px 18px' }}>

          {/* Exit Levels */}
          <p style={{ fontSize: 11, color: C.textDim, margin: '4px 0 12px', lineHeight: 1.5 }}>
            Exit level thresholds used in Claude trade evaluation. Control when to warn, scale out, and stop — expressed as a percentage of the spread debit or current price.
          </p>
          <SingleSlider label="Exit Warning Level" value={draft.exit_warning_pct} min={10} max={99} step={1} unit="% of debit" color={C.amber} onChange={v => upd('exit_warning_pct', v)} />
          <p style={{ fontSize: 10, color: C.textMuted, margin: '-8px 0 12px' }}>Alert threshold — e.g. 67% means warn when spread value drops to 0.67 on a 1.00 debit.</p>
          <SingleSlider label="Exit Scale-Out Level" value={draft.exit_scale_out_pct} min={110} max={300} step={5} unit="% of debit" color={C.green} onChange={v => upd('exit_scale_out_pct', v)} />
          <p style={{ fontSize: 10, color: C.textMuted, margin: '-8px 0 12px' }}>Partial profit exit — e.g. 160% means begin scaling out when spread is worth 1.60 on a 1.00 debit.</p>
          <NumInput label="Underlying Stop Buffer" value={draft.exit_underlying_stop_pct} onChange={v => upd('exit_underlying_stop_pct', v)} min={0.1} max={10} step={0.1} unit="% below price" />
          <p style={{ fontSize: 10, color: C.textMuted, margin: '-6px 0 12px' }}>Stock hard stop: min(SMA-short, price − buffer%). Exit the trade if stock falls here.</p>
          <NumInput label="Time Stop (days before expiry)" value={draft.exit_time_stop_days} onChange={v => upd('exit_time_stop_days', v)} min={1} max={60} step={1} unit="days" />
          <p style={{ fontSize: 10, color: C.textMuted, margin: '-6px 0 4px' }}>Force exit when DTE falls below this threshold to avoid gamma risk near expiration.</p>

          {/* Scoring Filters */}
          <SectionHeading title="Scoring Filters" />
          <p style={{ fontSize: 11, color: C.textDim, margin: '0 0 10px', lineHeight: 1.5 }}>Pre-scoring gates — spreads failing these are removed before scoring begins.</p>
          <NumInput label="Min Reward:Risk" value={draft.min_reward_risk} onChange={v => upd('min_reward_risk', v)} min={0.1} max={5.0} step={0.1} unit=":1" />
          <p style={{ fontSize: 10, color: C.textMuted, margin: '-6px 0 12px' }}>Minimum reward:risk ratio to consider. Default 0.5 = at least 0.50 profit per 1.00 risk.</p>
          <NumInput label="Min Expected Value" value={draft.min_ev_threshold} onChange={v => upd('min_ev_threshold', v)} min={-10} max={10} step={0.05} unit="× debit" />
          <p style={{ fontSize: 10, color: C.textMuted, margin: '-6px 0 4px' }}>Minimum EV as a multiple of the debit. 0 = only show positive EV trades.</p>

          {/* Health Indicators — Verticals */}
          <SectionHeading title="Health Indicator Thresholds — Verticals" />
          <p style={{ fontSize: 11, color: C.textDim, margin: '0 0 8px', lineHeight: 1.5 }}>R:R, Probability, Composite Score pip color cutoffs. Amber = lower bound, Green = upper bound.</p>
          <DualRangeSlider label="R:R Pip (amber / green)" minVal={draft.pip_rr_amber} maxVal={draft.pip_rr_green} min={0.1} max={5.0} step={0.1} color={C.green} onChange={(a, b) => setDraft(p => ({ ...p, pip_rr_amber: a, pip_rr_green: b }))} />
          <DualRangeSlider label="Prob Pip (amber / green)" minVal={draft.pip_prob_amber} maxVal={draft.pip_prob_green} min={0.10} max={0.90} step={0.05} color={C.accent} onChange={(a, b) => setDraft(p => ({ ...p, pip_prob_amber: a, pip_prob_green: b }))} />
          <DualRangeSlider label="Score Pip (amber / green)" minVal={draft.pip_score_amber} maxVal={draft.pip_score_green} min={0.10} max={0.95} step={0.05} color={C.purple} onChange={(a, b) => setDraft(p => ({ ...p, pip_score_amber: a, pip_score_green: b }))} />

          {/* Health Indicators — Puts & Calls */}
          <SectionHeading title="Health Indicator Thresholds — Puts & Calls" />
          <p style={{ fontSize: 11, color: C.textDim, margin: '0 0 8px', lineHeight: 1.5 }}>Delta sweet spot, IV entry quality, Theta runway pip color cutoffs.</p>
          <DualRangeSlider label="Delta Sweet Spot (lo / hi)" minVal={draft.pip_delta_lo} maxVal={draft.pip_delta_hi} min={0.05} max={0.95} step={0.05} color={C.accent} onChange={(a, b) => setDraft(p => ({ ...p, pip_delta_lo: a, pip_delta_hi: b }))} />
          <p style={{ fontSize: 10, color: C.textMuted, margin: '-8px 0 12px' }}>Green when delta is within this range. Amber within ±0.05 of either edge, red outside.</p>
          <DualRangeSlider label="IV Pip (green / amber)" minVal={draft.pip_iv_green} maxVal={draft.pip_iv_amber} min={5} max={150} step={5} unit="%" color={C.amber} onChange={(a, b) => setDraft(p => ({ ...p, pip_iv_green: a, pip_iv_amber: b }))} />
          <p style={{ fontSize: 10, color: C.textMuted, margin: '-8px 0 12px' }}>Green when IV ≤ left value, amber when ≤ right value, red above.</p>
          <DualRangeSlider label="Runway Pip (amber / green)" minVal={draft.pip_runway_amber} maxVal={draft.pip_runway_green} min={1} max={120} step={1} unit="d" color={C.green} onChange={(a, b) => setDraft(p => ({ ...p, pip_runway_amber: a, pip_runway_green: b }))} />
          <p style={{ fontSize: 10, color: C.textMuted, margin: '-8px 0 12px' }}>Green when runway ≥ right value, amber when ≥ left value, red below.</p>

        </div>

        {/* Footer */}
        <div style={{ padding: '12px 18px', borderTop: `1px solid ${C.border}`, flexShrink: 0 }}>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button
              onClick={handleReset}
              style={{ padding: '8px 16px', borderRadius: 8, border: `1px solid ${C.border}`, backgroundColor: 'transparent', color: C.textDim, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
            >
              Reset to Defaults
            </button>
            <button
              onClick={handleApply}
              style={{ padding: '8px 20px', borderRadius: 8, border: 'none', backgroundColor: C.accent, color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
            >
              Apply
            </button>
          </div>
        </div>

      </div>
    </>
  );
}
