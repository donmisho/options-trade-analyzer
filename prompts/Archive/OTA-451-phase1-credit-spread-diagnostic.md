---
allowedTools: ["Bash", "Read"]
---

# OTA-451 Phase 1 — Credit Spread Pipeline Diagnostic (READ-ONLY)

**Wave:** 1 (T2)
**Parent:** OTA-14 (Ongoing: Strategy Validation Reviews)
**Sequence label:** `05012026-7`

> ⚠️ **READ-ONLY.** This prompt makes NO code changes. Output is a single diagnostic report file. The Phase 2 fix prompt is written from this report's findings.

---

## Required reading

```bash
cat claude_context/CLAUDE.md
cat claude_context/business-rules.md
cat claude_context/architecture-plan.md
```

---

## Relevant Context — What We Already Know

**Source: OTA-451 ticket description + 04-24-2026 validation failure**

The vertical spread scan pipeline produces zero credit spread candidates. This was supposedly fixed and shipped 04-23-2026 21:04 CT, then reopened on 04-24 after validation showed AC #1–4 still unmet in production.

**Symptom:** Trades page for multiple symbols shows zero SP (Steady Paycheck) and WG (Weekly Grind) pills on any row. Debit trades appear normally at DTE 14, 21, 28, 35, 55. Under default strategy windows (SP 25–50 DTE, WG 5–16 DTE), at least one WG candidate (14 DTE) and multiple SP candidates (28, 35 DTE) should appear. Produced zero.

**Source: business-rules.md (scoring gates)**
- Credit spread P0 gate: credit as % of width ≥ 30%
- SP parameters: short delta 0.20–0.30, DTE 25–50, min IV rank 40%
- WG parameters: short delta 0.20–0.30, DTE 5–16

**Source: OTA-278 (cancelled, scope absorbed here)**
Previously scoped credit-spread leg assignment + structure detection. Closed as superseded by this Story.

---

## Diagnostic procedure — work the layers in order, do NOT skip any

The gap could be in any of four layers. Identify which one (or which combination) is responsible by working from the bottom of the stack upward.

### Layer 1 — Engine (does it generate credit spread candidates at all?)

```bash
# Locate the spread generation entry point
grep -rn "BULL_PUT_CREDIT\|BEAR_CALL_CREDIT" app/ --include="*.py"
grep -rn "generate.*spreads\|build.*spreads\|enumerate.*spreads" app/ --include="*.py"

# Find the vertical_engine module
find app/ -name "vertical_engine*"
cat <vertical_engine path>
```

Diagnostic questions to answer in the report:
1. Does the engine have separate functions / branches for credit spreads vs debit spreads, or is there one path that should produce both?
2. If there are credit-spread branches, are they actually called from the scan entry point, or are they orphaned?
3. If they ARE called, what is the leg-assignment logic? (Short leg = higher-premium for credit; verify.)
4. Does the engine apply the credit-as-%-of-width gate before or after the candidate is yielded? If before, log how many candidates fail that gate vs how many pass.

If possible, instrument the diagnostic with a one-time logger statement (in your own diagnostic notes — do NOT commit logging changes). Just READ the code path; do not modify.

---

### Layer 2 — Request path (does the request that hits /scan actually ask for credit spreads?)

```bash
# Find the scan API entry
grep -rn "@router.*scan\|/scan\|scan_routes" app/ --include="*.py"
cat <scan route file>

# Find the frontend scan call
grep -rn "scan\|getStrategyScorecard\|getTrades" web/src/ --include="*.{js,jsx,ts,tsx}"
```

Diagnostic questions:
1. What does the frontend send in the scan request? Is there a `spread_types` field? What values?
2. What does the backend route do with that field? Is there a default that excludes credit types?
3. Does the request include strategy-specific parameters (SP/WG DTE windows), or are they hardcoded backend-side?
4. If user_config / strategy overrides are forwarded (per OTA-512 / OTA-516), do they reach the engine in a form the engine can consume?

---

### Layer 3 — Scoring gates (do credit candidates exist, get scored, then get filtered out?)

```bash
# Find the scoring pipeline
find app/ -name "*scor*"
grep -rn "credit.*width\|width.*credit\|p0_gate\|hard_gate" app/ --include="*.py"
grep -rn "theta_margin_ratio\|credit_pct" app/ --include="*.py"
```

Diagnostic questions:
1. Are there hard gates that would zero-out credit spreads silently? (E.g., a min-credit-dollar threshold that's too high; a min-IV-rank check that fires before the credit gate; a debit-only assumption baked into a scoring function.)
2. For the AXP example (SP score 85, zero candidates): if you trace what the scoring layer sees vs what it emits, where does the gap appear?
3. Is the credit-as-%-of-width gate set to ≥ 30% (per business-rules.md)? Or higher? Higher would silently kill candidates.
4. Is `1 - abs(short_delta)` used as PoP for credit spreads, or is the debit PoP formula being applied incorrectly?

---

### Layer 4 — Display (do credit candidates make it to the API response but fail to render?)

```bash
# Find the trades response shape + the trades page
grep -rn "TradesResponse\|trades_response\|candidate_response" app/ --include="*.py"
grep -rn "strategy_pill\|StrategyPill\|sp_pill\|wg_pill" web/src/ --include="*.{js,jsx,ts,tsx}"
```

Diagnostic questions:
1. Does the API response include strategy_pills field per candidate? If so, are SP/WG ever populated?
2. Does the frontend filter rendering exclude any spread types (e.g., a hardcoded list of "rendered" types that omits the credit ones)?
3. Are credit candidates returned but rendered in a different section the user isn't looking at?

---

## Output: diagnostic report

Write the report to `/tmp/OTA-451-phase1-report.md`. Structure exactly as below. **Be specific — cite file paths and line numbers.** Vague findings are useless for the Phase 2 fix prompt.

```markdown
# OTA-451 Phase 1 Diagnostic Report
Generated: <date>
Scope: locate root cause of zero SP/WG candidates in trades pipeline

## Layer 1 — Engine findings
- File: <path>:<lines>
- Credit spread generation: PRESENT / ABSENT / PARTIAL
- Specific finding: <one paragraph>
- Evidence: <code excerpts with line refs>

## Layer 2 — Request path findings
[same structure]

## Layer 3 — Scoring gate findings
[same structure]

## Layer 4 — Display findings
[same structure]

## Root cause summary
- Most likely root cause: Layer N — <one-sentence statement>
- Confidence: HIGH / MEDIUM / LOW
- Secondary suspect: Layer M — <one-sentence statement>
- Why not Layer X: <brief>

## Recommended Phase 2 fix scope
- Files to modify: <list with paths>
- Order of changes: <numbered list>
- Risk: <regression surfaces — what existing tests may need to update>
- Verification path: <how the fix is verified — a specific scan command or test case>

## Open questions for Don before Phase 2 starts
- Q1: ...
- Q2: ...
```

---

## STOP — hand back

When the report is written:
1. `cat /tmp/OTA-451-phase1-report.md` to display the contents
2. Make NO commits (this prompt is read-only)
3. Don will use the report to write the Phase 2 fix prompt for Wave 3

Do NOT proceed to fix anything in this session.
