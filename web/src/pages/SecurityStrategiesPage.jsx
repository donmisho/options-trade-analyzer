/**
 * SecurityStrategiesPage — Primary landing page for a symbol.
 * Accessed via /security-strategies/:symbol or /security-strategies
 *
 * Layout (top to bottom):
 *   Symbol input + Analyze button
 *   QuoteBar — shared header with all fields
 *   CandlestickChart — price history with SMA lines + SMA config panel
 *   StrategyScorecard — all 4 strategies scored
 *   TradeEvaluationCards — rendered after evaluate
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  ComposedChart, Bar, Line, ReferenceLine, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { getQuote, getStrategyScorecard, evaluateStructured, searchSymbolsStatic } from '../api/client';
import SymbolSearch from '../components/SymbolSearch';
import { STRATEGY_CONFIGS } from '../strategy-configs/index';
import ConfigDrawer from '../components/ConfigDrawer';
import QuoteBar from '../components/QuoteBar';
import StrategyScorecard from '../components/StrategyScorecard';
import TradeEvaluationCard from '../components/TradeEvaluationCard';
import { C, mono, DEFAULT_PRESETS } from '../styles/tokens';

// ─── Chart helpers ──────────────────────────────────────────────────────────

const GREEN = C.candleGreen;
const RED   = C.red;
const SMA8_COLOR  = C.smaCyan;
const SMA21_COLOR = C.smaOrange;
const SMA50_COLOR = C.smaRed;

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
  const { activeSymbol, setActiveSymbol, prices, configOpen, setConfigOpen, positionSymbols } = useApp();
  const navigate = useNavigate();
  const location = useLocation();

  const initSymbol = (symbolParam || activeSymbol || 'SPY').toUpperCase();

  // ── State ──────────────────────────────────────────────────────────────────
  const [symbol,         setSymbol]         = useState(initSymbol);
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
  const [lastAnalyzed,   setLastAnalyzed]   = useState(null);
  const [chartRange,     setChartRange]     = useState(90);
  const [chartStartDate, setChartStartDate] = useState(() => tradingDaysAgo(90));
  const chartStartDateRef = useRef(chartStartDate);

  // ── Analysis config (smaPeriods used by chart legend + ConfigDrawer) ───────
  const [presets,        setPresets]        = useState(DEFAULT_PRESETS);
  const [activePresetId, setActivePresetId] = useState('balanced');
  const [analysisConfig, setAnalysisConfig] = useState(() => {
    const preset = DEFAULT_PRESETS.find(p => p.id === 'balanced') || DEFAULT_PRESETS[0];
    return { smaPeriods: { short: 8, mid: 21, long: 50 }, ...preset };
  });
  const smaPeriods = analysisConfig.smaPeriods || { short: 8, mid: 21, long: 50 };

  // ── Fetch quote + generate candles ─────────────────────────────────────
  const fetchQuote = useCallback(async (sym) => {
    const target = sym || symbol;
    if (!target) return;
    try {
      const data = await getQuote(target);
      setQuote(data);
      if (data?.price > 0) {
        const count = countTradingDays(chartStartDateRef.current);
        setCandles(generateCandles(data.price, count));
      }
    } catch { /* quote fetch is best-effort */ }
  }, [symbol]);

  // ── Fetch scorecard ─────────────────────────────────────────────────────
  const fetchScorecard = useCallback(async (sym) => {
    const target = sym || symbol;
    if (!target) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getStrategyScorecard(target);
      setScores(data.strategies || []);
      setSmaSignal(data.sma_signal || null);
      setLastAnalyzed(new Date());
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
  }, [symbol]);

  // ── Initial mount: auto-fetch when no URL param drives the fetch ─────────
  // When the page loads at /security-strategies (no param), the symbolParam
  // effect returns early, so nothing fetches. This fills that gap.
  useEffect(() => {
    if (!symbolParam) {
      fetchQuote(initSymbol);
      fetchScorecard(initSymbol);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Watchlist click: URL param changes with fromWatchlist state ──────────
  // Fires on mount (when URL has a param) and on subsequent param changes.
  const prevSymbolParam = useRef(null);
  useEffect(() => {
    if (!symbolParam) return;
    const sym = symbolParam.toUpperCase();
    setSymbol(sym);
    if (sym !== activeSymbol) setActiveSymbol(sym);

    const isWatchlistNav = location.state?.fromWatchlist === true;
    const symbolChanged  = symbolParam !== prevSymbolParam.current;
    prevSymbolParam.current = symbolParam;

    if (isWatchlistNav || symbolChanged) {
      // Reset stale data for new symbol
      setScores(null); setSmaSignal(null); setError(null);
      setSelectedKeys([]); setEvaluations([]); setEvalError(null);
      setQuote(null); setCandles([]); setLastAnalyzed(null);
      fetchQuote(sym);
      fetchScorecard(sym);
    }
  }, [symbolParam, location.state]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Regenerate candles when chart start date changes ─────────────────────
  useEffect(() => {
    chartStartDateRef.current = chartStartDate;
    if (quote?.price > 0) {
      const count = countTradingDays(chartStartDate);
      setCandles(generateCandles(quote.price, count));
    }
  }, [chartStartDate]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Symbol select — fires immediately on SymbolSearch selection ─────────
  const handleSymbolSelect = (sym) => {
    if (!sym) return;
    setSymbol(sym);
    setActiveSymbol(sym);
    // Reset stale data
    setScores(null); setSmaSignal(null); setError(null);
    setSelectedKeys([]); setEvaluations([]); setEvalError(null);
    setQuote(null); setCandles([]); setLastAnalyzed(null);
    // Update URL
    prevSymbolParam.current = sym.toLowerCase();
    navigate(`/security-strategies/${sym}`);
    fetchQuote(sym);
    fetchScorecard(sym);
  };

  // ── Config apply ────────────────────────────────────────────────────────
  const handleConfigApply = useCallback((newConfig) => {
    setAnalysisConfig(prev => ({ ...prev, ...newConfig }));
    setConfigOpen(false);
  }, [setConfigOpen]);

  // ── SMA computation from candles ───────────────────────────────────────
  const smaData = useMemo(() => {
    if (!candles.length) return null;
    const sma = (period) => {
      const slice = candles.slice(-period);
      return slice.reduce((s, c) => s + c.close, 0) / slice.length;
    };
    return { smaShort: sma(smaPeriods.short), smaMid: sma(smaPeriods.mid), smaLong: sma(smaPeriods.long) };
  }, [candles, smaPeriods]);

  const smaSignalStr = smaSignal?.alignment || (
    smaData && candles.length
      ? (candles[candles.length - 1]?.close > (smaData.smaShort || 0) &&
         smaData.smaShort > (smaData.smaMid || 0) ? 'BULLISH' : 'MIXED')
      : undefined
  );

  // ── Chart data with SMA values ─────────────────────────────────────────
  const chartData = useMemo(() => {
    return candles.map((c, i) => {
      const sma = (period) => {
        if (i < period - 1) return null;
        const slice = candles.slice(i - period + 1, i + 1);
        return slice.reduce((s, c) => s + c.close, 0) / slice.length;
      };
      return { ...c, sma8: sma(smaPeriods.short), sma21: sma(smaPeriods.mid), sma50: sma(smaPeriods.long) };
    });
  }, [candles, smaPeriods]);

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

  // ── Evaluate ────────────────────────────────────────────────────────────
  const handleEvaluate = useCallback(async (keys) => {
    if (!keys.length || !symbol) return;
    setEvalLoading(true);
    setEvalError(null);
    setEvaluations([]);
    const currentScores = scores || [];
    const ivSource = keys
      .map(k => currentScores.find(s => (s.strategy_key ?? s.key) === k))
      .find(s => s?.best_trade?.iv != null);
    const iv = ivSource?.best_trade?.iv ?? 0.25;
    const currentPrice = quote?.price || prices[symbol]?.price || 0;
    try {
      const data = await evaluateStructured({
        symbol,
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
  }, [symbol, scores, smaData, quote, prices]);

  const displayScores = scores || MOCK_SCORES;
  const usingMock = !scores && !loading;
  const currentPrice = quote?.price || prices[symbol]?.price || 0;

  const smaForCards = smaData
    ? { smaShort: smaData.smaShort, smaMid: smaData.smaMid, smaLong: smaData.smaLong }
    : null;

  return (
    <div style={{ backgroundColor: C.bg, minHeight: '100%', paddingBottom: 32 }}>

      {/* ── Symbol search ── */}
      <div style={{ padding: '10px 16px 10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <SymbolSearch
            onSelect={handleSymbolSelect}
            placeholder="Search symbol..."
            searchFn={searchSymbolsStatic}
            positionSymbols={positionSymbols}
            initialValue={null}
          />
          {loading && (
            <div style={{
              width: 16, height: 16, border: `2px solid ${C.border}`,
              borderTopColor: C.accent, borderRadius: '50%',
              animation: 'spin 0.7s linear infinite',
              flexShrink: 0,
            }} />
          )}
        </div>
      </div>

      {/* ── QuoteBar ── */}
      <QuoteBar
        symbol={symbol || undefined}
        quote={quote}
        smaSignal={smaSignalStr}
        lastAnalyzed={lastAnalyzed}
      />

      {/* ── Candlestick Chart ── */}
      {candles.length > 0 && (
        <div style={{ borderBottom: `1px solid ${C.border}`, backgroundColor: C.bg, position: 'relative' }}>
          {/* SMA + Date config panel — right side overlay */}
          <div style={{
            position: 'absolute', top: 0, right: 0, bottom: 0, zIndex: 10,
            width: 130,
            display: 'flex', flexDirection: 'column', justifyContent: 'center',
            padding: '8px 10px',
            borderLeft: `1px solid ${C.border}`,
            background: `linear-gradient(135deg, ${C.surfaceAlt} 0%, ${C.card} 100%)`,
            borderRadius: '0 4px 4px 0',
          }}>
            <div style={{
              fontSize: 8, fontWeight: 700, color: C.textMuted,
              letterSpacing: '0.07em', textTransform: 'uppercase',
              marginBottom: 7, textAlign: 'center',
              borderBottom: `1px solid ${C.border}`, paddingBottom: 5,
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

            <div style={{
              fontSize: 8, fontWeight: 700, color: C.textMuted,
              letterSpacing: '0.07em', textTransform: 'uppercase',
              marginTop: 10, marginBottom: 6, textAlign: 'center',
              borderTop: `1px solid ${C.border}`, paddingTop: 8,
            }}>
              Chart Range
            </div>
            {[30, 90, 180].map(n => (
              <button
                key={n}
                onClick={() => { setChartRange(n); setChartStartDate(tradingDaysAgo(n)); }}
                style={{
                  display: 'block', width: '100%', marginBottom: 4,
                  padding: '3px 0', borderRadius: 4, fontSize: 10,
                  fontFamily: mono, cursor: 'pointer',
                  border: `1px solid ${chartRange === n ? C.accent : C.border}`,
                  background: chartRange === n ? C.accent + '20' : 'none',
                  color: chartRange === n ? C.accent : C.textDim,
                }}
              >
                {n}d
              </button>
            ))}
          </div>

          <ResponsiveContainer width="100%" height={215}>
            <ComposedChart data={chartDataWithMeta} margin={{ top: 8, right: 138, bottom: 4, left: 0 }}>
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
              <Line type="monotone" dataKey="sma8"  stroke={SMA8_COLOR}  strokeWidth={1.5} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="sma21" stroke={SMA21_COLOR} strokeWidth={1.5} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="sma50" stroke={SMA50_COLOR} strokeWidth={1.5} dot={false} isAnimationActive={false} />
              {currentPrice > 0 && (
                <ReferenceLine y={currentPrice} stroke={C.accent + '90'} strokeDasharray="4 4" />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── Scorecard section ── */}
      <div style={{ padding: '16px 16px 0' }}>

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
            <button onClick={() => fetchScorecard()} style={{ background: 'none', border: 'none', color: C.red, fontSize: 11, cursor: 'pointer', textDecoration: 'underline', padding: 0 }}>Retry</button>
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

      {/* ── Evaluation results ── */}
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
                    symbol={symbol}
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

      {/* ── Bottom bar with Config button ── */}
      <div style={{
        display: 'flex', justifyContent: 'flex-end', alignItems: 'center',
        padding: '12px 16px 0', gap: 10,
      }}>
        <button
          onClick={() => setConfigOpen(true)}
          style={{
            padding: '4px 10px', borderRadius: 5, fontSize: 11,
            border: `1px solid ${C.border}`, background: 'none',
            color: C.textDim, cursor: 'pointer',
          }}
        >
          ⚙ Config
        </button>
      </div>

      {/* ── Config drawer (opened via ⚙ Config or Header gear) ── */}
      <ConfigDrawer
        mode="verticals"
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        config={analysisConfig}
        onApply={handleConfigApply}
        presets={presets}
        activePresetId={activePresetId}
        onPresetSelect={(id) => {
          setActivePresetId(id);
          const preset = presets.find(p => p.id === id);
          if (preset) setAnalysisConfig(prev => ({ ...prev, ...preset, smaPeriods: preset.smaPeriods || prev.smaPeriods }));
        }}
        onSavePreset={(name, cfg) => {
          const id = name.toLowerCase().replace(/\s+/g, '-');
          setPresets(prev => [...prev, { id, name, ...cfg }]);
          setActivePresetId(id);
        }}
      />
    </div>
  );
}
