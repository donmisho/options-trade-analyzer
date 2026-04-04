/**
 * SecurityStrategiesPage — Screen 1: Scan
 *
 * Route: /security-strategies
 * Purpose: Scan watchlist / positions for interesting symbols.
 * No Config drawer. No QuoteBar. No single-symbol analysis.
 *
 * Layout:
 *   Page title
 *   Filter bar: Source · Signal · Min score · Sort · "Scan now"
 *   Progress indicator (while scanning)
 *   Card grid: ScanCard per symbol (progressive render)
 *   Empty states
 */

import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { getWatchlist, getPositions, getStrategyScorecard, addWatchlistSymbol } from '../api/client';
import ScanCard from '../components/ScanCard';
import { useToast } from '../components/Toast';
import { C, mono } from '../styles/tokens';

// ─── Skeleton card (loading placeholder) ──────────────────────────────────
function SkeletonCard() {
  return (
    <div style={{
      border: `1px solid ${C.border}`,
      borderRadius: 6,
      padding: '12px',
      backgroundColor: C.card,
    }}>
      <div style={{ color: '#8b949e', fontSize: 10, fontFamily: mono, marginBottom: 10 }}>
        Loading...
      </div>
      {[0, 1, 2, 3].map(i => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <div style={{ width: 90, height: 8, borderRadius: 2, background: C.border }} />
          <div style={{ flex: 1, height: 3, borderRadius: 2, background: C.border }} />
          <div style={{ width: 38, height: 8, borderRadius: 2, background: C.border }} />
        </div>
      ))}
    </div>
  );
}

// ─── Failed card ───────────────────────────────────────────────────────────
function FailedCard({ symbol }) {
  return (
    <div style={{
      border: '1px solid rgba(248,113,113,0.4)',
      borderRadius: 6,
      padding: '12px',
      backgroundColor: C.card,
    }}>
      <span style={{ fontSize: 13, fontWeight: 700, color: '#e6edf3', fontFamily: mono }}>
        {symbol}
      </span>
      <div style={{ fontSize: 10, color: '#f87171', fontFamily: mono, marginTop: 6 }}>
        Failed to load
      </div>
    </div>
  );
}

// ─── Shared input styles ───────────────────────────────────────────────────
const selectStyle = {
  background: C.bg,
  border: `1px solid ${C.border}`,
  color: '#e6edf3',
  padding: '5px 8px',
  borderRadius: 4,
  fontSize: 11,
  fontFamily: mono,
  cursor: 'pointer',
};

const numInputStyle = {
  background: C.bg,
  border: `1px solid ${C.border}`,
  color: '#e6edf3',
  padding: '5px 8px',
  borderRadius: 4,
  fontSize: 11,
  fontFamily: mono,
  width: 60,
  textAlign: 'right',
};

