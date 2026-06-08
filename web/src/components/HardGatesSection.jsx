/**
 * HardGatesSection — the Hard Gates tab body of the Strategy Admin editor (OTA-785).
 *
 * Edits the `phase='gate'` junction rows of the selected strategy. Renders each
 * bound gate (from the OTA-826 junction read) sorted by evaluation_order, with
 * editable threshold parameters, a stop_if_fail toggle, and an editable
 * evaluation_order — all via the shared JunctionRowEditor. Provides:
 *   - "Add hard gate from catalog": opens the shared RuleCatalogDrawer (OTA-789)
 *     filtered to phase==='gate'. The drawer is the single rule-catalog source
 *     and owns the bind; on bind it bumps the page's refreshSignal so this
 *     section reloads. (Pre-OTA-789 this section rendered its own inline picker.)
 *   - "Remove": deletes only the junction row (the rule is untouched).
 *   - A client-side advisory collision indicator for duplicate evaluation_order
 *     within the gate phase (enabled bindings only, matching the server check).
 *
 * Save-to-draft (OTA-781): the live strategy is never written here. On the first
 * junction write we ensure `<key>__draft` exists (create-or-resume, which clones
 * the live header + junctions), then route every junction CRUD against the draft
 * key. Live is untouched until Apply (OTA-790).
 *
 * Authority note: the client collision indicator is ADVISORY only. The
 * server-authoritative catch for a draft collision is the PREVIEW path
 * (load_config(include_draft_key) → EVAL_ORDER_DUPLICATE); promote-time blocking
 * is Apply (OTA-790). The section *save* does NOT reject a colliding draft write
 * — the save-path validator excludes drafts by design (a colliding draft may
 * persist but cannot be promoted). See OTA-785 Phase 0 finding #2.
 *
 * Tokens: CSS var(--*) only. No inline hex, no `$`.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import JunctionRowEditor from './JunctionRowEditor';
import {
  getStrategyJunctions,
  updateJunction,
  deleteJunction,
  createOrResumeDraft,
} from '../api/client';
import { useToast } from './Toast';

const MONO = "'JetBrains Mono', monospace";
const GATE_PHASE = 'gate';

const sectionTitleStyle = {
  fontSize: 11, textTransform: 'uppercase', letterSpacing: '1px',
  color: 'var(--muted)', fontFamily: MONO,
};
const cardStyle = {
  border: '1px solid var(--border)', borderRadius: 6, padding: 16, fontFamily: MONO,
};
const addBtnStyle = {
  background: 'transparent', border: '1px dashed var(--border)', color: 'var(--muted)',
  padding: '7px 14px', borderRadius: 4, fontSize: 11, fontFamily: MONO, cursor: 'pointer',
};

export default function HardGatesSection({ strategyKey, editable, onOpenCatalog, refreshSignal }) {
  const { showToast } = useToast();
  const draftKey = `${strategyKey}__draft`;

  const [rows, setRows]           = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [draftExists, setDraftExists] = useState(false);
  const [mutating, setMutating]   = useState(false);

  // Keep a ref to the latest rows so blur-commit reads current values without
  // threading them through every handler.
  const rowsRef = useRef(rows);
  useEffect(() => { rowsRef.current = rows; }, [rows]);

  // ── Load gate bindings: prefer the draft (in-progress edits), else live ──
  const load = useCallback(async () => {
    if (!strategyKey) return;
    setLoading(true);
    setError(null);
    try {
      let list;
      let hasDraft = false;
      if (editable) {
        try {
          list = await getStrategyJunctions(draftKey);  // 404 if no draft yet
          hasDraft = true;
        } catch {
          list = await getStrategyJunctions(strategyKey);
        }
      } else {
        list = await getStrategyJunctions(strategyKey);
      }
      const gates = (list || [])
        .filter(j => j.phase === GATE_PHASE)
        .sort((a, b) => (a.evaluation_order ?? 0) - (b.evaluation_order ?? 0));
      setRows(gates);
      setDraftExists(hasDraft);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [strategyKey, draftKey, editable]);

  // Reload on strategy/editable change and after a shared-drawer bind (OTA-789).
  useEffect(() => {
    load();
  }, [load, refreshSignal]);

  // ── Draft ensure (first write) ──────────────────────────────────────────
  const ensureDraft = useCallback(async () => {
    if (draftExists) return draftKey;
    await createOrResumeDraft(strategyKey);   // clones live header + junctions
    setDraftExists(true);
    return draftKey;
  }, [draftExists, draftKey, strategyKey]);

  // ── Persist one row's full state to the draft (OTA-782 CRUD) ─────────────
  const persistRow = useCallback(async (row) => {
    try {
      const dk = await ensureDraft();
      await updateJunction(dk, row.rule_key, {
        evaluation_order: row.evaluation_order === '' ? 0 : Number(row.evaluation_order),
        stop_if_fail: Boolean(row.stop_if_fail),
        score_penalty: row.score_penalty,    // preserved (not edited on this tab)
        weight: row.weight,                  // preserved
        parameters: row.parameters,
        terminal_verdict: row.terminal_verdict,
        rationale: row.rationale,
        enabled: Boolean(row.enabled),
      });
    } catch (e) {
      showToast({ type: 'error', message: `Save failed: ${e.message}` });
      load();   // resync from the server on failure
    }
  }, [ensureDraft, load, showToast]);

  // Local (no-network) update — per keystroke.
  const patchRow = useCallback((ruleKey, patch) => {
    setRows(rs => rs.map(r => (r.rule_key === ruleKey ? { ...r, ...patch } : r)));
  }, []);

  // Persist — on blur (no patch) or toggle (explicit patch).
  const commitRow = useCallback((ruleKey, patch) => {
    const base = rowsRef.current.find(r => r.rule_key === ruleKey);
    if (!base) return;
    const merged = { ...base, ...(patch || {}) };
    if (patch) setRows(rs => rs.map(r => (r.rule_key === ruleKey ? merged : r)));
    persistRow(merged);
  }, [persistRow]);

  // ── Remove a gate (deletes the binding only) ────────────────────────────
  const removeGate = useCallback(async (row) => {
    setMutating(true);
    try {
      const dk = await ensureDraft();
      await deleteJunction(dk, row.rule_key);
      await load();
    } catch (e) {
      showToast({ type: 'error', message: `Remove failed: ${e.message}` });
    } finally {
      setMutating(false);
    }
  }, [ensureDraft, load, showToast]);

  // ── Advisory collision detection (enabled gate rows only — server parity) ──
  const orderCounts = {};
  rows.forEach(r => {
    if (!r.enabled) return;
    const k = String(r.evaluation_order);
    orderCounts[k] = (orderCounts[k] || 0) + 1;
  });
  const isDup = r => r.enabled && orderCounts[String(r.evaluation_order)] > 1;
  const hasCollision = rows.some(isDup);

  return (
    <div style={{ marginTop: 24 }}>
      <div style={{
        position: 'relative',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <div style={sectionTitleStyle}>Additional Hard Gates · beyond core parameters</div>
          {editable && draftExists && (
            <span style={{ fontSize: 9, color: 'var(--amber)', fontFamily: MONO }}>editing draft</span>
          )}
        </div>
        {editable && (
          <button onClick={() => onOpenCatalog?.(GATE_PHASE)} disabled={mutating}
            style={{ ...addBtnStyle, opacity: mutating ? 0.4 : 1, cursor: mutating ? 'default' : 'pointer' }}>
            + Add hard gate from catalog
          </button>
        )}
      </div>

      {/* Section body */}
      <div style={cardStyle}>
        {loading ? (
          <div style={{ fontSize: 11, color: 'var(--muted)' }}>Loading gates…</div>
        ) : error ? (
          <div style={{ fontSize: 11, color: 'var(--red)' }}>{error}</div>
        ) : rows.length === 0 ? (
          <div style={{ fontSize: 11, color: 'var(--muted)' }}>
            No hard gates bound to this strategy.{editable ? ' Add one from the catalog.' : ''}
          </div>
        ) : (
          <>
            {hasCollision && (
              <div style={{
                fontSize: 11, color: 'var(--amber)', marginBottom: 10,
                border: '1px solid var(--amber)', borderRadius: 4, padding: '6px 10px',
              }}>
                ● Duplicate evaluation order detected. This is advisory — the save still
                succeeds, but the collision blocks preview and Apply (OTA-790) until resolved.
              </div>
            )}
            {rows.map(row => (
              <JunctionRowEditor
                key={row.junction_id ?? row.rule_key}
                junction={row}
                editable={editable}
                showEvaluationOrder
                showStopIfFail
                showParameters
                duplicateOrder={isDup(row)}
                busy={mutating}
                onChange={patch => patchRow(row.rule_key, patch)}
                onCommit={patch => commitRow(row.rule_key, patch)}
                onRemove={() => removeGate(row)}
              />
            ))}
          </>
        )}
      </div>
    </div>
  );
}
