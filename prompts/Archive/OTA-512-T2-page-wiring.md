---
allowedTools:
  - Read
  - Grep
  - Glob
  - Edit
  - Bash(cd:*)
  - Bash(./venv/Scripts/activate*)
  - Bash(.\\venv\\Scripts\\activate*)
  - Bash(grep:*)
  - Bash(git:*)
  - Bash(npm:*)
---

# OTA-512 · T2 · Wire localStorage reads into SecurityStrategiesPage

**Jira:** [OTA-512](https://tmtctech-team.atlassian.net/browse/OTA-512)
**Parent:** OTA-507
**Session role:** T2 runs AFTER T1 has pushed its commit and written `docs/handoff/OTA-512-contract.md`. If that file doesn't exist yet, STOP — T1 hasn't finished.

---

## Starting context — ALWAYS

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\activate
cat CLAUDE.md
cat docs/handoff/OTA-512-contract.md
```

If the handoff doc is missing: STOP. Tell me T1 hasn't finished. Do not attempt to reconstruct the contract from memory.

---

## Phase 0 — Read the contract and confirm you understand it

Report back in your own words:

1. What localStorage key holds the strategy overrides?
2. What path within that key (if nested) reaches `strategyOverrides`?
3. What shape does the backend expect in `user_config`?
4. Does the localStorage shape match the `user_config` shape, or is a transform required?
5. Where does the API client live, and what is its new signature?

**STOP and report.**

---

## Phase 1 — Independently verify the localStorage write path

Don't blindly trust T1's contract doc — T1 may have guessed at one field. Confirm by reading the actual write sites:

```powershell
grep -n "strategyOverrides\|analysisConfig" web/src/ConfigDrawer.jsx
grep -n "strategyOverrides\|analysisConfig" web/src/StrategyPage.jsx
grep -rn "localStorage" web/src/SecurityStrategiesPage.jsx
```

Open each file and report:

1. Actual localStorage key being written
2. Actual shape being written (paste a small example if the code constructs one inline)
3. Whether the write is JSON-stringified
4. Whether the contract doc's description matches reality

**If the contract doc's shape doesn't match what's actually written, STOP and flag it — don't silently transform to paper over the disagreement.** That's a signal T1's Phase 0 discovery was incomplete, and I want to see it before we build on a wrong foundation.

---

## Phase 2 — Add a scan-time localStorage read helper

In `web/src/SecurityStrategiesPage.jsx` (or a small adjacent utility file if the project has a `utils/` pattern), add a helper that reads the strategy overrides from localStorage at scan time.

**Rules:**

- Helper is a small pure function. No React hooks.
- Called at scan-time, not at component-mount-time. The user may change config between mount and scan — we want the latest.
- Safe parsing:
  - If localStorage key is missing → return `null`
  - If `JSON.parse` throws → `console.warn` a descriptive message and return `null`
  - If parse succeeds but the overrides path is empty/missing → return `null`
- Returning `null` must cause the API client to omit `user_config` (T1 guaranteed this). So "no overrides" → "backend defaults" end-to-end.
- If the contract doc specifies a transform, apply it inside this helper. Keep the transform pure — no side effects, no logging beyond the one warn-on-parse-error line.

Make only this one change. No other edits.

Show the diff:

```powershell
git diff -- web/src/SecurityStrategiesPage.jsx
```

(and the utility file if you created one)

**STOP and report.**

---

## Phase 3 — Wire the helper into both call sites

The diagnostic identified two call sites:

- `SecurityStrategiesPage.jsx:161`
- `SecurityStrategiesPage.jsx:251`

Line numbers may have shifted slightly. Confirm with:

```powershell
grep -n "getStrategyScorecard" web/src/SecurityStrategiesPage.jsx
```

At each call site, pass the helper's return value as the second argument:

```js
getStrategyScorecard(sym, readStrategyOverrides())
```

(or whatever the helper is called).

One pattern for both sites. Don't introduce case-by-case variance.

Show the diff:

```powershell
git diff -- web/src/SecurityStrategiesPage.jsx
```

Run lint:

```powershell
cd web
npm run lint
cd ..
```

**STOP and report.**

---

## Phase 4 — Manual end-to-end verification (ACCEPTANCE CRITERIA)

This is the payoff. We're verifying every item in OTA-512's acceptance criteria. Manual, in browser, backend + frontend both running.

### 4.1 — Weekly-grind override respected

1. Clear localStorage to start clean: in DevTools console, `localStorage.clear()` → reload
2. Navigate to Strategies screen
3. Change weekly-grind `dte_min` from 5 to 10 → click Apply
4. Navigate to scan, run against AAPL
5. Open DevTools → Network → click the scorecard request → Payload tab
6. **Confirm:** payload includes `user_config: { "weekly-grind": { "dte_min": 10, ... } }` (exact shape per contract)
7. **Confirm:** no weekly-grind candidate in the results has DTE < 10

Copy-paste the payload JSON into the report.

### 4.2 — Reset returns to defaults

1. `localStorage.clear()` in console → reload
2. Run scan against AAPL
3. **Confirm:** Network → scorecard payload does NOT contain a `user_config` key (backend falls back to STRATEGIES dict)
4. **Confirm:** weekly-grind candidates now include some with DTE 5-9 (baseline behavior restored)

### 4.3 — All four strategies respect overrides

One by one, change a DTE value for each remaining strategy, rerun, confirm scan respects it:

- steady-paycheck
- trend-rider
- lottery-ticket

One-liner confirmation per strategy is fine (no need for full payload screenshot each time — just confirm the filter worked).

### 4.4 — No regression in default behavior

Clear localStorage one more time. Run scan. Compare against a known baseline (ask Don for the AMZN or AAPL fixture if there's one handy, otherwise confirm subjectively that results look normal).

**Report every check above. If any fail, STOP and report before Phase 5.**

---

## Phase 5 — Commit

One commit. Subject exactly:

```
OTA-512 feat: read strategyOverrides at scan time and forward to scorer
```

Body:

```
SecurityStrategiesPage now reads the strategy overrides from localStorage
at scan initiation and passes them as the second argument to
getStrategyScorecard (wired in the prior T1 commit).

When overrides are absent, the helper returns null and the API client
omits user_config — backend falls back to STRATEGIES dict defaults,
exactly matching prior behavior.

Verified end-to-end:
- weekly-grind dte_min 5→10 respected, candidates with DTE < 10 filtered
- localStorage.clear() reverts to default STRATEGIES behavior
- All four strategies (steady-paycheck, weekly-grind, trend-rider,
  lottery-ticket) respect localStorage overrides

Closes OTA-512.
```

Push. Report the commit SHA.

---

## Out of scope

- API client changes → owned by T1, already shipped
- Backend changes → already wired, no-op for this Story
- Dict consolidation → OTA-513
- Slider default reconciliation → OTA-513
- Persistence model decision → OTA-514

## Guardrails

- Do not edit the API client. T1 owns it. If you think it needs changing, STOP and report.
- If the localStorage shape doesn't match the contract doc, STOP — don't silently paper over a disagreement.
- Read before edit.
- Stop between phases and report. This is a small change, but the verification is what earns the ticket's close.
