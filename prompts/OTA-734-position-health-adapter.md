---
allowedTools:
  - Read
  - Edit
  - Write
  - Bash
  - Grep
  - Glob
---

# OTA-734 — Position-health input adapter
covers OTA-735, OTA-736, OTA-737, OTA-738, OTA-739, OTA-740, OTA-741

> Multi-story prompt. One package, built incrementally, committed once at the end after parity passes (OTA-741). Stop-and-report between every phase. Claude Code does not commit; Don commits manually after approving the gate.

## Terminal context
- This terminal: **Terminal A (Primary)**
- Concurrent terminals: **Terminal B** running OTA-752 (directional adapter + rules) in parallel
- Cross-terminal dependencies:
  - **UPSTREAM GATE (blocking):** this work reuses `app/ota_adapters/_shared/` (Schwab client + Black-Scholes), which is produced by **OTA-713** (options-chain adapter, plan F3 S3.1). At authoring time OTA-713 is still in Write Prompt and has **not committed** `_shared/`. The whole feature also sits behind **OTA-695** (Engine core extraction) / **OTA-702** (the `populate_computed(candidates, needed)` signature). **Do not start Phase 1 until Phase 0 confirms both gates are satisfied.**
  - **Shared-file caution vs Terminal B:** OTA-752 also reuses `_shared/` (read-only consumption — fine) and may register an adapter/strategy. If adapter registration touches a shared file (`app/main.py`, an engine adapter registry, `app/database.py`), Terminal A and Terminal B must not edit it simultaneously. Phase 0 identifies the registration site; if it is shared, **hard-stop and report** before editing.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/insight_engine.md
