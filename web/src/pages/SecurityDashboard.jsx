/**
 * SecurityDashboard — Per-symbol strategy scorecard page.
 *
 * Primary entry point for trade discovery. Shows all four strategies scored
 * simultaneously for the active symbol. User selects strategies, then clicks
 * Evaluate to trigger structured Claude analysis (Phase 2.11).
 *
 * URL: /security/:symbol
 *
 * Data flow:
 *   URL param :symbol → setActiveSymbol → QuoteBar fetches quote
 *   POST /api/v1/analysis/scorecard → StrategyScorecard receives real scores
 *   ConfigDrawer (strategy-aware) reads/writes localStorage overrides
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { getStrategyScorecard, evaluateStructured } from '../api/client';
import { STRATEGY_CONFIGS } from '../strategy-configs/index';
import QuoteBar from '../components/QuoteBar';
import StrategyScorecard from '../components/StrategyScorecard';
import TradeEvaluationCard from '../components/TradeEvaluationCard';
import ConfigDrawer from '../components/ConfigDrawer';
import { C, mono } from '../styles/tokens';

// Sample data shown before the first live scorecard loads.
// Scores here are intentionally spread to illustrate the range (not all high).
const MOCK_SCORES = [
  {
    key: 'steady-paycheck',
    label: 'Steady Paycheck',
    score: 84,
    best_trade: 'Sample — connect Schwab for live data',
    signal_summary: '30-45 DTE credit spreads. Sample data only.',
  },
  {
    key: 'weekly-grind',
    label: 'Weekly Grind',
    score: 71,
    best_trade: 'Sample — connect Schwab for live data',
    signal_summary: '7-14 DTE. Theta/Gamma ratio focus. Sample data only.',
  },
  {
    key: 'trend-rider',
    label: 'Trend Rider',
    score: 91,
    best_trade: 'Sample — connect Schwab for live data',
    signal_summary: 'SMA-aligned long calls. Sample data only.',
  },
  {
    key: 'lottery-ticket',
    label: 'Lottery Ticket',
    score: 23,
    best_trade: 'Sample — connect Schwab for live data',
    signal_summary: 'Deep OTM. Payout ratio below minimum. Sample data only.',
  },
];

// ── Skeleton card shown while evaluation is loading ───────────────────────────
function EvalSkeleton({ label }) {
  return (
    <div style={{
      borderRadius: 8,
      border: `1px solid ${C.border}`,
      backgroundColor: C.card,
      overflow: 'hidden',
    }}>
      {/* Verdict banner placeholder */}
      <div style={{ height: 36, backgroundColor: C.border, opacity: 0.4 }} />

      {/* Strategy label + score bar placeholder */}
      <div style={{ padding: '10px 16px', borderBottom: `1px solid ${C.border}` }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: C.textDim, marginBottom: 6 }}>
          {label}
        </div>
        <div style={{ height: 3, borderRadius: 2, backgroundColor: C.border }} />
      </div>

      {/* Trade row placeholders */}
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ height: 14, width: '55%', borderRadius: 3, backgroundColor: C.border }} />
        <div style={{ height: 12, width: '80%', borderRadius: 3, backgroundColor: C.border, opacity: 0.6 }} />
        <div style={{ height: 12, width: '70%', borderRadius: 3, backgroundColor: C.border, opacity: 0.6 }} />
        <div style={{ height: 12, width: '65%', borderRadius: 3, backgroundColor: C.border, opacity: 0.6 }} />
      </div>

      {/* Matrix placeholder */}
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${C.border}` }}>
        <div style={{ height: 10, width: 120, borderRadius: 3, backgroundColor: C.border, marginBottom: 10 }} />
        <div style={{ height: 80, borderRadius: 4, backgroundColor: C.border, opacity: 0.35 }} />
      </div>

      {/* Claude read placeholder */}
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', gap: 7 }}>
        <div style={{ height: 10, width: 90, borderRadius: 3, backgroundColor: C.border, marginBottom: 4 }} />
        <div style={{ height: 11, borderRadius: 3, backgroundColor: C.border, opacity: 0.5 }} />
        <div style={{ height: 11, width: '85%', borderRadius: 3, backgroundColor: C.border, opacity: 0.5 }} />
        <div style={{ height: 11, width: '60%', borderRadius: 3, backgroundColor: C.border, opacity: 0.5 }} />
      </div>

      {/* Action buttons placeholder */}
      <div style={{ padding: '14px 16px', display: 'flex', gap: 10 }}>
        <div style={{ flex: 1, height: 36, borderRadius: 6, backgroundColor: C.border, opacity: 0.4 }} />
        <div style={{ flex: 1, height: 36, borderRadius: 6, backgroundColor: C.border, opacity: 0.4 }} />
      </div>
    </div>
  );
}

export default function SecurityDashboard() {
  const { symbol } = useParams();
  const { activeSymbol, setActiveSymbol, configOpen, setConfigOpen, prices } = useApp();

  const [scores, setScores]           = useState(null);   // null = not yet loaded
  const [smaSignal, setSmaSignal]     = useState(null);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState(null);
  const [selectedKeys, setSelectedKeys] = useState([]);

  // Evaluation state (Phase 2.11)
  const [evalLoading, setEvalLoading]   = useState(false);
  const [evalError, setEvalError]       = useState(null);
  const [evaluations, setEvaluations]   = useState([]);   // TradeEvaluationCard[]

  const symbolUpper = symbol?.toUpperCase();

  // Keep AppContext activeSymbol in sync with URL param
  useEffect(() => {
    if (symbolUpper && symbolUpper !== activeSymbol) {
      setActiveSymbol(symbolUpper);
    }
  }, [symbolUpper]); // eslint-disable-line react-hooks/exhaustive-deps

  // Reset scorecard and evaluations when symbol changes
  useEffect(() => {
    setScores(null);
    setSmaSignal(null);
    setError(null);
    setSelectedKeys([]);
    setEvaluations([]);
    setEvalError(null);
  }, [symbolUpper]);

  const fetchScorecard = useCallback(async (userConfig = null) => {
    if (!symbolUpper) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getStrategyScorecard(symbolUpper, userConfig);
      setScores(data.strategies || []);
      setSmaSignal(data.sma_signal || null);
    } catch (err) {
      setError(err.message || 'Failed to load scorecard');
      setScores(null);
    } finally {
      setLoading(false);
    }
  }, [symbolUpper]);

  // Fetch scorecard on mount and when symbol changes
  useEffect(() => {
    fetchScorecard();
  }, [fetchScorecard]);

  // ConfigDrawer: show the first selected strategy's config, or first in the list
  const activeStrategyKey = selectedKeys[0] || scores?.[0]?.key || MOCK_SCORES[0].key;
  const activeStrategyCfg = STRATEGY_CONFIGS[activeStrategyKey];
  const hasConfigSchema = !!(activeStrategyCfg?.configSchema?.length);

  const handleEvaluate = useCallback(async (keys) => {
    if (!keys.length || !symbolUpper) return;

    setEvalLoading(true);
    setEvalError(null);
    setEvaluations([]);

    // Derive IV from the best available best_trade across selected strategies.
    // Fall back to 0.25 (25%) if no IV is present in the scorecard data.
    const currentScores = scores || [];
    const ivSource = keys
      .map(k => currentScores.find(s => (s.strategy_key ?? s.key) === k))
      .find(s => s?.best_trade?.iv != null);
    const iv = ivSource?.best_trade?.iv ?? 0.25;

    const currentPrice = prices[symbolUpper]?.price ?? 0;

    try {
      const data = await evaluateStructured({
        symbol:        symbolUpper,
        current_price: currentPrice,
        iv,
        sma_alignment: smaSignal ?? {},
        strategy_keys: keys,
        trade:         null,
      });
      // Sort highest score first
      const sorted = [...(data.evaluations ?? [])].sort((a, b) => b.score - a.score);
      setEvaluations(sorted);
    } catch (err) {
      setEvalError(err.message || 'Evaluation failed');
    } finally {
      setEvalLoading(false);
    }
  }, [symbolUpper, scores, smaSignal, prices]);

  const handleConfigApply = useCallback((overrides) => {
    // Re-run scorecard with updated config overrides for the active strategy
    fetchScorecard(overrides);
  }, [fetchScorecard]);

  // Display: use real scores if loaded, otherwise mock data as preview
  const displayScores = scores || MOCK_SCORES;
  const usingMockData = !scores && !loading;

  // SMA signal banner
  const smaAlignment = smaSignal?.alignment;
  const smaColor = smaAlignment === 'BULLISH' ? C.green
    : smaAlignment === 'BEARISH' ? C.red
    : C.amber;
  const smaBannerText = smaSignal
    ? `SMA: ${smaAlignment}${smaSignal.description ? '  ' + smaSignal.description : ''}`
    : null;

  return (
    <div style={{ backgroundColor: C.bg, minHeight: '100%', paddingBottom: 24 }}>

      {/* Quote bar — reads activeSymbol from AppContext */}
      <QuoteBar title="Security Dashboard" />

      {/* SMA alignment banner — shown only when real data is loaded */}
      {smaBannerText && (
        <div style={{
          padding: '6px 20px',
          borderBottom: `1px solid ${C.border}`,
          backgroundColor: C.surface,
        }}>
          <span style={{
            fontSize: 11.5,
            fontWeight: 600,
            color: smaColor,
            fontFamily: mono,
            letterSpacing: '0.03em',
          }}>
            {smaBannerText}
          </span>
        </div>
      )}

      {/* Main content */}
      <div style={{ padding: '20px 20px 0' }}>

        {/* Section header row */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 14,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              fontSize: 10.5,
              color: C.textMuted,
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.07em',
            }}>
              Strategy Scorecard
            </span>
            {symbolUpper && (
              <span style={{
                fontSize: 11,
                color: C.textDim,
                fontFamily: mono,
                padding: '1px 7px',
                borderRadius: 4,
                border: `1px solid ${C.border}`,
              }}>
                {symbolUpper}
              </span>
            )}
          </div>

          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {/* Refresh button */}
            <button
              onClick={() => fetchScorecard()}
              disabled={loading}
              title="Refresh scorecard"
              style={{
                background: 'none',
                border: `1px solid ${C.border}`,
                color: loading ? C.textMuted : C.textDim,
                fontSize: 14,
                cursor: loading ? 'default' : 'pointer',
                padding: '3px 8px',
                borderRadius: 5,
                transition: 'color 0.15s',
              }}
            >
              {loading ? '...' : '\u27f3'}
            </button>

            {/* Config gear — only shown when active strategy has configSchema */}
            {hasConfigSchema && (
              <button
                onClick={() => setConfigOpen(true)}
                title={`Configure ${activeStrategyCfg.label} parameters`}
                style={{
                  background: 'none',
                  border: `1px solid ${C.border}`,
                  color: C.textDim,
                  fontSize: 14,
                  cursor: 'pointer',
                  padding: '3px 8px',
                  borderRadius: 5,
                  transition: 'color 0.15s, border-color 0.15s',
                }}
              >
                &#9881;
              </button>
            )}
          </div>
        </div>

        {/* Mock data notice */}
        {usingMockData && !error && (
          <div style={{
            marginBottom: 12,
            padding: '7px 12px',
            borderRadius: 6,
            border: `1px solid ${C.border}`,
            backgroundColor: C.surfaceAlt,
            color: C.textDim,
            fontSize: 11,
          }}>
            Showing sample data — connect Schwab and click &#8627; for live scores
          </div>
        )}

        {/* Error banner */}
        {error && !loading && (
          <div style={{
            marginBottom: 12,
            padding: '8px 12px',
            borderRadius: 6,
            border: `1px solid ${C.red}40`,
            backgroundColor: C.redDim,
            color: C.red,
            fontSize: 12,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}>
            <span>{error}</span>
            <button
              onClick={() => fetchScorecard()}
              style={{
                background: 'none',
                border: 'none',
                color: C.red,
                fontSize: 11,
                cursor: 'pointer',
                textDecoration: 'underline',
                padding: 0,
              }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Strategy Scorecard component */}
        <StrategyScorecard
          scores={loading ? [] : displayScores}
          selectedKeys={selectedKeys}
          onSelectionChange={setSelectedKeys}
          onEvaluate={handleEvaluate}
          loading={loading}
        />
      </div>

      {/* ── Evaluation results ───────────────────────────────────────── */}
      {(evalLoading || evalError || evaluations.length > 0) && (
        <div style={{ padding: '20px 20px 0' }}>

          {/* Section label */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 14,
          }}>
            <span style={{
              fontSize: 10.5,
              color: C.textMuted,
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.07em',
            }}>
              Evaluation Results
            </span>
            {evaluations.length > 0 && !evalLoading && (
              <button
                onClick={() => { setEvaluations([]); setEvalError(null); }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: C.textMuted,
                  fontSize: 11,
                  cursor: 'pointer',
                  padding: 0,
                  textDecoration: 'underline',
                }}
              >
                Clear
              </button>
            )}
          </div>

          {/* Error banner */}
          {evalError && !evalLoading && (
            <div style={{
              marginBottom: 16,
              padding: '8px 12px',
              borderRadius: 6,
              border: `1px solid ${C.red}40`,
              backgroundColor: C.redDim,
              color: C.red,
              fontSize: 12,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}>
              <span>{evalError}</span>
              <button
                onClick={() => handleEvaluate(selectedKeys)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: C.red,
                  fontSize: 11,
                  cursor: 'pointer',
                  textDecoration: 'underline',
                  padding: 0,
                }}
              >
                Retry
              </button>
            </div>
          )}

          {/* Skeleton cards while loading */}
          {evalLoading && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {selectedKeys.map(k => (
                <EvalSkeleton key={k} label={
                  (scores || MOCK_SCORES).find(s => (s.strategy_key ?? s.key) === k)?.label ?? k
                } />
              ))}
            </div>
          )}

          {/* Real evaluation cards */}
          {!evalLoading && evaluations.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {evaluations.map(card => {
                const currentScores = scores || MOCK_SCORES;
                const matchingScore = currentScores.find(
                  s => (s.strategy_key ?? s.key) === card.strategy_key
                );
                const smaForCard = smaSignal
                  ? { smaShort: smaSignal.sma_8, smaMid: smaSignal.sma_21, smaLong: smaSignal.sma_50 }
                  : null;

                return (
                  <TradeEvaluationCard
                    key={card.strategy_key}
                    card={card}
                    symbol={symbolUpper}
                    currentPrice={prices[symbolUpper]?.price ?? 0}
                    smaData={smaForCard}
                    tradeData={matchingScore?.best_trade ?? null}
                    activeStrategy={card.strategy_key}
                  />
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Strategy-aware ConfigDrawer — opened via Header gear or inline gear button.
          Uses AppContext configOpen so the Header gear icon works on this page. */}
      <ConfigDrawer
        mode="strategy"
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        config={{}}
        onApply={handleConfigApply}
        activeStrategy={activeStrategyKey}
        presets={[]}
        activePresetId={null}
        onPresetSelect={() => {}}
        onSavePreset={() => {}}
        onOverwrite={() => {}}
        onDelete={() => {}}
        onRename={() => {}}
        alignment="mixed"
      />
    </div>
  );
}
