# Options Analyzer — UI-GUIDANCE.md (Updated 2026-05-11)
# Epic: OTA-477 | Feature: OTA-486

## Options Trade Analyzer — Experience & Visual Contract

_Version 3.4 — 05-11-2026_
_Historical reference: `ota-experience-mockups-v3.html` — superseded by the deployed app as of 2026-05-11. Mockups are retained for archaeological context only._

This document is the single source of truth for how the Options Trade Analyzer
looks, feels, and behaves. When this document conflicts with any other source —
architecture-plan.md, CLAUDE.md, inline code comments — this document wins.

Claude Code must read this document before building or modifying any frontend
component. No exceptions.

## Table of Contents

- [Part 1 — The Trader's Journey](#part-1--the-traders-journey)
- [Part 2 — Navigation](#part-2--navigation)
- [Part 3 — Design Tokens](#part-3--design-tokens)
- [Part 4 — Number & Display Formatting Rules](#part-4--number--display-formatting-rules)
- [Part 5 — Typography](#part-5--typography)
- [Part 6 — Shared Components](#part-6--shared-components)
  - [QuoteBar](#quotebar)
  - [SMA Chart](#sma-chart)
  - [ResultsTable](#resultstable)
  - [Trade type badges](#trade-type-badges)
- [Part 7 — Buttons](#part-7--buttons)
- [Part 8 — Claude's Voice: Summary Advice & Strategy Tags](#part-8--claudes-voice-summary-advice--strategy-tags)
- [Part 9 — Claude API Cost Guardrails](#part-9--claude-api-cost-guardrails)
- [Part 10 — Screen Specifications](#part-10--screen-specifications)
- [Part 11 — Rules for Claude Code](#part-11--rules-for-claude-code)

---

## Part 1 — The Trader's Journey

Every screen serves exactly one stage. A screen that answers two stages' questions
is overloaded and must be simplified.

```
SCAN → FIND TRADES → DECIDE → MANAGE → LEARN
```

| Stage | Question | Screen | Route |
|-------|----------|--------|-------|
| Scan | "What looks interesting?" | Security Strategies | /security-strategies |
| Find trades | "Which specific trade fits?" | Trades | /trades |
| Decide | "Enter, wait, or skip?" | Trade detail (inline on Trades) | /trades (expanded row) |
| Manage | "Hold, adjust, or exit?" | Positions | /positions |
| Learn | "Is this strategy working?" | Dashboard | /dashboard |

### Two paths to the Decide stage

**Path A — Strategy first.** Strategy page → "Find trades" → Trades (pre-filtered)
→ expand a row → evaluate.

**Path B — Trade first.** Scan card click (or direct symbol entry) → Trades →
expand a row → Claude recommends best strategy fit.

Both paths render the same trade detail expansion with the same components.

### Strategy pages

Each strategy has its own page (route: /strategies/{key}) showing:

1. Strategy header (name, description, DTE range, structure, requirement)
2. Parameters (editable cards for strategy-specific thresholds)
3. Scoring weights (read-only — shows how the score is computed)
4. "Find trades →" button (navigates to /trades?strategy={key})
5. Strategy positions (Positions component filtered to this strategy, with Refresh all)

---

## Part 2 — Navigation

### Left rail (200px fixed)

```
∧ Options Analyzer (click → Dashboard)
─────────────────────
Dashboard
Security Strategies
Trades
Positions
─────────────────────
STRATEGIES
  Steady Paycheck
  Weekly Grind
  Trend Rider
  Lottery Ticket
─────────────────────
● Schwab Connected
⚙ Settings
Sign out
```

Four primary nav items. Strategy items link to strategy pages. Never add more
primary nav items.

### Active state
- 3px solid #2dd4bf left border
- Teal text (#2dd4bf)
- Background: rgba(45,212,191,0.08)
- Applies to both primary and strategy nav items

### Inactive state
- No border (3px solid transparent)
- Muted gray (#8b949e)
- No background

---

## Part 3 — Design Tokens

### Colors
```
--bg:     #0d1117    page background
--bg2:    #161b22    RESTRICTED (see Part 3a)
--bg3:    #21262d    elevated, borders
--border: #30363d    default border
--teal:   #2dd4bf    brand, active, CTAs
--green:  #4ade80    bullish, positive, scores 70+
--amber:  #f59e0b    warning, mixed, scores 40-69
--red:    #f87171    bearish, negative, scores 0-39
--blue:   #60a5fa    informational
--purple: #c084fc    AI/Claude elements
--text:   #e6edf3    primary text
--muted:  #8b949e    secondary text
```

### Part 3a — Surface color restrictions (--bg2)
**Allowed:** QuoteBar, filter bars, calculation inset boxes, signal check boxes,
risk budget boxes, key level callout boxes in Claude's Read.

**Never:** Table rows, table headers, expansion panels, group headers, section
backgrounds, any full-width band.

### Score colors
- 70-100: var(--green)
- 40-69: var(--amber)
- 0-39: var(--red)

### Verdict badge colors
- EXECUTE: rgba(74,222,128,0.15) bg, var(--green) text
- WAIT: rgba(245,158,11,0.15) bg, var(--amber) text
- PASS: rgba(248,113,113,0.15) bg, var(--red) text

---

## Part 4 — Number & Display Formatting Rules

These apply everywhere, no exceptions.

| Data type | Format | Example | Notes |
|-----------|--------|---------|-------|
| Score | ##.00 | 71.00 | Always 0-100 scale |
| Probability (computed) | ##.00% | 47.00%, 4.85% | Two decimal places always |
| IV / IV Rank | ##.00% | 27.80%, 52.00% | Stored as decimal, display ×100. Two decimal places always |
| Monetary value | ##.00 | 634.00, 3.66 | No $ prefix. Use .toFixed(2) |
| Configuration % | ##% | 50%, 40% | No decimals (user-set whole numbers) |
| Configuration multiplier | #× | 2× | |
| Date | mm-dd-yyyy | 04-17-2026 | Via formatDate(). Never locale strings |
| Date with time | mm-dd-yyyy hh:mm | 03-30-2026 21:53 | |
| Health grade | Single letter | A, B, C, D, F | Color: A=green, B=teal, C=yellow, D=orange, F=red |
| Delta | 0.#### | 0.1010 | Four decimal places |
| Theta | ±0.#### | -0.0030 | Four decimal places, sign shown |
| Ratio | #.##:1 | 1.73:1 | Two decimal places |
| P&L display | ±##.00 (±##.00%) | +25.00 (+8.77%) | Sign always shown |
| Trade type display | Title Case, spaces | Bear Put Debit | Never raw enums with underscores. Bull=green, Bear=red |
| Position source | Title Case | Paper, Live | Never uppercase "PAPER"/"LIVE" |
| Strategy pills | 2-letter abbreviation | SP, WG, TR, LT | With tooltip showing full name. CSS custom property colors |

---

## Part 5 — Typography

All elements use monospace. No exceptions.

| Element | Size | Weight | Other |
|---------|------|--------|-------|
| Nav items | 12px | 400 | |
| QuoteBar symbol | 16px | 700 | |
| QuoteBar labels | 9px | 400 | uppercase, letter-spacing 0.4px, muted |
| QuoteBar values | 12px | 400 | |
| Page title | 16px | 700 | |
| Table headers | 10px | 400 | uppercase, letter-spacing 0.4px, muted |
| Table cells | 11px | 400 | |
| Section titles | 10px | 400 | uppercase, letter-spacing 0.6px, muted |
| Strategy names | 12px | 700 | |
| Score numbers (tables) | 11px | 700 | |
| Score numbers (cards) | 13px | 700 | |
| Claude read text | 10px | 400 | Non-italic, #c9d1d9, line-height 1.65 |
| Claude summary advice | 9px | 700 | White outlined badge (see Part 8) |

---

## Part 6 — Shared Components

### QuoteBar
File: `web/src/components/QuoteBar.jsx`

One shared component. Import `<QuoteBar />` everywhere. Zero reimplementations.

Field order: Symbol (16px bold) · SIGNAL badge · Last Analyzed · Price · CHG ·
CHG % · Day Range · 52W Range · Volume · Rel Vol · Earnings Date (if ≤60 days;
amber if ≤14 days) · Dividend Date (if ≤60 days)

Background: var(--bg2). Border: 1px solid var(--border). Border-radius: 4px.

**Field rules:**
- No `$` prefix on any value — house style
- Earnings and dividend: if null or >60 days away, do not render the field at all
- Earnings within 14 days: amber highlight badge — risk signal for options positions
- This component is the ONLY place QuoteBar rendering logic lives
- Every page that needs it imports `<QuoteBar />` — zero inline reimplementations

### SMA Chart
Candlestick chart with configurable moving averages. Moving average periods and
date range are user-selectable via the SMA Configuration and Chart Range controls.
Defaults: 8/21/50 day SMAs, 90-day range — but these are configurable, not fixed.

### ResultsTable
File: `web/src/components/ResultsTable.jsx`

Pure display component accepting a `columns` prop. Column configs in `web/src/config/`.
Never knows what page it is on. Adding a trade structure = adding a column config file.

### Table row backgrounds
- Normal: transparent
- Hover: rgba(45,212,191,0.02)
- Expanded: rgba(45,212,191,0.03)
- No alternating/striped colors

### Trade row column order (no row numbers)
```
[chevron] [score bar + number] [spread/strike] [type badge] ... [data] ... [strategy pills]
```

Leading with score gives an instant visual scan: "how good → what is it → what kind."

### Trade type badges
Type badges display clean, human-readable names — never raw enum values with
underscores. The frontend transforms at render time: replace underscores with
spaces, apply title case.

**Color convention — direction determines badge color:**
- Bull trades (bullish direction): green badge
- Bear trades (bearish direction): red badge

| Raw enum | Badge display | Badge color |
|----------|--------------|-------------|
| BULL_CALL_DEBIT | Bull Call Debit | green bg rgba(74,222,128,0.15), green text |
| BULL_PUT_CREDIT | Bull Put Credit | green bg rgba(74,222,128,0.15), green text |
| BEAR_PUT_DEBIT | Bear Put Debit | red bg rgba(248,113,113,0.15), red text |
| BEAR_CALL_CREDIT | Bear Call Credit | red bg rgba(248,113,113,0.15), red text |

This applies everywhere a trade type appears — results table rows, trade detail
headers (Section A), position rows, Config panel selectors. The same badge
component, the same formatting, the same colors.

Font: 9px bold. Padding: 2px 6px. Border-radius: 3px.

New trade types added in the future follow the same convention: the first word
determines direction and therefore color.

---

## Part 7 — Buttons

Never stretch to fill. Width: auto.

### Teal outlined (primary)
```css
background: rgba(45,212,191,0.1); border: 1px solid rgba(45,212,191,0.4);
color: #2dd4bf; padding: 7px 16px; border-radius: 4px; font-size: 11px;
font-family: monospace;
```

### Green filled (positive/confirm)
```css
background: rgba(74,222,128,0.12); border: 1px solid rgba(74,222,128,0.45);
color: #4ade80; font-weight: 700; padding: 7px 16px; border-radius: 4px;
font-size: 11px; font-family: monospace;
```

### Neutral outlined (secondary/discard)
```css
background: transparent; border: 1px solid #30363d; color: #8b949e;
padding: 7px 14px; border-radius: 4px; font-size: 11px; font-family: monospace;
```

### Small variant: padding 4px 10px, font-size 10px.
### Disabled: opacity 0.35, cursor default, pointer-events none.
### Visibility: every button visible in default state (border or background).
### Groupings: flex row, gap 10px, left-aligned, never stretch.

---

## Part 8 — Claude's Voice: Summary Advice & Strategy Tags

### Claude's Read (detailed analysis)
Inside a bordered card. 10px, #c9d1d9, line-height 1.65. Key level callout:
var(--bg2) bg, 2px amber left border. Multiple paragraphs with reasoning.

### Claude summary advice (one-line guidance)
A white outlined badge that stands out from muted UI chrome. Used in two places:
1. **Trade detail header:** "Best fit: Weekly Grind"
2. **Position re-read header:** "SPY drifts lower, thesis marginally intact"

```css
background: rgba(255,255,255,0.06);
border: 1px solid rgba(255,255,255,0.35);
color: #e6edf3;
font-size: 9px;
font-weight: 700;
padding: 3px 10px;
border-radius: 3px;
```

When a strategy name appears inside the advice badge, it renders in that
strategy's color while the rest of the text stays white:
```
"Best fit: [Weekly Grind]"
  ↑ #e6edf3   ↑ var(--green)
```

### Strategy pills (abbreviated with tooltip)

| Abbr | Full name | Background | Text color |
|------|-----------|------------|------------|
| SP | Steady Paycheck | rgba(245,158,11,0.12) | var(--amber) |
| WG | Weekly Grind | rgba(74,222,128,0.12) | var(--green) |
| TR | Trend Rider | rgba(96,165,250,0.12) | var(--blue) |
| LT | Lottery Ticket | rgba(192,132,252,0.12) | var(--purple) |

Font: 9px bold. Padding: 2px 5px. Border-radius: 3px. Margin: 0 1px.
A trade can show multiple pills.

Tooltip on hover: var(--bg3) bg, 1px var(--border), 9px normal, 3px 8px padding.

Strategy colors are consistent everywhere — pills, scoring weight bars, and
strategy names inside advice badges all use the same color per strategy.

---

## Part 9 — Claude API Cost Guardrails

| Action | Behavior |
|--------|----------|
| Daily automated refresh | One per position per day, after market close. No confirmation. |
| Single position manual refresh | Runs immediately, no confirmation. |
| "Refresh all" (>1 position) | Confirmation: "This will refresh X positions via Claude. Continue?" |
| Page load | Never triggers refresh. Shows cached data. |
| Timer/interval | No auto-refresh on any timer. |

### Confirmation dialog
- Overlay: rgba(0,0,0,0.6), 1px var(--border), border-radius 6px, 20px padding
- Title: 12px bold
- Body: 10px #c9d1d9, line-height 1.5
- Actions: "Confirm refresh" (teal outlined) + "Cancel" (neutral outlined)

---

## Part 10 — Screen Specifications

### Screen 1: Security Strategies (Scan)
**Route:** /security-strategies · **No Config drawer.**

- Filter bar: Source, Signal, Min score, Sort, "Scan now"
- Card grid (min 280px): symbol + signal + NEW badge, price line, 4 strategy
  score bars (##.00 format), signal summary (italic muted, IV rank as ##.00%)
- Click card → /trades?symbol={symbol}

### Screen 2: Trades
**Route:** /trades, /trades?symbol=XXX, /trades?strategy=XXX
**File:** `TradesPage.jsx` — unified terminal

- Symbol search, QuoteBar, SMA chart (configurable)
- Collapsible sections per trade structure, each with own ⚙ Config drawer (functional — Verticals→SP+WG, Puts & calls→TR+LT)
- Row: chevron → score → spread/strike → type badge → data → pills (no row numbers)
- Type badges use clean display names with bull=green / bear=red coloring
- Sections: Vertical spreads (live — POST /api/v1/analyze/verticals), Puts & calls (live — POST /api/v1/analyze/long-calls), Iron condors (coming soon)
- Click row → trade detail expansion (Sections A-E)

### Trade Detail Expansion
Teal top border (2px solid rgba(45,212,191,0.35)).

**A — Trade header:** Type badge (clean name, directional color) + context label +
strikes, expiry, DTE, entry, max P/L, breakeven, R:R, triggers, time exit

**B — Exit scenario table:** $5 increments. Loss zone: rgba(248,113,113,0.03). Footer: Total EV.

**C — Outcome summary:** P(max profit), P(breakeven+), P(partial), P(max loss), EV, EV % risk. Badge: POSITIVE/NEGATIVE EV.

**D — Probability matrix:** Color zones, cumulative prob, highlighted rows. Live — ProbabilityMatrix component, B-S data from POST /api/v1/analyze/probability-matrix.

**E — Claude's Read:** Verdict badge + summary advice (white badge, strategy name in color) + detailed analysis + key level + actions (Follow / Take Position / follow-up / Discard). Fully wired — evaluate → structured verdict → Follow/Take Position records to positions table → follow-up Q&A loop.

### Screen 3: Strategy Page
**Route:** /strategies/{key}

- Header, parameters (##% for config percentages), weights (read-only)
- "Find trades →" → /trades?strategy={key}
- Strategy positions (filtered, Refresh all with cost guardrail)

### Screen 4: Positions
**Route:** /positions

- Filters + "↻ Refresh all" (with cost guardrail confirmation when >1)
- Groups by strategy/symbol/health
- Rows: chevron → score → symbol → type badge (clean name) → pill → data → health
- Expanded: versioned re-reads with verdict + score + summary advice (white badge) + analysis + exit plan

### Screen 5: Dashboard (Phase 3.6+)
**Route:** /dashboard — not yet built.

---

## Part 11 — Rules for Claude Code

1. Read this document before any frontend work.
2. Never add a fifth primary nav item.
3. Never use var(--bg2) on table rows, headers, or expansion panels.
4. Never stretch a button to fill its container.
5. Never inline a QuoteBar reimplementation.
6. Never hardcode strategy names in filters — use trade_structure.
7. Scores: 0-100, ##.00, green/amber/red by threshold.
8. Probabilities: ##.00% always (two decimal places).
9. IV/IV Rank: ##.00% always.
10. Dates: formatDate() → mm-dd-yyyy. Never locale strings.
11. No $ prefix on monetary values.
12. Strategy pills: SP/WG/TR/LT with tooltip. Never full names in compact spaces.
13. Trade tables: no row numbers. Order: chevron → score → spread → type → data → pills.
14. Claude summary advice: white outlined badge. Strategy name in strategy color.
15. Claude API: confirmation when refreshing >1 position. One daily auto-refresh. No timers.
16. The deployed app is the visual ground truth. Mockups in `ota-experience-mockups-v3.html` are historical reference only; refer to deployed components and live styling for current state.
17. Type badges: clean display names (title case, spaces, no underscores). Bull = green, Bear = red. Frontend transforms enum at render time.
18. Health grades: single letter (A/B/C/D/F) with color token per grade.
19. Position source labels: "Paper" / "Live" — never uppercase.

---

## Change Log

| Date | Ticket | Change |
|---|---|---|
| 2026-05-11 UTC | OTA-635 | Rule 16 demoted: mockups in `ota-experience-mockups-v3.html` are no longer visual ground truth — the deployed app is. Mockups remain in the repo as historical reference. Header reference line updated correspondingly. This change accompanies the strategy-structure compatibility decision (architecture-plan.md and business-rules.md updates) — the v3 mockups depict SP/WG pills on bear_put trades, which is no longer correct under the new compatibility rule, so retaining them as "ground truth" would create contradictions with the new canon. |
