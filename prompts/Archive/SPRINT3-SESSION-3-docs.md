OTA-375

## SESSION 3 — Document Updates
### Run AFTER Sessions 1 and 2 are both committed

---

### Step 1 — Update CLAUDE.md

1. Update the "UI Decisions" / shared components section:
   - Add StrategyPage description: "StrategyPage.jsx — full strategy page with header,
     editable parameters, read-only scoring weights, 'Find trades →' navigation, and
     strategy-filtered positions table with Refresh all cost guardrail."
   - Add RefreshConfirmDialog: "RefreshConfirmDialog.jsx — reusable confirmation dialog
     for multi-position Claude API refresh. Used on both PositionsPage and StrategyPage."
   - Update PositionsPage description: "PositionsPage.jsx — v3 design with StrategyPill
     (abbreviated 2-letter pills), health grade letter badges (A-F), versioned re-reads
     with white outlined Claude advice badge, exit plan levels, group by
     strategy/symbol/health."
   - Add cost guardrail note: "Claude API cost guardrail: Refresh all shows confirmation
     dialog when >1 position. Single position refresh runs without confirmation. One
     daily auto-refresh per position after market close. Never on page load or timers."

2. Update timestamp

### Step 2 — Update project-hierarchy.md

1. Update StrategyPage.jsx entry from "(placeholder)" to full description
2. Add RefreshConfirmDialog.jsx under components/
3. Update PositionsPage.jsx description to v3
4. Update timestamp

---

Commit message: OTA-375 docs: update CLAUDE.md and project-hierarchy.md for Sprint 3

Recommended QA level: 0 (documentation only)
