# All endpoints in this file must filter by user_id.
# See architecture-plan.md § 2 (Data Isolation Invariant).
# Cross-user attempts return 404 (not 403) to avoid leaking existence.

"""
Structured Markdown Export API (OTA-621, OTA-641, OTA-642)

Endpoints:
  GET  /api/v1/export/trade/{trade_key}.md     — Download trade candidate as markdown
  GET  /api/v1/export/position/{position_id}.md — Download position as markdown

Auth: Tier 1 (require_read) — GET endpoints, no CSRF needed.
"""

import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_read
from app.core.config import settings
from app.models.session import get_db
from app.models.database import Position, PositionAssessment, OptionChainSnapshot
from app.providers.factory import ProviderRegistry, CONTEXT_SOURCE_REGISTRY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["export"])

# ─── Provider registry (set at startup via init_export_routes) ────────────────

_provider_registry: Optional[ProviderRegistry] = None


def init_export_routes(registry: ProviderRegistry):
    global _provider_registry
    _provider_registry = registry


def _get_provider():
    if _provider_registry is None:
        raise RuntimeError("Provider registry not initialized for export routes")
    token_mgr = getattr(_provider_registry, '_schwab_token_manager', None)
    if token_mgr and token_mgr.get_status().get('connected'):
        return _provider_registry.get_market_data("schwab")
    return _provider_registry.get_market_data(settings.default_market_data_provider)


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


# ─── Technicals helpers ──────────────────────────────────────────────────────


