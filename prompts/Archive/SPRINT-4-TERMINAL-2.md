# Sprint 4 — Terminal 2: Puts & Calls Data Integration + Config + Scan Audit

## Session Context

You are executing Sprint 4 of the Experience Framework v3 overhaul for the Options Trade Analyzer.

**Read these files first (in this order):**
1. `UI-GUIDANCE.md` — the visual contract, wins over all other sources
2. `architecture-plan.md` — backend endpoint specs and data flow
3. `CLAUDE.md` — project conventions and house style rules

**Key backend endpoints (all confirmed DONE and live):**
- `POST /api/v1/analyze/long-calls` — score long call/put options
- `POST /api/v1/evaluate/structured` — Claude structured evaluation
- `POST /api/v1/analyze/probability-matrix` — Black-Scholes matrix

**Column config:** `web/src/config/long-options-columns.js`
**Strategy configs:** `web/src/strategy-configs/` (index.js + per-strategy files)
**Shared components:** StrategyPill.jsx, TradeTypeBadge.jsx, ScoreCell.jsx, ConfigDrawer.jsx

**House style rules (enforce in every change):**
- No `$` prefix on any monetary value
- Monetary display: `##.00` via `.toFixed(2)`
- Dates: `mm-dd-yyyy` via `formatDate()` — never locale strings
- Scores: 0-100, `##.00`, green 70+ / amber 40-69 / red 0-39
- Probabilities: `##.00%` always
- Config percentages: `##%` (no decimals). Multipliers: `#×`
- Dark theme CSS variables only — never inline hex
- `var(--bg2)` restricted to filter bars, QuoteBar, pill badge backgrounds only
- Buttons: auto-width with padding, never full-width stretch
- Strategy pills: SP/WG/TR/LT abbreviations with tooltip
- Trade type badges: clean display names (title case, spaces). Bull=green, Bear=red
- Never hardcode strategy names — use trade_structure from config

---

## Subtask Sequence (execute in order)

### Step 1 — OTA-384: Wire Puts & calls ResultsTable

In the Trades page (TradesPage.jsx), locate the "Puts & calls" collapsible section.

Wire data fetching:
- On active symbol change, call POST /api/v1/analyze/long-calls with `{ symbol, config }`
- Store results in `longCallsResults` state
- Pass to `<ResultsTable columns={longOptionsColumns} data={longCallsResults} />`
- Import columns from `web/src/config/long-options-columns.js`

Section header: "Puts & calls · {count} results"
Loading state: "Analyzing long options..." in 10px muted
Empty state: "No long option candidates found for {symbol}" in 10px muted centered
Row click toggles expansion (same pattern as Vertical spreads section)

vs ITM coloring: green=ITM, amber=within 5%, muted=OTM

**Commit prefix:** `OTA-384`

### Step 2 — OTA-385: Wire Puts & calls trade detail expansion

When a Puts & calls row expands, render Sections A-E adapted for single-leg options:

Section A differences for long options:
- Type badge: "Long Call" (blue) or "Long Put" (red)
- No spread width field
- Fields: Strike, Expiry, DTE, Premium, Max profit (unlimited for calls), Max loss (premium), Breakeven (strike + premium for calls), Delta, Theta/Day

Section B: price increments based on strike proximity. P&L = `(price - strike - premium) × 100` for calls.
Section C: same component, probabilities from long option data.
Section D: ProbabilityMatrix (same pattern as verticals — reuse if Terminal 1 has completed OTA-383, otherwise use placeholder).
Section E: same component, evaluation payload uses `trade_structure: "long_call"` or `"long_put"`.

2px teal top border on expansion.

**Commit prefix:** `OTA-385`

### Step 3 — OTA-386: Wire strategy pills into Puts & calls

The Strategies column in long-options-columns.js renders StrategyPill for applicable strategies.

Long options are applicable to:
- Trend Rider (TR) — blue
- Lottery Ticket (LT) — purple
- NOT Steady Paycheck or Weekly Grind (these require credit spread structures)

Determine applicability by checking trade's `trade_structure` against each strategy config's required structures. Use the shared StrategyPill component (same as Verticals section).

**Commit prefix:** `OTA-386`

### Step 4 — OTA-387: Wire Config drawer per section

Each section header has a "⚙ Config" button. Wire onClick to open ConfigDrawer:
- Slides in from right (same as Settings panel)
- Loads `configSchema` from strategy config files in `web/src/strategy-configs/`
- Vertical spreads section: SP, WG configs (credit spread strategies)
- Puts & calls section: TR, LT configs (long option strategies)
- If multiple strategies apply, show strategy selector (pills or tabs) at top
- Render editable parameter cards: ##% for percentages, #× for multipliers
- "Apply" re-runs analysis with updated params
- "Reset" restores defaults
- Close on backdrop click or X

Never hardcode strategy names — read from config files.

**Commit prefix:** `OTA-387`

### Step 5 — OTA-389: Scan page v3 visual alignment audit

Navigate to /security-strategies. This is an AUDIT — fix discrepancies, don't rebuild.

Verify:
- No Config drawer on this page (retired per UI-GUIDANCE.md Part 11)
- Filter bar: Source, Signal, Min score, Sort, "Scan now"
- Card grid (min 280px auto-fill): symbol + signal + NEW badge, price, 4 strategy score bars (##.00), signal summary (italic muted, IV rank ##.00%)
- Click card → /trades?symbol={symbol}

Fix any discrepancies found. Do not add features not in the mockup.

**Commit prefix:** `OTA-389`

---

## Final Commit

After all steps pass:
```
OTA-384 OTA-385 OTA-386 OTA-387 OTA-389 feat: wire Puts & calls data, strategy pills, config drawers, scan audit
```

**Recommended QA level:** Level 2 (new data section, config integration, routing changes)
