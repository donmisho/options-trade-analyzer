/**
 * SymbolSearch — Type-ahead symbol picker with two-tier results.
 *
 * Tier 1: symbols with active positions — Emerald Teal (#00C896), bold, position count badge
 * Tier 2: all other market symbols — muted color, no badge
 *
 * Props (framework-portable):
 *   onSelect(symbol)   — called when user selects a result
 *   placeholder        — input placeholder text
 *   searchFn           — async (query) => [{ symbol, companyName }]  (injected, not hardcoded)
 *   positionSymbols    — [{ symbol, position_count }] from AppContext
 *   initialValue       — optional pre-populated value (null = show placeholder on load)
 */

import { useState, useEffect, useReducer, useRef } from 'react';

const TIER1_COLOR = '#00C896';
const DROPDOWN_BG = '#0D1117';

// ── Reducer: batch results + open + highlighted into one dispatch ──────────────
function dropdownReducer(state, action) {
  switch (action.type) {
    case 'SET_RESULTS':
      return { results: action.results, open: action.results.length > 0, highlighted: 0 };
    case 'CLOSE':
      return { results: state.results, open: false, highlighted: 0 };
    case 'HIGHLIGHT':
      return { results: state.results, open: state.open, highlighted: action.i };
    default:
      return state;
  }
}

const CLOSED = { results: [], open: false, highlighted: 0 };

export default function SymbolSearch({
  onSelect,
  placeholder = 'Search symbol...',
  searchFn,
  positionSymbols = [],
  initialValue = null,
}) {
  const [query, setQuery] = useState(initialValue || '');
  const [dropdown, dispatch] = useReducer(dropdownReducer, CLOSED);

  const inputRef = useRef(null);
  const containerRef = useRef(null);
  const isProgrammatic = useRef(false);

  // When initialValue changes (e.g. Scan card navigation), update input
  // without triggering the search effect.
  useEffect(() => {
    isProgrammatic.current = true;
    setQuery(initialValue || '');
    dispatch({ type: 'CLOSE' });
  }, [initialValue]); // eslint-disable-line react-hooks/exhaustive-deps

  // Run searchFn whenever query changes (skip programmatic updates)
  useEffect(() => {
    const q = query.trim();
    if (!q || !searchFn) {
      dispatch({ type: 'CLOSE' });
      return;
    }
    if (isProgrammatic.current) {
      isProgrammatic.current = false;
      return;
    }
    let cancelled = false;
    searchFn(q).then(r => {
      if (cancelled) return;
      dispatch({ type: 'SET_RESULTS', results: r || [] });
    });
    return () => { cancelled = true; };
  }, [query, searchFn]);

  // Close on outside click
  useEffect(() => {
    function handleMouseDown(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        dispatch({ type: 'CLOSE' });
      }
    }
    document.addEventListener('mousedown', handleMouseDown);
    return () => document.removeEventListener('mousedown', handleMouseDown);
  }, []);

  // Build position count lookup for O(1) access
  const positionMap = {};
  for (const ps of positionSymbols) {
    positionMap[ps.symbol] = ps.position_count;
  }

  // Sort: Tier 1 (with positions) first, then Tier 2 alphabetically within each tier
  const sorted = [...dropdown.results].sort((a, b) => {
    const aT1 = !!positionMap[a.symbol];
    const bT1 = !!positionMap[b.symbol];
    if (aT1 && !bT1) return -1;
    if (!aT1 && bT1) return 1;
    return a.symbol.localeCompare(b.symbol);
  });

  function handleKeyDown(e) {
    if (!dropdown.open) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      dispatch({ type: 'HIGHLIGHT', i: Math.min(dropdown.highlighted + 1, sorted.length - 1) });
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      dispatch({ type: 'HIGHLIGHT', i: Math.max(dropdown.highlighted - 1, 0) });
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (sorted[dropdown.highlighted]) selectItem(sorted[dropdown.highlighted]);
    } else if (e.key === 'Escape') {
      dispatch({ type: 'CLOSE' });
    }
  }

  function selectItem(item) {
    setQuery(item.symbol);
    dispatch({ type: 'CLOSE' });
    onSelect(item.symbol);
  }

  return (
    <div
      ref={containerRef}
      style={{ position: 'relative', flex: 1, maxWidth: 300 }}
    >
      <input
        ref={inputRef}
        value={query}
        onChange={e => setQuery(e.target.value.toUpperCase())}
        onKeyDown={handleKeyDown}
        onFocus={() => { if (sorted.length > 0) dispatch({ type: 'SET_RESULTS', results: dropdown.results }); }}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        style={{
          width: '100%',
          padding: '6px 10px',
          borderRadius: 6,
          border: '1px solid var(--border, #2a2a3a)',
          backgroundColor: 'var(--surface, #161622)',
          color: 'var(--text, #e0e0f0)',
          fontSize: 13,
          fontFamily: 'monospace',
          outline: 'none',
          boxSizing: 'border-box',
        }}
      />

      {dropdown.open && sorted.length > 0 && (
        <div style={{
          position: 'absolute',
          top: '100%',
          left: 0,
          right: 0,
          zIndex: 1200,
          backgroundColor: DROPDOWN_BG,
          border: '1px solid var(--border, #2a2a3a)',
          borderRadius: 6,
          marginTop: 3,
          maxHeight: 260,
          overflowY: 'auto',
          boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
        }}>
          {sorted.map((item, i) => {
            const posCount = positionMap[item.symbol];
            const isTier1 = !!posCount;
            const isHighlighted = i === dropdown.highlighted;

            return (
              <div
                key={item.symbol}
                onMouseDown={() => selectItem(item)}
                onMouseEnter={() => dispatch({ type: 'HIGHLIGHT', i })}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '7px 12px',
                  cursor: 'pointer',
                  backgroundColor: isHighlighted ? 'rgba(255,255,255,0.06)' : 'transparent',
                }}
              >
                {/* Symbol */}
                <span style={{
                  minWidth: 52,
                  fontFamily: 'monospace',
                  fontSize: 13,
                  fontWeight: isTier1 ? 700 : 400,
                  color: isTier1 ? TIER1_COLOR : 'var(--text-muted, #888)',
                }}>
                  {item.symbol}
                </span>

                {/* Company name */}
                {item.companyName && (
                  <span style={{
                    fontSize: 12,
                    color: isTier1 ? TIER1_COLOR : 'var(--text-muted, #888)',
                    opacity: isTier1 ? 0.85 : 0.65,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    — {item.companyName}
                  </span>
                )}

                {/* Tier 1 badge */}
                {isTier1 && (
                  <span style={{
                    marginLeft: 'auto',
                    flexShrink: 0,
                    fontSize: 10,
                    fontWeight: 700,
                    color: TIER1_COLOR,
                    backgroundColor: 'rgba(0,200,150,0.15)',
                    borderRadius: 4,
                    padding: '1px 7px',
                    whiteSpace: 'nowrap',
                  }}>
                    {posCount} position{posCount !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
