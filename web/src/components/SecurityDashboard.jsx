/**
 * SecurityDashboard — Per-symbol strategy scorecard component.
 *
 * OTA-152 (Phase 2.9 Stream B): Composes QuoteBar + StrategyScorecard +
 * placeholder div for TradeEvaluationCards. Uses mock scores until the
 * wiring session connects it to live API endpoints.
 *
 * Do NOT wire to a live API here — wiring happens in the next session.
 * Do NOT modify SecurityStrategiesPage.jsx to import this component yet.
 */

import { useState } from 'react';
import PropTypes from 'prop-types';
import QuoteBar from './QuoteBar';
import StrategyScorecard from './StrategyScorecard';
import { C, mono } from '../styles/tokens';

// ── Mock scores — used until wiring session ────────────────────────────────
// Shape matches StrategyScorecard's `scores` prop.
const MOCK_SCORES = [
  { key: 'steady-paycheck', label: 'Steady Paycheck', score: 72.50, signal_summary: '30-45 DTE credit spread · income objective' },
  { key: 'weekly-grind',    label: 'Weekly Grind',    score: 58.00, signal_summary: '7-14 DTE credit spread · theta efficiency' },
  { key: 'trend-rider',     label: 'Trend Rider',     score: 41.25, signal_summary: '30-60 DTE long call · directional' },
  { key: 'lottery-ticket',  label: 'Lottery Ticket',  score: 18.00, signal_summary: '1-7 DTE deep OTM · asymmetric payout' },
];

export default function SecurityDashboard({ symbol }) {
  const [selectedKeys, setSelectedKeys] = useState([]);

  return (
    <div style={{ backgroundColor: C.bg, minHeight: '100%', paddingBottom: 32 }}>

      {/* 1 — QuoteBar */}
      <QuoteBar symbol={symbol || undefined} />

      {/* 2 — Strategy Scorecard */}
      <div style={{ padding: '16px 16px 0' }}>
        <div style={{
          fontSize: 10,
          color: C.textMuted,
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          marginBottom: 12,
          fontFamily: mono,
        }}>
          Strategy Scorecard
        </div>

        <StrategyScorecard
          symbol={symbol}
          scores={MOCK_SCORES}
          selectedKeys={selectedKeys}
          onSelectionChange={setSelectedKeys}
          onEvaluate={() => {}}
          loading={false}
        />
      </div>

      {/* 3 — TradeEvaluationCards placeholder (wired in next session) */}
      <div
        id="trade-evaluation-cards-placeholder"
        style={{ padding: '16px 16px 0' }}
      />
    </div>
  );
}

SecurityDashboard.propTypes = {
  symbol: PropTypes.string,
};
