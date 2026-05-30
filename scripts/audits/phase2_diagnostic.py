"""
Phase 2 Diagnostic — Pre-migration read-only audit.

Checks all preconditions for Phase 2 (FK constraints, ISJSON checks, indexes).
Generates phase2-diagnostic-report.md at project root.

Usage:
    cd <project-root>
    source venv/Scripts/activate
    python scripts/audits/phase2_diagnostic.py
"""

import struct, sys, urllib.parse
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pyodbc
from azure.identity import DefaultAzureCredential
from app.core.config import settings


def get_connection():
    parsed = urllib.parse.urlparse(settings.database_url)
    server = parsed.hostname
    port = parsed.port or 1433
    database = parsed.path.lstrip("/")
    odbc_connect = (
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server={server},{port};Database={database};"
        f"Encrypt=yes;TrustServerCertificate=no;"
    )
    credential = DefaultAzureCredential()
    token = credential.get_token("https://database.windows.net/.default")
    token_bytes = token.token.encode("UTF-16-LE")
    token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
    conn = pyodbc.connect(odbc_connect, attrs_before={1256: token_struct})
    conn.autocommit = True
    return conn


# ── Target FKs from §4 ──
# (child_table, child_col, parent_table, parent_col, cascade_rule)
# cascade_rule: CASCADE, RESTRICT (NO ACTION in SQL Server), SET_NULL
TARGET_FKS = [
    # §4.1 Identity & Session
    ("user_sessions", "user_id", "users", "id", "CASCADE"),
    ("user_configs", "user_id", "users", "id", "CASCADE"),
    ("dashboard_layouts", "user_id", "users", "id", "CASCADE"),
    # audit_log.user_id → users.id — listed as "already exists" in §4.7
    # §4.2 Symbol Master
    ("symbol_quotes", "symbol", "symbol_reference", "symbol", "RESTRICT"),
    ("symbol_context", "symbol", "symbol_reference", "symbol", "RESTRICT"),
    ("option_chain_snapshots", "symbol", "symbol_reference", "symbol", "RESTRICT"),
    ("watchlist_symbols", "symbol", "symbol_reference", "symbol", "RESTRICT"),
    ("trade_candidates", "symbol", "symbol_reference", "symbol", "RESTRICT"),
    ("analysis_runs", "symbol", "symbol_reference", "symbol", "RESTRICT"),
    ("analyzed_trades", "symbol", "symbol_reference", "symbol", "RESTRICT"),
    ("positions", "symbol", "symbol_reference", "symbol", "RESTRICT"),
    ("trade_log", "symbol", "symbol_reference", "symbol", "RESTRICT"),
    ("trade_recommendations", "symbol", "symbol_reference", "symbol", "RESTRICT"),
    ("user_favorites", "symbol", "symbol_reference", "symbol", "RESTRICT"),
    ("agent_run_log", "symbol", "symbol_reference", "symbol", "SET_NULL"),
    ("validation_assessments", "symbol", "symbol_reference", "symbol", "RESTRICT"),
    # §4.3 Watchlist
    ("watchlists", "user_id", "users", "id", "CASCADE"),
    ("watchlist_symbols", "watchlist_id", "watchlists", "id", "CASCADE"),
    # §4.4 Positions
    ("positions", "user_id", "users", "id", "RESTRICT"),
    # §4.5 Trade evaluation
    ("trade_candidates", "user_id", "users", "id", "RESTRICT"),
    ("trade_recommendations", "user_id", "users", "id", "RESTRICT"),
    # §4.6 Insights
    ("insights", "source_position_id", "positions", "position_id", "SET_NULL"),
    ("insights", "user_id", "users", "id", "RESTRICT"),
    # §4.7 Other
    ("user_favorites", "user_id", "users", "id", "CASCADE"),
]

