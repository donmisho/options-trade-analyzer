/**
 * Toast — Temporary notification that slides up from the bottom-right.
 *
 * Controlled by AppContext toast state: { message, href?, linkLabel? }
 * showToast('text') and showToast({ message, href, linkLabel }) both work.
 */

import { useApp } from '../context/AppContext';
import './Toast.css';

export default function Toast() {
  const { toast, showToast } = useApp();
  const msg = toast?.message ?? '';
  const href = toast?.href;
  const linkLabel = toast?.linkLabel;

  return (
    <div
      className={`toast ${toast ? 'show' : ''}`}
      onClick={() => showToast(null)}
    >
      <span className="toast-star">★</span>
      <span>{msg}</span>
      {href && linkLabel && (
        <a
          href={href}
          style={{ color: '#2dd4bf', fontSize: 10, marginLeft: 6, textDecoration: 'underline' }}
          onClick={e => e.stopPropagation()}
        >
          {linkLabel}
        </a>
      )}
    </div>
  );
}
