# Sprint 3 — Strategy Pages + Positions v3 Redesign
## Epic: OTA-365

---

## Feature 1: Sprint 2 Integration Fixes (prerequisite)
**Parent:** OTA-365
**Summary:** Sprint 2 fixes — SMA chart, strategy pills wiring, Section B/C data gaps
**Note:** OTA-351 already exists for this. Reparent it under OTA-365.

### Subtask 1.1: SMA chart + pills + Section C + Section B data
**Parent:** OTA-351 (reparent under OTA-365)
**Summary:** Fix Trades page — import SMA chart, wire StrategyPill to columns, render SectionC, populate SectionB data
**Labels:** sprint-3, frontend, bug

---

## Feature 2: Strategy Page Full Build
**Parent:** OTA-365
**Summary:** Strategy Page — header, parameters, scoring weights, "Find trades", filtered positions

### Subtask 2.1: Strategy header + parameters cards
**Summary:** StrategyPage — strategy header card + editable parameter cards from config schema
**Labels:** sprint-3, frontend, experience-framework

**Claude Code Prompt:**

Read UI-GUIDANCE.md Part 1 (Strategy pages) and Part 10 (Screen 3). Review ota-experience-mockups-v3.html Screen 3 (Steady Paycheck example). Also read architecture-plan.md "Strategy Config Schema Pattern" section.

Replace the placeholder in web/src/pages/StrategyPage.jsx with the full strategy page:

1. Read :key from useParams (e.g., "steady-paycheck", "weekly-grind", "trend-rider", "lottery-ticket")
2. Map key to strategy config. Check for existing config files at web/src/strategy-configs/ or web/src/config/. If they don't exist, create a strategy data map with:

   steady-paycheck:
   - name: "Steady Paycheck", description: "25-50 DTE credit spreads, high IV rank, income focus"
   - DTE range: "25 – 50 DTE", Structure: "Credit spread", Requirement: "Requires credit spread structure"
   - Parameters: Min DTE (25, range 15-45), Max DTE (50, range 30-60), Max short delta (0.3 Δ, range 0.1-0.45), Min IV rank (40%, range 0-100), Take profit at (50%, range 25-90), Stop loss credit × (2×, range 1.5-4)

   weekly-grind:
   - name: "Weekly Grind", description: "5-16 DTE credit spreads, theta/gamma optimization"
   - DTE range: "5 – 16 DTE", Structure: "Credit spread", Requirement: "Requires credit spread structure"
   - Parameters: Min DTE (5, range 1-10), Max DTE (16, range 10-21), Max short delta (0.25 Δ, range 0.1-0.35), Min IV rank (30%, range 0-100), Take profit at (65%, range 40-90), Stop loss credit × (1.5×, range 1-3)

   trend-rider:
   - name: "Trend Rider", description: "25-65 DTE long calls on strong uptrends"
   - DTE range: "25 – 65 DTE", Structure: "Long call", Requirement: "Requires bullish SMA alignment"
   - Parameters: Min DTE (25, range 15-45), Max DTE (65, range 45-90), Target delta (0.60 Δ, range 0.40-0.80), Max IV rank (50%, range 0-100)

   lottery-ticket:
   - name: "Lottery Ticket", description: "1-8 DTE deep OTM calls, asymmetric payout"
   - DTE range: "1 – 8 DTE", Structure: "Deep OTM call", Requirement: "Catalyst present"
   - Parameters: Max DTE (8, range 1-14), Max delta (0.15 Δ, range 0.05-0.25), Min payout ratio (5:1, range 3-20)

3. Strategy header card (top of page):
   - Border: 1px solid var(--border), border-radius 4px, padding 20px, margin-bottom 16px
   - Name: 18px bold
   - Description: 11px muted, margin-bottom 12px
   - Metadata row (flex, gap 24px): DTE range, Structure, Requirement — each as stacked label/value (same .qf pattern as QuoteBar)

4. Parameters section:
   - Section label: "PARAMETERS" (10px uppercase, letter-spacing 0.6px, muted)
   - Grid of parameter cards: grid-template-columns repeat(4, 1fr), gap 10px
   - Each card: border 1px solid var(--border), border-radius 4px, padding 12px
     - Label: 9px uppercase, letter-spacing 0.4px, muted, margin-bottom 4px
     - Value: 18px bold (e.g., "25 days", "0.3 Δ", "40%", "2×")
     - Range hint: 9px muted, margin-top 2px (e.g., "Range: 15 – 45")
   - Configuration %: format as ##% (no decimals)
   - Configuration multiplier: format as #×
   - Last row may have fewer items — use repeat(2, 1fr) for 2-item rows

