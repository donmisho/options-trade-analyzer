/**
 * InsightCard — Renders one insight from the Insight Engine feed.
 *
 * Props:
 *   insight     {Object}   InsightResponse from GET /api/v1/insights
 *   onDismiss   {Function} called with insight.insight_id when Dismiss clicked
 *   onViewEntity {Function} called with action.route when a navigation action is clicked
 *
 * Severity → left border color:
 *   CRITICAL  #ef4444  (red)
 *   WARNING   #f97316  (orange)
 *   INFO      #3b82f6  (blue)
 */

const SEVERITY_CONFIG = {
  CRITICAL: { color: '#ef4444', icon: '⚠', label: 'CRITICAL' },
  WARNING:  { color: '#f97316', icon: '▲', label: 'WARNING' },
  INFO:     { color: '#3b82f6', icon: 'ℹ', label: 'INFO' },
};

function relativeTime(isoString) {
  if (!isoString) return '';
  const diff = Date.now() - new Date(isoString).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1)  return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24)   return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function InsightCard({ insight, onDismiss, onViewEntity }) {
  const cfg = SEVERITY_CONFIG[insight.severity] || SEVERITY_CONFIG.INFO;

  function handleAction(action) {
    if (action.action === 'dismiss') {
      onDismiss?.(insight.insight_id);
    } else if (action.route) {
      onViewEntity?.(action.route, insight.insight_id);
    }
  }

  return (
    <div
      style={{
        borderLeft: `3px solid ${cfg.color}`,
        background: '#1a1d26',
        borderRadius: '0 6px 6px 0',
        padding: '12px 14px',
        marginBottom: 8,
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{ color: cfg.color, fontSize: 14 }}>{cfg.icon}</span>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: cfg.color,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
          }}
        >
          {cfg.label}
        </span>
        <span
          style={{
            flex: 1,
            fontSize: 13,
            fontWeight: 600,
            color: '#e2e8f0',
            marginLeft: 4,
          }}
        >
          {insight.title}
        </span>
      </div>

      {/* Body */}
      <p
        style={{
          margin: '0 0 10px 0',
          fontSize: 13,
          color: '#94a3b8',
          lineHeight: 1.5,
        }}
      >
        {insight.body}
      </p>

      {/* Action buttons + timestamp */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {(insight.recommended_actions || []).map((action, i) => (
          <button
            key={i}
            onClick={() => handleAction(action)}
            style={{
              padding: '4px 10px',
              fontSize: 11,
              fontWeight: 600,
              borderRadius: 4,
              border: action.action === 'dismiss'
                ? '1px solid #374151'
                : `1px solid ${cfg.color}60`,
              background: action.action === 'dismiss' ? 'transparent' : `${cfg.color}18`,
              color: action.action === 'dismiss' ? '#6b7280' : cfg.color,
              cursor: 'pointer',
              letterSpacing: '0.04em',
            }}
          >
            {action.label}
          </button>
        ))}
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#4b5563' }}>
          {relativeTime(insight.created_at)}
        </span>
      </div>
    </div>
  );
}