def _compute_sma(prices: list[float], period: int) -> Optional[float]:
    """Simple moving average over the last `period` closing prices."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def _compute_atr(bars: list[dict], period: int = 14) -> Optional[float]:
    """Average True Range (Wilder smoothing) from OHLC bars.

    Each bar must have 'high', 'low', 'close' keys.
    """
    if len(bars) < period + 1:
        return None
    # Compute true ranges starting from the second bar
    true_ranges = []
    for i in range(1, len(bars)):
        h = bars[i]["high"]
        l = bars[i]["low"]
        prev_c = bars[i - 1]["close"]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        true_ranges.append(tr)
    if len(true_ranges) < period:
        return None
    # Wilder smoothing: first ATR is simple average, then EMA-like
    atr = sum(true_ranges[:period]) / period
    for tr in true_ranges[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def sma_alignment_narrative(spot: float, sma8: float, sma21: float, sma50: float) -> str:
    """Deterministic SMA alignment narrative per business-rules.md Technicals Classification."""
    bullish_stack = (sma8 > sma21 > sma50) and (spot > sma8)
    bearish_stack = (sma8 < sma21 < sma50) and (spot < sma8)
    max_spread_pct = (max(sma8, sma21, sma50) - min(sma8, sma21, sma50)) / spot * 100
    clustered = max_spread_pct < 0.5

    if bullish_stack:
        return "bullish stack — price above 8 > 21 > 50 SMA."
    if bearish_stack:
        return "bearish stack — price below 8 < 21 < 50 SMA."
    if clustered:
        return f"clustered — all three SMAs within {max_spread_pct:.1f}% of spot. Trend undefined."
    # mixed — describe where price sits relative to each SMA
    above = [name for name, val in [("8", sma8), ("21", sma21), ("50", sma50)] if spot > val]
    below = [name for name, val in [("8", sma8), ("21", sma21), ("50", sma50)] if spot <= val]
    return f"mixed — price below {' and '.join(below)}, above {' and '.join(above)}. Not a clean bullish or bearish stack."


def distance_from_50d_narrative(spot: float, sma_50: float) -> str:
    """Distance from 50-day SMA with extension label per business-rules.md."""
    dist_pct = (spot - sma_50) / sma_50 * 100
    if abs(dist_pct) < 2.0:
        tail = "within range, not extended"
    elif abs(dist_pct) < 5.0:
        tail = "somewhat extended"
    else:
        tail = "extended"
    sign = "+" if dist_pct >= 0 else ""
    # Use minus sign (−) for negative per the v2 sample
    formatted = f"{sign}{dist_pct:.1f}%"
    if dist_pct < 0:
        formatted = f"\u2212{abs(dist_pct):.1f}%"
    return f"{formatted} ({tail})"


async def _build_market_context_section(
    underlying_ivr_pct: float | None,
) -> str:
    """Build ## Market context section (VIX, SPY, QQQ, regime note).

    All quote/history reads go through _get_provider() — never hardcoded.
    # NOTE: $ prefix is retained on SPY and QQQ spot values in this block
    # per the v2 QA handoff sample convention.  This is an intentional override
    # of the house style "no $ in UI" rule — the export MD is consumed by a QA
    # skill, not displayed in the app UI.  (OTA-640)
    """
    from app.services.market_context import (
        get_vix_series, vix_percentile_52w, five_day_trend,
        distance_from_50d, regime_note, VIX_API_SYMBOL,
    )
    try:
        provider = _get_provider()

        # Fetch VIX quote + history in parallel-ish (sequential for simplicity)
        vix_quote = await provider.get_quote(VIX_API_SYMBOL)
        vix_price = float(vix_quote.get("price", 0)) if vix_quote else 0.0
        vix_series = await get_vix_series(provider, months=12)
        n_days = len(vix_series)

        if n_days > 0:
            vix_pctl = vix_percentile_52w(vix_price, vix_series)
            if n_days >= 252:
                vix_pctl_str = f"{vix_pctl}%"
            else:
                # Windowed-percentile fallback per OTA-640 Phase 1 rule 3
                vix_pctl_str = f"{vix_pctl}% based on {n_days} days"
        else:
            vix_pctl_str = "N/A"

        # SPY and QQQ: spot + candles for trend and SMA
        spy_candles = await provider.get_price_history("SPY", num_periods=3)
        qqq_candles = await provider.get_price_history("QQQ", num_periods=3)

        spy_spot = spy_candles[-1]["close"] if spy_candles else 0.0
        qqq_spot = qqq_candles[-1]["close"] if qqq_candles else 0.0

        spy_trend_label, spy_trend_pct = five_day_trend(spy_candles)
        qqq_trend_label, qqq_trend_pct = five_day_trend(qqq_candles)

        spy_dist, spy_dir = distance_from_50d(spy_spot, spy_candles)
        qqq_dist, qqq_dir = distance_from_50d(qqq_spot, qqq_candles)

        # Format signed trend pcts with Unicode minus
        def _trend_fmt(pct: float) -> str:
            if pct < 0:
                return f"\u2212{abs(pct):.1f}%"
            elif pct > 0:
                return f"+{pct:.1f}%"
            return f"{pct:.1f}%"

        def _dist_fmt(pct: float) -> str:
            if pct < 0:
                return f"\u2212{abs(pct):.1f}%"
            elif pct > 0:
                return f"+{pct:.1f}%"
            return f"{pct:.1f}%"

        # Regime note — deterministic, no Claude call (cost guardrail)
        ivr = float(underlying_ivr_pct) if underlying_ivr_pct is not None else 50.0
        regime = regime_note(vix_price, ivr)

        lines = [
            "## Market context",
            "",
            f"- **VIX:** {vix_price:.2f} (52w percentile: {vix_pctl_str})",
            f"- **SPY:** ${spy_spot:.2f} \u2014 5d trend: {spy_trend_label} ({_trend_fmt(spy_trend_pct)}) \u2014 vs 50d SMA: {_dist_fmt(spy_dist)} ({spy_dir})",
            f"- **QQQ:** ${qqq_spot:.2f} \u2014 5d trend: {qqq_trend_label} ({_trend_fmt(qqq_trend_pct)}) \u2014 vs 50d SMA: {_dist_fmt(qqq_dist)} ({qqq_dir})",
            f"- **Regime note:** {regime}",
        ]
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Market context section failed: {e}")
        return ""


async def _build_technicals_section(symbol: str) -> str:
    """Build ## Technicals (underlying) section from live daily bars.

    Uses _get_provider() for daily bar data. Returns empty string on failure.
    # NOTE: $ prefix is retained on SMA and ATR values in this block per the
    # v2 parse contract (QQQ sample). This is an intentional override of the
    # house style "no $ in UI" rule — the export MD is consumed by a QA skill,
    # not displayed in the app UI.
    """
    try:
        provider = _get_provider()
        # get_candles returns OHLC bars — need high/low/close for ATR
        bars = await provider.get_candles(symbol, range_days=90)
        if not bars or len(bars) < 50:
            logger.warning(f"Technicals: insufficient bars for {symbol} (got {len(bars)})")
            return ""

        closes = [b["close"] for b in bars]
        spot = closes[-1]

        sma8 = _compute_sma(closes, 8)
        sma21 = _compute_sma(closes, 21)
        sma50 = _compute_sma(closes, 50)
        atr14 = _compute_atr(bars, 14)

        if sma8 is None or sma21 is None or sma50 is None or atr14 is None:
            logger.warning(f"Technicals: could not compute indicators for {symbol}")
            return ""

        alignment = sma_alignment_narrative(spot, sma8, sma21, sma50)
        dist_50d = distance_from_50d_narrative(spot, sma50)

        lines = [
            "## Technicals (underlying)",
            "",
            f"- **SMA 8:** ${sma8:.2f}",
            f"- **SMA 21:** ${sma21:.2f}",
            f"- **SMA 50:** ${sma50:.2f}",
            f"- **ATR 14:** ${atr14:.2f}",
            f"- **SMA alignment:** {alignment}",
            f"- **Distance from 50d:** {dist_50d}",
        ]
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Technicals section failed for {symbol}: {e}")
        return ""


async def _build_earnings_section(
    symbol: str,
    expiration_str: Optional[str],
    db: AsyncSession,
) -> str:
    """Build ## Earnings section with ETF short-circuit and Finnhub provider gating.

    No Claude API call — all values are read or short-circuited (cost guardrail).
    """
    try:
        # Step 1: Check if ETF via symbol_reference
        result = await db.execute(
            text("SELECT asset_type FROM symbol_reference WHERE symbol = :sym"),
            {"sym": symbol.upper()},
        )
        row = result.fetchone()

        is_etf = False
        if row is None:
            # Symbol not in reference — treat as non-ETF, provider-gated
            is_etf = False
        else:
            asset_type = row[0]
            # Non-equity, non-ADR → ETF short-circuit (same logic as mcp_routes)
            is_etf = asset_type not in ("Equity", "ADR")

        if is_etf:
            # ETF short-circuit — never call earnings provider for ETFs
            lines = [
                "## Earnings",
                "",
                f"- **Next earnings:** N/A ({symbol.upper()} is an ETF)",
                "- **Days to earnings:** N/A",
                "- **Earnings in expiration window:** No",
            ]
            return "\n".join(lines)

        # Step 2: Check if Finnhub provider is active
        source = CONTEXT_SOURCE_REGISTRY.get("finnhub_earnings")
        if source is None:
            # Provider not registered — emit unavailable (not N/A)
            lines = [
                "## Earnings",
                "",
                "- **Next earnings:** unavailable (provider in flight under OTA-508)",
                "- **Days to earnings:** unavailable",
                "- **Earnings in expiration window:** unknown",
            ]
            return "\n".join(lines)

        # Step 3: Fetch earnings from Finnhub
        raw = await source.fetch(symbol.upper())
        normalized = source.normalize(raw)
        earnings_date_str = normalized.get("next_earnings_date")

        if not earnings_date_str:
            # Provider active but no data
            notes = (normalized.get("meta") or {}).get("notes", "")
            lines = [
                "## Earnings",
                "",
                "- **Next earnings:** unavailable (no upcoming earnings found)",
                "- **Days to earnings:** unavailable",
                "- **Earnings in expiration window:** unknown",
            ]
            return "\n".join(lines)

        # Compute days and window check
        earnings_date = date.fromisoformat(earnings_date_str)
        today = date.today()
        days_to = (earnings_date - today).days

        # Format date as mm-dd-yyyy per house style
        earnings_display = datetime.strptime(earnings_date_str, "%Y-%m-%d").strftime("%m-%d-%Y")

        # Check if earnings fall within expiration window
        in_window = "No"
        if expiration_str:
            try:
                exp_dt = datetime.fromisoformat(str(expiration_str).replace("Z", "+00:00"))
                if earnings_date <= exp_dt.date():
                    in_window = "Yes"
            except (ValueError, TypeError):
                in_window = "unknown"

        lines = [
            "## Earnings",
            "",
            f"- **Next earnings:** {earnings_display}",
            f"- **Days to earnings:** {days_to}",
            f"- **Earnings in expiration window:** {in_window}",
        ]
        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Earnings section failed for {symbol}: {e}")
        lines = [
            "## Earnings",
            "",
            "- **Next earnings:** unavailable (error fetching earnings data)",
            "- **Days to earnings:** unavailable",
            "- **Earnings in expiration window:** unknown",
        ]
        return "\n".join(lines)


# ─── Options chain helpers (OTA-642) ─────────────────────────────────────────


def select_strikes_around_legs(
    all_strikes: list[float], leg_strikes: list[float], n: int = 3,
) -> list[float]:
    """Return sorted deduplicated strikes within ±n positions of each leg strike.

    For each leg strike, takes the strike itself plus up to n strikes above and
    n strikes below from the sorted unique strike list. Unions across legs.
    """
    sorted_strikes = sorted(set(all_strikes))
    if not sorted_strikes or not leg_strikes:
        return sorted_strikes

    selected = set()
    for ls in leg_strikes:
        # Find position of leg strike in sorted list (or closest)
        try:
            idx = sorted_strikes.index(ls)
        except ValueError:
            # Leg strike not in snapshot — find closest
            idx = min(range(len(sorted_strikes)), key=lambda i: abs(sorted_strikes[i] - ls))
        lo = max(0, idx - n)
        hi = min(len(sorted_strikes), idx + n + 1)
        for i in range(lo, hi):
            selected.add(sorted_strikes[i])
        # Always include the leg strike itself
        selected.add(ls)

    return sorted(selected)


def select_calls_near_spot(
    call_strikes: list[float], spot: float, n: int = 3,
) -> list[float]:
    """Return n strikes straddling spot from a sorted unique list of call strikes.

    Picks the strike closest to spot (lower strike wins ties), then extends to
    fill n total (one below, one above, or as many as available).
    """
    sorted_strikes = sorted(set(call_strikes))
    if not sorted_strikes:
        return []

    # Find closest-to-spot index (lower wins ties)
    closest_idx = 0
    min_dist = abs(sorted_strikes[0] - spot)
    for i, s in enumerate(sorted_strikes):
        d = abs(s - spot)
        if d < min_dist or (d == min_dist and s < sorted_strikes[closest_idx]):
            min_dist = d
            closest_idx = i

    # Take n strikes centred around closest_idx
    half = (n - 1) // 2
    lo = max(0, closest_idx - half)
    hi = lo + n
    if hi > len(sorted_strikes):
        hi = len(sorted_strikes)
        lo = max(0, hi - n)

    return sorted_strikes[lo:hi]


def _build_chain_puts_table(
    contracts: list[dict],
    selected_strikes: list[float],
    leg_strikes: set[float],
) -> str:
    """Build the puts table for the ±3 strikes chain section.

    Leg rows are bolded. No $ prefix on any value.
    """
    # Filter to puts at selected strikes
    puts = {}
    for c in contracts:
        opt_type = str(c.get("option_type", c.get("type", ""))).lower()
        if opt_type != "put":
            continue
        strike = float(c.get("strike", 0))
        if strike in selected_strikes or any(abs(strike - s) < 0.001 for s in selected_strikes):
            puts[strike] = c

    if not puts:
        return ""

    lines = [
        "### Puts",
        "",
        "| Strike | Bid | Ask | Mid | Delta | IV | Volume | OI |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for strike in sorted(selected_strikes):
        c = puts.get(strike)
        if c is None:
            # Try fuzzy match
            for k, v in puts.items():
                if abs(k - strike) < 0.001:
                    c = v
                    break
        if c is None:
            continue

        bid = c.get("bid")
        ask = c.get("ask")
        mid = ((float(bid) + float(ask)) / 2) if bid is not None and ask is not None else None
        delta = c.get("delta")
        iv = c.get("implied_volatility", c.get("iv"))
        volume = c.get("volume")
        oi = c.get("open_interest")

        # Format delta with sign and Unicode minus
        delta_str = "N/A"
        if delta is not None:
            delta_str = _signed(float(delta))

        iv_str = _fmt_iv_1d(iv)
        vol_str = _fmt_thousands(volume)
        oi_str = _fmt_thousands(oi)

        is_leg = any(abs(strike - ls) < 0.001 for ls in leg_strikes)
        if is_leg:
            row = (
                f"| **{_fmt(strike)}** "
                f"| **{_fmt(bid)}** "
                f"| **{_fmt(ask)}** "
                f"| **{_fmt(mid)}** "
                f"| **{delta_str}** "
                f"| **{iv_str}** "
                f"| **{vol_str}** "
                f"| **{oi_str}** |"
            )
        else:
            row = (
                f"| {_fmt(strike)} "
                f"| {_fmt(bid)} "
                f"| {_fmt(ask)} "
                f"| {_fmt(mid)} "
                f"| {delta_str} "
                f"| {iv_str} "
                f"| {vol_str} "
                f"| {oi_str} |"
            )
        lines.append(row)

    lines.extend(["", "Trade legs **bolded**."])
    return "\n".join(lines)


def _build_chain_calls_table(
    contracts: list[dict],
    spot: float,
) -> str:
    """Build the Calls (for context only) table — 3 strikes near spot.

    No Volume or OI. No $ prefix.
    """
    # Collect unique call strikes
    call_strikes = []
    calls_by_strike = {}
    for c in contracts:
        opt_type = str(c.get("option_type", c.get("type", ""))).lower()
        if opt_type != "call":
            continue
        strike = float(c.get("strike", 0))
        call_strikes.append(strike)
        calls_by_strike[strike] = c

    if not call_strikes:
        return ""

    selected = select_calls_near_spot(call_strikes, spot)
    if not selected:
        return ""

    lines = [
        "### Calls (for context only)",
        "",
        "| Strike | Bid | Ask | Mid | Delta | IV |",
        "|---|---|---|---|---|---|",
    ]

    for strike in selected:
        c = calls_by_strike.get(strike)
        if c is None:
            continue

        bid = c.get("bid")
        ask = c.get("ask")
        mid = ((float(bid) + float(ask)) / 2) if bid is not None and ask is not None else None
        delta = c.get("delta")
        iv = c.get("implied_volatility", c.get("iv"))

        delta_str = "N/A"
        if delta is not None:
            delta_str = _signed(float(delta))

        lines.append(
            f"| {_fmt(strike)} "
            f"| {_fmt(bid)} "
            f"| {_fmt(ask)} "
            f"| {_fmt(mid)} "
            f"| {delta_str} "
            f"| {_fmt_iv_1d(iv)} |"
        )

    return "\n".join(lines)


def _build_options_chain_section(
    contracts: list[dict],
    legs: list[dict],
    symbol: str,
    expiration_str: str | None,
    underlying_spot: float | None,
) -> str:
    """Build the Options chain section for trade exports (single render).

    Renders puts ±3 strikes around legs + calls near spot.
    """
    if not contracts:
        return ""

    leg_strikes = set()
    for leg in legs:
        s = leg.get("strike")
        if s is not None:
            leg_strikes.add(float(s))

    # Get all put strikes from snapshot
    put_strikes = sorted(set(
        float(c.get("strike", 0))
        for c in contracts
        if str(c.get("option_type", c.get("type", ""))).lower() == "put"
    ))

    selected = select_strikes_around_legs(put_strikes, list(leg_strikes))

    exp_display = _fmt_date(expiration_str) if expiration_str else "N/A"
    spot = float(underlying_spot) if underlying_spot else 0.0

    lines = [
        "## Options chain \u2014 \u00b13 strikes around trade legs",
        "",
        f"{symbol} options expiring **{exp_display}** (same as trade).",
    ]

    puts_table = _build_chain_puts_table(contracts, selected, leg_strikes)
    if puts_table:
        lines.extend(["", puts_table])

    calls_table = _build_chain_calls_table(contracts, spot)
    if calls_table:
        lines.extend(["", calls_table])

    return "\n".join(lines)


async def _build_options_chain_section_position(
    original_contracts: list[dict] | None,
    legs: list[dict],
    symbol: str,
    expiration_str: str | None,
    underlying_spot: float | None,
) -> str:
    """Build the Options chain section for position exports (dual render).

    Renders original snapshot + fresh chain pull. On fresh pull failure,
    renders 'unavailable (provider error)' instead of failing the export.
    """
    leg_strikes = set()
    for leg in legs:
        s = leg.get("strike")
        if s is not None:
            leg_strikes.add(float(s))

    exp_display = _fmt_date(expiration_str) if expiration_str else "N/A"
    spot = float(underlying_spot) if underlying_spot else 0.0

    lines = [
        "## Options chain \u2014 \u00b13 strikes around trade legs",
        "",
        f"{symbol} options expiring **{exp_display}** (same as trade).",
    ]

    # Original snapshot
    lines.extend(["", "### Original snapshot (at evaluation)"])
    if original_contracts:
        put_strikes = sorted(set(
            float(c.get("strike", 0))
            for c in original_contracts
            if str(c.get("option_type", c.get("type", ""))).lower() == "put"
        ))
        selected = select_strikes_around_legs(put_strikes, list(leg_strikes))
        puts_table = _build_chain_puts_table(original_contracts, selected, leg_strikes)
        if puts_table:
            lines.extend(["", puts_table])
        calls_table = _build_chain_calls_table(original_contracts, spot)
        if calls_table:
            lines.extend(["", calls_table])
    else:
        lines.extend(["", "Original snapshot: unavailable (no snapshot persisted with this position)."])

    # Current chain at export (fresh pull)
    lines.extend(["", "### Current chain at export"])
    try:
        provider = _get_provider()
        chain_data = await provider.get_chain(
            symbol=symbol.upper(),
            min_dte=0,
            max_dte=70,
            strike_range_pct=20.0,
        )
        current_contracts = chain_data.get("contracts", [])
        current_spot = chain_data.get("underlying_price", spot)

        if current_contracts:
            put_strikes = sorted(set(
                float(c.get("strike", 0))
                for c in current_contracts
                if str(c.get("option_type", c.get("type", ""))).lower() == "put"
            ))
            selected = select_strikes_around_legs(put_strikes, list(leg_strikes))
            puts_table = _build_chain_puts_table(current_contracts, selected, leg_strikes)
            if puts_table:
                lines.extend(["", puts_table])
            calls_table = _build_chain_calls_table(current_contracts, current_spot)
            if calls_table:
                lines.extend(["", calls_table])
        else:
            lines.extend(["", "Current chain at export: unavailable (empty chain returned)."])
    except Exception as e:
        logger.warning(f"Fresh chain pull failed for {symbol}: {e}")
        lines.extend(["", "Current chain at export: unavailable (provider error)."])

    return "\n".join(lines)


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


def _fmt_iv_1d(val) -> str:
    """Format IV as ##.#% (one decimal). Accepts decimal (0.28) or percentage (28.0)."""
    if val is None:
        return "N/A"
    try:
        v = float(val)
        if -1 < v < 1 and v != 0:
            v *= 100
        return f"{v:.1f}%"
    except (ValueError, TypeError):
        return str(val)


