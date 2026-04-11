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
        await _m002_positions_drop_user_fk(conn)
        await _m003_create_named_watchlists(conn)
        await _m004_create_user_sessions(conn)


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


async def _m002_positions_drop_user_fk(conn) -> None:
    """
    Migration 002: Drop FK constraint from positions.user_id (MSSQL only).

    The positions table was initially defined with ForeignKey("users.id").
    SKIP_AUTH dev mode uses sub="00000000-0000-0000-0000-000000000001" which
    won't exist in the users table, causing FK violations on INSERT.

    This migration finds and drops the FK constraint if it still exists.
    The column itself (user_id) is kept — only the constraint is removed.
    Safe to re-run: no-op if the constraint is already gone or never existed.
    """
    if not _is_mssql(conn):
        return  # SQLite doesn't enforce FKs — no action needed

    # Find the FK constraint name dynamically (it's auto-named by SQL Server)
    fk_query = text("""
        SELECT fk.name AS fk_name
        FROM sys.foreign_keys AS fk
        INNER JOIN sys.foreign_key_columns AS fkc
            ON fk.object_id = fkc.constraint_object_id
        INNER JOIN sys.tables AS t
            ON fk.parent_object_id = t.object_id
        INNER JOIN sys.columns AS c
            ON fkc.parent_object_id = c.object_id
           AND fkc.parent_column_id = c.column_id
        WHERE t.name = 'positions'
          AND c.name = 'user_id'
    """)
    result = await conn.execute(fk_query)
    fk_name = result.scalar_one_or_none()

    if fk_name:
        logger.info(f"Migration 002: dropping FK {fk_name} from positions.user_id")
        await conn.execute(text(f"ALTER TABLE positions DROP CONSTRAINT [{fk_name}]"))
        logger.info("Migration 002: FK dropped")
    else:
        logger.debug("Migration 002: no FK on positions.user_id — skipping")


async def _table_exists(conn, table_name: str) -> bool:
    """Return True if table_name exists in the current database."""
    if _is_mssql(conn):
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_NAME = :t"
        ), {"t": table_name})
    else:
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name = :t"
        ), {"t": table_name})
    return result.scalar() > 0


async def _m003_create_named_watchlists(conn) -> None:
    """
    Migration 003: Create watchlists and watchlist_symbols tables (OTA-444).

    SQLAlchemy create_all handles this for fresh installs. This migration
    is for existing deployed databases that pre-date these tables.

    Idempotent: _table_exists checks before CREATE, so re-running is safe.
    """
    is_mssql = _is_mssql(conn)

    # ── 1. Create watchlists table if missing ──────────────────────────
    if not await _table_exists(conn, "watchlists"):
        logger.info("Migration 003: creating watchlists table")
        if is_mssql:
            await conn.execute(text("""
                CREATE TABLE watchlists (
                    id         NVARCHAR(36)  NOT NULL PRIMARY KEY,
                    name       NVARCHAR(100) NOT NULL,
                    user_id    NVARCHAR(255) NOT NULL,
                    is_default BIT           NOT NULL DEFAULT 0,
                    created_at DATETIME2     DEFAULT GETUTCDATE(),
                    updated_at DATETIME2     DEFAULT GETUTCDATE()
                )
            """))
        else:
            await conn.execute(text("""
                CREATE TABLE watchlists (
                    id         VARCHAR(36)  NOT NULL PRIMARY KEY,
                    name       VARCHAR(100) NOT NULL,
                    user_id    VARCHAR(255) NOT NULL,
                    is_default INTEGER      NOT NULL DEFAULT 0,
                    created_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
                )
            """))
        await conn.execute(text(
            "CREATE INDEX ix_watchlists_user ON watchlists (user_id)"
        ))
        logger.info("Migration 003: watchlists table created")
    else:
        logger.debug("Migration 003: watchlists already present — skipping")

    # ── 2. Create watchlist_symbols table if missing ───────────────────
    if not await _table_exists(conn, "watchlist_symbols"):
        logger.info("Migration 003: creating watchlist_symbols table")
        if is_mssql:
            await conn.execute(text("""
                CREATE TABLE watchlist_symbols (
                    id           NVARCHAR(36) NOT NULL PRIMARY KEY,
                    watchlist_id NVARCHAR(36) NOT NULL
                        REFERENCES watchlists(id) ON DELETE CASCADE,
                    symbol       NVARCHAR(20) NOT NULL,
                    added_at     DATETIME2    DEFAULT GETUTCDATE(),
                    CONSTRAINT uq_watchlist_symbol UNIQUE (watchlist_id, symbol)
                )
            """))
        else:
            await conn.execute(text("""
                CREATE TABLE watchlist_symbols (
                    id           VARCHAR(36) NOT NULL PRIMARY KEY,
                    watchlist_id VARCHAR(36) NOT NULL
                        REFERENCES watchlists(id) ON DELETE CASCADE,
                    symbol       VARCHAR(20) NOT NULL,
                    added_at     TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (watchlist_id, symbol)
                )
            """))
        await conn.execute(text(
            "CREATE INDEX ix_watchlist_symbols_watchlist "
            "ON watchlist_symbols (watchlist_id)"
        ))
        logger.info("Migration 003: watchlist_symbols table created")
    else:
        logger.debug("Migration 003: watchlist_symbols already present — skipping")


