"""
Seed importer: Scoring Parameters.xlsx → engine_* configuration tables.

STANDALONE, BUILD-TIME ONLY.
    The workbook is the one-time seed source. After import, the runtime tables
    are the source of truth and are maintained through the strategy-administration
    UI. Re-import is for dev rebuilds only — it will UPSERT (never duplicate)
    on natural keys. Production edits live in the tables, NOT in the spreadsheet.

Usage:
    cd <project-root>
    python -m scripts.seed_engine_config [--xlsx path/to/workbook.xlsx] [--dry-run]

Requires:
    - OTA-681 engine_* tables already applied (alembic upgrade head)
    - openpyxl installed (pip install openpyxl)
    - Azure SQL reachable via Entra ID (az login)
"""

import argparse
import json
import logging
import re
import struct
import sys
import urllib.parse
from pathlib import Path

import openpyxl
import pyodbc

# Add project root to path so we can import app.core.config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── Default workbook path ────────────────────────────────────────────────
DEFAULT_XLSX = Path(__file__).resolve().parent.parent / "requirements" / "Configuration" / "Scoring Parameters.xlsx"

# ── Strategy column mapping (0-indexed column letters → indices) ─────────
# Each strategy occupies 4 columns: Include, Low, High, Weight
STRATEGIES = [
    {"key": "steady_paycheck",  "display": "Steady Paycheck",  "cols": {"include": 6, "low": 7, "high": 8, "weight": 9}},   # G H I J
    {"key": "weekly_grind",     "display": "Weekly Grind",      "cols": {"include": 10, "low": 11, "high": 12, "weight": 13}}, # K L M N
    {"key": "trend_rider",      "display": "Trend Rider",       "cols": {"include": 14, "low": 15, "high": 16, "weight": 17}}, # O P Q R
    {"key": "lottery_ticket",   "display": "Lottery Ticket",    "cols": {"include": 18, "low": 19, "high": 20, "weight": 21}}, # S T U V
]

# ── Scan parameters from rows 69-72 (per strategy, same column order) ───
SCAN_PARAM_ROWS = {
    69: "evaluation_cap",
    70: "dte_priority_start",
    71: "dte_expansion_direction",
    72: "output_rank_cap",
}
SCAN_PARAM_COLS = {
    "steady_paycheck": 6,   # G
    "weekly_grind": 10,      # K
    "trend_rider": 14,       # O
    "lottery_ticket": 18,    # S
}


def slugify(text: str) -> str:
    """Convert a description to a snake_case rule_key."""
    text = text.strip().lower()
    text = re.sub(r"[–—]", "_", text)       # em/en dashes
    text = re.sub(r"[^a-z0-9_]+", "_", text) # non-alnum → underscore
    text = re.sub(r"_+", "_", text)          # collapse runs
    return text.strip("_")


def validate_json(value, context: str) -> str:
    """Validate and return a JSON string. Raises on invalid JSON."""
    if value is None:
        return None
    s = json.dumps(value) if not isinstance(value, str) else value
    try:
        json.loads(s)
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"Invalid JSON for {context}: {e}\n  Value: {s!r}")
    return s


def connect_db() -> pyodbc.Connection:
    """Connect to Azure SQL using the project's DATABASE_URL + Entra ID token."""
    database_url = settings.database_url
    if not database_url.startswith("mssql"):
        raise RuntimeError(f"Expected mssql DATABASE_URL, got: {database_url[:30]}...")

    parsed = urllib.parse.urlparse(database_url)
    server = parsed.hostname
    port = parsed.port or 1433
    database = parsed.path.lstrip("/")

    odbc_connect = (
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server={server},{port};"
        f"Database={database};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
    )

    from azure.identity import DefaultAzureCredential
    cred = DefaultAzureCredential()
    token = cred.get_token("https://database.windows.net/.default")
    token_bytes = token.token.encode("UTF-16-LE")
    token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)

    SQL_COPT_SS_ACCESS_TOKEN = 1256
    conn = pyodbc.connect(odbc_connect, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})
    conn.autocommit = False
    log.info(f"Connected to {server}/{database}")
    return conn