def _fmt_thousands(val) -> str:
    """Format an integer with thousands separators (e.g., 6,113)."""
    if val is None:
        return "N/A"
    try:
        return f"{int(val):,}"
    except (ValueError, TypeError):
        return str(val)


def _signed(val, decimals=2) -> str:
    """Format as signed value with Unicode minus (U+2212) for negative."""
    s = f"{val:+.{decimals}f}"
    if s.startswith("-"):
        s = "\u2212" + s[1:]
    return s


def _enrich_legs_from_chain(legs: list, chain_contracts: list) -> list:
    """Merge chain contract data (volume, OI, theta, vega, gamma) into legs.

    Matches by (strike, option_type, expiration). Raises HTTPException 422
    if a leg cannot be matched to a chain contract (fail-fast per OTA-621).
    """
    chain_lookup = {}
    for c in chain_contracts:
        strike = c.get("strike")
        opt_type = str(c.get("option_type", c.get("type", ""))).upper()
        exp = str(c.get("expiration", c.get("expiration_date", "")))[:10]
        if strike is not None:
            chain_lookup[(float(strike), opt_type, exp)] = c

    enriched = []
    for leg in legs:
        leg_copy = dict(leg)
        strike = leg.get("strike")
        opt_type = str(leg.get("option_type", "")).upper()
        exp = str(leg.get("expiration", ""))[:10]

        key = (float(strike), opt_type, exp) if strike is not None else None
        match = chain_lookup.get(key) if key else None

        if match is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Chain snapshot missing contract for leg: "
                    f"strike={strike}, type={opt_type}, expiration={exp}. "
                    f"Cannot build v2 export without matching chain data."
                ),
            )

        # Enrich with chain data (don't overwrite existing values)
        for field in ("volume", "open_interest", "theta", "vega", "gamma"):
            if leg_copy.get(field) is None and match.get(field) is not None:
                leg_copy[field] = match[field]

        enriched.append(leg_copy)
    return enriched


