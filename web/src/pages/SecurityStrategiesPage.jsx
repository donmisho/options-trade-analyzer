/**
 * SecurityStrategiesPage — Screen 1: Scan
 *
 * Route: /security-strategies
 * Purpose: Scan watchlist / positions for interesting symbols.
 * No Config drawer. No QuoteBar. No single-symbol analysis.
 *
 * Layout:
 *   Page title
 *   Filter bar: Source (WatchlistPicker) · Signal · Min score · Sort · "Scan now" · Add symbol
 *   Progress indicator (while scanning)
 *   Card grid: ScanCard per symbol (progressive render)
 *   Empty states
 */

import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  getPositions,
  getStrategyScorecard,
  getWatchlistSymbols,
  addSymbolToWatchlist,
  removeSymbolFromWatchlist,
} from '../api/client';
import ScanCard from '../components/ScanCard';
import WatchlistPicker from '../components/WatchlistPicker';
import { useToast } from '../components/Toast';
import { C, mono } from '../styles/tokens';

// Source ID for the "All Positions" built-in scan source (matches backend)
const ALL_POSITIONS_SOURCE_ID = 'all-positions';

// Cache version — bump when cache shape changes to invalidate stale entries
const CACHE_VERSION = 1;

/**
 * Reads the per-watchlist scan cache from localStorage.
 * Returns the map (possibly empty). Handles legacy single-object form by discarding it.
 */
function readScanCache() {
  try {
    const raw = localStorage.getItem('ota_scan_results');
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    // Legacy shape detection: old form has top-level `sourceId` + `results` + `timestamp`
    if (parsed.sourceId !== undefined && parsed.results !== undefined && parsed.timestamp !== undefined) {
      // Discard legacy — replace with empty map
      localStorage.setItem('ota_scan_results', JSON.stringify({}));
      return {};
    }
    return parsed || {};
  } catch {
    localStorage.setItem('ota_scan_results', JSON.stringify({}));
    return {};
  }
}

/**
 * Writes a single watchlist entry into the per-watchlist scan cache.
 * Preserves all other entries.
 */
function writeScanCacheEntry(sourceId, results) {
  try {
    const cache = readScanCache();
    cache[sourceId] = {
      results,
      scanned_at: new Date().toISOString(),
      version: CACHE_VERSION,
    };
    localStorage.setItem('ota_scan_results', JSON.stringify(cache));
  } catch { /* storage full — skip */ }
}

/**
 * Reads a single entry from the per-watchlist cache.
 * Returns { results, scanned_at } or null if missing/version mismatch.
 */
function readScanCacheEntry(sourceId) {
  const cache = readScanCache();
  const entry = cache[sourceId];
  if (!entry) return null;
  if (entry.version !== CACHE_VERSION) return null;
  return { results: entry.results || [], scanned_at: entry.scanned_at };
}

/**
 * Reads strategy overrides from localStorage at scan time (not mount time).
 * Returns the full strategyOverrides map { [strategyKey]: { dte_min, dte_max, ... } }
 * or null if missing, empty, or unparseable.
 * Returning null causes the API client to omit user_config — backend uses STRATEGIES defaults.
 */
function readStrategyOverrides() {
  try {
    const stored = JSON.parse(localStorage.getItem('analysisConfig') || '{}');
    const overrides = stored.strategyOverrides;
    if (!overrides || Object.keys(overrides).length === 0) return null;
    return overrides;
  } catch (e) {
    console.warn('[OTA-512] Failed to parse analysisConfig from localStorage:', e);
    return null;
  }
}

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

// ─── Build a scan result object from a scorecard API response ─────────────
// Used by both handleScan (bulk) and handleAddSymbol (single). extra is merged
// last so callers can override fields (e.g. isNew: true for manual adds).
function buildScanResult(sym, data, extra = {}) {
  const strats = data.strategies || [];
  const ivRaw = strats[0]?.best_trade?.iv_rank ?? strats[0]?.best_trade?.iv;
  return {
    symbol:        sym,
    description:   data.quote?.description || '',
    price:         data.quote?.price,
    change:        data.quote?.change,
    changePercent: data.quote?.change_pct,
    volume:        data.quote?.volume,
    relVolume:     data.quote?.rel_volume,
    signal:        data.sma_signal?.alignment || 'NEUTRAL',
    strategies:    strats,
    signalSummary: data.sma_signal?.summary || '',
    ivRank:        ivRaw,
    ...extra,
  };
}

