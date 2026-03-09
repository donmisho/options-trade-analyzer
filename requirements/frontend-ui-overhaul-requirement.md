# Frontend UI Overhaul — Verticals Page & Ask Claude Panel

## Context for Claude Code

**IMPORTANT:** Read the current versions of these files on disk before making changes. The project knowledge snapshots are stale — the live code has diverged. Always `cat` the actual file first.

Files to read:
- `web/src/pages/VerticalsPage.jsx`
- `web/src/components/AskClaudePanel.jsx`
- `web/src/styles/tokens.js`
- `web/src/pages/VerticalsPage.css` (or wherever table styles live)

---

## Current State (from live screenshot)

The results table currently displays these columns:

```
CLAUDE | FAV | TYPE | LONG / SHORT | EXP | DTE | DEBIT | MAX PROFIT | R:R | BREAKEVEN | PROB % | EV | SCORE | [fx]
```

- The CLAUDE column has checkboxes and an "eval" link per row
- TYPE shows "Bull Call" (green badge) and "Bear Put" (red badge) — only 2 types
- LONG / SHORT shows strikes like "250 / 260" or "230 / 220"
- DEBIT always shows a positive dollar amount
- There's a batch "✦ Ask Claude (0)" button above the table that counts selected trades
- The ✦ and ƒx action buttons are in the rightmost column

The Ask Claude panel (when open) shows:
- SELECTED TRADE card with: symbol, strikes, type label, expiration, DEBIT, MAX PROFIT, R:R, PROB
- MARKET CONTEXT (auto-filled from SMA data)
- YOUR THESIS section (direction, conviction, price target, timeframe, risk budget)
- PRE-SCREEN FLAGS
- "✦ Evaluate This Trade" button
- After evaluation: verdict banner + free-text analysis sections

---

## Part 1: Results Table Changes

### 1A. Rename "LONG / SHORT" header to "BUY / SELL"

Why: "Long/Short" is engine jargon. "Buy/Sell" tells the trader exactly what action to take at the broker.

Find the `<th>` that renders "LONG / SHORT" (or "Long / Short") and change it to "BUY / SELL".

The cell data does NOT need to change yet — the strike values displayed are the same regardless of the label. The current `long_strike / short_strike` values from the API happen to correspond to buy/sell for debit spreads. When the backend credit spread engine ships later, it will send explicit `buy_strike` / `sell_strike` fields and the cell rendering will update then.

For now, just change the header text.

### 1B. Rename "DEBIT" header to "NET"

Why: When credit spreads are added, some trades will show a credit (money received) instead of a debit (money paid). "NET" is a universal label that works for both.

Change the `<th>` from "DEBIT" to "NET".

The cell rendering should also be updated to handle future credit values. Add color coding now even though only debit values exist today:

```jsx
// In the cell that currently shows: ${s.net_debit.toFixed(2)}
// Change to handle both positive (debit) and negative (credit) net_cost:
const netCost = s.net_cost ?? s.net_debit;  // support both field names during transition
const isCredit = netCost < 0;

// Display:
<td className="mono" style={{ color: isCredit ? '#4ade80' : undefined }}>
  {isCredit 
    ? `($${Math.abs(netCost).toFixed(2)})` 
    : `$${netCost.toFixed(2)}`
  }
</td>
```

The parentheses-with-green convention means "money coming to you." For now, all values will be positive (debit), so this is a no-op visually — but it's wired up for when credit spreads arrive.

### 1C. Expand Type Badges to 4 Types

The current code uses a simple boolean (`isBull`) to choose between two badges. Replace this with a lookup that supports all four vertical spread types:

```jsx
const TYPE_CONFIG = {
  bull_call:  { label: 'Bull Call',  className: 'type-bull' },
  bear_put:   { label: 'Bear Put',  className: 'type-bear' },
  bull_put:   { label: 'Bull Put',  className: 'type-bull' },
  bear_call:  { label: 'Bear Call', className: 'type-bear' },
};

// In the row render:
const typeInfo = TYPE_CONFIG[s.spread_type] || { label: s.spread_type, className: '' };

<td>
  <span className={`type-badge ${typeInfo.className}`}>
    {typeInfo.label}
  </span>
</td>
```

This is backward compatible — `bull_call` and `bear_put` work exactly as before. When the backend starts returning `bull_put` and `bear_call`, the badges will render automatically.

### 1D. Update buildClaudeTrade() to use Buy/Sell Language

Find the `buildClaudeTrade(s)` function. It currently builds an object with `long_strike` and `short_strike`. Update it to ALSO include `buy_strike` and `sell_strike` fields:

