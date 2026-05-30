# OTA-668 — Phase 3b.2: api_symbol Normalization Helpers + Wiring

## Terminal context

- This terminal: Terminal A (single-terminal session)
- Concurrent terminals: none
- Cross-terminal dependencies: Phase 3b.1 (OTA-667) must be committed and validated. The `SymbolReference` ORM model must exist in `app/models/database.py` before this sub-phase starts — `to_api_symbol()` and `from_api_symbol()` depend on it for DB lookups.

## Required reading

Before any code changes:

```powershell
cat claude_context\CLAUDE.md
cat claude_context\architecture-plan.md
cat database-normalization-proposal.md
cat phase3a-orm-audit-report.md
cat phase2-migration-log.md
cat phase3b-1-cutover-log.md
```

Read **Sections 2.2, 3.1–3.4 of the audit report in full** plus **§7.3b.2**. Sections 2.2 and 3 enumerate the 11 individual write-call-sites (7 inbound + 4 outbound) plus the BREAKING gaps in `trade_evaluation_routes.py` and the missing-index-symbol-translation gaps in `schwab.py` / `schwab_context_source.py`. §7.3b.2 collapses them into three action lines. Both views must agree before any wiring is applied.

Also confirm 3b.1 shipped cleanly by reading `phase3b-1-cutover-log.md` — its SUCCESS banner is a precondition for this sub-phase.

## Relevant Context — Do Not Deviate Without Escalation

### Source: phase3a-orm-audit-report.md (authoritative for *what* to change)

The audit report's §7.3b.2 lists the three actions for this sub-phase. Section 3 lists every per-call-site finding the actions resolve. **This prompt does not enumerate findings** — it defines the workflow. The audit report enumerates the work.

If §7.3b.2's actions conflict with anything else read during this session, the audit report wins for matters of *what to change*. The proposal wins for matters of *what the new schema means*.

### Source: phase3a-orm-audit-report.md §3.4 (helper module signatures — authoritative)

The helper module location, function names, and signatures are fixed by audit §3.4:

```
Location: app/services/symbol_normalization.py

def canonicalize(symbol: str) -> str:
    """Strip $ prefix, uppercase. For inbound writes."""

async def to_api_symbol(db: AsyncSession, symbol: str, provider: str) -> str:
    """Canonical → provider-specific form. Looks up symbol_reference.api_symbol."""

async def from_api_symbol(db: AsyncSession, api_symbol: str) -> str:
    """Provider-specific → canonical form. Reverse lookup on api_symbol column."""
```

Do not deviate from these names or signatures. Earlier drafts of the prompt template used `to_canonical()` and a synchronous `to_api_symbol()` — those names are obsolete. The audit's signatures win.

### Source: database-normalization-proposal.md §10.7 (api_symbol semantics)

> "Application code normalizes inbound `$X` API symbols to canonical `X` form before writing to any child table's `symbol` column."

The DB column `symbol` always stores the canonical form (no `$`, uppercased). The `symbol_reference.api_symbol` column stores the form a provider expects to receive (e.g., canonical `SPX` ↔ Schwab API `$SPX`). All inbound writes pass through `canonicalize()` before reaching any `symbol` column; all outbound provider calls for symbols that have a non-null `api_symbol` pass through `to_api_symbol()` before reaching the provider.

For providers that already use the canonical form (Finnhub, per audit §3.3 row 4), `to_api_symbol()` will return the canonical value unchanged when `api_symbol` is NULL — no special-case logic needed at the call site.

### Source: phase2-migration-log.md (canonical column names)

`symbol_reference.api_symbol` is the canonical column name. Any reader of an older draft that says `apiSymbol`, `api_sym`, or `provider_symbol` is stale — use `api_symbol`.

### Source: CLAUDE.md (commit discipline, two-Claude workflow)

