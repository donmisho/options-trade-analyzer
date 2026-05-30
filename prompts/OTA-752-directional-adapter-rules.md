---
allowedTools:
  - Read
  - Edit
  - Write
  - Bash
  - Grep
  - Glob
---

# OTA-752 — Directional comparison adapter and rule library
covers OTA-753, OTA-754, OTA-755, OTA-756

> Single combined feature: adapter **and** rule library ship together (unlike position health, which split adapter OTA-734 from rules OTA-742). One commit at the end, after OTA-755's scoring parity, **except OTA-756** — see its gate. Stop-and-report between phases. Claude Code does not commit; Don commits manually.

## Terminal context
- This terminal: **Terminal B (Secondary)**
- Concurrent terminals: **Terminal A** running OTA-734 (position-health adapter) in parallel
- Cross-terminal dependencies:
  - **UPSTREAM GATE (blocking):** reuses `app/ota_adapters/_shared/` (Schwab client + Black-Scholes) from **OTA-713** (plan F3 S3.1), which has **not committed** at authoring time. The feature also sits behind **OTA-695** (engine core) / **OTA-702** (`populate_computed(candidates, needed)` signature). **Do not start Phase 1 until Phase 0 confirms both gates.**
  - **DOWNSTREAM BLOCK on OTA-756:** the file-deletion story (retire `directional_engine.py`) is blocked by **OTA-765** (Wave-4 directional route wiring, plan S5.8), currently in Write Prompt. OTA-765 is what swaps the route from `fitness_score` to the engine; until it lands and removes the last caller, `directional_engine.py` cannot be deleted. **Author OTA-756, but do not CLOSE it in this run** — see the OTA-756 phase.
  - **Shared-file caution vs Terminal A:** both terminals reuse `_shared/` read-only (fine). If adapter/strategy registration touches a shared file (`app/main.py`, an engine adapter registry, `app/database.py`), do not edit it while Terminal A is editing it. Phase 0 identifies the registration site; if shared, **hard-stop and report** before editing.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/insight_engine.md
