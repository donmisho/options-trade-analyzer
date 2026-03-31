/**
 * StrategyPage — Placeholder for per-strategy detail page.
 *
 * Route: /strategies/:key
 *
 * Full implementation (parameters, weights, positions) comes in a later session.
 */

import { useParams } from 'react-router-dom';

export default function StrategyPage() {
  const { key } = useParams();

  return (
    <div style={{
      padding: '32px 20px',
      fontFamily: 'monospace',
      fontSize: 16,
      fontWeight: 700,
      color: '#e6edf3',
    }}>
      Strategy: {key} — under construction
    </div>
  );
}
