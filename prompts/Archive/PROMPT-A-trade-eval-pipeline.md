---
allowedTools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
---

# OTA-515 + OTA-549 + OTA-509 + OTA-510 — Trade Eval Pipeline: WAIT_FOR_EARNINGS verdict + Narrative Grounding Validator v2

## Terminal context
- This terminal: **Terminal A**
- Concurrent terminals: **B (OTA-542 data isolation), C (OTA-560 frontend DTE filter), D (governance docs)**
- Cross-terminal dependencies:
  - **No file contention with B, C, D** in expected scope
  - **WARNING — SKILL.md exclusivity:** OTA-515 narrative-prompt update may touch a trade-evaluation SKILL.md. Terminal A holds exclusive write access to any SKILL.md under `app/` for this batch. Do not start OTA-537 in any other terminal until Terminal A commits.
  - **WARNING — `app/api/evaluation_routes.py`:** OTA-558 (deferred, not in this batch) also targets this file. Do not run OTA-558 in parallel.

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/UI-GUIDANCE.md
```

Then locate and read the current state of these specific files (use `find` / `grep` to confirm exact paths in the repo before opening):

```
# Verdict enum + decision-tree current state
grep -rn "EXECUTE\|WAIT\|PASS" app/ --include="*.py" | grep -i "verdict\|enum"
# Evaluation route + structured user-message builder
sed -n '550,650p' app/api/evaluation_routes.py
# AI adapter contract (architecture-plan.md § 4)
grep -n "AIAdapter\|chat(" app/ai/*.py app/providers/ai/*.py 2>/dev/null
# SKILL.md(s) currently driving trade evaluation
find app -name "SKILL.md" -print
```

After the structural read, also `cat` whichever SKILL.md drives `/evaluate/structured` so the narrative-prompt change in Phase 2 is a real edit, not a guess.

## Relevant Context — Do Not Deviate Without Escalation

**Source: `architecture-plan.md` § 4 (AI Adapter Contract)**
Rule: Adapter call shape `chat(system, user, max_tokens) -> {text, input_tokens, output_tokens, model, provider}`. The validator must run on the returned `text` BEFORE the response is emitted to the client. Validator failure triggers ONE retry by re-calling `chat()` with the same system/user; if the second attempt also fails, fall back to template-rendered fact list (no further AI calls — cost guardrail per `business-rules.md`).

**Source: `business-rules.md` § Cost Guardrails**
Rule: Maximum 1 retry per evaluation. No third Claude call under any circumstance for a single `/evaluate/structured` request.

**Source: `business-rules.md` § Verdicts and Gates**
Rule: NEG EV gate fires BEFORE WAIT_FOR_EARNINGS routing. A negative-EV trade does not become viable just because earnings is the reason. Order: NEG EV check → earnings check → standard scoring.

**Source: `business-rules.md` § Earnings Treatment**
Rule: "Never hold through earnings" remains a behavioral discipline. WAIT_FOR_EARNINGS preserves this discipline by surfacing a "come back on date X" signal instead of dumping the trade into PASS.

**Source: OTA-515 Decision Tree (this ticket)**
```
if earnings_in_window:
    dte_before_earnings = trading_days(entry, earnings - 1)
    dte_after_earnings  = trading_days(earnings + 1, expiry)

    if dte_before_earnings <= 7 AND dte_after_earnings < 14:
        verdict = PASS                     # Route 1
    elif dte_before_earnings <= 7 AND dte_after_earnings >= 14:
        verdict = WAIT_FOR_EARNINGS        # Route 2
    elif dte_after_earnings >= 21:
        verdict = WAIT_FOR_EARNINGS        # Route 3 (recommended)
    else:
        score normally with effective_DTE = dte_before_earnings  # Route 4
```

**Source: OTA-509 (this ticket)**
EV grounding rule:
```python
def validate_ev_grounding(narrative_text, computed_fields):
    errors = []
    if computed_fields.expected_value < 0:
        if re.search(r"positive ev|favorable ev|ev of \$?\d", narrative_text, re.I):
            errors.append("EV_CONTRADICTION: narrative asserts positive EV but computed EV < 0")
    return errors
```

**Source: OTA-510 (this ticket)**
SMA grounding rule (positional + numerical hallucination):
```python
def validate_sma_grounding(narrative_text, computed_fields):
    errors = []
    # Positional contradiction
    if computed_fields.price > computed_fields.sma_50:
        if re.search(r"below.*50|below.*all.*sma|under.*50", narrative_text, re.I):
            errors.append("SMA_POSITION: narrative asserts below SMA-50 but price > SMA-50")
    # Numerical hallucination — SMA value cited but not in input set within ±0.10
    sma_values_in_input = {computed_fields.sma_8, computed_fields.sma_21, computed_fields.sma_50}
    sma_values_in_narrative = re.findall(r"sma[- ]?\d+\s+at?\s+\$?(\d+\.\d+)", narrative_text, re.I)
    for v in sma_values_in_narrative:
        nearest = min(sma_values_in_input, key=lambda x: abs(x - float(v)))
        if abs(float(v) - nearest) > 0.10:
            errors.append(f"SMA_HALLUCINATION: narrative cites SMA value {v} not in inputs")
    return errors
```

**Source: `UI-GUIDANCE.md` § Verdict Badges**
Rule: Verdict badges use dark-theme CSS variables only (no inline hex). EXECUTE = green, WAIT = blue, PASS = red. The new WAIT_FOR_EARNINGS badge uses an amber variant — define a new CSS variable for it; do not reuse plain WAIT's color. Badge sizing follows existing badge pattern (sized to content, never full-width).

---

## Phase 1 — Read-only diagnostic (STOP gate before Phase 2)

Do not edit anything in Phase 1. Produce a diagnostic report covering:

1. **Verdict enum location.** Exact file + class/enum name where EXECUTE/WAIT/PASS are defined today.
2. **Decision-tree integration point.** Exact file(s) where verdict is currently assigned in the evaluation pipeline — list each function with line numbers.
3. **`dte_after_earnings` computation source.** Where (if anywhere) earnings dates flow into the evaluation. Confirm OTA-502's `earnings_in_window` check is live and reachable; report its exact location. If absent or moved, escalate before continuing.
4. **NEG EV gate location.** Confirm OTA-503's gate is live and fires before any verdict assignment. Report exact location.
5. **Narrative emission point.** Exact line where `adapter.chat()` is called for `/evaluate/structured` and exact line where the returned text is handed to the client (so we know where to insert the validator).
6. **SKILL.md governing the prompt.** Exact path of the SKILL.md whose system/user templates drive the narrative.
7. **Existing structured payload shape.** Schema of `computed_fields` (Pydantic model name + fields). Confirm `expected_value`, `sma_8`, `sma_21`, `sma_50`, `price` are present. Report any missing field.
8. **Frontend verdict badge component.** Exact file and component name; confirm it consumes verdict via prop/enum.

**STOP.** Surface the diagnostic. If any item above turns up missing or substantially different from the spec, do not proceed — escalate so the spec can be revised. Otherwise, proceed to Phase 2 on Don's go-ahead.

---

## Phase 2 — Implementation

Implement in this order. Do not skip steps.

### 2a. Verdict enum extension (OTA-515)
- Add `WAIT_FOR_EARNINGS` to the verdict enum identified in Phase 1.
- Add a `reevaluate_on` optional field to the structured payload (date type, populated only when verdict == WAIT_FOR_EARNINGS).
- Add `dte_after_earnings` and `dte_before_earnings` as computed fields in the evaluation payload (always populated when `earnings_in_window` is true).

### 2b. Decision tree (OTA-515)
- Implement the four-route decision tree from Relevant Context exactly as specified.
- Wire it AFTER NEG EV gate, BEFORE standard scoring.
- For Route 2/Route 3 verdicts, set `reevaluate_on = earnings + 1 trading day`.
- Route 4 routes back to standard scoring with `effective_DTE = dte_before_earnings`. Use the existing `effective_DTE` plumbing from OTA-506.

### 2c. Narrative prompt update (OTA-515)
- Update the SKILL.md identified in Phase 1 to differentiate debit vs credit rationale:
  - Debit: "Wait is strictly better — entry improves post-crush."
  - Credit: "Wait trades premium for safety — credit will be smaller but gap risk eliminated."
- Add WAIT_FOR_EARNINGS to the verdict vocabulary in the SKILL.md.
- Keep the change surgical — do not rewrite unrelated sections.

### 2d. Narrative Grounding Validator v2 (OTA-549, OTA-509, OTA-510)
- Create `app/validators/narrative_grounding.py` (or the path the existing app/validators tree dictates — confirm in Phase 1).
- Implement `validate_ev_grounding()` and `validate_sma_grounding()` exactly per Relevant Context.
- Compose into a single `validate_narrative(narrative_text, computed_fields) -> list[str]` that runs both and returns the combined errors list.
- Wire into `/evaluate/structured` between `adapter.chat()` and the response emission:
  - On non-empty errors: ONE retry of `adapter.chat()` with same system/user.
  - If retry also returns errors: fall back to template-rendered fact list (no third call).
  - In all cases, log validator failures to `agent_run_log` (or the equivalent observability sink — confirm in Phase 1) using fire-and-forget so a logging failure never blocks emission.

### 2e. Frontend badge (OTA-515 #5)
- Add a new amber CSS variable for the WAIT_FOR_EARNINGS badge state in the dark theme tokens file. Do NOT inline hex.
- Update the verdict badge component to render WAIT_FOR_EARNINGS with the new amber styling.
- Show `reevaluate_on` (formatted via `formatDate()` as `mm-dd-yyyy`) inline on the verdict line when verdict == WAIT_FOR_EARNINGS. No `$` prefix anywhere in this widget.

### 2f. Re-evaluation hook (OTA-515 #6)
- If user has opted into auto-re-run: schedule a re-scan trigger for `reevaluate_on`. Use the existing scheduler — do not introduce a new mechanism. If no opt-in mechanism exists yet, ship the field on the payload and skip the auto-trigger; document the gap as out-of-scope for this commit.

---

## Acceptance criteria

**OTA-515:**
- `WAIT_FOR_EARNINGS` present in verdict enum, narrative SKILL.md vocabulary, and frontend badge.
- All eight test cases from the OTA-515 ticket table produce the documented verdict.
- `reevaluate_on` populated for WAIT_FOR_EARNINGS verdicts; absent otherwise.
- Debit vs credit rationale differentiation verified on at least one debit and one credit example.
- Frontend badge renders amber via CSS variable, displays `reevaluate_on` as `mm-dd-yyyy`, no `$` prefix.
- NEG EV gate continues to fire before WAIT_FOR_EARNINGS routing — confirmed by a regression case where a negative-EV earnings-adjacent setup verdicts as PASS, not WAIT_FOR_EARNINGS.

**OTA-549 / OTA-509 / OTA-510:**
- `app/validators/narrative_grounding.py` exists with both validators wired.
- Validator runs on every `/evaluate/structured` response before emission.
- AMZN regression case from OTA-509 (narrative claims "positive EV of $89" against `computed_ev = -5.86`) is blocked, regenerated, second attempt logged.
- AMZN regression case from OTA-510 sub-rule A (narrative claims "below all three SMAs" against price > all three SMAs) is blocked.
- AMZN regression case from OTA-510 sub-rule B (narrative cites "SMA-21 at 257.64" not in input set) is blocked.
- ±0.10 tolerance honored for SMA numerical match.
- Validator failures logged to `agent_run_log` (or equivalent) via fire-and-forget.
- No false positives on a positive-EV trade with neutral phrasing or on a narrative that correctly summarizes positional context.

## Out of scope

- New grounding categories beyond EV and SMA — separate Stories.
- Prompt re-tuning beyond the WAIT_FOR_EARNINGS vocabulary additions — covered separately under OTA-501 and the SKILL.md migration in OTA-537 (deferred).
- OTA-558 (502 fix on naked options evaluate) — same area but separate ticket; sequenced after this commit.
- Reparenting OTA-509 / OTA-510 in Jira — Don will reparent under OTA-549 manually as part of post-commit hygiene.
- Auto-re-run scheduler infrastructure if it does not already exist — ship the field, document the gap.

## Verification steps

Before requesting commit approval:

1. `pytest` — full suite passes locally.
2. Specifically run the regression cases (AMZN narratives + the eight OTA-515 verdict-routing cases). Show the test output in your report.
3. Local uvicorn run + manual `curl` to `/evaluate/structured` for one debit and one credit symbol; verify WAIT_FOR_EARNINGS verdict path end-to-end including the `reevaluate_on` field on the response.
4. Vite frontend run; visually confirm amber badge renders for a WAIT_FOR_EARNINGS verdict with the `reevaluate_on` date displayed correctly.
5. `grep -rn "positive_ev_string\|favorable ev" app/` and similar — confirm validator regex patterns match the actual prose patterns the model produces (not just the spec strings).
6. Build a verdict-matrix table in your final report: 8 OTA-515 cases × actual verdict produced. Any miss is a Phase 2 failure, not a verification finding — fix and re-verify.

## Commit instruction
**I have been instructed to commit. Do you approve? (yes / no)**

## Coordination footer
**Independent — no downstream dependency.** Other terminals proceed in parallel; nothing in this batch waits on Terminal A.

## Commit message template (if committing)
```
OTA-515 OTA-549 OTA-509 OTA-510 feat: add WAIT_FOR_EARNINGS verdict and Narrative Grounding Validator v2
```