def _build_legs_table(legs: list) -> str:
    """Build a markdown table of option legs (v2 column set).

    Columns: Side · Type · Strike · Expiration · Qty · Bid · Ask · Mid · Delta · IV · Volume · OI.
    Mid is computed as (bid + ask) / 2, two decimals.
    IV is formatted ##.#% (one decimal).
    Volume and OI render as integers with thousands separators.
    """
    if not legs:
        return ""
    lines = [
        "### Legs",
        "",
        "| Side | Type | Strike | Expiration | Qty | Bid | Ask | Mid | Delta | IV | Volume | OI |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for leg in legs:
        bid = leg.get("bid")
        ask = leg.get("ask")
        mid = ((float(bid) + float(ask)) / 2) if bid is not None and ask is not None else None

        lines.append(
            f"| {leg.get('side', '\u2014')} "
            f"| {leg.get('option_type', '\u2014')} "
            f"| {_fmt(leg.get('strike'))} "
            f"| {_fmt_date(leg.get('expiration'))} "
            f"| {leg.get('qty', 1)} "
            f"| {_fmt(bid)} "
            f"| {_fmt(ask)} "
            f"| {_fmt(mid)} "
            f"| {_fmt(leg.get('delta'), 4)} "
            f"| {_fmt_iv_1d(leg.get('iv'))} "
            f"| {_fmt_thousands(leg.get('volume'))} "
            f"| {_fmt_thousands(leg.get('open_interest'))} |"
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


# ─── v2 Net metrics + Greeks builders (OTA-639) ──────────────────────────────

_CREDIT_SPREAD_TYPES = {"BULL_PUT_CREDIT", "BEAR_CALL_CREDIT"}
_BULL_SPREAD_TYPES = {"BULL_PUT_CREDIT", "BULL_CALL_DEBIT"}


def _extract_strikes(legs: list) -> tuple[float | None, float | None, int]:
    """Extract short_strike, long_strike, and qty from legs list."""
    short_strike = None
    long_strike = None
    qty = 1
    for leg in legs:
        side = str(leg.get("side", "")).upper()
        strike = leg.get("strike")
        if side in ("SELL", "SHORT"):
            short_strike = float(strike) if strike is not None else None
            qty = leg.get("qty", 1)
        elif side in ("BUY", "LONG"):
            long_strike = float(strike) if strike is not None else None
    return short_strike, long_strike, qty


def _build_net_metrics_v2(
    spread_type: str,
    legs: list,
    entry_price: float | None,
    underlying_spot: float | None,
    symbol: str = "underlying",
    breakeven: float | None = None,
    max_profit: float | None = None,
    max_loss: float | None = None,
) -> str:
    """Build the Net metrics block (v2 format).

    Branches on credit vs debit for the correct field set, labels,
    cushion formula, and narrative tail.

    # NOTE: $ prefix is used inside this block, overriding the general no-$
    # house rule. This matches the v2 QA handoff sample convention.
    # Do not "fix" this — it is intentional per OTA-639.
    """
    if spread_type not in _VALID_SPREAD_TYPES:
        # Fallback for unrecognized spread types — basic format
        return ""

    short_strike, long_strike, qty = _extract_strikes(legs)
    ep = float(entry_price) if entry_price is not None else 0.0
    spot = float(underlying_spot) if underlying_spot is not None else 0.0
    is_credit = spread_type in _CREDIT_SPREAD_TYPES
    is_bull = spread_type in _BULL_SPREAD_TYPES

    # Spread width
    width = abs(float(short_strike or 0) - float(long_strike or 0)) if short_strike and long_strike else 0.0

    # Total = per-contract * qty * 100 shares/contract
    total = ep * qty * 100
    pct_of_width = (ep / width * 100) if width > 0 else 0.0

    # Max profit / loss
    if max_profit is None:
        max_profit = ep if is_credit else (width - ep)
    mp = float(max_profit)
    mp_total = mp * qty * 100

    if max_loss is None:
        max_loss = (width - ep) if is_credit else ep
    ml = float(max_loss)
    ml_total = ml * qty * 100

    # Breakeven
    if breakeven is None:
        if is_credit:
            breakeven = (float(short_strike) - ep) if "PUT" in spread_type and short_strike else (
                (float(short_strike) + ep) if short_strike else 0.0
            )
        else:
            breakeven = (float(long_strike) - ep) if "PUT" in spread_type and long_strike else (
                (float(long_strike) + ep) if long_strike else 0.0
            )
    be = float(breakeven)

    rr = mp / ml if ml > 0 else 0.0

    # Max profit / loss narratives
    if is_credit:
        if is_bull:
            mp_narr = f"if {symbol} stays above ${_fmt(short_strike)} at expiration"
            ml_narr = f"if {symbol} drops below ${_fmt(long_strike)} at expiration"
        else:
            mp_narr = f"if {symbol} stays below ${_fmt(short_strike)} at expiration"
            ml_narr = f"if {symbol} rises above ${_fmt(long_strike)} at expiration"
    else:
        if is_bull:
            mp_narr = f"if {symbol} rises above ${_fmt(short_strike)} at expiration"
            ml_narr = f"if {symbol} drops below ${_fmt(long_strike)} at expiration"
        else:
            mp_narr = f"if {symbol} drops below ${_fmt(short_strike)} at expiration"
            ml_narr = f"if {symbol} stays above ${_fmt(long_strike)} at expiration"

    # NOTE: $ prefix used in this block only — overrides the general no-$ house
    # rule. This matches the v2 QA handoff sample convention. Do not remove. (OTA-639)
    lines = ["## Net metrics", ""]

    qty_label = f"{qty} contract{'s' if qty > 1 else ''}"
    if is_credit:
        lines.append(f"- **Entry credit:** ${ep:.2f} per contract (${total:.2f} for {qty_label})")
        lines.append(f"- **Spread width:** ${width:.2f}")
        lines.append(f"- **Credit % of width:** {pct_of_width:.1f}%")
    else:
        lines.append(f"- **Entry debit:** ${ep:.2f} per contract (${total:.2f} for {qty_label})")
        lines.append(f"- **Spread width:** ${width:.2f}")
        lines.append(f"- **Debit % of width:** {pct_of_width:.1f}%")

    lines.append(f"- **Max profit:** ${mp:.2f} per contract (${mp_total:.2f}) \u2014 {mp_narr}")
    lines.append(f"- **Max loss:** ${ml:.2f} per contract (${ml_total:.2f}) \u2014 {ml_narr}")
    lines.append(f"- **Breakeven:** ${be:.2f}")
    lines.append(f"- **R:R:** {rr:.2f} : 1")
    lines.append(f"- **Underlying spot:** ${spot:.2f}")

    # Cushion — credit vs debit split (OTA-639 semantic split)
    if is_credit:
        # Credit: cushion to short strike (direction-aware: positive = favorable)
        if is_bull:
            cushion = spot - float(short_strike or 0)
        else:
            cushion = float(short_strike or 0) - spot
        cushion_pct = (cushion / spot * 100) if spot > 0 else 0.0
        if cushion >= 0:
            lines.append(f"- **Cushion to short strike:** +${cushion:.2f} (+{cushion_pct:.2f}%)")
        else:
            lines.append(f"- **Cushion to short strike:** \u2212${abs(cushion):.2f} (\u2212{abs(cushion_pct):.2f}%)")
    else:
        # Debit: cushion to breakeven with narrative tail
        # Direction-aware: bull = spot - breakeven, bear = breakeven - spot
        if is_bull:
            cushion = spot - be
        else:
            cushion = be - spot
        cushion_pct = (cushion / spot * 100) if spot > 0 else 0.0

        spread_label = spread_type.lower().replace("_credit", "").replace("_debit", "").replace("_", " ")
        if cushion > 0:
            above_below = "ABOVE" if is_bull else "BELOW"
            tail = f"price is {above_below} breakeven at entry (favorable for {spread_label})"
            lines.append(f"- **Cushion to breakeven:** +${cushion:.2f} (+{cushion_pct:.2f}%) \u2014 {tail}")
        elif cushion < 0:
            above_below = "BELOW" if is_bull else "ABOVE"
            tail = f"price is {above_below} breakeven at entry (unfavorable for {spread_label})"
            lines.append(f"- **Cushion to breakeven:** \u2212${abs(cushion):.2f} (\u2212{abs(cushion_pct):.2f}%) \u2014 {tail}")
        else:
            lines.append(f"- **Cushion to breakeven:** $0.00 (0.00%) \u2014 price is AT breakeven at entry")

    return "\n".join(lines)


def _build_greeks_iv_section(legs: list, iv_rank: float | None) -> str:
    """Build the Greeks & IV (position-level) section.

    Net Greek formula (documented per OTA-639):
        net_g = \u03a3_legs (side_sign \u00d7 qty \u00d7 leg_g)
        where side_sign = +1 for long/BUY, \u22121 for short/SELL

    Spread mid IV: quantity-weighted mean of leg IVs:
        spread_mid_iv = \u03a3_legs (qty \u00d7 leg_iv) / \u03a3_legs (qty)
    """
    net_delta = 0.0
    net_theta = 0.0
    net_vega = 0.0
    net_gamma = 0.0
    total_iv_weighted = 0.0
    total_qty = 0

    for leg in legs:
        side = str(leg.get("side", "")).upper()
        side_sign = 1.0 if side in ("BUY", "LONG") else -1.0
        qty = leg.get("qty", 1)

        delta = float(leg.get("delta", 0) or 0)
        theta = float(leg.get("theta", 0) or 0)
        vega = float(leg.get("vega", 0) or 0)
        gamma = float(leg.get("gamma", 0) or 0)
        iv = float(leg.get("iv", 0) or 0)

        net_delta += side_sign * qty * delta
        net_theta += side_sign * qty * theta
        net_vega += side_sign * qty * vega
        net_gamma += side_sign * qty * gamma

        total_iv_weighted += qty * iv
        total_qty += qty

    spread_mid_iv = total_iv_weighted / total_qty if total_qty > 0 else 0.0
    # Convert to percentage if stored as decimal
    if -1 < spread_mid_iv < 1 and spread_mid_iv != 0:
        spread_mid_iv *= 100

    iv_rank_display = "N/A"
    if iv_rank is not None:
        iv_val = float(iv_rank)
        if -1 < iv_val < 1 and iv_val != 0:
            iv_val *= 100
        iv_rank_display = f"{iv_val:.1f}%"

    lines = [
        "## Greeks & IV (position-level)",
        "",
        f"- **Net delta:** {_signed(net_delta)}",
        f"- **Net theta:** {_signed(net_theta)}",
        f"- **Net vega:** {_signed(net_vega)}",
        f"- **Net gamma:** {_signed(net_gamma, 3)}",
        f"- **IV Rank (underlying):** {iv_rank_display}",
        f"- **Spread mid IV:** {spread_mid_iv:.1f}%",
    ]
    return "\n".join(lines)


# ─── Trade candidate export ──────────────────────────────────────────────────

async def _build_trade_markdown(
    candidate, db: AsyncSession, chain_contracts: list | None = None,
) -> tuple[str, str]:
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

    # Enrich legs with chain data (volume, OI, theta, vega, gamma) if available
    if chain_contracts:
        legs = _enrich_legs_from_chain(legs, chain_contracts)

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

    # Legs table (v2: Side, Type, Strike, Expiration, Qty, Bid, Ask, Mid, Delta, IV, Volume, OI)
    legs_table = _build_legs_table(legs)
    if legs_table:
        lines.append("")
        lines.append(legs_table)

    # Net metrics (v2: credit/debit-aware with cushion)
    net_metrics_v2 = _build_net_metrics_v2(
        spread_type=spread_type_enum,
        legs=legs,
        entry_price=net.get("entry_price"),
        underlying_spot=candidate.underlying_spot,
        symbol=symbol,
        breakeven=net.get("breakeven"),
        max_profit=net.get("max_profit"),
        max_loss=net.get("max_loss"),
    )
    if net_metrics_v2:
        lines.extend(["", net_metrics_v2])
    else:
        # Fallback for non-spread types (single legs, unrecognized)
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
            f"- **Underlying spot:** {_fmt(candidate.underlying_spot)}",
            f"- **IV Rank:** {_fmt_pct(net.get('iv_rank'))}",
        ])

    # Greeks & IV (position-level) — between Net metrics and Market context
    greeks_section = _build_greeks_iv_section(legs, net.get("iv_rank"))
    lines.extend(["", greeks_section])

    # Market context — between Greeks & IV and Technicals (OTA-640)
    market_ctx = await _build_market_context_section(net.get("iv_rank"))
    if market_ctx:
        lines.extend(["", market_ctx])

    # Technicals (underlying) — between Market context and Earnings
    technicals = await _build_technicals_section(symbol)
    if technicals:
        lines.extend(["", technicals])

    # Earnings — between Technicals and Options chain
    earnings = await _build_earnings_section(symbol, expiration, db)
    if earnings:
        lines.extend(["", earnings])

    # Options chain — ±3 strikes around trade legs (between Earnings and App verdict)
    if chain_contracts:
        chain_section = _build_options_chain_section(
            chain_contracts, legs, symbol, expiration, candidate.underlying_spot,
        )
        if chain_section:
            lines.extend(["", chain_section])

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

    # Invalidation conditions — heading always present (QA skill greps for it)
    lines.extend(["", "### Invalidation conditions (\"This Trade Is Wrong If\")", ""])
    if thesis_invalidators:
        for inv in thesis_invalidators:
            lines.append(f"- {inv}")
    else:
        lines.append("_No invalidation conditions recorded for this evaluation._")

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

