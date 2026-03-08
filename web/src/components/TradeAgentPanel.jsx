/**
 * TradeAgentPanel — Full-height slide-out panel for Claude trade evaluation.
 *
 * WHY one shared panel at the root instead of per-page:
 * Any analysis page can open it via AppContext.openAgent(). It handles
 * 1-10 trades in one conversation across three stages: triage → deep dive → followup.
 * The panel adapts its UI entirely to what the agent returns — no fixed form structure.
 *
 * States:
 *   idle            Trade cards shown, waiting for user to start
 *   triaging        Calling /agent/triage, loading
 *   triage_complete Rankings shown, user picks a trade to explore
 *   diving          Calling /agent/deep-dive, loading
 *   verdict         EXECUTE / WAIT / PASS verdict shown with full analysis
 *   followup        Conversation thread below a pinned verdict summary
 */

import { useState, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import { C, mono } from '../styles/tokens';
import { triageTrades, deepDiveTrade, followupTrade } from '../api/client';

// ─── Verdict colors ────────────────────────────────────────────────
const VERDICT_COLORS = {
  EXECUTE: C.green,
  WAIT: C.amber,
  PASS: C.red,
};

const RANK_COLORS = {
  STRONG: C.green,
  MEDIUM: C.amber,
  WEAK: C.red,
};

// ─── Small reusable pieces ────────────────────────────────────────

function DirectionBadge({ direction }) {
  const bull = direction === 'bullish';
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
      backgroundColor: bull ? C.greenBg : C.redBg,
      color: bull ? C.green : C.red,
      border: `1px solid ${bull ? C.green : C.red}30`,
    }}>
      {bull ? '▲ Bull' : '▼ Bear'}
    </span>
  );
}

function RankBadge({ rank }) {
  const color = RANK_COLORS[rank] || C.textDim;
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 4,
      backgroundColor: `${color}20`, color, border: `1px solid ${color}40`,
    }}>
      {rank}
    </span>
  );
}

function Spinner() {
  return (
    <span style={{
      display: 'inline-block', width: 14, height: 14, borderRadius: '50%',
      border: `2px solid ${C.border}`, borderTopColor: C.claudeAccent,
      animation: 'spin 0.7s linear infinite', flexShrink: 0,
    }} />
  );
}

function TradeCard({ trade, rank, reason, exploreButton, selected, dim }) {
  return (
    <div style={{
      borderRadius: 8,
      border: `1px solid ${selected ? C.claudeBorder : C.border}`,
      backgroundColor: selected ? C.claudeDim : C.card,
      padding: '10px 12px',
      opacity: dim ? 0.45 : 1,
      transition: 'opacity 0.2s',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, flexWrap: 'wrap' }}>
        {trade.direction && <DirectionBadge direction={trade.direction} />}
        <span style={{ color: C.text, fontSize: 13, fontWeight: 600 }}>{trade.spread_label}</span>
        {rank && <RankBadge rank={rank} />}
      </div>
      <div style={{ display: 'flex', gap: 12, color: C.textDim, fontSize: 11, flexWrap: 'wrap' }}>
        <span>{trade.expiration}</span>
        {trade.dte > 0 && <span>{Math.round(trade.dte)}d</span>}
        {trade.net_debit != null && <span>Debit {trade.net_debit.toFixed(2)}</span>}
        {trade.reward_risk_ratio != null && <span>R:R {trade.reward_risk_ratio.toFixed(2)}</span>}
        {trade.prob_of_profit != null && <span>PoP {Math.round(trade.prob_of_profit * 100)}%</span>}
      </div>
      {reason && <p style={{ margin: '6px 0 0', fontSize: 11.5, color: C.textDim, lineHeight: 1.45 }}>{reason}</p>}
      {exploreButton}
    </div>
  );
}

function CollapsibleSection({ title, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ marginBottom: 8, borderRadius: 8, border: `1px solid ${C.border}`, backgroundColor: C.card }}>
      <button onClick={() => setOpen(!open)} style={{
        width: '100%', padding: '9px 12px', display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', background: 'none', border: 'none', cursor: 'pointer',
      }}>
        <span style={{ color: C.text, fontSize: 12.5, fontWeight: 600 }}>{title}</span>
        <span style={{ color: C.textMuted, fontSize: 14, transform: open ? 'rotate(180deg)' : 'rotate(0)', display: 'inline-block', transition: 'transform 0.2s' }}>▾</span>
      </button>
      {open && (
        <div style={{ padding: '2px 12px 12px', borderTop: `1px solid ${C.border}` }}>
          {children}
        </div>
      )}
    </div>
  );
}

