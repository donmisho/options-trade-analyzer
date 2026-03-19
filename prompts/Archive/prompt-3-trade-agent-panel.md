# Session Prompt — Phase 2.6 Part 2: TradeAgentPanel (Frontend)

## Who You Are Talking To
I am an experienced Microsoft AI consultant building a personal options trading analyzer.
I have strong conceptual programming understanding but limited hands-on coding experience.
Always explain the "why" behind each step. I work on Windows with PowerShell.
I'm comfortable with VS Code but don't need coaching on basic editor navigation.

## The Project
**Options Trade Analyzer** — React + Vite frontend at `options-analyzer/web/`
- GitHub: `https://github.com/donmisho/options-trade-analyzer`
- Frontend: React + Vite v6, port 5173, HTTPS configured in `vite.config.js`
- Shared design tokens: `web/src/styles/tokens.js` — exports `C` (colors), `mono`, `WEIGHT_COLORS`, `WEIGHT_LABELS`
- Component pattern: inline styles using design tokens, no additional CSS files for new components

## Prerequisites for This Session
**Phase 2.6 backend must be working before starting this session.** Specifically:
- All 7 agent endpoints are live and tested
- `POST /api/v1/agent/triage` returns ranked JSON
- `POST /api/v1/agent/deep-dive` returns verdict + analysis
- `POST /api/v1/agent/followup` works
- GET/PUT/DELETE on `/api/v1/agent/recommendations/{key}` work
- `trade_recommendations` are being saved after deep-dive calls

## Existing Components That Are Being Replaced or Modified
- **`AskClaudePanel.jsx`** — being deleted this session. It is a single-trade slide-out panel
  with a thesis form (direction, conviction, timeframe, risk budget). It is deprecated.
  Don't read it for patterns — the new design is intentionally different.
- **`ConfigDrawer.jsx`** — NOT being changed, but use it as the visual and structural reference
  for how a full-height slide-out panel is built and mounted. TradeAgentPanel follows the same
  slide-from-right pattern, same dark panel styling.
- **`VerticalsPage.jsx`** and **`LongCallsPage.jsx`** — modified to remove old claude state
  and add multi-select + openAgent() call.
- **`AppContext.jsx`** — modified to add agent state and openAgent/closeAgent functions.

## The Architecture Decision to Understand Before Writing Any Code

**Why one shared panel instead of per-page panels?**
The old `AskClaudePanel` was mounted separately on each page and could only handle one trade
at a time. It also asked redundant questions — direction is already implied by the spread type
(a bull call is bullish), and timeframe is DTE. The new design:
- Mounts **once** at the app root, exactly like ConfigDrawer
- Opens via `AppContext.openAgent()` so any page can trigger it
- Accepts 1-10 trades and handles them all in one conversation
- Adapts its UI entirely based on what the agent returns — no fixed form structure
- Has exactly one optional user input: price target, shown only when the user selects a trade
  to explore further (the one thing the app genuinely cannot infer)

**The normalizer pattern:**
Each page calls `openAgent(trades, marketContext)` where `trades` is an array of normalized
trade objects. Each page implements its own `buildAgentTrade()` function that maps its local
trade shape to the shared schema. The panel doesn't know or care whether it received
verticals or long calls.

## What We Are Building This Session

### Step 1 — Update AppContext
File: `web/src/context/AppContext.jsx`

