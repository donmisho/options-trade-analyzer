/**
 * API Client — Talks to the FastAPI backend.
 *
 * WHY this file exists: The React components should never know the URL structure
 * or HTTP details of the backend. They call functions like `evaluateTrade(data)`
 * and get clean responses back. If the backend URL or auth scheme changes, only
 * this file needs updating.
 *
 * NOTE: The backend runs on HTTPS with a self-signed cert (https://127.0.0.1:8000).
 * During development, your browser needs to have accepted that cert. Visit
 * https://127.0.0.1:8000/docs once and click "proceed" to trust it.
 */

// ─── Base URL ─────────────────────────────────────────────────────
// In production, VITE_API_BASE_URL is the App Service URL baked in at build time.
// In local dev, it's empty so the Vite proxy handles /api/* → localhost backend.
const API_BASE = `${import.meta.env.VITE_API_BASE_URL || ''}/api/v1`;

// ─── CSRF token (set by AuthContext after /auth/me) ───────────────
export function setCsrfTokenGlobal(token) {
  window.__OTA_CSRF_TOKEN = token || '';
}

export function getCsrfToken() {
  return window.__OTA_CSRF_TOKEN || '';
}

// ─── Helper: Make authenticated requests ──────────────────────────
// All requests use credentials: 'include' so the ota_session cookie is sent.
// State-changing requests (POST/PATCH/PUT/DELETE) also include the CSRF token.
async function apiFetch(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const method = options.method?.toUpperCase() || 'GET';

  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  if (['POST', 'PATCH', 'PUT', 'DELETE'].includes(method)) {
    const csrf = getCsrfToken();
    if (csrf) headers['X-CSRF-Token'] = csrf;
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      credentials: 'include',
      signal: options.signal,
    });

    if (response.status === 401) {
      if (window.location.pathname !== '/' && !window.__OTA_REDIRECTING) {
        window.__OTA_REDIRECTING = true;
        // Clear startup flag so the next page load re-runs auth check
        // instead of silently skipping startup and hitting 401 again.
        try { sessionStorage.removeItem('ota_startup_complete'); } catch {}
        window.location.href = '/';
      }
      throw new Error("Session expired");
    }

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      const detail = errorBody.detail;
      const message = Array.isArray(detail)
        ? `Validation error: ${detail.map(d => d.msg || JSON.stringify(d)).join('; ')}`
        : (detail || `API error: ${response.status}`);
      throw new Error(message);
    }

    return await response.json();
  } catch (err) {
    if (err.name === "TypeError" && err.message.includes("fetch")) {
      throw new Error(
        import.meta.env.DEV
          ? "Cannot reach backend. Check: uvicorn running on https://127.0.0.1:8000 and Vite dev server running."
          : `Cannot reach backend at ${import.meta.env.VITE_API_BASE_URL}.`
      );
    }
    throw err;
  }
}


// ═══════════════════════════════════════════════════════════════════
// MARKET DATA
// ═══════════════════════════════════════════════════════════════════

export async function getQuote(symbol) {
  return apiFetch(`/market/quote/${symbol.toUpperCase()}`);
}

/**
 * Fetch quotes for multiple symbols in parallel.
 * Returns { SPY: { price, change, change_pct }, QQQ: { ... }, ... }
 */
export async function getQuotes(symbols) {
  const results = {};
  const promises = symbols.map(async (sym) => {
    try {
      const q = await getQuote(sym);
      results[sym] = q;
    } catch {
      results[sym] = null;
    }
  });
  await Promise.all(promises);
  return results;
}

export async function getHistoricalClose(symbol, date) {
  return apiFetch(`/market/history/${symbol.toUpperCase()}?date=${encodeURIComponent(date)}`);
}

export async function getCandles(symbol, rangeDays = 90) {
  return apiFetch(`/market/candles/${symbol.toUpperCase()}?range_days=${rangeDays}`);
}

