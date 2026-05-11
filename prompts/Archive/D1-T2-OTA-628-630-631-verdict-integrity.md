# OTA-628 + OTA-630 + OTA-631 — Verdict integrity bug cluster

## Deployment context
- Deployment: **D1**
- This terminal: **T2**
- Concurrent terminals: T1 (agent prompt template; disjoint files), T3 (governance docs; disjoint files)
- Cross-terminal dependencies: **none** — T2 owns `app/api/position_routes.py` and the positions UI; T1 and T3 do not touch these

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/UI-GUIDANCE.md
```

Plus:

```
cat app/api/position_routes.py        # primary surface for all three Stories
cat app/api/evaluation_routes.py      # the auto-pass branch source (OTA-628)
cat app/models/migrations.py          # m001-m004 pattern for new _m005 (OTA-628)
cat web/src/pages/TradesPage.jsx      # Follow-button disable conditions (OTA-628)
cat web/src/pages/StrategyPage.jsx    # expanded row at lines 729-748 (OTA-631)
cat web/src/pages/PositionsPage.jsx   # parallel render gap (OTA-631)
cat web/src/widgets/PositionsScorecardWidget.jsx   # parallel render gap (OTA-631)
```

## Relevant Context — Do Not Deviate Without Escalation

**Source: business-rules.md § Position lifecycle**
A FOLLOWING position must have non-null `claude_exit_levels`. The DB schema currently does not enforce this; OTA-628 adds the CHECK constraint. Pre-flight any migration that adds a constraint by cleaning offending existing rows in the same idempotent `_m005` block.

**Source: business-rules.md § Verdict shape**
Valid verdicts are exactly `{EXECUTE, WAIT, PASS}`. Any other verdict reaching the Follow handler is a hard error, not a value to coerce. Silently coercing `WAIT_FOR_EARNINGS → WAIT` is the bug OTA-628 fixes.

**Source: business-rules.md § Assessment is source of truth**
`position_assessments` is the source of truth for verdict / score / exit_levels. The four `claude_*` columns on `positions` are denormalized cache; OTA-630 keeps them in sync on every refresh. OTA-624 (future) drops the cache columns and joins the latest assessment; do not pre-empt that here.

**Source: architecture-plan.md § Data Isolation Invariant**
Every CRUD endpoint that takes a resource ID filters by `user_id`. The migration in OTA-628 does not violate this (table-level constraint), but verify the Follow / refresh handlers in this prompt's diff still filter by `user_id` after your changes — do not regress.

**Source: CLAUDE.md § House style**
- Buttons sized to content, never full-width; visible border or background in default state
- No `$` prefix on monetary values
- Scores formatted `##.00`
- Dates `mm-dd-yyyy`
- Trade type badges: title-case display names, no underscores; bull = green, bear = red
- `var(--bg2)` restricted to filter bars, QuoteBar, and pill badge backgrounds — do not use for the new expanded-row sections

**Source: CLAUDE.md § Project-critical shared files**
`app/api/position_routes.py` is **not** on the shared-file list, but this cluster makes overlapping edits within it. Because all three Stories ship in the same terminal sequentially, no concurrency risk.

---

## Execution order within this terminal

Sequential. One commit at the end covering all three tickets.

1. **OTA-628** first — DB and route gate (this is the High-priority root cause)
2. **OTA-630** second — refresh handler mirror update (depends on stabilized Follow path)
3. **OTA-631** third — frontend render expansion (depends on backend state being correct first)

Do not commit between Stories. If a Story fails verification, stop and report.

---

## OTA-628 — Follow accepts gate-disqualified cards

### Scope

1. **Idempotent migration `_m005_following_requires_exit_levels`** in `app/models/migrations.py`, implementing both MSSQL and SQLite branches following the existing `_is_mssql` pattern from `_m001`–`_m004`:
   ```sql
   ALTER TABLE positions ADD CONSTRAINT ck_positions_following_has_exit_levels
     CHECK ( NOT (status = 'FOLLOWING' AND claude_exit_levels IS NULL) )
   ```
   Pre-flight cleans any existing offending rows (set `claude_exit_levels = '{}'` if any FOLLOWING row has NULL) before creating the constraint. The migration is idempotent — re-running is a no-op.

2. **`POST /positions/follow` (`app/api/position_routes.py:370` area) returns 422** with structured error if the payload satisfies any of:
   - `claude_exit_levels` is null/empty
   - `claude_verdict.verdict` not in `{EXECUTE, WAIT, PASS}`
   - `entry_price` is null or `<= 0`
   - `claude_verdict` contains a non-empty `auto_pass_reason`

   Error response shape:
   ```json
   {
     "detail": "Follow rejected: <reason>",
     "code": "FOLLOW_GATE_FAIL",
     "failed_checks": ["<list of failed conditions>"]
   }
   ```

3. **Remove the silent verdict fallback** at `app/api/position_routes.py:282-284` (`_create_original_assessment` helper). Unknown verdict → `raise HTTPException(422)`. No defaulting to `"WAIT"`.

4. **Frontend Follow button (`web/src/pages/TradesPage.jsx`)** disables when any client-detectable condition is true:
   - `auto_pass_reason` present on the card
   - verdict in `{WAIT_FOR_EARNINGS, PASS}`
   - `entry_price == 0`
   Tooltip on hover explains which condition disabled the button.

### Acceptance criteria

- Async pytest regression reproducing CSCO 90/100:
  - `POST /follow` with a `WAIT_FOR_EARNINGS`-shaped payload → 422
  - `POST /follow` with `claude_exit_levels=null` → 422
  - `POST /follow` with `entry_price=0` → 422
  - Assert zero `positions` and zero `position_assessments` rows written in each rejection case.
