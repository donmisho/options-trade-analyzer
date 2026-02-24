import { useApp } from '../context/AppContext';
import './PageShared.css';

export default function DirectionalPage() {
  const { activeSymbol } = useApp();

  return (
    <div className="page-card">
      <h2 className="page-title">
        Directional Compare —{' '}
        <span className="symbol-highlight">{activeSymbol}</span>
      </h2>
      <p className="page-placeholder">
        Strategy comparison engine connected. Thesis form, results table,
        formula transparency, and configuration panel will render here.
      </p>
      <div className="placeholder-hint">
        Try clicking a different symbol in the watchlist →
        the title above should update immediately.
      </div>
    </div>
  );
}
