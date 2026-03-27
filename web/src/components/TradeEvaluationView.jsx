/**
 * TradeEvaluationView — OTA-299
 *
 * Parent container that composes all five evaluation sections in order:
 *   A — TradeIdentityHeader   (identity + key metrics, renders immediately)
 *   B — ExitScenarioTable     (exit rows — fetched on mount)
 *   C — OutcomeSummaryCard    (probability / EV metrics — derived from B fetch)
 *   D — ProbabilityMatrix     (Black-Scholes grid — fetched in parallel with B/C)
 *   E — ClaudesRead           (AI verdict — on-demand, triggered by Evaluate button)
 *
 * Props:
 *   spread — object from the analysis engine, with fields:
 *     spread_type:      "bear_put" | "bull_call" | "bull_put" | "bear_call"
 *     long_strike:      number
 *     short_strike:     number
 *     expiration:       "YYYY-MM-DD"  (engine field; also accepts expiry)
 *     net_debit:        number  (positive = debit paid; negative = credit received)
 *     underlying_price: number
 *     iv:               number  (decimal, e.g. 0.28)
 *     max_profit:       number  (dollars per contract, post OTA-283)
 *     max_loss:         number  (dollars per contract, post OTA-283)
 *     breakeven:        number
 *     dte:              number  (optional, computed from expiration if absent)
 *     symbol:           string  (optional, used for probability matrix label)
 *     risk_free_rate:   number  (optional, default 0.05)
 */

import { useState, useEffect } from 'react';
import { mono } from '../styles/tokens';
import { fetchExitScenario, fetchStructuredEvaluation, getProbabilityMatrix } from '../api/client';
import TradeIdentityHeader from './TradeIdentityHeader';
import ExitScenarioTable from './ExitScenarioTable';
import OutcomeSummaryCard from './OutcomeSummaryCard';
import ProbabilityMatrix from './ProbabilityMatrix';
import ClaudesRead from './ClaudesRead';

// ─── Spread type mapping ───────────────────────────────────────────────────────

