---
allowedTools: ["Bash", "Read", "Write", "Edit"]
---

# OTA-545 — Python Modernization

**Wave:** 1 (T3)
**Parent:** OTA-535 (Architecture Optimization Framework v1)
**Sequence label:** `05012026-6`
**Tier:** 2 (interleave)

Two independent hygiene items bundled in one Story. Phase 1 (datetime) is pure refactor with no infra impact. Phase 2 (ODBC installer) touches deployment configuration — proceed only after Phase 1 is committed and verified.

---

## Required reading

```bash
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
```

Then targeted source reads (Phase 2 only):

```bash
cat app/main.py
ls .github/workflows/         # current deploy workflow
```

---

## Relevant Context — Do Not Deviate Without Escalation

**Source: architecture-plan.md Cleanup Roadmap → Should Fix**
- Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` — Python 3.12+ deprecates `utcnow()`
- Remove ODBC installer from `main.py` startup — OS-level package install belongs in deployment config, not app code

**Source: GPT-5.4 architecture review § 1**
Both items flagged. Neither is functional; both are hygiene that prevents future warnings and isolates OS concerns from app code. The ODBC installer in `main.py` slows cold start measurably.

**Source: claude_context/CLAUDE.md**
Rule: Async credentials throughout (`azure.identity.aio`). This Story does not touch credentials, but if the ODBC install logic surfaces credential-related calls during relocation, preserve async patterns.

**Source: OTA-526 retro / OTA-527 (in flight)**
Rule: Claude Code commits + pushes + verifies the build run. Don owns deploy.

---

## Phase 1 — datetime modernization

### Step 1.1 — Find every call site

```bash
grep -rn "datetime\.utcnow" app/ --include="*.py"
grep -rn "datetime\.utcnow" tests/ --include="*.py" 2>/dev/null || true
```

Report the full list to Don before changing anything. Include count and per-file breakdown.

**STOP. Wait for "proceed."**

---

### Step 1.2 — Replace each call site

Replace pattern:
```python
from datetime import datetime
# ...
datetime.utcnow()
```

With:
```python
from datetime import datetime, timezone
# ...
datetime.now(timezone.utc)
```

Notes:
- If `timezone` is already imported in the file, do not add a duplicate import
- If a file uses `from datetime import datetime` only, extend to `from datetime import datetime, timezone`
- If a file uses `import datetime` (full module), use `datetime.datetime.now(datetime.timezone.utc)` — match the file's existing style
- Do NOT change the variable name or the assignment target — minimize the diff

Special case: any place that does math like `datetime.utcnow() - some_aware_datetime` will already be working only because `utcnow()` returns naive UTC and the comparison is happening to fail silently or be wrong. After the modernization, both sides become aware, which is the correct behavior. Flag any such site in your report; do not "fix" it beyond the swap unless Don approves additional scope.

---

### Step 1.3 — Run the test suite

```bash
cd <repo root>
source venv/Scripts/activate     # Windows; use venv/bin/activate elsewhere
pytest -x --tb=short
```

If any test fails, report which test, the failure, and your hypothesis. Do NOT fix test failures without Don's input — datetime semantics changes can mask real bugs.

**STOP. Confirm green with Don.**

---

### Step 1.4 — Commit Phase 1 only

```bash
git add app/ tests/
git commit -m "OTA-545 refactor: replace datetime.utcnow() with datetime.now(timezone.utc)

Python 3.12+ deprecates datetime.utcnow(). Replaced N call sites across
M files with timezone-aware equivalent. No behavioral change.

Part 1 of 2 for OTA-545."

git push origin main
```

Verify the build run, report status, then move to Phase 2.

---

## Phase 2 — ODBC installer relocation

### Step 2.1 — Locate the install logic in main.py

```bash
grep -n "ODBC\|odbc\|msodbcsql\|apt-get install\|pip install" app/main.py
```

Read the surrounding lifespan / startup function. Identify exactly which lines are responsible for OS-level package install vs. application initialization.

Report findings to Don.

**STOP.**

---

### Step 2.2 — Create startup.sh in repo root

Move the ODBC install logic to `startup.sh`. Template:

```bash
#!/bin/bash
set -e

echo "[startup.sh] Installing Microsoft ODBC Driver for SQL Server..."

# <move the existing logic here, preserving any version pinning, package source URLs, and platform checks>

echo "[startup.sh] ODBC install complete. Starting application..."

