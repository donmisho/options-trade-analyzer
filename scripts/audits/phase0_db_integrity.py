"""
Phase 0 — Database Integrity Audit (read-only)

Queries the OTA Azure SQL database for orphan FK candidates, trade_key namespace
consistency, JSON column validity, and width/format anomalies.

Outputs: phase0-audit-report.md at project root.
No schema changes. No row updates. Pure diagnostic.

Usage:
    cd <project-root>
    source venv/Scripts/activate   # or venv/bin/activate on Unix
    python scripts/audits/phase0_db_integrity.py
"""

import asyncio
import re
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path so `app.*` imports work
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from app.models.session import engine


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def fetch_all(conn, sql: str):
    result = await conn.execute(text(sql))
    return result.fetchall()


async def fetch_scalar(conn, sql: str):
    result = await conn.execute(text(sql))
    row = result.fetchone()
    return row[0] if row else None


async def table_exists(conn, table_name: str) -> bool:
    sql = f"SELECT OBJECT_ID('{table_name}', 'U')"
    val = await fetch_scalar(conn, sql)
    return val is not None


# ─── Section A — FK Orphan Counts ────────────────────────────────────────────

FK_CANDIDATES = [
    # (child_table, child_col, parent_table, parent_col, notes)
    ("user_sessions",          "user_id",          "users",                  "id",          "Width mismatch (255 vs 36)"),
    ("user_configs",           "user_id",          "users",                  "id",          "Already FK"),
    ("audit_log",              "user_id",          "users",                  "id",          "Already FK"),
    ("dashboard_layouts",      "user_id",          "users",                  "id",          ""),
    ("symbol_quotes",          "user_id",          "users",                  "id",          "Already FK"),
    ("symbol_quotes",          "symbol",           "symbol_reference",       "symbol",      ""),
    ("symbol_context",         "symbol",           "symbol_reference",       "symbol",      ""),
    ("option_chain_snapshots", "user_id",          "users",                  "id",          "Already FK"),
    ("option_chain_snapshots", "symbol",           "symbol_reference",       "symbol",      ""),
    ("watchlists",             "user_id",          "users",                  "id",          "Width mismatch (255 vs 36)"),
    ("watchlist_symbols",      "watchlist_id",     "watchlists",             "id",          "Already FK"),
    ("watchlist_symbols",      "symbol",           "symbol_reference",       "symbol",      ""),
    ("user_watchlist",         "user_id",          "users",                  "id",          "Slated for drop"),
    ("user_watchlist",         "symbol",           "symbol_reference",       "symbol",      "Slated for drop"),
    ("trade_candidates",       "user_id",          "users",                  "id",          ""),
    ("trade_candidates",       "symbol",           "symbol_reference",       "symbol",      ""),
    ("trade_recommendations",  "user_id",          "users",                  "id",          "Width mismatch (72 vs 36)"),
    ("trade_recommendations",  "symbol",           "symbol_reference",       "symbol",      ""),
    ("agent_run_log",          "user_id",          "users",                  "id",          "Already FK"),
    ("agent_run_log",          "symbol",           "symbol_reference",       "symbol",      ""),
    ("analysis_runs",          "user_id",          "users",                  "id",          "Already FK"),
    ("analysis_runs",          "symbol",           "symbol_reference",       "symbol",      ""),
    ("analysis_runs",          "chain_snapshot_id", "option_chain_snapshots", "id",         "Already FK"),
    ("analyzed_trades",        "run_id",           "analysis_runs",          "id",          "Already FK"),
    ("analyzed_trades",        "user_id",          "users",                  "id",          "Already FK"),
    ("analyzed_trades",        "symbol",           "symbol_reference",       "symbol",      ""),
    ("positions",              "user_id",          "users",                  "id",          ""),
    ("positions",              "symbol",           "symbol_reference",       "symbol",      ""),
    ("position_assessments",   "position_id",      "positions",              "position_id", "Already FK"),
    ("trade_log",              "user_id",          "users",                  "id",          "Already FK"),
    ("trade_log",              "symbol",           "symbol_reference",       "symbol",      ""),
    ("user_favorites",         "user_id",          "users",                  "id",          ""),
    ("user_favorites",         "symbol",           "symbol_reference",       "symbol",      ""),
    ("validation_assessments", "ticker",           "symbol_reference",       "symbol",      "Column will be renamed to symbol"),
]


