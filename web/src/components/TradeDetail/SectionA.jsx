import { formatDate } from '../../utils/formatDate';

// NOTE: Once TradeTypeBadge is built in the parallel session, replace this fallback with:
// import TradeTypeBadge from '../TradeTypeBadge';
// For now, render an inline badge using the same spec (9px bold, directional color).
const TradeTypeBadge = null;

function getTradeTypeDisplay(type) {
  if (!type) return { display: '', color: 'var(--text)' };
  const upper = type.toUpperCase();
  const isBull = upper.startsWith('BULL');
  const color = isBull ? 'var(--green)' : 'var(--red)';
  const bg = isBull ? 'rgba(74,222,128,0.15)' : 'rgba(248,113,113,0.15)';
  const display = type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  return { display, color, bg };
}

function getContextLabel(type) {
  if (!type) return '';
  const upper = type.toUpperCase();
  const isBull = upper.startsWith('BULL');
  const isDebit = upper.includes('DEBIT');
  const direction = isBull ? 'bullish' : 'bearish';
  const entry = isDebit ? 'you pay to enter' : 'you receive credit';
  return `(${direction} — ${entry})`;
}

const fieldStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: 2,
};

const labelStyle = {
  fontSize: 9,
  textTransform: 'uppercase',
  letterSpacing: '0.4px',
  color: 'var(--muted)',
  fontFamily: 'monospace',
};

const valueStyle = {
  fontSize: 12,
  fontWeight: 700,
  fontFamily: 'monospace',
};

function MetaField({ label, value, valueColor }) {
  return (
    <div style={fieldStyle}>
      <span style={labelStyle}>{label}</span>
      <span style={{ ...valueStyle, color: valueColor || 'var(--text)' }}>{value}</span>
    </div>
  );
}

export default function SectionA({ trade }) {
  if (!trade) return null;

  const {
    type, strikes, expiry, dte, entry, maxProfit, maxLoss,
    breakeven, rewardRisk, profitTrigger, stopTrigger, timeExit,
  } = trade;

  const { display, color: typeColor, bg: typeBg } = getTradeTypeDisplay(type);
  const contextLabel = getContextLabel(type);

  return (
    <div
      className="td-section-a-card"
      style={{
        border: '1px solid var(--border)',
        borderRadius: 4,
        padding: '10px 14px',
        display: 'flex',
        flexWrap: 'wrap',
        gap: 14,
        marginBottom: 12,
        alignItems: 'flex-start',
        fontFamily: 'monospace',
      }}
    >
      {/* Trade type badge */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {TradeTypeBadge ? (
          <TradeTypeBadge type={type} />
        ) : (
          <span
            style={{
              fontSize: 12,
              fontWeight: 700,
              background: typeBg,
              color: typeColor,
              padding: '2px 6px',
              borderRadius: 3,
              display: 'inline-block',
            }}
          >
            {display}
          </span>
        )}
        {contextLabel && (
          <span style={{ fontSize: 10, color: 'var(--muted)' }}>{contextLabel}</span>
        )}
      </div>

      {/* Metadata fields */}
      <MetaField label="Strikes" value={strikes || '—'} />
      <MetaField label="Expiry" value={formatDate(expiry)} />
      <MetaField label="DTE" value={dte != null ? `${dte}d` : '—'} />
      <MetaField
        label="Entry"
        value={
          entry != null
            ? `${Number(entry).toFixed(2)} debit (${(Number(entry) * 100).toFixed(2)} / contract)`
            : '—'
        }
      />
      <MetaField
        label="Max Profit"
        value={maxProfit != null ? Number(maxProfit).toFixed(2) : '—'}
        valueColor="var(--green)"
      />
      <MetaField
        label="Max Loss"
        value={maxLoss != null ? Number(maxLoss).toFixed(2) : '—'}
        valueColor="var(--red)"
      />
      <MetaField
        label="Breakeven"
        value={breakeven != null ? Number(breakeven).toFixed(2) : '—'}
      />
      <MetaField
        label="R:R"
        value={rewardRisk != null ? `${Number(rewardRisk).toFixed(2)}:1` : '—'}
      />
      <MetaField
        label="Profit Trigger"
        value={profitTrigger != null ? Number(profitTrigger).toFixed(2) : '—'}
        valueColor="var(--green)"
      />
      <MetaField
        label="Stop Trigger"
        value={stopTrigger != null ? Number(stopTrigger).toFixed(2) : '—'}
        valueColor="var(--red)"
      />
      <MetaField label="Time Exit" value={formatDate(timeExit)} />
    </div>
  );
}
