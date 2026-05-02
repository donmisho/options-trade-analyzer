OTA-343 OTA-344 OTA-345 OTA-346 OTA-347

## SESSION 2 — Trade Detail Section Components
### Run in Claude Code Terminal 2 (parallel with Session 1)

## IMPORTANT — Read First
Read UI-GUIDANCE.md (the ENTIRE file) before making any changes. It is the single source
of truth. Also open ota-experience-mockups-v3.html and study Screen 2's trade detail
expansion (the .td-exp section with Sections A through E).

This session creates all files under web/src/components/TradeDetail/.
Do NOT modify Layout.jsx, App.jsx, TradesPage.jsx, or any files outside TradeDetail/ —
those are being built by a parallel session.

Create the directory: web/src/components/TradeDetail/

---

### Step 1 — SectionA.jsx (OTA-343) — Trade Header

Create web/src/components/TradeDetail/SectionA.jsx

Props: trade (object with type, strikes, expiry, dte, entry, maxProfit, maxLoss,
breakeven, rewardRisk, profitTrigger, stopTrigger, timeExit)

The outermost wrapper has the teal top border (this goes on the parent container that
wraps ALL sections, but define the styling here as a CSS class for the parent to use):
- border-top: 2px solid rgba(45,212,191,0.35)
- padding: 16px 0

Section A content card:
- border: 1px solid var(--border), border-radius 4px, padding 10px 14px
- display flex, flex-wrap wrap, gap 14px, margin-bottom 12px

Contents left to right:
1. Import and render <TradeTypeBadge type={trade.type} /> — at 12px font-weight 700
   NOTE: TradeTypeBadge is being built in the parallel session. Import it but if it
   doesn't exist yet, create a local inline fallback that renders the type as text.
2. Context label: derive from trade type.
   - If type contains "DEBIT" → "(bearish — you pay to enter)" or "(bullish — you pay to enter)"
   - If type contains "CREDIT" → "(bearish — you receive credit)" or "(bullish — you receive credit)"
   - Bull/Bear determined by first word
   - Style: 10px, color var(--muted)
3. Metadata fields as stacked label/value pairs:
   Each field: label on top (9px uppercase, letter-spacing 0.4px, muted),
   value below (12px bold)

   Fields:
   - Strikes: e.g., "630 / 620"
   - Expiry: use formatDate() from web/src/utils/formatDate.js → mm-dd-yyyy
   - DTE: e.g., "17d"
   - Entry: e.g., "3.66 debit (366.00 / contract)" — NO $ prefix
   - Max profit: green, ##.00
   - Max loss: red, ##.00
   - Breakeven: ##.00
   - R:R: #.##:1 format
   - Profit trigger: green
   - Stop trigger: red
   - Time exit: formatDate()

Export default SectionA.

---

### Step 2 — SectionB.jsx (OTA-344) — Exit Scenario Table

Create web/src/components/TradeDetail/SectionB.jsx

Props: scenarios (array of { price, spreadValue, pnl, pnlPct, probability,
expectedValue, exitSignal }), totalEV (number)

Section label above table: "EXIT SCENARIO ANALYSIS"
- font-size 10px, text-transform uppercase, letter-spacing 0.6px, color var(--muted)
- margin: 16px 0 8px

Table columns:
Underlying price | Spread value | P&L / contract | P&L % | Probability | Expected value | Exit signal

Table styling:
- width 100%, border-collapse collapse
- th: font-size 9px, text-transform uppercase, letter-spacing 0.4px, color var(--muted),
  padding 6px 8px, text-align right (first col left), font-weight 400,
  border-bottom 1px solid var(--border)
- td: font-size 11px, padding 6px 8px, text-align right (first col left),
  border-bottom 1px solid rgba(48,54,61,0.3)

Loss zone: rows where pnl < 0 get background rgba(248,113,113,0.03)

P&L formatting:
- Positive: color var(--green), "+634.00", "+173.22%"
- Negative: color var(--red), "-366.00", "-100.00%"
- Sign ALWAYS shown. Format ##.00.

Probability: ##.00% format

Exit signal badges (9px bold, letter-spacing 0.3px):
- "MAX PROFIT" → var(--green)
- "BREAKEVEN" → var(--amber)
- "STOP" → var(--red)
- "TIME EXIT" → var(--muted)

Footer row:
- td colspan 5: "Total expected value" font-weight 700, text-align left
- td: EV value, font-weight 700, colored green if positive, red if negative

Export default SectionB.

---

### Step 3 — SectionC.jsx (OTA-345) — Outcome Summary

Create web/src/components/TradeDetail/SectionC.jsx

Props: outcome (object with pMaxProfit, pBreakeven, pPartial, pMaxLoss,
expectedValue, evPctRisk)

Section label: "OUTCOME SUMMARY" (same style as SectionB label)

Container: display flex, gap 1px, border 1px solid var(--border), border-radius 4px,
overflow hidden, margin-bottom 12px.

Six cells, each separated by border-left 1px solid var(--border) (except first):
- flex 1, padding 12px 14px

Cell internals:
- Label: font-size 9px, text-transform uppercase, letter-spacing 0.3px,
  color var(--muted), margin-bottom 4px
- Value: font-size 16px, font-weight 700

