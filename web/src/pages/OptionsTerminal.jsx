/**
 * OptionsTerminal — Reusable 4-stage analysis shell.
 *
 * Receives a single prop: activeStrategy (string key from STRATEGY_CONFIGS).
 * Looks up the config and renders accordingly — no hardcoded strategy knowledge.
 *
 * Stage 0: Ticker nav, market data ribbon, signal banner, candlestick chart
 * Stage 1: Master grid — ranked trades, dynamic columns from config
 * Stage 2: Inline expansion — math matrix + payoff diagram
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  ComposedChart, Bar, Line, ReferenceLine, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, Cell,
} from 'recharts';
import { STRATEGY_CONFIGS } from '../strategy-configs/index';
import { apiPost, getQuote, followTrade, takeTrade, getStrategyScorecard, evaluateStructured } from '../api/client';
import { useApp } from '../context/AppContext';
import ConfigDrawer from '../components/ConfigDrawer';
import QuoteBar from '../components/QuoteBar';
import ScoreBar from '../components/ScoreBar';
import StrategyScorecard from '../components/StrategyScorecard';
import TradeEvaluationCard from '../components/TradeEvaluationCard';
import { C, mono, DEFAULT_PRESETS } from '../styles/tokens';

// ─── Constants ───────────────────────────────────────────────────────────────

const BG       = C.bg;
const SURFACE  = C.surface;
const BORDER   = C.border;
const TEXT     = C.text;
const DIM      = C.textDim;
const MUTED    = C.textMuted;
const GREEN    = C.candleGreen;  // #26a69a
const AMBER    = C.amber;        // #f59e0b
const RED      = C.red;          // #ef5350
const ACCENT   = C.accent;       // #4f8ef7
const CL_ACCENT = C.claudeAccent; // #f59e0b
const SMA8_COLOR  = C.smaCyan;   // #00bcd4
const SMA21_COLOR = C.smaOrange; // #ff9800
const SMA50_COLOR = C.smaRed;    // #e8837c

// ─── generateCandles — copied verbatim from VerticalsPage ────────────────────

function generateCandles(price, count = 120) {
  // Walk backwards from today (inclusive), skipping weekends.
  // unshift() builds array oldest-first so index 0 = leftmost, last = today.
  const dates = [];
  const cursor = new Date();
  cursor.setHours(0, 0, 0, 0);
  while (dates.length < count) {
    const dow = cursor.getDay();
    if (dow !== 0 && dow !== 6) {
      const mm = String(cursor.getMonth() + 1).padStart(2, '0');
      const dd = String(cursor.getDate()).padStart(2, '0');
      dates.unshift(`${mm}/${dd}`);
    }
    cursor.setDate(cursor.getDate() - 1);
  }

  const candles = [];
  let p = price * 0.95;
  for (let i = 0; i < count; i++) {
    const change = (Math.random() - 0.48) * price * 0.012;
    const open = p; const close = p + change;
    const high = Math.max(open, close) + Math.random() * price * 0.005;
    const low = Math.min(open, close) - Math.random() * price * 0.005;
    candles.push({ open, high, low, close, day: dates[i] }); p = close;
  }
  const scale = price / candles[candles.length - 1].close;
  return candles.map(c => ({
    open: c.open * scale, high: c.high * scale,
    low: c.low * scale, close: c.close * scale, day: c.day,
  }));
}

// ─── CandleShape — custom SVG candle for Recharts Bar ────────────────────────

function CandleShape({ x, y, width, height, payload }) {
  if (!payload || !height || height <= 0) return null;

  // y = pixel position of `payload.high` (top of bar, domain max for this bar)
  // height = pixels from y to the bar's baseValue (domain min)
  // We use this to compute a price → pixel scale.
  const domainMin = payload.chartLow;
  if (payload.high <= domainMin) return null;

  const pixPerUnit = height / (payload.high - domainMin);
  const yFor = (price) => y + (payload.high - price) * pixPerUnit;

  const isGreen = payload.close >= payload.open;
  const color = isGreen ? GREEN : RED;
  const cx = x + width / 2;

  const yHigh  = y; // = yFor(payload.high)
  const yLow   = yFor(payload.low);
  const yBody1 = yFor(Math.max(payload.open, payload.close));
  const yBody2 = yFor(Math.min(payload.open, payload.close));

  return (
    <g>
      {/* Wick */}
      <rect x={cx - 0.5} y={yHigh} width={1} height={Math.max(0, yLow - yHigh)} fill={color} />
      {/* Body */}
      <rect
        x={cx - 3} y={yBody1} width={6}
        height={Math.max(1, yBody2 - yBody1)}
        fill={color + '50'} stroke={color} strokeWidth={1}
      />
    </g>
  );
}

// ─── Custom tooltip for the candlestick chart ─────────────────────────────────

function CandleTooltip({ active, payload }) {
  if (!active || !payload?.[0]) return null;
  const d = payload[0].payload;
  return (
    <div style={{
      background: SURFACE, border: `1px solid ${BORDER}`, borderRadius: 6,
      padding: '6px 10px', fontSize: 11, fontFamily: mono, color: TEXT,
    }}>
      <div>O: {d.open?.toFixed(2)}</div>
      <div>H: {d.high?.toFixed(2)}</div>
      <div>L: {d.low?.toFixed(2)}</div>
      <div>C: {d.close?.toFixed(2)}</div>
    </div>
  );
}

// ─── Health Pips ─────────────────────────────────────────────────────────────

function HealthPips({ pips }) {
  return (
    <div style={{ display: 'flex', gap: 3, justifyContent: 'center', alignItems: 'center' }}>
      {pips.map((pip, i) => (
        <div key={i} style={{
          width: 8, height: 8, borderRadius: '50%', backgroundColor: pip.color,
        }} />
      ))}
    </div>
  );
}

// ─── Payoff AreaChart ─────────────────────────────────────────────────────────

