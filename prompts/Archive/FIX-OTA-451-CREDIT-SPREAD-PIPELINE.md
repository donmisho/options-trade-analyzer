---
ticket: OTA-451
phase: 2
mode: fix
terminal: T2 (frontend only)
complexity: S
allowedTools:
  - Bash(cat *, grep *, find *, ls *, head *, tail *, wc *, sed *, awk *, git diff *, git status *, git add *, git commit *, git push *, npm run lint *, npm run build *)
  - Read
  - Edit
  - Glob
---

# OTA-451 Phase 2 — Route TradesPage verticals fetch through buildApiParams

## Context

Phase 1 diagnostic (04-24-2026) located the root cause:

- `app/analysis/vertical_engine.py` — credit spread generators `_build_bull_puts` (line 327) and `_build_bear_calls` (line 348) exist and work correctly.
- `app/api/analysis_routes.py` — backend schema default for `spread_types` is `["bull_call", "bear_put"]` but the endpoint accepts any of the four types and forwards to the engine.
- `web/src/strategy-configs/verticals.config.js` — `buildApiParams` correctly maps `spreadTypes` (camelCase object) → `spread_types` (snake_case array) and includes `bull_put` / `bear_call` when selected.
- `web/src/pages/TradesPage.jsx` — **`fetchVerticals` bypasses `buildApiParams` with inline fetch logic** that hardcodes `spread_types: ['bull_call', 'bear_put']` at line 841. The `...config` spread that was supposed to override this never lands because the config object uses `spreadTypes` (camelCase) while the API param is `spread_types` (snake_case). Three of the four call sites (lines 828, 916, 926) pass no config at all. Line 817 does pass config but the key mismatch makes it a no-op.
- `web/src/components/TradeTypeBadge.jsx`, `web/src/config/verticals-columns.jsx`, `TradesPage.inferStrategies` — display layer is fully correct; once credits reach the response, pills render correctly.

Result: credit spread types never appear in the API request, SP/WG never have trades to match, pills never render.

## The fix

Replace the inline `spread_types` handling in `fetchVerticals` with a call to `buildApiParams` from the active strategy config. Thread the config object through all four call sites so both ConfigDrawer changes and default strategy config flow correctly.

This is the architectural direction Phase 1 recommended — it eliminates the duplication between TradesPage's inline logic and the config plugin pattern, preventing future drift of the same class.

## Hard rules

1. **One file only.** All edits in `web/src/pages/TradesPage.jsx`. Do not touch `vertical_engine.py`, `analysis_routes.py`, `verticals.config.js`, or any backend or display file. Phase 1 confirmed those are correct.
2. **Make the change, then stop.** Do not deploy. Do not merge. Do not close the Jira ticket. Commit with the `OTA-451` prefix on a working branch and push. Manual verification happens after review.
3. **Read every file before editing.** Even small edits. If what you see differs from what Phase 1 reported, stop and report the discrepancy before editing.
4. **If `buildApiParams` doesn't return what fetchVerticals needs**, stop and report rather than adapting TradesPage to a shape you inferred. The contract matters.

## Setup

```bash
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
cat claude_context/CLAUDE.md
cat claude_context/UI-GUIDANCE.md | head -50
git status
git branch --show-current
```

Expected: clean working tree, on a feature branch (or main — confirm with user if on main).

---

## Phase A — Read the current code (no edits)

```bash
# Read the full buildApiParams contract
grep -n "buildApiParams\|spreadTypes\|spread_types" web/src/strategy-configs/verticals.config.js

# Read it in context
cat web/src/strategy-configs/verticals.config.js

# Read fetchVerticals and every call site
grep -n "fetchVerticals\|spread_types" web/src/pages/TradesPage.jsx

# Pull the full fetchVerticals function
sed -n '830,870p' web/src/pages/TradesPage.jsx

# Pull the four call sites with 10-line context each
sed -n '810,830p' web/src/pages/TradesPage.jsx   # line 817 area
sed -n '820,840p' web/src/pages/TradesPage.jsx   # line 828 area
sed -n '906,930p' web/src/pages/TradesPage.jsx   # lines 916, 926

# Confirm ConfigDrawer emits spreadTypes as object, not array
grep -rn "spreadTypes" web/src/components/ConfigDrawer* web/src/pages/TradesPage.jsx | head -20
```

