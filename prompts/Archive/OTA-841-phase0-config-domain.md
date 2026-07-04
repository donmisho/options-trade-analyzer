# OTA-841 — Normalize OTA-762 config domain (strategy_key → hyphen, compatible_structures → lowercase) — Phase 0

## Terminal context
- This terminal: Terminal A
- Concurrent terminals: none
- Cross-terminal dependencies: none. Phase 0 is read-only — it touches nothing. Do **not** edit `scripts/seed_engine_config.py`, any `app/api/` serializer, `app/api/engine_config_store.py`, or the test fixtures in this pass.

## Required reading
Before any investigation:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/insight_engine.md
cat claude_context/insight-agent-migration-plan.md
```

`business-rules.md` + the engine docs because the value domain in question — strategy keys and compatible structures — is the canonical strategy-config domain governed by the engine-config contract. Note: the migration-plan file is `insight-agent-migration-plan.md`; any reference to `insight_engine-migration-plan.md` elsewhere is a stale filename.

## Relevant Context — Do Not Deviate Without Escalation

**Source: OTA-841 body — the defect.** `GET /api/v1/config/strategies` (the OTA-762 read endpoint) serializes engine config in the engine seed's value domain — underscore strategy keys + UPPERCASE structures — while the rest of the system is hyphen keys + lowercase structures:

| Field | OTA-762 emits | System canonical |
|---|---|---|
| `strategy_key` | `steady_paycheck` | `steady-paycheck` |
| `compatible_structures` | `["BULL_PUT_CREDIT","LONG_CALL"]` | `bull_put_credit`, `long_call` |

**Source: OTA-841 body — evidence (verify live; the reseed may have moved these line numbers or the values).** Seed: `_SCREENING_VERDICT_BANDS` keyed underscore (`scripts/seed_engine_config.py:324-345`); `strategy_key = strat["key"]` (`:381`); `compatible_structures` appended UPPERCASE (`:375-377`). Store: `app/api/engine_config_store.py` is pass-through, no normalization. Fixtures: `tests/integration/test_options_chain_adapter.py:585-587, 701-703` assert underscore + UPPERCASE.

**Source: OTA-841 body — canonical domain agreement.** `strategy_definitions.py:46`, `strategy_classifier.py:38`, `export_routes.py:149-152`, the `/analyze/*` `spread_type`, and the frontend roster all use hyphen + lowercase. The engine seed is the lone outlier.

**Source: OTA-841 body — fix-layer decision (this Phase 0's core output).**
- **Default: fix at the seed** — source keys/structures from the canonical definitions so engine config matches the rest of the system; the reseed then emits the corrected domain.
- **Fallback: normalize at the OTA-762 serializer boundary** — only if the engine matches on underscore/UPPERCASE *internally* (gate IN-lists, junction keys, `formula_ref` lookups). One boundary for all consumers, reseed-independent.
- **Forbidden: per-consumer normalization shim** — that re-creates the dual-source mirror OTA-821 exists to kill.

**Source: OTA-841 body — contract guard.** The fix's AC includes a test asserting the OTA-762 emitted domain equals the system canonical domain, so the next drift fails CI rather than a build.

## Scope — Phase 0, read-only discovery (HARD STOP — GO/NO-GO gate)

No edits. **Don ran a reseed update on 2026-06-15 — the defect may be partially or fully resolved already. Verify the current state empirically; do not assume the defect still exists.**

1. **Current emitted domain (post-reseed).** Read the OTA-762 serializer path and capture exactly what `GET /api/v1/config/strategies` now emits for `strategy_key` and `compatible_structures` (form + case) after the reseed. If a live response is obtainable, capture it; otherwise trace the serializer plus the reseeded `engine_*` values it reads. State plainly: is the domain now **canonical, partially fixed, or unchanged?**
2. **Internal-match audit.** Determine whether the engine matches on underscore/UPPERCASE *internally* — grep gate IN-list literals, junction strategy keys, `formula_ref` lookups, and every `strategy_key` consumer across the engine / pipeline / loader. The deciding question for the fix layer: **would re-sourcing the seed to hyphen + lowercase break any internal lookup?** If yes → serializer-side; if no → seed-side is safe.
3. **Join check.** Confirm whether the underscore key breaks any backend join between engine config and `strategy_definitions` by key (OTA-841 flagged this as suspected — confirm or clear it).
4. **Emission-point + boundary inventory.** List the exact seed emission points (the `:375-377`, `:381` family, re-verified against current line numbers) and the serializer boundary file:lines — so the implementation can target a single layer cleanly.
5. **Reseed implication.** State whether the recommended layer requires a reseed (seed-side rides one; serializer-side is reseed-independent). Given Don just reseeded, note whether a seed-side fix would require *another* reseed.
6. **Contract-guard location.** Identify where the domain-equality test belongs.

**Then STOP and report A–E:**
- **A.** Current post-reseed emitted domain — canonical / partial / unchanged, with evidence.
- **B.** Internal-match findings — does the engine depend on underscore/UPPER? (with the grep set)
- **C.** Seed emission points + serializer boundary file:lines.
- **D.** Recommended fix layer (seed-side default vs serializer-side fallback) + reseed implication.
- **E.** GO / NO-GO to author the implementation prompt — explicitly including the possibility that the reseed already resolved the domain and **only the contract-guard test remains**.

Do not proceed to implementation without Don's GO.

## Acceptance criteria (of this Phase 0)
- The current post-reseed emitted domain is stated empirically, not assumed.
- The fix layer is recommended with internal-match evidence (B), not asserted.
- No per-consumer shim is proposed.
- The report enables a clean GO/NO-GO and, on GO, a single-layer implementation prompt.

## Out of scope
- Any edit to seed, serializer, store, or fixtures — Phase 0 is read-only.
- OTA-762 (the read endpoint itself — shipped).
- OTA-821 (frontend consumption — unblocked *by* this fix, not part of it).
- The implementation itself — authored after GO.

## Verification steps
- The A–E report is complete and each claim cites a file:line or a captured response.
- The internal-match conclusion (B) is backed by the actual grep set, not asserted.

## Commit instruction
Read-only — no edits, no commit. STOP and present the A–E report; await Don's GO before any implementation prompt is authored.

## Coordination footer
Independent — single terminal, read-only, no downstream terminal waiting. This Phase 0 unblocks the OTA-841 implementation, which in turn unblocks OTA-821 and OTA-759.
