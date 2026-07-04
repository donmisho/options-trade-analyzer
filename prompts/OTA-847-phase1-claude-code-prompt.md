---
allowedTools:
  - Read
  - Grep
  - Glob
  - Edit
  - Bash(cat*)
  - Bash(python*)
  - Bash(pytest*)
  - Bash(grep*)
---

# OTA-847 — Screening seed↔adapter named-value reconciliation (Phase 1+)

You are working on branch **`OTA-836-build-to-testable`**. Do NOT create a new branch. Do NOT run `git commit` — Don holds the commit gate.

## Status

Your Phase 0 read-only discovery for OTA-847 is **complete** and its findings are accepted. This prompt resolves the two open decisions you flagged (#1 delta leg-specificity, #4 earnings) and authorizes implementation. Two items that were *not* in your original Phase 0 — a suspected cushion unit-mismatch twin in the penalty rules, and the OTA-818/820 catalog-disable rationale — get a short read-only confirm gate (**Phase 0.5**) before any edit.

## Resolved decisions — the contract (Do Not Deviate Without Escalation)

| # | Concept | Disposition |
|---|---|---|
| 1 | delta — **TR** | Re-point `delta_quality`'s delta input `delta` → `long_delta` (debit-spread long leg = directional driver). |
| 1 | delta — **WG** | **Remove** WG's `delta` named-value dependency. WG never scores on delta; its mixed structure means no fixed leg-name is valid. (Gated on Phase 0.5-A non-load-bearing confirm.) |
| 1 | delta — **LT / SP** | No change. LT naked → adapter emits `delta` (correct); SP has no delta dependency. |
| 2 | `cushion_vs_atr_ratio` | Pure rename → `cushion_vs_atr`. Re-point the gate ref. Collapses the OTA-832 phantom distinction. |
| 3 | `cushion_pct` units | Rescale the `cushion_of_price` junction params fraction → percent by **×100 the existing values** (do NOT hand-type new bounds). Plus the penalty-rule twin, if Phase 0.5-B confirms it. |
| 4 | `earnings_days_past_expiry` | **DESCOPE / carve out.** Remove it from the screening data-completeness set so it stops dropping candidates. Do NOT re-point to `dte_after_earnings` in this ticket — that is a sign-inverted semantic against the load-bearing LT 7-day earnings buffer and will be handled in a separate follow-up. Leave a one-line rationale in the seed referencing the follow-up. |

**INVARIANTS (carried from the epic):**
- The adapter catalog is the source of truth for named-value names/units. The seed conforms to the adapter, never the reverse — except #2, which is a confirmed phantom in the seed.
- Fail-closed: removing WG's delta dep and carving #4 are only valid because no live rule consumes them. If Phase 0.5 finds a consumer, STOP.
- No domain branching in engine machinery. All Phase 1 fixes live in `scripts/seed_engine_config.py`; the §6.6 wiring (Phase 4) touches validation/runtime only.
- Single-path. No compensating fallbacks, no hardcoded literals.

## Authoritative adapter catalog (from your Phase 0 — the contract)

| Concept | Adapter name(s) | Tier | Units / semantics |
|---|---|---|---|
| Delta — spreads | `long_delta`, `short_delta` | RAW | per-leg; always populated (B-S fallback floors 0.0, never None) |
| Delta — naked | `delta` | RAW | single-leg; naked only — NOT emitted for spreads |
| Cushion (% of spot) | `cushion_pct` | DERIVED | **PERCENT** (3% → `3.0`) |
| Cushion vs ATR | `cushion_vs_atr` | DERIVED | ATR multiple — `cushion_vs_atr_ratio` does NOT exist |
| ATR | `atr_14` | DERIVED | Wilder ATR(14) |
| Earnings buffer | `dte_after_earnings` | DERIVED | out of scope this ticket — see #4 |

## Mechanism A — Required Reading (run first)

```
cat claude_context/CLAUDE.md
cat claude_context/insight_engine.md
cat claude_context/business-rules.md
cat scripts/seed_engine_config.py
cat app/ota_adapters/options_chain/adapter.py
cat app/insight_engine/validation.py
cat app/insight_engine/engine_runtime.py
```

(Plus the targeted greps in Phase 0.5 for the exact rows you will touch.)

## Mechanism B — Relevant Context (verify, do not trust blindly)

- Write path is `scripts/seed_engine_config.py` only: the `_CANONICAL_EXPRESSIONS` ref overrides (~lines 2108–2118), the data-completeness gate ref/binding logic, and the `cushion_of_price` junction params. #1 TR may also touch the `delta_quality` scoring-formula input. No rule-library `.py` change is expected for #2/#3.
- The §6.6 named-value-catalog check already exists — `_check_named_values_in_catalog` (code `NAMED_VALUE_MISSING`) at `app/insight_engine/validation.py:~547`, plus `_check_null_semantics`. Both are gated behind `input_catalog is not None` (~line 265). `init_engine_runtime` deliberately does NOT pass the catalog (`engine_runtime.py:~616–620`, "OTA-818/820 decision", citing CatalogEntry vs NamedValue shape). That dormancy is exactly why mismatched names slip past load and silently drop candidates at runtime.
- OTA-843 (commit `8f880b3`) is test-only (3 test files); it does not touch the seed. The branch seed is current as of OTA-844 (`fe166ea`). If the 10 `negative_ev_gate` reds are still present (843 not yet merged), they are pre-existing and unrelated to OTA-847 — do not treat them as 847 regressions.
- The OTA-795 cross-consumer harness currently *injects* these mismatched names to make its fixture pass (i.e., it masks the gap). Part of this fix is removing those compensating injections so the suite proves the real seeded catalog (Phase 3).

## Phase 0.5 — Read-only confirmations (HARD GO/NO-GO STOP)

Make NO edits. Answer A–C, then STOP and report.

**A. WG delta is non-load-bearing.** Enumerate every WG screening rule (gate, completeness, scoring, adjustment). Confirm the ONLY WG reference to a delta-family named value is the data-completeness / gate ref — no WG scoring or adjustment formula consumes delta. → If any WG scoring/adjustment consumes delta, **NO-GO**: report and stop.

**B. Cushion penalty-rule unit twin.** Locate the graduated cushion-penalty adjustment rules (the S4.3 decomposition — two atomic adjustment rows; intended bands ~1.0% / 2.0%). Report the units of their seeded threshold params and which named value they read. → If they read `cushion_pct` (percent) but their thresholds are seeded in fraction (e.g. 0.01 / 0.02), they share the #3 unit bug and MUST be rescaled ×100 in this pass. If already percent, note it and leave them. Report the finding either way.

**C. 818/820 disable rationale.** Read the comment at `engine_runtime.py:~616–620`. Confirm the catalog feed was disabled ONLY for the CatalogEntry-vs-NamedValue shape difference. → If it cites any other reason (e.g. false-positive `NAMED_VALUE_MISSING` fires on a clean surface), **NO-GO on Phase 4**: report and stop before re-enabling.

**GO** (to Phase 1) only if A confirms WG delta is non-load-bearing and B's finding is unambiguous. C gates Phase 4 only, not Phases 1–3.

## Phase 1 — Seed re-points (after GO)

In `scripts/seed_engine_config.py` only:

1. **#1 TR:** re-point the `delta_quality` input `delta` → `long_delta`.
2. **#1 WG:** remove the `delta` data-completeness / gate dependency from WG's screening config.
3. **#2:** rename the gate ref `cushion_vs_atr_ratio` → `cushion_vs_atr`.
4. **#3 gate junction:** rescale the `cushion_of_price` junction params ×100 — multiply the existing fraction values, do not retype new bounds.
5. **#3 penalty twin (only if Phase 0.5-B confirmed fraction):** rescale the cushion-penalty adjustment thresholds ×100 into the percent domain.
6. **#4 carve:** remove `earnings_days_past_expiry` from the screening data-completeness set; add a one-line rationale comment referencing the OTA-847 follow-up.

Leave screening's other rows, and the directional / position-health surfaces, untouched.

## Phase 2 — Re-seed & verify rows

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
python scripts/seed_engine_config.py
```

Confirm: screening rows now reference `long_delta` (TR) / `cushion_vs_atr` / percent-domain cushion params; WG has no delta dep; `earnings_days_past_expiry` is gone from completeness; directional and position-health row counts are unchanged.

## Phase 3 — Functional verification (the real gate)

1. Run the end-to-end Steady-Paycheck / screening path and confirm a representative live credit-spread candidate now passes data-completeness and **reaches a verdict** (no silent drop):

```powershell
pytest tests/integration/test_options_chain_adapter.py -q
```

(Expect the cushion / delta / cushion-vs-atr end-to-end and validation-with-live-registry tests to go green. If the 10 `negative_ev_gate` reds persist, they belong to OTA-843, not here.)

2. **Remove the OTA-795 harness's compensating injections** for the now-fixed names (`delta`→`long_delta`, `cushion_vs_atr`, `cushion_pct` percent) so the suite verifies the real seeded catalog. Leave any injection for the carved `earnings_days_past_expiry`, marked `# TODO OTA-847 follow-up` so it isn't lost. Satisfies AC#3 (regression fixture covers the previously-mismatched names).

3. Structural-only regression check that other surfaces still load:

```powershell
pytest tests/insight_engine tests/integration -q
```

## Manual commit gate #1

STOP. Summarize the staged diff (files, line counts) and the test results. The screening fix is committable on its own once a live credit-spread candidate reaches a verdict and the screening tests are green (negative_ev_gate reds excepted). Do NOT commit — Don commits with the `OTA-847 fix:` prefix.

## Phase 4 — §6.6 recurrence guard (only if Phase 0.5-C was GO)

Make the dormant named-value check fire loud at load:

1. Convert each adapter's `CatalogEntry` → `NamedValue` (drop `producer_ref`; both already carry name / tier / value_type / null_semantics).
2. Feed surface-scoped catalogs into `validate_by_surface` so `NAMED_VALUE_MISSING` fires at load for any future name/unit drift.
3. Boot and run surface validation.

**STOP-and-report rule:** if enabling the catalog feed raises `NAMED_VALUE_MISSING` on the **directional** or **position-health** surfaces, that is latent drift on those surfaces — STOP, report the offending names, and do NOT fix them here (they are their own bugs). The screening fix is already committed from gate #1, so this cannot block the critical-path fix.

## Manual commit gate #2

STOP. Report whether the §6.6 feed is clean across all three surfaces or surfaced drift. If clean, summarize the diff for Don to commit (`OTA-847 feat:` for the validation wiring). If it surfaced drift, report and await Don's call — do not commit a broken boot.

## Coordination

- Branch `OTA-836-build-to-testable` only. Screening-repair pair with OTA-843 — 843 (test hygiene) should land first so the engine suite is honest; if it hasn't, exclude the `negative_ev_gate` reds from 847 verification.
- Touches `scripts/seed_engine_config.py` (and, in Phase 4, the validation / runtime wiring). Single seed terminal — do not parallelize with other seed-touching work.
- Do not touch `position_routes.py` or `position_monitor.py`. Do not deploy. Don holds the commit and deploy gates.

QA level: Level 2 (engine-config seed + validation wiring change).
