"""
Phase 1a-followup -- Symbol Normalization Repair

Fixes two deviations from Phase 1a:
  1. Strips $-prefix from index symbols in all child tables, removes $-prefixed
     parent rows from symbol_reference, ensures canonical (non-prefixed) forms exist.
  2. Removes XYZNOTAREAL test artifact from all tables end-to-end.

Single transaction. Any error rolls back entirely. No schema changes.

Usage:
    cd <project-root>
    source venv/Scripts/activate
    python phase1a_followup_repair.py
"""

import asyncio
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from app.models.session import engine
from app.core.config import settings

# ---- Constants ----

SYMBOL_TABLES = [
    ("symbol_reference",       "symbol"),
    ("symbol_quotes",          "symbol"),
    ("symbol_context",         "symbol"),
    ("option_chain_snapshots", "symbol"),
    ("watchlist_symbols",      "symbol"),
    ("user_watchlist",         "symbol"),
    ("trade_candidates",       "symbol"),
    ("trade_recommendations",  "symbol"),
    ("agent_run_log",          "symbol"),
    ("analysis_runs",          "symbol"),
    ("analyzed_trades",        "symbol"),
    ("positions",              "symbol"),
    ("trade_log",              "symbol"),
    ("user_favorites",         "symbol"),
    ("validation_assessments", "ticker"),
]

CHILD_TABLES = [t for t in SYMBOL_TABLES if t[0] != "symbol_reference"]

CANONICAL_INDEX_FORMS = ["DJI", "DJIA", "INX", "NDX", "RUT", "SPX", "VIX"]

# Names for canonical forms inserted into symbol_reference
CANONICAL_NAMES = {
    "DJI":  "Dow Jones Industrial Average",
    "DJIA": "Dow Jones Industrial Average",
    "INX":  "S&P 500 Index",
    "NDX":  "Nasdaq 100 Index",
    "RUT":  "Russell 2000 Index",
    "SPX":  "S&P 500 Index",
    "VIX":  "CBOE Volatility Index",
}


async def table_exists(conn, tbl):
    r = await conn.execute(text(f"SELECT OBJECT_ID('{tbl}', 'U')"))
    return r.scalar() is not None


