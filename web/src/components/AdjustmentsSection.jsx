/**
 * AdjustmentsSection — the Post-Scoring Adjustments tab body of the Strategy
 * Admin editor (OTA-787).
 *
 * Edits the `phase='adjustment'` junction rows of the selected strategy.
 * Adjustments evaluate after the raw score exists; each runs in evaluation_order
 * and adds / subtracts / floors / caps the score (clamped to [0,100]). Floor/cap
 * adjustments are ordinary adjustment rows — NO special-casing here. Renders each
 * bound adjustment (from the OTA-826 junction read) sorted by evaluation_order,
 * with editable threshold parameters and evaluation_order via the shared
 * JunctionRowEditor. Provides "Add adjustment from catalog" (opens the shared
 * RuleCatalogDrawer filtered to phase==='adjustment' — OTA-789; the drawer owns
 * the bind and bumps refreshSignal so this section reloads) and "Remove".
 *
 * Save-to-draft (OTA-781): live is never written here. First junction write
 * ensures `<key>__draft` exists (create-or-resume, cloning live header +
 * junctions), then all junction CRUD targets the draft key. Live is untouched
 * until Apply (OTA-790).
 *
 * Authority note (OTA-785 precedent, decision a): the duplicate evaluation_order
 * indicator is ADVISORY only. The save does NOT reject a colliding draft (the
 * save-path validator excludes drafts by design); the server-authoritative catch
 * is the PREVIEW path (load_config(include_draft_key) → EVAL_ORDER_DUPLICATE) and
 * Apply (OTA-790).
 *
 * Tokens: CSS var(--*) only. No inline hex, no `$`. Scores ##.00.
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
const ADJUSTMENT_PHASE = 'adjustment';

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

export default function AdjustmentsSection({ strategyKey, editable, onOpenCatalog, refreshSignal }) {
  const { showToast } = useToast();
  const draftKey = `${strategyKey}__draft`;

  const [rows, setRows]           = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [draftExists, setDraftExists] = useState(false);
  const [mutating, setMutating]   = useState(false);

  const rowsRef = useRef(rows);
  useEffect(() => { rowsRef.current = rows; }, [rows]);

  // ── Load adjustment bindings: prefer the draft, else live ──
  const load = useCallback(async () => {
    if (!strategyKey) return;
    setLoading(true);
    setError(null);
    try {
      let list;
      let hasDraft = false;
      if (editable) {
        try {
          list = await getStrategyJunctions(draftKey);
          hasDraft = true;
        } catch {
          list = await getStrategyJunctions(strategyKey);
        }
      } else {
        list = await getStrategyJunctions(strategyKey);
      }
      const adjustments = (list || [])
        .filter(j => j.phase === ADJUSTMENT_PHASE)
        .sort((a, b) => (a.evaluation_order ?? 0) - (b.evaluation_order ?? 0));
      setRows(adjustments);
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

  // ── Draft ensure (first write) ──
  const ensureDraft = useCallback(async () => {
    if (draftExists) return draftKey;
    await createOrResumeDraft(strategyKey);
    setDraftExists(true);
    return draftKey;
  }, [draftExists, draftKey, strategyKey]);

  // ── Persist one row to the draft ──
  const persistRow = useCallback(async (row) => {
    try {
      const dk = await ensureDraft();
      await updateJunction(dk, row.rule_key, {
        evaluation_order: row.evaluation_order === '' ? 0 : Number(row.evaluation_order),
        stop_if_fail: Boolean(row.stop_if_fail),   // preserved (adjustments don't halt)
        score_penalty: row.score_penalty,          // preserved
        weight: row.weight,                         // preserved
        parameters: row.parameters,
        terminal_verdict: row.terminal_verdict,
        rationale: row.rationale,
        enabled: Boolean(row.enabled),
      });
    } catch (e) {
      showToast({ type: 'error', message: `Save failed: ${e.message}` });
      load();
    }
  }, [ensureDraft, load, showToast]);

  const patchRow = useCallback((ruleKey, patch) => {
    setRows(rs => rs.map(r => (r.rule_key === ruleKey ? { ...r, ...patch } : r)));
  }, []);

  const commitRow = useCallback((ruleKey, patch) => {
    const base = rowsRef.current.find(r => r.rule_key === ruleKey);
    if (!base) return;
    const merged = { ...base, ...(patch || {}) };
    if (patch) setRows(rs => rs.map(r => (r.rule_key === ruleKey ? merged : r)));
    persistRow(merged);
  }, [persistRow]);

  const removeAdjustment = useCallback(async (row) => {
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

  // ── Advisory collision detection (enabled rows only — server parity) ──
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
          <div style={sectionTitleStyle}>Post-Scoring Adjustments · penalties & bonuses</div>
          {editable && draftExists && (
            <span style={{ fontSize: 9, color: 'var(--amber)', fontFamily: MONO }}>editing draft</span>
          )}
        </div>
        {editable && (
          <button onClick={() => onOpenCatalog?.(ADJUSTMENT_PHASE)} disabled={mutating}
            style={{ ...addBtnStyle, opacity: mutating ? 0.4 : 1, cursor: mutating ? 'default' : 'pointer' }}>
            + Add adjustment from catalog
          </button>
        )}
      </div>

      {/* Section body */}
      <div style={cardStyle}>
        {loading ? (
          <div style={{ fontSize: 11, color: 'var(--muted)' }}>Loading adjustments…</div>
        ) : error ? (
          <div style={{ fontSize: 11, color: 'var(--red)' }}>{error}</div>
        ) : rows.length === 0 ? (
          <div style={{ fontSize: 11, color: 'var(--muted)' }}>
            No adjustments bound to this strategy.{editable ? ' Add one from the catalog.' : ''}
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
                showParameters
                duplicateOrder={isDup(row)}
                busy={mutating}
                onChange={patch => patchRow(row.rule_key, patch)}
                onCommit={patch => commitRow(row.rule_key, patch)}
                onRemove={() => removeAdjustment(row)}
              />
            ))}
          </>
        )}
      </div>
    </div>
  );
}