- Exactly one commit for this sub-phase, with `OTA-668` prefix.
- Do not advance Jira state. Do not push. Don holds those gates personally.
- Azure SDK calls in async FastAPI handlers must use `.aio` variants. This is more than a passing rule for 3b.2 — `to_api_symbol()` and `from_api_symbol()` are async and take an `AsyncSession`. Any call site that adopts them must be inside an async function with an async session in scope.

### 3b.2-specific guardrails

- **Async session pitfall — STOP if a call site doesn't have a session in scope.** `to_api_symbol()` and `from_api_symbol()` read from `symbol_reference` via the ORM and require an `AsyncSession`. If any outbound call site listed in audit §3.3 (especially the Schwab paths in `schwab.py` / `schwab_context_source.py`) doesn't already have an async session available — for example, if the Schwab client is constructed in a context that hasn't taken a session as a dependency — that's a refactor problem, not a wiring problem. **Halt and report.** Do not improvise async session creation (no `async with AsyncSession(engine)` inside provider code, no global session, no synchronous wrapper). The audit identified this risk; the fix to it is its own design decision and belongs to Don, not to Claude Code.

- **Index symbol smoke test is required for outbound wiring.** After wiring `to_api_symbol()` into Schwab outbound calls, the verification phase must demonstrate a real round-trip for at least one index symbol (e.g., `SPX` → `$SPX` → quote returned). Index symbol mapping is the medium-risk surface of 3b.2 and is the only place where an incorrect outbound mapping breaks production quotes silently. A passing unit test is not sufficient by itself — a live call against Schwab dev is the cross-check.

- **Round-trip identity must hold for all symbols.** The unit tests for the helpers must include a round-trip check: for any canonical symbol `s`, `from_api_symbol(to_api_symbol(s, "schwab"))` returns `s`. This applies whether or not `s` has an `api_symbol` mapping. A symbol with no mapping round-trips to itself (`canonicalize()` is idempotent).

- **Inbound BREAKING gaps in `trade_evaluation_routes.py` are the priority.** Per audit §2.2, lines 260, 497, 516, 616 of `trade_evaluation_routes.py` write `request.symbol` to `trade_recommendations` and `agent_run_log` with no normalization at all (not even `.upper()`). These are BREAKING — the other inbound paths in §3.2 are PARTIAL (they have `.upper()` but no `$`-strip). All seven inbound paths get wired through `canonicalize()`; the BREAKING ones are not a separate category, just the most important to confirm during verification.

- **Frontend `.toUpperCase()` is 3b.4, not 3b.2.** Audit §2.2 row 3 calls out `TradeEvaluationView.jsx` line 186 (`spread.symbol` sent without `.toUpperCase()`). That fix belongs to 3b.4 (OTA-670). Do not touch `web/src/` files in 3b.2.

### Out-of-scope guardrails

- No changes to `app/models/database.py` — 3b.1's territory.
- No `relationship()` changes, no FK additions, no Alembic migrations.
- No changes to `web/src/` — frontend `.toUpperCase()` is 3b.4.
- No changes to `app/agents/insight_engine.py` or `app/agents/position_monitor.py` — 3b.3's territory.
- No tightening of `insights.user_id` / `source_position_id` to NOT NULL.
- No varbinary token migration, no view creation, no async credential cleanup (OTA-671).
- No table drops.

## Scope

### Phase 1 — Read the audit report's 3b.2 entry and confirm 3b.1 preconditions

1. Open `phase3a-orm-audit-report.md` and locate §7.3b.2. Confirm the three actions match what's described above.
2. Open Section 3 and read §§3.1, 3.2, 3.3, 3.4 in full. Build a mental inventory of the seven inbound call sites and the four outbound call sites.
3. Open `app/models/database.py` and confirm `SymbolReference` exists with the eight columns from audit §1.1. If it doesn't, halt — 3b.1 didn't ship cleanly and 3b.2 cannot proceed.
4. For each outbound call site in §3.3, open the file and confirm whether an `AsyncSession` is in scope at that call site. If any are not, halt and notify Don with the specific file/line. Do not start wiring until the session-availability question is settled.

