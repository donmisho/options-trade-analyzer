# Options Analyzer — Bug Fixes & Improvements

## Context

This is a Python/FastAPI options trading application with a JavaScript frontend. It uses the Tradier API for live market data and displays vertical spread analysis with an integrated chart, configuration panel, and Claude triage system.

The following issues were identified through live testing on March 11, 2026. Fix them in order of priority.

---

## Fix 1 — Hard Filter: Remove Negative EV Spreads Before Scoring (CRITICAL)

**Problem:**
Spreads with negative Expected Value (EV < 0) are currently passing through the scoring pipeline and appearing in the ranked results table. A spread with EV = -0.85 was observed at mid-table rank (score 0.58), placed above spreads with positive EV. This is incorrect — negative EV means the trade has negative expected value over time and should never reach the user.

**Required behavior:**
- Before any spread is scored or ranked, apply a hard filter: `if EV < 0, discard the spread entirely`
- This filter must run **before** the composite scoring function — not as a scoring penalty weight
- Filtered spreads should not appear in the table at all
- This is not a configurable threshold — EV < 0 is always disqualifying regardless of preset

**Where to look:**
- The spread filtering/scoring pipeline, likely in the backend route that assembles spread candidates before returning them to the frontend
- Any function that calculates composite score — add the EV gate at the top before score calculation runs

---

## Fix 2 — SMA Signal Sync: Config Panel Must Reflect Chart Alignment in Real Time (HIGH)

**Problem:**
The chart component independently calculates SMA alignment (Bullish / Bearish / Mixed) based on current price vs. the three SMA values. The configuration panel has a "Spread Types" section that displays the SMA signal and suggests spread types (Bull Call / Bear Put). These two components are not staying in sync.

**Observed behavior:**
- Chart badge shows "Bullish Alignment"
- Config panel "SMA Signal" simultaneously shows "Mixed"
- This means the config panel is either reading stale data or calculating alignment independently with different logic

**Required behavior:**
- The config panel SMA Signal display must read from the **same computed alignment value** as the chart badge — single source of truth
- When the chart updates its alignment (on price refresh or period change), the config panel must reflect the same state immediately
- The suggested spread type highlight in the config panel (Bull Call / Bear Put) must update in real time to match

**Where to look:**
- The state management layer that holds the current SMA alignment value
- If the chart and config panel are each calculating alignment independently, consolidate into a single shared computation that both components read from
- Check whether the config panel is reading from a stale prop or a separate API call vs. the chart's live computed value

---

## Fix 3 — Triage Prompt: Add Explicit Negative EV Flag as Safety Net (MEDIUM)

**Problem:**
The Claude triage prompt evaluates spreads selected by the user but does not explicitly instruct Claude to call out negative EV as a disqualifying condition. If Fix 1 fails (e.g., a edge case lets a negative EV spread through), the triage has no backstop.

**Required behavior:**
Add the following instruction to the system prompt / triage prompt that is sent to Claude when evaluating selected spreads:

```
Before evaluating any spread, check the EV value. If EV is negative (< 0), 
immediately flag that spread as DISQUALIFIED due to negative expected value. 
Do not evaluate it further. State: "⛔ DISQUALIFIED — Negative EV ({value}). 
This spread has negative expected value and should not be traded."
```

This should appear in the spread evaluation logic section of the prompt, before the per-spread analysis block.

**Where to look:**
- The system prompt or prompt assembly function used for the "Ask Claude" triage feature
- Wherever individual spread data is injected into the prompt before being sent to the Anthropic API

---

## Validation Checklist

After implementing all three fixes, verify the following:

- [ ] Submit a spread batch that contains at least one spread with EV < 0 — confirm it does not appear in the results table
- [ ] Change the chart period so that SMA alignment flips (e.g., from Bullish to Bearish) — confirm the config panel SMA Signal label updates to match without requiring a page reload or manual re-analyze
- [ ] Manually inject a negative EV spread into a Claude triage request (bypassing Fix 1) — confirm Claude flags it as DISQUALIFIED before analysis
- [ ] Confirm that the score ranking is still monotonically descending after Fix 1 removes disqualified spreads
- [ ] Confirm that removing negative EV spreads does not reduce the result count below the configured display minimum — if it does, surface a message rather than showing fewer rows silently

---

## Notes

- Do not change the composite scoring weights or preset configurations — only the pre-score filter and the prompt language
- Fix 1 and Fix 2 are independent — implement and test them separately before combining
- The EV threshold of 0 is hard-coded by design — do not make it a user-configurable parameter
