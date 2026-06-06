/**
 * JunctionRowEditor + ParameterEditor — shared section-editor subcomponents.
 *
 * Created by OTA-785 (Hard Gates tab); reused by OTA-786 (Scoring Weights) and
 * OTA-787 (Adjustments). One junction binding renders as one row: the bound
 * rule's display metadata (label/phase/tier/intent, joined by OTA-826), an
 * enabled toggle, its variable threshold parameters (driven by the rule's
 * parameter_schema, written into the junction `parameters` JSON), and the
 * mechanical junction fields the host tab opts into.
 *
 * The mechanical fields are CONFIGURABLE, not hardcoded, so each tab shows only
 * what it edits:
 *   - Hard Gates (OTA-785): evaluation_order + stop_if_fail
 *   - Scoring (OTA-786):    weight
 *   - Adjustments (OTA-787): score_penalty (+ evaluation_order)
 *
 * Controlled component: the host owns the working row state. `onChange(patch)`
 * is a local (no-network) update fired per keystroke; `onCommit(patch?)` asks
 * the host to persist (number/text fields commit on blur, toggles commit
 * immediately). `onRemove()` deletes the binding.
 *
 * Tokens: CSS var(--*) only (UI-GUIDANCE Part 3). No inline hex, no `$`,
 * scores/penalties/weights formatted by the host where displayed read-only.
 */

import { useState } from 'react';

const MONO = "'JetBrains Mono', monospace";

const lblStyle = {
  fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.5px',
  color: 'var(--muted)', marginBottom: 4, fontFamily: MONO,
};
const inputStyle = {
  background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text)',
  padding: '4px 8px', borderRadius: 3, fontSize: 12, fontFamily: MONO,
};