function PayoffChart({ data, trade }) {
  const buyStrike  = trade.long_strike;
  const sellStrike = trade.short_strike;
  const midPrice   = trade.breakeven;

  return (
    <ResponsiveContainer width="100%" height={160}>
      <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="payoffGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor={GREEN} stopOpacity={0.25} />
            <stop offset="45%"  stopColor={GREEN} stopOpacity={0} />
            <stop offset="55%"  stopColor={RED}   stopOpacity={0} />
            <stop offset="100%" stopColor={RED}   stopOpacity={0.2} />
          </linearGradient>
        </defs>
        <XAxis dataKey="price" hide />
        <YAxis orientation="right" width={50} tick={{ fill: MUTED, fontSize: 9 }} tickFormatter={(v) => v.toFixed(0)} />
        <ReferenceLine y={0} stroke={BORDER} strokeDasharray="3 3" />
        {midPrice   && <ReferenceLine x={midPrice}   stroke={ACCENT + '60'} strokeDasharray="3 3" />}
        {buyStrike  && <ReferenceLine x={buyStrike}  stroke={MUTED + '80'} strokeDasharray="2 4" />}
        {sellStrike && <ReferenceLine x={sellStrike} stroke={MUTED + '80'} strokeDasharray="2 4" />}
        <Area
          type="monotone" dataKey="pnl" isAnimationActive={false}
          fill="url(#payoffGrad)" stroke={ACCENT} strokeWidth={1.5}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ─── Math Matrix (inline score breakdown) ────────────────────────────────────

function MathMatrix({ trade, config }) {
  const { scoreMetrics } = config;
  const total = scoreMetrics.reduce((sum, m) => {
    const val = trade?.[m.field];
    return sum + (val != null ? val * (m.weightPct / 100) : 0);
  }, 0);

  return (
    <div>
      {scoreMetrics.map((m, idx) => {
        const score = trade?.[m.field];
        const contribution = score != null ? score * (m.weightPct / 100) : null;

        return (
          <div key={m.key} style={{
            marginBottom: 10,
            paddingBottom: idx < scoreMetrics.length - 1 ? 10 : 0,
            borderBottom: idx < scoreMetrics.length - 1 ? `1px solid ${C.borderSubtle}` : 'none',
          }}>
            {/* Header row */}
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: m.color }} />
                <span style={{ color: TEXT, fontWeight: 600, fontSize: 12 }}>{m.label}</span>
                <span style={{
                  padding: '1px 6px', borderRadius: 4, fontSize: 10, fontWeight: 600,
                  backgroundColor: m.color + '20', color: m.color,
                }}>{m.weightPct}%</span>
              </div>
              <span style={{ color: m.color, fontWeight: 700, fontFamily: mono, fontSize: 12 }}>
                {contribution != null ? `+${contribution.toFixed(4)}` : '—'}
              </span>
            </div>

            {/* Formula */}
            <div style={{ marginLeft: 13, fontSize: 11, color: MUTED, fontFamily: mono, marginBottom: 3 }}>
              {m.formula}
            </div>

            {/* Score bar */}
            <div style={{ marginLeft: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{
                flex: 1, height: 4, backgroundColor: BORDER, borderRadius: 2, overflow: 'hidden',
              }}>
                <div style={{
                  height: '100%', width: `${(score || 0) * 100}%`,
                  backgroundColor: m.color, borderRadius: 2, transition: 'width 0.3s ease',
                }} />
              </div>
              <span style={{ color: DIM, fontSize: 10, fontFamily: mono, minWidth: 40, textAlign: 'right' }}>
                {score != null ? score.toFixed(4) : '—'}
              </span>
            </div>
          </div>
        );
      })}

      {/* Composite total */}
      <div style={{
        marginTop: 8, padding: '8px 12px', backgroundColor: C.surfaceAlt,
        borderRadius: 6, border: `1px solid ${BORDER}`,
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span style={{ color: TEXT, fontWeight: 700, fontSize: 13 }}>Composite Score</span>
        <span style={{
          color: total > 0.65 ? GREEN : total > 0.45 ? AMBER : RED,
          fontWeight: 800, fontSize: 18, fontFamily: mono,
        }}>
          {total.toFixed(4)}
        </span>
      </div>
    </div>
  );
}

// ─── Chart date helpers ───────────────────────────────────────────────────────

function tradingDaysAgo(n) {
  // Returns YYYY-MM-DD string for the date n trading days before today
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  let count = 0;
  while (count < n) {
    d.setDate(d.getDate() - 1);
    const dow = d.getDay();
    if (dow !== 0 && dow !== 6) count++;
  }
  return d.toISOString().slice(0, 10);
}

function countTradingDays(startDateStr) {
  // Count weekdays from startDateStr up to and including today
  const today = new Date();
  today.setHours(23, 59, 59, 0);
  const d = new Date(startDateStr + 'T12:00:00');
  let count = 0;
  while (d <= today) {
    const dow = d.getDay();
    if (dow !== 0 && dow !== 6) count++;
    d.setDate(d.getDate() + 1);
  }
  return Math.max(count, 10);
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function OptionsTerminal({ activeStrategy }) {
  const config = STRATEGY_CONFIGS[activeStrategy] || STRATEGY_CONFIGS.verticals;
  const { activeSymbol } = useApp();

  // ── State ──────────────────────────────────────────────────────────────────
  const [symbol,       setSymbol]       = useState(activeSymbol || 'QQQ');
  const [inputSymbol,  setInputSymbol]  = useState(activeSymbol || 'QQQ');
  const [trades,       setTrades]       = useState([]);
  const [underlyingPrice, setUnderlyingPrice] = useState(0);
  const [quoteData,    setQuoteData]    = useState(null);
  const [candles,      setCandles]      = useState([]);
  const [loading,        setLoading]        = useState(false);
  const [error,          setError]          = useState(null);
  const [lastAnalyzed,   setLastAnalyzed]   = useState(null);
  const [chartStartDate, setChartStartDate] = useState(() => tradingDaysAgo(90));
  const chartStartDateRef = useRef(chartStartDate);
  const [selectedId,   setSelectedId]   = useState(null);
  const [configOpen,   setConfigOpen]   = useState(false);

  // ── Strategy scorecard state (Stage 2 expansion — B3) ─────────────────────
  const [scorecardData,         setScorecardData]         = useState(null);
  const [scorecardLoading,      setScorecardLoading]      = useState(false);
  const [scorecardSelectedKeys, setScorecardSelectedKeys] = useState([]);

  // ── Per-trade evaluation results (inline in Stage 2) ──────────────────────
  const [terminalEvalLoading,   setTerminalEvalLoading]   = useState(false);
  const [terminalEvalError,     setTerminalEvalError]     = useState(null);
  const [terminalEvaluations,   setTerminalEvaluations]   = useState([]);

  // Follow/Take position modal — { trade, type: 'follow'|'take' }
  const [positionModal, setPositionModal] = useState(null);
  const [positionSubmitting, setPositionSubmitting] = useState(false);
  const [positionToast, setPositionToast] = useState(null); // { message, error }

  // ── Analysis config (weights, DTE, spread types, etc.) ────────────────────
  const [presets,        setPresets]        = useState(DEFAULT_PRESETS);
  const [activePresetId, setActivePresetId] = useState('balanced');
  const [analysisConfig, setAnalysisConfig] = useState(() => {
    const preset = DEFAULT_PRESETS.find(p => p.id === 'balanced') || DEFAULT_PRESETS[0];
    return {
      weights: { ...preset.weights },
      dte:     { min: preset.dte?.min || 14, max: preset.dte?.max || 60 },
      strikes: { range_pct: preset.strikes?.range_pct || 10, min_open_interest: 50, min_volume: 5 },
      spreads: { min_width: 1, max_width: 10 },
      risk:    { max_risk_per_trade: 500, profit_target_pct: 75, stop_loss_pct: 50 },
      spreadTypes: { bull_call: true, bear_put: true, bull_put: false, bear_call: false },
      greeks:  { min_short_delta: 0.15, max_short_delta: 0.45, min_net_delta: 0, max_net_theta: 0 },
      smaPeriods: { short: 8, mid: 21, long: 50 },
      systemVars: preset.systemVars
        ? { ...preset.systemVars }
        : { exit_warning_pct: 67, exit_scale_out_pct: 160, exit_underlying_stop_pct: 1.5, exit_time_stop_days: 10 },
    };
  });
  const analysisConfigRef = useRef(analysisConfig);
  analysisConfigRef.current = analysisConfig;

  // Track if we've initialized (avoids duplicate runs on mount)
  const initialized = useRef(false);

  // ── SMA computation — uses periods from analysisConfig ───────────────────
  const smaPeriods = analysisConfig.smaPeriods || { short: 8, mid: 21, long: 50 };

  const getSmaData = useCallback(() => {
    if (!candles.length) return { price: underlyingPrice, smaShort: 0, smaMid: 0, smaLong: 0 };
    const sma = (period) => {
      const slice = candles.slice(-period);
      return slice.reduce((s, c) => s + c.close, 0) / slice.length;
    };
    return {
      price: candles[candles.length - 1]?.close || underlyingPrice,
      smaShort: sma(smaPeriods.short),
      smaMid:   sma(smaPeriods.mid),
      smaLong:  sma(smaPeriods.long),
    };
  }, [candles, underlyingPrice]);

  const smaData = getSmaData();

  // ── Chart data with per-candle SMA values ─────────────────────────────────
  const chartData = useMemo(() => {
    return candles.map((c, i) => {
      const sma = (period) => {
        if (i < period - 1) return null;
        const slice = candles.slice(i - period + 1, i + 1);
        return slice.reduce((s, c) => s + c.close, 0) / slice.length;
      };
      return { ...c, sma8: sma(smaPeriods.short), sma21: sma(smaPeriods.mid), sma50: sma(smaPeriods.long) };
    });
  }, [candles]);

  // ── Chart Y-domain bounds — needed by CandleShape ─────────────────────────
  const chartBounds = useMemo(() => {
    if (!chartData.length) return { low: 0, high: 100 };
    const lows  = chartData.map(c => c.low);
    const highs = chartData.map(c => c.high);
    const low   = Math.min(...lows);
    const high  = Math.max(...highs);
    const pad   = (high - low) * 0.03;
    return { low: low - pad, high: high + pad };
  }, [chartData]);

  // Add chartLow to each candle so CandleShape can access it via payload
  const chartDataWithMeta = useMemo(() => {
    return chartData.map(c => ({ ...c, chartLow: chartBounds.low }));
  }, [chartData, chartBounds]);

  // ── Signal banner ─────────────────────────────────────────────────────────
  const signal = useMemo(() => {
    const { price, smaShort, smaMid, smaLong } = smaData;
    if (!smaShort || !smaMid || !smaLong) {
      return { text: '◆ Mixed — No directional confirmation', bg: BORDER, color: DIM };
    }
    if (price > smaShort && smaShort > smaMid && smaMid > smaLong) {
      return { text: '◆ Bullish Alignment — Price above all 3 SMAs', bg: GREEN, color: '#000' };
    }
    if (smaShort < smaMid) {
      return { text: '◆ Bearish Signal — Short-term weakness', bg: AMBER, color: '#000' };
    }
    return { text: '◆ Mixed — No directional confirmation', bg: BORDER, color: DIM };
  }, [smaData]);

  // ── Market ribbon helpers ─────────────────────────────────────────────────
  function fmtChange(v) {
    if (v == null) return '—';
    const s = v > 0 ? `+${v.toFixed(2)}` : v.toFixed(2);
    return s;
  }
  function fmtChangePct(v) {
    if (v == null) return '—';
    return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
  }
  function fmtVol(v) {
    if (!v) return '—';
    if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
    if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
    return v.toString();
  }
  function fmtRange(lo, hi) {
    if (!lo && !hi) return '—';
    const f = (n) => n?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '—';
    return `${f(lo)} – ${f(hi)}`;
  }
  function fmtRelVol(ratio) {
    if (ratio == null) return '—';
    return `${ratio.toFixed(1)}x`;
  }
  function fmtCriticalDate(dateStr) {
    if (!dateStr) return null;
    const d = new Date(dateStr);
    if (isNaN(d)) return null;
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const days = Math.round((d - today) / 86400000);
    const label = d.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: '2-digit' });
    return { label, days };
  }
  const changeColor = (v) => v == null ? DIM : v > 0 ? GREEN : v < 0 ? RED : DIM;
  const criticalDateColor = (days) => days == null ? DIM : days <= 14 ? RED : days <= 30 ? AMBER : GREEN;

  // ── runAnalysis ───────────────────────────────────────────────────────────
  const runAnalysis = useCallback(async (sym) => {
    const targetSym = sym || symbol;
    setLoading(true);
    setError(null);

    try {
      const [analysisResult, quote] = await Promise.all([
        apiPost(config.apiEndpoint, config.buildApiParams(targetSym, analysisConfigRef.current)),
        getQuote(targetSym).catch(() => null),
      ]);

      const tradeList = analysisResult[config.tradesKey] || [];
      setTrades(tradeList);
      setUnderlyingPrice(analysisResult.underlying_price || 0);
      setQuoteData(quote);
      setLastAnalyzed(new Date());

      if (analysisResult.underlying_price) {
        const count = countTradingDays(chartStartDateRef.current);
        setCandles(generateCandles(analysisResult.underlying_price, count));
      }
    } catch (err) {
      setError(err.message || 'Analysis failed');
      setTrades([]);
    } finally {
      setLoading(false);
    }
  }, [config, symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Load strategy scorecard for the currently expanded trade's symbol ─────
  const loadScorecardForTrade = useCallback(async () => {
    if (!symbol) return;
    setScorecardLoading(true);
    try {
      const data = await getStrategyScorecard(symbol);
      setScorecardData(data);
    } catch (err) {
      setScorecardData({ error: err.message || 'Failed to load strategy scores' });
    } finally {
      setScorecardLoading(false);
    }
  }, [symbol]);

  // ── Follow / Take position ────────────────────────────────────────────────
  const handlePositionConfirm = useCallback(async () => {
    if (!positionModal) return;
    const { trade, type } = positionModal;
    setPositionSubmitting(true);
    try {
      const isSpread = !!(trade.spread_type || trade.long_strike);
      const tradeStructure = isSpread
        ? {
            spread_type:  trade.spread_type,
            long_strike:  trade.long_strike,
            short_strike: trade.short_strike,
            expiration:   trade.expiration,
            dte:          trade.dte,
          }
        : {
            option_type: trade.option_type ?? 'call',
            strike:      trade.strike ?? trade.long_strike,
            expiration:  trade.expiration,
            dte:         trade.dte,
          };

      const payload = {
        symbol:                  symbol,
        strategy_key:            activeStrategy,
        trade_structure:         tradeStructure,
        entry_price:             trade.net_debit ?? trade.premium_dollars ?? 0,
        entry_greeks:            {
          delta: trade.delta ?? null,
          theta: trade.theta_per_day ?? null,
          iv:    trade.iv ?? null,
        },
        entry_iv_rank:           trade.iv ?? 0,
        entry_sma_alignment:     smaData
          ? { sma_8: smaData.smaShort, sma_21: smaData.smaMid, sma_50: smaData.smaLong }
          : {},
        entry_underlying_price:  underlyingPrice,
        claude_score:            null,
      };

      const fn = type === 'follow' ? followTrade : takeTrade;
      await fn(payload);

      setPositionToast({
        message: `${type === 'follow' ? 'Paper follow' : 'Live position'} created for ${symbol}`,
        error: false,
      });
      setTimeout(() => setPositionToast(null), 4000);
    } catch (err) {
      setPositionToast({ message: err.message || 'Failed to create position', error: true });
      setTimeout(() => setPositionToast(null), 5000);
    } finally {
      setPositionSubmitting(false);
      setPositionModal(null);
    }
  }, [positionModal, symbol, activeStrategy, smaData, underlyingPrice]);

  // ── Config apply ──────────────────────────────────────────────────────────
  const handleConfigApply = useCallback((newConfig) => {
    setAnalysisConfig(newConfig);
    setConfigOpen(false);
    analysisConfigRef.current = newConfig;
    runAnalysis(symbol);
  }, [runAnalysis, symbol]);

  // ── When activeStrategy changes: reset + re-analyze ──────────────────────
  useEffect(() => {
    setTrades([]);
    setSelectedId(null);
    setConfigOpen(false);
    setError(null);
    if (initialized.current) {
      runAnalysis(symbol);
    }
  }, [activeStrategy]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Reset scorecard when symbol changes (new symbol = fresh scores needed) ─
  useEffect(() => {
    setScorecardData(null);
    setScorecardSelectedKeys([]);
  }, [symbol]);

  // ── Reset scorecard selection and eval when trade row changes ─────────────
  useEffect(() => {
    setScorecardSelectedKeys([]);
    setTerminalEvalLoading(false);
    setTerminalEvalError(null);
    setTerminalEvaluations([]);
  }, [selectedId]);

  // ── Regenerate candles when chart start date changes ──────────────────────
  useEffect(() => {
    chartStartDateRef.current = chartStartDate;
    if (underlyingPrice > 0) {
      const count = countTradingDays(chartStartDate);
      setCandles(generateCandles(underlyingPrice, count));
    }
  }, [chartStartDate]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Initial load ──────────────────────────────────────────────────────────
  useEffect(() => {
    initialized.current = true;
    runAnalysis(symbol);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Watchlist selection: sync activeSymbol from context ───────────────────
  useEffect(() => {
    if (!activeSymbol || !initialized.current) return;
    setSymbol(activeSymbol);
    setInputSymbol(activeSymbol);
    setSelectedId(null);
    setConfigOpen(false);
    runAnalysis(activeSymbol);
  }, [activeSymbol]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Symbol submit ─────────────────────────────────────────────────────────
  const handleSubmit = (e) => {
    e.preventDefault();
    const sym = inputSymbol.trim().toUpperCase();
    if (!sym) return;
    setSymbol(sym);
    setSelectedId(null);
    setConfigOpen(false);
    runAnalysis(sym);
  };

  // ── Row click: toggle expansion ───────────────────────────────────────────
  const handleRowClick = (tradeId) => {
    setSelectedId(prev => prev === tradeId ? null : tradeId);
    setConfigOpen(false);
  };

  // ── Trade ID helper ───────────────────────────────────────────────────────
  const getTradeId = (trade, idx) => {
    return trade.long_strike != null
      ? `${trade.long_strike}-${trade.short_strike}-${trade.expiration}-${trade.spread_type}`
      : `${trade.strike}-${trade.expiration}-${trade.option_type}-${idx}`;
  };

  // ── Payoff data for selected trade ────────────────────────────────────────
  const selectedTrade = useMemo(() => {
    if (!selectedId || !trades.length) return null;
    return trades.find((t, i) => getTradeId(t, i) === selectedId) || null;
  }, [selectedId, trades]);

  const payoffData = useMemo(() => {
    if (!selectedTrade || config.payoffType !== 'spread' || !config.payoffFn) return [];
    try { return config.payoffFn(selectedTrade, underlyingPrice); }
    catch { return []; }
  }, [selectedTrade, config, underlyingPrice]);

  // ── Scorecard scores filtered by trade_structure ──────────────────────────
  // Verticals: all 4 strategies. Puts & Calls (long-calls): only long_option strategies.
  const filteredScorecardScores = useMemo(() => {
    if (!scorecardData?.strategies) return [];
    return scorecardData.strategies.filter(item => {
      const key = item.key ?? item.strategy_key;
      const cfg = STRATEGY_CONFIGS[key];
      return activeStrategy === 'verticals' || cfg?.trade_structure === 'long_option';
    });
  }, [scorecardData, activeStrategy]);

  const notApplicableScores = useMemo(() => {
    if (!scorecardData?.strategies || activeStrategy === 'verticals') return [];
    const applicableKeys = new Set(filteredScorecardScores.map(s => s.key ?? s.strategy_key));
    return scorecardData.strategies.filter(item => {
      const key = item.key ?? item.strategy_key;
      return !applicableKeys.has(key);
    });
  }, [scorecardData, filteredScorecardScores, activeStrategy]);

  // ── Evaluate selected strategies for the expanded trade ───────────────────
  const handleTerminalEvaluate = useCallback(async (keys) => {
    if (!keys.length || !symbol || !selectedTrade) return;
    setTerminalEvalLoading(true);
    setTerminalEvalError(null);
    setTerminalEvaluations([]);

    const ivSource = keys
      .map(k => filteredScorecardScores.find(s => (s.strategy_key ?? s.key) === k))
      .find(s => s?.best_trade?.iv != null);
    const iv = ivSource?.best_trade?.iv ?? selectedTrade.iv ?? 0.25;

    try {
      const data = await evaluateStructured({
        symbol,
        current_price: underlyingPrice,
        iv,
        sma_alignment: smaData
          ? { sma_8: smaData.smaShort, sma_21: smaData.smaMid, sma_50: smaData.smaLong }
          : {},
        strategy_keys: keys,
        trade: selectedTrade,
      });
      setTerminalEvaluations([...(data.evaluations ?? [])].sort((a, b) => b.score - a.score));
    } catch (err) {
      setTerminalEvalError(err.message || 'Evaluation failed');
    } finally {
      setTerminalEvalLoading(false);
    }
  }, [symbol, underlyingPrice, smaData, selectedTrade, filteredScorecardScores]);

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0, minHeight: 0 }}>

      {/* ── STAGE 0: Header + chart ────────────────────────────────────────── */}
      <div style={{ backgroundColor: BG, borderBottom: `1px solid ${BORDER}`, padding: '10px 16px 0' }}>

        {/* Nav bar */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <input
            value={inputSymbol}
            onChange={e => setInputSymbol(e.target.value.toUpperCase())}
            placeholder="Enter symbol…"
            style={{
              flex: 1, maxWidth: 220, padding: '6px 10px', borderRadius: 6,
              border: `1px solid ${BORDER}`, backgroundColor: SURFACE,
              color: TEXT, fontSize: 13, fontFamily: mono, outline: 'none',
            }}
          />

          <button type="submit" style={{
            padding: '6px 18px', borderRadius: 6, border: 'none',
            backgroundColor: ACCENT, color: '#fff', fontFamily: mono,
            fontSize: 13, fontWeight: 700, cursor: 'pointer',
          }}>
            Analyze
          </button>

          {loading && (
            <div style={{
              width: 16, height: 16, border: `2px solid ${BORDER}`,
              borderTopColor: ACCENT, borderRadius: '50%',
              animation: 'spin 0.7s linear infinite',
            }} />
          )}
        </form>

        {/* Market ribbon — unified QuoteBar */}
        {(() => {
          const smaSignalStr = signal.text.includes('Bullish') ? 'BULLISH'
            : signal.text.includes('Bearish') ? 'BEARISH'
            : 'MIXED';
          return (
            <QuoteBar
              symbol={symbol}
              quote={quoteData}
              smaSignal={candles.length > 0 ? smaSignalStr : undefined}
              lastAnalyzed={lastAnalyzed}
            />
          );
        })()}

        {/* Candlestick chart */}
        {candles.length > 0 && (
          <div style={{ position: 'relative' }}>
            {/* SMA legend — far right, outside Y-axis */}
            <div style={{
              position: 'absolute', top: 0, right: 0, bottom: 0, zIndex: 10,
              width: 130,
              display: 'flex', flexDirection: 'column', justifyContent: 'center',
              padding: '8px 10px',
              borderLeft: `1px solid ${BORDER}`,
              background: `linear-gradient(135deg, ${C.surfaceAlt} 0%, ${C.card} 100%)`,
              borderRadius: '0 4px 4px 0',
            }}>
              {/* SMA section */}
              <div style={{
                fontSize: 8, fontWeight: 700, color: MUTED,
                letterSpacing: '0.07em', textTransform: 'uppercase',
                marginBottom: 7, textAlign: 'center',
                borderBottom: `1px solid ${BORDER}`, paddingBottom: 5,
              }}>
                SMA Configuration
              </div>
              {[
                { period: smaPeriods.short, color: SMA8_COLOR  },
                { period: smaPeriods.mid,   color: SMA21_COLOR },
                { period: smaPeriods.long,  color: SMA50_COLOR },
              ].map(({ period, color }) => (
                <div key={period} style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
                  <div style={{ width: 12, height: 12, backgroundColor: color, borderRadius: 2, flexShrink: 0 }} />
                  <span style={{ fontSize: 11, fontFamily: mono, color, fontWeight: 700 }}>{period}-day</span>
                </div>
              ))}

              {/* Chart start date section */}
              <div style={{
                fontSize: 8, fontWeight: 700, color: MUTED,
                letterSpacing: '0.07em', textTransform: 'uppercase',
                marginTop: 10, marginBottom: 6, textAlign: 'center',
                borderTop: `1px solid ${BORDER}`, paddingTop: 8,
              }}>
                Chart Start Date
              </div>
              <input
                type="date"
                value={chartStartDate}
                max={new Date().toISOString().slice(0, 10)}
                onChange={e => e.target.value && setChartStartDate(e.target.value)}
                style={{
                  width: '100%', boxSizing: 'border-box',
                  backgroundColor: C.bg, border: `1px solid ${BORDER}`,
                  borderRadius: 4, color: DIM, fontSize: 10,
                  padding: '3px 4px', fontFamily: mono,
                  outline: 'none', cursor: 'pointer',
                  colorScheme: 'dark',
                }}
              />
            </div>

          <ResponsiveContainer width="100%" height={215}>
            <ComposedChart data={chartDataWithMeta} margin={{ top: 8, right: 138, bottom: 4, left: 0 }}>
              <CartesianGrid vertical={false} stroke={C.borderSubtle} />
              <XAxis
                dataKey="day"
                interval={13}
                tick={{ fill: DIM, fontSize: 10, fontFamily: 'monospace' }}
                axisLine={{ stroke: DIM }}
                tickLine={{ stroke: DIM }}
                height={22}
                minTickGap={40}
              />
              <YAxis
                orientation="right" width={55}
                domain={[chartBounds.low, chartBounds.high]}
                tick={{ fill: DIM, fontSize: 10 }}
                axisLine={{ stroke: DIM }}
                tickLine={{ stroke: DIM }}
                tickFormatter={v => v.toFixed(0)}
              />
              <Tooltip content={<CandleTooltip />} />

              {/* Candlestick bars — baseValue keeps the bar anchored to chartBounds.low */}
              <Bar
                dataKey="high"
                baseValue={chartBounds.low}
                shape={<CandleShape />}
                isAnimationActive={false}
                fill="transparent"
              />

              {/* SMA lines */}
              <Line type="monotone" dataKey="sma8"  stroke={SMA8_COLOR}  strokeWidth={1.5} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="sma21" stroke={SMA21_COLOR} strokeWidth={1.5} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="sma50" stroke={SMA50_COLOR} strokeWidth={1.5} dot={false} isAnimationActive={false} />

              {/* Current price reference */}
              <ReferenceLine y={underlyingPrice} stroke={ACCENT + '90'} strokeDasharray="4 4" />
            </ComposedChart>
          </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* ── STAGE 1: Master grid ───────────────────────────────────────────── */}
      <div style={{ flex: 1, overflowX: 'auto', padding: '0 0 80px' }}>

        {/* Loading */}
        {loading && (
          <div style={{ padding: '40px 16px', textAlign: 'center', color: DIM }}>
            <div style={{ fontSize: 13 }}>Analyzing {symbol} options chain…</div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{
            margin: 16, padding: '10px 14px', backgroundColor: C.redBg,
            border: `1px solid ${RED}40`, borderRadius: 6,
            display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <span style={{ color: RED }}>⚠ {error}</span>
            <button
              onClick={() => runAnalysis(symbol)}
              style={{ background: 'none', border: `1px solid ${RED}60`, color: RED, padding: '3px 10px', borderRadius: 4, cursor: 'pointer', fontSize: 12 }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Grid header */}
        {!loading && !error && trades.length > 0 && (
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '8px 16px', borderBottom: `1px solid ${BORDER}`,
          }}>
            <span style={{ fontFamily: mono, fontSize: 13, fontWeight: 700, color: TEXT }}>
              {symbol} <span style={{ color: DIM }}>{config.label}</span>
              <span style={{ color: MUTED, marginLeft: 8 }}>· {trades.length} results</span>
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 11, color: MUTED }}>
                Click a row to see scoring breakdown →
              </span>
              <button
                onClick={() => setConfigOpen(true)}
                style={{
                  padding: '4px 10px', borderRadius: 5, fontSize: 11,
                  border: `1px solid ${BORDER}`, background: 'none',
                  color: DIM, cursor: 'pointer',
                }}
              >
                ⚙ Config
              </button>
            </div>
          </div>
        )}

        {/* Table */}
        {!loading && !error && trades.length > 0 && (
          <table style={{
            width: '100%', borderCollapse: 'collapse',
            fontFamily: mono, fontSize: 12,
          }}>
            <thead>
              <tr style={{ backgroundColor: C.surfaceAlt, borderBottom: `1px solid ${BORDER}` }}>
                {config.columns.map(col => (
                  <th key={col.key} style={{
                    padding: '6px 8px', textAlign: col.align,
                    color: MUTED, fontWeight: 600, fontSize: 10,
                    textTransform: 'uppercase', letterSpacing: '0.06em',
                    whiteSpace: 'nowrap', width: col.width,
                  }}>
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trades.map((trade, idx) => {
                const tradeId   = getTradeId(trade, idx);
                const isSelected = tradeId === selectedId;
                const badge      = config.getBadge(trade);
                const pips       = config.getHealthPips(trade, analysisConfig.systemVars);

                return [
                  // Trade row
                  <tr
                    key={`row-${tradeId}`}
                    onClick={() => handleRowClick(tradeId)}
                    style={{
                      cursor: 'pointer',
                      borderLeft: `3px solid ${isSelected ? ACCENT : 'transparent'}`,
                      backgroundColor: isSelected ? ACCENT + '08' : 'transparent',
                      borderBottom: `1px solid ${BORDER}`,
                      transition: 'background 0.1s',
                    }}
                    onMouseEnter={e => { if (!isSelected) e.currentTarget.style.backgroundColor = SURFACE; }}
                    onMouseLeave={e => { if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent'; }}
                  >
                    {config.columns.map((col, ci) => {
                      const val = trade[col.key];

                      // Special: row index
                      if (col.key === '#') {
                        return (
                          <td key={ci} style={{ padding: '6px 8px', textAlign: 'center', color: MUTED }}>
                            {idx + 1}
                          </td>
                        );
                      }

                      // Special: type badge
                      if (col.key === 'badge') {
                        return (
                          <td key={ci} style={{ padding: '6px 8px', textAlign: 'center' }}>
                            <span style={{
                              display: 'inline-block', padding: '2px 7px', borderRadius: 4,
                              fontSize: 10, fontWeight: 700, letterSpacing: '0.04em',
                              color: badge.color, backgroundColor: badge.bg,
                            }}>
                              {badge.label}
                            </span>
                          </td>
                        );
                      }

                      // Special: score bar
                      if (col.key === 'composite_score') {
                        return (
                          <td key={ci} style={{ padding: '4px 8px', textAlign: 'center' }}>
                            <ScoreBar score={trade.composite_score} />
                          </td>
                        );
                      }

                      // Special: individual health pips
                      if (col.key === 'pip_rr' || col.key === 'pip_prob' || col.key === 'pip_score') {
                        const pip = pips[col.key === 'pip_rr' ? 0 : col.key === 'pip_prob' ? 1 : 2];
                        return (
                          <td key={ci} style={{ padding: '6px 8px', textAlign: 'center' }} title={col.title}>
                            <div style={{ width: 10, height: 10, borderRadius: '50%', backgroundColor: pip.color, margin: '0 auto' }} />
                          </td>
                        );
                      }

                      // Standard formatted cell
                      return (
                        <td key={ci} style={{
                          padding: '6px 8px',
                          textAlign: col.align,
                          color: TEXT,
                        }}>
                          {col.format ? col.format(val, trade, idx) : (val ?? '—')}
                        </td>
                      );
                    })}
                  </tr>,

                  // Stage 2: Inline expansion
                  isSelected && (
                    <tr key={`expand-${tradeId}`}>
                      <td colSpan={config.columns.length} style={{
                        backgroundColor: BG,
                        borderTop: `2px solid ${ACCENT}`,
                        borderBottom: `1px solid ${BORDER}`,
                        padding: 16,
                      }}>
                        {/* 2-column grid: Scoring Breakdown (left) + Strategy Fit (right) */}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>

                          {/* Left: Scoring Breakdown */}
                          <div>
                            <div style={{ fontSize: 10, color: MUTED, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
                              Score Breakdown
                            </div>
                            <MathMatrix trade={trade} config={config} />
                          </div>

                          {/* Right: Strategy Fit */}
                          <div>
                            <div style={{ fontSize: 10, color: MUTED, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
                              Strategy Fit — This Trade
                            </div>

                            {!scorecardData && !scorecardLoading && (
                              <button
                                onClick={loadScorecardForTrade}
                                style={{
                                  padding: '7px 14px', borderRadius: 6,
                                  border: `1px solid ${BORDER}`,
                                  backgroundColor: 'transparent', color: DIM, fontSize: 12,
                                  cursor: 'pointer', fontWeight: 500,
                                }}
                              >
                                &#8635; Load Strategy Scores for {symbol}
                              </button>
                            )}
                            {scorecardData?.error && (
                              <p style={{ color: C.red, fontSize: 12, margin: 0 }}>{scorecardData.error}</p>
                            )}
                            {(filteredScorecardScores.length > 0 || scorecardLoading) && (
                              <StrategyScorecard
                                scores={filteredScorecardScores}
                                selectedKeys={scorecardSelectedKeys}
                                onSelectionChange={setScorecardSelectedKeys}
                                onEvaluate={handleTerminalEvaluate}
                                loading={scorecardLoading}
                              />
                            )}

                            {/* Non-applicable strategies (Puts & Calls only) */}
                            {notApplicableScores.length > 0 && scorecardData && !scorecardLoading && (
                              <div style={{ marginTop: 10 }}>
                                <div style={{ position: 'relative', textAlign: 'center', marginBottom: 8 }}>
                                  <div style={{ borderBottom: '1px dashed rgba(48,54,61,0.5)', position: 'absolute', width: '100%', top: '50%' }} />
                                  <span style={{ position: 'relative', background: BG, padding: '0 8px', fontSize: 9, color: 'rgba(139,148,158,0.5)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                    not applicable to this trade type
                                  </span>
                                </div>
                                {notApplicableScores.map(item => {
                                  const key = item.key ?? item.strategy_key;
                                  const cfg = STRATEGY_CONFIGS[key];
                                  const reason = cfg?.trade_structure === 'credit_spread'
                                    ? 'requires credit spread structure'
                                    : 'not applicable';
                                  return (
                                    <div key={key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 4px' }}>
                                      <span style={{ fontSize: 11, color: MUTED, fontStyle: 'italic' }}>{item.label ?? item.strategy_label ?? key}</span>
                                      <span style={{ fontSize: 10, color: 'rgba(139,148,158,0.5)', fontStyle: 'italic' }}>{reason}</span>
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Evaluation results — below the 2-column grid */}
                        {terminalEvalLoading && (
                          <div style={{ marginTop: 14, padding: '10px 12px', borderRadius: 6, border: `1px solid ${BORDER}`, color: MUTED, fontSize: 12 }}>
                            Evaluating with Claude…
                          </div>
                        )}
                        {terminalEvalError && !terminalEvalLoading && (
                          <div style={{ marginTop: 14, padding: '8px 12px', borderRadius: 6, border: `1px solid ${C.red}40`, color: C.red, fontSize: 12 }}>
                            {terminalEvalError}
                            <button onClick={() => handleTerminalEvaluate(scorecardSelectedKeys)} style={{ marginLeft: 10, background: 'none', border: 'none', color: C.red, fontSize: 11, cursor: 'pointer', textDecoration: 'underline', padding: 0 }}>
                              Retry
                            </button>
                          </div>
                        )}
                        {!terminalEvalLoading && terminalEvaluations.length > 0 && (
                          <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 14 }}>
                            {terminalEvaluations.map(card => (
                              <TradeEvaluationCard
                                key={card.strategy_key}
                                card={card}
                                symbol={symbol}
                                currentPrice={underlyingPrice}
                                smaData={{ smaShort: smaData.smaShort, smaMid: smaData.smaMid, smaLong: smaData.smaLong }}
                                tradeData={selectedTrade}
                                activeStrategy={card.strategy_key}
                              />
                            ))}
                          </div>
                        )}

                        {/* Follow / Take Position buttons */}
                        <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
                          <button
                            onClick={() => setPositionModal({ trade, type: 'follow' })}
                            style={{
                              flex: 1, height: 36, borderRadius: 6,
                              border: `1px solid ${C.accent}40`,
                              backgroundColor: C.accent + '14',
                              color: C.accent, fontFamily: mono, fontSize: 12,
                              fontWeight: 700, cursor: 'pointer', letterSpacing: '0.03em',
                            }}
                          >
                            &#128204; Follow (Paper)
                          </button>
                          <button
                            onClick={() => setPositionModal({ trade, type: 'take' })}
                            style={{
                              flex: 1, height: 36, borderRadius: 6,
                              border: `1px solid ${C.green}40`,
                              backgroundColor: C.green + '14',
                              color: C.green, fontFamily: mono, fontSize: 12,
                              fontWeight: 700, cursor: 'pointer', letterSpacing: '0.03em',
                            }}
                          >
                            &#128176; Take Position (Live)
                          </button>
                        </div>


                      </td>
                    </tr>
                  ),
                ].filter(Boolean);
              })}
            </tbody>
          </table>
        )}

        {/* Empty state */}
        {!loading && !error && trades.length === 0 && underlyingPrice > 0 && (
          <div style={{ padding: '40px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>📊</div>
            <div style={{ fontSize: 15, color: TEXT, fontWeight: 600, marginBottom: 6 }}>
              No results found for {symbol}
            </div>
            <div style={{ fontSize: 13, color: DIM }}>
              No trades passed the current filters. Try a different symbol or adjust settings.
            </div>
          </div>
        )}
      </div>

      {/* Spinner keyframe */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      {/* Follow / Take confirmation modal */}
      {positionModal && (
        <div
          onClick={() => !positionSubmitting && setPositionModal(null)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200,
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: C.card, border: `1px solid ${C.border}`,
              borderRadius: 8, padding: 24, minWidth: 320, maxWidth: 440,
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 10 }}>
              {positionModal.type === 'follow' ? 'Follow (Paper)' : 'Take Position (Live)'}
            </div>
            <div style={{ fontSize: 13, color: C.textDim, marginBottom: 16, lineHeight: 1.5 }}>
              {positionModal.type === 'follow'
                ? `Create a paper-tracked position for ${symbol} — ${positionModal.trade.spread_label || positionModal.trade.label || 'this trade'}.`
                : `Record a live position for ${symbol}. This does not place an order with your broker.`}
            </div>
            <div style={{
              background: C.surfaceAlt, borderRadius: 6, padding: '10px 12px',
              marginBottom: 16, fontFamily: mono, fontSize: 12, color: C.textDim,
            }}>
              <div>Symbol: <span style={{ color: C.text }}>{symbol}</span></div>
              <div>Strategy: <span style={{ color: C.text }}>{activeStrategy}</span></div>
              <div>Entry price: <span style={{ color: C.text }}>
                {(positionModal.trade.net_debit ?? positionModal.trade.premium_dollars ?? 0).toFixed(2)}
              </span></div>
              <div>Underlying: <span style={{ color: C.text }}>{underlyingPrice.toFixed(2)}</span></div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button
                onClick={() => setPositionModal(null)}
                disabled={positionSubmitting}
                style={{
                  fontSize: 12, fontWeight: 600, padding: '6px 14px', borderRadius: 4,
                  border: `1px solid ${C.border}`, background: 'transparent',
                  color: C.textDim, cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={handlePositionConfirm}
                disabled={positionSubmitting}
                style={{
                  fontSize: 12, fontWeight: 700, padding: '6px 16px', borderRadius: 4,
                  border: 'none',
                  background: positionModal.type === 'follow' ? C.accent : C.green,
                  color: '#fff', cursor: positionSubmitting ? 'wait' : 'pointer',
                  fontFamily: mono,
                }}
              >
                {positionSubmitting ? 'Saving...' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Position toast notification */}
      {positionToast && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 300,
          background: positionToast.error ? '#ef4444' : C.green,
          color: '#fff', borderRadius: 6, padding: '10px 18px',
          fontSize: 13, fontWeight: 600, fontFamily: mono,
          boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
        }}>
          {positionToast.message}
        </div>
      )}

      {/* Config drawer — opened via Header gear or inline ⚙ button */}
      <ConfigDrawer
        mode={activeStrategy === 'long_calls' ? 'naked' : 'verticals'}
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        config={analysisConfig}
        onApply={handleConfigApply}
        alignment={signal.text.includes('Bullish') ? 'bullish' : signal.text.includes('Bearish') ? 'bearish' : 'mixed'}
        presets={presets}
        activePresetId={activePresetId}
        onPresetSelect={(id) => {
          setActivePresetId(id);
          const preset = presets.find(p => p.id === id);
          if (preset) setAnalysisConfig(prev => ({
            ...prev,
            weights: { ...preset.weights },
            dte:    { min: preset.dte?.min || 14, max: preset.dte?.max || 60 },
            strikes: { ...prev.strikes, range_pct: preset.strikes?.range_pct || 10 },
            spreads: { min_width: preset.spreads?.min_width || 1, max_width: preset.spreads?.max_width || 10 },
            ...(preset.systemVars ? { systemVars: { ...preset.systemVars } } : {}),
          }));
        }}
        onSavePreset={(name) => {
          const id = name.toLowerCase().replace(/\s+/g, '_');
          setPresets(prev => [...prev, { id, name, icon: '📌', desc: 'Custom preset', ...analysisConfig }]);
          setActivePresetId(id);
        }}
        onOverwrite={(id) => setPresets(prev => prev.map(p => p.id === id ? { ...p, ...analysisConfig } : p))}
        onDelete={(id) => {
          setPresets(prev => prev.filter(p => p.id !== id));
          if (activePresetId === id) setActivePresetId('balanced');
        }}
        onRename={(id, newName) => setPresets(prev => prev.map(p => p.id === id ? { ...p, name: newName } : p))}
      />
    </div>
  );
}
