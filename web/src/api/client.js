/**
 * API Client — talks to the FastAPI backend
 * 
 * WHY THIS EXISTS:
 * Every React component that needs data calls methods on this client
 * instead of doing raw fetch() calls. This centralizes:
 *   - The base URL (localhost:8000 in dev, your domain in production)
 *   - Auth token management (stored in localStorage after login)
 *   - Error handling (consistent error messages across the app)
 *   - Request/response transformation
 * 
 * HOW TO USE:
 *   import api from '../api/client';
 *   const result = await api.analyzeVerticals({ symbol: 'QQQ' });
 */

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const API_PREFIX = '/api/v1';

// ─── Token Management ────────────────────────────────────────────

let authToken = null;

/**
 * Set the JWT token after login. Stored in memory (not localStorage)
 * for security. You'd call this after the login API returns a token.
 */
export function setAuthToken(token) {
  authToken = token;
}

export function getAuthToken() {
  return authToken;
}

export function clearAuthToken() {
  authToken = null;
}

// ─── Core Request Function ───────────────────────────────────────

/**
 * Make an authenticated request to the API.
 * 
 * WHY async/await: Every API call is asynchronous because it's
 * waiting for the network. async/await lets us write code that
 * LOOKS synchronous but doesn't block the browser.
 * 
 * WHY we throw on non-200: React components can use try/catch
 * to handle errors consistently. The error object includes both
 * the HTTP status and the API's error message.
 */
async function request(method, path, body = null) {
  const url = `${BASE_URL}${API_PREFIX}${path}`;
  
  const headers = {
    'Content-Type': 'application/json',
  };
  
  // Add auth token if we have one
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }
  
  const options = {
    method,
    headers,
  };
  
  if (body && method !== 'GET') {
    options.body = JSON.stringify(body);
  }
  
  try {
    const response = await fetch(url, options);
    
    // Parse JSON response
    const data = await response.json().catch(() => null);
    
    if (!response.ok) {
      // Build a useful error message
      const message = data?.detail || `API error: ${response.status}`;
      const error = new Error(message);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    
    return data;
  } catch (err) {
    // Network errors (server down, CORS blocked, etc.)
    if (!err.status) {
      err.message = `Network error: ${err.message}. Is the API server running?`;
    }
    throw err;
  }
}

// ─── API Methods ─────────────────────────────────────────────────
// Each method maps to one FastAPI endpoint. The React components
// call these instead of knowing about URLs or HTTP methods.

const api = {
  
  // ── Auth ──────────────────────────────────────────────────────
  
  async login(username, password) {
    const data = await request('POST', '/auth/login', { username, password });
    if (data.access_token) {
      setAuthToken(data.access_token);
    }
    return data;
  },
  
  async register(username, email, password, inviteCode) {
    return request('POST', '/auth/register', {
      username, email, password, invite_code: inviteCode,
    });
  },
  
  // ── Market Data ──────────────────────────────────────────────
  
  async getQuote(symbol) {
    return request('GET', `/market/quote/${symbol.toUpperCase()}`);
  },
  
  async getChain(symbol, options = {}) {
    const params = new URLSearchParams({
      min_dte: options.minDte || 14,
      max_dte: options.maxDte || 45,
      strike_range_pct: options.strikeRange || 10,
      ...(options.optionType && { option_type: options.optionType }),
    });
    return request('GET', `/market/chain/${symbol.toUpperCase()}?${params}`);
  },
  
  async getExpirations(symbol) {
    return request('GET', `/market/expirations/${symbol.toUpperCase()}`);
  },
  
  // ── Analysis (Phase 2) ───────────────────────────────────────
  
  /**
   * Score and rank vertical spreads.
   * 
   * @param {Object} params
   * @param {string} params.symbol - Ticker to analyze (e.g., "QQQ")
   * @param {string[]} params.spreadTypes - ["bull_call", "bear_put"]
   * @param {number} params.maxResults - Max results to return
   * @param {Object} params.weights - Optional scoring weight overrides
   * @returns {Object} { symbol, underlying_price, total_valid, spreads[] }
   */
  async analyzeVerticals(params) {
    return request('POST', '/analyze/verticals', {
      symbol: params.symbol,
      spread_types: params.spreadTypes || ['bull_call', 'bear_put'],
      max_results: params.maxResults || 20,
      min_dte: params.minDte || 14,
      max_dte: params.maxDte || 60,
      strike_range_pct: params.strikeRange || 10,
      ...(params.weights && {
        ev_weight: params.weights.ev,
        rr_weight: params.weights.rr,
        prob_weight: params.weights.prob,
        liq_weight: params.weights.liq,
        theta_weight: params.weights.theta,
      }),
    });
  },
  
  /**
   * Score and rank long call candidates.
   */
  async analyzeLongCalls(params) {
    return request('POST', '/analyze/long-calls', {
      symbol: params.symbol,
      max_results: params.maxResults || 15,
      min_dte: params.minDte || 14,
      max_dte: params.maxDte || 60,
      strike_range_pct: params.strikeRange || 10,
      max_premium: params.maxPremium || 1500,
    });
  },
  
  /**
   * Compare strategies for a directional thesis.
   * 
   * @param {Object} thesis
   * @param {string} thesis.symbol
   * @param {string} thesis.direction - "bullish" or "bearish"
   * @param {number} thesis.targetPrice
   * @param {number} thesis.timeframeDays
   * @param {number} thesis.riskBudget
   */
  async analyzeDirectional(thesis) {
    return request('POST', '/analyze/directional', {
      symbol: thesis.symbol,
      direction: thesis.direction,
      target_price: thesis.targetPrice,
      timeframe_days: thesis.timeframeDays || 30,
      risk_budget: thesis.riskBudget,
      min_dte: thesis.minDte || 14,
      max_dte: thesis.maxDte || 90,
      strike_range_pct: thesis.strikeRange || 15,
    });
  },
  
  // ── Config ───────────────────────────────────────────────────
  
  async getConfig() {
    return request('GET', '/config');
  },
  
  async updateConfig(config) {
    return request('PUT', '/config', config);
  },
  
  // ── Health ───────────────────────────────────────────────────
  
  async healthCheck() {
    try {
      const data = await request('GET', '/../health');
      return { connected: true, ...data };
    } catch {
      return { connected: false };
    }
  },
};

export default api;
