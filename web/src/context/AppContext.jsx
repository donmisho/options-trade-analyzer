/**
 * AppContext — Shared state for symbol selection, watchlist, and favorites.
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
 * Watchlist is persisted in Azure SQL via named watchlists API (/api/v1/watchlists).
 */

import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { getQuotes, getWatchlists, getWatchlistSymbols, addSymbolToWatchlist, removeSymbolFromWatchlist, getFavorites, addFavoriteApi, removeFavoriteApi, getPositionSymbols } from '../api/client';
import { useToast } from '../components/Toast';

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

// ─── Provider ───────────────────────────────────────────────

export function AppProvider({ children }) {
  // Active symbol — shared across all analysis screens
  // Session-only: do NOT read from localStorage on init (UI-DECISIONS.md / OTA-327)
  const [activeSymbol, setActiveSymbol] = useState(null);

  // Dynamic watchlist — persisted in Azure SQL via named watchlists API
  const [watchlist, setWatchlist] = useState([]);
  // Default watchlist ID — resolved on mount, used for add/remove mutations
  const defaultWatchlistIdRef = useRef(null);

  // Active position symbols — [{ symbol, position_count }] for SymbolSearch Tier 1 highlighting
  const [positionSymbols, setPositionSymbols] = useState([]);

  const fetchPositionSymbols = useCallback(async () => {
    try {
      const data = await getPositionSymbols();
      setPositionSymbols(Array.isArray(data) ? data : []);
    } catch {
      // Silently fail — SymbolSearch gracefully degrades to Tier 2 only
    }
  }, []);

  useEffect(() => {
    fetchPositionSymbols();
  }, [fetchPositionSymbols]);

  // Config drawer — shared so Header gear icon can open it from any page
  const [configOpen, setConfigOpen] = useState(false);

  // System Vars Panel — application-wide settings drawer
  const [systemVarsPanelOpen, setSystemVarsPanelOpen] = useState(false);

  // System Variables — loaded from localStorage, updated by SystemVarsPanel
  const DEFAULT_SV = {
    exit_warning_pct: 67, exit_scale_out_pct: 160,
    exit_underlying_stop_pct: 1.5, exit_time_stop_days: 10,
    min_reward_risk: 0.5, min_ev_threshold: 0,
    pip_rr_green: 1.5, pip_rr_amber: 1.0,
    pip_prob_green: 0.55, pip_prob_amber: 0.45,
    pip_score_green: 0.65, pip_score_amber: 0.45,
    pip_delta_lo: 0.30, pip_delta_hi: 0.65,
    pip_iv_green: 30, pip_iv_amber: 50,
    pip_runway_green: 30, pip_runway_amber: 15,
  };
  const [systemVars, setSystemVars] = useState(() => {
    try {
      const stored = JSON.parse(localStorage.getItem('analysisConfig') || '{}');
      return stored.systemVars ? { ...DEFAULT_SV, ...stored.systemVars } : DEFAULT_SV;
    } catch {
      return DEFAULT_SV;
    }
  });

  // Strategy Admin — user enable/disable and rename overrides, saved to localStorage
  const [strategyAdmin, setStrategyAdmin] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('strategyAdmin') || '{}');
    } catch {
      return {};
    }
  });

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

  // Load watchlist from DB on mount via named watchlists API.
  // Resolves the default watchlist, stores its ID for add/remove mutations.
  // Falls back to STARTER_WATCHLIST if empty or API fails.
  useEffect(() => {
    (async () => {
      try {
        const data = await getWatchlists();
        const lists = data?.watchlists ?? [];
        const defaultList = lists.find(w => w.is_default) || lists[0];
        if (!defaultList) {
          setWatchlist(STARTER_WATCHLIST);
          fetchPrices(STARTER_WATCHLIST.map(w => w.symbol));
          return;
        }
        defaultWatchlistIdRef.current = defaultList.id;
        const entries = await getWatchlistSymbols(defaultList.id);
        const symbols = (entries || []).map(e => (typeof e === 'string' ? e : e.symbol)).filter(Boolean);
        const items = symbols.length > 0
          ? symbols.map(s => ({ symbol: s, name: SYMBOL_NAMES[s] || '' }))
          : STARTER_WATCHLIST;
        setWatchlist(items);
        fetchPrices(items.map(w => w.symbol));
      } catch (err) {
        console.error('[AppContext] getWatchlists failed, using starter:', err);
        setWatchlist(STARTER_WATCHLIST);
        fetchPrices(STARTER_WATCHLIST.map(w => w.symbol));
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Live prices keyed by symbol: { SPY: { price: 598.12, change: -2.31, change_pct: -0.38 }, ... }
  const [prices, setPrices] = useState({});
  const [pricesLoading, setPricesLoading] = useState(false);

  // Ref to prevent duplicate fetches if component re-renders during load
  const fetchingRef = useRef(false);

  // Mirror of watchlist as a ref so fetchPrices can read current symbols
  // without closing over watchlist state (which would force a new callback
  // identity on every mutation and re-trigger any effect that deps on it).
  const watchlistRef = useRef([]);
  useEffect(() => {
    watchlistRef.current = watchlist.map(w => w.symbol);
  }, [watchlist]);

  /**
   * Fetch live quotes for the given symbols (or all watchlist symbols if
   * called with no argument — preserving the no-arg contract used by
   * Header.jsx and Layout.jsx without closing over watchlist state).
   *
   * WHY empty dep array + watchlistRef?
   * fetchPrices must be stable so no useEffect can dep on it and re-fire
   * on every watchlist mutation. watchlistRef.current always reflects the
   * latest watchlist without introducing a dep.
   *
   * WHY parallel fetch instead of one-by-one?
   * Promise.all fires all quote requests simultaneously, so the latency
   * is the slowest single call (~1s) rather than N calls in series (~Ns).
   */
  const fetchPrices = useCallback(async (symbols) => {
    const list = symbols ?? watchlistRef.current;
    if (!list || list.length === 0) return;
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    setPricesLoading(true);
    try {
      const quotes = await getQuotes(list);
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
    } catch (err) {
      console.error('[AppContext] fetchPrices failed:', err);
    } finally {
      setPricesLoading(false);
      fetchingRef.current = false;
    }
  }, []);

  /**
   * Add a symbol to the watchlist (or move it to the top if already there).
   *
   * WHY move-to-top: The most recently searched symbol is the one you're
   * actively thinking about. Putting it at the top keeps it one click away.
   */
  const addToWatchlist = useCallback((symbol) => {
    const sym = symbol.toUpperCase();
    // Optimistic update
    setWatchlist(prev => {
      const filtered = prev.filter(w => w.symbol !== sym);
      return [{ symbol: sym, name: SYMBOL_NAMES[sym] || '' }, ...filtered];
    });
    // Persist to DB via named watchlist API (best-effort)
    if (defaultWatchlistIdRef.current) {
      addSymbolToWatchlist(defaultWatchlistIdRef.current, sym).catch(() => {});
    }
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

  const removeFromWatchlist = useCallback((symbol) => {
    const sym = symbol.toUpperCase();
    setWatchlist(prev => prev.filter(w => w.symbol !== sym));
    if (defaultWatchlistIdRef.current) {
      removeSymbolFromWatchlist(defaultWatchlistIdRef.current, sym).catch(() => {});
    }
  }, []);

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

  // Toast — delegate to ToastProvider (parent in App.jsx)
  const { showToast } = useToast();

  // Persist active symbol
  useEffect(() => {
    localStorage.setItem('optionsAnalyzer_symbol', activeSymbol);
  }, [activeSymbol]);

  // Persist favorites whenever they change
  useEffect(() => {
    saveFavorites(favorites);
  }, [favorites]);

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
    addToWatchlist,
    removeFromWatchlist,

    // Position symbols — for SymbolSearch Tier 1 highlighting
    positionSymbols,
    fetchPositionSymbols,

    // Config drawer
    configOpen,
    setConfigOpen,

    // System Vars Panel
    systemVarsPanelOpen,
    setSystemVarsPanelOpen,
    systemVars,
    setSystemVars,

    // Strategy Admin — user overrides for strategy enable/disable and names
    strategyAdmin,
    setStrategyAdmin,

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
