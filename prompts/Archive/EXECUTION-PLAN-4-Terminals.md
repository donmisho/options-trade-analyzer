# OTA — 4-Terminal Execution Plan
## All IN PROGRESS Prompts (March 28, 2026)

Run all four terminals simultaneously. Each terminal is independent.
Start all four at the same time after reviewing this plan.

---

## ⚡ Terminal 1 — Hotfixes (run first, fastest)

Two isolated one-file bugs. Sequential within this terminal.

| Order | Prompt File | Tickets | Est. |
|-------|-------------|---------|------|
| 1st | `PROMPT-OTA-327-QuoteBar-Stale-Symbol-Hotfix.md` | OTA-327 | ~5 min |
| 2nd | `PROMPT-OTA-NEW-RiskBudget-Hotfix.md` | OTA-[NEW] | ~10 min |

**Commit cadence:** One commit per ticket.

```
OTA-327  Fix stale activeSymbol on init — remove localStorage read
OTA-[N]  Fix risk budget max loss display and remove acct% line
```

---

## 🔧 Terminal 2 — Frontend: SystemVarsPanel (sequential within terminal)

OTA-325 must complete and validate before OTA-326 starts.
OTA-183/185 depend on OTA-325 (SystemVarsPanel must exist before Strategies Admin can live inside it).

| Order | Prompt File | Tickets | Est. |
|-------|-------------|---------|------|
| 1st | `PROMPT-OTA-325-SystemVarsPanel-Extract.md` | OTA-325 | ~30 min |
| 2nd | `PROMPT-OTA-326-GearIcon-Wire-SystemVarsPanel.md` | OTA-326 | ~10 min |
| 3rd | `PROMPT-OTA-183-185-Strategies-Nav-Admin.md` | OTA-183, OTA-185 | ~30 min |

**Validate between each step** — spot-check gear icon and SystemVarsPanel open/close before
moving to next prompt in this terminal.

```
OTA-325  Extract SystemVarsPanel from ConfigDrawer, wire gear icon placeholder
OTA-326  Wire gear icon permanently to SystemVarsPanel, add tooltip and hover style
OTA-183 OTA-185  Add strategies nav section and light strategy admin
```

---

## 🐍 Terminal 3 — Backend: AI / SKILL.md (run in order, fast)

Both tickets touch `claude-trade-agent/SKILL.md`. Run OTA-296 first, validate, then
OTA-264/266 adds `synopsis` on top of the structured prompt.

| Order | Prompt File | Tickets | Est. |
|-------|-------------|---------|------|
| 1st | `PROMPT-OTA-296-SKILL-Structured-Evaluation.md` | OTA-296 | ~20 min |
| 2nd | `PROMPT-OTA-264-266-Position-Refresh-Synopsis.md` | OTA-264, OTA-266 | ~40 min |

```
OTA-296  Update claude-trade-agent SKILL.md with structured evaluation prompt
OTA-264 OTA-266  Add synopsis to SKILL.md, build position refresh endpoint
```

---

## 🗄️ Terminal 4 — Backend: DB + Dashboard + Positions (sequential)

All backend/data work. Run in order within this terminal.

| Order | Prompt File | Tickets | Est. |
|-------|-------------|---------|------|
| 1st | `PROMPT-OTA-200-OptionsChainSnapshots-Table.md` | OTA-200 | ~30 min |
| 2nd | `PROMPT-OTA-179-177-Dashboard-Widgets.md` | OTA-179, OTA-177 | ~40 min |
| 3rd | `PROMPT-OTA-173-171-Positions-Health-Context.md` | OTA-173, OTA-171 | ~40 min |

```
OTA-200  Create options_chain_snapshots table and daily collection endpoint
OTA-179 OTA-177  Add Positions Scorecard and Market Overview dashboard widgets
OTA-173 OTA-171  Add portfolio context banner and health grade computation
```

---

## Ticket Count Summary

| Terminal | Tickets | Prompts |
|----------|---------|---------|
| T1 — Hotfixes | OTA-327, OTA-[NEW] | 2 |
| T2 — Frontend | OTA-325, OTA-326, OTA-183, OTA-185 | 3 |
| T3 — AI/SKILL | OTA-296, OTA-264, OTA-266 | 2 |
| T4 — DB/Data | OTA-200, OTA-179, OTA-177, OTA-173, OTA-171 | 3 |
| **Total** | **13 tickets** | **10 prompts** |

---

## Notes

- Terminal 1 is the fastest — likely done before any other terminal finishes its first prompt
- Terminal 2 step 3 (OTA-183/185) places Strategy Admin inside SystemVarsPanel — do not start
  it until OTA-325 is validated
- Terminal 3 step 2 (OTA-264/266) reads SKILL.md written by step 1 (OTA-296) — run sequentially
- Terminal 4 items are independent of each other but sequential within the terminal to avoid
  DB migration conflicts
- Commit messages must begin with OTA ticket numbers for GitHub→Jira automation to fire
