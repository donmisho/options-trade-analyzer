/**
 * Toast — Shared notification system.
 *
 * Exports:
 *   ToastProvider  — wraps the app, renders the fixed toast container
 *   useToast       — hook returning { showToast }
 *   default Toast  — no-op kept for Layout.jsx backward compat
 *
 * API:
 *   showToast('simple message')
 *   showToast({ message, actionText, onAction, href, linkLabel, duration })
 *
 * Toasts auto-dismiss after 4 seconds (or custom duration).
 * Multiple toasts stack vertically (gap: 8px), newest at top.
 */

import { createContext, useContext, useState, useCallback } from 'react';
import './Toast.css';

// ─── Context ──────────────────────────────────────────────────────────────────

const ToastContext = createContext({ showToast: () => {} });

// ─── Provider ─────────────────────────────────────────────────────────────────

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const showToast = useCallback((msgOrObj) => {
    if (msgOrObj === null) {
      setToasts([]);
      return;
    }
    const id = Date.now() + Math.random();
    const t = typeof msgOrObj === 'string'
      ? { id, message: msgOrObj }
      : { id, ...msgOrObj };
    setToasts(prev => [...prev, t]);
    setTimeout(() => {
      setToasts(prev => prev.filter(item => item.id !== id));
    }, t.duration ?? 4000);
  }, []);

  const dismiss = useCallback((id) => {
    setToasts(prev => prev.filter(item => item.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="toast-container">
        {toasts.map(t => (
          <ToastItem key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useToast() {
  return useContext(ToastContext);
}

// ─── Toast item ───────────────────────────────────────────────────────────────

function ToastItem({ toast, onDismiss }) {
  const handleAction = (e) => {
    e.stopPropagation();
    toast.onAction?.();
    onDismiss();
  };

  return (
    <div className="toast show" onClick={onDismiss}>
      <span className="toast-msg">{toast.message}</span>
      {toast.actionText && toast.onAction && (
        <button className="toast-action" onClick={handleAction}>
          {toast.actionText}
        </button>
      )}
      {!toast.onAction && toast.href && toast.linkLabel && (
        <a
          href={toast.href}
          className="toast-action"
          onClick={e => e.stopPropagation()}
        >
          {toast.linkLabel}
        </a>
      )}
    </div>
  );
}

// ─── Default export (no-op for backward compat) ───────────────────────────────
// Layout.jsx imports this; rendering is now handled by ToastProvider.

export default function Toast() {
  return null;
}
