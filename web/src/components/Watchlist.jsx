/**
 * Watchlist — Persistent left sidebar showing tracked symbols with live prices.
 *
 * Prices are fetched on app load and when you click the ⟳ button.
 * Green = up on the day, Red = down on the day.
 * The spinner on the refresh button shows when prices are loading.
 */

import { useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import './Watchlist.css';

export default function Watchlist() {
  const {
    watchlist,
    activeSymbol,
    setActiveSymbol,
    prices,
    pricesLoading,
    fetchPrices,
    showToast,
  } = useApp();
  const navigate = useNavigate();

  const handleClick = (symbol) => {
    setActiveSymbol(symbol);
    navigate(`/security/${symbol}`);
  };

  const handleRefresh = async () => {
    await fetchPrices();
    showToast('Prices refreshed');
  };

  return (
    <aside className="watchlist">
      <div className="watchlist-title">
        <span>Watchlist</span>
        <span
          className={`watchlist-refresh ${pricesLoading ? 'spinning' : ''}`}
          onClick={handleRefresh}
          title="Refresh prices"
        >
          ⟳
        </span>
      </div>
      {watchlist.map(({ symbol, name }) => {
        const quote = prices[symbol];
        const hasPrice = quote && quote.price > 0;
        const isUp = quote && quote.change >= 0;

        return (
          <div
            key={symbol}
            className={`watchlist-item ${symbol === activeSymbol ? 'active' : ''}`}
            onClick={() => handleClick(symbol)}
          >
            <div>
              <span className="wl-symbol">{symbol}</span>
              <div className="wl-sub">{name}</div>
            </div>
            <div className="wl-price-block">
              {hasPrice ? (
                <>
                  <span className="wl-price">{quote.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                  <span className={`wl-change ${isUp ? 'up' : 'down'}`}>
                    {isUp ? '+' : ''}{quote.change_pct.toFixed(2)}%
                  </span>
                </>
              ) : (
                <span className="wl-price">—</span>
              )}
            </div>
          </div>
        );
      })}
    </aside>
  );
}