async def audit_fk_orphans(conn):
    """Section A: FK orphan counts."""
    results = []
    total = len(FK_CANDIDATES)

    for i, (child_tbl, child_col, parent_tbl, parent_col, notes) in enumerate(FK_CANDIDATES, 1):
        print(f"  [A {i}/{total}] {child_tbl}.{child_col} → {parent_tbl}.{parent_col}")

        # Check both tables exist
        child_ok = await table_exists(conn, child_tbl)
        parent_ok = await table_exists(conn, parent_tbl)

        if not child_ok:
            results.append({
                "child": child_tbl, "child_col": child_col,
                "parent": parent_tbl, "parent_col": parent_col,
                "notes": notes, "orphan_count": None, "distinct_count": None,
                "samples": [], "error": f"Child table '{child_tbl}' does not exist",
            })
            continue
        if not parent_ok:
            results.append({
                "child": child_tbl, "child_col": child_col,
                "parent": parent_tbl, "parent_col": parent_col,
                "notes": notes, "orphan_count": None, "distinct_count": None,
                "samples": [], "error": f"Parent table '{parent_tbl}' does not exist",
            })
            continue

        # Count orphans
        sql_count = f"""
            SELECT COUNT(*)
            FROM [{child_tbl}] c
            LEFT JOIN [{parent_tbl}] p ON c.[{child_col}] = p.[{parent_col}]
            WHERE c.[{child_col}] IS NOT NULL AND p.[{parent_col}] IS NULL
        """
        orphan_count = await fetch_scalar(conn, sql_count)

        # Distinct orphan values
        sql_distinct = f"""
            SELECT COUNT(DISTINCT c.[{child_col}])
            FROM [{child_tbl}] c
            LEFT JOIN [{parent_tbl}] p ON c.[{child_col}] = p.[{parent_col}]
            WHERE c.[{child_col}] IS NOT NULL AND p.[{parent_col}] IS NULL
        """
        distinct_count = await fetch_scalar(conn, sql_distinct)

        # Sample orphan values (up to 5)
        samples = []
        if orphan_count and orphan_count > 0:
            sql_samples = f"""
                SELECT DISTINCT TOP 5 c.[{child_col}]
                FROM [{child_tbl}] c
                LEFT JOIN [{parent_tbl}] p ON c.[{child_col}] = p.[{parent_col}]
                WHERE c.[{child_col}] IS NOT NULL AND p.[{parent_col}] IS NULL
            """
            rows = await fetch_all(conn, sql_samples)
            samples = [str(r[0]) for r in rows]

        results.append({
            "child": child_tbl, "child_col": child_col,
            "parent": parent_tbl, "parent_col": parent_col,
            "notes": notes, "orphan_count": orphan_count,
            "distinct_count": distinct_count, "samples": samples,
            "error": None,
        })

    # Width anomaly for user_sessions.user_id
    if await table_exists(conn, "user_sessions"):
        over36 = await fetch_scalar(conn,
            "SELECT COUNT(*) FROM [user_sessions] WHERE LEN([user_id]) > 36")
        results.append({
            "child": "user_sessions", "child_col": "user_id (LEN > 36)",
            "parent": "—", "parent_col": "—",
            "notes": "Width anomaly check", "orphan_count": over36,
            "distinct_count": None, "samples": [], "error": None,
        })

    return results


# ─── Section B — trade_key Namespace Audit ───────────────────────────────────

TRADE_KEY_TABLES = [
    ("trade_candidates",      "trade_key"),
    ("trade_recommendations", "trade_key"),
    ("agent_run_log",         "trade_key"),
    ("user_favorites",        "trade_id"),
]

UUID_REGEX = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)


