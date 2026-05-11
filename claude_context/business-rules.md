# business-rules.md

**Last Updated:** 2026-05-11 22:00 UTC
**Instigating Ticket:** OTA-495 (v1 Create — Extract business rules from architecture-plan.md and CLAUDE.md)
**Status:** Cost Guardrails section populated. Strategy Scoring → Strategy-Structure Compatibility subsection populated (canonical compatibility map established). Remaining subsections (Strategy Scoring formula and weights, Hard Gates, PoP Computation, Health Grade Computation, Position Lifecycle, Signal Freshness / TTL Windows, Display Formatting Rules, Validation Baseline) are placeholders. Full extraction of remaining content is the body of OTA-495 implementation work.

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
- [Technicals Classification](#technicals-classification)
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

### Strategy-Structure Compatibility

Each strategy declares which trade structures it accepts. The scorer gates at pipeline entry: if a candidate's structure is not in the strategy's `compatible_structures` list, the scorer returns null and the candidate is never evaluated against that strategy. This rule is enforced before any metric scoring occurs.

| Strategy | Compatible structures | Mechanism |
|---|---|---|
| Steady Paycheck | `BULL_PUT_CREDIT`, `BEAR_CALL_CREDIT` | Premium collection; theta works for the trader; edge from win frequency, not payoff size |
| Weekly Grind | `BULL_PUT_CREDIT`, `BEAR_CALL_CREDIT` | Same family as SP; differentiated by tighter DTE floor (≥ 14) and weekly-cycle parameters |
| Trend Rider | `BULL_CALL_DEBIT`, `BEAR_PUT_DEBIT` | Directional payoff; theta is a headwind; edge from payoff size, R:R ≥ 1.5 |
| Lottery Ticket | `SINGLE_LONG_CALL`, `SINGLE_LONG_PUT` | Long premium; far-OTM permitted; asymmetric payoff trades |

The compatibility list is the source of truth for:

- Whether the scorer evaluates a candidate against a given strategy.
- Which structures the verticals scanner and long-options scanner request when a strategy is selected.
- Which strategies appear as eligible best-fit candidates for a given trade.

**Rationale.** Strategy is a *mechanism*, not a metrics bucket. A bull put credit and a bear put debit may share calendar metrics (DTE, probability of profit) but they have opposite relationships with time (theta tailwind vs theta headwind), opposite cash-flow shapes (premium received vs premium paid), and require different management (exit at 50% of credit captured vs exit at fixed R:R multiple of debit paid). Calling both "Steady Paycheck" because they share calendar metrics is a category error. This compatibility rule prevents that conflation at the scoring boundary rather than relying on the narrative prompt to catch it after the fact.

**`best_fit` semantics under compatibility.** The `best_fit` field reports the highest-scoring strategy among the structurally-compatible subset. If no strategy is compatible with the candidate's structure (defensive case — should not occur for well-formed candidates), `best_fit` is null and `best_fit_reason` carries an explanation.

### Scoring formula and weights

*Content pending under OTA-495 — extract per-metric formula, per-strategy weights, and thresholds from `app/analysis/strategy_scorer.py` / `strategy_definitions.py`. Five scoring metrics × four strategies. Document the interplay with hard gates (see Hard Gates section).*

*Strategy DTE ranges: see OTA-513 for the canonical-source decision (`STRATEGIES` vs `STRATEGY_DEFINITIONS` consolidation). After OTA-513 ships, this section documents the surviving canonical dict and per-strategy DTE windows.*

---

## Technicals Classification

### SMA Alignment Narrative

The SMA alignment narrative is computed deterministically from the spot price and three simple moving averages (8, 21, 50). Four mutually exclusive cases, evaluated in priority order:

1. **Bullish stack** — `sma8 > sma21 > sma50` AND `spot > sma8`:
   → `"bullish stack — price above 8 > 21 > 50 SMA."`

2. **Bearish stack** — `sma8 < sma21 < sma50` AND `spot < sma8`:
   → `"bearish stack — price below 8 < 21 < 50 SMA."`

3. **Clustered** — `max_spread_pct < 0.5` where `max_spread_pct = (max(sma8, sma21, sma50) - min(sma8, sma21, sma50)) / spot * 100`:
   → `"clustered — all three SMAs within {max_spread_pct:.1f}% of spot. Trend undefined."`

4. **Mixed** (default) — describe where price sits relative to each SMA:
   → `"mixed — price below {below_list}, above {above_list}. Not a clean bullish or bearish stack."`

The mixed case renders exactly as: `mixed — price below 8 and 50, above 21. Not a clean bullish or bearish stack.` (for the QQQ sample inputs: spot=715.0, sma8=717.32, sma21=713.85, sma50=720.71).

### Distance from 50-Day SMA

| Absolute distance | Label |
|---|---|
| < 2.0% | `within range, not extended` |
| 2.0% – 4.99% | `somewhat extended` |
| ≥ 5.0% | `extended` |

Rendered as `<signed_pct>% (<label>)`. Negative distances use the Unicode minus sign (−).

### Computation Inputs

- **SMA(n):** Simple average of the last `n` daily closing prices from the market data provider via `_get_provider()`.
- **ATR(14):** Wilder-smoothed Average True Range from 14-period OHLC daily bars.
- **Source:** Schwab daily bars, fetched at export time. No cached or stale values.

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
| 2026-05-11 UTC | OTA-641 | Technicals Classification subsection added under Strategy Scoring: SMA alignment narrative rules (bullish/bearish/clustered/mixed), distance-from-50d label thresholds, computation inputs (SMA, ATR, source). |
| 2026-05-11 UTC | OTA-635 | Strategy Scoring section: Strategy-Structure Compatibility subsection populated. Canonical compatibility map established: SP/WG → credit structures only (BULL_PUT_CREDIT, BEAR_CALL_CREDIT); TR → debit structures only (BULL_CALL_DEBIT, BEAR_PUT_DEBIT); LT → single-leg long options (SINGLE_LONG_CALL, SINGLE_LONG_PUT). Rationale documented: strategy is a mechanism (premium collection vs directional payoff), not a metrics bucket. Resolves the production contradiction where bear_put debit spreads were scored against SP and produced verdicts contradicting their own narrative. `best_fit` semantics under compatibility documented. Scoring formula and weights subsection remains a placeholder under OTA-495. |
| 2026-04-30 22:05 UTC | OTA-495 | Cost Guardrails section populated as the first extraction. Rule moved from CLAUDE.md House Style section to here. CLAUDE.md now references this file for the canonical rule. |
| 2026-04-30 21:33 UTC | OTA-495 | Initial shell created. Sections and TOC defined per OTA-495 scope (Strategy Scoring, Hard Gates, PoP Computation, Health Grade, Position Lifecycle, Signal Freshness, Display Formatting, Cost Guardrails, Validation Baseline). Each section contains a placeholder describing the source material to extract from and the rules to document. Full content extraction is the body of OTA-495 implementation work. |
