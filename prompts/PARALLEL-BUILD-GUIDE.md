# Parallel Build Guide
## Options Analyzer — Phases 2.9 through 3.6

This document is the master sequencing guide. Read this before starting any phase.
It tells you which Claude Code sessions can run simultaneously, when to integrate,
and when to run integration tests.

---

## STATUS — Last Updated 2026-03-12

### ✅ COMPLETE
- **Phase 2.9** — Security Dashboard + Strategy Scorecard (all streams A + B)
- **Phase 2.10** — Positions Page + Follow/Take Position (all streams A + B)
- **Phase 2.11** — Structured Claude Evaluation + Probability Matrix (all streams A + B)
- **Phase 3.5** — Position Monitor Agent + APScheduler (all streams A + B)
  - Stream C (Foundry portal registration) — **manual step still pending** — register
    `ota-position-monitor-agent` in Azure AI Foundry and add `POSITION_MONITOR_AGENT_ID` to `.env`

### ⏭ NEXT UP
- **Phase 3.6** — Insight Engine (generic) + Options Domain — **not started**
  - Start with: Session 9 Window 2 → `3.6-A1` (Insight model + DeviationDetector)
  - Then: Session 10 Window 2 → `3.6-A2` (InsightEngine + insight_routes.py)
  - Then: Session 11 Windows 1 + 2 → options SKILL.md + InsightCard + Dashboard feed

### Git tags outstanding
- `v2.0.0-pre-azure` — not yet tagged (Integration Test 2 not formally run)
- `v2.1.0` — not yet tagged (Phase 3.6 not complete)

---

## The Big Picture

```
Phase 2.9  ──────────────────────────────────► Phase 2.11
           Stream A (backend) ┐                  ↓
           Stream B (frontend)┘            Integration Test 1

Phase 2.10 ──────────────────────────────────► (parallel with 2.9 possible)
           Stream A (backend) ┐
           Stream B (frontend)┘

                    ↓ Integration Test 2 (2.9 + 2.10 + 2.11 combined)

Phase 3    ─────────────────────────────────────────────────────►
           (Azure deployment — prerequisite for 3.5 and 3.6)

Phase 3.5  ──────────────────────────────────► Phase 3.6
           Stream A (infra) ┐                    ↓
           Stream B (agent) ┤             Integration Test 3
           Stream C (Foundry)┘
```

---

## Session Sequencing: What To Run When

### Session 1 — Foundation (2 parallel Claude Code windows)

**Window 1: Phase 2.9 Stream A**
Paste Prompt A1 from PHASE-2.9.md
→ Creates strategy_definitions.py and black_scholes.py

**Window 2: Phase 2.9 Stream B**
Paste Prompt B1 from PHASE-2.9.md
→ Creates StrategyScorecard.jsx (mock data) and SecurityDashboard.jsx

These are completely independent. Run simultaneously.

---

### Session 2 — Backend completion + Frontend wiring (2 parallel windows)

**Prerequisite**: Session 1 complete.

**Window 1: Phase 2.9 Stream A continued**
Paste Prompt A2 from PHASE-2.9.md
→ Creates strategy_scorer.py and the two new API endpoints

**Window 2: Phase 2.10 Stream A**
Paste Prompt A1 from PHASE-2.10.md
→ Creates positions table, Position model, health_grade.py

These are independent. Run simultaneously.

---

### Session 3 — Position API + Frontend integration (2 parallel windows)

**Prerequisite**: Session 2 complete.

**Window 1: Phase 2.10 Stream A continued**
Paste Prompt A2 from PHASE-2.10.md
→ Creates position_routes.py with all 5 endpoints

**Window 2: Phase 2.9 Stream B continued + Phase 2.10 Stream B**
Paste Prompt B1 from PHASE-2.10.md (PositionsPage with mock data)
Can also start Phase 2.9 Prompt B2 if backend endpoints from Session 2 are ready

These are independent. Run simultaneously.

---

### Session 4 — Integration Test 1: Phase 2.9

**Prerequisite**: Sessions 1-3 complete, both 2.9 streams done.

Paste Phase 2.9 Prompt B2 (wire SecurityDashboard to real backend data).

Then run Integration Tests 1-5 from PHASE-2.9.md manually.

**Stop here if any test fails.** Fix before proceeding.