async def audit_trade_key_namespace(conn):
    """Section B: trade_key namespace audit."""
    per_table = []

    for i, (tbl, col) in enumerate(TRADE_KEY_TABLES, 1):
        print(f"  [B {i}/{len(TRADE_KEY_TABLES)}] {tbl}.{col}")

        if not await table_exists(conn, tbl):
            per_table.append({"table": tbl, "col": col, "error": f"Table '{tbl}' does not exist"})
            continue

        total = await fetch_scalar(conn, f"SELECT COUNT(*) FROM [{tbl}] WHERE [{col}] IS NOT NULL")
        distinct = await fetch_scalar(conn, f"SELECT COUNT(DISTINCT [{col}]) FROM [{tbl}] WHERE [{col}] IS NOT NULL")
        min_len = await fetch_scalar(conn, f"SELECT MIN(LEN([{col}])) FROM [{tbl}] WHERE [{col}] IS NOT NULL")
        max_len = await fetch_scalar(conn, f"SELECT MAX(LEN([{col}])) FROM [{tbl}] WHERE [{col}] IS NOT NULL")
        avg_len = await fetch_scalar(conn, f"SELECT AVG(CAST(LEN([{col}]) AS FLOAT)) FROM [{tbl}] WHERE [{col}] IS NOT NULL")

        # Pull all distinct values for UUID check (may be large — limit to 10000)
        rows = await fetch_all(conn, f"SELECT DISTINCT TOP 10000 [{col}] FROM [{tbl}] WHERE [{col}] IS NOT NULL")
        all_vals = [str(r[0]) for r in rows]
        uuid_count = sum(1 for v in all_vals if UUID_REGEX.match(v))
        non_uuid_count = len(all_vals) - uuid_count

        # Sample non-UUID values
        non_uuid_samples = [v for v in all_vals if not UUID_REGEX.match(v)][:10]

        per_table.append({
            "table": tbl, "col": col, "error": None,
            "total": total, "distinct": distinct,
            "min_len": min_len, "max_len": max_len, "avg_len": avg_len,
            "uuid_count": uuid_count, "non_uuid_count": non_uuid_count,
            "non_uuid_samples": non_uuid_samples,
            "distinct_sampled": len(all_vals),
        })

    # Cross-table overlap
    print("  [B overlap] Computing cross-table namespace overlap...")
    overlap = {}

    # trade_recommendations.trade_key NOT IN trade_candidates.trade_key
    if (await table_exists(conn, "trade_recommendations")) and (await table_exists(conn, "trade_candidates")):
        orphan_recs = await fetch_scalar(conn, """
            SELECT COUNT(DISTINCT tr.trade_key)
            FROM trade_recommendations tr
            WHERE tr.trade_key IS NOT NULL
              AND tr.trade_key NOT IN (SELECT tc.trade_key FROM trade_candidates tc WHERE tc.trade_key IS NOT NULL)
        """)
        overlap["recs_not_in_candidates"] = orphan_recs

    # agent_run_log.trade_key NOT IN trade_candidates.trade_key
    if (await table_exists(conn, "agent_run_log")) and (await table_exists(conn, "trade_candidates")):
        orphan_agent = await fetch_scalar(conn, """
            SELECT COUNT(DISTINCT a.trade_key)
            FROM agent_run_log a
            WHERE a.trade_key IS NOT NULL
              AND a.trade_key NOT IN (SELECT tc.trade_key FROM trade_candidates tc WHERE tc.trade_key IS NOT NULL)
        """)
        overlap["agent_not_in_candidates"] = orphan_agent

    # user_favorites.trade_id that are UUIDs AND present in trade_candidates.trade_key
    if (await table_exists(conn, "user_favorites")) and (await table_exists(conn, "trade_candidates")):
        # We need to check UUID format in Python since Azure SQL doesn't have regex
        fav_rows = await fetch_all(conn, """
            SELECT DISTINCT uf.trade_id
            FROM user_favorites uf
            WHERE uf.trade_id IS NOT NULL
        """)
        fav_uuids = [str(r[0]) for r in fav_rows if UUID_REGEX.match(str(r[0]))]

        if fav_uuids:
            # Check how many are in trade_candidates
            # Build batched IN clause (Azure SQL limit ~2100 params, use string concat)
            uuid_list = ",".join(f"'{v}'" for v in fav_uuids[:2000])
            match_count = await fetch_scalar(conn, f"""
                SELECT COUNT(*)
                FROM trade_candidates
                WHERE trade_key IN ({uuid_list})
            """)
            overlap["fav_uuid_in_candidates"] = match_count
            overlap["fav_total_uuids"] = len(fav_uuids)
        else:
            overlap["fav_uuid_in_candidates"] = 0
            overlap["fav_total_uuids"] = 0

    return per_table, overlap


# ─── Section C — JSON Column Validity ────────────────────────────────────────

JSON_COLUMNS = [
    ("positions",              "trade_structure"),
    ("positions",              "entry_greeks"),
    ("positions",              "entry_sma_alignment"),
    ("positions",              "claude_probability_matrix"),
    ("positions",              "claude_exit_levels"),
    ("positions",              "claude_verdict"),
    ("analyzed_trades",        "score_breakdown"),
    ("analyzed_trades",        "scoring_weights"),
    ("analysis_runs",          "scoring_weights"),
    ("analysis_runs",          "filter_params"),
    ("option_chain_snapshots", "chain_data"),
    ("trade_candidates",       "legs"),
    ("trade_candidates",       "net_metrics"),
    ("trade_candidates",       "pipeline_components"),
    ("trade_candidates",       "claude_evaluation"),
    ("trade_log",              "legs"),
    ("trade_recommendations",  "market_snapshot"),
    ("trade_recommendations",  "trade_snapshot"),
    ("agent_run_log",          "market_snapshot"),
    ("agent_run_log",          "trade_snapshot"),
    ("agent_run_log",          "model_response_raw"),
    ("position_assessments",   "claude_read"),
    ("position_assessments",   "exit_levels"),
    ("position_assessments",   "market_snapshot"),
    ("insights",               "recommended_actions"),
    ("insights",               "source_signals"),
    ("user_configs",           "extra_settings"),
    ("user_favorites",         "trade_data"),
    ("symbol_context",         "signal_value"),
    ("dashboard_layouts",      "layout_json"),
    ("dashboard_layouts",      "widgets_json"),
]