# ── Workbook parsing ─────────────────────────────────────────────────────

def parse_workbook(xlsx_path: Path):
    """Parse the workbook into rule dicts, strategy dicts, junction dicts, lookup dicts."""
    wb = openpyxl.load_workbook(str(xlsx_path), data_only=True)
    ws = wb["Sheet1"]

    # Read all rows into a list of dicts (0-indexed columns)
    all_rows = []
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True):
        all_rows.append(list(row))

    rules = []
    junctions = []  # list of (rule_key, strategy_key, junction_data)
    eval_order_counters = {}  # (strategy_key, phase) → next order

    def next_eval_order(strategy_key, phase):
        k = (strategy_key, phase)
        eval_order_counters[k] = eval_order_counters.get(k, 0) + 1
        return eval_order_counters[k]

    # Parse data rows (4 through 58, skipping blanks and section headers)
    for row_idx in range(3, len(all_rows)):  # 0-indexed, so row 4 = index 3
        row = all_rows[row_idx]
        rule_type = row[0]  # col A
        if not rule_type or rule_type in (
            "Pattern: Rules below may also appear as Hard Gates above. This is intentional layering",
            "POST-SCORING ADJUSTMENTS",
            "VERDICT BANDS",
            "STRATEGY SCAN PARAMETERS",
        ):
            continue
        # Stop before verdict bands section
        if str(rule_type).startswith("Pattern:"):
            continue
        if rule_type in ("Verdict", "EXECUTE", "WAIT", "PASS", "Note:", "Parameter"):
            continue
        if rule_type not in ("Hard Gate", "Soft Gate", "Scoring Criteria", "Post-Scoring"):
            continue

        category = row[1]   # col B
        description = row[2]  # col C
        dtype = row[3]       # col D
        condition = row[4]   # col E
        tier = row[5]        # col F

        if not description:
            continue

        rule_key = slugify(str(description))

        # Map rule_type to engine phase
        if rule_type in ("Hard Gate", "Soft Gate"):
            phase = "gate"
        elif rule_type == "Scoring Criteria":
            phase = "scoring"
        elif rule_type == "Post-Scoring":
            phase = "adjustment"
            # Prefix adjustment rules to avoid key collision with gate rules
            # that share the same description (intentional layering per workbook)
            rule_key = f"adj_{rule_key}"
        else:
            continue

        # Determine null_semantics for data-completeness gates
        null_semantics = None
        if description and "Data completeness" in str(description):
            null_semantics = "FAIL_CLOSED"

        # Determine condition_expression
        condition_expression = str(condition) if condition else None

        # Determine formula_ref
        formula_ref = None
        if condition and "Black Scholes" in str(condition):
            formula_ref = f"formula:{rule_key}"
        elif condition and str(condition).startswith("TBD"):
            formula_ref = f"formula:{rule_key}"

        # Build referenced_named_values from condition text (best effort)
        ref_values = _extract_named_values(condition, description)

        # Build parameter_schema based on what parameters this rule accepts
        param_schema = _build_parameter_schema(rule_type, condition, description, dtype)

        rule = {
            "owner_app_id": "OTA",
            "rule_key": rule_key,
            "phase": phase,
            "tier": str(tier) if tier else None,
            "intent": str(description),
            "condition_expression": condition_expression,
            "formula_ref": formula_ref,
            "referenced_named_values": ref_values,
            "parameter_schema": param_schema,
            "null_semantics": null_semantics,
            "enabled": True,
        }
        rules.append(rule)

        # Build junction rows for each strategy
        for strat in STRATEGIES:
            cols = strat["cols"]
            include = row[cols["include"]]
            if not include or str(include).upper() != "Y":
                continue

            low_val = row[cols["low"]]
            high_val = row[cols["high"]]
            weight_val = row[cols["weight"]]

            # Build parameters JSON
            params = {}
            if low_val is not None and str(low_val) not in ("N/A", "lookup", ""):
                try:
                    params["low"] = float(low_val)
                except (ValueError, TypeError):
                    params["low"] = str(low_val)
            if high_val is not None and str(high_val) not in ("N/A", "lookup", ""):
                try:
                    params["high"] = float(high_val)
                except (ValueError, TypeError):
                    params["high"] = str(high_val)

            # For lookup-based thresholds (width tier compliance)
            if low_val == "lookup" or high_val == "lookup":
                params["lookup_set"] = "spread_width_tiers"

            # Determine stop_if_fail and score_penalty
            if rule_type == "Hard Gate":
                stop_if_fail = True
                score_penalty = None
            elif rule_type == "Soft Gate":
                stop_if_fail = False
                score_penalty = _extract_penalty(condition)
            elif rule_type == "Post-Scoring":
                stop_if_fail = False
                score_penalty = _extract_penalty(condition)
            else:
                stop_if_fail = False
                score_penalty = None

            # Weight (scoring criteria only)
            weight = None
            if phase == "scoring" and weight_val is not None:
                try:
                    weight = float(weight_val)
                except (ValueError, TypeError):
                    pass

            junction = {
                "rule_key": rule_key,
                "strategy_key": strat["key"],
                "evaluation_order": next_eval_order(strat["key"], phase),
                "stop_if_fail": stop_if_fail,
                "score_penalty": score_penalty,
                "weight": weight,
                "parameters": params if params else None,
                "enabled": True,
            }
            junctions.append(junction)

    # ── Strategies ───────────────────────────────────────────────────────
    # Verdict bands (rows 62-64)
    verdict_bands = [
        {"verdict": "EXECUTE", "min_score": 70, "max_score": 100},
        {"verdict": "WAIT",    "min_score": 50, "max_score": 69.99},
        {"verdict": "PASS",    "min_score": 0,  "max_score": 49.99},
    ]

    # Scan parameters (rows 69-72)
    scan_params_by_strategy = {}
    for row_num, param_name in SCAN_PARAM_ROWS.items():
        row = all_rows[row_num - 1]  # 0-indexed
        for strat_key, col_idx in SCAN_PARAM_COLS.items():
            val = row[col_idx]
            if strat_key not in scan_params_by_strategy:
                scan_params_by_strategy[strat_key] = {}
            if val is not None:
                scan_params_by_strategy[strat_key][param_name] = val

    strategies = []
    for strat in STRATEGIES:
        # Extract DTE window from the per-strategy DTE hard gate (row 15 = index 14)
        dte_row = all_rows[14]
        cols = strat["cols"]
        dte_low = dte_row[cols["low"]]
        dte_high = dte_row[cols["high"]]

        # Determine compatible_structures from trade type gates
        compat = []
        for row_idx in range(23, 32):  # rows 24-32 (0-indexed 23-31)
            row = all_rows[row_idx]
            if row[0] == "Hard Gate" and row[1] == "Trade Type":
                include = row[cols["include"]]
                if include and str(include).upper() == "Y":
                    desc = str(row[2])
                    # Only add specific trade types, not meta-rules
                    if desc in ("BULL_PUT_CREDIT", "BEAR_CALL_CREDIT", "BULL_CALL_DEBIT",
                                "BEAR_PUT_DEBIT", "LONG_CALL", "LONG_PUT", "IRON_CONDOR"):
                        compat.append(desc)

        strategy = {
            "owner_app_id": "OTA",
            "strategy_key": strat["key"],
            "display_name": strat["display"],
            "consumer_surface": "SCREENING",
            "description": None,
            "compatible_structures": compat if compat else None,
            "verdict_band_set": verdict_bands,
            "dte_min": int(dte_low) if dte_low else None,
            "dte_max": int(dte_high) if dte_high else None,
            "enabled": True,
        }
        strategies.append(strategy)

    # ── Lookups ──────────────────────────────────────────────────────────
    lookups = []

    # Pipeline phases (SHARED)
    for i, phase in enumerate(["gate", "scoring", "adjustment", "verdict"], 1):
        lookups.append({
            "owner_app_id": "SHARED",
            "lookup_set": "pipeline_phases",
            "lookup_key": phase,
            "payload": {"label": phase.title(), "description": f"Pipeline phase: {phase}"},
            "sort_order": i,
        })

    # Calculation tiers (SHARED)
    for i, tier in enumerate(["RAW", "DERIVED", "COMPUTED"], 1):
        lookups.append({
            "owner_app_id": "SHARED",
            "lookup_set": "calculation_tiers",
            "lookup_key": tier,
            "payload": {"label": tier, "description": f"Calculation tier: {tier}"},
            "sort_order": i,
        })

    # Null semantics (SHARED)
    for i, sem in enumerate(["FAIL_OPEN", "FAIL_CLOSED", "SKIP"], 1):
        lookups.append({
            "owner_app_id": "SHARED",
            "lookup_set": "null_semantics",
            "lookup_key": sem,
            "payload": {"label": sem},
            "sort_order": i,
        })

    # Consumer surfaces (SHARED)
    for i, surf in enumerate(["SCREENING", "POSITION_HEALTH", "DIRECTIONAL"], 1):
        lookups.append({
            "owner_app_id": "SHARED",
            "lookup_set": "consumer_surfaces",
            "lookup_key": surf,
            "payload": {"label": surf},
            "sort_order": i,
        })

    # Verdict domains (OTA — screening verdicts)
    for i, v in enumerate(verdict_bands, 1):
        lookups.append({
            "owner_app_id": "OTA",
            "lookup_set": "screening_verdicts",
            "lookup_key": v["verdict"],
            "payload": {"min_score": v["min_score"], "max_score": v["max_score"]},
            "sort_order": i,
        })

    # Width tiers from Width Configuration sheet (OTA)
    ws2 = wb["Width Configuration"]
    for i, row in enumerate(ws2.iter_rows(min_row=3, max_row=7, values_only=True), 1):
        if row[0] is None:
            continue
        lookups.append({
            "owner_app_id": "OTA",
            "lookup_set": "spread_width_tiers",
            "lookup_key": f"tier_{i}",
            "payload": {
                "price_min": row[0],
                "price_max": row[1],
                "width_min": row[2],
                "width_max": row[3],
                "width_increment": row[4],
            },
            "sort_order": i,
        })

    # Scan parameters per strategy (OTA)
    for strat_key, params in scan_params_by_strategy.items():
        lookups.append({
            "owner_app_id": "OTA",
            "lookup_set": "scan_parameters",
            "lookup_key": strat_key,
            "payload": params,
            "sort_order": None,
        })

    return rules, strategies, junctions, lookups


