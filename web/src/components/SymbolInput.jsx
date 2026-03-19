/**
 * SymbolInput — Inline symbol text field for analysis pages.
 *
 * WHY THIS EXISTS:
 * The watchlist sidebar lets you pick from 6 pre-set symbols.
 * But you also need to analyze arbitrary symbols that aren't
 * on the watchlist (e.g., NVDA, AMZN, any ticker you're researching).
 * This component adds a small text input next to the page title
 * so you can type any symbol and hit Enter.
 *
 * HOW IT WORKS:
 * - Shows the current activeSymbol in an input field
 * - Type a new symbol → hit Enter or click "Go"
 * - It updates the global activeSymbol via context
 * - The analysis page auto-runs because it watches activeSymbol
 *
 * The input is uppercase-forced so "tsla" becomes "TSLA" automatically.
 */

import { useState, useRef, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import './SymbolInput.css';

export default function SymbolInput() {
  const { activeSymbol, setActiveSymbol, showToast } = useApp();
  const [value, setValue] = useState(activeSymbol);
  const inputRef = useRef(null);

  // Keep the input in sync if activeSymbol changes from elsewhere
  // (e.g., clicking a watchlist item)
  useEffect(() => {
    setValue(activeSymbol);
  }, [activeSymbol]);

  const handleSubmit = () => {
    const symbol = value.trim().toUpperCase();
    if (!symbol) return;
    if (symbol === activeSymbol) return;
    setActiveSymbol(symbol);
    showToast(`Switched to ${symbol}`);
    // Blur the input so the focus goes back to the results
    inputRef.current?.blur();
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleSubmit();
    }
  };

  return (
    <div className="symbol-input-wrap">
      <input
        ref={inputRef}
        type="text"
        className="symbol-input"
        value={value}
        onChange={(e) => setValue(e.target.value.toUpperCase())}
        onKeyDown={handleKeyDown}
        placeholder="Enter a symbol"
        maxLength={10}
        spellCheck={false}
        autoComplete="off"
      />
      <button
        className="symbol-go-btn"
        onClick={handleSubmit}
        title="Analyze this symbol"
      >
        Go
      </button>
    </div>
  );
}
