/**
 * VerticalsPage — Vertical Spread analysis screen.
 *
 * This is a Layer 1 placeholder that proves the routing and
 * symbol state work correctly. In the next step (Layer 2),
 * we'll add the form, API call, results table with StarButtons,
 * formula widget, and config panel.
 */

import { useApp } from '../context/AppContext';
import './PageShared.css';

export default function VerticalsPage() {
  const { activeSymbol } = useApp();

  return (
    <div className="page-card">
      <h2 className="page-title">
        Vertical Spread Analysis —{' '}
        <span className="symbol-highlight">{activeSymbol}</span>
      </h2>
      <p className="page-placeholder">
        Analysis engine connected. Results table, formula transparency,
        and configuration panel will render here in the next build step.
      </p>
      <div className="placeholder-hint">
        Try clicking a different symbol in the watchlist →
        the title above should update immediately.
      </div>
    </div>
  );
}
