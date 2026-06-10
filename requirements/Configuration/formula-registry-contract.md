# Formula Registry Contract

> **Generated:** 2026-06-10 — scanned from `engine_rules.formula_ref` (OTA-689; OTA-836 refresh)
> **Source:** `scripts/seed_engine_config.py` → `build_formula_registry()`
> **Persistence:** `engine_lookups` rows with `owner_app_id='SHARED'`, `lookup_set='formula_registry'`

---

## Purpose

This is the implementation contract for the screening rule library. Every
`formula:<name>` value referenced in `engine_rules.formula_ref` must have a
registered implementation in the rule library before the engine can load.

The engine's startup validation (`insight_engine.md` §6.6) checks that every
`formula_ref` in `engine_rules` has a matching entry in the formula registry.
The registry is the `SHARED/formula_registry` lookup set in `engine_lookups`.

## Contract rules

1. **No orphans.** Every `formula_ref` value in `engine_rules` appears in this
   list. The list is scanned from seeded rules, not hand-maintained.
2. **Build target.** The screening rule library must implement every name below.
3. **Membership check.** The engine's startup validation rejects any
   `formula_ref` that is not in the `SHARED/formula_registry` lookup set.

## Formula list (26 formulas)

Ordered alphabetically by name (matching `build_formula_registry`'s `sorted()`
emission into the SHARED `formula_registry` lookup set).

| # | Formula name | Phase | Source |
|---|---|---|---|
| 1 | `adj_dte_8_13_penalty` | adjustment | Code-only rule (OTA-688); live impl OTA-836 |
| 2 | `adj_sma_alignment_against_trade` | adjustment | Workbook rule; live impl OTA-836 |
| 3 | `bid_ask_tightness` | scoring | TBD formula (OTA-686) |
| 4 | `chart_state_matches_direction` | gate | Code-only rule (OTA-688); live impl OTA-836 |
| 5 | `credit_width` | scoring | TBD formula (OTA-686) |
| 6 | `cushion_penalty_moderate` | adjustment | Code-only rule (OTA-688) |
| 7 | `delta_otm_score` | scoring | TBD formula (OTA-686) |
| 8 | `delta_quality` | scoring | TBD formula (OTA-686) |
| 9 | `earnings_route1_no_viable_window` | gate | Code-only rule (OTA-688) |
| 10 | `earnings_route2_wait_post_window` | gate | Code-only rule (OTA-688) |
| 11 | `earnings_route3_post_entry_better` | gate | Code-only rule (OTA-688) |
| 12 | `earnings_route4_pre_momentum_play` | gate | Code-only rule (OTA-688) |
| 13 | `expected_value` | scoring | Black-Scholes formula |
| 14 | `extension_matches_trade_direction` | adjustment | Code-only rule (OTA-688); live impl OTA-836 |
| 15 | `iv_percentile_cost` | scoring | TBD formula (OTA-686) |
| 16 | `iv_rank` | scoring | Black-Scholes formula |
| 17 | `liquidity` | scoring | TBD formula (OTA-686) |
| 18 | `open_interest` | scoring | TBD formula (OTA-686) |
| 19 | `payout_ratio` | scoring | TBD formula (OTA-686) |
| 20 | `probability_asymmetry_penalty` | adjustment | Code-only rule (OTA-688) |
| 21 | `probability_of_profit` | scoring | Black-Scholes formula |
| 22 | `reward_risk` | scoring | Black-Scholes formula |
| 23 | `runway_score` | scoring | TBD formula (OTA-686) |
| 24 | `sma_alignment_score` | scoring | TBD formula (OTA-686) |
| 25 | `theta_gamma_ratio` | scoring | TBD formula (OTA-686) |
| 26 | `theta_margin_ratio` | scoring | Black-Scholes formula |

> **OTA-836 note:** five formulas that were live in the screening registry but
> never in this contract — `dte_hard_filter`, `dte_warning_penalty`,
> `credit_pct_of_width_floor`, `debit_pct_of_width_ceiling`, `negative_ev_gate`
> — were deregistered (they fired `FORMULA_REGISTRY_DRIFT`; the engine's real EV
> gate is the `total_expected_value` BETWEEN rule). Directional `dir_*` formulas
> are intentionally NOT in this SHARED contract — the directional surface is
> parked (enabled=0) and returns under the deferred surface-scoped-validation
> story.

## Verification

```sql
-- Must return 0 (no orphans)
SELECT r.formula_ref
FROM dbo.engine_rules r
WHERE r.formula_ref IS NOT NULL
  AND REPLACE(r.formula_ref, 'formula:', '') NOT IN (
      SELECT l.lookup_key FROM dbo.engine_lookups l
      WHERE l.owner_app_id = 'SHARED' AND l.lookup_set = 'formula_registry'
  );
```
