/**
 * AppContext — Shared state for symbol selection, watchlist, and favorites.
 *
 * WHY React Context instead of prop drilling?
 * The active symbol needs to be visible to: the Header (shows it),
 * the Watchlist (highlights it), and every analysis screen (fetches data for it).
 * Passing it as props through 4+ levels of components would be messy.
 * Context makes it available to any component that needs it via useApp().
 *
 * WHY localStorage for favorites and watchlist?
 * Both need to survive page refreshes and browser restarts.
 * localStorage is the simplest persistence layer for client-side data.
 * In a future phase, we could sync to the database via an API endpoint.
 */

import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { getQuotes, getWatchlist, saveWatchlist as saveWatchlistApi, getFavorites, addFavoriteApi, removeFavoriteApi } from '../api/client';

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
// The starter symbols — used on first ever load when there's
// nothing saved in localStorage yet.

const STARTER_WATCHLIST = [
  { symbol: 'SPY', name: 'S&P 500 ETF' },
  { symbol: 'QQQ', name: 'Nasdaq 100' },
  { symbol: 'MSFT', name: 'Microsoft' },
  { symbol: 'GLD', name: 'Gold ETF' },
  { symbol: 'T', name: 'AT&T' },
  { symbol: 'GEV', name: 'GE Vernova' },
];

// Known names for common symbols — used to show a friendly name
// in the watchlist sidebar. If a symbol isn't here, we just show
// the ticker with no subtitle.
const SYMBOL_NAMES = {
  SPY: 'S&P 500 ETF', QQQ: 'Nasdaq 100', MSFT: 'Microsoft',
  GLD: 'Gold ETF', T: 'AT&T', GEV: 'GE Vernova',
  AAPL: 'Apple', AMZN: 'Amazon', GOOG: 'Alphabet',
  GOOGL: 'Alphabet', META: 'Meta', NVDA: 'NVIDIA',
  TSLA: 'Tesla', AMD: 'AMD', NFLX: 'Netflix',
  JPM: 'JPMorgan', BAC: 'Bank of America', V: 'Visa',
  MA: 'Mastercard', DIS: 'Disney', INTC: 'Intel',
  CRM: 'Salesforce', PYPL: 'PayPal', COIN: 'Coinbase',
  PLTR: 'Palantir', SOFI: 'SoFi', RIVN: 'Rivian',
  IWM: 'Russell 2000 ETF', TLT: 'Treasury Bond ETF',
  XLF: 'Financial ETF', XLE: 'Energy ETF', SLV: 'Silver ETF',
};

const WL_KEY = 'optionsAnalyzer_watchlist';

function loadWatchlist() {
  try {
    const raw = localStorage.getItem(WL_KEY);
    if (!raw) return STARTER_WATCHLIST;
    const saved = JSON.parse(raw);
    if (!Array.isArray(saved) || saved.length === 0) return STARTER_WATCHLIST;
    return saved;
  } catch {
    return STARTER_WATCHLIST;
  }
}

function saveWatchlist(list) {
  localStorage.setItem(WL_KEY, JSON.stringify(list));
}

// ─── Provider ───────────────────────────────────────────────