```jsx
function buildClaudeTrade(s) {
  // Derive buy/sell from the spread data
  // For current debit-only spreads: buy = long_strike, sell = short_strike
  // When credit spreads arrive, the API will send buy_strike/sell_strike directly
  const buyStrike = s.buy_strike ?? s.long_strike;
  const sellStrike = s.sell_strike ?? s.short_strike;
  const netCost = s.net_cost ?? s.net_debit;
  const isCredit = netCost < 0;

  return {
    symbol: activeSymbol,
    spread_type: s.spread_type,
    strategy_label: TYPE_CONFIG[s.spread_type]?.label || s.spread_type,
    is_credit: isCredit,

    // Buy/Sell (new, preferred)
    buy_strike: buyStrike,
    sell_strike: sellStrike,

    // Legacy (keep for backward compat until backend fully migrated)
    long_strike: s.long_strike,
    short_strike: s.short_strike,

    option_type: s.option_type || (s.spread_type === 'bull_call' || s.spread_type === 'bear_call' ? 'call' : 'put'),
    expiration: s.expiration,
    net_cost: netCost,
    net_debit: s.net_debit,  // legacy
    max_profit: s.max_profit,
    max_loss: s.max_loss ?? s.net_debit,
    breakeven: s.breakeven,
    reward_risk_ratio: s.reward_risk_ratio,
    prob_of_profit: s.prob_of_profit,
    composite_score: s.composite_score,
  };
}
```

---

## Part 2: Ask Claude Panel — Selected Trade Card

### Current state
The SELECTED TRADE card at the top of AskClaudePanel shows:
```
▲ QQQ 440/445  Call Spread · Exp 2026-03-20
DEBIT        MAX PROFIT      R:R       PROB
$2.10        $290            1.38      58%
```

### Required changes

#### 2A. Update the trade summary line

Replace the strikes display with Buy/Sell action language:

```
BEFORE: ▲ QQQ 440/445  Call Spread · Exp 2026-03-20
AFTER:  ▲ QQQ Bull Call · Exp 2026-03-20
        Buy 440 call / Sell 445 call
```

The strategy label comes from `trade.strategy_label`. The buy/sell line uses `trade.buy_strike`, `trade.sell_strike`, and `trade.option_type`.

#### 2B. Update the stats row

Replace "DEBIT" label with "NET" and handle credit display:

```jsx
// Stats row
const netCost = trade.net_cost ?? trade.net_debit;
const isCredit = netCost < 0;
const netLabel = isCredit ? 'CREDIT' : 'NET';
const netDisplay = isCredit 
  ? `($${Math.abs(netCost).toFixed(2)})` 
  : `$${netCost.toFixed(2)}`;
```

Render:
```
NET          MAX PROFIT      R:R       PROB
$3.50        $6.50           1.86      58%
```

Or for a credit spread (future):
```
CREDIT       MAX PROFIT      R:R       PROB
($2.15)      $2.15           0.27      72%
```

---

## Part 3: Ask Claude Panel — Structured Response Rendering

### Current state
After clicking "Evaluate This Trade", the panel currently receives a free-text response from the backend and displays it as prose, with the verdict parsed out of the text via string matching.

### Required changes

The backend is being updated to return STRUCTURED JSON (see foundry-structured-output-instructions.md). The response shape will be:

```json
{
  "verdict": "EXECUTE" | "WAIT" | "PASS",
  "verdict_rationale": "One sentence...",
  "thesis_alignment": "paragraph...",
  "risk_reward_quality": "paragraph...",
  "probability_assessment": "paragraph...",
  "red_flags": ["flag 1", "flag 2"],
  "alternatives": ["alt 1", "alt 2"],
  "exit_plan": {
    "underlying_alerts": [
      {"label": "Profit trigger", "price_or_value": "$445", "action": "Prepare to close"}
    ],
    "spread_value_alerts": [
      {"label": "Scale out", "price_or_value": "$5.47", "action": "Close 50-75%"}
    ],
    "time_rules": ["If flat after 10 days, reassess"]
  }
}
```

The panel needs to handle BOTH the old free-text format AND the new structured format during the transition, since the backend upgrade may not be deployed yet.

#### 3A. Verdict Banner (already works, just wire to field)

The verdict banner already exists with color coding (EXECUTE=green, WAIT=amber, PASS=red). Update it to read from the structured field:

```jsx
// Detection: if response has a "verdict" field, it's structured
const isStructured = response && typeof response.verdict === 'string';

// Verdict
const verdict = isStructured ? response.verdict : parseVerdictFromText(response);
const rationale = isStructured ? response.verdict_rationale : null;
```

If `rationale` exists, display it as a subtitle under the verdict banner.

#### 3B. Analysis Sections (collapsible)

Render each analysis section as a collapsible card. All should be EXPANDED by default on first render:

