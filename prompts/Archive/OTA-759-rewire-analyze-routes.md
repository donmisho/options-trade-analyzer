# OTA-759 — Rewire /analyze/* routes to call the engine

*(Carries the inherited `app/api/` band-literal sweep from cancelled OTA-761 — see Scope §B.)*

## Terminal context
- This terminal: Terminal A
- Concurrent terminals: none
- Cross-terminal dependencies: none. Touches `app/api/evaluation_routes.py` and the `/analyze/*` route module(s) only. Do **not** touch `app/main.py`, `app/database.py`, or `web/src/api/client.js` — if the work appears to require any of these, STOP and escalate.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/insight_engine.md
cat claude_context/insight_engine-migration-plan.md
```

Domain = architecture/patterns + scoring/gates (route wiring + verdict-band removal). Per the per-domain required-reading table in `CLAUDE.md`, that pulls CLAUDE.md + architecture-plan.md + business-rules.md; `insight_engine*.md` added because this Story is governed by the engine-invocation contract and the LLM-precedence principle.

## Relevant Context — Do Not Deviate Without Escalation

**Source: OTA-759 body + OTA-757 (App-side wiring) body — engine-invocation pattern.**
Each `/analyze/*` endpoint becomes a thin engine invocation, in this exact shape:
`parse request → resolve strategy id → adapter.produce_candidates(...) (options_chain adapter, F3) → engine.evaluate(candidates, strategy_id, source_app_id="OTA") → return ResultRecord(s)`.
No filtering, scoring, gating, or verdict logic remains in the route — only request parsing, the adapter call, the engine call, and response shaping. Persistence happens **inside** `engine.evaluate(...)` via the injected sink (OTA-758) — the route does not persist anything itself.
*(The signatures above are the contract as documented; verify the exact `produce_candidates(...)` and `engine.evaluate(...)` signatures against live code in Phase 0 before wiring — do not assume.)*

**Source: `insight_engine.md` §2.6 — LLM precedence.**
The engine runs to completion (gates → scoring → verdict) BEFORE any Claude narrative call. Claude is invoked only on survivors, only to narrate an already-decided verdict — never to discover a rule violation. If any `/analyze/*` route currently calls Claude inside or before the rule path (a "scoring sandwich"), Claude must be moved strictly downstream of the engine verdict.

**Source: OTA-761 body (inherited residual scope) — band-literal removal.**
Delete the literal verdict-band thresholds in `_assign_verdict` (`app/api/evaluation_routes.py:175–182`, the hardcoded 70/50). Verdicts come from the strategy's `verdict_band_set` in engine config, applied by the engine's Phase-7 band lookup — never by app code. The residual sweep assigned to this Story (per OTA-761's 06-11 cancel note): **no orphaned `_assign_verdict`, and no band-number literal in any remaining route under `app/api/`.** OTA-759 removes the last `_assign_verdict` caller.

**Source: `insight_engine.md` — fail-closed principle.**
Strategy resolution and engine invocation fail-closed: explicit errors, never a hardcoded fallback verdict or default band. If a strategy id cannot be resolved, raise — do not substitute a default.

**Source: OTA-758 body — sink semantics (for awareness; do NOT re-implement).**
The injected sink writes bronze fire-and-forget: a persistence failure is logged and swallowed, and the evaluate response still returns. 759 relies on this; it does not add its own persistence or error handling around it.

## Scope

### Phase 0 — Read-only discovery (HARD STOP — GO/NO-GO gate)
No edits. Investigate and report:

1. **Route inventory.** Enumerate every `/analyze/*` endpoint and the file(s) they live in. For each, list the inline rule / gate / scoring / verdict logic currently present.
2. **Band-literal + `_assign_verdict` sweep.** `grep` across `app/api/` for: the `_assign_verdict` definition and every caller; and any band-number literal (70, 50, or any threshold constant used for verdict assignment). Produce the exact file:line list. Confirm whether `/analyze/*` holds the **last** `_assign_verdict` caller (OTA-760 should already have removed the `/evaluate/structured` one).
3. **Contract verification.** Read the live signatures for the options_chain adapter's `produce_candidates(...)` and `engine.evaluate(...)`. Confirm the engine is constructed with the injected sink at app startup (OTA-758 wiring) and that routes can obtain the engine instance. Confirm the strategy-id resolution path that maps a request to a strategy id.
4. **Hydration check (deploy-order gate).** Confirm the engine config hydrates in this environment — i.e., `load_config` succeeds. If hydration fails because the OTA-836 reseed is not yet deployed here, that is a **NO-GO**: 759's verification cannot pass against a non-hydrating engine. Report it as the blocker rather than proceeding.
5. **Claude-call audit.** Identify any Claude/LLM call reachable from `/analyze/*` and whether it currently sits upstream of, or interleaved with, the rule path (§2.6 violation).

**Then STOP and report A–E:**
- **A.** `/analyze/*` route + inline-logic inventory.
- **B.** `_assign_verdict` + band-literal file:line list, and whether 759 holds the last caller.
- **C.** Verified `produce_candidates` / `engine.evaluate` signatures + sink-injection + strategy-resolution path.
- **D.** Hydration result (GO if `load_config` succeeds here; NO-GO + reason if not).
- **E.** GO / NO-GO recommendation with rationale.

Do not proceed to Phase 1 without Don's GO.

### Phase 1 — Rewire `/analyze/*` (after GO)
For each `/analyze/*` route, reduce it to the thin engine-invocation pattern from Relevant Context: parse → resolve strategy id → `adapter.produce_candidates(...)` → `engine.evaluate(candidates, strategy_id, source_app_id="OTA")` → shape response from the returned `ResultRecord(s)`. Remove all inline rule/gate/scoring/verdict logic. Move any reachable Claude narrative call strictly downstream of the engine verdict (survivors only). Strategy resolution fails closed.

### Phase 2 — `app/api/` band-literal sweep (inherited from OTA-761)
Remove the `_assign_verdict` function and every band-number literal under `app/api/`. Verdict assignment is the engine's job (Phase-7 band lookup against per-strategy `verdict_band_set`). After this phase, no `_assign_verdict` and no band-threshold literal remains anywhere in `app/api/`.

## Acceptance criteria
- `/analyze/*` routes contain no rule, gate, scoring, or verdict logic — only request parsing, the adapter call, the engine call, and response shaping.
- Routes pass `source_app_id="OTA"` and the resolved strategy id to `engine.evaluate(...)`.
- Removed inline logic is covered by engine config + rule libraries — no behavior silently dropped.
- `_assign_verdict` is gone; `grep` confirms no `_assign_verdict` and no band-number verdict literal remains anywhere under `app/api/`.
- Any Claude narrative call reachable from `/analyze/*` runs only after the engine verdict exists, only on survivors, and cannot alter/override/create a verdict.
- Strategy resolution fails closed (explicit error; no default verdict/band fallback).

## Out of scope
- `/evaluate/structured` — already rewired (OTA-760, Code & Test Complete).
- The persistence sink itself — OTA-758 (Code & Test Complete); 759 only relies on it.
- Engine internals, rule content, thresholds, weights, verdict bands — those live in the `engine_*` tables and rule libraries, not app code.
- Directional route wiring / legacy retire — OTA-765, OTA-756.
- Frontend strategy-config migration — OTA-821.
- `app/main.py`, `app/database.py`, `web/src/api/client.js` — do not touch.

## Verification steps
1. `grep -rn "_assign_verdict" app/api/` → no matches.
2. `grep -rn -E "\b(70|50)\b" app/api/` reviewed → no remaining verdict-band threshold literal (filter out unrelated incidental numbers and document why each remaining hit is not a band literal).
3. Each `/analyze/*` route reads as parse → adapter → `engine.evaluate(..., source_app_id="OTA")` → shape, with no inline gate/scoring/verdict.
4. Run the route/integration tests for `/analyze/*`; confirm verdicts originate from the engine and match expected bands for a known fixture (requires hydrated engine — see Phase 0 §4).
5. Confirm no Claude call precedes or interleaves with the rule path on any `/analyze/*` route.

## Commit instruction
Do **not** run `git commit`. On completion, present the full diff and the proposed commit message below; Don commits manually (the `OTA-759` prefix triggers Jira automation).

> "Phases 1–2 complete and verified. Diff and proposed commit message are ready for your review — do you approve the commit? (yes / no)"

## Coordination footer
Independent — single-terminal execution, no concurrent terminal, no downstream terminal waiting on this. Deploy-order note for Don (not for Claude Code): 759 should reach prod only after the OTA-836 reseed is live, so `/analyze/*` calls a hydrated engine.

## Commit message template (if approved)
```
OTA-759 feat: rewire /analyze/* to engine invocation; remove app-layer verdict bands (inherits OTA-761 sweep)
```

---
*References: OTA-759, OTA-757 (Feature — app-side wiring), OTA-761 (cancelled; residual sweep folded here), OTA-758 (sink), OTA-760 (sibling route, done). `insight_engine.md` §2.6, §4.3; `insight_engine-migration-plan.md` S5.2, S5.4; audit §5a #7, §5d.*
