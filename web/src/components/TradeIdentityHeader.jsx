/**
 * TradeIdentityHeader — OTA-291
 *
 * Compact two-row header bar summarising a trade's identity and key metrics.
 * Stateless — pure display, all data via props.
 */

import { formatDate } from '../utils/formatDate';
import { mono } from '../styles/tokens';

// ─── Design system colors ─────────────────────────────────────────────────────

const EMERALD = '#00C896';
const AMBER   = '#F5A623';
const DANGER  = '#F85149';

// ─── Spread type metadata ─────────────────────────────────────────────────────

const SPREAD_META = {
  BEAR_PUT_DEBIT:   { direction: 'bearish', entry: 'debit' },
  BULL_CALL_DEBIT:  { direction: 'bullish', entry: 'debit' },
  BULL_PUT_CREDIT:  { direction: 'bullish', entry: 'credit' },
  BEAR_CALL_CREDIT: { direction: 'bearish', entry: 'credit' },
};

const DIRECTION_DESC = {
  bearish: 'you pay to enter',
  bullish: 'you pay to enter',
};
const ENTRY_DESC = {
  debit:  'you pay to enter',
  credit: 'you receive credit',
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmt2(val) {
  return val != null ? Number(val).toFixed(2) : '—';
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function MetaItem({ label, value, color }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
      <span style={{
        fontSize: 8,
        color: '#555b6e',
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        fontFamily: mono,
        whiteSpace: 'nowrap',
      }}>
        {label}
      </span>
      <span style={{
        fontSize: 11,
        color: color ?? '#c9d1d9',
        fontWeight: 500,
        fontFamily: mono,
        whiteSpace: 'nowrap',
      }}>
        {value ?? '—'}
      </span>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function TradeIdentityHeader({
  spread_type,
  long_strike,
  short_strike,
  expiry,
  entry_price,
  entry_price_contract,
  max_profit,
  max_loss,
  breakeven,
  dte,
  reward_risk,
  profit_trigger,
  stop_trigger,
  time_exit_date,
}) {
  const meta       = SPREAD_META[spread_type] ?? {};
  const entryKind  = meta.entry ?? (spread_type?.includes('DEBIT') ? 'debit' : 'credit');
  const desc       = ENTRY_DESC[entryKind] ?? '';

  const entryLabel = entry_price != null
    ? `${fmt2(entry_price)} ${entryKind} / share (${entry_price_contract ?? '—'} / contract)`
    : '—';

  return (
    <div style={{
      backgroundColor: '#141722',
      border: '1px solid #252a3a',
      borderRadius: 6,
      padding: '10px 16px',
    }}>
      {/* ── Row 1: identity ─────────────────────────────────────── */}
      <div style={{
        display: 'flex',
        gap: 20,
        alignItems: 'center',
        flexWrap: 'wrap',
        marginBottom: 10,
      }}>
        <div style={{ fontFamily: mono }}>
          <span style={{ fontSize: 12, color: '#e4e7ef', fontWeight: 700 }}>
            {spread_type ?? '—'}
          </span>
          {desc && (
            <span style={{ fontSize: 11, color: '#8b90a0', fontWeight: 400, marginLeft: 6 }}>
              ({meta.direction ?? ''} — {desc})
            </span>
          )}
        </div>
        <MetaItem label="Strikes"  value={`${long_strike ?? '—'} / ${short_strike ?? '—'}`} />
        <MetaItem label="Expiry"   value={formatDate(expiry)} />
        <MetaItem label="DTE"      value={dte != null ? `${dte}d` : '—'} />
      </div>

      {/* ── Row 2: metrics ──────────────────────────────────────── */}
      <div style={{
        display: 'flex',
        gap: 20,
        alignItems: 'center',
        flexWrap: 'wrap',
        paddingTop: 8,
        borderTop: '1px solid #252a3a',
      }}>
        <MetaItem label="Entry"          value={entryLabel} />
        <MetaItem label="Max Profit"     value={fmt2(max_profit)}   color={EMERALD} />
        <MetaItem label="Max Loss"       value={fmt2(max_loss)}     color={DANGER} />
        <MetaItem label="Breakeven"      value={fmt2(breakeven)} />
        <MetaItem label="R:R"            value={reward_risk != null ? `${fmt2(reward_risk)}:1` : '—'} />
        <MetaItem label="Profit Trigger" value={profit_trigger}     color={EMERALD} />
        <MetaItem label="Stop Trigger"   value={stop_trigger}       color={AMBER} />
        <MetaItem label="Time Exit"      value={formatDate(time_exit_date)} />
      </div>
    </div>
  );
}
