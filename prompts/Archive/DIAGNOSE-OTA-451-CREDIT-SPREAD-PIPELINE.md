---
ticket: OTA-451
phase: 1
mode: read-only
allowedTools:
  - Bash(cat *, grep *, find *, ls *, head *, tail *, wc *, sed *, awk *)
  - Read
  - Glob
---

# OTA-451 — Phase 1: Diagnose why SP/WG credit spreads produce zero trade candidates

## Context

OTA-451 shipped to Production on 04-23-2026 21:04 CT claiming to add the credit spread pipeline. 24-hour validation on 04-24-2026 shows zero SP/WG pills on the Trades page for multiple symbols, across DTE windows where SP and WG should qualify (14, 21, 28, 35 DTE against debit spread results; SP window 25–50, WG window 5–16).

The fix either (a) never generated credit candidates at all, (b) generated them but a downstream filter dropped them, or (c) generated them but the display layer doesn't surface the pills. This prompt locates which.

## Hard rules

1. **Read-only.** No file edits. No `git` operations. No package installs. If you find yourself reaching for `str_replace` or `write`, stop and re-read this section.
2. **Report at the end, not after each step.** Finish all five steps, then produce the single consolidated report described at the bottom. Do not run any fix code.
3. **Stop immediately** if a step's expected file doesn't exist — that is itself a finding. Note it and continue to the next step.
4. **Do not guess.** If a grep returns zero matches, report zero matches. Do not infer what the code "probably" does.

## Setup

```bash
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
cat claude_context/CLAUDE.md
cat claude_context/UI-GUIDANCE.md | head -100
cat claude_context/business-rules.md 2>/dev/null | head -50
```

---

## Step 1 — Does the engine define credit spread types at all?

```bash
# Find vertical engine
find app -name "vertical_engine.py" -o -name "vertical*.py" 2>/dev/null

# Look for credit spread enum/types
grep -rn "BULL_PUT_CREDIT\|BEAR_CALL_CREDIT\|bull_put_credit\|bear_call_credit" app/ --include="*.py"

# Look for where spread types are enumerated
grep -rn "spread_type\|SpreadType" app/ --include="*.py" | head -40
```

**Report:**
- Are `bull_put_credit` and `bear_call_credit` defined as spread types in the enum or constants?
- What file defines them?
- Is there a `SpreadType` enum? List all its members.

## Step 2 — Does the engine have builder functions that generate credit candidates?

```bash
# Look for credit spread builder methods
grep -rn "def.*bull_put\|def.*bear_call\|def.*credit_spread\|def _best.*credit\|def _build.*credit" app/ --include="*.py"

# Look for the credit-specific logic: selling higher-strike put, buying lower
grep -rn "sell.*put\|short_put\|short.*call\|short_leg\|higher.*premium" app/analysis/ app/api/ 2>/dev/null --include="*.py" | head -20

# Find the main entry point that dispatches spread generation
grep -rn "_best_bull_call\|_best_bear_put\|for spread_type in\|if spread_type ==" app/ --include="*.py" | head -20
```

**Report:**
- Do `_best_bull_put_credit_spread` / `_best_bear_call_credit_spread` (or equivalents) exist?
- If yes, paste the function signatures (first 5 lines each).
- If no, note that the engine has no generator for credit spreads.
- In the dispatch logic, is there an `if spread_type == "bull_put_credit"` branch?

## Step 3 — What does the frontend actually request?

```bash
# Find where the frontend calls the verticals endpoint
find web/src -name "*.js" -o -name "*.jsx" | xargs grep -l "verticals\|analyze/verticals" 2>/dev/null

# Look at the request payload being sent
grep -rn "spread_types\|spreadTypes" web/src/ 2>/dev/null

# Check the backend request schema default
grep -rn "spread_types.*Field\|spread_types.*=.*\[" app/ --include="*.py" | head -10
```

