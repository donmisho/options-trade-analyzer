---
allowedTools:
  - Read
  - Grep
  - Glob
  - Edit
  - Write
  - Bash(cd:*)
  - Bash(./venv/Scripts/activate*)
  - Bash(.\\venv\\Scripts\\activate*)
  - Bash(curl.exe:*)
  - Bash(Invoke-RestMethod:*)
  - Bash(grep:*)
  - Bash(git:*)
  - Bash(npm:*)
---

# OTA-512 · T1 · Extend API client to forward `user_config` (backend side)

**Jira:** [OTA-512](https://tmtctech-team.atlassian.net/browse/OTA-512)
**Parent:** OTA-507 (Ongoing: Trade Evaluation Anomaly Resolution)
**Session role:** T1 runs FIRST. T1 establishes the contract that T2 consumes. Do not start T2 until T1 has completed Phase 4 and written the handoff doc.

---

## Starting context — ALWAYS

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\activate
cat CLAUDE.md
```

Report the CLAUDE.md hash or last-modified date so we know you read the current version.

---

## Phase 0 — Re-confirm the diagnostic trace (read-only)

Before any edits, verify the trace points from the diagnostic prompt still hold in the current tree. Do not edit anything in this phase.

```powershell
# Backend route accepts user_config
grep -n "user_config" app/analysis/analysis_routes.py

# Schema model + default
grep -rn "user_config" app/analysis/ --include="*.py"

# Scorer fallback behavior
grep -n "user_config\|STRATEGIES\[" app/analysis/strategy_scorer.py
```

Report:

1. Does `analysis_routes.py` still accept `req.user_config` and forward it to the scorer?
2. What is the schema default for `user_config`? (`None`, `{}`, something else?)
3. What is the **expected shape** of `user_config` when provided? Specifically:
   - Top-level key format: strategy id strings like `"weekly-grind"`?
   - Per-strategy value shape: which fields does `strategy_scorer.py` actually read? (`dte_min`, `dte_max`, anything else?)
4. What endpoint path does the scorecard call use? (needed for Phase 3 curl test)

**STOP after reporting.** Do not proceed to Phase 1 until I confirm the trace still holds.

---

## Phase 1 — Locate the API client

```powershell
grep -rn "getStrategyScorecard" web/src --include="*.js" --include="*.jsx" --include="*.ts" --include="*.tsx"
```

Read the function. Report:

1. Exact file path
2. Current signature
3. HTTP method + endpoint URL
4. How the request body is constructed today
5. Every call site (should be 2 per the diagnostic — confirm or correct)

**STOP and report.**

---

## Phase 2 — Extend the API client signature (one file change)

Extend `getStrategyScorecard` to accept an optional second argument `userConfig` and forward it to the backend as the `user_config` field in the request body.

**Strict rules:**

- Second arg is optional; default to `null` (or `undefined` — match the codebase convention).
- Only include `user_config` in the request body when `userConfig` is **truthy AND non-empty** (`Object.keys(userConfig).length > 0`). When omitted, do not send the key at all — this keeps the backend fallback path clean and distinguishes "no override" from "empty override".
- Do not change endpoint URL, method, headers, auth handling, response shape, or any error-handling path.
- Do not modify first-arg behavior. Existing single-arg call sites must continue to work unchanged.

After editing, show the diff:

```powershell
git diff -- web/src
```

Then run whatever frontend check the project uses:

```powershell
cd web
npm run lint
cd ..
```

**STOP.** Report the diff and lint output. Do not commit yet.

---

## Phase 3 — End-to-end backend verification (live curl)

Confirm the backend actually honors `user_config` with a live call. The backend should already be running — if not, ask Don to start it before proceeding.

Use `curl.exe` explicitly (NOT `curl` — that's a PowerShell alias for `Invoke-WebRequest` on Windows and the Unix-style flags will not work).

Fill in the correct endpoint path from Phase 0, and adjust the jq filter based on the actual response shape. The goal is: prove the backend changes its filtering behavior when `user_config` is supplied.

```powershell
# Baseline: no user_config — confirm default DTE behavior
curl.exe -X POST "http://localhost:8000/<ENDPOINT_FROM_PHASE_0>" `
  -H "Content-Type: application/json" `
  -d '{\"symbol\": \"AAPL\"}' | jq '.'

# Override: weekly-grind min bumped 5 → 10
curl.exe -X POST "http://localhost:8000/<ENDPOINT_FROM_PHASE_0>" `
  -H "Content-Type: application/json" `
  -d '{\"symbol\": \"AAPL\", \"user_config\": {\"weekly-grind\": {\"dte_min\": 10, \"dte_max\": 20}}}' | jq '.'
```

Report both responses. Confirm the weekly-grind candidate set (or DTE filter window shown in the response) changed between the two calls.

**If the backend does NOT behave as the diagnostic claims, STOP and report.** Do not try to "fix" the backend — that would expand scope and this Story is frontend-only.

---

## Phase 4 — Write the handoff contract for T2

Create `docs/handoff/OTA-512-contract.md` with exactly these sections, populated from what you discovered above:

```markdown
# OTA-512 API contract (T1 → T2 handoff)

## localStorage read target (for T2 to consume)
- Top-level key: <observed in ConfigDrawer.jsx / StrategyPage.jsx — confirm actual key name>
- Nested path to overrides: <e.g., parsed JSON then `.strategyOverrides`>
- Storage format: JSON string
- Written by: ConfigDrawer.jsx line 232-235, StrategyPage.jsx line 441-444

## API client signature (confirmed in Phase 2)
- File: <path>
- New signature: `getStrategyScorecard(sym, userConfig = null)`
- Request body when userConfig is truthy and non-empty: `{ symbol, user_config: <object> }`
- Request body when userConfig is null/undefined/empty: `{ symbol }` (no user_config key)

## user_config shape expected by backend (confirmed in Phase 0 + Phase 3)
- Top-level keys: <list actual strategy ids>
- Per-strategy value shape: <list every field the scorer reads>

## Transform from localStorage → user_config
- If shapes match: identity pass-through, no transform needed.
- If shapes differ: <describe exact mapping needed — field renames, nesting, etc.>

## T2 responsibilities
- Read localStorage at scan time (not mount time).
- Apply transform (if any).
- Pass result as second arg to `getStrategyScorecard`.
- Do NOT modify the API client. T1 owns it.

## Verified curl commands (Phase 3 reference)
<paste the two curl commands from Phase 3 so T2 can reproduce if needed>
```

Show the file contents.

---

## Phase 5 — Commit

One commit. Subject line exactly:

```
OTA-512 feat: extend getStrategyScorecard to forward user_config
```

Body:

```
Adds optional second argument userConfig. When truthy and non-empty,
forwarded to the backend as user_config in the request body. When
omitted/null/empty, the user_config key is not included — backend falls
back to STRATEGIES dict defaults exactly as before.

Existing single-arg call sites remain behaviorally identical. Backend
pathway already wired (analysis_routes.py, strategy_scorer.py fallback
at lines 132/136/282/286). Live curl verification confirmed backend
honors user_config when provided.

T1 of OTA-512. T2 (page wiring) consumes docs/handoff/OTA-512-contract.md.
```

Push. Report the commit SHA.

---

## Out of scope for T1 (and for OTA-512 generally)

- Page component changes (T2 owns SecurityStrategiesPage.jsx)
- Dict consolidation → OTA-513
- Persistence model decision → OTA-514
- Slider default reconciliation → OTA-513
- Any backend code changes — already wired

## Guardrails

- One file touched per commit in Phase 5 (plus the handoff doc).
- Read before edit, every time.
- If anything in Phase 0 or Phase 3 contradicts the diagnostic, STOP and report. Do not silently adapt.
- If the response shape in Phase 3 doesn't obviously show the override taking effect, STOP — the diagnostic's assumption that the backend path is fully wired may be wrong, which would change the whole shape of OTA-512.
