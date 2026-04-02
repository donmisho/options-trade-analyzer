/**
 * Toast — Shared notification system.
 *
 * Exports:
 *   ToastProvider  — wraps the app (inside BrowserRouter), renders the fixed toast container
 *   useToast       — hook returning { showToast }
 *   default Toast  — no-op kept for Layout.jsx backward compat
 *
 * API:
 *   showToast('simple message')
 *   showToast({ type, message, link: { text, to }, duration })
 *   showToast({ message, actionText, onAction, href, linkLabel, duration })
 *
 * type variants: 'success' | 'error' | 'info'  (left border color)
 * link.to: React Router navigate path (useNavigate — requires BrowserRouter ancestor)
 * href: plain anchor fallback (legacy)
 *
 * Toasts auto-dismiss after 4 seconds (or custom duration).
 * Multiple toasts stack vertically (gap: 8px), newest at top.
 */

import { createContext, useContext, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
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
// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  return useContext(ToastContext);
}

// ─── Toast item ───────────────────────────────────────────────────────────────

function ToastItem({ toast, onDismiss }) {
  const navigate = useNavigate();

  const typeClass = toast.type ? `toast-${toast.type}` : '';

  // Normalize link from both formats:
  //   link: { text, to }   ← new format (React Router navigation)
  //   linkLabel + href      ← legacy format (plain anchor)
  //   actionText + onAction ← legacy format (callback)
  const linkText = toast.link?.text ?? toast.linkLabel ?? null;
  const linkTo   = toast.link?.to   ?? null;
  const linkHref = toast.href ?? null;
  const hasLink  = linkText && (linkTo || linkHref || toast.onAction);

  function handleLinkClick(e) {
    e.stopPropagation();
    if (toast.onAction) {
      toast.onAction();
    } else if (linkTo) {
      navigate(linkTo);
    }
    onDismiss();
  }

  return (
    <div className={`toast show ${typeClass}`} onClick={onDismiss}>
      <span className="toast-msg">{toast.message}</span>
      {hasLink && (
        linkHref && !linkTo && !toast.onAction ? (
          <a
            href={linkHref}
            className="toast-action"
            onClick={e => e.stopPropagation()}
          >
            {linkText}
          </a>
        ) : (
          <button className="toast-action" onClick={handleLinkClick}>
            {linkText}
          </button>
        )
      )}
    </div>
  );
}

// ─── Default export (no-op for backward compat) ───────────────────────────────
// Layout.jsx imports this; rendering is now handled by ToastProvider.

export default function Toast() {
  return null;
}
