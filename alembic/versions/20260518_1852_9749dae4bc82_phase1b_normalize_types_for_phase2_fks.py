"""phase1b_normalize_types_for_phase2_fks

Phase 1b schema expand: normalizes column types and widths to prepare for
Phase 2 FK constraints. No FK or CHECK constraints are added here.

Operations:
  A. Add api_symbol column to symbol_reference + filtered unique index
  B. Populate api_symbol for 7 canonical INDEX symbols
  C. Add user_id and source_position_id to insights
  D. Narrow user_id in user_sessions (varchar 255->36), watchlists (varchar 255->36)
     Convert trade_recommendations.user_id from nvarchar(36) to varchar(36)
  E. Widen symbol columns from varchar(10) to varchar(20) in 6 child tables
  F. Convert symbol_reference.symbol PK from nvarchar(20) to varchar(20)
  G. Rename validation_assessments.ticker to symbol

NOTE: All ALTER COLUMN operations use raw op.execute() instead of op.alter_column()
because Alembic's MSSQL implementation of alter_column performs complex constraint
drop/recreate logic that hangs on Azure SQL with MARS connections. Raw ALTER TABLE
is safe here because Phase 0 confirmed all data fits the target widths.

NOTE: Dependent indexes must be dropped before ALTER COLUMN and recreated after,
because SQL Server does not allow ALTER COLUMN when indexes reference the column.

Revision ID: 9749dae4bc82
Revises: c7d8e9f01234
Create Date: 2026-05-18 18:52:57.958360

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9749dae4bc82'
down_revision: Union[str, Sequence[str], None] = 'c7d8e9f01234'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── A. Add api_symbol column to symbol_reference ──
    op.add_column('symbol_reference',
        sa.Column('api_symbol', sa.String(20), nullable=True))

    # ── B. Create filtered unique index on api_symbol ──
    op.execute("""
        CREATE UNIQUE INDEX ux_symbol_reference_api_symbol
        ON symbol_reference (api_symbol)
        WHERE api_symbol IS NOT NULL
    """)

    # ── C. Populate api_symbol for canonical INDEX rows ──
    op.execute("""
        UPDATE symbol_reference
        SET api_symbol = '$' + symbol
        WHERE symbol IN ('DJI', 'DJIA', 'INX', 'NDX', 'RUT', 'SPX', 'VIX')
    """)

    # ── D. Add new columns to insights ──
    op.add_column('insights',
        sa.Column('user_id', sa.String(36), nullable=True))
    op.add_column('insights',
        sa.Column('source_position_id', sa.String(36), nullable=True))

    # ── E. Narrow user_id columns ──
    # user_sessions.user_id: no dependent indexes
    op.execute("ALTER TABLE user_sessions ALTER COLUMN user_id VARCHAR(36) NOT NULL")

    # watchlists.user_id: drop ix_watchlists_user first
    op.drop_index('ix_watchlists_user', table_name='watchlists')
    op.execute("ALTER TABLE watchlists ALTER COLUMN user_id VARCHAR(36) NOT NULL")
    op.create_index('ix_watchlists_user', 'watchlists', ['user_id'])

    # trade_recommendations.user_id: drop composite index first
    op.drop_index('ix_trade_recommendations_user_symbol', table_name='trade_recommendations')
    op.execute("ALTER TABLE trade_recommendations ALTER COLUMN user_id VARCHAR(36) NULL")
    op.create_index('ix_trade_recommendations_user_symbol', 'trade_recommendations', ['user_id', 'symbol'])

    # ── F. Widen symbol columns from varchar(10) to varchar(20) ──

    # symbol_quotes.symbol: 2 indexes
    op.drop_index('ix_symbol_quotes_symbol_time', table_name='symbol_quotes')
    op.drop_index('ix_symbol_quotes_user_symbol_time', table_name='symbol_quotes')
    op.execute("ALTER TABLE symbol_quotes ALTER COLUMN symbol VARCHAR(20) NOT NULL")
    op.create_index('ix_symbol_quotes_symbol_time', 'symbol_quotes', ['symbol', 'captured_at'])
    op.create_index('ix_symbol_quotes_user_symbol_time', 'symbol_quotes', ['user_id', 'symbol', 'captured_at'])

    # analysis_runs.symbol: 2 indexes
    op.drop_index('ix_analysis_runs_symbol_time', table_name='analysis_runs')
    op.drop_index('ix_analysis_runs_user_symbol', table_name='analysis_runs')
    op.execute("ALTER TABLE analysis_runs ALTER COLUMN symbol VARCHAR(20) NOT NULL")
    op.create_index('ix_analysis_runs_symbol_time', 'analysis_runs', ['symbol', 'ran_at'])
    op.create_index('ix_analysis_runs_user_symbol', 'analysis_runs', ['user_id', 'symbol', 'ran_at'])

    # analyzed_trades.symbol: 2 indexes
    op.drop_index('ix_analyzed_trades_symbol_expiry', table_name='analyzed_trades')
    op.drop_index('ix_analyzed_trades_user_symbol', table_name='analyzed_trades')
    op.execute("ALTER TABLE analyzed_trades ALTER COLUMN symbol VARCHAR(20) NOT NULL")
    op.create_index('ix_analyzed_trades_symbol_expiry', 'analyzed_trades', ['symbol', 'expiration'])
    op.create_index('ix_analyzed_trades_user_symbol', 'analyzed_trades', ['user_id', 'symbol', 'captured_at'])

    # trade_log.symbol: no indexes
    op.execute("ALTER TABLE trade_log ALTER COLUMN symbol VARCHAR(20) NOT NULL")

    # user_favorites.symbol: no indexes
    op.execute("ALTER TABLE user_favorites ALTER COLUMN symbol VARCHAR(20) NOT NULL")

    # user_configs.default_symbol: no indexes
    op.execute("ALTER TABLE user_configs ALTER COLUMN default_symbol VARCHAR(20) NULL")

    # ── G. Convert symbol_reference.symbol PK from nvarchar(20) to varchar(20) ──
    # Drop PK dynamically (system-generated name), alter column, recreate PK.
    op.execute("""
        DECLARE @pk_name NVARCHAR(200);
        SELECT @pk_name = name FROM sys.key_constraints
        WHERE parent_object_id = OBJECT_ID('symbol_reference') AND type = 'PK';
        IF @pk_name IS NOT NULL
        BEGIN
            DECLARE @sql NVARCHAR(MAX) = N'ALTER TABLE symbol_reference DROP CONSTRAINT ' + QUOTENAME(@pk_name);
            EXEC sp_executesql @sql;
        END
    """)
    op.execute("ALTER TABLE symbol_reference ALTER COLUMN symbol VARCHAR(20) NOT NULL")
    op.create_primary_key('PK_symbol_reference', 'symbol_reference', ['symbol'])

    # ── H. Rename validation_assessments.ticker to symbol ──
    # Drop index on ticker first, rename column, recreate index on new name.
    op.execute("""
        IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_validation_assessments_ticker'
                   AND object_id = OBJECT_ID('validation_assessments'))
            DROP INDEX ix_validation_assessments_ticker ON validation_assessments
    """)
    op.execute("EXEC sp_rename 'validation_assessments.ticker', 'symbol', 'COLUMN'")
    op.create_index('ix_validation_assessments_symbol', 'validation_assessments', ['symbol'])


def downgrade() -> None:
    # Reverse H: rename symbol back to ticker
    op.execute("""
        IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_validation_assessments_symbol'
                   AND object_id = OBJECT_ID('validation_assessments'))
            DROP INDEX ix_validation_assessments_symbol ON validation_assessments
    """)
    op.execute("EXEC sp_rename 'validation_assessments.symbol', 'ticker', 'COLUMN'")
    op.create_index('ix_validation_assessments_ticker', 'validation_assessments', ['ticker'])

    # Reverse G: convert symbol_reference.symbol back to nvarchar(20)
    op.execute("""
        DECLARE @pk_name NVARCHAR(200);
        SELECT @pk_name = name FROM sys.key_constraints
        WHERE parent_object_id = OBJECT_ID('symbol_reference') AND type = 'PK';
        IF @pk_name IS NOT NULL
        BEGIN
            DECLARE @sql NVARCHAR(MAX) = N'ALTER TABLE symbol_reference DROP CONSTRAINT ' + QUOTENAME(@pk_name);
            EXEC sp_executesql @sql;
        END
    """)
    op.execute("ALTER TABLE symbol_reference ALTER COLUMN symbol NVARCHAR(20) NOT NULL")
    op.create_primary_key('PK_symbol_reference_restore', 'symbol_reference', ['symbol'])

    # Reverse F: narrow symbol columns back to varchar(10)
    # Drop indexes, alter, recreate
    op.drop_index('ix_analyzed_trades_user_symbol', table_name='analyzed_trades')
    op.drop_index('ix_analyzed_trades_symbol_expiry', table_name='analyzed_trades')
    op.execute("ALTER TABLE analyzed_trades ALTER COLUMN symbol VARCHAR(10) NOT NULL")
    op.create_index('ix_analyzed_trades_symbol_expiry', 'analyzed_trades', ['symbol', 'expiration'])
    op.create_index('ix_analyzed_trades_user_symbol', 'analyzed_trades', ['user_id', 'symbol', 'captured_at'])

    op.drop_index('ix_analysis_runs_user_symbol', table_name='analysis_runs')
    op.drop_index('ix_analysis_runs_symbol_time', table_name='analysis_runs')
    op.execute("ALTER TABLE analysis_runs ALTER COLUMN symbol VARCHAR(10) NOT NULL")
    op.create_index('ix_analysis_runs_symbol_time', 'analysis_runs', ['symbol', 'ran_at'])
    op.create_index('ix_analysis_runs_user_symbol', 'analysis_runs', ['user_id', 'symbol', 'ran_at'])

    op.drop_index('ix_symbol_quotes_user_symbol_time', table_name='symbol_quotes')
    op.drop_index('ix_symbol_quotes_symbol_time', table_name='symbol_quotes')
    op.execute("ALTER TABLE symbol_quotes ALTER COLUMN symbol VARCHAR(10) NOT NULL")
    op.create_index('ix_symbol_quotes_symbol_time', 'symbol_quotes', ['symbol', 'captured_at'])
    op.create_index('ix_symbol_quotes_user_symbol_time', 'symbol_quotes', ['user_id', 'symbol', 'captured_at'])

    op.execute("ALTER TABLE trade_log ALTER COLUMN symbol VARCHAR(10) NOT NULL")
    op.execute("ALTER TABLE user_favorites ALTER COLUMN symbol VARCHAR(10) NOT NULL")
    op.execute("ALTER TABLE user_configs ALTER COLUMN default_symbol VARCHAR(10) NULL")

    # Reverse E: widen user_id columns back
    op.execute("ALTER TABLE user_sessions ALTER COLUMN user_id VARCHAR(255) NOT NULL")

    op.drop_index('ix_watchlists_user', table_name='watchlists')
    op.execute("ALTER TABLE watchlists ALTER COLUMN user_id VARCHAR(255) NOT NULL")
    op.create_index('ix_watchlists_user', 'watchlists', ['user_id'])

    op.drop_index('ix_trade_recommendations_user_symbol', table_name='trade_recommendations')
    op.execute("ALTER TABLE trade_recommendations ALTER COLUMN user_id NVARCHAR(36) NULL")
    op.create_index('ix_trade_recommendations_user_symbol', 'trade_recommendations', ['user_id', 'symbol'])

    # Reverse D: drop insights columns
    op.drop_column('insights', 'source_position_id')
    op.drop_column('insights', 'user_id')

    # Reverse C: clear api_symbol values
    op.execute("UPDATE symbol_reference SET api_symbol = NULL WHERE api_symbol IS NOT NULL")

    # Reverse B: drop unique index
    op.execute("""
        IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_symbol_reference_api_symbol'
                   AND object_id = OBJECT_ID('symbol_reference'))
            DROP INDEX ux_symbol_reference_api_symbol ON symbol_reference
    """)

    # Reverse A: drop api_symbol column
    op.drop_column('symbol_reference', 'api_symbol')
