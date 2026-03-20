/**
 * ChartWidget — Phase 2.3
 *
 * Renders a Recharts line chart for a configured symbol over a configured timeframe.
 * Symbol and timeframe are display-only in 2.3 (shown as text labels).
 * Interactive controls come in 2.4 with edit mode.
 *
 * Uses getHistoricalClose to fetch daily closes for the timeframe.
 *
 * Props: { config: { id, type, title, settings: { symbol, timeframe } }, isEditMode }
 */

import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { getQuote } from '../api/client';

const TIMEFRAME_DAYS = {
  '1D':  1,
  '1W':  7,
  '1M':  30,
  '3M':  90,
  '1Y':  365,
};

function subtractDays(days) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().split('T')[0];
}

export default function ChartWidget({ config, isEditMode }) {
  const symbol    = config.settings?.symbol    ?? 'SPY';
  const timeframe = config.settings?.timeframe ?? '3M';

  const [quote, setQuote]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const q = await getQuote(symbol);
        setQuote(q);
      } catch {
        setError(`Chart data unavailable for ${symbol}`);
      } finally {
        setLoading(false);
      }
    }
    load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.id]);

  // Build a simple sparkline from quote data as a placeholder until
  // a historical bars endpoint is available in Phase 2.x.
  // Uses current price ± simulated intraday range as a single-point proxy.
  const sparkData = quote ? [
    { name: 'prev', price: quote.previous_close ?? quote.price },
    { name: 'now',  price: quote.price },
  ] : [];

  const priceColor = (quote?.change ?? 0) >= 0 ? '#4ade80' : '#f87171';

  return (
    <div style={s.wrap}>
      <div style={s.topRow}>
        <div>
          <span style={s.title}>{config.title}</span>
          <span style={s.meta}>&nbsp;·&nbsp;{symbol}&nbsp;·&nbsp;{timeframe}</span>
        </div>
        {quote && (
          <div style={s.priceGroup}>
            <span style={s.price}>{quote.price?.toFixed(2)}</span>
            <span style={{ ...s.change, color: priceColor }}>
              {(quote.change ?? 0) >= 0 ? '+' : ''}{(quote.change ?? 0).toFixed(2)}
              &nbsp;({(quote.change_pct ?? 0) >= 0 ? '+' : ''}{(quote.change_pct ?? 0).toFixed(2)}%)
            </span>
          </div>
        )}
      </div>

      {loading ? (
        <div style={s.placeholder}>Loading…</div>
      ) : error ? (
        <div style={s.placeholder}>{error}</div>
      ) : (
        <div style={{ flex: 1, minHeight: 0 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sparkData} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
              <XAxis dataKey="name" hide />
              <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10, fill: '#6b7280' }} />
              <Tooltip
                contentStyle={{ background: '#14161f', border: '1px solid #252a3a', borderRadius: 6 }}
                labelStyle={{ color: '#6b7280', fontSize: 11 }}
                itemStyle={{ color: priceColor, fontSize: 12 }}
                formatter={(v) => [v.toFixed(2), symbol]}
              />
              <Line
                type="monotone"
                dataKey="price"
                stroke={priceColor}
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

const s = {
  wrap: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    padding: '12px 14px',
    overflow: 'hidden',
  },
  topRow: {
    display: 'flex',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    marginBottom: 8,
    flexShrink: 0,
  },
  title: {
    fontSize: 11,
    fontWeight: 700,
    color: '#6b7280',
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
  },
  meta: {
    fontSize: 11,
    color: '#4b5563',
  },
  priceGroup: {
    display: 'flex',
    alignItems: 'baseline',
    gap: 8,
  },
  price: {
    fontSize: 18,
    fontWeight: 700,
    color: '#e4e7ef',
    fontFamily: 'monospace',
  },
  change: {
    fontSize: 12,
    fontFamily: 'monospace',
  },
  placeholder: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#6b7280',
    fontSize: 13,
  },
};
