# Write Prompt Queue — Launch Sheet

**Created:** 2026-05-10
**Source:** Jira `status = "Write Prompt"` (27 items pulled)
**Approach:** 1 prompt per terminal per deployment; single push per deployment.

---

## Items NOT covered by Claude Code prompts (your hands-on work)

These 5 Subtasks are explicitly "Done by Don directly at profile level — Claude Web cannot reach profile docs from project context." They live outside the OTA repo and need to be applied by you against the profile-level files.

| Ticket | Profile-level doc | Source draft |
|---|---|---|
| OTA-589 | `jira-structure.md` — Feature-removal update | Wording in the ticket description |
| OTA-590 | `prompt-style.md` — initial creation | `/mnt/user-data/outputs/prompt-style.md` |
| OTA-591 | `build-execution.md` — initial creation | `/mnt/user-data/outputs/build-execution.md` |
| OTA-592 | `claude-web.md` — initial creation | `/mnt/user-data/outputs/claude-web.md` |
| OTA-594 | `CLAUDEMD-root-pointer-template.md` — initial creation | `/mnt/user-data/outputs/CLAUDEMD-root-pointer-template.md` |

Each transitions to Code & Test Complete after you apply the change.

---

## Deployment 0 — Jira hygiene (Claude.ai action, no terminal)

| Action | Tickets affected | Tool |
|---|---|---|
| OTA-623 execution | OTA-604 (parent), OTA-605, 606, 607, 608, 609 → Idea + "ON HOLD: " prefix; OTA-612 → closed; OTA-615 untouched | Atlassian MCP from Claude.ai |

Run this from a Claude.ai session (or this one) before D1. It clears 7 items from the active queue and reframes OTA-604 + children as parked.

---

## Deployment 1 — Gate-fix, agent-prompt coherence, governance docs

**3 terminals, fully parallel. Single push at end.**

| Terminal | Prompt file | Tickets | Files touched | Commit |
|---|---|---|---|---|
| T1 | `D1-T1-OTA-616-620-agent-prompt-cluster.md` | OTA-616, 617, 618, 619, 620 | `app/ai/prompts/<eval prompt template>` | Single commit, 5 tickets |
| T2 | `D1-T2-OTA-628-630-631-verdict-integrity.md` | OTA-628 (High), 630, 631 | `app/api/position_routes.py`, `app/api/evaluation_routes.py`, `app/models/migrations.py`, `web/src/pages/TradesPage.jsx`, `web/src/pages/StrategyPage.jsx`, `web/src/pages/PositionsPage.jsx`, `web/src/widgets/PositionsScorecardWidget.jsx` | Single commit, 3 tickets |
| T3 | `D1-T3-OTA-584-585-586-587-588-595-governance-docs.md` | OTA-584, 585, 586, 587, 588, 595 | `claude_context/CLAUDE.md`, `claude_context/bugfix.md`, `claude_context/product-roadmap.md` (NEW), `claude_context/development-environment.md` (NEW), `claude_context/deployment-workflow.md` (NEW), root `CLAUDE.md` | Single commit, 6 tickets |

**Cross-terminal dependencies:** none. All 3 terminals work disjoint file scopes.

**Push gate:** all 3 terminals report commit → you push once → Jira automation moves 14 tickets to Code & Test Complete in one go.

---

## Deployment 2 — Strategy structure expansion

**2 terminals, T2 sequenced after T1 commit. Single push at end.**

| Terminal | Prompt file | Tickets | Files touched | Commit |
|---|---|---|---|---|
| T1 | `D2-T1-OTA-627-strategy-compatible-structures.md` | OTA-627 | `web/src/strategy-configs/*.config.js`, `web/src/strategy-configs/index.js`, `web/src/pages/TradesPage.jsx`, backend strategy registry, `app/analysis/structural_fit_gate.py` or equivalent | Single commit |
| T2 | `D2-T2-OTA-632-trades-drawer-dynamic-strategies.md` | OTA-632 | `web/src/pages/TradesPage.jsx` (depends on T1's `index.js` map), Configuration drawer body, other strategy-aware surfaces | Single commit |

**Cross-terminal dependency:** T2 must not start Phase 2 (code change) until T1 has committed. T2 may run Phase 1 (read-only discovery) concurrently with T1.

**Push gate:** T1 commits → you signal T2 to proceed → T2 commits → you push once.

---

## Deployment 3 — Scan, cache, export (fully parallel)

**3 terminals, no dependencies. Single push at end.**

| Terminal | Prompt file | Tickets | Files touched | Commit |
|---|---|---|---|---|
| T1 | `D3-T1-OTA-624-persist-trade-candidates.md` | OTA-624 | `app/models/migrations.py` (new `trade_candidates` table), `app/api/evaluation_routes.py`, `app/api/position_routes.py` (Follow reads `trade_key`) | Single commit |
| T2 | `D3-T2-OTA-629-per-watchlist-scan-cache.md` | OTA-629 | `web/src/pages/SecurityStrategiesPage.jsx`, possibly new `web/src/lib/relativeTime.js` | Single commit |
| T3 | `D3-T3-OTA-621-export-md.md` | OTA-621 | `app/api/export_routes.py` (NEW), `web/src/pages/TradesPage.jsx`, `web/src/pages/PositionsPage.jsx`, shared export-button component | Single commit |

**Cross-terminal dependencies:** none. All 3 terminals work disjoint file scopes.

**Push gate:** all 3 terminals report commit → you push once.

---

## Push discipline (applies to every deployment)

1. Each terminal commits to its working branch when its scope passes verification.
2. Each prompt explicitly states **"DO NOT push — single push for Deployment X coordinated by Don."**
3. You merge/integrate the terminal branches as needed and push once.
4. The push triggers `build-on-push.yml` → Jira automation moves all referenced tickets to Code & Test Complete.
5. Slot-swap to prod (per `deployment-workflow.md`) is a separate later step.

---

## Total ticket coverage

- **Deployment 0:** 7 tickets cleared (OTA-604, 605, 606, 607, 608, 609, 612)
- **Deployment 1:** 14 tickets shipped (OTA-616–620 + OTA-628 + OTA-630 + OTA-631 + OTA-584 + OTA-585 + OTA-586 + OTA-587 + OTA-588 + OTA-595)
- **Deployment 2:** 2 tickets shipped (OTA-627, 632)
- **Deployment 3:** 3 tickets shipped (OTA-624, 629, 621)
- **Profile-level by Don:** 5 tickets (OTA-589, 590, 591, 592, 594)

**= 31 tickets — covers all 27 in Write Prompt plus the 4 sibling MCP Stories (OTA-605–609) parked via OTA-623.**

Note: 27 in Write Prompt + 4 parked siblings (which were in Schedule, not Write Prompt) = 31 total touches. The 27 in Write Prompt are all addressed.
