/**
 * StrategyProfilePage — OTA-184
 *
 * Route: /strategies/:slug  (e.g. /strategies/steady-paycheck)
 *
 * Sections:
 *   1. Header      — name, tagline, DTE range, spread type
 *   2. Parameters  — configSchema defaults in a card grid
 *   3. Scoring Weights — strategy's priority factors
 *   4. Backtest    — placeholder (data in Phase 3.3)
 */

import { useParams } from 'react-router-dom';
import { STRATEGY_CONFIGS } from '../strategy-configs/index';
import { mono } from '../styles/tokens';

// ─── Design tokens ────────────────────────────────────────────────────────────

const BG      = '#0D1117';
const SURFACE = '#141722';
const BORDER  = '#252a3a';
const TEXT    = '#e4e7ef';
const DIM     = '#8b90a0';
const MUTED   = '#555b6e';
const EMERALD = '#00C896';
const VIOLET  = '#8B5CF6';
const AMBER   = '#F5A623';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatTradeStructure(ts) {
  if (!ts) return '—';
  return ts.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatParamValue(field) {
  if (field.type === 'toggle') {
    return field.default === 1 ? 'On' : 'Off';
  }
  const val = field.default != null ? field.default : '—';
  const unit = field.unit ?? '';
  return `${val}${unit ? '\u00a0' + unit : ''}`;
}

function formatParamRange(field) {
  if (field.type === 'toggle') return null;
  if (field.min == null || field.max == null) return null;
  const unit = field.unit ?? '';
  return `${field.min}${unit ? '\u00a0' + unit : ''} – ${field.max}${unit ? '\u00a0' + unit : ''}`;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function SectionLabel({ children }) {
  return (
    <div style={{
      fontFamily: mono,
      fontSize: 9,
      fontWeight: 400,
      color: MUTED,
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      marginBottom: 12,
    }}>
      {children}
    </div>
  );
}

function ParamCard({ field }) {
  const value = formatParamValue(field);
  const range = formatParamRange(field);

  return (
    <div style={{
      backgroundColor: SURFACE,
      border: `1px solid ${BORDER}`,
      borderRadius: 6,
      padding: '10px 14px',
    }}>
      <div style={{
        fontFamily: mono,
        fontSize: 9,
        color: MUTED,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        marginBottom: 6,
      }}>
        {field.label}
      </div>
      <div style={{
        fontFamily: mono,
        fontSize: 16,
        fontWeight: 700,
        color: TEXT,
        marginBottom: range ? 4 : 0,
      }}>
        {value}
      </div>
      {range && (
        <div style={{ fontFamily: mono, fontSize: 9, color: MUTED }}>
          Range: {range}
        </div>
      )}
    </div>
  );
}

function WeightRow({ label, weight }) {
  const pct = Math.round(weight * 100);
  const barWidth = `${pct}%`;
  const barColor = pct >= 30 ? EMERALD : pct >= 20 ? VIOLET : AMBER;

  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        marginBottom: 4,
      }}>
        <span style={{ fontFamily: mono, fontSize: 11, color: TEXT }}>
          {label.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
        </span>
        <span style={{ fontFamily: mono, fontSize: 11, fontWeight: 700, color: barColor }}>
          {pct}%
        </span>
      </div>
      <div style={{
        height: 4,
        borderRadius: 2,
        backgroundColor: `${BORDER}`,
        overflow: 'hidden',
      }}>
        <div style={{
          height: '100%',
          width: barWidth,
          borderRadius: 2,
          backgroundColor: barColor,
          transition: 'width 0.3s ease',
        }} />
      </div>
    </div>
  );
}

// ─── Not found ────────────────────────────────────────────────────────────────

function NotFound({ slug }) {
  return (
    <div style={{
      padding: 40,
      textAlign: 'center',
      fontFamily: mono,
      color: MUTED,
    }}>
      <div style={{ fontSize: 14, marginBottom: 8 }}>Strategy not found</div>
      <div style={{ fontSize: 11, color: MUTED }}>
        No strategy config for slug: <span style={{ color: AMBER }}>{slug}</span>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function StrategyProfilePage() {
  const { slug } = useParams();
  const config = STRATEGY_CONFIGS[slug];

  if (!config) return <NotFound slug={slug} />;

  const dteRange = (config.dte_min != null && config.dte_max != null)
    ? `${config.dte_min} – ${config.dte_max} DTE`
    : null;

  const tradeStructure = formatTradeStructure(config.trade_structure);
  const weights        = config.scoring_weights ?? {};
  const schema         = config.configSchema ?? [];

  return (
    <div style={{
      backgroundColor: BG,
      minHeight: '100%',
      padding: '24px 28px',
      maxWidth: 900,
    }}>
      {/* ── 1. Header ────────────────────────────────────────────── */}
      <div style={{
        backgroundColor: SURFACE,
        border: `1px solid ${BORDER}`,
        borderRadius: 8,
        padding: '18px 22px',
        marginBottom: 20,
      }}>
        <h1 style={{
          margin: '0 0 6px',
          fontFamily: mono,
          fontSize: 22,
          fontWeight: 700,
          color: TEXT,
          letterSpacing: '-0.01em',
        }}>
          {config.label}
        </h1>

        <p style={{
          margin: '0 0 14px',
          fontFamily: mono,
          fontSize: 12,
          color: DIM,
        }}>
          {config.description}
        </p>

        <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
          {dteRange && (
            <Chip label="DTE Range" value={dteRange} />
          )}
          <Chip label="Structure" value={tradeStructure} />
          {config.non_applicable_reason && (
            <Chip label="Requirement" value={config.non_applicable_reason} />
          )}
        </div>
      </div>

      {/* ── 2. Parameters ────────────────────────────────────────── */}
      {schema.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <SectionLabel>Parameters</SectionLabel>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
            gap: 10,
          }}>
            {schema.map(field => (
              <ParamCard key={field.key} field={field} />
            ))}
          </div>
        </div>
      )}

      {/* ── 3. Scoring Weights ───────────────────────────────────── */}
      {Object.keys(weights).length > 0 && (
        <div style={{
          backgroundColor: SURFACE,
          border: `1px solid ${BORDER}`,
          borderRadius: 8,
          padding: '16px 20px',
          marginBottom: 20,
        }}>
          <SectionLabel>Scoring Weights</SectionLabel>
          {Object.entries(weights).map(([key, w]) => (
            <WeightRow key={key} label={key} weight={w} />
          ))}
        </div>
      )}

      {/* ── 4. Backtest Placeholder ──────────────────────────────── */}
      <div style={{
        border: `1px dashed ${MUTED}`,
        borderRadius: 8,
        padding: '24px 20px',
        textAlign: 'center',
      }}>
        <div style={{
          fontFamily: mono,
          fontSize: 11,
          color: MUTED,
        }}>
          Backtest data available in Phase 3.3
        </div>
      </div>
    </div>
  );
}

// ─── Chip helper ──────────────────────────────────────────────────────────────

function Chip({ label, value }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{
        fontFamily: mono,
        fontSize: 8,
        color: MUTED,
        textTransform: 'uppercase',
        letterSpacing: '0.07em',
      }}>
        {label}
      </span>
      <span style={{
        fontFamily: mono,
        fontSize: 11,
        color: TEXT,
        fontWeight: 500,
      }}>
        {value}
      </span>
    </div>
  );
}
