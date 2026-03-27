/**
 * ClaudesRead — OTA-298
 *
 * Claude's Read on a trade: verdict badge + EV commentary + key levels.
 * Stateless — all state managed by parent (TradeEvaluationView).
 *
 * Props:
 *   onEvaluate  — Function   called when Evaluate button is clicked
 *   loading     — boolean
 *   error       — string | null
 *   result      — {
 *     ev_commentary,
 *     key_level: { price, description },
 *     iv_context,
 *     verdict,            // "EXECUTE" | "WATCH" | "PASS"
 *     verdict_rationale
 *   } | null
 *
 * Dev mock (remove when wired via TradeEvaluationView):
 * const mockResult = {
 *   ev_commentary: "Positive expected value of 312 suggests this trade has statistical edge, though it's modest relative to max risk.",
 *   key_level: { price: 361.20, description: "Breakeven — must stay below for any profit" },
 *   iv_context: "IV at 28% is elevated — premiums are rich, slightly favouring this bear put debit.",
 *   verdict: "EXECUTE",
 *   verdict_rationale: "P(Breakeven or Better) at 58.40% exceeds breakeven threshold. EV is positive at 312."
 * }
 */

import { mono } from '../styles/tokens';

// ─── Design system colors ─────────────────────────────────────────────────────

const EMERALD = '#00C896';
const AMBER   = '#F5A623';
const DANGER  = '#F85149';
const VIOLET  = '#8B5CF6';

// ─── Verdict config ───────────────────────────────────────────────────────────

const VERDICT_STYLE = {
  EXECUTE: { bg: `${EMERALD}22`, border: `${EMERALD}55`, color: EMERALD },
  WATCH:   { bg: `${AMBER}22`,   border: `${AMBER}55`,   color: AMBER   },
  PASS:    { bg: 'rgba(255,255,255,0.04)', border: 'rgba(255,255,255,0.12)', color: '#8b90a0' },
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function VerdictBadge({ verdict }) {
  const style = VERDICT_STYLE[verdict] ?? VERDICT_STYLE.PASS;
  return (
    <span style={{
      display: 'inline-block',
      fontFamily: mono,
      fontSize: 13,
      fontWeight: 700,
      color: style.color,
      backgroundColor: style.bg,
      border: `1px solid ${style.border}`,
      borderRadius: 4,
      padding: '4px 14px',
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
    }}>
      {verdict}
    </span>
  );
}

function SkeletonLine({ width = '100%', height = 12, mb = 8 }) {
  return (
    <div style={{
      width,
      height,
      borderRadius: 3,
      backgroundColor: 'rgba(255,255,255,0.06)',
      marginBottom: mb,
    }} />
  );
}

function Skeleton() {
  return (
    <div style={{ padding: '12px 0' }}>
      <SkeletonLine width="40%" height={18} mb={16} />
      <SkeletonLine width="90%" mb={6} />
      <SkeletonLine width="75%" mb={16} />
      <SkeletonLine width="60%" height={10} mb={6} />
      <SkeletonLine width="50%" height={10} mb={16} />
      <SkeletonLine width="85%" mb={6} />
      <SkeletonLine width="70%" />
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function ClaudesRead({ onEvaluate, loading = false, error = null, result = null }) {
  return (
    <div style={{
      backgroundColor: '#0D1117',
      border: '1px solid #252a3a',
      borderRadius: 6,
      padding: '14px 16px',
      fontFamily: mono,
    }}>
      {/* ── Header + Evaluate button ─────────────────────────── */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 14,
      }}>
        <span style={{
          fontSize: 10,
          color: '#8b90a0',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
        }}>
          Claude's Read
        </span>
        <button
          onClick={onEvaluate}
          disabled={loading}
          style={{
            fontFamily: mono,
            fontSize: 11,
            fontWeight: 600,
            color: loading ? '#555b6e' : '#fff',
            backgroundColor: loading ? 'rgba(139,92,246,0.15)' : VIOLET,
            border: `1px solid ${loading ? 'rgba(139,92,246,0.25)' : VIOLET}`,
            borderRadius: 4,
            padding: '5px 14px',
            cursor: loading ? 'not-allowed' : 'pointer',
            transition: 'opacity 0.15s',
            whiteSpace: 'nowrap',
          }}
        >
          {loading ? 'Evaluating…' : 'Evaluate'}
        </button>
      </div>

      {/* ── Loading skeleton ─────────────────────────────────── */}
      {loading && <Skeleton />}

      {/* ── Error state ──────────────────────────────────────── */}
      {!loading && error && (
        <div style={{
          padding: '10px 12px',
          backgroundColor: 'rgba(248, 81, 73, 0.08)',
          border: `1px solid rgba(248, 81, 73, 0.25)`,
          borderRadius: 4,
          fontSize: 12,
          color: DANGER,
        }}>
          {error}
        </div>
      )}

      {/* ── Result state ─────────────────────────────────────── */}
      {!loading && !error && result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Verdict badge */}
          <div>
            <VerdictBadge verdict={result.verdict} />
          </div>

          {/* EV commentary */}
          <p style={{ margin: 0, fontSize: 12, color: '#c9d1d9', lineHeight: 1.55 }}>
            {result.ev_commentary}
          </p>

          {/* Key level callout */}
          {result.key_level && (
            <div style={{
              padding: '8px 12px',
              backgroundColor: 'rgba(79, 142, 247, 0.06)',
              border: '1px solid rgba(79, 142, 247, 0.20)',
              borderRadius: 4,
              display: 'flex',
              gap: 10,
              alignItems: 'baseline',
            }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: '#4f8ef7' }}>
                {result.key_level.price != null ? Number(result.key_level.price).toFixed(2) : '—'}
              </span>
              <span style={{ fontSize: 11, color: '#8b90a0' }}>
                {result.key_level.description}
              </span>
            </div>
          )}

          {/* IV context */}
          {result.iv_context && (
            <p style={{ margin: 0, fontSize: 11, color: '#8b90a0', lineHeight: 1.5 }}>
              {result.iv_context}
            </p>
          )}

          {/* Verdict rationale */}
          {result.verdict_rationale && (
            <p style={{ margin: 0, fontSize: 10, color: '#555b6e', lineHeight: 1.5 }}>
              {result.verdict_rationale}
            </p>
          )}
        </div>
      )}

      {/* ── Empty state ──────────────────────────────────────── */}
      {!loading && !error && !result && (
        <div style={{
          padding: '20px 0',
          textAlign: 'center',
          fontSize: 12,
          color: '#555b6e',
        }}>
          Click Evaluate to get Claude's read on this trade.
        </div>
      )}
    </div>
  );
}
