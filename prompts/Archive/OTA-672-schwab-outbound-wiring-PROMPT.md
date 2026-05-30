---
allowedTools:
  - Bash
  - Read
  - Grep
  - Edit
  - Write
---

# OTA-672 — Schwab outbound symbol translation (caller-side wiring)

**Ticket:** OTA-672
**Branch:** `fix/OTA-672-schwab-outbound-translation`
**Commit (final):** `OTA-672 feat: schwab outbound symbol translation caller-side wiring`
**Cutover log:** `OTA-672-cutover-log.md` (project root)

---

## Required reading

Before doing anything, `cat` the following:

* `claude_context/CLAUDE.md`
* `claude_context/architecture-plan.md` — focus on **Pattern 1 (Provider Adapter)**
* `phase3a-orm-audit-report.md` §3.3 — outbound call-site inventory (existing artifact on disk)
* `phase3b-2-cutover-log.md` — confirms `app/services/symbol_normalization.to_api_symbol` already exists with `provider == "schwab"` branching (existing artifact on disk)

---

## What this prompt does

Routes canonical symbols through `to_api_symbol()` at the **upstream caller sites** that invoke Schwab provider methods. Translation happens at the caller, not in the provider.

The three Schwab outbound call sites are:

* `app/providers/schwab.py:78` — `SchwabMarketData.get_quote(...)`
* `app/providers/schwab.py:129` — `SchwabMarketData.get_chain(...)`
* `app/agents/contexts/schwab_context_source.py:58` — `SchwabContextSource.fetch(...)`

These provider methods currently accept whatever symbol the caller passes them. After OTA-668 shipped inbound canonicalization, the DB now stores canonical-form symbols (`SPX`, not `$SPX`). When a caller reads canonical from DB and passes it to Schwab without translation, Schwab rejects index symbols. This prompt fixes that by translating at every upstream caller that has an `AsyncSession` (`db`) in scope.

## Architectural decision

**Translate at the caller, not in the provider** (per `architecture-plan.md` Pattern 1 — providers are thin adapters and should not be DB-aware).

Pattern:

```python
# In API route or other caller with `db` in scope:
api_symbol = await to_api_symbol(db, canonical_symbol, "schwab")
quote = await provider.get_quote(api_symbol)
```

Rejected alternatives (do not implement either):

* Adding `db` to the `MarketDataProvider` ABC — leaks DB lifecycle into every provider
* Injecting a session factory into providers at construction — adds resource-accounting complexity

## In scope

* Audit upstream callers of `SchwabMarketData.get_quote`, `SchwabMarketData.get_chain`, and `SchwabContextSource.fetch`
* At each upstream caller that has `db` in scope, wire `to_api_symbol(db, symbol, "schwab")` before invoking the provider method
* Update docstrings on the three provider methods to state explicitly that they expect the `api_symbol` form, not canonical
* Add a one-line contract note in `architecture-plan.md` under Pattern 1
* Live SPX round-trip verification recorded in the cutover log

## Out of scope

* Any change to the `MarketDataProvider` ABC or to provider method signatures
* Injecting `AsyncSession` or `session_factory` into provider constructors
* Outbound paths for non-Schwab providers (Finnhub is already correct)
* Inbound `canonicalize()` wiring (already shipped in OTA-668)
* Any change to `to_api_symbol()` itself (already exists from OTA-668)

---

## Step 1 — Discovery (read-only, HARD HALT after)

Do not modify any file in this step. Output is a report only.

Run grep for every upstream caller of each Schwab outbound method:

```bash
# Caller search — use ripgrep where available
rg -n "provider\.get_quote\(|\.get_quote\(" app/ --type py
rg -n "provider\.get_chain\(|\.get_chain\(" app/ --type py
rg -n "SchwabContextSource\(|context_source\.fetch\(|schwab_context.*fetch\(" app/ --type py
```

For each caller hit, determine:

| Caller file:line | Provider method | `db` (AsyncSession) in scope? | If yes: how does `db` arrive? (e.g. `Depends(get_db)`, function param, constructed) |

Report this table to Don.

### HARD HALT — verify with Don before proceeding

Stop here and report:

1. The full table above
2. Whether all callers have `db` in scope (the architectural decision assumes most do)
3. Any caller that does NOT have `db` in scope — this is a deeper architectural question (likely affects `SchwabContextSource.fetch()` since context sources are invoked from agents rather than API routes)

