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
                params["lookup_set"] = "width_configuration"

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

    # ── Post-process: enrich ETF adjustment rule's referenced_named_values ──
    # OTA-690: is_etf is a required input (producer = options-chain adapter,
    # not yet built). The ETF rule also references the width_configuration
    # lookup for ETF-specific spread width adjustments.
    for r in rules:
        if r["rule_key"].startswith("adj_") and "etf" in r["rule_key"]:
            r["referenced_named_values"] = [
                {
                    "name": "is_etf",
                    "producer": "options-chain-adapter",
                    "status": "requirement-only",
                    "note": "Producer not yet built — later feature. Records the input requirement.",
                },
                {
                    "name": "width_configuration",
                    "type": "lookup_ref",
                    "lookup_set": "width_configuration",
                    "note": "Width tiers may vary for ETF underlyings; runtime resolves via lookup.",
                },
            ]

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
    tier_count = 0
    for i, row in enumerate(ws2.iter_rows(min_row=3, max_row=7, values_only=True), 1):
        if row[0] is None:
            continue
        lookups.append({
            "owner_app_id": "OTA",
            "lookup_set": "width_configuration",
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
        tier_count = i

    # Per-security override shape (empty — overrides added later via admin UI)
    lookups.append({
        "owner_app_id": "OTA",
        "lookup_set": "width_configuration",
        "lookup_key": "_override_schema",
        "payload": {
            "type": "per_security_override",
            "fields": {
                "ticker": {"type": "string", "required": True},
                "width_min": {"type": "number", "required": True},
                "width_max": {"type": "number", "required": True},
                "width_increment": {"type": "number", "required": True},
                "note": {"type": "string", "required": False},
            },
            "description": "Per-security width overrides. Ticker match → use override; else fall back to price-tier default.",
        },
        "sort_order": tier_count + 1,
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


# ── Compound rule decomposition (OTA-683) ───────────────────────────────
#
# Post-parse step: identifies compound rules in the workbook-parsed output
# and replaces each with its stated number of atomic rules (2/2/2/4/2/2 = 14).
# BETWEEN → two comparison rows. No runtime BETWEEN operator is implemented.
# Earnings 4-route tree mirrors earnings_gate.py route semantics exactly.
# Graduated cushion penalty mirrors strategy_scorer.py _cushion_penalty bands.


def _find_compound(rules, *keywords, phase=None, exclude=None):
    """Find a rule whose rule_key or intent contains all given keywords."""
    for r in rules:
        key = r["rule_key"].lower()
        intent = (r.get("intent") or "").lower()
        text = f"{key} {intent}"
        if all(kw.lower() in text for kw in keywords):
            if phase and r["phase"] != phase:
                continue
            if exclude and exclude.lower() in key:
                continue
            return r
    return None


def _make_atomic(base_rule, *, rule_key, intent, condition_expr=None,
                 formula_ref=None, ref_values=None, param_schema=None):
    """Create an atomic rule dict derived from a compound rule's metadata."""
    return {
        "owner_app_id": base_rule["owner_app_id"],
        "rule_key": rule_key,
        "phase": base_rule["phase"],
        "tier": base_rule["tier"],
        "intent": intent,
        "condition_expression": condition_expr,
        "formula_ref": formula_ref,
        "referenced_named_values": ref_values if ref_values is not None else base_rule.get("referenced_named_values", []),
        "parameter_schema": param_schema,
        "null_semantics": base_rule.get("null_semantics"),
        "enabled": True,
    }


# ── Individual decomposers ──────────────────────────────────────────────
# Each returns (old_rule_key, [(atomic_rule_dict, junction_overrides)]) or None.
# junction_overrides is a dict of fields to override on each replicated junction,
# or None to inherit the compound's junction properties unchanged.


def _decompose_chart_state(rules):
    """1. Chart state confirms direction → 2 atomic rules."""
    compound = _find_compound(rules, "chart_state", "direction", phase="gate")
    if not compound:
        compound = _find_compound(rules, "chart_state", "confirms", phase="gate")
    if not compound:
        return None

    atoms = [
        (_make_atomic(
            compound,
            rule_key="chart_state_valid_alignment",
            intent="Chart state must be Bullish Alignment or Bearish Alignment",
            condition_expr="chart_state IN ('Bullish Alignment', 'Bearish Alignment')",
            ref_values=["chart_state"],
        ), None),
        (_make_atomic(
            compound,
            rule_key="chart_state_matches_trade_direction",
            intent="Chart state alignment must match trade direction (bullish for bull trades, bearish for bear trades)",
            formula_ref="formula:chart_state_matches_direction",
            ref_values=["chart_state", "trade_direction"],
        ), None),
    ]
    return compound["rule_key"], atoms


def _decompose_stock_extended(rules):
    """2. Stock extended in trade direction → 2 atomic rules."""
    compound = _find_compound(rules, "stock", "extended", phase="adjustment")
    if not compound:
        return None

    atoms = [
        (_make_atomic(
            compound,
            rule_key="adj_stock_extended_magnitude",
            intent="Stock price extended > 5% from 50-day SMA",
            condition_expr="abs(spot - SMA_50) / SMA_50 > 0.05",
            ref_values=["stock_price", "sma_50"],
        ), None),
        (_make_atomic(
            compound,
            rule_key="adj_stock_extended_direction_match",
            intent="Extension direction matches trade direction (above SMA for bull, below for bear)",
            formula_ref="formula:extension_matches_trade_direction",
            ref_values=["stock_price", "sma_50", "trade_direction"],
        ), None),
    ]
    return compound["rule_key"], atoms


def _decompose_cushion_atr(rules):
    """3. Cushion barely above ATR floor (BETWEEN) → 2 comparison rules."""
    compound = _find_compound(rules, "cushion", "atr", phase="adjustment")
    if not compound:
        return None

    atoms = [
        (_make_atomic(
            compound,
            rule_key="adj_cushion_vs_atr_gte_floor",
            intent="Cushion-to-ATR ratio at or above lower bound (>= 1.0)",
            condition_expr="cushion_vs_ATR >= 1.0",
            ref_values=["cushion_vs_atr"],
            param_schema={"threshold": {"type": "number", "default": 1.0}},
        ), None),
        (_make_atomic(
            compound,
            rule_key="adj_cushion_vs_atr_lte_ceiling",
            intent="Cushion-to-ATR ratio at or below upper bound (<= 1.5)",
            condition_expr="cushion_vs_ATR <= 1.5",
            ref_values=["cushion_vs_atr"],
            param_schema={"threshold": {"type": "number", "default": 1.5}},
        ), None),
    ]
    return compound["rule_key"], atoms


def _decompose_earnings(rules):
    """4. Earnings gate 4-route tree → 4 atomic rules per earnings_gate.py.

    Route semantics mirror EarningsInWindowGate exactly:
      Route 1: dte_before <= 7, dte_after < 14  → PASS (stop)
      Route 2: dte_before <= 7, dte_after >= 14  → WAIT_FOR_EARNINGS (stop)
      Route 3: dte_before >= 8, dte_after >= 21  → WAIT_FOR_EARNINGS (stop)
      Route 4: dte_before >= 8, dte_after < 21   → score with 15-pt penalty (non-stop)
    """
    compound = _find_compound(rules, "earnings", phase="gate")
    if not compound:
        return None

    atoms = [
        (_make_atomic(
            compound,
            rule_key="earnings_route1_no_viable_window",
            intent="Route 1: No viable window — dte_before <= 7 and dte_after < 14. Verdict: PASS.",
            formula_ref="formula:earnings_route1_no_viable_window",
            ref_values=["next_earnings_date", "entry_date", "expiry_date",
                        "dte_before_earnings", "dte_after_earnings"],
        ), {"stop_if_fail": True, "score_penalty": None}),

        (_make_atomic(
            compound,
            rule_key="earnings_route2_wait_post_window",
            intent="Route 2: Pre-earnings window too short, strong post-earnings window — dte_before <= 7 and dte_after >= 14. Verdict: WAIT_FOR_EARNINGS.",
            formula_ref="formula:earnings_route2_wait_post_window",
            ref_values=["next_earnings_date", "entry_date", "expiry_date",
                        "dte_before_earnings", "dte_after_earnings"],
        ), {"stop_if_fail": True, "score_penalty": None}),

        (_make_atomic(
            compound,
            rule_key="earnings_route3_post_entry_better",
            intent="Route 3: Post-earnings entry likely better — dte_before >= 8 and dte_after >= 21. Verdict: WAIT_FOR_EARNINGS.",
            formula_ref="formula:earnings_route3_post_entry_better",
            ref_values=["next_earnings_date", "entry_date", "expiry_date",
                        "dte_before_earnings", "dte_after_earnings"],
        ), {"stop_if_fail": True, "score_penalty": None}),

        (_make_atomic(
            compound,
            rule_key="earnings_route4_pre_momentum_play",
            intent="Route 4: Pre-earnings momentum play — dte_before >= 8 and dte_after < 21. Score normally with 15-point penalty, effective DTE = dte_before - 1.",
            formula_ref="formula:earnings_route4_pre_momentum_play",
            ref_values=["next_earnings_date", "entry_date", "expiry_date",
                        "dte_before_earnings", "dte_after_earnings"],
        ), {"stop_if_fail": False, "score_penalty": -15.0}),
    ]
    return compound["rule_key"], atoms


def _decompose_credit_debit(rules):
    """5. Credit/debit quality gate → 2 atomic rules.

    Thresholds from evaluation_routes.py lines 626-663:
      Credit: credit_pct_of_width >= 0.30 (fail below)
      Debit:  debit_pct_of_width  <= 0.40 (fail above)
    """
    compound = _find_compound(rules, "credit", "debit", phase="gate")
    if not compound:
        compound = _find_compound(rules, "credit", "width", phase="gate")
    if not compound:
        compound = _find_compound(rules, "spread", "quality", phase="gate")
    if not compound:
        return None

    atoms = [
        (_make_atomic(
            compound,
            rule_key="credit_pct_of_width_floor",
            intent="Credit spread: credit received must be >= 30% of spread width",
            condition_expr="credit_pct_of_width >= 0.30",
            ref_values=["credit_width_pct", "spread_width", "net_credit"],
            param_schema={"threshold": {"type": "number", "default": 0.30}},
        ), {"stop_if_fail": True, "score_penalty": None}),
        (_make_atomic(
            compound,
            rule_key="debit_pct_of_width_ceiling",
            intent="Debit spread: debit paid must be <= 40% of spread width",
            condition_expr="debit_pct_of_width <= 0.40",
            ref_values=["debit_width_pct", "spread_width", "net_debit"],
            param_schema={"threshold": {"type": "number", "default": 0.40}},
        ), {"stop_if_fail": True, "score_penalty": None}),
    ]
    return compound["rule_key"], atoms


def _decompose_cushion_penalty(rules):
    """6. Cushion penalty graduated bands → 2 ordered adjustment rules.

    Bands from strategy_scorer.py _cushion_penalty (lines 138-142):
      Band 1: cushion_pct < 1.0%  → -20 points
      Band 2: cushion_pct in [1.0%, 2.0%) → -10 points

    This compound exists in code (strategy_scorer.py) but may not be in the
    workbook as a single row. If no compound is found, the atomic rules are
    injected directly using a synthetic base template.
    """
    compound = _find_compound(rules, "cushion", phase="adjustment", exclude="atr")
    if not compound:
        compound = _find_compound(rules, "cushion", "penalty", phase="adjustment")

    # Synthetic base when the workbook has no matching compound row
    base = compound or {
        "owner_app_id": "OTA",
        "phase": "adjustment",
        "tier": "DERIVED",
        "null_semantics": None,
    }

    atoms = [
        (_make_atomic(
            base,
            rule_key="adj_cushion_penalty_severe",
            intent="Cushion < 1.0% of underlying price — severe proximity to short strike (-20 points)",
            condition_expr="cushion_pct < 1.0",
            ref_values=["stock_price", "short_strike"],
        ), {"score_penalty": -20.0}),
        (_make_atomic(
            base,
            rule_key="adj_cushion_penalty_moderate",
            intent="Cushion >= 1.0% and < 2.0% of underlying price — moderate proximity to short strike (-10 points)",
            formula_ref="formula:cushion_penalty_moderate",
            ref_values=["stock_price", "short_strike"],
        ), {"score_penalty": -10.0}),
    ]

    if compound:
        return compound["rule_key"], atoms
    # No compound to remove — return sentinel key that won't match any existing rule
    return "_synthetic_cushion_penalty_", atoms


# ── Orchestrator ────────────────────────────────────────────────────────

def decompose_compound_rules(rules, junctions):
    """
    OTA-683: Decompose compound rules into atomic engine_rules rows.

    Six compounds are decomposed into 14 total atomic rules (2+2+2+4+2+2).
    BETWEEN-style conditions become two comparison rows; the runtime BETWEEN
    operator is deferred to the engine-core expression library.
    Earnings routes mirror earnings_gate.py; stop_if_fail is intrinsic per route.
    Graduated cushion penalty mirrors strategy_scorer.py _cushion_penalty bands.
    """
    decomposers = [
        ("chart_state_confirms_direction",    _decompose_chart_state),
        ("stock_extended_in_trade_direction",  _decompose_stock_extended),
        ("cushion_barely_above_atr_floor",     _decompose_cushion_atr),
        ("earnings_4_route_tree",              _decompose_earnings),
        ("credit_debit_quality_gate",          _decompose_credit_debit),
        ("cushion_penalty_graduated_bands",    _decompose_cushion_penalty),
    ]

    removals = set()
    additions = []       # (old_key, [(rule, junction_overrides)])
    injections = []      # [(rule, junction_overrides)] — new rules with no compound to replace

    for label, decomposer in decomposers:
        result = decomposer(rules)
        if result is None:
            log.warning(f"  Compound '{label}' not found in parsed rules — skipping")
            continue
        old_key, atoms = result
        atom_keys = [a[0]["rule_key"] for a in atoms]
        if old_key.startswith("_synthetic_"):
            # No compound to remove; rules are injected fresh
            injections.extend(atoms)
            log.info(f"  Injected (no workbook compound): {atom_keys}")
        else:
            removals.add(old_key)
            additions.append((old_key, atoms))
            log.info(f"  Decomposed '{old_key}' → {atom_keys}")

    # Rebuild rules: remove compounds, add atomics + injections
    new_rules = [r for r in rules if r["rule_key"] not in removals]
    for _, atoms in additions:
        for rule, _ in atoms:
            new_rules.append(rule)
    for rule, _ in injections:
        new_rules.append(rule)

    # Rebuild junctions: replace compound refs with per-atomic refs
    new_junctions = []
    for j in junctions:
        if j["rule_key"] not in removals:
            new_junctions.append(j)
            continue
        for old_key, atoms in additions:
            if j["rule_key"] == old_key:
                for rule, overrides in atoms:
                    new_j = dict(j)
                    new_j["rule_key"] = rule["rule_key"]
                    if overrides:
                        new_j.update(overrides)
                    new_junctions.append(new_j)
                break

    # Create junctions for injected rules (no compound junction to expand).
    # Cushion penalty applies to credit-spread strategies (short strike present).
    if injections:
        _inject_junctions(new_junctions, injections)

    total_atomic = sum(len(a) for _, a in additions) + len(injections)
    log.info(f"Decomposition complete: {len(removals)} compounds → "
             f"{total_atomic} atomic rules ({len(injections)} injected fresh)")
    return new_rules, new_junctions


# Strategies that use cushion-based adjustments (credit spreads with a short strike)
_CUSHION_PENALTY_STRATEGIES = ["steady_paycheck", "weekly_grind"]


def _inject_junctions(junctions, injections):
    """Create junction rows for freshly injected rules (no compound to expand from)."""
    for rule, overrides in injections:
        key = rule["rule_key"]
        if not key.startswith("adj_cushion_penalty_"):
            continue
        for strat_key in _CUSHION_PENALTY_STRATEGIES:
            j = {
                "rule_key": key,
                "strategy_key": strat_key,
                "evaluation_order": 0,   # placeholder — OTA-684 sets proper ordering
                "stop_if_fail": False,
                "score_penalty": (overrides or {}).get("score_penalty"),
                "weight": None,
                "parameters": None,
                "enabled": True,
            }
            junctions.append(j)
    log.info(f"  Injected {len(_CUSHION_PENALTY_STRATEGIES) * len(injections)} "
             f"junctions for cushion penalty bands")


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

    # OTA-683: Decompose compound rules into atomic rules
    log.info("Decomposing compound rules into atomic rules (OTA-683)...")
    rules, junctions = decompose_compound_rules(rules, junctions)

    log.info(f"After decomposition: {len(rules)} rules, {len(junctions)} junctions")

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
