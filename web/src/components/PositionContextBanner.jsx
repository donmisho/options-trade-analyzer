/**
 * PositionContextBanner — OTA-173
 *
 * Displays a non-blocking amber banner when the user has open positions in the
 * active symbol. Dismissable for the session. Renders nothing if no positions.
 *
 * Props: { symbol: string }
 */

import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { getPositions } from '../api/client';

export default function PositionContextBanner({ symbol }) {
  const navigate              = useNavigate();
  const [count, setCount]     = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const lastSymbol            = useRef(null);

  useEffect(() => {
    if (!symbol) return;
    // Reset dismiss state when symbol changes
    if (symbol !== lastSymbol.current) {
      setDismissed(false);
      lastSymbol.current = symbol;
    }

    let cancelled = false;
    getPositions({ symbol, status: 'FOLLOWING,LIVE' })
      .then(res => {
        if (cancelled) return;
        const positions = Array.isArray(res) ? res : (res?.positions ?? []);
        setCount(positions.length);
      })
      .catch(() => {
        if (!cancelled) setCount(0);
      });
    return () => { cancelled = true; };
  }, [symbol]);

  if (!symbol || count === 0 || dismissed) return null;

  const noun = count === 1 ? 'position' : 'positions';

  return (
    <div style={s.banner}>
      <span style={s.text}>
        You have <strong>{count}</strong> open {noun} in <strong>{symbol}</strong>.
      </span>
      <button
        style={s.viewBtn}
        onClick={() => navigate('/positions')}
      >
        View →
      </button>
      <button
        style={s.dismiss}
        onClick={() => setDismissed(true)}
        aria-label="Dismiss"
      >
        ×
      </button>
    </div>
  );
}

const s = {
  banner: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '8px 16px',
    background: 'rgba(245, 158, 11, 0.10)',
    borderLeft: '3px solid #f59e0b',
    fontSize: 13,
    color: '#e4e7ef',
  },
  text: {
    flex: 1,
  },
  viewBtn: {
    background: 'none',
    border: 'none',
    color: '#f59e0b',
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    padding: '0 4px',
  },
  dismiss: {
    background: 'none',
    border: 'none',
    color: '#6b7280',
    fontSize: 18,
    cursor: 'pointer',
    padding: '0 4px',
    lineHeight: 1,
  },
};