- Migration `_m005` runs cleanly against an empty DB and against a DB with one pre-existing offending FOLLOWING row.
- Frontend: a card displaying a `WAIT_FOR_EARNINGS` verdict shows the Follow button disabled with a tooltip.

### Out of scope

- Removing the four `claude_*` columns from `positions` (OTA-624 territory).
- Backfilling old offending rows beyond what's required for the migration to install cleanly.
- Schema migration to a new verdict enum.

---

## OTA-630 — Refresh handler mirrors verdict to parent positions row

### Scope

When the refresh handler at `app/api/position_routes.py:1038-1059` commits a new `position_assessments` row, also UPDATE the parent `positions` row with the same values from the new assessment:
- `claude_verdict` (as JSON) ← assessment's verdict
- `claude_score` (numeric) ← assessment's score
- `claude_exit_levels` (as JSON) ← assessment's exit_levels

**Use the assessment's values verbatim — do not recompute.**

The update is atomic with the assessment insert (same transaction, single commit).

Existing updates to `current_price`, `current_pnl`, `last_monitored_at`, `updated_at` are preserved exactly as today.

### Acceptance criteria

- Async pytest regression:
  - Follow a position with verdict EXECUTE/score 72.
  - Run refresh that produces a different verdict (WAIT/score 58).
  - `GET /positions` response shows the refreshed verdict 58/WAIT, not the original 72/EXECUTE.
  - The parent `positions` row's `claude_*` fields reflect the latest assessment.
- A second refresh that produces yet another verdict updates the parent row again — no stale values.

### Out of scope

- Dropping the `claude_*` columns from positions (note as follow-up: pair with OTA-624 to eliminate the duplication entirely).
- Refactoring `_to_response` to join `position_assessments` directly.

---

## OTA-631 — Expanded position row renders full state

### Scope

Rewrite the expanded `<tr>` at `web/src/pages/StrategyPage.jsx:729-748` to render the full position state from fields already on `pos`. No new API calls.

Render these groups, each line omitted if the source field is null/missing — no "Not available" placeholders, no zero-renders:

1. **Verdict block** — `claude_verdict.verdict` as a color-coded pill, `claude_score` formatted `##.00`, synopsis/`claude_read` text (truncate ~200 chars with "show more" toggle).
2. **Trade structure block** — legs from `trade_structure` (long/short, type, strike, expiry, qty), DTE at entry vs DTE remaining.
3. **Entry context** — `entry_underlying_price`, `entry_iv_rank` (formatted `##.00%`), `entry_sma_alignment` label.
4. **Current state** — `current_price`, `current_pnl` (formatted with sign and color: green positive, red negative), `last_monitored_at` in SharePoint-style relative format ("12 minutes ago" / "3 hours ago" / "May 3").
5. **Exit levels (collapsible)** — `take_profit`, `warning_level`, `hard_stop`, `calendar_exit` if present; each labeled, formatted as price + delta from current.
6. **Probability matrix (collapsible)** — per-scenario bars if a shared component exists; simple text fallback ("70% scenario A: +$X / 30% scenario B: -$Y") otherwise.

**Audit the same render gap in:**
- `web/src/pages/PositionsPage.jsx`
- `web/src/widgets/PositionsScorecardWidget.jsx`

Apply the same expansion if the gap is present. Note in commit message which surfaces were verified.

**Optional but recommended:** extract `<PositionDetailPanel>` shared component if the implementation across the three surfaces is duplicative. Implementer's call — only if the diff is materially cleaner.

### Acceptance criteria

- Open a known FOLLOWING position on a Strategy screen → expand → all six groups render with values from the response payload.
- Toggle a position with `take_profit = null` → exit-levels collapsible omits that line (no "Not available", no zero).
- After OTA-630 ships (it commits in the same diff), refreshing a position updates the expanded panel's verdict block on next render (no separate fetch needed beyond what `GET /positions` already returns).
- `var(--bg2)` not used in the new panel sections — verify with grep.
- No `$` prefix on monetary fields; scores formatted `##.00`; dates `mm-dd-yyyy`.
- PositionsPage and PositionsScorecardWidget audited; commit message names which were updated.

### Out of scope

- Backend changes (the `_to_response` already carries all fields needed).
- New endpoints (no `GET /positions/{id}/assessments` rendering — that's a separate follow-up Story).
- Schema changes.

---

## Combined verification steps (run before commit)

1. **Migration `_m005` runs cleanly** in dev DB; constraint visible via `sp_help` (MSSQL) or `PRAGMA table_info` (SQLite).
2. **Async pytest suite** for `app/api/position_routes.py` passes — including new regression cases from OTA-628 and OTA-630.
3. **Manual smoke (dev frontend):**
   - Click Follow on a `WAIT_FOR_EARNINGS` card → button disabled + tooltip.
   - Click Follow on a valid EXECUTE card → 200, position appears.
   - Refresh a position → verdict on Position list updates (was stuck before).
   - Expand a position row on Strategy screen → full verdict / exit levels / probability matrix visible.
4. **No regression** in existing `_to_response` tests; existing `GET /positions` consumers unaffected.
5. **No `var(--bg2)` use** outside the documented allowlist (filter bars, QuoteBar, pill badges).

If any verification fails, stop and report.

---

## Commit instruction

**I have been instructed to commit. Do you approve? (yes / no)**

One commit covers all three Stories.

## Push instruction

**DO NOT push. Single push for Deployment 1 will be coordinated by Don after all D1 terminals (T1, T2, T3) report commit.**

## Coordination footer

**Independent — no downstream dependency.** This terminal can close after committing.

## Commit message template

```
OTA-628 OTA-630 OTA-631 fix: verdict integrity — follow gate hardened, refresh mirrors verdict to positions row, expanded row renders full state
```