def _extract_named_values(condition, description) -> list[str]:
    """Best-effort extraction of named values from condition text."""
    vals = []
    if not condition:
        return vals
    cond = str(condition)
    # Common patterns
    patterns = {
        r"\bstock_price\b": "stock_price",
        r"\bnext_earnings_date\b": "next_earnings_date",
        r"\bexpiry_date\b": "expiry_date",
        r"\bspread\b": "bid_ask_spread",
        r"\bmin_leg_OI\b": "min_leg_open_interest",
        r"\bmin_leg_volume\b": "min_leg_volume",
        r"\bDTE\b": "dte",
        r"\bIV_rank\b": "iv_rank",
        r"\bdelta\b": "delta",
        r"\bATR_14\b": "atr_14",
        r"\bcredit/spread_width\b": "credit_width_pct",
        r"\bdebit/spread_width\b": "debit_width_pct",
        r"\btotal_EV\b": "total_ev",
        r"\bspot\b": "stock_price",
        r"\bshort_strike\b": "short_strike",
        r"\bSMA_50\b": "sma_50",
        r"\bchart_state\b": "chart_state",
        r"\bspread_width\b": "spread_width",
        r"\bcushion_vs_ATR\b": "cushion_vs_atr",
        r"\btheta_total_over_trade\b": "theta_total",
        r"\bdebit\b": "debit",
    }
    for pattern, name in patterns.items():
        if re.search(pattern, cond, re.IGNORECASE):
            if name not in vals:
                vals.append(name)

    # Data completeness gates
    desc = str(description) if description else ""
    if "Data completeness" in desc:
        if "IV Rank" in desc:
            vals.append("iv_rank")
        elif "Delta" in desc:
            vals.append("delta")
        elif "ATR_14" in desc:
            vals.append("atr_14")

    # For ETF bonus
    if "ETF" in str(condition or ""):
        vals.append("is_etf")

    return vals