### Phase 2 — Create the helper module

Create `app/services/symbol_normalization.py` with the three functions from audit §3.4, exact signatures. Implementation notes:

- `canonicalize(symbol)` — strip leading `$`, uppercase, strip whitespace. Idempotent.
- `to_api_symbol(db, symbol, provider)` — first call `canonicalize(symbol)` to ensure canonical input. **Branch on the provider parameter.** Today's `symbol_reference.api_symbol` column stores the Schwab-specific form (e.g., `$SPX` for `SPX`); it is implicitly Schwab-only. The function body must reflect that:
  - If `provider == "schwab"`: query `SymbolReference` for the symbol's `api_symbol` field. If `api_symbol` is non-null, return it. Otherwise return the canonical symbol unchanged.
  - For any other `provider` value: return the canonical symbol unchanged. Do not apply the Schwab mapping to non-Schwab providers — doing so would send `$SPX` to a provider that expects `SPX`, breaking quotes silently.
  
  Log at DEBUG level when a mapping is applied so audit trails capture index translations. When the proposal §10.7 per-provider schema lands in a future phase, the branching here evolves but the function signature does not.
- `from_api_symbol(db, api_symbol)` — reverse lookup on `SymbolReference.api_symbol`. If a row matches, return its `symbol` (the canonical form). If no row matches, call `canonicalize(api_symbol)` and return that. This makes the function tolerant of inputs that are already canonical.

### Phase 3 — Add unit tests for the helpers

Tests live alongside the existing test convention in this repo (look at where the `pytest` config and existing tests live; mirror that). The test file covers:

- `canonicalize`: `"$SPX"` → `"SPX"`, `"spx"` → `"SPX"`, `"  SPX  "` → `"SPX"`, `"SPX"` → `"SPX"` (idempotent), edge cases like `"$"` and `""`.
- `to_api_symbol`: for a symbol with `api_symbol="$SPX"` in fixtures, `to_api_symbol(db, "SPX", "schwab")` returns `"$SPX"`; `to_api_symbol(db, "SPX", "finnhub")` returns `"SPX"` (the Schwab mapping is NOT applied to non-Schwab providers). For a symbol with `api_symbol=None`, returns the canonical input regardless of provider.
- `from_api_symbol`: for `"$SPX"` with a fixture row mapping `SPX → $SPX`, returns `"SPX"`. For an input that has no matching row, returns the canonical form of the input.
- **Round-trip identity**: for every canonical symbol in the test set, `from_api_symbol(db, to_api_symbol(db, s, "schwab"))` returns `s`.

Use an async test fixture for the DB session. If the existing test suite already has an async-DB fixture pattern (e.g., a session-scoped fixture that yields an `AsyncSession` against a test database or in-memory SQLite), reuse it. Do not introduce a new fixture pattern.

### Phase 4 — Wire `canonicalize()` into inbound write paths

Apply `canonicalize()` at each of the seven inbound call sites listed in audit §3.2. Each site already does `.upper()` (except the BREAKING ones in §2.2 which do nothing); replace the existing normalization (or lack thereof) with a single `canonicalize()` call.

The seven files (one site per row in §3.2):

1. `app/api/position_routes.py` (lines 664–666, 750–752)
2. `app/api/analysis_routes.py` (lines 227–234, 508, 378–392, 462–476 — multiple sites)
3. `app/analysis/chain_collection.py` (lines 55–65)
4. `app/agents/context_store.py` (line 75)
5. `app/api/trade_evaluation_routes.py` (lines 260, 497, 516, 616 — BREAKING per §2.2)
6. `app/api/evaluation_routes.py` (lines 679, 737 — and also lines 566, 750 from §2.2 STALE)

For each site, the change is mechanical: locate where the symbol is being assigned to a DB row's `symbol` field or passed to a function that does so, and replace `request.symbol` or `request.symbol.upper()` with `canonicalize(request.symbol)`. Import the helper at the top of each file.

