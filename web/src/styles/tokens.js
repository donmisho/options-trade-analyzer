/**
 * Design Tokens — Single source of truth for colors, fonts, and shared constants.
 *
 * WHY a separate file: Every component in the prototypes duplicated the same
 * color object (C) and font variables. By extracting them here, changing a color
 * changes it everywhere. This also makes it easy to add a light theme later —
 * you'd just swap which token set gets exported.
 */

export const C = {
  // Backgrounds
  bg: "#0c0e14",
  surface: "#141722",
  surfaceAlt: "#1a1e2c",
  card: "#181c28",
  cardHover: "#1e2333",

  // Borders
  border: "#252a3a",
  borderFocus: "#4f8ef7",
  borderSubtle: "#1e2230",

  // Text
  text: "#e4e7ef",
  textDim: "#8b90a0",
  textMuted: "#555b6e",

  // Accent / Brand
  accent: "#4f8ef7",
  accentDim: "#3460b8",
  accentGlow: "#4f8ef720",

  // Semantic
  green: "#26a69a",
  greenDim: "#0d3320",
  greenBg: "#0a1f18",
  red: "#ef5350",
  redDim: "#2d0f0f",
  redBg: "#1f0a0a",
  amber: "#f59e0b",
  amberDim: "#3d2800",
  amberBg: "#1f1a0a",
  purple: "#a855f7",
  pink: "#ec4899",

  // Overlay
  overlay: "rgba(0,0,0,0.55)",

  // SMA chart colors
  smaCyan: "#00bcd4",
  smaOrange: "#ff9800",
  smaRed: "#e8837c",
  candleGreen: "#26a69a",
  candleRed: "#ef5350",

  // Verdict — WAIT_FOR_EARNINGS (burnt orange)
  verdictWaitEarnings: "#e67e22",

  // Claude / AI branding
  claude: "#d97706",
  claudeDim: "#1c1408",
  claudeBorder: "#d9770625",
  claudeAccent: "#f59e0b",
};

export const mono = "'IBM Plex Mono', monospace";

// Scoring category colors (used in ConfigDrawer and FormulaBreakdown)
export const WEIGHT_COLORS = {
  expected_value: "#4f8ef7",
  reward_risk: "#26a69a",
  probability: "#f59e0b",
  liquidity: "#a855f7",
  theta_efficiency: "#ec4899",
};

export const WEIGHT_LABELS = {
  expected_value: "Expected Value",
  reward_risk: "Reward : Risk",
  probability: "Probability",
  liquidity: "Liquidity",
  theta_efficiency: "Theta Efficiency",
};

// Default analysis presets (used by ConfigDrawer)
export const DEFAULT_PRESETS = [
  {
    id: "balanced", name: "Balanced", icon: "⚖️", builtIn: true,
    desc: "Default — good all-around",
    weights: { expected_value: 0.35, reward_risk: 0.25, probability: 0.20, liquidity: 0.15, theta_efficiency: 0.05 },
    dte: { min: 14, max: 45 },
    strikes: { range_pct: 10, min_open_interest: 10, min_volume: 1 },
    spreads: { min_width: 1, max_width: 10 },
    risk: { max_risk_per_trade: 500, profit_target_pct: 50, stop_loss_pct: 100 },
    systemVars: { exit_warning_pct: 67, exit_scale_out_pct: 160, exit_underlying_stop_pct: 1.5, exit_time_stop_days: 10, min_reward_risk: 0.5, min_ev_threshold: 0, pip_rr_green: 1.5, pip_rr_amber: 1.0, pip_prob_green: 0.55, pip_prob_amber: 0.45, pip_score_green: 0.65, pip_score_amber: 0.45, pip_delta_lo: 0.30, pip_delta_hi: 0.65, pip_iv_green: 30, pip_iv_amber: 50, pip_runway_green: 30, pip_runway_amber: 15 },
  },
  {
    id: "aggressive", name: "Aggressive", icon: "🔥", builtIn: true,
    desc: "High EV + reward",
    weights: { expected_value: 0.45, reward_risk: 0.30, probability: 0.10, liquidity: 0.10, theta_efficiency: 0.05 },
    dte: { min: 7, max: 30 },
    strikes: { range_pct: 15, min_open_interest: 5, min_volume: 1 },
    spreads: { min_width: 2, max_width: 15 },
    risk: { max_risk_per_trade: 1000, profit_target_pct: 70, stop_loss_pct: 100 },
    systemVars: { exit_warning_pct: 60, exit_scale_out_pct: 175, exit_underlying_stop_pct: 2.0, exit_time_stop_days: 7, min_reward_risk: 0.5, min_ev_threshold: 0.25, pip_rr_green: 2.0, pip_rr_amber: 1.5, pip_prob_green: 0.45, pip_prob_amber: 0.35, pip_score_green: 0.60, pip_score_amber: 0.40, pip_delta_lo: 0.20, pip_delta_hi: 0.75, pip_iv_green: 40, pip_iv_amber: 65, pip_runway_green: 21, pip_runway_amber: 10 },
  },
  {
    id: "conservative", name: "Conservative", icon: "🛡️", builtIn: true,
    desc: "High probability",
    weights: { expected_value: 0.20, reward_risk: 0.15, probability: 0.40, liquidity: 0.20, theta_efficiency: 0.05 },
    dte: { min: 21, max: 60 },
    strikes: { range_pct: 8, min_open_interest: 50, min_volume: 5 },
    spreads: { min_width: 1, max_width: 5 },
    risk: { max_risk_per_trade: 300, profit_target_pct: 40, stop_loss_pct: 80 },
    systemVars: { exit_warning_pct: 70, exit_scale_out_pct: 140, exit_underlying_stop_pct: 1.0, exit_time_stop_days: 14, min_reward_risk: 0.75, min_ev_threshold: 0, pip_rr_green: 1.2, pip_rr_amber: 0.8, pip_prob_green: 0.65, pip_prob_amber: 0.55, pip_score_green: 0.70, pip_score_amber: 0.50, pip_delta_lo: 0.35, pip_delta_hi: 0.55, pip_iv_green: 25, pip_iv_amber: 40, pip_runway_green: 45, pip_runway_amber: 21 },
  },
  {
    id: "theta_gang", name: "Theta Gang", icon: "⏳", builtIn: true,
    desc: "Max theta, short DTE",
    weights: { expected_value: 0.20, reward_risk: 0.15, probability: 0.25, liquidity: 0.15, theta_efficiency: 0.25 },
    dte: { min: 7, max: 21 },
    strikes: { range_pct: 8, min_open_interest: 20, min_volume: 5 },
    spreads: { min_width: 1, max_width: 5 },
    risk: { max_risk_per_trade: 400, profit_target_pct: 50, stop_loss_pct: 100 },
    systemVars: { exit_warning_pct: 67, exit_scale_out_pct: 150, exit_underlying_stop_pct: 1.5, exit_time_stop_days: 7, min_reward_risk: 0.3, min_ev_threshold: 0, pip_rr_green: 0.5, pip_rr_amber: 0.3, pip_prob_green: 0.70, pip_prob_amber: 0.60, pip_score_green: 0.65, pip_score_amber: 0.45, pip_delta_lo: 0.25, pip_delta_hi: 0.50, pip_iv_green: 35, pip_iv_amber: 55, pip_runway_green: 21, pip_runway_amber: 10 },
  },
];
