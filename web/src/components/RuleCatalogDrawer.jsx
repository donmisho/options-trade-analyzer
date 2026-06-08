/**
 * RuleCatalogDrawer — the single read-only rule-catalog browser (OTA-789).
 *
 * One shared drawer, opened from the Hard Gates / Scoring / Adjustments section
 * "+ Add from catalog" buttons. It is the SINGLE source feeding all three tab
 * pickers: it reads the owner-spanning rule catalog (OTA + SHARED) from the
 * OTA-825 `/config/rules/admin` endpoint via getRulesAdmin(), and binds the
 * chosen rule to the selected strategy's draft junction.
 *
 * Layout contract: the v2 prototype catalog drawer (right-side panel, header +
 * three phase tabs, stacked rule cards). Per rule it surfaces the five fields
 * OTA-789 requires: intent, referenced named values (inputs), expected output
 * (phase-derived), phase, and formula-registry status (registered yes/no/n/a,
 * from the endpoint's computed `formula_registered`).
 *
 * SHARED rules are shown and SELECTABLE for binding (a junction row may reference
 * them) but are read-only as rules — this surface never edits or deletes a rule,
 * only creates a junction binding, so every rule here is rule-immutable by design.
 *
 * Bind parity (OTA-789): the bind action is byte-identical to the inline pickers
 * it replaces (OTA-785/786/787) — ensure `<key>__draft` (create-or-resume, which
 * clones live header + junctions), compute the next evaluation_order within the
 * rule's phase, and createJunction with the phase-appropriate defaults:
 *   gate       → stop_if_fail=true
 *   scoring    → stop_if_fail=false, weight=0
 *   adjustment → stop_if_fail=false
 * After a bind we re-read this drawer's junctions (refresh dimming) and call
 * onBound() so the open sections reload their rows. Live is untouched until Apply.
 *
 * Tokens: CSS var(--*) per UI-GUIDANCE Part 3 (matching StrategyAdminPage). No
 * inline hex, no `$`.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { defaultsFromSchema } from './JunctionRowEditor';
import {
  getRulesAdmin,
  getStrategyJunctions,
  createJunction,
  createOrResumeDraft,
} from '../api/client';
import { useToast } from './Toast';

const MONO = "'JetBrains Mono', monospace";
const OTA_OWNER = 'OTA';

// Tab keys ARE the engine phase values (gate/scoring/adjustment) so there is no
// plural/singular mapping to drift. Labels are the human-facing display.
const TABS = [
  { key: 'gate', label: 'Hard Gates' },
  { key: 'scoring', label: 'Scoring' },
  { key: 'adjustment', label: 'Adjustments' },
];

// Phase → "expected output" display label (insight_engine.md §9.1: what the
// engine does with the rule's result — derived from phase, not a stored column).
const EXPECTED_OUTPUT = {
  gate: 'Pass / fail gate',
  scoring: 'Score contribution',
  adjustment: 'Score adjustment (±)',
};

/** snake_case / kebab → Title Case (matches the section components). */
function prettify(s) {
  return String(s).replace(/[_-]+/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

/** Render a rule's referenced named values (inputs) as a readable list. */
function inputsLabel(refs) {
  if (Array.isArray(refs)) return refs.length ? refs.join(', ') : '—';
  if (refs && typeof refs === 'object') {
    const keys = Object.keys(refs);
    return keys.length ? keys.join(', ') : '—';
  }
  return refs ? String(refs) : '—';
}

export default function RuleCatalogDrawer({
  strategyKey,
  editable,
  initialPhase = 'gate',
  onClose,
  onBound,
}) {
  const { showToast } = useToast();
  const draftKey = `${strategyKey}__draft`;

  const [activeTab, setActiveTab] = useState(initialPhase);
  const [catalog, setCatalog]     = useState(null);   // null = loading
  const [catalogErr, setCatalogErr] = useState(null);
  const [junctions, setJunctions] = useState([]);     // bound rows (draft-preferred)
  const [mutating, setMutating]   = useState(false);

  // Re-open from a different section → switch the tab without remount/refetch.
  useEffect(() => { setActiveTab(initialPhase); }, [initialPhase]);

  // ── Load the owner-spanning catalog once (OTA + SHARED, OTA-825). ──
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const rows = await getRulesAdmin();
        if (alive) setCatalog(rows || []);
      } catch (e) {
        if (alive) { setCatalogErr(e.message); setCatalog([]); }
      }
    })();
    return () => { alive = false; };
  }, []);

  // ── Load the strategy's current bindings (prefer draft) for dimming + order. ──
  const loadJunctions = useCallback(async () => {
    if (!strategyKey) return;
    try {
      let list;
      if (editable) {
        try { list = await getStrategyJunctions(draftKey); }   // 404 if no draft yet
        catch { list = await getStrategyJunctions(strategyKey); }
      } else {
        list = await getStrategyJunctions(strategyKey);
      }
      setJunctions(list || []);
    } catch {
      setJunctions([]);   // bindings are advisory here (dimming only) — never block browsing
    }
  }, [strategyKey, draftKey, editable]);

  useEffect(() => { loadJunctions(); }, [loadJunctions]);

  // Rules for the active phase tab.
  const phaseRules = useMemo(
    () => (catalog || []).filter(r => r.phase === activeTab),
    [catalog, activeTab],
  );

  // Rule keys already bound in the active phase → dim as "in active set".
  const boundKeys = useMemo(
    () => new Set(junctions.filter(j => j.phase === activeTab).map(j => j.rule_key)),
    [junctions, activeTab],
  );

  // ── Bind a rule (identical effect to the inline pickers it replaces). ──
  const bind = useCallback(async (rule) => {
    if (!editable || mutating) return;
    setMutating(true);
    try {
      await createOrResumeDraft(strategyKey);   // clones live header + junctions
      // Next evaluation_order within this rule's phase (draft-preferred junctions).
      const samePhase = junctions.filter(j => j.phase === rule.phase);
      const nextOrder = samePhase.length
        ? Math.max(...samePhase.map(j => Number(j.evaluation_order) || 0)) + 1
        : 1;
      const body = {
        strategy_key: draftKey,
        rule_key: rule.rule_key,
        evaluation_order: nextOrder,
        stop_if_fail: rule.phase === 'gate',   // gates halt by default; scoring/adjustments don't
        parameters: defaultsFromSchema(rule.parameter_schema),
        enabled: true,
      };
      if (rule.phase === 'scoring') body.weight = 0;   // starts at 0.00% — sum indicator flags until set
      await createJunction(body);
      await loadJunctions();   // refresh dimming
      onBound?.();             // open sections reload their rows
    } catch (e) {
      showToast({ type: 'error', message: `Add failed: ${e.message}` });
    } finally {
      setMutating(false);
    }
  }, [editable, mutating, strategyKey, draftKey, junctions, loadJunctions, onBound, showToast]);

  const boundCount = phaseRules.filter(r => boundKeys.has(r.rule_key)).length;

  return (
    <>
      <div
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 100 }}
      />
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 480, zIndex: 101,
        background: 'var(--bg, #0d1117)', borderLeft: '1px solid var(--border, #30363d)',
        display: 'flex', flexDirection: 'column', fontFamily: MONO,
      }}>
        {/* Header */}
        <div style={{
          padding: '18px 20px', borderBottom: '1px solid var(--border, #30363d)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text, #e6edf3)' }}>Rule Catalog</div>
            <div style={{ fontSize: 11, color: 'var(--muted, #8b949e)', marginTop: 2 }}>
              OTA + Shared · read-only reference
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{ background: 'transparent', border: 'none', color: 'var(--muted, #8b949e)', fontSize: 20, cursor: 'pointer' }}
          >×</button>
        </div>

        {/* Phase tabs — the only tabbed element on this surface */}
        <div style={{ display: 'flex', gap: 16, padding: '0 20px', borderBottom: '1px solid var(--border, #30363d)' }}>
          {TABS.map(t => {
            const on = t.key === activeTab;
            return (
              <div
                key={t.key}
                role="tab"
                aria-selected={on}
                onClick={() => setActiveTab(t.key)}
                style={{
                  padding: '10px 0', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.5px',
                  cursor: 'pointer',
                  color: on ? 'var(--teal, #2dd4bf)' : 'var(--muted, #8b949e)',
                  borderBottom: `2px solid ${on ? 'var(--teal, #2dd4bf)' : 'transparent'}`,
                }}
              >{t.label}</div>
            );
          })}
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <div style={{
            padding: '10px 20px', borderBottom: '1px solid var(--border, #30363d)',
            fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--muted, #8b949e)',
          }}>
            {catalog == null ? 'Loading…' : `${phaseRules.length} rules · ${boundCount} in active set`}
          </div>

          {catalog == null ? (
            <div style={{ padding: 20, fontSize: 11, color: 'var(--muted, #8b949e)' }}>Loading catalog…</div>
          ) : catalogErr ? (
            <div style={{ padding: 20, fontSize: 11, color: 'var(--red, #f87171)' }}>{catalogErr}</div>
          ) : phaseRules.length === 0 ? (
            <div style={{ padding: 20, fontSize: 11, color: 'var(--muted, #8b949e)' }}>
              No rules in this phase.
            </div>
          ) : phaseRules.map(rule => (
            <CatalogRule
              key={`${rule.owner_app_id}:${rule.rule_key}`}
              rule={rule}
              bound={boundKeys.has(rule.rule_key)}
              editable={editable}
              mutating={mutating}
              onBind={() => bind(rule)}
            />
          ))}
        </div>
      </div>
    </>
  );
}

