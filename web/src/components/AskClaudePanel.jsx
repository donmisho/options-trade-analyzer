/**
 * AskClaudePanel — Single-trade evaluation using structured output.
 *
 * @deprecated
 * This panel and the /evaluate/trade backend endpoint have been superseded
 * by the TradeAgentPanel flow (triage → deep-dive → follow-up via agent routes).
 * Retained for reference and potential future use (e.g. direct Foundry vs.
 * Anthropic latency comparisons). Do not wire into new pages without discussion.
 *
 * Last active: VerticalsPage (removed March 2026 — eval button dropped in favour
 * of the ✦ Ask Claude agent flow).
 */

import { useState } from 'react';
import { evaluateTrade } from '../api/client';
import { C } from '../styles/tokens';

// ─── Constants ───────────────────────────────────────────────────

const VERDICT_COLORS = {
  EXECUTE: { bg: C.greenBg,  border: '#22c55e', text: '#4ade80' },
  WAIT:    { bg: C.amberBg,  border: C.amber,   text: '#fbbf24' },
  PASS:    { bg: C.redBg,    border: C.red,     text: '#f87171' },
};

// ─── Sub-components ──────────────────────────────────────────────

function VerdictBanner({ verdict, rationale, note }) {
  const colors = VERDICT_COLORS[verdict] || VERDICT_COLORS.WAIT;
  const icon = verdict === 'EXECUTE' ? '✦' : verdict === 'WAIT' ? '⏳' : '✗';
  return (
    <div style={{
      backgroundColor: colors.bg, border: `1px solid ${colors.border}`,
      borderRadius: 8, padding: '12px 16px', marginBottom: 12,
    }}>
      <div style={{ fontSize: 19, fontWeight: 800, color: colors.text, letterSpacing: 2 }}>
        {icon} {verdict}
        {note && <span style={{ fontSize: 12, fontWeight: 400, marginLeft: 10, opacity: 0.7 }}>{note}</span>}
      </div>
      {rationale && (
        <div style={{ fontSize: 13, color: colors.text, opacity: 0.85, marginTop: 4, lineHeight: 1.5 }}>
          {rationale}
        </div>
      )}
    </div>
  );
}

function CollapsibleSection({ title, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ borderBottom: `1px solid ${C.border}`, marginBottom: 4 }}>
      <button onClick={() => setOpen(o => !o)} style={{
        background: 'none', border: 'none', width: '100%', textAlign: 'left',
        color: C.text, fontSize: 13, fontWeight: 600, cursor: 'pointer',
        padding: '8px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        {title}
        <span style={{ opacity: 0.4, fontSize: 10 }}>{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div style={{ fontSize: 13, color: C.textDim, lineHeight: 1.65, paddingBottom: 10, paddingLeft: 4 }}>
          {children}
        </div>
      )}
    </div>
  );
}

function BulletList({ items, color }) {
  if (!items?.length) return null;
  return (
    <ul style={{ margin: 0, paddingLeft: 16 }}>
      {items.map((item, i) => (
        <li key={i} style={{ color: color || C.textDim, marginBottom: 4 }}>{item}</li>
      ))}
    </ul>
  );
}