Cells:
1. "P(MAX PROFIT)" → value in var(--green), format ##.00%
2. "P(BREAKEVEN OR BETTER)" → value in var(--green), format ##.00%
3. "P(PARTIAL PROFIT)" → default text color, format ##.00%
4. "P(MAX LOSS)" → value in var(--red), format ##.00%
5. "EXPECTED VALUE" → colored by sign (green +, red -), format ±##.00
6. "EV % OF RISK" → default text color, format ##.00%
   Below value: badge div
   - "POSITIVE EV" if evPctRisk > 0: bg rgba(74,222,128,0.1), color var(--green)
   - "NEGATIVE EV" if evPctRisk <= 0: bg rgba(248,113,113,0.1), color var(--red)
   - font-size 9px, font-weight 700, padding 3px 8px, border-radius 3px,
     display inline-block, margin-top 4px

Export default SectionC.

---

### Step 4 — SectionD.jsx (OTA-347) — Probability Matrix Placeholder

Create web/src/components/TradeDetail/SectionD.jsx

Props: none

Section label: "PROBABILITY MATRIX" (same style)

Placeholder card:
- border 1px solid var(--border), border-radius 4px, padding 20px, text-align center
- Text: "Probability matrix — available when Phase 2.11 backend is complete"
- font-size 11px, color var(--muted)

Export default SectionD.

---

### Step 5 — SectionE.jsx (OTA-346) — Claude's Read

Create web/src/components/TradeDetail/SectionE.jsx

Props: evaluation (object with verdict, bestStrategy, summaryText, analysis,
keyLevelPrice, keyLevelExplanation), tradeContext (string like "SPY · BEAR PUT · 630/620 · 04-16"),
onEvaluate, onFollow, onTakePosition, onFollowUp, onDiscard

Two states: pre-evaluation (evaluation is null) and post-evaluation.

**Pre-evaluation state:**
Just render the Evaluate button (teal outlined: bg rgba(45,212,191,0.1),
border 1px solid rgba(45,212,191,0.4), color var(--teal), padding 7px 16px,
border-radius 4px, font-size 11px, font-family monospace, width auto).
onClick → onEvaluate()

**Post-evaluation state:**
Container: border 1px solid var(--border), border-radius 4px, padding 14px 16px,
margin-top 12px

Header row: display flex, align-items center, gap 10px, flex-wrap wrap, margin-bottom 10px
1. Label "CLAUDE'S READ": font-size 9px, text-transform uppercase,
   letter-spacing 0.6px, color var(--muted)
2. Verdict badge: font-size 10px, font-weight 700, padding 3px 10px, border-radius 3px
   - "EXECUTE" → bg rgba(74,222,128,0.15), color var(--green)
   - "WAIT" → bg rgba(245,158,11,0.15), color var(--amber)
   - "PASS" → bg rgba(248,113,113,0.15), color var(--red)
3. Claude summary advice badge — THIS IS A WHITE OUTLINED BADGE, NOT PURPLE:
   - background rgba(255,255,255,0.06)
   - border 1px solid rgba(255,255,255,0.35)
   - color #e6edf3
   - font-size 9px, font-weight 700, padding 3px 10px, border-radius 3px
   - display inline-flex, align-items center, gap 4px
   - Text format: "Best fit: " in #e6edf3 + strategy name in strategy color
   - Import STRATEGY_COLORS from StrategyPill.jsx (or define locally if not available yet)
     to get the correct color for the strategy name
4. Trade context: font-size 9px, color var(--muted), margin-left auto
5. Evaluate button (teal outlined small: padding 4px 10px, 10px font)

Analysis text: font-size 10px, color #c9d1d9, line-height 1.65, margin-bottom 8px.
NON-italic. Multiple paragraphs (map over analysis array or split by \n\n).

Key level callout:
- background var(--bg2), border-left 2px solid var(--amber)
- padding 6px 10px, font-size 10px, margin 8px 0, border-radius 0 4px 4px 0
- Price in var(--amber) font-weight 700, followed by explanation text in default color

Actions row: display flex, gap 10px, margin-top 12px, align-items center
1. "Follow (Paper)" — teal outlined button (padding 7px 16px)
2. "Take Position (Live)" — green filled button: bg rgba(74,222,128,0.12),
   border 1px solid rgba(74,222,128,0.45), color var(--green), font-weight 700
3. Follow-up input: flex 1, bg var(--bg), border 1px solid var(--border),
   color var(--text), font-family monospace, font-size 10px, padding 7px 12px,
   border-radius 4px, placeholder "Ask a follow-up about this trade..."
4. "Discard ✕" — neutral outlined: bg transparent, border 1px solid var(--border),
   color var(--muted)

ALL buttons: width auto (never full-width stretch), font-family monospace, font-size 11px.

Wire callbacks: Follow → onFollow(), Take Position → onTakePosition(),
follow-up submit (Enter key) → onFollowUp(text), Discard → onDiscard()

Export default SectionE.

---

### Step 6 — Index file

Create web/src/components/TradeDetail/index.js:
```js
export { default as SectionA } from './SectionA';
export { default as SectionB } from './SectionB';
export { default as SectionC } from './SectionC';
export { default as SectionD } from './SectionD';
export { default as SectionE } from './SectionE';
```

---

### Commit Checkpoint

After completing all steps, verify each component renders without errors when imported
individually. Test with mock data if needed.

Wait for Session 1 to complete before running Session 3 (integration).

Recommended QA level: 1 (targeted — TradeDetail components only)

Commit message: OTA-343 OTA-344 OTA-345 OTA-346 OTA-347 feat: trade detail Sections A-E components