async def audit_json_columns(conn):
    """Section C: JSON column validity."""
    results = []
    total = len(JSON_COLUMNS)

    for i, (tbl, col) in enumerate(JSON_COLUMNS, 1):
        print(f"  [C {i}/{total}] {tbl}.{col}")

        if not await table_exists(conn, tbl):
            results.append({"table": tbl, "col": col, "error": f"Table '{tbl}' does not exist"})
            continue

        # Check column exists
        col_exists = await fetch_scalar(conn, f"""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = '{tbl}' AND COLUMN_NAME = '{col}'
        """)
        if not col_exists:
            results.append({"table": tbl, "col": col, "error": f"Column '{col}' does not exist in '{tbl}'"})
            continue

        non_null = await fetch_scalar(conn, f"SELECT COUNT(*) FROM [{tbl}] WHERE [{col}] IS NOT NULL")
        invalid = await fetch_scalar(conn, f"SELECT COUNT(*) FROM [{tbl}] WHERE [{col}] IS NOT NULL AND ISJSON([{col}]) = 0")

        samples = []
        if invalid and invalid > 0:
            sample_rows = await fetch_all(conn, f"""
                SELECT TOP 3 LEFT(CAST([{col}] AS NVARCHAR(MAX)), 200) AS sample_val
                FROM [{tbl}]
                WHERE [{col}] IS NOT NULL AND ISJSON([{col}]) = 0
            """)
            samples = [str(r[0]) for r in sample_rows]

        is_special = (tbl == "agent_run_log" and col == "model_response_raw")

        results.append({
            "table": tbl, "col": col, "error": None,
            "non_null": non_null, "invalid": invalid,
            "samples": samples, "special_case": is_special,
        })

    return results


# ─── Section D — Width and Format Anomalies ──────────────────────────────────