**Acceptance Criteria:**
- /strategies/steady-paycheck shows full strategy header with name, description, metadata
- Parameter cards render in grid with correct values and ranges
- All 4 strategies render correctly with their own data
- Configuration % formatted as ##%, multipliers as #×
- Strategy name matches nav rail highlight

---

### Subtask 2.2: Scoring weights section
**Summary:** StrategyPage — read-only scoring weights bars from architecture-plan.md definitions
**Labels:** sprint-3, frontend, experience-framework

**Claude Code Prompt:**

Read architecture-plan.md "Strategy Scorecard — Scoring Engine Data Inputs" section for the weight definitions per strategy.

Add scoring weights section below parameters in StrategyPage.jsx:

1. Section label: "SCORING WEIGHTS" (same label style)
2. Container: border 1px solid var(--border), border-radius 4px, padding 14px, margin-bottom 16px
3. Weight bars for each strategy (read-only, not editable):

   Steady Paycheck weights:
   - Theta Margin Ratio: 30%
   - Probability of Profit: 25%
   - Expected Value: 20%
   - Reward Risk: 15%
   - IV Rank: 10%

   Weekly Grind weights:
   - Theta Gamma Ratio: 35%
   - Probability of Profit: 25%
   - Credit Width %: 20%
   - Expected Value: 15%
   - Liquidity: 5%

   Trend Rider weights:
   - SMA Alignment Score: 30%
   - Delta Quality: 25%
   - Expected Value: 20%
   - IV Percentile Cost: 15%
   - Runway Score: 10%

   Lottery Ticket weights:
   - Payout Ratio: 45%
   - Delta OTM Score: 25%
   - Bid Ask Tightness: 20%
   - Open Interest: 10%

4. Each weight bar row:
   - Metric name: 10px muted, width 140px
   - Bar background: flex 1, height 3px, var(--bg3), border-radius 2px
   - Bar fill: height 100%, border-radius 2px, width = weight%
   - Bar colors: use strategy-consistent colors or rotate through teal/purple/blue/amber
   - Weight %: 10px bold, width 30px, text-align right, var(--green)
   - margin-bottom 10px per row (last row margin-bottom 0)

**Acceptance Criteria:**
- Weight bars render with correct percentages per strategy
- Bars visually proportional to weight values
- Weights are read-only (no interaction)
- All 4 strategies show their unique weight definitions

---

### Subtask 2.3: "Find trades" button + strategy positions section
**Summary:** StrategyPage — "Find trades →" navigation + filtered positions table with Refresh all
**Labels:** sprint-3, frontend, experience-framework

**Claude Code Prompt:**

Read UI-GUIDANCE.md Part 10 (Screen 3) and Part 9 (Claude API Cost Guardrails).

Add below the scoring weights section:

1. "Find trades →" button + helper text:
   - Teal outlined button: "Find trades →"
   - onClick: navigate to /trades?strategy={key}
   - Helper text next to button: "Opens Trades page filtered to {strategy name} parameters" (10px muted)
   - Flex row, gap 10px, align-items center, margin-bottom 24px

2. Strategy positions section:
   - Section label: "{Strategy Name} positions" (e.g., "Steady Paycheck positions")
   - Filter bar (same styling as Positions page filter bar, var(--bg2) bg):
     - Status: Active (dropdown)
     - Type: All / Paper / Live (dropdown)
     - Position count + last refreshed: "3 positions · last refreshed 03-29-2026 16:05" (9px muted, margin-left auto)
     - "↻ Refresh all" button (teal outlined small)