async def _build_position_markdown(
    position: Position, latest_assessment, db: AsyncSession,
    chain_contracts: list | None = None,
) -> tuple[str, str]:
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

    # Enrich legs with chain data if available
    if chain_contracts:
        legs = _enrich_legs_from_chain(legs, chain_contracts)

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

    # Legs table (v2: 12 columns)
    legs_table = _build_legs_table(legs)
    if legs_table:
        lines.append("")
        lines.append(legs_table)

    # Net metrics (v2: credit/debit-aware with cushion)
    net_metrics_v2 = _build_net_metrics_v2(
        spread_type=spread_type_enum,
        legs=legs,
        entry_price=position.entry_price,
        underlying_spot=position.entry_underlying_price,
        symbol=symbol,
        breakeven=ts.get("breakeven"),
        max_profit=ts.get("max_profit"),
        max_loss=ts.get("max_loss"),
    )
    if net_metrics_v2:
        lines.extend(["", net_metrics_v2])
    else:
        # Fallback for non-spread types
        breakeven = ts.get("breakeven")
        if isinstance(breakeven, list):
            breakeven_str = f"[{', '.join(_fmt(b) for b in breakeven)}]"
        else:
            breakeven_str = _fmt(breakeven)
        lines.extend([
            "",
            "## Net metrics",
            "",
            f"- **Entry price:** {_fmt(position.entry_price)}",
            f"- **Max profit:** {_fmt(ts.get('max_profit'))}",
            f"- **Max loss:** {_fmt(ts.get('max_loss'))}",
            f"- **Breakeven:** {breakeven_str}",
            f"- **Underlying spot:** {_fmt(position.entry_underlying_price)}",
            f"- **IV Rank:** {_fmt_pct(position.entry_iv_rank)}",
        ])

    # Greeks & IV (position-level) — between Net metrics and Market context
    greeks_section = _build_greeks_iv_section(legs, position.entry_iv_rank)
    lines.extend(["", greeks_section])

    # Market context — between Greeks & IV and Technicals (OTA-640)
    market_ctx = await _build_market_context_section(position.entry_iv_rank)
    if market_ctx:
        lines.extend(["", market_ctx])

    # Technicals (underlying) — between Market context and Earnings
    technicals = await _build_technicals_section(symbol)
    if technicals:
        lines.extend(["", technicals])

    # Earnings — between Technicals and Options chain
    earnings = await _build_earnings_section(symbol, expiration, db)
    if earnings:
        lines.extend(["", earnings])

    # Options chain — ±3 strikes (dual render: original snapshot + fresh pull)
    chain_section = await _build_options_chain_section_position(
        chain_contracts, legs, symbol, expiration, position.entry_underlying_price,
    )
    if chain_section:
        lines.extend(["", chain_section])

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

    # Invalidation conditions — heading always present (QA skill greps for it)
    lines.extend(["", "### Invalidation conditions (\"This Trade Is Wrong If\")", ""])
    if thesis_invalidators:
        for inv in thesis_invalidators:
            lines.append(f"- {inv}")
    else:
        lines.append("_No invalidation conditions recorded for this evaluation._")

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

    # Fetch most recent chain snapshot for this symbol to enrich legs
    chain_result = await db.execute(
        select(OptionChainSnapshot)
        .where(
            and_(
                OptionChainSnapshot.user_id == user["sub"],
                OptionChainSnapshot.symbol == candidate.symbol,
            )
        )
        .order_by(OptionChainSnapshot.captured_at.desc())
        .limit(1)
    )
    chain_snapshot = chain_result.scalar_one_or_none()
    chain_contracts = None
    if chain_snapshot and chain_snapshot.chain_data:
        raw = chain_snapshot.chain_data
        chain_contracts = raw if isinstance(raw, list) else _safe_json(raw)

    body, filename = await _build_trade_markdown(candidate, db, chain_contracts=chain_contracts)
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

    # Fetch most recent chain snapshot for this symbol to enrich legs
    chain_result = await db.execute(
        select(OptionChainSnapshot)
        .where(
            and_(
                OptionChainSnapshot.user_id == user["sub"],
                OptionChainSnapshot.symbol == position.symbol,
            )
        )
        .order_by(OptionChainSnapshot.captured_at.desc())
        .limit(1)
    )
    chain_snapshot = chain_result.scalar_one_or_none()
    chain_contracts = None
    if chain_snapshot and chain_snapshot.chain_data:
        raw = chain_snapshot.chain_data
        chain_contracts = raw if isinstance(raw, list) else _safe_json(raw)

    body, filename = await _build_position_markdown(
        position, latest_assessment, db, chain_contracts=chain_contracts,
    )
    return Response(
        content=body,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
