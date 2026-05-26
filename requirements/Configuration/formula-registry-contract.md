# Formula Registry Contract

> **Generated:** 2026-05-26 — scanned from `engine_rules.formula_ref` (OTA-689)
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

## Formula list (24 formulas)

| # | Formula name | Phase | Source |
|---|---|---|---|
| 1 | `bid_ask_tightness` | scoring | TBD formula (OTA-686) |
| 2 | `chart_state_matches_direction` | gate | Code-only rule (OTA-688) |
| 3 | `credit_width` | scoring | TBD formula (OTA-686) |
| 4 | `cushion_penalty_moderate` | adjustment | Code-only rule (OTA-688) |
| 5 | `delta_otm_score` | scoring | TBD formula (OTA-686) |
| 6 | `delta_quality` | scoring | TBD formula (OTA-686) |
| 7 | `earnings_route1_no_viable_window` | gate | Code-only rule (OTA-688) |
| 8 | `earnings_route2_wait_post_window` | gate | Code-only rule (OTA-688) |
| 9 | `earnings_route3_post_entry_better` | gate | Code-only rule (OTA-688) |
| 10 | `earnings_route4_pre_momentum_play` | gate | Code-only rule (OTA-688) |
| 11 | `expected_value` | scoring | Black-Scholes formula |
| 12 | `extension_matches_trade_direction` | adjustment | Code-only rule (OTA-688) |
| 13 | `iv_percentile_cost` | scoring | TBD formula (OTA-686) |
| 14 | `iv_rank` | scoring | Black-Scholes formula |
| 15 | `liquidity` | scoring | TBD formula (OTA-686) |
| 16 | `open_interest` | scoring | TBD formula (OTA-686) |
| 17 | `payout_ratio` | scoring | TBD formula (OTA-686) |
| 18 | `probability_asymmetry_penalty` | adjustment | Code-only rule (OTA-688) |
| 19 | `probability_of_profit` | scoring | Black-Scholes formula |
| 20 | `reward_risk` | scoring | Black-Scholes formula |
| 21 | `runway_score` | scoring | TBD formula (OTA-686) |
| 22 | `sma_alignment_score` | scoring | TBD formula (OTA-686) |
| 23 | `theta_gamma_ratio` | scoring | TBD formula (OTA-686) |
| 24 | `theta_margin_ratio` | scoring | Black-Scholes formula |

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
