/**
 * ParametersSection — the Parameters slot of the Strategy Admin editor (OTA-827).
 *
 * Phase-0 finding (NO-GO as drawn): the v2 prototype's `.params-grid` cards have
 * no net-new backing store at current HEAD, so there is nothing for this section
 * to edit — every card resolves elsewhere:
 *
 *   - Min / Max DTE        → the strategy HEADER above (engine_strategies.dte_min /
 *                            dte_max). Single source of truth — NOT duplicated here
 *                            (no `syncDteFromParams`-style two-store mirroring).
 *   - Max Short Delta,     → SCORING criteria, not gates (delta_quality /
 *     Min IV Rank            delta_otm_score / iv_rank). `delta_max` / `iv_rank_min`
 *                            are "dead fields dropped" (strategy_definitions.py).
 *   - Credit % / Debit %   → hard-gate thresholds, edited in Additional Hard Gates
 *     of Width               below (credit_pct_of_width_floor / debit_pct_of_width_
 *                            ceiling). Already editable there (OTA-785).
 *   - Take Profit, Stop     → exit-management values; not part of engine screening
 *     Loss                    configuration at all.
 *
 * Per the ticket's junction-only / no-invented-store rule, no card is rebound to a
 * fabricated store. This section is therefore an orientation guide pointing each
 * former card at where its value actually lives. No param-editor, no junction
 * writes, no draft mutation.
 *
 * Tokens: CSS var(--*) only (UI-GUIDANCE Part 3). No inline hex, no `$`.
 */

const MONO = "'JetBrains Mono', monospace";

const sectionTitleStyle = {
  fontSize: 11, textTransform: 'uppercase', letterSpacing: '1px',
  color: 'var(--muted)', fontFamily: MONO,
};
const cardStyle = {
  border: '1px solid var(--border)', borderRadius: 6, padding: 16, fontFamily: MONO,
};

// Each row: the prototype card(s) → where the value actually lives at HEAD.
const GUIDE = [
  { cards: 'Min DTE · Max DTE', where: 'Strategy header above — single source of truth (DTE Range).' },
  { cards: 'Max Short Delta · Min IV Rank', where: 'Scored, not gated — tune as Scoring Weights criteria below.' },
  { cards: 'Credit % / Debit % of Width', where: 'Hard-gate thresholds — edit in Additional Hard Gates below.' },
  { cards: 'Take Profit · Stop Loss', where: 'Exit-management settings — not part of engine screening config.' },
];

export default function ParametersSection() {
  return (
    <div style={{ marginTop: 24 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12,
      }}>
        <div style={sectionTitleStyle}>Parameters</div>
      </div>

      <div style={cardStyle}>
        <div style={{ fontSize: 11, color: 'var(--muted)', lineHeight: 1.6, marginBottom: 12 }}>
          Core scalar parameters are edited at their source of truth — this section is a
          guide, not a second store. Nothing here duplicates the header or the gate junctions.
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '8px 18px', alignItems: 'baseline' }}>
          {GUIDE.map(g => (
            <div key={g.cards} style={{ display: 'contents' }}>
              <div style={{ fontSize: 12, color: 'var(--text)', whiteSpace: 'nowrap' }}>{g.cards}</div>
              <div style={{ fontSize: 11, color: 'var(--muted)', lineHeight: 1.5 }}>{g.where}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
