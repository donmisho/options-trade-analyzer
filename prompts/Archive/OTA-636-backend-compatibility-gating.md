# OTA-636 — Backend: enforce strategy-structure compatibility at scoring entry

## Terminal context
- This terminal: Terminal A (single-stream — W1 of routing-fix build schedule)
- Concurrent terminals: none
- Cross-terminal dependencies: none — this Story is the foundation. OTA-637, OTA-645, OTA-649, OTA-650, OTA-651 all wait on this commit.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
```

Plus, before editing anything in `app/analysis/`:

```
cat app/analysis/strategy_definitions.py
cat app/analysis/strategy_scorer.py
```

And the two scanner files (find with `Get-ChildItem -Recurse app/analysis -Filter "*scanner*.py"` from PowerShell, or `find app/analysis -name "*scanner*.py"` from bash).

## Relevant Context — Do Not Deviate Without Escalation

**Source: business-rules.md → Strategy-Structure Compatibility**
The canonical compatibility matrix:

| Strategy | Compatible structures |
|---|---|
| Steady Paycheck (SP) | BULL_PUT_CREDIT, BEAR_CALL_CREDIT |
| Weekly Grind (WG)    | BULL_PUT_CREDIT, BEAR_CALL_CREDIT (DTE ≤ 14) |
| Trend Rider (TR)     | BULL_CALL_DEBIT, BEAR_PUT_DEBIT |
| Lottery Ticket (LT)  | SINGLE_LONG_CALL, SINGLE_LONG_PUT |

This table is the single source of truth. The `compatible_structures` field added to each strategy definition MUST match this exactly. If business-rules.md differs from the table above at read time, business-rules.md wins — read it before editing strategy_definitions.py.

**Source: architecture-plan.md → The Strategy System**
The scorer is the enforcement point. The Foundry prompt's structural compatibility check remains in place as defense in depth — do not remove it.

**Source: CLAUDE.md → Async-first Azure rule**
All Azure SDK calls in async FastAPI handlers must use `azure.identity.aio` async variants exclusively. Sync credential calls block the event loop and only manifest in production. If the modified code paths touch any Azure provider, audit for sync credential usage.

**Source: CLAUDE.md → Scoring conventions**
Scores 0–100 formatted `##.00`. The null-score case is `null`, not `0` or `0.00` — the distinction is load-bearing for the frontend's pill-rendering logic (OTA-637).

## Scope

This Story has one purpose: make incompatible (trade, strategy) pairs return `None` at the scorer entry, and propagate that signal cleanly through the surrounding helpers and scanners.

### Phase 1 — Read-only diagnostic (mandatory stop-and-report)

1. `cat` every file in Required Reading above.
2. Inspect `app/analysis/strategy_definitions.py` and confirm the structure of strategy definitions. Report: do strategies currently have any kind of compatibility field, or is this the first introduction?
3. Inspect `app/analysis/strategy_scorer.py` and find the function-entry point used by callers. Report the function name and signature.
4. Inspect both scanners (verticals + long-options) and find where they decide which spread types to request from the broker. Report the current logic — is it driven by `trade_structure`, by strategy, by a config dict, or hardcoded?
5. Find where `best_fit` is currently assembled. Report the file path and a 5-line summary of the current selection logic.

**STOP at the end of Phase 1.** Report findings to Don. Do not edit any file. Wait for "proceed to Phase 2" before continuing.

### Phase 2 — Implementation

#### 2a. `app/analysis/strategy_definitions.py`
- Add `compatible_structures: List[str]` (or the type matching the existing definition style) to each of the four strategy definitions.
- Populate from the matrix in Relevant Context above.
- For Weekly Grind, the DTE ≤ 14 constraint is a separate gate, not a structure restriction — the `compatible_structures` field is `["BULL_PUT_CREDIT", "BEAR_CALL_CREDIT"]` for both SP and WG; the DTE gate stays where it already lives.
- Single source of truth. Do not duplicate into a separate constants file or into the scanner.

#### 2b. `app/analysis/strategy_routing.py` (new file)
Create a new module to hold the routing predicates. This keeps the predicate isolated from the scorer's broader scoring concerns.

```python
def get_compatible_strategies(structure: str) -> List[str]:
    """Inverse lookup: given a trade_structure, return the strategy keys that accept it."""

def is_compatible(strategy_key: str, structure: str) -> bool:
    """Convenience predicate. Reads from strategy_definitions; no duplication."""
```

Both functions read from `strategy_definitions.py`. No hardcoded duplicate of the matrix.

#### 2c. `app/analysis/strategy_scorer.py`
- At the scoring-entry function: if `trade.structure not in strategy.compatible_structures`, return `None` immediately.
- Update the return-type annotation to reflect nullability (`Optional[ScoreResult]` or whatever the existing return type is).
- Update the docstring to document the null-return contract.
- Do NOT return `0.0` for incompatible pairs. The distinction between "structurally incompatible" (None) and "compatible but failed gates" (0.0 or low score) is load-bearing.

