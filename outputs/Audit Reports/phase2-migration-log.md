# Phase 2 Migration Verification Log

**Run at:** 2026-05-19 01:00:36 UTC
**Database:** options-analyzer-sql-cus.database.windows.net/options-analyzer-db
**Alembic revision:** ade9a09d8001 (down_revision: 9749dae4bc82)
**Status:** SUCCESS (4th attempt — 3 bugs fixed in migration file)

## Bugs Fixed During Migration

1. **`option_chain_snapshots.symbol` varchar(10) → varchar(20)** — missed in Phase 1b; FK to `symbol_reference.symbol` varchar(20) failed due to length mismatch. Added as section A0 in migration.
2. **`agent_run_log.trace_id` → `otel_trace_id`** — diagnostic script used wrong column name; actual column is `otel_trace_id`.
3. **Duplicate watchlist rows** — `watchlists` table had 2 duplicate (user_id, name) pairs preventing unique index creation. Migration now deduplicates (keeps newest) before creating `ux_watchlists_user_id__name`.

## Verification Results

### A0. Column Widen (Phase 1b catch-up)
- [PASS] option_chain_snapshots.symbol = varchar(20)

### A. Replaced FK Cascade Rules (2)
- [PASS] fk_user_configs_user_id_users — CASCADE
- [PASS] fk_audit_log_user_id_users — SET NULL

### B. New FK Constraints (22)
- [PASS] fk_user_sessions_user_id_users — CASCADE
- [PASS] fk_dashboard_layouts_user_id_users — CASCADE
- [PASS] fk_watchlists_user_id_users — CASCADE
- [PASS] fk_positions_user_id_users — NO_ACTION
- [PASS] fk_trade_candidates_user_id_users — NO_ACTION
- [PASS] fk_trade_recommendations_user_id_users — NO_ACTION
- [PASS] fk_insights_user_id_users — NO_ACTION
- [PASS] fk_user_favorites_user_id_users — CASCADE
- [PASS] fk_symbol_quotes_symbol_symbol_reference — NO_ACTION
- [PASS] fk_symbol_context_symbol_symbol_reference — NO_ACTION
- [PASS] fk_option_chain_snapshots_symbol_symbol_reference — NO_ACTION
- [PASS] fk_watchlist_symbols_symbol_symbol_reference — NO_ACTION
- [PASS] fk_trade_candidates_symbol_symbol_reference — NO_ACTION
- [PASS] fk_analysis_runs_symbol_symbol_reference — NO_ACTION
- [PASS] fk_analyzed_trades_symbol_symbol_reference — NO_ACTION
- [PASS] fk_positions_symbol_symbol_reference — NO_ACTION
- [PASS] fk_trade_log_symbol_symbol_reference — NO_ACTION
- [PASS] fk_trade_recommendations_symbol_symbol_reference — NO_ACTION
- [PASS] fk_user_favorites_symbol_symbol_reference — NO_ACTION
- [PASS] fk_agent_run_log_symbol_symbol_reference — SET NULL
- [PASS] fk_validation_assessments_symbol_symbol_reference — NO_ACTION
- [PASS] fk_insights_source_position_id_positions — SET NULL

### C. ISJSON Check Constraints (29)
- [PASS] ck_positions_trade_structure_isjson
- [PASS] ck_positions_entry_greeks_isjson
- [PASS] ck_positions_entry_sma_alignment_isjson
- [PASS] ck_positions_claude_probability_matrix_isjson
- [PASS] ck_positions_claude_exit_levels_isjson
- [PASS] ck_positions_claude_verdict_isjson
- [PASS] ck_analyzed_trades_score_breakdown_isjson
- [PASS] ck_analyzed_trades_scoring_weights_isjson
- [PASS] ck_analysis_runs_scoring_weights_isjson
- [PASS] ck_analysis_runs_filter_params_isjson
- [PASS] ck_option_chain_snapshots_chain_data_isjson
- [PASS] ck_trade_candidates_legs_isjson
- [PASS] ck_trade_candidates_net_metrics_isjson
- [PASS] ck_trade_candidates_pipeline_components_isjson
- [PASS] ck_trade_candidates_claude_evaluation_isjson
- [PASS] ck_trade_log_legs_isjson
- [PASS] ck_trade_recommendations_market_snapshot_isjson
- [PASS] ck_trade_recommendations_trade_snapshot_isjson
- [PASS] ck_agent_run_log_market_snapshot_isjson
- [PASS] ck_agent_run_log_trade_snapshot_isjson
- [PASS] ck_position_assessments_exit_levels_isjson
- [PASS] ck_position_assessments_market_snapshot_isjson
- [PASS] ck_insights_recommended_actions_isjson
- [PASS] ck_insights_source_signals_isjson
- [PASS] ck_user_configs_extra_settings_isjson
- [PASS] ck_user_favorites_trade_data_isjson
- [PASS] ck_symbol_context_signal_value_isjson
- [PASS] ck_dashboard_layouts_layout_json_isjson
- [PASS] ck_dashboard_layouts_widgets_json_isjson

### D. FK Supporting Indexes (6)
- [PASS] ix_watchlist_symbols_symbol
- [PASS] ix_positions_symbol
- [PASS] ix_trade_log_symbol
- [PASS] ix_trade_recommendations_symbol
- [PASS] ix_user_favorites_symbol
- [PASS] ix_agent_run_log_symbol

### E. §7 Composite/Unique Indexes (14)
- [PASS] ix_symbol_quotes_user_id__symbol__captured_at
- [PASS] ix_option_chain_snapshots_user_id__symbol__captured_at
- [PASS] ix_option_chain_snapshots_symbol__captured_at
- [PASS] ix_symbol_context_symbol__signal_type__expires_at
- [PASS] ix_positions_user_id__status__last_monitored_at
- [PASS] ix_trade_candidates_user_id__scanned_at
- [PASS] ix_trade_candidates_symbol__scanned_at
- [PASS] ix_agent_run_log_user_id__created_at
- [PASS] ix_agent_run_log_otel_trace_id
- [PASS] ix_analyzed_trades_run_id__composite_score
- [PASS] ix_insights_user_id__domain__created_at
- [PASS] ix_insights_source_position_id
- [PASS] ix_user_sessions_user_id__expires_at
- [PASS] ux_watchlists_user_id__name

### Diagnostic Column Name Discrepancies (not bugs — diagnostic script has stale names)
- Diagnostic expects `agent_run_log.trace_id` → actual column is `otel_trace_id`; index `ix_agent_run_log_otel_trace_id` exists
- Diagnostic expects `insights.surfaced_at` → actual column is `created_at`; index `ix_insights_user_id__domain__created_at` exists

## Data Cleanup
- Deleted 2 duplicate watchlist rows (kept newest per user_id+name)
- Deleted associated watchlist_symbols for the older duplicates

## Post-Migration
- Dev App Service restarted: `az webapp start --name options-analyzer-api-dev`
