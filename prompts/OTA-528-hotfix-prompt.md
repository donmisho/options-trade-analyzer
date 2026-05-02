---
allowedTools: Bash, Read, Write, Edit
ticket: OTA-528
type: hot-fix
scope: web/src/context/AppContext.jsx
estimated_lines: ~10–15
risk: low
---

# OTA-528 — Hot Fix: Eliminate Quote Fan-Out Loop in AppContext

## Context

Production is currently storming the backend with N+1 quote requests (one per symbol the user has ever searched) on every watchlist mutation. Root cause is a `useCallback` / `useEffect` identity loop in `web/src/context/AppContext.jsx`, amplified by OTA-419's auto-add-on-search behavior. The Central US SQL migration removed the cross-region latency that had been masking the bug; in-region, all N requests now arrive simultaneously and produce 502s.

QA-UX Level 2 regression confirmed this in `C:\Temp\OTA-528-regression-2026-04-30-1530.md`. All 7 underlying watchlist tickets (OTA-419/423/425/443/444/445/446) PASS their ACs. The defect is purely in `AppContext.jsx`.

## What you are doing

A surgical patch to `web/src/context/AppContext.jsx` only. No backend changes. No other frontend files. No new dependencies.

After the patch, watchlist mutations (add, remove, reorder) MUST NOT trigger a refetch of all N watchlist symbols. Initial price load happens exactly once per session, after the watchlist resolves from `getWatchlist()`. Per-symbol incremental fetches (when a new symbol is added) continue to work as today.

## Step 0 — Orient

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
cat CLAUDE.md
```

Then read the relevant slices only:

```powershell
Get-Content web/src/context/AppContext.jsx
Get-Content web/src/api/client.js | Select-String -Pattern "getQuote|getQuotes|getWatchlist" -Context 2,2
```

Confirm the current shape matches what QA-UX described:

- `fetchPrices` is a `useCallback` with `[watchlist]` (or similar) in its dep array
- A `useEffect` exists with `[fetchPrices]` as its dep
- `getQuotes(symbols)` in `client.js` is a `Promise.all` of individual `getQuote(sym)` calls (NOT a batch endpoint)
- `getWatchlist()` returns the symbol list and is called inside a mount-only `useEffect`

If the file shape differs materially from this, **STOP and report back what you actually see** — do not improvise. The patch shape below assumes the QA-UX description is accurate.

## Step 1 — Patch

Apply these three changes to `web/src/context/AppContext.jsx`:

### Change A — `fetchPrices` becomes a stable, parameterized function

The current pattern (paraphrased):
```javascript
const fetchPrices = useCallback(async () => {
  const symbols = watchlist.map(w => w.symbol);
  if (symbols.length === 0) return;
  const data = await getQuotes(symbols);
  setPrices(prev => ({ ...prev, ...data }));
}, [watchlist]);
```

Replace with:
```javascript
const fetchPrices = useCallback(async (symbols) => {
  if (!symbols || symbols.length === 0) return;
  try {
    const data = await getQuotes(symbols);
    setPrices(prev => ({ ...prev, ...data }));
  } catch (err) {
    console.error('[AppContext] fetchPrices failed:', err);
  }
}, []);
```

Key properties:
- Empty dep array → stable identity for the lifetime of the provider
- Accepts an explicit `symbols` array → no closure over `watchlist`
- Wrapped in try/catch (mirror the existing error handling pattern from the original; if there was none, add the try/catch as shown — do not let a quote failure unmount the provider)

### Change B — Remove the auto-firing useEffect

Delete this block entirely (location: roughly lines 247–249 per QA-UX):
```javascript
useEffect(() => {
  fetchPrices();
}, [fetchPrices]);
```

This is the loop. It must go.

### Change C — Move initial price load into the watchlist load chain

Locate the mount-only `useEffect` that calls `getWatchlist()` (roughly lines 153–166 per QA-UX). Modify it so `fetchPrices(symbols)` is called explicitly once the watchlist resolves, in BOTH the success and the error paths:

```javascript
useEffect(() => {
  getWatchlist()
    .then(data => {
      const symbols = data?.symbols ?? (Array.isArray(data) ? data : []);
      const items = symbols.length > 0
        ? symbols.map(s => ({ symbol: s, name: SYMBOL_NAMES[s] || '' }))
        : STARTER_WATCHLIST;
      setWatchlist(items);
      fetchPrices(items.map(w => w.symbol));
    })
    .catch(err => {
      console.error('[AppContext] getWatchlist failed, using starter:', err);
      setWatchlist(STARTER_WATCHLIST);
      fetchPrices(STARTER_WATCHLIST.map(w => w.symbol));
    });
}, []); // eslint-disable-line react-hooks/exhaustive-deps
```

The `eslint-disable-line` is intentional and correct — this effect is designed to fire exactly once on mount. Document with a comment if the file convention is to comment over disabling.

### Step 1.5 — Audit other call sites of `fetchPrices`

```powershell
Select-String -Path "web/src/**/*.jsx","web/src/**/*.js" -Pattern "fetchPrices" -Context 2,2
```

Expected call sites after the patch:
- `addToWatchlist` — should already call `getQuotes([sym])` for the newly added symbol; if it instead calls `fetchPrices()`, change it to `fetchPrices([sym])`
- The mount effect from Change C
- `removeFromWatchlist` — should NOT call `fetchPrices` (removing a symbol doesn't need new prices); if it does, remove that call

If `fetchPrices` is called anywhere else (e.g. a manual refresh button), update those call sites to pass an explicit `symbols` array. If you find a call site that needs all current watchlist symbols, use `watchlist.map(w => w.symbol)` at the call site (NOT inside `fetchPrices` — keep that function pure of `watchlist` closure).

Report each call site you find and what you did with it.

## Step 2 — Verify locally

### 2a. Lint and build

```powershell
cd web
npm run lint
npm run build
cd ..
```

Both must pass with zero new warnings related to the changed file. Existing pre-fix warnings in unrelated files are acceptable; flag them but do not fix them in this patch.

### 2b. Manual sanity (optional, only if backend is already running locally)

If a local backend is already running on `https://127.0.0.1:8000` AND a Vite dev server is already running, do a quick console check. **Do NOT start servers as part of this prompt** — Don controls dev environment startup.

