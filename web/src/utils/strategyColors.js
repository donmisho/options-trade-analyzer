/**
 * strategyColors — Strategy abbreviation + color constants.
 *
 * Derived from SCORECARD_STRATEGIES registry — no hardcoded strategy data.
 * Shared by StrategyPill, advice badges, and any other component
 * that renders strategy identity.
 */

import { SCORECARD_STRATEGIES } from '../strategy-configs/index';

// Keyed by underscore form (steady_paycheck) for consumer compatibility
export const STRATEGY_COLORS = Object.fromEntries(
  SCORECARD_STRATEGIES.map(cfg => [
    cfg.key.replace(/-/g, '_'),
    { abbr: cfg.short_code, bg: cfg.color_bg, text: cfg.color_text, fullName: cfg.label },
  ])
);

// Reverse lookup: abbr → underscore key
export const ABBR_TO_STRATEGY_KEY = Object.fromEntries(
  SCORECARD_STRATEGIES.map(cfg => [cfg.short_code, cfg.key.replace(/-/g, '_')])
);
