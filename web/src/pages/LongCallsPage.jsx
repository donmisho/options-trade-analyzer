import { useApp } from '../context/AppContext';
import './PageShared.css';

export default function LongCallsPage() {
  const { activeSymbol } = useApp();

  return (
    <div className="page-card">
      <h2 className="page-title">
        Long Call Analysis —{' '}
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
