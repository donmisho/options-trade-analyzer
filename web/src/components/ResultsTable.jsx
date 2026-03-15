/**
 * ResultsTable — Pure display component for scored trade results.
 *
 * Accepts a `columns` prop array describing exactly what to render.
 * Never hardcodes column definitions — those live in web/src/config/.
 *
 * Manages sort state internally. Calls onRowClick(null) when a sort
 * header is clicked so the parent can collapse any open expansion row.
 *
 * Props:
 *   results            — array of trade objects
 *   columns            — column config array (see web/src/config/*.jsx)
 *   context            — object passed as 2nd arg to each col.render fn
 *                        (e.g. { currentPrice, systemVars, idx })
 *   expandedRowId      — id of currently expanded row (controlled by parent)
 *   onRowClick         — called with (id) when row clicked; null = collapse
 *   renderExpansionRow — (trade) => ReactNode rendered in the expanded <tr>
 *   getRowId           — optional (trade, idx) => string; defaults to String(idx)
 *   defaultSortKey     — initial sort column key (default 'composite_score')
 *   defaultSortDir     — initial sort direction (default 'desc')
 */

import { useState, useMemo } from 'react';
import { C, mono } from '../styles/tokens';

const SURFACE = C.surface;
const BORDER  = C.border;
const TEXT    = C.text;
const MUTED   = C.textMuted;
const ACCENT  = C.accent;
const TEAL    = '#2dd4bf';

// Returns the sort key for a column — uses sortKey override if defined, else col.key
function getSortKey(col) {
  return col.sortKey || col.key;
}

export default function ResultsTable({
  results = [],
  columns = [],
  context,
  expandedRowId,
  onRowClick,
  renderExpansionRow,
  getRowId,
  defaultSortKey = 'composite_score',
  defaultSortDir = 'desc',
}) {
  const [sortColumn,    setSortColumn]    = useState(defaultSortKey);
  const [sortDirection, setSortDirection] = useState(defaultSortDir);

  const handleSort = (col) => {
    // Collapse any open expansion row before reordering
    onRowClick?.(null);
    const sk = getSortKey(col);
    if (sortColumn === sk) {
      setSortDirection(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(sk);
      setSortDirection('desc');
    }
  };

  const sortedResults = useMemo(() => {
    if (!results || results.length === 0) return [];
    return [...results].sort((a, b) => {
      const aVal = a[sortColumn] ?? 0;
      const bVal = b[sortColumn] ?? 0;
      const dir  = sortDirection === 'asc' ? 1 : -1;
      if (typeof aVal === 'string') return aVal.localeCompare(bVal) * dir;
      return (aVal - bVal) * dir;
    });
  }, [results, sortColumn, sortDirection]);

  const rowId = (trade, idx) => (getRowId ? getRowId(trade, idx) : String(idx));

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: mono, fontSize: 12 }}>
      <thead>
        <tr style={{ backgroundColor: C.surfaceAlt, borderBottom: `1px solid ${BORDER}` }}>
          {columns.map(col => {
            const isSortable = col.sortable !== false;
            const sk         = getSortKey(col);
            const isActive   = isSortable && sortColumn === sk;
            return (
              <th
                key={col.key}
                onClick={isSortable ? () => handleSort(col) : undefined}
                title={col.title}
                style={{
                  padding: '6px 8px',
                  textAlign: col.align || 'right',
                  color: isActive ? TEAL : MUTED,
                  fontWeight: 600,
                  fontSize: 10,
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                  whiteSpace: 'nowrap',
                  width: col.width,
                  cursor: isSortable ? 'pointer' : 'default',
                  userSelect: 'none',
                }}
              >
                {col.label}
                {isActive && (
                  <span style={{ marginLeft: 4, fontSize: 9, color: TEAL }}>
                    {sortDirection === 'desc' ? '▼' : '▲'}
                  </span>
                )}
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {sortedResults.map((trade, idx) => {
          const id         = rowId(trade, idx);
          const isExpanded = id === expandedRowId;
          const ctx        = { ...(context || {}), idx };

          return [
            <tr
              key={`row-${id}`}
              onClick={() => onRowClick?.(isExpanded ? null : id)}
              style={{
                cursor: 'pointer',
                borderLeft: `3px solid ${isExpanded ? ACCENT : 'transparent'}`,
                backgroundColor: isExpanded ? ACCENT + '08' : 'transparent',
                borderBottom: `1px solid ${BORDER}`,
                transition: 'background 0.1s',
              }}
              onMouseEnter={e => { if (!isExpanded) e.currentTarget.style.backgroundColor = SURFACE; }}
              onMouseLeave={e => { if (!isExpanded) e.currentTarget.style.backgroundColor = 'transparent'; }}
            >
              {columns.map((col, ci) => {
                const content = col.render
                  ? col.render(trade, ctx)
                  : (trade[col.key] ?? '—');

                return (
                  <td
                    key={ci}
                    title={col.title}
                    style={{
                      padding: col.key === 'composite_score' ? '4px 8px' : '6px 8px',
                      textAlign: col.align || 'right',
                      color: TEXT,
                    }}
                  >
                    {content}
                  </td>
                );
              })}
            </tr>,

            isExpanded && renderExpansionRow && (
              <tr key={`exp-${id}`}>
                <td colSpan={columns.length} style={{ padding: 0 }}>
                  {renderExpansionRow(trade)}
                </td>
              </tr>
            ),
          ].filter(Boolean);
        })}
      </tbody>
    </table>
  );
}