export async function getOptionChain(symbol, params = {}) {
  const query = new URLSearchParams();
  if (params.min_dte !== undefined) query.set("min_dte", params.min_dte);
  if (params.max_dte !== undefined) query.set("max_dte", params.max_dte);
  if (params.strike_range_pct !== undefined) query.set("strike_range_pct", params.strike_range_pct);
  if (params.option_type) query.set("option_type", params.option_type);
  const qs = query.toString();
  return apiFetch(`/market/chain/${symbol.toUpperCase()}${qs ? `?${qs}` : ""}`);
}


// ═══════════════════════════════════════════════════════════════════
// ANALYSIS ENGINES (Phase 2)
// ═══════════════════════════════════════════════════════════════════

export async function analyzeVerticals(data) {
  return apiFetch("/analyze/verticals", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function analyzeLongCalls({ symbol, max_results = 15, option_types = ["call"], ...extra }) {
  return apiFetch("/analyze/long-calls", {
    method: "POST",
    body: JSON.stringify({ symbol, max_results, option_types, ...extra }),
  });
}

export async function analyzeDirectional(data) {
  return apiFetch("/analyze/directional", {
    method: "POST",
    body: JSON.stringify(data),
  });
}


// ═══════════════════════════════════════════════════════════════════
// TRADE EVALUATION (AI — Ask Claude)
// ═══════════════════════════════════════════════════════════════════

/**
 * Evaluate a trade using the AI provider (Claude via Anthropic or Azure Foundry).
 *
 * @param {Object} tradeData — Matches the POST /evaluate/trade request schema
 * @returns {Object} — { verdict, analysis, exit_levels, pre_screen_flags,
 *                        model_used, provider, input_tokens, output_tokens }
 */
export async function evaluateTrade(tradeData) {
  return apiFetch("/evaluate/trade", {
    method: "POST",
    body: JSON.stringify(tradeData),
  });
}

/**
 * Send a follow-up question about a previous trade evaluation.
 *
 * @param {string} question — The follow-up question text
 * @param {Array} conversationHistory — Prior messages [{ role, content }, ...]
 */
export async function followUpQuestion(question, conversationHistory = []) {
  return apiFetch("/evaluate/follow-up", {
    method: "POST",
    body: JSON.stringify({
      question,
      conversation_history: conversationHistory,
    }),
  });
}

/**
 * Check if the AI evaluation service is healthy.
 * @returns {Object} — { status: "ok", provider: "anthropic"|"foundry" }
 */
export async function checkAiHealth() {
  return apiFetch("/evaluate/health");
}

/**
 * Generic authenticated POST — used by OptionsTerminal strategy configs
 * so the terminal doesn't need to know each strategy's named function.
 */
export async function apiPost(path, data) {
  return apiFetch(path, { method: 'POST', body: JSON.stringify(data) });
}


// ═══════════════════════════════════════════════════════════════════
// STRATEGY SCORECARD (Phase 2.9)
// ═══════════════════════════════════════════════════════════════════

/**
 * Run all strategies against a symbol in one backend call.
 * Returns { symbol, quote, sma_signal, strategies: [{ key, label, score, best_trade, signal_summary }] }
 *
 * @param {string} symbol — Ticker symbol (e.g. 'MSFT')
 * @param {Object} userConfig — Optional strategy config overrides from localStorage
 */
export async function getStrategyScorecard(symbol, userConfig = null) {
  return apiFetch('/analyze/scorecard', {
    method: 'POST',
    body: JSON.stringify({ symbol: symbol.toUpperCase(), user_config: userConfig || undefined }),
  });
}

/** Alias for getStrategyScorecard — used by SecurityDashboard Task 1 spec. */
export const runScorecard = getStrategyScorecard;

/**
 * Compute Black-Scholes probability matrix for a trade.
 * Returns { price_levels, dates, matrix }
 */
export async function getProbabilityMatrix({ symbol, current_price, iv, dte }) {
  return apiFetch('/analyze/probability-matrix', {
    method: 'POST',
    body: JSON.stringify({ symbol, current_price, iv, dte }),
  });
}

/** Alias for getProbabilityMatrix — used by SecurityDashboard Task 1 spec. */
export const computeProbabilityMatrix = getProbabilityMatrix;

/**
 * Evaluate selected strategies for a symbol (OTA-153 spec).
 * Thin convenience wrapper around evaluateStructured for SecurityDashboard use.
 *
 * @param {string} symbol
 * @param {string[]} strategyKeys
 */
export async function evaluateStrategies(symbol, strategyKeys) {
  return apiFetch('/evaluate/structured', {
    method: 'POST',
    body: JSON.stringify({ symbol: symbol.toUpperCase(), strategy_keys: strategyKeys }),
  });
}

/**
 * Run structured Claude evaluation for one or more strategies.
 *
 * @param {Object} data
 *   symbol          — ticker
 *   current_price   — float
 *   iv              — annualized IV as decimal (0.25 = 25%)
 *   sma_alignment   — dict from scorecard sma_signal
 *   strategy_keys   — string[]
 *   trade           — optional pre-populated trade dict (null = Claude picks best)
 *
 * @returns {{ evaluations: TradeEvaluationCard[], evaluated_at: string, agent_run_id: string }}
 */
export async function evaluateStructured(data) {
  return apiFetch('/evaluate/structured', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}


// ═══════════════════════════════════════════════════════════════════
// TRADE EVALUATION — Phase 2.11 (OTA-292 / OTA-297)
// ═══════════════════════════════════════════════════════════════════

/**
 * Compute exit scenario rows for a vertical spread.
 * Pure math — no AI involved.
 * @param {Object} payload — ExitScenarioRequest fields
 * @returns ExitScenarioResponse — { rows, breakeven, max_profit_price, max_loss_price, total_ev, dte, time_exit_date }
 */
export async function fetchExitScenario(payload) {
  return apiFetch('/evaluate/exit-scenario', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Get Claude's structured verdict on a single vertical spread (OTA-297).
 * Accepts pre-computed spread economics from fetchExitScenario.
 * @param {Object} payload — TradeVerdictRequest fields
 * @returns TradeVerdictResponse — { ev_commentary, key_level, iv_context, verdict, verdict_rationale }
 */
export async function fetchStructuredEvaluation(payload) {
  return apiFetch('/evaluate/trade-verdict', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}


// ═══════════════════════════════════════════════════════════════════
// CONFIG
// ═══════════════════════════════════════════════════════════════════

export async function getUserConfig() {
  return apiFetch("/config");
}

export async function updateUserConfig(configData) {
  return apiFetch("/config", {
    method: "PUT",
    body: JSON.stringify(configData),
  });
}
// ═══════════════════════════════════════════════════════════════════
// USER PREFERENCES — Favorites
// ═══════════════════════════════════════════════════════════════════

export async function getFavorites() {
  return apiFetch("/user/favorites");
}

export async function addFavoriteApi(trade) {
  return apiFetch("/user/favorites", {
    method: "POST",
    body: JSON.stringify({
      id: trade.id,
      symbol: trade.symbol,
      label: trade.label || "",
      strategy: trade.strategy || "",
      trade_data: trade,
    }),
  });
}

export async function removeFavoriteApi(tradeId) {
  return apiFetch(`/user/favorites/${encodeURIComponent(tradeId)}`, {
    method: "DELETE",
  });
}


/**
 * Check Schwab OAuth connection status.
 * Used by Header to show connection indicator.
 */
export async function getSchwabStatus(signal) {
  try {
    const data = await apiFetch("/auth/schwab/status", { signal });
    return data;
  } catch {
    return { connected: false, error: "Not available" };
  }
}

export async function getSchwabAuthUrl() {
  const data = await apiFetch("/auth/schwab/get-url");
  return data.authorization_url;
}

export async function getServicesStatus(signal) {
  try {
    const data = await apiFetch("/services/status", { signal });
    return data;
  } catch {
    return { services: [] };
  }
}


// ═══════════════════════════════════════════════════════════════════
// AGENT — Claude Trade Evaluation
// ═══════════════════════════════════════════════════════════════════

/**
 * Stage 1: Batch rank 1-10 trades STRONG / MEDIUM / WEAK.
 * Returns { run_id, rankings: [{trade_id, rank, reason, explore_further}], triage_summary }
 */
export async function triageTrades(trades, marketContext) {
  return apiFetch("/agent/triage", {
    method: "POST",
    body: JSON.stringify({
      symbol: marketContext.symbol,
      underlying_price: marketContext.underlying_price,
      sma_8: marketContext.sma_8,
      sma_21: marketContext.sma_21,
      sma_50: marketContext.sma_50,
      ma_alignment: marketContext.ma_alignment,
      vix: marketContext.vix || null,
      trades,
    }),
  });
}

/**
 * Stage 2: Full single-trade deep dive. Returns verdict + full analysis.
 * exit_levels are pre-calculated here (per SKILL.md formula) so Claude
 * doesn't have to do math.
 */
export async function deepDiveTrade(trade, marketContext, priceTarget, runId, riskConfig) {
  const debit = trade.net_debit || 0;
  const maxProfit = trade.max_profit || 0;
  const dte = trade.dte || 30;
  const price = marketContext.underlying_price;
  const sma8 = marketContext.sma_8;

  // Risk config from user settings — fall back to SKILL.md defaults if not provided
  const riskBudget           = riskConfig?.max_risk_per_trade ?? 500;
  const stopLossPct          = (riskConfig?.stop_loss_pct    ?? 50)  / 100;
  const profitTargetPct      = (riskConfig?.profit_target_pct ?? 75) / 100;

  // System variables — configurable exit level thresholds
  const sv = riskConfig?.systemVars || {};
  const exitWarningPct       = sv.exit_warning_pct          ?? 67;
  const exitScaleOutPct      = sv.exit_scale_out_pct        ?? 160;
  const exitUnderlyingStopPct = sv.exit_underlying_stop_pct ?? 1.5;
  const exitTimeStopDays     = sv.exit_time_stop_days       ?? 10;

  // Exit levels derived from user config + system variables
  const stopLossDebit    = parseFloat((debit * stopLossPct).toFixed(2));
  const warningDebit     = parseFloat((debit * (exitWarningPct / 100)).toFixed(2));
  const scaleOutDebit    = parseFloat((debit * (exitScaleOutPct / 100)).toFixed(2));
  const fullProfitAmount = parseFloat((maxProfit * profitTargetPct).toFixed(2));

  return apiFetch("/agent/deep-dive", {
    method: "POST",
    body: JSON.stringify({
      symbol: trade.symbol,
      current_price: price,
      sma_8: sma8,
      sma_21: marketContext.sma_21,
      sma_50: marketContext.sma_50,
      ma_alignment: marketContext.ma_alignment,
      vix: marketContext.vix || null,
      direction: trade.direction || "Bullish",
      timeframe_days: Math.round(dte),
      price_target: priceTarget ? parseFloat(priceTarget) : null,
      conviction: "Medium",
      spread_type_label: trade.spread_label || trade.spread_type,
      spread_label: trade.spread_label,
      expiration: trade.expiration,
      dte,
      net_debit: debit,
      max_profit: maxProfit,
      reward_risk_ratio: trade.reward_risk_ratio || 0,
      prob_of_profit: trade.prob_of_profit || 0,
      composite_score: trade.composite_score || null,
      risk_budget: riskBudget,
      num_contracts: 1,
      total_cost: debit * 100,
      // Pre-calculated exit levels derived from user risk config
      exit_stop_loss:       stopLossDebit,
      exit_warning:         warningDebit,
      exit_scale_out:       scaleOutDebit,
      exit_full_profit:     fullProfitAmount,
      exit_underlying_stop: parseFloat(Math.min(sma8, price - price * (exitUnderlyingStopPct / 100)).toFixed(2)),
      exit_time_stop:       Math.round(Math.max(0, dte - exitTimeStopDays)),
      system_vars: {
        exit_warning_pct:          exitWarningPct,
        exit_scale_out_pct:        exitScaleOutPct,
        exit_underlying_stop_pct:  exitUnderlyingStopPct,
        exit_time_stop_days:       exitTimeStopDays,
      },
      run_id: runId || null,
    }),
  });
}

/**
 * Stage 3: Contextual follow-up on a prior verdict.
 */
export async function followupTrade(trade, verdict, verdictSummary, question, runId) {
  return apiFetch("/agent/followup", {
    method: "POST",
    body: JSON.stringify({
      trade_key: `${trade.symbol}:${trade.spread_label}:${trade.expiration}`,
      symbol: trade.symbol,
      spread_label: trade.spread_label,
      expiration: trade.expiration,
      verdict,
      verdict_summary: verdictSummary,
      user_question: question,
      run_id: runId || null,
    }),
  });
}

/**
 * List all saved recommendations for a symbol.
 * Returns a Map keyed by trade_key for O(1) lookup in the results table.
 */
export async function listRecommendations(symbol) {
  try {
    const results = await apiFetch(`/agent/recommendations?symbol=${encodeURIComponent(symbol)}`);
    const map = new Map();
    for (const rec of (results || [])) {
      map.set(rec.trade_key, rec);
    }
    return map;
  } catch {
    return new Map();
  }
}

/**
 * Look up a stored recommendation by trade key.
 * Returns null if not found (404 → null).
 */
export async function getRecommendation(tradeKey) {
  try {
    return await apiFetch(`/agent/recommendations/${encodeURIComponent(tradeKey)}`);
  } catch (err) {
    if (err.message?.includes("404") || err.message?.includes("No recommendation")) return null;
    return null;
  }
}

/**
 * Delete a stored recommendation (clear so next deep dive starts fresh).
 */
export async function deleteRecommendation(tradeKey) {
  return apiFetch(`/agent/recommendations/${encodeURIComponent(tradeKey)}`, {
    method: "DELETE",
  });
}


// ═══════════════════════════════════════════════════════════════════
// POSITIONS (Phase 2.10)
// ═══════════════════════════════════════════════════════════════════

/**
 * List positions with composable filters.
 * @param {Object} filters — { status, source, symbol, strategy_key, include_archived } — all optional
 * @returns PositionListResponse — { positions, total, aggregate }
 */
export async function getPositions(filters = {}) {
  const params = new URLSearchParams();
  if (filters.status && filters.status !== 'all') params.set('status', filters.status);
  if (filters.source && filters.source !== 'all') params.set('source', filters.source);
  if (filters.symbol) params.set('symbol', filters.symbol.toUpperCase());
  if (filters.strategy_key && filters.strategy_key !== 'all') params.set('strategy_key', filters.strategy_key);
  if (filters.include_archived) params.set('include_archived', 'true');
  const qs = params.toString();
  return apiFetch(`/positions${qs ? `?${qs}` : ''}`);
}

/**
 * Create a paper-tracked position (source=PAPER, status=FOLLOWING).
 * @param {Object} data — FollowPositionRequest fields
 */
export async function followTrade(data) {
  return apiFetch('/positions/follow', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Create a live position (source=LIVE, status=LIVE).
 * @param {Object} data — TakePositionRequest fields (same shape as follow)
 */
export async function takeTrade(data) {
  return apiFetch('/positions/take', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Close a position and record the outcome.
 * @param {string} positionId — UUID
 * @param {Object} data — { exit_price: float, exit_reason: string }
 */
export async function closePosition(positionId, data) {
  return apiFetch(`/positions/${encodeURIComponent(positionId)}/close`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

/**
 * Return all Claude assessments for a position, newest first.
 * @param {string} positionId — UUID
 * @returns PositionAssessmentResponse[]
 */
export async function getPositionAssessments(positionId) {
  return apiFetch(`/positions/${encodeURIComponent(positionId)}/assessments`);
}

/**
 * Re-evaluate an open position with current market data and Claude.
 * @param {string} positionId — UUID
 * @returns PositionRefreshResponse — { assessment, current_premium, current_pnl, pnl_pct, perf_status }
 */
export async function refreshPosition(positionId) {
  return apiFetch(`/positions/${encodeURIComponent(positionId)}/refresh`, { method: 'POST' });
}

/** Alias for followTrade — POST /api/v1/positions/follow (source=PAPER) */
export const followPosition = followTrade;

/** Alias for takeTrade — POST /api/v1/positions/take (source=LIVE) */
export const takePosition = takeTrade;

/**
 * Ask a follow-up question about a specific trade evaluation.
 * @param {Object} payload — { symbol, trade_data, original_evaluation, question }
 */
export async function evaluateFollowUp(payload) {
  return apiFetch('/evaluate/follow-up', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Archive a position (status → ARCHIVED). No P&L recorded.
 * @param {string} positionId — UUID
 */
export async function archivePosition(positionId) {
  return apiFetch(`/positions/${encodeURIComponent(positionId)}/archive`, { method: 'PATCH' });
}

/**
 * Fetch live pricing + P&L for a batch of positions.
 * @param {string[]} positionIds — array of UUIDs
 * @returns PositionCurrentPrice[]
 */
export async function getPositionCurrentPrices(positionIds) {
  const ids = positionIds.join(',');
  return apiFetch(`/positions/current-prices?position_ids=${encodeURIComponent(ids)}`);
}

/**
 * Fetch symbols that have active (FOLLOWING or LIVE) positions.
 * Used by SymbolSearch to highlight Tier 1 results.
 * @returns [{ symbol, position_count }]
 */
export async function getPositionSymbols() {
  return apiFetch('/positions/symbols');
}

// ─── Static symbol search ─────────────────────────────────────────────────────
// Used as the default searchFn prop for SymbolSearch. Filters a static ticker map
// by prefix match on the query. Extend TICKER_MAP as needed for common symbols.

const TICKER_MAP = {
  AAPL: 'Apple', AMZN: 'Amazon', GOOG: 'Alphabet', GOOGL: 'Alphabet',
  META: 'Meta Platforms', MSFT: 'Microsoft', NVDA: 'NVIDIA', TSLA: 'Tesla',
  AMD: 'Advanced Micro Devices', NFLX: 'Netflix', COIN: 'Coinbase',
  CRM: 'Salesforce', PYPL: 'PayPal', PLTR: 'Palantir', SOFI: 'SoFi',
  RIVN: 'Rivian', INTC: 'Intel', DIS: 'Disney', V: 'Visa', MA: 'Mastercard',
  JPM: 'JPMorgan Chase', BAC: 'Bank of America', GS: 'Goldman Sachs',
  MS: 'Morgan Stanley', WFC: 'Wells Fargo', C: 'Citigroup',
  SPY: 'S&P 500 ETF', QQQ: 'Nasdaq 100 ETF', IWM: 'Russell 2000 ETF',
  TLT: 'Treasury Bond ETF', GLD: 'Gold ETF', SLV: 'Silver ETF',
  XLF: 'Financial ETF', XLE: 'Energy ETF', XLK: 'Technology ETF',
  XLV: 'Healthcare ETF', XLI: 'Industrial ETF', XLP: 'Consumer Staples ETF',
  T: 'AT&T', VZ: 'Verizon', TMUS: 'T-Mobile',
  CVX: 'Chevron', XOM: 'ExxonMobil', COP: 'ConocoPhillips',
  LLY: 'Eli Lilly', JNJ: 'Johnson & Johnson', PFE: 'Pfizer',
  ABBV: 'AbbVie', MRK: 'Merck', UNH: 'UnitedHealth',
  AMGN: 'Amgen', GILD: 'Gilead Sciences', BIIB: 'Biogen',
  ORCL: 'Oracle', IBM: 'IBM', HPQ: 'HP', CSCO: 'Cisco',
  QCOM: 'Qualcomm', TXN: 'Texas Instruments', MU: 'Micron',
  AVGO: 'Broadcom', AMAT: 'Applied Materials', LRCX: 'Lam Research',
  COST: 'Costco', WMT: 'Walmart', TGT: 'Target', HD: 'Home Depot',
  LOW: 'Lowe\'s', NKE: 'Nike', SBUX: 'Starbucks', MCD: 'McDonald\'s',
  BABA: 'Alibaba', NIO: 'NIO', SPOT: 'Spotify', UBER: 'Uber',
  LYFT: 'Lyft', SNAP: 'Snap', PINS: 'Pinterest', TWTR: 'Twitter',
  GEV: 'GE Vernova', GE: 'General Electric', BA: 'Boeing', CAT: 'Caterpillar',
  DE: 'Deere & Company', MMM: '3M', HON: 'Honeywell', RTX: 'Raytheon',
  LMT: 'Lockheed Martin', NOC: 'Northrop Grumman',
  BRK: 'Berkshire Hathaway', BRKB: 'Berkshire Hathaway B',
  MSTR: 'MicroStrategy', MARA: 'Marathon Digital', RIOT: 'Riot Platforms',
};

/**
 * Search symbols by prefix using the static TICKER_MAP.
 * Injected as the `searchFn` prop for SymbolSearch on analysis pages.
 * @param {string} query
 * @returns Promise<[{ symbol, companyName }]>
 */
export async function searchSymbolsStatic(query) {
  const q = query.toUpperCase().trim();
  if (!q) return [];
  return Object.entries(TICKER_MAP)
    .filter(([sym]) => sym.startsWith(q))
    .map(([symbol, companyName]) => ({ symbol, companyName }))
    .slice(0, 12);
}


/**
 * Search instruments via the backend (Schwab-backed), with automatic
 * fallback to the static TICKER_MAP if the API is unavailable.
 * Injected as the `searchFn` prop for SymbolSearch on analysis pages.
 * @param {string} query
 * @returns Promise<[{ symbol, companyName }]>
 */
export async function searchInstruments(query) {
  const q = query.toUpperCase().trim();
  if (!q) return [];

  try {
    const data = await apiFetch(`/market/instruments?symbol=${encodeURIComponent(q)}`);
    const instruments = data?.instruments || [];
    if (instruments.length > 0) {
      return instruments.map(inst => ({ symbol: inst.symbol, companyName: inst.name }));
    }
  } catch (_) {
    // fall through to static
  }

  // Fallback: static list
  return Object.entries(TICKER_MAP)
    .filter(([sym]) => sym.startsWith(q))
    .map(([symbol, companyName]) => ({ symbol, companyName }))
    .slice(0, 12);
}


// ═══════════════════════════════════════════════════════════════════
// INSIGHTS (Phase 3.6)
// ═══════════════════════════════════════════════════════════════════

/**
 * Fetch active insights for a domain.
 * @param {string} domain — 'options' | 'manufacturing' etc. (default 'options')
 * @param {string} status — 'ACTIVE' | 'DISMISSED' | 'ACTED_ON' (default 'ACTIVE')
 * @returns InsightResponse[]
 */
export async function getInsights(domain = 'options', status = 'ACTIVE') {
  return apiFetch(`/insights?domain=${encodeURIComponent(domain)}&status=${encodeURIComponent(status)}`);
}

/**
 * Dismiss an insight. Removes it from the active feed.
 * @param {string} insightId — UUID
 */
export async function dismissInsight(insightId) {
  return apiFetch(`/insights/${encodeURIComponent(insightId)}/dismiss`, {
    method: 'PATCH',
  });
}

/**
 * Mark an insight as acted on (user navigated to the entity).
 * @param {string} insightId — UUID
 */
export async function actOnInsight(insightId) {
  return apiFetch(`/insights/${encodeURIComponent(insightId)}/act`, {
    method: 'PATCH',
  });
}


// ═══════════════════════════════════════════════════════════════════
// HEALTH (OTA-441)
// ═══════════════════════════════════════════════════════════════════

export async function getDetailedHealth() {
  return apiFetch('/health/detailed');
}

// ═══════════════════════════════════════════════════════════════════
// NAMED WATCHLISTS (OTA-444 / OTA-445 / OTA-446)
// ═══════════════════════════════════════════════════════════════════

/** Return all watchlists for the current user. Creates default on first call. */
export async function getWatchlists() {
  return apiFetch('/watchlists');
}

/** Create a new watchlist. @returns {id, name, is_default, symbol_count} */
export async function createWatchlist(name) {
  return apiFetch('/watchlists', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

/** Rename a watchlist. @returns {id, name, updated_at} */
export async function renameWatchlist(id, name) {
  return apiFetch(`/watchlists/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify({ name }),
  });
}

/** Delete a watchlist and its symbols. Cannot delete default watchlist. */
export async function deleteWatchlist(id) {
  return apiFetch(`/watchlists/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
}

/** List symbols in a watchlist. @returns [{symbol, added_at}] */
export async function getWatchlistSymbols(id) {
  return apiFetch(`/watchlists/${encodeURIComponent(id)}/symbols`);
}

/** Add a symbol to a named watchlist. Validates via Schwab. */
export async function addSymbolToWatchlist(id, symbol) {
  return apiFetch(`/watchlists/${encodeURIComponent(id)}/symbols`, {
    method: 'POST',
    body: JSON.stringify({ symbol: symbol.toUpperCase() }),
  });
}

/** Remove a symbol from a named watchlist. */
export async function removeSymbolFromWatchlist(id, symbol) {
  return apiFetch(`/watchlists/${encodeURIComponent(id)}/symbols/${encodeURIComponent(symbol.toUpperCase())}`, {
    method: 'DELETE',
  });
}

/**
 * Get available scan sources for Security Strategies page.
 * @returns { watchlists: [{id, name, is_default, symbol_count}], builtin: [{id, name, symbol_count}] }
 */
export async function getWatchlistSources() {
  return apiFetch('/watchlists/sources');
}


// ═══════════════════════════════════════════════════════════════════
// DASHBOARD (Phase 2.3)
// ═══════════════════════════════════════════════════════════════════

export async function getDashboardLayout() {
  return apiFetch('/dashboard');
}

export async function saveDashboardLayout(payload) {
  return apiFetch('/dashboard', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function getDashboardMedia(widgetId) {
  return apiFetch(`/dashboard/media/${encodeURIComponent(widgetId)}`);
}


// ═══════════════════════════════════════════════════════════════════
// CHANGELOG (OTA-602)
// ═══════════════════════════════════════════════════════════════════

/**
 * Fetch deploy history in reverse-chronological order.
 * @param {Object} opts — { limit?: number, environment?: 'dev'|'prod' }
 * @returns DeployLogEntry[]
 */
export async function getChangeLog({ limit = 50, environment } = {}) {
  const params = new URLSearchParams();
  if (limit) params.set('limit', limit);
  if (environment) params.set('environment', environment);
  const qs = params.toString();
  return apiFetch(`/changelog${qs ? `?${qs}` : ''}`);
}
