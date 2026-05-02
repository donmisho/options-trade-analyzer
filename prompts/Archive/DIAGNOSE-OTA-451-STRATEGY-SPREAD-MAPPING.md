---
ticket: OTA-451
phase: 2b (diagnostic follow-up)
mode: read-only
terminal: T2 (frontend inspection)
allowedTools:
  - Bash(cat *, grep *, find *, ls *, head *, tail *, sed *, awk *, wc *, git log *, git show *)
  - Read
  - Glob
---

# OTA-451 Phase 2b — How does strategy selection reach buildApiParams today?

## Context

OTA-451 Phase 2 commit `0e56cb3` (branch `fix/OTA-451-credit-spread-pipeline`) routed `TradesPage.fetchVerticals` through `buildApiParams`. That eliminates the camelCase/snake_case key mismatch that was silently dropping config — but Claude Code's own summary flagged that three of the four call sites pass `config = {}` and `buildApiParams` defaults to debit-only when called that way. Default page load still requests debit-only. No user-visible change.

Separately, the ConfigDrawer no longer has Bull Put / Bear Call checkboxes. It exposes strategies (SP, WG, TR, LT) as the user-facing selection. Claude Code's suggested verification path ("enable Bull Put in ConfigDrawer") doesn't exist in the UI anymore.

Before writing Phase 2c, we need to know exactly what lives in `verticals.config.js` and the ConfigDrawer state today — specifically whether a `strategies → spread_types` mapping already exists anywhere, or whether it's new territory.

## Hard rules

1. **Read-only.** No edits. No commits. No file creation except your own scratch notes if needed.
2. **Report at the end, not per step.** Finish all four steps, then produce the single report at the bottom.
3. **Paste actual code for the key functions.** Don't summarize `buildApiParams` — copy it verbatim into the report. Same for the ConfigDrawer state shape.
4. **If something contradicts Phase 1 or Phase 2 Phase A's findings, flag it.** Don't harmonize silently.

## Setup

```bash
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
git status
git log --oneline -5
git branch --show-current
```

Confirm you're on `fix/OTA-451-credit-spread-pipeline` or a branch that includes `0e56cb3`. If on a different branch, stop and report.

---

## Step 1 — Full contents of buildApiParams

```bash
cat web/src/strategy-configs/verticals.config.js
```

**Report:**
- Paste `buildApiParams` verbatim (the whole function).
- What keys does it read from `cfg`? (`spreadTypes`? `strategies`? `trade_structure`? something else?)
- What does it return when `cfg` is empty / `{}` / undefined?
- Is there any mapping from strategy keys (SP/WG/TR/LT) to spread types anywhere in this file?
- Paste the default config export (if one exists) verbatim.

## Step 2 — What ConfigDrawer actually emits today

```bash
# Find the ConfigDrawer component(s)
find web/src -name "ConfigDrawer*" -o -name "*Config*Drawer*"

# Read the main ConfigDrawer
cat web/src/components/ConfigDrawer.jsx 2>/dev/null || find web/src -name "ConfigDrawer.jsx" -exec cat {} \;

# Grep for what it writes to localStorage or calls onApply with
grep -n "onApply\|localStorage\|strategyOverrides\|spreadTypes\|strategies" web/src/components/ConfigDrawer*.jsx

# Also check for any strategy toggle / selection UI
grep -rn "SP\|WG\|TR\|LT\|steady-paycheck\|weekly-grind\|trend-rider\|lottery-ticket" web/src/components/ConfigDrawer*.jsx | head -30
```

**Report:**
- What shape is the state that ConfigDrawer manages? Paste the useState initial value(s).
- What does it pass to its parent via onApply (or equivalent)?
- Does ConfigDrawer still have any concept of individual spread-type toggles (`bull_call`, `bear_put`, etc.), or has it moved fully to strategy selection?
- What's the user-facing UI — four strategy checkboxes? A single strategy dropdown? A multi-select? Paste the relevant JSX.

## Step 3 — The config argument at each fetchVerticals call site

```bash
# All four call sites with full context
sed -n '810,830p' web/src/pages/TradesPage.jsx
echo "---"
sed -n '820,840p' web/src/pages/TradesPage.jsx
echo "---"
sed -n '830,850p' web/src/pages/TradesPage.jsx  # fetchVerticals body, post-0e56cb3
echo "---"
sed -n '906,935p' web/src/pages/TradesPage.jsx

# What does the first call site pass?
grep -B2 -A5 "fetchVerticals" web/src/pages/TradesPage.jsx
```