def _build_parameter_schema(rule_type, condition, description, dtype) -> dict | None:
    """Build a parameter schema for the rule based on its type."""
    if dtype == "Binary Choice":
        return None  # No parameters — it's a Y/N gate

    cond = str(condition) if condition else ""
    desc = str(description) if description else ""

    # Data completeness gates have no parameters
    if "IS NOT NULL" in cond or "IS NULL" in cond:
        return None

    # BETWEEN-style rules have low/high
    if "BETWEEN" in cond or "is BETWEEN" in cond:
        return {"low": {"type": "number"}, "high": {"type": "number"}}

    # >= threshold style
    if ">= threshold" in cond or "<= threshold" in cond:
        return {"low": {"type": "number"}, "high": {"type": "number"}}

    # Post-scoring penalties/bonuses with a threshold
    if rule_type == "Post-Scoring" and (">" in cond or "BETWEEN" in cond):
        return {"threshold": {"type": "number"}}

    # Scoring criteria — formulas, typically no user-configurable params
    if rule_type == "Scoring Criteria":
        return None

    # Chart state matching
    if "chart_state" in cond:
        return None

    # Lookup-based
    if "Width Configuration" in cond:
        return {"lookup_set": {"type": "string"}}

    return None


def _extract_penalty(condition) -> float | None:
    """Extract penalty/bonus amount from condition text like 'REDUCE SCORE BY 10'."""
    if not condition:
        return None
    m = re.search(r"(?:REDUCE|DECREASE)\s+SCORE\s+BY\s+(\d+)", str(condition), re.IGNORECASE)
    if m:
        return -float(m.group(1))
    m = re.search(r"INCREASE\s+SCORE\s+BY\s+(\d+)", str(condition), re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


# ── Database write ───────────────────────────────────────────────────────

def upsert_rules(cursor, rules: list[dict]) -> dict[str, int]:
    """Upsert rules and return {rule_key: rule_id} mapping."""
    rule_id_map = {}
    for r in rules:
        ref_vals = validate_json(r["referenced_named_values"], f"rule {r['rule_key']} referenced_named_values")
        param_sch = validate_json(r["parameter_schema"], f"rule {r['rule_key']} parameter_schema")

        # Check if exists
        cursor.execute(
            "SELECT rule_id FROM dbo.engine_rules WHERE owner_app_id = ? AND rule_key = ?",
            r["owner_app_id"], r["rule_key"],
        )
        existing = cursor.fetchone()

        if existing:
            rule_id = existing[0]
            cursor.execute("""
                UPDATE dbo.engine_rules SET
                    phase = ?, tier = ?, intent = ?, condition_expression = ?,
                    formula_ref = ?, referenced_named_values = ?, parameter_schema = ?,
                    null_semantics = ?, enabled = ?, updated_at = GETUTCDATE()
                WHERE rule_id = ?
            """, r["phase"], r["tier"], r["intent"], r["condition_expression"],
                r["formula_ref"], ref_vals, param_sch,
                r["null_semantics"], 1 if r["enabled"] else 0, rule_id)
            log.debug(f"  Updated rule: {r['rule_key']} (id={rule_id})")
        else:
            cursor.execute("""
                INSERT INTO dbo.engine_rules
                    (owner_app_id, rule_key, phase, tier, intent, condition_expression,
                     formula_ref, referenced_named_values, parameter_schema, null_semantics, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, r["owner_app_id"], r["rule_key"], r["phase"], r["tier"], r["intent"],
                r["condition_expression"], r["formula_ref"], ref_vals, param_sch,
                r["null_semantics"], 1 if r["enabled"] else 0)
            cursor.execute("SELECT @@IDENTITY")
            rule_id = int(cursor.fetchone()[0])
            log.debug(f"  Inserted rule: {r['rule_key']} (id={rule_id})")

        rule_id_map[r["rule_key"]] = rule_id

    log.info(f"Rules: {len(rule_id_map)} upserted")
    return rule_id_map


def upsert_strategies(cursor, strategies: list[dict]) -> dict[str, int]:
    """Upsert strategies and return {strategy_key: strategy_id} mapping."""
    strat_id_map = {}
    for s in strategies:
        compat = validate_json(s["compatible_structures"], f"strategy {s['strategy_key']} compatible_structures")
        bands = validate_json(s["verdict_band_set"], f"strategy {s['strategy_key']} verdict_band_set")

        cursor.execute(
            "SELECT strategy_id FROM dbo.engine_strategies WHERE owner_app_id = ? AND strategy_key = ?",
            s["owner_app_id"], s["strategy_key"],
        )
        existing = cursor.fetchone()

        if existing:
            strat_id = existing[0]
            cursor.execute("""
                UPDATE dbo.engine_strategies SET
                    display_name = ?, consumer_surface = ?, description = ?,
                    compatible_structures = ?, verdict_band_set = ?,
                    dte_min = ?, dte_max = ?, enabled = ?, updated_at = GETUTCDATE()
                WHERE strategy_id = ?
            """, s["display_name"], s["consumer_surface"], s["description"],
                compat, bands, s["dte_min"], s["dte_max"],
                1 if s["enabled"] else 0, strat_id)
            log.debug(f"  Updated strategy: {s['strategy_key']} (id={strat_id})")
        else:
            cursor.execute("""
                INSERT INTO dbo.engine_strategies
                    (owner_app_id, strategy_key, display_name, consumer_surface, description,
                     compatible_structures, verdict_band_set, dte_min, dte_max, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, s["owner_app_id"], s["strategy_key"], s["display_name"],
                s["consumer_surface"], s["description"], compat, bands,
                s["dte_min"], s["dte_max"], 1 if s["enabled"] else 0)
            cursor.execute("SELECT @@IDENTITY")
            strat_id = int(cursor.fetchone()[0])
            log.debug(f"  Inserted strategy: {s['strategy_key']} (id={strat_id})")

        strat_id_map[s["strategy_key"]] = strat_id

    log.info(f"Strategies: {len(strat_id_map)} upserted")
    return strat_id_map


def upsert_junctions(cursor, junctions: list[dict], rule_id_map: dict, strat_id_map: dict):
    """Upsert junction rows keyed on (strategy_id, rule_id)."""
    count = 0
    for j in junctions:
        rule_id = rule_id_map.get(j["rule_key"])
        strat_id = strat_id_map.get(j["strategy_key"])
        if rule_id is None:
            log.warning(f"  Skipping junction: unknown rule_key '{j['rule_key']}'")
            continue
        if strat_id is None:
            log.warning(f"  Skipping junction: unknown strategy_key '{j['strategy_key']}'")
            continue

        params = validate_json(j["parameters"], f"junction {j['strategy_key']}×{j['rule_key']} parameters")

        cursor.execute(
            "SELECT junction_id FROM dbo.engine_strategy_rule_junction WHERE strategy_id = ? AND rule_id = ?",
            strat_id, rule_id,
        )
        existing = cursor.fetchone()

        if existing:
            jid = existing[0]
            cursor.execute("""
                UPDATE dbo.engine_strategy_rule_junction SET
                    evaluation_order = ?, stop_if_fail = ?, score_penalty = ?,
                    weight = ?, parameters = ?, enabled = ?, updated_at = GETUTCDATE()
                WHERE junction_id = ?
            """, j["evaluation_order"], 1 if j["stop_if_fail"] else 0,
                j["score_penalty"], j["weight"], params,
                1 if j["enabled"] else 0, jid)
            log.debug(f"  Updated junction: {j['strategy_key']}×{j['rule_key']}")
        else:
            cursor.execute("""
                INSERT INTO dbo.engine_strategy_rule_junction
                    (strategy_id, rule_id, evaluation_order, stop_if_fail,
                     score_penalty, weight, parameters, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, strat_id, rule_id, j["evaluation_order"],
                1 if j["stop_if_fail"] else 0, j["score_penalty"],
                j["weight"], params, 1 if j["enabled"] else 0)
            log.debug(f"  Inserted junction: {j['strategy_key']}×{j['rule_key']}")
        count += 1

    log.info(f"Junctions: {count} upserted")


def upsert_lookups(cursor, lookups: list[dict]):
    """Upsert lookup rows keyed on (owner_app_id, lookup_set, lookup_key)."""
    count = 0
    for lk in lookups:
        payload = validate_json(lk["payload"], f"lookup {lk['lookup_set']}/{lk['lookup_key']}")

        cursor.execute(
            "SELECT lookup_id FROM dbo.engine_lookups WHERE owner_app_id = ? AND lookup_set = ? AND lookup_key = ?",
            lk["owner_app_id"], lk["lookup_set"], lk["lookup_key"],
        )
        existing = cursor.fetchone()

        if existing:
            lid = existing[0]
            cursor.execute("""
                UPDATE dbo.engine_lookups SET
                    payload = ?, sort_order = ?, enabled = ?
                WHERE lookup_id = ?
            """, payload, lk["sort_order"], 1, lid)
        else:
            cursor.execute("""
                INSERT INTO dbo.engine_lookups
                    (owner_app_id, lookup_set, lookup_key, payload, sort_order, enabled)
                VALUES (?, ?, ?, ?, ?, ?)
            """, lk["owner_app_id"], lk["lookup_set"], lk["lookup_key"],
                payload, lk["sort_order"], 1)
        count += 1

    log.info(f"Lookups: {count} upserted")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Seed engine_* config tables from Scoring Parameters.xlsx")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX, help="Path to workbook")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, do not write to DB")
    args = parser.parse_args()

    if not args.xlsx.exists():
        log.error(f"Workbook not found: {args.xlsx}")
        sys.exit(1)

    log.info(f"Parsing workbook: {args.xlsx}")
    rules, strategies, junctions, lookups = parse_workbook(args.xlsx)

    log.info(f"Parsed: {len(rules)} rules, {len(strategies)} strategies, "
             f"{len(junctions)} junctions, {len(lookups)} lookups")

    if args.dry_run:
        log.info("DRY RUN — no database writes")
        for r in rules:
            log.info(f"  Rule: {r['rule_key']} ({r['phase']}/{r['tier']})")
        for s in strategies:
            log.info(f"  Strategy: {s['strategy_key']} ({s['consumer_surface']})")
        for j in junctions:
            log.info(f"  Junction: {j['strategy_key']} × {j['rule_key']} "
                     f"(order={j['evaluation_order']}, stop={j['stop_if_fail']})")
        for lk in lookups:
            log.info(f"  Lookup: {lk['owner_app_id']}/{lk['lookup_set']}/{lk['lookup_key']}")
        return

    conn = connect_db()
    cursor = conn.cursor()
    try:
        # Verify engine_apps seed exists
        cursor.execute("SELECT app_id FROM dbo.engine_apps")
        apps = {row[0] for row in cursor.fetchall()}
        if "SHARED" not in apps or "OTA" not in apps:
            log.error("engine_apps missing SHARED or OTA rows. Apply OTA-681 migration first.")
            sys.exit(1)

        rule_id_map = upsert_rules(cursor, rules)
        strat_id_map = upsert_strategies(cursor, strategies)
        upsert_junctions(cursor, junctions, rule_id_map, strat_id_map)
        upsert_lookups(cursor, lookups)

        conn.commit()
        log.info("Seed import committed successfully.")

        # Summary counts
        for table in ["engine_rules", "engine_strategies", "engine_strategy_rule_junction", "engine_lookups"]:
            cursor.execute(f"SELECT COUNT(*) FROM dbo.{table}")
            log.info(f"  {table}: {cursor.fetchone()[0]} rows")

    except Exception:
        conn.rollback()
        log.exception("Seed import FAILED — rolled back")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
