---
allowedTools: [Bash, Read, Write, Edit]
---

# OTA-173 + OTA-171 — Positions: Portfolio Context Note + Health Grade Computation

**Jira:** OTA-173, OTA-171 | Parent: OTA-29 (Positions-Specific Requirements)
**Priority:** Low/Medium | **Labels:** options-domain, requirement
**Can run in parallel with OTA-264/266 and OTA-296.**

---

## Before You Start

```bash
cat app/api/evaluation_routes.py
cat app/models/database.py
grep -n "position\|health\|grade\|assessment" app/models/database.py
grep -n "positions\|health_grade\|portfolio" app/api/ -r
cat web/src/pages/Positions.jsx 2>/dev/null || echo "file not found"
```

Read all output before making any changes.

---

## Context

Two Positions-related requirements are batched here. Both are lower-priority enhancements
to the positions system.

---

## Feature A — OTA-173: Portfolio Position Context Note

### Description

When analyzing a symbol that the user already holds as an open position, display a
contextual note surfacing that fact. Issue #8 from validation assessment.

### When It Applies

On the **Security Strategies** and **Verticals** / **Puts & Calls** analysis pages:
after a symbol is loaded, cross-reference the symbol against the user's open positions.

### UI Behavior

If the user has one or more open positions in the active symbol:
- Display a context banner (non-blocking, dismissable) below the QuoteBar
- Banner text: `"You have [N] open position[s] in [SYMBOL]. [View →]"`
- `[View →]` navigates to `/positions` (can filter by symbol if routing supports it)
- Banner background: `var(--amber)` at 10% opacity with amber border-left (3px)
- Dismiss button (`×`) hides banner for the session (not persisted)

If no open positions for the symbol: render nothing (no banner, no empty state).

### Data Source

`GET /api/v1/positions?status=open&symbol={activeSymbol}`

Fire this call whenever `activeSymbol` changes on analysis pages. Use existing API client.

### Backend

If the positions endpoint doesn't already support `symbol` query param filtering, add it:

```python
# In GET /api/v1/positions route
@router.get("/api/v1/positions")
async def get_positions(
    status: str = None,
    symbol: str = None,
    ...
):
    query = select(Position)
    if status:
        query = query.where(Position.status == status)
    if symbol:
        query = query.where(Position.symbol == symbol.upper())
    ...
```

---

## Feature B — OTA-171: Health Grade Computation (A–F), Updated Daily

### Description

The Position Monitor Agent computes health grades A–F for each open position based on
current market data vs. the exit levels recorded at position entry. Grades updated daily
after market close.

### Grade Definition

| Grade | Meaning | Color |
|-------|---------|-------|
| A | On track — all exit conditions healthy | `var(--green)` |
| B | Slightly off track — within tolerance | `var(--teal)` |
| C | Warning — approaching one exit level | `var(--amber)` |
| D | Danger — breached one exit level | `var(--orange)` |
| F | Thesis invalid — multiple exit levels breached | `var(--red)` |

### Computation Logic

Add `compute_health_grade(position, current_quote) -> str` to
`app/analysis/` (create `position_health.py`):

```python
def compute_health_grade(position, current_price: float, current_dte: int) -> str:
    """
    Compute A-F health grade from position exit levels vs current market state.
    
    Exit levels stored on position at entry:
    - exit_warning_level: price threshold for warning
    - exit_scale_out_level: price threshold for scale-out
    - time_stop_days: DTE floor
    - underlying_stop_buffer: stop below entry price
    
    Returns: "A" | "B" | "C" | "D" | "F"
    """
    breach_count = 0
    
    # Check time stop
    if current_dte <= position.time_stop_days:
        breach_count += 1
    
    # Check underlying stop
    if position.underlying_stop_buffer:
        stop_price = position.entry_underlying_price - position.underlying_stop_buffer
        if current_price <= stop_price:
            breach_count += 2  # hard stop = double breach weight
    
    # Check exit warning level
    # For credit spreads: warning when P&L loss exceeds exit_warning_level % of credit
    # Implementation depends on what's stored in position exit_levels JSON
    # Parse position.exit_levels JSON and evaluate each threshold
    
    if breach_count == 0:
        return "A"
    elif breach_count == 1:
        return "B" if False else "C"  # single soft warning → C
    elif breach_count == 2:
        return "D"
    else:
        return "F"
```

**Note:** The exact thresholds depend on what `exit_levels` JSON structure is stored on
the position. Read the existing `positions` table schema and `position_assessments` data
to understand what's available. Fill in the actual logic based on real field names.

### Daily Update Mechanism

Add `POST /api/v1/positions/update-health-grades` endpoint:

```python
@router.post("/api/v1/positions/update-health-grades")
async def update_health_grades(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_write)
):
    """
    Recompute health grades for all open positions.
    Called by scheduler daily after market close. Also callable on-demand.
    """
    from app.analysis.position_health import compute_health_grade
    ...
```

- Fetches current quotes for all open position symbols in a batch
- Calls `compute_health_grade()` for each
- Updates `health_grade` column on each position row
- Returns `{ updated: N, errors: [] }`

### Schema Update

If `positions` table doesn't have `health_grade` column:

```sql
ALTER TABLE positions ADD health_grade NVARCHAR(1) NULL;
```

Add to SQLAlchemy model in `database.py`:
```python
health_grade = Column(String(1), nullable=True)  # "A"|"B"|"C"|"D"|"F"
```

---

## Acceptance Criteria

### OTA-173
- [ ] Context banner appears when active symbol has open positions
- [ ] Banner shows correct count and symbol
- [ ] `View →` navigates to Positions page
- [ ] Banner is dismissable (session-only)
- [ ] No banner shown when no positions exist for symbol
- [ ] GET /api/v1/positions supports `symbol` query param filter

### OTA-171
- [ ] `compute_health_grade()` function exists in `app/analysis/position_health.py`
- [ ] Returns correct letter grade A–F
- [ ] `POST /api/v1/positions/update-health-grades` endpoint exists
- [ ] `health_grade` column exists on `positions` table
- [ ] Grades displayed with correct colors: A=green, B=teal, C=amber, D=orange, F=red
- [ ] Grades display as single letter, never numeric

---

## House Style Rules

- Health grades: always single letter (A/B/C/D/F) with color tokens — never numeric
- No `$` prefix on any monetary value
- Position source labels: "Paper" / "Live"
- Dark theme tokens throughout
- Provider routing: `_get_provider()`

---

## Commit Message

```
OTA-173 OTA-171 Add portfolio context banner and health grade computation for positions
```
