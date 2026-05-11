# All endpoints in this file must filter by user_id.
# See architecture-plan.md § 2 (Data Isolation Invariant).
# Cross-user attempts return 404 (not 403) to avoid leaking existence.

"""
Structured Markdown Export API (OTA-621)

Endpoints:
  GET  /api/v1/export/trade/{trade_key}.md     — Download trade candidate as markdown
  GET  /api/v1/export/position/{position_id}.md — Download position as markdown

Auth: Tier 1 (require_read) — GET endpoints, no CSRF needed.
"""

import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_read
from app.models.session import get_db
from app.models.database import Position, PositionAssessment

router = APIRouter(prefix="/export", tags=["export"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _sanitize_filename(s: str) -> str:
    """Make a string safe for use in a filename."""
    return re.sub(r'[^\w\-.]', '_', str(s))


def _fmt(val, decimals=2) -> str:
    """Format a numeric value to fixed decimals, no $ prefix."""
    if val is None:
        return "N/A"
    try:
        return f"{float(val):.{decimals}f}"
    except (ValueError, TypeError):
        return str(val)


def _fmt_pct(val) -> str:
    """Format a value as ##.00%."""
    if val is None:
        return "N/A"
    try:
        v = float(val)
        # If stored as decimal (0.47), convert to percentage
        if -1 < v < 1 and v != 0:
            v = v * 100
        return f"{v:.2f}%"
    except (ValueError, TypeError):
        return str(val)


def _fmt_date(val) -> str:
    """Format a date as mm-dd-yyyy."""
    if val is None:
        return "N/A"
    if isinstance(val, datetime):
        return val.strftime("%m-%d-%Y")
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        return dt.strftime("%m-%d-%Y")
    except (ValueError, TypeError):
        return str(val)


def _fmt_datetime(val) -> str:
    """Format a datetime as mm-dd-yyyy hh:mm UTC."""
    if val is None:
        return "N/A"
    if isinstance(val, datetime):
        return val.strftime("%m-%d-%Y %H:%M") + " UTC"
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        return dt.strftime("%m-%d-%Y %H:%M") + " UTC"
    except (ValueError, TypeError):
        return str(val)


def _display_structure(raw: str) -> str:
    """Convert raw structure enum to display label: 'bull_put_credit' → 'Bull Put Credit'."""
    if not raw:
        return "Unknown"
    return raw.replace("_", " ").title()


# ─── v2 spread_type ENUM ────────────────────────────────────────────────────

_VALID_SPREAD_TYPES = {
    "BULL_PUT_CREDIT",
    "BEAR_CALL_CREDIT",
    "BEAR_PUT_DEBIT",
    "BULL_CALL_DEBIT",
}


def format_spread_type_enum(spread_type: str | None) -> str:
    """Return the canonical uppercase ENUM string for a spread type.

    Accepts any casing or underscore/space variant. Returns one of the four
    canonical values or 'UNKNOWN' if the input cannot be mapped.
    """
    if not spread_type:
        return "UNKNOWN"
    normalized = spread_type.strip().upper().replace(" ", "_")
    if normalized in _VALID_SPREAD_TYPES:
        return normalized
    return "UNKNOWN"


def _strategy_display_name(strategy_key: str | None) -> str:
    """Map strategy_key slug to display name for export. Returns 'unassigned' for missing."""
    if not strategy_key:
        return "unassigned"
    _MAP = {
        "steady-paycheck": "Steady Paycheck",
        "weekly-grind": "Weekly Grind",
        "trend-rider": "Trend Rider",
        "lottery-ticket": "Lottery Ticket",
    }
    return _MAP.get(strategy_key, strategy_key.replace("-", " ").title())


def _fmt_signed_pnl(val) -> str:
    """Format P&L as signed ##.00 (always show sign, no $ prefix)."""
    if val is None:
        return "N/A"
    try:
        v = float(val)
        return f"{v:+.2f}"
    except (ValueError, TypeError):
        return str(val)


def _compute_dte(expiration_str: str | None, ref_date: datetime | None = None) -> int:
    """Compute DTE from expiration string. Raises HTTPException 422 if expiration is missing."""
    if not expiration_str:
        raise HTTPException(
            status_code=422,
            detail="Expiration date is required for active trades/positions but was missing.",
        )
    try:
        exp_dt = datetime.fromisoformat(str(expiration_str).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail=f"Cannot parse expiration date: {expiration_str}",
        )
    ref = ref_date or datetime.now(timezone.utc)
    # Ensure both are date-only for day computation
    if exp_dt.tzinfo is None:
        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
    return max(0, (exp_dt.date() - ref.date()).days)


_V2_FOOTER = (
    "*Generated by Options Analyzer for QA handoff via the "
    "`options-analyzer-qa` skill on claude.ai. Schema v2.0. "
    "Field labels are pinned to the v2 parse contract.*"
)


def _safe_json(raw) -> dict | list | None:
    """Parse a JSON string or return as-is if already parsed."""
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _build_legs_table(legs: list) -> str:
    """Build a markdown table of option legs."""
    if not legs:
        return ""
    lines = [
        "### Legs",
        "",
        "| Side | Type | Strike | Expiration | Qty | Bid | Ask | Delta | IV |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for leg in legs:
        lines.append(
            f"| {leg.get('side', '—')} "
            f"| {leg.get('option_type', '—')} "
            f"| {_fmt(leg.get('strike'))} "
            f"| {_fmt_date(leg.get('expiration'))} "
            f"| {leg.get('qty', 1)} "
            f"| {_fmt(leg.get('bid'))} "
            f"| {_fmt(leg.get('ask'))} "
            f"| {_fmt(leg.get('delta'), 4)} "
            f"| {_fmt_pct(leg.get('iv'))} |"
        )
    return "\n".join(lines)


def _build_probability_table(matrix) -> str:
    """Build probability matrix markdown table."""
    if not matrix:
        return ""
    # Handle both list-of-dicts and nested object formats
    rows = []
    if isinstance(matrix, list):
        rows = matrix
    elif isinstance(matrix, dict):
        # Could be { scenarios: [...] } or similar
        rows = matrix.get("scenarios", [])
        if not rows:
            return ""

    if not rows:
        return ""

    lines = [
        "## Probability matrix",
        "",
        "| Scenario | Probability | P&L |",
        "|---|---|---|",
    ]
    for row in rows:
        name = row.get("name", row.get("scenario", "—"))
        prob = _fmt_pct(row.get("probability", row.get("prob")))
        pnl = _fmt(row.get("pnl", row.get("p_and_l")))
        lines.append(f"| {name} | {prob} | {pnl} |")
    return "\n".join(lines)


# ─── Trade candidate export ──────────────────────────────────────────────────

def _build_trade_markdown(candidate) -> tuple[str, str]:
    """
    Build markdown body and filename from a trade_candidates row.
    Returns (markdown_body, filename).
    """
    legs = _safe_json(candidate.legs) or []
    net = _safe_json(candidate.net_metrics) or {}
    evaluation = _safe_json(candidate.claude_evaluation) or {}
    components = _safe_json(candidate.pipeline_components) or {}

    symbol = candidate.symbol
    spread_type_enum = format_spread_type_enum(candidate.structure)

    # Build strikes label
    strikes_parts = []
    for leg in legs:
        s = leg.get("strike")
        if s is not None:
            strikes_parts.append(str(s))
    strikes_label = "/".join(strikes_parts) if strikes_parts else "single"

    # Expiration from first leg
    expiration = legs[0].get("expiration") if legs else None

    # Compute DTE — fail-fast if expiration missing
    dte = _compute_dte(expiration)

    verdict = evaluation.get("verdict", "N/A")
    score = evaluation.get("score")
    claude_read = evaluation.get("claude_read", "")
    key_risks = evaluation.get("key_risks", [])
    thesis_invalidators = evaluation.get("thesis_invalidators", [])

    now_iso = datetime.now(timezone.utc).isoformat()
    strategy_profile = _strategy_display_name(getattr(candidate, "scan_strategy_key", None))

    lines = [
        f"# Trade Candidate — {symbol}",
        "",
        f"**Exported:** {now_iso}",
        f"**Schema version:** 2.0",
        f"**Strategy profile:** {strategy_profile}",
        f"**Trade key:** {candidate.trade_key}",
        f"**Current P&L:** N/A",
        "",
        "## Trade structure",
        "",
        f"- **Ticker:** {symbol}",
        f"- **Spread type:** {spread_type_enum}",
        f"- **Strikes:** {strikes_label}",
        f"- **Expiration:** {_fmt_date(expiration)}",
        f"- **DTE:** {dte}",
        f"- **Quantity:** {legs[0].get('qty', 1) if legs else 1} contracts",
    ]

    # Legs table
    legs_table = _build_legs_table(legs)
    if legs_table:
        lines.append("")
        lines.append(legs_table)

    # Net metrics
    breakeven = net.get("breakeven")
    if isinstance(breakeven, list):
        breakeven_str = f"[{', '.join(_fmt(b) for b in breakeven)}]"
    else:
        breakeven_str = _fmt(breakeven)

    lines.extend([
        "",
        "## Net metrics",
        "",
        f"- **Entry price:** {_fmt(net.get('entry_price'))}",
        f"- **Max profit:** {_fmt(net.get('max_profit'))}",
        f"- **Max loss:** {_fmt(net.get('max_loss'))}",
        f"- **Breakeven:** {breakeven_str}",
        f"- **Net bid-ask:** {_fmt(net.get('net_bid_ask'))}",
        f"- **Underlying spot:** {_fmt(candidate.underlying_spot)}",
        f"- **IV Rank:** {_fmt_pct(net.get('iv_rank'))}",
        f"- **Scenario-weighted EV:** {_fmt(net.get('scenario_weighted_ev'))}",
        f"- **Probability of profit:** {_fmt_pct(net.get('prob_of_profit'))}",
    ])

    # Verdict
    lines.extend([
        "",
        f"## App verdict: {verdict}",
        "",
        f"**App score:** {_fmt(score)}",
    ])

    # Score breakdown (only if pipeline_components present)
    if components:
        lines.extend(["", "### App score breakdown", ""])
        for comp_name, comp_val in components.items():
            lines.append(f"- {comp_name}: {_fmt(comp_val) if isinstance(comp_val, (int, float)) else comp_val}")

    # Claude's Read
    if claude_read:
        lines.extend([
            "",
            "### App narrative (\"Claude's Read\")",
            "",
            claude_read,
        ])

    # Thesis invalidators
    if thesis_invalidators:
        lines.extend(["", "### This Trade Is Wrong If", ""])
        for inv in thesis_invalidators:
            lines.append(f"- {inv}")

    # Key risks
    if key_risks:
        lines.extend(["", "### Key risks", ""])
        for risk in key_risks:
            lines.append(f"- {risk}")

    # Probability matrix
    prob_matrix = net.get("probability_matrix")
    if prob_matrix:
        prob_table = _build_probability_table(prob_matrix)
        if prob_table:
            lines.extend(["", prob_table])

    # Footer
    lines.extend([
        "",
        "---",
        "",
        _V2_FOOTER,
    ])

    filename = _sanitize_filename(f"{symbol}_{strikes_label}_{candidate.structure}") + ".md"
    return "\n".join(lines), filename


# ─── Position export ─────────────────────────────────────────────────────────

def _build_position_markdown(position: Position, latest_assessment) -> tuple[str, str]:
    """
    Build markdown body and filename from a positions row + latest assessment.
    Returns (markdown_body, filename).
    """
    ts = _safe_json(position.trade_structure) or {}
    legs = ts.get("legs", [])
    verdict_data = _safe_json(position.claude_verdict) or {}
    exit_levels = _safe_json(position.claude_exit_levels) or {}

    symbol = position.symbol
    structure = ts.get("structure", ts.get("spread_structure", ""))
    trade_type = ts.get("trade_type", structure)
    spread_type_enum = format_spread_type_enum(trade_type or structure)

    # Build strikes label
    short_strike = ts.get("short_strike")
    long_strike = ts.get("long_strike")
    if short_strike and long_strike:
        strikes_label = f"{short_strike}/{long_strike}"
    elif short_strike:
        strikes_label = str(short_strike)
    elif long_strike:
        strikes_label = str(long_strike)
    else:
        strikes_parts = [str(leg.get("strike")) for leg in legs if leg.get("strike") is not None]
        strikes_label = "/".join(strikes_parts) if strikes_parts else "single"

    expiration = ts.get("expiration")
    if not expiration and legs:
        expiration = legs[0].get("expiration")

    # Compute DTE — fail-fast if expiration missing
    dte = _compute_dte(expiration)

    # Status mapping for display
    status_display = {
        "FOLLOWING": "FOLLOWING",
        "LIVE": "TAKEN",
        "CLOSED": "CLOSED",
        "ARCHIVED": "CLOSED",
    }.get(position.status, position.status)

    now_iso = datetime.now(timezone.utc).isoformat()
    strategy_profile = _strategy_display_name(position.strategy_key)

    lines = [
        f"# Position — {symbol} (id {position.position_id})",
        "",
        f"**Exported:** {now_iso}",
        f"**Schema version:** 2.0",
        f"**Strategy profile:** {strategy_profile}",
        f"**Status:** {status_display}",
        f"**Followed at:** {_fmt_date(position.entry_date)}",
        f"**Last monitored:** {_fmt_datetime(position.last_monitored_at)}",
        f"**Current price:** {_fmt(position.current_price)}",
        f"**Current P&L:** {_fmt_signed_pnl(position.current_pnl)}",
    ]

    lines.extend([
        "",
        "## Trade structure",
        "",
        f"- **Ticker:** {symbol}",
        f"- **Spread type:** {spread_type_enum}",
        f"- **Strikes:** {strikes_label}",
        f"- **Expiration:** {_fmt_date(expiration)}",
        f"- **DTE:** {dte}",
        f"- **Quantity:** {legs[0].get('qty', 1) if legs else 1} contracts",
    ])

    # Legs table
    legs_table = _build_legs_table(legs)
    if legs_table:
        lines.append("")
        lines.append(legs_table)

    # Net metrics from trade_structure or position fields
    entry_price = position.entry_price
    max_profit = ts.get("max_profit")
    max_loss = ts.get("max_loss")
    breakeven = ts.get("breakeven")

    if isinstance(breakeven, list):
        breakeven_str = f"[{', '.join(_fmt(b) for b in breakeven)}]"
    else:
        breakeven_str = _fmt(breakeven)

    lines.extend([
        "",
        "## Net metrics",
        "",
        f"- **Entry price:** {_fmt(entry_price)}",
        f"- **Max profit:** {_fmt(max_profit)}",
        f"- **Max loss:** {_fmt(max_loss)}",
        f"- **Breakeven:** {breakeven_str}",
        f"- **Underlying spot:** {_fmt(position.entry_underlying_price)}",
        f"- **IV Rank:** {_fmt_pct(position.entry_iv_rank)}",
    ])

    # Use latest assessment values if available, otherwise fall back to position-level
    verdict = "N/A"
    score = None
    claude_read = ""
    key_risks = []
    thesis_invalidators = []

    if latest_assessment:
        verdict = latest_assessment.verdict or "N/A"
        score = latest_assessment.score
        claude_read = latest_assessment.claude_read or ""
    elif verdict_data:
        verdict = verdict_data.get("verdict", "N/A")
        score = verdict_data.get("score", position.claude_score)
        claude_read = verdict_data.get("claude_read", "")
        key_risks = verdict_data.get("key_risks", [])
        thesis_invalidators = verdict_data.get("thesis_invalidators", [])

    if score is None:
        score = position.claude_score

    # Verdict section
    lines.extend([
        "",
        f"## App verdict: {verdict}",
        "",
        f"**App score:** {_fmt(score)}",
    ])

    # Claude's Read
    if claude_read:
        lines.extend([
            "",
            "### App narrative (\"Claude's Read\")",
            "",
            claude_read,
        ])

    # Thesis invalidators
    if thesis_invalidators:
        lines.extend(["", "### This Trade Is Wrong If", ""])
        for inv in thesis_invalidators:
            lines.append(f"- {inv}")

    # Key risks
    if key_risks:
        lines.extend(["", "### Key risks", ""])
        for risk in key_risks:
            lines.append(f"- {risk}")

    # Probability matrix
    prob_matrix = _safe_json(position.claude_probability_matrix)
    if prob_matrix:
        prob_table = _build_probability_table(prob_matrix)
        if prob_table:
            lines.extend(["", prob_table])

    # Footer
    lines.extend([
        "",
        "---",
        "",
        _V2_FOOTER,
    ])

    filename = _sanitize_filename(f"{symbol}_position_{position.position_id}") + ".md"
    return "\n".join(lines), filename


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/trade/{trade_key}.md")
async def export_trade_md(
    trade_key: str,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Download a trade candidate as structured markdown for QA handoff."""
    # Import here to avoid circular import and to tolerate OTA-624 not yet shipped
    try:
        from app.models.database import TradeCandidate
    except ImportError:
        raise HTTPException(status_code=501, detail="Trade candidate persistence not yet available (OTA-624)")

    result = await db.execute(
        select(TradeCandidate).where(
            and_(
                TradeCandidate.trade_key == trade_key,
                TradeCandidate.user_id == user["sub"],
            )
        )
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Trade candidate not found")

    body, filename = _build_trade_markdown(candidate)
    return Response(
        content=body,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/position/{position_id}.md")
async def export_position_md(
    position_id: str,
    user: dict = Depends(require_read),
    db: AsyncSession = Depends(get_db),
):
    """Download a position as structured markdown for QA handoff."""
    # Fetch position filtered by user_id (Data Isolation Invariant)
    result = await db.execute(
        select(Position).where(
            and_(
                Position.position_id == position_id,
                Position.user_id == user["sub"],
            )
        )
    )
    position = result.scalar_one_or_none()
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    # Get latest assessment
    asm_result = await db.execute(
        select(PositionAssessment)
        .where(PositionAssessment.position_id == position_id)
        .order_by(PositionAssessment.created_at.desc())
        .limit(1)
    )
    latest_assessment = asm_result.scalar_one_or_none()

    body, filename = _build_position_markdown(position, latest_assessment)
    return Response(
        content=body,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
