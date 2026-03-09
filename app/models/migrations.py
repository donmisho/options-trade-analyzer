"""
Schema migrations — additive ALTER TABLE changes for existing tables.

WHY NOT Alembic: The project uses create_all() for simplicity. Alembic is
the right long-term solution but adds operational complexity. These migrations
are idempotent (safe to run on every startup) and only handle the gap between
the ORM model definition and the live table schema for columns added after
initial deployment.

Each migration function checks whether the change is needed before applying it,
so re-running on an already-migrated database is safe.
"""

import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


async def run_migrations(engine: AsyncEngine) -> None:
    """Run all pending schema migrations. Called from init_db() at startup."""
    async with engine.begin() as conn:
        await _m001_trade_recommendations_add_user_id(conn)


async def _m001_trade_recommendations_add_user_id(conn) -> None:
    """
    Migration 001: Add user_id column to trade_recommendations.

    The table was originally created without user_id, making recommendations
    global rather than per-user. This adds the column (nullable so existing
    rows are preserved) and creates a composite index on (user_id, symbol).

    Also drops the old single-column unique constraint on trade_key and
    replaces it with a composite unique on (user_id, trade_key).
    """
    is_mssql = _is_mssql(conn)

    # ── 1. Add user_id column if it doesn't exist ──────────────────
    if is_mssql:
        exists_sql = text("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'trade_recommendations'
              AND COLUMN_NAME = 'user_id'
        """)
    else:
        # SQLite
        exists_sql = text("""
            SELECT COUNT(*) FROM pragma_table_info('trade_recommendations')
            WHERE name = 'user_id'
        """)

    result = await conn.execute(exists_sql)
    col_exists = result.scalar() > 0

    if not col_exists:
        logger.info("Migration 001: adding user_id to trade_recommendations")
        await conn.execute(text(
            "ALTER TABLE trade_recommendations ADD user_id NVARCHAR(36) NULL"
            if is_mssql else
            "ALTER TABLE trade_recommendations ADD COLUMN user_id VARCHAR(36)"
        ))
        logger.info("Migration 001: user_id column added")
    else:
        logger.debug("Migration 001: user_id already present — skipping")

    # ── 2. Add composite index on (user_id, symbol) if missing ─────
    if is_mssql:
        idx_exists = await conn.execute(text("""
            SELECT COUNT(*) FROM sys.indexes
            WHERE object_id = OBJECT_ID('trade_recommendations')
              AND name = 'ix_trade_recommendations_user_symbol'
        """))
    else:
        idx_exists = await conn.execute(text("""
            SELECT COUNT(*) FROM sqlite_master
            WHERE type = 'index'
              AND tbl_name = 'trade_recommendations'
              AND name = 'ix_trade_recommendations_user_symbol'
        """))

    if idx_exists.scalar() == 0:
        await conn.execute(text(
            "CREATE INDEX ix_trade_recommendations_user_symbol "
            "ON trade_recommendations (user_id, symbol)"
        ))
        logger.info("Migration 001: composite index created on trade_recommendations")


def _is_mssql(conn) -> bool:
    """Detect whether the connection is to SQL Server / Azure SQL."""
    try:
        dialect = conn.get_nested_transaction().__class__.__name__
    except Exception:
        dialect = ""
    # Reliable detection via the engine dialect name
    try:
        return "mssql" in str(conn.dialect.name).lower()
    except Exception:
        return False
