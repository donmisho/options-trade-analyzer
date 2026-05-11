/**
 * StrategyPage — Per-strategy detail page.
 *
 * Route: /strategies/:key (e.g. /strategies/steady-paycheck)
 *
 * Sections:
 *   OTA-359 — Strategy header (name, description, metadata)
 *   OTA-360 — Parameters grid + Scoring weights + "Find trades" button
 *   OTA-361 — Filtered positions list for this strategy
 */

import { useState, useEffect, useMemo, Fragment } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { STRATEGY_CONFIGS } from '../strategy-configs/index';
import { STRATEGY_COLORS } from '../utils/strategyColors';
import { PositionHealthBadge } from '../components/PositionHealthBadge';
import PositionDetailPanel from '../components/PositionDetailPanel';
import { getPositions, refreshPosition } from '../api/client';
import RefreshConfirmDialog from '../components/RefreshConfirmDialog';
import { formatDate } from '../utils/formatDate';
import { useToast } from '../components/Toast';
import './PageShared.css';

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Convert snake_case weight key to Title Case label. */
function weightLabel(key) {
  return key
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

/** Format a parameter value per UI-GUIDANCE Part 4 rules. */
function formatParamValue(value, unit) {
  if (unit === '%')                     return `${value}%`;
  if (unit === '×' || unit === '\xd7')  return `${value}×`;
  if (unit === '\u0394' || unit === 'Δ') return `${Number(value).toFixed(2)} Δ`;
  if (unit === 'days')                  return `${value} days`;
  return `${value}`;
}

/** Format range note for a parameter card. */
function formatRange(min, max, unit) {
  if (unit === '×' || unit === '\xd7')   return `Range: ${min}× – ${max}×`;
  if (unit === '\u0394' || unit === 'Δ') return `Range: ${min} – ${max}`;
  if (unit === '%')                      return `Range: ${min} – ${max}`;
  if (unit === 'days')                   return `Range: ${min} – ${max}d`;
  return `Range: ${min} – ${max}`;
}

/** Normalize a raw API position into a flat display shape. */
function normalizePos(apiPos) {
  const ts   = apiPos.trade_structure || {};
  const legs = Array.isArray(ts.legs) ? ts.legs : [];

  const expiration =
    ts.expiration ||
    (legs.length > 0 ? legs[0].expiration : null) ||
    null;

  let dte = null;
  if (expiration) {
    const diff = new Date(expiration) - new Date();
    dte = Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
  }

  const shortLeg    = legs.find(l => l.side === 'short');
  const longLeg     = legs.find(l => l.side === 'long');
  const shortStrike = ts.short_strike ?? shortLeg?.strike ?? null;
  const longStrike  = ts.long_strike  ?? longLeg?.strike  ?? null;

  let strikeDisplay = '—';
  if (shortStrike && longStrike) {
    strikeDisplay = `${shortStrike}/${longStrike}`;
  } else if (shortStrike) {
    strikeDisplay = `${shortStrike}`;
  } else if (longStrike) {
    strikeDisplay = `${longStrike}`;
  }

  const entryPrice    = apiPos.entry_price ?? 0;
  const currentPrice  = apiPos.current_price ?? null;
  const rawPnl        = apiPos.current_pnl;
  const pnlAmount     = rawPnl != null ? rawPnl * 100 : null;
  const pnlPct        = rawPnl != null && entryPrice ? (rawPnl / entryPrice) * 100 : null;

  return {
    id:           apiPos.position_id,
    symbol:       apiPos.symbol,
    source:       apiPos.source,
    strategy_key: apiPos.strategy_key,
    strike:       strikeDisplay,
    expiration,
    entry_price:  entryPrice,
    current_price: currentPrice,
    pnl_amount:   pnlAmount,
    pnl_pct:      pnlPct,
    dte,
    status:       apiPos.status,
    claude_score: apiPos.claude_score ?? null,
    health_grade: apiPos.health_grade ?? null,
    // Full state for expanded row (OTA-631)
    claude_verdict:            apiPos.claude_verdict ?? null,
    claude_exit_levels:        apiPos.claude_exit_levels ?? null,
    claude_probability_matrix: apiPos.claude_probability_matrix ?? null,
    trade_structure:           apiPos.trade_structure ?? null,
    entry_underlying_price:    apiPos.entry_underlying_price ?? null,
    entry_iv_rank:             apiPos.entry_iv_rank ?? null,
    entry_sma_alignment:       apiPos.entry_sma_alignment ?? null,
    entry_date:                apiPos.entry_date ?? null,
    last_monitored_at:         apiPos.last_monitored_at ?? null,
    dte_at_entry:              apiPos.dte_at_entry ?? null,
  };
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ScoreCell({ score }) {
  if (score == null) return <span style={{ color: '#5a6070', fontSize: 11 }}>—</span>;
  const color = score >= 70 ? '#4ade80' : score >= 40 ? '#f59e0b' : '#f87171';
  const fillPct = Math.min(100, Math.max(0, score));
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{
        width: 40, height: 3, background: '#21262d', borderRadius: 2, overflow: 'hidden', flexShrink: 0,
      }}>
        <div style={{ width: `${fillPct}%`, height: '100%', background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, color }}>{Number(score).toFixed(2)}</span>
    </div>
  );
}

