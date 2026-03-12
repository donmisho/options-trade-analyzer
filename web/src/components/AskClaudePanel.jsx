/**
 * AskClaudePanel — Thesis Matrix design.
 *
 * Phase 2.7 overhaul: replaced flat text sections with:
 *   Section 1 — Sticky header: verdict banner + metadata row + close button
 *   Section 2 — Table 1: Thesis Matrix (5 collapsible groups, 14 rows)
 *   Section 3 — Table 2: Action Command Center (WAIT vs EXECUTE shape)
 *   Section 4 — Sticky footer: primary CTA + Ask Follow-up
 *
 * Props unchanged: open, onClose, trade, smaData, smaPeriods
 * Bug fix: useEffect resets state when a different trade is selected.
 */

import { useState, useEffect } from 'react';
import { evaluateTrade } from '../api/client';
import { C, mono } from '../styles/tokens';

// ─── Color constants ──────────────────────────────────────────────────────────

// Verdict banner backgrounds (spec colors)
const VERDICT_BG    = { EXECUTE: '#20C997', WAIT: '#FF9E43' };
const VERDICT_ICON  = { EXECUTE: '⚡', WAIT: '⏳' };

// Status pip colors
const PIP = {
  pass:    C.green,   // #26a69a  — favorable
  caution: C.amber,   // #f59e0b  — marginal
  risk:    C.red,     // #ef5350  — warning
  alt:     C.purple,  // #a855f7  — suggestion
};

// ─── Tiny shared components ────────────────────────────────────────────────────

function Pip({ status }) {
  return (
    <div style={{
      width: 8, height: 8, borderRadius: '50%', flexShrink: 0, marginTop: 4,
      backgroundColor: PIP[status] || C.textMuted,
    }} />
  );
}

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 9, fontWeight: 700, color: C.textMuted,
      textTransform: 'uppercase', letterSpacing: '0.08em',
      marginTop: 18, marginBottom: 8,
    }}>
      {children}
    </div>
  );
}

// ─── Thesis Matrix ─────────────────────────────────────────────────────────────

function ThesisGroup({ title, rows, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  if (!rows?.length) return null;
  return (
    <div style={{ borderBottom: `1px solid ${C.borderSubtle}` }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', background: 'none', border: 'none', cursor: 'pointer',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '7px 0', color: C.textDim, fontSize: 11, fontWeight: 600,
          textTransform: 'uppercase', letterSpacing: '0.06em',
        }}
      >
        {title}
        <span style={{ fontSize: 10, opacity: 0.5 }}>{open ? '▲' : '▼'}</span>
      </button>

      {open && rows.map((row, i) => (
        <div key={i} style={{
          display: 'flex', gap: 8, alignItems: 'flex-start', padding: '6px 4px',
          borderTop: i > 0 ? `1px solid ${C.borderSubtle}` : 'none',
        }}>
          <span style={{
            color: C.textDim, fontSize: 11, width: 124, flexShrink: 0, lineHeight: 1.4,
          }}>
            {row.label}
          </span>
          <Pip status={row.status} />
          <span style={{ color: C.text, fontSize: 12, lineHeight: 1.5, flex: 1 }}>
            {row.text || '—'}
          </span>
        </div>
      ))}
    </div>
  );
}

function ThesisMatrix({ insights }) {
  if (!insights) return null;
  return (
    <div>
      <SectionLabel>Thesis Matrix</SectionLabel>
      <ThesisGroup
        title="Verdict & Directional Thesis"
        rows={insights.verdictAndThesis}
        defaultOpen
      />
      <ThesisGroup title="Trade Structure Quality"      rows={insights.tradeStructure} />
      <ThesisGroup title="Probability & Volatility"    rows={insights.probabilityAndVolatility} />
      <ThesisGroup title="Risk & Execution Flags"      rows={insights.riskAndExecution} />
      <ThesisGroup title="Alternate Considerations"    rows={insights.alternateConsiderations} />
    </div>
  );
}

// ─── Action Command Center ─────────────────────────────────────────────────────

