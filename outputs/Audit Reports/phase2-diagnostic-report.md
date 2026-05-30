# Phase 2 Diagnostic Report

**Run at:** 2026-05-19 01:01:01 UTC
**Database:** options-analyzer-sql-cus.database.windows.net/options-analyzer-db
**Alembic head:** 9749dae4bc82 (Phase 1b)

## 1. FK Inventory

### Target FKs (from §4)

| Child Table | Child Col | Parent Table | Parent Col | Cascade | Status |
|---|---|---|---|---|---|
| user_sessions | user_id | users | id | CASCADE | PRESENT-AND-CORRECT (fk_user_sessions_user_id_users) |
| user_configs | user_id | users | id | CASCADE | PRESENT-AND-CORRECT (fk_user_configs_user_id_users) |
| dashboard_layouts | user_id | users | id | CASCADE | PRESENT-AND-CORRECT (fk_dashboard_layouts_user_id_users) |
| symbol_quotes | symbol | symbol_reference | symbol | RESTRICT | PRESENT-AND-CORRECT (fk_symbol_quotes_symbol_symbol_reference) |
| symbol_context | symbol | symbol_reference | symbol | RESTRICT | PRESENT-AND-CORRECT (fk_symbol_context_symbol_symbol_reference) |
| option_chain_snapshots | symbol | symbol_reference | symbol | RESTRICT | PRESENT-AND-CORRECT (fk_option_chain_snapshots_symbol_symbol_reference) |
| watchlist_symbols | symbol | symbol_reference | symbol | RESTRICT | PRESENT-AND-CORRECT (fk_watchlist_symbols_symbol_symbol_reference) |
| trade_candidates | symbol | symbol_reference | symbol | RESTRICT | PRESENT-AND-CORRECT (fk_trade_candidates_symbol_symbol_reference) |
| analysis_runs | symbol | symbol_reference | symbol | RESTRICT | PRESENT-AND-CORRECT (fk_analysis_runs_symbol_symbol_reference) |
| analyzed_trades | symbol | symbol_reference | symbol | RESTRICT | PRESENT-AND-CORRECT (fk_analyzed_trades_symbol_symbol_reference) |
| positions | symbol | symbol_reference | symbol | RESTRICT | PRESENT-AND-CORRECT (fk_positions_symbol_symbol_reference) |
| trade_log | symbol | symbol_reference | symbol | RESTRICT | PRESENT-AND-CORRECT (fk_trade_log_symbol_symbol_reference) |
| trade_recommendations | symbol | symbol_reference | symbol | RESTRICT | PRESENT-AND-CORRECT (fk_trade_recommendations_symbol_symbol_reference) |
| user_favorites | symbol | symbol_reference | symbol | RESTRICT | PRESENT-AND-CORRECT (fk_user_favorites_symbol_symbol_reference) |
| agent_run_log | symbol | symbol_reference | symbol | SET_NULL | PRESENT-AND-CORRECT (fk_agent_run_log_symbol_symbol_reference) |
| validation_assessments | symbol | symbol_reference | symbol | RESTRICT | PRESENT-AND-CORRECT (fk_validation_assessments_symbol_symbol_reference) |
| watchlists | user_id | users | id | CASCADE | PRESENT-AND-CORRECT (fk_watchlists_user_id_users) |
| watchlist_symbols | watchlist_id | watchlists | id | CASCADE | PRESENT-AND-CORRECT (FK__watchlist__watch__32AB8735) |
| positions | user_id | users | id | RESTRICT | PRESENT-AND-CORRECT (fk_positions_user_id_users) |
| trade_candidates | user_id | users | id | RESTRICT | PRESENT-AND-CORRECT (fk_trade_candidates_user_id_users) |
| trade_recommendations | user_id | users | id | RESTRICT | PRESENT-AND-CORRECT (fk_trade_recommendations_user_id_users) |
| insights | source_position_id | positions | position_id | SET_NULL | PRESENT-AND-CORRECT (fk_insights_source_position_id_positions) |
| insights | user_id | users | id | RESTRICT | PRESENT-AND-CORRECT (fk_insights_user_id_users) |
| user_favorites | user_id | users | id | CASCADE | PRESENT-AND-CORRECT (fk_user_favorites_user_id_users) |

### Pre-existing FKs (marked 'already exists' in §4)

