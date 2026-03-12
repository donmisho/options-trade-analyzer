/**
 * Strategy Config Registry — maps strategy key → config object.
 *
 * To add a new strategy:
 *   1. Create web/src/strategy-configs/your-strategy.config.js
 *   2. Import and add it here
 *   3. The tab appears in Header and the terminal renders it automatically
 */

import verticalsConfig from './verticals.config';
import longCallsConfig from './long-calls.config';

export const STRATEGY_CONFIGS = {
  [verticalsConfig.key]:  verticalsConfig,
  [longCallsConfig.key]:  longCallsConfig,
};
