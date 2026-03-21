/**
 * TradeEvaluationCard — Renders one strategy's structured Claude evaluation.
 *
 * Sections (top → bottom):
 *   1. Header    — strategy label, score badge, verdict banner
 *   2. Trade     — trade_structure string, entry/profit/loss, exit levels
 *   3. Matrix    — ProbabilityMatrix (B-S, pre-computed)
 *   4. Claude    — claude_read, key_risks, thesis_invalidators
 *   5. Actions   — Follow (paper) + Take Position (live) buttons
 *
 * Props:
 *   card           — TradeEvaluationCard from POST /evaluate/structured
 *   symbol         — ticker string
 *   currentPrice   — float (for ProbabilityMatrix current-price highlight)
 *   smaData        — optional { smaShort, smaMid, smaLong }
 *   tradeData      — optional raw trade from analysis engine (for Follow/Take payload
 *                    and ProbabilityMatrix zone highlight)
 *   activeStrategy — string key (e.g. 'steady-paycheck')
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { followTrade, takeTrade } from '../api/client';
import { C, mono } from '../styles/tokens';
import ProbabilityMatrix from './ProbabilityMatrix';
import { useToast } from './Toast';

// ─── Currency formatter — ##,###.00 (no $ prefix, caller adds it) ────────────

const formatCurrency = (val) => {
  if (val == null || isNaN(val)) return '—';
  return Number(val).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
};

// ─── Verdict config ───────────────────────────────────────────────────────────

const VERDICT_CONFIG = {
  EXECUTE: { label: 'EXECUTE', bg: '#20C997', textColor: '#000' },
  WAIT:    { label: 'WAIT',    bg: C.amber,   textColor: '#000' },
  PASS:    { label: 'PASS',    bg: C.red,     textColor: '#fff' },
};

// ─── Score color (mirrors StrategyScorecard) ──────────────────────────────────

function scoreColor(score) {
  if (score >= 65) return C.green;
  if (score >= 35) return C.amber;
  return C.red;
}

// ─── DTE Warning Banner ───────────────────────────────────────────────────────

function DTEWarningBanner({ warning }) {
  if (!warning) return null;
  return (
    <div style={{
      margin: '0 16px',
      padding: '8px 12px',
      backgroundColor: C.amber + '18',
      border: `1px solid ${C.amber}50`,
      borderRadius: 6,
      display: 'flex',
      alignItems: 'flex-start',
      gap: 8,
      fontSize: 12,
      color: C.amber,
    }}>
      <span style={{ flexShrink: 0, fontSize: 14 }}>⚠</span>
      <span style={{ lineHeight: 1.5 }}>{warning}</span>
    </div>
  );
}

// ─── Pre-Screen Checks section ────────────────────────────────────────────────

function PreScreenSection({ card }) {
  const { credit_pct_of_width, debit_pct_of_width } = card;
  if (credit_pct_of_width == null && debit_pct_of_width == null) return null;

  const isCredit = credit_pct_of_width != null;
  const pct = isCredit ? credit_pct_of_width : debit_pct_of_width;
  const pctDisplay = (pct * 100).toFixed(1);

  let qualityColor;
  if (isCredit) {
    qualityColor = pct >= 0.30 ? C.green : pct >= 0.25 ? C.amber : C.red;
  } else {
    qualityColor = pct <= 0.35 ? C.green : pct <= 0.40 ? C.amber : C.red;
  }

  return (
    <Section>
      <SectionLabel>Pre-Screen Checks</SectionLabel>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12 }}>
        <span style={{ color: C.textDim }}>
          {isCredit ? 'Credit Quality' : 'Debit Quality'}
        </span>
        <span style={{ color: qualityColor, fontFamily: mono, fontWeight: 600 }}>
          {pctDisplay}% of width
        </span>
      </div>
    </Section>
  );
}

// ─── Shared section layout ────────────────────────────────────────────────────

function Section({ children, noBorderBottom }) {
  return (
    <div style={{
      padding: '14px 16px',
      borderBottom: noBorderBottom ? 'none' : `1px solid ${C.border}`,
    }}>
      {children}
    </div>
  );
}

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 9,
      fontWeight: 700,
      color: C.textMuted,
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      marginBottom: 10,
    }}>
      {children}
    </div>
  );
}

// ─── Section 1: Header ────────────────────────────────────────────────────────

function CardHeader({ card }) {
  const vc = VERDICT_CONFIG[card.verdict] || VERDICT_CONFIG.WAIT;
  const sc = scoreColor(card.score);

  return (
    <>
      {/* Verdict banner */}
      <div style={{
        backgroundColor: vc.bg,
        padding: '8px 16px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span style={{
          fontSize: 13,
          fontWeight: 800,
          color: vc.textColor,
          fontFamily: mono,
          letterSpacing: '0.06em',
        }}>
          {vc.label}
        </span>

        {/* Score badge */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          backgroundColor: 'rgba(0,0,0,0.2)',
          borderRadius: 4,
          padding: '3px 8px',
        }}>
          <span style={{
            fontSize: 10,
            color: vc.textColor,
            opacity: 0.75,
          }}>
            Score
          </span>
          <span style={{
            fontSize: 15,
            fontWeight: 800,
            fontFamily: mono,
            color: vc.textColor,
          }}>
            {card.score}
          </span>
        </div>
      </div>

      {/* Strategy label */}
      <div style={{
        padding: '8px 16px',
        backgroundColor: C.surface,
        borderBottom: `1px solid ${C.border}`,
      }}>
        <span style={{
          fontSize: 13,
          fontWeight: 600,
          color: C.text,
        }}>
          {card.strategy_label}
        </span>

        {/* Mini score bar */}
        <div style={{
          marginTop: 5,
          height: 3,
          borderRadius: 2,
          backgroundColor: C.border,
          overflow: 'hidden',
        }}>
          <div style={{
            height: '100%',
            width: `${card.score}%`,
            backgroundColor: sc,
            borderRadius: 2,
            transition: 'width 0.4s ease',
          }} />
        </div>
      </div>
    </>
  );
}

