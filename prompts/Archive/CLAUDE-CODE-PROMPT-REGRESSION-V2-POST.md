---
allowedTools:
  - Bash(*)
  - Read(*)
  - Write(*)
  - Edit(*)
---

# Post-Integration Documentation Pass

**Ticket:** OTA-411
**Commit prefix:** `OTA-411 docs: transition Sprint 3/4 to DONE, update UI-GUIDANCE, CLAUDE.md, architecture-plan`

Run this AFTER Terminal 1 and Terminal 2 are both committed and merged.

---

## Step 1: Transition Sprint 3 & 4 to DONE in Jira

Use the Jira REST API to transition these epics and features to DONE:

### Sprint 3
```bash
# Epic
curl -s -X POST "https://tmtctech-team.atlassian.net/rest/api/3/issue/OTA-365/transitions" \
  -H "Authorization: Basic $(echo -n "$JIRA_EMAIL:$JIRA_API_TOKEN" | base64)" \
  -H "Content-Type: application/json" \
  -d '{"transition":{"id":"51"}}'

# Features
for key in OTA-366 OTA-367 OTA-368; do
  curl -s -X POST "https://tmtctech-team.atlassian.net/rest/api/3/issue/$key/transitions" \
    -H "Authorization: Basic $(echo -n "$JIRA_EMAIL:$JIRA_API_TOKEN" | base64)" \
    -H "Content-Type: application/json" \
    -d '{"transition":{"id":"51"}}'
done
```

### Sprint 4
```bash
# Epic
curl -s -X POST "https://tmtctech-team.atlassian.net/rest/api/3/issue/OTA-376/transitions" \
  -H "Authorization: Basic $(echo -n "$JIRA_EMAIL:$JIRA_API_TOKEN" | base64)" \
  -H "Content-Type: application/json" \
  -d '{"transition":{"id":"51"}}'

# Features
for key in OTA-377 OTA-378 OTA-379; do
  curl -s -X POST "https://tmtctech-team.atlassian.net/rest/api/3/issue/$key/transitions" \
    -H "Authorization: Basic $(echo -n "$JIRA_EMAIL:$JIRA_API_TOKEN" | base64)" \
    -H "Content-Type: application/json" \
    -d '{"transition":{"id":"51"}}'
done
```

**Important:** First fetch the Jira API token from Azure Key Vault:
```bash
export JIRA_API_TOKEN=$(az keyvault secret show --vault-name options-analyzer --name jira-api-token --query value -o tsv)
```

If the `JIRA_EMAIL` env var is not set, ask Don for it.

---

## Step 2: Update UI-GUIDANCE.md

Read current file:
```
cat claude_context/UI-GUIDANCE.md
```

Updates needed:
1. **Part 10, Screen 2 (Trades):** Remove ProbabilityMatrix from trade detail section spec. Sections are now A → B → C → E (no D).
2. **Part 10, Screen 1 (Security Strategies):** Note v3 card grid is complete, watchlist-driven, Add Symbol typeahead wired.
3. **Part 11 (Retired items):** Add:
   - Watchlist sidebar panel (replaced by Positions page + watchlist auto-add)
   - ProbabilityMatrix display (backend retained, frontend removed from trade detail)
   - AskClaudePanel (replaced by Section E inline evaluation)
4. **Part 12:** Add rule: "Trade type badges: clean display names (title case, spaces, no underscores). Bull = green, Bear = red. Frontend transforms enum at render time."
5. Update timestamp at top of file.

---

## Step 3: Update CLAUDE.md

Read current file:
```
cat claude_context/CLAUDE.md
```

Updates needed:
1. **Phase History:** Add entry:
   ```
   - **Sprint 5**: Integration, polish & cleanup — regression fixes (evaluate payload, pill colors, dropdown, watchlist auto-add, exit scenarios condensed), scorecard API enrichment (quote data + signal), scan page caching, CSS custom properties for strategy colors, column reorder, cleanup (dead files, alert→Toast, RefreshConfirmDialog consolidation) ✅
   ```
2. **Known Limitations:** Remove items that are now fixed (if any are listed)
3. **File tree:** Note deleted files (AskClaudePanel_v2.jsx, Watchlist.jsx)
4. Update timestamp at top of file.

---

## Step 4: Update architecture-plan.md

Read current file:
```
cat claude_context/architecture-plan.md
```

Updates needed:
1. **Phase History:** Add Sprint 5 entry matching CLAUDE.md
2. Update timestamp at top of file.

---

## Verification

```bash
# Confirm all doc files have today's date in the header
head -1 claude_context/UI-GUIDANCE.md
head -1 claude_context/CLAUDE.md
head -1 claude_context/architecture-plan.md
```

All should show today's date.

```bash
# Confirm no stale references to deleted components
grep -rn "AskClaudePanel_v2\|ProbabilityMatrix" claude_context/UI-GUIDANCE.md
```
Should return zero hits (or only in the "retired" section).