**Stop and report before Phase B** with:

1. The exact `buildApiParams` signature and return shape from `verticals.config.js`
2. The exact `fetchVerticals` signature and how `config` is (or isn't) consumed
3. The shape of the `config` object at each of the four call sites (what's actually in it)
4. Whether `buildApiParams` needs any adaptation to be callable from `fetchVerticals`, or whether it drops in as-is

If any of these differ materially from what Phase 1 reported, surface that first and wait for direction before editing.

---

## Phase B — Implement the fix

Based on Phase A findings, make the edits. The intended shape is:

```javascript
// Before (simplified, at line ~840)
const fetchVerticals = async (symbol, config = {}) => {
  const body = {
    symbol,
    spread_types: ['bull_call', 'bear_put'],
    ...config
  };
  // ...fetch
};

// After
import { buildApiParams } from '@/strategy-configs/verticals.config';  // path from Phase A

const fetchVerticals = async (symbol, config) => {
  const apiParams = buildApiParams(config);  // handles spreadTypes → spread_types + all other param mapping
  const body = {
    symbol,
    ...apiParams
  };
  // ...fetch
};
```

Adapt the above to match what you actually observed in Phase A — this is a sketch, not a verbatim edit plan.

**Call sites to update** (lines 817, 828, 916, 926 per Phase 1; reconfirm line numbers in Phase A since the file may have shifted):

- Identify the active strategy config at each site. For sites that currently pass no config, pass the default config from `verticals.config.js` (or the currently selected strategy's config if ConfigDrawer state is available in scope — Phase A determines which).
- Every call site must end up threading a config through to `fetchVerticals`. No bare calls with undefined config.

**Do not** add a fallback that re-introduces the hardcoded `['bull_call', 'bear_put']`. If `config` is undefined at a call site, fix the call site — do not paper over it in `fetchVerticals`.

## Phase C — Verify

```bash
# Confirm no hardcoded spread_types remain in TradesPage
grep -n "spread_types\|'bull_call'\|'bear_put'\|'bull_put'\|'bear_call'" web/src/pages/TradesPage.jsx

# Expected: zero matches for spread_types literal array, zero matches for any individual hardcoded spread type string in this file. Any match is either (a) you missed a call site, or (b) unrelated code — inspect each and confirm.

# Confirm the import landed
grep -n "buildApiParams" web/src/pages/TradesPage.jsx

# Lint
cd web && npm run lint 2>&1 | tee /tmp/lint.log | tail -30

# Build (catches import path errors and type issues)
npm run build 2>&1 | tee /tmp/build.log | tail -40
cd ..
```

If lint or build fails, fix the error and re-run. Do not commit broken code.

## Phase D — Commit

```bash
git add web/src/pages/TradesPage.jsx
git diff --cached  # review the diff one more time

git commit -m "OTA-451 fix: route TradesPage verticals fetch through buildApiParams

Eliminates hardcoded spread_types: ['bull_call', 'bear_put'] and the
camelCase-vs-snake_case key mismatch in the ...config spread that
prevented credit spread types from reaching the API.

TradesPage.fetchVerticals now delegates to buildApiParams from
verticals.config.js, which correctly maps the spreadTypes config object
to the spread_types array including bull_put and bear_call when selected.

All four call sites updated to thread config consistently.

Root cause per Phase 1 diagnostic (04-24-2026): backend engine generators
and display layer were correct; only the frontend request payload was
missing credit types.

Validation pending — manual scan against OTA-149 baseline tickers to
confirm SP pills appear on 25-50 DTE credit spreads and WG pills on
5-16 DTE credit spreads."

git push
```

## Phase E — Stop

Report:

1. Commit SHA
2. Branch pushed to
3. List of call sites updated (line numbers pre- and post-edit)
4. Any surprises from Phase A that shaped the final edit
5. Any warnings from lint or build that you fixed along the way

**Do not** move OTA-451 in Jira. Do not deploy. Manual verification by Don first. Expected next step: Don runs a scan against AAPL / XOM / IWM / LLY / AVGO / META in the dev environment, confirms SP pills on 25-50 DTE credits and WG pills on 5-16 DTE credits, then advances the ticket.
