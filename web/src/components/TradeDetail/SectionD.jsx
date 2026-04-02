import { useState, useEffect, useRef } from 'react';
import ProbabilityMatrix from '../ProbabilityMatrix';
import { getProbabilityMatrix } from '../../api/client';

const sectionLabelStyle = {
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: '0.6px',
  color: 'var(--muted)',
  fontFamily: 'monospace',
  margin: '16px 0 8px',
};

const placeholderStyle = {
  border: '1px solid var(--border)',
  borderRadius: 4,
  padding: 20,
  textAlign: 'center',
};

function makeFetchKey(trade, symbol, currentPrice) {
  if (!trade || !symbol || !currentPrice) return '';
  return `${symbol}|${currentPrice}|${trade.iv ?? ''}|${trade.dte ?? ''}|${trade.expiration ?? ''}`;
}

export default function SectionD({ trade, symbol, currentPrice, breakeven }) {
  const [matrixData, setMatrixData] = useState(null);
  const [error, setError] = useState(null);
  const [completedKey, setCompletedKey] = useState('');

  const currentKey = makeFetchKey(trade, symbol, currentPrice);
  // Derive loading: a trade exists but we haven't completed a fetch for it yet
  const loading = !!currentKey && currentKey !== completedKey && !error;

  const cancelRef = useRef(null);

  useEffect(() => {
    if (!trade || !currentPrice || !symbol) return;

    const key = makeFetchKey(trade, symbol, currentPrice);
    // Already fetched for this exact combination
    if (key === completedKey) return;

    // Prevent superseded fetch from writing state
    if (cancelRef.current) cancelRef.current();
    let cancelled = false;
    cancelRef.current = () => { cancelled = true; };

    const dte = trade.dte != null
      ? Math.max(1, trade.dte)
      : trade.expiration
      ? Math.max(1, Math.round((new Date(trade.expiration) - new Date()) / 86400000))
      : 30;

    getProbabilityMatrix({
      symbol,
      current_price: currentPrice,
      iv: trade.iv || 0.25,
      dte,
    })
      .then(data => {
        if (!cancelled) {
          setError(null);
          setMatrixData(data);
          setCompletedKey(key);
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(err.message || 'Failed to load probability matrix');
          setMatrixData(null);
          setCompletedKey(key);
        }
      });

    return () => { cancelled = true; };
  }, [trade, symbol, currentPrice]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <div style={sectionLabelStyle}>PROBABILITY MATRIX</div>

      {loading && (
        <div style={placeholderStyle}>
          <span style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'monospace' }}>
            Computing probability matrix…
          </span>
        </div>
      )}

      {!loading && error && (
        <div style={placeholderStyle}>
          <span style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'monospace' }}>
            Probability matrix — {error}
          </span>
        </div>
      )}

      {!loading && !error && matrixData && (
        <ProbabilityMatrix
          matrix={matrixData}
          currentPrice={currentPrice}
          tradeStructure={trade ? {
            spread_type: trade.spread_type,
            short_strike: trade.short_strike,
            long_strike: trade.long_strike,
          } : null}
          breakeven={breakeven ?? null}
        />
      )}

      {!loading && !error && !matrixData && (
        <div style={placeholderStyle}>
          <span style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'monospace' }}>
            Probability matrix — expand a trade row to compute
          </span>
        </div>
      )}
    </div>
  );
}
