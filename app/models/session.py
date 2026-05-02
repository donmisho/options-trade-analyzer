"""
Database engine and session management.

WHY async: FastAPI is an async framework. Using async SQLAlchemy means database
queries don't block other requests. With SQLite this doesn't matter much, but
when we upgrade to Azure SQL for multi-user, it becomes essential.

AZURE SQL vs SQLITE:
- SQLite uses aiosqlite (async SQLite driver)
- Azure SQL uses aioodbc (async ODBC driver for SQL Server)
- The connection string format determines which driver is used
"""

import asyncio
import struct
import urllib.parse
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings
from app.models.database import Base
import logging

logger = logging.getLogger(__name__)

# Detect database type and create appropriate engine
database_url = settings.database_url

# Azure SQL: use azure-identity to get an AAD access token and inject it
# via SQL_COPT_SS_ACCESS_TOKEN. This works with both `az login` (local dev)
# and Managed Identity (Azure production) without needing MSAL linked to
# the ODBC driver.
if database_url.startswith("mssql+pyodbc://"):
    parsed = urllib.parse.urlparse(database_url)
    server = parsed.hostname
    port = parsed.port or 1433
    database = parsed.path.lstrip("/")

    # Base ODBC string — no auth attributes (token injected at connect time).
    # MARS_Connection=Yes: required because SQLAlchemy's create_all fires
    # multiple has_table() queries concurrently on one connection; without MARS
    # pyodbc raises "Connection is busy with results for another command".
    _odbc_connect = (
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server={server},{port};"
        f"Database={database};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
        f"MARS_Connection=Yes;"
    )

    SQL_COPT_SS_ACCESS_TOKEN = 1256  # pyodbc constant for AAD token injection

    # Singleton credential — lazily initialized on first DB connection.
    # WHY singleton: DefaultAzureCredential caches tokens internally (~1hr TTL),
    # so all pool connections share one token rather than each making a separate
    # MSI HTTP round-trip. The original per-connection instantiation caused
    # concurrent cold-start requests to race to the MSI endpoint, exhausting
    # the pool before any connection was established.
    # WHY lazy (not module-level): DefaultAzureCredential() can block during
    # construction in some Azure environments. Running it at import time blocks
    # the main thread and hangs uvicorn startup. Lazy init defers construction
    # to the first do_connect call, which runs in a background thread.
    import threading as _threading
    _azure_credential = None
    _azure_credential_lock = _threading.Lock()

    def _get_azure_token_attr() -> dict:
        """Get a fresh AAD token for Azure SQL and pack it for pyodbc."""
        global _azure_credential
        if _azure_credential is None:
            with _azure_credential_lock:
                if _azure_credential is None:
                    from azure.identity import DefaultAzureCredential
                    _azure_credential = DefaultAzureCredential()
        token = _azure_credential.get_token("https://database.windows.net/.default")
        token_bytes = token.token.encode("UTF-16-LE")
        token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
        return {SQL_COPT_SS_ACCESS_TOKEN: token_struct}

    logger.info(f"Using Azure SQL: {server}/{database}")

    engine = create_async_engine(
        f"mssql+aioodbc:///?odbc_connect={urllib.parse.quote_plus(_odbc_connect)}",
        echo=settings.debug,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=10,
        max_overflow=20,
    )

    # WHY do_connect event: connect_args would bake in a token once at startup
    # and it would expire after ~1 hour. This event fires for every new physical
    # connection from the pool, fetching a fresh token each time.
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "do_connect")
    def inject_azure_token(dialect, conn_rec, cargs, cparams):
        cparams["attrs_before"] = _get_azure_token_attr()
elif database_url.startswith("sqlite"):
    logger.info("Using SQLite with aiosqlite driver")

    # SQLite specific engine configuration
    engine = create_async_engine(
        database_url,
        echo=settings.debug,
        connect_args={"check_same_thread": False},  # SQLite needs this for async
    )