If servers are NOT already running, skip 2b entirely and rely on the dev deploy verification (Step 5 below).

## Step 3 — Cleanup audit

Per `OTA-528-regression-2026-04-30-1530.md` minor finding:

```powershell
Get-Content web/src/context/AppContext.jsx | Select-String -Pattern "localStorage" -Context 1,1
```

Lines around 10–13 contain a stale comment referencing watchlist localStorage. Update the comment so it no longer claims watchlist uses localStorage. Keep the favorites reference (favorites still use localStorage). One-line text change only — no logic.

## Step 4 — Commit

Single commit. Do not split.

```powershell
git status
git diff web/src/context/AppContext.jsx
git add web/src/context/AppContext.jsx
git commit -m "OTA-528: Eliminate quote fan-out loop in AppContext

Root cause: fetchPrices useCallback had [watchlist] dependency,
causing useEffect([fetchPrices]) to re-fire on every watchlist
mutation. With OTA-419 auto-add and accumulated lifetime watchlist,
each symbol search triggered N+1 individual quote requests. SQL
migration to Central US removed cross-region latency that had been
masking the storm.

Fix: fetchPrices is now stable (empty deps) and parameterized.
Initial load fires once from the watchlist load chain. Per-symbol
adds continue to fetch only the new symbol.

Findings: C:\\Temp\\OTA-528-regression-2026-04-30-1530.md"
```

## Step 5 — Push and verify build

```powershell
git push origin main
```

Then verify the build workflow succeeded:

```powershell
gh run list --workflow=build-on-push.yml --limit 3
```

Wait for the most recent run to show `completed success`. If it fails:
- Capture the failure logs: `gh run view --log-failed`
- Report the failure summary back to Don
- Do NOT attempt a follow-up patch in the same session — surface the failure and wait

If the build succeeds, report:
- The commit SHA
- The build run ID and URL
- Confirmation that you have STOPPED at the deploy boundary

**Do NOT trigger any deploy workflow.** Don owns the deploy step via the GitHub Actions UI.

## Acceptance criteria

| AC | How to verify |
|---|---|
| `fetchPrices` has empty dep array (`[]`) | Read modified `AppContext.jsx`, confirm `useCallback(async (symbols) => {...}, [])` |
| `fetchPrices` accepts explicit `symbols` parameter, does not close over `watchlist` | Read function signature; grep the function body for `watchlist` references — there should be none |
| The `useEffect(() => { fetchPrices(); }, [fetchPrices])` block is removed | `Select-String -Pattern "fetchPrices" web/src/context/AppContext.jsx` shows no useEffect dep on `fetchPrices` |
| Mount effect calls `fetchPrices(symbols)` in both success and error branches | Read modified mount effect |
| `addToWatchlist` calls `fetchPrices([sym])` (or `getQuotes([sym])` directly) for the new symbol only | Read modified `addToWatchlist` |
| `removeFromWatchlist` does NOT call `fetchPrices` | Read modified `removeFromWatchlist` |
| Stale watchlist localStorage comment removed at lines ~10–13 | Read updated comment |
| `npm run lint` passes (no new warnings in `AppContext.jsx`) | Lint output |
| `npm run build` passes | Build output |
| Single commit with `OTA-528:` prefix | `git log --oneline -1` |
| `build-on-push.yml` succeeds | `gh run list` |

## Hard boundaries

- Do NOT modify any file other than `web/src/context/AppContext.jsx`
- Do NOT add a batch quotes endpoint — that's a separate Story
- Do NOT touch backend code
- Do NOT trigger any deploy workflow
- Do NOT start or stop dev servers
- Do NOT remove unrelated lint warnings
- Do NOT update Jira from this session — Don will paste the comment manually after he verifies on dev
- If anything in the actual file structure contradicts this prompt, STOP and report
