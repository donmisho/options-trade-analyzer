/**
 * SecurityDashboard — Per-symbol strategy scorecard page.
 *
 * OTA-152/153: Shows all four strategies scored simultaneously for the active
 * symbol. User selects strategies → Evaluate → structured Claude analysis.
 *
 * Routes: /security-strategies  and  /security-strategies/:symbol
 *
 * Data flow:
 *   URL param :symbol → setActiveSymbol → QuoteBar fetches quote
 *   POST /api/v1/analyze/scorecard → StrategyScorecard receives real scores
 *   POST /api/v1/evaluate/structured → TradeEvaluationCard(s) per strategy
 */

import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { getStrategyScorecard, evaluateStrategies } from '../api/client';
import { STRATEGY_CONFIGS } from '../strategy-configs/index';
import QuoteBar from '../components/QuoteBar';
import StrategyScorecard from '../components/StrategyScorecard';
import TradeEvaluationCard from '../components/TradeEvaluationCard';
import ConfigDrawer from '../components/ConfigDrawer';
import { C, mono } from '../styles/tokens';

// ── Skeleton card shown while evaluation is loading ───────────────────────────
function EvalSkeleton({ label }) {
  return (
    <div style={{
      borderRadius: 8,
      border: `1px solid ${C.border}`,
      backgroundColor: C.card,
      overflow: 'hidden',
    }}>
      <div style={{ height: 36, backgroundColor: C.border, opacity: 0.4 }} />
      <div style={{ padding: '10px 16px', borderBottom: `1px solid ${C.border}` }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: C.textDim, marginBottom: 6 }}>
          {label}
        </div>
        <div style={{ height: 3, borderRadius: 2, backgroundColor: C.border }} />
      </div>
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ height: 14, width: '55%', borderRadius: 3, backgroundColor: C.border }} />
        <div style={{ height: 12, width: '80%', borderRadius: 3, backgroundColor: C.border, opacity: 0.6 }} />
        <div style={{ height: 12, width: '70%', borderRadius: 3, backgroundColor: C.border, opacity: 0.6 }} />
      </div>
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${C.border}` }}>
        <div style={{ height: 10, width: 120, borderRadius: 3, backgroundColor: C.border, marginBottom: 10 }} />
        <div style={{ height: 80, borderRadius: 4, backgroundColor: C.border, opacity: 0.35 }} />
      </div>
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', gap: 7 }}>
        <div style={{ height: 10, width: 90, borderRadius: 3, backgroundColor: C.border, marginBottom: 4 }} />
        <div style={{ height: 11, borderRadius: 3, backgroundColor: C.border, opacity: 0.5 }} />
        <div style={{ height: 11, width: '85%', borderRadius: 3, backgroundColor: C.border, opacity: 0.5 }} />
      </div>
      <div style={{ padding: '14px 16px', display: 'flex', gap: 10 }}>
        <div style={{ width: 110, height: 32, borderRadius: 4, backgroundColor: C.border, opacity: 0.4 }} />
        <div style={{ width: 130, height: 32, borderRadius: 4, backgroundColor: C.border, opacity: 0.4 }} />
      </div>
    </div>
  );
}

export default function SecurityDashboard() {
  const { symbol } = useParams();
  const { activeSymbol, setActiveSymbol, configOpen, setConfigOpen, prices } = useApp();

  const [scores, setScores]             = useState([]);
  const [smaSignal, setSmaSignal]       = useState(null);
  const [loadingScores, setLoadingScores] = useState(false);
  const [error, setError]               = useState(null);
  const [selectedKeys, setSelectedKeys] = useState([]);

  const [evaluating, setEvaluating]     = useState(false);
  const [evalError, setEvalError]       = useState(null);
  const [verdicts, setVerdicts]         = useState([]);

  const symbolUpper = (symbol || activeSymbol || '').toUpperCase();

  // Keep AppContext activeSymbol in sync with URL param
  useEffect(() => {
    if (symbolUpper && symbolUpper !== activeSymbol) {
      setActiveSymbol(symbolUpper);
    }
  }, [symbolUpper]); // eslint-disable-line react-hooks/exhaustive-deps

  // Reset when symbol changes
  useEffect(() => {
    setScores([]);
    setSmaSignal(null);
    setError(null);
    setSelectedKeys([]);
    setVerdicts([]);
    setEvalError(null);
  }, [symbolUpper]);

  // Fetch scorecard when symbol available
  useEffect(() => {
    if (!symbolUpper) return;
    setLoadingScores(true);
    getStrategyScorecard(symbolUpper)
      .then(data => {
        setScores(data.strategies || []);
        setSmaSignal(data.sma_signal || null);
      })
      .catch(err => setError(err.message || 'Failed to load scorecard'))
      .finally(() => setLoadingScores(false));
  }, [symbolUpper]);

  // ConfigDrawer active strategy
  const activeStrategyKey = selectedKeys[0] || scores?.[0]?.key || 'steady-paycheck';
  const activeStrategyCfg = STRATEGY_CONFIGS[activeStrategyKey];
  const hasConfigSchema = !!(activeStrategyCfg?.configSchema?.length);

  async function handleEvaluate(selectedKeys) {
    if (!selectedKeys.length || !symbolUpper) return;
    setEvaluating(true);
    setVerdicts([]);
    setEvalError(null);
    try {
      const data = await evaluateStrategies(symbolUpper, selectedKeys);
      // Sort by score descending
      const sorted = (data.evaluations || []).sort((a, b) => b.score - a.score);
      setVerdicts(sorted);
    } catch (err) {
      setEvalError(err.message || 'Evaluation failed');
    } finally {
      setEvaluating(false);
    }
  }

  const smaAlignment = smaSignal?.alignment;
  const smaForCards = smaSignal
    ? { smaShort: smaSignal.sma_8, smaMid: smaSignal.sma_21, smaLong: smaSignal.sma_50 }
    : null;

  return (
    <div style={{ backgroundColor: C.bg, minHeight: '100%', paddingBottom: 24 }}>

      {/* Quote bar */}
      <QuoteBar symbol={symbolUpper || undefined} smaSignal={smaAlignment || undefined} />

      <div style={{ padding: '20px 20px 0' }}>

        {/* Section header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 14,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              fontSize: 10,
              color: '#8b949e',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
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
            <button
              onClick={() => {
                if (!symbolUpper) return;
                setLoadingScores(true);
                setError(null);
                getStrategyScorecard(symbolUpper)
                  .then(data => { setScores(data.strategies || []); setSmaSignal(data.sma_signal || null); })
                  .catch(err => setError(err.message || 'Failed'))
                  .finally(() => setLoadingScores(false));
              }}
              disabled={loadingScores}
              title="Refresh scorecard"
              style={{
                background: 'none',
                border: `1px solid ${C.border}`,
                color: loadingScores ? '#8b949e' : C.textDim,
                fontSize: 14,
                cursor: loadingScores ? 'default' : 'pointer',
                padding: '3px 8px',
                borderRadius: 5,
              }}
            >
              {loadingScores ? '...' : '\u27f3'}
            </button>

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
                }}
              >
                &#9881;
              </button>
            )}
          </div>
        </div>

        {/* Error banner */}
        {error && !loadingScores && (
          <div style={{
            marginBottom: 12,
            padding: '8px 12px',
            borderRadius: 6,
            border: `1px solid rgba(248,113,113,0.4)`,
            backgroundColor: 'rgba(248,113,113,0.08)',
            color: '#f87171',
            fontSize: 12,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}>
            <span>{error}</span>
            <button
              onClick={() => { setError(null); }}
              style={{ background: 'none', border: 'none', color: '#f87171', fontSize: 11, cursor: 'pointer', padding: 0 }}
            >
              ✕
            </button>
          </div>
        )}

        {/* Strategy Scorecard */}
        <StrategyScorecard
          scores={loadingScores ? [] : scores}
          selectedKeys={selectedKeys}
          onSelectionChange={setSelectedKeys}
          onEvaluate={handleEvaluate}
          loading={loadingScores}
        />
      </div>

      {/* Evaluation results */}
      {(evaluating || evalError || verdicts.length > 0) && (
        <div style={{ padding: '20px 20px 0' }}>

          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 14,
          }}>
            <span style={{
              fontSize: 10,
              color: '#8b949e',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
            }}>
              Evaluation Results
            </span>
            {verdicts.length > 0 && !evaluating && (
              <button
                onClick={() => { setVerdicts([]); setEvalError(null); }}
                style={{ background: 'none', border: 'none', color: '#8b949e', fontSize: 11, cursor: 'pointer', padding: 0, textDecoration: 'underline' }}
              >
                Clear
              </button>
            )}
          </div>

          {evalError && !evaluating && (
            <div style={{
              marginBottom: 16,
              padding: '8px 12px',
              borderRadius: 6,
              border: `1px solid rgba(248,113,113,0.4)`,
              backgroundColor: 'rgba(248,113,113,0.08)',
              color: '#f87171',
              fontSize: 12,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}>
              <span>{evalError}</span>
              <button
                onClick={() => handleEvaluate(selectedKeys)}
                style={{ background: 'none', border: 'none', color: '#f87171', fontSize: 11, cursor: 'pointer', textDecoration: 'underline', padding: 0 }}
              >
                Retry
              </button>
            </div>
          )}

          {evaluating && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {selectedKeys.map(k => (
                <EvalSkeleton key={k} label={scores.find(s => (s.strategy_key ?? s.key) === k)?.label ?? k} />
              ))}
            </div>
          )}

          {!evaluating && verdicts.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {verdicts.map(card => {
                const matchingScore = scores.find(s => (s.strategy_key ?? s.key) === card.strategy_key);
                return (
                  <TradeEvaluationCard
                    key={card.strategy_key}
                    card={card}
                    symbol={symbolUpper}
                    currentPrice={prices[symbolUpper]?.price ?? 0}
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

      <ConfigDrawer
        mode="strategy"
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        config={{}}
        onApply={() => setConfigOpen(false)}
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
