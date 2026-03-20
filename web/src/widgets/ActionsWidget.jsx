/**
 * ActionsWidget — Phase 2.3
 *
 * Computes action alerts from open positions and displays them as cards.
 * Three alert types:
 *   1. Near target  — unrealized P&L >= profit_target_pct of entry_price
 *   2. Exit zone    — nearest DTE across legs <= dte_exit_threshold
 *   3. Health degraded — health_grade is D or F
 *
 * Props: { config: { id, type, title, settings: { profit_target_pct, dte_exit_threshold, health_alert_grade } }, isEditMode }
 */

import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getPositions } from '../api/client';

const STRATEGY_LABELS = {
  steady_paycheck: 'Steady Paycheck',
  weekly_grind:    'Weekly Grind',
  trend_rider:     'Trend Rider',
  lottery_ticket:  'Lottery Ticket',
};

function strategyLabel(key) {
  return STRATEGY_LABELS[key] || key || '—';
}

function parseDte(position) {
  // Try to extract nearest DTE from trade_structure legs
  const legs = position.trade_structure?.legs ?? [];
  const dtes = legs
    .map(l => {
      if (!l.expiration) return null;
      const exp = new Date(l.expiration);
      const now = new Date();
      return Math.round((exp - now) / (1000 * 60 * 60 * 24));
    })
    .filter(d => d != null);
  return dtes.length > 0 ? Math.min(...dtes) : null;
}

export default function ActionsWidget({ config, isEditMode }) {
  const settings = config.settings ?? {};
  const profitTargetPct   = settings.profit_target_pct    ?? 0.90;
  const dteExitThreshold  = settings.dte_exit_threshold   ?? 7;
  const healthAlertGrade  = settings.health_alert_grade   ?? 'D';

  const navigate = useNavigate();
  const [alerts, setAlerts]   = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await getPositions({ status: 'open' });
        const positions = data?.positions ?? [];
        const computed = [];

        const badGrades = ['D', 'F'];
        const alertGradeIndex = badGrades.indexOf(healthAlertGrade);
        const badGradeSet = new Set(badGrades.slice(alertGradeIndex >= 0 ? alertGradeIndex : 0));

        for (const pos of positions) {
          const entryPrice    = parseFloat(pos.entry_price)   || 0;
          const currentPnl    = parseFloat(pos.current_pnl)   ?? null;
          const currentPrice  = parseFloat(pos.current_price) ?? null;
          const dte           = parseDte(pos);
          const grade         = pos.health_grade;
          const label         = `${pos.symbol} — ${strategyLabel(pos.strategy_key)}`;

          // Near target
          if (currentPnl != null && entryPrice > 0) {
            const pnlPct = currentPnl / (entryPrice * 100);
            if (pnlPct >= profitTargetPct) {
              computed.push({
                key:     `${pos.position_id}-target`,
                type:    'target',
                badge:   'Near Target',
                color:   '#4ade80',
                label,
                sub:     `At ${Math.round(pnlPct * 100)}% of profit target · ${dte ?? '?'} DTE`,
                posId:   pos.position_id,
              });
            }
          }

          // Exit zone (DTE)
          if (dte != null && dte <= dteExitThreshold) {
            computed.push({
              key:   `${pos.position_id}-dte`,
              type:  'dte',
              badge: 'Exit Zone',
              color: '#facc15',
              label,
              sub:   `${dte} DTE — within exit threshold`,
              posId: pos.position_id,
            });
          }

          // Health degraded
          if (grade && badGradeSet.has(grade)) {
            computed.push({
              key:   `${pos.position_id}-health`,
              type:  'health',
              badge: `Health: ${grade}`,
              color: '#f87171',
              label,
              sub:   `Position health grade ${grade}`,
              posId: pos.position_id,
            });
          }
        }

        setAlerts(computed);
      } catch {
        // silently fail
      } finally {
        setLoading(false);
      }
    }
    load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config.id]);

  return (
    <div style={s.wrap}>
      <div style={s.header}>
        <span style={s.title}>{config.title}</span>
      </div>

      <div style={s.body}>
        {loading ? (
          <p style={s.muted}>Loading…</p>
        ) : alerts.length === 0 ? (
          <p style={s.muted}>No actions required today.</p>
        ) : (
          alerts.map(alert => (
            <div key={alert.key} style={s.alertCard}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <span style={{ ...s.badge, background: alert.color + '22', color: alert.color }}>
                  {alert.badge}
                </span>
                <span style={s.alertLabel}>{alert.label}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={s.alertSub}>{alert.sub}</span>
                <button style={s.viewBtn} onClick={() => navigate('/positions')}>
                  View →
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      <p style={s.note}>
        Action alerts computed from position data · Insight Engine wires in at Phase 3.x
      </p>
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
  header: {
    marginBottom: 10,
    flexShrink: 0,
  },
  title: {
    fontSize: 11,
    fontWeight: 700,
    color: '#6b7280',
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
  },
  body: {
    flex: 1,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  muted: {
    color: '#6b7280',
    fontSize: 13,
    margin: 0,
  },
  alertCard: {
    background: '#1a1d27',
    border: '1px solid #252a3a',
    borderRadius: 8,
    padding: '10px 12px',
  },
  badge: {
    fontSize: 11,
    fontWeight: 700,
    padding: '2px 8px',
    borderRadius: 4,
    flexShrink: 0,
  },
  alertLabel: {
    fontSize: 13,
    color: '#e4e7ef',
    fontWeight: 500,
  },
  alertSub: {
    fontSize: 12,
    color: '#6b7280',
  },
  viewBtn: {
    background: 'none',
    border: 'none',
    color: '#38bdf8',
    fontSize: 12,
    cursor: 'pointer',
    padding: 0,
    width: 'auto',
    flexShrink: 0,
  },
  note: {
    fontSize: 11,
    color: '#4b5563',
    margin: '8px 0 0',
    flexShrink: 0,
  },
};
