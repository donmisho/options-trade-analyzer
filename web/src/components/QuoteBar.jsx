/**
 * QuoteBar — Enhanced symbol header for analysis pages.
 *
 * Shows at the top of each analysis screen:
 *   [Symbol Input] [Go]   $392.74  -1.24%   Day: $389.12 – $395.50   52W: $312.10 – $468.35   🔥 1.8x Vol
 *
 * WHY a dedicated component?
 * This replaces the old <h2> with just the symbol name. Every analysis
 * page needs the same info: current price, whether it's up or down,
 * how today's range compares to the 52-week range, and whether there's
 * unusual volume (which often signals something interesting for options).
 *
 * ACTIVITY INDICATOR:
 * Compares today's volume to the average daily volume. If the ratio
 * is > 1.5x, we show an orange/red indicator. Unusual volume often
 * means earnings, news, or institutional activity — all of which
 * affect options pricing and are worth knowing before you trade.
 */

import { useState, useEffect, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import { getQuote } from '../api/client';
import SymbolInput from './SymbolInput';
import './QuoteBar.css';

export default function QuoteBar({ title }) {
  const { activeSymbol } = useApp();
  const [quote, setQuote] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchQuote = useCallback(async () => {
    if (!activeSymbol) return;
    setLoading(true);
    try {
      const data = await getQuote(activeSymbol);
      setQuote(data);
    } catch {
      setQuote(null);
    } finally {
      setLoading(false);
    }
  }, [activeSymbol]);

  useEffect(() => {
    fetchQuote();
  }, [fetchQuote]);

  const isUp = quote && quote.change >= 0;
  const hasPrice = quote && quote.price > 0;
  const has52w = quote && quote.week_52_high && quote.week_52_low;
  const hasActivity = quote && quote.volume_ratio != null;

  // Activity level thresholds
  let activityLevel = null;
  let activityLabel = '';
  if (hasActivity) {
    const ratio = quote.volume_ratio;
    if (ratio >= 3.0) {
      activityLevel = 'extreme';
      activityLabel = `${ratio.toFixed(1)}x Vol`;
    } else if (ratio >= 1.5) {
      activityLevel = 'high';
      activityLabel = `${ratio.toFixed(1)}x Vol`;
    } else if (ratio >= 0.8) {
      activityLevel = 'normal';
      activityLabel = `${ratio.toFixed(1)}x Vol`;
    } else {
      activityLevel = 'low';
      activityLabel = `${ratio.toFixed(1)}x Vol`;
    }
  }

  // Format large numbers for volume display
  function fmtVol(n) {
    if (!n) return '—';
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1_000) return (n / 1_000).toFixed(0) + 'K';
    return n.toLocaleString();
  }

  return (
    <div className="quote-bar">
      {/* Row 1: Title + Symbol Input */}
      <div className="qb-title-row">
        <h2 className="qb-title">{title} —</h2>
        <SymbolInput />
      </div>

      {/* Row 2: Price data strip */}
      {hasPrice && !loading && (
        <div className="qb-data-row">
          {/* Price + Change */}
          <div className="qb-price-group">
            <span className="qb-price">${quote.price.toFixed(2)}</span>
            <span className={`qb-change ${isUp ? 'up' : 'down'}`}>
              {isUp ? '+' : ''}{quote.change.toFixed(2)} ({isUp ? '+' : ''}{quote.change_pct.toFixed(2)}%)
            </span>
          </div>

          <span className="qb-divider">|</span>

          {/* Day Range */}
          <div className="qb-range-group">
            <span className="qb-range-label">Day</span>
            <span className="qb-range-values">
              ${quote.day_low.toFixed(2)} – ${quote.day_high.toFixed(2)}
            </span>
          </div>

          {/* 52-Week Range */}
          {has52w && (
            <>
              <span className="qb-divider">|</span>
              <div className="qb-range-group">
                <span className="qb-range-label">52W</span>
                <span className="qb-range-values">
                  ${quote.week_52_low.toFixed(2)} – ${quote.week_52_high.toFixed(2)}
                </span>
              </div>
            </>
          )}

          {/* Volume */}
          <span className="qb-divider">|</span>
          <div className="qb-range-group">
            <span className="qb-range-label">Vol</span>
            <span className="qb-range-values">{fmtVol(quote.volume)}</span>
          </div>

          {/* Critical Dates */}
          {quote.next_earnings_date && (
            <>
              <span className="qb-divider">|</span>
              <div className="qb-critical-date">
                <span className="qb-critical-date-label">Earnings:</span>
                <span className="qb-critical-date-value">{quote.next_earnings_date}</span>
              </div>
            </>
          )}
          {quote.next_dividend_date && (
            <>
              <span className="qb-divider">|</span>
              <div className="qb-critical-date">
                <span className="qb-critical-date-label">Dividend:</span>
                <span className="qb-critical-date-value">{quote.next_dividend_date}</span>
              </div>
            </>
          )}

          {/* Activity Indicator */}
          {activityLevel && (
            <>
              <span className="qb-divider">|</span>
              <div className={`qb-activity qb-activity-${activityLevel}`} title={
                activityLevel === 'extreme' ? 'Extremely high volume — 3x+ above average' :
                activityLevel === 'high' ? 'Above average volume — 1.5x+ normal' :
                activityLevel === 'low' ? 'Below average volume' :
                'Normal volume'
              }>
                <span className="qb-activity-icon">
                  {activityLevel === 'extreme' ? '🔥' :
                   activityLevel === 'high' ? '📈' :
                   activityLevel === 'low' ? '💤' : ''}
                </span>
                <span className="qb-activity-label">{activityLabel}</span>
              </div>
            </>
          )}
        </div>
      )}

      {loading && (
        <div className="qb-data-row">
          <span className="qb-loading">Loading quote...</span>
        </div>
      )}
    </div>
  );
}
