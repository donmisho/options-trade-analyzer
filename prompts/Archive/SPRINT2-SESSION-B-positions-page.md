OTA-362 OTA-363 OTA-364

## Sprint 2 Session B — Positions Page v3 Redesign
### Run in Claude Code Terminal 2 (parallel with Session A — Strategy Page)

Read UI-GUIDANCE.md (the ENTIRE file) and review ota-experience-mockups-v3.html Screen 4 before starting. Pay special attention to Part 8 (Claude's Voice — summary advice badge styling) and Part 9 (Cost Guardrails).

This session ONLY modifies web/src/pages/PositionsPage.jsx and its related position components. Do NOT modify StrategyPage.jsx — that's being built in the parallel session.

---

### Step 1 — v3 Column Order + Shared Components (OTA-362)

Update web/src/pages/PositionsPage.jsx:

1. Replace full-name strategy badges (e.g., green "Steady Paycheck" badges) with StrategyPill components (2-letter abbreviations SP/WG/TR/LT with tooltips). Import from web/src/components/StrategyPill.jsx.

2. Replace any raw score displays with ScoreCell component (bar + number with threshold coloring). Import from web/src/components/ScoreCell.jsx.

3. Replace any raw trade type text with TradeTypeBadge component. Position type badges: "Paper" = blue (rgba(96,165,250,0.12), color var(--blue)), "Live" = green (rgba(74,222,128,0.12), color var(--green)). Font 9px bold, 2px 6px padding, 3px border-radius.

4. Add health grade column using PositionHealthBadge.jsx if it exists, or create inline:
   - Single letter A/B/C/D/F
   - 22x22px badge, inline-flex, center aligned, border-radius 3px, 11px bold
   - A: bg rgba(74,222,128,0.15), color var(--green)
   - B: bg rgba(74,222,128,0.1), color var(--green)
   - C: bg rgba(245,158,11,0.15), color var(--amber)
   - D: bg rgba(245,158,11,0.1), color var(--amber)
   - F: bg rgba(248,113,113,0.15), color var(--red)

5. Update column order to match v3 mockup:
   chevron → Score → Symbol (bold) → Type (Paper/Live badge) → Strategy (pill) → Strike/Spread → Expiration → Premium → Current → P&L → DTE → Health

6. P&L format: ±##.00 (±##.00%) with sign always shown, green for positive, red for negative. No $ prefix.

7. Remove any old-style "PERF" column or red dot indicators — replace with Health grade badge.

**Verify:** Strategy pills show 2-letter codes with tooltips. Score column has bar + number. Health column shows letter grades. Column order matches mockup. No old-style badges visible.

---

### Step 2 — Group Headers + Filter Bar + Group By (OTA-364)

Update Positions page layout elements:

1. Page title: "Positions" 16px bold + "{n} active" (11px muted) — matching the diamond icon if it exists in current implementation.

2. Group headers: chevron (▼/▶), strategy name (12px bold, var(--teal)), position count (10px muted). The current page shows "STEADY PAYCHECK 3" in uppercase — update to match v3 mockup styling:
   - Not uppercase (use title case from strategy config)
   - Color var(--teal) for the name
   - Click toggles collapse/expand

3. Filter bar (var(--bg2) bg, 1px var(--border), border-radius 4px, padding 8px 14px):
   - Status: dropdown (Active/All/Closed)
   - Type: dropdown (All/Paper/Live)
   - Strategy: dropdown (All/Steady Paycheck/Weekly Grind/Trend Rider/Lottery Ticket)
   - Symbol: text input with placeholder "e.g. META"
   - Group By: dropdown (Strategy/Symbol/Health) — right-aligned with margin-left auto
   - "↻ Refresh all" button: teal outlined small (padding 4px 10px, 10px font)

4. "Group by" must actually work: Strategy (default) groups by strategy name, Symbol groups by ticker, Health groups by grade letter. Changing the dropdown re-renders the grouping.

5. Cost guardrail on "Refresh all" when >1 position:
   - Confirmation overlay: rgba(0,0,0,0.6) bg, 1px var(--border), border-radius 6px, 20px padding, max-width 400px
   - Title: "Refresh {n} positions?" (12px bold)
   - Body: "This will trigger {n} Claude API calls to update scores, synopses, and exit levels for all positions matching your current filter." (10px #c9d1d9, line-height 1.5)
   - Actions: "Confirm refresh" (teal outlined) + "Cancel" (neutral outlined)
   - Single-position refresh (clicking refresh icon on a row) runs without confirmation

**Verify:** Group headers match v3 style. Filter bar functional. Group By changes grouping. Refresh all shows confirmation for >1.

---

### Step 3 — Versioned Re-reads + White Advice Badge (OTA-363)

Update the Positions page expansion to render versioned re-reads matching v3:

1. When a position row is expanded, show all Claude re-reads in reverse chronological order (most recent first). Each re-read shows:

   **Header row** (flex, align-items center, gap 8px, margin-bottom 6px):
   - Verdict badge: EXECUTE (bg rgba(74,222,128,0.15), color var(--green)), WAIT (bg rgba(245,158,11,0.15), color var(--amber)), PASS (bg rgba(248,113,113,0.15), color var(--red)). Font 9px bold, 3px 10px padding, 3px border-radius.
   - Score: ##.00 format, 11px bold, colored by threshold (green 70+, amber 40-69, red 0-39)
   - Claude summary advice badge — **WHITE OUTLINED, NOT PURPLE:**
     - background: rgba(255,255,255,0.06)
     - border: 1px solid rgba(255,255,255,0.35)
     - color: #e6edf3
     - font-size: 9px, font-weight: 700, padding: 3px 10px, border-radius: 3px
     - Text is a short synopsis like "SPY drifts lower, thesis marginally intact"
   - Timestamp: 9px muted, margin-left auto. Format: mm-dd-yyyy hh:mm
   - "Original" label on the first (oldest) assessment: 9px muted

   **Claude's Read text** (only on expanded re-read):
   - border-left: 2px solid var(--border)
   - padding: 8px 12px, margin: 6px 0 6px 20px
   - font-size: 10px, color: #c9d1d9, line-height: 1.6

   **Exit plan** (only on expanded re-read):
   - flex row, gap 20px, font-size 10px, margin-top 6px
   - "Take Profit:" label (muted) + price (var(--green))
   - "Hard Stop:" label (muted) + price (var(--red))

2. The MOST RECENT re-read is fully expanded (shows analysis text + exit plan). Older re-reads show only the header row (verdict + score + summary + timestamp) and expand on click.

3. If a strategy name appears inside the advice badge, render it in that strategy's color using STRATEGY_COLORS from StrategyPill.jsx.

**Verify:** Expanded position shows versioned re-reads (newest first). Most recent fully expanded. Older ones collapsed to header (expandable). Verdict badges correct colors. Summary advice is WHITE OUTLINED. Timestamps in mm-dd-yyyy hh:mm. Exit plan shows Take Profit (green) and Hard Stop (red). "Original" label on oldest assessment.

---

### Commit

Commit message: OTA-362 OTA-363 OTA-364 feat: positions page v3 — pills, health grades, versioned re-reads, white advice badge, group by

Recommended QA level: 2 (full regression — PositionsPage touches multiple components)