async def audit_width_anomalies(conn):
    """Section D: width and format anomalies."""
    findings = {}

    # D1: user_id columns wider than 36 chars
    print("  [D1] user_id width anomalies...")
    user_id_tables = [
        "users", "user_configs", "audit_log", "user_sessions",
        "dashboard_layouts", "symbol_quotes", "option_chain_snapshots",
        "watchlists", "watchlist_symbols", "user_watchlist",
        "trade_candidates", "trade_recommendations", "agent_run_log",
        "analysis_runs", "analyzed_trades", "positions",
        "position_assessments", "trade_log", "user_favorites",
        "insights", "deploy_log",
    ]
    d1_results = []
    for tbl in user_id_tables:
        if not await table_exists(conn, tbl):
            continue
        # Check if user_id column exists
        uid_col = "id" if tbl == "users" else "user_id"
        col_exists = await fetch_scalar(conn, f"""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = '{tbl}' AND COLUMN_NAME = '{uid_col}'
        """)
        if not col_exists:
            continue
        over36 = await fetch_scalar(conn, f"SELECT COUNT(*) FROM [{tbl}] WHERE LEN([{uid_col}]) > 36")
        if over36 and over36 > 0:
            samples = await fetch_all(conn, f"""
                SELECT DISTINCT TOP 5 LEFT([{uid_col}], 60) FROM [{tbl}] WHERE LEN([{uid_col}]) > 36
            """)
            d1_results.append({"table": tbl, "col": uid_col, "count": over36,
                               "samples": [str(r[0]) for r in samples]})
    findings["user_id_wide"] = d1_results

    # D2: symbol columns wider than 20 chars
    print("  [D2] symbol width anomalies...")
    symbol_tables = [
        ("symbol_reference", "symbol"), ("symbol_quotes", "symbol"),
        ("symbol_context", "symbol"), ("option_chain_snapshots", "symbol"),
        ("watchlist_symbols", "symbol"), ("user_watchlist", "symbol"),
        ("trade_candidates", "symbol"), ("trade_recommendations", "symbol"),
        ("agent_run_log", "symbol"), ("analysis_runs", "symbol"),
        ("analyzed_trades", "symbol"), ("positions", "symbol"),
        ("trade_log", "symbol"), ("user_favorites", "symbol"),
        ("validation_assessments", "ticker"),
    ]
    d2_results = []
    for tbl, col in symbol_tables:
        if not await table_exists(conn, tbl):
            continue
        col_exists = await fetch_scalar(conn, f"""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = '{tbl}' AND COLUMN_NAME = '{col}'
        """)
        if not col_exists:
            continue
        over20 = await fetch_scalar(conn, f"SELECT COUNT(*) FROM [{tbl}] WHERE LEN([{col}]) > 20")
        if over20 and over20 > 0:
            samples = await fetch_all(conn, f"""
                SELECT DISTINCT TOP 5 [{col}] FROM [{tbl}] WHERE LEN([{col}]) > 20
            """)
            d2_results.append({"table": tbl, "col": col, "count": over20,
                               "samples": [str(r[0]) for r in samples]})
    findings["symbol_wide"] = d2_results

    # D3: trade_candidates varchar(MAX) fields
    print("  [D3] trade_candidates short-categorical fields...")
    d3_results = []
    if await table_exists(conn, "trade_candidates"):
        for col in ["structure", "scan_source", "scan_strategy_key"]:
            col_exists = await fetch_scalar(conn, f"""
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = 'trade_candidates' AND COLUMN_NAME = '{col}'
            """)
            if not col_exists:
                d3_results.append({"col": col, "error": "Column does not exist"})
                continue
            distinct_count = await fetch_scalar(conn, f"SELECT COUNT(DISTINCT [{col}]) FROM trade_candidates WHERE [{col}] IS NOT NULL")
            max_len = await fetch_scalar(conn, f"SELECT MAX(LEN([{col}])) FROM trade_candidates WHERE [{col}] IS NOT NULL")
            samples = await fetch_all(conn, f"SELECT DISTINCT TOP 20 [{col}] FROM trade_candidates WHERE [{col}] IS NOT NULL")
            d3_results.append({
                "col": col, "error": None,
                "distinct_count": distinct_count, "max_len": max_len,
                "samples": [str(r[0]) for r in samples],
            })
    findings["trade_candidates_varchar_max"] = d3_results

    # D4: expiration columns — format analysis
    print("  [D4] expiration column format analysis...")
    exp_tables = [
        ("analyzed_trades", "expiration"),
        ("trade_log", "expiration"),
        ("trade_recommendations", "expiration"),
    ]
    d4_results = []
    for tbl, col in exp_tables:
        if not await table_exists(conn, tbl):
            continue
        col_exists = await fetch_scalar(conn, f"""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = '{tbl}' AND COLUMN_NAME = '{col}'
        """)
        if not col_exists:
            d4_results.append({"table": tbl, "col": col, "error": "Column does not exist"})
            continue
        total = await fetch_scalar(conn, f"SELECT COUNT(*) FROM [{tbl}] WHERE [{col}] IS NOT NULL")
        samples = await fetch_all(conn, f"SELECT DISTINCT TOP 10 [{col}] FROM [{tbl}] WHERE [{col}] IS NOT NULL")
        sample_vals = [str(r[0]) for r in samples]

        # Try to detect format
        formats_seen = set()
        unparseable = 0
        for v in sample_vals:
            if re.match(r'^\d{4}-\d{2}-\d{2}$', v):
                formats_seen.add("YYYY-MM-DD")
            elif re.match(r'^\d{2}-\d{2}-\d{4}$', v):
                formats_seen.add("MM-DD-YYYY")
            elif re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}', v):
                formats_seen.add("YYYY-MM-DD HH:MM")
            else:
                formats_seen.add("OTHER")
                unparseable += 1

        # Count rows that can't be parsed as date via TRY_CONVERT
        bad_dates = await fetch_scalar(conn, f"""
            SELECT COUNT(*) FROM [{tbl}]
            WHERE [{col}] IS NOT NULL AND TRY_CONVERT(DATE, [{col}]) IS NULL
        """)

        d4_results.append({
            "table": tbl, "col": col, "error": None,
            "total": total, "samples": sample_vals,
            "formats_seen": list(formats_seen),
            "unparseable_date_rows": bad_dates,
        })
    findings["expiration_format"] = d4_results

    # D5: insights.entity_id cross-domain check
    print("  [D5] insights.entity_id cross-domain check...")
    d5 = {}
    if await table_exists(conn, "insights") and await table_exists(conn, "positions"):
        # entity_id values for domain='options' that look like UUIDs
        rows = await fetch_all(conn, """
            SELECT DISTINCT entity_id FROM insights WHERE domain = 'options' AND entity_id IS NOT NULL
        """)
        all_eids = [str(r[0]) for r in rows]
        uuid_eids = [v for v in all_eids if UUID_REGEX.match(v)]
        d5["options_entity_ids_total"] = len(all_eids)
        d5["options_entity_ids_uuid"] = len(uuid_eids)

        if uuid_eids:
            uuid_list = ",".join(f"'{v}'" for v in uuid_eids[:2000])
            matched = await fetch_scalar(conn, f"""
                SELECT COUNT(*) FROM positions WHERE position_id IN ({uuid_list})
            """)
            d5["uuid_eids_in_positions"] = matched
        else:
            d5["uuid_eids_in_positions"] = 0
    else:
        d5["error"] = "insights or positions table missing"
    findings["insights_entity_id"] = d5

    return findings


# ─── Report Generation ───────────────────────────────────────────────────────

def severity(orphan_count, notes):
    if orphan_count is None:
        return "SKIP"
    if orphan_count == 0:
        return "OK"
    if "Already FK" in (notes or ""):
        return "WARN"
    return "BLOCKER"


