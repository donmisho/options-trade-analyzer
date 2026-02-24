/**
 * Toast — Temporary notification that slides up from the bottom-right.
 *
 * WHY a separate component?
 * The toast is used by many different actions (favorite, unfavorite,
 * symbol switch, price refresh). Putting the animation and styling
 * in one component keeps things DRY. The show/hide is controlled
 * by the AppContext toast state.
 */

import { useApp } from '../context/AppContext';
import './Toast.css';

export default function Toast() {
  const { toast } = useApp();

  return (
    <div className={`toast ${toast ? 'show' : ''}`}>
      <span className="toast-star">★</span>
      <span>{toast || ''}</span>
    </div>
  );
}