**Do not proceed to Step 2 without explicit go from Don.** If `SchwabContextSource.fetch()` callers don't have `db`, Don needs to decide between:

* Plumbing `db` down to context source callers
* Letting `SchwabContextSource.fetch()` accept api_symbol from its caller and documenting that contract
* Some other resolution

---

## Step 2 — Implementation (only after Don approves Step 1)

For each caller that has `db` in scope:

```python
# Import (at top of file if not already present)
from app.services.symbol_normalization import to_api_symbol

# Before invoking provider:
api_symbol = await to_api_symbol(db, canonical_symbol, "schwab")
result = await provider.get_quote(api_symbol)
# ... same pattern for get_chain and fetch
```

* Use the canonical symbol variable that already exists at that call site — don't introduce new query/lookup logic
* Do NOT change provider method signatures
* Do NOT modify `to_api_symbol()` itself (already shipped in OTA-668)
* Estimated: ~3 files touched, ~10 LOC total

If you encounter a caller without `db` in scope despite Step 1 saying it had one, HARD HALT immediately and report. Do not work around.

---

## Step 3 — Docstring updates

Update docstrings on three provider methods. The contract change is the same in each — they now expect the `api_symbol` form:

* `app/providers/schwab.py` → `SchwabMarketData.get_quote`
* `app/providers/schwab.py` → `SchwabMarketData.get_chain`
* `app/agents/contexts/schwab_context_source.py` → `SchwabContextSource.fetch`

Add to each method's docstring:

> Expects the `api_symbol` form (e.g. `$SPX` for indexes), not the canonical form. Callers must translate via `app.services.symbol_normalization.to_api_symbol(db, canonical, "schwab")` before invoking this method. See `architecture-plan.md` Pattern 1.

Wording can be adapted per-method but the contract statement is non-negotiable.

---

## Step 4 — Architecture-plan.md contract note

Add a one-line contract statement to `claude_context/architecture-plan.md` under Pattern 1 (Provider Adapter). Insert near the existing description of provider responsibilities:

> Providers consume `api_symbol`-form strings; canonical-to-API translation is the caller's responsibility. See `app/services/symbol_normalization.to_api_symbol` for the helper.

Update the `Last Updated` header of `architecture-plan.md` to today's date (UTC) and add a Change Log entry referencing OTA-672 if the doc has one.

---

## Step 5 — Verification

### Backend tests

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
pytest --ignore=scratch --ignore=dev-agents -q
```

Expected: same pass count as the rest of the cutover (503 passed, 2 skipped). Zero failures.

### Live SPX round-trip — REQUIRED

This is the verification step that was deferred from OTA-668's outbound scope.

Trigger the live quote path for `SPX` (canonical form). Use whichever route is simplest — likely a direct call into `SchwabMarketData.get_quote` via a small inline script, or a curl against an existing endpoint that touches `provider.get_quote`. Confirm:

1. The caller submits `SPX` (canonical)
2. `to_api_symbol(db, "SPX", "schwab")` returns `$SPX`
3. The Schwab provider receives `$SPX`
4. A valid quote is returned

Record in the cutover log: canonical input → api form returned by `to_api_symbol` → quote received from Schwab (last price, timestamp). If any step fails, write the cutover log as FAILURE with the failure mode documented and do not proceed to commit.

---

## Step 6 — Cutover log and commit

Write `OTA-672-cutover-log.md` at project root. Include:

* Actions applied (table of caller files + line numbers)
* Test results (pytest, live SPX round-trip)
* Deviations from prompt (if any)
* File inventory (status + path)
* Banner: **SUCCESS** if all verification passes, **FAILURE** otherwise with detail

Single commit. Do not push to remote.

```powershell
git add -A
git commit -m "OTA-672 feat: schwab outbound symbol translation caller-side wiring"
```

Then STOP. Do not push, do not advance Jira manually — Don controls both gates.

---

## Banner contract

* **SUCCESS** — pytest passes, live SPX round-trip succeeds, all three call sites wired, docstrings updated, architecture-plan.md updated, single commit landed locally, cutover log written
* **FAILURE** — any of the above fails. Report failure mode in the cutover log; do not commit until Don confirms next step
