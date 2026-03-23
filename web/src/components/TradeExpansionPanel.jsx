/**
 * TradeExpansionPanel — 4-column expansion panel for Verticals (and Puts & Calls).
 *
 * Replaces the previous 2-column layout (Score Breakdown + Ask Claude).
 * Spec: UI-DECISIONS.md → "Verticals Page — Expansion Panel (Revised)"
 *
 * Column 1: Score Breakdown — colored dot + metric + weight badge + bar
 * Column 2: Actual Calculation — formula with real numbers + norm bar + contribution
 * Column 3: Strategy Fit — single-select radio rows + "Evaluate with Claude →"
 * Column 4: Strategy Explanation — selected strategy params + signal check box
 *
 * Verdict Card: slides in below the 4-column panel after Claude evaluation.
 *
 * State managed internally:
 *   selectedStrategy  — string | null (auto-set to highest scorer)
 *   verdictVisible    — boolean
 *   verdictLoading    — boolean
 *   verdictData       — object | null
 *
 * Rules:
 *   - When selectedStrategy changes, collapse and clear verdictVisible/verdictData
 *   - Column 4 updates immediately on strategy click (no API call)
 *   - Verdict card slides in with CSS max-height transition
 *   - All buttons use exact styles from Button Standards in UI-DECISIONS.md
 *   - Width: auto on all buttons (never full-width)
 */

import { useState, useEffect, useRef } from 'react';
import { STRATEGY_CONFIGS } from '../strategy-configs/index';
import { evaluateStructured, followupTrade } from '../api/client';

// ─── Spec-exact colors (override tokens.js for this component) ────────────────
// These are the canonical colors from UI-DECISIONS.md Color System.
const TEAL   = '#2dd4bf';
const GREEN  = '#4ade80';
const AMBER  = '#f59e0b';
const RED    = '#f87171';
const PURPLE = '#c084fc';
const BLUE   = '#60a5fa';

const TEXT  = '#e6edf3';
const MUTED = '#8b949e';
const DIM   = '#444d56';
const BG    = '#0d1117';
const BG2   = '#161b22';
const BG3   = '#21262d';
const BORD  = '#30363d';

// Metric colors — locked per UI-DECISIONS.md. Never change.
const METRIC_COLORS = {
  expected_value:   BLUE,
  reward_risk:      TEAL,
  probability:      AMBER,
  liquidity:        PURPLE,
  theta_efficiency: RED,
};

function scoreColor(s) {
  if (s >= 70) return GREEN;
  if (s >= 40) return AMBER;
  return RED;
}

// ─── Button Standards (exact from UI-DECISIONS.md) ────────────────────────────
const BTN_TEAL = {
  background: 'rgba(45,212,191,0.1)',
  border: '1px solid rgba(45,212,191,0.4)',
  color: TEAL,
  padding: '7px 16px',
  borderRadius: 4,
  fontSize: 11,
  fontFamily: 'monospace',
  cursor: 'pointer',
  width: 'auto',
};

const BTN_TEAL_LOADING = {
  ...BTN_TEAL,
  background: 'rgba(45,212,191,0.06)',
  color: MUTED,
  cursor: 'default',
  pointerEvents: 'none',
};

const BTN_GREEN = {
  background: 'rgba(74,222,128,0.12)',
  border: '1px solid rgba(74,222,128,0.45)',
  color: GREEN,
  fontWeight: 700,
  padding: '7px 16px',
  borderRadius: 4,
  fontSize: 11,
  fontFamily: 'monospace',
  cursor: 'pointer',
  width: 'auto',
};

const BTN_NEUTRAL = {
  background: 'transparent',
  border: `1px solid ${BORD}`,
  color: MUTED,
  padding: '7px 14px',
  borderRadius: 4,
  fontSize: 11,
  fontFamily: 'monospace',
  cursor: 'pointer',
  width: 'auto',
};

// ─── Animated dots for loading state ─────────────────────────────────────────
const DOT_STYLE = `
  @keyframes dotpulse {
    0%, 80%, 100% { opacity: 0.2; transform: scale(0.8); }
    40% { opacity: 1; transform: scale(1); }
  }
  .epDot1 { display: inline-block; animation: dotpulse 1.4s infinite 0.0s; }
  .epDot2 { display: inline-block; animation: dotpulse 1.4s infinite 0.2s; }
  .epDot3 { display: inline-block; animation: dotpulse 1.4s infinite 0.4s; }
  .epVerdictSlide {
    animation: verdictIn 0.4s ease;
  }
  @keyframes verdictIn {
    from { opacity: 0; transform: translateY(-6px); }
    to   { opacity: 1; transform: translateY(0); }
  }
`;

