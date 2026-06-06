/**
 * StrategyAdminPage — Strategy editor shell + selector (OTA-784).
 *
 * Route: /strategy-admin (rendered inside the Layout shell — rail + main).
 *
 * This is the CONTAINER story. It stands up:
 *   - the strategy selector, sourced from GET /config/strategies/admin (OTA-823):
 *     OTA-owned strategies are editable; SHARED strategies are read-only.
 *   - the per-strategy header (key, label, status, enabled structures, DTE range),
 *     whose edits persist through the CRUD PUT (OTA-782) and are validated at
 *     save time (OTA-783).
 *   - the stacked config sections per strategy-rules-prototype-v2.html
 *     (Parameters / Scoring Weights / Hard Gates / Adjustments) + a Verdict Bands
 *     panel. The section BODIES are their own stories (OTA-785/786/787/788); here
 *     they are scaffolding/mount points.
 *   - the rule-catalog drawer, which keeps its own internal tabs (the only tabbed
 *     element on this surface — the body is stacked sections, not three tabs).
 *
 * Layout contract: the v2 prototype. Tokens: CSS var(--*) per UI-GUIDANCE Part 3
 * (NOT the legacy tokens.js C palette). Scores ##.00.
 */

import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  getAdminStrategies,
  updateEngineStrategy,
  createOrResumeDraft,
  refreshDraftFromLive,
  previewDraft,
} from '../api/client';
import { useToast } from '../components/Toast';
import { formatDate } from '../utils/formatDate';
import HardGatesSection from '../components/HardGatesSection';
import ScoringSection from '../components/ScoringSection';
import './PageShared.css';

// ─── Domain constants ───────────────────────────────────────────────────────

const OTA_OWNER = 'OTA';

// User-pickable lifecycle values (OTA-822 column / OTA-525 vocabulary). `draft`
// is reserved for the OTA-791 preview mechanism and is intentionally NOT offered.
const STATUS_OPTIONS = ['active', 'inactive', 'deprecated'];

// Canonical trade-structure enum values (match strategy-configs/*.config.js).
const AVAILABLE_STRUCTURES = [
  'bull_put_credit',
  'bear_call_credit',
  'bull_call_debit',
  'bear_put_debit',
  'long_call',
  'long_put',
];

// Stacked config sections — bodies are their own stories; this shell mounts them.
// Story tags corrected per OTA-785 Phase 0 finding #4 (the OTA-784 shell shipped
// with the tags shifted by one slot): Parameters=OTA-827, Scoring=OTA-786,
// Hard Gates=OTA-785 (built here), Adjustments=OTA-787.
const SECTIONS = [
  { key: 'parameters', title: 'Parameters', story: 'OTA-827', catalog: null },
  { key: 'scoring',    title: 'Scoring Weights', story: 'OTA-786', catalog: 'scoring' },
  { key: 'gates',      title: 'Additional Hard Gates · beyond core parameters', story: 'OTA-785', catalog: 'gates', addLabel: '+ Add hard gate from catalog' },
  { key: 'adjustments', title: 'Post-Scoring Adjustments · penalties & bonuses', story: 'OTA-787', catalog: 'adjustments', addLabel: '+ Add adjustment from catalog' },
];

const DRAWER_TABS = [
  { key: 'gates', label: 'Hard Gates' },
  { key: 'scoring', label: 'Scoring' },
  { key: 'adjustments', label: 'Adjustments' },
];

// ─── Helpers ────────────────────────────────────────────────────────────────