---

### Session 5 — Phase 2.11 (2 parallel windows)

**Prerequisite**: Phase 2.9 integration tests passing.

**Window 1: Phase 2.11 Stream A**
Paste Prompt A1 from PHASE-2.11.md
→ Updates SKILL.md for structured output, creates evaluation endpoint

**Window 2: Phase 2.11 Stream B**
Paste Prompt B1 from PHASE-2.11.md
→ Creates ProbabilityMatrix.jsx and TradeEvaluationCard.jsx (mock data)

These are independent. Run simultaneously.

---

### Session 6 — Phase 2.10 wiring + Phase 2.11 wiring (2 parallel windows)

**Prerequisite**: Session 5 complete.

**Window 1: Phase 2.10 Stream B wiring**
Paste Prompt B2 from PHASE-2.10.md
→ Wires PositionsPage to real data, adds Follow/Take Position buttons

**Window 2: Phase 2.11 Stream B wiring**
Paste Prompt B2 from PHASE-2.11.md
→ Wires evaluation flow end-to-end, retires AskClaudePanel

These are mostly independent. Run simultaneously.
Note: Phase 2.11 B2 adds claude_* data to Follow/Take Position — coordinate
with Phase 2.10 B2 if both touch the same button handlers.

---

### Integration Test 2 — Full Phase 2.9 + 2.10 + 2.11

**Prerequisite**: Sessions 4-6 complete.

Run these tests in order:

1. Phase 2.9 Integration Tests (all 5) — verify scorecard still works
2. Phase 2.10 Integration Tests (all 5) — verify positions work
3. Phase 2.11 Integration Tests (all 6) — verify structured evaluation works
4. **Cross-phase test**: Follow a trade from the evaluation card → verify position
   has all claude_* fields populated → verify health grade computes correctly
5. **Retirement test**: Confirm AskClaudePanel is gone, old endpoints return 410

**Git tag**: After passing all tests, tag as `v2.0.0-pre-azure`

---

### Session 7 — Azure Deployment (Phase 3)

**Prerequisite**: Integration Test 2 passing, v2.0.0-pre-azure tagged.

This is the standard Phase 3 deployment sequence from the project plan:
- Azure SQL (migrate from SQLite)
- Key Vault
- App Service
- Static Web App

All new tables from Phases 2.9/2.10/2.11 deploy with the Azure SQL migration.

**After Azure deployment**: run Integration Test 2 again against Azure to verify
cloud deployment is clean.

---

### Session 8 — Phase 3.5 Infrastructure (2 parallel windows)

**Prerequisite**: Azure deployment complete and verified.

**Window 1: Phase 3.5 Stream A**
Paste Prompt A1 from PHASE-3.5.md
→ Creates symbol_context table, ContextSource interface, SchwabPriceContextSource,
  ContextStore

**Window 2: Phase 3.5 Stream C (Foundry Registration)**
Do this manually in Azure portal — no Claude Code needed.
Register ota-position-monitor-agent in Foundry. Note Entra Agent ID.

These are independent. Run simultaneously.

---

### Session 9 — Phase 3.5 Agent (2 parallel windows)

**Prerequisite**: Session 8 complete.

**Window 1: Phase 3.5 Stream B, Prompt B1**
→ Creates position_monitor.py + SKILL.md

**Window 2: Phase 3.6 Stream A, Prompt A1**
→ Creates insights table, DeviationDetector

These are independent. Run simultaneously.

---

### Session 10 — Phase 3.5 completion + Phase 3.6 engine (2 parallel windows)

**Prerequisite**: Session 9 complete.

**Window 1: Phase 3.5 Stream B, Prompt B2**
→ Adds scheduler, on-demand endpoint

**Window 2: Phase 3.6 Stream A, Prompt A2**
→ Creates InsightEngine, insight_routes.py

These are independent. Run simultaneously.

---

### Session 11 — Phase 3.6 wiring (3 parallel windows)

**Prerequisite**: Session 10 complete.

**Window 1: Phase 3.6 Stream B, Prompt B1**
→ Creates options SKILL.md, wires InsightEngine into Position Monitor

**Window 2: Phase 3.6 Stream C, Prompt C1**
→ Creates InsightCard.jsx, Dashboard feed (mock data)