cat claude_context/insight_engine-migration-plan.md
```

Then the actual sources:

```
cat app/analysis/directional_engine.py                 # fitness_score parity target (OTA-755) + deletion target (OTA-756)
ls -R app/ota_adapters/                                 # confirm _shared/ exists (GATE)
cat app/ota_adapters/_shared/*.py                       # the providers you REUSE
ls -R app/ota_adapters/options_chain/                   # OTA-713 reference adapter
cat app/ota_adapters/options_chain/*.py                 # the §5 contract, implemented
ls -R app/options_rules/                                # existing rule-library layout (e.g. screening rules)
```

If the `insight_engine*` docs are not under `claude_context/`, locate them (`git ls-files | grep insight_engine`). If `rules-engine-audit-2026-05-20.md` is present, read its `directional_engine.py` / §7.5 #5 section; if absent, the live `directional_engine.py` is the authoritative parity target.

## Relevant Context — Do Not Deviate Without Escalation

**Source: insight_engine.md §5 / §5.1 / §5.2 (adapter contract)**
`DirectionalAdapter` implements exactly `produce_candidates`, `populate_computed` (signature `(candidates, needed)` — §5.2), and an `input_catalog` (§5.1, startup-validated). The adapter holds the domain knowledge; it does not run rules, assign scores, or know strategies/junctions/verdict bands.

**Source: OTA-753 Work body — thesis in, candidates out**
Inputs: a thesis (ticker, direction, conviction) + the Schwab chain (via `_shared/`). Output: **one candidate per (structure, strikes, expiry) combination compatible with the thesis.** The adapter publishes the input catalog its own rule library consumes — because both halves ship in this one feature, there is **no cross-feature catalog wait** of the kind OTA-742 had on OTA-734.

**Source: insight_engine.md §3.4 / §6 (strategies + junction)**
Strategy selection is configuration, not code. Each strategy's rules, weights, `evaluation_order`, `stop_if_fail`, and `score_penalty` live in junction rows; verdict bands come from the strategy's band config. **No code branches on strategy identity.** The runtime tables are the source of truth; the spreadsheet only seeds them.

**Source: OTA-755 Work body — fitness_score becomes formulas**
The `fitness_score` math in `directional_engine.py` decomposes into atomic scoring criteria, each registered as a pure formula `(named_values, params) -> float in [0, 100]` under `app/options_rules/directional/`. Junction rows supply weights — **no weights or thresholds remain as literals in code.** Startup validation verifies every `formula:<name>` reference resolves to a registered implementation.

**Source: OTA-752 Work body — the disposition this resolves**
After the feature ships, `fitness_score` is replaced by the engine's verdict + weighted score, and `app/analysis/directional_engine.py` is deleted — resolving the DirectionalEngine disposition (audit 7.5 #5; supersedes the retired plan story S8.5). Route wiring (the directional route calling the engine) is **not** this feature — it is the Wave-4 story **OTA-765**, on which the deletion depends.

**Source: CLAUDE.md House Style + architecture-plan.md Pattern 1 (provider routing)**
Never hardcode a provider name. The Schwab chain and Black-Scholes come from the committed `_shared/` providers — **reuse, never duplicate.** If `_shared/` does not export what you need, stop and report rather than copying provider code into `directional/`.

**Source: architecture-plan.md (async Azure invariant)**
Any Azure SDK call in an async path uses `.aio` variants; `DefaultAzureCredential()` is never module-level (lazy-init double-checked locking). Applies only if the adapter touches Azure SDK directly.

**Source: insight_engine.md §1 — `source_app_id`**
OTA runs stamp `source_app_id="OTA"`. The route (OTA-765) sets it; the adapter and catalog must be consistent with an `"OTA"`-stamped run.

---

## Phase 0 — Read-only discovery + GATE VERIFICATION (no edits)

Make no file changes. Report findings and STOP before Phase 1.

1. **Gate — `_shared/` committed?** Confirm `app/ota_adapters/_shared/` exists and exports the Schwab client + Black-Scholes. Record exact import paths / signatures. Absent → **STOP: "OTA-713 gate not met."**
2. **Gate — engine core committed?** Confirm OTA-695 present and `populate_computed(candidates, needed)` matches §5.2; record the `Candidate` construction API. Absent/mismatch → **STOP: "OTA-695/OTA-702 gate not met."**
3. **Reference adapter.** Read `app/ota_adapters/options_chain/` to mirror its structure and catalog pattern.
4. **Rule-library layout.** Read `app/options_rules/` (e.g. the screening rule library) to mirror the formula-registration pattern, the `formula:<name>` reference convention, and the junction/Strategies-tab mechanism.
5. **Parity target.** Read `app/analysis/directional_engine.py` fully. Decompose `fitness_score` into its atomic scoring components and record each, with the weights/thresholds currently embedded — these become formulas (OTA-755) + junction parameters (OTA-754).
6. **Callers (for OTA-756 only).** `grep -rn "directional_engine\|fitness_score" app/` — list every caller. Confirm the directional **route** still calls `directional_engine.py` (i.e. OTA-765 has not yet swapped it). This determines whether OTA-756 can close in this run (it cannot, until OTA-765 lands).
7. **Registration site.** Determine where the adapter/strategy is registered. If shared with Terminal A, flag and plan to sequence.

**STOP. Report Phase 0 findings, both gate verdicts, the fitness_score decomposition, and the OTA-756 caller status. Wait for Don.**

---

## OTA-753 — Scope: adapter package and thesis-to-candidate interface
Create `app/ota_adapters/directional/` with `DirectionalAdapter` implementing the §5 contract. Inputs: thesis (ticker, direction, conviction) + Schwab chain via `_shared/`. Output: one candidate per (structure, strikes, expiry) compatible with the thesis. Publish the input catalog the directional rule library (OTA-755) consumes; engine validates it at startup. Reuse `_shared/` — no duplication.

**OTA-753 — Acceptance** (derived from the Work body): package imports cleanly; the three §5 methods exist with the §5.2 signature; against a fixture thesis the adapter yields one candidate per compatible (structure, strikes, expiry); `grep` proves no Schwab/B-S re-implementation inside `directional/`; the catalog passes startup validation.

**OTA-753 — Out of scope:** scoring formulas (OTA-755); strategy rows (OTA-754); route wiring (OTA-765).

**STOP-AND-REPORT gate after OTA-753.**

---

## OTA-754 — Scope: define the directional strategy(ies) and junction rows
Add the directional strategy(ies) to the Strategies tab with junction rows. **Decision to make and record:** a single strategy ("which structure best fits this thesis") vs several (one per thesis-type). Whichever is chosen, every rule binding, weight, `evaluation_order`, `stop_if_fail`, `score_penalty`, and verdict band lives in config — no strategy-identity branching in code.

**OTA-754 — Acceptance:** the single-vs-multiple decision is stated with rationale; strategy row(s) + junction rows exist in the runtime tables; verdict bands are set in config; the engine constructs the strategy at startup with no code change required to add or reweight a rule.

**OTA-754 — Out of scope:** the formula implementations themselves (OTA-755).

**STOP-AND-REPORT gate after OTA-754.**

---

## OTA-755 — Scope: migrate the fitness_score math into registered formulas
Decompose `fitness_score` (from `directional_engine.py`, per the Phase 0 decomposition) into atomic scoring criteria, each a pure formula `(named_values, params) -> float in [0, 100]` under `app/options_rules/directional/`. Junction rows (OTA-754) supply the weights; no weights/thresholds remain as code literals. Each formula is reachable by its `formula:<name>` reference and startup validation confirms it is registered.

**OTA-755 — Acceptance:** every component of the old `fitness_score` maps to a registered formula; running the directional strategy through the engine on a fixture thesis reproduces the old ranking/verdict within an agreed tolerance (document intentional divergences); startup validation passes for all `formula:<name>` references; `grep` shows no weight/threshold literals left in directional code paths.

**OTA-755 — Out of scope:** deleting `directional_engine.py` (OTA-756); swapping the route (OTA-765).

**STOP-AND-REPORT gate after OTA-755.** *(This is the natural commit boundary for the feature's buildable scope — OTA-753 + OTA-754 + OTA-755.)*

---

## OTA-756 — Scope: retire `directional_engine.py` — AUTHOR ONLY, DO NOT CLOSE
Delete `app/analysis/directional_engine.py` **once the directional route calls the engine instead of `fitness_score`** — i.e. once **OTA-765** (Wave-4 route wiring) has landed and removed the last caller. Acceptance for the eventual close: `grep -rn "directional_engine" app/` returns no hits except legitimate references to the generic engine package, and no caller remains.

**OTA-756 — In this run:** Phase 0 step 6 will show the route still imports `directional_engine.py` (OTA-765 not yet done). Therefore: **do not delete the file.** Instead, leave a `# TODO(OTA-756): delete after OTA-765 removes the route caller` marker at the top of `directional_engine.py`, and report that OTA-756 remains open pending OTA-765. Do not transition or close OTA-756.

**OTA-756 — Out of scope (and why):** the route swap is OTA-765's job, not this feature's. Deleting the file before OTA-765 lands breaks the live directional route.

---

## Verification steps (buildable scope: OTA-753–755)
1. `python -c "import app.ota_adapters.directional"` and `python -c "import app.options_rules.directional"` succeed.
2. `grep -rn "BlackScholes\|black_scholes\|schwab" app/ota_adapters/directional/` shows only `_shared/` imports.
3. Engine startup validation passes: directional catalog (OTA-753) + every `formula:<name>` from OTA-755 resolve.
4. Directional strategy run on a fixture thesis reproduces the legacy `fitness_score` ranking within tolerance (OTA-755), divergences annotated.
5. `directional_engine.py` is **still present** with the OTA-756 TODO marker; OTA-765 caller status reported.
6. **Post-Build QA Gate** (CLAUDE.md): cross-cutting backend extraction touching scoring → recommend **Level 2** (analysis-layer suite + targeted exercise of the directional comparison). State the level in the commit body.

## Commit instruction
**"I have been instructed to commit. Do you approve? (yes / no)"**
One commit covers OTA-753 + OTA-754 + OTA-755 after the OTA-755 parity gate. **OTA-756 is NOT in this commit** — it stays open until OTA-765 lands. Don commits manually.

## Coordination footer
**STOP until OTA-713 commits `app/ota_adapters/_shared/` and OTA-695/OTA-702 land** before Phase 1. **OTA-756 is blocked downstream by OTA-765** (Wave-4 route wiring) — author it, leave the TODO marker, do not close. After this feature commits, this terminal is **Independent** of Terminal A; nothing further queued here until OTA-765.

## Commit message template (if committing)
```
OTA-752 OTA-753 OTA-754 OTA-755 feat: directional comparison adapter + rule library (§5 contract, _shared reuse, fitness_score migrated to registered formulas)
```
*(OTA-756 deliberately omitted — it remains open pending OTA-765.)*
