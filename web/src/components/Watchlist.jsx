/**
 * Watchlist — Persistent left sidebar showing tracked symbols.
 *
 * WHY always visible?
 * Options traders constantly flip between symbols to compare
 * opportunities. Having the watchlist always one click away
 * (instead of buried in a menu) matches how ThinkorSwim and
 * other trading platforms work.
 *
 * HOW symbol switching works:
 * Clicking a symbol calls setActiveSymbol() from AppContext.
 * Every analysis screen reads activeSymbol from the same context,
 * so they all react to the change automatically. This is React's
 * "lifting state up" pattern — the state lives in the shared
 * parent (AppContext), and children just consume it.
 */

import { useApp } from '../context/AppContext';
import './Watchlist.css';

export default function Watchlist() {
  const { watchlist, activeSymbol, setActiveSymbol, showToast } = useApp();

  const handleClick = (symbol) => {
    if (symbol === activeSymbol) return; // Already selected
    setActiveSymbol(symbol);
    showToast(`Switched to ${symbol} — analysis will refresh`);
  };

  return (
    <aside className="watchlist">
      <div className="watchlist-title">
        <span>Watchlist</span>
        <span
          className="watchlist-refresh"
          onClick={() => showToast('Prices refreshed')}
          title="Refresh prices"
        >
          ⟳
        </span>
      </div>
      {watchlist.map(({ symbol, name }) => (
        <div
          key={symbol}
          className={`watchlist-item ${symbol === activeSymbol ? 'active' : ''}`}
          onClick={() => handleClick(symbol)}
        >
          <div>
            <span className="wl-symbol">{symbol}</span>
            <div className="wl-sub">{name}</div>
          </div>
          {/* Price will be filled by API quote calls in Layer 2 */}
          <span className="wl-price">—</span>
        </div>
      ))}
    </aside>
  );
}
