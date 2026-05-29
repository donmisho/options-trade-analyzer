"""
OptionsChainAdapter — §5 input adapter for the screening surface.

Three contract methods:
    produce_candidates  — fetch chain, build trade structures, populate RAW + DERIVED
    populate_computed   — COMPUTED callback matching engine ComputedAdapter (OTA-716)
    input_catalog       — §5.1 catalog of all named values

The adapter builds one Candidate per (structure, strikes, expiry) combination.
Spread building (debit + credit) and naked-option identification live here —
domain knowledge on the input side of the engine (§5).

The adapter does NOT run rules, assign scores, or reference strategies.

OTA-713 (skeleton), OTA-714 (chain fetch + structure building), OTA-715 (DERIVED)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date
from typing import Any

from scipy.stats import norm

from app.core.config import settings
from app.insight_engine import Candidate, Tier
from app.ota_adapters._shared.schwab_client import get_market_data_provider
from app.services.symbol_cache import to_api_symbol_cached

log = logging.getLogger(__name__)

# ── Structure type constants ───────────────────────────────────────────

DEBIT_SPREAD_TYPES = frozenset({"bull_call", "bear_put"})
CREDIT_SPREAD_TYPES = frozenset({"bull_put", "bear_call"})
SPREAD_TYPES = DEBIT_SPREAD_TYPES | CREDIT_SPREAD_TYPES
NAKED_TYPES = frozenset({"long_call", "long_put"})
ALL_STRUCTURE_TYPES = SPREAD_TYPES | NAKED_TYPES


# ── IV normalisation ──────────────────────────────────────────────────

def _normalize_iv(raw_iv):
    """Schwab returns IV as decimal (0.26 = 26%). Guard against > 2.0."""
    if raw_iv is None:
        return None
    return raw_iv / 100.0 if raw_iv > 2.0 else raw_iv


# ── B-S delta fallback (after-hours null greeks) ─────────────────────

def _bs_delta(option_type: str, S: float, K: float, T: float,
              sigma: float, r: float = 0.05) -> float:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return float(norm.cdf(d1)) if option_type == "call" else float(norm.cdf(d1) - 1.0)


def _get_delta(leg: dict, underlying_price: float, exp: str) -> float:
    """Return delta from the API, or estimate via Black-Scholes."""
    delta = leg.get("delta")
    if delta is not None:
        return delta
    iv_raw = leg.get("implied_volatility") or leg.get("iv") or 0
    iv = _normalize_iv(iv_raw) or 0
    if iv <= 0:
        return 0.0
    strike = leg.get("strike", 0)
    option_type = leg.get("option_type", "call")
    try:
        dte = max((date.fromisoformat(exp[:10]) - date.today()).days, 0)
    except (ValueError, TypeError):
        return 0.0
    return _bs_delta(option_type, underlying_price, strike, dte / 365.0, iv)


def _compute_dte(expiration: str) -> int:
    try:
        return max(0, (date.fromisoformat(expiration[:10]) - date.today()).days)
    except (ValueError, TypeError):
        return 0


# ── DERIVED producers (OTA-715) ──────────────────────────────────────

def _compute_derived(candidate: Candidate) -> None:
    """Populate all DERIVED named values from RAW values on a Candidate."""
    nv = candidate.named_values
    nv["DTE"] = _compute_dte(nv.get("expiration", ""))

    structure = nv.get("spread_type")
    if structure in SPREAD_TYPES:
        _compute_spread_derived(nv, structure)
    else:
        _compute_naked_derived(nv)


def _compute_spread_derived(nv: dict, structure: str) -> None:
    long_mid = ((nv.get("long_bid", 0) or 0) + (nv.get("long_ask", 0) or 0)) / 2
    short_mid = ((nv.get("short_bid", 0) or 0) + (nv.get("short_ask", 0) or 0)) / 2
    width = nv.get("spread_width", 0)
    price = nv.get("underlying_price", 0)

    if structure in DEBIT_SPREAD_TYPES:
        net_debit = long_mid - short_mid
        nv["net_debit"] = round(net_debit, 4)
        nv["net_credit"] = None
        max_profit = (width - net_debit) * 100
        max_loss = net_debit * 100
        nv["max_profit"] = round(max_profit, 2)
        nv["max_loss"] = round(max_loss, 2)

        long_strike = nv.get("long_strike", 0)
        if structure == "bull_call":
            nv["breakeven"] = round(long_strike + net_debit, 2)
        else:  # bear_put
            nv["breakeven"] = round(long_strike - net_debit, 2)

        nv["prob_of_profit"] = round(abs(nv.get("long_delta", 0) or 0), 4)
        nv["debit_pct_of_width"] = round(net_debit / width * 100, 2) if width > 0 else None
        nv["credit_pct_of_width"] = None
    else:
        net_credit = short_mid - long_mid
        nv["net_credit"] = round(net_credit, 4)
        nv["net_debit"] = round(-net_credit, 4)
        max_profit = net_credit * 100
        max_loss = (width - net_credit) * 100
        nv["max_profit"] = round(max_profit, 2)
        nv["max_loss"] = round(max_loss, 2)

        short_strike = nv.get("short_strike", 0)
        if structure == "bull_put":
            nv["breakeven"] = round(short_strike - net_credit, 2)
        else:  # bear_call
            nv["breakeven"] = round(short_strike + net_credit, 2)

        nv["prob_of_profit"] = round(1.0 - abs(nv.get("short_delta", 0) or 0), 4)
        nv["credit_pct_of_width"] = round(net_credit / width * 100, 2) if width > 0 else None
        nv["debit_pct_of_width"] = None

    prob = nv.get("prob_of_profit", 0)
    mp = nv.get("max_profit", 0)
    ml = nv.get("max_loss", 0)
    nv["ev_raw"] = round(prob * mp - (1 - prob) * ml, 2)
    nv["reward_risk_ratio"] = round(mp / ml, 4) if ml > 0 else 0

    breakeven = nv.get("breakeven", 0)
    if price > 0 and breakeven > 0:
        if structure in ("bull_call", "bear_call"):
            nv["cushion_pct"] = round(((breakeven - price) / price) * 100, 2)
        else:
            nv["cushion_pct"] = round(((price - breakeven) / price) * 100, 2)
    else:
        nv["cushion_pct"] = None


def _compute_naked_derived(nv: dict) -> None:
    bid = nv.get("bid", 0) or 0
    ask = nv.get("ask", 0) or 0
    mid = (bid + ask) / 2 if (bid + ask) > 0 else 0
    strike = nv.get("strike", 0)
    price = nv.get("underlying_price", 0)
    option_type = nv.get("option_type", "call")
    theta = nv.get("theta", 0) or 0

    nv["premium_dollars"] = round(mid * 100, 2)
    nv["bid_ask_spread_pct"] = round(((ask - bid) / mid) * 100, 2) if mid > 0 else None

    if option_type == "put":
        be = strike - mid
        nv["breakeven"] = round(be, 2)
        nv["breakeven_distance_pct"] = (
            round(((price - be) / price) * 100, 2) if price > 0 else None
        )
    else:
        be = strike + mid
        nv["breakeven"] = round(be, 2)
        nv["breakeven_distance_pct"] = (
            round(((be - price) / price) * 100, 2) if price > 0 else None
        )

    theta_per_day = abs(theta) * 100
    premium = mid * 100
    nv["theta_runway_days"] = (
        round(premium / theta_per_day, 1) if theta_per_day > 0 else None
    )


# ── §5.1 Input catalog ────────────────────────────────────────────────


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


_CATALOG: dict[str, CatalogEntry] = {
    # ── RAW — chain level ──
    "underlying_price":  _raw("underlying_price", "number", "FAIL_CLOSED"),
    "option_type":       _raw("option_type", "enum", "FAIL_CLOSED"),
    "expiration":        _raw("expiration", "date", "FAIL_CLOSED"),
    # ── RAW — spread legs ──
    "spread_type":       _raw("spread_type", "enum", "FAIL_CLOSED"),
    "long_strike":       _raw("long_strike", "number", "FAIL_CLOSED"),
    "short_strike":      _raw("short_strike", "number", "FAIL_CLOSED"),
    "long_bid":          _raw("long_bid", "number"),
    "long_ask":          _raw("long_ask", "number"),
    "short_bid":         _raw("short_bid", "number"),
    "short_ask":         _raw("short_ask", "number"),
    "long_delta":        _raw("long_delta", "number", "SKIP"),
    "short_delta":       _raw("short_delta", "number", "SKIP"),
    "long_theta":        _raw("long_theta", "number"),
    "short_theta":       _raw("short_theta", "number"),
    "long_gamma":        _raw("long_gamma", "number"),
    "short_gamma":       _raw("short_gamma", "number"),
    "long_vega":         _raw("long_vega", "number"),
    "short_vega":        _raw("short_vega", "number"),
    "long_volume":       _raw("long_volume", "number"),
    "short_volume":      _raw("short_volume", "number"),
    "long_oi":           _raw("long_oi", "number"),
    "short_oi":          _raw("short_oi", "number"),
    "long_iv":           _raw("long_iv", "number"),
    "short_iv":          _raw("short_iv", "number"),
    "spread_width":      _raw("spread_width", "number", "FAIL_CLOSED"),
    # ── RAW — naked option ──
    "strike":            _raw("strike", "number", "FAIL_CLOSED"),
    "bid":               _raw("bid", "number"),
    "ask":               _raw("ask", "number"),
    "delta":             _raw("delta", "number", "SKIP"),
    "theta":             _raw("theta", "number"),
    "gamma":             _raw("gamma", "number"),
    "vega":              _raw("vega", "number"),
    "iv":                _raw("iv", "number"),
    "volume":            _raw("volume", "number"),
    "open_interest":     _raw("open_interest", "number"),
    # ── DERIVED ──
    "DTE":                   _derived("DTE", "number", "FAIL_CLOSED"),
    "net_debit":             _derived("net_debit", "number", "SKIP"),
    "net_credit":            _derived("net_credit", "number", "SKIP"),
    "max_profit":            _derived("max_profit", "number", "FAIL_CLOSED"),
    "max_loss":              _derived("max_loss", "number", "FAIL_CLOSED"),
    "breakeven":             _derived("breakeven", "number", "FAIL_CLOSED"),
    "prob_of_profit":        _derived("prob_of_profit", "number"),
    "ev_raw":                _derived("ev_raw", "number"),
    "reward_risk_ratio":     _derived("reward_risk_ratio", "number"),
    "cushion_pct":           _derived("cushion_pct", "number", "SKIP"),
    "bid_ask_spread_pct":    _derived("bid_ask_spread_pct", "number", "SKIP"),
    "premium_dollars":       _derived("premium_dollars", "number"),
    "theta_runway_days":     _derived("theta_runway_days", "number", "SKIP"),
    "credit_pct_of_width":   _derived("credit_pct_of_width", "number", "SKIP"),
    "debit_pct_of_width":    _derived("debit_pct_of_width", "number", "SKIP"),
    "breakeven_distance_pct": _derived("breakeven_distance_pct", "number", "SKIP"),
}


# ── Adapter ────────────────────────────────────────────────────────────


class OptionsChainAdapter:
    """Input adapter for options-chain screening (§5 contract).

    After calling ``produce_candidates``, the adapter exposes the raw
    chain data via ``contracts``, ``underlying_price``, and ``chain_data``
    so routes can backward-compat with existing analysis engines during
    the migration period.
    """

    def __init__(self) -> None:
        self._contracts: list[dict] = []
        self._underlying_price: float = 0.0
        self._chain_data: dict[str, Any] = {}

    # ── backward-compat accessors ──

    @property
    def contracts(self) -> list[dict]:
        return self._contracts

    @property
    def underlying_price(self) -> float:
        return self._underlying_price

    @property
    def chain_data(self) -> dict[str, Any]:
        return self._chain_data

    # ── §5.1 — input catalog ──

    def input_catalog(self) -> list[CatalogEntry]:
        return list(_CATALOG.values())

    # ── §5 — produce candidates ──

    async def produce_candidates(
        self,
        scan_request: dict[str, Any],
    ) -> list[Candidate]:
        """Fetch chain data and build a stream of Candidate records.

        Each Candidate represents one trade structure (spread or naked
        option) with RAW named values from the chain and DERIVED values
        computed from them.

        scan_request keys:
            symbol (str):            required
            min_dte (int):           default 14
            max_dte (int):           default 60
            strike_range_pct (float): default 10.0
            option_type (str|None):  "call", "put", or None for both
            user_id (str|None):      for provider auth
            structure_types (list[str]|None): which structures to build,
                                             None = all
        """
        await self._fetch_chain(scan_request)

        if not self._contracts or self._underlying_price <= 0:
            return []

        symbol = scan_request.get("symbol", "")
        requested = scan_request.get("structure_types")
        candidates: list[Candidate] = []

        # Spreads
        spread_set = (
            (set(requested) & SPREAD_TYPES) if requested is not None
            else SPREAD_TYPES
        )
        if spread_set:
            candidates.extend(self._build_spreads(symbol, spread_set))

        # Naked options
        naked_set = (
            (set(requested) & NAKED_TYPES) if requested is not None
            else NAKED_TYPES
        )
        if naked_set:
            candidates.extend(self._build_naked(symbol, naked_set))

        for c in candidates:
            _compute_derived(c)

        log.debug(
            "OptionsChainAdapter.produce_candidates: %d candidates for %s",
            len(candidates), symbol,
        )
        return candidates

    # ── §5.2 — COMPUTED callback (engine ComputedAdapter protocol) ──

    def populate_computed(
        self,
        candidates: list[Candidate],
        needed: set[str],
    ) -> None:
        """Populate COMPUTED named values on surviving candidates.

        Stub — real COMPUTED math lands in OTA-716.
        """
        log.debug(
            "OptionsChainAdapter.populate_computed (stub) needed=%s, n=%d",
            needed, len(candidates),
        )

    # ── internal: chain fetch ──

    async def _fetch_chain(self, scan_request: dict[str, Any]) -> None:
        provider = get_market_data_provider(scan_request.get("user_id"))
        symbol = scan_request["symbol"]
        api_sym = to_api_symbol_cached(
            symbol, settings.default_market_data_provider,
        )
        chain_data = await provider.get_chain(
            symbol=api_sym,
            min_dte=scan_request.get("min_dte", 14),
            max_dte=scan_request.get("max_dte", 60),
            strike_range_pct=scan_request.get("strike_range_pct", 10.0),
            option_type=scan_request.get("option_type"),
        )
        self._contracts = chain_data.get("contracts", [])
        self._underlying_price = chain_data.get("underlying_price", 0)
        self._chain_data = chain_data

    # ── internal: spread building ──

    def _build_spreads(
        self, symbol: str, spread_types: set[str],
    ) -> list[Candidate]:
        price = self._underlying_price

        by_exp: dict[tuple[str, str], list[dict]] = {}
        for c in self._contracts:
            key = (c["expiration"], c["option_type"])
            by_exp.setdefault(key, []).append(c)
        for key in by_exp:
            by_exp[key].sort(key=lambda x: x["strike"])

        candidates: list[Candidate] = []
        for (exp, opt_type), chain in by_exp.items():
            n = len(chain)
            for i in range(n):
                for j in range(i + 1, n):
                    lower, upper = chain[i], chain[j]
                    if opt_type == "call":
                        if "bull_call" in spread_types:
                            c = self._make_spread(
                                lower, upper, exp, "bull_call",
                                symbol, price, is_debit=True,
                            )
                            if c:
                                candidates.append(c)
                        if "bear_call" in spread_types:
                            c = self._make_spread(
                                upper, lower, exp, "bear_call",
                                symbol, price, is_debit=False,
                            )
                            if c:
                                candidates.append(c)
                    elif opt_type == "put":
                        if "bear_put" in spread_types:
                            c = self._make_spread(
                                upper, lower, exp, "bear_put",
                                symbol, price, is_debit=True,
                            )
                            if c:
                                candidates.append(c)
                        if "bull_put" in spread_types:
                            c = self._make_spread(
                                lower, upper, exp, "bull_put",
                                symbol, price, is_debit=False,
                            )
                            if c:
                                candidates.append(c)
        return candidates

    def _make_spread(
        self,
        long_leg: dict,
        short_leg: dict,
        exp: str,
        spread_type: str,
        symbol: str,
        price: float,
        *,
        is_debit: bool,
    ) -> Candidate | None:
        """Build a single spread Candidate. Returns None if structurally invalid."""
        width = abs(long_leg["strike"] - short_leg["strike"])
        if width <= 0:
            return None

        long_mid = ((long_leg.get("bid", 0) or 0) + (long_leg.get("ask", 0) or 0)) / 2
        short_mid = ((short_leg.get("bid", 0) or 0) + (short_leg.get("ask", 0) or 0)) / 2

        if is_debit:
            if (long_mid - short_mid) <= 0:
                return None
            if (width - (long_mid - short_mid)) * 100 <= 0:
                return None
        else:
            if (short_mid - long_mid) <= 0:
                return None
            if (width - (short_mid - long_mid)) * 100 <= 0:
                return None

        long_iv_raw = long_leg.get("implied_volatility") or long_leg.get("iv") or 0
        short_iv_raw = short_leg.get("implied_volatility") or short_leg.get("iv") or 0

        cid = f"{symbol}_{spread_type}_{long_leg['strike']}_{short_leg['strike']}_{exp}"
        return Candidate(
            candidate_id=cid,
            candidate_type="options_trade",
            symbol=symbol,
            subject_type="TRADE_CANDIDATE",
            named_values={
                "underlying_price": price,
                "spread_type": spread_type,
                "option_type": long_leg["option_type"],
                "expiration": exp,
                "long_strike": long_leg["strike"],
                "short_strike": short_leg["strike"],
                "spread_width": width,
                "long_bid": long_leg.get("bid", 0) or 0,
                "long_ask": long_leg.get("ask", 0) or 0,
                "short_bid": short_leg.get("bid", 0) or 0,
                "short_ask": short_leg.get("ask", 0) or 0,
                "long_delta": _get_delta(long_leg, price, exp),
                "short_delta": _get_delta(short_leg, price, exp),
                "long_theta": long_leg.get("theta", 0) or 0,
                "short_theta": short_leg.get("theta", 0) or 0,
                "long_gamma": long_leg.get("gamma", 0) or 0,
                "short_gamma": short_leg.get("gamma", 0) or 0,
                "long_vega": long_leg.get("vega", 0) or 0,
                "short_vega": short_leg.get("vega", 0) or 0,
                "long_volume": long_leg.get("volume", 0) or 0,
                "short_volume": short_leg.get("volume", 0) or 0,
                "long_oi": long_leg.get("open_interest", 0) or 0,
                "short_oi": short_leg.get("open_interest", 0) or 0,
                "long_iv": _normalize_iv(long_iv_raw) or 0,
                "short_iv": _normalize_iv(short_iv_raw) or 0,
            },
        )

    # ── internal: naked option building ──

    def _build_naked(
        self, symbol: str, naked_types: set[str],
    ) -> list[Candidate]:
        price = self._underlying_price
        candidates: list[Candidate] = []

        for c in self._contracts:
            opt_type = c.get("option_type", "call")
            structure = f"long_{opt_type}"
            if structure not in naked_types:
                continue

            iv_raw = c.get("implied_volatility") or c.get("iv") or 0

            cid = f"{symbol}_{structure}_{c['strike']}_{c['expiration']}"
            candidates.append(Candidate(
                candidate_id=cid,
                candidate_type="options_trade",
                symbol=symbol,
                subject_type="TRADE_CANDIDATE",
                named_values={
                    "underlying_price": price,
                    "spread_type": structure,
                    "option_type": opt_type,
                    "expiration": c["expiration"],
                    "strike": c["strike"],
                    "bid": c.get("bid", 0) or 0,
                    "ask": c.get("ask", 0) or 0,
                    "delta": _get_delta(c, price, c["expiration"]),
                    "theta": c.get("theta", 0) or 0,
                    "gamma": c.get("gamma", 0) or 0,
                    "vega": c.get("vega", 0) or 0,
                    "iv": _normalize_iv(iv_raw) or 0,
                    "volume": c.get("volume", 0) or 0,
                    "open_interest": c.get("open_interest", 0) or 0,
                },
            ))

        return candidates
