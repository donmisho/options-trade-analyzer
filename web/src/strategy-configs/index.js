/**
 * Strategy Config Registry — maps strategy key → config object.
 *
 * To add a new strategy:
 *   1. Create web/src/strategy-configs/your-strategy.config.js
 *   2. Import and add it here
 *   3. The tab appears in Header and the terminal renders it automatically
 */

import verticalsConfig     from './verticals.config';
import longCallsConfig     from './long-calls.config';
import steadyPaycheckConfig from './steady-paycheck.config';
import weeklyGrindConfig    from './weekly-grind.config';
import trendRiderConfig     from './trend-rider.config';
import lotteryTicketConfig  from './lottery-ticket.config';

export const STRATEGY_CONFIGS = {
  [verticalsConfig.key]:      verticalsConfig,
  [longCallsConfig.key]:      longCallsConfig,
  [steadyPaycheckConfig.key]: steadyPaycheckConfig,
  [weeklyGrindConfig.key]:    weeklyGrindConfig,
  [trendRiderConfig.key]:     trendRiderConfig,
  [lotteryTicketConfig.key]:  lotteryTicketConfig,
};

// Ordered list of scorecard strategies for nav and admin UI.
// Verticals and long_calls are excluded — they have top-level nav items.
export const SCORECARD_STRATEGIES = [
  steadyPaycheckConfig,
  weeklyGrindConfig,
  trendRiderConfig,
  lotteryTicketConfig,
];

// ── short_code uniqueness check (runs at module load) ──────────────────────
const seenShortCodes = new Set();
for (const strat of SCORECARD_STRATEGIES) {
  if (seenShortCodes.has(strat.short_code)) {
    throw new Error(`Duplicate strategy short_code: ${strat.short_code}`);
  }
  seenShortCodes.add(strat.short_code);
}

// ── Derived maps — single source of truth for key ↔ short_code ────────────
export const STRATEGY_KEY_MAP = Object.fromEntries(
  SCORECARD_STRATEGIES.map(s => [s.short_code, s.key])
);
export const SHORT_CODE_MAP = Object.fromEntries(
  SCORECARD_STRATEGIES.map(s => [s.key, s.short_code])
);

/**
 * Reverse lookup: given a spread-type identifier (e.g. 'bull_put_credit'),
 * return the strategy keys whose compatible_structures include it.
 */
export function getStrategiesForStructure(spreadType) {
  return SCORECARD_STRATEGIES
    .filter(cfg => (cfg.compatible_structures || []).includes(spreadType))
    .map(cfg => cfg.key);
}

/**
 * Forward lookup: given a strategy key, return its compatible_structures array.
 */
export function getCompatibleStructures(strategyKey) {
  const cfg = STRATEGY_CONFIGS[strategyKey];
  return cfg?.compatible_structures || [];
}
