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
