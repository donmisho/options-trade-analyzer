import { useState } from 'react';
import { STRATEGY_COLORS, ABBR_TO_STRATEGY_KEY } from '../../utils/strategyColors';

function getStrategyColor(strategyKey) {
  if (!strategyKey) return 'var(--text)';
  const abbrKey = ABBR_TO_STRATEGY_KEY[strategyKey.toUpperCase()];
  if (abbrKey) return STRATEGY_COLORS[abbrKey]?.text || 'var(--text)';
  const normalized = strategyKey.toLowerCase().replace(/[-\s]+/g, '_');
  return STRATEGY_COLORS[normalized]?.text || 'var(--text)';
}

function VerdictBadge({ verdict }) {
  if (!verdict) return null;
  const upper = verdict.toUpperCase();
  const styles = {
    EXECUTE: { bg: 'rgba(74,222,128,0.15)', color: 'var(--green)' },
    WAIT:    { bg: 'rgba(245,158,11,0.15)',  color: 'var(--amber)' },
    PASS:    { bg: 'rgba(248,113,113,0.15)', color: 'var(--red)'   },
  };
  const s = styles[upper] || { bg: 'rgba(255,255,255,0.06)', color: 'var(--muted)' };
  return (
    <span style={{
      fontSize: 10,
      fontWeight: 700,
      padding: '3px 10px',
      borderRadius: 3,
      background: s.bg,
      color: s.color,
      fontFamily: 'monospace',
    }}>
      {upper}
    </span>
  );
}

function SummaryAdviceBadge({ bestStrategy, bestFitReason }) {
  const hasBestFit = bestStrategy != null;
  const stratColor = hasBestFit ? getStrategyColor(bestStrategy) : 'var(--muted)';
  const displayName = hasBestFit
    ? bestStrategy.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
    : 'none';
  return (
    <span
      title={!hasBestFit && bestFitReason ? bestFitReason : undefined}
      style={{
        background: 'rgba(255,255,255,0.06)',
        border: '1px solid rgba(255,255,255,0.35)',
        color: '#e6edf3',
        fontSize: 9,
        fontWeight: 700,
        padding: '3px 10px',
        borderRadius: 3,
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        fontFamily: 'monospace',
      }}>
      <span style={{ color: '#e6edf3' }}>Best fit:&nbsp;</span>
      <span style={{ color: stratColor }}>{displayName}</span>
    </span>
  );
}

const tealOutlined = {
  background: 'rgba(45,212,191,0.1)',
  border: '1px solid rgba(45,212,191,0.4)',
  color: 'var(--teal)',
  padding: '7px 16px',
  borderRadius: 4,
  fontSize: 11,
  fontFamily: 'monospace',
  cursor: 'pointer',
  width: 'auto',
};

const tealOutlinedSmall = {
  ...tealOutlined,
  padding: '4px 10px',
  fontSize: 10,
};

const greenFilled = {
  background: 'rgba(74,222,128,0.12)',
  border: '1px solid rgba(74,222,128,0.45)',
  color: 'var(--green)',
  fontWeight: 700,
  padding: '7px 16px',
  borderRadius: 4,
  fontSize: 11,
  fontFamily: 'monospace',
  cursor: 'pointer',
  width: 'auto',
};

const neutralOutlined = {
  background: 'transparent',
  border: '1px solid var(--border)',
  color: 'var(--muted)',
  padding: '7px 14px',
  borderRadius: 4,
  fontSize: 11,
  fontFamily: 'monospace',
  cursor: 'pointer',
  width: 'auto',
};