// ─── Section 2: Trade structure + exit levels ─────────────────────────────────

function TradeSection({ card, symbol }) {
  const maxProfitDollars = Math.round(card.max_profit * 100);
  const maxLossDollars   = Math.round(card.max_loss   * 100);
  const warnPnlDollars   = Math.round((card.exit_warning_pnl ?? 0) * 100);

  return (
    <Section>
      {/* Trade description */}
      <div style={{
        fontFamily: mono,
        fontSize: 13,
        fontWeight: 600,
        color: C.text,
        marginBottom: 10,
      }}>
        {card.trade_structure}
      </div>

      {/* Key numbers row */}
      <div style={{
        display: 'flex',
        gap: 16,
        flexWrap: 'wrap',
        marginBottom: 12,
      }}>
        <MetricPill label="Entry" value={`${formatCurrency(card.entry_price)} credit`} />
        <MetricPill label="Max Profit" value={formatCurrency(maxProfitDollars)} color={C.green} />
        <MetricPill label="Max Loss"   value={formatCurrency(maxLossDollars)}   color={C.red}   />
      </div>

      {/* Exit levels */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        <ExitRow
          label="Exit Warning"
          value={
            card.exit_warning_price != null
              ? `${symbol} below ${formatCurrency(card.exit_warning_price)}`
              : '—'
          }
          note={warnPnlDollars !== 0 ? `P&L: ${warnPnlDollars < 0 ? '-' : '+'}$${formatCurrency(Math.abs(warnPnlDollars))}` : null}
          color={C.amber}
        />
        <ExitRow
          label="Exit Target"
          value={
            card.exit_target_debit != null
              ? `Buy back at ${formatCurrency(card.exit_target_debit)} debit (50% profit)`
              : '—'
          }
          color={C.green}
        />
        <ExitRow
          label="Exit Stop"
          value={
            card.exit_stop_debit != null
              ? `Buy back at ${formatCurrency(card.exit_stop_debit)} debit (2x credit)`
              : '—'
          }
          color={C.red}
        />
      </div>
    </Section>
  );
}

function MetricPill({ label, value, color }) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 2,
    }}>
      <span style={{ fontSize: 9, color: C.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {label}
      </span>
      <span style={{
        fontFamily: mono,
        fontSize: 12,
        fontWeight: 600,
        color: color || C.text,
      }}>
        {value}
      </span>
    </div>
  );
}

function ExitRow({ label, value, note, color }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'baseline',
      gap: 8,
      fontSize: 11.5,
    }}>
      <span style={{
        color: color || C.textDim,
        fontWeight: 600,
        width: 80,
        flexShrink: 0,
      }}>
        {label}:
      </span>
      <span style={{ color: C.text, fontFamily: mono }}>
        {value}
      </span>
      {note && (
        <span style={{ color: C.textMuted, fontSize: 10.5, fontFamily: mono }}>
          ({note})
        </span>
      )}
    </div>
  );
}

