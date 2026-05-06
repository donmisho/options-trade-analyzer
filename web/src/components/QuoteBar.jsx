/**
 * QuoteBar — Single shared symbol header. Single flex row matching mockup.
 *
 * Props:
 *   symbol        — ticker string (falls back to AppContext activeSymbol)
 *   quote         — quote object; if undefined → auto-fetches internally
 *   smaSignal     — 'BULLISH' | 'BEARISH' | 'MIXED'
 *   lastAnalyzed  — Date object or ISO string
 *   fundamentals  — { earningsDate?, dividendDate? } override
 *
 * Rules: No $ prefix. Earnings/dividend only within 60 days. Earnings <14d = amber badge.
 */

import { useState, useEffect, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import { getQuote } from '../api/client';
import { formatDate } from '../utils/formatDate';
import './QuoteBar.css';

function daysUntil(dateStr) {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  if (isNaN(d)) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((d - today) / 86400000);
}

function fmtDateShort(dateStr) {
  return formatDate(dateStr);
}

function fmtLastAnalyzed(val) {
  if (!val) return null;
  return formatDate(val, true);
}

function fmtVol(n) {
  if (!n) return '—';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(0) + 'K';
  return n.toLocaleString();
}

function fmtNum(n, decimals = 2) {
  if (n == null) return '—';
  return n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export default function QuoteBar({ symbol: symbolProp, quote: quoteProp, smaSignal, lastAnalyzed, fundamentals }) {
  const { activeSymbol } = useApp();
  const symbol = symbolProp || activeSymbol;

  const autoFetch = quoteProp === undefined;
  const [fetchedQuote, setFetchedQuote] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchQuote = useCallback(async () => {
    if (!symbol) return;
    setLoading(true);
    try {
      const data = await getQuote(symbol);
      setFetchedQuote(data);
    } catch {
      setFetchedQuote(null);
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    if (autoFetch) fetchQuote();
  }, [fetchQuote, autoFetch]);

  const quote = autoFetch ? fetchedQuote : quoteProp;

  const hasPrice = quote && quote.price > 0;
  const isUp = quote && quote.change >= 0;
  const changeColor = isUp ? '#4ade80' : '#f87171';
  const ratio = quote?.volume_ratio;
  const relVolHigh = ratio != null && ratio >= 1.5;

  const rawEarnings = fundamentals?.earningsDate || quote?.next_earnings_date;
  const rawDividend = fundamentals?.dividendDate  || quote?.next_dividend_date;
  const earningsTimeOfDay = quote?.earnings_time_of_day;
  const earningsDays = daysUntil(rawEarnings);
  const dividendDays = daysUntil(rawDividend);
  const showEarnings = earningsDays !== null && earningsDays >= 0;
  const showDividend = dividendDays !== null && dividendDays >= 0;

  const lastAnalyzedStr = fmtLastAnalyzed(lastAnalyzed);

  const sigBadgeClass = smaSignal === 'BULLISH' ? 'qb-badge qb-badge-bull'
    : smaSignal === 'BEARISH' ? 'qb-badge qb-badge-bear'
    : smaSignal === 'MIXED'   ? 'qb-badge qb-badge-mixed'
    : null;

  return (
    <div className="quote-bar">
      {symbol && <span className="qb-symbol">{symbol}</span>}

      {sigBadgeClass && (
        <span className={sigBadgeClass}>{smaSignal}</span>
      )}

      {lastAnalyzedStr && (
        <div className="qb-field">
          <span className="qb-label">Last Analyzed</span>
          <span className="qb-value">{lastAnalyzedStr}</span>
        </div>
      )}

      {loading && <span className="qb-loading">Loading…</span>}

      {hasPrice && !loading && (
        <>
          <div className="qb-field">
            <span className="qb-label">Price</span>
            <span className="qb-value">{fmtNum(quote.price)}</span>
          </div>
          <div className="qb-field">
            <span className="qb-label">CHG</span>
            <span className="qb-value" style={{ color: changeColor }}>
              {isUp ? '+' : ''}{fmtNum(quote.change)}
            </span>
          </div>
          <div className="qb-field">
            <span className="qb-label">CHG %</span>
            <span className="qb-value" style={{ color: changeColor }}>
              {isUp ? '+' : ''}{fmtNum(quote.change_pct)}%
            </span>
          </div>
          <div className="qb-field">
            <span className="qb-label">Day Range</span>
            <span className="qb-value">{fmtNum(quote.day_low)} – {fmtNum(quote.day_high)}</span>
          </div>
          {quote.week_52_high && quote.week_52_low && (
            <div className="qb-field">
              <span className="qb-label">52W Range</span>
              <span className="qb-value">{fmtNum(quote.week_52_low)} – {fmtNum(quote.week_52_high)}</span>
            </div>
          )}
          <div className="qb-field">
            <span className="qb-label">Volume</span>
            <span className="qb-value">{fmtVol(quote.volume)}</span>
          </div>
          {ratio != null && (
            <div className="qb-field">
              <span className="qb-label">Rel Vol</span>
              <span className="qb-value" style={{ color: relVolHigh ? '#f59e0b' : undefined }}>
                {ratio.toFixed(1)}x
              </span>
            </div>
          )}
          {showEarnings && (
            <div className="qb-field">
              <span className="qb-label">Earnings</span>
              <span className="qb-value" style={earningsDays <= 14 ? { color: '#f59e0b' } : undefined}>
                {fmtDateShort(rawEarnings)} ({earningsDays}){earningsTimeOfDay ? ` ${earningsTimeOfDay}` : ''}
              </span>
            </div>
          )}
          {showDividend && (
            <div className="qb-field">
              <span className="qb-label">Dividend</span>
              <span className="qb-value">{fmtDateShort(rawDividend)} ({dividendDays})</span>
            </div>
          )}
        </>
      )}
    </div>
  );
}