```
┌─ Thesis Alignment                                    [▼]
│  Price at $599.75 is below all three SMAs, confirming
│  the bearish thesis. The SMA 8 at $602 is acting as...
└────────────────────────────────────────────────────────

┌─ Risk / Reward Quality                               [▼]
│  R:R of 1.86 meets the 1.5 minimum threshold...
└────────────────────────────────────────────────────────

┌─ Probability & Expected Move                         [▼]
│  With a $550 target requiring an 8.3% drop...
└────────────────────────────────────────────────────────
```

Each section maps to a field:
- "Thesis Alignment" → `response.thesis_alignment`
- "Risk / Reward Quality" → `response.risk_reward_quality`
- "Probability & Expected Move" → `response.probability_assessment`

#### 3C. Red Flags & Alternatives

If `response.red_flags` has items, show a red-accented section:

```
┌─ 🚩 Red Flags
│  • Buy leg at 630 is $30 ITM — massive intrinsic value cost
│  • Breakeven at $610.73 is ABOVE current price
└────────────────────────────────────────────────────────
```

If `response.alternatives` has items, show below:

```
┌─ 💡 Alternatives
│  • 590/550 bear put debit spread: costs ~$8-12, R:R of 3:1
│  • Single 590 put for a simple directional bet
└────────────────────────────────────────────────────────
```

If either array is empty, don't render that section.

#### 3D. Exit Plan

Render the exit plan as a structured table/card layout:

```
┌─ Exit Plan
│
│  📊 Underlying Price Alerts
│  ┌──────────────────┬───────────┬────────────────────────┐
│  │ Profit trigger   │ $445.00   │ Check value, prepare   │
│  │ Full target      │ $450.00   │ Close spread           │
│  │ Thesis invalid   │ $435.00   │ Close immediately      │
│  └──────────────────┴───────────┴────────────────────────┘
│
│  💰 Spread Value Alerts
│  ┌──────────────────┬───────────┬────────────────────────┐
│  │ Scale out        │ $5.47     │ Close 50-75%           │
│  │ Full exit        │ $7.40     │ Close 100%             │
│  │ Hard stop        │ $1.71     │ Close, no exceptions   │
│  └──────────────────┴───────────┴────────────────────────┘
│
│  ⏰ Time Rules
│  • If flat after 10 days → reassess, theta accelerating
│  • Never hold into final 7 days unless deep ITM
│
└────────────────────────────────────────────────────────
```

Each alert row comes from the `underlying_alerts` and `spread_value_alerts` arrays. Time rules come from the `time_rules` array.

#### 3E. Backward Compatibility with Free-Text Response

Until the backend structured output migration is complete, the panel must handle the OLD free-text response format. Detection logic:

```jsx
function renderEvaluation(response) {
  // New structured format — has typed verdict field
  if (response && typeof response === 'object' && response.verdict) {
    return <StructuredEvaluation result={response} />;
  }
  
  // Old free-text format — response is a string or has a text field
  const text = typeof response === 'string' ? response : response?.text || response?.result;
  if (text) {
    return <LegacyTextEvaluation text={text} />;
  }
  
  return null;
}
```

The `LegacyTextEvaluation` component is the current rendering logic — don't delete it, just wrap it so it can coexist with the new structured renderer.

#### 3F. Follow-Up Responses

The follow-up endpoint will also return structured JSON:

```json
{
  "answer": "Direct answer to the question...",
  "updated_verdict": "PASS",       // or null if verdict unchanged
  "updated_rationale": "Because..." // or null
}
```

If `updated_verdict` is not null, update the verdict banner to show the new verdict with an indicator that it changed:

```
PASS  (updated from WAIT)
Because the earnings date falls within the expiration window...
```

If `updated_verdict` is null, just display the `answer` text in the follow-up area as it works today.

---

## Styling Notes

All styling should use the existing design token system from `tokens.js` (the `C` object for colors, `mono` for monospace font). Match the dark theme and existing component patterns.

For the collapsible analysis sections, use a simple chevron toggle with smooth height transition. Don't introduce new CSS dependencies — use inline styles with `C.*` tokens, consistent with how SmaPanel, ConfigDrawer, and FormulaBreakdownPanel are styled.

For the exit plan tables, use a compact table style matching the results table's density. Use the same `C.border`, `C.bg`, `C.textDim` tokens.

---

## Execution Order

1. **Table columns first** (Part 1A-1C) — pure display changes, no API dependency
2. **buildClaudeTrade update** (Part 1D) — prepares the payload for the panel
3. **Selected trade card** (Part 2) — update the panel's header display
4. **Structured response renderer** (Part 3) — build the new rendering components
5. **Backward compat wrapper** (Part 3E) — ensure old format still works

Test after each step. The table changes (step 1) are visible immediately. The panel changes (steps 2-5) require clicking the eval button on a trade.
