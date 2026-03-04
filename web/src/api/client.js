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

// ─── Helper: Make authenticated requests ──────────────────────────
async function apiFetch(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const token = localStorage.getItem("ota_token");

  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  try {
    const response = await fetch(url, { ...options, headers });

    // 401 with an existing token means the session expired → kick back to login.
    // Don't hard-reload if already on /login — that would kill an in-flight MSAL popup.
    if (response.status === 401 && localStorage.getItem("ota_token")) {
      localStorage.removeItem("ota_token");
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
      throw new Error("Session expired");
    }

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      const message = errorBody.detail || `API error: ${response.status}`;
      throw new Error(message);
    }

    return await response.json();
  } catch (err) {
    if (err.name === "TypeError" && err.message.includes("fetch")) {
      throw new Error("Cannot reach the backend. Is it running on https://127.0.0.1:8000?");
    }
    throw err;
  }
}


// ═══════════════════════════════════════════════════════════════════
// AUTH — Entra ID token exchange
// ═══════════════════════════════════════════════════════════════════

/**
 * Exchange a Microsoft Entra id_token for our app JWT.
 * Called by LoginPage after a successful MSAL loginPopup.
 * No Authorization header needed — this is the login endpoint.
 */
export async function entraLogin(entraToken) {
  return apiFetch("/auth/entra/token", {
    method: "POST",
    body: JSON.stringify({ entra_token: entraToken }),
  });
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

export async function analyzeLongCalls({ symbol, max_results = 15, option_types = ["call"] }) {
  return apiFetch("/analyze/long-calls", {
    method: "POST",
    body: JSON.stringify({ symbol, max_results, option_types }),
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
// USER PREFERENCES — Watchlist & Favorites
// ═══════════════════════════════════════════════════════════════════

export async function getWatchlist() {
  return apiFetch("/user/watchlist");
}

export async function saveWatchlist(symbols) {
  return apiFetch("/user/watchlist", {
    method: "PUT",
    body: JSON.stringify({ symbols }),
  });
}

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
export async function getSchwabStatus() {
  try {
    const data = await apiFetch("/auth/schwab/status");
    return data;
  } catch {
    return { connected: false, error: "Not available" };
  }
}

export async function getSchwabAuthUrl() {
  const data = await apiFetch("/auth/schwab/get-url");
  return data.authorization_url;
}
