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
  - Bash(ls:*)
  - Bash(cat:*)
  - Bash(grep:*)
  - Bash(rm:*)
  - Bash(git:*)
  - Bash(python:*)
  - Bash(az:*)
---

# OTA-524 · Tradier deprecation cleanup

**Jira:** [OTA-524](https://tmtctech-team.atlassian.net/browse/OTA-524)
**Parent Epic:** OTA-236 (Development Workflow)
**Origin:** Surfaced during OTA-519. App Service settings already cleaned (TRADIER_API_KEY and TRADIER_ENVIRONMENT deleted from prod). This Story removes the codebase residue.

---

## Starting context — ALWAYS

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\activate
cat CLAUDE.md
```

Report the CLAUDE.md last-modified date.

---

## Phase 0 — Discovery (read-only)

Before any edits, confirm the file/line targets are still where the Jira description says they are. Codebases drift; line numbers in particular shift over time.

### 0.1 Verify Tradier files and references exist where expected

```powershell
ls app/providers/tradier.py
grep -n "tradier" app/providers/factory.py
grep -n "tradier" app/api/service_routes.py
grep -n "tradier" app/core/config.py
grep -n "tradier" app/models/database.py
grep -n "tradier" app/models/schemas.py
grep -n "tradier\|TRADIER\|CORS_ORIGINS" .env.example
```

Report each result. Flag any of these:

- `app/providers/tradier.py` doesn't exist → already partially cleaned, adjust scope
- Line numbers don't match the Jira description → use the actual locations from this discovery
- Tradier references appear in files NOT listed in the Jira description → flag and stop. Don may need to expand scope

### 0.2 Full-codebase Tradier audit

```powershell
grep -rin "tradier" app/ --include="*.py"
grep -rin "tradier" web/src --include="*.js" --include="*.jsx" --include="*.ts" --include="*.tsx"
```

Report every hit. Categorize each as:

- **Will be removed** (in the explicit change list below)
- **Whitelisted** (Schwab adapter docstrings, route comments, secrets.py docstring — per Jira guardrails)
- **Surprise** (anything not yet categorized) — STOP and report before continuing

Frontend is unlikely to have hits. If it does, that's worth knowing before this Story closes — the user-facing strings need different treatment than backend cleanup.

### 0.3 Pre-flight database check

This is the most important step in Phase 0. The change in Phase 5 flips the `market_data_provider` column default from `"tradier"` to `"schwab"`. Existing rows with `"tradier"` continue to exist at the DB level but will fail at runtime when the factory tries to resolve the provider name.

We need to know if any user rows have `"tradier"` set BEFORE we ship the change.

The connection string lives in Key Vault. Use Azure CLI to fetch it, then run a SELECT.

```powershell
# Fetch the SQL connection string from Key Vault. Adjust secret name if it differs.
$conn = az keyvault secret show --vault-name options-analyzer --name <SECRET_NAME_FOR_AZURE_SQL> --query value -o tsv

# Then run a SELECT via Python with pyodbc
python -c "
import pyodbc
import os
conn = pyodbc.connect(os.environ['CONN_STR'])
cur = conn.cursor()
cur.execute(\"SELECT id, market_data_provider FROM users WHERE market_data_provider = 'tradier'\")
rows = cur.fetchall()
print(f'Rows with tradier: {len(rows)}')
for r in rows:
    print(r)
"
```

If the secret name for the SQL connection string isn't obvious from CLAUDE.md or recent context, list secrets first:

```powershell
az keyvault secret list --vault-name options-analyzer --query "[].name" -o tsv
```

And report which one looks like the SQL connection string for Don to confirm. Don't guess.

Report:

- Number of rows with `market_data_provider = 'tradier'`
- If > 0, list the user IDs (so we know whose row needs updating)

If > 0 rows, the Phase 5 commit will include a one-line UPDATE statement run via the same connection. If 0 rows, no migration needed and the commit is purely code.

**STOP and report Phase 0 before proceeding.**

---

## Phase 1 — Delete `app/providers/tradier.py`

```powershell
rm app/providers/tradier.py
```

Verify:

```powershell
ls app/providers/tradier.py
```

Should return "not found." If `git status` shows the file as deleted, proceed.

**STOP and report.**

---

## Phase 2 — Update `app/providers/factory.py`

Three sub-changes in one file:

### 2.1 Remove the import

Find and delete the line:

```python
from app.providers.tradier import TradierMarketData
```

(Approximately line 19 per Jira; use Phase 0.1's actual location.)

### 2.2 Remove the `"tradier"` registry entry

Find the entire `"tradier": { ... }` block in `PROVIDER_REGISTRY`. Delete the whole entry, including the trailing comma if present. Approximately lines 38–48.

After deletion, `PROVIDER_REGISTRY` should still be valid Python — confirm by checking the dict structure: opening `{`, remaining entries (likely `"schwab"`), closing `}`.

### 2.3 Update docstrings

- Module docstring (~line 11): remove the sentence "Tradier supports MarketDataProvider + AccountProvider + TradingProvider."
- `ProviderFactory` class docstring (~line 64): replace any example showing `factory.get_market_data("tradier", ...)` with the equivalent Schwab call (e.g., `factory.get_market_data("schwab", secrets, user_id, env)`).

Show the diff:

```powershell
git diff app/providers/factory.py
```

Sanity check the file imports and parses cleanly:

```powershell
python -c "from app.providers.factory import PROVIDER_REGISTRY, ProviderFactory; print(list(PROVIDER_REGISTRY.keys()))"
```

Should print `['schwab']` (or whatever the remaining provider keys are). If it errors with an `ImportError`, something's wrong — STOP and report.

**STOP and report.**

---

## Phase 3 — Remove Tradier entry from `app/api/service_routes.py`

Find the `"tradier"` entry in `_SERVICE_REGISTRY` (approximately lines 42–49). It's already marked `active: False` and labeled "Market Data (Deprecated)". Delete the entire entry, not just the flag.

Show the diff:

```powershell
git diff app/api/service_routes.py
```

Verify the file still parses:

```powershell
python -c "from app.api.service_routes import _SERVICE_REGISTRY; print(list(_SERVICE_REGISTRY.keys()))"
```

**STOP and report.**

---

## Phase 4 — Remove `tradier_environment` from `app/core/config.py`

Find lines 52–53 (or wherever Phase 0.1 located them):

```python
# --- Tradier (non-secret settings) ---
tradier_environment: str = "sandbox"  # "sandbox" or "production"
```

Delete both lines.

Show the diff and verify the config class still parses:

```powershell
git diff app/core/config.py
python -c "from app.core.config import Settings; print(Settings.__fields__.keys())"
```

The output should NOT contain `tradier_environment`. If it does, find and remove any other reference.

**STOP and report.**

---

## Phase 5 — DB column default change in `app/models/database.py`

This is the one substantive behavioral change in this Story.

Line 50 (or wherever Phase 0.1 located it):

```python
# Before
market_data_provider = Column(String(50), default="tradier")
# After
market_data_provider = Column(String(50), default="schwab")
```

After editing, **handle existing rows based on Phase 0.3's pre-flight result:**

### 5.1 If Phase 0.3 found 0 rows with `'tradier'`

Skip the data migration. Existing rows are all already on Schwab or some other valid provider. The default change only affects new rows.

### 5.2 If Phase 0.3 found > 0 rows with `'tradier'`

Update them now, before the next deploy ships. Use the same connection mechanism from Phase 0.3:

```powershell
python -c "
import pyodbc
import os
conn = pyodbc.connect(os.environ['CONN_STR'])
cur = conn.cursor()
cur.execute(\"UPDATE users SET market_data_provider = 'schwab' WHERE market_data_provider = 'tradier'\")
print(f'Updated {cur.rowcount} rows')
conn.commit()
"
```

Then re-run the Phase 0.3 SELECT to confirm 0 rows now have `'tradier'`.

Note in your Phase 5 report:

- Whether the data migration was needed
- If yes, how many rows were updated
- Confirmation that re-query shows 0 rows

**STOP and report.**

---

## Phase 6 — Update `app/models/schemas.py` comment

Line 226 (or wherever Phase 0.1 located it):

```python
# Before
provider: str  # "tradier" or "schwab"
# After
provider: str  # "schwab"
```

One-line comment change. Show the diff.

**STOP and report.**

---

## Phase 7 — Clean up `.env.example`

Three sub-changes:

### 7.1 Remove the Tradier section

Lines 20–23 (or as found in Phase 0.1):

```
# --- Tradier ---
# Get your sandbox token at: https://dash.tradier.com/settings/api
TRADIER_API_TOKEN=your-tradier-sandbox-token-here
TRADIER_ENVIRONMENT=sandbox
```

Delete all four lines.

### 7.2 Remove the dead CORS comment block

Lines 25–27 (or as found):

```
# --- CORS ---
# Add your web app URL if not localhost
# CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
```

`CORS_ORIGINS` is hardcoded in `main.py` (per OTA-519's discovery) — the env-based comment is misleading and was already dead before this Story. Cleaning it up here while we're touching `.env.example` anyway.

### 7.3 Update `DEFAULT_MARKET_DATA_PROVIDER`

Find the last line (or wherever it lives):

```
DEFAULT_MARKET_DATA_PROVIDER=tradier
```

Change to:

```
DEFAULT_MARKET_DATA_PROVIDER=schwab
```

Show the diff:

```powershell
git diff .env.example
```

**STOP and report.**

---

## Phase 8 — Clean up local `.env` (NOT committed)

Security hygiene — don't leave commented-out credentials sitting around.

```powershell
cat .env
```

Find and delete:

1. The commented-out `TRADIER_API_TOKEN` line. It contains a real credential value even though commented — `git log` won't see this since `.env` is gitignored, but local copies floating around are still a leak risk.
2. `TRADIER_ENVIRONMENT=production` (or whatever value).

Verify both are gone:

```powershell
grep -i "tradier" .env
```

Should return no results.

**Important: `.env` is gitignored — DO NOT add to staging.** Just edit it in place.

**STOP and report.**

---

## Phase 9 — Final grep audit

```powershell
grep -rin "tradier" app/ --include="*.py"
```

Expected remaining hits (per Jira guardrails — these are intentionally preserved):

- `app/providers/schwab.py` — docstrings comparing Schwab to Tradier for developer education
- `app/api/market_routes.py` — informational route comments
- `app/api/schwab_auth_routes.py` — informational route comments
- `app/core/secrets.py` — docstring uses Tradier as illustration of multi-tenant key naming pattern

**Any hits NOT in this whitelist → STOP and report.** Could be a missed file or a new reference introduced since Phase 0.

```powershell
grep -rin "tradier" web/src --include="*.js" --include="*.jsx" --include="*.ts" --include="*.tsx"
```

Expected: zero hits. If anything turns up, report — frontend cleanup wasn't in this Story's scope but we want to know.

**STOP and report.**

---

## Phase 10 — Commit

One commit. All file changes in Phases 1–7 land together. Phase 8's local `.env` change is NOT committed.

```powershell
git status
git add -A
git diff --cached
```

Verify only the expected files are staged:

- `app/providers/tradier.py` (deleted)
- `app/providers/factory.py` (modified)
- `app/api/service_routes.py` (modified)
- `app/core/config.py` (modified)
- `app/models/database.py` (modified)
- `app/models/schemas.py` (modified)
- `.env.example` (modified)

If anything else is staged, STOP and report.

Commit message:

```
OTA-524 chore: remove Tradier adapter and all dead Tradier config

Schwab is the sole market data provider. Tradier was never used in
production with these credentials. App Service settings (TRADIER_API_KEY,
TRADIER_ENVIRONMENT) were removed from prod in OTA-519. This commit
removes the codebase residue.

Code changes:
- Delete app/providers/tradier.py (unused adapter)
- Remove tradier entry from PROVIDER_REGISTRY in factory.py
- Remove tradier import and update docstrings in factory.py
- Remove tradier entry from _SERVICE_REGISTRY in service_routes.py
- Remove tradier_environment field from config.py
- Change market_data_provider DB column default from "tradier" to "schwab"
- Update ProviderConnectRequest.provider comment in schemas.py

.env.example:
- Remove Tradier section
- Remove dead CORS_ORIGINS comment block (CORS is hardcoded in main.py,
  not env-driven — comment was misleading even before this Story)
- Change DEFAULT_MARKET_DATA_PROVIDER from "tradier" to "schwab"

Data migration: <FILL IN BASED ON PHASE 5>
- If 0 rows: "No existing rows had market_data_provider='tradier' — no
  data migration required."
- If > 0 rows: "Updated N existing user rows from 'tradier' to 'schwab'
  via direct SQL. Confirmed via re-query."

Local .env cleanup (not committed) was performed separately for security
hygiene — removed commented-out TRADIER_API_TOKEN containing a real
credential and TRADIER_ENVIRONMENT=production.

Whitelisted Tradier references retained in schwab.py docstrings,
market_routes.py comments, schwab_auth_routes.py comments, and
secrets.py docstring (developer education / multi-tenant key naming
pattern illustration).

Closes OTA-524.
```

Push. Report commit SHA.

---

## Phase 11 — Post-commit verification (Don does this — minimal)

This Story doesn't ship to prod via the deploy workflow because it's pure code cleanup. The change reaches dev/prod when the next normal deploy happens.

Quick local verification Don can do:

```powershell
.\venv\Scripts\activate
python -c "from app.main import app; print('App imports cleanly')"
```

If imports fail, something's wrong — investigate the error before triggering any deploy.

If imports succeed, the cleanup is complete. The change ships with whatever the next deploy is.

---

## Out of scope

- Removing Tradier from documentation (`CLAUDE.md`, `architecture-plan.md`, `auth-process.md`) — folded into OTA-521 (docs rewrite Story)
- Schwab adapter docstring / route comment cleanup — intentionally preserved per Jira guardrails
- Audit of other dead config patterns elsewhere in the codebase — separate audit Story if appetite exists
- Frontend cleanup beyond reporting — if Phase 0.2 finds frontend hits, file a follow-up Story
- Alembic migration tooling — OTA-522 handles migration infrastructure; this Story uses direct SQL for the one-row-update case

## Guardrails

- **Do NOT touch `app/providers/schwab.py`.** Docstrings compare Schwab to Tradier for developer education — leave them.
- **Do NOT touch route comments in `market_routes.py` or `schwab_auth_routes.py`.** Informational only.
- **Do NOT touch `app/core/secrets.py`.** The docstring uses Tradier as an illustration of multi-tenant key naming, not a functional reference.
- **Do NOT skip Phase 0.3 (DB pre-flight check).** This is the only behaviorally-affecting change in the Story; getting the migration right matters.
- **Do NOT commit `.env`.** It's gitignored. Phase 8 changes are local only.
- **Do NOT batch-skip phases.** Stop and report between every phase. Cleanup work is exactly where "I'll just do all of it and report at the end" introduces silent errors.
- **If any phase produces a Python parse/import error, STOP.** Don't proceed assuming subsequent edits will fix it.
- Read before edit. Every time.

## Sequencing after this Story

OTA-524 is independent of OTA-520, OTA-522, OTA-521. Closes when committed. The change ships to dev and prod via normal deploy workflows whenever the next deploy fires.
