# OTA-616 + OTA-617 + OTA-618 + OTA-619 + OTA-620 — Agent prompt coherence cluster

## Deployment context
- Deployment: **D1**
- This terminal: **T1**
- Concurrent terminals: T2 (verdict-integrity bug fix; disjoint files), T3 (governance docs; disjoint files)
- Cross-terminal dependencies: **none** — T1 owns the agent prompt template and the upstream payload assembly; T2 and T3 do not touch these files

## Required reading
Before any code changes:

```
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/auth-process.md
```

Plus:

```
cat app/ai/prompts/<the evaluation system-prompt file>   # Phase 1 discovery locates exact path
cat app/api/evaluation_routes.py                          # confirm where the user-message payload is assembled
cat app/analysis/hard_gates/*.py                          # confirm existing gate semantics for cross-reference
```

## Relevant Context — Do Not Deviate Without Escalation

**Source: business-rules.md § Verdict logic**
The verdict ladder is `EXECUTE / WAIT / PASS`. The existing score thresholds are ≥70 EXECUTE, 50–69 WAIT, <50 PASS. Hard floors override score; soft gates demote (never promote) the score-derived verdict.

**Source: business-rules.md § Hard gates**
P0 hard gates (EarningsInWindowGate, NegativeEVGate) filter trades before scoring. The prompt-level hard floors added here are a second line of defense for the agent path — they do NOT replace the pipeline gates.

**Source: architecture-plan.md § Pattern 2 (Skill-Driven Prompts)**
Skill files are the sole source of prompt content. No hardcoded prompts in Python or React. The agent prompt template referenced in this cluster is the canonical prompt definition; do not duplicate its content into Python strings.

**Source: business-rules.md § JSON contract**
`TradeVerdict` schema is frozen for this cluster. Required-mentions and field-binding rules from OTA-619 are content contracts inside the existing `claude_read` text field — not schema changes.

**Source: architecture-plan.md § AI Adapter Contract**
`chat(system, user, max_tokens) -> {text, input_tokens, output_tokens, model, provider}`. Both adapter implementations must implement this exact dict shape. Do not modify the adapter; only the prompt content and the user-message payload assembly are in scope.

**Source: CLAUDE.md § Cost guardrail**
Any refresh that triggers more than one Claude API call must show a confirmation dialog before firing. Not directly in this prompt's scope, but do not introduce additional API calls in the eval path.

---

## Execution order within this terminal

This is a multi-OTA prompt. The five Stories execute sequentially in the order below. **One commit at the end covers all five tickets.** Do not commit between Stories.

If a Story fails its verification step, stop and report — do not proceed to the next Story.

---

## OTA-616 — Reconcile field names + add computed values

