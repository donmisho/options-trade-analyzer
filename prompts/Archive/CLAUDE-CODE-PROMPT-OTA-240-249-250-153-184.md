# Claude Code Prompt — OTA-240 OTA-249 OTA-250 OTA-153 OTA-184
## Dev Workflow, CLAUDE.md Updates, SecurityDashboard Wiring, Strategy Profiles

### Tickets
- OTA-240: Document Jira workflow status definitions in CLAUDE.md
- OTA-249: Configure Claude-to-Jira MCP interaction (diagnostic + documentation)
- OTA-250: Verify and document Jira commit automation rule
- OTA-153: Wire SecurityDashboard to real backend data (Phase 2.9 integration gate)
- OTA-184: Strategy Profile pages

> **Note:** OTA-240/249/250 are documentation/configuration tasks with no code changes.
> OTA-153 depends on Phase 2.9 backend being live. OTA-184 is a frontend build.
> Run OTA-153 only if Phase 2.9 backend endpoints (`/api/v1/analyze/scorecard`) are responding correctly.

---

## Task 1 — OTA-240: Document Jira Workflow in CLAUDE.md

```bash
cat CLAUDE.md | grep -n "Jira\|workflow\|status" | head -20
```

Verify whether the 5-stage workflow table is already present. If it IS already in CLAUDE.md, mark this task done and skip — do not duplicate.

If NOT present, add the following section to CLAUDE.md under a `## Jira Workflow — Status Definitions` heading:

```markdown
## Jira Workflow — Status Definitions

The OTA project uses a 5-stage workflow. When reading or updating Jira status,
always map to these definitions:

| # | Jira Status | Who Acts | Meaning |
|---|-------------|----------|---------|
| 0 | Idea | Don | Raw backlog item, not yet committed to |
| 1 | To Do | Don | Promoted — confirmed candidate for next work set |
| 2 | In Review | Claude (Web) | Being grouped, sequenced, dependencies mapped, prompts being planned |
| 3 | In Progress | Claude (Code) | Prompt written and actively executing in Claude Code |
| 4 | Done | Automation | Commit pushed to main → Jira auto-closes via commit trigger |

**Workflow rules:**
- Don selects items from Idea → promotes to To Do
- Claude Web groups To Do items into logical prompt sequences → moves to In Review
- Claude Web writes the Claude Code prompt → status moves to In Progress
- Claude Code executes the prompt, pushes to GitHub with OTA ticket numbers in commit message
- Jira automation moves In Progress → Done automatically on commit
```

---

## Task 2 — OTA-249: Diagnose Atlassian MCP Tool Resolution

This is a **diagnostic and documentation task only** — no code changes to the app.

**Background:** The Atlassian MCP connector is active in Claude.ai but the tools are not surfacing via `tool_search`. This means Claude Web cannot read/update Jira directly and must use browser automation instead.

**What to document in CLAUDE.md:**

1. Confirm whether `Atlassian MCP` tools are currently available by attempting a test call pattern
2. Document the current workaround: "Atlassian MCP tools do not surface in Claude.ai tool_search as of March 2026. Workaround: export Jira CSV manually or use Claude in Chrome to navigate the Jira list view at `https://tmtctech-team.atlassian.net/jira/software/projects/OTA/list`"
3. Add a note that when this is resolved, the session start protocol in CLAUDE.md should be updated to use MCP directly

**Add this note to the `## Session Start Protocol` section in CLAUDE.md** — do not replace the existing section, just append the workaround note.

---

## Task 3 — OTA-250: Verify Jira Commit Automation

**Steps:**
1. Look up the most recent git commit on main that includes an OTA ticket number:
```bash
git log --oneline -10
```
2. Check if a ticket referenced in that commit was automatically moved to Done in Jira
3. If you cannot verify Jira status from the command line, document what you can see and note that manual verification in Jira is required

**Add a brief note to CLAUDE.md** under the `## Jira Automation` section:
- If automation is confirmed working: "Verified working as of [date of last commit with OTA number]"
- If unconfirmed: "Automation rule configured; manual verification pending. To test: push a commit to main with an OTA ticket number and check ticket status in Jira."

---

## Task 4 — OTA-153: Wire SecurityDashboard to Real Backend Data

**Prerequisite check — run this first:**
```bash
curl -k https://127.0.0.1:8000/api/v1/analyze/scorecard -X POST \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL"}'
```

If this returns a 404 or 500, **stop here** — Phase 2.9 backend is not ready and this task cannot proceed. Document the blocker in a comment and skip to Task 5.

If the endpoint responds, proceed:

```bash
cat web/src/pages/SecurityDashboard.jsx
grep -rn "mock\|mockData\|placeholder" web/src/pages/SecurityDashboard.jsx
cat web/src/client.js | grep -n "scorecard\|strategy"
```

Replace mock data with real calls to:
- `GET /api/v1/analyze/scorecard?symbol={symbol}` → populate StrategyScorecard
- Any other data needed for the QuoteBar and chart on this page

Follow the same loading/error state pattern used on the Verticals page.

**Acceptance criteria (Integration Tests 1-5 from PHASE-2.9.md):**
Run the integration tests as documented in `PARALLEL-BUILD-GUIDE.md` Session 4. Report all failures together.

---

## Task 5 — OTA-184: Strategy Profile Pages

```bash
grep -rn "strategy\|StrategyProfile\|/strategies" web/src/ | grep -v node_modules | head -20
cat web/src/App.jsx | grep -n "route\|Route\|path" | head -30
```

**What to build:** One page per strategy. Four strategies: Steady Paycheck, Weekly Grind, Trend Rider, Lottery Ticket.

**Route pattern:** `/strategies/{strategy-slug}` (e.g. `/strategies/steady-paycheck`)

**Page layout per strategy:**
1. **Header:** Strategy name, tagline, DTE range, spread type
2. **Parameters section:** Key parameters (DTE, strike selection, credit target, max risk) in a card grid
3. **Scoring Weights section:** Show what factors this strategy prioritizes — use the weights from the strategy config if available
4. **Backtest section:** Placeholder card with text `"Backtest data available in Phase 3.3"` — no live data

**Read strategy configs first:**
```bash
find web/src -name "*.config.js" | xargs grep -l "strategy\|DTE\|steady\|grind" 2>/dev/null | head -5
```

Use whatever config data is already defined — do not hardcode parameters that exist in config files.

**House style:**
- Background `#0D1117`
- Strategy name in white, tagline in muted
- No full-width buttons
- Backtest placeholder card: muted border, muted text, no action elements

---

### Commit Message
```
OTA-240 OTA-249 OTA-250 OTA-153 OTA-184 docs: CLAUDE.md workflow docs, SecurityDashboard wiring, Strategy Profile pages
```

> Note: Only include ticket numbers for tasks that were actually completed in the commit prefix.