else:
    # Fallback for other database types
    logger.warning(f"Unknown database type in URL: {database_url}")
    engine = create_async_engine(
        database_url,
        echo=settings.debug,
    )

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """
    Run Alembic migrations at startup.

    Dev / staging: runs `alembic upgrade head` to apply any pending migrations.
    A fresh empty database gets the full baseline schema from the baseline migration.
    An already-stamped database is a no-op (already at head).

    Production: skipped entirely. Migrations in production are run manually as part
    of the deploy procedure — see docs/runbooks/alembic-stamp-prod.md and
    architecture-plan.md § 7. This prevents accidental schema changes during a
    rolling deploy or slot-swap window.

    Unmanaged legacy state: if the database has application tables but no
    alembic_version table (pre-Alembic state), startup fails with a clear
    instruction to run `alembic stamp f9e59a180957` before restarting.
    """
    from app.core.config import settings

    if settings.app_env == "production":
        logger.info(
            "Production: skipping automatic migration. "
            "Run `alembic upgrade head` manually after deploy — "
            "see docs/runbooks/alembic-stamp-prod.md"
        )
        return

    try:
        # Detect unmanaged legacy state: application tables exist but alembic_version
        # does not.  Running upgrade head against this state would attempt to re-create
        # all tables and fail with "table already exists".  Fail fast with clear guidance.
        async with engine.connect() as conn:
            has_version_table = await conn.run_sync(_alembic_version_table_exists)
            has_app_tables = await conn.run_sync(_any_app_table_exists)

        if has_app_tables and not has_version_table:
            _db_url = settings.database_url
            _parsed = urllib.parse.urlparse(_db_url)
            _target_server = _parsed.hostname or "(unknown host)"
            _target_db = _parsed.path.lstrip("/") or "(unknown db)"
            raise RuntimeError(
                "Database has application tables but no alembic_version table. "
                "This is a pre-Alembic (unmanaged) database. "
                f"\n\nTarget that needs stamping:\n"
                f"  Server:   {_target_server}\n"
                f"  Database: {_target_db}\n\n"
                "Run `alembic stamp f9e59a180957` from the project root "
                "WITH ENV VARS POINTED AT THIS SERVER, "
                "then restart the app."
            )

        # Run migrations — no-op if already at head, creates all tables if empty.
        from pathlib import Path
        from alembic.config import Config
        from alembic import command as alembic_command

        alembic_ini = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
        alembic_cfg = Config(str(alembic_ini))
        # WHY asyncio.to_thread: alembic_command.upgrade() is synchronous and
        # calls asyncio.run() internally (via env.py run_migrations_online).
        # Calling asyncio.run() from within a running event loop raises
        # "RuntimeError: This event loop is already running."
        # Running in a thread-pool worker gives alembic a clean thread with no
        # active event loop, so asyncio.run() can create its own.
        await asyncio.to_thread(alembic_command.upgrade, alembic_cfg, "head")
        logger.info("Database migrations applied (alembic upgrade head)")

    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"Failed to run database migrations: {e}")
        raise


def _alembic_version_table_exists(conn) -> bool:
    """Synchronous helper — detect whether alembic_version table exists."""
    from sqlalchemy import text, inspect
    try:
        return inspect(conn).has_table("alembic_version")
    except Exception:
        return False


def _any_app_table_exists(conn) -> bool:
    """Synchronous helper — detect whether any OTA application table exists."""
    from sqlalchemy import inspect
    try:
        existing = set(inspect(conn).get_table_names())
        return bool(existing - {"alembic_version"})
    except Exception:
        return False


async def get_db() -> AsyncSession:
    """
    Dependency that provides a database session per request.

    Usage in endpoints:
        @router.get("/something")
        async def get_something(db: AsyncSession = Depends(get_db)):
            ...

    WHY Depends: FastAPI's dependency injection ensures each request gets its
    own session, and the session is properly closed when the request finishes,
    even if there's an error.
    """
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
