/**
 * AppContext — Shared state for symbol selection and favorites.
 *
 * WHY React Context instead of prop drilling?
 * The active symbol needs to be visible to: the Header (shows it),
 * the Watchlist (highlights it), and every analysis screen (fetches data for it).
 * Passing it as props through 4+ levels of components would be messy.
 * Context makes it available to any component that needs it via useApp().
 *
 * WHY localStorage for favorites?
 * Favorites need to survive page refreshes and browser restarts.
 * localStorage is the simplest persistence layer for client-side data.
 * In a future phase, we could sync favorites to the database via an API
 * endpoint, but localStorage is perfect for now.
 */

import { createContext, useContext, useState, useEffect, useCallback } from 'react';

const AppContext = createContext(null);

// ─── Favorites localStorage helpers ─────────────────────────

const FAV_KEY = 'optionsAnalyzer_favorites';
const FAV_TTL_DAYS = 30;

function loadFavorites() {
  try {
    const raw = localStorage.getItem(FAV_KEY);
    if (!raw) return [];
    const favs = JSON.parse(raw);
    // Filter out expired favorites (older than 30 days)
    const now = Date.now();
    const cutoff = FAV_TTL_DAYS * 24 * 60 * 60 * 1000;
    return favs.filter(f => now - f.savedAt < cutoff);
  } catch {
    return [];
  }
}

function saveFavorites(favs) {
  localStorage.setItem(FAV_KEY, JSON.stringify(favs));
}

// ─── Watchlist data ─────────────────────────────────────────
// Static for now — in a future phase this comes from the DB
// via the user config endpoint.

const DEFAULT_WATCHLIST = [
  { symbol: 'SPY', name: 'S&P 500 ETF' },
  { symbol: 'QQQ', name: 'Nasdaq 100' },
  { symbol: 'MSFT', name: 'Microsoft' },
  { symbol: 'GLD', name: 'Gold ETF' },
  { symbol: 'T', name: 'AT&T' },
  { symbol: 'GEV', name: 'GE Vernova' },
];

// ─── Provider ───────────────────────────────────────────────

export function AppProvider({ children }) {
  // Active symbol — shared across all analysis screens
  const [activeSymbol, setActiveSymbol] = useState(() => {
    return localStorage.getItem('optionsAnalyzer_symbol') || 'SPY';
  });

  // Watchlist with live prices (prices fetched separately)
  const [watchlist] = useState(DEFAULT_WATCHLIST);

  // Favorites
  const [favorites, setFavorites] = useState(loadFavorites);

  // Toast notification
  const [toast, setToast] = useState(null);

  // Persist active symbol
  useEffect(() => {
    localStorage.setItem('optionsAnalyzer_symbol', activeSymbol);
  }, [activeSymbol]);

  // Persist favorites whenever they change
  useEffect(() => {
    saveFavorites(favorites);
  }, [favorites]);

  // Auto-dismiss toast
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(timer);
  }, [toast]);

  const showToast = useCallback((message) => {
    setToast(message);
  }, []);

  /**
   * Add a trade to favorites.
   *
   * Each favorite stores a snapshot of the trade at the moment
   * you star it: the pricing, score, and which screen it came from.
   * This is the "original price" column on the Favorites screen.
   *
   * The `id` is a unique key so we can find/remove specific favorites.
   * We build it from the trade details so the same trade doesn't
   * get duplicated if you star it twice.
   */
  const addFavorite = useCallback((trade) => {
    setFavorites(prev => {
      // Don't add duplicates
      if (prev.some(f => f.id === trade.id)) return prev;
      const fav = {
        ...trade,
        savedAt: Date.now(),
        savedDate: new Date().toISOString().slice(0, 10),
      };
      showToast(`★ Saved: ${trade.label}`);
      return [...prev, fav];
    });
  }, [showToast]);

  const removeFavorite = useCallback((id) => {
    setFavorites(prev => prev.filter(f => f.id !== id));
    showToast('Removed from favorites');
  }, [showToast]);

  const isFavorited = useCallback((id) => {
    return favorites.some(f => f.id === id);
  }, [favorites]);

  const value = {
    // Symbol
    activeSymbol,
    setActiveSymbol,
    watchlist,

    // Favorites
    favorites,
    addFavorite,
    removeFavorite,
    isFavorited,

    // Toast
    toast,
    showToast,
  };

  return (
    <AppContext.Provider value={value}>
      {children}
    </AppContext.Provider>
  );
}

/**
 * Hook to access app state from any component.
 *
 * Usage:
 *   const { activeSymbol, setActiveSymbol, favorites } = useApp();
 */
export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