| Child Table | Child Col | Parent Table | Parent Col | Cascade | Status |
|---|---|---|---|---|---|
| position_assessments | position_id | positions | position_id | -- | PRESENT (NO_ACTION, FK__position___posit__30C33EC3) |
| agent_run_log | user_id | users | id | -- | PRESENT (NO_ACTION, FK__agent_run__user___282DF8C2) |
| analysis_runs | user_id | users | id | -- | PRESENT (NO_ACTION, FK__analysis___user___2DE6D218) |
| analysis_runs | chain_snapshot_id | option_chain_snapshots | id | -- | PRESENT (NO_ACTION, FK__analysis___chain__2CF2ADDF) |
| analyzed_trades | run_id | analysis_runs | id | -- | PRESENT (NO_ACTION, FK__analyzed___run_i__2A164134) |
| analyzed_trades | user_id | users | id | -- | PRESENT (NO_ACTION, FK__analyzed___user___2B0A656D) |
| trade_log | user_id | users | id | -- | PRESENT (NO_ACTION, FK__trade_log__user___2BFE89A6) |
| symbol_quotes | user_id | users | id | -- | PRESENT (NO_ACTION, FK__symbol_qu__user___2EDAF651) |
| option_chain_snapshots | user_id | users | id | -- | PRESENT (NO_ACTION, FK__option_ch__user___2FCF1A8A) |
| audit_log | user_id | users | id | -- | PRESENT (SET_NULL, fk_audit_log_user_id_users) |

### Unexpected FKs (not in §4 target list)

| Child Table | Child Col | Parent Table | Parent Col | Cascade | FK Name |
|---|---|---|---|---|---|
| schwab_tokens | user_id | users | id | NO_ACTION | FK__schwab_to__user___31B762FC |

## 2. Check Constraint Inventory (ISJSON)

| Table | Column | Status |
|---|---|---|
| positions | trade_structure | PRESENT (ck_positions_trade_structure_isjson) |
| positions | entry_greeks | PRESENT (ck_positions_entry_greeks_isjson) |
| positions | entry_sma_alignment | PRESENT (ck_positions_entry_sma_alignment_isjson) |
| positions | claude_probability_matrix | PRESENT (ck_positions_claude_probability_matrix_isjson) |
| positions | claude_exit_levels | PRESENT (ck_positions_claude_exit_levels_isjson) |
| positions | claude_verdict | PRESENT (ck_positions_claude_verdict_isjson) |
| analyzed_trades | score_breakdown | PRESENT (ck_analyzed_trades_score_breakdown_isjson) |
| analyzed_trades | scoring_weights | PRESENT (ck_analyzed_trades_scoring_weights_isjson) |
| analysis_runs | scoring_weights | PRESENT (ck_analysis_runs_scoring_weights_isjson) |
| analysis_runs | filter_params | PRESENT (ck_analysis_runs_filter_params_isjson) |
| option_chain_snapshots | chain_data | PRESENT (ck_option_chain_snapshots_chain_data_isjson) |
| trade_candidates | legs | PRESENT (ck_trade_candidates_legs_isjson) |
| trade_candidates | net_metrics | PRESENT (ck_trade_candidates_net_metrics_isjson) |
| trade_candidates | pipeline_components | PRESENT (ck_trade_candidates_pipeline_components_isjson) |
| trade_candidates | claude_evaluation | PRESENT (ck_trade_candidates_claude_evaluation_isjson) |
| trade_log | legs | PRESENT (ck_trade_log_legs_isjson) |
| trade_recommendations | market_snapshot | PRESENT (ck_trade_recommendations_market_snapshot_isjson) |
| trade_recommendations | trade_snapshot | PRESENT (ck_trade_recommendations_trade_snapshot_isjson) |
| agent_run_log | market_snapshot | PRESENT (ck_agent_run_log_market_snapshot_isjson) |
| agent_run_log | trade_snapshot | PRESENT (ck_agent_run_log_trade_snapshot_isjson) |
| position_assessments | exit_levels | PRESENT (ck_position_assessments_exit_levels_isjson) |
| position_assessments | market_snapshot | PRESENT (ck_position_assessments_market_snapshot_isjson) |
| insights | recommended_actions | PRESENT (ck_insights_recommended_actions_isjson) |
| insights | source_signals | PRESENT (ck_insights_source_signals_isjson) |
| user_configs | extra_settings | PRESENT (ck_user_configs_extra_settings_isjson) |
| user_favorites | trade_data | PRESENT (ck_user_favorites_trade_data_isjson) |
| symbol_context | signal_value | PRESENT (ck_symbol_context_signal_value_isjson) |
| dashboard_layouts | layout_json | PRESENT (ck_dashboard_layouts_layout_json_isjson) |
| dashboard_layouts | widgets_json | PRESENT (ck_dashboard_layouts_widgets_json_isjson) |

**Note:** `options_chain_snapshots` (plural) table EXISTS.
Per prompt: do NOT add ISJSON to `options_chain_snapshots.chain_json`. Skipped.

### Unexpected Check Constraints

None found.

## 3. Index Inventory

### §7 Target Indexes

