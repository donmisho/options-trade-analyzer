/**
 * StartupProgress — 6-step startup checklist.
 *
 * Pure display component — parents (LoginPage, Layout) drive state via
 * useStartupProgress hook or local state.
 *
 * Props:
 *   steps:        Array<{ id, label, status, elapsed, hint }>
 *                 status: 'pending' | 'active' | 'complete' | 'warning' | 'error'
 *   totalElapsed: number (seconds, shown as running total)
 *   visible:      boolean — false triggers CSS fade-out
 *   onRetry:      function | null — shown when any step has 'error' status
 */

import { useState } from 'react';

function iconFor(step) {
  // 'ready' step gets brand teal on complete
  if (step.id === 'ready' && step.status === 'complete') {
    return { icon: '✓', colorVar: 'var(--teal)', pulse: false };
  }
  switch (step.status) {
    case 'active':   return { icon: '●', colorVar: 'var(--amber)', pulse: true };
    case 'complete': return { icon: '✓', colorVar: 'var(--green)', pulse: false };
    case 'warning':  return { icon: '⚠', colorVar: 'var(--amber)', pulse: false };
    case 'error':    return { icon: '✗', colorVar: 'var(--red)',   pulse: false };
    default:         return { icon: '○', colorVar: 'var(--muted)', pulse: false };
  }
}

export default function StartupProgress({ steps, totalElapsed, visible, onRetry, children }) {
  const hasError = steps.some(s => s.status === 'error');

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '60vh',
      opacity: visible ? 1 : 0,
      transition: 'opacity 300ms ease-out',
      pointerEvents: visible ? 'auto' : 'none',
    }}>
      <div style={{
        background: 'var(--bg)',
        border: '1px solid var(--border)',
        borderRadius: 4,
        padding: '16px 24px',
        maxWidth: 360,
        width: '100%',
        fontFamily: 'monospace',
      }}>

        {steps.map(step => {
          const { icon, colorVar, pulse } = iconFor(step);
          return (
            <div key={step.id} style={{ display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '6px 0' }}>
                <span style={{
                  fontSize: 14,
                  color: colorVar,
                  width: 16,
                  textAlign: 'center',
                  flexShrink: 0,
                  fontWeight: (step.status === 'complete' || step.status === 'warning') ? 700 : 400,
                  animation: pulse ? 'ota-pulse 1.5s ease-in-out infinite' : 'none',
                }}>
                  {icon}
                </span>
                <span style={{
                  fontSize: 12,
                  color: step.status === 'pending' ? 'var(--muted)' : 'var(--text)',
                  flex: 1,
                  fontFamily: 'monospace',
                }}>
                  {step.label}
                </span>
                {step.elapsed !== null && (
                  <span style={{
                    fontSize: 11,
                    color: 'var(--muted)',
                    fontFamily: 'monospace',
                    flexShrink: 0,
                  }}>
                    {step.elapsed.toFixed(1)}s
                  </span>
                )}
              </div>

              {step.hint && (
                <div style={{
                  fontSize: 11,
                  color: 'var(--muted)',
                  fontFamily: 'monospace',
                  paddingLeft: 28,
                  paddingBottom: 4,
                  maxWidth: 300,
                }}>
                  {step.hint}
                </div>
              )}
            </div>
          );
        })}

        {/* Services panel (or other inline content) injected by parent */}
        {children && (
          <div style={{ marginTop: 4 }}>
            {children}
          </div>
        )}

        {/* Total elapsed timer */}
        <div style={{
          marginTop: 12,
          fontSize: 11,
          color: 'var(--muted)',
          fontFamily: 'monospace',
          textAlign: 'center',
        }}>
          Total: {totalElapsed.toFixed(1)}s
        </div>

        {/* Retry button — only when a step has errored */}
        {hasError && onRetry && (
          <div style={{ marginTop: 12, textAlign: 'center' }}>
            <RetryButton onClick={onRetry} />
          </div>
        )}

      </div>
    </div>
  );
}

function RetryButton({ onClick }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: '7px 20px',
        background: 'none',
        border: `1px solid ${hovered ? 'var(--teal)' : 'var(--muted)'}`,
        borderRadius: 4,
        color: hovered ? 'var(--teal)' : 'var(--text)',
        fontFamily: 'monospace',
        fontSize: 12,
        cursor: 'pointer',
        transition: 'border-color 150ms, color 150ms',
      }}
    >
      Retry
    </button>
  );
}