**Window 3: Phase 3.5 Integration Testing**
Run Integration Tests 1-5 from PHASE-3.5.md manually

Three windows simultaneously. Windows 1 and 2 are independent of each other.
Window 3 (testing) can run while 1 and 2 are building.

---

### Integration Test 3 — Full Phase 3.5 + 3.6

**Prerequisite**: Sessions 8-11 complete.

Run these tests in order:

1. Phase 3.5 Integration Tests (all 5)
2. Phase 3.6 Integration Tests (all 6)
3. **End-to-end test**:
   - Create a paper position
   - Manually set its price past the exit warning in SQL
   - Run position monitor
   - Verify insight appears in database
   - Navigate to Dashboard — verify insight card shows
   - Click View Position — verify navigation to correct position
   - Click Dismiss — verify insight disappears
4. **Domain isolation test** (Phase 3.6 Test 5) — generic engine stays generic

**Git tag**: After passing, tag as `v2.1.0`

---

## What To Do When A Test Fails

**Individual test failure**: Fix the specific issue in that stream. Re-run only
the failing test — don't re-run the full suite.

**Multiple related test failures**: Usually indicates a data model mismatch.
Check schemas.py, the SQLAlchemy model, and the API response shape are all consistent.

**Integration test failure after parallel streams merge**: Usually indicates one
stream made an assumption about another stream's output. Check the API contract
(request/response shape) between the two streams.

**Never skip a failing test and move to the next phase.** Each phase builds on
the previous. A broken foundation causes cascading failures.

---

## Quick Reference: Which Prompts Can Run Simultaneously

| Session | Window 1 | Window 2 | Window 3 |
|---------|----------|----------|----------|
| 1 | 2.9-A1 | 2.9-B1 | — |
| 2 | 2.9-A2 | 2.10-A1 | — |
| 3 | 2.10-A2 | 2.10-B1 + 2.9-B2 | — |
| 4 | 2.9-B2 wiring | Manual testing | — |
| 5 | 2.11-A1 | 2.11-B1 | — |
| 6 | 2.10-B2 | 2.11-B2 | — |
| 7 | Azure deployment | — | — |
| 8 | 3.5-A1 | Foundry portal | — |
| 9 | 3.5-B1 | 3.6-A1 | — |
| 10 | 3.5-B2 | 3.6-A2 | — |
| 11 | 3.6-B1 | 3.6-C1 | 3.5 tests |

---

## Files Modified Per Phase (Quick Reference)

### Phase 2.9
New: `strategy_definitions.py`, `black_scholes.py`, `strategy_scorer.py`,
`StrategyScorecard.jsx`, `SecurityDashboard.jsx`, `steady-paycheck.config.js`,
`weekly-grind.config.js`, `trend-rider.config.js`, `lottery-ticket.config.js`
Updated: `analysis_routes.py`, `schemas.py`, `ConfigDrawer.jsx`,
`OptionsTerminal.jsx`, `App.jsx`, `strategy-configs/index.js`

### Phase 2.10
New: `position_routes.py`, `health_grade.py`, `PositionsPage.jsx`,
`PositionHealthBadge.jsx`
Updated: `database.py`, `schemas.py`, `main.py`, `Header.jsx`,
`OptionsTerminal.jsx`, `client.js`, `App.jsx`

### Phase 2.11
New: `TradeEvaluationCard.jsx`, `ProbabilityMatrix.jsx`
Updated: `evaluation_routes.py`, `schemas.py`, `SecurityDashboard.jsx`,
`OptionsTerminal.jsx`, `client.js`, `app/skills/claude-trade-agent/SKILL.md`
Deprecated: `AskClaudePanel.jsx` (keep file, remove all imports)

### Phase 3.5
New: `context_store.py`, `position_monitor.py`, `schwab_context_source.py`,
`agents_routes.py`, `app/skills/position-monitor/SKILL.md`
Updated: `database.py`, `providers/base.py`, `main.py`, `requirements.txt`

### Phase 3.6
New: `deviation_detector.py`, `insight_engine.py`, `insight_routes.py`,
`InsightCard.jsx`, `app/skills/insight-engine/SKILL.md`,
`app/skills/insight-engine/domains/options/SKILL.md`
Updated: `database.py`, `position_monitor.py`, `main.py`, `DashboardPage.jsx`,
`client.js`
