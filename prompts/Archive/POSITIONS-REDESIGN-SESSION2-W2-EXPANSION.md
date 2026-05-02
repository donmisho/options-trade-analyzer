---
allowedTools:
  - Bash(*)
  - Read(*)
  - Write(*)
  - Edit(*)
---

# Positions Redesign — Session 2, Window 2: Expansion Panel + Actions
# Jira: OTA-269, OTA-271
# Prerequisites: Session 1 Window 2 complete (page shell with mock data)

## Context

You are building the position row expansion panel that shows stacked Claude
assessment versions, and wiring the Refresh/Archive icon buttons. This replaces
the placeholder expansion from Session 1.

**Read these files first:**
```
cat CLAUDE.md
cat UI-DECISIONS.md
cat project-mockups/positions-page-prototype-v6.html
cat web/src/pages/PositionsPage.jsx
cat web/src/config/positions-columns.jsx
```

Study the prototype HTML carefully. The expansion panel is simpler than
Verticals — no 4-column score breakdown. Just Claude's Read + Exit Plan.

## Task 1: Assessment Version Stack (OTA-269)

Replace the placeholder `renderExpansionRow` in PositionsPage with the real
assessment version stack.

### Version Header (collapsed state)

Each assessment version renders as a clickable row:

```
▶  [EXECUTE]  71.00  Update: 03-24-2026 09:45  Synopsis: IV expanding, thesis strengthening slightly
```

Left to right:
1. **Chevron** ▶ (collapsed) / ▼ (expanded) — 9px, muted
2. **Verdict badge** — EXECUTE (green), WAIT (amber), PASS (red). Same badge styling as Verticals verdict.
3. **Score** — 13px bold, colored to match score rules (green ≥70, amber 40-69, red <40). Format: ##.00
4. **Label** — "Original: mm-dd-yyyy hh:mm" or "Update: mm-dd-yyyy hh:mm". 10px, muted color.
5. **Synopsis** — "Synopsis: [text]". 10px, muted, italic. Left-justified after the label.