/** snake_case / kebab → Title Case ('min_credit_pct' → 'Min Credit Pct'). */
function prettify(s) {
  return String(s)
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

const TIER_COLOR = {
  raw: 'var(--muted)',
  derived: 'var(--blue)',
  computed: 'var(--purple)',
};

/**
 * Build a parameters object pre-filled with every default declared in a rule's
 * parameter_schema. Used when binding a new rule so the junction starts with
 * sensible values. Returns {} for an absent/empty schema.
 */
export function defaultsFromSchema(schema) {
  if (!schema || typeof schema !== 'object') return {};
  const out = {};
  for (const [key, spec] of Object.entries(schema)) {
    if (spec && typeof spec === 'object' && 'default' in spec) out[key] = spec.default;
  }
  return out;
}

/**
 * ParameterEditor — renders one input per key in a rule's parameter_schema,
 * editing into the junction `parameters` JSON object. Number specs render a
 * number input (with optional min/max/step/suffix); boolean specs a checkbox;
 * anything else a text input. Emits the WHOLE updated parameters object so the
 * host can store it verbatim.
 *
 * @param {Object|null} schema      — rule.parameter_schema ({ key: {type,default,...} })
 * @param {Object|null} parameters  — current junction.parameters
 * @param {boolean}     editable
 * @param {(params:Object)=>void} onChange  — local update (per keystroke)
 * @param {()=>void}    onCommit    — persist (on blur / toggle)
 */
export function ParameterEditor({ schema, parameters, editable, onChange, onCommit }) {
  const entries = schema && typeof schema === 'object' ? Object.entries(schema) : [];
  const values = parameters && typeof parameters === 'object' ? parameters : {};

  if (entries.length === 0) {
    return (
      <span style={{ fontSize: 10, color: 'var(--muted)', fontStyle: 'italic', fontFamily: MONO }}>
        No parameters
      </span>
    );
  }

  const setOne = (key, next) => onChange({ ...values, [key]: next });

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
      {entries.map(([key, spec]) => {
        const type = (spec && spec.type) || 'string';
        const label = (spec && spec.label) || prettify(key);
        const suffix = spec && spec.suffix;
        const current = key in values ? values[key] : (spec && spec.default);

        if (type === 'boolean') {
          return (
            <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: MONO }}>
              <input
                type="checkbox"
                checked={Boolean(current)}
                disabled={!editable}
                onChange={e => { setOne(key, e.target.checked); onCommit && onCommit(); }}
              />
              <span style={{ fontSize: 11, color: 'var(--text)' }}>{label}</span>
            </label>
          );
        }

        const isNum = type === 'number' || type === 'integer';
        return (
          <div key={key}>
            <div style={lblStyle}>{label}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <input
                type={isNum ? 'number' : 'text'}
                value={current ?? ''}
                disabled={!editable}
                min={spec && spec.min}
                max={spec && spec.max}
                step={spec && spec.step != null ? spec.step : (type === 'integer' ? 1 : 'any')}
                onChange={e => {
                  const raw = e.target.value;
                  setOne(key, isNum ? (raw === '' ? '' : Number(raw)) : raw);
                }}
                onBlur={() => onCommit && onCommit()}
                style={{ ...inputStyle, width: isNum ? 76 : 130, textAlign: isNum ? 'right' : 'left' }}
              />
              {suffix && <span style={{ fontSize: 11, color: 'var(--muted)' }}>{suffix}</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * PercentWeightInput — edits the junction `weight` as a PERCENT (OTA-786) while
 * the stored value stays a FRACTION (numeric(7,4), summing to 1.0 server-side).
 * Displays/edits e.g. `30.00 %`; emits the fraction (raw/100) on each keystroke
 * so the host's live sum indicator stays current, and the host rounds to 4dp on
 * write. Local string state echoes exactly what the user types (no mid-type
 * rounding jank); it initialises from the prop at mount only — new rows remount
 * via their junction_id key, so reloads pick up server values.
 */
function PercentWeightInput({ weight, disabled, onChange, onCommit }) {
  const toPct = w => (w === '' || w == null ? '' : String(+(Number(w) * 100).toFixed(2)));
  const [str, setStr] = useState(() => toPct(weight));

  return (
    <div>
      <div style={lblStyle}>Weight</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <input
          type="number"
          value={str}
          disabled={disabled}
          step={0.01}
          onChange={e => {
            const raw = e.target.value;
            setStr(raw);
            onChange({ weight: raw === '' ? '' : Number(raw) / 100 });
          }}
          onBlur={() => onCommit && onCommit()}
          style={{ ...inputStyle, width: 76, textAlign: 'right' }}
        />
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>%</span>
      </div>
    </div>
  );
}

/**
 * JunctionRowEditor — one junction binding as an editable row.
 *
 * @param {Object}  junction          — StrategyJunctionRow (OTA-826 shape)
 * @param {boolean} editable
 * @param {boolean} showEvaluationOrder — render the evaluation_order input (default true)
 * @param {boolean} showStopIfFail      — render the stop_if_fail toggle (gates)
 * @param {boolean} showWeight          — render the weight input (scoring)
 * @param {boolean} weightAsPercent     — display/edit weight as percent (OTA-786); stored as fraction
 * @param {boolean} showScorePenalty    — render the score_penalty input (adjustments)
 * @param {boolean} showParameters      — render the ParameterEditor (default true)
 * @param {boolean} duplicateOrder      — advisory: this row's evaluation_order collides
 * @param {boolean} busy                — a write is in flight; disable controls
 * @param {(patch:Object)=>void}        onChange  — local update (per keystroke)
 * @param {(patch?:Object)=>void}       onCommit  — persist (blur / toggle)
 * @param {()=>void}                    onRemove  — delete this binding
 */
export default function JunctionRowEditor({
  junction,
  editable,
  showEvaluationOrder = true,
  showStopIfFail = false,
  showWeight = false,
  weightAsPercent = false,
  showScorePenalty = false,
  showParameters = true,
  duplicateOrder = false,
  busy = false,
  onChange,
  onCommit,
  onRemove,
}) {
  const j = junction;
  const tier = (j.tier || '').toLowerCase();
  const disabled = !editable || busy;

  // Number field that commits on blur (evaluation_order / weight / score_penalty).
  const numberField = (label, field, value, { step = 'any', width = 76, isInt = false } = {}) => (
    <div>
      <div style={lblStyle}>{label}</div>
      <input
        type="number"
        value={value ?? ''}
        disabled={disabled}
        step={isInt ? 1 : step}
        onChange={e => {
          const raw = e.target.value;
          onChange({ [field]: raw === '' ? '' : (isInt ? parseInt(raw, 10) : Number(raw)) });
        }}
        onBlur={() => onCommit && onCommit()}
        style={{
          ...inputStyle, width, textAlign: 'right',
          borderColor: field === 'evaluation_order' && duplicateOrder ? 'var(--amber)' : 'var(--border)',
        }}
      />
    </div>
  );

  return (
    <div style={{
      border: '1px solid var(--border)',
      borderRadius: 6, padding: '12px 14px', marginBottom: 8,
      opacity: j.enabled ? 1 : 0.55,
      display: 'flex', gap: 16, alignItems: 'flex-start', justifyContent: 'space-between',
      fontFamily: MONO,
    }}>
      {/* ── Identity + parameters ── */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {/* enabled toggle */}
          <input
            type="checkbox"
            checked={Boolean(j.enabled)}
            disabled={disabled}
            aria-label={`${j.enabled ? 'Disable' : 'Enable'} ${j.rule_key}`}
            onChange={e => onCommit && onCommit({ enabled: e.target.checked })}
          />
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>
            {prettify(j.rule_key)}
          </span>
          {tier && (
            <span style={{
              fontSize: 8, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.4px',
              color: TIER_COLOR[tier] || 'var(--muted)',
              border: `1px solid ${TIER_COLOR[tier] || 'var(--muted)'}`,
              borderRadius: 3, padding: '1px 5px',
            }}>{tier}</span>
          )}
          <span style={{ fontSize: 10, color: 'var(--muted)' }}>{j.rule_key}</span>
        </div>

        {j.intent && (
          <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4, lineHeight: 1.5 }}>
            {j.intent}
          </div>
        )}

        {showParameters && (
          <div style={{ marginTop: 10 }}>
            <ParameterEditor
              schema={j.parameter_schema}
              parameters={j.parameters}
              editable={!disabled}
              onChange={params => onChange({ parameters: params })}
              onCommit={onCommit}
            />
          </div>
        )}

        {duplicateOrder && (
          <div style={{ fontSize: 10, color: 'var(--amber)', marginTop: 8 }}>
            ● Duplicate evaluation order in this phase — advisory only; resolve before Apply.
          </div>
        )}
      </div>

      {/* ── Mechanical fields + remove ── */}
      <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start', flexShrink: 0 }}>
        {showEvaluationOrder && numberField('Order', 'evaluation_order', j.evaluation_order, { isInt: true, width: 60 })}
        {showWeight && (weightAsPercent
          ? <PercentWeightInput weight={j.weight} disabled={disabled} onChange={onChange} onCommit={onCommit} />
          : numberField('Weight', 'weight', j.weight, { step: 0.01, width: 76 }))}
        {showScorePenalty && numberField('Penalty', 'score_penalty', j.score_penalty, { step: 0.01, width: 76 })}
        {showStopIfFail && (
          <div>
            <div style={lblStyle}>Stop if fail</div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, height: 26 }}>
              <input
                type="checkbox"
                checked={Boolean(j.stop_if_fail)}
                disabled={disabled}
                onChange={e => onCommit && onCommit({ stop_if_fail: e.target.checked })}
              />
              <span style={{ fontSize: 10, color: j.stop_if_fail ? 'var(--red)' : 'var(--muted)' }}>
                {j.stop_if_fail ? 'halts' : 'records'}
              </span>
            </label>
          </div>
        )}
        {editable && (
          <button
            onClick={onRemove}
            disabled={busy}
            title="Remove this binding (the rule is not deleted)"
            style={{
              background: 'transparent', border: '1px solid var(--border)', color: 'var(--muted)',
              borderRadius: 4, padding: '4px 10px', fontSize: 11, fontFamily: MONO,
              cursor: busy ? 'default' : 'pointer', alignSelf: 'center',
            }}
          >Remove</button>
        )}
      </div>
    </div>
  );
}