# FKs marked "already exists" in the proposal
ALREADY_EXISTS_FKS = [
    ("position_assessments", "position_id", "positions", "position_id"),
    ("agent_run_log", "user_id", "users", "id"),
    ("analysis_runs", "user_id", "users", "id"),
    ("analysis_runs", "chain_snapshot_id", "option_chain_snapshots", "id"),
    ("analyzed_trades", "run_id", "analysis_runs", "id"),
    ("analyzed_trades", "user_id", "users", "id"),
    ("trade_log", "user_id", "users", "id"),
    ("symbol_quotes", "user_id", "users", "id"),
    ("option_chain_snapshots", "user_id", "users", "id"),
    ("audit_log", "user_id", "users", "id"),
]

# ── ISJSON columns from §5 ──
ISJSON_COLUMNS = [
    ("positions", "trade_structure"),
    ("positions", "entry_greeks"),
    ("positions", "entry_sma_alignment"),
    ("positions", "claude_probability_matrix"),
    ("positions", "claude_exit_levels"),
    ("positions", "claude_verdict"),
    ("analyzed_trades", "score_breakdown"),
    ("analyzed_trades", "scoring_weights"),
    ("analysis_runs", "scoring_weights"),
    ("analysis_runs", "filter_params"),
    ("option_chain_snapshots", "chain_data"),
    ("trade_candidates", "legs"),
    ("trade_candidates", "net_metrics"),
    ("trade_candidates", "pipeline_components"),
    ("trade_candidates", "claude_evaluation"),
    ("trade_log", "legs"),
    ("trade_recommendations", "market_snapshot"),
    ("trade_recommendations", "trade_snapshot"),
    ("agent_run_log", "market_snapshot"),
    ("agent_run_log", "trade_snapshot"),
    ("position_assessments", "exit_levels"),
    ("position_assessments", "market_snapshot"),
    ("insights", "recommended_actions"),
    ("insights", "source_signals"),
    ("user_configs", "extra_settings"),
    ("user_favorites", "trade_data"),
    ("symbol_context", "signal_value"),
    ("dashboard_layouts", "layout_json"),
    ("dashboard_layouts", "widgets_json"),
]

# ── §7 Target Indexes ──
# (table, columns_tuple, unique, has_desc_columns)
# columns with DESC are marked with a '-' prefix
TARGET_INDEXES = [
    ("symbol_quotes", ("user_id", "symbol", "-captured_at"), False),
    ("option_chain_snapshots", ("user_id", "symbol", "-captured_at"), False),
    ("option_chain_snapshots", ("symbol", "-captured_at"), False),
    ("symbol_context", ("symbol", "signal_type", "expires_at"), False),
    ("positions", ("user_id", "status", "last_monitored_at"), False),
    ("positions", ("user_id", "status"), False),
    ("trade_candidates", ("user_id", "-scanned_at"), False),
    ("trade_candidates", ("symbol", "-scanned_at"), False),
    ("agent_run_log", ("user_id", "-created_at"), False),
    ("agent_run_log", ("trace_id",), False),
    ("agent_run_log", ("run_id",), False),
    ("analyzed_trades", ("run_id", "-composite_score"), False),
    ("insights", ("user_id", "domain", "-surfaced_at"), False),
    ("insights", ("source_position_id",), False),
    ("user_sessions", ("session_id",), True),
    ("user_sessions", ("user_id", "expires_at"), False),
    ("watchlist_symbols", ("watchlist_id", "symbol"), True),
    ("watchlists", ("user_id", "name"), True),
]

# Phase 1b created indexes (from phase1b-migration-log.md)
PHASE1B_INDEXES = [
    ("symbol_reference", "ux_symbol_reference_api_symbol"),
    ("watchlists", "ix_watchlists_user"),
    ("trade_recommendations", "ix_trade_recommendations_user_symbol"),
    ("symbol_quotes", "ix_symbol_quotes_symbol_time"),
    ("symbol_quotes", "ix_symbol_quotes_user_symbol_time"),
    ("analysis_runs", "ix_analysis_runs_symbol_time"),
    ("analysis_runs", "ix_analysis_runs_user_symbol"),
    ("analyzed_trades", "ix_analyzed_trades_symbol_expiry"),
    ("analyzed_trades", "ix_analyzed_trades_user_symbol"),
    ("validation_assessments", "ix_validation_assessments_symbol"),
]