exec gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:${PORT:-8000} --timeout 120
```

Important:
- Preserve any version pinning the existing code does
- Preserve any platform / architecture checks
- The final `exec` line must match how the app currently starts on App Service — confirm against the current Startup Command before writing

```bash
chmod +x startup.sh
```

---

### Step 2.3 — Remove the install block from app/main.py

Edit `app/main.py`:
- Remove the OS-level install logic from the lifespan / startup function
- Leave a comment indicating the work moved to `startup.sh`:
  ```python
  # ODBC driver install moved to repo-root startup.sh (OTA-545).
  # App Service Configuration > General Settings > Startup Command must reference startup.sh.
  ```
- Confirm that `app/main.py`'s lifespan only does application-level initialization now (DB engine, scheduler, AI adapter, etc.)

**Show diff. STOP.**

---

### Step 2.4 — Document the App Service startup command requirement

Update `claude_context/architecture-plan.md` § 7 (Deployment Architecture). Add a subsection:

```markdown
### App Service Startup Command

The App Service is configured with `Startup Command: bash startup.sh` (Configuration > General Settings).

`startup.sh` performs OS-level setup (Microsoft ODBC Driver install) before invoking the gunicorn/uvicorn worker that launches the FastAPI app. Keeping OS install out of `app/main.py` lifespan eliminates cold-start coupling between app code and platform package management.

**Long-term direction:** A custom container image with ODBC pre-installed eliminates `startup.sh` entirely. Tracked as a follow-up in OTA-547 (Polish & Future-Proofing) backlog if `startup.sh` proves fragile.
```

**Show diff. STOP.**

---

### Step 2.5 — Verify the App Service Configuration manually

Don needs to do this in the Azure portal — Claude Code cannot change App Service configuration. The verification checklist (write to `/tmp/OTA-545-phase2-handoff.md`):

```markdown
# OTA-545 Phase 2 — Manual Verification Required

After this commit lands and before deploy:

1. Azure Portal → App Service → Configuration → General Settings
2. Set `Startup Command` to: `bash startup.sh`
3. Save and confirm the App Service restarts cleanly
4. Tail the App Service log stream during restart — confirm:
   - "[startup.sh] Installing Microsoft ODBC Driver..." appears
   - ODBC install completes without errors
   - "[startup.sh] ODBC install complete. Starting application..." appears
   - The gunicorn workers start
   - The app health check (/api/v1/health) returns 200
5. Measure cold-start time before vs after — note in this file:
   - Before: <seconds>
   - After: <seconds>
   - Delta: <seconds>

If any of the above fails, the rollback is: revert the Startup Command to its previous value and the previous code path resumes (since the install logic still exists in this commit's parent).
```

---

### Step 2.6 — Commit Phase 2

```bash
git add startup.sh app/main.py claude_context/architecture-plan.md
git commit -m "OTA-545 refactor: move ODBC installer from main.py lifespan to startup.sh

OS-level package install no longer runs inside the FastAPI lifespan.
startup.sh handles ODBC driver install before invoking the gunicorn
worker. App Service Startup Command must be set to 'bash startup.sh'
(see /tmp/OTA-545-phase2-handoff.md for the manual portal step).

architecture-plan.md § 7 updated with the new startup pattern.

Part 2 of 2 for OTA-545. Closes OTA-545."

git push origin main
```

Verify the build run.

---

## Final handback

Report back with:

```
Branch: main
Commits:
  - <sha1> OTA-545 datetime modernization
  - <sha2> OTA-545 ODBC installer to startup.sh
Push: confirmed pushed to origin/main at <time>
Build: GitHub Actions run <run-id> — <status>
Build artifact: <artifact-name> (<size>)

Manual verification handoff: /tmp/OTA-545-phase2-handoff.md
- Don must set App Service Startup Command to 'bash startup.sh' before deploying

Ready for user to deploy via deploy-to-dev.yml after the manual portal step.
```

**STOP. Do NOT trigger any deploy workflow.**

---

## Acceptance criteria

- [ ] `grep -r "datetime\.utcnow" app/` returns no results
- [ ] All tests pass after datetime migration
- [ ] `startup.sh` exists in repo root and is executable (`chmod +x`)
- [ ] `app/main.py` lifespan does not invoke ODBC installer
- [ ] `claude_context/architecture-plan.md` § 7 documents the App Service Startup Command pattern
- [ ] Manual handoff file at `/tmp/OTA-545-phase2-handoff.md` for Don's portal step

## Out of scope

- Custom container image with ODBC pre-installed (deferred to OTA-547 if `startup.sh` proves insufficient)
- Other Python 3.12+ deprecation cleanups beyond `datetime.utcnow` (separate cleanup if any are flagged)
- Triggering any deploy workflow (Don's job)
