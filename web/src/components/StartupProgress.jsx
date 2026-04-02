/**
 * StartupProgress — Inline startup status widget shown in the main content area.
 *
 * Pure display component — no business logic. Layout.jsx drives the step state machine
 * and passes steps + visible as props.
 *
 * Props:
 *   steps:   Array of { id, label, status, hint }
 *            status: 'pending' | 'active' | 'success' | 'warning' | 'error'
 *            hint:   optional string shown below label on warning/error
 *   visible: boolean — false triggers the fade-out transition
 *   onRetry: function — called when user clicks Retry after a backend error
 */

const TEAL  = '#2dd4bf';
const GREEN = '#4ade80';
const AMBER = '#fbbf24';
const RED   = '#f87171';
const MUTED = '#8b949e';
const TEXT  = '#e6edf3';

const STATUS_ICON = {
  pending: { icon: '○', color: MUTED },
  active:  { icon: '◉', color: AMBER, pulse: true },
  success: { icon: '✓', color: GREEN },
  warning: { icon: '!', color: AMBER },
  error:   { icon: '✗', color: RED },
};

// Final "Ready" step uses teal check
function iconFor(step) {
  if (step.id === 'ready' && step.status === 'success') {
    return { icon: '✓', color: TEAL, pulse: false };
  }
  return STATUS_ICON[step.status] || STATUS_ICON.pending;
}

export default function StartupProgress({ steps, visible, onRetry }) {
  const hasBackendError = steps.find(s => s.id === 'backend' && s.status === 'error');

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '70vh',
      opacity: visible ? 1 : 0,
      transition: 'opacity 300ms ease-out',
      pointerEvents: visible ? 'auto' : 'none',
    }}>
      <div style={{ textAlign: 'center' }}>

        {/* App name */}
        <div style={{
          fontSize: 18, fontWeight: 700, color: TEAL,
          fontFamily: 'monospace', marginBottom: 6,
        }}>
          Options Analyzer
        </div>

        {/* Subtitle */}
        <div style={{
          fontSize: 12, color: MUTED, fontFamily: 'monospace', marginBottom: 28,
        }}>
          Starting up…
        </div>

        {/* Step list */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, alignItems: 'flex-start' }}>
          {steps.map(step => {
            const { icon, color, pulse } = iconFor(step);
            return (
              <div key={step.id} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{
                    fontSize: 14, color, width: 16, textAlign: 'center', flexShrink: 0,
                    animation: pulse ? 'ota-pulse 1.2s ease-in-out infinite' : 'none',
                  }}>
                    {icon}
                  </span>
                  <span style={{ fontSize: 13, color: TEXT, fontFamily: 'monospace' }}>
                    {step.label}
                  </span>
                </div>
                {step.hint && (
                  <div style={{
                    fontSize: 11, color: MUTED, fontFamily: 'monospace',
                    paddingLeft: 26, maxWidth: 320,
                  }}>
                    {step.hint}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Retry button — only shown when backend step failed */}
        {hasBackendError && (
          <button
            onClick={onRetry}
            style={{
              marginTop: 24,
              padding: '7px 20px',
              background: 'none',
              border: `1px solid ${MUTED}`,
              borderRadius: 4,
              color: TEXT,
              fontFamily: 'monospace',
              fontSize: 12,
              cursor: 'pointer',
              transition: 'border-color 150ms, color 150ms',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = TEAL; e.currentTarget.style.color = TEAL; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = MUTED; e.currentTarget.style.color = TEXT; }}
          >
            Retry
          </button>
        )}

      </div>
    </div>
  );
}
