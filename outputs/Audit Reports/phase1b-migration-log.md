# Phase 1b Migration Verification Log

**Run at:** 2026-05-19 00:12:07 UTC
**Database:** options-analyzer-sql-cus.database.windows.net/options-analyzer-db
**Status:** SUCCESS

## Verification Results

- [PASS] Alembic version = 9749dae4bc82 -- actual=9749dae4bc82
- [PASS] api_symbol column exists
- [PASS] api_symbol type=varchar(20) -- varchar(20)
- [PASS] api_symbol nullable=True
- [PASS] ux_symbol_reference_api_symbol index exists
- [PASS] api_symbol populated for 7 INDEX symbols -- count=7
- [PASS]   DJI -> $DJI
- [PASS]   DJIA -> $DJIA
- [PASS]   INX -> $INX
- [PASS]   NDX -> $NDX
- [PASS]   RUT -> $RUT
- [PASS]   SPX -> $SPX
- [PASS]   VIX -> $VIX
- [PASS] insights.user_id exists
- [PASS] insights.user_id type=varchar(36) -- varchar(36)
- [PASS] insights.source_position_id exists
- [PASS] insights.source_position_id type=varchar(36) -- varchar(36)
- [PASS] user_sessions.user_id type=varchar(36) -- varchar(36)
- [PASS] watchlists.user_id type=varchar(36) -- varchar(36)
- [PASS] trade_recommendations.user_id type=varchar(36) -- varchar(36)
- [PASS] symbol_quotes.symbol type=varchar(20) -- varchar(20)
- [PASS] analysis_runs.symbol type=varchar(20) -- varchar(20)
- [PASS] analyzed_trades.symbol type=varchar(20) -- varchar(20)
- [PASS] trade_log.symbol type=varchar(20) -- varchar(20)
- [PASS] user_favorites.symbol type=varchar(20) -- varchar(20)
- [PASS] user_configs.default_symbol type=varchar(20) -- varchar(20)
- [PASS] symbol_reference.symbol type=varchar(20) -- varchar(20)
- [PASS] symbol_reference has a PK -- name=PK_symbol_reference
- [PASS] validation_assessments.symbol column exists
- [PASS] validation_assessments.ticker column does NOT exist -- correctly removed
- [PASS] ix_validation_assessments_symbol index exists
- [PASS] ix_watchlists_user on watchlists
- [PASS] ix_trade_recommendations_user_symbol on trade_recommendations
- [PASS] ix_symbol_quotes_symbol_time on symbol_quotes
- [PASS] ix_symbol_quotes_user_symbol_time on symbol_quotes
- [PASS] ix_analysis_runs_symbol_time on analysis_runs
- [PASS] ix_analysis_runs_user_symbol on analysis_runs
- [PASS] ix_analyzed_trades_symbol_expiry on analyzed_trades
- [PASS] ix_analyzed_trades_user_symbol on analyzed_trades