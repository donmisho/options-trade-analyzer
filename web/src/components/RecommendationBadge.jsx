/**
 * RecommendationBadge — Inline badge for results table rows.
 *
 * Shows ✦ EXECUTE / ✦ WAIT / ✦ PASS in the appropriate color.
 * Clicking it opens the Trade Agent Panel with that trade pre-loaded,
 * which will detect the prior recommendation and open at verdict state.
 */

import { useApp } from '../context/AppContext';
import { C } from '../styles/tokens';

const VERDICT_COLORS = {
  EXECUTE: C.green,
  WAIT: C.amber,
  PASS: C.red,
};

export default function RecommendationBadge({ verdict, trade, marketContext }) {
  const { openAgent } = useApp();
  const color = VERDICT_COLORS[verdict] || C.textDim;

  return (
    <button
      onClick={e => {
        e.stopPropagation();
        openAgent([trade], marketContext);
      }}
      title={`Claude verdict: ${verdict} — click to re-evaluate`}
      style={{
        padding: '2px 7px', borderRadius: 4, fontSize: 11, fontWeight: 700,
        cursor: 'pointer', border: `1px solid ${color}40`,
        backgroundColor: `${color}15`, color,
        whiteSpace: 'nowrap',
      }}
    >
      ✦ {verdict}
    </button>
  );
}
