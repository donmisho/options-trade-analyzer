/**
 * VerdictBandsSection — the Verdict Bands editor of the Strategy Admin editor (OTA-788).
 *
 * Edits the selected strategy's `verdict_band_set` (engine_strategies JSON column,
 * NOT junction rows). A band set is a per-strategy monotonic mapping from final
 * adjusted score → categorical verdict; the engine treats the labels as opaque
 * strings (screening: EXECUTE/WAIT/PASS; health: A/B/C/D/F — by consumer_surface).
 * Each band is { verdict, min_score, max_score }.
 *
 * Write path: the whole band set is saved via the strategy PUT (updateEngineStrategy,
 * OTA-782) against the DRAFT key. On first save we ensure `<key>__draft` exists
 * (create-or-resume), then PUT the full draft row with the edited verdict_band_set
 * and status='draft' preserved (server maps draft → enabled=0, so the draft never
 * enters the running config). Live is untouched until Apply (OTA-790).
 *
 * Monotonicity (OTA-788 decision, OTA-785/786 precedent): the non-monotonic
 * indicator is ADVISORY only — Save is never disabled. The server check
 * (validation.py::_check_verdict_bands_monotonic, min_score strictly descending)
 * excludes drafts at save by design, so the authoritative backstop is the PREVIEW
 * path (load_config include_draft_key) and Apply (OTA-790).
 *
 * No hardcoded band thresholds: every threshold comes from / writes to the data;
 * colors come from CSS var(--*) tokens only. (The legacy /evaluate/structured
 * literals in evaluation_routes.py::_assign_verdict are a separate, pre-existing
 * concern tracked outside this story — see OTA-788 Phase 0 finding #3.)
 *
 * Tokens: CSS var(--*) only. No inline hex, no `$`. Scores ##.00.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  getAdminStrategies,
  updateEngineStrategy,
  createOrResumeDraft,
} from '../api/client';
import { useToast } from './Toast';

const MONO = "'JetBrains Mono', monospace";

// Verdict label → display color (tokens only). Covers both vocabularies:
// screening (EXECUTE/STRONG/WAIT/CAUTION/PASS) and health grades (A/B/C/D/F).
// Unmapped labels fall back to neutral text — labels are opaque to the engine.
const VERDICT_COLOR = {
  EXECUTE: 'var(--green)', STRONG: 'var(--teal)', WAIT: 'var(--amber)',
  CAUTION: 'var(--orange)', PASS: 'var(--red)',
  A: 'var(--green)', B: 'var(--teal)', C: 'var(--yellow)', D: 'var(--orange)', F: 'var(--red)',
};
const verdictColor = v => VERDICT_COLOR[String(v || '').toUpperCase()] || 'var(--text)';

const sectionTitleStyle = {
  fontSize: 11, textTransform: 'uppercase', letterSpacing: '1px',
  color: 'var(--muted)', fontFamily: MONO,
};
const inputStyle = {
  background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text)',
  padding: '3px 6px', borderRadius: 3, fontSize: 11, fontFamily: MONO, width: 64, textAlign: 'right',
};
const tealBtn = {
  background: 'rgba(45,212,191,0.1)', border: '1px solid rgba(45,212,191,0.4)',
  color: 'var(--teal)', padding: '7px 16px', borderRadius: 4,
  fontSize: 11, fontFamily: MONO, cursor: 'pointer',
};

const num = v => (v === '' || v == null ? '' : Number(v));
const fmt = v => (v === '' || v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(2));

export default function VerdictBandsSection({ strategyKey, editable, liveBands }) {
  const { showToast } = useToast();
  const draftKey = `${strategyKey}__draft`;

  const [bands, setBands]         = useState(Array.isArray(liveBands) ? liveBands : []);
  const [loaded, setLoaded]       = useState(Array.isArray(liveBands) ? liveBands : []);
  const [draftExists, setDraftExists] = useState(false);
  const [saving, setSaving]       = useState(false);

  // ── Load bands: prefer the draft's set, else live ──
  const load = useCallback(async () => {
    if (!strategyKey) return;
    try {
      const all = await getAdminStrategies();
      const draftRow = all.find(r => r.strategy_key === draftKey);
      const liveRow = all.find(r => r.strategy_key === strategyKey);
      const src = (editable && draftRow) ? draftRow : liveRow;
      const set = Array.isArray(src?.verdict_band_set) ? src.verdict_band_set : [];
      setBands(set);
      setLoaded(set);
      setDraftExists(Boolean(draftRow));
    } catch (e) {
      showToast({ type: 'error', message: `Could not load verdict bands: ${e.message}` });
    }
  }, [strategyKey, draftKey, editable, showToast]);

  useEffect(() => { load(); }, [load]);

  const dirty = useMemo(
    () => JSON.stringify(bands) !== JSON.stringify(loaded),
    [bands, loaded],
  );

  // ── Advisory monotonicity: min_score must be strictly descending down the set ──
  // (mirrors validation.py::_check_verdict_bands_monotonic). Advisory only.
  const violations = useMemo(() => {
    const bad = new Set();
    let prevMin = null;
    bands.forEach((b, i) => {
      const min = num(b.min_score);
      if (min === '' || Number.isNaN(min)) return;
      if (prevMin != null && min >= prevMin) bad.add(i);
      prevMin = min;
    });
    return bad;
  }, [bands]);
  const nonMonotonic = violations.size > 0;

  const setBand = (i, patch) =>
    setBands(bs => bs.map((b, idx) => (idx === i ? { ...b, ...patch } : b)));

  // ── Save the whole set to the draft (ensure-draft → full-row strategy PUT) ──
  const handleSave = async () => {
    if (!editable || !dirty) return;
    setSaving(true);
    try {
      if (!draftExists) await createOrResumeDraft(strategyKey);
      // Re-read the draft row to build a full-row PUT body (status='draft' preserved
      // so the draft stays enabled=0 and out of the running config).
      const all = await getAdminStrategies();
      const dr = all.find(r => r.strategy_key === draftKey);
      if (!dr) throw new Error('Draft row not found after ensure');
      await updateEngineStrategy(draftKey, {
        display_name: dr.display_name,
        consumer_surface: dr.consumer_surface,
        description: dr.description ?? null,
        compatible_structures: dr.compatible_structures,
        verdict_band_set: bands,
        dte_min: dr.dte_min,
        dte_max: dr.dte_max,
        status: dr.status,   // 'draft' — preserved (server derives enabled=0)
      });
      showToast({ type: 'success', message: 'Verdict bands saved to draft' });
      setDraftExists(true);
      await load();
    } catch (e) {
      showToast({ type: 'error', message: `Save failed: ${e.message}` });
    } finally {
      setSaving(false);
    }
  };

  const cols = Math.min(Math.max(bands.length, 1), 5);

  return (
    <div style={{ marginTop: 24 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <div style={sectionTitleStyle}>Verdict Bands · final score → grade</div>
          {editable && draftExists && (
            <span style={{ fontSize: 9, color: 'var(--amber)', fontFamily: MONO }}>editing draft</span>
          )}
        </div>
        {editable && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {dirty && (
              <span style={{ fontSize: 11, color: 'var(--amber)', fontFamily: MONO }}>● Unsaved changes</span>
            )}
            <button
              onClick={handleSave}
              disabled={!dirty || saving}
              style={{ ...tealBtn, opacity: (!dirty || saving) ? 0.35 : 1, cursor: (!dirty || saving) ? 'default' : 'pointer' }}
            >
              {saving ? 'Saving…' : 'Save bands'}
            </button>
          </div>
        )}
      </div>

      {/* Advisory non-monotonic flag — Save is NOT disabled (OTA-785/786 precedent) */}
      {editable && nonMonotonic && (
        <div style={{
          fontSize: 11, color: 'var(--amber)', marginBottom: 10, fontFamily: MONO,
          border: '1px solid var(--amber)', borderRadius: 4, padding: '6px 10px',
        }}>
          ● Non-monotonic band set — min score must strictly decrease down the list. Advisory
          only; the save still succeeds, but preview and Apply (OTA-790) reject a non-monotonic
          set until corrected.
        </div>
      )}

      <div style={{
        border: '1px solid var(--border)', borderRadius: 6, padding: 16,
        display: bands.length ? 'grid' : 'block',
        gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 8, fontFamily: MONO,
      }}>
        {bands.length === 0 ? (
          <div style={{ fontSize: 11, color: 'var(--muted)' }}>No verdict bands configured.</div>
        ) : bands.map((b, i) => {
          const flagged = violations.has(i);
          return (
            <div key={i} style={{
              border: `1px solid ${flagged ? 'var(--amber)' : 'var(--border)'}`,
              borderRadius: 4, padding: '10px 12px',
            }}>
              {/* Verdict label */}
              {editable ? (
                <input
                  value={b.verdict ?? ''}
                  onChange={e => setBand(i, { verdict: e.target.value })}
                  aria-label={`Band ${i + 1} verdict`}
                  style={{
                    ...inputStyle, width: '100%', textAlign: 'left', fontSize: 14, fontWeight: 600,
                    color: verdictColor(b.verdict), marginBottom: 8,
                  }}
                />
              ) : (
                <div style={{ fontSize: 16, fontWeight: 600, color: verdictColor(b.verdict), marginBottom: 6 }}>
                  {b.verdict}
                </div>
              )}

              {/* min – max */}
              {editable ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <input
                    type="number" step="0.01" value={b.min_score ?? ''}
                    onChange={e => setBand(i, { min_score: e.target.value === '' ? '' : Number(e.target.value) })}
                    aria-label={`Band ${i + 1} min score`}
                    style={inputStyle}
                  />
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>–</span>
                  <input
                    type="number" step="0.01" value={b.max_score ?? ''}
                    onChange={e => setBand(i, { max_score: e.target.value === '' ? '' : Number(e.target.value) })}
                    aria-label={`Band ${i + 1} max score`}
                    style={inputStyle}
                  />
                </div>
              ) : (
                <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                  {fmt(b.min_score)} – {fmt(b.max_score)}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {!editable && (
        <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 6, fontFamily: MONO }}>
          Shared strategy — read-only
        </div>
      )}
    </div>
  );
}
