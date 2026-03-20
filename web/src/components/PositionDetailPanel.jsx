/**
 * PositionDetailPanel — Expansion row showing leg details and AI scores.
 *
 * Rendered inside a <td colSpan> below an expanded position row.
 * Data comes from the PositionResponse object returned by the API.
 *
 * Handles both structured leg arrays (trade_structure.legs) and
 * flat trade_structure dicts (e.g. from vertical spread trades).
 *
 * Score format: ##.00
 * No $ prefix anywhere.
 */

import { PositionHealthBadge } from './PositionHealthBadge';

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtScore(val) {
  if (val == null) return '—';
  return Number(val).toFixed(2);
}

function verdictColor(verdict) {
  if (verdict === 'EXECUTE') return '#22c55e';
  if (verdict === 'WAIT')    return '#eab308';
  if (verdict === 'PASS')    return '#6b7280';
  return 'var(--text-muted)';
}

// ── Leg display ────────────────────────────────────────────────────────────

function LegRow({ leg }) {
  const side   = (leg.side || leg.action || '').toUpperCase();
  const type   = (leg.option_type || leg.type || '').toUpperCase();
  const strike = leg.strike != null ? Number(leg.strike).toFixed(2) : '—';
  const exp    = leg.expiration ? String(leg.expiration).slice(0, 10) : '—';
  const qty    = leg.contracts ?? leg.quantity ?? 1;

  return (
    <div className="pos-detail-leg">
      <span className={`pos-detail-leg-side ${side === 'SHORT' ? 'pos-leg-short' : 'pos-leg-long'}`}>
        {side}
      </span>
      <span className="pos-detail-leg-type">{type}</span>
      <span className="pos-detail-leg-strike mono">{strike}</span>
      <span className="pos-detail-leg-exp mono text-muted">{exp}</span>
      <span className="pos-detail-leg-qty mono text-muted">×{qty}</span>
    </div>
  );
}

function LegsSection({ tradeStructure }) {
  const legs = tradeStructure?.legs;

  if (legs && Array.isArray(legs) && legs.length > 0) {
    return (
      <div className="pos-detail-section">
        <div className="pos-detail-label">Legs</div>
        {legs.map((leg, i) => <LegRow key={i} leg={leg} />)}
      </div>
    );
  }

  // Flat trade structure (vertical spread from API): show spread_type + strikes
  const fields = [];
  if (tradeStructure?.spread_type)  fields.push(['Type',       tradeStructure.spread_type.replace(/_/g, ' ')]);
  if (tradeStructure?.long_strike)  fields.push(['Long strike',  Number(tradeStructure.long_strike).toFixed(2)]);
  if (tradeStructure?.short_strike) fields.push(['Short strike', Number(tradeStructure.short_strike).toFixed(2)]);
  if (tradeStructure?.expiration)   fields.push(['Expiry',       String(tradeStructure.expiration).slice(0, 10)]);
  if (tradeStructure?.strike)       fields.push(['Strike',       Number(tradeStructure.strike).toFixed(2)]);

  if (fields.length === 0) return null;

  return (
    <div className="pos-detail-section">
      <div className="pos-detail-label">Structure</div>
      {fields.map(([k, v]) => (
        <div key={k} className="pos-detail-kv">
          <span className="pos-detail-kv-key text-muted">{k}</span>
          <span className="pos-detail-kv-val mono">{v}</span>
        </div>
      ))}
    </div>
  );
}

// ── Score section ──────────────────────────────────────────────────────────

function ScoreSection({ position }) {
  const verdict = position.claude_verdict;
  const entryScore   = verdict?.score   ?? position.claude_score;
  const entryVerdict = verdict?.verdict ?? null;
  const claude_read  = verdict?.claude_read ?? null;

  return (
    <>
      <div className="pos-detail-section">
        <div className="pos-detail-label">AI Scores</div>
        <div className="pos-detail-scores">
          <div className="pos-detail-score-item">
            <span className="text-muted" style={{ fontSize: 11 }}>Entry Score</span>
            <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>
              {fmtScore(entryScore)}
            </span>
          </div>
          {entryVerdict && (
            <div className="pos-detail-score-item">
              <span className="text-muted" style={{ fontSize: 11 }}>Verdict</span>
              <span style={{ fontSize: 12, fontWeight: 700, color: verdictColor(entryVerdict) }}>
                {entryVerdict}
              </span>
            </div>
          )}
          <div className="pos-detail-score-item">
            <span className="text-muted" style={{ fontSize: 11 }}>Health</span>
            <PositionHealthBadge grade={position.health_grade} />
          </div>
        </div>
      </div>

      {claude_read && (
        <div className="pos-detail-section">
          <div className="pos-detail-label">Claude at Entry</div>
          <p className="pos-detail-claude-read">"{claude_read}"</p>
        </div>
      )}
    </>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export function PositionDetailPanel({ position, colSpan }) {
  return (
    <tr className="pos-detail-row">
      <td colSpan={colSpan} style={{ padding: 0 }}>
        <div className="pos-detail-panel">
          <LegsSection tradeStructure={position.trade_structure} />
          <ScoreSection position={position} />
        </div>
      </td>
    </tr>
  );
}