// ─── Section 3: Probability Matrix ───────────────────────────────────────────

function MatrixSection({ card, currentPrice, tradeData }) {
  const tradeStructure = tradeData ? {
    spread_type: tradeData.spread_type,
    short_strike: tradeData.short_strike,
    long_strike:  tradeData.long_strike,
  } : null;

  return (
    <Section>
      <SectionLabel>Probability Matrix</SectionLabel>
      <ProbabilityMatrix
        matrix={card.probability_matrix}
        tradeStructure={tradeStructure}
        currentPrice={currentPrice}
      />
    </Section>
  );
}

// ─── Section 4: Claude's Read (or Auto-Pass Reason) ──────────────────────────

function ClaudeSection({ card }) {
  if (card.auto_pass_reason) {
    return (
      <Section>
        <SectionLabel>Auto-Pass Reason</SectionLabel>
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 10,
          padding: '10px 12px',
          backgroundColor: C.amber + '12',
          border: `1px solid ${C.amber}40`,
          borderRadius: 6,
        }}>
          <span style={{ fontSize: 15, color: C.amber, flexShrink: 0, lineHeight: 1.6 }}>ℹ</span>
          <p style={{
            fontSize: 12.5,
            color: C.amber,
            lineHeight: 1.65,
            margin: 0,
          }}>
            {card.auto_pass_reason}
          </p>
        </div>
      </Section>
    );
  }

  return (
    <Section>
      <SectionLabel>Claude's Read</SectionLabel>

      {/* claude_read prose */}
      <p style={{
        fontSize: 12.5,
        color: C.text,
        lineHeight: 1.65,
        margin: '0 0 14px 0',
        paddingLeft: 10,
        borderLeft: `2px solid ${C.claudeBorder}`,
      }}>
        {card.claude_read || '—'}
      </p>

      {/* Key Risks */}
      {card.key_risks?.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{
            fontSize: 10,
            fontWeight: 700,
            color: C.amber,
            textTransform: 'uppercase',
            letterSpacing: '0.07em',
            marginBottom: 6,
          }}>
            Key Risks
          </div>
          <BulletList items={card.key_risks} color={C.amber} />
        </div>
      )}

      {/* Thesis Invalidators */}
      {card.thesis_invalidators?.length > 0 && (
        <div>
          <div style={{
            fontSize: 10,
            fontWeight: 700,
            color: C.red,
            textTransform: 'uppercase',
            letterSpacing: '0.07em',
            marginBottom: 6,
          }}>
            This Trade is Wrong If
          </div>
          <BulletList items={card.thesis_invalidators} color={C.red} />
        </div>
      )}
    </Section>
  );
}