Add these to the existing context (do not remove anything that's already there):
```javascript
// New state
const [agentOpen, setAgentOpen] = useState(false);
const [agentTrades, setAgentTrades] = useState([]);
const [agentMarketContext, setAgentMarketContext] = useState(null);

// New functions exposed on context
function openAgent(trades, marketContext) {
  setAgentTrades(trades);
  setAgentMarketContext(marketContext);
  setAgentOpen(true);
}
function closeAgent() {
  setAgentOpen(false);
  // Don't clear trades/context on close — allow re-open to same state
}
```
Expose: `agentOpen`, `agentTrades`, `agentMarketContext`, `openAgent`, `closeAgent`

### Step 2 — Build TradeAgentPanel.jsx
File: `web/src/components/TradeAgentPanel.jsx`

This is the main deliverable of the session. It is a full-height slide-out panel (same as
ConfigDrawer — slides in from the right, covers the right ~45% of the screen, dark background).

**Internal state:**
```javascript
const [agentState, setAgentState] = useState('idle');
// 'idle' | 'triaging' | 'triage_complete' | 'diving' | 'verdict' | 'followup'

const [triageResults, setTriageResults] = useState(null);     // response from /triage
const [selectedTrade, setSelectedTrade] = useState(null);     // trade chosen for deep dive
const [priceTarget, setPriceTarget] = useState('');           // the one user input
const [verdictData, setVerdictData] = useState(null);         // response from /deep-dive
const [followupThread, setFollowupThread] = useState([]);     // [{question, response}]
const [followupInput, setFollowupInput] = useState('');
const [loading, setLoading] = useState(false);
```

**Four visual states — render one based on agentState:**

**`idle`:**
- Header: "✦ Ask Claude" with subtitle showing symbol and trade count
- Body: compact trade cards. Each card shows: direction badge (▲/▼), spread/strike label,
  expiration, score bar, debit/premium, R:R or delta. If the trade has a stored recommendation
  in `trade_recommendations`, show a small verdict badge (EXECUTE/WAIT/PASS) on the card.
- Footer: single button "✦ Triage These Trades". If only 1 trade AND it has a prior
  recommendation, button says "✦ Re-evaluate" and goes straight to `diving`. If only 1 trade
  with no prior recommendation, button says "✦ Analyze This Trade" and goes straight to `diving`.

**`triaging`:**
- Show the trade cards in a loading state (subtle pulse animation or spinner overlay)
- Status text: "Reading the trades…"

**`triage_complete`:**
- Each trade card now has a colored rank badge: STRONG (green), MEDIUM (yellow), WEAK (red/dim)
- One-sentence reason appears under each card
- Cards re-sorted: STRONG first, then MEDIUM, then WEAK
- Triage summary paragraph below all cards (from `triage_summary` in API response)
- "Explore Further →" button on trades flagged with `explore_further: true`
- "← New Selection" link to go back to idle with the same trades

**`diving` (loading for deep dive):**
- Selected trade card shown at top with "Analyzing…" spinner

**`verdict`:**
- Verdict banner at top: large colored box — green for EXECUTE, amber for WAIT, red for PASS
  — with the verdict word large and bold
- Optional price target input shown here (not before): small text field labeled
  "Price target used in this analysis: $___" — pre-filled if the user entered one, blank if not.
  If blank, Claude analyzed without a target (that's fine — prompt handles it gracefully).
- Four collapsible sections (open by default on first render):
  1. Thesis Alignment
  2. Risk/Reward Quality
  3. Probability & Expected Move
  4. Red Flags / Alternatives
- Exit plan table: 5-6 rows, two columns (Alert / Action), colored icons (🟢🎯🔴⏰🏆🛑⚠️)
- Two action areas at bottom:
  - "Tell me more" button → triggers a followup call asking Claude to expand on its reasoning
  - Free text input: "Ask a follow-up question…" with send button

**`followup`:**
- Small collapsed verdict summary card pinned at top (shows verdict + one line summary)
- Conversation thread: alternating user question bubbles and Claude response bubbles
- Text input stays live at bottom
- "← Back to trades" link returns to `triage_complete` (or `idle` if triage was skipped)

### Step 3 — Add RecommendationBadge component
File: `web/src/components/RecommendationBadge.jsx`

A tiny inline badge for results table rows. Shows `✦ EXECUTE`, `✦ WAIT`, or `✦ PASS` in the
appropriate color. Clicking it calls `openAgent([trade], marketContext)` which will detect
the prior recommendation and open at `verdict` state.

```javascript
// Props: verdict ('EXECUTE' | 'WAIT' | 'PASS'), trade, marketContext
// On click: openAgent([trade], marketContext)
```

### Step 4 — Update VerticalsPage
- Add a checkbox column to the results table (leftmost column)
- "✦ Ask Claude (N)" button in the table header, disabled when 0 trades selected,
  shows count when ≥1 selected. On click: `openAgent(selectedTrades.map(buildAgentTrade), getSmaData())`
- Add `buildAgentTrade(spread)` normalizer function — maps vertical spread fields to agent trade schema:
  ```javascript
  function buildAgentTrade(s) {
    return {
      trade_id: `${activeSymbol}-${s.long_strike}-${s.short_strike}-${s.expiration}`,
      symbol: activeSymbol,
      spread_type: s.spread_type,         // 'bull_call' | 'bear_put'
      spread_label: `${s.long_strike}/${s.short_strike} ${s.spread_type === 'bull_call' ? 'Call' : 'Put'} Spread`,
      expiration: s.expiration,
      dte: s.dte || 0,
      net_debit: s.net_debit,
      max_profit: s.max_profit,
      reward_risk_ratio: s.reward_risk_ratio,
      prob_of_profit: s.prob_of_profit,
      composite_score: s.composite_score,
      direction: s.spread_type === 'bull_call' ? 'bullish' : 'bearish',
    };
  }
  ```
- Replace the single `✦ Ask` per-row button with the `RecommendationBadge` component for trades
  that have a stored recommendation; keep a plain `✦ Ask` button for trades without one
- Remove: `claudeOpen`, `setClaudeOpen`, `claudeTrade`, `setClaudeTrade` state
- Remove: `<AskClaudePanel ... />` from JSX
- Add: `<TradeAgentPanel />` is already mounted at app root — no panel JSX needed here

### Step 5 — Update LongCallsPage
Same pattern as VerticalsPage. The `buildAgentTrade` normalizer for long calls:
```javascript
function buildAgentTrade(c) {
  return {
    trade_id: `${activeSymbol}-${c.strike}-${c.expiration}`,
    symbol: activeSymbol,
    spread_type: 'long_call',
    spread_label: `${c.strike} Call`,
    expiration: c.expiration,
    dte: c.theta_runway_days || 0,
    net_debit: c.premium_dollars,
    max_profit: null,                      // unlimited — the prompt handles this
    reward_risk_ratio: null,               // n/a for long options
    prob_of_profit: c.delta,               // delta ≈ probability
    composite_score: c.composite_score,
    direction: 'bullish',
    // Long call specific extras (agent prompt can use these if present)
    delta: c.delta,
    theta_per_day: c.theta_per_day_dollars,
    iv: c.iv,
    breakeven: c.breakeven,
  };
}
```

### Step 6 — Mount TradeAgentPanel at app root
In `App.jsx` (or whatever the root component is), add one line alongside the existing `<ConfigDrawer />`:
```jsx
<TradeAgentPanel />
```
It reads `agentOpen`, `agentTrades`, `agentMarketContext` directly from AppContext.

### Step 7 — Delete AskClaudePanel.jsx
Delete the file. Remove the import from VerticalsPage and LongCallsPage (already done in Steps 4-5).

## API calls from the frontend
All agent API calls go through `web/src/api/client.js`. Add these functions:
```javascript
export async function triageTrades(trades, marketContext) { ... }
export async function deepDiveTrade(trade, marketContext, priceTarget, priorRecommendation) { ... }
export async function followupTrade(trade, verdict, verdictSummary, question) { ... }
export async function getRecommendation(tradeKey) { ... }
export async function saveRecommendation(tradeKey, verdictData) { ... }
```

## Visual Design Notes
- Follow existing color tokens from `C` in tokens.js
- Claude accent color (`C.claudeAccent` — the gold/amber) for "Ask Claude" buttons and the panel header
- EXECUTE = green (use `C.bullish` or similar), WAIT = amber, PASS = red (use `C.bearish`)
- STRONG badge = green, MEDIUM = amber, WEAK = muted red
- Panel slide animation: same CSS transition as ConfigDrawer (check ConfigDrawer for exact classes/styles)
- Keep all styles inline using tokens — no new CSS files

## Start Here
Before writing any code:
1. Pull the latest code from GitHub — ask me to paste the current versions of `AppContext.jsx`,
   `VerticalsPage.jsx`, and `App.jsx` so you have the actual current state (never rely on
   project knowledge snapshots for current code — they're stale)
2. Confirm the 7 backend agent endpoints are live and responding
3. Start with Step 1 (AppContext) since everything else depends on it
