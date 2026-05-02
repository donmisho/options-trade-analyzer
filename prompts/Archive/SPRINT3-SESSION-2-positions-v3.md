OTA-374 OTA-372 OTA-373

## SESSION 2 — Positions Page v3 Redesign
### Run in Claude Code Terminal 2 (parallel with Session 1)

## IMPORTANT — Read First
Read UI-GUIDANCE.md (the ENTIRE file) before making any changes. It is the single source
of truth. Also review ota-experience-mockups-v3.html Screen 4 (Positions) — study both
the table layout and the expanded position with versioned re-reads.

This session covers the RefreshConfirmDialog component and the full Positions page v3
redesign. Do NOT modify StrategyPage.jsx or TradesPage.jsx — those are being built by
Terminal 1.

---

### Step 1 — RefreshConfirmDialog Component (OTA-374)

Create web/src/components/RefreshConfirmDialog.jsx:

Props: positionCount (number), onConfirm (function), onCancel (function), isOpen (boolean)

Only renders when isOpen is true. Returns null otherwise.

```jsx
const RefreshConfirmDialog = ({ positionCount, onConfirm, onCancel, isOpen }) => {
  if (!isOpen) return null;

  return (
    <div style={{
      background: 'rgba(0,0,0,0.6)',
      border: '1px solid var(--border)',
      borderRadius: '6px',
      padding: '20px',
      maxWidth: '400px',
      margin: '12px 0'
    }}>
      <div style={{ fontSize: '12px', fontWeight: 700, marginBottom: '8px' }}>
        Refresh {positionCount} positions?
      </div>
      <div style={{
        fontSize: '10px', color: '#c9d1d9', lineHeight: 1.5, marginBottom: '12px'
      }}>
        This will trigger {positionCount} Claude API calls to update scores,
        synopses, and exit levels for all positions matching your current filter.
        Each position will update as its call returns.
      </div>
      <div style={{ display: 'flex', gap: '10px' }}>
        {/* Teal outlined "Confirm refresh" */}
        <button onClick={onConfirm} style={{
          background: 'rgba(45,212,191,0.1)',
          border: '1px solid rgba(45,212,191,0.4)',
          color: 'var(--teal)', padding: '7px 16px', borderRadius: '4px',
          fontSize: '11px', fontFamily: 'monospace', cursor: 'pointer', width: 'auto'
        }}>Confirm refresh</button>
        {/* Neutral outlined "Cancel" */}
        <button onClick={onCancel} style={{
          background: 'transparent',
          border: '1px solid var(--border)',
          color: 'var(--muted)', padding: '7px 14px', borderRadius: '4px',
          fontSize: '11px', fontFamily: 'monospace', cursor: 'pointer', width: 'auto'
        }}>Cancel</button>
      </div>
    </div>
  );
};

export default RefreshConfirmDialog;
```

This is a reference implementation — adjust to match your project's styling patterns
(CSS modules, styled-components, inline styles — use whatever the codebase uses).

---

### Step 2 — Positions Table v3 (OTA-372)

Redesign web/src/pages/PositionsPage.jsx:

**2a. Page header:**
- "Positions" (16px bold) + "{N} active" (11px muted)
- Flex row, gap 12px, margin-bottom 12px

**2b. Filter bar:**
- Background: var(--bg2), border: 1px solid var(--border), border-radius 4px,
  padding 8px 14px, flex row, gap 12px, flex-wrap wrap, margin-bottom 12px
- Filters (each: label 10px muted + dropdown 10px):
  - Status: Active / All / Closed
  - Type: All / Paper / Live
  - Strategy: All / Steady Paycheck / Weekly Grind / Trend Rider / Lottery Ticket
  - Symbol: text input (placeholder "e.g. META", width 60px, 10px)
  - Group by: Strategy / Symbol / Health (margin-left auto)
  - "↻ Refresh all" button (teal outlined small: padding 4px 10px, 10px)

**2c. Refresh all behavior:**
- Import RefreshConfirmDialog from step 1
- Count positions matching current filters
- If count > 1: show RefreshConfirmDialog
- If count == 1: refresh immediately without confirmation
- Track isRefreshDialogOpen state

**2d. Group headers (collapsible):**
- When Group by = "Strategy": group by strategy name
- Header: flex row, align-items center, padding 10px 0, cursor pointer,
  border-bottom 1px solid var(--border), gap 8px
  - Chevron: ▼ expanded / ▶ collapsed (9px muted, width 14px)
  - Strategy name: 12px bold, color var(--teal)
  - Count: 10px muted (e.g., "3")
- Click toggles expand/collapse

**2e. Position row columns (NO row numbers):**
[chevron] [Score] [Symbol] [Pos Type] [Strategy] [Strike/Spread] [Expiration] [Premium] [Current] [P&L] [DTE] [Health]

Column rendering:
- Chevron: ▶ collapsed / ▼ expanded (9px muted)
- Score: import ScoreCell from web/src/components/ScoreCell.jsx
- Symbol: font-weight 700
- Pos Type badge:
  - "Paper": bg rgba(96,165,250,0.12), color var(--blue), 9px bold, 2px 6px padding, 3px radius
  - "Live": bg rgba(74,222,128,0.12), color var(--green), same styling
