# OTA-683 (follow-up) — Retire un-decomposed compounds to clear evaluation_order collisions

> Follow-up to OTA-683. The compound→atom decomposition created the atomic rules but never retired the
> original compound rules, leaving them bound alongside their atoms. Result: 14 `evaluation_order`
> collisions within `(strategy, phase)`, which the engine validates at load (`insight_engine.md` §6.6) —
> i.e. the seed will not load. OTA-683's acceptance criterion ("compound rules split into atoms" — implying
> the compound is replaced) was not fully met. Regress OTA-683 to Write Prompt; this re-commits as OTA-683.

## Objective (read first — it scopes everything)
All rules are **placeholders**. The goal of this story is a **loadable, runnable seed** — NOT rule-content
correctness. Fix only what blocks the engine from loading (the collisions). Do **not** fix value
divergences, mis-bindings, phase oddities, or penalty semantics — those are explicitly deferred to the
later tuning phase (see Out of scope). Resist the urge to "also fix" anything you notice; if you spot
something beyond the collision fix, report it, do not change it.

## Terminal context
- This terminal: Terminal A
- Concurrent terminals: none — confirm with Don.
- Cross-terminal dependencies: operates on the live dev seed + the decomposition path of the seed importer.
  Touches no project-critical shared file (`app/main.py`, `app/database.py`, `web/src/api/client.js`).

## Required reading
```
cat claude_context/CLAUDE.md
cat claude_context/insight_engine.md                 # §3.6 atomic rules, §6.6 load-time evaluation_order uniqueness
cat claude_context/insight_engine-schema-ddl.md       # §2 engine_rules, engine_strategy_rule_junction
# The OTA-683 decomposition logic in the seed importer (locate it; it emits compound + atoms today)
```

## Confirmed state (dev verification, 2026-05-26)
Collision query returned **14 rows**, every one pairing a keeper rule with a rule on the retire/disable
list below. All collisions are `dupes = 2`, so removing the offending member leaves exactly one rule per
slot — **no renumbering is required.**

| strategy | phase | order | colliding pair (keeper ← retire/disable) |
|---|---|---|---|
| all 4 | adjustment | 1 | `adj_dte_8_13_penalty` ← `adj_stock_extended_in_trade_direction` |
| SP, WG | adjustment | 3 | `adj_cushion_penalty_severe` ← `adj_cushion_barely_above_atr_floor` |
| all 4 | gate | 2 | `earnings_route2_wait_post_window` ← `days_until_next_earnings` |
| SP, WG | gate | 13 | `data_completeness_iv_rank` ← `credit_of_width` |
| LT, TR | gate | 15 | `data_completeness_atr_14` ← `chart_state_confirms_direction` |

## Relevant Context — Do Not Deviate Without Escalation

Source: `insight_engine-schema-ddl.md` §2 + collision analysis
`evaluation_order` is a column on `engine_strategy_rule_junction`, NOT on `engine_rules`. Collisions are
therefore cleared by removing the offending **junction rows**, independent of the rule row's `enabled`
state. Removing a junction row removes that rule from that strategy's phase sequence.