export function AppProvider({ children }) {
  // Active symbol — shared across all analysis screens
  const [activeSymbol, setActiveSymbol] = useState(() => {
    return localStorage.getItem('optionsAnalyzer_symbol') || 'SPY';
  });

  // Dynamic watchlist — persisted in localStorage + backend
  const [watchlist, setWatchlist] = useState(loadWatchlist);

  // Config drawer — shared so Header gear icon can open it from any page
  const [configOpen, setConfigOpen] = useState(false);

  // Trade Agent Panel — shared so any page can trigger Claude evaluation
  const [agentOpen, setAgentOpen] = useState(false);
  const [agentTrades, setAgentTrades] = useState([]);
  const [agentMarketContext, setAgentMarketContext] = useState(null);

  function openAgent(trades, marketContext) {
    setAgentTrades(trades);
    setAgentMarketContext(marketContext);
    setAgentOpen(true);
  }
  function closeAgent() {
    setAgentOpen(false);
    // Don't clear trades/context on close — allow re-open to same state
  }

  // Load watchlist from backend on mount; fall back to localStorage if API fails
  useEffect(() => {
    getWatchlist()
      .then(data => {
        if (Array.isArray(data) && data.length > 0) {
          setWatchlist(data);
          saveWatchlist(data); // keep localStorage in sync
        }
      })
      .catch(() => {}); // silently use localStorage fallback
  }, []);

  // Live prices keyed by symbol: { SPY: { price: 598.12, change: -2.31, change_pct: -0.38 }, ... }
  const [prices, setPrices] = useState({});
  const [pricesLoading, setPricesLoading] = useState(false);

  // Ref to prevent duplicate fetches if component re-renders during load
  const fetchingRef = useRef(false);

  /**
   * Fetch live quotes for all watchlist symbols.
   *
   * WHY parallel fetch instead of one-by-one?
   * Calling getQuote for 6 symbols sequentially would take ~6 seconds
   * (each call waits for the previous). Promise.all fires them all at
   * once, so it takes as long as the slowest single call (~1 second).
   */
  const fetchPrices = useCallback(async (symbolList) => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    setPricesLoading(true);
    try {
      const symbols = symbolList || watchlist.map(w => w.symbol);
      const quotes = await getQuotes(symbols);
      setPrices(prev => {
        const updated = { ...prev };
        for (const [symbol, q] of Object.entries(quotes)) {
          if (q) {
            updated[symbol] = {
              price: q.price,
              change: q.change,
              change_pct: q.change_pct,
            };
          }
        }
        return updated;
      });
    } catch {
      // Silently fail — stale prices are better than crashing
    } finally {
      setPricesLoading(false);
      fetchingRef.current = false;
    }
  }, [watchlist]);

  /**
   * Add a symbol to the watchlist (or move it to the top if already there).
   *
   * WHY move-to-top: The most recently searched symbol is the one you're
   * actively thinking about. Putting it at the top keeps it one click away.
   */
  const addToWatchlist = useCallback((symbol) => {
    const sym = symbol.toUpperCase();
    setWatchlist(prev => {
      const filtered = prev.filter(w => w.symbol !== sym);
      const entry = { symbol: sym, name: SYMBOL_NAMES[sym] || '' };
      const updated = [entry, ...filtered];
      saveWatchlist(updated);
      return updated;
    });
    // Fetch price for the new symbol if we don't have it yet
    if (!prices[sym]) {
      getQuotes([sym]).then(quotes => {
        const q = quotes[sym];
        if (q) {
          setPrices(prev => ({
            ...prev,
            [sym]: { price: q.price, change: q.change, change_pct: q.change_pct },
          }));
        }
      });
    }
  }, [prices]);

  // Fetch prices on initial load
  useEffect(() => {
    fetchPrices();
  }, [fetchPrices]);

  // Favorites — loaded from backend on mount, localStorage as fallback
  const [favorites, setFavorites] = useState(loadFavorites);

  useEffect(() => {
    getFavorites()
      .then(data => {
        if (Array.isArray(data) && data.length > 0) {
          // Backend stores trade_data as the full snapshot; add savedAt for TTL logic
          const favs = data.map(f => ({
            ...f.trade_data,
            savedAt: new Date(f.saved_at).getTime(),
            savedDate: f.saved_at.slice(0, 10),
          }));
          setFavorites(favs);
          saveFavorites(favs);
        }
      })
      .catch(() => {});
  }, []);

  // Toast notification
  const [toast, setToast] = useState(null);

  // Persist watchlist to localStorage + backend whenever it changes
  useEffect(() => {
    saveWatchlist(watchlist);
    saveWatchlistApi(watchlist).catch(() => {}); // best-effort API sync
  }, [watchlist]);

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

  const showToast = useCallback((msgOrObj) => {
    setToast(typeof msgOrObj === 'string' ? { message: msgOrObj } : msgOrObj);
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
      if (prev.some(f => f.id === trade.id)) return prev;
      const fav = {
        ...trade,
        savedAt: Date.now(),
        savedDate: new Date().toISOString().slice(0, 10),
      };
      showToast(`★ Saved: ${trade.label}`);
      addFavoriteApi(fav).catch(() => {}); // best-effort API sync
      return [...prev, fav];
    });
  }, [showToast]);

  const removeFavorite = useCallback((id) => {
    setFavorites(prev => prev.filter(f => f.id !== id));
    removeFavoriteApi(id).catch(() => {}); // best-effort API sync
    showToast('Removed from favorites');
  }, [showToast]);

  const isFavorited = useCallback((id) => {
    return favorites.some(f => f.id === id);
  }, [favorites]);

  // Wrap setActiveSymbol to also update the watchlist
  const handleSetActiveSymbol = useCallback((symbol) => {
    setActiveSymbol(symbol);
    addToWatchlist(symbol);
  }, [addToWatchlist]);

  const value = {
    // Symbol
    activeSymbol,
    setActiveSymbol: handleSetActiveSymbol,
    watchlist,

    // Config drawer
    configOpen,
    setConfigOpen,

    // Prices
    prices,
    pricesLoading,
    fetchPrices,

    // Favorites
    favorites,
    addFavorite,
    removeFavorite,
    isFavorited,

    // Toast
    toast,
    showToast,

    // Agent panel
    agentOpen,
    agentTrades,
    agentMarketContext,
    openAgent,
    closeAgent,
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
