# OTA-756 — Retire directional_engine.py

## Terminal context
- **This terminal:** single terminal — `app/analysis/` package cleanup (no seed, no config, no route changes).
- **Concurrent terminals:** none.
- **Cross-terminal dependencies:** runs **after OTA-765** (wire directional comparison through the engine) — committed and pushed, currently Code & Test Complete. OTA-765 removed the route's evaluation caller; the only references left to retire are the passive re-export and the module file itself. If Phase 0 finds any *live* caller still importing from `directional_engine`, that is a NO-GO — OTA-765 did not fully clear callers and this prompt stops.

---

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/insight_engine.md          # generic engine package — the replacement for the retired directional engine
```

Then, before editing, `cat` the actual current contents of the two files this prompt touches:

```
cat app/analysis/__init__.py
cat app/analysis/directional_engine.py
```

---

## Relevant Context — Do Not Deviate Without Escalation

**Source: OTA-756 body (acceptance) + OTA-765 (the route-wiring story that unblocks this)**
- OTA-765 rewired the directional-comparison route to call `engine.evaluate(..., adapter=directional, source_app_id="OTA")` across all three directional strategies. No route, service, or test should still import the legacy `directional_engine` evaluation path.
- The internal `_fitness_score` sort key lived only inside `directional_engine.py` and was never emitted in the response (confirmed by OTA-765's rescope). It dies with this file — nothing reads it.

**Source: OTA-756 body (acceptance grep)**
- Definition of done is a clean grep: `directional_engine` returns **zero hits** under `app/` and `tests/`, with the sole permitted exceptions being references to the *new* generic engine package (e.g. `app/insight_engine/`), which are unrelated string matches, not the retired module.

**Source: architecture-plan.md (engine package structure) + insight_engine.md**
- The directional surface is now served by the generic Insight Engine package, not by `app/analysis/directional_engine.py`. Removing the legacy module must not touch any symbol the generic engine package exports.

---

## Scope

### Phase 0 — read-only discovery (hard STOP for GO/NO-GO; no edits)

1. Run the caller census across the whole backend and test tree:
   ```powershell
   Select-String -Path app\*.py,app\**\*.py,tests\*.py,tests\**\*.py -Pattern "directional_engine" |
     Select-Object Path, LineNumber, Line
   ```
2. Classify every hit into exactly one bucket:
   - **(A) The module file itself** — `app/analysis/directional_engine.py`.
   - **(B) The passive re-export** — the `import`/`from` line and the `__all__` entry in `app/analysis/__init__.py` (expected ~L22–23 for the import, ~L37 for the `__all__` membership; confirm actual line numbers from the live file).
   - **(C) Any live caller** — a route, service, adapter, or test that imports or invokes a `directional_engine` symbol.
3. Report the full classified list as `file:line → bucket`.
4. **GO/NO-GO:**
   - **GO** only if every hit is bucket (A) or (B) — i.e. the re-export and the file are the *only* remaining references.
   - **NO-GO** (STOP, report, do not edit) if any bucket (C) live caller remains. That means OTA-765 left a caller behind; surface it for Don rather than deleting a file something still imports.

**Hard STOP here.** Do not proceed to implementation until Don gives GO.

### Implementation — after Don's GO

1. In `app/analysis/__init__.py`: remove the `directional_engine` re-export — both the `import`/`from … import` line and the corresponding `__all__` entry. Leave every other export untouched.
2. Delete `app/analysis/directional_engine.py`.
3. Do **not** touch routes, the directional adapter, the engine package, seed scripts, or any config. This is a deletion-only story.

---

## Acceptance criteria

- `Select-String -Path app\**\*.py -Pattern "directional_engine"` returns **zero hits** other than incidental matches inside the generic engine package (none expected).
- `Select-String -Path tests\**\*.py -Pattern "directional_engine"` returns zero hits.
- `app/analysis/__init__.py` no longer imports or re-exports any `directional_engine` symbol, and its `__all__` no longer lists one.
- `app/analysis/directional_engine.py` no longer exists.
- The app boots clean and the directional-comparison route responds without an import error (it now resolves through `engine.evaluate` per OTA-765).
- No `if strategy_key ==` / structure branching introduced (none should be — this is a deletion).

---

## Out of scope

- Any route, adapter, engine, or scoring change — OTA-765 owns the wiring; this prompt only removes the dead module.
- Any seed / config / reseed work.
- Any Jira status transition — Don gates those.
- Renaming or restructuring the `app/analysis/` package beyond removing the single re-export.

---

## Verification steps

Run from the project root, venv active:

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1

# 1. Grep must come back clean (engine-package incidental matches only)
Select-String -Path app\*.py,app\**\*.py -Pattern "directional_engine"
Select-String -Path tests\*.py,tests\**\*.py -Pattern "directional_engine"

# 2. Import smoke — the package still imports with the re-export gone
python -c "import app.analysis; print('app.analysis OK')"

# 3. Boot smoke — app comes up, directional route resolves via the engine
#    (start the API, hit the directional-comparison endpoint, confirm 200 / no ImportError)
```

Report grep output, the import smoke result, and the boot/route smoke result before requesting the commit gate.

---

## Commit instruction

"I have been instructed to commit. Do you approve? (yes / no)"

(Don commits manually. Do not run `git commit` until Don answers yes.)

---

## Coordination footer

Independent — no downstream dependency. (This is the tail of the directional retirement; nothing waits on it.)

---

## Commit message template (if committing)

```
OTA-756 chore: retire directional_engine.py; remove passive re-export from app/analysis/__init__.py
```