Source: collision analysis + decomposition intent (each compound's atoms already exist and are bound)
**Retire these five compound rules** — their atomic replacements already exist and are bound to the same
strategies, so removing the compound loses no coverage:
- `chart_state_confirms_direction` (LT, TR) — atoms: `chart_state_valid_alignment`, `chart_state_matches_trade_direction`
- `credit_of_width` (SP, WG) — atom: `credit_pct_of_width_floor`
- `debit_of_width` (TR) — atom: `debit_pct_of_width_ceiling`
- `adj_cushion_barely_above_atr_floor` (SP, WG) — atoms: `adj_cushion_vs_atr_gte_floor`, `adj_cushion_vs_atr_lte_ceiling`
- `adj_stock_extended_in_trade_direction` (all 4) — atoms: `adj_stock_extended_magnitude`, `adj_stock_extended_direction_match`

Retire = delete the compound's junction rows, then delete the compound rule from `engine_rules`.

Source: OTA-685 divergence capture + collision analysis
**Unbind `days_until_next_earnings` from all four strategies** (delete its 4 junction rows). This is the
captured sheet earnings gate; the 4-route tree (`earnings_route1…4`) supersedes it for now. KEEP the rule
row in `engine_rules` with `enabled = 0` so the captured divergence survives as a definition for tuning,
but with no junction binding it cannot collide. Do NOT delete the rule row.

Source: OTA-682 model (the OTA-687 repair lesson)
A DB-only cleanup unblocks the current dev engine, but a future rebuild re-runs the importer. **Fix the
importer's decomposition logic so it emits atomic rules ONLY (no leftover compound)** — otherwise the
collisions return on the next rebuild. Phase 0 must locate and characterize this before any change.

Source: directive (placeholders)
Touch nothing beyond the items above. Specifically do NOT: rebind, re-weight, re-order, change thresholds,
move rules between phases, or "correct" any binding. Removing the listed junction rows + the importer fix
is the entire change.

## PHASE 0 — Diagnose, then STOP and report
Locate the decomposition logic in the seed importer and confirm why it emits the original compound rule in
addition to its atoms (e.g. it appends the compound then appends atoms, instead of replacing). Report the
file:line and the precise fix. **STOP. Wait for Don's go before changing anything.**

## PHASE 1 — Fix (after Don's go)
1. Fix the importer so decomposition emits atoms only — no compound rule, no compound junction binding —
   so a clean rebuild reproduces a collision-free seed.
2. In the live dev DB: delete the junction rows for the five compounds, then delete the five compound rows
   from `engine_rules`.
3. Delete the four `days_until_next_earnings` junction rows; set that rule's `engine_rules.enabled = 0`
   (keep the row).
4. Do not renumber — each affected slot now holds exactly one rule.

## Acceptance criteria
- The collision query (below) returns **0 rows** across all strategies and phases.
- The five compound rules are absent from `engine_rules`; none of their junction rows remain.
- `days_until_next_earnings` has zero junction rows and remains in `engine_rules` with `enabled = 0`.
- Scoring weights are untouched — still `SUM(weight) = 1.0000` for all four strategies.
- No strategy is left with an empty gate or adjustment phase.
- The importer, on a clean rebuild, produces a seed with zero collisions (atoms only, no compounds).
- Nothing in the Out-of-scope list was modified.

## Out of scope — DEFERRED TO TUNING (do not touch)
- `debit_pct_of_width_ceiling` is bound to SP/WG (credit strategies) and absent from TR — known mis-binding,
  leave exactly as-is.
- Gate-phase `stock_extended_in_trade_direction` (SP/WG) and `stock_extended_against_entry` (LT) — wrong
  phase / redundancy, leave as-is.
- Cushion BETWEEN penalty applying `-5 + -5` via the two atoms — leave as-is.
- All sheet-vs-code value/threshold divergences (already noted in `rationale`) — leave as-is.
- Any rule-content correctness, weights, or re-binding — tuning phase.

## Verification steps
PowerShell, project root, dev DB:
```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
# apply the importer fix + run the cleanup, then verify in SSMS:
```
```sql
-- 1. Collisions — must return ZERO rows
SELECT s.strategy_key, r.phase, j.evaluation_order, COUNT(*) AS dupes,
       STRING_AGG(r.rule_key, ' | ') AS colliding_rules
FROM dbo.engine_strategy_rule_junction j
JOIN dbo.engine_strategies s ON s.strategy_id = j.strategy_id
JOIN dbo.engine_rules      r ON r.rule_id     = j.rule_id
GROUP BY s.strategy_key, r.phase, j.evaluation_order
HAVING COUNT(*) > 1;

-- 2. Compounds gone (must return ZERO rows)
SELECT rule_key FROM dbo.engine_rules
WHERE rule_key IN ('chart_state_confirms_direction','credit_of_width','debit_of_width',
                   'adj_cushion_barely_above_atr_floor','adj_stock_extended_in_trade_direction');

-- 3. days_until_next_earnings: rule kept (enabled=0), no junction rows
SELECT r.enabled,
       (SELECT COUNT(*) FROM dbo.engine_strategy_rule_junction j WHERE j.rule_id = r.rule_id) AS bindings
FROM dbo.engine_rules r WHERE r.rule_key = 'days_until_next_earnings';  -- expect enabled=0, bindings=0

-- 4. Scoring weights unchanged (must be 1.0000 x4)
SELECT s.strategy_key, SUM(j.weight) AS weight_sum
FROM dbo.engine_strategies s
JOIN dbo.engine_strategy_rule_junction j ON j.strategy_id = s.strategy_id
WHERE j.weight IS NOT NULL GROUP BY s.strategy_key;
```
Expect: query 1 empty, query 2 empty, query 3 = `enabled 0 / bindings 0`, query 4 = four rows at 1.0000.

Post-Build QA Gate: Level 1 — config-data cleanup + importer fix, no existing reader of `engine_*` yet.
Note in commit body.

## Commit instruction
I have been instructed to commit. Do you approve? (yes / no)

## Coordination footer
After this lands, re-run the full seed-verification script. Once collisions = 0 and weights hold, the seed
is load-clean and the engine-core build can begin. (Deferred tuning items above are tracked separately.)

## Commit message template (if committing)
```
OTA-683 fix: retire un-decomposed compounds to clear evaluation_order collisions

Decomposition emitted compound + atoms; the un-retired compounds collided with
keeper rules on shared order slots (14 collisions, blocks engine load). Retires 5
compounds (atoms already cover them), unbinds days_until_next_earnings (kept
enabled=0 as captured divergence), and fixes the importer to emit atoms only so
rebuilds stay clean. No renumber. Placeholder content/mis-bindings deferred to
tuning. QA Level 1.
```
