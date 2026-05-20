"""phase2_fks_isjson_checks_indexes

Phase 2: Add FK constraints, ISJSON check constraints, and remaining §7 indexes.

Operations:
  A0. Widen option_chain_snapshots.symbol from varchar(10) to varchar(20)
      (missed in Phase 1b; required for FK to symbol_reference.symbol varchar(20))
  A. Replace 2 pre-existing FKs with corrected cascade rules:
     - user_configs.user_id: NO_ACTION -> CASCADE
     - audit_log.user_id: NO_ACTION -> SET NULL
  B. Add 22 new FK constraints (parent-before-child order)
  C. Add 29 ISJSON check constraints
  D. Add 6 FK supporting indexes (single-column)
  E. Add 14 §7 composite/unique indexes

Revision ID: ade9a09d8001
Revises: 9749dae4bc82
Create Date: 2026-05-18 19:51:01.884698

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import logging

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = 'ade9a09d8001'
down_revision: Union[str, Sequence[str], None] = '9749dae4bc82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    try:
        _do_upgrade()
    except Exception:
        logger.error("Phase 2 upgrade failed — attempting auto-downgrade")
        try:
            _do_downgrade()
        except Exception:
            logger.error("Auto-downgrade also failed — manual cleanup required")
        raise


def _do_upgrade() -> None:
    # ══════════════════════════════════════════════════════════════
    # A0. Widen option_chain_snapshots.symbol varchar(10) -> varchar(20)
    #     Missed in Phase 1b; required before FK to symbol_reference.symbol
    # ══════════════════════════════════════════════════════════════
    op.drop_index('ix_option_chain_snapshots_symbol_time', table_name='option_chain_snapshots')
    op.drop_index('ix_option_chain_snapshots_user_symbol', table_name='option_chain_snapshots')
    op.execute("ALTER TABLE option_chain_snapshots ALTER COLUMN symbol VARCHAR(20) NOT NULL")
    op.create_index('ix_option_chain_snapshots_symbol_time', 'option_chain_snapshots', ['symbol', 'captured_at'])
    op.create_index('ix_option_chain_snapshots_user_symbol', 'option_chain_snapshots', ['user_id', 'symbol', 'captured_at'])

    # ══════════════════════════════════════════════════════════════
    # A. Replace 2 pre-existing FKs with corrected cascade rules
    # ══════════════════════════════════════════════════════════════

    # A1. user_configs.user_id: NO_ACTION -> CASCADE
    op.execute("""
        DECLARE @fk NVARCHAR(200);
        SELECT @fk = name FROM sys.foreign_keys
        WHERE parent_object_id = OBJECT_ID('user_configs')
          AND referenced_object_id = OBJECT_ID('users');
        IF @fk IS NOT NULL
        BEGIN
            DECLARE @sql NVARCHAR(MAX) = N'ALTER TABLE [user_configs] DROP CONSTRAINT ' + QUOTENAME(@fk);
            EXEC sp_executesql @sql;
        END
    """)
    op.create_foreign_key(
        'fk_user_configs_user_id_users',
        'user_configs', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )

    # A2. audit_log.user_id: NO_ACTION -> SET NULL
    op.execute("""
        DECLARE @fk NVARCHAR(200);
        SELECT @fk = name FROM sys.foreign_keys
        WHERE parent_object_id = OBJECT_ID('audit_log')
          AND referenced_object_id = OBJECT_ID('users');
        IF @fk IS NOT NULL
        BEGIN
            DECLARE @sql NVARCHAR(MAX) = N'ALTER TABLE [audit_log] DROP CONSTRAINT ' + QUOTENAME(@fk);
            EXEC sp_executesql @sql;
        END
    """)
    op.create_foreign_key(
        'fk_audit_log_user_id_users',
        'audit_log', 'users',
        ['user_id'], ['id'],
        ondelete='SET NULL'
    )

    # ══════════════════════════════════════════════════════════════
    # B. Add 22 new FK constraints
    # ══════════════════════════════════════════════════════════════

    # ── B1. FKs to users (parent: users.id) ──
    op.create_foreign_key(
        'fk_user_sessions_user_id_users',
        'user_sessions', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_dashboard_layouts_user_id_users',
        'dashboard_layouts', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_watchlists_user_id_users',
        'watchlists', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_positions_user_id_users',
        'positions', 'users',
        ['user_id'], ['id'],
        ondelete='NO ACTION'  # RESTRICT
    )
    op.create_foreign_key(
        'fk_trade_candidates_user_id_users',
        'trade_candidates', 'users',
        ['user_id'], ['id'],
        ondelete='NO ACTION'  # RESTRICT
    )
    op.create_foreign_key(
        'fk_trade_recommendations_user_id_users',
        'trade_recommendations', 'users',
        ['user_id'], ['id'],
        ondelete='NO ACTION'  # RESTRICT
    )
    op.create_foreign_key(
        'fk_insights_user_id_users',
        'insights', 'users',
        ['user_id'], ['id'],
        ondelete='NO ACTION'  # RESTRICT
    )
    op.create_foreign_key(
        'fk_user_favorites_user_id_users',
        'user_favorites', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )

    # ── B2. FKs to symbol_reference (parent: symbol_reference.symbol) ──
    op.create_foreign_key(
        'fk_symbol_quotes_symbol_symbol_reference',
        'symbol_quotes', 'symbol_reference',
        ['symbol'], ['symbol'],
        ondelete='NO ACTION'  # RESTRICT
    )
    op.create_foreign_key(
        'fk_symbol_context_symbol_symbol_reference',
        'symbol_context', 'symbol_reference',
        ['symbol'], ['symbol'],
        ondelete='NO ACTION'  # RESTRICT
    )
    op.create_foreign_key(
        'fk_option_chain_snapshots_symbol_symbol_reference',
        'option_chain_snapshots', 'symbol_reference',
        ['symbol'], ['symbol'],
        ondelete='NO ACTION'  # RESTRICT
    )
    op.create_foreign_key(
        'fk_watchlist_symbols_symbol_symbol_reference',
        'watchlist_symbols', 'symbol_reference',
        ['symbol'], ['symbol'],
        ondelete='NO ACTION'  # RESTRICT
    )
    op.create_foreign_key(
        'fk_trade_candidates_symbol_symbol_reference',
        'trade_candidates', 'symbol_reference',
        ['symbol'], ['symbol'],
        ondelete='NO ACTION'  # RESTRICT
    )
    op.create_foreign_key(
        'fk_analysis_runs_symbol_symbol_reference',
        'analysis_runs', 'symbol_reference',
        ['symbol'], ['symbol'],
        ondelete='NO ACTION'  # RESTRICT
    )
    op.create_foreign_key(
        'fk_analyzed_trades_symbol_symbol_reference',
        'analyzed_trades', 'symbol_reference',
        ['symbol'], ['symbol'],
        ondelete='NO ACTION'  # RESTRICT
    )
    op.create_foreign_key(
        'fk_positions_symbol_symbol_reference',
        'positions', 'symbol_reference',
        ['symbol'], ['symbol'],
        ondelete='NO ACTION'  # RESTRICT
    )
    op.create_foreign_key(
        'fk_trade_log_symbol_symbol_reference',
        'trade_log', 'symbol_reference',
        ['symbol'], ['symbol'],
        ondelete='NO ACTION'  # RESTRICT
    )
    op.create_foreign_key(
        'fk_trade_recommendations_symbol_symbol_reference',
        'trade_recommendations', 'symbol_reference',
        ['symbol'], ['symbol'],
        ondelete='NO ACTION'  # RESTRICT
    )
    op.create_foreign_key(
        'fk_user_favorites_symbol_symbol_reference',
        'user_favorites', 'symbol_reference',
        ['symbol'], ['symbol'],
        ondelete='NO ACTION'  # RESTRICT
    )
    op.create_foreign_key(
        'fk_agent_run_log_symbol_symbol_reference',
        'agent_run_log', 'symbol_reference',
        ['symbol'], ['symbol'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_validation_assessments_symbol_symbol_reference',
        'validation_assessments', 'symbol_reference',
        ['symbol'], ['symbol'],
        ondelete='NO ACTION'  # RESTRICT
    )

    # ── B3. FKs to positions / watchlists ──
    op.create_foreign_key(
        'fk_insights_source_position_id_positions',
        'insights', 'positions',
        ['source_position_id'], ['position_id'],
        ondelete='SET NULL'
    )

    # watchlist_symbols.watchlist_id -> watchlists.id already exists (skipped)

    # ══════════════════════════════════════════════════════════════
    # C. Add 29 ISJSON check constraints
    # ══════════════════════════════════════════════════════════════

    # positions (6)
    op.execute("ALTER TABLE [positions] ADD CONSTRAINT [ck_positions_trade_structure_isjson] CHECK ([trade_structure] IS NULL OR ISJSON([trade_structure]) = 1)")
    op.execute("ALTER TABLE [positions] ADD CONSTRAINT [ck_positions_entry_greeks_isjson] CHECK ([entry_greeks] IS NULL OR ISJSON([entry_greeks]) = 1)")
    op.execute("ALTER TABLE [positions] ADD CONSTRAINT [ck_positions_entry_sma_alignment_isjson] CHECK ([entry_sma_alignment] IS NULL OR ISJSON([entry_sma_alignment]) = 1)")
    op.execute("ALTER TABLE [positions] ADD CONSTRAINT [ck_positions_claude_probability_matrix_isjson] CHECK ([claude_probability_matrix] IS NULL OR ISJSON([claude_probability_matrix]) = 1)")
    op.execute("ALTER TABLE [positions] ADD CONSTRAINT [ck_positions_claude_exit_levels_isjson] CHECK ([claude_exit_levels] IS NULL OR ISJSON([claude_exit_levels]) = 1)")
    op.execute("ALTER TABLE [positions] ADD CONSTRAINT [ck_positions_claude_verdict_isjson] CHECK ([claude_verdict] IS NULL OR ISJSON([claude_verdict]) = 1)")

    # analyzed_trades (2)
    op.execute("ALTER TABLE [analyzed_trades] ADD CONSTRAINT [ck_analyzed_trades_score_breakdown_isjson] CHECK ([score_breakdown] IS NULL OR ISJSON([score_breakdown]) = 1)")
    op.execute("ALTER TABLE [analyzed_trades] ADD CONSTRAINT [ck_analyzed_trades_scoring_weights_isjson] CHECK ([scoring_weights] IS NULL OR ISJSON([scoring_weights]) = 1)")

    # analysis_runs (2)
    op.execute("ALTER TABLE [analysis_runs] ADD CONSTRAINT [ck_analysis_runs_scoring_weights_isjson] CHECK ([scoring_weights] IS NULL OR ISJSON([scoring_weights]) = 1)")
    op.execute("ALTER TABLE [analysis_runs] ADD CONSTRAINT [ck_analysis_runs_filter_params_isjson] CHECK ([filter_params] IS NULL OR ISJSON([filter_params]) = 1)")

    # option_chain_snapshots (1)
    op.execute("ALTER TABLE [option_chain_snapshots] ADD CONSTRAINT [ck_option_chain_snapshots_chain_data_isjson] CHECK ([chain_data] IS NULL OR ISJSON([chain_data]) = 1)")

    # trade_candidates (4)
    op.execute("ALTER TABLE [trade_candidates] ADD CONSTRAINT [ck_trade_candidates_legs_isjson] CHECK ([legs] IS NULL OR ISJSON([legs]) = 1)")
    op.execute("ALTER TABLE [trade_candidates] ADD CONSTRAINT [ck_trade_candidates_net_metrics_isjson] CHECK ([net_metrics] IS NULL OR ISJSON([net_metrics]) = 1)")
    op.execute("ALTER TABLE [trade_candidates] ADD CONSTRAINT [ck_trade_candidates_pipeline_components_isjson] CHECK ([pipeline_components] IS NULL OR ISJSON([pipeline_components]) = 1)")
    op.execute("ALTER TABLE [trade_candidates] ADD CONSTRAINT [ck_trade_candidates_claude_evaluation_isjson] CHECK ([claude_evaluation] IS NULL OR ISJSON([claude_evaluation]) = 1)")

    # trade_log (1)
    op.execute("ALTER TABLE [trade_log] ADD CONSTRAINT [ck_trade_log_legs_isjson] CHECK ([legs] IS NULL OR ISJSON([legs]) = 1)")

    # trade_recommendations (2)
    op.execute("ALTER TABLE [trade_recommendations] ADD CONSTRAINT [ck_trade_recommendations_market_snapshot_isjson] CHECK ([market_snapshot] IS NULL OR ISJSON([market_snapshot]) = 1)")
    op.execute("ALTER TABLE [trade_recommendations] ADD CONSTRAINT [ck_trade_recommendations_trade_snapshot_isjson] CHECK ([trade_snapshot] IS NULL OR ISJSON([trade_snapshot]) = 1)")

    # agent_run_log (2)
    op.execute("ALTER TABLE [agent_run_log] ADD CONSTRAINT [ck_agent_run_log_market_snapshot_isjson] CHECK ([market_snapshot] IS NULL OR ISJSON([market_snapshot]) = 1)")
    op.execute("ALTER TABLE [agent_run_log] ADD CONSTRAINT [ck_agent_run_log_trade_snapshot_isjson] CHECK ([trade_snapshot] IS NULL OR ISJSON([trade_snapshot]) = 1)")

    # position_assessments (2)
    op.execute("ALTER TABLE [position_assessments] ADD CONSTRAINT [ck_position_assessments_exit_levels_isjson] CHECK ([exit_levels] IS NULL OR ISJSON([exit_levels]) = 1)")
    op.execute("ALTER TABLE [position_assessments] ADD CONSTRAINT [ck_position_assessments_market_snapshot_isjson] CHECK ([market_snapshot] IS NULL OR ISJSON([market_snapshot]) = 1)")

    # insights (2)
    op.execute("ALTER TABLE [insights] ADD CONSTRAINT [ck_insights_recommended_actions_isjson] CHECK ([recommended_actions] IS NULL OR ISJSON([recommended_actions]) = 1)")
    op.execute("ALTER TABLE [insights] ADD CONSTRAINT [ck_insights_source_signals_isjson] CHECK ([source_signals] IS NULL OR ISJSON([source_signals]) = 1)")

    # user_configs (1)
    op.execute("ALTER TABLE [user_configs] ADD CONSTRAINT [ck_user_configs_extra_settings_isjson] CHECK ([extra_settings] IS NULL OR ISJSON([extra_settings]) = 1)")

    # user_favorites (1)
    op.execute("ALTER TABLE [user_favorites] ADD CONSTRAINT [ck_user_favorites_trade_data_isjson] CHECK ([trade_data] IS NULL OR ISJSON([trade_data]) = 1)")

    # symbol_context (1)
    op.execute("ALTER TABLE [symbol_context] ADD CONSTRAINT [ck_symbol_context_signal_value_isjson] CHECK ([signal_value] IS NULL OR ISJSON([signal_value]) = 1)")

    # dashboard_layouts (2)
    op.execute("ALTER TABLE [dashboard_layouts] ADD CONSTRAINT [ck_dashboard_layouts_layout_json_isjson] CHECK ([layout_json] IS NULL OR ISJSON([layout_json]) = 1)")
    op.execute("ALTER TABLE [dashboard_layouts] ADD CONSTRAINT [ck_dashboard_layouts_widgets_json_isjson] CHECK ([widgets_json] IS NULL OR ISJSON([widgets_json]) = 1)")

    # ══════════════════════════════════════════════════════════════
    # D. FK supporting indexes (single-column, not covered by §7)
    # ══════════════════════════════════════════════════════════════
    op.create_index('ix_watchlist_symbols_symbol', 'watchlist_symbols', ['symbol'])
    op.create_index('ix_positions_symbol', 'positions', ['symbol'])
    op.create_index('ix_trade_log_symbol', 'trade_log', ['symbol'])
    op.create_index('ix_trade_recommendations_symbol', 'trade_recommendations', ['symbol'])
    op.create_index('ix_user_favorites_symbol', 'user_favorites', ['symbol'])
    op.create_index('ix_agent_run_log_symbol', 'agent_run_log', ['symbol'])

    # ══════════════════════════════════════════════════════════════
    # E. §7 composite/unique indexes
    # ══════════════════════════════════════════════════════════════

    # symbol_quotes: (user_id, symbol, captured_at DESC)
    op.execute("CREATE INDEX [ix_symbol_quotes_user_id__symbol__captured_at] ON [symbol_quotes]([user_id], [symbol], [captured_at] DESC)")

    # option_chain_snapshots: (user_id, symbol, captured_at DESC)
    op.execute("CREATE INDEX [ix_option_chain_snapshots_user_id__symbol__captured_at] ON [option_chain_snapshots]([user_id], [symbol], [captured_at] DESC)")

    # option_chain_snapshots: (symbol, captured_at DESC)
    op.execute("CREATE INDEX [ix_option_chain_snapshots_symbol__captured_at] ON [option_chain_snapshots]([symbol], [captured_at] DESC)")

    # symbol_context: (symbol, signal_type, expires_at)
    op.create_index('ix_symbol_context_symbol__signal_type__expires_at', 'symbol_context', ['symbol', 'signal_type', 'expires_at'])

    # positions: (user_id, status, last_monitored_at)
    op.create_index('ix_positions_user_id__status__last_monitored_at', 'positions', ['user_id', 'status', 'last_monitored_at'])

    # positions: (user_id, status) -- already exists as ix_positions_user_status (skipped)

    # trade_candidates: (user_id, scanned_at DESC)
    op.execute("CREATE INDEX [ix_trade_candidates_user_id__scanned_at] ON [trade_candidates]([user_id], [scanned_at] DESC)")

    # trade_candidates: (symbol, scanned_at DESC)
    op.execute("CREATE INDEX [ix_trade_candidates_symbol__scanned_at] ON [trade_candidates]([symbol], [scanned_at] DESC)")

    # agent_run_log: (user_id, created_at DESC)
    op.execute("CREATE INDEX [ix_agent_run_log_user_id__created_at] ON [agent_run_log]([user_id], [created_at] DESC)")

    # agent_run_log: (otel_trace_id)
    op.create_index('ix_agent_run_log_otel_trace_id', 'agent_run_log', ['otel_trace_id'])

    # agent_run_log: (run_id) -- already exists as ix_agent_run_log_run_id (skipped)

    # analyzed_trades: (run_id, composite_score DESC)
    op.execute("CREATE INDEX [ix_analyzed_trades_run_id__composite_score] ON [analyzed_trades]([run_id], [composite_score] DESC)")

    # insights: (user_id, domain, created_at DESC)
    op.execute("CREATE INDEX [ix_insights_user_id__domain__created_at] ON [insights]([user_id], [domain], [created_at] DESC)")

    # insights: (source_position_id)
    op.create_index('ix_insights_source_position_id', 'insights', ['source_position_id'])

    # user_sessions: (session_id) UNIQUE -- already exists as UQ__user_ses__... (skipped)

    # user_sessions: (user_id, expires_at)
    op.create_index('ix_user_sessions_user_id__expires_at', 'user_sessions', ['user_id', 'expires_at'])

    # watchlist_symbols: (watchlist_id, symbol) UNIQUE -- already exists as uq_watchlist_symbol (skipped)

    # watchlists: (user_id, name) UNIQUE — deduplicate first
    op.execute("""
        -- Delete watchlist_symbols belonging to older duplicate watchlists
        DELETE ws FROM watchlist_symbols ws
        INNER JOIN (
            SELECT id FROM watchlists w
            WHERE EXISTS (
                SELECT 1 FROM watchlists w2
                WHERE w2.user_id = w.user_id AND w2.name = w.name
                  AND w2.created_at > w.created_at
            )
        ) dup ON ws.watchlist_id = dup.id;
        -- Delete older duplicate watchlists (keep newest per user_id+name)
        DELETE FROM watchlists
        WHERE id IN (
            SELECT w.id FROM watchlists w
            WHERE EXISTS (
                SELECT 1 FROM watchlists w2
                WHERE w2.user_id = w.user_id AND w2.name = w.name
                  AND w2.created_at > w.created_at
            )
        );
    """)
    op.execute("CREATE UNIQUE INDEX [ux_watchlists_user_id__name] ON [watchlists]([user_id], [name])")


def downgrade() -> None:
    _do_downgrade()


def _do_downgrade() -> None:
    # ══════════════════════════════════════════════════════════════
    # Reverse E: Drop §7 composite/unique indexes
    # ══════════════════════════════════════════════════════════════
    _safe_drop_index('ux_watchlists_user_id__name', 'watchlists')
    _safe_drop_index('ix_user_sessions_user_id__expires_at', 'user_sessions')
    _safe_drop_index('ix_insights_source_position_id', 'insights')
    _safe_drop_index('ix_insights_user_id__domain__created_at', 'insights')
    _safe_drop_index('ix_analyzed_trades_run_id__composite_score', 'analyzed_trades')
    _safe_drop_index('ix_agent_run_log_otel_trace_id', 'agent_run_log')
    _safe_drop_index('ix_agent_run_log_user_id__created_at', 'agent_run_log')
    _safe_drop_index('ix_trade_candidates_symbol__scanned_at', 'trade_candidates')
    _safe_drop_index('ix_trade_candidates_user_id__scanned_at', 'trade_candidates')
    _safe_drop_index('ix_positions_user_id__status__last_monitored_at', 'positions')
    _safe_drop_index('ix_symbol_context_symbol__signal_type__expires_at', 'symbol_context')
    _safe_drop_index('ix_option_chain_snapshots_symbol__captured_at', 'option_chain_snapshots')
    _safe_drop_index('ix_option_chain_snapshots_user_id__symbol__captured_at', 'option_chain_snapshots')
    _safe_drop_index('ix_symbol_quotes_user_id__symbol__captured_at', 'symbol_quotes')

    # ══════════════════════════════════════════════════════════════
    # Reverse D: Drop FK supporting indexes
    # ══════════════════════════════════════════════════════════════
    _safe_drop_index('ix_agent_run_log_symbol', 'agent_run_log')
    _safe_drop_index('ix_user_favorites_symbol', 'user_favorites')
    _safe_drop_index('ix_trade_recommendations_symbol', 'trade_recommendations')
    _safe_drop_index('ix_trade_log_symbol', 'trade_log')
    _safe_drop_index('ix_positions_symbol', 'positions')
    _safe_drop_index('ix_watchlist_symbols_symbol', 'watchlist_symbols')

    # ══════════════════════════════════════════════════════════════
    # Reverse C: Drop ISJSON check constraints
    # ══════════════════════════════════════════════════════════════
    _safe_drop_check('ck_dashboard_layouts_widgets_json_isjson', 'dashboard_layouts')
    _safe_drop_check('ck_dashboard_layouts_layout_json_isjson', 'dashboard_layouts')
    _safe_drop_check('ck_symbol_context_signal_value_isjson', 'symbol_context')
    _safe_drop_check('ck_user_favorites_trade_data_isjson', 'user_favorites')
    _safe_drop_check('ck_user_configs_extra_settings_isjson', 'user_configs')
    _safe_drop_check('ck_insights_source_signals_isjson', 'insights')
    _safe_drop_check('ck_insights_recommended_actions_isjson', 'insights')
    _safe_drop_check('ck_position_assessments_market_snapshot_isjson', 'position_assessments')
    _safe_drop_check('ck_position_assessments_exit_levels_isjson', 'position_assessments')
    _safe_drop_check('ck_agent_run_log_trade_snapshot_isjson', 'agent_run_log')
    _safe_drop_check('ck_agent_run_log_market_snapshot_isjson', 'agent_run_log')
    _safe_drop_check('ck_trade_recommendations_trade_snapshot_isjson', 'trade_recommendations')
    _safe_drop_check('ck_trade_recommendations_market_snapshot_isjson', 'trade_recommendations')
    _safe_drop_check('ck_trade_log_legs_isjson', 'trade_log')
    _safe_drop_check('ck_trade_candidates_claude_evaluation_isjson', 'trade_candidates')
    _safe_drop_check('ck_trade_candidates_pipeline_components_isjson', 'trade_candidates')
    _safe_drop_check('ck_trade_candidates_net_metrics_isjson', 'trade_candidates')
    _safe_drop_check('ck_trade_candidates_legs_isjson', 'trade_candidates')
    _safe_drop_check('ck_option_chain_snapshots_chain_data_isjson', 'option_chain_snapshots')
    _safe_drop_check('ck_analysis_runs_filter_params_isjson', 'analysis_runs')
    _safe_drop_check('ck_analysis_runs_scoring_weights_isjson', 'analysis_runs')
    _safe_drop_check('ck_analyzed_trades_scoring_weights_isjson', 'analyzed_trades')
    _safe_drop_check('ck_analyzed_trades_score_breakdown_isjson', 'analyzed_trades')
    _safe_drop_check('ck_positions_claude_verdict_isjson', 'positions')
    _safe_drop_check('ck_positions_claude_exit_levels_isjson', 'positions')
    _safe_drop_check('ck_positions_claude_probability_matrix_isjson', 'positions')
    _safe_drop_check('ck_positions_entry_sma_alignment_isjson', 'positions')
    _safe_drop_check('ck_positions_entry_greeks_isjson', 'positions')
    _safe_drop_check('ck_positions_trade_structure_isjson', 'positions')

    # ══════════════════════════════════════════════════════════════
    # Reverse B: Drop 22 new FK constraints
    # ══════════════════════════════════════════════════════════════
    _safe_drop_fk('fk_insights_source_position_id_positions', 'insights')
    _safe_drop_fk('fk_user_favorites_user_id_users', 'user_favorites')
    _safe_drop_fk('fk_insights_user_id_users', 'insights')
    _safe_drop_fk('fk_trade_recommendations_user_id_users', 'trade_recommendations')
    _safe_drop_fk('fk_trade_candidates_user_id_users', 'trade_candidates')
    _safe_drop_fk('fk_positions_user_id_users', 'positions')
    _safe_drop_fk('fk_watchlists_user_id_users', 'watchlists')
    _safe_drop_fk('fk_validation_assessments_symbol_symbol_reference', 'validation_assessments')
    _safe_drop_fk('fk_agent_run_log_symbol_symbol_reference', 'agent_run_log')
    _safe_drop_fk('fk_user_favorites_symbol_symbol_reference', 'user_favorites')
    _safe_drop_fk('fk_trade_recommendations_symbol_symbol_reference', 'trade_recommendations')
    _safe_drop_fk('fk_trade_log_symbol_symbol_reference', 'trade_log')
    _safe_drop_fk('fk_positions_symbol_symbol_reference', 'positions')
    _safe_drop_fk('fk_analyzed_trades_symbol_symbol_reference', 'analyzed_trades')
    _safe_drop_fk('fk_analysis_runs_symbol_symbol_reference', 'analysis_runs')
    _safe_drop_fk('fk_trade_candidates_symbol_symbol_reference', 'trade_candidates')
    _safe_drop_fk('fk_watchlist_symbols_symbol_symbol_reference', 'watchlist_symbols')
    _safe_drop_fk('fk_option_chain_snapshots_symbol_symbol_reference', 'option_chain_snapshots')
    _safe_drop_fk('fk_symbol_context_symbol_symbol_reference', 'symbol_context')
    _safe_drop_fk('fk_symbol_quotes_symbol_symbol_reference', 'symbol_quotes')
    _safe_drop_fk('fk_dashboard_layouts_user_id_users', 'dashboard_layouts')
    _safe_drop_fk('fk_user_sessions_user_id_users', 'user_sessions')

    # ══════════════════════════════════════════════════════════════
    # Reverse A: Restore original cascade rules on 2 replaced FKs
    # ══════════════════════════════════════════════════════════════

    # A2 reverse: audit_log.user_id back to NO_ACTION
    _safe_drop_fk('fk_audit_log_user_id_users', 'audit_log')
    op.create_foreign_key(
        'fk_audit_log_user_id_users_restore',
        'audit_log', 'users',
        ['user_id'], ['id'],
        ondelete='NO ACTION'
    )

    # A1 reverse: user_configs.user_id back to NO_ACTION
    _safe_drop_fk('fk_user_configs_user_id_users', 'user_configs')
    op.create_foreign_key(
        'fk_user_configs_user_id_users_restore',
        'user_configs', 'users',
        ['user_id'], ['id'],
        ondelete='NO ACTION'
    )

    # A0 reverse: narrow option_chain_snapshots.symbol back to varchar(10)
    _safe_drop_index('ix_option_chain_snapshots_user_symbol', 'option_chain_snapshots')
    _safe_drop_index('ix_option_chain_snapshots_symbol_time', 'option_chain_snapshots')
    op.execute("ALTER TABLE option_chain_snapshots ALTER COLUMN symbol VARCHAR(10) NOT NULL")
    op.create_index('ix_option_chain_snapshots_symbol_time', 'option_chain_snapshots', ['symbol', 'captured_at'])
    op.create_index('ix_option_chain_snapshots_user_symbol', 'option_chain_snapshots', ['user_id', 'symbol', 'captured_at'])


def _safe_drop_index(index_name: str, table_name: str) -> None:
    op.execute(f"""
        IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = '{index_name}'
                   AND object_id = OBJECT_ID('{table_name}'))
            DROP INDEX [{index_name}] ON [{table_name}]
    """)


def _safe_drop_check(constraint_name: str, table_name: str) -> None:
    op.execute(f"""
        IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = '{constraint_name}'
                   AND parent_object_id = OBJECT_ID('{table_name}'))
            ALTER TABLE [{table_name}] DROP CONSTRAINT [{constraint_name}]
    """)


def _safe_drop_fk(constraint_name: str, table_name: str) -> None:
    op.execute(f"""
        IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = '{constraint_name}'
                   AND parent_object_id = OBJECT_ID('{table_name}'))
            ALTER TABLE [{table_name}] DROP CONSTRAINT [{constraint_name}]
    """)