/** snake_case enum → Title Case display ('bull_put_credit' → 'Bull Put Credit'). */
function titleCase(s) {
  return String(s)
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

/** Title Case a single lifecycle word for display ('active' → 'Active'). */
function cap(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

/** Build the editable form state from an admin row. */
function toForm(row) {
  return {
    display_name: row.display_name ?? '',
    status: STATUS_OPTIONS.includes(row.status) ? row.status : 'active',
    structures: Array.isArray(row.compatible_structures) ? [...row.compatible_structures] : [],
    dte_min: row.dte_min ?? '',
    dte_max: row.dte_max ?? '',
  };
}

// ─── Inline style atoms (var(--*) tokens, UI-GUIDANCE Part 3) ───────────────

const MONO = "'JetBrains Mono', monospace";

const labelStyle = {
  fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.5px',
  color: 'var(--muted, #8b949e)', marginBottom: 6, fontFamily: MONO,
};
const inputStyle = {
  background: 'var(--bg, #0d1117)',
  border: '1px solid var(--border, #30363d)',
  color: 'var(--text, #e6edf3)',
  padding: '4px 8px', borderRadius: 3, fontSize: 12, fontFamily: MONO,
};
const sectionTitleStyle = {
  fontSize: 11, textTransform: 'uppercase', letterSpacing: '1px',
  color: 'var(--muted, #8b949e)', fontFamily: MONO,
};
const tealBtn = {
  background: 'rgba(45,212,191,0.1)', border: '1px solid rgba(45,212,191,0.4)',
  color: 'var(--teal, #2dd4bf)', padding: '7px 16px', borderRadius: 4,
  fontSize: 11, fontFamily: MONO, cursor: 'pointer',
};
const mutedBtn = {
  background: 'transparent', border: '1px solid var(--border, #30363d)',
  color: 'var(--muted, #8b949e)', padding: '7px 14px', borderRadius: 4,
  fontSize: 11, fontFamily: MONO, cursor: 'pointer',
};

// ─── Main component ──────────────────────────────────────────────────────────

export default function StrategyAdminPage() {
  const { showToast } = useToast();

  const [strategies, setStrategies] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);

  const [selectedKey, setSelectedKey] = useState(null);
  const [form, setForm]               = useState(null);   // editable header state
  const [saving, setSaving]           = useState(false);

  const [drawerTab, setDrawerTab]     = useState(null);   // null = closed
  const structMenuRef                 = useRef(null);
  const [structMenuOpen, setStructMenuOpen] = useState(false);

  // ── Live preview (OTA-791): evaluate the draft against a symbol's chain ──
  const [previewSymbol, setPreviewSymbol]   = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewResults, setPreviewResults] = useState(null);  // null = not run
  const [previewMeta, setPreviewMeta]       = useState(null);
  const [previewError, setPreviewError]     = useState(null);
  const [draftBusy, setDraftBusy]           = useState(false);

  // ── Load the admin strategy list ──────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await getAdminStrategies();
      setStrategies(rows || []);
      // Default selection: first OTA-editable strategy, else first row.
      setSelectedKey(prev => {
        if (prev && rows?.some(r => r.strategy_key === prev)) return prev;
        const firstEditable = rows?.find(r => r.owner_app_id === OTA_OWNER);
        return (firstEditable ?? rows?.[0])?.strategy_key ?? null;
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // The currently selected row + whether it is editable.
  const selected = useMemo(
    () => strategies.find(r => r.strategy_key === selectedKey) ?? null,
    [strategies, selectedKey],
  );
  const editable = selected?.owner_app_id === OTA_OWNER;

  // Reset the editable form + preview whenever the selection changes.
  useEffect(() => {
    setForm(selected ? toForm(selected) : null);
    setStructMenuOpen(false);
    setPreviewResults(null);
    setPreviewMeta(null);
    setPreviewError(null);
  }, [selected]);

  // Dirty check — does the form differ from the persisted row?
  const dirty = useMemo(() => {
    if (!selected || !form) return false;
    const base = toForm(selected);
    return (
      base.display_name !== form.display_name ||
      base.status !== form.status ||
      String(base.dte_min) !== String(form.dte_min) ||
      String(base.dte_max) !== String(form.dte_max) ||
      base.structures.join(',') !== form.structures.join(',')
    );
  }, [selected, form]);

  // Grouped selector lists.
  const otaStrategies    = strategies.filter(r => r.owner_app_id === OTA_OWNER);
  const sharedStrategies = strategies.filter(r => r.owner_app_id !== OTA_OWNER);

  // ── Header field mutators ───────────────────────────────────────────────────
  const setField = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const removeStructure = (s) =>
    setForm(f => ({ ...f, structures: f.structures.filter(x => x !== s) }));

  const addStructure = (s) => {
    setForm(f => (f.structures.includes(s) ? f : { ...f, structures: [...f.structures, s] }));
    setStructMenuOpen(false);
  };

  // ── Save (PUT — full-row replace, OTA-782/783) ──────────────────────────────
  const handleSave = async () => {
    if (!selected || !editable || !form) return;
    const dteMin = form.dte_min === '' ? null : Number(form.dte_min);
    const dteMax = form.dte_max === '' ? null : Number(form.dte_max);
    if (dteMin != null && dteMax != null && dteMin > dteMax) {
      showToast({ type: 'error', message: 'DTE min cannot exceed DTE max' });
      return;
    }
    // Full-row body: editable fields + every persisted field that is not edited
    // here (description, consumer_surface, verdict_band_set) so the replace does
    // not null them. `enabled` is derived from `status` server-side — never sent.
    const body = {
      display_name: form.display_name,
      consumer_surface: selected.consumer_surface,
      description: selected.description ?? null,
      compatible_structures: form.structures,
      verdict_band_set: selected.verdict_band_set,
      dte_min: dteMin,
      dte_max: dteMax,
      status: form.status,
    };
    setSaving(true);
    try {
      await updateEngineStrategy(selected.strategy_key, body);
      showToast({ type: 'success', message: `Saved ${form.display_name}` });
      await load();   // re-read persisted state (write is not restart-gated)
    } catch (err) {
      showToast({ type: 'error', message: `Save failed: ${err.message}` });
    } finally {
      setSaving(false);
    }
  };

  // ── Live preview handlers (OTA-791) ─────────────────────────────────────────
  // "Find trades →": ensure a draft exists (create-or-resume), then evaluate it
  // against the symbol's chain. The draft is the write target for editing; until
  // the section editors (OTA-785–788) land it mirrors live, so preview reflects
  // the live config until edits are applied to the draft.
  const handleFindTrades = async () => {
    const sym = previewSymbol.trim().toUpperCase();
    if (!selected || !editable || !sym) return;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      await createOrResumeDraft(selected.strategy_key);
      const resp = await previewDraft(selected.strategy_key, sym);
      setPreviewResults(resp.results || []);
      setPreviewMeta({
        underlying_price: resp.underlying_price,
        candidates_evaluated: resp.candidates_evaluated,
        config_version: resp.config_version,
      });
    } catch (err) {
      setPreviewError(err.message);
      setPreviewResults(null);
      setPreviewMeta(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  // "Refresh from live": discard the draft and re-clone from the live strategy
  // (OTA-790 Reset reuses this). Clears any stale preview.
  const handleRefreshFromLive = async () => {
    if (!selected || !editable) return;
    setDraftBusy(true);
    try {
      await refreshDraftFromLive(selected.strategy_key);
      showToast({ type: 'success', message: 'Draft reset to live config' });
      setPreviewResults(null);
      setPreviewMeta(null);
      setPreviewError(null);
    } catch (err) {
      showToast({ type: 'error', message: `Refresh failed: ${err.message}` });
    } finally {
      setDraftBusy(false);
    }
  };

  // ── Render: loading / error ─────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="page-card" style={{ fontFamily: MONO, color: 'var(--muted)', fontSize: 12 }}>
        Loading strategies…
      </div>
    );
  }
  if (error) {
    return (
      <div className="page-card" style={{ fontFamily: MONO, color: 'var(--red)', fontSize: 12 }}>
        Could not load strategies: {error}
      </div>
    );
  }

  return (
    <div className="page-card" style={{ fontFamily: MONO }}>
      <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>

        {/* ═══════════════ Selector ═══════════════ */}
        <Selector
          ota={otaStrategies}
          shared={sharedStrategies}
          selectedKey={selectedKey}
          onSelect={setSelectedKey}
        />

        {/* ═══════════════ Editor ═══════════════ */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {!selected ? (
            <div style={{ color: 'var(--muted)', fontSize: 12, padding: '20px 0' }}>
              No strategy selected.
            </div>
          ) : (
            <>
              {/* ── Header card ── */}
              <div style={{
                border: '1px solid var(--border, #30363d)', borderRadius: 6,
                padding: '18px 22px', marginBottom: 20,
              }}>
                {/* Title row: label (editable) + owner badge */}
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    {editable ? (
                      <input
                        value={form?.display_name ?? ''}
                        onChange={e => setField('display_name', e.target.value)}
                        aria-label="Display name"
                        style={{
                          ...inputStyle, fontSize: 18, fontWeight: 600,
                          width: '100%', maxWidth: 420,
                          background: 'transparent', border: '1px solid transparent',
                          padding: '2px 4px', color: 'var(--text, #e6edf3)',
                        }}
                        onFocus={e => { e.target.style.border = '1px solid var(--border, #30363d)'; e.target.style.background = 'var(--bg, #0d1117)'; }}
                        onBlur={e => { e.target.style.border = '1px solid transparent'; e.target.style.background = 'transparent'; }}
                      />
                    ) : (
                      <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--text, #e6edf3)' }}>
                        {selected.display_name}
                      </div>
                    )}
                    {/* strategy_key — immutable natural key */}
                    <div style={{ fontSize: 10, color: 'var(--muted, #8b949e)', marginTop: 4 }}>
                      {selected.strategy_key} · {selected.consumer_surface}
                    </div>
                    {/* description — preserved on save, shown read-only (per mockup subtitle) */}
                    {selected.description && (
                      <div style={{ fontSize: 12, color: 'var(--muted, #8b949e)', marginTop: 6 }}>
                        {selected.description}
                      </div>
                    )}
                  </div>
                  <OwnerBadge owner={selected.owner_app_id} editable={editable} />
                </div>

                {/* Meta grid: Status · Structures · DTE range */}
                <div style={{
                  display: 'grid', gridTemplateColumns: 'max-content max-content 1fr',
                  gap: 28, alignItems: 'start', marginTop: 18,
                }}>
                  {/* Status */}
                  <div>
                    <div style={labelStyle}>Status</div>
                    {editable ? (
                      <select
                        value={form?.status ?? 'active'}
                        onChange={e => setField('status', e.target.value)}
                        style={{ ...inputStyle, cursor: 'pointer' }}
                      >
                        {STATUS_OPTIONS.map(s => (
                          <option key={s} value={s}>{cap(s)}</option>
                        ))}
                      </select>
                    ) : (
                      <div style={{ fontSize: 12, color: 'var(--text, #e6edf3)' }}>{cap(selected.status)}</div>
                    )}
                    <div style={{ fontSize: 9, color: 'var(--muted, #8b949e)', marginTop: 4 }}>
                      enabled: {(editable ? form?.status : selected.status) === 'active' ? 'yes' : 'no'} (derived)
                    </div>
                  </div>

                  {/* DTE range */}
                  <div>
                    <div style={labelStyle}>DTE Range</div>
                    {editable ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <input
                          type="number" value={form?.dte_min ?? ''}
                          onChange={e => setField('dte_min', e.target.value)}
                          aria-label="DTE min"
                          style={{ ...inputStyle, width: 56, textAlign: 'center' }}
                        />
                        <span style={{ color: 'var(--muted, #8b949e)' }}>–</span>
                        <input
                          type="number" value={form?.dte_max ?? ''}
                          onChange={e => setField('dte_max', e.target.value)}
                          aria-label="DTE max"
                          style={{ ...inputStyle, width: 56, textAlign: 'center' }}
                        />
                        <span style={{ color: 'var(--muted, #8b949e)', fontSize: 11, marginLeft: 4 }}>days</span>
                      </div>
                    ) : (
                      <div style={{ fontSize: 12, color: 'var(--text, #e6edf3)' }}>
                        {selected.dte_min ?? '—'} – {selected.dte_max ?? '—'} days
                      </div>
                    )}
                  </div>

                  {/* Structures */}
                  <div style={{ position: 'relative' }}>
                    <div style={labelStyle}>Enabled Structures</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
                      {(editable ? form?.structures ?? [] : selected.compatible_structures ?? []).map(s => (
                        <span key={s} style={{
                          background: 'var(--bg3, #21262d)', border: '1px solid var(--border, #30363d)',
                          color: 'var(--text, #e6edf3)', padding: '3px 8px', borderRadius: 12,
                          fontSize: 11, display: 'inline-flex', alignItems: 'center', gap: 6,
                        }}>
                          {titleCase(s)}
                          {editable && (
                            <span
                              onClick={() => removeStructure(s)}
                              role="button" aria-label={`Remove ${titleCase(s)}`}
                              style={{ color: 'var(--muted, #8b949e)', cursor: 'pointer', fontSize: 14, lineHeight: 1 }}
                            >×</span>
                          )}
                        </span>
                      ))}
                      {editable && (
                        <button
                          onClick={() => setStructMenuOpen(o => !o)}
                          style={{
                            background: 'transparent', border: '1px dashed var(--border, #30363d)',
                            color: 'var(--muted, #8b949e)', padding: '3px 10px', borderRadius: 12,
                            fontSize: 11, fontFamily: MONO, cursor: 'pointer',
                          }}
                        >+ Add</button>
                      )}
                      {(editable ? form?.structures : selected.compatible_structures)?.length === 0 && !editable && (
                        <span style={{ fontSize: 11, color: 'var(--muted, #8b949e)' }}>—</span>
                      )}
                    </div>

                    {/* Add-structure menu */}
                    {editable && structMenuOpen && (
                      <div ref={structMenuRef} style={{
                        position: 'absolute', top: '100%', left: 0, marginTop: 4, zIndex: 50,
                        background: 'var(--bg, #0d1117)', border: '1px solid var(--border, #30363d)',
                        borderRadius: 4, padding: '6px 0', minWidth: 200,
                        boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
                      }}>
                        {AVAILABLE_STRUCTURES.map(s => {
                          const added = form?.structures.includes(s);
                          return (
                            <div
                              key={s}
                              onClick={() => !added && addStructure(s)}
                              style={{
                                padding: '6px 12px', fontSize: 12, cursor: added ? 'default' : 'pointer',
                                color: added ? 'var(--muted, #8b949e)' : 'var(--text, #e6edf3)',
                                opacity: added ? 0.5 : 1,
                              }}
                            >
                              {titleCase(s)}{added ? ' (added)' : ''}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>

                {/* Save actions */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 18 }}>
                  <button
                    onClick={handleSave}
                    disabled={!editable || !dirty || saving}
                    style={{
                      ...tealBtn,
                      opacity: (!editable || !dirty || saving) ? 0.35 : 1,
                      cursor: (!editable || !dirty || saving) ? 'default' : 'pointer',
                    }}
                  >
                    {saving ? 'Saving…' : 'Save changes'}
                  </button>
                  {dirty && editable && (
                    <span style={{ fontSize: 11, color: 'var(--amber, #f59e0b)' }}>● Unsaved changes</span>
                  )}
                  {!editable && (
                    <span style={{ fontSize: 11, color: 'var(--muted, #8b949e)' }}>
                      Shared strategy — read-only
                    </span>
                  )}
                </div>
              </div>

              {/* ── Stacked config sections ── */}
              {/* Hard Gates (OTA-785) and Scoring Weights (OTA-786) are built; the
                  others remain scaffolds until their stories land (Parameters
                  OTA-827, Adjustments OTA-787). */}
              {SECTIONS.map(sec => {
                if (sec.key === 'gates') {
                  return (
                    <HardGatesSection
                      key={sec.key}
                      strategyKey={selected.strategy_key}
                      editable={editable}
                    />
                  );
                }
                if (sec.key === 'scoring') {
                  return (
                    <ScoringSection
                      key={sec.key}
                      strategyKey={selected.strategy_key}
                      editable={editable}
                    />
                  );
                }
                return (
                  <SectionScaffold
                    key={sec.key}
                    section={sec}
                    editable={editable}
                    onOpenCatalog={sec.catalog ? () => setDrawerTab(sec.catalog) : null}
                  />
                );
              })}

              {/* ── Verdict Bands panel ── */}
              <div style={{ marginTop: 24 }}>
                <div style={{ ...sectionTitleStyle, marginBottom: 12 }}>
                  Verdict Bands · final score → grade
                </div>
                <VerdictBands bands={selected.verdict_band_set} />
              </div>

              {/* ── Live preview (OTA-791) — editable strategies only ── */}
              {editable && (
                <PreviewPanel
                  symbol={previewSymbol}
                  onSymbol={setPreviewSymbol}
                  onFindTrades={handleFindTrades}
                  onRefreshFromLive={handleRefreshFromLive}
                  loading={previewLoading}
                  draftBusy={draftBusy}
                  results={previewResults}
                  meta={previewMeta}
                  error={previewError}
                />
              )}
            </>
          )}
        </div>
      </div>

      {/* ═══════════════ Rule catalog drawer (keeps internal tabs) ═══════════════ */}
      {drawerTab && (
        <RuleCatalogDrawer activeTab={drawerTab} onTab={setDrawerTab} onClose={() => setDrawerTab(null)} />
      )}
    </div>
  );
}

// ─── Selector ────────────────────────────────────────────────────────────────

function Selector({ ota, shared, selectedKey, onSelect }) {
  const renderGroup = (rows) => rows.map(r => {
    const active = r.strategy_key === selectedKey;
    const ro = r.owner_app_id !== OTA_OWNER;
    return (
      <div
        key={r.strategy_key}
        onClick={() => onSelect(r.strategy_key)}
        title={ro ? 'Shared — read-only' : 'Editable'}
        style={{
          padding: '7px 12px', fontSize: 12, cursor: 'pointer', userSelect: 'none',
          fontFamily: MONO,
          color: active ? 'var(--teal, #2dd4bf)' : 'var(--muted, #8b949e)',
          borderLeft: `3px solid ${active ? 'var(--teal, #2dd4bf)' : 'transparent'}`,
          background: active ? 'rgba(45,212,191,0.08)' : 'transparent',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6,
        }}
      >
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {r.display_name}
        </span>
        {ro && <span style={{ fontSize: 8, color: 'var(--muted, #8b949e)' }}>RO</span>}
      </div>
    );
  });

  return (
    <div style={{
      width: 200, flexShrink: 0,
      border: '1px solid var(--border, #30363d)', borderRadius: 6,
      padding: '12px 0', alignSelf: 'flex-start',
    }}>
      <div style={{ padding: '0 12px 8px', fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.6px', color: 'var(--muted, #8b949e)' }}>
        Your Strategies
      </div>
      {ota.length ? renderGroup(ota) : (
        <div style={{ padding: '4px 12px', fontSize: 11, color: 'var(--muted, #8b949e)' }}>None</div>
      )}
      {shared.length > 0 && (
        <>
          <div style={{ height: 1, background: 'var(--border, #30363d)', margin: '10px 0' }} />
          <div style={{ padding: '0 12px 8px', fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.6px', color: 'var(--muted, #8b949e)' }}>
            Shared · read-only
          </div>
          {renderGroup(shared)}
        </>
      )}
    </div>
  );
}

// ─── Owner badge ─────────────────────────────────────────────────────────────

function OwnerBadge({ owner, editable }) {
  return (
    <span style={{
      flexShrink: 0, fontSize: 9, fontWeight: 700, fontFamily: MONO,
      padding: '3px 8px', borderRadius: 3, textTransform: 'uppercase', letterSpacing: '0.4px',
      color: editable ? 'var(--teal, #2dd4bf)' : 'var(--muted, #8b949e)',
      background: editable ? 'rgba(45,212,191,0.12)' : 'var(--bg3, #21262d)',
      border: `1px solid ${editable ? 'rgba(45,212,191,0.4)' : 'var(--border, #30363d)'}`,
    }}>
      {owner} · {editable ? 'editable' : 'read-only'}
    </span>
  );
}

// ─── Section scaffold (mount point for OTA-785/786/787/788) ──────────────────

function SectionScaffold({ section, editable, onOpenCatalog }) {
  return (
    <div style={{ marginTop: 24 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12,
      }}>
        <div style={sectionTitleStyle}>{section.title}</div>
      </div>
      <div style={{
        border: '1px solid var(--border, #30363d)', borderRadius: 6, padding: 16,
      }}>
        <div style={{ fontSize: 11, color: 'var(--muted, #8b949e)', fontFamily: MONO }}>
          {section.title.split(' · ')[0]} configuration lands in {section.story}.
        </div>
        {onOpenCatalog && (
          <button
            onClick={onOpenCatalog}
            disabled={!editable}
            style={{
              ...mutedBtn, marginTop: 12,
              border: '1px dashed var(--border, #30363d)',
              opacity: editable ? 1 : 0.35,
              cursor: editable ? 'pointer' : 'default',
            }}
          >
            {section.addLabel || '+ Add from catalog'}
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Verdict bands (read-only render of verdict_band_set) ────────────────────

const GRADE_FOR_VERDICT = {
  EXECUTE: { grade: 'A', color: 'var(--green, #4ade80)' },
  STRONG:  { grade: 'B', color: 'var(--teal, #2dd4bf)' },
  WAIT:    { grade: 'C', color: '#eab308' },
  CAUTION: { grade: 'D', color: '#f97316' },
  PASS:    { grade: 'F', color: 'var(--red, #f87171)' },
};

function VerdictBands({ bands }) {
  const list = Array.isArray(bands) ? bands : [];
  if (!list.length) {
    return (
      <div style={{
        border: '1px solid var(--border, #30363d)', borderRadius: 6, padding: 16,
        fontSize: 11, color: 'var(--muted, #8b949e)', fontFamily: MONO,
      }}>
        No verdict bands configured.
      </div>
    );
  }
  return (
    <div style={{
      border: '1px solid var(--border, #30363d)', borderRadius: 6, padding: 16,
      display: 'grid', gridTemplateColumns: `repeat(${Math.min(list.length, 5)}, 1fr)`, gap: 8,
    }}>
      {list.map((b, i) => {
        const meta = GRADE_FOR_VERDICT[String(b.verdict || '').toUpperCase()]
          ?? { grade: b.verdict, color: 'var(--text, #e6edf3)' };
        return (
          <div key={i} style={{
            border: '1px solid var(--border, #30363d)', borderRadius: 4, padding: '10px 12px',
          }}>
            <div style={{ fontSize: 16, fontWeight: 600, color: meta.color, marginBottom: 4 }}>
              {meta.grade}
            </div>
            <div style={{ fontSize: 11, color: 'var(--muted, #8b949e)' }}>
              {Number(b.min_score).toFixed(2)} – {Number(b.max_score).toFixed(2)}
            </div>
            <div style={{ fontSize: 10, color: 'var(--muted, #8b949e)', textTransform: 'uppercase', letterSpacing: '0.5px', marginTop: 6 }}>
              {b.verdict}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Live preview panel (OTA-791) ───────────────────────────────────────────
//
// "Find trades →" evaluates the strategy's DRAFT against one symbol's chain,
// loading the draft fresh from the tables through the engine. Results render as
// scores (##.00) + verdicts (verdict colors); expiry via formatDate; no `$`.

const verdictColor = (verdict) =>
  (GRADE_FOR_VERDICT[String(verdict || '').toUpperCase()] || {}).color
  || 'var(--text, #e6edf3)';

function PreviewPanel({
  symbol, onSymbol, onFindTrades, onRefreshFromLive,
  loading, draftBusy, results, meta, error,
}) {
  const canRun = symbol.trim().length > 0 && !loading;
  return (
    <div style={{ marginTop: 28 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12,
      }}>
        <div style={sectionTitleStyle}>Live Preview · evaluate draft against a symbol</div>
        <button
          onClick={onRefreshFromLive}
          disabled={draftBusy}
          title="Discard the draft and re-clone it from the live strategy"
          style={{ ...mutedBtn, opacity: draftBusy ? 0.4 : 1, cursor: draftBusy ? 'default' : 'pointer' }}
        >
          {draftBusy ? 'Refreshing…' : 'Refresh from live'}
        </button>
      </div>

      {/* Callout box — var(--bg2) is permitted on inset/callout boxes (UI Part 3a) */}
      <div style={{
        border: '1px solid var(--border, #30363d)', borderRadius: 6, padding: 16,
        background: 'var(--bg2, #161b22)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <input
            value={symbol}
            onChange={e => onSymbol(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && canRun) onFindTrades(); }}
            placeholder="Symbol (e.g. AAPL)"
            aria-label="Preview symbol"
            style={{ ...inputStyle, width: 160, textTransform: 'uppercase' }}
          />
          <button
            onClick={onFindTrades}
            disabled={!canRun}
            style={{ ...tealBtn, opacity: canRun ? 1 : 0.35, cursor: canRun ? 'pointer' : 'default' }}
          >
            {loading ? 'Evaluating…' : 'Find trades →'}
          </button>
          {meta && (
            <span style={{ fontSize: 10, color: 'var(--muted, #8b949e)' }}>
              {meta.underlying_price > 0 ? `underlying ${Number(meta.underlying_price).toFixed(2)} · ` : ''}
              {meta.candidates_evaluated} candidates · config {String(meta.config_version).slice(0, 8)}
            </span>
          )}
        </div>

        {error && (
          <div style={{ marginTop: 12, fontSize: 11, color: 'var(--red, #f87171)' }}>
            {error}
          </div>
        )}

        {results && <PreviewResults results={results} />}
      </div>
    </div>
  );
}

function PreviewResults({ results }) {
  if (!results.length) {
    return (
      <div style={{ marginTop: 14, fontSize: 11, color: 'var(--muted, #8b949e)' }}>
        No candidates surfaced for this symbol and strategy.
      </div>
    );
  }
  const cell = { padding: '6px 10px', fontSize: 11, textAlign: 'left', whiteSpace: 'nowrap' };
  const head = { ...cell, fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--muted, #8b949e)' };
  // Cap rendered rows; the backend already ranks by score descending.
  const shown = results.slice(0, 50);
  return (
    <div style={{ marginTop: 14, overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', fontFamily: MONO }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border, #30363d)' }}>
            <th style={head}>Structure</th>
            <th style={head}>Strikes</th>
            <th style={head}>Expiry</th>
            <th style={{ ...head, textAlign: 'right' }}>DTE</th>
            <th style={{ ...head, textAlign: 'right' }}>Score</th>
            <th style={head}>Verdict</th>
          </tr>
        </thead>
        <tbody>
          {shown.map(r => (
            <tr key={r.candidate_id} style={{ borderBottom: '1px solid rgba(48,54,61,0.5)' }}>
              <td style={{ ...cell, color: 'var(--text, #e6edf3)' }}>{r.structure_label || r.structure || '—'}</td>
              <td style={{ ...cell, color: 'var(--muted, #8b949e)' }}>{r.strikes || '—'}</td>
              <td style={{ ...cell, color: 'var(--muted, #8b949e)' }}>{r.expiration ? formatDate(r.expiration) : '—'}</td>
              <td style={{ ...cell, textAlign: 'right', color: 'var(--muted, #8b949e)' }}>{r.dte ?? '—'}</td>
              <td style={{ ...cell, textAlign: 'right', color: 'var(--text, #e6edf3)' }}>
                {r.score != null ? Number(r.score).toFixed(2) : '—'}
              </td>
              <td style={{ ...cell, color: verdictColor(r.verdict), fontWeight: 600 }}>
                {r.verdict || r.terminal_phase}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {results.length > shown.length && (
        <div style={{ marginTop: 8, fontSize: 10, color: 'var(--muted, #8b949e)' }}>
          Showing top {shown.length} of {results.length} evaluated.
        </div>
      )}
    </div>
  );
}

// ─── Rule catalog drawer (the only tabbed element on this surface) ───────────

function RuleCatalogDrawer({ activeTab, onTab, onClose }) {
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
        <div style={{
          padding: '18px 20px', borderBottom: '1px solid var(--border, #30363d)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text, #e6edf3)' }}>Rule Catalog</div>
            <div style={{ fontSize: 11, color: 'var(--muted, #8b949e)', marginTop: 2 }}>
              From the rules schema
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{ background: 'transparent', border: 'none', color: 'var(--muted, #8b949e)', fontSize: 20, cursor: 'pointer' }}
          >×</button>
        </div>

        {/* Internal tabs — the only tabs on this surface */}
        <div style={{ display: 'flex', gap: 16, padding: '0 20px', borderBottom: '1px solid var(--border, #30363d)' }}>
          {DRAWER_TABS.map(t => {
            const on = t.key === activeTab;
            return (
              <div
                key={t.key}
                onClick={() => onTab(t.key)}
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

        <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          <div style={{ fontSize: 11, color: 'var(--muted, #8b949e)', lineHeight: 1.6 }}>
            The {DRAWER_TABS.find(t => t.key === activeTab)?.label} catalog and add-to-strategy
            wiring are delivered with the section bodies (OTA-785 / OTA-786 / OTA-787 / OTA-788).
            This shell stands up the drawer and its tabs.
          </div>
        </div>
      </div>
    </>
  );
}
