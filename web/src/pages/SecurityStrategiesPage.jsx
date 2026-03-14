/**
 * SecurityStrategiesPage — Primary landing page for a symbol.
 * Accessed via /security-strategies/:symbol or /security-strategies
 *
 * Layout (top to bottom):
 *   QuoteBar — shared header with all 12 fields
 *   CandlestickChart — price history with SMA lines
 *   StrategyScorecard — all 4 strategies scored
 *   TradeEvaluationCards — rendered after evaluate
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  ComposedChart, Bar, Line, ReferenceLine, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { useParams } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { getQuote, getStrategyScorecard, evaluateStructured } from '../api/client';
import { STRATEGY_CONFIGS } from '../strategy-configs/index';
import QuoteBar from '../components/QuoteBar';
import StrategyScorecard from '../components/StrategyScorecard';
import TradeEvaluationCard from '../components/TradeEvaluationCard';
import { C, mono } from '../styles/tokens';

// ─── Chart helpers (parallel to OptionsTerminal) ───────────────────────────

const GREEN = C.candleGreen;
const RED   = C.red;

function tradingDaysAgo(n) {
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

function generateCandles(price, count = 90) {
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
    const low  = Math.min(open, close) - Math.random() * price * 0.005;
    candles.push({ open, high, low, close, day: dates[i] }); p = close;
  }
  const scale = price / candles[candles.length - 1].close;
  return candles.map(c => ({
    open: c.open * scale, high: c.high * scale,
    low: c.low * scale, close: c.close * scale, day: c.day,
  }));
}

function CandleShape({ x, y, width, height, payload }) {
  if (!payload || !height || height <= 0) return null;
  const domainMin = payload.chartLow;
  if (payload.high <= domainMin) return null;
  const pixPerUnit = height / (payload.high - domainMin);
  const yFor = (price) => y + (payload.high - price) * pixPerUnit;
  const isGreen = payload.close >= payload.open;
  const color = isGreen ? GREEN : RED;
  const cx = x + width / 2;
  const yHigh  = y;
  const yLow   = yFor(payload.low);
  const yBody1 = yFor(Math.max(payload.open, payload.close));
  const yBody2 = yFor(Math.min(payload.open, payload.close));
  return (
    <g>
      <rect x={cx - 0.5} y={yHigh} width={1} height={Math.max(0, yLow - yHigh)} fill={color} />
      <rect x={cx - 3} y={yBody1} width={6} height={Math.max(1, yBody2 - yBody1)}
        fill={color + '50'} stroke={color} strokeWidth={1} />
    </g>
  );
}

function CandleTooltip({ active, payload }) {
  if (!active || !payload?.[0]) return null;
  const d = payload[0].payload;
  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`, borderRadius: 6,
      padding: '6px 10px', fontSize: 11, fontFamily: mono, color: C.text,
    }}>
      <div>O: {d.open?.toFixed(2)}</div>
      <div>H: {d.high?.toFixed(2)}</div>
      <div>L: {d.low?.toFixed(2)}</div>
      <div>C: {d.close?.toFixed(2)}</div>
    </div>
  );
}

// ─── Skeleton eval card ────────────────────────────────────────────────────

function EvalSkeleton({ label }) {
  return (
    <div style={{ borderRadius: 8, border: `1px solid ${C.border}`, backgroundColor: C.card, overflow: 'hidden' }}>
      <div style={{ height: 36, backgroundColor: C.border, opacity: 0.4 }} />
      <div style={{ padding: '10px 16px', borderBottom: `1px solid ${C.border}` }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: C.textDim, marginBottom: 6 }}>{label}</div>
        <div style={{ height: 3, borderRadius: 2, backgroundColor: C.border }} />
      </div>
      <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ height: 14, width: '55%', borderRadius: 3, backgroundColor: C.border }} />
        <div style={{ height: 12, width: '80%', borderRadius: 3, backgroundColor: C.border, opacity: 0.6 }} />
      </div>
    </div>
  );
}

// ─── Mock scores for before-load state ────────────────────────────────────

const MOCK_SCORES = [
  { key: 'steady-paycheck', label: 'Steady Paycheck', score: 84, signal_summary: '30-45 DTE credit spread' },
  { key: 'weekly-grind',    label: 'Weekly Grind',    score: 71, signal_summary: '7-14 DTE credit spread' },
  { key: 'trend-rider',     label: 'Trend Rider',     score: 91, signal_summary: '30-60 DTE long call' },
  { key: 'lottery-ticket',  label: 'Lottery Ticket',  score: 23, signal_summary: '1-7 DTE deep OTM' },
];

// ─── Main component ────────────────────────────────────────────────────────

export default function SecurityStrategiesPage() {
  const { symbol: symbolParam } = useParams();
  const { activeSymbol, setActiveSymbol, prices } = useApp();

  const symbolUpper = (symbolParam || activeSymbol || '').toUpperCase();

  const [quote,          setQuote]          = useState(null);
  const [candles,        setCandles]        = useState([]);
  const [scores,         setScores]         = useState(null);
  const [smaSignal,      setSmaSignal]      = useState(null);
  const [loading,        setLoading]        = useState(false);
  const [error,          setError]          = useState(null);
  const [selectedKeys,   setSelectedKeys]   = useState([]);
  const [evalLoading,    setEvalLoading]    = useState(false);
  const [evalError,      setEvalError]      = useState(null);
  const [evaluations,    setEvaluations]    = useState([]);

  const chartStartDate = useRef(tradingDaysAgo(90));

  // Sync activeSymbol with URL param
  useEffect(() => {
    if (symbolUpper && symbolUpper !== activeSymbol) {
      setActiveSymbol(symbolUpper);
    }
  }, [symbolUpper]); // eslint-disable-line react-hooks/exhaustive-deps

  // Reset on symbol change
  useEffect(() => {
    setScores(null);
    setSmaSignal(null);
    setError(null);
    setSelectedKeys([]);
    setEvaluations([]);
    setEvalError(null);
    setQuote(null);
    setCandles([]);
  }, [symbolUpper]);

  // Fetch quote + generate candles
  const fetchQuote = useCallback(async () => {
    if (!symbolUpper) return;
    try {
      const data = await getQuote(symbolUpper);
      setQuote(data);
      if (data?.price > 0) {
        const count = countTradingDays(chartStartDate.current);
        setCandles(generateCandles(data.price, count));
      }
    } catch { /* quote fetch is best-effort */ }
  }, [symbolUpper]);

  // Fetch scorecard
  const fetchScorecard = useCallback(async () => {
    if (!symbolUpper) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getStrategyScorecard(symbolUpper);
      setScores(data.strategies || []);
      setSmaSignal(data.sma_signal || null);
      // Pre-check highest scorer
      const sorted = [...(data.strategies || [])].sort((a, b) => b.score - a.score);
      if (sorted.length > 0) {
        const topKey = sorted[0].key ?? sorted[0].strategy_key;
        setSelectedKeys([topKey]);
      }
    } catch (err) {
      setError(err.message || 'Failed to load scorecard');
    } finally {
      setLoading(false);
    }
  }, [symbolUpper]);

  useEffect(() => {
    if (symbolUpper) {
      fetchQuote();
      fetchScorecard();
    }
  }, [fetchQuote, fetchScorecard]);

  // SMA from candles
  const smaData = useMemo(() => {
    if (!candles.length) return null;
    const sma = (period) => {
      const slice = candles.slice(-period);
      return slice.reduce((s, c) => s + c.close, 0) / slice.length;
    };
    return { smaShort: sma(8), smaMid: sma(21), smaLong: sma(50) };
  }, [candles]);

  const smaSignalStr = smaSignal?.alignment || (
    smaData && candles.length
      ? (candles[candles.length - 1]?.close > (smaData.smaShort || 0) &&
         smaData.smaShort > (smaData.smaMid || 0) ? 'BULLISH' : 'MIXED')
      : undefined
  );

  // Chart data with SMA values
  const chartData = useMemo(() => {
    return candles.map((c, i) => {
      const sma = (period) => {
        if (i < period - 1) return null;
        const slice = candles.slice(i - period + 1, i + 1);
        return slice.reduce((s, c) => s + c.close, 0) / slice.length;
      };
      return { ...c, sma8: sma(8), sma21: sma(21), sma50: sma(50) };
    });
  }, [candles]);

  const chartBounds = useMemo(() => {
    if (!chartData.length) return { low: 0, high: 100 };
    const lows  = chartData.map(c => c.low);
    const highs = chartData.map(c => c.high);
    const low   = Math.min(...lows);
    const high  = Math.max(...highs);
    const pad   = (high - low) * 0.03;
    return { low: low - pad, high: high + pad };
  }, [chartData]);

  const chartDataWithMeta = useMemo(() => {
    return chartData.map(c => ({ ...c, chartLow: chartBounds.low }));
  }, [chartData, chartBounds]);

  // Evaluate
  const handleEvaluate = useCallback(async (keys) => {
    if (!keys.length || !symbolUpper) return;
    setEvalLoading(true);
    setEvalError(null);
    setEvaluations([]);
    const currentScores = scores || [];
    const ivSource = keys
      .map(k => currentScores.find(s => (s.strategy_key ?? s.key) === k))
      .find(s => s?.best_trade?.iv != null);
    const iv = ivSource?.best_trade?.iv ?? 0.25;
    const currentPrice = quote?.price || prices[symbolUpper]?.price || 0;
    try {
      const data = await evaluateStructured({
        symbol:        symbolUpper,
        current_price: currentPrice,
        iv,
        sma_alignment: smaData
          ? { sma_8: smaData.smaShort, sma_21: smaData.smaMid, sma_50: smaData.smaLong }
          : {},
        strategy_keys: keys,
        trade:         null,
      });
      setEvaluations([...(data.evaluations ?? [])].sort((a, b) => b.score - a.score));
    } catch (err) {
      setEvalError(err.message || 'Evaluation failed');
    } finally {
      setEvalLoading(false);
    }
  }, [symbolUpper, scores, smaData, quote, prices]);

  const displayScores = scores || MOCK_SCORES;
  const usingMock = !scores && !loading;
  const currentPrice = quote?.price || prices[symbolUpper]?.price || 0;

  const smaForCards = smaData
    ? { smaShort: smaData.smaShort, smaMid: smaData.smaMid, smaLong: smaData.smaLong }
    : null;

  return (
    <div style={{ backgroundColor: C.bg, minHeight: '100%', paddingBottom: 32 }}>

      {/* QuoteBar */}
      <QuoteBar
        symbol={symbolUpper || undefined}
        quote={quote}
        smaSignal={smaSignalStr}
      />

      {/* Candlestick Chart */}
      {candles.length > 0 && (
        <div style={{ borderBottom: `1px solid ${C.border}`, backgroundColor: C.bg }}>
          <ResponsiveContainer width="100%" height={180}>
            <ComposedChart data={chartDataWithMeta} margin={{ top: 8, right: 60, bottom: 4, left: 0 }}>
              <CartesianGrid vertical={false} stroke={C.borderSubtle} />
              <XAxis
                dataKey="day" interval={13}
                tick={{ fill: C.textDim, fontSize: 10, fontFamily: 'monospace' }}
                axisLine={{ stroke: C.textDim }} tickLine={{ stroke: C.textDim }}
                height={22} minTickGap={40}
              />
              <YAxis
                orientation="right" width={55}
                domain={[chartBounds.low, chartBounds.high]}
                tick={{ fill: C.textDim, fontSize: 10 }}
                axisLine={{ stroke: C.textDim }} tickLine={{ stroke: C.textDim }}
                tickFormatter={v => v.toFixed(0)}
              />
              <Tooltip content={<CandleTooltip />} />
              <Bar dataKey="high" baseValue={chartBounds.low} shape={<CandleShape />}
                isAnimationActive={false} fill="transparent" />
              <Line type="monotone" dataKey="sma8"  stroke={C.smaCyan}   strokeWidth={1.5} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="sma21" stroke={C.smaOrange} strokeWidth={1.5} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="sma50" stroke={C.smaRed}    strokeWidth={1.5} dot={false} isAnimationActive={false} />
              {currentPrice > 0 && (
                <ReferenceLine y={currentPrice} stroke={C.accent + '90'} strokeDasharray="4 4" />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Scorecard section */}
      <div style={{ padding: '16px 16px 0' }}>

        {/* Header row */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 10.5, color: C.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
              Strategy Scorecard
            </span>
            {symbolUpper && (
              <span style={{ fontSize: 11, color: C.textDim, fontFamily: mono, padding: '1px 7px', borderRadius: 4, border: `1px solid ${C.border}` }}>
                {symbolUpper}
              </span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 10, color: C.textMuted }}>Select strategies to evaluate</span>
            <button
              onClick={() => fetchScorecard()}
              disabled={loading}
              style={{ background: 'none', border: `1px solid ${C.border}`, color: loading ? C.textMuted : C.textDim, fontSize: 13, cursor: loading ? 'default' : 'pointer', padding: '2px 7px', borderRadius: 5 }}
            >
              {loading ? '…' : '⟳'}
            </button>
          </div>
        </div>

        {/* Mock data notice */}
        {usingMock && !error && (
          <div style={{ marginBottom: 12, padding: '7px 12px', borderRadius: 6, border: `1px solid ${C.border}`, backgroundColor: C.surfaceAlt, color: C.textDim, fontSize: 11 }}>
            Showing sample data — connect Schwab and click ⟳ for live scores
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div style={{ marginBottom: 12, padding: '8px 12px', borderRadius: 6, border: `1px solid ${C.red}40`, backgroundColor: C.redDim, color: C.red, fontSize: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>{error}</span>
            <button onClick={fetchScorecard} style={{ background: 'none', border: 'none', color: C.red, fontSize: 11, cursor: 'pointer', textDecoration: 'underline', padding: 0 }}>Retry</button>
          </div>
        )}

        {/* Scorecard */}
        <StrategyScorecard
          scores={loading ? [] : displayScores}
          selectedKeys={selectedKeys}
          onSelectionChange={setSelectedKeys}
          onEvaluate={handleEvaluate}
          loading={loading}
        />
      </div>

      {/* Evaluation results */}
      {(evalLoading || evalError || evaluations.length > 0) && (
        <div style={{ padding: '16px 16px 0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <span style={{ fontSize: 10.5, color: C.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
              Evaluation Results
            </span>
            {evaluations.length > 0 && !evalLoading && (
              <button
                onClick={() => { setEvaluations([]); setEvalError(null); }}
                style={{ background: 'none', border: 'none', color: C.textMuted, fontSize: 11, cursor: 'pointer', padding: 0, textDecoration: 'underline' }}
              >
                Clear
              </button>
            )}
          </div>

          {evalError && !evalLoading && (
            <div style={{ marginBottom: 16, padding: '8px 12px', borderRadius: 6, border: `1px solid ${C.red}40`, backgroundColor: C.redDim, color: C.red, fontSize: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>{evalError}</span>
              <button onClick={() => handleEvaluate(selectedKeys)} style={{ background: 'none', border: 'none', color: C.red, fontSize: 11, cursor: 'pointer', textDecoration: 'underline', padding: 0 }}>Retry</button>
            </div>
          )}

          {evalLoading && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {selectedKeys.map(k => (
                <EvalSkeleton key={k} label={(scores || MOCK_SCORES).find(s => (s.strategy_key ?? s.key) === k)?.label ?? k} />
              ))}
            </div>
          )}

          {!evalLoading && evaluations.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {evaluations.map(card => {
                const matchingScore = (scores || MOCK_SCORES).find(s => (s.strategy_key ?? s.key) === card.strategy_key);
                return (
                  <TradeEvaluationCard
                    key={card.strategy_key}
                    card={card}
                    symbol={symbolUpper}
                    currentPrice={currentPrice}
                    smaData={smaForCards}
                    tradeData={matchingScore?.best_trade ?? null}
                    activeStrategy={card.strategy_key}
                  />
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
