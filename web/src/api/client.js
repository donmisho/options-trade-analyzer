/**
 * API Client — All backend communication goes through here.
 *
 * WHY a centralized client?
 * Every API call needs the same base URL, auth token, and error
 * handling. Instead of repeating that in every component, we
 * configure it once here. If the base URL changes (local → Azure),
 * you update ONE line.
 *
 * WHY axios?
 * It auto-parses JSON, supports interceptors for auth tokens,
 * and has cleaner error handling than raw fetch(). The request/
 * response interceptors below will be important when we add
 * JWT auth tokens in a later phase.
 */

import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1',
  timeout: 30000, // 30s — option chains can be large
  headers: {
    'Content-Type': 'application/json',
  },
});

// ─── Request interceptor: attach auth token ───
// (Currently a placeholder — will be wired up in Phase 3 when
//  we add proper login flow to the React app)
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('optionsAnalyzer_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ─── Response interceptor: normalize errors ───
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // If the API returns a structured error, pull out the detail message
    if (error.response?.data?.detail) {
      error.message = error.response.data.detail;
    }
    return Promise.reject(error);
  }
);

export default api;

// ─── Convenience methods for each endpoint ───

export async function analyzeVerticals(params) {
  const { data } = await api.post('/analyze/verticals', params);
  return data;
}

export async function analyzeLongCalls(params) {
  const { data } = await api.post('/analyze/long-calls', params);
  return data;
}

export async function analyzeDirectional(params) {
  const { data } = await api.post('/analyze/directional', params);
  return data;
}

export async function getQuote(symbol) {
  const { data } = await api.get(`/market/quote/${symbol}`);
  return data;
}