// Render inline markdown — bold stays bold, rest is stripped
function renderInline(text) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) {
      return <strong key={i} style={{ color: C.text, fontWeight: 700 }}>{p.slice(2, -2)}</strong>;
    }
    return p.replace(/\*(.+?)\*/g, '$1').replace(/`(.+?)`/g, '$1');
  });
}

// Render a block of Claude's markdown as clean JSX — no raw markup visible
function RenderMarkdown({ text }) {
  if (!text) return null;
  const lines = text.split('\n');
  const elements = [];
  let key = 0;

  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line === '---' || line === '***' || line === '---') continue;

    // Heading lines (##, ###) — render as a styled sub-header with accent bar
    if (line.startsWith('#')) {
      const content = line.replace(/^#+\s*/, '').replace(/\*\*/g, '');
      // Skip lines that are just the section title (already shown in CollapsibleSection header)
      if (content) elements.push(
        <div key={key++} style={{
          display: 'flex', alignItems: 'center', gap: 7,
          marginTop: 10, marginBottom: 4,
        }}>
          <div style={{ width: 3, height: 14, borderRadius: 2, backgroundColor: C.claudeAccent, flexShrink: 0 }} />
          <span style={{ fontWeight: 700, color: C.textDim, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            {content}
          </span>
        </div>
      );
      continue;
    }

    // Emoji-led lines (🚩, ✅, ⚠️, 💡, etc.) — preserve emoji as the icon
    const emojiMatch = line.match(/^(\p{Emoji_Presentation}|\p{Emoji}\uFE0F)\s*(.*)/u);
    if (emojiMatch) {
      elements.push(
        <div key={key++} style={{ display: 'flex', gap: 7, marginBottom: 4, alignItems: 'flex-start' }}>
          <span style={{ flexShrink: 0, fontSize: 14, lineHeight: 1.4 }}>{emojiMatch[1]}</span>
          <span style={{ lineHeight: 1.5 }}>{renderInline(emojiMatch[2])}</span>
        </div>
      );
      continue;
    }

    // Bullet lines (- or *) — replace with ◆ icon
    const bulletMatch = line.match(/^[-*]\s+(.+)/);
    if (bulletMatch) {
      elements.push(
        <div key={key++} style={{ display: 'flex', gap: 8, marginBottom: 3, alignItems: 'flex-start' }}>
          <span style={{ color: C.claudeAccent, flexShrink: 0, fontSize: 8, marginTop: 5 }}>◆</span>
          <span style={{ lineHeight: 1.5 }}>{renderInline(bulletMatch[1])}</span>
        </div>
      );
      continue;
    }

    // Numbered list — preserve numbering with accent color
    const numMatch = line.match(/^(\d+)\.\s+(.+)/);
    if (numMatch) {
      elements.push(
        <div key={key++} style={{ display: 'flex', gap: 8, marginBottom: 3, alignItems: 'flex-start' }}>
          <span style={{ color: C.claudeAccent, flexShrink: 0, fontWeight: 700, fontSize: 11, minWidth: 18, marginTop: 2 }}>{numMatch[1]}.</span>
          <span style={{ lineHeight: 1.5 }}>{renderInline(numMatch[2])}</span>
        </div>
      );
      continue;
    }

    // Plain text paragraph
    const content = renderInline(line);
    elements.push(
      <div key={key++} style={{ marginBottom: 3, lineHeight: 1.5 }}>{content}</div>
    );
  }

  return <div style={{ fontSize: 12.5, color: C.text, paddingTop: 4 }}>{elements}</div>;
}

// Parse Claude's markdown analysis into named sections
function parseAnalysis(text) {
  if (!text) return {};
  const sections = {};
  const sectionMap = {
    'thesis': 'Thesis Alignment',
    'risk': 'Risk/Reward Quality',
    'prob': 'Probability & Expected Move',
    'red flag': 'Red Flags / Alternatives',
    'alternative': 'Red Flags / Alternatives',
    'exit': 'Exit Plan',
  };
  const lines = text.split('\n');
  let current = null;
  let buffer = [];

  for (const line of lines) {
    const lower = line.toLowerCase();
    let matched = false;
    for (const [key, label] of Object.entries(sectionMap)) {
      if (lower.includes(key) && (line.startsWith('#') || line.startsWith('**'))) {
        if (current && buffer.length) sections[current] = buffer.join('\n').trim();
        current = label;
        buffer = [];
        matched = true;
        break;
      }
    }
    if (!matched && current) buffer.push(line);
  }
  if (current && buffer.length) sections[current] = buffer.join('\n').trim();
  return sections;
}

// ─── Main Panel ────────────────────────────────────────────────────

export default function TradeAgentPanel() {
  const { agentOpen, agentTrades, agentMarketContext, closeAgent } = useApp();

  const [agentState, setAgentState] = useState('idle');
  // idle | triaging | triage_complete | pre_dive | diving | verdict | followup
  const [triageResults, setTriageResults] = useState(null);
  const [selectedTrade, setSelectedTrade] = useState(null);
  const [priceTarget, setPriceTarget] = useState('');
  const [verdictData, setVerdictData] = useState(null);
  const [followupThread, setFollowupThread] = useState([]);
  const [followupInput, setFollowupInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [runId, setRunId] = useState(null);

  // Reset internal state when the panel opens with new trades
  useEffect(() => {
    if (agentOpen) {
      setAgentState('idle');
      setTriageResults(null);
      setSelectedTrade(null);
      setPriceTarget('');
      setVerdictData(null);
      setFollowupThread([]);
      setFollowupInput('');
      setError(null);
      setRunId(null);
    }
  }, [agentOpen, agentTrades]);

  // ─── Stage handlers ─────────────────────────────────────────────

  async function handleTriage() {
    setLoading(true);
    setError(null);
    setAgentState('triaging');
    try {
      const result = await triageTrades(agentTrades, agentMarketContext);
      setRunId(result.run_id);
      setTriageResults(result);
      setAgentState('triage_complete');
    } catch (e) {
      setError(e.message || 'Triage failed');
      setAgentState('idle');
    } finally {
      setLoading(false);
    }
  }

  async function handleDeepDive(trade) {
    setSelectedTrade(trade);
    setAgentState('diving');
    setLoading(true);
    setError(null);
    try {
      const result = await deepDiveTrade(trade, agentMarketContext, priceTarget, runId);
      setVerdictData(result);
      setRunId(result.run_id);
      setAgentState('verdict');
    } catch (e) {
      setError(e.message || 'Deep dive failed');
      setAgentState(triageResults ? 'triage_complete' : 'idle');
    } finally {
      setLoading(false);
    }
  }

  async function handleFollowup(question) {
    if (!question.trim() || !verdictData) return;
    const q = question.trim();
    setFollowupInput('');
    setAgentState('followup');
    setLoading(true);
    setFollowupThread(prev => [...prev, { question: q, response: null }]);
    try {
      const result = await followupTrade(
        selectedTrade,
        verdictData.verdict,
        verdictData.analysis?.slice(0, 300) || '',
        q,
        runId,
      );
      setFollowupThread(prev => prev.map((item, i) =>
        i === prev.length - 1 ? { ...item, response: result.response } : item
      ));
    } catch (e) {
      setFollowupThread(prev => prev.map((item, i) =>
        i === prev.length - 1 ? { ...item, response: '⚠ Follow-up failed. Try again.' } : item
      ));
    } finally {
      setLoading(false);
    }
  }

  // ─── Derived values ─────────────────────────────────────────────

  function selectTrade(trade) {
    setSelectedTrade(trade);
    setPriceTarget('');
    setAgentState('pre_dive');
  }

  const isSingleTrade = agentTrades.length === 1;
  const symbol = agentMarketContext?.symbol || agentTrades[0]?.symbol || '';

  // Build ranked trade list for triage_complete
  const rankedTrades = triageResults
    ? [...agentTrades].sort((a, b) => {
        const order = { STRONG: 0, MEDIUM: 1, WEAK: 2 };
        const ra = triageResults.rankings.find(r => r.trade_id === a.trade_id);
        const rb = triageResults.rankings.find(r => r.trade_id === b.trade_id);
        return (order[ra?.rank] ?? 3) - (order[rb?.rank] ?? 3);
      })
    : agentTrades;

  // ─── Render helpers ──────────────────────────────────────────────

  function renderIdle() {
    const btnLabel = isSingleTrade
      ? '✦ Analyze This Trade'
      : `✦ Triage These ${agentTrades.length} Trades`;

    return (
      <>
        <div style={{ padding: '0 16px 16px', flex: 1, overflowY: 'auto' }}>
          <p style={{ fontSize: 12, color: C.textDim, margin: '0 0 12px' }}>
            {isSingleTrade
              ? 'Claude will analyze this trade in depth.'
              : `Claude will rank all ${agentTrades.length} trades, then you pick one to explore further.`}
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {agentTrades.map(t => (
              <TradeCard key={t.trade_id} trade={t} />
            ))}
          </div>
          {error && <p style={{ color: C.red, fontSize: 12, marginTop: 8 }}>⚠ {error}</p>}
        </div>
        <div style={{ padding: '12px 16px', borderTop: `1px solid ${C.border}` }}>
          <button onClick={isSingleTrade ? () => selectTrade(agentTrades[0]) : handleTriage}
            disabled={loading}
            style={{
              width: '100%', padding: '10px', borderRadius: 7,
              backgroundColor: C.claudeDim, border: `1px solid ${C.claudeBorder}`,
              color: C.claudeAccent, fontSize: 13, fontWeight: 700, cursor: 'pointer',
            }}>
            {btnLabel}
          </button>
        </div>
      </>
    );
  }

  function renderTriaging() {
    return (
      <div style={{ padding: '0 16px 16px', flex: 1, overflowY: 'auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14, color: C.textDim, fontSize: 13 }}>
          <Spinner /> Reading the trades…
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, opacity: 0.4 }}>
          {agentTrades.map(t => <TradeCard key={t.trade_id} trade={t} />)}
        </div>
      </div>
    );
  }

  function renderTriageComplete() {
    return (
      <>
        <div style={{ padding: '0 16px 16px', flex: 1, overflowY: 'auto' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 14 }}>
            {rankedTrades.map(t => {
              const ranking = triageResults.rankings.find(r => r.trade_id === t.trade_id);
              return (
                <TradeCard
                  key={t.trade_id}
                  trade={t}
                  rank={ranking?.rank}
                  reason={ranking?.reason}
                  exploreButton={ranking?.explore_further && (
                    <button
                      onClick={() => selectTrade(t)}
                      style={{
                        marginTop: 8, padding: '5px 12px', borderRadius: 6, fontSize: 12,
                        fontWeight: 600, cursor: 'pointer',
                        backgroundColor: C.claudeDim, border: `1px solid ${C.claudeBorder}`,
                        color: C.claudeAccent,
                      }}>
                      Explore Further →
                    </button>
                  )}
                />
              );
            })}
          </div>
          {triageResults.triage_summary && (
            <div style={{ padding: '10px 12px', borderRadius: 8, backgroundColor: C.surfaceAlt, border: `1px solid ${C.border}`, fontSize: 12.5, color: C.textDim, lineHeight: 1.5 }}>
              {triageResults.triage_summary}
            </div>
          )}
        </div>
        <div style={{ padding: '12px 16px', borderTop: `1px solid ${C.border}` }}>
          <button onClick={() => setAgentState('idle')}
            style={{ background: 'none', border: 'none', color: C.textDim, fontSize: 12, cursor: 'pointer' }}>
            ← New Selection
          </button>
        </div>
      </>
    );
  }

  function renderPreDive() {
    return (
      <>
        <div style={{ padding: '0 16px 16px', flex: 1, overflowY: 'auto' }}>
          {selectedTrade && <TradeCard trade={selectedTrade} selected />}
          <div style={{ marginTop: 14, padding: '12px 14px', borderRadius: 8, backgroundColor: C.card, border: `1px solid ${C.border}` }}>
            <label style={{ display: 'block', fontSize: 11, color: C.textDim, fontWeight: 600, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Price Target (optional)
            </label>
            <input
              type="number"
              placeholder="e.g. 565.00"
              value={priceTarget}
              onChange={e => setPriceTarget(e.target.value)}
              autoFocus
              style={{
                width: '100%', padding: '8px 10px', borderRadius: 6, fontSize: 13,
                border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text,
                fontFamily: mono, outline: 'none', boxSizing: 'border-box',
              }}
              onFocus={e => e.target.style.borderColor = C.claudeAccent}
              onBlur={e => e.target.style.borderColor = C.border}
              onKeyDown={e => e.key === 'Enter' && handleDeepDive(selectedTrade)}
            />
            <p style={{ margin: '6px 0 0', fontSize: 11, color: C.textMuted, lineHeight: 1.4 }}>
              Claude uses this to assess whether the spread reaches profitability. Leave blank to analyze without a target.
            </p>
          </div>
          {error && <p style={{ color: C.red, fontSize: 12, marginTop: 8 }}>⚠ {error}</p>}
        </div>
        <div style={{ padding: '12px 16px', borderTop: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button onClick={() => handleDeepDive(selectedTrade)} disabled={loading}
            style={{
              width: '100%', padding: '10px', borderRadius: 7,
              backgroundColor: C.claudeDim, border: `1px solid ${C.claudeBorder}`,
              color: C.claudeAccent, fontSize: 13, fontWeight: 700, cursor: 'pointer',
            }}>
            ✦ Analyze This Trade
          </button>
          <button onClick={() => setAgentState(triageResults ? 'triage_complete' : 'idle')}
            style={{ background: 'none', border: 'none', color: C.textDim, fontSize: 11, cursor: 'pointer' }}>
            ← Back
          </button>
        </div>
      </>
    );
  }

  function renderDiving() {
    return (
      <div style={{ padding: '0 16px 16px', flex: 1 }}>
        {selectedTrade && <TradeCard trade={selectedTrade} selected />}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 14, color: C.textDim, fontSize: 13 }}>
          <Spinner /> Analyzing…
        </div>
      </div>
    );
  }

  function renderVerdict() {
    if (!verdictData) return null;
    const { verdict, analysis, had_prior_recommendation } = verdictData;
    const vColor = VERDICT_COLORS[verdict] || C.textDim;
    const sections = parseAnalysis(analysis);
    const sectionOrder = ['Thesis Alignment', 'Risk/Reward Quality', 'Probability & Expected Move', 'Red Flags / Alternatives', 'Exit Plan'];

    return (
      <>
        <div style={{ padding: '0 16px 16px', flex: 1, overflowY: 'auto' }}>
          {/* Verdict banner */}
          <div style={{
            borderRadius: 8, padding: '14px 16px', marginBottom: 12,
            backgroundColor: `${vColor}15`, border: `1.5px solid ${vColor}50`,
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <div>
              <div style={{ fontSize: 22, fontWeight: 800, color: vColor, letterSpacing: '0.02em' }}>{verdict}</div>
              {had_prior_recommendation && (
                <div style={{ fontSize: 11, color: C.textDim, marginTop: 2 }}>Updated from prior evaluation</div>
              )}
            </div>
            {selectedTrade && <DirectionBadge direction={selectedTrade.direction} />}
          </div>

          {priceTarget && (
            <div style={{ marginBottom: 10, fontSize: 11, color: C.textDim }}>
              Price target: <span style={{ color: C.text, fontFamily: mono }}>{priceTarget}</span>
            </div>
          )}

          {/* Collapsible analysis sections */}
          {sectionOrder.map(title =>
            sections[title] ? (
              <CollapsibleSection key={title} title={title}>
                <RenderMarkdown text={sections[title]} />
              </CollapsibleSection>
            ) : null
          )}

          {/* If no sections parsed, show full analysis cleaned */}
          {Object.keys(sections).length === 0 && (
            <RenderMarkdown text={analysis} />
          )}

          {error && <p style={{ color: C.red, fontSize: 12, marginTop: 8 }}>⚠ {error}</p>}
        </div>
        <div style={{ padding: '12px 16px', borderTop: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <button onClick={() => handleFollowup('Can you expand on your reasoning?')}
            disabled={loading}
            style={{
              padding: '8px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer',
              border: `1px solid ${C.border}`, backgroundColor: C.surfaceAlt, color: C.text,
            }}>
            Tell me more
          </button>
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              value={followupInput}
              onChange={e => setFollowupInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleFollowup(followupInput)}
              placeholder="Ask a follow-up question…"
              style={{
                flex: 1, padding: '8px 10px', borderRadius: 6, fontSize: 12,
                border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text,
                outline: 'none',
              }}
            />
            <button onClick={() => handleFollowup(followupInput)}
              disabled={loading || !followupInput.trim()}
              style={{
                padding: '8px 12px', borderRadius: 6, fontSize: 13, cursor: 'pointer',
                backgroundColor: C.claudeDim, border: `1px solid ${C.claudeBorder}`,
                color: C.claudeAccent, fontWeight: 700,
              }}>
              ↑
            </button>
          </div>
          {triageResults && (
            <button onClick={() => setAgentState('triage_complete')}
              style={{ background: 'none', border: 'none', color: C.textDim, fontSize: 11, cursor: 'pointer', textAlign: 'left' }}>
              ← Back to triage results
            </button>
          )}
        </div>
      </>
    );
  }

  function renderFollowup() {
    if (!verdictData) return null;
    const { verdict } = verdictData;
    const vColor = VERDICT_COLORS[verdict] || C.textDim;

    return (
      <>
        {/* Pinned verdict summary */}
        <div style={{ padding: '0 16px 10px', borderBottom: `1px solid ${C.border}` }}>
          <div style={{ padding: '8px 12px', borderRadius: 6, backgroundColor: `${vColor}12`, border: `1px solid ${vColor}30`, display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontWeight: 700, color: vColor, fontSize: 13 }}>{verdict}</span>
            <span style={{ fontSize: 11, color: C.textDim }}>{selectedTrade?.spread_label}</span>
          </div>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {followupThread.map((item, i) => (
            <div key={i}>
              {/* User bubble */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 6 }}>
                <div style={{ maxWidth: '80%', padding: '8px 12px', borderRadius: '12px 12px 3px 12px', backgroundColor: C.accentDim, color: C.text, fontSize: 12.5 }}>
                  {item.question}
                </div>
              </div>
              {/* Claude bubble */}
              <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                <div style={{ maxWidth: '90%', padding: '8px 12px', borderRadius: '12px 12px 12px 3px', backgroundColor: C.card, border: `1px solid ${C.border}`, color: C.text, fontSize: 12.5, lineHeight: 1.55 }}>
                  {item.response
                    ? <RenderMarkdown text={item.response} />
                    : (loading && i === followupThread.length - 1
                      ? <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: C.textDim }}><Spinner /> Thinking…</span>
                      : null
                    )}
                </div>
              </div>
            </div>
          ))}
        </div>

        <div style={{ padding: '12px 16px', borderTop: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              value={followupInput}
              onChange={e => setFollowupInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleFollowup(followupInput)}
              placeholder="Ask a follow-up question…"
              style={{
                flex: 1, padding: '8px 10px', borderRadius: 6, fontSize: 12,
                border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text,
                outline: 'none',
              }}
            />
            <button onClick={() => handleFollowup(followupInput)}
              disabled={loading || !followupInput.trim()}
              style={{
                padding: '8px 12px', borderRadius: 6, fontSize: 13, cursor: 'pointer',
                backgroundColor: C.claudeDim, border: `1px solid ${C.claudeBorder}`,
                color: C.claudeAccent, fontWeight: 700,
              }}>
              ↑
            </button>
          </div>
          <button onClick={() => setAgentState('verdict')}
            style={{ background: 'none', border: 'none', color: C.textDim, fontSize: 11, cursor: 'pointer', textAlign: 'left' }}>
            ← Back to analysis
          </button>
        </div>
      </>
    );
  }

  // ─── Main render ────────────────────────────────────────────────

  return (
    <>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      {/* Overlay */}
      {agentOpen && (
        <div onClick={closeAgent} style={{ position: 'fixed', inset: 0, backgroundColor: C.overlay, zIndex: 90 }} />
      )}

      {/* Panel */}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 420,
        backgroundColor: C.surface, borderLeft: `1px solid ${C.border}`,
        zIndex: 100,
        transform: agentOpen ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform 0.25s cubic-bezier(0.4,0,0.2,1)',
        boxShadow: agentOpen ? '-8px 0 30px rgba(0,0,0,0.4)' : 'none',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{ padding: '14px 16px 12px', borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                <span style={{ color: C.claudeAccent, fontSize: 16, fontWeight: 700 }}>✦</span>
                <span style={{ color: C.text, fontSize: 15, fontWeight: 700 }}>Ask Claude</span>
              </div>
              <div style={{ fontSize: 11, color: C.textDim, marginTop: 2 }}>
                {symbol} · {agentTrades.length} trade{agentTrades.length !== 1 ? 's' : ''}
              </div>
            </div>
            <button onClick={closeAgent} style={{
              background: 'none', border: 'none', color: C.textMuted, fontSize: 18,
              cursor: 'pointer', padding: '4px 8px', borderRadius: 4,
            }}>✕</button>
          </div>
        </div>

        {/* Body — one of the four state views */}
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          {agentState === 'idle' && renderIdle()}
          {agentState === 'triaging' && renderTriaging()}
          {agentState === 'triage_complete' && renderTriageComplete()}
          {agentState === 'pre_dive' && renderPreDive()}
          {agentState === 'diving' && renderDiving()}
          {agentState === 'verdict' && renderVerdict()}
          {agentState === 'followup' && renderFollowup()}
        </div>
      </div>
    </>
  );
}
