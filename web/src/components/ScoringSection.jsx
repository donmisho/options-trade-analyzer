/**
 * ScoringSection — the Scoring Weights tab body of the Strategy Admin editor (OTA-786).
 *
 * Edits the `phase='scoring'` junction rows of the selected strategy. Renders each
 * bound scoring criterion (from the OTA-826 junction read) with an editable
 * weight and threshold parameters via the shared JunctionRowEditor. Provides a
 * live sum-to-1.0 indicator, "Add scoring criterion from catalog" (opens the
 * shared RuleCatalogDrawer filtered to phase==='scoring' — OTA-789; the drawer
 * owns the bind and bumps refreshSignal so this section reloads), and "Remove".
 *
 * Weight units (OTA-786 decision): the weight is STORED as a fraction
 * (numeric(7,4)) that must sum to 1.0 server-side; it is DISPLAYED/EDITED as a
 * percent formatted ##.00 (e.g. 30.00 %, total 100.00%). JunctionRowEditor's
 * weightAsPercent handles the per-row conversion; this section rounds to 4dp on
 * write and totals the percent for the indicator.
 *
 * Save-to-draft (OTA-781): live is never written here. First junction write
 * ensures `<key>__draft` exists (create-or-resume, cloning live header +
 * junctions), then all junction CRUD targets the draft key. Live is untouched
 * until Apply (OTA-790).
 *
 * Authority note (OTA-785 precedent, decision a): the sum-to-1.0 indicator is
 * ADVISORY only — it is an editor-side pre-check. The save does NOT reject an
 * off-sum draft (the save-path validator excludes drafts by design). The
 * server-authoritative catch is the PREVIEW path (load_config(include_draft_key)
 * → SCORING_WEIGHTS_NOT_UNITY) and Apply (OTA-790). The server tolerance is 1e-4
 * on the fraction sum; the indicator flags when |pctSum − 100.00| > 0.01.
 *
 * Tokens: CSS var(--*) only. No inline hex, no `$`. Percent/weights ##.00.
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
const SCORING_PHASE = 'scoring';
const PCT_TOLERANCE = 0.01;   // advisory tolerance on the percent sum (server: 1e-4 on the fraction)

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

export default function ScoringSection({ strategyKey, editable, onOpenCatalog, refreshSignal }) {
  const { showToast } = useToast();
  const draftKey = `${strategyKey}__draft`;

  const [rows, setRows]           = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [draftExists, setDraftExists] = useState(false);
  const [mutating, setMutating]   = useState(false);

  const rowsRef = useRef(rows);
  useEffect(() => { rowsRef.current = rows; }, [rows]);

  // ── Load scoring bindings: prefer the draft, else live ──
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
      const scoring = (list || [])
        .filter(j => j.phase === SCORING_PHASE)
        .sort((a, b) => (a.evaluation_order ?? 0) - (b.evaluation_order ?? 0));
      setRows(scoring);
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

  // ── Persist one row to the draft (weight rounded to 4dp for numeric(7,4)) ──
  const persistRow = useCallback(async (row) => {
    try {
      const dk = await ensureDraft();
      const w = row.weight === '' || row.weight == null
        ? null
        : Math.round(Number(row.weight) * 10000) / 10000;
      await updateJunction(dk, row.rule_key, {
        evaluation_order: row.evaluation_order === '' ? 0 : Number(row.evaluation_order),
        stop_if_fail: Boolean(row.stop_if_fail),   // preserved (scoring rules don't halt)
        score_penalty: row.score_penalty,          // preserved
        weight: w,
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

  const removeCriterion = useCallback(async (row) => {
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

  // ── Live sum indicator (enabled scoring rows only — server parity) ──
  const enabledRows = rows.filter(r => r.enabled);
  const pctSum = enabledRows.reduce(
    (s, r) => s + (r.weight === '' || r.weight == null ? 0 : Number(r.weight) * 100),
    0,
  );
  const sumBad = enabledRows.length > 0 && Math.abs(pctSum - 100) > PCT_TOLERANCE;

  return (
    <div style={{ marginTop: 24 }}>
      <div style={{
        position: 'relative',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <div style={sectionTitleStyle}>Scoring Weights</div>
          {editable && draftExists && (
            <span style={{ fontSize: 9, color: 'var(--amber)', fontFamily: MONO }}>editing draft</span>
          )}
        </div>
        {editable && (
          <button onClick={() => onOpenCatalog?.(SCORING_PHASE)} disabled={mutating}
            style={{ ...addBtnStyle, opacity: mutating ? 0.4 : 1, cursor: mutating ? 'default' : 'pointer' }}>
            + Add scoring criterion from catalog
          </button>
        )}
      </div>

      {/* Section body */}
      <div style={cardStyle}>
        {loading ? (
          <div style={{ fontSize: 11, color: 'var(--muted)' }}>Loading scoring criteria…</div>
        ) : error ? (
          <div style={{ fontSize: 11, color: 'var(--red)' }}>{error}</div>
        ) : rows.length === 0 ? (
          <div style={{ fontSize: 11, color: 'var(--muted)' }}>
            No scoring criteria bound to this strategy.{editable ? ' Add one from the catalog.' : ''}
          </div>
        ) : (
          <>
            {rows.map(row => (
              <JunctionRowEditor
                key={row.junction_id ?? row.rule_key}
                junction={row}
                editable={editable}
                showEvaluationOrder={false}
                showWeight
                weightAsPercent
                showParameters
                busy={mutating}
                onChange={patch => patchRow(row.rule_key, patch)}
                onCommit={patch => commitRow(row.rule_key, patch)}
                onRemove={() => removeCriterion(row)}
              />
            ))}

            {/* Live sum-to-1.0 indicator (advisory) */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8, marginTop: 12,
              paddingTop: 12, borderTop: '1px solid var(--border)', fontSize: 12,
            }}>
              <span style={{ color: 'var(--muted)' }}>Total:</span>
              <span style={{ fontWeight: 700, color: sumBad ? 'var(--red)' : 'var(--green)' }}>
                {pctSum.toFixed(2)}%
              </span>
              <span style={{ fontSize: 10, color: 'var(--muted)', marginLeft: 4 }}>
                (must equal 100.00%)
              </span>
              {sumBad && (
                <span style={{ fontSize: 10, color: 'var(--amber)', marginLeft: 8 }}>
                  ● Advisory — the save still succeeds, but the off-sum blocks preview and
                  Apply (OTA-790) until weights total 100.00%.
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
