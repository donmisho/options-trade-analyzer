---
allowedTools:
  - Bash(*)
  - Read(*)
  - Write(*)
  - Edit(*)
---

# Positions Redesign — Session 1, Window 2: Frontend Shell
# Jira: OTA-268, OTA-270
# Prerequisites: None — independent from backend window

## Context

You are rebuilding the Positions page frontend to match the Verticals and
Puts & Calls page styling. This session creates the column config, filter bar,
group-by logic, and page shell with mock data. The expansion panel and real
data wiring come in Session 2.

**Read these files first:**
```
cat CLAUDE.md
cat UI-DECISIONS.md
cat web/src/config/verticals-columns.jsx
cat web/src/config/long-options-columns.jsx
cat web/src/pages/OptionsTerminal.jsx | head -100
cat project-mockups/positions-page-prototype-v6.html
```

Pay close attention to the styling in UI-DECISIONS.md. The Positions page must
look like it belongs on the same app as Verticals and Puts & Calls.

## Task 1: Positions Column Config (OTA-268)

Create `web/src/config/positions-columns.jsx` following the exact pattern
from `verticals-columns.jsx`.

**Columns (in order):**

| Key | Label | Align | Sortable | Render Notes |
|-----|-------|-------|----------|--------------|
| _chevron | (none) | left | no | ▶ collapsed, ▼ expanded |
| symbol | SYMBOL | left | yes | Bold, teal (#2dd4bf) |
| pos_type | POS TYPE | center | yes | Pill: Paper (blue) or Live (green) |
| strategy_key | STRATEGY | center | yes | Teal pill with strategy display name |
| structure | STRUCTURE | center | yes | Plain text: Vertical, Put, Call, etc. |
| trade_type | TYPE | center | yes | Colored pill: Bull Put/Bull Call (green), Bear Put/Bear Call (red) |
| analysis_date | ANALYSIS DATE | center | yes | mm-dd-yyyy format |
| strike_spread | STRIKE/SPREAD | center | yes | e.g. "590/580" or "200" |
| expiration | EXPIRATION | center | yes | mm-dd-yyyy format |
| entry_price | PREMIUM | right | yes | No $ prefix |
| current_premium | CURRENT | right | yes | No $ prefix |
| pnl | P&L | right | yes | Green positive, red negative. Show amount + (pct%) |
| dte | DTE | center | yes | Integer |
| perf_status | PERF | center | yes | 10px dot: green/amber/red with box-shadow |
| _actions | (none) | center | no | Refresh ↻ and Archive ⊘ icon buttons |

**Default sort:** PERF descending (best performing first).

**Header styling (must match Puts & Calls exactly):**
- font-size: 10px
- text-transform: uppercase
- letter-spacing: 0.4px
- color: var(--muted) (#8b949e)
- font-weight: 400 (not bold)
- Headers centered over data (except SYMBOL left-aligned)
- Active sort column: color var(--teal) with ▼ or ▲ indicator

## Task 2: Filter Bar and Collapsible Group-By (OTA-270)

### Filter Bar

Build the filter bar as a flex row inside `PositionsPage.jsx`. Match the
existing OTA filter pattern from the prototype.

**Filters (left to right, left-justified):**

1. **STATUS** — multi-select dropdown. Options: Active, Archived. Default: Active only.
2. **TYPE** — multi-select dropdown. Options: Paper, Live. Default: both selected.
3. **STRATEGY** — multi-select dropdown. Options: All four strategy display names. Default: all selected.
4. **SYMBOL** — typeahead text input. Placeholder: "e.g. META or Meta Platforms". Queries positions in state for matching symbols. In this session, filter client-side from loaded positions. Full backend typeahead endpoint can come later.
5. **GROUP BY** — single-select dropdown. Options: Strategy, Symbol, Position Type, Structure, Type, DTE, Performance. Default: Strategy.

Filter bar styling:
- Background: var(--bg2) (#161b22)
- Border: 1px solid var(--border) (#30363d)
- Border-radius: 6px
- Padding: 10px 14px
- Filter labels: 10px uppercase, letter-spacing 0.4px, muted
- Dropdowns: var(--bg) background, var(--border) border, var(--text) color

### Group-By with Collapse

Group positions by the selected Group By field. Each group renders:

- **Group header** (clickable): chevron ▼/▶ + group name (teal, uppercase, 12px bold, letter-spacing 0.4px) + count (muted)
- **Table** with column headers + position rows

Clicking the group header collapses/expands the table below it.
Groups with 0 matching positions: show collapsed by default.
State: track which groups are collapsed in component state.

### Mock Data

Create at least 8 mock positions across 3 strategy groups for development:
- 2 Lottery Ticket positions (META Bear Put, META Bear Call)
- 4 Steady Paycheck positions (F, IBM, GEV, XOM)
- 0 Weekly Grind (shown collapsed)
- 0 Trend Rider (shown collapsed)

Use the data from the prototype HTML as reference for realistic values.
Include at least one Live position (GEV) and one with negative P&L (XOM, amber perf).

## Task 3: Page Shell

The PositionsPage should follow this structure:
```jsx
<div>
  <PageHeader title="Positions" count={filteredPositions.length} />
  <FilterBar filters={...} onChange={...} />
  {groups.map(group => (
    <PositionGroup
      key={group.key}
      name={group.name}
      count={group.positions.length}
      collapsed={collapsedGroups[group.key]}
      onToggle={() => toggleGroup(group.key)}
    >
      <PositionsTable
        positions={group.positions}
        columns={positionsColumns}
        expandedRowId={expandedRowId}
        onRowClick={setExpandedRowId}
        renderExpansionRow={renderExpansionRow}
      />
    </PositionGroup>
  ))}
</div>
```

For this session, `renderExpansionRow` can return a placeholder div saying
"Assessment versions will render here". The real expansion panel comes in Session 2.

## Validation

1. Navigate to /positions — page renders with filter bar and grouped tables
2. All column headers match Puts & Calls styling exactly
3. Click a column header — rows sort correctly
4. Toggle Status filter to Archived — positions disappear (none are archived in mock data)
5. Type "META" in Symbol filter — only META positions shown
6. Change Group By to "Symbol" — positions regroup by symbol
7. Click a group header — group collapses/expands
8. Click a position row — expansion placeholder appears with teal top border

## House Rules
- Dates: mm-dd-yyyy everywhere (use formatDate from web/src/utils/formatDate.js)
- No $ prefix on any value
- Buttons never full-width
- Monospace font family throughout
- Score format: ##.00
- Display "Paper" and "Live" (not "PAPER"/"LIVE")