- Strategy: import StrategyPill from web/src/components/StrategyPill.jsx
  - Render abbreviated 2-letter pill (SP/WG/TR/LT) with tooltip
  - REMOVE all existing full-name strategy badges (the green "Steady Paycheck",
    "Weekly Grind" etc. badges visible in the current screenshots)
- Strike/Spread: e.g., "585/590" or "142/140"
- Expiration: formatDate() → mm-dd-yyyy
- Premium: ##.00 (no $ prefix)
- Current: ##.00 (no $ prefix)
- P&L: ±##.00 (±##.00%) — green positive with "+", red negative with "-", sign always shown
- DTE: number
- Health grade badge:
  - A: bg rgba(74,222,128,0.15), color var(--green)
  - B: bg rgba(74,222,128,0.1), color var(--green)
  - C: bg rgba(245,158,11,0.15), color var(--amber)
  - D: bg rgba(245,158,11,0.1), color var(--amber)
  - F: bg rgba(248,113,113,0.15), color var(--red)
  - 11px bold, width 22px, height 22px, inline-flex, align-items center,
    justify-content center, border-radius 3px

**2f. Table styling:**
- Table rows: transparent background (no alternating stripes)
- Hover: rgba(45,212,191,0.02)
- Expanded: rgba(45,212,191,0.03)
- Headers: 10px uppercase, letter-spacing 0.4px, muted, font-weight 400
- Cells: 11px, padding 8px 6px

---

### Step 3 — Position Expansion with Versioned Re-reads (OTA-373)

Update the expanded row content in PositionsPage.jsx:

**3a. Expansion container:**
- Only one row expanded at a time
- Expanded row spans full table width via colspan

**3b. Most recent re-read (top):**
- Header row: flex, align-items center, gap 8px, margin-bottom 6px
  - Verdict badge: EXECUTE / WAIT / PASS
    - EXECUTE: bg rgba(74,222,128,0.15), color var(--green)
    - WAIT: bg rgba(245,158,11,0.15), color var(--amber)
    - PASS: bg rgba(248,113,113,0.15), color var(--red)
    - 9px bold (in the positions context, slightly smaller than trades), 3px 10px padding,
      border-radius 3px
  - Score: 11px bold, colored by threshold (green/amber/red)
  - Claude summary advice badge — THIS IS A WHITE OUTLINED BADGE:
    - background: rgba(255,255,255,0.06)
    - border: 1px solid rgba(255,255,255,0.35)
    - color: #e6edf3
    - font-size: 9px, font-weight: 700, padding: 3px 10px, border-radius: 3px
    - Text like "SPY drifts lower, thesis marginally intact"
    - NOT purple. NOT the old badge style.
  - Timestamp: 9px muted, margin-left auto (formatted mm-dd-yyyy hh:mm)

**3c. Analysis text:**
- border-left: 2px solid var(--border)
- padding: 8px 12px
- margin: 6px 0 6px 20px
- font-size: 10px, color: #c9d1d9, line-height: 1.6
- NON-italic

**3d. Exit plan:**
- Flex row, gap 20px, font-size 10px, margin-top 6px
- "Take profit:" (muted label) + price value (green, e.g., "621.00")
- "Hard stop:" (muted label) + price value (red, e.g., "634.50")

**3e. Previous re-reads (below most recent):**
- Render each previous assessment with same header format
- COLLAPSED by default — header visible, analysis hidden
- Click header to expand/collapse the analysis text
- Original assessment has "Original" label next to timestamp
  (e.g., "03-31-2026 02:19 · Original")
- Order: most recent first, original last

**3f. Ensure the expansion replaces any existing old-style expansion panel.**
Remove the old CLAUDE'S READ + EXIT PLAN layout if it exists. The new layout uses
the bordered-left analysis text pattern with exit plan below, not the old side-by-side
two-column layout visible in the current screenshots.

---

### Commit Checkpoint

Verify:
- /positions shows v3 column order (score after chevron, pills not full names)
- All full-name strategy badges replaced with abbreviated StrategyPill
- Health grades show as colored single-letter badges (A/B/C/D/F)
- Position type shows "Paper" (blue) / "Live" (green) badge
- P&L formatted with sign and color
- Groups collapse/expand with chevron
- Group by dropdown changes grouping
- Refresh all shows RefreshConfirmDialog when >1 position
- Expanded position shows versioned re-reads (most recent first)
- Claude advice badge is WHITE OUTLINED (not purple, not old style)
- Exit plan shows take profit (green) and hard stop (red)
- Previous re-reads are collapsible
- Original assessment labeled "Original"
- Timestamps as mm-dd-yyyy hh:mm

Recommended QA level: 2 (full Positions page redesign)

Commit message: OTA-374 OTA-372 OTA-373 feat: positions page v3 redesign with pills, health grades, versioned re-reads