function SourceBadge({ source }) {
  const isLive = source === 'LIVE';
  const color  = isLive ? '#4ade80' : '#60a5fa';
  const bg     = isLive ? 'rgba(74,222,128,0.12)' : 'rgba(96,165,250,0.12)';
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 6px',
      borderRadius: 3,
      fontSize: 9,
      fontWeight: 700,
      color,
      background: bg,
      fontFamily: 'monospace',
    }}>
      {isLive ? 'Live' : 'Paper'}
    </span>
  );
}

function PnLCell({ amount, pct }) {
  if (amount == null) return <span style={{ color: '#5a6070' }}>—</span>;
  const color = amount >= 0 ? '#4ade80' : '#f87171';
  const sign  = amount >= 0 ? '+' : '';
  const pctStr = pct != null ? ` (${amount >= 0 ? '+' : ''}${Number(pct).toFixed(2)}%)` : '';
  return (
    <span style={{ color, fontFamily: 'monospace', fontSize: 11 }}>
      {sign}{Number(amount).toFixed(2)}{pctStr}
    </span>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function StrategyPage() {
  const { key }    = useParams();
  const navigate   = useNavigate();
  const { showToast } = useToast();
  const { activeSymbol } = useApp();

  // Config + color lookup
  const config   = STRATEGY_CONFIGS[key] ?? null;
  const colorKey = key?.replace(/-/g, '_');
  const colors   = STRATEGY_COLORS[colorKey] ?? null;

  // Positions state
  const [positions,      setPositions]      = useState([]);
  const [posLoading,     setPosLoading]     = useState(false);
  const [posError,       setPosError]       = useState(null);
  const [lastRefreshed,  setLastRefreshed]  = useState(null);
  const [statusFilter,   setStatusFilter]   = useState('Active');
  const [sourceFilter,   setSourceFilter]   = useState('all');
  const [expandedIds,    setExpandedIds]    = useState(new Set());
  const [showConfirm,    setShowConfirm]    = useState(false);
  const [refreshingAll,  setRefreshingAll]  = useState(false);

  // Editable parameters state (OTA-408)
  const [editedParams,   setEditedParams]   = useState({});

  useEffect(() => {
    if (key) loadPositions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // Initialize editedParams from configSchema defaults (or saved overrides)
  useEffect(() => {
    const schema = STRATEGY_CONFIGS[key]?.configSchema ?? [];
    if (!schema.length) return;
    try {
      const stored    = JSON.parse(localStorage.getItem('analysisConfig') || '{}');
      const overrides = stored.strategyOverrides?.[key] || {};
      const initial   = {};
      for (const p of schema) {
        initial[p.key] = p.key in overrides ? overrides[p.key] : p.default;
      }
      setEditedParams(initial);
    } catch {
      const initial = {};
      for (const p of schema) initial[p.key] = p.default;
      setEditedParams(initial);
    }
  }, [key]);

  async function loadPositions() {
    setPosLoading(true);
    setPosError(null);
    try {
      const data = await getPositions({ strategy_key: key, include_archived: true });
      setPositions((data.positions || []).map(normalizePos));
      setLastRefreshed(new Date());
    } catch (err) {
      setPosError(err.message);
    } finally {
      setPosLoading(false);
    }
  }

  async function runRefreshAll() {
    const activePositions = filtered.filter(p => !isInactive(p.status));
    setRefreshingAll(true);
    let succeeded = 0;
    let failed    = 0;
    for (const pos of activePositions) {
      try {
        const result = await refreshPosition(pos.id);
        setPositions(prev => prev.map(p => {
          if (p.id !== pos.id) return p;
          return {
            ...p,
            current_price: result.current_premium ?? p.current_price,
            pnl_amount:    result.current_pnl != null ? result.current_pnl * 100 : p.pnl_amount,
            pnl_pct:       result.pnl_pct     != null ? result.pnl_pct     * 100 : p.pnl_pct,
          };
        }));
        succeeded++;
      } catch {
        failed++;
      }
    }
    setRefreshingAll(false);
    setLastRefreshed(new Date());
    if (failed === 0) {
      showToast({ type: 'success', message: `Refreshed ${succeeded} position${succeeded !== 1 ? 's' : ''}` });
    } else {
      showToast({ type: 'error', message: `Refreshed ${succeeded}, failed ${failed}` });
    }
  }

  function handleRefreshAll() {
    const activeCount = filtered.filter(p => !isInactive(p.status)).length;
    if (activeCount > 1) {
      setShowConfirm(true);
    } else {
      runRefreshAll();
    }
  }

  function isInactive(status) {
    return status === 'CLOSED' || status === 'ARCHIVED';
  }

  function toggleRow(id) {
    setExpandedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  // ── Filter positions ─────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    return positions.filter(pos => {
      if (statusFilter === 'Active' && isInactive(pos.status)) return false;
      if (statusFilter === 'Closed' && !isInactive(pos.status)) return false;
      if (sourceFilter !== 'all' && pos.source !== sourceFilter) return false;
      return true;
    });
  }, [positions, statusFilter, sourceFilter]);

  // ── Unknown strategy guard ───────────────────────────────────────────────
  if (!config) {
    return (
      <div className="page-card" style={{ fontFamily: 'monospace', color: '#8b949e', fontSize: 12 }}>
        Unknown strategy: {key}
      </div>
    );
  }

  const weights     = config.scoring_weights ?? {};
  const schema      = config.configSchema ?? [];
  const stratColor  = colors?.text ?? '#2dd4bf';

  return (
    <div className="page-card">

      {/* ═══════════════════════════════════════════════════════════════
          OTA-359 — Strategy Header
      ════════════════════════════════════════════════════════════════ */}
      <div style={{
        border: '1px solid var(--border, #30363d)',
        borderRadius: 4,
        padding: 20,
        marginBottom: 16,
        fontFamily: 'monospace',
      }}>
        <div style={{ fontSize: 18, fontWeight: 700, color: '#e6edf3', marginBottom: 6 }}>
          {config.label}
        </div>
        <div style={{ fontSize: 11, color: '#8b949e', marginBottom: 12 }}>
          {config.description}
        </div>

        {/* Metadata row */}
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.4px', color: '#8b949e' }}>
              DTE Range
            </div>
            <div style={{ fontSize: 12, color: '#e6edf3', marginTop: 2 }}>
              {config.dte_min} – {config.dte_max} days
            </div>
          </div>
          <div>
            <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.4px', color: '#8b949e' }}>
              Structure
            </div>
            <div style={{ fontSize: 12, color: '#e6edf3', marginTop: 2 }}>
              {config.trade_structure
                ? config.trade_structure.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
                : '—'}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.4px', color: '#8b949e' }}>
              Requirement
            </div>
            <div style={{ fontSize: 12, color: '#e6edf3', marginTop: 2 }}>
              {config.non_applicable_reason
                ? config.non_applicable_reason.charAt(0).toUpperCase() + config.non_applicable_reason.slice(1)
                : '—'}
            </div>
          </div>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════
          OTA-360 — Parameters + Weights + Find Trades
      ════════════════════════════════════════════════════════════════ */}

      {/* Parameters */}
      <div style={{
        fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.6px',
        color: '#8b949e', marginBottom: 10, fontFamily: 'monospace',
      }}>
        Parameters
      </div>

      {/* Unsaved changes indicator */}
      {schema.some(p => editedParams[p.key] !== p.default) && (
        <div style={{
          fontSize: 10, color: '#f59e0b', fontFamily: 'monospace',
          marginBottom: 8,
        }}>
          ● Unsaved changes
        </div>
      )}

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 10,
        marginBottom: 12,
      }}>
        {schema.map(param => {
          const currentVal = editedParams[param.key] ?? param.default;
          const isModified = currentVal !== param.default;
          return (
            <div key={param.key} style={{
              border: `1px solid ${isModified ? 'rgba(245,158,11,0.4)' : 'var(--border, #30363d)'}`,
              borderRadius: 4,
              padding: 12,
              fontFamily: 'monospace',
            }}>
              <div style={{
                fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.4px',
                color: '#8b949e', marginBottom: 6,
              }}>
                {param.label}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <input
                  type="number"
                  min={param.min}
                  max={param.max}
                  step={param.step}
                  value={currentVal}
                  onChange={e => setEditedParams(prev => ({
                    ...prev,
                    [param.key]: Number(e.target.value),
                  }))}
                  style={{
                    width: 64,
                    background: 'var(--bg, #0d1117)',
                    border: '1px solid var(--border, #30363d)',
                    color: '#e6edf3',
                    borderRadius: 3,
                    padding: '3px 6px',
                    fontSize: 14,
                    fontWeight: 700,
                    fontFamily: 'monospace',
                  }}
                />
                <span style={{ fontSize: 11, color: '#8b949e' }}>
                  {param.unit === '\xd7' ? '×' : param.unit === '\u0394' ? 'Δ' : param.unit || ''}
                </span>
              </div>
              <div style={{ fontSize: 9, color: '#8b949e' }}>
                Default: {formatParamValue(param.default, param.unit)}
              </div>
              <div style={{ fontSize: 9, color: '#8b949e' }}>
                {formatRange(param.min, param.max, param.unit)}
              </div>
            </div>
          );
        })}
      </div>

      {/* Apply / Reset buttons */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
        <button
          style={{
            background: 'rgba(45,212,191,0.1)', border: '1px solid rgba(45,212,191,0.4)',
            color: '#2dd4bf', padding: '7px 16px', borderRadius: 4, fontSize: 11,
            fontFamily: 'monospace', cursor: 'pointer',
          }}
          onClick={() => {
            try {
              const stored    = JSON.parse(localStorage.getItem('analysisConfig') || '{}');
              const overrides = stored.strategyOverrides || {};
              overrides[key]  = { ...overrides[key], ...editedParams };
              localStorage.setItem('analysisConfig', JSON.stringify({ ...stored, strategyOverrides: overrides }));
              showToast({ type: 'success', message: `Parameters saved for ${config.label}` });
            } catch {
              showToast({ type: 'error', message: 'Failed to save parameters' });
            }
          }}
        >
          Apply
        </button>
        <button
          style={{
            background: 'transparent', border: '1px solid #30363d',
            color: '#8b949e', padding: '7px 14px', borderRadius: 4, fontSize: 11,
            fontFamily: 'monospace', cursor: 'pointer',
          }}
          onClick={() => {
            const defaults = {};
            for (const p of schema) defaults[p.key] = p.default;
            setEditedParams(defaults);
            showToast({ type: 'info', message: 'Parameters reset to defaults' });
          }}
        >
          Reset to defaults
        </button>
      </div>

      {/* Scoring Weights */}
      <div style={{
        fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.6px',
        color: '#8b949e', marginBottom: 10, fontFamily: 'monospace',
      }}>
        Scoring Weights
      </div>

      <div style={{
        border: '1px solid var(--border, #30363d)',
        borderRadius: 4,
        padding: 14,
        marginBottom: 16,
        fontFamily: 'monospace',
      }}>
        {Object.entries(weights).map(([wKey, wVal]) => {
          const pct = Math.round(wVal * 100);
          return (
            <div key={wKey} style={{
              display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8,
            }}>
              <div style={{ width: 140, fontSize: 10, color: '#8b949e', flexShrink: 0 }}>
                {weightLabel(wKey)}
              </div>
              <div style={{
                flex: 1, height: 3, background: 'var(--bg3, #21262d)', borderRadius: 2,
              }}>
                <div style={{
                  width: `${pct}%`, height: '100%',
                  background: stratColor,
                  borderRadius: 2,
                }} />
              </div>
              <div style={{ width: 30, fontSize: 10, fontWeight: 700, color: '#e6edf3', textAlign: 'right' }}>
                {pct}%
              </div>
            </div>
          );
        })}
      </div>

      {/* Find trades */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <button
          style={{
            background: 'rgba(45,212,191,0.1)', border: '1px solid rgba(45,212,191,0.4)',
            color: '#2dd4bf', padding: '7px 16px', borderRadius: 4, fontSize: 11,
            fontFamily: 'monospace', cursor: 'pointer',
          }}
          onClick={() => {
            const params = new URLSearchParams({ strategy: key });
            if (activeSymbol) params.set('symbol', activeSymbol);
            navigate(`/trades?${params.toString()}`);
          }}
        >
          Find trades →
        </button>
        <span style={{ fontSize: 10, color: '#8b949e', fontFamily: 'monospace' }}>
          {activeSymbol
            ? `Opens Trades page for ${activeSymbol} filtered to ${config.label}`
            : `Opens Trades page filtered to ${config.label} parameters`}
        </span>
      </div>

      {/* ═══════════════════════════════════════════════════════════════
          OTA-361 — Filtered Positions
      ════════════════════════════════════════════════════════════════ */}
      <div style={{
        fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.6px',
        color: '#8b949e', marginBottom: 10, fontFamily: 'monospace',
      }}>
        {config.label} Positions
      </div>

      {/* Filter bar */}
      <div style={{
        background: 'var(--bg2, #161b22)',
        border: '1px solid var(--border, #30363d)',
        borderRadius: 4,
        padding: '8px 12px',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        marginBottom: 12,
        fontFamily: 'monospace',
        flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.4px', color: '#8b949e' }}>
            Status
          </label>
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            style={selectStyle}
          >
            <option value="Active">Active</option>
            <option value="All">All</option>
            <option value="Closed">Closed</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.4px', color: '#8b949e' }}>
            Type
          </label>
          <select
            value={sourceFilter}
            onChange={e => setSourceFilter(e.target.value)}
            style={selectStyle}
          >
            <option value="all">All</option>
            <option value="PAPER">Paper</option>
            <option value="LIVE">Live</option>
          </select>
        </div>

        <span style={{ fontSize: 9, color: '#8b949e', marginLeft: 4 }}>
          {filtered.length} position{filtered.length !== 1 ? 's' : ''}
          {lastRefreshed ? ` · refreshed ${formatDate(lastRefreshed, true)}` : ''}
        </span>

        <div style={{ marginLeft: 'auto' }}>
          <button
            onClick={handleRefreshAll}
            disabled={refreshingAll}
            style={{
              background: 'rgba(45,212,191,0.1)', border: '1px solid rgba(45,212,191,0.4)',
              color: '#2dd4bf', padding: '4px 10px', borderRadius: 4, fontSize: 10,
              fontFamily: 'monospace', cursor: refreshingAll ? 'default' : 'pointer',
              opacity: refreshingAll ? 0.35 : 1,
            }}
          >
            {refreshingAll ? '↻ Refreshing…' : '↻ Refresh all'}
          </button>
        </div>
      </div>

      {/* Confirmation dialog */}
      {showConfirm && (
        <RefreshConfirmDialog
          count={filtered.filter(p => !isInactive(p.status)).length}
          onConfirm={() => { setShowConfirm(false); runRefreshAll(); }}
          onCancel={() => setShowConfirm(false)}
        />
      )}

      {/* Positions table */}
      {posLoading && (
        <div style={{ fontFamily: 'monospace', fontSize: 11, color: '#8b949e', padding: '20px 0' }}>
          Loading positions…
        </div>
      )}

      {!posLoading && posError && (
        <div style={{ fontFamily: 'monospace', fontSize: 11, color: '#f87171', padding: '20px 0' }}>
          Could not load positions: {posError}
        </div>
      )}

      {!posLoading && !posError && filtered.length === 0 && (
        <div style={{
          fontFamily: 'monospace', fontSize: 11, color: '#8b949e',
          padding: '20px 0', textAlign: 'center',
        }}>
          No {statusFilter.toLowerCase()} positions for {config.label}.
        </div>
      )}

      {!posLoading && !posError && filtered.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'monospace', fontSize: 11 }}>
            <thead>
              <tr>
                {[
                  { label: '',         width: 24  },
                  { label: 'Score',    width: 90  },
                  { label: 'Symbol',   width: 70  },
                  { label: 'Type',     width: 60  },
                  { label: 'Strike / Spread', width: 100 },
                  { label: 'Expiration', width: 100 },
                  { label: 'Premium',  width: 80  },
                  { label: 'Current',  width: 80  },
                  { label: 'P&L',      width: 140 },
                  { label: 'DTE',      width: 50  },
                  { label: 'Health',   width: 60  },
                ].map(col => (
                  <th key={col.label} style={{
                    width: col.width,
                    fontSize: 10, fontWeight: 400,
                    textTransform: 'uppercase', letterSpacing: '0.4px',
                    color: '#8b949e', textAlign: 'left',
                    padding: '6px 8px', borderBottom: '1px solid var(--border, #30363d)',
                  }}>
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(pos => {
                const isExpanded = expandedIds.has(pos.id);
                return (
                  <Fragment key={pos.id}>
                    <tr
                      style={{
                        cursor: 'pointer',
                        background: isExpanded ? 'rgba(45,212,191,0.03)' : 'transparent',
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = isExpanded ? 'rgba(45,212,191,0.03)' : 'rgba(45,212,191,0.02)'}
                      onMouseLeave={e => e.currentTarget.style.background = isExpanded ? 'rgba(45,212,191,0.03)' : 'transparent'}
                      onClick={() => toggleRow(pos.id)}
                    >
                      {/* Chevron */}
                      <td style={{ padding: '8px 8px', color: '#8b949e', fontSize: 9 }}>
                        {isExpanded ? '▼' : '▶'}
                      </td>
                      {/* Score */}
                      <td style={{ padding: '8px 8px' }}>
                        <ScoreCell score={pos.claude_score} />
                      </td>
                      {/* Symbol */}
                      <td style={{ padding: '8px 8px', fontWeight: 700, color: '#e6edf3' }}>
                        {pos.symbol}
                      </td>
                      {/* Type (Paper/Live) */}
                      <td style={{ padding: '8px 8px' }}>
                        <SourceBadge source={pos.source} />
                      </td>
                      {/* Strike / Spread */}
                      <td style={{ padding: '8px 8px', color: '#c9d1d9' }}>
                        {pos.strike}
                      </td>
                      {/* Expiration */}
                      <td style={{ padding: '8px 8px', color: '#c9d1d9' }}>
                        {pos.expiration ? formatDate(pos.expiration) : '—'}
                      </td>
                      {/* Premium (entry) */}
                      <td style={{ padding: '8px 8px', color: '#c9d1d9' }}>
                        {pos.entry_price != null ? Number(pos.entry_price).toFixed(2) : '—'}
                      </td>
                      {/* Current */}
                      <td style={{ padding: '8px 8px', color: '#c9d1d9' }}>
                        {pos.current_price != null ? Number(pos.current_price).toFixed(2) : '—'}
                      </td>
                      {/* P&L */}
                      <td style={{ padding: '8px 8px' }}>
                        <PnLCell amount={pos.pnl_amount} pct={pos.pnl_pct} />
                      </td>
                      {/* DTE */}
                      <td style={{ padding: '8px 8px', color: '#c9d1d9' }}>
                        {pos.dte != null ? `${pos.dte}d` : '—'}
                      </td>
                      {/* Health */}
                      <td style={{ padding: '8px 8px' }}>
                        <PositionHealthBadge grade={pos.health_grade} />
                      </td>
                    </tr>

                    {isExpanded && (
                      <tr>
                        <td colSpan={11} style={{ padding: 0 }}>
                          <PositionDetailPanel pos={pos} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Inline styles ─────────────────────────────────────────────────────────────

const selectStyle = {
  background: 'var(--bg3, #21262d)',
  border: '1px solid var(--border, #30363d)',
  color: '#e6edf3',
  fontSize: 10,
  padding: '3px 6px',
  borderRadius: 3,
  fontFamily: 'monospace',
  cursor: 'pointer',
};