function AnimatedDots() {
  return (
    <>
      <style>{DOT_STYLE}</style>
      <span className="epDot1">.</span>
      <span className="epDot2">.</span>
      <span className="epDot3">.</span>
    </>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Return actual calculation string for column 2 */
function getCalcDisplay(metricKey, trade) {
  // Long options (naked calls/puts) have different fields than vertical spreads
  const isLongOpt = !trade.spread_type && !!trade.option_type;

  if (isLongOpt) {
    const delta    = trade.delta ?? 0;
    const prem     = trade.premium_dollars ?? 0;
    const thetaPD  = trade.theta_per_day_dollars ?? 0;
    const runway   = trade.theta_runway_days ?? 0;
    const iv       = trade.iv ?? 0;
    const vol      = trade.volume ?? 0;
    const oi       = trade.open_interest ?? 0;

    switch (metricKey) {
      case 'delta_alignment':
        return `Δ ${delta.toFixed(3)}`;
      case 'iv_value':
        return `IV ${(iv * 100).toFixed(1)}%`;
      case 'theta_efficiency':
        if (!prem) return '—';
        return `θ $${thetaPD.toFixed(2)}/day · ${runway}d runway`;
      case 'reward_risk':
        if (!prem) return '—';
        return `(Δ ${delta.toFixed(3)} × 100) / ${prem.toFixed(2)} = ${(delta * 100 / prem).toFixed(2)}`;
      case 'liquidity':
        return `vol ${vol.toLocaleString()} · OI ${oi.toLocaleString()}`;
      default:
        return '—';
    }
  }

  // Vertical spreads
  const prob  = trade.prob_of_profit ?? 0;
  const maxP  = ((trade.max_profit  ?? 0) * 100);
  const maxL  = ((trade.max_loss    ?? Math.abs(trade.net_debit ?? 0)) * 100);
  const theta = trade.net_theta;

  switch (metricKey) {
    case 'expected_value': {
      const ev = prob * maxP - (1 - prob) * maxL;
      return `(${prob.toFixed(2)}×${maxP.toFixed(0)}) − (${(1 - prob).toFixed(2)}×${maxL.toFixed(0)}) = ${ev >= 0 ? '+' : ''}${ev.toFixed(0)}`;
    }
    case 'reward_risk':
      if (!maxL) return '—';
      return `${maxP.toFixed(0)} / ${maxL.toFixed(0)} = ${(maxP / maxL).toFixed(2)}`;
    case 'probability':
      return `${(prob * 100).toFixed(1)}% prob of profit`;
    case 'liquidity':
      return 'volume + open interest';
    case 'theta_efficiency':
      if (theta == null || !maxL) return '—';
      return `θ${theta.toFixed(4)} / ${maxL.toFixed(0)} = ${(theta / maxL * 100).toFixed(4)}`;
    default:
      return '—';
  }
}

/** Return 'pass' | 'fail' | 'neutral' for a configSchema param against a trade */
function getParamStatus(paramKey, paramDefault, trade) {
  const dte   = trade.dte;
  const delta = Math.abs(trade.net_delta ?? trade.delta ?? 0);
  const ivRk  = trade.iv_rank;

  switch (paramKey) {
    case 'dte_min':      return dte    != null ? (dte    >= paramDefault ? 'pass' : 'fail') : 'neutral';
    case 'dte_max':      return dte    != null ? (dte    <= paramDefault ? 'pass' : 'fail') : 'neutral';
    case 'delta_max':    return delta  ?         (delta  <= paramDefault ? 'pass' : 'fail') : 'neutral';
    case 'delta_min':    return delta  ?         (delta  >= paramDefault ? 'pass' : 'fail') : 'neutral';
    case 'iv_rank_min':  return ivRk   != null ? (ivRk   >= paramDefault ? 'pass' : 'fail') : 'neutral';
    case 'iv_rank_max':  return ivRk   != null ? (ivRk   <= paramDefault ? 'pass' : 'fail') : 'neutral';
    default:             return 'neutral';
  }
}

/** Format a configSchema default value for display */
function formatParamValue(key, val, unit) {
  if (val == null) return '—';
  return unit ? `${val}${unit}` : String(val);
}

/** Build 3-4 signal items for a strategy + trade + smaData */
function getSignals(strategyKey, trade, smaData) {
  const cfg = STRATEGY_CONFIGS[strategyKey];
  if (!cfg) return [];
  const signals = [];

  // 1. SMA alignment
  const { smaShort, smaMid, smaLong, price } = smaData || {};
  if (smaShort && smaMid && smaLong && price) {
    const bullish = price > smaShort && smaShort > smaMid && smaMid > smaLong;
    const bearish = smaShort < smaMid;
    signals.push({
      label: bullish ? 'SMA: bullish — 8 > 21 > 50'
           : bearish ? 'SMA: bearish — short < mid'
           : 'SMA: mixed — no clear alignment',
      status: bullish ? 'green' : bearish ? 'red' : 'amber',
    });
  }

  // 2. DTE in strategy range
  const dte = trade.dte;
  if (dte != null && cfg.dte_min != null && cfg.dte_max != null) {
    const inRange = dte >= cfg.dte_min && dte <= cfg.dte_max;
    signals.push({
      label: `DTE ${dte} (target ${cfg.dte_min}–${cfg.dte_max})`,
      status: inRange ? 'green' : 'amber',
    });
  }

  // 3. Delta
  const delta = Math.abs(trade.net_delta ?? trade.delta ?? 0);
  const deltaSchema = cfg.configSchema?.find(s => s.key === 'delta_max');
  if (delta && deltaSchema?.default) {
    signals.push({
      label: `Delta ${delta.toFixed(3)} (≤${deltaSchema.default} target)`,
      status: delta <= deltaSchema.default ? 'green' : 'red',
    });
  }

  // 4. Composite score
  const scorePct = trade.composite_score ?? 0;
  signals.push({
    label: `Composite score ${scorePct} / 100`,
    status: scorePct >= 70 ? 'green' : scorePct >= 40 ? 'amber' : 'red',
  });

  return signals.slice(0, 4);
}

// ─── Column 1: Score Breakdown ────────────────────────────────────────────────
function ScoreBreakdownCol({ trade, config }) {
  const metrics = config.scoreMetrics || [];
  return (
    <div style={{ padding: '16px 14px' }}>
      <div style={{ fontSize: 9, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 12 }}>
        Score Breakdown
      </div>
      {metrics.map((m, i) => {
        const color     = METRIC_COLORS[m.key] || m.color;
        const normScore = Math.max(0, Math.min(1, trade[m.field] ?? 0));
        return (
          <div key={m.key} style={{ marginBottom: i < metrics.length - 1 ? 12 : 0 }}>
            {/* Dot + label + weight badge */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: color, flexShrink: 0 }} />
              <span style={{ fontSize: 11, color: TEXT }}>{m.label}</span>
              <span style={{
                fontSize: 9, padding: '1px 5px', borderRadius: 3,
                background: color + '22', color, fontWeight: 600,
              }}>
                {m.weightPct}%
              </span>
            </div>
            {/* Formula */}
            <div style={{ fontSize: 9, fontStyle: 'italic', color: MUTED, marginLeft: 12, marginBottom: 4 }}>
              {m.formula}
            </div>
            {/* 3px bar */}
            <div style={{ marginLeft: 12, height: 3, backgroundColor: BG3, borderRadius: 2, overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                width: `${normScore * 100}%`,
                backgroundColor: color,
                borderRadius: 2,
                transition: 'width 0.3s ease',
              }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Column 2: Actual Calculation ─────────────────────────────────────────────
function ActualCalcCol({ trade, config }) {
  const metrics = config.scoreMetrics || [];
  const total   = metrics.reduce((sum, m) => sum + (trade[m.field] ?? 0) * m.weightPct, 0);

  return (
    <div style={{ padding: '16px 14px' }}>
      <div style={{ fontSize: 9, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 12 }}>
        Actual Calculation
      </div>
      {metrics.map((m, i) => {
        const color   = METRIC_COLORS[m.key] || m.color;
        const norm    = Math.max(0, Math.min(1, trade[m.field] ?? 0));
        const contrib = norm * m.weightPct;
        return (
          <div key={m.key} style={{ marginBottom: i < metrics.length - 1 ? 10 : 0 }}>
            <div style={{ fontSize: 9, color: MUTED, marginBottom: 2 }}>{m.label}</div>
            {/* Dark inset box */}
            <div style={{
              background: BG2,
              borderLeft: `2px solid ${BORD}`,
              padding: '3px 8px',
              borderRadius: '0 3px 3px 0',
              fontSize: 10,
              fontFamily: 'monospace',
              marginBottom: 3,
            }}>
              <span style={{ color }}>{getCalcDisplay(m.key, trade)}</span>
            </div>
            {/* norm label + mini bar + contribution */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ fontSize: 9, color: DIM }}>norm</span>
              <div style={{ flex: 1, height: 2, background: BG3, borderRadius: 1, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${norm * 100}%`, background: color, borderRadius: 1 }} />
              </div>
              <span style={{ fontSize: 9, color, minWidth: 48, textAlign: 'right', fontFamily: 'monospace' }}>
                {contrib >= 0 ? '+' : ''}{contrib.toFixed(2)}
              </span>
            </div>
          </div>
        );
      })}
      {/* Totals row */}
      <div style={{
        marginTop: 10, paddingTop: 8,
        borderTop: `1px solid ${BORD}`,
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span style={{ fontSize: 9, color: MUTED }}>
          composite → {total.toFixed(2)}
        </span>
        <span style={{
          fontSize: 14, fontWeight: 700, fontFamily: 'monospace',
          color: scoreColor(total),
        }}>
          {total.toFixed(2)}
        </span>
      </div>
    </div>
  );
}

// ─── Column 3: Strategy Fit ───────────────────────────────────────────────────
function StrategyFitCol({ strategies, notApplicable, selectedKey, onSelect, onEvaluate, evalState }) {
  return (
    <div style={{ padding: '16px 14px', display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ fontSize: 9, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 12 }}>
        Strategy Fit
      </div>

      <div style={{ flex: 1 }}>
        {strategies.map(s => {
          const key      = s.key ?? s.strategy_key;
          const label    = s.label ?? s.strategy_label ?? key;
          const score    = s.score ?? 0;
          const isActive = key === selectedKey;
          const hint     = s.signal_summary
            ? s.signal_summary
            : score >= 70 ? 'Strong fit — parameters align well'
            : score >= 40 ? 'Moderate fit — some params outside ideal range'
            : 'Score below threshold for this strategy';

          return (
            <div
              key={key}
              onClick={() => onSelect(key)}
              style={{
                cursor: 'pointer',
                borderLeft: `2px solid ${isActive ? TEAL : 'transparent'}`,
                background: isActive ? 'rgba(45,212,191,0.06)' : 'transparent',
                padding: '6px 8px 4px',
                borderRadius: '0 4px 4px 0',
                marginBottom: 4,
                transition: 'background 0.15s',
              }}
            >
              {/* Name + score */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                <span style={{
                  fontSize: 10,
                  color: isActive ? TEAL : TEXT,
                  fontWeight: isActive ? 600 : 400,
                  flex: 1,
                }}>
                  {label}
                </span>
                <span style={{ fontSize: 11, fontWeight: 700, color: scoreColor(score), fontFamily: 'monospace' }}>
                  {score}
                </span>
              </div>
              {/* Score bar */}
              <div style={{ height: 2, background: BG3, borderRadius: 1, marginBottom: 3 }}>
                <div style={{ height: '100%', width: `${score}%`, background: scoreColor(score), borderRadius: 1 }} />
              </div>
              {/* Hint */}
              <div style={{ fontSize: 9, fontStyle: 'italic', color: MUTED }}>{hint}</div>
            </div>
          );
        })}

        {/* P-2: Non-applicable strategies — grayed, non-interactive */}
        {notApplicable?.length > 0 && (
          <>
            <div style={{ borderTop: `1px dashed ${BORD}`, margin: '8px 0 6px' }} />
            <div style={{ fontSize: 9, fontStyle: 'italic', color: MUTED, marginBottom: 6 }}>
              not applicable to this trade type
            </div>
            {notApplicable.map(s => {
              const key   = s.key ?? s.strategy_key;
              const label = s.label ?? s.strategy_label ?? key;
              const score = s.score ?? 0;
              return (
                <div
                  key={key}
                  style={{
                    opacity: 0.35,
                    pointerEvents: 'none',
                    padding: '6px 8px 4px',
                    marginBottom: 4,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                    <span style={{ fontSize: 10, color: TEXT, flex: 1 }}>{label}</span>
                    <span style={{ fontSize: 11, fontFamily: 'monospace', color: MUTED }}>{score}</span>
                  </div>
                  <div style={{ height: 2, background: BG3, borderRadius: 1, marginBottom: 3 }}>
                    <div style={{ height: '100%', width: `${score}%`, background: MUTED, borderRadius: 1 }} />
                  </div>
                  <div style={{ fontSize: 9, fontStyle: 'italic', color: MUTED }}>{STRATEGY_CONFIGS[key]?.non_applicable_reason ?? 'not applicable to this trade type'}</div>
                </div>
              );
            })}
          </>
        )}
      </div>

      {/* Evaluate button */}
      <div style={{ marginTop: 12, paddingTop: 10, borderTop: `1px solid ${BORD}` }}>
        {evalState === 'loading' ? (
          <>
            <button style={BTN_TEAL_LOADING}>
              Evaluating<AnimatedDots />
            </button>
            {selectedKey && (
              <div style={{ fontSize: 9, color: DIM, marginTop: 5 }}>
                {selectedKey} · evaluating…
              </div>
            )}
          </>
        ) : (
          <button onClick={onEvaluate} style={BTN_TEAL}>
            {evalState === 'reevaluate' ? 'Re-evaluate →' : 'Evaluate with Claude →'}
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Column 4: Strategy Explanation ──────────────────────────────────────────
function StrategyExplainCol({ strategyKey, trade, smaData }) {
  if (!strategyKey) {
    return <div style={{ padding: 16, color: MUTED, fontSize: 10 }}>Loading strategy details…</div>;
  }
  const cfg = STRATEGY_CONFIGS[strategyKey];
  if (!cfg) return <div style={{ padding: 16 }} />;

  // Parameter rows — only keys we know how to compare
  const PARAM_KEYS = ['dte_min', 'dte_max', 'delta_max', 'delta_min', 'iv_rank_min', 'iv_rank_max'];
  const paramRows = (cfg.configSchema || [])
    .filter(p => PARAM_KEYS.includes(p.key))
    .map(p => ({
      label:  p.label,
      value:  formatParamValue(p.key, p.default, p.unit),
      status: getParamStatus(p.key, p.default, trade),
    }));

  const signals = getSignals(strategyKey, trade, smaData);
  const subtitle = cfg.description || `${cfg.dte_min ?? 0}–${cfg.dte_max ?? 60} DTE · ${(cfg.trade_structure ?? '').replace('_', ' ')}`;

  return (
    <div style={{ padding: '16px 14px' }}>
      <div style={{ fontSize: 9, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 8 }}>
        Strategy Details
      </div>
      <div style={{ fontSize: 12, fontWeight: 700, color: TEAL, marginBottom: 3 }}>{cfg.label}</div>
      <div style={{ fontSize: 9, color: MUTED, marginBottom: 10, lineHeight: 1.5 }}>{subtitle}</div>

      {/* OTA-158: Parameter grid — 2 columns inside dark inset box */}
      {paramRows.length > 0 ? (
        <div style={{ background: BG, borderRadius: 4, padding: '8px 10px', marginBottom: 8 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 10px' }}>
            {paramRows.map(p => (
              <div key={p.label}>
                <div style={{ fontSize: 9, textTransform: 'uppercase', color: MUTED, marginBottom: 1 }}>
                  {p.label}
                </div>
                <div style={{
                  fontSize: 11,
                  color: p.status === 'pass' ? GREEN : p.status === 'fail' ? RED : TEXT,
                }}>
                  {p.status === 'pass' ? '✓ ' : p.status === 'fail' ? '✗ ' : ''}{p.value}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div style={{ background: BG, borderRadius: 4, padding: '8px 10px', marginBottom: 8 }}>
          <div style={{ fontSize: 9, color: MUTED, fontStyle: 'italic' }}>
            Strategy parameters not yet configured
          </div>
        </div>
      )}

      {/* OTA-159: Signal check box with section label */}
      {signals.length > 0 && (
        <div style={{ background: BG, borderRadius: 4, padding: '8px 10px', marginTop: 8 }}>
          <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.5px', color: MUTED, marginBottom: 6 }}>
            Signal Checks
          </div>
          {signals.map((sig, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'flex-start', gap: 6,
              marginBottom: i < signals.length - 1 ? 5 : 0,
              lineHeight: 1.6,
            }}>
              <div style={{
                width: 6, height: 6, borderRadius: '50%', flexShrink: 0, marginTop: 2,
                background: sig.status === 'green' ? '#4ade80'
                          : sig.status === 'amber' ? '#f59e0b'
                          : '#f87171',
              }} />
              <span style={{ fontSize: 9, color: MUTED, lineHeight: 1.6 }}>{sig.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Verdict Card ─────────────────────────────────────────────────────────────
const VERDICT_COLORS = {
  EXECUTE: { bg: 'rgba(74,222,128,.15)',  text: GREEN,  border: 'rgba(74,222,128,0.4)' },
  WAIT:    { bg: 'rgba(245,158,11,.15)',  text: AMBER,  border: 'rgba(245,158,11,0.4)' },
  PASS:    { bg: 'rgba(248,113,113,.15)', text: RED,    border: 'rgba(248,113,113,0.4)' },
};

function VerdictCard({ verdictData, trade, symbol, strategyKey, onFollow, onTake, onDiscard }) {
  const [followUpText,    setFollowUpText]    = useState('');
  const [followUpLoading, setFollowUpLoading] = useState(false);
  const [followUpHistory, setFollowUpHistory] = useState([]);
  // Ref-based in-flight guard: prevents double-submission from rapid Enter presses
  // before the followUpLoading state update has propagated.
  const followUpInFlight = useRef(false);

  const verdict = verdictData.verdict || 'WAIT';
  const vc      = VERDICT_COLORS[verdict] || VERDICT_COLORS.WAIT;
  const cfg     = STRATEGY_CONFIGS[strategyKey];

  // Trade reference string
  const isCredit     = trade.net_debit != null && trade.net_debit < 0;
  const credit       = isCredit ? Math.abs(trade.net_debit) : 0;
  const isLongOpt    = !trade.spread_type && !!trade.option_type;
  const optSuffix    = isLongOpt ? (trade.option_type === 'put' ? 'P' : 'C') : '';
  const strikeStr    = trade.long_strike && trade.short_strike
    ? `${trade.long_strike}/${trade.short_strike}`
    : trade.strike ? `${trade.strike}${optSuffix}` : '';
  const typeStr      = isLongOpt
    ? `Long ${trade.option_type === 'put' ? 'Put' : 'Call'}`
    : trade.spread_type?.replace('_', ' ')?.toUpperCase() || trade.option_type?.toUpperCase() || '';
  const debitAmt     = !isCredit ? Math.abs(trade.net_debit ?? trade.premium_dollars ?? 0) : 0;
  const priceStr     = credit ? `${credit.toFixed(2)} cr` : (debitAmt > 0 ? `${debitAmt.toFixed(2)} debit` : '');
  const tradeRef     = [symbol, typeStr, strikeStr, trade.expiration?.slice(5), priceStr]
    .filter(Boolean).join(' · ');
  const ts = verdictData.evaluated_at
    ? new Date(verdictData.evaluated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : '';

  // Exit levels — prefer Claude's underlying-price exit plan (from verdictData),
  // fall back to client-side estimation if Claude didn't return them.
  const isLongOption = !trade.spread_type && !!trade.option_type;
  const isPut        = trade.spread_type?.includes('put') || trade.option_type === 'put';
  const shortStrike  = trade.short_strike ?? trade.strike ?? 0;
  // Client-side fallback values for warning level (underlying-based)
  const warningFallback = shortStrike ? (shortStrike * (isPut ? 1.0125 : 0.9875)).toFixed(2) : '—';
  // Use Claude's underlying prices when available; fall back to client-side
  const takeProfitVal  = verdictData.take_profit  != null ? verdictData.take_profit.toFixed(2)  : '—';
  const warningLevelVal = verdictData.warning_level != null ? verdictData.warning_level.toFixed(2) : warningFallback;
  const hardStopVal    = verdictData.hard_stop    != null ? verdictData.hard_stop.toFixed(2)    : '—';

  // Pre-screen checks
  const rr    = trade.reward_risk_ratio ?? 0;
  const pop   = trade.prob_of_profit ?? 0;
  const score = trade.composite_score ?? 0;
  // DTE: use trade.dte if > 0, otherwise compute from trade.expiration
  let dte = trade.dte ?? 0;
  if (!dte && trade.expiration) {
    const expStr = trade.expiration;
    let expDate;
    if (/^\d{4}-\d{2}-\d{2}/.test(expStr)) {
      expDate = new Date(expStr + 'T00:00:00');
    } else if (/^\d{2}-\d{2}-\d{4}/.test(expStr)) {
      const [m, d, y] = expStr.split('-');
      expDate = new Date(`${y}-${m}-${d}T00:00:00`);
    } else if (/^\d{2}\/\d{2}\/\d{4}/.test(expStr)) {
      const [m, d, y] = expStr.split('/');
      expDate = new Date(`${y}-${m}-${d}T00:00:00`);
    }
    if (expDate && !isNaN(expDate)) {
      dte = Math.max(0, Math.floor((expDate - new Date()) / (1000 * 60 * 60 * 24)));
    }
  }
  const checks = [
    { label: `R:R ${rr.toFixed(2)}`, status: rr >= 1.0 ? 'pass' : rr >= 0.5 ? 'caution' : 'fail' },
    { label: `PoP ${(pop * 100).toFixed(2)}%`, status: pop >= 0.55 ? 'pass' : pop >= 0.45 ? 'caution' : 'fail' },
    { label: `Score ${score.toFixed(2)}`, status: score >= 65 ? 'pass' : score >= 45 ? 'caution' : 'fail' },
    { label: `DTE ${dte}`, status: dte >= 7 ? 'pass' : 'caution' },
  ];

  // Risk budget
  const maxLossPerShare = trade.max_loss ?? Math.abs(trade.net_debit ?? 0);
  const maxLossDollars  = maxLossPerShare * 100;
  const ACCT_DEFAULT    = 10000;
  const riskPct         = ACCT_DEFAULT > 0 ? (maxLossDollars / ACCT_DEFAULT * 100).toFixed(1) : '—';

  const handleFollowUp = async () => {
    const q = followUpText.trim();
    // Ref check prevents double-submission before React state update propagates
    if (!q || followUpLoading || followUpInFlight.current) return;
    followUpInFlight.current = true;
    setFollowUpText('');
    setFollowUpLoading(true);

    // Build spread_label: vertical spreads have spread_type but not spread_label.
    // The backend FollowUpRequest requires spread_label as a non-optional string.
    const spreadLabel = trade.spread_label
      || trade.label
      || [
          (trade.spread_type || trade.option_type || 'option').replace(/_/g, ' '),
          trade.long_strike && trade.short_strike
            ? `${trade.long_strike}/${trade.short_strike}`
            : (trade.strike != null ? String(trade.strike) : ''),
        ].filter(Boolean).join(' ')
      || 'trade';

    try {
      const res = await followupTrade(
        { ...trade, symbol, spread_label: spreadLabel },
        verdict,
        verdictData.claude_read || '',
        q,
        null,
      );
      // Backend returns { response: "..." } — not "answer"
      setFollowUpHistory(prev => [...prev, { question: q, answer: res.response || 'No response received.' }]);
    } catch {
      setFollowUpHistory(prev => [...prev, { question: q, answer: 'Follow-up failed — please try again.' }]);
    } finally {
      setFollowUpLoading(false);
      followUpInFlight.current = false;
    }
  };

  return (
    <div
      className="epVerdictSlide"
      style={{
        background: '#0a0f15',
        borderTop: `2px solid ${vc.border}`,
      }}
    >
      {/* Header */}
      <div style={{
        padding: '10px 16px',
        borderBottom: `1px solid ${BG3}`,
        display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
      }}>
        <span style={{
          padding: '2px 9px', borderRadius: 3, fontSize: 11, fontWeight: 700,
          background: vc.bg, color: vc.text, letterSpacing: '0.05em',
        }}>
          {verdict}
        </span>
        <span style={{
          padding: '2px 8px', borderRadius: 3, fontSize: 10,
          background: 'rgba(192,132,252,0.12)',
          color: PURPLE,
          border: '1px solid rgba(192,132,252,0.3)',
        }}>
          {cfg?.label || strategyKey}
        </span>
        <span style={{ fontSize: 10, color: MUTED, flex: 1 }}>{tradeRef}</span>
        <span style={{ fontSize: 9, color: DIM }}>{ts}</span>
      </div>

      {/* Body — 3 columns */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1.4fr 1fr 1fr',
        padding: '14px 16px',
        gap: 0,
      }}>

        {/* Claude's Read */}
        <div style={{ paddingRight: 14 }}>
          <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.6px', color: MUTED, marginBottom: 8 }}>
            Claude's Read
          </div>
          {verdictData.auto_pass_reason ? (
            <div style={{ fontSize: 10, color: AMBER, lineHeight: 1.65, padding: '8px 10px', background: 'rgba(245,158,11,0.08)', borderRadius: 4, border: '1px solid rgba(245,158,11,0.2)' }}>
              {verdictData.auto_pass_reason}
            </div>
          ) : (
            <div style={{ fontSize: 10, color: '#c9d1d9', lineHeight: 1.65 }}>
              {verdictData.claude_read || 'No evaluation text available.'}
            </div>
          )}
          {verdictData.dte_warning && !verdictData.auto_pass_reason && (
            <div style={{ marginTop: 6, fontSize: 9, color: AMBER, padding: '4px 8px', background: 'rgba(245,158,11,0.06)', borderRadius: 3 }}>
              ⚠ {verdictData.dte_warning}
            </div>
          )}
          {verdictData.key_risks?.length > 0 && (
            <div style={{ marginTop: 8 }}>
              {verdictData.key_risks.map((r, i) => (
                <div key={i} style={{ fontSize: 9, color: MUTED, marginBottom: 2 }}>• {r}</div>
              ))}
            </div>
          )}
          {/* Follow-up Q&A history */}
          {followUpHistory.map((entry, i) => (
            <div key={i} style={{ marginTop: 10, paddingTop: 8, borderTop: `1px solid ${BORD}` }}>
              <div style={{ fontSize: 9, color: DIM, marginBottom: 3 }}>Q: {entry.question}</div>
              <div style={{ fontSize: 10, color: '#c9d1d9', lineHeight: 1.6 }}>
                {entry.answer}
              </div>
            </div>
          ))}
        </div>

        {/* Exit Plan */}
        <div style={{ borderLeft: `1px solid ${BG3}`, paddingLeft: 14, paddingRight: 14 }}>
          <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.6px', color: MUTED, marginBottom: 8 }}>
            Exit Plan
          </div>
          {[
            { label: 'TAKE PROFIT',   sub: 'underlying price — full profit exit',  value: takeProfitVal,   color: GREEN },
            { label: 'WARNING LEVEL', sub: 'underlying price — early warning',      value: warningLevelVal, color: AMBER },
            { label: 'HARD STOP',     sub: 'underlying price — cut the loss',       value: hardStopVal,     color: RED   },
          ].map((row, i, arr) => (
            <div key={row.label} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
              padding: '5px 0',
              borderBottom: i < arr.length - 1 ? `1px dashed ${BG3}` : 'none',
            }}>
              <div>
                <div style={{ fontSize: 9, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{row.label}</div>
                <div style={{ fontSize: 8, color: DIM }}>{row.sub}</div>
              </div>
              <span style={{ fontSize: 11, fontWeight: 700, fontFamily: 'monospace', color: row.color }}>
                {row.value}
              </span>
            </div>
          ))}
        </div>

        {/* Pre-Screen Checks */}
        <div style={{ borderLeft: `1px solid ${BG3}`, paddingLeft: 14 }}>
          <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.6px', color: MUTED, marginBottom: 8 }}>
            Pre-Screen Checks
          </div>
          {checks.map((c, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
              <div style={{
                width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                background: c.status === 'pass' ? GREEN : c.status === 'caution' ? AMBER : RED,
              }} />
              <span style={{ fontSize: 9, color: MUTED }}>{c.label}</span>
            </div>
          ))}
          {/* Risk budget box */}
          <div style={{
            marginTop: 8, background: BG2, borderRadius: 4, padding: '6px 8px',
          }}>
            <div style={{ fontSize: 9, color: MUTED, marginBottom: 2 }}>Risk Budget</div>
            <div style={{ fontSize: 11, color: TEXT, fontFamily: 'monospace' }}>
              {maxLossDollars.toFixed(0)} max loss
            </div>
            <div style={{ fontSize: 9, color: parseFloat(riskPct) > 5 ? AMBER : MUTED }}>
              {riskPct}% of {ACCT_DEFAULT.toLocaleString()} acct
            </div>
          </div>
        </div>
      </div>

      {/* Action row */}
      <div style={{
        padding: '10px 16px',
        borderTop: `1px solid ${BG3}`,
        display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
      }}>
        <button onClick={onFollow} style={BTN_TEAL}>Follow (Paper)</button>
        <button onClick={onTake}   style={BTN_GREEN}>Take Position (Live)</button>
        <input
          type="text"
          value={followUpText}
          onChange={e => setFollowUpText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') handleFollowUp(); }}
          placeholder="Ask a follow-up about this trade…"
          disabled={followUpLoading}
          style={{
            flex: 1, padding: '6px 10px', borderRadius: 4,
            background: BG2, border: `1px solid ${BORD}`,
            color: TEXT, fontSize: 11, fontFamily: 'monospace',
            outline: 'none', minWidth: 160,
          }}
        />
        <button onClick={onDiscard} style={BTN_NEUTRAL}>Discard ✕</button>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
/**
 * @param {Object} trade                — the full trade object from analysis API
 * @param {Object} config               — strategy config from STRATEGY_CONFIGS (has scoreMetrics)
 * @param {string} symbol               — ticker symbol
 * @param {number} underlyingPrice      — current price of the underlying
 * @param {Object} smaData              — { smaShort, smaMid, smaLong, price, alignment }
 * @param {Array}  scorecardStrategies    — [{ key, label, score, signal_summary }] from scorecard
 * @param {Array}  scorecardNotApplicable — strategies not applicable to this trade type (grayed)
 * @param {boolean} scorecardLoading      — true while scorecard is being fetched
 * @param {string|null} scorecardError    — error message if scorecard load failed, else null
 * @param {Function} onLoadScorecard      — callback to trigger scorecard load
 * @param {Function} onFollowTrade        — callback(trade) to open Follow (Paper) modal
 * @param {Function} onTakeTrade          — callback(trade) to open Take Position (Live) modal
 */
export default function TradeExpansionPanel({
  trade,
  config,
  symbol,
  underlyingPrice,
  smaData,
  scorecardStrategies,
  scorecardNotApplicable,
  scorecardLoading,
  scorecardError,
  onLoadScorecard,
  onFollowTrade,
  onTakeTrade,
}) {
  const [selectedStrategy, setSelectedStrategy] = useState(null);
  const [verdictVisible,   setVerdictVisible]   = useState(false);
  const [verdictLoading,   setVerdictLoading]   = useState(false);
  const [verdictData,      setVerdictData]      = useState(null);
  const [evalError,        setEvalError]        = useState(null);

  // V-6: Reset verdict and strategy when trade identity changes
  useEffect(() => {
    setVerdictVisible(false);
    setVerdictData(null);
    setSelectedStrategy(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trade?.symbol, trade?.long_strike, trade?.short_strike, trade?.expiration]);

  // Auto-load scorecard on mount if not yet loaded
  useEffect(() => {
    if (!scorecardStrategies?.length && !scorecardLoading) {
      onLoadScorecard?.();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-select highest-scoring strategy once scorecard arrives
  useEffect(() => {
    if (scorecardStrategies?.length > 0 && !selectedStrategy) {
      const best = scorecardStrategies.reduce((a, b) =>
        ((b.score ?? 0) > (a.score ?? 0) ? b : a)
      );
      setSelectedStrategy(best.key ?? best.strategy_key);
    }
  }, [scorecardStrategies, selectedStrategy]);

  const handleStrategySelect = (key) => {
    if (key === selectedStrategy) return;
    setSelectedStrategy(key);
    // Collapse verdict card when strategy changes (per spec)
    if (verdictVisible) {
      setVerdictVisible(false);
      setVerdictData(null);
    }
  };

  const handleEvaluate = async () => {
    if (!selectedStrategy) return;
    setVerdictLoading(true);
    setVerdictVisible(false);
    setEvalError(null);

    try {
      // Derive IV from scorecard best_trade or fall back to trade.iv or default
      const stratEntry = scorecardStrategies?.find(
        s => (s.key ?? s.strategy_key) === selectedStrategy
      );
      const iv = stratEntry?.best_trade?.iv ?? trade.iv ?? 0.25;

      // Build sma_alignment dict
      const smaAlignment = smaData ? {
        sma_8:     smaData.smaShort,
        sma_21:    smaData.smaMid,
        sma_50:    smaData.smaLong,
        alignment: smaData.alignment ?? (
          (smaData.price > smaData.smaShort && smaData.smaShort > smaData.smaMid)
            ? 'bullish'
            : 'mixed'
        ),
      } : {};

      // scores dict — all strategies visible in column 3
      const scores = scorecardStrategies
        ? Object.fromEntries(
            scorecardStrategies.map(s => [s.key ?? s.strategy_key, s.score ?? 0])
          )
        : {};

      const result = await evaluateStructured({
        symbol,
        current_price: underlyingPrice,
        iv,
        sma_alignment:  smaAlignment,
        strategy_keys:  [selectedStrategy],
        scores,
        trade,
      });

      const card = result.evaluations?.[0];
      if (card) {
        setVerdictData({ ...card, evaluated_at: result.evaluated_at });
        setVerdictVisible(true);
      } else {
        setEvalError('No evaluation returned. Please try again.');
      }
    } catch (err) {
      setEvalError(err.message || 'Evaluation failed.');
    } finally {
      setVerdictLoading(false);
    }
  };

  const evalState = verdictLoading          ? 'loading'
    : (verdictVisible && verdictData)       ? 'reevaluate'
    : 'default';

  return (
    <div style={{ borderTop: '2px solid rgba(45,212,191,0.35)', background: BG }}>
      <style>{DOT_STYLE}</style>

      {/* 4-column grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr 1fr 1fr',
        borderBottom: `1px solid ${BG3}`,
      }}>
        <ScoreBreakdownCol trade={trade} config={config} />

        <div style={{ borderLeft: `1px solid ${BG3}` }}>
          <ActualCalcCol trade={trade} config={config} />
        </div>

        <div style={{ borderLeft: `1px solid ${BG3}` }}>
          {scorecardLoading ? (
            <div style={{ padding: 16, color: MUTED, fontSize: 11 }}>
              Loading strategy scores<AnimatedDots />
            </div>
          ) : scorecardStrategies?.length > 0 ? (
            <StrategyFitCol
              strategies={scorecardStrategies}
              notApplicable={scorecardNotApplicable}
              selectedKey={selectedStrategy}
              onSelect={handleStrategySelect}
              onEvaluate={handleEvaluate}
              evalState={evalState}
            />
          ) : (
            <div style={{ padding: 16 }}>
              <div style={{ fontSize: 9, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 10 }}>
                Strategy Fit
              </div>
              {scorecardError && (
                <div style={{ fontSize: 10, color: '#f87171', marginBottom: 8, lineHeight: 1.4 }}>
                  {scorecardError}
                </div>
              )}
              <button onClick={onLoadScorecard} style={BTN_NEUTRAL}>
                {scorecardError ? 'Retry' : 'Load Strategy Scores'}
              </button>
            </div>
          )}
        </div>

        <div style={{ borderLeft: `1px solid ${BG3}` }}>
          <StrategyExplainCol
            strategyKey={selectedStrategy}
            trade={trade}
            smaData={smaData}
          />
        </div>
      </div>

      {/* Eval error */}
      {evalError && (
        <div style={{
          padding: '8px 16px',
          display: 'flex', alignItems: 'center', gap: 8,
          fontSize: 11, color: RED,
          borderBottom: `1px solid ${BG3}`,
        }}>
          {evalError}
          <button onClick={() => setEvalError(null)} style={{ ...BTN_NEUTRAL, padding: '3px 8px', fontSize: 10 }}>
            Dismiss
          </button>
        </div>
      )}

      {/* Loading indicator */}
      {verdictLoading && (
        <div style={{
          padding: '10px 16px',
          display: 'flex', alignItems: 'center', gap: 10,
          borderBottom: `1px solid ${BG3}`,
        }}>
          <span style={{ fontSize: 11, color: MUTED }}>
            Evaluating<AnimatedDots />
          </span>
          <span style={{ fontSize: 9, color: DIM }}>
            {selectedStrategy} · {symbol}
          </span>
        </div>
      )}

      {/* Verdict card — slides in below the 4-column grid */}
      {verdictVisible && verdictData && (
        <VerdictCard
          verdictData={verdictData}
          trade={trade}
          symbol={symbol}
          strategyKey={selectedStrategy}
          onFollow={() => onFollowTrade(trade)}
          onTake={() => onTakeTrade(trade)}
          onDiscard={() => { setVerdictVisible(false); setVerdictData(null); }}
        />
      )}
    </div>
  );
}
