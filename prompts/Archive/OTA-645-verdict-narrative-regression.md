# OTA-645 — Bug: verdict/narrative inconsistency regression coverage

## Terminal context
- This terminal: Terminal A (single-stream — W3 of routing-fix build schedule)
- Concurrent terminals: none
- Cross-terminal dependencies: OTA-636 and OTA-637 must be committed before this Story starts. Both close the symptom; this Story locks in regression coverage so the contradiction cannot return on a different code path.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/bugfix.md
```

Plus, before adding test fixtures:

```
cat app/analysis/strategy_scorer.py
cat app/analysis/strategy_routing.py
```

And the verdict-classification path. Find it with PowerShell: `Get-ChildItem -Recurse app/analysis -Filter "*.py" | Select-String "verdict\|EXECUTE\|WAIT\|PASS"`.

## Relevant Context — Do Not Deviate Without Escalation

**Source: this Story's original description (OTA-645)**
Reproducer (pre-OTA-636): a BEAR_PUT_DEBIT trade evaluated through Steady Paycheck produced banner verdict `WAIT` and narrative opener `PASS — structural mismatch`. Two surfaces, one trade, contradictory verdicts.

Probable cause documented in the original ticket: verdict classifier and narrative generator read the trade through different lenses. Verdict classifier bucketed by total score (which fell into WAIT range); narrative generator fired structural compatibility first and produced PASS prose. No short-circuit between them.

**Source: OTA-636 (committed before this Story)**
The contradiction is now structurally impossible for the originating case: the scorer returns `None` for BEAR_PUT_DEBIT + Steady Paycheck at pipeline entry, so there is no SP score to bucket and no narrative to produce against SP for that trade. The trade is filtered before either surface receives it.

**Source: OTA-637 (committed before this Story)**
The verdict pill and narrative verdict word read from the same backend field. A pill/prose split on the same `verdict` object cannot occur.

**Source: this Story's surviving scope**
What remains after 636+637 is regression coverage. The original defect (verdict and narrative reading from different sources) is closed, but the *test fixture* that locks it shut needs to exist. The fixture is what prevents a future refactor from silently reintroducing the contradiction on a different code path.

## Scope

This Story is now narrowly scoped to regression coverage. No production-code edits expected unless Phase 1 surfaces a leak that 636 or 637 missed.

### Phase 1 — Read-only verification (mandatory stop-and-report)

1. `cat` every file in Required Reading.
2. Re-run the original reproducer manually:
   - In Phase 1's read-only mode, this is a curl/Invoke-RestMethod call against the local dev backend or a print-statement trace through the scorer for a BEAR_PUT_DEBIT + Steady Paycheck candidate.
   - Confirm the scorer returns `None`, the spread is filtered out of any SP-context response, and no verdict is computed against SP for that spread.
3. Locate the verdict-classification path. Read it. Confirm there is no code path that can produce a verdict object where `verdict.verdict` ("PASS/WAIT/EXECUTE") and `verdict.narrative` start with disagreeing verdict words.
4. Inspect the existing test fixtures under `tests/analysis/` and `tests/regression/`. Report whether any existing test covers the verdict/narrative consistency invariant. If yes, report the file and what it covers. If no, the new fixture in Phase 2 has no overlap.

**STOP at the end of Phase 1.** Report findings to Don. If the manual reproducer still produces a contradiction post-636/637, this is a leak — escalate before proceeding. If the manual reproducer is clean (scorer returns None, no SP verdict on Bear Put), proceed to Phase 2.

### Phase 2 — Regression test fixture

Add tests under `tests/regression/test_verdict_narrative_consistency.py` (new file):

#### 2a. Structural-incompatibility short-circuit
For each (debit structure, credit-focused strategy) pair below, assert that the scorer returns `None` and no verdict object is produced:

| Structure | Strategy | Expected scorer return |
|---|---|---|
| BEAR_PUT_DEBIT | Steady Paycheck | None |
| BEAR_PUT_DEBIT | Weekly Grind | None |
| BULL_CALL_DEBIT | Steady Paycheck | None |
| BULL_CALL_DEBIT | Weekly Grind | None |
| BULL_PUT_CREDIT | Trend Rider | None |
| BEAR_CALL_CREDIT | Trend Rider | None |
| BULL_PUT_CREDIT | Lottery Ticket | None |
| SINGLE_LONG_CALL | Steady Paycheck | None |
| SINGLE_LONG_PUT | Trend Rider | None |

This is the inverse coverage of OTA-636's positive-case tests. Both directions need fixtures so a future refactor can't reintroduce a leak by accident.

#### 2b. Verdict object consistency invariant
For every spread that *does* produce a verdict (i.e., a compatible structure that passes the scorer):
- `verdict.verdict` is one of `{"EXECUTE", "WAIT", "PASS"}`.
- The first word (or first capitalized token) of `verdict.narrative` matches `verdict.verdict`.
- This is a property-based test — generate or fixture 20+ compatible (spread, strategy) pairs and assert the invariant on each.

#### 2c. End-to-end fixture: MMM Bear Put on production response shape
- Mock or capture the actual API response for the MMM 146/136 Bear Put scenario (from the original screenshots).
- Assert: `eligible_strategies = ["trend_rider"]` (plus LT if compatibility permits — confirm against business-rules.md).
- Assert: `best_fit = "trend_rider"`.
- Assert: there is no SP entry in `eligible_strategies` and no narrative produced against SP.
- This fixture is the canary for the originally-reported user-visible defect.

### Phase 3 — Documentation

- Add a one-line entry in `bugfix.md` referencing OTA-645 and the regression test file.
- No SoT doc edits beyond `bugfix.md`.

## Acceptance criteria

- [ ] `tests/regression/test_verdict_narrative_consistency.py` exists with the three test categories above.
- [ ] All structural-incompatibility cells from the 2a matrix assert `None`.
- [ ] The verdict consistency invariant in 2b is enforced across 20+ compatible (spread, strategy) pairs.
- [ ] The MMM Bear Put canary fixture from 2c passes.
- [ ] `bugfix.md` carries a one-line OTA-645 reference.
- [ ] Test suite green: `pytest tests/regression/test_verdict_narrative_consistency.py -v`.
- [ ] Full regression suite green: `pytest tests/regression/ -v`.

## Out of scope

- Production-code edits (unless Phase 1 surfaces a leak; escalate if so).
- Changing the verdict enum or adding new verdict types (separate concern, OTA-515 covers WAIT_FOR_EARNINGS).
- Touching the narrative-generation prompt (Foundry SKILL.md).
- Frontend regression tests (covered functionally by OTA-637's manual verification).

## Verification steps

1. Run the new test file in isolation: `pytest tests/regression/test_verdict_narrative_consistency.py -v`
2. Run the full regression suite: `pytest tests/regression/ -v`
3. Manually re-evaluate the original reproducer (MMM Bear Put through Steady Paycheck via the local dev backend). Confirm the API returns no SP entry in `eligible_strategies` and no verdict object naming SP.
4. Re-export the same trade via the OTA-621 Export MD path. Confirm banner and narrative both reflect the absence of an SP verdict (or both name Trend Rider if that's how the export presents `best_fit`).

## Commit instruction

I have been instructed to commit. Do you approve? (yes / no)

## Coordination footer

OK to continue to **OTA-649 / OTA-650 / OTA-651** — these three are independent of each other and may be sequenced in any order. Recommend running them in the order 649 → 650 → 651 in a single terminal to avoid `web/src/client.js` merge conflicts (see BUILD-SCHEDULE-routing-fix.md).

## Commit message template

```
OTA-645 test: regression coverage for verdict/narrative consistency

- New tests/regression/test_verdict_narrative_consistency.py
- Structural-incompatibility short-circuit: 9 (structure, strategy)
  cells assert scorer returns None
- Verdict consistency invariant: verdict.verdict == first word of
  verdict.narrative for 20+ compatible (spread, strategy) pairs
- MMM Bear Put canary fixture: asserts eligible_strategies=[trend_rider],
  best_fit=trend_rider, no SP entry anywhere in response
- bugfix.md updated with OTA-645 reference

Closes the verdict/narrative split documented in the original ticket.
Depends on OTA-636 and OTA-637; both must be live for tests to pass.
```
