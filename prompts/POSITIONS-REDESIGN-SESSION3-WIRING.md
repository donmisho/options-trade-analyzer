---
allowedTools:
  - Bash(*)
  - Read(*)
  - Write(*)
  - Edit(*)
---

# Positions Redesign — Session 3: Wiring + Integration Tests
# Jira: OTA-268, OTA-269, OTA-270, OTA-271 (wiring all frontend to backend)
# Prerequisites: Sessions 1 and 2 both complete

## Context

Sessions 1-2 built the backend (table, endpoints, SKILL.md) and frontend
(page shell, expansion panel) independently with mock data. This session
wires them together and runs integration tests.

**Read these files first:**
```
cat CLAUDE.md
cat web/src/api/client.js
cat web/src/pages/PositionsPage.jsx
cat app/api/position_routes.py
```

## Task 1: API Client Functions

Add to `web/src/api/client.js`:

```javascript
// Position assessments
export async function getPositionAssessments(positionId) {
  const res = await fetch(`/api/v1/positions/${positionId}/assessments`);
  return res.json();
}

// Position refresh — triggers new Claude evaluation
export async function refreshPosition(positionId) {
  const res = await fetch(`/api/v1/positions/${positionId}/refresh`, { method: 'POST' });
  return res.json();
}

// Archive position
export async function archivePosition(positionId) {
  const res = await fetch(`/api/v1/positions/${positionId}/archive`, { method: 'PATCH' });
  return res.json();
}

// Batch current pricing
export async function getPositionCurrentPrices(positionIds) {
  const ids = positionIds.join(',');
  const res = await fetch(`/api/v1/positions/current-prices?position_ids=${ids}`);
  return res.json();
}
```

## Task 2: Wire PositionsPage to Real Data

Replace all mock data in `PositionsPage.jsx` with real API calls:

1. **Page load:** Call `GET /api/v1/positions` → populate positions state
2. **After positions load:** Call `GET /api/v1/positions/current-prices` with all position IDs → merge current premium, P&L, perf_status into position objects
3. **On row expand:** Call `GET /api/v1/positions/{id}/assessments` → populate assessment stack for that position. Cache in state so re-expanding doesn't re-fetch.
4. **On refresh click:** Call `POST /api/v1/positions/{id}/refresh` → add returned assessment to the stack, expand the new version, update the position's current premium/P&L in the table row
5. **On archive click:** Confirm → call `PATCH /api/v1/positions/{id}/archive` → remove from active view, show toast "Position archived"
6. **Auto-archive:** On load, check positions where expiration < today → batch call archive → show toast "N positions archived (expired)"
7. **Symbol typeahead:** For now, filter client-side from loaded positions. Extract unique symbols + strategy names for filter dropdowns from loaded data.

## Task 3: Integration Tests

Run these manually after wiring:

### Test 1: Page Load
1. Navigate to /positions
2. Verify positions load from backend (not mock data)
3. Verify current prices populate after initial load
4. Verify P&L column shows real calculated values
5. Verify Performance dots are colored correctly based on P&L and exit levels

### Test 2: Assessment Expansion
1. Click a position row
2. Verify assessments load from GET /assessments endpoint
3. Verify most recent version is expanded by default
4. Verify Claude's Read shows on left (2/3), Exit Plan on right (1/3)
5. Click a collapsed version — verify it expands with full content
6. Verify all dates are mm-dd-yyyy hh:mm format
7. Verify no $ prefix on any value

### Test 3: Refresh Flow
1. Click ↻ on a position
2. Verify loading state appears on the icon
3. Verify new assessment appears at top of stack when Claude responds
4. Verify the new assessment is expanded by default
5. Verify synopsis appears in the version header
6. Verify exit levels may differ from original
7. Verify current premium and P&L update in the table row
8. Verify agent_run_log has a new row

### Test 4: Archive Flow
1. Click ⊘ on a position
2. Verify confirmation dialog appears
3. Confirm → verify position disappears from Active view
4. Change Status filter to include Archived → verify position reappears
5. Verify archived position shows ⊘ icon disabled (can't double-archive)

### Test 5: Filters and Group By
1. Toggle Type filter to Paper only → verify Live positions hidden
2. Type a symbol in Symbol filter → verify only matching positions shown
3. Change Group By to "Symbol" → verify positions regroup
4. Collapse a group → verify it collapses
5. Change Group By back to "Strategy" → verify groups reform correctly
6. Toggle Status to include Archived → verify archived positions appear

### Test 6: Styling Compliance
1. Compare column headers with Puts & Calls page side-by-side
2. Verify header font matches: 10px uppercase muted, 0.4px letter-spacing
3. Verify expansion panel has teal top border (2px solid rgba(45,212,191,0.35))
4. Verify no surface shading (#161b22) on assessment version rows — all var(--bg)
5. Verify pills match: Paper=blue, Live=green, Strategy=teal, Bear=red, Bull=green
6. Verify buttons are never full-width

## Commit

After all tests pass:
```
git add .
git commit -m "OTA-263 OTA-264 OTA-265 OTA-266 OTA-268 OTA-269 OTA-270 OTA-271 feat: positions page redesign with versioned assessments"
git push origin main
```

This commit message will auto-close all 8 subtasks via Jira automation.