// ─── One catalog rule card (five fields + owner badge + bind affordance) ─────

function CatalogRule({ rule, bound, editable, mutating, onBind }) {
  const shared = rule.owner_app_id !== OTA_OWNER;
  // Selectable for binding only when: strategy editable, rule enabled, not already
  // bound in this phase, and no bind in flight. SHARED rules ARE selectable.
  const selectable = editable && rule.enabled && !bound && !mutating;

  return (
    <div
      onClick={() => selectable && onBind()}
      style={{
        padding: '12px 20px', borderBottom: '1px solid var(--border, #30363d)',
        cursor: selectable ? 'pointer' : 'default',
        opacity: bound || !rule.enabled ? 0.45 : 1,
      }}
    >
      {/* Name + owner badge + state tags */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text, #e6edf3)' }}>
          {prettify(rule.rule_key)}
        </span>
        <OwnerBadge shared={shared} />
        {bound && (
          <span style={{ fontSize: 9, color: 'var(--muted, #8b949e)' }}>(in active set)</span>
        )}
        {!rule.enabled && (
          <span style={{ fontSize: 9, color: 'var(--muted, #8b949e)' }}>(disabled)</span>
        )}
      </div>

      {/* Field 1 — intent */}
      {rule.intent && (
        <div style={{ fontSize: 11, color: 'var(--muted, #8b949e)', marginTop: 4, lineHeight: 1.4 }}>
          {rule.intent}
        </div>
      )}

      {/* Fields 2–4 — inputs · expected output · phase */}
      <div style={{ fontSize: 10, color: 'var(--muted, #8b949e)', marginTop: 6, lineHeight: 1.5 }}>
        <span style={{ color: 'var(--text, #e6edf3)' }}>Inputs:</span> {inputsLabel(rule.referenced_named_values)}
        <span style={{ margin: '0 6px', opacity: 0.5 }}>·</span>
        <span style={{ color: 'var(--text, #e6edf3)' }}>Output:</span> {EXPECTED_OUTPUT[rule.phase] || rule.phase}
        <span style={{ margin: '0 6px', opacity: 0.5 }}>·</span>
        <span style={{ color: 'var(--text, #e6edf3)' }}>Phase:</span> {rule.phase}
      </div>

      {/* Field 5 — formula-registry status */}
      <div style={{ marginTop: 6 }}>
        <FormulaStatus registered={rule.formula_registered} />
      </div>
    </div>
  );
}

function OwnerBadge({ shared }) {
  return (
    <span style={{
      fontSize: 8, fontWeight: 700, fontFamily: MONO, padding: '2px 6px', borderRadius: 3,
      textTransform: 'uppercase', letterSpacing: '0.4px',
      color: shared ? 'var(--muted, #8b949e)' : 'var(--teal, #2dd4bf)',
      background: shared ? 'var(--bg3, #21262d)' : 'rgba(45,212,191,0.12)',
      border: `1px solid ${shared ? 'var(--border, #30363d)' : 'rgba(45,212,191,0.4)'}`,
    }}>
      {shared ? 'Shared · read-only' : 'OTA'}
    </span>
  );
}

// Tri-state (insight_engine.md §6.6 / OTA-825): registered ✓ / unregistered ✗ /
// n-a for a pure condition-expression rule with no formula_ref.
function FormulaStatus({ registered }) {
  if (registered === null || registered === undefined) {
    return (
      <span style={{ fontSize: 10, color: 'var(--muted, #8b949e)' }}>
        ○ No formula (condition rule)
      </span>
    );
  }
  return registered ? (
    <span style={{ fontSize: 10, color: 'var(--green, #4ade80)' }}>● Formula registered</span>
  ) : (
    <span style={{ fontSize: 10, color: 'var(--red, #f87171)' }}>● Formula not registered</span>
  );
}
