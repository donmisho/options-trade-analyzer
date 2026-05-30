---
allowedTools:
  - mcp__atlassian
  - Bash
  - Read
---

# OTA-535 — Create two cleanup Stories from the OTA-653 ADR

## Terminal context
- Single-terminal Jira admin work (~5 minutes)
- No code changes, no commit, no branch

## Required reading

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
cat claude_context/CLAUDE.md
cat claude_context/jira-structure.md
cat claude_context/architecture-plan.md   # for OTA-535 context and the new ADR-1
```

## Relevant Context — Do Not Deviate Without Escalation

**Source:** `CLAUDE.md` (Workflow Phases) and `jira-structure.md`
- Project key: `OTA`. CloudID: `53c395d7-bac7-4a5f-baf2-ee2b0f375a2b`.
- New Stories are created at **Write Story** status (status ID 10002) — Claude Web's refinement phase.
- The transition named "To Do" (transition ID 21) confusingly moves issues to **Schedule**, not "To Do." There is no "To Do" status. Do not assume transition IDs — use `getTransitionsForJiraIssue` against an existing issue to discover the right transition ID to reach Write Story.
- Stories parent directly to Epics. Pass `parent` as a top-level named parameter, never nested inside `additional_fields`.
- Use `contentFormat: markdown` for descriptions.

**Source:** `architecture-plan.md` (Instigating Ticket; ADR-1)
- OTA-535 is the **Architecture Optimization Framework v1 Epic**. Both new Stories parent to it.
- ADR-1 (just merged in the OTA-653 prompt) identifies these two Stories as the consumer-wiring follow-up housekeeping.

**Source:** `architecture-plan.md` Cleanup Roadmap appendix
- The roadmap entry "Consolidate `STRATEGIES` and `STRATEGY_DEFINITIONS` dicts in `strategy_definitions.py`" (OTA-513) is adjacent to Story 1 below but addresses a separate backend-internal duplication. Reference but do not collapse.

## Scope

Create two Stories under OTA-535 using the Atlassian MCP. Both Stories land at **Write Story** status. Report the assigned Story keys to the user when done.

### Step 1 — Discover the transition ID to Write Story

Call `getTransitionsForJiraIssue` against any in-flight OTA issue (e.g., OTA-654, which is currently at Write Story) to confirm:
- The transition ID required to move a newly-created issue into Write Story.
- Or confirm whether newly-created Stories default to Write Story without an explicit transition.

If `createJiraIssue` accepts a `transition` parameter and that transition exists, use it. Otherwise, create the issue and follow up with `transitionJiraIssue` to reach Write Story.

### Step 2 — Create Story 1: Frontend Strategy Config Deduplication

- **Type:** Story
- **Parent:** OTA-535
- **Summary:** `Backend-served strategy config — remove frontend mirror`
- **Description (markdown):**

```markdown
Source: ADR-1 in `architecture-plan.md` (OTA-653 outcome).

The frontend maintains a hand-edited mirror of the backend `STRATEGIES` dict at `web/src/strategy-configs/` (6 per-strategy config files + `index.js`). This duplicated source is the single remaining structural cause of strategy metadata drift between frontend and backend, and the OTA-653 discovery identified it as the highest-priority remaining wiring fix.

This Story replaces the frontend mirror with a backend-served config endpoint. The frontend fetches strategy metadata at app init from `GET /api/v1/config/strategies` and stores it in `AppContext`. The static `web/src/strategy-configs/` directory is deleted.

## Acceptance criteria

- New endpoint `GET /api/v1/config/strategies` returns the `STRATEGIES` dict in a frontend-consumable shape (per-strategy: key, label, compatible_structures, DTE window, color_text, plus any other metadata currently maintained in the frontend mirror).
- Endpoint follows the existing API authentication convention (BFF session cookie + CSRF if other config endpoints require it; otherwise unauthenticated).
- Frontend bootstraps the strategy config at app init via `AppContext`.
- All frontend call sites that previously imported from `web/src/strategy-configs/` (TradesPage, StrategyPage, SecurityStrategiesPage, ConfigDrawer, and any others — grep first) read from `AppContext`.
- `web/src/strategy-configs/` directory is deleted.
- QA harness Phase 2 smoke is green against the same 5-symbol universe.
- Visual regression: no UI changes — frontend renders identically to pre-change.

## Out of scope

- The OTA-513 consolidation of `STRATEGIES` and `STRATEGY_DEFINITIONS` dicts. That Story addresses a backend-internal duplication and is separate.
```

### Step 3 — Create Story 2: Score Color Threshold Unification

- **Type:** Story
- **Parent:** OTA-535
- **Summary:** `Unify frontend score color thresholds with backend verdict bands`
- **Description (markdown):**

```markdown
Source: ADR-1 in `architecture-plan.md` (OTA-653 outcome).

Score color thresholds drift across frontend components. `ScoreBar.jsx` uses green ≥75; `StrategyScorecard.jsx`, `ScanCard.jsx`, and `ScoreCell.jsx` use green ≥70. The backend `_assign_verdict()` banding at `app/api/evaluation_routes.py:174–181` uses ≥70 for EXECUTE, 50–69 for WAIT, <50 for PASS.

This Story unifies the frontend thresholds against the backend verdict bands. All score color components reference a single shared source for the 70 and 50 thresholds.

## Acceptance criteria

- Single source for the 70 / 50 score color thresholds. **Preferred:** thresholds are added to the response from `GET /api/v1/config/strategies` (the endpoint introduced by the Frontend Strategy Config Deduplication Story) so they originate in the backend. **Fallback if that Story has not shipped:** a shared frontend constant in a clearly-named module (e.g., `web/src/constants/scoreThresholds.js`).
- `ScoreBar.jsx`, `StrategyScorecard.jsx`, `ScanCard.jsx`, `ScoreCell.jsx` all reference the shared source.
- Green threshold is 70 (matches backend ≥70 EXECUTE band), not 75.
- Visual regression: green/amber/red boundaries match across all score-displaying surfaces.

## Dependencies

- Best landed after the Frontend Strategy Config Deduplication Story so the thresholds can be served by the same endpoint. If sequenced earlier, use the fallback shared frontend constant.
```

### Step 4 — Verify and report

For each Story key returned by Jira:

1. Call `getJiraIssue` to confirm parent (`OTA-535`), summary, description, and status (Write Story).
2. Report both Story keys back to the user in the session output, along with a brief confirmation of parent and status.

## Acceptance criteria

- Two Stories exist in OTA at Write Story status.
- Both Stories have `parent: OTA-535`.
- Both Stories have markdown-formatted descriptions matching the content above.
- Both Story keys are reported in the session output.

## Out of scope

- Writing the Claude Code execution prompts for either Story (Claude Web does this in a later session).
- Linking the new Stories to OTAR Categories (Claude Web does this).
- Setting priorities, story points, or assignees.
- Implementing either Story.

## Verification steps

1. `getJiraIssue` on each new key — confirm parent is `OTA-535`, status is `Write Story`, summary matches.
2. Confirm the description rendered as markdown (description text contains the expected ## headers).

## Commit instruction

I have been instructed NOT to commit. No code changes. This is a Jira admin prompt.

## Coordination footer

Independent — no downstream dependency. Once Story keys are returned, Claude Web will draft Claude Code execution prompts for each in a future session.
