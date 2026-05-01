# business-rules.md

**Last Updated:** 2026-04-30 22:05 UTC
**Instigating Ticket:** OTA-495 (v1 Create — Extract business rules from architecture-plan.md and CLAUDE.md)
**Status:** Shell with Cost Guardrails section populated. Remaining sections (Strategy Scoring, Hard Gates, PoP Computation, Health Grade Computation, Position Lifecycle, Signal Freshness / TTL Windows, Display Formatting Rules, Validation Baseline) are placeholders. Full extraction of those sections is the body of OTA-495 implementation work.

---

This document is the source of truth for **what the system computes and enforces**: scoring formulas, hard gates, computation rules, lifecycle states, freshness windows, formatting standards, and the validation baseline.

Business rules live here exclusively. They do not appear in `CLAUDE.md`, `architecture-plan.md`, `UI-GUIDANCE.md`, or `auth-process.md`. Those documents reference this file.

When any other document and `business-rules.md` disagree on a business rule, this document wins.

For workflow guidance, read `CLAUDE.md`.
For architectural rationale and patterns, read `architecture-plan.md`.
For UI presentation rules and decisions, read `UI-GUIDANCE.md`.
For auth flows, sessions, and security, read `auth-process.md`.

---

## Table of Contents

- [Strategy Scoring](#strategy-scoring)
- [Hard Gates (P0 Pipeline)](#hard-gates-p0-pipeline)
- [Probability of Profit (PoP) Computation](#probability-of-profit-pop-computation)
- [Health Grade Computation](#health-grade-computation)
- [Position Lifecycle](#position-lifecycle)
- [Signal Freshness / TTL Windows](#signal-freshness--ttl-windows)
- [Display Formatting Rules](#display-formatting-rules)
- [Cost Guardrails](#cost-guardrails)
- [Validation Baseline](#validation-baseline)

---

## Strategy Scoring

*Content pending — extract from `architecture-plan.md` "The Strategy System" section and `app/analysis/strategy_scorer.py` / `strategy_definitions.py`. Scope per OTA-495: four strategies (Steady Paycheck, Weekly Grind, Trend Rider, Lottery Ticket — current cute-name taxonomy; mechanics-based redesign tracked separately under future epic) × five scoring metrics. Document the scoring formula per metric, the weight per strategy, the threshold values, and the interplay with hard gates.*

*Strategy DTE ranges: see OTA-513 for the canonical-source decision (`STRATEGIES` vs `STRATEGY_DEFINITIONS` consolidation). After OTA-513 ships, this section documents the surviving canonical dict and per-strategy DTE windows.*

---

## Hard Gates (P0 Pipeline)

*Content pending — extract from `app/analysis/hard_gates/` (registered gates) and document each gate's trigger condition, scope (which strategies it applies to), and PASS/FAIL logic. Initial registered gates:*

- *EarningsInWindowGate — triggers when earnings within 5 days of expiration*
- *NegativeEVGate — triggers when expected value calculation is negative*

*Also document:*

- *0-DTE hard filter rule (DTE ≤ 7 → auto-PASS before scoring)*
- *Credit % of width gates: 30% minimum for credit spreads, 40% maximum for debit spreads*

---

## Probability of Profit (PoP) Computation

*Content pending — document the canonical PoP formula. Key established rule: long-leg delta is used (not `1 - short_delta`). Document why, the source-of-truth code path (`app/analysis/`), and any per-strategy variation.*

---

## Health Grade Computation

*Content pending — extract from `architecture-plan.md` "Health Grade Computation" section. Document:*

- *Letter grade scale: A (on track) → F (thesis invalid)*
- *Color mapping: A=green, B=teal, C=yellow, D=orange, F=red*
- *Inputs: Claude's exit levels stored at position entry; current price; time elapsed; P&L vs target*
- *Update cadence: daily after market close, plus on-demand*
- *Computed by Position Monitor Agent against deterministic math, not by Claude*

---

## Position Lifecycle

*Content pending — extract from `architecture-plan.md` "Position Lifecycle" section. Document the state machine:*

- *Source: PAPER | LIVE*
- *Status: FOLLOWING | LIVE | CLOSED*
- *Transitions: when each transition is allowed, who triggers it, what side effects occur*
- *Cross-reference to Pattern 4 (Unified Position Model) in `architecture-plan.md`*

---

## Signal Freshness / TTL Windows

*Content pending — document the TTL per signal type. Each `ContextSource` adapter declares `ttl_seconds()`. Catalog them here:*

- *Schwab quotes: TTL window TBD*
- *Finnhub earnings: TTL window TBD*
- *Future signal sources: list as added*

*Document staleness rules: when a signal exceeds its TTL, what behavior is correct (refetch on demand, mark stale in UI, drop from scoring, etc.).*

---

## Display Formatting Rules

*Content pending — extract from `CLAUDE.md` House Style Rules. These are presentation rules that derive from business meaning (e.g., score precision, monetary precision, percentage precision), distinct from pure UI rules in `UI-GUIDANCE.md`.*

*Rules to document:*

- *Date format: `mm-dd-yyyy`; with time: `mm-dd-yyyy hh:mm`*
- *Monetary display: `##.00` via `.toFixed(2)`; no `$` prefix*
- *Probabilities: `##.00%`*
- *IV rank: `##.00%`*
- *Config percentages: `##%` (no decimals)*
- *Scores (0–100 scale): `##.00` everywhere*
- *Health grades: letter (A/B/C/D/F) with color mapping (cross-reference Health Grade Computation section)*
- *Position source labels: "Paper" / "Live" (title case in UI)*
- *Trade type display names: title case, no underscores*

---

## Cost Guardrails

These rules constrain Claude API call volume. They apply to every UI action and background job that may invoke a Claude API call.

- **Multi-call refresh confirmation.** Any refresh action that would trigger more than one Claude API call must show a confirmation dialog before firing. The dialog must state the number of calls about to be made and require explicit user confirmation.
- **Single-call refreshes.** Run without confirmation.
- **Daily auto-refresh.** One auto-refresh per position per day, fired after market close. No other timer-driven Claude calls are permitted.
- **No page-load Claude calls.** Visiting a page must never trigger a Claude API call. Calls are only triggered by explicit user action or the post-market-close batch.
- **Rationale.** Cost containment and explicit user awareness of paid-API consumption. The user-facing confirmation dialog is the enforcement point that prevents accidental fan-out.

The UI implementation pattern that enforces the confirmation requirement (`RefreshConfirmDialog.jsx`) is documented in `UI-GUIDANCE.md`. This document specifies *what* the rule is; `UI-GUIDANCE.md` specifies *how* it is rendered.

---

## Validation Baseline

*Content pending — document the regression suite expectations:*

- *AMZN regression suite: location, scope, what it validates*
- *Hard gate ordering test: what it asserts*
- *Strategy scoring regressions: per-strategy expected outputs against fixed inputs*
- *When the baseline can be updated: only after a Level 2 QA run with all tests passing (see CLAUDE.md Post-Build QA Gate)*
- *Where snapshots live: `agents/qa-context/baseline-ux.json`, `baseline-data.json`*

---

## Change Log

| Date | Ticket | Change |
|---|---|---|
| 2026-04-30 22:05 UTC | OTA-495 | Cost Guardrails section populated as the first extraction. Rule moved from CLAUDE.md House Style section to here. CLAUDE.md now references this file for the canonical rule. |
| 2026-04-30 21:33 UTC | OTA-495 | Initial shell created. Sections and TOC defined per OTA-495 scope (Strategy Scoring, Hard Gates, PoP Computation, Health Grade, Position Lifecycle, Signal Freshness, Display Formatting, Cost Guardrails, Validation Baseline). Each section contains a placeholder describing the source material to extract from and the rules to document. Full content extraction is the body of OTA-495 implementation work. |