export default function SectionE({
  evaluation,
  tradeContext,
  canEvaluate = true,  // false when price data not yet loaded
  onEvaluate,      // async () => void — parent handles API call + state update
  onFollow,        // async () => void
  onTakePosition,  // async () => void
  onFollowUp,      // async (question, evaluation) => { answer }
  onDiscard,
  tradeKey,        // string | null — from OTA-624 trade_candidates persistence
}) {
  const [isEvalLoading, setIsEvalLoading] = useState(false);
  const [followUps, setFollowUps] = useState([]);
  const [followUpInput, setFollowUpInput] = useState('');
  const [isFollowUpLoading, setIsFollowUpLoading] = useState(false);

  async function handleEvaluate() {
    if (isEvalLoading) return;
    setFollowUps([]);
    setIsEvalLoading(true);
    try {
      await onEvaluate?.();
    } finally {
      setIsEvalLoading(false);
    }
  }

  async function handleFollowUpSubmit() {
    const q = followUpInput.trim();
    if (!q || isFollowUpLoading) return;
    setFollowUpInput('');
    const id = Date.now() + Math.random();
    setFollowUps(prev => [...prev, { id, question: q, answer: null }]);
    setIsFollowUpLoading(true);
    try {
      const resp = await onFollowUp?.(q, evaluation);
      const answer = resp?.answer || resp?.claude_read || resp?.response || 'No response received';
      setFollowUps(prev => prev.map(fu => fu.id === id ? { ...fu, answer } : fu));
    } catch (err) {
      setFollowUps(prev => prev.map(fu => fu.id === id ? { ...fu, answer: `Error: ${err.message}` } : fu));
    } finally {
      setIsFollowUpLoading(false);
    }
  }

  function handleFollowUpKey(e) {
    if (e.key === 'Enter') handleFollowUpSubmit();
  }

  function handleDiscard() {
    setFollowUps([]);
    setFollowUpInput('');
    onDiscard?.();
  }

  // Loading state (evaluate in flight)
  if (isEvalLoading) {
    return (
      <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 10 }}>
        <button style={{ ...tealOutlined, opacity: 0.5, cursor: 'default' }} disabled>
          Evaluating…
        </button>
        {tradeContext && (
          <span style={{ fontSize: 9, color: 'var(--muted)', fontFamily: 'monospace' }}>
            {tradeContext} · Evaluating…
          </span>
        )}
      </div>
    );
  }

  // Pre-evaluation state
  if (!evaluation) {
    return (
      <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 10 }}>
        <button
          style={{ ...tealOutlined, ...(canEvaluate ? {} : { opacity: 0.35, cursor: 'default' }) }}
          onClick={canEvaluate ? handleEvaluate : undefined}
          disabled={!canEvaluate}
        >
          Evaluate
        </button>
        {!canEvaluate && (
          <span style={{ fontSize: 9, color: 'var(--muted)', fontFamily: 'monospace' }}>
            Loading price data…
          </span>
        )}
      </div>
    );
  }

  // Post-evaluation state
  const {
    verdict,
    bestStrategy,
    bestFitReason,
    analysis,
    keyLevelPrice,
    keyLevelExplanation,
    score,
    autoPassReason,
  } = evaluation;

  const analysisBlocks = Array.isArray(analysis)
    ? analysis
    : typeof analysis === 'string'
    ? analysis.split(/\n\n+/).filter(Boolean)
    : [];

  return (
    <div style={{
      border: '1px solid var(--border)',
      borderRadius: 4,
      padding: '14px 16px',
      marginTop: 12,
      fontFamily: 'monospace',
    }}>
      {/* Header row */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        flexWrap: 'wrap',
        marginBottom: 10,
      }}>
        <span style={{
          fontSize: 9,
          textTransform: 'uppercase',
          letterSpacing: '0.6px',
          color: 'var(--muted)',
        }}>
          CLAUDE'S READ
        </span>

        <VerdictBadge verdict={verdict} />
        <SummaryAdviceBadge bestStrategy={bestStrategy} bestFitReason={bestFitReason} />

        {score != null && (
          <span style={{
            fontSize: 11,
            fontWeight: 700,
            color: score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--amber)' : 'var(--red)',
          }}>
            {Number(score).toFixed(2)}
          </span>
        )}

        {tradeContext && (
          <span style={{ fontSize: 9, color: 'var(--muted)', marginLeft: 'auto' }}>
            {tradeContext}
          </span>
        )}

        <button style={tealOutlinedSmall} onClick={handleEvaluate}>
          Evaluate
        </button>
      </div>

      {/* Analysis text */}
      {analysisBlocks.map((para, i) => (
        <p key={i} style={{
          fontSize: 10,
          color: '#c9d1d9',
          lineHeight: 1.65,
          margin: i < analysisBlocks.length - 1 ? '0 0 8px 0' : '0',
          fontStyle: 'normal',
        }}>
          {para}
        </p>
      ))}

      {/* Auto-pass reason (shown when evaluation was skipped by pipeline gate) */}
      {!analysisBlocks.length && autoPassReason && (
        <div style={{
          background: 'rgba(248,113,113,0.08)',
          borderLeft: '2px solid var(--red)',
          padding: '6px 10px',
          fontSize: 10,
          color: 'var(--muted)',
          borderRadius: '0 4px 4px 0',
        }}>
          {autoPassReason}
        </div>
      )}

      {/* Key level callout */}
      {(keyLevelPrice != null || keyLevelExplanation) && (
        <div style={{
          background: 'var(--bg2)',
          borderLeft: '2px solid var(--amber)',
          padding: '6px 10px',
          fontSize: 10,
          margin: '8px 0',
          borderRadius: '0 4px 4px 0',
        }}>
          {keyLevelPrice != null && (
            <span style={{ color: 'var(--amber)', fontWeight: 700 }}>
              {Number(keyLevelPrice).toFixed(2)}&nbsp;
            </span>
          )}
          {keyLevelExplanation && (
            <span style={{ color: 'var(--text)' }}>{keyLevelExplanation}</span>
          )}
        </div>
      )}

      {/* Follow-up responses */}
      {followUps.map(fu => (
        <div key={fu.id} style={{
          borderLeft: '2px solid var(--border)',
          paddingLeft: 10,
          margin: '8px 0',
        }}>
          <div style={{ fontSize: 9, color: 'var(--muted)', fontStyle: 'italic', marginBottom: 4 }}>
            {fu.question}
          </div>
          {fu.answer == null ? (
            <span style={{ fontSize: 10, color: 'var(--muted)' }}>●●●</span>
          ) : (
            <span style={{ fontSize: 10, color: '#c9d1d9', lineHeight: 1.65 }}>{fu.answer}</span>
          )}
        </div>
      ))}

      {/* Actions row */}
      <div style={{
        display: 'flex',
        gap: 10,
        marginTop: 12,
        alignItems: 'center',
        flexWrap: 'wrap',
      }}>
        {(() => {
          // OTA-628: Disable Follow/Take for gate-disqualified cards
          const disableReasons = [];
          if (autoPassReason) disableReasons.push('Auto-pass: trade disqualified');
          const upperVerdict = verdict ? verdict.toUpperCase() : '';
          if (upperVerdict === 'WAIT_FOR_EARNINGS' || upperVerdict === 'PASS')
            disableReasons.push(`Verdict: ${verdict}`);
          const isDisabled = disableReasons.length > 0;
          const tip = disableReasons.join('; ');
          const disabledStyle = { opacity: 0.35, cursor: 'default', pointerEvents: 'none' };
          return (
            <>
              <span title={isDisabled ? tip : undefined}>
                <button
                  style={{ ...tealOutlined, ...(isDisabled ? disabledStyle : {}) }}
                  onClick={() => !isDisabled && onFollow?.()}
                  disabled={isDisabled}
                >
                  Follow (Paper)
                </button>
              </span>
              <span title={isDisabled ? tip : undefined}>
                <button
                  style={{ ...greenFilled, ...(isDisabled ? disabledStyle : {}) }}
                  onClick={() => !isDisabled && onTakePosition?.()}
                  disabled={isDisabled}
                >
                  Take Position (Live)
                </button>
              </span>
            </>
          );
        })()}

        {tradeKey && (
          <a
            href={`/api/v1/export/trade/${tradeKey}.md`}
            style={{
              ...neutralOutlined,
              textDecoration: 'none',
              display: 'inline-block',
            }}
          >
            Export MD
          </a>
        )}

        <input
          type="text"
          value={followUpInput}
          onChange={e => setFollowUpInput(e.target.value)}
          onKeyDown={handleFollowUpKey}
          placeholder="Ask a follow-up about this trade..."
          disabled={isFollowUpLoading}
          style={{
            flex: 1,
            minWidth: 0,
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            color: 'var(--text)',
            fontFamily: 'monospace',
            fontSize: 10,
            padding: '7px 12px',
            borderRadius: 4,
            outline: 'none',
            opacity: isFollowUpLoading ? 0.5 : 1,
          }}
        />

        {isFollowUpLoading && (
          <span style={{ fontSize: 10, color: 'var(--muted)' }}>●●●</span>
        )}

        <button style={neutralOutlined} onClick={handleDiscard}>
          Discard ✕
        </button>
      </div>
    </div>
  );
}