def generate_report(fk_results, tk_per_table, tk_overlap, json_results, width_findings, db_target, run_time):
    lines = []
    w = lines.append

    w("# Phase 0 Database Integrity Audit — Report\n")
    w(f"**Run at:** {run_time}")
    w(f"**Database target:** {db_target}")
    w("**Generated by:** Phase 0 audit prompt (read-only)\n")

    # ── Executive Summary ──
    fk_audited = len([r for r in fk_results if r.get("error") is None and r.get("parent") != "—"])
    fk_with_orphans = len([r for r in fk_results if r.get("error") is None and r.get("parent") != "—" and (r.get("orphan_count") or 0) > 0])
    json_audited = len([r for r in json_results if r.get("error") is None])
    json_with_invalid = len([r for r in json_results if r.get("error") is None and not r.get("special_case") and (r.get("invalid") or 0) > 0])
    total_invalid_json = sum(r.get("invalid") or 0 for r in json_results if r.get("error") is None and not r.get("special_case"))

    # trade_key summary
    tk_summary = "See Section B for details"
    all_uuid = all(t.get("non_uuid_count", 0) == 0 for t in tk_per_table if t.get("error") is None and t.get("total", 0) > 0)
    if all_uuid:
        tk_summary = "All trade_key values are UUID format — DB-enforced FK is feasible"
    else:
        tk_summary = "trade_key namespace is heterogeneous — see Section B for breakdown"

    # width summary
    width_issues = []
    if width_findings.get("user_id_wide"):
        width_issues.append(f"{len(width_findings['user_id_wide'])} table(s) with user_id > 36 chars")
    if width_findings.get("symbol_wide"):
        width_issues.append(f"{len(width_findings['symbol_wide'])} table(s) with symbol > 20 chars")
    width_summary = "; ".join(width_issues) if width_issues else "No width anomalies found"

    w("## Executive Summary\n")
    w(f"- Total FK candidates audited: {fk_audited}")
    w(f"- FK candidates with orphan rows: {fk_with_orphans}")
    w(f"- JSON columns audited: {json_audited}")
    w(f"- JSON columns with invalid JSON values: {json_with_invalid}")
    w(f"- Total invalid-JSON rows: {total_invalid_json}")
    w(f"- `trade_key` namespace finding: {tk_summary}")
    w(f"- Width/format anomalies: {width_summary}\n")

    # ── Section A ──
    w("---\n")
    w("## Section A — Foreign Key Orphans\n")
    w("| Child Table | Child Column | Parent Table | Parent Column | Orphan Rows | Distinct Orphans | Severity | Notes |")
    w("|---|---|---|---|---|---|---|---|")

    for r in fk_results:
        if r.get("parent") == "—":
            continue  # skip the width-check pseudo-entry
        if r.get("error"):
            w(f"| {r['child']} | {r['child_col']} | {r['parent']} | {r['parent_col']} | — | — | SKIP | {r['error']} |")
            continue
        sev = severity(r["orphan_count"], r["notes"])
        w(f"| {r['child']} | {r['child_col']} | {r['parent']} | {r['parent_col']} | {r['orphan_count']:,} | {r['distinct_count']:,} | {sev} | {r['notes']} |")

    # Sample values for orphans
    orphan_entries = [r for r in fk_results if r.get("error") is None and (r.get("orphan_count") or 0) > 0 and r.get("parent") != "—"]
    if orphan_entries:
        w("\n### Orphan Sample Values\n")
        for r in orphan_entries:
            w(f"**{r['child']}.{r['child_col']}** ({r['orphan_count']:,} orphan rows, {r['distinct_count']:,} distinct values):")
            for s in r["samples"]:
                w(f"  - `{s}`")
            w("")

    # Width anomaly entry
    width_entry = [r for r in fk_results if r.get("parent") == "—"]
    if width_entry:
        w("\n### user_sessions.user_id Width Check\n")
        for r in width_entry:
            w(f"- Rows with LEN(user_id) > 36: **{r['orphan_count']:,}**\n")

    # ── Section B ──
    w("---\n")
    w("## Section B — `trade_key` Namespace\n")
    w("### Per-Table Stats\n")
    w("| Table | Column | Total Non-Null | Distinct | Min Len | Max Len | Avg Len | UUID Count | Non-UUID Count |")
    w("|---|---|---|---|---|---|---|---|---|")

    for t in tk_per_table:
        if t.get("error"):
            w(f"| {t['table']} | {t['col']} | — | — | — | — | — | — | {t['error']} |")
            continue
        avg_str = f"{t['avg_len']:.1f}" if t['avg_len'] is not None else "—"
        w(f"| {t['table']} | {t['col']} | {t.get('total', 0):,} | {t.get('distinct', 0):,} | {t.get('min_len', '—')} | {t.get('max_len', '—')} | {avg_str} | {t.get('uuid_count', 0):,} | {t.get('non_uuid_count', 0):,} |")

    # Non-UUID samples
    for t in tk_per_table:
        if t.get("non_uuid_samples"):
            w(f"\n**Non-UUID samples in {t['table']}.{t['col']}:**")
            for s in t["non_uuid_samples"]:
                w(f"  - `{s}`")

    w("\n### Cross-Table Overlap\n")
    w(f"- `trade_recommendations.trade_key` values NOT in `trade_candidates.trade_key`: **{tk_overlap.get('recs_not_in_candidates', '—')}**")
    w(f"- `agent_run_log.trade_key` values NOT in `trade_candidates.trade_key`: **{tk_overlap.get('agent_not_in_candidates', '—')}**")
    w(f"- `user_favorites.trade_id` UUID values present in `trade_candidates.trade_key`: **{tk_overlap.get('fav_uuid_in_candidates', '—')}** out of **{tk_overlap.get('fav_total_uuids', '—')}** UUID trade_ids")

    # Recommendation
    all_uuid_flag = all(t.get("non_uuid_count", 0) == 0 for t in tk_per_table if t.get("error") is None and t.get("total", 0) > 0)
    if all_uuid_flag:
        w("\n**Recommendation:** trade_key can be standardized at varchar(36) UUID with DB-enforced FK.\n")
    else:
        w("\n**Recommendation:** trade_key namespace is heterogeneous — FK must remain application-enforced, retain wider column type.\n")

    # ── Section C ──
    w("---\n")
    w("## Section C — JSON Validity\n")
    w("| Table | Column | Non-Null Rows | Invalid-JSON Rows | % Invalid | Recommendation |")
    w("|---|---|---|---|---|---|")

    for r in json_results:
        if r.get("error"):
            w(f"| {r['table']} | {r['col']} | — | — | — | SKIP ({r['error']}) |")
            continue
        pct = (r["invalid"] / r["non_null"] * 100) if r["non_null"] and r["non_null"] > 0 else 0
        if r.get("special_case"):
            rec = "SPECIAL — see note below"
        elif r["invalid"] == 0:
            rec = "APPLY ISJSON CHECK"
        elif pct < 5:
            rec = "CLEAN FIRST"
        else:
            rec = "CLEAN FIRST (high %)"
        w(f"| {r['table']} | {r['col']} | {r['non_null']:,} | {r['invalid']:,} | {pct:.2f}% | {rec} |")

    # Invalid JSON samples
    invalid_entries = [r for r in json_results if r.get("error") is None and (r.get("invalid") or 0) > 0]
    if invalid_entries:
        w("\n### Invalid JSON Samples\n")
        for r in invalid_entries:
            label = " (SPECIAL CASE)" if r.get("special_case") else ""
            w(f"**{r['table']}.{r['col']}**{label} — {r['invalid']:,} invalid rows:")
            for s in r["samples"]:
                w(f"  - `{s}`")
            w("")

    if any(r.get("special_case") for r in json_results):
        w("**Note on `agent_run_log.model_response_raw`:** This column may contain non-JSON text (raw model output). "
          "Invalid-JSON counts are reported for informational purposes; the ISJSON constraint may not apply here.\n")

    # ── Section D ──
    w("---\n")
    w("## Section D — Width and Format Anomalies\n")

    # D1
    w("### D1 — `user_id` columns wider than 36 chars\n")
    if width_findings.get("user_id_wide"):
        w("| Table | Column | Rows with LEN > 36 | Sample Values |")
        w("|---|---|---|---|")
        for d in width_findings["user_id_wide"]:
            samples_str = ", ".join(f"`{s}`" for s in d["samples"])
            w(f"| {d['table']} | {d['col']} | {d['count']:,} | {samples_str} |")
    else:
        w("No user_id values exceed 36 characters.\n")

    # D2
    w("\n### D2 — `symbol` columns wider than 20 chars\n")
    if width_findings.get("symbol_wide"):
        w("| Table | Column | Rows with LEN > 20 | Sample Values |")
        w("|---|---|---|---|")
        for d in width_findings["symbol_wide"]:
            samples_str = ", ".join(f"`{s}`" for s in d["samples"])
            w(f"| {d['table']} | {d['col']} | {d['count']:,} | {samples_str} |")
    else:
        w("No symbol values exceed 20 characters.\n")

    # D3
    w("\n### D3 — `trade_candidates` short-categorical fields (currently varchar MAX)\n")
    if width_findings.get("trade_candidates_varchar_max"):
        w("| Column | Distinct Values | Max Observed Length | Fits varchar(50)? | Sample Values |")
        w("|---|---|---|---|---|")
        for d in width_findings["trade_candidates_varchar_max"]:
            if d.get("error"):
                w(f"| {d['col']} | — | — | — | {d['error']} |")
                continue
            fits = "YES" if (d["max_len"] or 0) <= 50 else "NO"
            samples_str = ", ".join(f"`{s}`" for s in d["samples"][:5])
            w(f"| {d['col']} | {d['distinct_count']} | {d['max_len']} | {fits} | {samples_str} |")
    else:
        w("trade_candidates table not found or no varchar(MAX) columns.\n")

    # D4
    w("\n### D4 — Expiration column format analysis\n")
    if width_findings.get("expiration_format"):
        for d in width_findings["expiration_format"]:
            if d.get("error"):
                w(f"**{d['table']}.{d['col']}:** {d['error']}\n")
                continue
            w(f"**{d['table']}.{d['col']}** — {d['total']:,} non-null rows")
            w(f"  - Formats seen: {', '.join(d['formats_seen'])}")
            w(f"  - Rows not parseable as DATE: {d['unparseable_date_rows']:,}")
            w(f"  - Sample values: {', '.join(f'`{s}`' for s in d['samples'])}")
            w("")
    else:
        w("No expiration columns found.\n")

    # D5
    w("\n### D5 — `insights.entity_id` cross-domain check\n")
    d5 = width_findings.get("insights_entity_id", {})
    if d5.get("error"):
        w(f"{d5['error']}\n")
    else:
        w(f"- Options-domain entity_ids (total distinct): **{d5.get('options_entity_ids_total', 0)}**")
        w(f"- Of those, UUID-format count: **{d5.get('options_entity_ids_uuid', 0)}**")
        w(f"- UUID entity_ids that match a `positions.position_id`: **{d5.get('uuid_eids_in_positions', 0)}**\n")

    # ── Cleanup Tasks ──
    w("---\n")
    w("## Cleanup Tasks for Phase 1\n")
    task_num = 0

    # Blockers from Section A
    for r in fk_results:
        if r.get("error") or r.get("parent") == "—":
            continue
        sev = severity(r["orphan_count"], r["notes"])
        if sev == "BLOCKER":
            task_num += 1
            w(f"{task_num}. **{r['child']}.{r['child_col']}** → {r['parent']}.{r['parent_col']}: "
              f"Delete/remap {r['orphan_count']:,} orphan rows ({r['distinct_count']:,} distinct values) "
              f"before adding FK constraint.")

    # Clean-first from Section C
    for r in json_results:
        if r.get("error") or r.get("special_case"):
            continue
        if (r.get("invalid") or 0) > 0:
            task_num += 1
            w(f"{task_num}. **{r['table']}.{r['col']}**: Fix {r['invalid']:,} invalid-JSON rows before adding ISJSON check constraint.")

    if task_num == 0:
        w("No blocking cleanup tasks identified.\n")

    # ── Open Items ──
    w("\n---\n")
    w("## Open Items for User Review\n")
    open_items = []

    # Orphan user_ids that might be test data
    for r in fk_results:
        if r.get("error") or r.get("parent") == "—":
            continue
        if (r.get("orphan_count") or 0) > 0 and r["child_col"] == "user_id":
            open_items.append(
                f"- **{r['child']}.user_id** has {r['orphan_count']:,} orphan rows with values: "
                f"{', '.join(f'`{s}`' for s in r['samples'])}. "
                f"Are these test data to purge, or legitimate records to remap?"
            )

    # WARN-level FKs (ORM declares FK but orphans exist)
    for r in fk_results:
        if r.get("error") or r.get("parent") == "—":
            continue
        sev = severity(r["orphan_count"], r["notes"])
        if sev == "WARN":
            open_items.append(
                f"- **{r['child']}.{r['child_col']}** is declared as FK in ORM but has {r['orphan_count']:,} orphan rows. "
                f"This means the FK may not be enforced at the DB level — investigate."
            )

    # model_response_raw
    for r in json_results:
        if r.get("special_case") and (r.get("invalid") or 0) > 0:
            open_items.append(
                f"- **agent_run_log.model_response_raw** has {r['invalid']:,} non-JSON rows. "
                f"Decide whether ISJSON constraint applies to this column."
            )

    if open_items:
        for item in open_items:
            w(item)
    else:
        w("No open items requiring user review.\n")

    return "\n".join(lines)


