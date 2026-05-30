"""
PositionHealthAdapter — §5 input adapter for the position-health surface.

Three contract methods:
    produce_candidates  — load open positions, fetch market state, populate RAW + DERIVED
    populate_computed   — COMPUTED callback (B-S values, feature-flagged)
    input_catalog       — §5.1 catalog of all named values

The adapter builds one Candidate per open position (status FOLLOWING or LIVE).
Each candidate carries position entry data, parsed exit levels, current market
state, and derived breach / P&L values.

The adapter does NOT run rules, assign scores, or reference strategies.

OTA-735 (skeleton), OTA-736 (RAW from positions), OTA-737 (RAW from market),
OTA-738 (DERIVED), OTA-739 (COMPUTED), OTA-740 (catalog), OTA-741 (parity)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import text

from app.core.config import settings
from app.insight_engine import Candidate, Tier
from app.models.session import async_session
from app.ota_adapters._shared.black_scholes import (
    black_scholes_probability,
    compute_naked_long_option_ev,
    compute_probability_matrix,
)
from app.ota_adapters._shared.schwab_client import get_market_data_provider
from app.services.symbol_cache import to_api_symbol_cached

log = logging.getLogger(__name__)


# ── Structure type → direction mapping ────────────────────────────────

_BULLISH_STRUCTURES = frozenset({
    "bull_put_credit", "bull_call_debit", "long_call",
})
_BEARISH_STRUCTURES = frozenset({
    "bear_call_credit", "bear_put_debit", "long_put",
})


def _direction_from_structure(structure: str | None) -> str | None:
    """Derive direction at load time — replaces runtime sign(stop-warning)."""
    if structure in _BULLISH_STRUCTURES:
        return "bullish"
    if structure in _BEARISH_STRUCTURES:
        return "bearish"
    return None


# ── DERIVED producers (OTA-738) ──────────────────────────────────────


def _compute_derived(candidate: Candidate) -> None:
    """Populate all DERIVED named values from RAW values on a Candidate."""
    nv = candidate.named_values

    # pnl_pct — abs denominator for credit spreads (OTA-738)
    entry = nv.get("position_entry_price")
    mark = nv.get("current_position_mark")
    if entry is not None and mark is not None and entry != 0:
        nv["pnl_pct"] = (mark - entry) / abs(entry)
    else:
        nv["pnl_pct"] = None

    # Structure-aware breach flags (OTA-738)
    direction = nv.get("position_structure_direction")
    current_price = nv.get("current_underlying_price")
    warning = nv.get("position_exit_warning_underlying")
    stop = nv.get("position_exit_stop_underlying")

    if direction and current_price is not None and warning is not None:
        if direction == "bullish":
            nv["warning_breached"] = current_price <= warning
        else:  # bearish
            nv["warning_breached"] = current_price >= warning
    else:
        nv["warning_breached"] = None

    if direction and current_price is not None and stop is not None:
        if direction == "bullish":
            nv["stop_breached"] = current_price <= stop
        else:  # bearish
            nv["stop_breached"] = current_price >= stop
    else:
        nv["stop_breached"] = None

    # warning_proximity_ratio — normalised distance, no 20% literal (OTA-738)
    if (direction and current_price is not None
            and warning is not None and stop is not None):
        buffer = abs(warning - stop)
        if buffer > 0:
            if direction == "bullish":
                distance = current_price - warning
            else:
                distance = warning - current_price
            nv["warning_proximity_ratio"] = distance / buffer
        else:
            nv["warning_proximity_ratio"] = None
    else:
        nv["warning_proximity_ratio"] = None

    # days_since_entry (OTA-738)
    entry_date_iso = nv.get("position_entry_date")
    if entry_date_iso:
        try:
            entry_d = date.fromisoformat(entry_date_iso[:10])
            nv["days_since_entry"] = (date.today() - entry_d).days
        except (ValueError, TypeError):
            nv["days_since_entry"] = None
    else:
        nv["days_since_entry"] = None

    # days_to_expiration (OTA-738)
    expiration_iso = nv.get("position_expiration")
    if expiration_iso:
        try:
            exp_d = date.fromisoformat(expiration_iso[:10])
            nv["days_to_expiration"] = max(0, (exp_d - date.today()).days)
        except (ValueError, TypeError):
            nv["days_to_expiration"] = None
    else:
        nv["days_to_expiration"] = None


# ── §5.1 Input catalog ───────────────────────────────────────────────


@dataclass(frozen=True)
class CatalogEntry:
    """One entry in the §5.1 input catalog."""
    name: str
    tier: Tier
    value_type: str
    null_semantics: str | None
    producer_ref: str


def _raw(name, vtype, null_sem="FAIL_OPEN"):
    return CatalogEntry(name, Tier.RAW, vtype, null_sem, "produce_candidates")


def _derived(name, vtype, null_sem="FAIL_OPEN"):
    return CatalogEntry(name, Tier.DERIVED, vtype, null_sem, "_compute_derived")


def _computed(name, vtype, null_sem="SKIP"):
    return CatalogEntry(name, Tier.COMPUTED, vtype, null_sem, "populate_computed")


_CATALOG: dict[str, CatalogEntry] = {
    # ── RAW — positions table (OTA-736) ──
    "position_entry_price":              _raw("position_entry_price", "number", "FAIL_CLOSED"),
    "position_structure":                _raw("position_structure", "enum", "FAIL_OPEN"),
    "position_structure_direction":      _raw("position_structure_direction", "enum:bullish|bearish", "FAIL_OPEN"),
    "position_exit_warning_underlying":  _raw("position_exit_warning_underlying", "number", "SKIP"),
    "position_exit_stop_underlying":     _raw("position_exit_stop_underlying", "number", "SKIP"),
    "position_exit_scale_out_underlying": _raw("position_exit_scale_out_underlying", "number", "SKIP"),
    "position_exit_levels_complete":     _raw("position_exit_levels_complete", "boolean", "FAIL_OPEN"),
    "position_entry_date":              _raw("position_entry_date", "date", "FAIL_OPEN"),
    "position_entry_underlying_price":  _raw("position_entry_underlying_price", "number", "SKIP"),
    "position_expiration":              _raw("position_expiration", "date", "SKIP"),
    # ── RAW — current market state (OTA-737) ──
    "current_underlying_price":         _raw("current_underlying_price", "number", "FAIL_CLOSED"),
    "current_position_mark":            _raw("current_position_mark", "number", "FAIL_CLOSED"),
    # ── DERIVED (OTA-738) ──
    "pnl_pct":                          _derived("pnl_pct", "number", "FAIL_CLOSED"),
    "warning_breached":                 _derived("warning_breached", "boolean", "SKIP"),
    "stop_breached":                    _derived("stop_breached", "boolean", "SKIP"),
    "warning_proximity_ratio":          _derived("warning_proximity_ratio", "number", "SKIP"),
    "days_since_entry":                 _derived("days_since_entry", "number", "FAIL_OPEN"),
    "days_to_expiration":               _derived("days_to_expiration", "number", "SKIP"),
    # ── COMPUTED (OTA-739, feature-flagged) ──
    "current_prob_of_profit":           _computed("current_prob_of_profit", "number"),
    "current_ev":                       _computed("current_ev", "number"),
    "probability_of_max_loss_now":      _computed("probability_of_max_loss_now", "number"),
}


# ── Adapter ───────────────────────────────────────────────────────────


class PositionHealthAdapter:
    """Input adapter for position-health grading (§5 contract).

    Produces one Candidate per open position (status FOLLOWING or LIVE).
    Reuses ``_shared/`` Schwab client for market data and Black-Scholes
    for COMPUTED values — no domain math is duplicated here.
    """

    # ── §5.1 — input catalog ──

    def input_catalog(self) -> list[CatalogEntry]:
        return list(_CATALOG.values())

    # ── §5 — produce candidates ──

    async def produce_candidates(
        self,
        scan_request: dict[str, Any],
    ) -> list[Candidate]:
        """Load open positions and build a stream of Candidate records.

        Each Candidate represents one open position with RAW named values
        from the positions table and DERIVED values computed from them.

        scan_request keys:
            user_id (str|None):   filter positions by user
            position_ids (list[str]|None): specific positions to evaluate
        """
        positions = await self._load_open_positions(scan_request)

        if not positions:
            return []

        candidates: list[Candidate] = []
        for pos in positions:
            c = self._build_candidate(pos)
            if c is not None:
                candidates.append(c)

        if not candidates:
            return []

        # OTA-737: fetch current underlying prices via _shared/ Schwab provider
        await self._stamp_market_prices(candidates, scan_request)

        # OTA-738: compute DERIVED values from RAW
        for c in candidates:
            _compute_derived(c)

        log.debug(
            "PositionHealthAdapter.produce_candidates: %d candidates from %d positions",
            len(candidates), len(positions),
        )
        return candidates

    # ── §5.2 — COMPUTED callback (engine ComputedAdapter protocol) ──

    # Feature flag for COMPUTED producers (OTA-739).
    # Default OFF — v1 grading does not use these values.
    ENABLE_COMPUTED = False

    def populate_computed(
        self,
        candidates: list[Candidate],
        needed: set[str],
    ) -> None:
        """Populate COMPUTED named values on surviving candidates.

        Only computes the values listed in *needed* — the engine passes
        the exact set of COMPUTED names referenced by active rules that
        still apply to the survivors.

        COMPUTED producers (OTA-739) are feature-flagged — default OFF.
        """
        if not needed:
            return
        if not self.ENABLE_COMPUTED:
            return
        log.debug(
            "PositionHealthAdapter.populate_computed needed=%s, n=%d",
            needed, len(candidates),
        )
        for c in candidates:
            nv = c.named_values
            price = nv.get("current_underlying_price")
            if not price or price <= 0:
                continue

            # Need IV and DTE for B-S — extract from position context
            dte = nv.get("days_to_expiration")
            if not dte or dte <= 0:
                continue

            # Use entry underlying price to estimate ATM IV proxy
            # (adapter doesn't have chain data — use a conservative default)
            iv = 0.30  # conservative default; future: fetch live IV from chain
            t_years = max(dte / 365.0, 0.001)

            structure = nv.get("position_structure")
            entry_price = nv.get("position_entry_price", 0)

            if "current_prob_of_profit" in needed:
                be = self._estimate_breakeven(nv)
                if be is not None:
                    nv["current_prob_of_profit"] = round(
                        black_scholes_probability(price, be, t_years, 0.05, iv), 4,
                    )
                else:
                    nv["current_prob_of_profit"] = None

            if "current_ev" in needed and entry_price:
                # For spreads, approximate EV from PoP and max P/L
                pop = nv.get("current_prob_of_profit")
                if pop is not None:
                    # Approximate max_profit / max_loss from entry
                    # This is a rough estimate; full chain data would be better
                    nv["current_ev"] = None  # requires more context than adapter has
                else:
                    nv["current_ev"] = None

            if "probability_of_max_loss_now" in needed:
                stop = nv.get("position_exit_stop_underlying")
                direction = nv.get("position_structure_direction")
                if stop is not None and direction:
                    if direction == "bullish":
                        # P(price <= stop)
                        nv["probability_of_max_loss_now"] = round(
                            1.0 - black_scholes_probability(price, stop, t_years, 0.05, iv), 4,
                        )
                    else:
                        # P(price >= stop)
                        nv["probability_of_max_loss_now"] = round(
                            black_scholes_probability(price, stop, t_years, 0.05, iv), 4,
                        )
                else:
                    nv["probability_of_max_loss_now"] = None

    @staticmethod
    def _estimate_breakeven(nv: dict) -> float | None:
        """Estimate breakeven from position structure and entry price."""
        structure = nv.get("position_structure")
        entry_price = nv.get("position_entry_price")
        entry_underlying = nv.get("position_entry_underlying_price")
        if not entry_price or not entry_underlying:
            return None
        # Rough estimate: for credit spreads, breakeven ≈ short_strike ± credit
        # Without full leg data, use entry_underlying ± entry_price as proxy
        if structure in _BULLISH_STRUCTURES:
            return entry_underlying - abs(entry_price)
        elif structure in _BEARISH_STRUCTURES:
            return entry_underlying + abs(entry_price)
        return None

    # ── internal: market price fetch (OTA-737) ──

    async def _stamp_market_prices(
        self,
        candidates: list[Candidate],
        scan_request: dict[str, Any],
    ) -> None:
        """Fetch underlying quotes via _shared/ and stamp two explicit values.

        ``current_underlying_price`` — live underlying spot from Schwab.
        ``current_position_mark``    — spread/position mark from the DB
            ``current_price`` column (populated by the monitor agent via Schwab).

        These replace health_grade.py's overloaded single ``current_price``.
        """
        # Collect unique symbols
        symbols = {c.symbol for c in candidates if c.symbol}
        if not symbols:
            return

        # Fetch quotes — one call per unique symbol
        quotes: dict[str, float] = {}
        provider = get_market_data_provider(scan_request.get("user_id"))
        for symbol in symbols:
            try:
                api_sym = to_api_symbol_cached(
                    symbol, settings.default_market_data_provider,
                )
                quote = await provider.get_quote(api_sym)
                spot = quote.get("price", 0)
                if spot and spot > 0:
                    quotes[symbol] = float(spot)
            except Exception as exc:
                log.warning("Quote fetch failed for %s: %s", symbol, exc)

        # Stamp onto candidates
        for c in candidates:
            nv = c.named_values
            # current_underlying_price — live spot from Schwab
            nv["current_underlying_price"] = quotes.get(c.symbol)
            # current_position_mark — from DB (already loaded in _build_candidate)
            # Stored on the candidate during build; see _build_candidate

    # ── internal: load positions from DB ──

    async def _load_open_positions(
        self, scan_request: dict[str, Any],
    ) -> list[dict]:
        """Query positions table for open positions."""
        user_id = scan_request.get("user_id")
        position_ids = scan_request.get("position_ids")

        clauses = ["status IN ('FOLLOWING', 'LIVE')"]
        params: dict[str, Any] = {}

        if user_id:
            clauses.append("user_id = :user_id")
            params["user_id"] = user_id

        if position_ids:
            placeholders = ", ".join(f":pid{i}" for i in range(len(position_ids)))
            clauses.append(f"position_id IN ({placeholders})")
            for i, pid in enumerate(position_ids):
                params[f"pid{i}"] = pid

        where = " AND ".join(clauses)
        query = f"""
            SELECT position_id, user_id, symbol, strategy_key,
                   trade_structure, source, status,
                   entry_price, entry_date,
                   entry_underlying_price,
                   claude_exit_levels,
                   current_price,
                   health_grade,
                   last_monitored_at
            FROM positions
            WHERE {where}
        """

        try:
            async with async_session() as db:
                result = await db.execute(text(query), params)
                rows = result.fetchall()
        except Exception as exc:
            log.error("Failed to load positions: %s", exc)
            return []

        columns = [
            "position_id", "user_id", "symbol", "strategy_key",
            "trade_structure", "source", "status",
            "entry_price", "entry_date",
            "entry_underlying_price",
            "claude_exit_levels",
            "current_price",
            "health_grade",
            "last_monitored_at",
        ]
        return [dict(zip(columns, row)) for row in rows]

    # ── internal: build a single candidate from a position row ──

    def _build_candidate(self, pos: dict) -> Candidate | None:
        """Build a Candidate from a positions row.

        Returns None if the position lacks required data for grading
        (e.g. missing entry_price).
        """
        entry_price = pos.get("entry_price")
        if entry_price is None or float(entry_price) == 0:
            log.debug(
                "Skipping position %s: entry_price is %s",
                pos.get("position_id"), entry_price,
            )
            return None

        position_id = pos["position_id"]
        symbol = pos["symbol"]

        # Parse trade_structure JSON for structure type and expiration
        trade_structure_json = pos.get("trade_structure")
        structure = self._parse_structure_type(trade_structure_json)
        direction = _direction_from_structure(structure)
        expiration = self._parse_expiration(trade_structure_json)

        # Parse claude_exit_levels
        exit_levels = self._parse_exit_levels(pos.get("claude_exit_levels"))

        # Exit level values (OTA-736)
        warning = self._safe_float(exit_levels.get("warning")) if exit_levels else None
        stop = self._safe_float(exit_levels.get("stop")) if exit_levels else None
        scale_out = self._safe_float(exit_levels.get("scale_out")) if exit_levels else None
        exit_levels_complete = warning is not None and stop is not None

        # entry_date as ISO string for DERIVED producers (OTA-738)
        raw_entry_date = pos.get("entry_date")
        entry_date_iso = None
        if isinstance(raw_entry_date, datetime):
            entry_date_iso = raw_entry_date.date().isoformat()
        elif isinstance(raw_entry_date, date):
            entry_date_iso = raw_entry_date.isoformat()
        elif isinstance(raw_entry_date, str):
            entry_date_iso = raw_entry_date[:10]

        named_values: dict[str, Any] = {
            # ── RAW from positions table (OTA-736) ──
            "position_entry_price": float(entry_price),
            "position_structure": structure,
            "position_structure_direction": direction,
            "position_exit_warning_underlying": warning,
            "position_exit_stop_underlying": stop,
            "position_exit_scale_out_underlying": scale_out,
            "position_exit_levels_complete": exit_levels_complete,
            # ── RAW from market state (OTA-737) ──
            # current_underlying_price stamped by _stamp_market_prices (live Schwab)
            # current_position_mark from DB (populated by monitor agent via Schwab)
            "current_position_mark": (
                float(pos["current_price"])
                if pos.get("current_price") is not None else None
            ),
            # RAW auxiliaries for OTA-738
            "position_entry_date": entry_date_iso,
            "position_expiration": expiration,
            "position_entry_underlying_price": (
                float(pos["entry_underlying_price"])
                if pos.get("entry_underlying_price") is not None else None
            ),
        }

        return Candidate(
            candidate_id=position_id,
            candidate_type="position",
            symbol=symbol,
            user_id=pos.get("user_id"),
            subject_type="POSITION",
            subject_id=position_id,
            named_values=named_values,
        )

    @staticmethod
    def _parse_structure_type(trade_structure_json: str | None) -> str | None:
        """Extract structure type from trade_structure JSON."""
        if not trade_structure_json:
            return None
        try:
            ts = json.loads(trade_structure_json)
            # trade_structure may store type directly or under a key
            if isinstance(ts, dict):
                return ts.get("type") or ts.get("structure_type") or ts.get("spread_type")
            return None
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _parse_expiration(trade_structure_json: str | None) -> str | None:
        """Extract expiration date from trade_structure JSON."""
        if not trade_structure_json:
            return None
        try:
            ts = json.loads(trade_structure_json)
            if isinstance(ts, dict):
                return ts.get("expiration") or ts.get("expiry")
            return None
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _parse_exit_levels(claude_exit_levels_json: str | None) -> dict | None:
        """Parse claude_exit_levels JSON into a dict."""
        if not claude_exit_levels_json:
            return None
        try:
            levels = json.loads(claude_exit_levels_json)
            if isinstance(levels, dict):
                return levels
            return None
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        """Convert a value to float, returning None on failure."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
