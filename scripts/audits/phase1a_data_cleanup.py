"""
Phase 1a — Data Cleanup (single transaction, rollback on failure)

Cleans orphan data identified by Phase 0 audit so that Phase 2 FK constraints
can be applied without violation.

Actions:
  1. INSERT missing symbols into symbol_reference
  2. UPDATE truncated user_id (6232a881-23e9-4954-8ed0-6303ea7d188 -> ...ea7fd188)
  3. DELETE orphan rows from watchlists (test user 00000000-...)
  4. DELETE orphan rows from user_watchlist (dev-user, 00000000-...)
  5. SET agent_run_log.market_snapshot = NULL where value is literal string 'null'

No schema changes. No Alembic migrations. No ORM model changes.

Usage:
    cd <project-root>
    source venv/Scripts/activate
    python scripts/audits/phase1a_data_cleanup.py
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from app.models.session import engine

# ─── Constants ───────────────────────────────────────────────────────────────

TRUNCATED_UID = "6232a881-23e9-4954-8ed0-6303ea7d188"   # 35 chars, missing 'f'
CORRECT_UID   = "6232a881-23e9-4954-8ed0-6303ea7fd188"   # 36 chars, Don's real ID
TEST_UID      = "00000000-0000-0000-0000-000000000001"
DEV_UID       = "dev-user"

# Orphan symbols to insert into symbol_reference.
# (symbol, name, asset_type) — name defaults to symbol for index symbols,
# human-readable for known tickers.
ORPHAN_SYMBOLS = [
    # Index symbols (Schwab API format)
    ("$DJI",   "Dow Jones Industrial Average",    "INDEX"),
    ("$DJIA",  "Dow Jones Industrial Average",    "INDEX"),
    ("$INX",   "S&P 500 Index",                   "INDEX"),
    ("$NDX",   "Nasdaq 100 Index",                "INDEX"),
    ("$RUT",   "Russell 2000 Index",              "INDEX"),
    ("$SPX",   "S&P 500 Index",                   "INDEX"),
    ("$VIX",   "CBOE Volatility Index",           "INDEX"),
    # ETFs
    ("AGG",    "iShares Core U.S. Aggregate Bond ETF",       "ETF"),
    ("GLD",    "SPDR Gold Shares",                            "ETF"),
    ("IEFA",   "iShares Core MSCI EAFE ETF",                 "ETF"),
    ("IEMG",   "iShares Core MSCI Emerging Markets ETF",     "ETF"),
    ("IJH",    "iShares Core S&P Mid-Cap ETF",               "ETF"),
    ("IJR",    "iShares Core S&P Small-Cap ETF",             "ETF"),
    ("IVV",    "iShares Core S&P 500 ETF",                   "ETF"),
    ("IWF",    "iShares Russell 1000 Growth ETF",            "ETF"),
    ("QUAL",   "iShares MSCI USA Quality Factor ETF",        "ETF"),
    ("VB",     "Vanguard Small-Cap ETF",                     "ETF"),
    ("VEA",    "Vanguard FTSE Developed Markets ETF",        "ETF"),
    ("VIG",    "Vanguard Dividend Appreciation ETF",         "ETF"),
    ("VO",     "Vanguard Mid-Cap ETF",                       "ETF"),
    ("VOO",    "Vanguard S&P 500 ETF",                       "ETF"),
    ("VTI",    "Vanguard Total Stock Market ETF",            "ETF"),
    ("VTV",    "Vanguard Value ETF",                         "ETF"),
    ("VUG",    "Vanguard Growth ETF",                        "ETF"),
    ("VWO",    "Vanguard FTSE Emerging Markets ETF",         "ETF"),
    ("VXUS",   "Vanguard Total International Stock ETF",     "ETF"),
    # Stocks
    ("TSLA",   "Tesla Inc",                                  "STOCK"),
    ("WDC",    "Western Digital Corporation",                "STOCK"),
    ("WMT",    "Walmart Inc",                                "STOCK"),
    ("WULF",   "TeraWulf Inc",                               "STOCK"),
    # Legacy/test — from user_watchlist
    ("DJI",    "Dow Jones Industrial Average (legacy)",      "INDEX"),
    ("IVM",    "iShares MSCI USA Minimum Volatility (legacy)", "ETF"),
    # Obvious test data — insert so FK is satisfiable, can be pruned later
    ("XYZNOTAREAL", "Test symbol (non-production)", "TEST"),
]

# Tables with truncated user_id to fix
USER_ID_FIX_TABLES = [
    "watchlists",
    "trade_candidates",
    "positions",
]


async def main():
    run_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"Phase 1a Data Cleanup")
    print(f"Run at: {run_time}")
    print("=" * 60)

    log_lines = []

    def log(msg):
        print(f"  {msg}")
        log_lines.append(msg)

    async with engine.begin() as conn:
        # ── 1. INSERT orphan symbols ─────────────────────────────────
        print("\n[1/5] Inserting missing symbols into symbol_reference...")

        inserted = 0
        skipped = 0
        for sym, name, asset_type in ORPHAN_SYMBOLS:
            # Check if already exists (idempotent)
            exists = await conn.execute(
                text("SELECT COUNT(*) FROM symbol_reference WHERE symbol = :s"),
                {"s": sym}
            )
            if exists.scalar() > 0:
                skipped += 1
                continue

            await conn.execute(
                text("""
                    INSERT INTO symbol_reference (symbol, name, asset_type, last_updated)
                    VALUES (:symbol, :name, :asset_type, SYSUTCDATETIME())
                """),
                {"symbol": sym, "name": name, "asset_type": asset_type}
            )
            inserted += 1
            log(f"INSERT symbol_reference: {sym} ({asset_type})")

        log(f"Symbols: {inserted} inserted, {skipped} already existed")

        # ── 2. Fix truncated user_id ─────────────────────────────────
        print("\n[2/5] Fixing truncated user_id across tables...")

        for tbl in USER_ID_FIX_TABLES:
            result = await conn.execute(
                text(f"UPDATE [{tbl}] SET user_id = :correct WHERE user_id = :truncated"),
                {"correct": CORRECT_UID, "truncated": TRUNCATED_UID}
            )
            count = result.rowcount
            log(f"UPDATE {tbl}.user_id: {count} rows fixed ({TRUNCATED_UID} -> {CORRECT_UID})")

        # ── 3. DELETE orphan watchlists rows ─────────────────────────
        print("\n[3/5] Deleting orphan watchlists rows (test user)...")

        # First delete child watchlist_symbols for orphan watchlists
        result = await conn.execute(
            text("""
                DELETE FROM watchlist_symbols
                WHERE watchlist_id IN (
                    SELECT id FROM watchlists WHERE user_id = :test_uid
                )
            """),
            {"test_uid": TEST_UID}
        )
        log(f"DELETE watchlist_symbols (children of test-user watchlists): {result.rowcount} rows")

        result = await conn.execute(
            text("DELETE FROM watchlists WHERE user_id = :test_uid"),
            {"test_uid": TEST_UID}
        )
        log(f"DELETE watchlists (test user {TEST_UID}): {result.rowcount} rows")

        # ── 4. DELETE orphan user_watchlist rows ─────────────────────
        print("\n[4/5] Deleting orphan user_watchlist rows (slated for drop)...")

        result = await conn.execute(
            text("DELETE FROM user_watchlist WHERE user_id = :dev"),
            {"dev": DEV_UID}
        )
        log(f"DELETE user_watchlist (dev-user): {result.rowcount} rows")

        result = await conn.execute(
            text("DELETE FROM user_watchlist WHERE user_id = :test"),
            {"test": TEST_UID}
        )
        log(f"DELETE user_watchlist (test user): {result.rowcount} rows")

        # ── 5. Fix literal 'null' in agent_run_log.market_snapshot ──
        print("\n[5/5] Setting agent_run_log.market_snapshot = NULL where value is literal 'null'...")

        result = await conn.execute(
            text("""
                UPDATE agent_run_log
                SET market_snapshot = NULL
                WHERE market_snapshot IS NOT NULL AND CAST(market_snapshot AS NVARCHAR(10)) = 'null'
            """)
        )
        log(f"UPDATE agent_run_log.market_snapshot: {result.rowcount} rows set to NULL")

        # ── Verify ───────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("VERIFICATION — re-running orphan counts on cleaned data...")

        # Re-check symbol orphans
        remaining_sym = await conn.execute(text("""
            SELECT COUNT(DISTINCT s.sym) FROM (
                SELECT symbol AS sym FROM symbol_quotes WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                UNION SELECT symbol FROM symbol_context WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                UNION SELECT symbol FROM option_chain_snapshots WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                UNION SELECT symbol FROM watchlist_symbols WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                UNION SELECT symbol FROM trade_candidates WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                UNION SELECT symbol FROM trade_recommendations WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                UNION SELECT symbol FROM agent_run_log WHERE symbol IS NOT NULL AND symbol NOT IN (SELECT symbol FROM symbol_reference)
                UNION SELECT symbol FROM analysis_runs WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                UNION SELECT symbol FROM analyzed_trades WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                UNION SELECT symbol FROM positions WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
            ) s
        """))
        remaining_sym_count = remaining_sym.scalar()
        log(f"VERIFY: Remaining symbol orphans across all tables: {remaining_sym_count}")

        if remaining_sym_count > 0:
            rows = await conn.execute(text("""
                SELECT DISTINCT s.sym FROM (
                    SELECT symbol AS sym FROM symbol_quotes WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                    UNION SELECT symbol FROM symbol_context WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                    UNION SELECT symbol FROM option_chain_snapshots WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                    UNION SELECT symbol FROM watchlist_symbols WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                    UNION SELECT symbol FROM trade_candidates WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                    UNION SELECT symbol FROM trade_recommendations WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                    UNION SELECT symbol FROM agent_run_log WHERE symbol IS NOT NULL AND symbol NOT IN (SELECT symbol FROM symbol_reference)
                    UNION SELECT symbol FROM analysis_runs WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                    UNION SELECT symbol FROM analyzed_trades WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                    UNION SELECT symbol FROM positions WHERE symbol NOT IN (SELECT symbol FROM symbol_reference)
                ) s ORDER BY s.sym
            """))
            remaining = [r[0] for r in rows]
            log(f"  Still orphaned: {', '.join(remaining)}")

        # Re-check user_id orphans
        for tbl in USER_ID_FIX_TABLES:
            result = await conn.execute(
                text(f"""
                    SELECT COUNT(*) FROM [{tbl}] c
                    LEFT JOIN users u ON c.user_id = u.id
                    WHERE c.user_id IS NOT NULL AND u.id IS NULL
                """)
            )
            count = result.scalar()
            log(f"VERIFY: {tbl}.user_id orphans remaining: {count}")

        # Re-check watchlists orphans
        result = await conn.execute(text("""
            SELECT COUNT(*) FROM watchlists w
            LEFT JOIN users u ON w.user_id = u.id
            WHERE w.user_id IS NOT NULL AND u.id IS NULL
        """))
        log(f"VERIFY: watchlists.user_id orphans remaining: {result.scalar()}")

        # Re-check agent_run_log.market_snapshot
        result = await conn.execute(text("""
            SELECT COUNT(*) FROM agent_run_log
            WHERE market_snapshot IS NOT NULL AND ISJSON(market_snapshot) = 0
        """))
        log(f"VERIFY: agent_run_log.market_snapshot invalid JSON remaining: {result.scalar()}")

        # Re-check user_watchlist orphans
        result = await conn.execute(text("""
            SELECT COUNT(*) FROM user_watchlist w
            LEFT JOIN users u ON w.user_id = u.id
            WHERE w.user_id IS NOT NULL AND u.id IS NULL
        """))
        log(f"VERIFY: user_watchlist.user_id orphans remaining: {result.scalar()}")

        # Transaction commits here (engine.begin() context manager)
        print("\n" + "=" * 60)
        print("TRANSACTION COMMITTED SUCCESSFULLY")

    # Write cleanup log
    log_path = PROJECT_ROOT / "phase1a-cleanup-log.md"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("# Phase 1a Data Cleanup Log\n\n")
        f.write(f"**Run at:** {run_time}\n")
        f.write(f"**Database:** options-analyzer-sql-cus.database.windows.net/options-analyzer-db\n\n")
        f.write("## Actions\n\n")
        for line in log_lines:
            f.write(f"- {line}\n")

    print(f"\nCleanup log written to: {log_path}")
    print("No schema changes were made. No Alembic migrations were run.")


if __name__ == "__main__":
    asyncio.run(main())