**Report:**
- What file builds the request to `/api/v1/analyze/verticals`?
- What value does the frontend pass for `spread_types` (or does it omit it)?
- What is the backend default for `spread_types` in the request schema?
- If the frontend passes only `["bull_call", "bear_put"]` OR the backend default excludes credit types, credits are never requested regardless of whether the engine can build them.

## Step 4 — Do the P0 scoring gates filter credits out?

```bash
# Find the P0 / pre-filter gates
grep -rn "credit_pct\|credit.*percent\|credit.*width\|min_credit\|credit_as_pct" app/ --include="*.py" | head -20

# Find the scoring pipeline entry
grep -rn "def score\|def _score\|def filter_candidates\|P0\|pre_filter" app/analysis/ --include="*.py" | head -20

# Check what happens when credit_pct < 30 or similar thresholds
grep -rn "credit.*0.30\|credit.*30\|credit_pct.*<\|credit_pct.*>=" app/ --include="*.py"
```

**Report:**
- Is there a P0 gate that requires `credit ≥ 30% of width`?
- What happens to candidates that fail — excluded entirely, scored zero, or flagged with a reason?
- Is there any log/count of pre-gate vs post-gate candidate counts?

## Step 5 — Does the display layer recognize credit spreads?

```bash
# Find the pill rendering logic
find web/src -name "StrategyPill*" -o -name "ResultsTable*" -o -name "*column*config*"

# Check verticals columns config
cat web/src/config/verticals-columns.js 2>/dev/null | head -80

# Find where strategy pills are derived from trade data
grep -rn "strategies\|strategy_keys\|strategyPills\|SP\|WG" web/src/config/ web/src/components/StrategyPill* web/src/components/ResultsTable* 2>/dev/null | head -30

# Trade type badge logic — does it know about credit spread types?
grep -rn "BULL_PUT_CREDIT\|BEAR_CALL_CREDIT\|bull_put_credit\|bear_call_credit\|Bull Put Credit\|Bear Call Credit" web/src/ 2>/dev/null
```

**Report:**
- Where does the strategies column in the Trades table get its value from? (server field name)
- Is the trade_type badge component aware of `BULL_PUT_CREDIT` / `BEAR_CALL_CREDIT`?
- Does `verticals-columns.js` filter/transform strategies in any way that could drop SP/WG?

---

## Final consolidated report

After all five steps, produce one report with this exact structure (no extra commentary):

```
## OTA-451 Phase 1 Findings — 04-24-2026

### Step 1 — Type definitions
- bull_put_credit defined: YES / NO — file: <path> line <n>
- bear_call_credit defined: YES / NO — file: <path> line <n>
- Definition location: <enum name / module>

### Step 2 — Engine generators
- Bull Put Credit builder exists: YES / NO — function: <name> at <path:line>
- Bear Call Credit builder exists: YES / NO — function: <name> at <path:line>
- Dispatch branch for credit types: YES / NO — at <path:line>

### Step 3 — Request path
- Frontend request file: <path>
- Frontend spread_types value: <literal value>
- Backend schema default: <literal value>
- Credits reach the engine: YES / NO — reasoning: <1 sentence>

### Step 4 — Scoring gates
- Credit % of width gate: YES / NO — implementation at <path:line>
- Gate behavior on failure: <exclude / score zero / flag>
- Gate threshold: <number>
- Observability on gate drops: YES / NO

### Step 5 — Display layer
- Strategies field source: <backend field name>
- Trade type badge knows credit types: YES / NO
- Column config filters strategies: YES / NO — details: <1 sentence>

### Root cause hypothesis (ranked)
1. <most likely gap, one sentence + location>
2. <next most likely, one sentence + location>
3. <third, if any>

### Recommended Phase 2 scope
- Files to edit: <list>
- Files confirmed correct (do not touch): <list>
- Estimated complexity: S / M / L
```

End of Phase 1. Do not start Phase 2. Stop here and wait for approval.