#### 2d. Scanners (verticals + long-options)
- Replace OTA-451's pattern of deriving `spread_types` from `trade_structure × strategy` with a cleaner inversion: when a strategy is active, request only the structures in `strategy.compatible_structures`.
- The mapping is: `strategy → strategy.compatible_structures → spread_types_to_request`.
- Both scanners use `get_compatible_strategies` or `is_compatible` from `strategy_routing.py`. No duplication of the matrix in scanner code.

#### 2e. `best_fit` assembly
- Locate the current `best_fit` selection logic (reported in Phase 1).
- Update it to pick the highest-scoring strategy **among non-null scores only**.
- If all four strategies returned `None` (defensive case; should not occur for well-formed candidates after the scanner pre-filter), set `best_fit = None` and populate `best_fit_reason` with an explanatory string.

#### 2f. Foundry prompt / SKILL.md audit
- Locate the active strategy-scoring SKILL.md (likely under `app/skills/strategy_scoring/` or similar; find with PowerShell `Get-ChildItem -Recurse app/skills -Filter SKILL.md`).
- Do NOT remove the existing structural compatibility check inside the prompt — it stays as defense in depth.
- Read the prompt for any logic that presumes "try to find a fit across all four strategies" — that assumption is now invalid. If present, flag in your summary and recommend a follow-up subtask. Do NOT edit the prompt in this Story; that's a separate concern under OTA-507.

### Phase 3 — Tests

Add tests under `tests/analysis/test_strategy_routing.py` (new file):

1. **Compatibility matrix coverage:** 4 strategies × all known structures. Each cell asserts `is_compatible(strategy, structure)` matches the matrix.
2. **Scorer null contract:** scoring a `BEAR_PUT_DEBIT` against Steady Paycheck returns `None`. Scoring a `BULL_PUT_CREDIT` at 30 DTE against Steady Paycheck returns a non-null numeric score.
3. **Scanner request shape:** when active strategy is Trend Rider, scanner request payload includes `BULL_CALL_DEBIT` and `BEAR_PUT_DEBIT` and excludes credit structures.
4. **best_fit non-null selection:** given mock scores `{SP: None, WG: None, TR: 78.40, LT: None}`, `best_fit` returns `"trend_rider"`. Given all-None, `best_fit` returns `None` with populated `best_fit_reason`.

## Acceptance criteria

- [ ] `compatible_structures` present on all four strategy definitions, matching the business-rules.md matrix exactly.
- [ ] `app/analysis/strategy_routing.py` exists with `get_compatible_strategies()` and `is_compatible()`, both reading from `strategy_definitions.py`.
- [ ] `strategy_scorer.py` returns `None` (not `0` or `0.0`) for incompatible pairs.
- [ ] Verticals and long-options scanners request only compatible structures per active strategy.
- [ ] `best_fit` selects highest-scoring among non-null; returns `None` with reason when all-None.
- [ ] New tests pass (4 categories above).
- [ ] AMZN regression suite passes unchanged.
- [ ] MSFT anchor regression endpoint (OTA-284) passes unchanged.
- [ ] Foundry SKILL.md structural compatibility check is still in place (defense in depth).

## Out of scope

- Frontend rendering changes — OTA-637.
- Verdict/narrative consistency tests — OTA-645.
- Security Strategies grid changes — OTA-649.
- Positions surface changes — OTA-650.
- Path B grouping — OTA-651.
- Strategy taxonomy renaming.

## Verification steps

1. Run the new test file: `pytest tests/analysis/test_strategy_routing.py -v`
2. Run the full analysis test suite: `pytest tests/analysis/ -v`
3. Run AMZN regression: `pytest tests/regression/test_amzn_regression.py -v` (or the project's documented regression command).
4. Run the MSFT anchor endpoint test (OTA-284).
5. Manually `curl` (or use Invoke-RestMethod in PowerShell) the verticals endpoint with strategy=trend-rider for MMM — confirm response includes only debit structures.
6. Manually evaluate a MMM Bear Put — confirm scorer returns a score for TR (non-null), None for SP/WG.

## Commit instruction

I have been instructed to commit. Do you approve? (yes / no)

## Coordination footer

OK to continue to **OTA-637-frontend-pills-bestfit-verdict.md**

## Commit message template

```
OTA-636 feat: enforce strategy-structure compatibility at scoring entry

- Add compatible_structures field to strategy definitions (SP/WG/TR/LT)
- New module app/analysis/strategy_routing.py with is_compatible() and
  get_compatible_strategies() predicates
- strategy_scorer.py returns None for incompatible pairs (not 0.0)
- Verticals/long-options scanners request only compatible structures
  per active strategy (supersedes OTA-451's Option C wedge)
- best_fit selects highest non-null score; None with reason when all-None
- Tests cover 4×N matrix, scorer null contract, scanner request shape,
  best_fit non-null selection
- Foundry SKILL.md structural compatibility check retained as defense
  in depth (no change)

Supersedes OTA-451.
```