// ─── Main component ────────────────────────────────────────────────────────
export default function SecurityStrategiesPage() {
  const navigate = useNavigate();
  const { showToast } = useToast();

  // ── Source selection (WatchlistPicker) ─────────────────────────────────
  const [selectedSource, setSelectedSource] = useState(null);

  // ── Track scanned_at for "Last scanned X ago" indicator ────────────────
  const [scannedAt, setScannedAt] = useState(null);

  function handleSourceChange(source) {
    setSelectedSource(source);
    setErrors([]);

    // Read per-watchlist cache for this source
    const entry = source?.id ? readScanCacheEntry(source.id) : null;
    if (entry && entry.results.length > 0) {
      setResults(entry.results);
      setScannedAt(entry.scanned_at);
      setHasScanned(true);
    } else {
      setResults([]);
      setScannedAt(null);
      setHasScanned(false);
    }
  }

  // ── Add symbol ─────────────────────────────────────────────────────────
  const [newSymbol, setNewSymbol] = useState('');
  const [addError, setAddError]   = useState('');

  const isWatchlistSource = selectedSource?.type === 'watchlist';

  async function handleAddSymbol() {
    const sym = newSymbol.trim().toUpperCase();
    if (!sym || !isWatchlistSource) return;
    setAddError('');

    if (results.some(r => r.symbol === sym)) {
      showToast({ type: 'info', message: `${sym} is already in scan results` });
      setNewSymbol('');
      return;
    }

    try {
      await addSymbolToWatchlist(selectedSource.id, sym);
      setNewSymbol('');
      // Update local count
      setSelectedSource(prev => ({ ...prev, symbolCount: (prev.symbolCount || 0) + 1 }));

      // Trigger single-symbol scorecard and append card
      try {
        const data = await getStrategyScorecard(sym, readStrategyOverrides());
        setResults(prev => [...prev, buildScanResult(sym, data, { isNew: true })]);
      } catch {
        // Symbol added to watchlist but scorecard failed — that's OK
      }

      showToast({ type: 'success', message: `${sym} added to watchlist` });
    } catch (err) {
      setAddError(err.message || `Failed to add ${sym}`);
    }
  }

  // ── Remove symbol from watchlist + grid ────────────────────────────────
  async function handleRemoveSymbol(symbol) {
    if (!isWatchlistSource) return;
    try {
      await removeSymbolFromWatchlist(selectedSource.id, symbol);
      setResults(prev => prev.filter(r => r.symbol !== symbol));
      setSelectedSource(prev => ({ ...prev, symbolCount: Math.max(0, (prev.symbolCount || 1) - 1) }));
      showToast({ type: 'success', message: `${symbol} removed from watchlist` });
    } catch (err) {
      showToast({ type: 'error', message: `Failed to remove ${symbol}: ${err.message}` });
    }
  }

  // ── Scan state ──────────────────────────────────────────────────────────
  const [filterSignal,   setFilterSignal]   = useState('all');
  const [filterMinScore, setFilterMinScore] = useState(0);
  const [filterSort,     setFilterSort]     = useState('score');
  const [scanning,       setScanning]       = useState(false);
  const [results,        setResults]        = useState([]);
  const [errors,         setErrors]         = useState([]);
  const [progress,       setProgress]       = useState({ completed: 0, total: 0 });
  const [hasScanned,     setHasScanned]     = useState(false);

  // On mount: migrate legacy cache if needed (readScanCache handles this).
  // Actual cache hydration happens in handleSourceChange when WatchlistPicker
  // fires its initial auto-select. No need to hydrate here.
  useEffect(() => {
    readScanCache(); // triggers legacy migration if needed
  }, []);

  // 60s interval to re-render relative time on cards
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 60_000);
    return () => clearInterval(id);
  }, []);

  // ── Scan orchestration ──────────────────────────────────────────────────
  const handleScan = async () => {
    setScanning(true);
    setResults([]);
    setErrors([]);
    setProgress({ completed: 0, total: 0 });
    setHasScanned(true);
    setAddError('');

    let symbols = [];
    try {
      if (selectedSource?.type === 'watchlist') {
        const data = await getWatchlistSymbols(selectedSource.id).catch(() => []);
        symbols = (data || []).map(s => (typeof s === 'string' ? s : s.symbol)).filter(Boolean);
      } else if (selectedSource?.id === ALL_POSITIONS_SOURCE_ID) {
        const resp = await getPositions({ status: 'all' }).catch(() => ({ positions: [] }));
        symbols = [...new Set((resp?.positions || []).map(p => p.symbol))];
      }
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

    // Fan out with max 5 concurrent; accumulate final list for localStorage
    let completed = 0;
    const finalResults = [];
    for (let i = 0; i < symbols.length; i += 5) {
      const chunk = symbols.slice(i, i + 5);
      const settled = await Promise.allSettled(
        chunk.map(sym => getStrategyScorecard(sym, readStrategyOverrides()))
      );

      settled.forEach((result, idx) => {
        const sym = chunk[idx];
        completed++;
        if (result.status === 'fulfilled') {
          const item = buildScanResult(sym, result.value);
          finalResults.push(item);
          setResults(prev => [...prev, item]);
        } else {
          setErrors(prev => [...prev, { symbol: sym }]);
        }
      });

      setProgress({ completed, total });
    }

    setScanning(false);
    showToast({ type: 'info', message: `Scanned ${total} symbol${total !== 1 ? 's' : ''}` });

    // Persist results for this watchlist only — other entries preserved
    if (selectedSource?.id) {
      writeScanCacheEntry(selectedSource.id, finalResults);
      setScannedAt(new Date().toISOString());
    }
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
    && isWatchlistSource
    && (selectedSource?.symbolCount ?? 0) === 0;

  const showPreScan  = !hasScanned && !showNoWatchlist;
  const showNoMatch  = hasScanned && !scanning && results.length > 0 && filtered.length === 0;
  const showEmpty    = hasScanned && !scanning && results.length === 0 && errors.length === 0;
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
        {/* Source — WatchlistPicker */}
        <WatchlistPicker
          selectedSource={selectedSource}
          onSourceChange={handleSourceChange}
        />

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

        {/* Add symbol to current watchlist */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginLeft: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="text"
              placeholder={isWatchlistSource ? 'Add symbol…' : 'Select a watchlist to add'}
              value={newSymbol}
              onChange={e => { setNewSymbol(e.target.value.toUpperCase()); setAddError(''); }}
              onKeyDown={e => e.key === 'Enter' && handleAddSymbol()}
              disabled={!isWatchlistSource || scanning}
              title={!isWatchlistSource ? 'Select a watchlist to add symbols' : undefined}
              style={{
                ...selectStyle,
                width: isWatchlistSource ? 110 : 160,
                padding: '5px 8px',
                letterSpacing: '0.04em',
                opacity: !isWatchlistSource ? 0.5 : 1,
                cursor: !isWatchlistSource ? 'not-allowed' : 'text',
              }}
            />
            <button
              onClick={handleAddSymbol}
              disabled={!isWatchlistSource || scanning || !newSymbol.trim()}
              style={{
                background: 'transparent',
                border: '1px solid #30363d',
                color: '#8b949e',
                padding: '5px 10px',
                borderRadius: 4,
                fontSize: 10,
                fontFamily: mono,
                cursor: isWatchlistSource && newSymbol.trim() ? 'pointer' : 'not-allowed',
                opacity: (!isWatchlistSource || !newSymbol.trim()) ? 0.5 : 1,
              }}
            >
              Add
            </button>
          </div>
          {addError && (
            <span style={{ fontSize: 10, color: C.red, fontFamily: mono }}>
              {addError}
            </span>
          )}
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

        {/* Empty: watchlist has no symbols */}
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
            {selectedSource
              ? `Click "Scan now" to analyze ${selectedSource.name}`
              : 'Select a source and click "Scan now" to analyze symbols'}
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
                scannedAt={scannedAt}
                onClick={() => navigate(`/trades?symbol=${r.symbol}`)}
                onRemove={isWatchlistSource ? () => handleRemoveSymbol(r.symbol) : undefined}
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
