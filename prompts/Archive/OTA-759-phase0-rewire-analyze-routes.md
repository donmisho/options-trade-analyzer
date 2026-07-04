# OTA-759 — Rewire the remaining inline-scoring /analyze/* routes to the engine — Phase 0

## Terminal context
- This terminal: Terminal A
- Concurrent terminals: none
- Cross-terminal dependencies: none. Phase 0 is read-only — it touches nothing. Do **not** edit `app/api/analysis_routes.py`, `app/main.py`, `app/database.py`, or `web/src/api/client.js`.

## Required reading
Before any investigation:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/insight_engine.md
cat claude_context/insight-agent-migration-plan.md
```

The engine docs because this Story is governed by the engine-invocation contract and the §2.6 LLM-precedence principle. Note: the migration-plan file is `insight-agent-migration-plan.md`; `insight_engine-migration-plan.md` is a stale name.

## Relevant Context — Do Not Deviate Without Escalation

**Source: OTA-759 body (rescoped 2026-06-15) — scope.** Wire the three remaining inline-scoring `/analyze/*` routes to the engine: `/analyze/verticals` (legacy `VerticalSpreadEngine` + OTA-559 band tagging + OTA-624 candidate persistence), `/analyze/long-calls` (legacy `LongCallEngine` + persistence), `/analyze/scorecard` (inline min-max scoring across the four strategies). These are different shapes — scan-rank-persist vs score-for-display.

**Source: OTA-759 prior Phase 0 (2026-06-15) — already-absorbed scope (do NOT re-touch).** `/analyze/directional` is already engine-backed (OTA-765). `_assign_verdict` + hardcoded 70/50 bands already removed (OTA-760). `/analyze/probability-matrix` is pure Black-Scholes — no gate/score/verdict. The `position_routes.py:1408` band literal is POSITION_HEALTH surface → OTA-764, not this Story.

**Source: OTA-759 body — verified engine contract.** Keyword-only:
```
evaluate(*, candidates, strategy_key, source_app_id, config, registry=None, adapter=None, sink=None, null_semantics=None) -> list[ResultRecord]
```
The sink is injected at startup (OTA-758) and reachable via `get_engine_runtime().sink` — `/analyze/directional` already does this. Do not assume the positional `evaluate(candidates, strategy_id, ...)` shape; it is wrong.

**Source: insight_engine.md §2.6 — LLM precedence.** The engine runs to completion (gates → scoring → verdict) before any Claude narrative call. If any target route calls Claude inside/before the rule path, Claude must move strictly downstream of the engine verdict. (Prior Phase 0 found `analysis_routes.py` imports no LLM adapter — re-confirm.)

**Source: OTA-759 body — OTA-841 dependency (hard).** All three routes resolve strategy keys; the engine's fail-closed `_unknown_keys → 422` guard rejects hyphen keys against the underscore-keyed config. **Blocked by OTA-841.** Do **not** introduce a per-route hyphen↔underscore shim — that re-creates the dual-source mirror OTA-841 / OTA-821 exist to kill. This Story consumes 841's single-boundary fix.

**Source: OTA-759 body — preservation invariant.** OTA-559 band-tagging and OTA-624 persistence behavior must be preserved — persistence via the OTA-758 sink, band assignment via engine verdict bands. **No behavior silently dropped** (the Story's core AC).

## Scope — Phase 0, read-only discovery (HARD STOP — GO/NO-GO gate)

No edits. Investigate and report:

1. **Per-route inventory + engine mapping.** For `/analyze/verticals`, `/analyze/long-calls`, `/analyze/scorecard`: enumerate the current inline gate / score / filter / persist logic, and map each piece to its engine equivalent (`adapter.produce_candidates(...)` → `engine.evaluate(..., strategy_key, source_app_id="OTA")` → verdict bands → sink). Identify the OptionsChainAdapter candidate shape each route needs.
2. **Route → strategy mapping.** Determine which engine strategy/strategies back each route (e.g., which of `steady_paycheck` / `weekly_grind` / `trend_rider` / `lottery_ticket` apply to verticals vs long-calls), and whether scorecard scores all four. Read the route code and the strategy/structure compatibility — do not guess.
3. **Behavior-preservation audit.** Identify the OTA-559 band-tagging output and the OTA-624 persistence side-effects each route produces today. Determine precisely whether engine verdict bands + the OTA-758 sink reproduce them, or where a gap exists. Flag any behavior a thin `evaluate` rewrite would silently drop.
4. **Scorecard shape verdict.** Decide whether "score four strategies for display" is expressible as per-strategy `evaluate` calls, or is a genuinely different shape that doesn't fit the per-candidate engine contract.
5. **One-Story-vs-split recommendation.** Based on 1–4, recommend whether the three routes wire under this single Story or split (the likely shape: a scan-surface wiring Story for verticals + long-calls, plus a smaller scorecard Story). Propose the concrete ticket breakdown if split.
6. **Strategy-resolution state + 841 gate.** Confirm the current strategy-key resolution path and whether keys resolve canonically post-reseed. Treat the hyphen↔underscore resolution as OTA-841-gated — report the current state but do **not** design a shim. Implementation GO is conditional on OTA-841 landing.
7. **Claude-call audit.** Re-confirm no LLM call is reachable upstream of / interleaved with the rule path on any target route (§2.6).

**Then STOP and report A–F:**
- **A.** Per-route inline-logic inventory + engine mapping.
- **B.** Route → strategy mapping.
- **C.** Behavior-preservation findings (OTA-559 tagging + OTA-624 persistence; any silent-drop risk).
- **D.** Scorecard shape verdict + one-Story-vs-split recommendation (with proposed ticket breakdown).
- **E.** Strategy-resolution state + explicit OTA-841 dependency.
- **F.** GO / NO-GO — noting GO is conditional on OTA-841 landing and the hydrated post-836 engine.

Do not proceed to implementation without Don's GO.

## Acceptance criteria (of this Phase 0)
- Each target route's inline logic is inventoried and mapped to an engine equivalent with file:line evidence.
- The OTA-559 / OTA-624 preservation question is answered concretely (reproduced how, or gap identified).
- A clear one-Story-vs-split recommendation, with a ticket breakdown if split.
- The 841 dependency is stated, with no shim proposed.

## Out of scope
- Any edit — Phase 0 is read-only.
- `/analyze/directional` (OTA-765), `_assign_verdict` / bands (OTA-760), `/analyze/probability-matrix` (math), the position literal (OTA-764).
- The OTA-841 fix itself (separate Phase 0 / Story).
- The implementation — authored after GO and after OTA-841 lands.

## Verification steps
- The A–F report is complete; each route claim cites file:line.
- The split recommendation is justified by the shape findings, not asserted.

## Commit instruction
Read-only — no edits, no commit. STOP and present the A–F report; await Don's GO. Implementation is additionally gated on OTA-841 landing.

## Coordination footer
Independent — single terminal, read-only. Implementation is blocked by OTA-841 and verification-gated on the hydrated post-836 engine. Recommend running the OTA-841 Phase 0 first, since this Story's strategy-resolution conclusion (E) depends on 841's domain confirmation.
