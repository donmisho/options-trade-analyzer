/**
 * RefreshConfirmDialog — Inline confirmation panel for batch position refresh.
 *
 * Props:
 *   positionCount — number of positions to be refreshed
 *   onConfirm     — called when user confirms
 *   onCancel      — called when user cancels
 *   isOpen        — renders null when false
 *
 * OTA-374
 */

const RefreshConfirmDialog = ({ positionCount, onConfirm, onCancel, isOpen }) => {
  if (!isOpen) return null;

  return (
    <div style={{
      background: 'rgba(0,0,0,0.6)',
      border: '1px solid var(--border, #30363d)',
      borderRadius: 6,
      padding: 20,
      maxWidth: 400,
      margin: '12px 0',
    }}>
      <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8, color: 'var(--text, #e6edf3)' }}>
        Refresh {positionCount} positions?
      </div>
      <div style={{
        fontSize: 10, color: '#c9d1d9', lineHeight: 1.5, marginBottom: 12,
      }}>
        This will trigger {positionCount} Claude API calls to update scores,
        synopses, and exit levels for all positions matching your current filter.
        Each position will update as its call returns.
      </div>
      <div style={{ display: 'flex', gap: 10 }}>
        <button onClick={onConfirm} style={{
          background: 'rgba(45,212,191,0.1)',
          border: '1px solid rgba(45,212,191,0.4)',
          color: 'var(--teal, #2dd4bf)', padding: '7px 16px', borderRadius: 4,
          fontSize: 11, fontFamily: 'monospace', cursor: 'pointer', width: 'auto',
        }}>Confirm refresh</button>
        <button onClick={onCancel} style={{
          background: 'transparent',
          border: '1px solid var(--border, #30363d)',
          color: 'var(--muted, #8b949e)', padding: '7px 14px', borderRadius: 4,
          fontSize: 11, fontFamily: 'monospace', cursor: 'pointer', width: 'auto',
        }}>Cancel</button>
      </div>
    </div>
  );
};

export default RefreshConfirmDialog;
