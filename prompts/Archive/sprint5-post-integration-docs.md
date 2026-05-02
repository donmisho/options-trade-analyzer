---
allowedTools:
  - Bash(*)
  - Read(*)
  - Write(*)
  - Edit(*)
---

# Sprint 5 — Post-Integration: Documentation & Status Cleanup

**Ticket:** OTA-411
**Commit prefix:** `OTA-411`

Run this AFTER all three terminals have committed and you've verified the integration manually.

---

## Step 1 — Update UI-GUIDANCE.md

1. `cat claude_context/UI-GUIDANCE.md` to read current state
2. Update Part 10 Screen 1: Note that Security Strategies page is now the v3 card grid (filter bar + multi-symbol scan + ScanCard cards + click → Trades)
3. Update Part 10 Screen 2: Remove Section D (ProbabilityMatrix) from the trade detail expansion spec. Trade detail is now A → B → C → E.
4. Update Part 11 (Retired items): Add these entries:
   - `ProbabilityMatrix in trade detail` → `Backend scoring only (not displayed)`
   - `Watchlist sidebar panel` → `Positions page`
   - `Single-symbol Security Strategies page` → `Multi-symbol card grid`
   - `AskClaudePanel.jsx` → `Claude's Read (Section E)`
   - `FavoritesPage.jsx` → `Positions page`
   - `OptionsTerminal.jsx` → `TradesPage.jsx`
5. Update the timestamp at the top of the file

## Step 2 — Update CLAUDE.md

1. `cat claude_context/CLAUDE.md` to read current state
2. Update Phase History: Add `Sprint 5: Scan page v3 rebuild, deprecated code removal, ProbabilityMatrix display removed, Watchlist panel removed, trade type badge fix, Toast component, StrategyPage editable params, navigation verification ✅`
3. Update Known Limitations: Remove items that Sprint 5 fixed:
   - Remove "OptionsTerminal.jsx and SecurityDashboard.jsx are retired but not yet deleted"
   - Remove "Watchlist/favorites not yet synced to backend"
4. Update file tree: Remove deleted files (AskClaudePanel, FavoritesPage, OptionsTerminal, SecurityDashboard x2), add new files (ScanCard.jsx, Toast.jsx)
5. Update the Security Strategies page note: "Config drawer removed" → "Full v3 card grid with watchlist scan, filter bar, card click → Trades"
6. Update timestamp

## Step 3 — Update architecture-plan.md

1. `cat claude_context/architecture-plan.md` to read current state
2. Update Phase History: Add Sprint 5 entry
3. Verify no contradictions with UI-GUIDANCE.md or CLAUDE.md
4. Update timestamp

## Step 4 — Jira status cleanup

This step documents the Jira transitions to make. Execute via the Atlassian MCP in Claude Web or manually in Jira:

**Sprint 3 (code was done, Jira wasn't updated):**
- OTA-365 (Epic) → DONE
- OTA-366 (Strategy Page) → DONE
- OTA-367 (Positions v3) → DONE
- OTA-368 (Doc Updates Sprint 3) → DONE

**Sprint 4 (code was done, Jira wasn't updated):**
- OTA-376 (Epic) → DONE
- OTA-377 (Section E Wiring) → DONE
- OTA-378 (Puts & Calls) → DONE
- OTA-379 (Config Drawers, Cleanup) → DONE

Note: Sprint 4 subtasks (OTA-380 through OTA-390) are already DONE.

## Verification

1. All three docs have updated timestamps
2. No contradictions between documents
3. Part 11 retired items list is comprehensive
4. File tree in CLAUDE.md matches actual filesystem
5. Phase history is accurate and complete
