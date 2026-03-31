import { useState } from 'react';

// Local strategy color definitions — import from StrategyPill.jsx once available
const STRATEGY_COLORS = {
  'steady-paycheck': 'var(--amber)',
  'weekly-grind': 'var(--green)',
  'trend-rider': 'var(--blue)',
  'lottery-ticket': 'var(--purple)',
  SP: 'var(--amber)',
  WG: 'var(--green)',
  TR: 'var(--blue)',
  LT: 'var(--purple)',
};

function getStrategyColor(strategyKey) {
  if (!strategyKey) return 'var(--text)';
  const lower = strategyKey.toLowerCase().replace(/\s+/g, '-');
  return STRATEGY_COLORS[lower] || STRATEGY_COLORS[strategyKey.toUpperCase()] || 'var(--text)';
}

function VerdictBadge({ verdict }) {
  if (!verdict) return null;
  const upper = verdict.toUpperCase();
  const styles = {
    EXECUTE: { bg: 'rgba(74,222,128,0.15)', color: 'var(--green)' },
    WAIT: { bg: 'rgba(245,158,11,0.15)', color: 'var(--amber)' },
    PASS: { bg: 'rgba(248,113,113,0.15)', color: 'var(--red)' },
  };
  const s = styles[upper] || { bg: 'rgba(255,255,255,0.06)', color: 'var(--muted)' };
  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: 700,
        padding: '3px 10px',
        borderRadius: 3,
        background: s.bg,
        color: s.color,
        fontFamily: 'monospace',
      }}
    >
      {upper}
    </span>
  );
}

function SummaryAdviceBadge({ bestStrategy }) {
  if (!bestStrategy) return null;
  const stratColor = getStrategyColor(bestStrategy);
  const displayName = bestStrategy
    .replace(/-/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
  return (
    <span
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
      }}
    >
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
  onEvaluate,
  onFollow,
  onTakePosition,
  onFollowUp,
  onDiscard,
}) {
  const [followUpText, setFollowUpText] = useState('');

  function handleFollowUpKey(e) {
    if (e.key === 'Enter' && followUpText.trim()) {
      onFollowUp?.(followUpText.trim());
      setFollowUpText('');
    }
  }

  // Pre-evaluation state
  if (!evaluation) {
    return (
      <div style={{ marginTop: 12 }}>
        <button style={tealOutlined} onClick={onEvaluate}>
          Evaluate
        </button>
      </div>
    );
  }

  // Post-evaluation state
  const {
    verdict,
    bestStrategy,
    analysis,
    keyLevelPrice,
    keyLevelExplanation,
  } = evaluation;

  const analysisBlocks = Array.isArray(analysis)
    ? analysis
    : typeof analysis === 'string'
    ? analysis.split(/\n\n+/).filter(Boolean)
    : [];

  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 4,
        padding: '14px 16px',
        marginTop: 12,
        fontFamily: 'monospace',
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          flexWrap: 'wrap',
          marginBottom: 10,
        }}
      >
        <span
          style={{
            fontSize: 9,
            textTransform: 'uppercase',
            letterSpacing: '0.6px',
            color: 'var(--muted)',
          }}
        >
          CLAUDE'S READ
        </span>

        <VerdictBadge verdict={verdict} />

        <SummaryAdviceBadge bestStrategy={bestStrategy} />

        {tradeContext && (
          <span
            style={{
              fontSize: 9,
              color: 'var(--muted)',
              marginLeft: 'auto',
            }}
          >
            {tradeContext}
          </span>
        )}

        <button style={tealOutlinedSmall} onClick={onEvaluate}>
          Evaluate
        </button>
      </div>

      {/* Analysis text */}
      {analysisBlocks.map((para, i) => (
        <p
          key={i}
          style={{
            fontSize: 10,
            color: '#c9d1d9',
            lineHeight: 1.65,
            marginBottom: 8,
            margin: i < analysisBlocks.length - 1 ? '0 0 8px 0' : '0',
            fontStyle: 'normal',
          }}
        >
          {para}
        </p>
      ))}

      {/* Key level callout */}
      {(keyLevelPrice != null || keyLevelExplanation) && (
        <div
          style={{
            background: 'var(--bg2)',
            borderLeft: '2px solid var(--amber)',
            padding: '6px 10px',
            fontSize: 10,
            margin: '8px 0',
            borderRadius: '0 4px 4px 0',
          }}
        >
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

      {/* Actions row */}
      <div
        style={{
          display: 'flex',
          gap: 10,
          marginTop: 12,
          alignItems: 'center',
        }}
      >
        <button style={tealOutlined} onClick={onFollow}>
          Follow (Paper)
        </button>

        <button style={greenFilled} onClick={onTakePosition}>
          Take Position (Live)
        </button>

        <input
          type="text"
          value={followUpText}
          onChange={e => setFollowUpText(e.target.value)}
          onKeyDown={handleFollowUpKey}
          placeholder="Ask a follow-up about this trade..."
          style={{
            flex: 1,
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            color: 'var(--text)',
            fontFamily: 'monospace',
            fontSize: 10,
            padding: '7px 12px',
            borderRadius: 4,
            outline: 'none',
          }}
        />

        <button style={neutralOutlined} onClick={onDiscard}>
          Discard ✕
        </button>
      </div>
    </div>
  );
}
