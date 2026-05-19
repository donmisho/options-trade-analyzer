# Phase 3b.3 — Insights Write Wiring Cutover Log

**Date:** 2026-05-19
**Ticket:** OTA-669
**Commit:** `OTA-669 feat: phase 3b.3 - insights write wiring`

---

## Actions Applied

### Action 1 — Add `user_id` and `source_position_id` to `InsightEngine.generate()`

**File:** `app/agents/insight_engine.py`

- Added `user_id: str` as a required keyword parameter (line 75)
- Added `source_position_id: Optional[str] = None` as an optional keyword parameter (line 77)
- **Create path (lines 180–181):** New `Insight()` constructor now passes `user_id=user_id` and `source_position_id=source_position_id`
- **Update path (lines 154–156):** Existing insight updated with `existing.user_id = user_id`; `source_position_id` overwritten only if non-None (preserves existing FK if caller passes `None`)

### Action 2 — Forward values from `PositionMonitorAgent._trigger_insights()`

**File:** `app/agents/position_monitor.py`

- Call at line 378–380: added `user_id=pos.user_id` and `source_position_id=pos.position_id`
- `entity_id=update.position_id` unchanged (separate semantic purpose per audit §4.3)

### Action 3 — Wire `user_id` into `AgentRunLog` write

**File:** `app/agents/insight_engine.py`

- Line 196: changed `user_id=None` → `user_id=user_id`
- Fixes audit §2.6 STALE finding

---

## Test Results

### Import check
```
python -c "from app.agents import insight_engine, position_monitor; print('imports OK')"  → PASS
```

### pytest
```
pytest --ignore=scratch --ignore=dev-agents -q
503 passed, 2 skipped, 0 failures in 60.59s
```

Same scope as 3b.1 and 3b.2. No existing tests needed signature updates — no test directly calls `InsightEngine.generate()`.

### Smoke-test queries (Section 5)

Not re-run for 3b.3. No schema, FK, or ORM model changes were made — only application-code wiring within two agent files. 3b.1's smoke test results remain valid.

---

## Deviations from Audit

- None. All three actions applied exactly as specified in §7.3b.3.

## Findings Not in Audit

- None.

---

## File Inventory

| Status | File |
|--------|------|
| MODIFIED | `app/agents/insight_engine.py` |
| MODIFIED | `app/agents/position_monitor.py` |

**No files in `app/models/`, `app/api/`, `app/services/`, or `web/src/` were modified.**

---

## Banner: SUCCESS
