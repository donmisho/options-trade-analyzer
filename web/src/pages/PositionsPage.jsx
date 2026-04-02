/**
 * PositionsPage — Redesigned position tracking view.
 *
 * Session 1: Column config, filter bar, group-by, page shell.
 * Session 2: Expansion panel (assessment version stack) + Refresh/Archive actions.
 * Session 3: Wired to real backend API — no mock data.
 *
 * Jira: OTA-268, OTA-269, OTA-270, OTA-271
 */

import { useState, useMemo, useEffect } from 'react';
import { positionsColumns, POSITIONS_DEFAULT_SORT } from '../config/positions-columns';
import { formatDate } from '../utils/formatDate';
import {
  getPositions,
  getPositionAssessments,
  refreshPosition,
  archivePosition,
  getPositionCurrentPrices,
} from '../api/client';
import RefreshConfirmDialog from '../components/RefreshConfirmDialog';
import { useToast } from '../components/Toast';
import './PageShared.css';
import './PositionsPage.css';

// ─── API → UI normalisation ───────────────────────────────────────────────────

/**
 * Map a PositionResponse from the API to the flat shape expected by the
 * column config and group helpers.
 */
function normalizePosition(apiPos) {
  const ts   = apiPos.trade_structure || {};
  const legs = Array.isArray(ts.legs) ? ts.legs : [];

  const expiration =
    ts.expiration ||
    (legs.length > 0 ? legs[0].expiration : null) ||
    null;

  // Current DTE computed from expiration (live, not at-entry)
  let dte = null;
  if (expiration) {
    const diff = new Date(expiration) - new Date();
    dte = Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
  }

  const shortLeg   = legs.find(l => l.side === 'short');
  const longLeg    = legs.find(l => l.side === 'long');
  const shortStrike = ts.short_strike ?? shortLeg?.strike ?? null;
  const longStrike  = ts.long_strike  ?? longLeg?.strike  ?? null;

  const entryPrice = apiPos.entry_price ?? 0;
  const rawPnl     = apiPos.current_pnl;                           // premium diff
  const pnlAmount  = rawPnl != null ? rawPnl * 100 : null;         // per-contract dollars
  const pnlPct     = (rawPnl != null && entryPrice)
    ? (rawPnl / entryPrice) * 100
    : null;

  return {
    id:             apiPos.position_id,
    symbol:         apiPos.symbol,
    source:         apiPos.source,
    strategy_key:   apiPos.strategy_key,
    structure:      ts.structure || ts.spread_structure || 'Vertical',
    trade_type:     ts.trade_type || null,
    analysis_date:  apiPos.entry_date,
    short_strike:   shortStrike,
    long_strike:    longStrike,
    expiration,
    entry_price:    entryPrice,
    current_premium: apiPos.current_price ?? null,
    pnl_amount:     pnlAmount,
    pnl_pct:        pnlPct,
    dte,
    perf_status:    'unknown',   // updated by getPositionCurrentPrices
    status:         apiPos.status,
    health_grade:   apiPos.health_grade ?? null,
    score:          apiPos.claude_score ?? null,
  };
}

// ─── Strategy/Group metadata ──────────────────────────────────────────────────

const STRATEGY_LABELS = {
  'steady-paycheck': 'Steady Paycheck',
  'weekly-grind':    'Weekly Grind',
  'trend-rider':     'Trend Rider',
  'lottery-ticket':  'Lottery Ticket',
  'verticals':       'Vertical Spreads',
  'long-calls':      'Long Calls',
};

const STRATEGY_ORDER = [
  'lottery-ticket', 'steady-paycheck', 'weekly-grind', 'trend-rider',
  'verticals', 'long-calls',
];

// ─── Group-by helpers ─────────────────────────────────────────────────────────

