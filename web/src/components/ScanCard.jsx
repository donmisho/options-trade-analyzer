/**
 * ScanCard — Displays a single symbol's scan result on the Security Strategies page.
 *
 * Props:
 *   symbol, description, price, change, changePercent, volume, signal, isNew,
 *   strategies: [{key, label, score}], signalSummary, ivRank, onClick
 */

import { useState, useRef, useEffect } from 'react';
import { C, mono } from '../styles/tokens';
import { SCORECARD_STRATEGIES } from '../strategy-configs/index';
import { formatRelativeTime } from '../lib/relativeTime';
import './ScanCard.css';

const STRATEGY_META = Object.fromEntries(
  SCORECARD_STRATEGIES.map(cfg => [cfg.key, { color: cfg.color_text }])
);

const SIGNAL_BADGE = {
  BULLISH: { bg: 'rgba(74,222,128,0.15)',  color: '#4ade80' },
  BEARISH: { bg: 'rgba(248,113,113,0.15)', color: '#f87171' },
  MIXED:   { bg: 'rgba(245,158,11,0.15)',  color: '#f59e0b' },
  NEUTRAL: { bg: 'rgba(139,148,158,0.15)', color: '#8b949e' },
};

function scoreColor(score) {
  if (score >= 70) return '#4ade80';
  if (score >= 40) return '#f59e0b';
  return '#f87171';
}

function formatVolume(v) {
  if (v == null) return null;
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
  if (v >= 1_000) return (v / 1_000).toFixed(1) + 'K';
  return String(v);
}