const SPREAD_TYPE_TO_API = {
  bear_put:  'BEAR_PUT_DEBIT',
  bull_call: 'BULL_CALL_DEBIT',
  bull_put:  'BULL_PUT_CREDIT',
  bear_call: 'BEAR_CALL_CREDIT',
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function dteDaysFromExpiry(expiryStr) {
  if (!expiryStr) return 30;
  try {
    const exp  = new Date(expiryStr);
    const now  = new Date();
    now.setHours(0, 0, 0, 0);
    return Math.max(0, Math.round((exp - now) / 86400000));
  } catch {
    return 30;
  }
}

/** Aggregate exit-row probabilities by zone for OutcomeSummaryCard + TradeVerdictRequest. */
function aggregateProbabilities(rows) {
  let p_max_profit = 0;
  let p_breakeven_or_better = 0;
  let p_max_loss = 0;
  for (const row of rows) {
    if (row.exit_signal === 'TIME EXIT') continue; // exclude synthetic time-exit row
    if (row.zone === 'max_profit') {
      p_max_profit += row.probability;
      p_breakeven_or_better += row.probability;
    } else if (row.zone === 'profit') {
      p_breakeven_or_better += row.probability;
    } else if (row.zone === 'max_loss') {
      p_max_loss += row.probability;
    }
  }
  return { p_max_profit, p_breakeven_or_better, p_max_loss };
}

// ─── Section scaffolding ──────────────────────────────────────────────────────

function SectionHeader({ label }) {
  return (
    <div style={{
      fontSize: 9,
      color: '#555b6e',
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      fontFamily: mono,
      paddingBottom: 6,
      borderBottom: '1px solid rgba(255,255,255,0.06)',
    }}>
      {label}
    </div>
  );
}

function Skeleton({ height = 72 }) {
  return (
    <div style={{
      height,
      borderRadius: 6,
      backgroundColor: 'rgba(255,255,255,0.04)',
    }} />
  );
}

function ErrorBanner({ message }) {
  return (
    <div style={{
      padding: '10px 14px',
      borderRadius: 6,
      backgroundColor: 'rgba(248,81,73,0.08)',
      border: '1px solid rgba(248,81,73,0.25)',
      fontSize: 12,
      color: '#F85149',
      fontFamily: mono,
    }}>
      {message}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function TradeEvaluationView({ spread }) {
  // ── Normalize spread fields ──────────────────────────────────────────────────
  const spreadTypeApi   = SPREAD_TYPE_TO_API[spread?.spread_type] || spread?.spread_type || '';
  const expiry          = spread?.expiry || spread?.expiration || '';
  const entryPrice      = spread?.entry_price ?? Math.abs(spread?.net_debit ?? 0);
  const underlyingPrice = spread?.underlying_price ?? 0;
  const iv              = spread?.iv ?? 0;
  const riskFreeRate    = spread?.risk_free_rate ?? 0.05;
  const maxProfit       = spread?.max_profit ?? 0;  // dollars
  const maxLoss         = spread?.max_loss ?? 0;    // dollars
  const spreadDte       = spread?.dte ?? dteDaysFromExpiry(expiry);

  // ── Exit scenario state (sections B + C) ─────────────────────────────────────
  const [exitLoading, setExitLoading] = useState(false);
  const [exitError,   setExitError]   = useState(null);
  const [exitData,    setExitData]    = useState(null);

  // ── Probability matrix state (section D) ─────────────────────────────────────
  const [matrixLoading, setMatrixLoading] = useState(false);
  const [matrixError,   setMatrixError]   = useState(null);
  const [matrixData,    setMatrixData]    = useState(null);

  // ── Claude verdict state (section E) ─────────────────────────────────────────
  const [claudeLoading, setClaudeLoading] = useState(false);
  const [claudeError,   setClaudeError]   = useState(null);
  const [claudeResult,  setClaudeResult]  = useState(null);

  // ── Fetch on mount / when spread identity changes ────────────────────────────
  useEffect(() => {
    if (!spread) return;
    fetchData();
    setClaudeResult(null);
    setClaudeError(null);
  }, [
    spread?.spread_type,
    spread?.long_strike,
    spread?.short_strike,
    spread?.expiry,
    spread?.expiration,
  ]);

  async function fetchData() {
    setExitLoading(true);
    setExitError(null);
    setExitData(null);
    setMatrixLoading(true);
    setMatrixError(null);
    setMatrixData(null);

    const [exitResult, matrixResult] = await Promise.allSettled([
      fetchExitScenario({
        spread_type:      spreadTypeApi,
        long_strike:      spread.long_strike,
        short_strike:     spread.short_strike,
        expiry,
        entry_price:      entryPrice,
        underlying_price: underlyingPrice,
        iv,
        risk_free_rate:   riskFreeRate,
      }),
      getProbabilityMatrix({
        symbol:        spread.symbol || '',
        current_price: underlyingPrice,
        iv,
        dte:           spreadDte,
      }),
    ]);

    if (exitResult.status === 'fulfilled') {
      setExitData(exitResult.value);
    } else {
      setExitError(exitResult.reason?.message || 'Failed to load exit scenarios.');
    }
    setExitLoading(false);

    if (matrixResult.status === 'fulfilled') {
      setMatrixData(matrixResult.value);
    } else {
      setMatrixError(matrixResult.reason?.message || 'Failed to load probability matrix.');
    }
    setMatrixLoading(false);
  }

  // ── Evaluate button handler ───────────────────────────────────────────────────
  async function handleEvaluate() {
    if (!exitData) return;
    setClaudeLoading(true);
    setClaudeError(null);
    setClaudeResult(null);

    const { p_max_profit, p_breakeven_or_better, p_max_loss } = aggregateProbabilities(exitData.rows);
    const evPctOfRisk = maxLoss > 0 ? (exitData.total_ev / maxLoss) * 100 : 0;

    try {
      const result = await fetchStructuredEvaluation({
        spread_type:           spreadTypeApi,
        long_strike:           spread.long_strike,
        short_strike:          spread.short_strike,
        expiry,
        entry_price:           entryPrice,
        max_profit:            maxProfit,
        max_loss:              maxLoss,
        breakeven:             exitData.breakeven,
        dte:                   exitData.dte,
        total_ev:              exitData.total_ev,
        ev_pct_of_risk:        evPctOfRisk,
        p_max_profit:          p_max_profit,
        p_breakeven_or_better: p_breakeven_or_better,
        p_max_loss:            p_max_loss,
        iv,
      });
      setClaudeResult(result);
    } catch (err) {
      setClaudeError(err.message || 'Evaluation failed. Please try again.');
    } finally {
      setClaudeLoading(false);
    }
  }

  // ── Derived values for sections ───────────────────────────────────────────────
  const rewardRisk  = maxLoss > 0 ? maxProfit / maxLoss : 0;
  const dte         = exitData?.dte ?? spreadDte;
  const probs       = exitData ? aggregateProbabilities(exitData.rows) : null;
  const evFraction  = maxLoss > 0 && exitData ? exitData.total_ev / maxLoss : null;

  if (!spread) return null;

  return (
    <div style={{
      background: '#0D1117',
      padding: '16px 20px',
      display: 'flex',
      flexDirection: 'column',
      gap: 16,
      fontFamily: mono,
    }}>

      {/* ── A: Trade Identity Header ───────────────────────────────────────── */}
      <TradeIdentityHeader
        spread_type={spreadTypeApi}
        long_strike={spread.long_strike}
        short_strike={spread.short_strike}
        expiry={expiry}
        entry_price={entryPrice}
        entry_price_contract={(entryPrice * 100).toFixed(2)}
        max_profit={maxProfit}
        max_loss={maxLoss}
        breakeven={exitData?.breakeven ?? spread.breakeven}
        dte={dte}
        reward_risk={rewardRisk}
        profit_trigger={exitData?.max_profit_price ?? null}
        stop_trigger={exitData?.max_loss_price ?? null}
        time_exit_date={exitData?.time_exit_date ?? null}
      />

      {/* ── B: Exit Scenario Table ────────────────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <SectionHeader label="Exit Scenario Analysis" />
        {exitLoading && <Skeleton height={180} />}
        {!exitLoading && exitError && <ErrorBanner message={exitError} />}
        {!exitLoading && !exitError && exitData && (
          <ExitScenarioTable rows={exitData.rows} totalEV={exitData.total_ev} />
        )}
      </div>

      {/* ── C: Outcome Summary Card ───────────────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <SectionHeader label="Outcome Summary" />
        {exitLoading && <Skeleton height={100} />}
        {!exitLoading && !exitError && probs && (
          <OutcomeSummaryCard
            p_max_profit={probs.p_max_profit}
            p_breakeven_or_better={probs.p_breakeven_or_better}
            p_max_loss={probs.p_max_loss}
            expected_value={exitData.total_ev}
            ev_pct_of_risk={evFraction}
          />
        )}
      </div>

      {/* ── D: Probability Matrix ─────────────────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <SectionHeader label="Probability Matrix" />
        {matrixLoading && <Skeleton height={200} />}
        {!matrixLoading && matrixError && <ErrorBanner message={matrixError} />}
        {!matrixLoading && !matrixError && matrixData && (
          <ProbabilityMatrix
            matrix={matrixData}
            tradeStructure={{
              spread_type:  spreadTypeApi,
              long_strike:  spread.long_strike,
              short_strike: spread.short_strike,
            }}
            currentPrice={underlyingPrice}
            breakeven={exitData?.breakeven ?? spread.breakeven}
            profitTarget={exitData?.max_profit_price ?? null}
            stopLoss={exitData?.max_loss_price ?? null}
          />
        )}
      </div>

      {/* ── E: Claude's Read ──────────────────────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <SectionHeader label="Claude's Read" />
        <ClaudesRead
          onEvaluate={handleEvaluate}
          loading={claudeLoading}
          error={claudeError}
          result={claudeResult}
        />
      </div>

      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }`}</style>
    </div>
  );
}