function getGroupValue(pos, groupBy) {
  switch (groupBy) {
    case 'Strategy': return pos.strategy_key;
    case 'Symbol':   return pos.symbol;
    case 'Health':   return pos.health_grade ?? 'Ungraded';
    default:         return pos.strategy_key;
  }
}

function groupLabel(groupBy, key) {
  if (groupBy === 'Strategy') return STRATEGY_LABELS[key] ?? key;
  if (groupBy === 'Health')   return key === 'Ungraded' ? 'Ungraded' : `Grade ${key}`;
  return key;
}

function groupSortKey(groupBy, key) {
  if (groupBy === 'Strategy') {
    const idx = STRATEGY_ORDER.indexOf(key);
    return idx >= 0 ? idx : 99;
  }
  if (groupBy === 'Health') {
    return { A: 0, B: 1, C: 2, D: 3, F: 4, Ungraded: 5 }[key] ?? 6;
  }
  return key;
}

// ─── Sorting ──────────────────────────────────────────────────────────────────

function sortPositions(positions, sortKey, sortDir) {
  const col = positionsColumns.find(c => c.key === sortKey);
  return [...positions].sort((a, b) => {
    let av, bv;
    if (col?.sortValue) {
      av = col.sortValue(a);
      bv = col.sortValue(b);
    } else {
      av = a[sortKey] ?? a[col?.sortKey ?? sortKey];
      bv = b[sortKey] ?? b[col?.sortKey ?? sortKey];
    }
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    const cmp = typeof av === 'string' ? av.localeCompare(bv) : av - bv;
    return sortDir === 'asc' ? cmp : -cmp;
  });
}

// ─── Assessment Version Stack ─────────────────────────────────────────────────

function scoreColor(score) {
  if (score >= 70) return 'var(--green, #4ade80)';
  if (score >= 40) return 'var(--amber, #f59e0b)';
  return 'var(--red, #f87171)';
}

const VERDICT_STYLES = {
  EXECUTE: { color: '#4ade80', bg: 'rgba(74,222,128,0.15)' },
  WAIT:    { color: '#f59e0b', bg: 'rgba(245,158,11,0.15)' },
  PASS:    { color: '#f87171', bg: 'rgba(248,113,113,0.15)' },
};

function VerdictBadge({ verdict }) {
  const s = VERDICT_STYLES[verdict] ?? VERDICT_STYLES.PASS;
  return (
    <span style={{
      display: 'inline-block', padding: '2px 7px', borderRadius: 3,
      fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.3px',
      color: s.color, background: s.bg,
    }}>
      {verdict}
    </span>
  );
}