export default function ScanCard({
  symbol, description, price, change, changePercent, volume,
  signal, isNew, strategies = [], signalSummary, ivRank, scannedAt, onClick, onRemove,
}) {
  const [hovered, setHovered] = useState(false);
  const nameRef = useRef(null);
  const [isTruncated, setIsTruncated] = useState(false);

  useEffect(() => {
    const el = nameRef.current;
    if (el) setIsTruncated(el.scrollWidth > el.clientWidth);
  }, [description]);

  const sig = (signal || 'NEUTRAL').toUpperCase();
  const badge = SIGNAL_BADGE[sig] || SIGNAL_BADGE.NEUTRAL;
  const isPositive = (change ?? 0) >= 0;

  // IV rank: backend may return decimal (0.28) or percentage (28.0)
  const ivDisplay = ivRank != null
    ? (ivRank < 1.5 ? (ivRank * 100).toFixed(2) : Number(ivRank).toFixed(2)) + '%'
    : null;

  const summaryLine = [
    signalSummary || null,
    ivDisplay ? `IV rank ${ivDisplay}` : null,
  ].filter(Boolean).join(' · ');

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: 'relative',
        border: `1px solid ${hovered ? 'rgba(45,212,191,0.3)' : C.border}`,
        borderRadius: 6,
        padding: '12px',
        cursor: 'pointer',
        backgroundColor: C.card,
        transition: 'border-color 0.15s',
        userSelect: 'none',
      }}
    >
      {/* ── Remove button (× — hover only, watchlist source only) ── */}
      {onRemove && hovered && (
        <button
          className="scan-remove-btn"
          onClick={e => { e.stopPropagation(); onRemove(); }}
          style={{
            position: 'absolute',
            top: 6,
            right: 8,
            background: 'none',
            border: 'none',
            color: C.textDim,
            fontSize: 16,
            lineHeight: 1,
            cursor: 'pointer',
            padding: '0 2px',
            fontFamily: mono,
            zIndex: 1,
          }}
          title={`Remove ${symbol} from watchlist`}
        >×</button>
      )}

      {/* ── Header: symbol · signal badge · NEW badge · description ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, minWidth: 0 }}>
        <span style={{ fontSize: 14, fontWeight: 700, color: '#e6edf3', fontFamily: mono, flexShrink: 0 }}>
          {symbol}
        </span>
        <span style={{
          fontSize: 9, fontWeight: 700, fontFamily: mono,
          padding: '2px 5px', borderRadius: 3,
          background: badge.bg, color: badge.color,
          flexShrink: 0,
        }}>
          {sig}
        </span>
        {isNew && (
          <span style={{
            fontSize: 8, fontWeight: 700, fontFamily: mono,
            padding: '1px 4px', borderRadius: 3,
            background: 'rgba(45,212,191,0.2)', color: '#2dd4bf',
            flexShrink: 0,
          }}>
            NEW
          </span>
        )}
        {description && (
          <span
            ref={nameRef}
            className="scan-card-name"
            style={{
              fontSize: 10,
              fontWeight: 400,
              color: 'var(--muted)',
              fontFamily: mono,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              flex: 1,
              minWidth: 0,
              position: 'relative',
              cursor: 'default',
            }}
          >
            {description}
            {isTruncated && (
              <span
                className="scan-card-name-tooltip"
                style={{
                  display: 'none',
                  position: 'absolute',
                  bottom: '100%',
                  left: '50%',
                  transform: 'translateX(-50%)',
                  backgroundColor: 'var(--bg3, #21262d)',
                  border: '1px solid var(--border, #30363d)',
                  fontSize: 9,
                  fontWeight: 400,
                  padding: '3px 8px',
                  borderRadius: 3,
                  whiteSpace: 'nowrap',
                  marginBottom: 4,
                  zIndex: 10,
                  color: 'var(--text, #e6edf3)',
                  pointerEvents: 'none',
                }}
              >
                {description}
              </span>
            )}
          </span>
        )}
      </div>

      {/* ── Price line ── */}
      <div style={{ fontSize: 11, fontFamily: mono, color: '#8b949e', marginBottom: scannedAt ? 4 : 10 }}>
        {price != null ? price.toFixed(2) : '—'}
        {change != null && (
          <>
            <span style={{ color: isPositive ? '#4ade80' : '#f87171', marginLeft: 6 }}>
              {isPositive ? '+' : ''}{change.toFixed(2)}
            </span>
            <span style={{ color: isPositive ? '#4ade80' : '#f87171', marginLeft: 2 }}>
              ({isPositive ? '+' : ''}{(changePercent ?? 0).toFixed(2)}%)
            </span>
          </>
        )}
        {volume != null && (
          <span style={{ marginLeft: 6 }}>{formatVolume(volume)}</span>
        )}
      </div>

      {/* ── Last scanned indicator ── */}
      {scannedAt && formatRelativeTime(scannedAt) && (
        <div style={{ fontSize: 9, fontFamily: mono, color: '#8b949e', marginBottom: 10 }}>
          Last scanned {formatRelativeTime(scannedAt)}
        </div>
      )}

      {/* ── Strategy score bars ── */}
      {strategies.filter(s => (s.score ?? null) !== null).map(s => {
        const key = s.key ?? s.strategy_key;
        const meta = STRATEGY_META[key] || { color: '#8b949e' };
        const score = s.score ?? 0;
        return (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
            <span style={{
              fontSize: 10, color: '#8b949e', fontFamily: mono,
              width: 90, flexShrink: 0,
              overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis',
            }}>
              {s.label || key}
            </span>
            <div style={{
              flex: 1, height: 3, borderRadius: 2,
              background: C.border, overflow: 'hidden',
            }}>
              <div style={{
                width: `${Math.min(100, Math.max(0, score))}%`,
                height: '100%',
                borderRadius: 2,
                background: meta.color,
              }} />
            </div>
            <span style={{
              fontSize: 11, fontWeight: 700, fontFamily: mono,
              color: scoreColor(score),
              width: 38, textAlign: 'right', flexShrink: 0,
            }}>
              {score.toFixed(2)}
            </span>
          </div>
        );
      })}

      {/* ── Signal summary ── */}
      {summaryLine && (
        <div style={{
          fontSize: 10, fontStyle: 'italic', color: '#8b949e',
          fontFamily: mono, marginTop: 6,
        }}>
          {summaryLine}
        </div>
      )}
    </div>
  );
}
