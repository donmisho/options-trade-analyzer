---
allowedTools:
  - Read
  - Grep
  - Glob
  - Bash
  - Edit
---

# OTA-842 — Wire /analyze/scorecard to the engine (display-only)

## ⛔ Hard gate before anything

Do **NOT** begin until **OTA-759 is committed** to `OTA-836-build-to-testable`.
First action, before any reading or editing:

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
git branch --show-current   # must be OTA-836-build-to-testable
git log --oneline -8        # an OTA-759 commit must be present
```

If the OTA-759 commit is not present, STOP and report. This Story is single-terminal sequential on `app/api/analysis_routes.py` behind OTA-759 — do not edit that file until 759 has landed.

## Terminal context
- This terminal: Scorecard terminal (analysis_routes.py owner, post-759)
- Concurrent terminals: OTA-764 may be running in another terminal (Position Monitor Agent — edits `app/api/position_routes.py`, a different file; no conflict)
- Cross-terminal dependencies: **OTA-759 must be committed first** (same file: `analysis_routes.py`). OTA-764 is independent.

## Required reading
Before any code changes:

```powershell
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/insight_engine.md
cat claude_context/UI-GUIDANCE.md
```

Then read the **post-759 current state** of the route and its scorer (never from memory — 759 refactored this file):

```powershell
# Re-read as they exist NOW; line numbers below are pre-759 and may have shifted.
# The committed file is authoritative; embedded line refs are orientation only.
```
- `app/api/analysis_routes.py` — the `/analyze/scorecard` route and `score_all_strategies`
- `app/api/analysis_routes.py` — the `/analyze/directional` loop (the reference pattern)
- whatever helper(s) OTA-759 extracted for the scan routes (you will reuse them — see Phase 0)

## Relevant Context — Do Not Deviate Without Escalation

**1 — Display-only invariant (the 842 trap; inverse of 759).**
`/analyze/scorecard` has **no operational persistence today** — the route has no db dependency (pre-759 ref: `analysis_routes.py:1438-1442`). Do **NOT** add `TradeCandidate`, `AnalyzedTrade`, or `OptionChainSnapshot` writes. The OTA-758 sink is **additive bronze audit only** and is the *only* persistence this route gains. OTA-759's invariant was "preserve operational persistence"; 842's is the mirror — "do not introduce any."
Source: OTA-759 Phase 0 §D; PO decision on record.

**2 — Adapter is the input, not `provider.get_chain`.**
All chain fetching goes through `OptionsChainAdapter.produce_candidates` (the §5 SCREENING input adapter), replacing the legacy direct `provider.get_chain` inside `score_all_strategies` (pre-759 ref: `868-929`). Same adapter `/analyze/verticals` and `/analyze/directional` already feed.
Source: OTA-759 Phase 0 §A; `options_chain/adapter.py`.

**3 — Structure-derived routing (Option 1, ratified 06-16).**
Each strategy scores only candidates whose structure matches its `compatible_structures`. Resolve dynamically off `compatible_structures` via `strategy_routing.py` — **no route→strategy table, no `if strategy_key ==` branching.** Mapping per `strategy_definitions.py:44-100`:
- `steady-paycheck`, `weekly-grind` → credit (`bull_put` / `bear_call`)
- `trend-rider` → debit (`bull_call` / `bear_put`)
- `lottery-ticket` → naked (`long_call` / `long_put`)
The adapter builds all of these so each of the four strategies has compatible candidates to score.
Source: this session's routing decision; `strategy_definitions.py`.

**4 — Single-path / reuse 759's machinery.**
OTA-759 extracted the engine evaluate-loop for `analysis_routes.py` (per-candidate compatible-strategy resolution, `ResultRecord`→display mapping, pick-best-by-(verdict tier, score)). 842 **reuses** those helpers. Do not introduce a second engine call site or a parallel scoring path. If 759 did not extract a reusable helper for a piece you need, extract it cleanly so both the scan routes and scorecard share one path — do not copy-paste.
Source: insight_engine.md single-path rule.

**5 — Absolute composite replaces min-max (accepted shift).**
The engine produces **absolute** per-candidate weighted scores. The legacy scorecard returned a **min-max relative** composite across the candidate set (`_scorer_normalize`, pre-759 ref `506-521`). The displayed number's *meaning* changes. This is the intended end-state and is **accepted** (PO). The AMZN/MSFT before/after delta is *expected*; any **other** unexplained change is a regression.
Source: OTA-759 Phase 0 §D; PO decision on record.

**6 — Canonical keys, fail-closed.**
Screening keys are canonical hyphen post-OTA-841 (`steady-paycheck` / `weekly-grind` / `trend-rider` / `lottery-ticket`). Unknown keys fail closed → **422** (the directional guard, pre-759 ref `1351-1361`). No shim, no hyphen↔underscore translation.
Source: OTA-841; OTA-759 Phase 0 §E.

**7 — Pick semantics.**
Best by **(verdict tier, score)** — the `/analyze/directional` loop (pre-759 ref `1404-1418`). One best candidate **per strategy** (scorecard shows all four), not one across all.
Source: OTA-759 Phase 0 §A/§D.

**8 — Branch discipline.**
Stay on `OTA-836-build-to-testable`. Do not merge to `main` or deploy ahead of the 836/841 line.
Source: OTA-759 Phase 0 §E.

---

## Phase 0 — Read-only discovery (HARD STOP before any edit)

No edits in this phase. Confirm the gate, then answer all six. Stop and report; await GO.

1. **Gate:** OTA-759 commit present on `OTA-836-build-to-testable`? (git log evidence.) If not — STOP.
2. **Reusable seam:** Name the helper(s) OTA-759 left in `analysis_routes.py` for (a) candidate→compatible-strategy resolution, (b) `ResultRecord`→display mapping, (c) pick-best-by-(verdict tier, score). State exactly which 842 will reuse. If any piece wasn't extracted, say so and propose the clean shared extraction.
3. **No-persistence confirm:** Verify the post-759 `/analyze/scorecard` path still performs no operational-persistence writes (no `TradeCandidate` / `AnalyzedTrade` / `OptionChainSnapshot`). Quote the route's db posture.
4. **Frontend contract:** Identify the live (mounted) scorecard consumer, the fields it reads, and — critically — whether it hard-depends on the min-max fields (`norm_min` / `norm_max` or equivalent) that the absolute shift removes. Clean rebuild, or frontend-contract touch?
5. **Hydration:** Confirm the four SCREENING `rule_sets` hydrate on the post-836/841 reseeded dev engine (`load_config` VALID; `steady-paycheck` / `weekly-grind` / `trend-rider` / `lottery-ticket` present in `config.rule_sets`).
6. **Routing reuse:** Confirm `strategy_routing.py` exposes the structure→strategy resolution 842 needs without a new branch table.

**Report format (A–E):**
- A. Ticket + title
- B. Objective / system impact (1–2 lines)
- C. Discovery points (the six above, 10–15 words each)
- D. Decision points — for each, your recommendation at ≥85% confidence, or open it for discussion below that bar. Expected open items: frontend min-max dependency (D-4), any helper that needs fresh extraction (D-2).
- E. **STOP.** "Phase 0 complete — awaiting GO to implement."

---

## Scope (Phase 1 — after GO)

Rewire `/analyze/scorecard` to score via the engine:
- Fetch candidates through `OptionsChainAdapter.produce_candidates` (drop the direct `provider.get_chain` path in `score_all_strategies`).
- For each of the four strategies, run `evaluate()` over its structurally-compatible candidates (reuse 759's resolver), pick best by (verdict tier, score).
- Rebuild the scorecard response from engine output (absolute composite; additive per-candidate verdict), preserving the fields the live frontend consumer reads (per Phase 0 §4).
- Pass the OTA-758 sink to `evaluate()` as **additive bronze only**.
- Retire the legacy scorecard scorers from the route path (`score_all_strategies`, `_score_credit_spread_strategy`, `_score_long_option_strategy`, `_scorer_normalize`) — remove or quarantine so no engine call routes through them.

## Acceptance criteria
- `/analyze/scorecard` scores all four strategies via engine `evaluate()` over `OptionsChainAdapter` candidates.
- No legacy scorer (`score_all_strategies` / `_score_credit_spread_strategy` / `_score_long_option_strategy` / `_scorer_normalize`) is reachable in the scorecard request path. (grep-clean)
- Chain fetch is via the adapter, not `provider.get_chain` directly.
- Per-strategy pick = best by (verdict tier, score); strategy↔candidate compatibility is structure-derived via `strategy_routing.py` (no `if strategy_key ==`).
- **Display-only preserved:** zero operational-persistence writes added; route remains db-free except the additive bronze sink.
- Response preserves the live consumer's expected fields; absolute composite replaces min-max (documented); per-candidate verdict is additive.
- Canonical hyphen keys resolve; unknown key → 422; no shim.
- AMZN + MSFT scorecard before/after captured; only the min-max→absolute delta differs.

## Out of scope
- `/analyze/verticals`, `/analyze/long-calls` (OTA-759 — landed).
- Adding any operational persistence to scorecard (it has none — do not add).
- OTA-559 `fitting_strategies` tagging (scan-route concern; scorecard does not tag).
- Repurposing the route or changing which structures it builds beyond what "score all four" requires.
- Frontend restyle. If the live consumer hard-reads min-max fields, surface at Phase 0 and map gracefully — do not silently break it, and do not redesign the surface.

## Verification steps
- `git log` shows OTA-759 committed (gate).
- grep confirms no legacy scorer in the scorecard path; no `provider.get_chain` direct call there; no `if strategy_key ==`.
- App boots; `load_config` VALID; four screening `rule_sets` hydrate.
- Run scorecard on **AMZN** and **MSFT**; capture before/after JSON. Confirm all four strategies returned, absolute composite present, verdict additive, no unexplained field change.
- Bogus strategy key (if the route accepts one) → 422.
- Live scorecard frontend surface renders without error.
- **QA Level 2** (data-model / output-shape change → AMZN regression + MSFT anchor, OTA-284). Engine math is unchanged — only the normalization layer is removed — so this is Level 2, not a Level 3 scoring-math change. If the live surface shows a verdict narrative, eyeball it on both anchors.

## Commit instruction
"I have been instructed to commit. Do you approve? (yes / no)"
Do **not** `git commit`. When both anchors are green and verification passes, present the full diff and proposed commit message and await Don's approval. (OTA-842 prefix triggers the Jira automation; Don commits manually.)

## Coordination footer
Independent — no downstream dependency. (842 is the tail of the scan-wiring wave.)

## Commit message template (if committing)
OTA-842 feat: wire /analyze/scorecard to the engine (display-only; absolute composite replaces min-max)
