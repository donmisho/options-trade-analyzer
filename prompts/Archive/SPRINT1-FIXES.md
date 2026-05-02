OTA-352 OTA-353 OTA-354 OTA-355

## Sprint 1 Integration Fixes — Run First (Single Session)
### Covers: SMA chart, StrategyPill wiring, Section B/C gaps, Puts & Calls verification

Read UI-GUIDANCE.md (the ENTIRE file) before starting. These are wiring bugs from Sprint 1 where components exist but aren't connected properly.

---

### Fix 1 — SMA Chart (OTA-352)

The SMA chart component works on the Security Strategies page (candlestick with 8/21/50 day SMAs, SMA Configuration panel, Chart Range selector 30d/90d/180d). But TradesPage.jsx renders a placeholder div instead of importing the real chart.

1. Find the chart component used on the Security Strategies page. Search for the component that renders candlestick data with SMA overlays — likely in web/src/components/.
2. In TradesPage.jsx, import that chart component.
3. Replace the placeholder div ("SMA chart — configurable moving averages") with the real chart component.
4. Pass the active symbol so it loads correct data.
5. The chart renders between QuoteBar and the trade-structure sections, matching Security Strategies layout.
6. Replicate the same props pattern Security Strategies uses (symbol, SMA config, date range).

**Verify:** /trades?symbol=SPY shows a real candlestick chart with SMA lines, SMA Configuration panel (8-day, 21-day, 50-day), Chart Range selector (30d, 90d, 180d). Chart updates when symbol changes. No placeholder text visible.

---

### Fix 2 — StrategyPill Wiring (OTA-353)

The Strategies column header appears in the ResultsTable but cells are empty. StrategyPill component exists but isn't wired into the column config.

1. Verify web/src/components/StrategyPill.jsx exists and exports correctly (including STRATEGY_COLORS).
2. Open web/src/config/verticals-columns.js. Find the Strategies column definition.
3. Update its render function to map over the trade's strategy tags and render StrategyPill for each. Check what field the backend returns — likely `strategies`, `strategy_tags`, or `matched_strategies`.
4. Do the same for web/src/config/long-options-columns.js.
5. If the backend analysis response doesn't include strategy tags yet, add a temporary mapper that assigns strategies based on trade_structure and DTE (e.g., credit spreads 25-50 DTE → steady_paycheck, 5-16 DTE → weekly_grind). This is a stopgap until Phase 2.9 scoring is wired.

**Verify:** Trade rows show colored 2-letter pills (SP, WG, TR, LT) in the Strategies column. Tooltips appear on hover. Multiple pills can appear per row.

---

### Fix 3 — Section C Missing + Section B Empty (OTA-354)

**Problem 1:** Section C (Outcome Summary) is completely missing from the expansion. The render order jumps from Section B directly to Section D. Section C should show 6 horizontal metric cells (P(max profit), P(breakeven+), P(partial), P(max loss), EV, EV % of risk) with a POSITIVE/NEGATIVE EV badge.

**Problem 2:** Section B (Exit Scenario Table) renders headers and footer but no data rows. The scenarios array is empty or not mapped from the analysis response.

1. Open TradesPage.jsx (or wherever the trade detail expansion is assembled).
2. Check imports — verify SectionC is imported from TradeDetail/. If not, add the import.
3. Find the render order of sections in the expansion div. Ensure it goes: SectionA → SectionB → SectionC → SectionD → SectionE. Add SectionC if missing.
4. For Section B data: inspect the analysis response object returned by the verticals/long-calls API. The scenarios need to be either returned by the backend or computed on the frontend from trade parameters. Check how the old VerticalsPage computed/displayed exit scenarios and replicate that data flow.
5. For Section C data: map probability and EV fields from the analysis response to SectionC props (pMaxProfit, pBreakeven, pPartial, pMaxLoss, expectedValue, evPctRisk). If the backend doesn't return these yet, compute from the trade data: P(max profit) from delta-derived probability, EV from (credit × PoP) - (max_loss × (1-PoP)), etc.
6. If SectionC.jsx doesn't exist at all, create it per UI-GUIDANCE.md Part 10 Section C spec.

**Verify:** Section C renders between B and D showing 6 horizontal metric cells. POSITIVE/NEGATIVE EV badge appears. Section B populates with scenario data rows. Loss zone rows have subtle red background. All values formatted per house rules (##.00, no $ prefix, ##.00%).

---

### Fix 4 — Puts & Calls / Iron Condors Sections (OTA-355)

Screenshots only show the Vertical spreads section. Confirm the other two sections render.

1. Scroll below the Vertical spreads section on TradesPage. Verify "Puts & calls" section header renders (collapsed by default) with result count and Config button.
2. Verify "Iron condors" section header renders (collapsed, opacity 0.5, "· coming soon" italic, not clickable, no Config button).
3. If either is missing, check the collapsible sections array in TradesPage.jsx and ensure all three sections are defined.
4. If Puts & calls expands, verify it loads data from the long-calls analysis endpoint and renders its own ResultsTable with the long-options column config.
5. Verify no duplicate section headers or rendering artifacts.

**Verify:** All three sections visible in order. Puts & calls expands with data. Iron condors grayed out with "coming soon".

---

### Commit

Commit message: OTA-352 OTA-353 OTA-354 OTA-355 fix: SMA chart import, strategy pills wiring, Section B/C data, section verification

Recommended QA level: 2 (multiple components, integration points)