### Scope
1. **Field-name reconciliation.** The current prompt instructions reference `total_ev`, `ma_alignment`, `p_max_loss`, `p_max_profit`. The payload supplies `ev_raw`, `alignment`, `prob_of_profit`. Phase 1 reads both prompt and payload assembly and picks the canonical name per field (rename whichever side requires fewer downstream changes).
2. **Add computed values to the user-message payload:**
   - `scenario_weighted_ev` — same formula the panel uses (sum over scenarios of `probability × pnl`)
   - `net_bid_ask` — spread-level: debit spreads `long_ask − short_bid`, credit spreads `short_bid − long_ask` (align with the panel's existing convention)
   - `dte` — integer days-to-expiration at evaluation request time
   - `debit_pct_of_width` — debit spreads only (max-loss-as-fraction-of-width gate input)
   - `cushion_pct` — credit spreads only (distance from short strike to current price as fraction of underlying)

### Acceptance criteria
- Every field name referenced in the prompt's instruction text exists verbatim in the user-message payload.
- The five new computed fields are present in every payload emitted by `app/api/evaluation_routes.py`.
- For a regression sample of 5 evaluations, no figure cited in `claude_read` reconciles to a field that does not exist.

### Out of scope
- `TradeVerdict` schema changes.
- Panel-side rendering changes.
- Renaming the canonical field on the panel side (frontend stays put unless Phase 1 chose to rename the payload side).

---

## OTA-617 — Verdict reasoning chain (hard floors, soft gates, score band)

### Scope
Add a verdict-reasoning chain to the prompt that runs in this fixed order:

1. **Hard floors** (any failure → verdict = PASS regardless of score; reason cited verbatim in `claude_read`):
   - DTE ≤ 7
   - Earnings date inside the expiry window
   - `scenario_weighted_ev` ≤ 0
2. **Score band** — base verdict from existing thresholds (≥70 EXECUTE, 50–69 WAIT, <50 PASS).
3. **Soft gates** (demote-only; base = EXECUTE and any soft gate fails → verdict = WAIT; failed soft gates named in `claude_read`):
   - DTE outside the strategy's preferred entry window
   - IV Rank below strategy minimum (direction by structure: debit benefits from low IV, credit from high IV)
   - `net_bid_ask` > 10% of entry premium
   - SMA alignment ambiguous against the directional thesis

Soft gates demote at most one level (EXECUTE → WAIT). They never promote PASS → WAIT or WAIT → EXECUTE.

### Acceptance criteria
- The prompt explicitly lists the three-tier order (hard floors → score band → soft gates) with each rule named.
- For a regression sample with a known DTE-out-of-window trade and EXECUTE-base-score, the verdict comes back WAIT with the soft gate cited.
- For a regression sample with earnings-inside-expiry, verdict is PASS regardless of score.

### Out of scope
- `TradeVerdict` schema changes (failed soft gates appear in narrative text, not as a structured field).
- Pipeline-layer changes (the P0 gates in `app/analysis/hard_gates/` are not touched).
- Promotion logic (PASS → WAIT, WAIT → EXECUTE never happens via soft gates).

---

## OTA-618 — strategy_spec block + structural fit gate

### Scope
1. **Add a `strategy_spec` block to the user-message payload**, populated per strategy at evaluation time:
   - `preferred_dte_window` — `[min, max]` integer pair
   - `preferred_structure` — `"credit"` | `"debit"`
   - `compatible_structures` — array of spread-type identifiers
2. **Sourcing for `compatible_structures`:** the strategy registry at `web/src/strategy-configs/index.js` is the SoT. **OTA-627 (D2-T1) adds the `compatible_structures` field to each `*.config.js`.** Until OTA-627 ships, this Story's `compatible_structures` reads from a **temporary mapping in the evaluation-route assembler** that mirrors OTA-627's initial values:
   - `steady-paycheck`: `['bull_put_credit', 'bear_call_credit']`
   - `weekly-grind`: `['bull_put_credit', 'bear_call_credit']`
   - `trend-rider`: `['long_call', 'long_put', 'bull_call_debit', 'bear_put_debit']`
   - `lottery-ticket`: `['long_call', 'long_put']`
   Mark the temporary mapping with a `# TODO: remove after OTA-627` comment and a link reference.
3. **Add a structural fit gate** to the prompt's verdict reasoning chain (sits at the same level as hard floors):
   ```
   if trade.spread_type not in strategy_spec.compatible_structures
       → verdict = PASS
       → reason = "structural mismatch: {spread_type} not in compatible structures for {strategy_label}"
   ```
4. **The DTE-window soft gate from OTA-617 reads from `strategy_spec.preferred_dte_window`** rather than any hardcoded window.

### Acceptance criteria
- `strategy_spec` appears in every payload emitted by `app/api/evaluation_routes.py`.
- Regression: a `bear_put` debit trade routed to `steady-paycheck` returns verdict PASS with the structural-mismatch reason in `claude_read`.
- The DTE-window soft gate reads from `strategy_spec.preferred_dte_window`, not a constant.

### Out of scope
- Pipeline-layer credit-spread generation (OTA-451 territory).
- Strategy taxonomy rename (separate future epic).
- Auto-routing of trades to compatible strategies — the gate rejects mismatches, it does not re-route.

---

## OTA-619 — Narrative field bindings and required mentions

### Scope
1. **Pin every narrative fact to a named field.** Add explicit instruction to the prompt: every numeric figure in `claude_read` must reference a specific named field from the payload. If the field is not present, the figure is omitted — not improvised.
2. **"If missing, omit; do not invent" guard** for each commonly-cited category: EV, bid-ask, IV rank, breakeven, DTE.
3. **Required-mentions checklist** for `claude_read`. Each verdict's narrative must include:
   - DTE value + status relative to `strategy_spec.preferred_dte_window` (in window / outside window — comes from OTA-617's soft gate)
   - One dominant strength (highest-weighted positive scoring metric)
   - One dominant weakness (highest-weighted negative scoring metric)
   - One specific invalidator price tied to a named SMA, breakeven, or short strike (e.g., "thesis invalidates above SMA-21 at 132.40")

### Acceptance criteria
- For a regression sample of 5 evaluations, every numeric figure in `claude_read` reconciles to a named field in the payload (no figures appear that aren't pinned to a payload field).
- All four required-mentions categories appear in every verdict's `claude_read`.
- One field-binding example included in the prompt to anchor the rule.

### Out of scope
- `TradeVerdict` JSON schema (text-only changes to `claude_read` content rules).
- Tone or style edits beyond the binding and required-mentions rules.

---

## OTA-620 — Structural restructure with worked example (OPTIONAL)

**This Story is optional.** If the four prior Stories took longer than expected, **cancel OTA-620 and re-file it under D2 or later**. Do not let it block the cluster commit.

### Scope (if proceeding)
Restructure the system prompt into 7 named sections in this order:
1. Role and output contract
2. Input contract (field-by-field, what each one carries)
3. Verdict logic (the reasoning chain from OTA-617 + OTA-618's structural gate)
4. Field-binding rules (from OTA-619)
5. Narrative requirements (required mentions from OTA-619)
6. Anti-hallucination guards ("if missing, omit; do not invent")
7. One worked example (real trade payload sourced from `agent_run_log`, annotated to show which rule produced which sentence)

**Pure refactor. No rule changes.**

### Acceptance criteria
- Behavioral regression: for the OTA-616–619 regression sample, verdicts and `claude_read` blocks match the pre-restructure baseline exactly (or within rounding for any numeric assertion).
- 7 sections appear with named headers in the specified order.
- Worked example is real (sourced from `agent_run_log`) and annotated.

### Out of scope
- Rule changes from OTA-616–619 (this Story relocates, doesn't edit).
- Schema changes.

### Decision rule for skipping
If at the start of OTA-620 the wall-clock budget for D1 is exhausted, skip it. Document in the commit message that OTA-620 was deferred. Re-file under D2 backlog and continue to commit.

---

## Combined verification steps (run before commit)

1. **Phase 1 diagnostic completed for each Story** — the actual prompt template path identified, the payload-assembly point identified, field-name drift inventoried.
2. **Regression sample run:** pick 5 historical evaluations from `agent_run_log` (mix of EXECUTE / WAIT / PASS, mix of debit and credit, at least one DTE-out-of-window case, at least one structural mismatch case). Re-run each through the updated prompt path and confirm:
   - Every numeric figure in each `claude_read` reconciles to a payload field.
   - The 4 required mentions appear in every `claude_read`.
   - The structural-mismatch case returns PASS with the named reason.
   - The DTE-out-of-window case returns WAIT (assuming base ≥70) with the soft gate named.
3. **No unit-test failures** in `app/ai/` or `app/api/evaluation_routes.py` test scope.
4. **No `TradeVerdict` schema changes** anywhere in the diff (`grep -n "class TradeVerdict" app/` returns the same definition as pre-change).

If any of the above fail, do not commit. Report findings.

---

## Commit instruction

**I have been instructed to commit. Do you approve? (yes / no)**

One commit covers all five Stories (or four, if OTA-620 was deferred per the skip rule).

## Push instruction

**DO NOT push. Single push for Deployment 1 will be coordinated by Don after all D1 terminals (T1, T2, T3) report commit.**

## Coordination footer

**Independent — no downstream dependency.** This terminal can close after committing.

## Commit message template

If all five shipped:
```
OTA-616 OTA-617 OTA-618 OTA-619 OTA-620 feat: agent prompt coherence pass — field reconciliation, verdict reasoning chain, strategy_spec gate, narrative binding, structural restructure
```

If OTA-620 deferred:
```
OTA-616 OTA-617 OTA-618 OTA-619 feat: agent prompt coherence pass — field reconciliation, verdict reasoning chain, strategy_spec gate, narrative binding (OTA-620 deferred)
```