function AlertTable({ alerts }) {
  if (!alerts?.length) return null;
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <tbody>
        {alerts.map((a, i) => (
          <tr key={i} style={{ borderBottom: `1px solid ${C.border}` }}>
            <td style={{ padding: '4px 6px', color: C.textDim, whiteSpace: 'nowrap' }}>{a.label}</td>
            <td style={{ padding: '4px 6px', color: C.accent, fontWeight: 700, whiteSpace: 'nowrap' }}>{a.price_or_value}</td>
            <td style={{ padding: '4px 6px', color: C.text }}>{a.action}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ExitPlanCard({ exitPlan }) {
  if (!exitPlan) return null;
  return (
    <div style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
      {exitPlan.underlying_alerts?.length > 0 && (
        <div>
          <div style={{ color: C.textMuted, fontWeight: 600, marginBottom: 4, textTransform: 'uppercase', fontSize: 10, letterSpacing: 1 }}>
            📊 Underlying Price Alerts
          </div>
          <AlertTable alerts={exitPlan.underlying_alerts} />
        </div>
      )}
      {exitPlan.spread_value_alerts?.length > 0 && (
        <div>
          <div style={{ color: C.textMuted, fontWeight: 600, marginBottom: 4, textTransform: 'uppercase', fontSize: 10, letterSpacing: 1 }}>
            💰 Spread Value Alerts
          </div>
          <AlertTable alerts={exitPlan.spread_value_alerts} />
        </div>
      )}
      {exitPlan.time_rules?.length > 0 && (
        <div>
          <div style={{ color: C.textMuted, fontWeight: 600, marginBottom: 4, textTransform: 'uppercase', fontSize: 10, letterSpacing: 1 }}>
            ⏰ Time Rules
          </div>
          <BulletList items={exitPlan.time_rules} />
        </div>
      )}
    </div>
  );
}

// ─── Structured response renderer ────────────────────────────────

function StructuredEvaluation({ result }) {
  return (
    <div>
      <CollapsibleSection title="Thesis Alignment">
        {result.thesis_alignment}
      </CollapsibleSection>
      <CollapsibleSection title="Risk / Reward Quality">
        {result.risk_reward_quality}
      </CollapsibleSection>
      <CollapsibleSection title="Probability & Expected Move">
        {result.probability_assessment}
      </CollapsibleSection>
      {result.red_flags?.length > 0 && (
        <CollapsibleSection title={`🚩 Red Flags (${result.red_flags.length})`}>
          <BulletList items={result.red_flags} color="#f87171" />
        </CollapsibleSection>
      )}
      {result.alternatives?.length > 0 && (
        <CollapsibleSection title="💡 Alternatives">
          <BulletList items={result.alternatives} color="#60a5fa" />
        </CollapsibleSection>
      )}
      {result.exit_plan && (
        <CollapsibleSection title="Exit Plan">
          <ExitPlanCard exitPlan={result.exit_plan} />
        </CollapsibleSection>
      )}
    </div>
  );
}

// ─── Legacy free-text renderer (backward compat) ─────────────────

function LegacyTextEvaluation({ text }) {
  return (
    <div style={{
      fontSize: 13, color: C.textDim, lineHeight: 1.65,
      whiteSpace: 'pre-wrap', fontFamily: 'inherit',
    }}>
      {text}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────

export default function AskClaudePanel({ open, onClose, trade, smaData }) {
  const [direction, setDirection] = useState(
    trade?.spread_type?.includes('bear') ? 'Bearish' : 'Bullish'
  );
  const [priceTarget, setPriceTarget] = useState('');
  const [timeframeDays, setTimeframeDays] = useState(30);
  const [conviction, setConviction] = useState('Medium');
  const [riskBudget, setRiskBudget] = useState(500);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [originalContext, setOriginalContext] = useState('');

  const [followUpText, setFollowUpText] = useState('');
  const [followUpLoading, setFollowUpLoading] = useState(false);
  const [followUpResult, setFollowUpResult] = useState(null);
  const [activeVerdict, setActiveVerdict] = useState(null);

  if (!open || !trade) return null;

  // ── Derived trade display values ──────────────────────────────
  const netCost = trade.net_cost ?? trade.net_debit ?? 0;
  const isCredit = netCost < 0;
  const netLabel = isCredit ? 'CREDIT' : 'NET';
  const netDisplay = isCredit ? `($${Math.abs(netCost).toFixed(2)})` : `$${netCost.toFixed(2)}`;
  const strategyLabel = trade.strategy_label || trade.spread_type || '';
  const buyStrike = trade.buy_strike ?? trade.long_strike;
  const sellStrike = trade.sell_strike ?? trade.short_strike;
  const optType = trade.option_type || 'option';

  // ── Detect response format ────────────────────────────────────
  const isStructured = result && typeof result === 'object' && typeof result.verdict === 'string';
  const legacyText = !isStructured && result
    ? (typeof result === 'string' ? result : result?.analysis || result?.text || null)
    : null;
  const currentVerdict = activeVerdict || (isStructured ? result.verdict : null);

  // ── Handlers ─────────────────────────────────────────────────
  const handleEvaluate = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setFollowUpResult(null);
    setActiveVerdict(null);

    try {
      const payload = {
        symbol: trade.symbol,
        current_price: smaData?.price || 0,
        sma_8: smaData?.smaShort || 0,
        sma_21: smaData?.smaMid || 0,
        sma_50: smaData?.smaLong || 0,
        ma_alignment: smaData?.alignment || 'mixed',
        spread_type: trade.spread_type,
        option_type: optType,
        buy_strike: buyStrike,
        sell_strike: sellStrike,
        long_strike: trade.long_strike,
        short_strike: trade.short_strike,
        expiration: trade.expiration,
        net_cost: netCost,
        net_debit: trade.net_debit,
        is_credit: isCredit,
        max_profit: trade.max_profit,
        max_loss: trade.max_loss ?? Math.abs(netCost),
        breakeven: trade.breakeven,
        reward_risk_ratio: trade.reward_risk_ratio,
        prob_of_profit: trade.prob_of_profit,
        composite_score: trade.composite_score,
        thesis: {
          direction,
          price_target: priceTarget ? parseFloat(priceTarget) : null,
          timeframe_days: timeframeDays,
          conviction,
          risk_budget: riskBudget,
        },
      };

      const data = await evaluateTrade(payload);
      setResult(data);
      setActiveVerdict(data.verdict);

      setOriginalContext(
        `${trade.symbol} ${strategyLabel} — Buy ${buyStrike} / Sell ${sellStrike} ${optType} ` +
        `exp ${trade.expiration} | Net: ${netDisplay} | Max profit: $${trade.max_profit?.toFixed(2)} ` +
        `| R:R: ${trade.reward_risk_ratio?.toFixed(2)} | Direction: ${direction} | Target: ${priceTarget || 'unset'}`
      );
    } catch (err) {
      setError(err.message || 'Evaluation failed');
    } finally {
      setLoading(false);
    }
  };

  const handleFollowUp = async () => {
    if (!followUpText.trim() || !result) return;
    setFollowUpLoading(true);
    setFollowUpResult(null);

    try {
      const res = await fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/v1/evaluate/follow-up`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(localStorage.getItem('ota_token') ? { Authorization: `Bearer ${localStorage.getItem('ota_token')}` } : {}),
        },
        body: JSON.stringify({
          question: followUpText,
          original_trade_context: originalContext,
          original_verdict: currentVerdict || 'WAIT',
        }),
      });
      if (!res.ok) throw new Error(`Follow-up failed: ${res.status}`);
      const data = await res.json();
      setFollowUpResult(data);
      if (data.updated_verdict) setActiveVerdict(data.updated_verdict);
      setFollowUpText('');
    } catch (err) {
      setFollowUpResult({ answer: `Error: ${err.message}` });
    } finally {
      setFollowUpLoading(false);
    }
  };

  const reset = () => { setResult(null); setFollowUpResult(null); setActiveVerdict(null); setError(null); };

  // ── Render ───────────────────────────────────────────────────
  return (
    <div style={{
      position: 'fixed', right: 0, top: 0, bottom: 0, width: 500,
      backgroundColor: C.surface, borderLeft: `1px solid ${C.border}`,
      zIndex: 200, display: 'flex', flexDirection: 'column',
      boxShadow: '-4px 0 24px rgba(0,0,0,0.5)',
    }}>
      {/* Header */}
      <div style={{
        padding: '14px 16px', borderBottom: `1px solid ${C.border}`,
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
        backgroundColor: C.bg, flexShrink: 0,
      }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: C.claudeAccent, marginBottom: 2 }}>
            ✦ Ask Claude — {trade.symbol} {strategyLabel}
          </div>
          <div style={{ fontSize: 12, color: C.textDim }}>
            Buy {buyStrike} / Sell {sellStrike} {optType} · {trade.expiration}
          </div>
        </div>
        <button onClick={onClose} style={{
          background: 'none', border: 'none', color: C.textDim,
          fontSize: 18, cursor: 'pointer', lineHeight: 1, paddingLeft: 8,
        }}>✕</button>
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>

        {/* Trade stats card */}
        <div style={{
          backgroundColor: C.bg, border: `1px solid ${C.border}`,
          borderRadius: 6, padding: '10px 14px', marginBottom: 16,
          display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '4px 8px',
        }}>
          {[
            [netLabel, netDisplay, isCredit ? '#4ade80' : C.text],
            ['MAX PROFIT', `$${trade.max_profit?.toFixed(2)}`, '#4ade80'],
            ['R:R', trade.reward_risk_ratio?.toFixed(2), C.text],
            ['PROB', `${(trade.prob_of_profit * 100).toFixed(0)}%`, C.text],
          ].map(([label, value, color]) => (
            <div key={label} style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 9, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 2 }}>{label}</div>
              <div style={{ fontSize: 13, fontWeight: 700, color, fontFamily: "'IBM Plex Mono', monospace" }}>{value}</div>
            </div>
          ))}
        </div>

        {/* Thesis form (hidden after evaluation) */}
        {!result && (
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12 }}>
              Your Thesis
            </div>

            <label style={{ fontSize: 12, color: C.textDim, display: 'block', marginBottom: 6 }}>Direction</label>
            <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
              {['Bullish', 'Bearish', 'Neutral'].map(d => (
                <button key={d} onClick={() => setDirection(d)} style={{
                  padding: '5px 14px', borderRadius: 4, fontSize: 12,
                  border: `1px solid ${direction === d ? C.claudeBorder : C.border}`,
                  backgroundColor: direction === d ? C.claudeDim : 'transparent',
                  color: direction === d ? C.claudeAccent : C.textDim,
                  cursor: 'pointer',
                }}>{d}</button>
              ))}
            </div>

            <label style={{ fontSize: 12, color: C.textDim, display: 'block', marginBottom: 4 }}>Price Target</label>
            <input
              type="number" step="0.5"
              placeholder={`e.g. ${((smaData?.price || 100) * (direction === 'Bearish' ? 0.97 : 1.03)).toFixed(0)}`}
              value={priceTarget} onChange={e => setPriceTarget(e.target.value)}
              style={{
                width: '100%', padding: '6px 8px', borderRadius: 4, boxSizing: 'border-box',
                border: `1px solid ${C.border}`, backgroundColor: C.bg,
                color: C.text, fontSize: 13, marginBottom: 14,
              }}
            />

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
              <div>
                <label style={{ fontSize: 12, color: C.textDim, display: 'block', marginBottom: 4 }}>Timeframe (days)</label>
                <input type="number" min={1} max={365} value={timeframeDays}
                  onChange={e => setTimeframeDays(parseInt(e.target.value) || 30)}
                  style={{ width: '100%', padding: '6px 8px', borderRadius: 4, boxSizing: 'border-box', border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text, fontSize: 13 }}
                />
              </div>
              <div>
                <label style={{ fontSize: 12, color: C.textDim, display: 'block', marginBottom: 4 }}>Risk Budget ($)</label>
                <input type="number" min={50} step={50} value={riskBudget}
                  onChange={e => setRiskBudget(parseFloat(e.target.value) || 500)}
                  style={{ width: '100%', padding: '6px 8px', borderRadius: 4, boxSizing: 'border-box', border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text, fontSize: 13 }}
                />
              </div>
            </div>

            <label style={{ fontSize: 12, color: C.textDim, display: 'block', marginBottom: 6 }}>Conviction</label>
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              {['Low', 'Medium', 'High'].map(c => (
                <button key={c} onClick={() => setConviction(c)} style={{
                  padding: '5px 14px', borderRadius: 4, fontSize: 12,
                  border: `1px solid ${conviction === c ? C.claudeBorder : C.border}`,
                  backgroundColor: conviction === c ? C.claudeDim : 'transparent',
                  color: conviction === c ? C.claudeAccent : C.textDim,
                  cursor: 'pointer',
                }}>{c}</button>
              ))}
            </div>

            <button onClick={handleEvaluate} disabled={loading} style={{
              width: '100%', padding: '10px 0', borderRadius: 6, fontSize: 13, fontWeight: 700,
              border: `1px solid ${C.claudeBorder}`, backgroundColor: C.claudeDim,
              color: C.claudeAccent, cursor: loading ? 'wait' : 'pointer',
              opacity: loading ? 0.6 : 1,
            }}>
              {loading ? 'Evaluating…' : '✦ Evaluate This Trade'}
            </button>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{
            color: '#f87171', fontSize: 13, padding: '8px 12px',
            backgroundColor: C.redBg, borderRadius: 6, marginBottom: 12,
          }}>
            {error}
            <button onClick={reset} style={{
              marginLeft: 12, background: 'none', border: 'none',
              color: '#f87171', cursor: 'pointer', fontSize: 12,
            }}>Try again</button>
          </div>
        )}

        {/* Evaluation result */}
        {result && (
          <div>
            {/* Verdict banner — shows updated verdict if follow-up changed it */}
            <VerdictBanner
              verdict={activeVerdict}
              rationale={
                followUpResult?.updated_verdict
                  ? followUpResult.updated_rationale
                  : (isStructured ? result.verdict_rationale : null)
              }
              note={followUpResult?.updated_verdict ? `(updated from ${result.verdict})` : null}
            />

            {/* Pre-screen flags */}
            {isStructured && result.pre_screen_flags?.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                {result.pre_screen_flags.map((f, i) => (
                  <div key={i} style={{
                    fontSize: 12, padding: '4px 10px', borderRadius: 4, marginBottom: 4,
                    backgroundColor: f.level === 'alert' ? C.redBg : C.amberBg,
                    color: f.level === 'alert' ? '#f87171' : '#fbbf24',
                    border: `1px solid ${f.level === 'alert' ? '#ef444430' : '#f59e0b30'}`,
                  }}>
                    {f.level === 'alert' ? '⚠ ' : '⚡ '}{f.msg}
                  </div>
                ))}
              </div>
            )}

            {/* Analysis sections */}
            {isStructured ? <StructuredEvaluation result={result} /> : <LegacyTextEvaluation text={legacyText} />}

            <button onClick={reset} style={{
              marginTop: 14, padding: '5px 12px', borderRadius: 4, fontSize: 12,
              border: `1px solid ${C.border}`, backgroundColor: 'transparent',
              color: C.textDim, cursor: 'pointer',
            }}>
              ← Re-evaluate
            </button>

            {/* Follow-up */}
            <div style={{ marginTop: 16, borderTop: `1px solid ${C.border}`, paddingTop: 14 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
                Follow-up
              </div>
              <textarea
                value={followUpText}
                onChange={e => setFollowUpText(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleFollowUp(); } }}
                placeholder="e.g. What if VIX spikes next week?"
                rows={2}
                style={{
                  width: '100%', padding: '6px 8px', borderRadius: 4, boxSizing: 'border-box',
                  border: `1px solid ${C.border}`, backgroundColor: C.bg,
                  color: C.text, fontSize: 12, resize: 'vertical',
                }}
              />
              <button onClick={handleFollowUp} disabled={followUpLoading || !followUpText.trim()} style={{
                marginTop: 6, padding: '6px 16px', borderRadius: 4, fontSize: 12,
                border: `1px solid ${C.claudeBorder}`, backgroundColor: C.claudeDim,
                color: C.claudeAccent, cursor: followUpLoading ? 'wait' : 'pointer',
                opacity: followUpLoading || !followUpText.trim() ? 0.5 : 1,
              }}>
                {followUpLoading ? 'Asking…' : 'Ask'}
              </button>

              {followUpResult && (
                <div style={{
                  marginTop: 10, padding: '10px 12px', backgroundColor: C.bg,
                  borderRadius: 6, border: `1px solid ${C.border}`,
                }}>
                  <div style={{ fontSize: 13, color: C.text, lineHeight: 1.65 }}>
                    {followUpResult.answer}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