| Table | Columns | Unique | Status |
|---|---|---|---|
| symbol_quotes | user_id, symbol, captured_at DESC | No | PRESENT-EXACT-MATCH (ix_symbol_quotes_user_id__symbol__captured_at) |
| option_chain_snapshots | user_id, symbol, captured_at DESC | No | PRESENT-EXACT-MATCH (ix_option_chain_snapshots_user_id__symbol__captured_at) |
| option_chain_snapshots | symbol, captured_at DESC | No | PRESENT-EXACT-MATCH (ix_option_chain_snapshots_symbol__captured_at) |
| symbol_context | symbol, signal_type, expires_at | No | PRESENT-EXACT-MATCH (ix_symbol_context_symbol__signal_type__expires_at) |
| positions | user_id, status, last_monitored_at | No | PRESENT-EXACT-MATCH (ix_positions_user_id__status__last_monitored_at) |
| positions | user_id, status | No | PRESENT-EXACT-MATCH (ix_positions_user_status) |
| trade_candidates | user_id, scanned_at DESC | No | PRESENT-EXACT-MATCH (ix_trade_candidates_user_id__scanned_at) |
| trade_candidates | symbol, scanned_at DESC | No | PRESENT-EXACT-MATCH (ix_trade_candidates_symbol__scanned_at) |
| agent_run_log | user_id, created_at DESC | No | PRESENT-EXACT-MATCH (ix_agent_run_log_user_id__created_at) |
| agent_run_log | trace_id | No | MISSING |
| agent_run_log | run_id | No | PRESENT-EXACT-MATCH (ix_agent_run_log_run_id) |
| analyzed_trades | run_id, composite_score DESC | No | PRESENT-EXACT-MATCH (ix_analyzed_trades_run_id__composite_score) |
| insights | user_id, domain, surfaced_at DESC | No | MISSING |
| insights | source_position_id | No | PRESENT-EXACT-MATCH (ix_insights_source_position_id) |
| user_sessions | session_id | Yes | PRESENT-EXACT-MATCH (UQ__user_ses__69B13FDDA611039B) |
| user_sessions | user_id, expires_at | No | PRESENT-EXACT-MATCH (ix_user_sessions_user_id__expires_at) |
| watchlist_symbols | watchlist_id, symbol | Yes | PRESENT-EXACT-MATCH (uq_watchlist_symbol) |
| watchlists | user_id, name | Yes | PRESENT-EXACT-MATCH (ux_watchlists_user_id__name) |

### Phase 1b Created Indexes

| Table | Index Name | §7 Match |
|---|---|---|
| symbol_reference | ux_symbol_reference_api_symbol [api_symbol ASC, unique=True] | extra (no §7 counterpart) |
| watchlists | ix_watchlists_user [user_id ASC, unique=False] | extra (no §7 counterpart) |
| trade_recommendations | ix_trade_recommendations_user_symbol [user_id ASC, symbol ASC, unique=False] | extra (no §7 counterpart) |
| symbol_quotes | ix_symbol_quotes_symbol_time [symbol ASC, captured_at ASC, unique=False] | extra (no §7 counterpart) |
| symbol_quotes | ix_symbol_quotes_user_symbol_time [user_id ASC, symbol ASC, captured_at ASC, unique=False] | partial match to §7 (captured_at direction differs) |
| analysis_runs | ix_analysis_runs_symbol_time [symbol ASC, ran_at ASC, unique=False] | extra (no §7 counterpart) |
| analysis_runs | ix_analysis_runs_user_symbol [user_id ASC, symbol ASC, ran_at ASC, unique=False] | extra (no §7 counterpart) |
| analyzed_trades | ix_analyzed_trades_symbol_expiry [symbol ASC, expiration ASC, unique=False] | extra (no §7 counterpart) |
| analyzed_trades | ix_analyzed_trades_user_symbol [user_id ASC, symbol ASC, captured_at ASC, unique=False] | extra (no §7 counterpart) |
| validation_assessments | ix_validation_assessments_symbol [symbol ASC, unique=False] | extra (no §7 counterpart) |

## 4. Column Existence Check

| Table | Column | Exists | Type | Nullable |
|---|---|---|---|---|
| insights | user_id | Yes | varchar(36) | Yes |
| insights | source_position_id | Yes | varchar(36) | Yes |

## 5. Type Pre-condition Check (ISJSON columns)