async def _m004_create_user_sessions(conn) -> None:
    """
    Migration 004: Create user_sessions table for BFF identity management (OTA-461).

    Server-side session store for the OIDC confidential client auth pattern.
    Replaces browser-side MSAL.js token management.

    Idempotent: _table_exists checks before CREATE, so re-running is safe.
    """
    if await _table_exists(conn, "user_sessions"):
        logger.debug("Migration 004: user_sessions already present — skipping")
        return

    logger.info("Migration 004: creating user_sessions table")
    is_mssql = _is_mssql(conn)

    if is_mssql:
        await conn.execute(text("""
            CREATE TABLE user_sessions (
                id                      NVARCHAR(36)  NOT NULL PRIMARY KEY,
                session_id              NVARCHAR(128) NOT NULL UNIQUE,
                user_id                 NVARCHAR(255) NOT NULL,
                provider                NVARCHAR(50)  NOT NULL DEFAULT 'entra',
                email                   NVARCHAR(255),
                display_name            NVARCHAR(255),
                access_token_encrypted  NVARCHAR(MAX),
                refresh_token_encrypted NVARCHAR(MAX),
                id_token                NVARCHAR(MAX),
                token_expires_at        DATETIME2,
                csrf_token              NVARCHAR(128) NOT NULL,
                created_at              DATETIME2     DEFAULT GETUTCDATE(),
                expires_at              DATETIME2     NOT NULL,
                last_active_at          DATETIME2     DEFAULT GETUTCDATE()
            )
        """))
    else:
        await conn.execute(text("""
            CREATE TABLE user_sessions (
                id                      VARCHAR(36)  NOT NULL PRIMARY KEY,
                session_id              VARCHAR(128) NOT NULL UNIQUE,
                user_id                 VARCHAR(255) NOT NULL,
                provider                VARCHAR(50)  NOT NULL DEFAULT 'entra',
                email                   VARCHAR(255),
                display_name            VARCHAR(255),
                access_token_encrypted  TEXT,
                refresh_token_encrypted TEXT,
                id_token                TEXT,
                token_expires_at        TIMESTAMP,
                csrf_token              VARCHAR(128) NOT NULL,
                created_at              TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
                expires_at              TIMESTAMP    NOT NULL,
                last_active_at          TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
            )
        """))

    await conn.execute(text(
        "CREATE INDEX ix_user_sessions_expires_at ON user_sessions (expires_at)"
    ))
    logger.info("Migration 004: user_sessions table created")


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