async def main():
    run_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    parsed = urllib.parse.urlparse(settings.database_url)
    db_target = f"{parsed.hostname}/{parsed.path.lstrip('/')}"

    print(f"Phase 1a-followup Symbol Normalization Repair")
    print(f"Run at: {run_time}")
    print(f"Database: {db_target}")
    print("=" * 60)

    log = []  # collects all log lines for report
    status = "SUCCESS"
    warnings = []

    def L(msg):
        print(f"  {msg}")
        log.append(msg)

    # FK orphan checks for verification
    FK_SYMBOL_CHECKS = [
        ("symbol_quotes",          "symbol"),
        ("symbol_context",         "symbol"),
        ("option_chain_snapshots", "symbol"),
        ("watchlist_symbols",      "symbol"),
        ("user_watchlist",         "symbol"),
        ("trade_candidates",       "symbol"),
        ("trade_recommendations",  "symbol"),
        ("agent_run_log",          "symbol"),
        ("analysis_runs",          "symbol"),
        ("analyzed_trades",        "symbol"),
        ("positions",              "symbol"),
        ("trade_log",              "symbol"),
        ("user_favorites",         "symbol"),
        ("validation_assessments", "ticker"),
    ]

    # ================================================================
    # REPAIR TRANSACTION
    # ================================================================
    async with engine.begin() as conn:

        # ---- Step 3.1: $-prefix inventory ----
        print("\n[3.1] Inventory $-prefix rows across all symbol-bearing tables...")
        dollar_inventory = {}
        for tbl, col in SYMBOL_TABLES:
            if not await table_exists(conn, tbl):
                L(f"  {tbl}.{col}: TABLE DOES NOT EXIST")
                continue
            r = await conn.execute(text(
                f"SELECT COUNT(*), COUNT(DISTINCT [{col}]) FROM [{tbl}] WHERE [{col}] LIKE '$%'"
            ))
            row = r.fetchone()
            cnt, dist = row[0], row[1]
            dollar_inventory[(tbl, col)] = (cnt, dist)
            if cnt > 0:
                L(f"  {tbl}.{col}: {cnt} rows, {dist} distinct $-prefixed values")
            else:
                L(f"  {tbl}.{col}: 0")

        # ---- Step 3.2: XYZNOTAREAL inventory ----
        print("\n[3.2] Inventory XYZNOTAREAL references...")
        xyz_inventory = {}
        for tbl, col in SYMBOL_TABLES:
            if not await table_exists(conn, tbl):
                continue
            r = await conn.execute(text(
                f"SELECT COUNT(*) FROM [{tbl}] WHERE [{col}] = 'XYZNOTAREAL'"
            ))
            cnt = r.scalar()
            xyz_inventory[(tbl, col)] = cnt
            if cnt > 0:
                L(f"  {tbl}.{col}: {cnt} XYZNOTAREAL rows")
            else:
                L(f"  {tbl}.{col}: 0")

        # ---- Step 3.3: Confirm canonical INDEX forms ----
        print("\n[3.3] Checking canonical INDEX forms in symbol_reference...")
        missing_canonicals = []
        existing_canonicals = []
        for sym in CANONICAL_INDEX_FORMS:
            r = await conn.execute(text(
                "SELECT symbol FROM symbol_reference WHERE symbol = :s"
            ), {"s": sym})
            if r.fetchone() is None:
                missing_canonicals.append(sym)
                L(f"  {sym}: MISSING -- will insert")
            else:
                existing_canonicals.append(sym)
                L(f"  {sym}: exists")

        # ---- Step 4.1: Insert missing canonical INDEX forms ----
        print("\n[4.1] Inserting missing canonical INDEX forms...")
        for sym in missing_canonicals:
            name = CANONICAL_NAMES.get(sym, sym)
            await conn.execute(text("""
                INSERT INTO symbol_reference (symbol, name, asset_type, last_updated)
                VALUES (:symbol, :name, 'INDEX', SYSUTCDATETIME())
            """), {"symbol": sym, "name": name})
            L(f"  INSERT symbol_reference: {sym} ('{name}', INDEX)")
        if not missing_canonicals:
            L("  No missing canonical forms -- all already exist")

        # ---- Step 4.2: Strip $-prefix from child tables ----
        print("\n[4.2] Stripping $-prefix from child tables...")
        for tbl, col in CHILD_TABLES:
            if not await table_exists(conn, tbl):
                continue
            r = await conn.execute(text(
                f"UPDATE [{tbl}] SET [{col}] = SUBSTRING([{col}], 2, LEN([{col}]) - 1) WHERE [{col}] LIKE '$%'"
            ))
            cnt = r.rowcount
            if cnt > 0:
                L(f"  {tbl}.{col}: {cnt} rows stripped of $-prefix")
            else:
                L(f"  {tbl}.{col}: 0")

        # ---- Step 4.3: Delete $-prefix rows from symbol_reference ----
        print("\n[4.3] Deleting $-prefix rows from symbol_reference...")
        r = await conn.execute(text(
            "DELETE FROM symbol_reference WHERE symbol LIKE '$%'"
        ))
        L(f"  Deleted {r.rowcount} $-prefix rows from symbol_reference (expected 7)")

        # ---- Step 4.4: Delete XYZNOTAREAL from child tables ----
        print("\n[4.4] Deleting XYZNOTAREAL from child tables...")
        for tbl, col in CHILD_TABLES:
            if not await table_exists(conn, tbl):
                continue
            r = await conn.execute(text(
                f"DELETE FROM [{tbl}] WHERE [{col}] = 'XYZNOTAREAL'"
            ))
            if r.rowcount > 0:
                L(f"  {tbl}.{col}: {r.rowcount} XYZNOTAREAL rows deleted")
            else:
                L(f"  {tbl}.{col}: 0")

        # ---- Step 4.5: Delete XYZNOTAREAL from symbol_reference ----
        print("\n[4.5] Deleting XYZNOTAREAL from symbol_reference...")
        r = await conn.execute(text(
            "DELETE FROM symbol_reference WHERE symbol = 'XYZNOTAREAL'"
        ))
        L(f"  Deleted {r.rowcount} XYZNOTAREAL row(s) from symbol_reference (expected 1)")

        # Transaction auto-commits here

    print("\n" + "=" * 60)
    print("TRANSACTION COMMITTED")

    # ================================================================
    # POST-COMMIT VERIFICATION (new connection)
    # ================================================================
    print("\n[5] Post-commit verification...")
    async with engine.connect() as conn:

        # 5.1: $% in symbol_reference
        r = await conn.execute(text("SELECT COUNT(*) FROM symbol_reference WHERE symbol LIKE '$%'"))
        cnt = r.scalar()
        L(f"  VERIFY $% in symbol_reference: {cnt} (must be 0)")
        if cnt != 0:
            status = "WARNING"
            warnings.append(f"$-prefix rows remain in symbol_reference: {cnt}")

        # 5.2: $% in child tables
        for tbl, col in CHILD_TABLES:
            if not await table_exists(conn, tbl):
                continue
            r = await conn.execute(text(
                f"SELECT COUNT(*) FROM [{tbl}] WHERE [{col}] LIKE '$%'"
            ))
            cnt = r.scalar()
            L(f"  VERIFY $% in {tbl}.{col}: {cnt} (must be 0)")
            if cnt != 0:
                status = "WARNING"
                warnings.append(f"$-prefix rows remain in {tbl}.{col}: {cnt}")

        # 5.3: XYZNOTAREAL everywhere
        for tbl, col in SYMBOL_TABLES:
            if not await table_exists(conn, tbl):
                continue
            r = await conn.execute(text(
                f"SELECT COUNT(*) FROM [{tbl}] WHERE [{col}] = 'XYZNOTAREAL'"
            ))
            cnt = r.scalar()
            L(f"  VERIFY XYZNOTAREAL in {tbl}.{col}: {cnt} (must be 0)")
            if cnt != 0:
                status = "WARNING"
                warnings.append(f"XYZNOTAREAL remains in {tbl}.{col}: {cnt}")

        # 5.4: Symbol-FK orphan re-check
        print("\n  Re-checking symbol-FK orphans...")
        for tbl, col in FK_SYMBOL_CHECKS:
            if not await table_exists(conn, tbl):
                continue
            r = await conn.execute(text(f"""
                SELECT COUNT(*) FROM [{tbl}] c
                LEFT JOIN symbol_reference sr ON c.[{col}] = sr.symbol
                WHERE c.[{col}] IS NOT NULL AND sr.symbol IS NULL
            """))
            cnt = r.scalar()
            L(f"  VERIFY FK orphans {tbl}.{col} -> symbol_reference: {cnt} (must be 0)")
            if cnt != 0:
                status = "WARNING"
                warnings.append(f"FK orphans remain: {tbl}.{col} has {cnt} orphan rows")

        await conn.rollback()  # read-only, nothing to commit

    # ================================================================
    # GENERATE REPORT
    # ================================================================
    report_lines = []
    W = report_lines.append

    W("# Phase 1a-followup Symbol Normalization Repair -- Log\n")
    W(f"**Run at:** {run_time}")
    W(f"**Database target:** {db_target}")
    W(f"**Status:** {status}\n")

    W("## Diagnostic Findings\n")
    W("### $-prefix inventory (Step 3.1)\n")
    W("| Table | Column | Rows | Distinct |")
    W("|---|---|---|---|")
    for (tbl, col), (cnt, dist) in dollar_inventory.items():
        W(f"| {tbl} | {col} | {cnt} | {dist} |")

    W("\n### XYZNOTAREAL inventory (Step 3.2)\n")
    W("| Table | Column | Rows |")
    W("|---|---|---|")
    for (tbl, col), cnt in xyz_inventory.items():
        W(f"| {tbl} | {col} | {cnt} |")

    W("\n### Missing canonical INDEX forms (Step 3.3)\n")
    if missing_canonicals:
        W(f"Inserted: {', '.join(missing_canonicals)}")
    else:
        W("All canonical forms already existed.")
    if existing_canonicals:
        W(f"Already present: {', '.join(existing_canonicals)}")

    W("\n## Repair Actions\n")
    for line in log:
        if line.startswith("  VERIFY"):
            continue
        if "INSERT" in line or "strip" in line or "Delete" in line or "deleted" in line:
            W(f"- {line.strip()}")

    W("\n## Post-Commit Verification\n")
    for line in log:
        if line.startswith("  VERIFY"):
            W(f"- {line.strip()}")

    W("\n## Notes / Warnings\n")
    if warnings:
        for w in warnings:
            W(f"- WARNING: {w}")
    else:
        W("No warnings. All post-commit checks passed.")

    report_text = "\n".join(report_lines)

    report_path = PROJECT_ROOT / "phase1a-followup-repair-log.md"
    report_path.write_text(report_text, encoding="utf-8")

    # Print full report
    print("\n" + "=" * 60)
    print(report_text)
    print("=" * 60)
    print(f"\nReport: {report_path}")
    print(f"Script: {Path(__file__).resolve()}")
    print("\nRepair transaction committed. No schema changes were made. No Alembic migrations were created.")


if __name__ == "__main__":
    asyncio.run(main())