def cascade_rule_from_sql(delete_action):
    """Convert SQL Server sys.foreign_keys delete_referential_action to label."""
    return {0: "NO_ACTION", 1: "CASCADE", 2: "SET_NULL", 3: "SET_DEFAULT"}.get(delete_action, f"UNKNOWN({delete_action})")


def normalize_cascade(rule):
    """Normalize RESTRICT -> NO_ACTION for comparison."""
    if rule == "RESTRICT":
        return "NO_ACTION"
    return rule


def main():
    run_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    parsed = urllib.parse.urlparse(settings.database_url)
    db_target = f"{parsed.hostname}/{parsed.path.lstrip('/')}"

    print(f"Phase 2 Diagnostic")
    print(f"Run at: {run_time}")
    print(f"Database: {db_target}")
    print("=" * 60)

    conn = get_connection()
    cursor = conn.cursor()

    report = []
    W = report.append

    W("# Phase 2 Diagnostic Report\n")
    W(f"**Run at:** {run_time}")
    W(f"**Database:** {db_target}")
    W(f"**Alembic head:** 9749dae4bc82 (Phase 1b)\n")

    # ================================================================
    # §1. FK Inventory
    # ================================================================
    print("\n[1] FK Inventory...")
    W("## 1. FK Inventory\n")

    # Get all existing FKs
    cursor.execute("""
        SELECT
            OBJECT_NAME(fk.parent_object_id) AS child_table,
            COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS child_col,
            OBJECT_NAME(fk.referenced_object_id) AS parent_table,
            COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id) AS parent_col,
            fk.delete_referential_action,
            fk.name AS fk_name
        FROM sys.foreign_keys fk
        JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
        ORDER BY child_table, child_col
    """)
    existing_fks = {}
    all_existing_fks = []
    for row in cursor.fetchall():
        key = (row[0], row[1], row[2], row[3])
        cascade = cascade_rule_from_sql(row[4])
        existing_fks[key] = (cascade, row[5])
        all_existing_fks.append((row[0], row[1], row[2], row[3], cascade, row[5]))

    W("### Target FKs (from §4)\n")
    W("| Child Table | Child Col | Parent Table | Parent Col | Cascade | Status |")
    W("|---|---|---|---|---|---|")

    fk_actions = []  # (action, child_table, child_col, parent_table, parent_col, cascade, fk_name)
    escalations = []

    for child_tbl, child_col, parent_tbl, parent_col, cascade in TARGET_FKS:
        key = (child_tbl, child_col, parent_tbl, parent_col)
        if key in existing_fks:
            actual_cascade, fk_name = existing_fks[key]
            expected = normalize_cascade(cascade)
            if actual_cascade == expected:
                status = f"PRESENT-AND-CORRECT ({fk_name})"
                print(f"  {child_tbl}.{child_col} -> {parent_tbl}.{parent_col}: {status}")
            else:
                status = f"PRESENT-WRONG-CASCADE (actual={actual_cascade}, expected={expected}, name={fk_name})"
                escalations.append(f"FK {child_tbl}.{child_col} -> {parent_tbl}.{parent_col}: actual cascade={actual_cascade}, expected={expected}")
                print(f"  WARNING: {child_tbl}.{child_col}: {status}")
        else:
            status = "MISSING"
            fk_name = f"fk_{child_tbl}_{child_col}_{parent_tbl}"
            fk_actions.append(("ADD FK", child_tbl, child_col, parent_tbl, parent_col, cascade, fk_name))
            print(f"  {child_tbl}.{child_col} -> {parent_tbl}.{parent_col}: MISSING")
        W(f"| {child_tbl} | {child_col} | {parent_tbl} | {parent_col} | {cascade} | {status} |")

    # Check "already exists" FKs
    W("\n### Pre-existing FKs (marked 'already exists' in §4)\n")
    W("| Child Table | Child Col | Parent Table | Parent Col | Cascade | Status |")
    W("|---|---|---|---|---|---|")
    for child_tbl, child_col, parent_tbl, parent_col in ALREADY_EXISTS_FKS:
        key = (child_tbl, child_col, parent_tbl, parent_col)
        if key in existing_fks:
            actual_cascade, fk_name = existing_fks[key]
            status = f"PRESENT ({actual_cascade}, {fk_name})"
            # Special check for audit_log.user_id
            if child_tbl == "audit_log" and child_col == "user_id":
                if actual_cascade != "SET_NULL":
                    escalations.append(
                        f"audit_log.user_id FK cascade={actual_cascade}, §4.1 specifies SET NULL. "
                        f"§4.7 marks it 'already exists' without specifying cascade. ESCALATE for Don's decision."
                    )
                    status += f" -- ESCALATE: §4.1 says SET NULL, actual is {actual_cascade}"
        else:
            status = "NOT FOUND (unexpected)"
        W(f"| {child_tbl} | {child_col} | {parent_tbl} | {parent_col} | -- | {status} |")
        print(f"  [pre-existing] {child_tbl}.{child_col}: {status}")

    # Unexpected FKs
    W("\n### Unexpected FKs (not in §4 target list)\n")
    target_keys = set((t[0], t[1], t[2], t[3]) for t in TARGET_FKS)
    already_keys = set((t[0], t[1], t[2], t[3]) for t in ALREADY_EXISTS_FKS)
    known_keys = target_keys | already_keys
    unexpected = [(t, c, pt, pc, cas, name) for t, c, pt, pc, cas, name in all_existing_fks if (t, c, pt, pc) not in known_keys]
    if unexpected:
        W("| Child Table | Child Col | Parent Table | Parent Col | Cascade | FK Name |")
        W("|---|---|---|---|---|---|")
        for t, c, pt, pc, cas, name in unexpected:
            W(f"| {t} | {c} | {pt} | {pc} | {cas} | {name} |")
            print(f"  [unexpected] {t}.{c} -> {pt}.{pc} ({cas}, {name})")
    else:
        W("None found.")

    # ================================================================
    # §2. Check Constraint Inventory
    # ================================================================
    print("\n[2] Check Constraint Inventory (ISJSON)...")
    W("\n## 2. Check Constraint Inventory (ISJSON)\n")

    # Get all existing check constraints
    cursor.execute("""
        SELECT OBJECT_NAME(cc.parent_object_id) AS table_name, cc.name, cc.definition
        FROM sys.check_constraints cc
        ORDER BY table_name, cc.name
    """)
    existing_checks = {}
    all_checks = []
    for row in cursor.fetchall():
        all_checks.append((row[0], row[1], row[2]))
        # Index by table+partial column match
        if "isjson" in row[2].lower():
            existing_checks[(row[0], row[1])] = row[2]

    W("| Table | Column | Status |")
    W("|---|---|---|")

    check_actions = []

    for tbl, col in ISJSON_COLUMNS:
        # Check if a constraint referencing this column with ISJSON exists
        found = False
        for (chk_tbl, chk_name), chk_def in existing_checks.items():
            if chk_tbl == tbl and col.lower() in chk_def.lower():
                found = True
                status = f"PRESENT ({chk_name})"
                break
        if not found:
            status = "MISSING"
            ck_name = f"ck_{tbl}_{col}_isjson"
            check_actions.append((tbl, col, ck_name))
        W(f"| {tbl} | {col} | {status} |")
        print(f"  {tbl}.{col}: {status}")

    # Check for options_chain_snapshots (plural)
    cursor.execute("SELECT OBJECT_ID('options_chain_snapshots', 'U')")
    plural_table_exists = cursor.fetchone()[0] is not None
    W(f"\n**Note:** `options_chain_snapshots` (plural) table {'EXISTS' if plural_table_exists else 'does NOT exist'}.")
    if plural_table_exists:
        W("Per prompt: do NOT add ISJSON to `options_chain_snapshots.chain_json`. Skipped.")
    print(f"  options_chain_snapshots (plural): {'EXISTS - skipped per prompt' if plural_table_exists else 'not present'}")

    # Unexpected check constraints
    W("\n### Unexpected Check Constraints\n")
    isjson_tables = set(t for t, _ in ISJSON_COLUMNS)
    unexpected_checks = [(t, n, d) for t, n, d in all_checks if t in isjson_tables and "isjson" not in d.lower()]
    if unexpected_checks:
        W("| Table | Name | Definition |")
        W("|---|---|---|")
        for t, n, d in unexpected_checks:
            W(f"| {t} | {n} | `{d}` |")
    else:
        W("None found.")

    # ================================================================
    # §3. Index Inventory
    # ================================================================
    print("\n[3] Index Inventory...")
    W("\n## 3. Index Inventory\n")

    # Fetch all indexes with column details
    cursor.execute("""
        SELECT
            OBJECT_NAME(i.object_id) AS table_name,
            i.name AS index_name,
            i.is_unique,
            i.has_filter,
            i.filter_definition,
            ic.key_ordinal,
            c.name AS col_name,
            ic.is_descending_key
        FROM sys.indexes i
        JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
        JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        WHERE i.type IN (1, 2)  -- clustered and nonclustered
          AND ic.is_included_column = 0
          AND i.name IS NOT NULL
        ORDER BY table_name, i.name, ic.key_ordinal
    """)
    # Build index map: (table, index_name) -> {is_unique, has_filter, filter_def, columns: [(col, desc)]}
    index_map = {}
    for row in cursor.fetchall():
        key = (row[0], row[1])
        if key not in index_map:
            index_map[key] = {"is_unique": row[2], "has_filter": row[3], "filter_def": row[4], "columns": []}
        index_map[key]["columns"].append((row[6], row[7]))

    W("### §7 Target Indexes\n")
    W("| Table | Columns | Unique | Status |")
    W("|---|---|---|---|")

    index_actions = []

    for tbl, cols_spec, is_unique in TARGET_INDEXES:
        # Parse column spec: '-col' means DESC
        target_cols = []
        for c in cols_spec:
            if c.startswith("-"):
                target_cols.append((c[1:], True))  # (name, is_desc)
            else:
                target_cols.append((c, False))

        col_display = ", ".join(f"{c} DESC" if d else c for c, d in target_cols)

        # Search for exact match
        found_exact = None
        found_partial = None
        for (idx_tbl, idx_name), info in index_map.items():
            if idx_tbl != tbl:
                continue
            idx_cols = info["columns"]
            # Check exact match: same columns, same order, same direction, same unique, no filter
            if (len(idx_cols) == len(target_cols)
                    and all(idx_cols[i][0] == target_cols[i][0] and bool(idx_cols[i][1]) == target_cols[i][1]
                            for i in range(len(target_cols)))
                    and bool(info["is_unique"]) == is_unique
                    and not info["has_filter"]):
                found_exact = idx_name
                break
            # Check partial match: same columns (ignoring direction/unique)
            idx_col_names = [c[0] for c in idx_cols]
            target_col_names = [c[0] for c in target_cols]
            if idx_col_names == target_col_names:
                diffs = []
                for i in range(len(target_cols)):
                    if bool(idx_cols[i][1]) != target_cols[i][1]:
                        diffs.append(f"{target_cols[i][0]}: {'DESC' if target_cols[i][1] else 'ASC'} expected, {'DESC' if idx_cols[i][1] else 'ASC'} actual")
                if bool(info["is_unique"]) != is_unique:
                    diffs.append(f"unique={is_unique} expected, {info['is_unique']} actual")
                if info["has_filter"]:
                    diffs.append(f"has filter: {info['filter_def']}")
                if diffs:
                    found_partial = (idx_name, "; ".join(diffs))

        if found_exact:
            status = f"PRESENT-EXACT-MATCH ({found_exact})"
        elif found_partial:
            status = f"PRESENT-PARTIAL-MATCH ({found_partial[0]}: {found_partial[1]})"
            # Still need to create the exact index
            index_actions.append((tbl, cols_spec, is_unique))
        else:
            status = "MISSING"
            index_actions.append((tbl, cols_spec, is_unique))

        W(f"| {tbl} | {col_display} | {'Yes' if is_unique else 'No'} | {status} |")
        print(f"  {tbl} ({col_display}): {status}")

    # Phase 1b index analysis
    W("\n### Phase 1b Created Indexes\n")
    W("| Table | Index Name | §7 Match |")
    W("|---|---|---|")

    for tbl, idx_name in PHASE1B_INDEXES:
        key = (tbl, idx_name)
        if key in index_map:
            info = index_map[key]
            cols = info["columns"]
            col_str = ", ".join(f"{c} {'DESC' if d else 'ASC'}" for c, d in cols)

            # Check if it matches any §7 target
            match_desc = "extra (no §7 counterpart)"
            for s7_tbl, s7_cols, s7_unique in TARGET_INDEXES:
                if s7_tbl != tbl:
                    continue
                s7_target = []
                for c in s7_cols:
                    if c.startswith("-"):
                        s7_target.append((c[1:], True))
                    else:
                        s7_target.append((c, False))
                s7_col_names = [c[0] for c in s7_target]
                idx_col_names = [c[0] for c in cols]
                if idx_col_names == s7_col_names:
                    # Check if exact
                    if (len(cols) == len(s7_target)
                            and all(bool(cols[i][1]) == s7_target[i][1] for i in range(len(s7_target)))
                            and bool(info["is_unique"]) == s7_unique
                            and not info["has_filter"]):
                        match_desc = f"exact match to §7 ({', '.join(f'{c} DESC' if d else c for c, d in s7_target)})"
                    else:
                        diffs = []
                        for i in range(len(s7_target)):
                            if i < len(cols) and bool(cols[i][1]) != s7_target[i][1]:
                                diffs.append(f"{s7_target[i][0]} direction differs")
                        if bool(info["is_unique"]) != s7_unique:
                            diffs.append("unique flag differs")
                        if info["has_filter"]:
                            diffs.append("has filter predicate")
                        match_desc = f"partial match to §7 ({', '.join(diffs) if diffs else 'column subset match'})"
                    break

            W(f"| {tbl} | {idx_name} [{col_str}, unique={info['is_unique']}] | {match_desc} |")
        else:
            W(f"| {tbl} | {idx_name} | NOT FOUND (unexpected) |")
        print(f"  Phase1b: {tbl}.{idx_name}: present={key in index_map}")

    # ================================================================
    # §4. Column Existence Check
    # ================================================================
    print("\n[4] Column Existence Check (insights)...")
    W("\n## 4. Column Existence Check\n")

    W("| Table | Column | Exists | Type | Nullable |")
    W("|---|---|---|---|---|")
    for col in ["user_id", "source_position_id"]:
        cursor.execute(f"""
            SELECT t.name AS type_name, c.max_length, c.is_nullable
            FROM sys.columns c
            JOIN sys.types t ON c.user_type_id = t.user_type_id
            WHERE c.object_id = OBJECT_ID('insights') AND c.name = '{col}'
        """)
        row = cursor.fetchone()
        if row:
            W(f"| insights | {col} | Yes | {row[0]}({row[1]}) | {'Yes' if row[2] else 'No'} |")
            print(f"  insights.{col}: {row[0]}({row[1]}), nullable={row[2]}")
        else:
            W(f"| insights | {col} | **No** | -- | -- |")
            print(f"  insights.{col}: MISSING")

    # ================================================================
    # §5. Type Pre-condition Check (ISJSON columns must be nvarchar(max))
    # ================================================================
    print("\n[5] Type Pre-condition Check (ISJSON columns)...")
    W("\n## 5. Type Pre-condition Check (ISJSON columns)\n")
    W("| Table | Column | Type | Max Length | OK? |")
    W("|---|---|---|---|---|")

    type_blockers = []
    for tbl, col in ISJSON_COLUMNS:
        cursor.execute(f"""
            SELECT t.name AS type_name, c.max_length
            FROM sys.columns c
            JOIN sys.types t ON c.user_type_id = t.user_type_id
            WHERE c.object_id = OBJECT_ID('{tbl}') AND c.name = '{col}'
        """)
        row = cursor.fetchone()
        if row:
            type_name, max_len = row[0], row[1]
            # nvarchar(max) shows as max_length=-1, varchar(max) also -1
            is_ok = (type_name in ("nvarchar", "varchar") and max_len == -1)
            ok_str = "Yes" if is_ok else "**BLOCKER**"
            if not is_ok:
                type_blockers.append(f"{tbl}.{col} is {type_name}({max_len}), expected nvarchar(max) or varchar(max)")
            W(f"| {tbl} | {col} | {type_name} | {max_len} | {ok_str} |")
        else:
            W(f"| {tbl} | {col} | NOT FOUND | -- | **BLOCKER** |")
            type_blockers.append(f"{tbl}.{col} column not found")

    if type_blockers:
        W(f"\n**{len(type_blockers)} type blockers found:**")
        for b in type_blockers:
            W(f"- {b}")

    # ================================================================
    # §6. Data Pre-condition Check (FK orphan counts)
    # ================================================================
    print("\n[6] Data Pre-condition Check (FK orphan counts)...")
    W("\n## 6. Data Pre-condition Check (FK orphan counts)\n")
    W("| Child Table | Child Col | Parent Table | Parent Col | Orphan Count | Status |")
    W("|---|---|---|---|---|---|")

    orphan_blockers = []
    for action_type, child_tbl, child_col, parent_tbl, parent_col, cascade, fk_name in fk_actions:
        # Only check orphans for FKs we're about to add
        cursor.execute(f"""
            SELECT COUNT(*) FROM [{child_tbl}] c
            LEFT JOIN [{parent_tbl}] p ON c.[{child_col}] = p.[{parent_col}]
            WHERE c.[{child_col}] IS NOT NULL AND p.[{parent_col}] IS NULL
        """)
        orphan_count = cursor.fetchone()[0]
        status = "OK" if orphan_count == 0 else "**BLOCKER**"
        if orphan_count > 0:
            orphan_blockers.append(f"{child_tbl}.{child_col} -> {parent_tbl}.{parent_col}: {orphan_count} orphans")
        W(f"| {child_tbl} | {child_col} | {parent_tbl} | {parent_col} | {orphan_count} | {status} |")
        print(f"  {child_tbl}.{child_col} -> {parent_tbl}: orphans={orphan_count}")

    if orphan_blockers:
        W(f"\n**{len(orphan_blockers)} orphan blockers found:**")
        for b in orphan_blockers:
            W(f"- {b}")

    # Also check ISJSON data validity for columns getting constraints
    print("\n  Checking ISJSON data validity...")
    W("\n### ISJSON Data Validity\n")
    W("| Table | Column | Non-NULL Rows | Invalid JSON | Status |")
    W("|---|---|---|---|---|")

    json_blockers = []
    for tbl, col in ISJSON_COLUMNS:
        cursor.execute(f"""
            SELECT
                COUNT(*) AS total_nonnull,
                SUM(CASE WHEN ISJSON([{col}]) = 0 THEN 1 ELSE 0 END) AS invalid
            FROM [{tbl}]
            WHERE [{col}] IS NOT NULL
        """)
        row = cursor.fetchone()
        total, invalid = row[0] or 0, row[1] or 0
        status = "OK" if invalid == 0 else "**BLOCKER**"
        if invalid > 0:
            json_blockers.append(f"{tbl}.{col}: {invalid}/{total} rows have invalid JSON")
        W(f"| {tbl} | {col} | {total} | {invalid} | {status} |")

    if json_blockers:
        W(f"\n**{len(json_blockers)} JSON data blockers found:**")
        for b in json_blockers:
            W(f"- {b}")

    # ================================================================
    # §7. Final Action List
    # ================================================================
    print("\n[7] Generating action list...")
    W("\n## 7. Escalations\n")
    if escalations:
        for e in escalations:
            W(f"- **ESCALATE:** {e}")
    else:
        W("None.")

    W("\n## 8. Final Action List\n")
    W("This is the complete list of DDL statements Phase 2 will issue.\n")

    all_blockers = type_blockers + orphan_blockers + json_blockers
    if all_blockers:
        W(f"**WARNING: {len(all_blockers)} blockers must be resolved before migration can proceed.**\n")

    # FK additions
    W("### A. Foreign Key Constraints\n")
    W("```sql")
    for action_type, child_tbl, child_col, parent_tbl, parent_col, cascade, fk_name in fk_actions:
        cascade_sql = {"CASCADE": "CASCADE", "RESTRICT": "NO ACTION", "SET_NULL": "SET NULL"}[cascade]
        W(f"ALTER TABLE [{child_tbl}] ADD CONSTRAINT [{fk_name}]")
        W(f"    FOREIGN KEY ([{child_col}]) REFERENCES [{parent_tbl}]([{parent_col}])")
        W(f"    ON DELETE {cascade_sql};")
        W("")
    W("```\n")

    # ISJSON check constraints
    W("### B. ISJSON Check Constraints\n")
    W("```sql")
    for tbl, col, ck_name in check_actions:
        W(f"ALTER TABLE [{tbl}] ADD CONSTRAINT [{ck_name}]")
        W(f"    CHECK ([{col}] IS NULL OR ISJSON([{col}]) = 1);")
        W("")
    W("```\n")

    # Indexes
    W("### C. Indexes\n")

    # FK supporting indexes (single-column for each new FK that doesn't already have one)
    fk_index_actions = []
    for action_type, child_tbl, child_col, parent_tbl, parent_col, cascade, fk_name in fk_actions:
        # Check if an index starting with this column already exists
        has_index = False
        for (idx_tbl, idx_name), info in index_map.items():
            if idx_tbl == child_tbl and info["columns"][0][0] == child_col:
                has_index = True
                break
        # Also check if it's in the §7 target list (will be created as a named index)
        in_s7 = False
        for s7_tbl, s7_cols, s7_unique in TARGET_INDEXES:
            if s7_tbl == child_tbl and s7_cols[0].lstrip("-") == child_col:
                in_s7 = True
                break
        if not has_index and not in_s7:
            idx_name = f"ix_{child_tbl}_{child_col}"
            fk_index_actions.append((child_tbl, child_col, idx_name))

    # §7 named indexes to create
    W("```sql")
    W("-- FK supporting indexes (single-column, not covered by §7)")
    for tbl, col, idx_name in fk_index_actions:
        W(f"CREATE INDEX [{idx_name}] ON [{tbl}]([{col}]);")
    W("")
    W("-- §7 named composite/unique indexes")
    for tbl, cols_spec, is_unique in index_actions:
        col_parts = []
        for c in cols_spec:
            if c.startswith("-"):
                col_parts.append(f"[{c[1:]}] DESC")
            else:
                col_parts.append(f"[{c}]")
        col_str = ", ".join(col_parts)
        prefix = "ux" if is_unique else "ix"
        col_names = [c.lstrip("-") for c in cols_spec]
        idx_name = f"{prefix}_{tbl}_{'__'.join(col_names)}"
        unique_str = "UNIQUE " if is_unique else ""
        W(f"CREATE {unique_str}INDEX [{idx_name}] ON [{tbl}]({col_str});")
    W("```\n")

    # Summary
    W("### Summary\n")
    W(f"- **FKs to add:** {len(fk_actions)}")
    W(f"- **ISJSON checks to add:** {len(check_actions)}")
    W(f"- **FK supporting indexes to add:** {len(fk_index_actions)}")
    W(f"- **§7 indexes to add:** {len(index_actions)}")
    W(f"- **Escalations:** {len(escalations)}")
    W(f"- **Blockers:** {len(all_blockers)}")

    # Write report
    report_text = "\n".join(report)
    report_path = PROJECT_ROOT / "phase2-diagnostic-report.md"
    report_path.write_text(report_text, encoding="utf-8")

    cursor.close()
    conn.close()

    print(f"\n{'=' * 60}")
    print(f"Report written to: {report_path}")
    print(f"FKs to add: {len(fk_actions)}")
    print(f"ISJSON checks to add: {len(check_actions)}")
    print(f"FK supporting indexes: {len(fk_index_actions)}")
    print(f"§7 indexes: {len(index_actions)}")
    print(f"Escalations: {len(escalations)}")
    print(f"Blockers: {len(all_blockers)}")


if __name__ == "__main__":
    main()