function BulletList({ items, color }) {
  return (
    <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
      {items.map((item, i) => (
        <li key={i} style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 8,
          fontSize: 12,
          color: C.text,
          lineHeight: 1.55,
          marginBottom: i < items.length - 1 ? 5 : 0,
        }}>
          <span style={{
            color,
            flexShrink: 0,
            marginTop: 2,
            fontSize: 11,
            fontFamily: mono,
          }}>
            •
          </span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

// ─── Section 5: Action buttons ────────────────────────────────────────────────

function ActionBar({ card, symbol, currentPrice, smaData, tradeData, activeStrategy }) {
  const [state, setState] = useState('idle'); // 'idle' | 'loading_follow' | 'loading_take' | 'done_follow' | 'done_take' | 'error'
  const [errorMsg, setErrorMsg] = useState(null);
  const { showToast } = useToast();
  const navigate = useNavigate();

  const buildPayload = () => {
    // Prefer tradeData for structured fields; fall back to card fields
    const tradeStructure = tradeData
      ? {
          spread_type:  tradeData.spread_type,
          short_strike: tradeData.short_strike,
          long_strike:  tradeData.long_strike,
          expiration:   tradeData.expiration,
          dte:          tradeData.dte,
        }
      : {
          trade_description: card.trade_structure,
        };

    return {
      symbol:                  symbol,
      strategy_key:            activeStrategy || card.strategy_key,
      trade_structure:         tradeStructure,
      entry_price:             card.entry_price ?? 0,
      entry_greeks: {
        delta: tradeData?.delta ?? null,
        theta: tradeData?.theta_per_day ?? null,
        iv:    tradeData?.iv ?? null,
      },
      entry_iv_rank:           tradeData?.iv ?? 0,
      entry_sma_alignment:     smaData
        ? { sma_8: smaData.smaShort, sma_21: smaData.smaMid, sma_50: smaData.smaLong }
        : {},
      entry_underlying_price:  currentPrice ?? 0,
      claude_score:            card.score ?? null,
    };
  };

  const handleAction = async (type) => {
    setState(type === 'follow' ? 'loading_follow' : 'loading_take');
    setErrorMsg(null);
    try {
      const payload = buildPayload();
      if (type === 'follow') {
        await followTrade(payload);
        setState('done_follow');
        showToast({
          message: 'Position added to Positions page',
          actionText: 'View Positions',
          onAction: () => navigate('/positions'),
        });
      } else {
        await takeTrade(payload);
        setState('done_take');
        showToast({
          message: 'Live position created',
          actionText: 'View Positions',
          onAction: () => navigate('/positions'),
        });
      }
    } catch (err) {
      setErrorMsg(err.message || 'Failed. Try again.');
      setState('error');
    }
  };

  const isDone  = state === 'done_follow' || state === 'done_take';
  const isError = state === 'error';
  const doneMsg = state === 'done_follow' ? 'Paper follow created' : 'Live position created';

  return (
    <Section noBorderBottom>
      {isError && (
        <div style={{
          fontSize: 11,
          color: C.red,
          backgroundColor: C.redBg,
          border: `1px solid ${C.red}30`,
          borderRadius: 4,
          padding: '6px 10px',
          marginBottom: 10,
          fontFamily: mono,
        }}>
          {errorMsg}
        </div>
      )}

      {isDone ? (
        <div style={{
          textAlign: 'center',
          fontSize: 12,
          color: C.green,
          backgroundColor: C.greenBg,
          border: `1px solid ${C.green}30`,
          borderRadius: 6,
          padding: '10px 0',
          fontFamily: mono,
          fontWeight: 600,
        }}>
          {doneMsg}
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 10 }}>
          <ActionButton
            label="Follow"
            icon="Pin"
            loading={state === 'loading_follow'}
            disabled={state === 'loading_take' || isDone}
            onClick={() => handleAction('follow')}
            color={C.accent}
          />
          <ActionButton
            label="Take Position"
            icon="Money"
            loading={state === 'loading_take'}
            disabled={state === 'loading_follow' || isDone}
            onClick={() => handleAction('take')}
            color={C.green}
          />
        </div>
      )}
    </Section>
  );
}

function ActionButton({ label, loading, disabled, onClick, color }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      style={{
        width: 'auto',
        padding: '7px 16px',
        borderRadius: 6,
        border: `1px solid ${(disabled || loading) ? C.border : color + '60'}`,
        backgroundColor: (disabled || loading) ? C.surface : color + '12',
        color: (disabled || loading) ? C.textMuted : color,
        fontSize: 12,
        fontWeight: 700,
        fontFamily: mono,
        cursor: (disabled || loading) ? 'not-allowed' : 'pointer',
        letterSpacing: '0.04em',
        transition: 'background-color 0.15s, border-color 0.15s',
      }}
    >
      {loading ? '...' : label}
    </button>
  );
}

// ─── Root component ───────────────────────────────────────────────────────────

export default function TradeEvaluationCard({
  card,
  symbol,
  currentPrice,
  smaData = null,
  tradeData = null,
  activeStrategy = null,
}) {
  if (!card) return null;

  const isAutoPass = !!card.auto_pass_reason;
  const hasMatrix = card.probability_matrix && Object.keys(card.probability_matrix).length > 0;

  return (
    <div style={{
      borderRadius: 8,
      border: `1px solid ${C.border}`,
      backgroundColor: C.card,
      overflow: 'hidden',
    }}>
      <CardHeader card={card} />
      <TradeSection card={card} symbol={symbol} />
      <PreScreenSection card={card} />
      {!isAutoPass && hasMatrix && (
        <MatrixSection card={card} currentPrice={currentPrice} tradeData={tradeData} />
      )}
      {!isAutoPass && card.dte_warning && (
        <DTEWarningBanner warning={card.dte_warning} />
      )}
      <ClaudeSection card={card} />
      <ActionBar
        card={card}
        symbol={symbol}
        currentPrice={currentPrice}
        smaData={smaData}
        tradeData={tradeData}
        activeStrategy={activeStrategy}
      />
    </div>
  );
}
