/**
 * PositionsPage — Unified position tracking view.
 *
 * Replaces FavoritesPage. Shows all paper and live positions grouped by strategy,
 * with per-group aggregate stats and a composable filter bar.
 *
 * Phase 2.10 B2: wired to real API.
 */

import { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { PositionHealthBadge } from '../components/PositionHealthBadge';
import { PositionDetailPanel } from '../components/PositionDetailPanel';
import { getPositions, closePosition } from '../api/client';
import './PageShared.css';
import './PositionsPage.css';

// ─── Strategy display labels ─────────────────────────────────────────────────

const STRATEGY_LABELS = {
  'steady-paycheck': 'Steady Paycheck',
  'weekly-grind':    'Weekly Grind',
  'trend-rider':     'Trend Rider',
  'lottery-ticket':  'Lottery Ticket',
  'verticals':       'Vertical Spreads',
  'long-calls':      'Long Calls',
};

const STRATEGY_ORDER = [
  'steady-paycheck', 'weekly-grind', 'trend-rider', 'lottery-ticket',
  'verticals', 'long-calls',
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function isActive(pos) {
  return pos.status === 'FOLLOWING' || pos.status === 'LIVE';
}

function calcDte(expiration) {
  if (!expiration) return null;
  try {
    const diff = Math.ceil((new Date(expiration) - new Date()) / 86400000);
    return Math.max(0, diff);
  } catch {
    return null;
  }
}

function fmtPrice(val) {
  if (val == null) return '—';
  return Number(val).toFixed(2);
}

function fmtPnl(val) {
  if (val == null) return '—';
  const n = Number(val);
  return (n >= 0 ? '+' : '') + n.toFixed(0);
}

function pnlClass(val) {
  if (val == null) return '';
  return Number(val) >= 0 ? 'pos-pnl-up' : 'pos-pnl-down';
}

function aggregateStats(positions) {
  const active = positions.filter(isActive);
  const closed = positions.filter(p => p.status === 'CLOSED');
  const winners = closed.filter(p => (p.outcome_pnl ?? 0) > 0);
  const winRate = closed.length > 0 ? Math.round((winners.length / closed.length) * 100) : null;
  const avgPnl = closed.length > 0
    ? Math.round(closed.reduce((s, p) => s + (p.outcome_pnl ?? 0), 0) / closed.length)
    : null;
  const avgHold = closed.length > 0
    ? Math.round(closed.reduce((s, p) => s + (p.days_held ?? 0), 0) / closed.length)
    : null;
  return { active: active.length, closed: closed.length, winRate, avgPnl, avgHold };
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function SourceBadge({ source }) {
  const isLive = source === 'LIVE';
  return (
    <span className={`pos-source-badge ${isLive ? 'pos-source-live' : 'pos-source-paper'}`}>
      {isLive ? 'Live' : 'Paper'}
    </span>
  );
}

function ExitReasonBadge({ reason }) {
  const cls = {
    TARGET:  'pos-exit-target',
    WARNING: 'pos-exit-warning',
    STOP:    'pos-exit-stop',
    EXPIRED: 'pos-exit-expired',
    MANUAL:  'pos-exit-manual',
  }[reason] ?? '';
  const label = reason ? reason.charAt(0) + reason.slice(1).toLowerCase() : '—';
  return <span className={`pos-exit-badge ${cls}`}>{label}</span>;
}

function ActiveTable({ positions, onClose, onView }) {
  const [expandedId, setExpandedId] = useState(null);
  if (!positions.length) return null;
  const toggleExpand = (id) => setExpandedId(prev => prev === id ? null : id);
  const COL_COUNT = 10;
  return (
    <div className="table-wrap" style={{ marginBottom: 12 }}>
      <table>
        <thead>
          <tr>
            <th style={{ width: 20 }}></th>
            <th>Symbol</th>
            <th>Type</th>
            <th>Grade</th>
            <th>Entry</th>
            <th>Current</th>
            <th>P&amp;L</th>
            <th>DTE</th>
            <th>Score</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {positions.map(pos => {
            const dte = calcDte(pos.trade_structure?.expiration);
            const dteColor = dte == null ? '' : dte <= 5 ? '#ef4444' : dte <= 10 ? '#f97316' : '';
            const isExpanded = expandedId === pos.position_id;
            return (
              <>
                <tr key={pos.position_id}>
                  <td>
                    <button
                      className="pos-expand-btn"
                      onClick={() => toggleExpand(pos.position_id)}
                      title={isExpanded ? 'Collapse' : 'Expand'}
                    >
                      {isExpanded ? '▾' : '▸'}
                    </button>
                  </td>
                  <td>
                    <button className="pos-symbol-btn" onClick={() => onView(pos.symbol)}>
                      {pos.symbol}
                    </button>
                  </td>
                  <td><SourceBadge source={pos.source} /></td>
                  <td><PositionHealthBadge grade={pos.health_grade} /></td>
                  <td className="mono text-muted">{fmtPrice(pos.entry_underlying_price)}</td>
                  <td className="mono">{fmtPrice(pos.current_price)}</td>
                  <td className={`mono ${pnlClass(pos.current_pnl)}`}>{fmtPnl(pos.current_pnl)}</td>
                  <td className="mono" style={{ color: dteColor || undefined }}>
                    {dte != null ? `${dte}d` : '—'}
                  </td>
                  <td className="mono text-muted">{pos.claude_score ?? '—'}</td>
                  <td>
                    <div className="pos-actions">
                      <button className="pos-btn-close" onClick={() => onClose(pos)}>Close</button>
                      <button className="pos-btn-view" onClick={() => onView(pos.symbol)}>View</button>
                    </div>
                  </td>
                </tr>
                {isExpanded && (
                  <PositionDetailPanel
                    key={`detail-${pos.position_id}`}
                    position={pos}
                    colSpan={COL_COUNT}
                  />
                )}
              </>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ClosedTable({ positions }) {
  const [expandedId, setExpandedId] = useState(null);
  if (!positions.length) return null;
  const toggleExpand = (id) => setExpandedId(prev => prev === id ? null : id);
  const COL_COUNT = 9;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th style={{ width: 20 }}></th>
            <th>Symbol</th>
            <th>Type</th>
            <th>Grade</th>
            <th>Entry</th>
            <th>Exit</th>
            <th>P&amp;L</th>
            <th>Hold</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {positions.map(pos => {
            const isExpanded = expandedId === pos.position_id;
            return (
              <>
                <tr key={pos.position_id}>
                  <td>
                    <button
                      className="pos-expand-btn"
                      onClick={() => toggleExpand(pos.position_id)}
                      title={isExpanded ? 'Collapse' : 'Expand'}
                    >
                      {isExpanded ? '▾' : '▸'}
                    </button>
                  </td>
                  <td className="mono text-cyan">{pos.symbol}</td>
                  <td><SourceBadge source={pos.source} /></td>
                  <td><PositionHealthBadge grade={pos.health_grade} /></td>
                  <td className="mono text-muted">{fmtPrice(pos.entry_underlying_price)}</td>
                  <td className="mono">{fmtPrice(pos.exit_price)}</td>
                  <td className={`mono ${pnlClass(pos.outcome_pnl)}`}>{fmtPnl(pos.outcome_pnl)}</td>
                  <td className="mono text-muted">{pos.days_held != null ? `${pos.days_held}d` : '—'}</td>
                  <td><ExitReasonBadge reason={pos.exit_reason} /></td>
                </tr>
                {isExpanded && (
                  <PositionDetailPanel
                    key={`detail-${pos.position_id}`}
                    position={pos}
                    colSpan={COL_COUNT}
                  />
                )}
              </>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function StrategyGroup({ strategyKey, positions, onClose, onView }) {
  const label = STRATEGY_LABELS[strategyKey] ?? strategyKey;
  const active = positions.filter(isActive);
  const closed = positions.filter(p => p.status === 'CLOSED');
  const stats = aggregateStats(positions);

  return (
    <div className="pos-strategy-group">
      <div className="pos-group-header">
        <span className="pos-group-title">{label}</span>
        <span className="pos-group-stats">
          {stats.active > 0 && <span>{stats.active} active</span>}
          {stats.active > 0 && stats.closed > 0 && <span className="pos-stats-sep">·</span>}
          {stats.closed > 0 && <span>{stats.closed} closed</span>}
          {stats.winRate != null && (
            <>
              <span className="pos-stats-sep">·</span>
              <span>Win rate {stats.winRate}%</span>
            </>
          )}
          {stats.avgPnl != null && (
            <>
              <span className="pos-stats-sep">·</span>
              <span className={stats.avgPnl >= 0 ? 'pos-pnl-up' : 'pos-pnl-down'}>
                Avg P&L {fmtPnl(stats.avgPnl)}
              </span>
            </>
          )}
          {stats.avgHold != null && (
            <>
              <span className="pos-stats-sep">·</span>
              <span>Avg hold {stats.avgHold}d</span>
            </>
          )}
        </span>
      </div>

      {active.length > 0 && (
        <ActiveTable positions={active} onClose={onClose} onView={onView} />
      )}
      {closed.length > 0 && (
        <>
          {active.length > 0 && (
            <div className="pos-closed-divider">Closed</div>
          )}
          <ClosedTable positions={closed} />
        </>
      )}
    </div>
  );
}

// ─── Close Modal ──────────────────────────────────────────────────────────────

function CloseModal({ pos, onCancel, onConfirm, closing }) {
  const [exitPrice, setExitPrice] = useState(
    pos.current_price != null ? String(pos.current_price) : ''
  );
  const [exitReason, setExitReason] = useState('MANUAL');
  const [err, setErr] = useState(null);

  const handleConfirm = () => {
    const price = parseFloat(exitPrice);
    if (isNaN(price) || price <= 0) {
      setErr('Enter a valid exit price');
      return;
    }
    setErr(null);
    onConfirm({ exit_price: price, exit_reason: exitReason });
  };

  return (
    <div className="pos-modal-overlay" onClick={onCancel}>
      <div className="pos-modal" onClick={e => e.stopPropagation()}>
        <h3 className="pos-modal-title">Close Position</h3>
        <p className="pos-modal-body">
          Close <strong>{pos.symbol}</strong> ({pos.source === 'LIVE' ? 'Live' : 'Paper'})?
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <label style={{ fontSize: 12, color: 'var(--text-muted)', width: 90 }}>Exit price</label>
            <input
              type="number"
              step="0.01"
              value={exitPrice}
              onChange={e => setExitPrice(e.target.value)}
              className="pos-filter-input"
              style={{ flex: 1 }}
              placeholder="0.00"
            />
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <label style={{ fontSize: 12, color: 'var(--text-muted)', width: 90 }}>Reason</label>
            <select
              value={exitReason}
              onChange={e => setExitReason(e.target.value)}
              className="pos-filter-select"
              style={{ flex: 1 }}
            >
              <option value="TARGET">Target</option>
              <option value="WARNING">Warning</option>
              <option value="STOP">Stop</option>
              <option value="EXPIRED">Expired</option>
              <option value="MANUAL">Manual</option>
            </select>
          </div>
          {err && <p style={{ fontSize: 12, color: '#ef4444', margin: 0 }}>{err}</p>}
        </div>

        <div className="pos-modal-actions">
          <button className="pos-btn-view" onClick={onCancel} disabled={closing}>Cancel</button>
          <button className="pos-btn-close" onClick={handleConfirm} disabled={closing}>
            {closing ? 'Closing...' : 'Confirm Close'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function PositionsPage() {
  const navigate = useNavigate();

  const [positions, setPositions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [filters, setFilters] = useState({
    status: 'all',       // all | active | closed
    source: 'all',       // all | PAPER | LIVE
    symbol: '',
    strategy: 'all',
  });

  const [closeModal, setCloseModal] = useState(null);
  const [closing, setClosing] = useState(false);

  const setFilter = (key, val) => setFilters(f => ({ ...f, [key]: val }));

  const fetchPositions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const apiFilters = {
        status: filters.status,
        source: filters.source,
        symbol: filters.symbol,
        strategy_key: filters.strategy,
      };
      const data = await getPositions(apiFilters);
      setPositions(data.positions || []);
    } catch (err) {
      setError(err.message || 'Failed to load positions');
      setPositions([]);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchPositions();
  }, [fetchPositions]);

  // Group by strategy in canonical order
  const grouped = useMemo(() => {
    const map = {};
    for (const pos of positions) {
      if (!map[pos.strategy_key]) map[pos.strategy_key] = [];
      map[pos.strategy_key].push(pos);
    }
    // Render known strategy order first, then any unknown keys
    const knownKeys = STRATEGY_ORDER.filter(k => map[k]);
    const otherKeys = Object.keys(map).filter(k => !STRATEGY_ORDER.includes(k));
    return [...knownKeys, ...otherKeys].map(k => ({ key: k, positions: map[k] }));
  }, [positions]);

  const handleView = (symbol) => navigate(`/security/${symbol}`);
  const handleClose = (pos) => setCloseModal(pos);

  const handleCloseConfirm = async ({ exit_price, exit_reason }) => {
    if (!closeModal) return;
    setClosing(true);
    try {
      const updated = await closePosition(closeModal.position_id, { exit_price, exit_reason });
      setPositions(prev => prev.map(p => p.position_id === updated.position_id ? updated : p));
      setCloseModal(null);
    } catch (err) {
      alert(err.message || 'Failed to close position');
    } finally {
      setClosing(false);
    }
  };

  const totalActive = positions.filter(isActive).length;
  const totalClosed = positions.filter(p => p.status === 'CLOSED').length;

  return (
    <div className="page-card">
      <div className="pos-page-header">
        <h2 className="page-title">
          <span className="icon">◈</span> Positions
        </h2>
        <span className="pos-header-count">
          {!loading && totalActive > 0 && <span>{totalActive} active</span>}
          {!loading && totalActive > 0 && totalClosed > 0 && ' · '}
          {!loading && totalClosed > 0 && <span>{totalClosed} closed</span>}
        </span>
      </div>

      {/* Filter bar */}
      <div className="pos-filter-bar">
        <div className="pos-filter-group">
          <label className="pos-filter-label">Status</label>
          <select
            className="pos-filter-select"
            value={filters.status}
            onChange={e => setFilter('status', e.target.value)}
          >
            <option value="all">All</option>
            <option value="active">Active</option>
            <option value="closed">Closed</option>
          </select>
        </div>

        <div className="pos-filter-group">
          <label className="pos-filter-label">Type</label>
          <select
            className="pos-filter-select"
            value={filters.source}
            onChange={e => setFilter('source', e.target.value)}
          >
            <option value="all">All</option>
            <option value="PAPER">Paper</option>
            <option value="LIVE">Live</option>
          </select>
        </div>

        <div className="pos-filter-group">
          <label className="pos-filter-label">Symbol</label>
          <input
            type="text"
            className="pos-filter-input"
            placeholder="e.g. MSFT"
            value={filters.symbol}
            onChange={e => setFilter('symbol', e.target.value)}
          />
        </div>

        <div className="pos-filter-group">
          <label className="pos-filter-label">Strategy</label>
          <select
            className="pos-filter-select"
            value={filters.strategy}
            onChange={e => setFilter('strategy', e.target.value)}
          >
            <option value="all">All</option>
            {STRATEGY_ORDER.map(k => (
              <option key={k} value={k}>{STRATEGY_LABELS[k]}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
          Loading positions...
        </div>
      )}

      {/* Error state */}
      {!loading && error && (
        <div style={{ padding: '20px', textAlign: 'center', color: '#ef4444', fontSize: 13 }}>
          {error}
          <button
            onClick={fetchPositions}
            style={{ marginLeft: 12, fontSize: 12, cursor: 'pointer', color: 'var(--accent-cyan)', background: 'none', border: 'none' }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Strategy groups */}
      {!loading && !error && grouped.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">◈</div>
          <h3>No positions yet</h3>
          <p>Follow a trade from the analysis screens to create your first position.</p>
        </div>
      )}

      {!loading && !error && grouped.map(({ key, positions: grpPositions }) => (
        <StrategyGroup
          key={key}
          strategyKey={key}
          positions={grpPositions}
          onClose={handleClose}
          onView={handleView}
        />
      ))}

      {/* Close confirmation modal */}
      {closeModal && (
        <CloseModal
          pos={closeModal}
          onCancel={() => setCloseModal(null)}
          onConfirm={handleCloseConfirm}
          closing={closing}
        />
      )}
    </div>
  );
}