### Phase 5 — Wire `to_api_symbol()` into Schwab outbound calls

Apply `to_api_symbol(db, symbol, "schwab")` at the three Schwab outbound call sites from audit §3.3:

1. `app/providers/schwab.py` (lines 91–101 — `get_quote`)
2. `app/providers/schwab.py` (line 182 — chain fetch)
3. `app/providers/schwab_context_source.py` (line 60 — quote via context source)

Each site currently does `symbol.upper()` before sending to Schwab. Replace with `await to_api_symbol(db, symbol, "schwab")`. The session-availability precondition was settled in Phase 1; if it wasn't, this phase should not have started.

Do **not** touch `app/providers/finnhub_earnings.py` (line 135) — audit §3.3 row 4 confirms it's already correct.

### Phase 6 — Verify

1. **Syntax / import check.**
   ```powershell
   cd C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer
   .\venv\Scripts\Activate.ps1
   python -c "from app.services import symbol_normalization; print('imports OK')"
   ```
   Then a broader import check on the wired files:
   ```powershell
   python -c "from app.api import position_routes, analysis_routes, trade_evaluation_routes, evaluation_routes; from app.providers import schwab; from app.analysis import chain_collection; from app.agents import context_store; print('imports OK')"
   ```

2. **Test suite.**
   ```powershell
   pytest
   ```
   All tests must pass. The new `symbol_normalization` unit tests must be among the passing set. If any pre-existing test fails because it was relying on un-normalized symbol handling, that's a real finding — log it in the cutover log and halt; do not patch the test in this sub-phase.

3. **Smoke test the three audit Section 5 queries.** Same three queries from 3b.1, same user, same expected row counts (39 / 6 / 10).

4. **Index symbol live round-trip (REQUIRED for 3b.2).** Run a one-off script (do not commit it) that calls the Schwab `get_quote` path for `SPX`:
   ```powershell
   python -c "import asyncio; from app.providers.schwab import get_quote; from app.models.session import async_session; \
   asyncio.run((lambda: (lambda db: get_quote(db, 'SPX'))(async_session()))())"
   ```
   (Adapt to the actual function signature — the point is one canonical → API → canonical round-trip via the real Schwab provider against the dev DB.) Confirm: the call returns a non-empty quote, and Schwab was actually called with `$SPX` (verify via Schwab provider logs or a debug print). Record the canonical input, the API form sent, and the quote returned in the cutover log.

5. **No frontend touched.** `npm run build` is not required for 3b.2.

If any verification step fails, do **not** commit. Stop and report.

### Phase 7 — Commit

One commit for this sub-phase with this message format:

```
OTA-668 feat: phase 3b.2 - api_symbol normalization helpers and wiring
```

After commit, **stop**. Write a brief log file `phase3b-2-cutover-log.md` at project root summarizing:

- The three actions applied (helper module + inbound wiring + outbound wiring), with file counts and line-counts
- Test results (`pytest` summary, including the new `symbol_normalization` tests by count)
- Smoke-test outcomes (3 queries, pass/fail, row counts)
- **Index symbol round-trip result** (canonical input → API form sent → quote returned)
- Any deviations from the audit-report-recommended fix (with reason)
- Any findings surfaced during application that the audit didn't capture
- Banner: SUCCESS / FAIL

Do not proceed to 3b.3. Don opens a fresh Claude Code session with `phase3b-3-insights-write-wiring-PROMPT.md` after confirming 3b.2 is committed and validated.

## Acceptance criteria

