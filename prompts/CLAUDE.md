# Options Analyzer — prompts/CLAUDE.md

Guidance for Claude Code when working in the `prompts/` directory.

## Pre-Authorization Rules

Files in this directory are mission prompts and reference documents. They describe tasks for Claude Code to execute — they are not application code.

- Read any `.md` file in this directory freely
- Do not execute `.md` files as shell commands
- Do not modify mission prompts once they have been executed
- Archive completed mission prompts by moving them to `prompts/Archive/`

---

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

```
Build complete. Changes: [list files touched]
Recommended QA level: [0/1/2]
Reason: [one sentence — why this level]
Run QA? [waiting for your answer]
```

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
