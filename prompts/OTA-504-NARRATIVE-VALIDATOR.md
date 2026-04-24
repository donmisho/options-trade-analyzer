---
allowedTools:
  - Bash
  - Read
  - Write
  - Edit
---

# OTA-504 — Narrative Grounding Validator (with OTA-509 + OTA-510 Subtasks)

**Wave:** AMZN April 22 Scoring Pipeline Fixes v2
**Parent Epic:** OTA-507 (Ongoing: Trade Evaluation Anomaly Resolution)
**Parent Feature:** OTA-501 (Scoring Pipeline Fixes v2 — AMZN Validation April 22)
**Subtasks:** OTA-509 (EV grounding rule), OTA-510 (SMA grounding rule)

## Context

Live AMZN 260/270 May 15 evaluation surfaced two narrative-vs-data contradictions in a single emission:

**Contradiction A (EV):** Claude's Read narrative asserted "The positive EV of $89... support the trade" while the same payload's computed EV was -5.86 (NEGATIVE).

**Contradiction B (SMA):** Claude's Read claimed "AMZN sits just below all three SMAs with mixed trend alignment" while structured inputs showed AMZN $255.36 ABOVE 20-SMA $252.52, 50-SMA $252.39, 200-SMA $251.86. Narrative also cited "SMA-21 at 257.64" — a value not in the input chart (hallucination).

Root cause: evaluation prose is generated with structured inputs available, but Claude's text output is never cross-validated against those same inputs before emission. Same hallucination class as OTA-145 (IV impact reversal).

## Implementation — two parts

### Part 1: Prompt grounding (SKILL.md update)

Update the evaluation skill to:
- Receive structured fields as named template variables: `{ev}`, `{sma_8}`, `{sma_21}`, `{sma_50}`, `{price}`, `{cushion_pct}`, `{ma_alignment}`, etc.
- Require narrative to cite values verbatim from these variables
- Prohibit narrative from asserting numerical values not in the input set
- Explicit instruction: "Do not infer SMA positioning. Use the `ma_alignment` field as authoritative."

### Part 2: Post-generation validator (new module)

Create `app/validators/narrative_grounding.py`. Runs pre-emission. Returns a list of `ValidationError` objects. One or more errors triggers regeneration (max 1 retry), then template-rendered fallback.

Two rules (one per Subtask):
- **OTA-509 — `validate_ev_grounding(narrative_text, computed_fields)`** — blocks prose contradicting the computed EV sign
- **OTA-510 — `validate_sma_grounding(narrative_text, computed_fields)`** — blocks prose contradicting SMA positioning AND catches numerical hallucinations of SMA values

Both rules compose: the parent validator runs both and merges error lists.

## Prerequisites

```bash
cat CLAUDE.md
pwd                                     # should show ...options-analyzer
venv\Scripts\activate
git status
```

If venv isn't activated or you're not in project root, STOP and report.

## Phase 0 — Read context documents

