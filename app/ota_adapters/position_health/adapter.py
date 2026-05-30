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


# Catalog populated in OTA-740; placeholder for now
_CATALOG: dict[str, CatalogEntry] = {}


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

        log.debug(
            "PositionHealthAdapter.produce_candidates: %d candidates from %d positions",
            len(candidates), len(positions),
        )
        return candidates

    # ── §5.2 — COMPUTED callback (engine ComputedAdapter protocol) ──

    def populate_computed(
        self,
        candidates: list[Candidate],
        needed: set[str],
    ) -> None:
        """Populate COMPUTED named values on surviving candidates.

        Only computes the values listed in *needed* — the engine passes
        the exact set of COMPUTED names referenced by active rules that
        still apply to the survivors.

        COMPUTED producers (OTA-739) are feature-flagged and not yet active.
        """
        if not needed:
            return
        log.debug(
            "PositionHealthAdapter.populate_computed needed=%s, n=%d",
            needed, len(candidates),
        )
        # COMPUTED producers added in OTA-739

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

        # Parse trade_structure JSON for structure type
        structure = self._parse_structure_type(pos.get("trade_structure"))
        direction = _direction_from_structure(structure)

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