- [ ] Audit report §7.3b.2 and Section 3 (§§3.1–3.4) were read in full before any code change.
- [ ] `phase3b-1-cutover-log.md` was read and shows SUCCESS; `SymbolReference` exists in `app/models/database.py`.
- [ ] Each outbound call site in §3.3 was confirmed to have an `AsyncSession` in scope before wiring began (or the session-availability gap was escalated to Don and resolved).
- [ ] `app/services/symbol_normalization.py` exists with `canonicalize`, `to_api_symbol`, `from_api_symbol` per audit §3.4 signatures exactly.
- [ ] Unit tests for the three helpers exist, cover the cases listed in Phase 3, and pass.
- [ ] Round-trip identity test passes for every canonical symbol in the test set.
- [ ] All seven inbound call sites from audit §3.2 route through `canonicalize()`; the four BREAKING sites in `trade_evaluation_routes.py` per §2.2 are among them.
- [ ] All three Schwab outbound call sites from audit §3.3 route through `to_api_symbol(..., "schwab")`. `finnhub_earnings.py` is unchanged.
- [ ] No file in `web/src/`, `app/models/`, `app/agents/insight_engine.py`, or `app/agents/position_monitor.py` is modified.
- [ ] `python -c "from app.services import symbol_normalization"` succeeds with no warnings.
- [ ] Full `pytest` run passes.
- [ ] Three audit-Section-5 smoke-test queries pass with original row counts.
- [ ] **Index symbol live round-trip recorded in the cutover log** — canonical → API form → quote returned, confirmed via Schwab provider logs.
- [ ] Exactly one commit with message `OTA-668 feat: phase 3b.2 - api_symbol normalization helpers and wiring`.
- [ ] `phase3b-2-cutover-log.md` exists at project root with SUCCESS banner and the index round-trip result captured.
- [ ] Don has been notified in chat that 3b.2 is complete.
- [ ] **No** Jira state advance (Don's gate).
- [ ] **No** push (Don's gate).

## Out of scope

- Any file in `app/models/` (3b.1's territory; closed).
- `app/agents/insight_engine.py` and `app/agents/position_monitor.py` (3b.3 / OTA-669).
- Any file in `web/src/` (3b.4 / OTA-670).
- Frontend `.toUpperCase()` on `TradeEvaluationView.jsx` (3b.4).
- `ValidationAssessment.ticker → symbol` call-site sweep outside `database.py` (3b.4).
- Async credential cleanup (OTA-671).
- Tightening any column to NOT NULL.
- New Alembic migrations or DB schema change.
- Per-provider `api_symbol` schema work (changing `symbol_reference` to support per-provider mappings is proposal §10.7 future work; only the function-body branching on provider is in 3b.2 scope).
- Varbinary token migration, view creation, strategy taxonomy redesign, table drops.

## Verification

1. `git status` shows only: the new `app/services/symbol_normalization.py`, the new test file, the seven wired files, and the cutover log at project root.
2. `git log --oneline -1` shows the standardized commit message.
3. `phase3b-2-cutover-log.md` matches the format of `phase3b-1-cutover-log.md` with the additional index round-trip section.
4. No file outside the §3.2 / §3.3 / §3.4 scope was touched.

**QA Level:** Level 3 — touches every call site that handles symbols. The medium-risk surface is the outbound Schwab wiring; index round-trip in verification is the mitigation. Inbound wiring is mechanical (Level 2) but spans seven files; the round-trip identity unit test is the cross-check.

## Commit instruction

I have been instructed to commit exactly **one commit** for this sub-phase. After the commit, **stop** and notify Don. Do not advance Jira state. Do not push. Don holds those gates.

"I have been instructed to commit. Do you approve? (yes / no)"

## Coordination footer

- Previous: OTA-667 (Phase 3b.1) at Code & Test Complete or beyond. `SymbolReference` ORM model must exist in `app/models/database.py` — verified in Phase 1 of this prompt.
- Next: a fresh Claude Code session with `phase3b-3-insights-write-wiring-PROMPT.md` (OTA-669). Don opens that session after confirming 3b.2 is committed and validated. 3b.3 depends on the `Insight` model having `user_id` and `source_position_id` (added in 3b.1) — no dependency on 3b.2's helpers.