// ─── Main component ────────────────────────────────────────────────────────
export default function SecurityStrategiesPage() {
  const { watchlist, addToWatchlist } = useApp();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [newSymbol, setNewSymbol] = useState('');

  async function handleAddSymbol() {
    const sym = newSymbol.trim().toUpperCase();
    if (!sym) return;
    if (watchlist.some(w => (typeof w === 'string' ? w : w.symbol) === sym)) {
      showToast({ type: 'info', message: `${sym} is already in your scan list` });
      setNewSymbol('');
      return;
    }
    try {
      await addWatchlistSymbol(sym);
      addToWatchlist(sym);
      setNewSymbol('');
      showToast({ type: 'success', message: `${sym} added to scan list` });
    } catch (err) {
      showToast({ type: 'error', message: `Failed to add ${sym}: ${err.message}` });
    }
  }

  const [filterSource,   setFilterSource]   = useState('watchlist');
  const [filterSignal,   setFilterSignal]   = useState('all');
  const [filterMinScore, setFilterMinScore] = useState(0);
  const [filterSort,     setFilterSort]     = useState('score');
  const [scanning,       setScanning]       = useState(false);
  const [results,        setResults]        = useState([]);
  const [errors,         setErrors]         = useState([]);
  const [progress,       setProgress]       = useState({ completed: 0, total: 0 });
  const [hasScanned,     setHasScanned]     = useState(false);

  // Load cached scan results on mount (show last scan instantly)
  useEffect(() => {
    try {
      const raw = localStorage.getItem('ota_scan_results');
      if (raw) {
        const { results: cached } = JSON.parse(raw);
        if (cached?.length > 0) {
          setResults(cached);
          setHasScanned(true);
        }
      }
    } catch (_) {
      // corrupt cache — ignore
    }
  }, []);

  // ── Scan orchestration ─────────────────────────────────────────────────
  const handleScan = async () => {
    setScanning(true);
    setResults([]);
    setErrors([]);
    setProgress({ completed: 0, total: 0 });
    setHasScanned(true);

    // Gather symbols from selected source
    let symbols = [];
    try {
      if (filterSource === 'watchlist' || filterSource === 'all') {
        const wl = await getWatchlist().catch(() => []);
        const wlSymbols = (wl || [])
          .map(w => (typeof w === 'string' ? w : w.symbol))
          .filter(Boolean);
        symbols.push(...wlSymbols);
      }
      if (filterSource === 'positions' || filterSource === 'all') {
        const resp = await getPositions({ status: 'all' }).catch(() => ({ positions: [] }));
        const posSymbols = [...new Set((resp?.positions || []).map(p => p.symbol))];
        symbols.push(...posSymbols);
      }
      // Deduplicate, preserve order
      symbols = [...new Set(symbols)];
    } catch (err) {
      setScanning(false);
      showToast({ type: 'error', message: `Scan failed: ${err.message || 'Could not load symbols'}` });
      return;
    }

    if (symbols.length === 0) {
      setScanning(false);
      showToast({ type: 'info', message: 'No symbols found for the selected source' });
      return;
    }

    const total = symbols.length;
    setProgress({ completed: 0, total });

    // Fan out with max 5 concurrent using chunked Promise.allSettled
    let completed = 0;
    for (let i = 0; i < symbols.length; i += 5) {
      const chunk = symbols.slice(i, i + 5);
      const settled = await Promise.allSettled(
        chunk.map(sym => getStrategyScorecard(sym))
      );

      // Append results progressively as each chunk resolves
      settled.forEach((result, idx) => {
        const sym = chunk[idx];
        completed++;
        if (result.status === 'fulfilled') {
          const data = result.value;
          const strats = data.strategies || [];
          const ivRaw = strats[0]?.best_trade?.iv_rank ?? strats[0]?.best_trade?.iv;
          setResults(prev => [...prev, {
            symbol:        sym,
            price:         data.quote?.price,
            change:        data.quote?.change,
            changePercent: data.quote?.change_pct,
            volume:        data.quote?.volume,
            relVolume:     data.quote?.rel_volume,
            signal:        data.sma_signal?.alignment || 'NEUTRAL',
            strategies:    strats,
            signalSummary: data.sma_signal?.summary || '',
            ivRank:        ivRaw,
          }]);
        } else {
          setErrors(prev => [...prev, { symbol: sym }]);
        }
      });

      setProgress({ completed, total });
    }

    setScanning(false);
    showToast({ type: 'info', message: `Scanned ${total} symbol${total !== 1 ? 's' : ''}` });

    // Persist results so returning to this page shows them instantly
    setResults(prev => {
      try {
        localStorage.setItem('ota_scan_results', JSON.stringify({ results: prev, timestamp: Date.now() }));
      } catch (_) { /* storage full — skip */ }
      return prev;
    });
  };

  // ── Apply client-side filters + sort ──────────────────────────────────
  const filtered = results
    .filter(r => {
      if (filterSignal === 'all') return true;
      return (r.signal || '').toUpperCase() === filterSignal.toUpperCase();
    })
    .filter(r => {
      const top = r.strategies.length > 0
        ? Math.max(...r.strategies.map(s => s.score ?? 0))
        : 0;
      return top >= filterMinScore;
    })
    .sort((a, b) => {
      if (filterSort === 'score') {
        const aTop = a.strategies.length > 0 ? Math.max(...a.strategies.map(s => s.score ?? 0)) : 0;
        const bTop = b.strategies.length > 0 ? Math.max(...b.strategies.map(s => s.score ?? 0)) : 0;
        return bTop - aTop;
      }
      if (filterSort === 'symbol') return a.symbol.localeCompare(b.symbol);
      if (filterSort === 'signal') return (a.signal || '').localeCompare(b.signal || '');
      return 0;
    });

  // ── Empty state flags ──────────────────────────────────────────────────
  const showNoWatchlist = !hasScanned
    && (filterSource === 'watchlist' || filterSource === 'all')
    && watchlist.length === 0;

  const showPreScan  = !hasScanned && !showNoWatchlist;
  const showNoMatch  = hasScanned && !scanning && results.length > 0 && filtered.length === 0;
  const showEmpty    = hasScanned && !scanning && results.length === 0 && errors.length === 0;

  // Show 3 skeleton cards while scanning (visual placeholder for in-flight items)
  const showSkeletons = scanning;

  return (
    <div style={{ backgroundColor: C.bg, minHeight: '100%', paddingBottom: 32 }}>

      {/* ── Page title ── */}
      <div style={{ padding: '12px 16px 10px', borderBottom: `1px solid ${C.border}` }}>
        <span style={{ fontSize: 16, fontWeight: 700, color: '#e6edf3', fontFamily: mono }}>
          Security Strategies
        </span>
      </div>

      {/* ── Filter bar ── */}
      <div style={{
        background: C.surface,
        padding: '12px 16px',
        borderBottom: `1px solid ${C.border}`,
        display: 'flex',
        gap: 12,
        alignItems: 'center',
        flexWrap: 'wrap',
      }}>
        {/* Source */}
        <select
          value={filterSource}
          onChange={e => setFilterSource(e.target.value)}
          style={selectStyle}
        >
          <option value="watchlist">Watchlist</option>
          <option value="positions">Positions</option>
          <option value="all">All</option>
        </select>

        {/* Signal */}
        <select
          value={filterSignal}
          onChange={e => setFilterSignal(e.target.value)}
          style={selectStyle}
        >
          <option value="all">All Signals</option>
          <option value="bullish">Bullish</option>
          <option value="bearish">Bearish</option>
          <option value="mixed">Mixed</option>
        </select>

        {/* Min score */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            fontSize: 10, color: '#8b949e', fontFamily: mono,
            letterSpacing: '0.04em', textTransform: 'uppercase',
          }}>
            Min Score
          </span>
          <input
            type="number"
            min={0} max={100}
            value={filterMinScore}
            onChange={e => setFilterMinScore(Number(e.target.value))}
            style={numInputStyle}
          />
        </div>

        {/* Sort */}
        <select
          value={filterSort}
          onChange={e => setFilterSort(e.target.value)}
          style={selectStyle}
        >
          <option value="score">Score ↓</option>
          <option value="symbol">Symbol A-Z</option>
          <option value="signal">Signal</option>
        </select>

        {/* Scan now */}
        <button
          onClick={handleScan}
          disabled={scanning}
          style={{
            background: 'rgba(45,212,191,0.1)',
            border: '1px solid rgba(45,212,191,0.4)',
            color: '#2dd4bf',
            padding: '7px 16px',
            borderRadius: 4,
            fontSize: 11,
            fontFamily: mono,
            cursor: scanning ? 'default' : 'pointer',
            opacity: scanning ? 0.5 : 1,
          }}
        >
          {scanning ? 'Scanning...' : 'Scan now'}
        </button>

        {/* Add symbol to watchlist */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto' }}>
          <input
            type="text"
            placeholder="Add symbol..."
            value={newSymbol}
            onChange={e => setNewSymbol(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleAddSymbol()}
            style={{
              ...selectStyle,
              width: 110,
              padding: '5px 8px',
              letterSpacing: '0.04em',
            }}
          />
          <button
            onClick={handleAddSymbol}
            style={{
              background: 'transparent',
              border: '1px solid #30363d',
              color: '#8b949e',
              padding: '5px 10px',
              borderRadius: 4,
              fontSize: 10,
              fontFamily: mono,
              cursor: 'pointer',
            }}
          >
            Add
          </button>
        </div>
      </div>

      {/* ── Progress ── */}
      {scanning && progress.total > 0 && (
        <div style={{ padding: '8px 16px', fontSize: 10, color: '#8b949e', fontFamily: mono }}>
          Scanning {progress.completed} of {progress.total} symbols...
        </div>
      )}

      {/* ── Content ── */}
      <div style={{ padding: '16px' }}>

        {/* Empty: no watchlist symbols yet */}
        {showNoWatchlist && (
          <div style={{
            textAlign: 'center', padding: '64px 16px',
            color: '#8b949e', fontSize: 12, fontFamily: mono,
          }}>
            Add symbols to your watchlist to scan
          </div>
        )}

        {/* Pre-scan default message */}
        {showPreScan && (
          <div style={{
            textAlign: 'center', padding: '64px 16px',
            color: '#8b949e', fontSize: 12, fontFamily: mono,
          }}>
            Select a source and click "Scan now" to analyze symbols
          </div>
        )}

        {/* Post-scan, all results filtered out */}
        {showNoMatch && (
          <div style={{
            textAlign: 'center', padding: '32px 16px',
            color: '#8b949e', fontSize: 12, fontFamily: mono,
          }}>
            No results match the current filters
          </div>
        )}

        {/* Post-scan, no data at all */}
        {showEmpty && (
          <div style={{
            textAlign: 'center', padding: '32px 16px',
            color: '#8b949e', fontSize: 12, fontFamily: mono,
          }}>
            No symbols found for the selected source
          </div>
        )}

        {/* Card grid */}
        {(filtered.length > 0 || showSkeletons || errors.length > 0) && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: 12,
          }}>
            {filtered.map(r => (
              <ScanCard
                key={r.symbol}
                {...r}
                onClick={() => navigate(`/trades?symbol=${r.symbol}`)}
              />
            ))}

            {showSkeletons && [0, 1, 2].map(i => (
              <SkeletonCard key={`sk-${i}`} />
            ))}

            {errors.map(e => (
              <FailedCard key={`err-${e.symbol}`} symbol={e.symbol} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
