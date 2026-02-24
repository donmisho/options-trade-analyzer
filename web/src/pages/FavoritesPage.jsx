/**
 * FavoritesPage — Shows all saved favorites with sortable columns.
 *
 * WHY this is fully functional in Layer 1:
 * Unlike the analysis screens (which need API data), favorites are
 * stored in localStorage via AppContext. So we can build the complete
 * Favorites experience right away: sortable table, expiry countdown,
 * remove button, empty state.
 *
 * The "Current Price" column and refresh button will be wired to the
 * /market/quote API in Layer 2. For now they show the original price.
 */

import { useState, useMemo } from 'react';
import { useApp } from '../context/AppContext';
import ScoreBar from '../components/ScoreBar';
import './PageShared.css';
import './FavoritesPage.css';

// ─── Helpers ──────────────────────────────────────────────

function daysRemaining(savedAt) {
  const elapsed = Date.now() - savedAt;
  const remaining = 30 - Math.floor(elapsed / (24 * 60 * 60 * 1000));
  return Math.max(0, remaining);
}

function formatDate(isoString) {
  const d = new Date(isoString);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function sourceLabel(source) {
  const map = {
    vertical: { text: 'Vertical Spread', cls: 'type-bull' },
    longcall: { text: 'Long Call', cls: 'type-long' },
    directional: { text: 'Directional', cls: 'type-directional' },
  };
  return map[source] || { text: source, cls: '' };
}

function expiryColor(days) {
  if (days >= 20) return 'var(--accent-green)';
  if (days >= 10) return 'var(--accent-yellow)';
  return 'var(--accent-orange)';
}

// ─── Component ────────────────────────────────────────────

export default function FavoritesPage() {
  const { favorites, removeFavorite, showToast } = useApp();

  // Sort state
  const [sortCol, setSortCol] = useState('saved');
  const [sortDir, setSortDir] = useState('desc');

  const handleSort = (column) => {
    if (sortCol === column) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortCol(column);
      // Default direction that makes sense for each column
      setSortDir(column === 'score' ? 'desc' : 'asc');
    }
  };

  const sortedFavorites = useMemo(() => {
    const arr = [...favorites];
    arr.sort((a, b) => {
      let valA, valB;
      switch (sortCol) {
        case 'trade':
          valA = (a.label || '').toLowerCase();
          valB = (b.label || '').toLowerCase();
          return sortDir === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
        case 'source':
          valA = a.source || '';
          valB = b.source || '';
          return sortDir === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
        case 'saved':
          valA = a.savedAt || 0;
          valB = b.savedAt || 0;
          return sortDir === 'asc' ? valA - valB : valB - valA;
        case 'score':
          valA = a.score || 0;
          valB = b.score || 0;
          return sortDir === 'asc' ? valA - valB : valB - valA;
        case 'expires':
          valA = daysRemaining(a.savedAt);
          valB = daysRemaining(b.savedAt);
          return sortDir === 'asc' ? valA - valB : valB - valA;
        default:
          return 0;
      }
    });
    return arr;
  }, [favorites, sortCol, sortDir]);

  // Column header with sort indicator
  const SortTh = ({ column, children }) => {
    const isActive = sortCol === column;
    let cls = 'sortable';
    if (isActive) cls += sortDir === 'asc' ? ' sort-asc' : ' sort-desc';
    return (
      <th className={cls} onClick={() => handleSort(column)}>
        {children}
      </th>
    );
  };

  // ─── Empty state ─────────────────────────────────────────
  if (favorites.length === 0) {
    return (
      <div className="page-card">
        <h2 className="page-title"><span className="icon">★</span> Saved Favorites</h2>
        <div className="empty-state">
          <div className="empty-icon">☆</div>
          <h3>No favorites yet</h3>
          <p>
            Click the star icon on any trade in the Vertical Spreads, Long Calls,
            or Directional Compare screens to save it here for 30 days.
          </p>
        </div>
      </div>
    );
  }

  // ─── Favorites table ─────────────────────────────────────
  return (
    <div className="page-card">
      <h2 className="page-title"><span className="icon">★</span> Saved Favorites</h2>
      <p className="page-subtitle">
        Click any column header to sort. Favorites auto-expire after 30 days.
        Click ⟳ to refresh current pricing.
      </p>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th style={{ width: 32 }}></th>
              <SortTh column="trade">Trade</SortTh>
              <SortTh column="source">Source</SortTh>
              <SortTh column="saved">Saved</SortTh>
              <th>Original Price</th>
              <th>Current Price</th>
              <th>Change</th>
              <SortTh column="score">Score</SortTh>
              <SortTh column="expires">Expires</SortTh>
              <th style={{ width: 32 }}></th>
            </tr>
          </thead>
          <tbody>
            {sortedFavorites.map((fav) => {
              const days = daysRemaining(fav.savedAt);
              const { text, cls } = sourceLabel(fav.source);
              const pctLeft = Math.round((days / 30) * 100);
              return (
                <tr key={fav.id}>
                  <td>
                    <button className="star-btn favorited">★</button>
                  </td>
                  <td>
                    <span className="mono text-cyan">{fav.symbol}</span>{' '}
                    <span className="mono">{fav.label}</span>
                    {fav.expiration && (
                      <span className="mono text-muted" style={{ fontSize: 11, marginLeft: 4 }}>
                        · {fav.expiration}
                      </span>
                    )}
                  </td>
                  <td>
                    <span className={`type-badge ${cls}`}>{text}</span>
                  </td>
                  <td className="mono text-muted" style={{ fontSize: 12 }}>
                    {formatDate(fav.savedDate)}
                  </td>
                  <td>
                    <span className="fav-orig mono">{fav.originalPrice || '—'}</span>
                  </td>
                  <td>
                    <span className="mono">—</span>{' '}
                    <span
                      className="refresh-btn"
                      title="Refresh pricing"
                      onClick={() => showToast(`Pricing refreshed for ${fav.label}`)}
                    >
                      ⟳
                    </span>
                  </td>
                  <td><span className="mono text-muted">—</span></td>
                  <td>
                    {fav.score ? <ScoreBar score={fav.score} /> : <span className="mono text-muted">—</span>}
                  </td>
                  <td>
                    <span
                      className="fav-days-left"
                      style={{ color: expiryColor(days) }}
                    >
                      {days}d
                    </span>
                    <div className="fav-days-bar">
                      <div
                        className="fav-days-fill"
                        style={{ width: `${pctLeft}%`, background: expiryColor(days) }}
                      />
                    </div>
                  </td>
                  <td>
                    <button
                      className="remove-btn"
                      title="Remove"
                      onClick={() => removeFavorite(fav.id)}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