function AssessmentVersion({ version, defaultExpanded, isOriginal }) {
  const [open, setOpen] = useState(defaultExpanded);
  const dateStr = version.created_at ? formatDate(version.created_at, true) : '—';
  const sc      = scoreColor(version.score);
  const exits   = version.exit_levels ?? {};

  return (
    <div className="av-version">
      {/* Header row */}
      <div className="av-header" onClick={() => setOpen(o => !o)} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className="av-chevron">{open ? '▼' : '▶'}</span>
        <VerdictBadge verdict={version.verdict} />
        <span style={{ fontSize: 11, fontWeight: 700, color: sc }}>
          {Number(version.score ?? 0).toFixed(2)}
        </span>
        {version.synopsis && (
          <span style={{
            display: 'inline-block',
            fontSize: 9, fontWeight: 700,
            padding: '3px 10px', borderRadius: 3,
            background: 'rgba(255,255,255,0.06)',
            border: '1px solid rgba(255,255,255,0.35)',
            color: '#e6edf3',
          }}>
            {version.synopsis}
          </span>
        )}
        <span style={{ fontSize: 9, color: 'var(--muted, #8b949e)', marginLeft: 'auto' }}>
          {dateStr}{isOriginal ? ' · Original' : ''}
        </span>
      </div>

      {/* Expanded body */}
      {open && (
        <div className="av-body">
          {/* Claude's Read */}
          <div style={{
            borderLeft: '2px solid var(--border, #30363d)',
            padding: '8px 12px',
            margin: '6px 0 6px 20px',
            fontSize: 10,
            color: '#c9d1d9',
            lineHeight: 1.6,
          }}>
            {(version.claude_read ?? '').split('\n\n').map((para, i) => (
              <p key={i} style={{ margin: '0 0 6px' }}>{para}</p>
            ))}
          </div>

          {/* Exit plan */}
          {(exits.take_profit != null || exits.hard_stop != null) && (
            <div style={{ display: 'flex', gap: 20, fontSize: 10, marginTop: 6, paddingLeft: 20 }}>
              {exits.take_profit != null && (
                <span>
                  <span style={{ color: 'var(--muted, #8b949e)' }}>Take Profit: </span>
                  <span style={{ color: 'var(--green, #4ade80)', fontWeight: 700 }}>
                    {Number(exits.take_profit).toFixed(2)}
                  </span>
                </span>
              )}
              {exits.hard_stop != null && (
                <span>
                  <span style={{ color: 'var(--muted, #8b949e)' }}>Hard Stop: </span>
                  <span style={{ color: 'var(--red, #f87171)', fontWeight: 700 }}>
                    {Number(exits.hard_stop).toFixed(2)}
                  </span>
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AssessmentVersionStack({ positionId, assessmentsCache, isLoading }) {
  if (isLoading) {
    return (
      <div className="av-stack av-empty" style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
        Loading assessments…
      </div>
    );
  }

  const raw = assessmentsCache?.[positionId] ?? [];
  const assessments = [...raw].sort(
    (a, b) => new Date(b.created_at) - new Date(a.created_at)
  );

  if (!assessments.length) {
    return (
      <div className="av-stack av-empty">
        No assessments recorded for this position.
      </div>
    );
  }

  return (
    <div className="av-stack">
      {assessments.map((v, idx) => (
        <AssessmentVersion
          key={v.assessment_id}
          version={v}
          defaultExpanded={idx === 0}
          isOriginal={idx === assessments.length - 1}
        />
      ))}
    </div>
  );
}

// ─── PositionsTable ───────────────────────────────────────────────────────────

function PositionsTable({
  positions,
  expandedRowIds,
  onRowClick,
  onRefresh,
  onArchive,
  refreshingId,
  assessmentsCache,
  loadingAssessmentIds,
}) {
  const [sort, setSort] = useState(POSITIONS_DEFAULT_SORT);

  const sorted = useMemo(
    () => sortPositions(positions, sort.key, sort.dir),
    [positions, sort]
  );

  function handleHeaderClick(col) {
    if (!col.sortable) return;
    setSort(prev => ({
      key: col.key,
      dir: prev.key === col.key && prev.dir === 'desc' ? 'asc' : 'desc',
    }));
  }

  const colCount = positionsColumns.length;

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {positionsColumns.map(col => {
              const isActive = sort.key === col.key;
              return (
                <th
                  key={col.key}
                  style={{
                    textAlign: col.align === 'right' ? 'right' : col.align === 'left' ? 'left' : 'center',
                    width: col.width,
                    cursor: col.sortable ? 'pointer' : 'default',
                    color: isActive ? '#2dd4bf' : undefined,
                    userSelect: 'none',
                    fontSize: 10,
                    textTransform: 'uppercase',
                    letterSpacing: '0.4px',
                    fontWeight: 400,
                  }}
                  onClick={() => handleHeaderClick(col)}
                >
                  {col.label}
                  {isActive && (
                    <span style={{ marginLeft: 3, fontSize: 9, color: '#2dd4bf' }}>
                      {sort.dir === 'desc' ? '▼' : '▲'}
                    </span>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map(pos => {
            const isExpanded   = expandedRowIds.has(pos.id);
            const isRefreshing = refreshingId === pos.id;
            const ctx = { isExpanded, onRefresh, onArchive, isRefreshing };
            return (
              <>
                <tr
                  key={pos.id}
                  style={{ background: isExpanded ? 'rgba(45,212,191,0.03)' : undefined, cursor: 'pointer' }}
                  onClick={() => onRowClick(pos.id)}
                >
                  {positionsColumns.map(col => (
                    <td
                      key={col.key}
                      style={{
                        textAlign: col.align === 'right' ? 'right' : col.align === 'left' ? 'left' : 'center',
                      }}
                    >
                      {col.render ? col.render(pos, ctx) : (pos[col.key] ?? '—')}
                    </td>
                  ))}
                </tr>
                {isExpanded && (
                  <tr key={`exp-${pos.id}`}>
                    <td
                      colSpan={colCount}
                      style={{ padding: 0, borderBottom: '1px solid var(--border)' }}
                    >
                      <div className="av-expansion-panel">
                        <AssessmentVersionStack
                          positionId={pos.id}
                          assessmentsCache={assessmentsCache}
                          isLoading={loadingAssessmentIds?.has(pos.id)}
                        />
                      </div>
                    </td>
                  </tr>
                )}
              </>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ─── PositionGroup ────────────────────────────────────────────────────────────

function PositionGroup({ name, count, collapsed, onToggle, children }) {
  return (
    <div className="pos-strategy-group">
      <div
        className="pos-group-header pos-group-header--clickable"
        onClick={onToggle}
        style={{ cursor: 'pointer' }}
      >
        <span style={{ color: 'var(--muted, #8b949e)', fontSize: 9, marginRight: 4 }}>
          {collapsed ? '▶' : '▼'}
        </span>
        <span style={{ color: 'var(--teal, #2dd4bf)', fontSize: 12, fontWeight: 700 }}>{name}</span>
        <span style={{ color: 'var(--muted, #8b949e)', fontSize: 10, marginLeft: 6 }}>{count}</span>
      </div>
      {!collapsed && children}
    </div>
  );
}

// ─── FilterBar ────────────────────────────────────────────────────────────────

const GROUP_BY_OPTIONS = ['Strategy', 'Symbol', 'Health'];

const STRATEGY_FILTER_OPTIONS = [
  { value: 'steady-paycheck', label: 'Steady Paycheck' },
  { value: 'weekly-grind',    label: 'Weekly Grind' },
  { value: 'trend-rider',     label: 'Trend Rider' },
  { value: 'lottery-ticket',  label: 'Lottery Ticket' },
];

function FilterBar({ filters, onChange, onRefreshAll, refreshingAll, filteredCount }) {
  return (
    <div className="pos-filter-bar">
      <div className="pos-filter-group">
        <label className="pos-filter-label">Status</label>
        <select
          className="pos-filter-select"
          value={filters.status}
          onChange={e => onChange('status', e.target.value)}
        >
          <option value="Active">Active</option>
          <option value="All">All</option>
          <option value="Closed">Closed</option>
        </select>
      </div>

      <div className="pos-filter-group">
        <label className="pos-filter-label">Type</label>
        <select
          className="pos-filter-select"
          value={filters.source}
          onChange={e => onChange('source', e.target.value)}
        >
          <option value="all">All</option>
          <option value="PAPER">Paper</option>
          <option value="LIVE">Live</option>
        </select>
      </div>

      <div className="pos-filter-group">
        <label className="pos-filter-label">Strategy</label>
        <select
          className="pos-filter-select"
          value={filters.strategy}
          onChange={e => onChange('strategy', e.target.value)}
        >
          <option value="all">All</option>
          {STRATEGY_FILTER_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      <div className="pos-filter-group">
        <label className="pos-filter-label">Symbol</label>
        <input
          type="text"
          className="pos-filter-input"
          placeholder="e.g. META"
          value={filters.symbol}
          onChange={e => onChange('symbol', e.target.value)}
          style={{ width: 60 }}
        />
      </div>

      <div className="pos-filter-group" style={{ marginLeft: 'auto' }}>
        <label className="pos-filter-label">Group By</label>
        <select
          className="pos-filter-select"
          value={filters.groupBy}
          onChange={e => onChange('groupBy', e.target.value)}
          style={{ minWidth: 110 }}
        >
          {GROUP_BY_OPTIONS.map(o => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
      </div>

      <button
        disabled={refreshingAll || filteredCount === 0}
        onClick={onRefreshAll}
        style={{
          padding: '4px 10px', fontSize: 10, fontFamily: 'monospace',
          background: 'rgba(45,212,191,0.1)', border: '1px solid rgba(45,212,191,0.4)',
          color: '#2dd4bf', borderRadius: 4, cursor: 'pointer',
          opacity: (refreshingAll || filteredCount === 0) ? 0.35 : 1,
          alignSelf: 'flex-end',
        }}
      >
        {refreshingAll ? '…' : '↻ Refresh all'}
      </button>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

const _inactive = (s) => s === 'CLOSED' || s === 'ARCHIVED';

export default function PositionsPage() {
  const { showToast }                               = useToast();
  const [positions, setPositions]                   = useState([]);
  const [loading, setLoading]                       = useState(true);
  const [error, setError]                           = useState(null);
  const [assessmentsCache, setAssessmentsCache]     = useState({});
  const [loadingAssessmentIds, setLoadingAsmIds]    = useState(new Set());
  const [refreshingId, setRefreshingId]             = useState(null);
  const [expandedRowIds, setExpandedRowIds]         = useState(new Set());
  const [collapsedGroups, setCollapsedGroups]       = useState({});
  const [showRefreshConfirm, setShowRefreshConfirm]       = useState(false);
  const [refreshingAll, setRefreshingAll]                 = useState(false);
  const [pendingRefreshPositions, setPendingRefreshPositions] = useState(null);
  const [filters, setFilters]                       = useState({
    status:   'Active',
    source:   'all',
    strategy: 'all',
    symbol:   '',
    groupBy:  'Strategy',
  });

  // ── Load positions on mount ────────────────────────────────────────────────
  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        setError(null);
        const data = await getPositions({ include_archived: true });
        const normalized = (data.positions || []).map(normalizePosition);
        setPositions(normalized);

        // Fetch current prices for active positions (background, non-blocking)
        const activeIds = normalized
          .filter(p => !_inactive(p.status))
          .map(p => p.id);
        if (activeIds.length > 0) {
          _fetchCurrentPrices(activeIds);
        }

        // Auto-archive expired positions
        const now = new Date();
        const expired = normalized.filter(
          p => p.expiration && new Date(p.expiration) < now && !_inactive(p.status)
        );
        if (expired.length > 0) {
          _archiveExpiredBatch(expired);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function _fetchCurrentPrices(ids) {
    try {
      const prices = await getPositionCurrentPrices(ids);
      setPositions(prev => {
        const priceMap = {};
        for (const cp of prices) priceMap[cp.position_id] = cp;
        return prev.map(p => {
          const cp = priceMap[p.id];
          if (!cp || cp.error) return p;
          const pnlAmount = cp.current_pnl != null ? cp.current_pnl * 100 : p.pnl_amount;
          const pnlPct    = cp.pnl_pct    != null ? cp.pnl_pct    * 100 : p.pnl_pct;
          return {
            ...p,
            current_premium: cp.current_premium ?? p.current_premium,
            pnl_amount:      pnlAmount,
            pnl_pct:         pnlPct,
            perf_status:     cp.perf_status ?? p.perf_status,
          };
        });
      });
    } catch (err) {
      console.warn('PositionsPage: current prices fetch failed:', err.message);
    }
  }

  async function _archiveExpiredBatch(expired) {
    let count = 0;
    for (const pos of expired) {
      try {
        await archivePosition(pos.id);
        setPositions(prev => prev.map(p => p.id === pos.id ? { ...p, status: 'ARCHIVED' } : p));
        count++;
      } catch {
        // non-fatal
      }
    }
    if (count > 0) {
      showToast({ type: 'info', message: `${count} position${count > 1 ? 's' : ''} archived (expired)` });
    }
  }

  function setFilter(key, val) {
    setFilters(f => ({ ...f, [key]: val }));
  }

  function toggleGroup(groupKey) {
    setCollapsedGroups(prev => ({ ...prev, [groupKey]: !prev[groupKey] }));
  }

  async function handleRowClick(id) {
    setExpandedRowIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
    // Load assessments if not yet cached and not already in-flight
    if (!assessmentsCache[id] && !loadingAssessmentIds.has(id)) {
      setLoadingAsmIds(prev => new Set([...prev, id]));
      try {
        const data = await getPositionAssessments(id);
        setAssessmentsCache(prev => ({ ...prev, [id]: data }));
      } catch {
        // silently fail → empty state shown
      } finally {
        setLoadingAsmIds(prev => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      }
    }
  }

  async function handleRefresh(pos) {
    setRefreshingId(pos.id);
    setExpandedRowIds(prev => { const next = new Set(prev); next.add(pos.id); return next; });
    try {
      const result = await refreshPosition(pos.id);
      // Prepend new assessment to cache
      setAssessmentsCache(prev => ({
        ...prev,
        [pos.id]: [result.assessment, ...(prev[pos.id] ?? [])],
      }));
      // Update position row with latest premium / P&L
      setPositions(prev => prev.map(p => {
        if (p.id !== pos.id) return p;
        return {
          ...p,
          current_premium: result.current_premium,
          pnl_amount:      result.current_pnl * 100,
          pnl_pct:         result.pnl_pct     * 100,
          perf_status:     result.perf_status,
        };
      }));
      showToast({ type: 'success', message: `${pos.symbol} refreshed` });
    } catch (err) {
      showToast({ type: 'error', message: `Refresh failed: ${err.message}` });
    } finally {
      setRefreshingId(null);
    }
  }

  function handleArchive(pos) {
    if (!window.confirm(`Archive this position? (${pos.symbol} · ${pos.source === 'LIVE' ? 'Live' : 'Paper'})`)) return;
    archivePosition(pos.id)
      .then(() => {
        setPositions(prev => prev.map(p => p.id === pos.id ? { ...p, status: 'ARCHIVED' } : p));
        setExpandedRowIds(prev => { const next = new Set(prev); next.delete(pos.id); return next; });
        showToast({ type: 'info', message: 'Position archived' });
      })
      .catch(err => showToast({ type: 'error', message: `Archive failed: ${err.message}` }));
  }

  function handleRefreshAllClick() {
    if (filtered.length > 1) {
      setPendingRefreshPositions(filtered); // capture current filter snapshot
      setShowRefreshConfirm(true);
    } else if (filtered.length === 1) {
      handleRefresh(filtered[0]);
    }
  }

  async function confirmRefreshAll() {
    const toRefresh = pendingRefreshPositions ?? [];
    setShowRefreshConfirm(false);
    setPendingRefreshPositions(null);
    setRefreshingAll(true);
    try {
      // Sequential to avoid rate-limit spikes
      for (const pos of toRefresh) {
        await handleRefresh(pos);
      }
      showToast({ type: 'success', message: `Refreshed ${toRefresh.length} position${toRefresh.length !== 1 ? 's' : ''}` });
    } finally {
      setRefreshingAll(false);
    }
  }

  // ── Filter positions ───────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    return positions.filter(pos => {
      if (filters.status === 'Active') {
        if (_inactive(pos.status)) return false;
      } else if (filters.status === 'Closed') {
        if (!_inactive(pos.status)) return false;
      }
      // 'All' shows everything
      if (filters.source !== 'all' && pos.source !== filters.source) return false;
      if (filters.strategy !== 'all' && pos.strategy_key !== filters.strategy) return false;
      if (filters.symbol.trim()) {
        const q = filters.symbol.trim().toUpperCase();
        if (!pos.symbol.toUpperCase().includes(q)) return false;
      }
      return true;
    });
  }, [positions, filters]);

  // ── Group positions ────────────────────────────────────────────────────────
  const groups = useMemo(() => {
    const map = {};
    for (const pos of filtered) {
      const key = getGroupValue(pos, filters.groupBy);
      if (!map[key]) map[key] = [];
      map[key].push(pos);
    }

    const entries = Object.entries(map).sort((a, b) => {
      const ak = groupSortKey(filters.groupBy, a[0]);
      const bk = groupSortKey(filters.groupBy, b[0]);
      if (typeof ak === 'number' && typeof bk === 'number') return ak - bk;
      return String(ak).localeCompare(String(bk));
    });

    const result = entries.map(([key, positions]) => ({
      key,
      name: groupLabel(filters.groupBy, key),
      positions,
    }));

    if (filters.groupBy === 'Strategy') {
      const emptyStrategies = ['weekly-grind', 'trend-rider'].filter(k => !map[k]);
      for (const k of emptyStrategies) {
        result.push({ key: k, name: STRATEGY_LABELS[k], positions: [] });
      }
    }

    return result;
  }, [filtered, filters.groupBy]);

  // Empty groups default to collapsed
  const effectiveCollapsed = useMemo(() => {
    const result = { ...collapsedGroups };
    for (const g of groups) {
      if (g.positions.length === 0 && !(g.key in collapsedGroups)) {
        result[g.key] = true;
      }
    }
    return result;
  }, [groups, collapsedGroups]);

  const activeCount = positions.filter(p => !_inactive(p.status)).length;

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="page-card">
      <div className="pos-page-header">
        <h2 className="page-title">
          <span className="icon">◈</span> Positions
        </h2>
        <span className="pos-header-count" style={{ fontSize: 11, color: 'var(--muted, #8b949e)' }}>
          {activeCount} active
        </span>
      </div>

      <FilterBar
        filters={filters}
        onChange={setFilter}
        onRefreshAll={handleRefreshAllClick}
        refreshingAll={refreshingAll}
        filteredCount={filtered.length}
      />

      <RefreshConfirmDialog
        positionCount={pendingRefreshPositions?.length ?? 0}
        onConfirm={confirmRefreshAll}
        onCancel={() => setShowRefreshConfirm(false)}
        isOpen={showRefreshConfirm}
      />

      {loading && (
        <div className="empty-state">
          <div className="empty-icon" style={{ opacity: 0.4 }}>◈</div>
          <p style={{ color: 'var(--text-muted)' }}>Loading positions…</p>
        </div>
      )}

      {!loading && error && (
        <div className="empty-state">
          <div className="empty-icon">⚠</div>
          <h3>Could not load positions</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>{error}</p>
        </div>
      )}

      {!loading && !error && groups.map(group => (
        <PositionGroup
          key={group.key}
          name={group.name}
          count={group.positions.length}
          collapsed={effectiveCollapsed[group.key] ?? false}
          onToggle={() => toggleGroup(group.key)}
        >
          <PositionsTable
            positions={group.positions}
            expandedRowIds={expandedRowIds}
            onRowClick={handleRowClick}
            onRefresh={handleRefresh}
            onArchive={handleArchive}
            refreshingId={refreshingId}
            assessmentsCache={assessmentsCache}
            loadingAssessmentIds={loadingAssessmentIds}
          />
        </PositionGroup>
      ))}

      {!loading && !error && filtered.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">◈</div>
          <h3>No positions</h3>
          <p>Adjust your filters or follow a trade from the analysis screens.</p>
        </div>
      )}
    </div>
  );
}
