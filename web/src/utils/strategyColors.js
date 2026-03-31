/**
 * strategyColors — Strategy abbreviation + color constants.
 *
 * Shared by StrategyPill, advice badges, and any other component
 * that renders strategy identity.
 */

export const STRATEGY_COLORS = {
  steady_paycheck: { abbr: 'SP', bg: 'rgba(245,158,11,0.12)', text: 'var(--amber)', fullName: 'Steady Paycheck' },
  weekly_grind:    { abbr: 'WG', bg: 'rgba(74,222,128,0.12)',  text: 'var(--green)', fullName: 'Weekly Grind' },
  trend_rider:     { abbr: 'TR', bg: 'rgba(96,165,250,0.12)',  text: 'var(--blue)',  fullName: 'Trend Rider' },
  lottery_ticket:  { abbr: 'LT', bg: 'rgba(192,132,252,0.12)', text: 'var(--purple)', fullName: 'Lottery Ticket' },
};

// Reverse lookup: abbr → key
export const ABBR_TO_STRATEGY_KEY = {
  SP: 'steady_paycheck',
  WG: 'weekly_grind',
  TR: 'trend_rider',
  LT: 'lottery_ticket',
};
