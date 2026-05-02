# Sprint 4 — Post-Integration: Doc Updates

## Session Context

Run this AFTER both Terminal 1 and Terminal 2 have completed and been committed.

**Read these files first:**
1. `UI-GUIDANCE.md`
2. `CLAUDE.md`
3. `architecture-plan.md`

---

## OTA-390: Update living documents

### UI-GUIDANCE.md
- Part 10 Screen 2: Note Section E is fully wired (evaluate → verdict → Follow/Take Position → follow-up)
- Note Section D uses real ProbabilityMatrix with live Black-Scholes data
- Note Puts & calls section has live data from /analyze/long-calls
- Note Config drawers are functional per trade-structure section
- Note VerticalsPage.jsx and LongCallsPage.jsx are deleted

### CLAUDE.md
- Update Phase History / Known Limitations to reflect Sprint 4 completions
- Remove deprecated page references from Frontend Structure section
- Confirm endpoint references match what was built

### architecture-plan.md
- Update Phase History section
- Remove any "NOT STARTED" flags for features now complete

### All files
- Update timestamp header: `# Options Analyzer — [filename] (Updated yyyy-mm-dd hh:mm)`
- Ensure no contradictions between documents

**Commit prefix:** `OTA-390`

```
OTA-390 docs: update living documents for Sprint 4 completions
```

**Recommended QA level:** Level 0 (documentation only)