# ─── Main ────────────────────────────────────────────────────────────────────

async def main():
    run_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Resolve DB target display string
    from app.core.config import settings
    import urllib.parse as up
    parsed = up.urlparse(settings.database_url)
    db_target = f"{parsed.hostname}/{parsed.path.lstrip('/')}"

    print(f"Phase 0 Database Integrity Audit")
    print(f"Target: {db_target}")
    print(f"Run at: {run_time}")
    print("=" * 60)

    async with engine.connect() as conn:
        print("\n[Section A] Foreign Key Orphan Counts")
        fk_results = await audit_fk_orphans(conn)

        print("\n[Section B] trade_key Namespace Audit")
        tk_per_table, tk_overlap = await audit_trade_key_namespace(conn)

        print("\n[Section C] JSON Column Validity")
        json_results = await audit_json_columns(conn)

        print("\n[Section D] Width and Format Anomalies")
        width_findings = await audit_width_anomalies(conn)

    print("\n" + "=" * 60)
    print("Generating report...")

    report = generate_report(fk_results, tk_per_table, tk_overlap, json_results, width_findings, db_target, run_time)

    report_path = PROJECT_ROOT / "phase0-audit-report.md"
    report_path.write_text(report, encoding="utf-8")

    # Print executive summary
    print("\n" + "=" * 60)
    print("EXECUTIVE SUMMARY")
    print("=" * 60)
    for line in report.split("\n"):
        if line.startswith("- "):
            print(line)
        if line.startswith("---") and "Executive" not in line:
            break

    print(f"\nReport written to: {report_path}")
    print(f"Script location:   {Path(__file__).resolve()}")
    print("\nNo schema changes were made. No rows were modified.")


if __name__ == "__main__":
    asyncio.run(main())