Read in full:
- `CLAUDE.md`
- `architecture-plan.md` (focus on "Claude Structured Evaluation" section, "Observability" section)
- `UI-GUIDANCE.md` (focus on Section E Claude's Read emission)

Report the current evaluation emission flow: where does `claude_read` prose get generated, where does it get cross-referenced with structured fields, where does it go to the UI. Identify the exact file and function responsible for emission.

Expected landmarks (verify):
- Skill file: `app/skills/claude-trade-agent/SKILL.md` (per house rules, all prompts live in SKILL.md)
- Evaluation route: `app/api/evaluation_routes.py` (per architecture-plan.md)
- Claude adapter: likely `app/providers/anthropic_adapter.py` or `foundry_adapter.py`

**STOP and report:**
- Exact file path where narrative emission happens
- Exact function name that returns the structured evaluation payload
- Whether that function already passes structured fields alongside the prose (it probably does — we just need to validate cross-consistency before returning)

Wait for confirmation before Phase 1.

## Phase 1 — Design the validator module

Before writing any validator code, propose the module structure as a small design note. Show:

1. The `ValidationError` dataclass (fields: `code: str`, `message: str`, `field_context: str`)
2. The public entry point signature:
```python
   def validate_narrative(
       narrative_text: str,
       computed_fields: EvaluationFields,
   ) -> list[ValidationError]:
       """Run all grounding rules. Empty list = narrative is grounded."""
```
3. How individual rules register (module-level list of rule functions, or class with methods, or dispatch dict — pick what matches existing codebase conventions)
4. Where regeneration is triggered from (evaluation_routes.py or the adapter layer — depends on Phase 0 findings)
5. The retry/fallback policy: max 1 regeneration, then template fallback (define what the fallback text looks like — e.g., "Structured evaluation complete. See computed fields for details. Narrative unavailable this cycle.")

**STOP and report** the design note. Wait for approval before Phase 2.

## Phase 2 — Implement OTA-509 (EV grounding rule)

Create `app/validators/narrative_grounding.py` with the module skeleton from Phase 1 plus the first rule:

```python
import re

def validate_ev_grounding(narrative_text: str, computed_fields) -> list[ValidationError]:
    errors = []
    if computed_fields.expected_value < 0:
        # Pattern matches "positive EV", "favorable EV", or "EV of $XX" / "EV of 89"
        if re.search(r"positive\s+ev|favorable\s+ev|ev\s+of\s+\$?\d", narrative_text, re.IGNORECASE):
            errors.append(ValidationError(
                code="EV_CONTRADICTION",
                message=f"Narrative asserts positive EV but computed EV is {computed_fields.expected_value:.2f}",
                field_context="expected_value"
            ))
    return errors
```

**False-positive guard:** the rule must NOT flag narratives that correctly reference negative EV (e.g., "the negative EV signals caution"). Test this explicitly. The regex `positive\s+ev` should not match "the EV is negative" — confirm by running the rule against a hand-crafted "negative EV" narrative.

Write unit tests in `tests/validators/test_narrative_grounding.py`:
- Positive case: AMZN-style narrative with "positive EV of $89" + computed_ev=-5.86 → 1 error
- Negative case: narrative correctly saying "EV of -5.86 makes this a pass" + computed_ev=-5.86 → 0 errors
- Null case: narrative with no EV mention + computed_ev=-5.86 → 0 errors
- Edge case: computed_ev=0 (boundary) → 0 errors (rule only fires when EV < 0)

Run the tests. Confirm all pass.

**STOP and report** the module + tests. `git diff`. Wait for approval before Phase 3.

## Phase 3 — Implement OTA-510 (SMA grounding rule)

Add to `app/validators/narrative_grounding.py`:

```python
def validate_sma_grounding(narrative_text: str, computed_fields) -> list[ValidationError]:
    errors = []
    
    # Sub-rule A: positional contradiction (price above SMA-50 but narrative claims below)
    if computed_fields.price > computed_fields.sma_50:
        if re.search(r"below.*(50|all\s+sma|all\s+three\s+sma)|under.*50", 
                     narrative_text, re.IGNORECASE):
            errors.append(ValidationError(
                code="SMA_POSITION",
                message=f"Narrative asserts below SMA-50 but price ({computed_fields.price:.2f}) > SMA-50 ({computed_fields.sma_50:.2f})",
                field_context="sma_50"
            ))
    
    # Sub-rule B: numerical hallucination
    sma_values_in_input = {computed_fields.sma_8, computed_fields.sma_21, computed_fields.sma_50}
    sma_values_in_narrative = re.findall(
        r"sma[- ]?\d+\s+at\s+\$?(\d+\.\d+)",
        narrative_text, re.IGNORECASE
    )
    for v_str in sma_values_in_narrative:
        v = float(v_str)
        nearest = min(sma_values_in_input, key=lambda x: abs(x - v))
        if abs(v - nearest) > 0.10:  # 10¢ tolerance
            errors.append(ValidationError(
                code="SMA_HALLUCINATION",
                message=f"Narrative cites SMA value {v:.2f} not in input set {sorted(sma_values_in_input)}",
                field_context=f"sma_value_{v_str}"
            ))
    
    return errors
```

**Regex cautions:**
- Sub-rule A's regex must not fire on "above 50" or "above all SMAs" — test these explicitly
- Sub-rule B's regex must handle "SMA-21 at 257.64" AND "SMA21 at 257.64" AND "sma 50 at $252.39"

Add tests to `tests/validators/test_narrative_grounding.py`:
- AMZN regression A: "sits just below all three SMAs" + price > all three → 1 error (SMA_POSITION)
- AMZN regression B: narrative cites "257.64 SMA-21" + input set {$252.x, $252.x, $251.x} → 1 error (SMA_HALLUCINATION)
- False-positive: "above all three SMAs" + price > all three → 0 errors
- False-positive: narrative correctly cites "SMA-8 at 252.52" matching exact input → 0 errors
- Edge case: `abs(v - nearest) == 0.10` → 0 errors (boundary — 10¢ is still within tolerance)

Run tests. Confirm all pass.

**STOP and report** the updated module + tests. `git diff`. Wait for approval before Phase 4.

## Phase 4 — Wire the composed validator

Add the parent entry point to `app/validators/narrative_grounding.py`:

```python
def validate_narrative(narrative_text: str, computed_fields) -> list[ValidationError]:
    """Run all grounding rules. Empty list = narrative is grounded."""
    errors = []
    errors.extend(validate_ev_grounding(narrative_text, computed_fields))
    errors.extend(validate_sma_grounding(narrative_text, computed_fields))
    return errors
```

Add a test:
- AMZN full case: narrative contains BOTH contradictions → 2+ errors, one EV_CONTRADICTION and one SMA_POSITION (SMA_HALLUCINATION also possible depending on values)

**STOP.** `git diff`. Wait for approval before Phase 5.

## Phase 5 — Integrate into evaluation emission

Based on Phase 0 findings, edit the evaluation route/adapter to:

1. Generate narrative as before
2. Before returning the payload, call `validate_narrative(narrative_text, computed_fields)`
3. If errors list is non-empty:
   - Log the errors to `agent_run_log` (or equivalent observability table) with trace_id
   - Regenerate narrative ONCE (second Claude call with same context)
   - Re-validate
   - If second attempt also fails, substitute template fallback text
4. If errors list is empty on first or second attempt, return payload as normal

**Implementation notes:**
- Regeneration should NOT loop more than once. Hard stop at 1 retry.
- Fallback template should be clearly recognizable ("Structured evaluation complete. See computed fields. Narrative unavailable this cycle.") — so QA can spot validator-triggered fallback in production
- Observability: fire-and-forget log of validation failures (`validator=narrative_grounding`, `errors=[codes]`, `retry_triggered=bool`, `fallback_used=bool`)
- Wrap observability in `asyncio.create_task` — never block emission

**STOP.** `git diff`. Show all edits to route/adapter. Wait for approval before Phase 6.

## Phase 6 — SKILL.md prompt grounding update

Locate `app/skills/claude-trade-agent/SKILL.md` (or whichever skill file drives the evaluation prompt — confirm from Phase 0 findings).

Update the prompt to:

1. **Explicitly list structured fields as named variables** in the input section:
```
   Structured inputs (use these values verbatim; do not infer alternatives):
   - Price: {price}
   - Expected value: {expected_value}  (sign is authoritative)
   - SMA-8: {sma_8}
   - SMA-21: {sma_21}
   - SMA-50: {sma_50}
   - MA alignment: {ma_alignment}  (authoritative — do not infer positioning)
   - Max loss probability: {p_max_loss}
   - Max profit probability: {p_max_profit}
```

2. **Add a "Narrative grounding rules" section** in the prompt:
```
   Narrative grounding rules (violations will fail validation):
   - Use {expected_value} verbatim. If negative, do NOT describe EV as positive or favorable.
   - Use {ma_alignment} as authoritative for SMA positioning. Do not infer "below/above SMA" from other signals.
   - Only cite SMA values from {sma_8}, {sma_21}, {sma_50}. Do not invent intermediate values.
   - Probabilities: use {p_max_loss} and {p_max_profit} verbatim.
```

3. **Preserve existing prompt structure** (verdict reasoning, recommendations, etc.) — only add grounding discipline, don't rewrite the core.

**STOP.** `git diff app/skills/claude-trade-agent/SKILL.md`. Wait for approval before Phase 7.

## Phase 7 — Regression test with AMZN fixture

Locate existing regression test infrastructure (likely `tests/` or similar). Add AMZN fixture:

- Inputs: price=$255.36, sma_8=252.52, sma_21=252.39, sma_50=251.86, expected_value=-5.86, p_max_profit=0.2985, p_max_loss=0.5666
- Run full evaluation end-to-end
- Assert: validator flags the BAD narratives, regeneration is attempted, final output is either grounded-good or template-fallback (not the hallucinated original)

Also add a "golden path" fixture for a trade that SHOULD pass unchanged (positive EV, price above SMA with narrative correctly saying so). Assert zero validator errors.

Run both fixtures. Confirm.

**STOP and report.** `git diff --stat`.

## Phase 8 — Summary

Print:
- Files created (paths + line counts)
- Files modified (paths + diffs summary)
- Test coverage: which AMZN failures are now caught
- Which OTA-504 acceptance criteria are satisfied
- Any deviations from this prompt and why

**Do not commit.** Don reviews and commits manually.

## Commit message format (when Don is ready to commit)

```
OTA-504 OTA-509 OTA-510: Narrative grounding validator — EV + SMA rules + SKILL.md update
```

## House rules summary

- All validator rules return `list[ValidationError]`, never raise
- Prompt grounding lives in SKILL.md, not Python code
- Regeneration capped at 1 retry (never loop)
- Template fallback is recognizable so QA can spot it in production
- Fire-and-forget observability — never block emission
- False-positive guards are tested explicitly with negative-case fixtures
- STOP after every phase with a diff for review
- Don does all commits manually

## Exit criteria

- Phases 0–8 complete and approved
- AMZN EV contradiction blocked (OTA-509 criterion)
- AMZN SMA positioning contradiction blocked (OTA-510 criterion A)
- AMZN SMA hallucination blocked (OTA-510 criterion B)
- Golden-path fixture passes without triggering regeneration
- SKILL.md updated with grounding rules
- No commit made