**Report:**
- For each call site (post-`0e56cb3` line numbers): what is the actual shape of `config` / the second argument being passed?
- Is there any place the selected strategy (from ConfigDrawer or URL param `?strategy=`) is currently being threaded into the config?
- Is the `?strategy=` URL param consumed anywhere in TradesPage today?

## Step 4 — Strategy-to-spread-type mapping, if any

```bash
# Is there an authoritative mapping anywhere?
grep -rn "trade_structure\|tradeStructure\|spread_type.*strategy\|strategy.*spread_type" web/src/ --include="*.js" --include="*.jsx" | head -40

# The strategy config files (SP/WG/TR/LT) should have trade_structure per CLAUDE.md
find web/src -path "*/strategy-configs/*" -name "*.js" -o -path "*/strategy-configs/*" -name "*.jsx"
ls web/src/strategy-configs/ 2>/dev/null

# Read each strategy config file for its trade_structure
for f in web/src/strategy-configs/steady-paycheck* web/src/strategy-configs/weekly-grind* web/src/strategy-configs/trend-rider* web/src/strategy-configs/lottery-ticket*; do
  echo "=== $f ==="
  grep -n "trade_structure\|tradeStructure\|spread_type\|spreadType" "$f" 2>/dev/null
done

# Backend side — is there a strategy → spread_type mapping?
grep -rn "trade_structure\|tradeStructure" app/analysis/ app/api/ --include="*.py" | head -20
```

**Report:**
- Is there a canonical `strategy_key → [spread_type, ...]` mapping anywhere in the codebase today? If yes: where, and paste it.
- Does each strategy config file declare a `trade_structure` field? Paste the value for each of SP, WG, TR, LT.
- Is the mapping consistent with domain intent (SP → credit spreads, WG → credit spreads, TR → debit spreads, LT → debit spreads)?

---

## Final consolidated report

Produce one report with this exact structure:

```
## OTA-451 Phase 2b Findings — 04-24-2026

### Step 1 — buildApiParams
<verbatim function>
- Signature: buildApiParams(<args>)
- Keys read from cfg: <list>
- Return shape when cfg={}: <paste or describe>
- Strategy → spread_types mapping inside: YES / NO — <location if yes>
- Default config export: <verbatim or "none found">

### Step 2 — ConfigDrawer emission
- Initial state shape: <paste useState initial>
- Emitted to parent on apply: <paste or describe shape>
- Individual spread-type toggles still present in UI: YES / NO
- Strategy selection UI pattern: <checkboxes / dropdown / multi-select / other>
- JSX (relevant excerpt): <paste>

### Step 3 — fetchVerticals call sites today
- Site 1 (line ~X, ConfigDrawer apply): config = <shape>
- Site 2 (line ~X, mount auto-fetch): config = <shape or absent>
- Site 3 (line ~X, symbol change): config = <shape or absent>
- Site 4 (line ~X, section toggle): config = <shape or absent>
- ?strategy= URL param consumed: YES / NO — <location if yes>
- Selected strategy currently threaded anywhere into config: YES / NO

### Step 4 — Strategy → spread_type mapping
- Authoritative mapping exists: YES / NO — <location if yes>
- trade_structure values:
    - steady-paycheck: <value>
    - weekly-grind: <value>
    - trend-rider: <value>
    - lottery-ticket: <value>
- Consistent with domain intent (SP/WG credit, TR/LT debit): YES / NO / PARTIAL — <notes>

### Decision inputs for Don

A. Default page-load behavior today: requests <list of spread types>
B. To make default page-load surface all four: <one-line change description — e.g., "change buildApiParams default fallback to return all four" OR "add strategies: [SP,WG,TR,LT] to fetchVerticals default config">
C. Strategy-derived behavior feasibility:
    - Mapping source exists: YES / NO
    - If YES: buildApiParams needs <change description> to consume it
    - If NO: new mapping needs to be added in <location>
    - Complexity estimate: S / M / L

### Anything that contradicts Phase 1 or Phase 2 Phase A findings
<list or "none">
```

End of Phase 2b. Do not write any Phase 2c code. Wait for direction on which default behavior to implement.