function ActionCommandCenter({ plan, verdict }) {
  if (!plan) return null;
  const isExecute = verdict === 'EXECUTE';

  return (
    <div>
      <SectionLabel>Action Command Center</SectionLabel>

      {/* Criteria card */}
      {plan.criteria?.length > 0 && (
        <div style={{
          backgroundColor: isExecute ? '#20C99712' : '#FF9E4312',
          border: `1px solid ${isExecute ? '#20C99730' : '#FF9E4330'}`,
          borderRadius: 6, padding: '10px 12px', marginBottom: 12,
        }}>
          <div style={{
            fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
            textTransform: 'uppercase', marginBottom: 6,
            color: isExecute ? '#20C997' : '#FF9E43',
          }}>
            {isExecute ? 'Entry Confirmation' : 'Wait Criteria'}
          </div>
          {plan.criteria.map((c, i) => (
            <div key={i} style={{
              color: C.text, fontSize: 12, marginBottom: 4,
              display: 'flex', gap: 6, alignItems: 'flex-start',
            }}>
              <span style={{ color: isExecute ? '#20C997' : '#FF9E43', flexShrink: 0 }}>
                {isExecute ? '✓' : '◆'}
              </span>
              {c}
            </div>
          ))}
        </div>
      )}

      {/* Watch alerts table — WAIT only */}
      {!isExecute && plan.alerts?.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 12 }}>
          <tbody>
            {plan.alerts.map((a, i) => (
              <tr key={i} style={{ borderBottom: `1px solid ${C.borderSubtle}` }}>
                <td style={{ padding: '7px 4px', color: C.textDim, fontSize: 11, width: '42%' }}>
                  {a.label}
                </td>
                <td style={{
                  padding: '7px 4px', fontFamily: mono, fontWeight: 700, fontSize: 13,
                  color: a.type === 'confirm' ? C.green : C.red,
                }}>
                  {a.price != null ? a.price.toFixed(2) : '—'}
                </td>
                <td style={{ padding: '7px 4px', textAlign: 'right' }}>
                  <button style={{
                    padding: '2px 10px', borderRadius: 4, fontSize: 11,
                    border: `1px solid ${C.border}`, background: 'none',
                    color: C.textDim, cursor: 'pointer',
                  }} title="Set alert">
                    +
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Exit ladder — EXECUTE only */}
      {isExecute && plan.ladder?.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{
            fontSize: 9, fontWeight: 700, color: C.textMuted,
            textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6,
          }}>
            Exit Ladder
          </div>
          {plan.ladder.map((rung, i) => {
            const isStop = rung.label.toLowerCase().includes('stop');
            return (
              <div key={i} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '6px 8px', borderRadius: 4,
                backgroundColor: i % 2 === 0 ? C.card : 'transparent',
              }}>
                <span style={{ color: C.textDim, fontSize: 11 }}>{rung.label}</span>
                <span style={{
                  fontFamily: mono, fontWeight: 700, fontSize: 13,
                  color: isStop ? C.red : C.green,
                }}>
                  {rung.price != null ? rung.price.toFixed(2) : '—'}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Planning insight — WAIT only */}
      {!isExecute && (
        <div style={{
          fontSize: 11, color: C.textDim, paddingTop: 8,
          borderTop: `1px solid ${C.borderSubtle}`, lineHeight: 1.5,
        }}>
          If within 10 DTE without a trigger hit, roll to the next expiration cycle to preserve optionality.
        </div>
      )}
    </div>
  );
}

// ─── Main component ────────────────────────────────────────────────────────────

export default function AskClaudePanel({ open, onClose, trade, smaData, smaPeriods, riskConfig }) {
  // ── Thesis form state ──────────────────────────────────────────────────────
  const [direction,     setDirection]     = useState('Bullish');
  const [priceTarget,   setPriceTarget]   = useState('');
  const [timeframeDays, setTimeframeDays] = useState(30);
  const [conviction,    setConviction]    = useState('Medium');
  const [riskBudget,    setRiskBudget]    = useState(() => riskConfig?.max_risk_per_trade ?? 500);

  // ── Evaluation state ───────────────────────────────────────────────────────
  const [loading,        setLoading]       = useState(false);
  const [error,          setError]         = useState(null);
  const [result,         setResult]        = useState(null);
  const [originalContext, setOriginalContext] = useState('');
  const [activeVerdict,  setActiveVerdict] = useState(null);

  // ── Follow-up state ────────────────────────────────────────────────────────
  const [followUpOpen,    setFollowUpOpen]    = useState(false);
  const [followUpText,    setFollowUpText]    = useState('');
  const [followUpLoading, setFollowUpLoading] = useState(false);
  const [followUpHistory, setFollowUpHistory] = useState([]);

  // ── Reset when the selected trade changes ─────────────────────────────────
  useEffect(() => {
    setResult(null);
    setError(null);
    setFollowUpOpen(false);
    setFollowUpText('');
    setFollowUpHistory([]);
    setActiveVerdict(null);
    setOriginalContext('');
    if (trade?.spread_type) {
      setDirection(trade.spread_type.includes('bear') ? 'Bearish' : 'Bullish');
    }
  }, [trade?.long_strike, trade?.short_strike, trade?.expiration, trade?.spread_type]);

  if (!open || !trade) return null;

  // ── Derived display values ─────────────────────────────────────────────────
  const netCost      = trade.net_cost ?? trade.net_debit ?? 0;
  const isCredit     = netCost < 0;
  const netLabel     = isCredit ? 'CREDIT' : 'NET';
  const netDisplay   = isCredit ? `(${Math.abs(netCost).toFixed(2)})` : netCost.toFixed(2);
  const strategyLabel = trade.strategy_label || trade.spread_type || '';
  const buyStrike    = trade.buy_strike ?? trade.long_strike;
  const sellStrike   = trade.sell_strike ?? trade.short_strike;
  const optType      = trade.option_type || 'option';
  const currentVerdict = activeVerdict || result?.verdict;
  const verdictBg    = VERDICT_BG[currentVerdict] || C.amberBg;

  // ── Handlers ───────────────────────────────────────────────────────────────
  const handleEvaluate = async () => {
    setLoading(true);
    setError(null);
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
        `exp ${trade.expiration} | Net: ${netDisplay} | R:R: ${trade.reward_risk_ratio?.toFixed(2)} ` +
        `| Direction: ${direction} | Target: ${priceTarget || 'unset'} | Conviction: ${conviction}`
      );
    } catch (err) {
      setError(err.message || 'Evaluation failed');
    } finally {
      setLoading(false);
    }
  };

  const handleFollowUp = async () => {
    if (!followUpText.trim() || !result) return;
    const question = followUpText.trim();
    setFollowUpLoading(true);
    setFollowUpText('');
    try {
      const res = await fetch(
        `${import.meta.env.VITE_API_BASE_URL || ''}/api/v1/evaluate/follow-up`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(localStorage.getItem('ota_token')
              ? { Authorization: `Bearer ${localStorage.getItem('ota_token')}` }
              : {}),
          },
          body: JSON.stringify({
            question,
            original_trade_context: originalContext,
            original_verdict: currentVerdict || 'WAIT',
          }),
        }
      );
      if (!res.ok) throw new Error(`Follow-up failed: ${res.status}`);
      const data = await res.json();
      setFollowUpHistory(prev => [...prev, {
        question,
        answer: data.answer,
        updated_verdict: data.updated_verdict,
        updated_rationale: data.updated_rationale,
      }]);
      if (data.updated_verdict) setActiveVerdict(data.updated_verdict);
    } catch (err) {
      setFollowUpHistory(prev => [...prev, { question, answer: `Error: ${err.message}` }]);
    } finally {
      setFollowUpLoading(false);
    }
  };

  const reset = () => {
    setResult(null);
    setError(null);
    setFollowUpOpen(false);
    setFollowUpText('');
    setFollowUpHistory([]);
    setActiveVerdict(null);
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{
      position: 'fixed', right: 0, top: 0, bottom: 0, width: 500,
      backgroundColor: C.surface, borderLeft: `1px solid ${C.border}`,
      zIndex: 200, display: 'flex', flexDirection: 'column',
      boxShadow: '-4px 0 24px rgba(0,0,0,0.5)',
    }}>

      {result ? (
        // ── POST-EVALUATION VIEW ───────────────────────────────────────────────
        <>
          {/* Section 1: Sticky header */}
          <div style={{ flexShrink: 0 }}>
            {/* Verdict banner */}
            <div style={{
              backgroundColor: verdictBg,
              padding: '10px 16px',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
              <span style={{ fontSize: 15, fontWeight: 800, color: '#000', letterSpacing: '0.05em' }}>
                {VERDICT_ICON[currentVerdict] || '◆'} {currentVerdict}
              </span>
              <button onClick={onClose} style={{
                background: 'none', border: 'none', color: 'rgba(0,0,0,0.5)',
                fontSize: 18, cursor: 'pointer', lineHeight: 1,
              }}>✕</button>
            </div>

            {/* Metadata row */}
            <div style={{
              padding: '7px 16px', backgroundColor: C.bg,
              borderBottom: `1px solid ${C.border}`,
              display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap',
              fontSize: 11, color: C.textDim,
            }}>
              <span style={{ fontFamily: mono, fontWeight: 700, color: C.text }}>{trade.symbol}</span>
              <span>·</span>
              <span>{strategyLabel || `${buyStrike}/${sellStrike}`}</span>
              <span>·</span>
              <span>{trade.expiration}</span>
              {priceTarget && (
                <>
                  <span>·</span>
                  <span>Target <span style={{ fontFamily: mono, color: C.text }}>{priceTarget}</span></span>
                </>
              )}
              <span>·</span>
              <span>{direction} · {conviction}</span>
            </div>
          </div>

          {/* Scrollable body */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '4px 16px 16px' }}>

            {/* Pre-screen flags */}
            {result.pre_screen_flags?.length > 0 && (
              <div style={{ marginTop: 12, marginBottom: 4 }}>
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

            {/* Section 2: Thesis Matrix */}
            <ThesisMatrix insights={result.thesisInsights} />

            {/* Section 3: Action Command Center */}
            <ActionCommandCenter plan={result.executionPlan} verdict={currentVerdict} />

            {/* Re-evaluate link */}
            <button onClick={reset} style={{
              marginTop: 14, background: 'none', border: 'none',
              color: C.textMuted, fontSize: 11, cursor: 'pointer',
              padding: 0, textDecoration: 'underline',
            }}>
              ← Re-evaluate with different thesis
            </button>

            {/* Follow-up conversation history */}
            {followUpHistory.length > 0 && (
              <div style={{ marginTop: 16, borderTop: `1px solid ${C.border}`, paddingTop: 12 }}>
                <div style={{
                  fontSize: 9, fontWeight: 700, color: C.textMuted,
                  textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8,
                }}>
                  Follow-up Thread
                </div>
                {followUpHistory.map((entry, i) => (
                  <div key={i} style={{ marginBottom: 12 }}>
                    <div style={{
                      backgroundColor: C.card, borderRadius: 6, padding: '7px 10px',
                      fontSize: 12, color: C.textDim, marginBottom: 4,
                    }}>
                      💬 {entry.question}
                    </div>
                    <div style={{
                      padding: '8px 12px', backgroundColor: C.bg,
                      border: `1px solid ${C.border}`, borderRadius: 6,
                      fontSize: 12, color: C.text, lineHeight: 1.6,
                    }}>
                      {entry.answer}
                      {entry.updated_verdict && (
                        <div style={{
                          marginTop: 6, fontSize: 11,
                          color: VERDICT_BG[entry.updated_verdict] || C.amber,
                        }}>
                          Verdict updated → {entry.updated_verdict}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Inline follow-up input */}
            {followUpOpen && (
              <div style={{ marginTop: 12, borderTop: `1px solid ${C.border}`, paddingTop: 12 }}>
                <textarea
                  value={followUpText}
                  onChange={e => setFollowUpText(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleFollowUp();
                    }
                  }}
                  placeholder="e.g. What if VIX spikes next week?"
                  rows={2}
                  autoFocus
                  style={{
                    width: '100%', padding: '6px 8px', borderRadius: 4,
                    boxSizing: 'border-box', border: `1px solid ${C.border}`,
                    backgroundColor: C.bg, color: C.text, fontSize: 12,
                    resize: 'none', outline: 'none',
                  }}
                />
                <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                  <button
                    onClick={handleFollowUp}
                    disabled={followUpLoading || !followUpText.trim()}
                    style={{
                      padding: '6px 16px', borderRadius: 4, fontSize: 12,
                      border: `1px solid ${C.claudeBorder}`, backgroundColor: C.claudeDim,
                      color: C.claudeAccent, cursor: followUpLoading ? 'wait' : 'pointer',
                      opacity: followUpLoading || !followUpText.trim() ? 0.5 : 1,
                    }}
                  >
                    {followUpLoading ? 'Asking…' : 'Ask'}
                  </button>
                  <button
                    onClick={() => { setFollowUpOpen(false); setFollowUpText(''); }}
                    style={{
                      padding: '6px 10px', borderRadius: 4, fontSize: 12,
                      border: `1px solid ${C.border}`, background: 'none',
                      color: C.textMuted, cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Section 4: Sticky footer */}
          <div style={{
            flexShrink: 0, padding: '12px 16px',
            borderTop: `1px solid ${C.border}`, backgroundColor: C.bg,
            display: 'flex', gap: 8,
          }}>
            <button style={{
              flex: 1, padding: '9px 0', borderRadius: 6,
              backgroundColor: verdictBg, border: 'none',
              color: '#000', fontSize: 12, fontWeight: 700, cursor: 'pointer',
            }}>
              {currentVerdict === 'EXECUTE' ? '⚡ Draft Order in Broker' : '🔔 Set All Triggers'}
            </button>
            <button
              onClick={() => setFollowUpOpen(o => !o)}
              style={{
                padding: '9px 14px', borderRadius: 6, whiteSpace: 'nowrap',
                border: `1px solid ${C.claudeBorder}`, backgroundColor: C.claudeDim,
                color: C.claudeAccent, fontSize: 12, cursor: 'pointer',
              }}
            >
              💬 Ask Follow-up
            </button>
          </div>
        </>

      ) : (
        // ── PRE-EVALUATION VIEW (thesis form — unchanged) ──────────────────────
        <>
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
                [netLabel, netDisplay, isCredit ? C.green : C.text],
                ['MAX PROFIT', trade.max_profit?.toFixed(2), C.green],
                ['R:R', trade.reward_risk_ratio?.toFixed(2), C.text],
                ['PROB', `${((trade.prob_of_profit || 0) * 100).toFixed(0)}%`, C.text],
              ].map(([label, value, color]) => (
                <div key={label} style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 9, color: C.textMuted, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 2 }}>
                    {label}
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 700, color, fontFamily: mono }}>{value}</div>
                </div>
              ))}
            </div>

            {/* Thesis form */}
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
              value={priceTarget}
              onChange={e => setPriceTarget(e.target.value)}
              style={{
                width: '100%', padding: '6px 8px', borderRadius: 4, boxSizing: 'border-box',
                border: `1px solid ${C.border}`, backgroundColor: C.bg,
                color: C.text, fontSize: 13, marginBottom: 14, outline: 'none',
              }}
            />

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
              <div>
                <label style={{ fontSize: 12, color: C.textDim, display: 'block', marginBottom: 4 }}>Timeframe (days)</label>
                <input
                  type="number" min={1} max={365} value={timeframeDays}
                  onChange={e => setTimeframeDays(parseInt(e.target.value) || 30)}
                  style={{ width: '100%', padding: '6px 8px', borderRadius: 4, boxSizing: 'border-box', border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text, fontSize: 13, outline: 'none' }}
                />
              </div>
              <div>
                <label style={{ fontSize: 12, color: C.textDim, display: 'block', marginBottom: 4 }}>Risk Budget ($)</label>
                <input
                  type="number" min={50} step={50} value={riskBudget}
                  onChange={e => setRiskBudget(parseFloat(e.target.value) || 500)}
                  style={{ width: '100%', padding: '6px 8px', borderRadius: 4, boxSizing: 'border-box', border: `1px solid ${C.border}`, backgroundColor: C.bg, color: C.text, fontSize: 13, outline: 'none' }}
                />
              </div>
            </div>

            <label style={{ fontSize: 12, color: C.textDim, display: 'block', marginBottom: 6 }}>Conviction</label>
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              {['Low', 'Medium', 'High'].map(conv => (
                <button key={conv} onClick={() => setConviction(conv)} style={{
                  padding: '5px 14px', borderRadius: 4, fontSize: 12,
                  border: `1px solid ${conviction === conv ? C.claudeBorder : C.border}`,
                  backgroundColor: conviction === conv ? C.claudeDim : 'transparent',
                  color: conviction === conv ? C.claudeAccent : C.textDim,
                  cursor: 'pointer',
                }}>{conv}</button>
              ))}
            </div>

            {/* Error */}
            {error && (
              <div style={{
                color: '#f87171', fontSize: 13, padding: '8px 12px',
                backgroundColor: C.redBg, borderRadius: 6, marginBottom: 12,
              }}>
                {error}
                <button onClick={() => setError(null)} style={{
                  marginLeft: 12, background: 'none', border: 'none',
                  color: '#f87171', cursor: 'pointer', fontSize: 12,
                }}>
                  Dismiss
                </button>
              </div>
            )}

            <button
              onClick={handleEvaluate}
              disabled={loading}
              style={{
                width: '100%', padding: '10px 0', borderRadius: 6,
                fontSize: 13, fontWeight: 700,
                border: `1px solid ${C.claudeBorder}`, backgroundColor: C.claudeDim,
                color: C.claudeAccent, cursor: loading ? 'wait' : 'pointer',
                opacity: loading ? 0.6 : 1,
              }}
            >
              {loading ? 'Evaluating…' : '✦ Evaluate This Trade'}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