cat claude_context/insight_engine-migration-plan.md
```

Then read the actual current sources you are extracting from / building against:

```
cat app/analysis/health_grade.py                       # parity target (OTA-741)
ls -R app/ota_adapters/                                 # confirm _shared/ exists (GATE)
cat app/ota_adapters/_shared/*.py                       # the providers you REUSE
ls -R app/ota_adapters/options_chain/                   # OTA-713 reference adapter
cat app/ota_adapters/options_chain/*.py                 # the §5 contract, implemented
```

If `insight_engine.md` / `insight_engine-migration-plan.md` are not under `claude_context/`, locate them (`git ls-files | grep insight_engine`) and read them where they live. If `rules-engine-audit-2026-05-20.md` is present in the repo, read its `health_grade.py` section; if absent, the live `app/analysis/health_grade.py` is the authoritative parity target — do not block on the audit doc.

## Relevant Context — Do Not Deviate Without Escalation

**Source: insight_engine.md §5 (input adapter contract)**
The adapter implements exactly three responsibilities and nothing more: `produce_candidates`, `populate_computed`, and an `input_catalog`. The adapter fetches raw data, computes DERIVED values, and produces COMPUTED values on demand. The adapter **does not run rules, does not assign scores, and does not know about strategies, junctions, or verdict bands.** Engine code that references a domain name is a defect — the inverse holds for the adapter: domain knowledge lives here and only here.

**Source: insight_engine.md §5.2 (COMPUTED callback)**
Signature is `adapter.populate_computed(candidates: list[Candidate], needed: set[str]) -> list[Candidate]`. The engine passes the survivor set plus the COMPUTED names still-active rules need; the adapter populates only those fields, only for those candidates. COMPUTED is never run on the full candidate set up front. This signature is fixed by **OTA-702** — confirm it in the committed engine core before implementing against it.

**Source: insight_engine.md §5.1 (input catalog)**
Every named value the adapter produces is declared with name, tier (RAW / DERIVED / COMPUTED), type, null semantics, and producer reference. The engine validates at startup that every named value referenced by an active rule is present with a compatible type. Missing names fail **loudly at startup**, never silently at evaluation.

**Source: OTA-734 Work body + insight_engine-migration-plan.md (Position Health input adapter)**
Replaces every input `app/analysis/health_grade.py` reads ad hoc. After this feature, the Position Monitor Agent calls `produce_candidates(...)` and the engine drives `populate_computed` for survivors — **no position-health data logic remains in the app layer.** Output: one candidate per open position.

**Source: OTA-738 Work body — the P&L formula (exact)**
`pnl_pct = (current_position_mark - position_entry_price) / abs(position_entry_price)`. The `abs()` denominator is mandatory: it preserves correct grading for credit spreads, where a negative `entry_price` moving toward zero is a win. This mirrors `health_grade.py:_pnl_pct` — verify against the live source.

**Source: OTA-737 Work body — kill the `current_price` overload**
`health_grade.py` overloads a single `current_price` to mean both the underlying spot (inside the exit-levels path) and the spread mark (in the P&L path). The adapter publishes **both** explicitly: `current_underlying_price` and `current_position_mark`. The overload disappears; each downstream rule accesses the value it actually needs.

**Source: OTA-736 / OTA-738 Work bodies — structure-aware, not sign-inferred**
`position_structure_direction` (bullish/bearish) is derived from `position_structure` **at adapter load**, replacing the runtime `sign(stop - warning)` direction inference at `health_grade.py:55-56`. `warning_breached` / `stop_breached` are structure-aware booleans: bullish uses `current_underlying_price <= level`; bearish uses `>=`.

**Source: OTA-738 Work body — the 20% becomes a parameter, not adapter code**
`warning_proximity_ratio` (float in `[0, 1+]`) is distance from current underlying to the warning level, normalised by the warning-to-stop buffer. The 20% literal at `health_grade.py:65-66, 75-76` does **not** live in the adapter — it becomes a rule parameter (`proximity_buffer_fraction`) consumed downstream in OTA-742. The adapter publishes the raw ratio only.

**Source: CLAUDE.md House Style + architecture-plan.md Pattern 1 (provider routing)**
Never hardcode a provider name. Market data routes through the shared provider in `app/ota_adapters/_shared/` (which itself uses `_get_provider()` / settings). The position-health adapter **reuses** the committed `_shared/` Schwab client and Black-Scholes implementation — it never duplicates either. If `_shared/` does not export what you need, **stop and report**; do not copy provider code into `position_health/`.

**Source: architecture-plan.md (async Azure invariant) + memory of prod incidents**
Any Azure SDK call in an async FastAPI path uses the `.aio` async variants (`azure.identity.aio`), never synchronous `azure.identity`. `DefaultAzureCredential()` is never instantiated at module level — lazy-init double-checked locking. Synchronous calls block the event loop and hang only in prod. If the adapter touches Azure SDK at all (e.g. for secrets), honor this; otherwise N/A.

**Source: insight_engine.md §1 (multi-app stamping)**
Every engine call carries `source_app_id`. For OTA this is the string `"OTA"`. The adapter does not set it (the caller does), but candidates and catalog must be consistent with an `"OTA"`-stamped run.

---

## Phase 0 — Read-only discovery + GATE VERIFICATION (no edits)

Make no file changes in this phase. Report findings and STOP for Don's go-ahead before Phase 1.

1. **Gate — `_shared/` committed?** Confirm `app/ota_adapters/_shared/` exists on the current HEAD and exports a Schwab client and a Black-Scholes implementation. Record the exact module names, import paths, class/function names, and signatures you will call. If `_shared/` is absent or empty → **STOP. Report "OTA-713 gate not met."**
2. **Gate — engine core committed?** Confirm the engine core (OTA-695) is present and that the COMPUTED callback signature matches §5.2 exactly: `populate_computed(candidates, needed)`. Confirm the `Candidate` type / candidate construction API the chain adapter (OTA-713) uses. If absent or signature differs → **STOP. Report "OTA-695/OTA-702 gate not met."**
3. **Reference adapter.** Read `app/ota_adapters/options_chain/` end to end. The position-health adapter mirrors its structure (class implementing the §5 contract, catalog declaration pattern, how it consumes `_shared/`). Record the pattern you will follow.
4. **Parity target.** Read `app/analysis/health_grade.py` fully. Map each value it reads and each branch it takes to the named values listed in OTA-736/737/738/739. Record line references for the parity test (OTA-741): `_pnl_pct`, `_grade_from_pnl_pct`, the `sign(stop - warning)` inference (≈55-56), the within-20% logic (≈65-66, 75-76), stop→F (≈60-61, 71-72), warning→D (≈62-63, 73-74), the `scale_out` parse at ≈31, the parse-failure try/except at ≈78.
5. **`positions` table shape.** Confirm the columns / JSON fields the RAW producers read: `entry_price`, position legs / `position_structure`, `claude_exit_levels_json` (`warning`, `stop`, `scale_out`). Note the actual column names so OTA-736 reads real fields.
6. **Adapter registration site.** Determine where an adapter is registered/discovered by the engine. If it is a shared file (`app/main.py`, an engine registry, `app/database.py`) → flag it as a Terminal A/B collision risk and plan to sequence with Terminal B.

**STOP. Report Phase 0 findings + both gate verdicts. Wait for Don.**

---

## OTA-735 — Scope: adapter package and interface
Create `app/ota_adapters/position_health/` with a `PositionHealthAdapter` class implementing the §5 contract (`produce_candidates`, `populate_computed`, `input_catalog`), structured like the OTA-713 chain adapter. Inputs: open positions from the `positions` table + current market state per underlying. Output: one candidate per open position. Wire in the **reused** `_shared/` Schwab client and Black-Scholes providers via the import paths recorded in Phase 0 — no duplication.

**OTA-735 — Acceptance** (derived from the Work body): the package imports cleanly; the class exposes the three §5 methods with the §5.2 signature; provider access is via `_shared/` (grep proves no Schwab/B-S logic is redefined inside `position_health/`); `produce_candidates` returns one candidate per open position against a fixture. Skeleton only — producers are filled in OTA-736–739.

**OTA-735 — Out of scope:** any scoring, gating, strategy, or verdict logic (that is OTA-742); editing `_shared/`; editing the chain adapter.

**STOP-AND-REPORT gate after OTA-735.**

---

## OTA-736 — Scope: RAW producers from the `positions` table
Pull from each open position: `position_entry_price` (net credit/debit at entry — current `entry_price`); `position_structure` (enum: bull_put_credit, bear_call_credit, bull_call_debit, bear_put_debit, long_call, long_put — from legs at entry, not inferred); `position_structure_direction` (bullish/bearish, derived from `position_structure` **at adapter load**, replacing `sign(stop - warning)`); `position_exit_warning_underlying`, `position_exit_stop_underlying`, `position_exit_scale_out_underlying` (from `claude_exit_levels_json.warning/stop/scale_out` — scale_out currently parsed-but-unused; promote to a real input so OTA-749 can decide its fate); `position_exit_levels_complete` (bool: warning and stop both non-null and parseable — today drives the fall-back-to-P&L try/except, here it is a hard-gate input for OTA-744).

**OTA-736 — Acceptance:** all seven RAW values populate from real `positions` columns recorded in Phase 0; `position_structure_direction` is set at load from `position_structure` with zero runtime sign-inference; the three exit-level values and the completeness boolean derive from `claude_exit_levels_json`.

**OTA-736 — Out of scope:** computing breach flags or P&L (OTA-738); any rule consuming these.

**STOP-AND-REPORT gate after OTA-736.**

---

## OTA-737 — Scope: RAW producers from current market state
Via the **reused** `_shared/` Schwab provider, publish two RAW values **explicitly**: `current_underlying_price` (underlying spot) and `current_position_mark` (spread's current mark). Retire `health_grade.py`'s single-`current_price` overload — each is its own named value.

**OTA-737 — Acceptance:** both values populate via `_shared/` (not a re-implemented Schwab call); the catalog (OTA-740) will list both; no single value conflates spot and mark.

**OTA-737 — Out of scope:** caching/streaming design; OAuth/token work (owned by the shared provider / SCHWAB-LOGIN-PROCESS.md).

**STOP-AND-REPORT gate after OTA-737.**

---

## OTA-738 — Scope: DERIVED producers
Compute from the RAW set: `pnl_pct = (current_position_mark - position_entry_price) / abs(position_entry_price)` (abs denominator mandatory — see Relevant Context); `warning_breached` (structure-aware bool against `position_exit_warning_underlying`); `stop_breached` (same shape against `position_exit_stop_underlying`); `warning_proximity_ratio` (float `[0, 1+]`, normalised by the warning-to-stop buffer — **no 20% literal here**); `days_since_entry`, `days_to_expiration`.

**OTA-738 — Acceptance:** `pnl_pct` reproduces `health_grade.py:_pnl_pct` including the abs() behavior on a credit-spread fixture; breach flags match the structure-aware definition (bullish `<=`, bearish `>=`) for at least one bullish and one bearish fixture; `warning_proximity_ratio` is the raw normalised ratio with no embedded threshold.

**OTA-738 — Out of scope:** mapping the ratio to a score, or applying any 20% threshold (that is OTA-745/OTA-748 parameters).

**STOP-AND-REPORT gate after OTA-738.**

---

## OTA-739 — Scope: COMPUTED producers behind a feature flag
Behind a feature flag, implement `current_prob_of_profit`, `current_ev`, `probability_of_max_loss_now` for positions still inside their Black-Scholes validity window, computed via the **reused** `_shared/` Black-Scholes provider through the engine's `populate_computed` callback (only for survivors, never the full set). Not used by the v1 grade — present for the future weighted-scoring upgrade.

**OTA-739 — Acceptance:** these values are produced **only** inside `populate_computed`, **only** for the `needed` set, **only** for surviving candidates; the flag defaults off so v1 grading is unaffected; B-S comes from `_shared/`.

**OTA-739 — Out of scope:** wiring these into any rule; turning the flag on by default.

**STOP-AND-REPORT gate after OTA-739.**

---

## OTA-740 — Scope: publish the input catalog
Implement and publish the adapter's input catalog per §5.1 — every named value (RAW/DERIVED/COMPUTED) declared with name, tier, type, null semantics, producer reference. The engine validates required inputs against this at startup. **This catalog is the artifact OTA-742 (position-health rule library) has its soft dependency on** — it must be published (and committed) before OTA-742 can be fired in another terminal.

**OTA-740 — Acceptance:** the catalog declares every value from OTA-736/737/738/739 with correct tiers and null semantics; engine startup validation passes against a strategy that references these names; a name typo demonstrably fails startup loudly (spot-check).

**OTA-740 — Out of scope:** defining strategies or rules that reference the catalog (OTA-742).

**STOP-AND-REPORT gate after OTA-740.** *(This is the catalog-publish checkpoint that unblocks Terminal B's OTA-742.)*

---

## OTA-741 — Scope: adapter parity tests vs `health_grade.py`
End-to-end parity: a fixture of historical positions produces the same letter grade from the engine (with OTA-742's rules) as from pre-extraction `app/analysis/health_grade.py`. Cover the spectrum: just-entered/positive P&L; mid-life nearing warning; warning breached but not stop; stop breached; no-exit-levels across P&L bands. This test set is the acceptance gate for the Wave-4 Position Monitor Agent wiring story.

**OTA-741 — Acceptance:** the fixture suite runs green; intentional letter divergences (the Option B → Option A upgrade) are explicitly annotated as expected rather than treated as failures. If OTA-742's rules are not yet committed in this terminal's HEAD, the parity harness is authored and marked `skip` with a clear reason, to be un-skipped after OTA-742 lands.

**OTA-741 — Out of scope:** authoring the rules themselves (OTA-742).

---

## Verification steps (whole feature)
1. `python -c "import app.ota_adapters.position_health"` succeeds.
2. `grep -rn "BlackScholes\|black_scholes\|schwab" app/ota_adapters/position_health/` shows only **imports from `_shared/`**, never re-implementations.
3. `grep -rn "current_price" app/ota_adapters/position_health/` returns nothing — the overload is gone; both explicit names exist.
4. Engine startup validation passes with the published catalog (OTA-740).
5. The DERIVED parity checks (OTA-738) pass for at least one credit spread, one bullish, one bearish fixture.
6. The OTA-741 parity suite runs (green, or `skip` with stated reason pending OTA-742).
7. Apply the **Post-Build QA Gate** (CLAUDE.md): this is a cross-cutting backend extraction → recommend **Level 2** (full analysis-layer suite + targeted manual exercise of position-health). State the level in the commit body.

## Commit instruction
**"I have been instructed to commit. Do you approve? (yes / no)"**
One commit covers the whole feature after the OTA-741 parity gate passes (or is justified-skip). Don commits manually — Claude Code does not run `git commit`.

## Coordination footer
**STOP until OTA-713 commits `app/ota_adapters/_shared/` and OTA-695/OTA-702 (engine core + COMPUTED callback) land.** This prompt is authored ahead of those gates; do not run Phase 1 until Phase 0 confirms both. After this feature commits, the catalog-publish checkpoint (OTA-740) unblocks Terminal B's **OTA-742**.

## Commit message template (if committing)
```
OTA-734 OTA-735 OTA-736 OTA-737 OTA-738 OTA-739 OTA-740 OTA-741 feat: position-health input adapter (§5 contract, _shared reuse, input catalog, health_grade.py parity)
```
