import { formatDate } from '../../utils/formatDate';
import TradeTypeBadge from '../TradeTypeBadge';


const SPREAD_INFO = {
  bull_call: { direction: 'bullish', entry: 'you pay debit' },
  bear_put:  { direction: 'bearish', entry: 'you pay debit' },
  bull_put:  { direction: 'bullish', entry: 'you receive credit' },
  bear_call: { direction: 'bearish', entry: 'you receive credit' },
  long_call: { direction: 'bullish', entry: 'you pay premium' },
  long_put:  { direction: 'bearish', entry: 'you pay premium' },
};

function getContextLabel(type) {
  if (!type) return '';
  const key = type.toLowerCase().replace(/-/g, '_');
  const info = SPREAD_INFO[key];
  if (!info) return '';
  return `(${info.direction} — ${info.entry})`;
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
        <TradeTypeBadge type={type} />
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
