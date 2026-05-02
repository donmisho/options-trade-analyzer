# Mission: Add QA Gate and Run Types to CLAUDE.md Files

Three changes needed. Do not modify any existing content — only add new sections.

## Change 1: Add Post-Build QA Gate to prompts/CLAUDE.md

Read `prompts/CLAUDE.md`. Add the following new section after the existing pre-authorization rules section (before any appendix or glossary sections). Do not modify any existing content.

Add this section:

```markdown
## Post-Build QA Gate

At the end of every build run — before marking any ticket as done or creating a PR — assess the scope of changes and recommend a QA level.

### QA Levels

**Level 0 — No QA needed:**
- Cosmetic fixes: typos, copy changes, comment updates
- Documentation-only changes
- Changes to files outside `app/` and `web/src/`
- Just commit and move on.

**Level 1 — Targeted validation:**
- Changes to a single component's styling or layout
- Token value changes in `web/src/styles/tokens.js`
- Changes scoped to one ticket's UI
- Run the UX agent against only the affected ticket(s).

**Level 2 — Full regression:**
- Changes to `app/services/` (vertical_engine, filter_engine, greeks, P&L calculators)
- Changes that touch multiple components
- Changes to provider adapters or SKILL.md files
- Changes to auth, database models, or SecretsManager
- Any build run that touched 3+ tickets across parallel streams
- Run both QA agents: full UX sweep of all Done tickets plus full 64-config data matrix.

### Before committing, state your recommendation:

Build complete. Changes: [list files touched]
Recommended QA level: [0/1/2]
Reason: [one sentence — why this level]
Run QA? [waiting for your answer]

The human approves, adjusts, or skips. Never run QA without asking. Never skip the recommendation — always state the level even if you expect a Level 0.

### Regression runs

When running Level 2 QA, compare current results against the baseline files in `agents/qa-context/`. A test that failed in the previous run and still fails is a known issue. A test that passed in the previous run and now fails is a REGRESSION — mark severity BLOCKER and escalate immediately to Teams.

After a clean Level 2 run where all tests pass, snapshot the results as the new baseline:
- Copy UX results to `agents/qa-context/baseline-ux.json`
- Copy data results to `agents/qa-context/baseline-data.json`

### Keeping QA configuration in sync

If you modify the QA gate levels, thresholds, or agent behavior described in this section, also update the corresponding sections in:
- `agents/qa-ux/CLAUDE.md`
- `agents/qa-data/CLAUDE.md`
- `agents/fe-dev/CLAUDE.md`
- `agents/be-dev/CLAUDE.md`

All five files must stay in sync. When in doubt, read the agent CLAUDE.md files to verify consistency before making changes.
```

---

## Change 2: Add QA Run Types to All Four Agent CLAUDE.md Files

Add the following section to the **end** of each of these four files:
- `agents/qa-ux/CLAUDE.md`
- `agents/qa-data/CLAUDE.md`
- `agents/fe-dev/CLAUDE.md`
- `agents/be-dev/CLAUDE.md`

```markdown
## QA Run Types

This agent may be invoked in three modes. The mode is specified in the mission prompt.

### Active build validation
Run against specific tickets currently being built. Check only the listed ticket keys. Deviations are reported as normal findings.

### Post-build regression sweep
Run against ALL tickets with status "Done" (for UX agent) or the full 64-config matrix (for data agent). Compare results against baseline files in `agents/qa-context/`. Any test that previously passed but now fails is a REGRESSION — mark severity BLOCKER regardless of the nature of the failure and tag as REGRESSION in the report and Teams notification.

### Targeted investigation
Run against a specific subset (e.g., one component, one spread type, one configuration). Focus on root cause analysis rather than broad coverage.

### Baseline management
After a clean post-build regression sweep (zero failures), snapshot results as the new baseline:
- UX results → `agents/qa-context/baseline-ux.json`
- Data results → `agents/qa-context/baseline-data.json`
Only snapshot on fully clean runs. Never overwrite the baseline with results that contain failures.
```

---

## Change 3: Update agents/.gitignore

Replace the current contents of `agents/.gitignore` with:

```
qa-ux/test-results/*
!qa-ux/test-results/.gitkeep
qa-data/test-results/*
!qa-data/test-results/.gitkeep
qa-context/jira-extract.json
qa-context/agent-run-log.jsonl
# Baseline files ARE committed — they are the regression reference
# Do not add baseline-ux.json or baseline-data.json to this gitignore
```

---

## Validation

After all three changes:
1. Verify `prompts/CLAUDE.md` contains the new "Post-Build QA Gate" section
2. Verify all four agent CLAUDE.md files contain the new "QA Run Types" section
3. Verify `agents/.gitignore` has the baseline comment
4. Commit changes to the `feature/qa-agent-system` branch