**Do NOT use badge styling for "Original" / "Update"** — plain muted text only.
Most recent version expanded by default. All others collapsed.
Background: var(--bg) (#0d1117) — no surface shading on version rows.

### Expanded Version Content

When a version is expanded, show a **flex row with 2/3 + 1/3 split**:

```css
.av-content {
  display: flex;
}
.av-col-read {
  flex: 2;
  padding-right: 16px;
}
.av-col-exit {
  flex: 1;
  padding-left: 16px;
  border-left: 1px solid var(--border);
  min-width: 220px;
}
```

**Left column (2/3) — Claude's Read:**
- Section label: "CLAUDE'S READ" — 9px uppercase muted
- Text: 10px, color #c9d1d9, line-height 1.65, LEFT-justified
- Paragraphs separated by 8px margin
- This is NOT italic (UI-DECISIONS.md specifies "normal")

**Right column (1/3) — Exit Plan:**
- Section label: "EXIT PLAN" — 9px uppercase muted
- Rows with dashed dividers between them:
  - Take Profit — label muted, price green
  - Warning Level — label muted, price amber
  - Hard Stop — label muted, price red
  - Calendar Exit (optional) — label muted, date purple
- Each row: flex space-between, label on left, price/date on right

**CRITICAL: The expansion panel must NOT repeat any info from the trade header row.**
No symbol, no strategy, no strikes, no expiration, no premium. That's all in the
header already.

### Mock Assessment Data

Until wired to real backend, create mock assessments for the META position:

```javascript
const mockAssessments = [
  {
    assessment_id: 'a4',
    version_number: 4,
    assessment_type: 'UPDATE',
    verdict: 'EXECUTE',
    score: 71,
    synopsis: 'IV expanding, thesis strengthening slightly',
    claude_read: 'META has pulled back toward the 590 short strike...',
    exit_levels: { take_profit: 580, warning: 586, hard_stop: 595, calendar_exit: '2026-04-03' },
    created_at: '2026-03-24T09:45:00'
  },
  {
    assessment_id: 'a3',
    version_number: 3,
    assessment_type: 'UPDATE',
    verdict: 'EXECUTE',
    score: 72,
    synopsis: 'SMA 8 test approaching, volume contracting',
    claude_read: 'META consolidated between 588-594...',
    exit_levels: { take_profit: 580, warning: 586, hard_stop: 593 },
    created_at: '2026-03-22T15:30:00'
  },
  {
    assessment_id: 'a2',
    version_number: 2,
    assessment_type: 'UPDATE',
    verdict: 'WAIT',
    score: 65,
    synopsis: 'Bullish rally pressuring thesis, hold for now',
    claude_read: 'META rallied 1.8% on Friday...',
    exit_levels: { take_profit: 580, warning: 588, hard_stop: 598 },
    created_at: '2026-03-21T10:15:00'
  },
  {
    assessment_id: 'a1',
    version_number: 1,
    assessment_type: 'ORIGINAL',
    verdict: 'EXECUTE',
    score: 73,
    synopsis: 'Strong IV, contrarian bear play on META',
    claude_read: 'META is currently trading above all key SMAs...',
    exit_levels: { take_profit: 580, warning: 586, hard_stop: 591 },
    created_at: '2026-03-20T14:12:00'
  }
];
```

## Task 2: Refresh and Archive Icon Buttons (OTA-271)

### Icon Buttons in Trade Header Row

Two small icon buttons in the ACTIONS column (last column) of each position row:

```jsx
<span className="row-actions">
  <button className="icon-btn" onClick={handleRefresh} title="Refresh analysis">↻</button>
  <button className="icon-btn archive" onClick={handleArchive} title="Archive position">⊘</button>
</span>
```

Styling (must follow Button Standards from UI-DECISIONS.md):
```css
.icon-btn {
  width: 20px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 3px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 11px;
  font-family: inherit;
  /* NEVER full-width */
  width: auto;
  min-width: 20px;
  max-width: 20px;
}
.icon-btn:hover {
  border-color: var(--teal);
  color: var(--teal);
}
.icon-btn.archive:hover {
  border-color: rgba(248,113,113,0.4);
  color: var(--red);
}
```

### Refresh Click Handler (mock for now)
```javascript
const handleRefresh = async (positionId) => {
  // In Session 3 wiring: POST /api/v1/positions/{id}/refresh
  // For now: show a loading spinner on the icon, then add a mock assessment
  setRefreshing(positionId);
  // Simulate API delay
  await new Promise(r => setTimeout(r, 1500));
  // Add new mock assessment to the stack
  // Expand the position row and the new assessment version
  setRefreshing(null);
};
```

### Archive Click Handler (mock for now)
```javascript
const handleArchive = async (positionId) => {
  // Show confirmation: "Archive this position?"
  if (!window.confirm('Archive this position?')) return;
  // In Session 3 wiring: PATCH /api/v1/positions/{id}/archive
  // For now: remove from the active positions list
};
```

### Auto-Archive on Expiration
On page load (useEffect), check all positions. Any with expiration date in
the past should show a toast: "N positions archived (expired)" and be removed
from the active view. Wire to backend in Session 3.

## Validation

1. Click a position row — expansion panel opens with assessment versions stacked
2. Most recent version is expanded, others collapsed
3. Click collapsed version — it expands, shows Claude's Read (2/3) + Exit Plan (1/3)
4. Claude's Read is LEFT-justified, not centered
5. Exit Plan shows colored prices with dashed dividers
6. Version header shows: verdict badge → score → "Update: date" → "Synopsis: text"
7. No background shading on version rows — pure var(--bg) black
8. Refresh icon ↻ highlights teal on hover
9. Archive icon ⊘ highlights red on hover
10. Click refresh — loading state shown, mock assessment added to stack
11. Click archive — confirmation dialog, position removed from view

## House Rules
- No $ prefix on any value
- Dates: mm-dd-yyyy hh:mm (use formatDate)
- Score format: ##.00
- Claude read text: 10px normal (NOT italic), color #c9d1d9, line-height 1.65
- Buttons NEVER full-width
- Display "Paper" and "Live" (not "PAPER"/"LIVE")