3. Refresh all cost guardrail:
   - If >1 position: show confirmation dialog before refreshing
   - Dialog: overlay rgba(0,0,0,0.6), 1px var(--border), border-radius 6px, 20px padding
   - Title: "Refresh {N} positions?" (12px bold)
   - Body: "This will trigger {N} Claude API calls..." (10px #c9d1d9, line-height 1.5)
   - Actions: "Confirm refresh" (teal outlined) + "Cancel" (neutral outlined)
   - Single position refresh: no confirmation needed

4. Positions table (filtered to this strategy):
   - Import existing positions table/component from PositionsPage
   - Filter positions by strategy = current strategy key
   - Column order matching v3 mockup: chevron → Score → Symbol → Type (Paper/Live badge) → Strike/Spread → Expiration → Premium → Current → P&L → DTE → Health
   - Use ScoreCell, TradeTypeBadge (for Paper/Live), StrategyPill (though single pill since filtered)
   - Health grade: A/B/C/D/F badge with color tokens

5. Below the table: "Backtest data available in Phase 3.3" placeholder card (11px muted, centered)

**Acceptance Criteria:**
- "Find trades →" navigates to /trades?strategy={key}
- Positions table shows only positions for the current strategy
- Refresh all shows confirmation dialog when >1 position
- Single refresh runs without confirmation
- Filter bar renders with Status and Type dropdowns
- Health grades display as colored letter badges

---

## Feature 3: Positions Page v3 Redesign
**Parent:** OTA-365
**Summary:** Positions Page v3 — strategy pills, health grades, white advice badges, versioned re-reads, v3 column order

### Subtask 3.1: Positions table v3 column order + strategy pills + health grades
**Summary:** PositionsPage v3 — new column order, StrategyPill, TradeTypeBadge, ScoreCell, health grade badges
**Labels:** sprint-3, frontend, experience-framework

**Claude Code Prompt:**

Read UI-GUIDANCE.md Part 10 (Screen 4: Positions). Review ota-experience-mockups-v3.html Screen 4.

Redesign web/src/pages/PositionsPage.jsx:

1. Page header: "Positions" (16px bold) + "{N} active" (11px muted), flex row gap 12px

2. Filter bar (var(--bg2) bg, 1px var(--border), border-radius 4px, padding 8px 14px):
   - Status: Active / All / Closed (dropdown)
   - Type: All / Paper / Live (dropdown)
   - Strategy: All / Steady Paycheck / Weekly Grind / etc. (dropdown)
   - Symbol: text input filter (placeholder "e.g. META", width 60px)
   - Group by: Strategy / Symbol / Health (dropdown, margin-left auto)
   - "↻ Refresh all" button (teal outlined small)

3. Group headers (collapsible):
   - Chevron (▼/▶) + strategy name (12px bold, var(--teal)) + count (10px muted)
   - Click toggles collapse/expand
   - Groups determined by "Group by" dropdown selection

4. Position row column order (NO row numbers):
   [chevron] [Score] [Symbol] [Pos Type] [Strategy] [Strike/Spread] [Expiration] [Premium] [Current] [P&L] [DTE] [Health]

   - Score: use <ScoreCell score={position.score} />
   - Symbol: font-weight 700
   - Pos Type: badge — "Paper" in blue (rgba(96,165,250,0.12), var(--blue)) or "Live" in green (rgba(74,222,128,0.12), var(--green)). 9px bold, 2px 6px padding, 3px border-radius.
   - Strategy: use <StrategyPill strategy={position.strategy} /> (abbreviated 2-letter pill)
   - P&L: formatted as ±##.00 (±##.00%), green positive, red negative, sign always shown
   - Health: single letter badge A/B/C/D/F
     - A: bg rgba(74,222,128,0.15), color var(--green)
     - B: bg rgba(74,222,128,0.1), color var(--green)
     - C: bg rgba(245,158,11,0.15), color var(--amber)
     - D: bg rgba(245,158,11,0.1), color var(--amber)
     - F: bg rgba(248,113,113,0.15), color var(--red)
     - 11px bold, 22px × 22px, inline-flex centered, border-radius 3px

5. Replace all existing full-name strategy badges (e.g., green "Steady Paycheck" pill) with the abbreviated <StrategyPill /> component

6. Refresh all cost guardrail: same confirmation dialog as Strategy Page (Part 9 spec)

**Acceptance Criteria:**
- Column order matches v3 mockup (score after chevron, pills not full names)
- StrategyPill renders abbreviated 2-letter pills (not full-name badges)
- Health grades render as colored single-letter badges
- Position type shows "Paper" (blue) or "Live" (green)
- P&L with sign and color
- Group headers collapsible with chevron
- Group by dropdown changes grouping
- Refresh all shows confirmation when >1 position

---

### Subtask 3.2: Position expansion — versioned re-reads with white advice badge
**Summary:** Positions expansion v3 — versioned re-reads, verdict + score + white advice badge, exit plan
**Labels:** sprint-3, frontend, experience-framework

**Claude Code Prompt:**

Read UI-GUIDANCE.md Part 8 (Claude's Voice) and Part 10 (Screen 4 expanded). Review ota-experience-mockups-v3.html Screen 4 — the expanded SPY position showing re-reads.

Update the position expansion panel in PositionsPage.jsx:

1. When a position row is clicked, expand inline below it (same pattern as Trades page)

2. Most recent re-read (top):
   - Header row: flex, align-items center, gap 8px, margin-bottom 6px
     - Verdict badge: EXECUTE/WAIT/PASS (same styling as Trades Section E)
     - Score: 11px bold, colored by threshold (e.g., "58.00" in amber)
     - Claude summary advice badge: WHITE OUTLINED (not purple)
       - bg rgba(255,255,255,0.06), border 1px solid rgba(255,255,255,0.35), color #e6edf3
       - 9px bold, 3px 10px padding, 3px border-radius
       - Text like "SPY drifts lower, thesis marginally intact"
     - Timestamp: 9px muted, margin-left auto (e.g., "03-31-2026 02:20")

   - Analysis text: border-left 2px solid var(--border), padding 8px 12px, margin 6px 0 6px 20px, 10px, #c9d1d9, line-height 1.6

   - Exit plan: flex row, gap 20px, 10px
     - "Take profit:" label (muted) + value (green)
     - "Hard stop:" label (muted) + value (red)

3. Previous re-reads (below most recent):
   - Each previous re-read has same header format (verdict + score + advice + timestamp)
   - Collapsed by default — show header only, click to expand analysis
   - Original assessment marked with "Original" label next to timestamp
   - Most recent first, original last

4. Only one position expanded at a time

**Acceptance Criteria:**
- Expanded position shows versioned re-reads (most recent first)
- Verdict badge with correct EXECUTE/WAIT/PASS coloring
- Claude advice badge is WHITE OUTLINED (not purple)
- Analysis text in bordered left-border container
- Exit plan shows take profit (green) and hard stop (red) levels
- Previous re-reads collapsible
- Original assessment labeled "Original"
- Timestamps formatted as mm-dd-yyyy hh:mm

---

### Subtask 3.3: Refresh all confirmation dialog component
**Summary:** RefreshConfirmDialog — reusable confirmation dialog for multi-position Claude API refresh
**Labels:** sprint-3, frontend, framework-portable

**Claude Code Prompt:**

Read UI-GUIDANCE.md Part 9 (Claude API Cost Guardrails).

Create web/src/components/RefreshConfirmDialog.jsx:

1. Props: positionCount (number), onConfirm (function), onCancel (function), isOpen (boolean)

2. Only renders when isOpen is true

3. Dialog styling:
   - Overlay: rgba(0,0,0,0.6), 1px solid var(--border), border-radius 6px, 20px padding
   - Max-width 400px, centered (or positioned inline like the mockup)
   - Title: "Refresh {positionCount} positions?" (12px bold)
   - Body: "This will trigger {positionCount} Claude API calls to update scores, synopses, and exit levels for all positions matching your current filter. Each position will update as its call returns." (10px #c9d1d9, line-height 1.5, margin-bottom 12px)
   - Actions: flex row, gap 10px
     - "Confirm refresh" (teal outlined button)
     - "Cancel" (neutral outlined button)

4. Reusable on both PositionsPage and StrategyPage

**Acceptance Criteria:**
- Dialog renders only when isOpen is true
- Shows correct position count in title and body
- Confirm triggers onConfirm callback
- Cancel triggers onCancel callback
- Styling matches mockup (overlay, bordered, rounded)
- Component exported for reuse

---

## Feature 4: Document Updates
**Parent:** OTA-365
**Summary:** Update living docs for Sprint 3 — CLAUDE.md, project-hierarchy.md

### Subtask 4.1: Update docs for Strategy Pages + Positions v3
**Summary:** Update CLAUDE.md and project-hierarchy.md for Strategy Pages and Positions v3 changes
**Labels:** sprint-3, documentation

---

## Dependency Graph

```
Feature 1 (Sprint 2 Fixes)     Feature 3.3 (RefreshConfirmDialog)
  └─ 1.1 SMA/pills/B/C fix       └─ standalone component
       │                               │
       ▼                               ▼
Feature 2 (Strategy Pages)     Feature 3 (Positions v3)
  └─ 2.1 Header + params        └─ 3.1 Table v3 + pills + health
  └─ 2.2 Weights                 └─ 3.2 Expansion + re-reads
  └─ 2.3 Find trades + positions (depends on 3.1 for reusable positions components)
                │
                ▼
Feature 4 (Doc updates — last)
  └─ 4.1 Update docs
```

## Parallel Execution Plan (2 terminals)

**Terminal 1:** 1.1 (Sprint 2 fixes) → 2.1 (header + params) → 2.2 (weights) → 2.3 (Find trades + positions)
**Terminal 2:** 3.3 (RefreshConfirmDialog) → 3.1 (Positions table v3) → 3.2 (Expansion + re-reads)
**Integration:** 4.1 (doc updates — after both terminals commit)

## Ticket Summary

| Level | Count |
|-------|-------|
| Epic | 1 (OTA-365) |
| Features | 4 |
| Subtasks | 8 |
| **Total** | **13** |