| Table | Column | Type | Max Length | OK? |
|---|---|---|---|---|
| positions | trade_structure | varchar | -1 | Yes |
| positions | entry_greeks | varchar | -1 | Yes |
| positions | entry_sma_alignment | varchar | -1 | Yes |
| positions | claude_probability_matrix | varchar | -1 | Yes |
| positions | claude_exit_levels | varchar | -1 | Yes |
| positions | claude_verdict | varchar | -1 | Yes |
| analyzed_trades | score_breakdown | nvarchar | -1 | Yes |
| analyzed_trades | scoring_weights | nvarchar | -1 | Yes |
| analysis_runs | scoring_weights | nvarchar | -1 | Yes |
| analysis_runs | filter_params | nvarchar | -1 | Yes |
| option_chain_snapshots | chain_data | nvarchar | -1 | Yes |
| trade_candidates | legs | varchar | -1 | Yes |
| trade_candidates | net_metrics | varchar | -1 | Yes |
| trade_candidates | pipeline_components | varchar | -1 | Yes |
| trade_candidates | claude_evaluation | varchar | -1 | Yes |
| trade_log | legs | nvarchar | -1 | Yes |
| trade_recommendations | market_snapshot | nvarchar | -1 | Yes |
| trade_recommendations | trade_snapshot | nvarchar | -1 | Yes |
| agent_run_log | market_snapshot | nvarchar | -1 | Yes |
| agent_run_log | trade_snapshot | nvarchar | -1 | Yes |
| position_assessments | exit_levels | varchar | -1 | Yes |
| position_assessments | market_snapshot | varchar | -1 | Yes |
| insights | recommended_actions | varchar | -1 | Yes |
| insights | source_signals | varchar | -1 | Yes |
| user_configs | extra_settings | nvarchar | -1 | Yes |
| user_favorites | trade_data | nvarchar | -1 | Yes |
| symbol_context | signal_value | varchar | -1 | Yes |
| dashboard_layouts | layout_json | varchar | -1 | Yes |
| dashboard_layouts | widgets_json | varchar | -1 | Yes |

## 6. Data Pre-condition Check (FK orphan counts)

| Child Table | Child Col | Parent Table | Parent Col | Orphan Count | Status |
|---|---|---|---|---|---|

### ISJSON Data Validity

| Table | Column | Non-NULL Rows | Invalid JSON | Status |
|---|---|---|---|---|
| positions | trade_structure | 90 | 0 | OK |
| positions | entry_greeks | 90 | 0 | OK |
| positions | entry_sma_alignment | 90 | 0 | OK |
| positions | claude_probability_matrix | 1 | 0 | OK |
| positions | claude_exit_levels | 25 | 0 | OK |
| positions | claude_verdict | 36 | 0 | OK |
| analyzed_trades | score_breakdown | 11375 | 0 | OK |
| analyzed_trades | scoring_weights | 11375 | 0 | OK |
| analysis_runs | scoring_weights | 674 | 0 | OK |
| analysis_runs | filter_params | 674 | 0 | OK |
| option_chain_snapshots | chain_data | 674 | 0 | OK |
| trade_candidates | legs | 334 | 0 | OK |
| trade_candidates | net_metrics | 334 | 0 | OK |
| trade_candidates | pipeline_components | 334 | 0 | OK |
| trade_candidates | claude_evaluation | 20 | 0 | OK |
| trade_log | legs | 0 | 0 | OK |
| trade_recommendations | market_snapshot | 25 | 0 | OK |
| trade_recommendations | trade_snapshot | 25 | 0 | OK |
| agent_run_log | market_snapshot | 643 | 0 | OK |
| agent_run_log | trade_snapshot | 650 | 0 | OK |
| position_assessments | exit_levels | 95 | 0 | OK |
| position_assessments | market_snapshot | 128 | 0 | OK |
| insights | recommended_actions | 0 | 0 | OK |
| insights | source_signals | 0 | 0 | OK |
| user_configs | extra_settings | 2 | 0 | OK |
| user_favorites | trade_data | 2 | 0 | OK |
| symbol_context | signal_value | 558 | 0 | OK |
| dashboard_layouts | layout_json | 0 | 0 | OK |
| dashboard_layouts | widgets_json | 0 | 0 | OK |

## 7. Escalations

None.

## 8. Final Action List

This is the complete list of DDL statements Phase 2 will issue.

### A. Foreign Key Constraints

```sql
```

### B. ISJSON Check Constraints

```sql
```

### C. Indexes

```sql
-- FK supporting indexes (single-column, not covered by §7)

-- §7 named composite/unique indexes
CREATE INDEX [ix_agent_run_log_trace_id] ON [agent_run_log]([trace_id]);
CREATE INDEX [ix_insights_user_id__domain__surfaced_at] ON [insights]([user_id], [domain], [surfaced_at] DESC);
```

### Summary

- **FKs to add:** 0
- **ISJSON checks to add:** 0
- **FK supporting indexes to add:** 0
- **§7 indexes to add:** 2
- **Escalations:** 0
- **Blockers:** 0