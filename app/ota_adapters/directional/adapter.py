"""
DirectionalAdapter — §5 input adapter for the directional comparison surface.

Three contract methods:
    produce_candidates  — fetch chain, build thesis-compatible structures, populate RAW + DERIVED
    populate_computed   — COMPUTED callback matching engine ComputedAdapter (OTA-716)
    input_catalog       — §5.1 catalog of all named values

The adapter takes a thesis (ticker, direction, conviction, target price,
timeframe, risk budget) and builds one Candidate per (structure, strikes,
expiry) combination compatible with the thesis direction:
    bullish thesis → bull_call debit spreads + long_call
    bearish thesis → bear_put debit spreads + long_put

The adapter does NOT run rules, assign scores, or reference strategies.

OTA-753
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
from app.ota_adapters._shared.black_scholes import (
    black_scholes_probability,
    compute_naked_long_option_ev,
    compute_probability_matrix,
)
from app.ota_adapters._shared.schwab_client import get_market_data_provider
from app.ota_adapters._shared.sma import compute_sma_signal
from app.services.symbol_cache import to_api_symbol_cached

log = logging.getLogger(__name__)

# ── Structure type constants ───────────────────────────────────────────

BULLISH_STRUCTURES = frozenset({"bull_call", "long_call"})
BEARISH_STRUCTURES = frozenset({"bear_put", "long_put"})
SPREAD_TYPES = frozenset({"bull_call", "bear_put"})
NAKED_TYPES = frozenset({"long_call", "long_put"})
ALL_STRUCTURE_TYPES = BULLISH_STRUCTURES | BEARISH_STRUCTURES


# ── IV normalisation (same as options_chain) ──────────────────────────

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


# ── DERIVED producers ─────────────────────────────────────────────────

def _compute_spread_derived(nv: dict) -> None:
    """Populate DERIVED values for a debit spread candidate."""
    long_mid = ((nv.get("long_bid", 0) or 0) + (nv.get("long_ask", 0) or 0)) / 2
    short_mid = ((nv.get("short_bid", 0) or 0) + (nv.get("short_ask", 0) or 0)) / 2
    width = nv.get("spread_width", 0)
    price = nv.get("underlying_price", 0)

    # Directional adapter only builds debit spreads (bull_call, bear_put)
    net_debit = long_mid - short_mid
    nv["net_debit"] = round(net_debit, 4)
    nv["cost"] = round(net_debit * 100, 2)
    max_profit = (width - net_debit) * 100
    max_loss = net_debit * 100
    nv["max_profit"] = round(max_profit, 2)
    nv["max_loss"] = round(max_loss, 2)

    structure = nv.get("spread_type")
    long_strike = nv.get("long_strike", 0)
    if structure == "bull_call":
        nv["breakeven"] = round(long_strike + net_debit, 2)
    else:  # bear_put
        nv["breakeven"] = round(long_strike - net_debit, 2)

    nv["prob_of_profit"] = round(abs(nv.get("long_delta", 0) or 0), 4)

    prob = nv.get("prob_of_profit", 0)
    mp = nv.get("max_profit", 0)
    ml = nv.get("max_loss", 0)
    nv["ev_raw"] = round(prob * mp - (1 - prob) * ml, 2)
    nv["reward_risk_ratio"] = round(mp / ml, 4) if ml > 0 else 0

    nv["structure_type"] = "vertical_spread"

    # net_theta (position perspective)
    nv["net_theta"] = round(
        (nv.get("long_theta", 0) or 0) + (nv.get("short_theta", 0) or 0), 6,
    )


def _compute_naked_derived(nv: dict) -> None:
    """Populate DERIVED values for a naked long option candidate."""
    bid = nv.get("bid", 0) or 0
    ask = nv.get("ask", 0) or 0
    mid = (bid + ask) / 2 if (bid + ask) > 0 else 0
    strike = nv.get("strike", 0)
    price = nv.get("underlying_price", 0)
    option_type = nv.get("option_type", "call")
    theta = nv.get("theta", 0) or 0

    cost = mid * 100
    nv["cost"] = round(cost, 2)
    nv["max_loss"] = round(cost, 2)
    nv["max_profit"] = None  # unlimited
    nv["net_theta"] = theta
    nv["mid_price"] = round(mid, 4)
    nv["prob_of_profit"] = round(abs(nv.get("delta", 0) or 0), 4)
    nv["ev_raw"] = None  # computed via B-S in COMPUTED tier
    nv["reward_risk_ratio"] = None  # undefined for unlimited upside

    if option_type == "put":
        be = strike - mid
        nv["breakeven"] = round(be, 2)
    else:
        be = strike + mid
        nv["breakeven"] = round(be, 2)

    nv["structure_type"] = "long_option"


def _compute_thesis_derived(nv: dict) -> None:
    """Populate thesis-dependent DERIVED values."""
    price = nv.get("underlying_price", 0)
    target = nv.get("thesis_target_price", 0)
    direction = nv.get("thesis_direction", "bullish")
    budget = nv.get("thesis_risk_budget", 0)
    breakeven = nv.get("breakeven", 0)
    cost = nv.get("cost", 0)

    # required_move_pct — how much stock must move for profit
    if price > 0 and breakeven > 0:
        if direction == "bullish":
            nv["required_move_pct"] = round(((breakeven - price) / price) * 100, 2)
        else:
            nv["required_move_pct"] = round(((price - breakeven) / price) * 100, 2)
    else:
        nv["required_move_pct"] = None

    # target_move_pct — how much the thesis expects
    if price > 0 and target > 0:
        nv["target_move_pct"] = round(
            ((target - price) / price) * 100, 2,
        )
    else:
        nv["target_move_pct"] = None

    # buffer_pct — room for error between required move and expected move
    target_move = nv.get("target_move_pct")
    required_move = nv.get("required_move_pct")
    if target_move is not None and required_move is not None:
        nv["buffer_pct"] = round(abs(target_move) - abs(required_move), 2)
    else:
        nv["buffer_pct"] = None

    # fits_budget — does the trade cost fit within the thesis risk budget
    nv["fits_budget"] = cost <= budget if (cost > 0 and budget > 0) else False

    # contracts — how many contracts the budget supports
    nv["contracts"] = int(budget / cost) if cost > 0 else 0


def _compute_derived(candidate: Candidate) -> None:
    """Populate all DERIVED named values from RAW values on a Candidate."""
    nv = candidate.named_values
    nv["dte"] = _compute_dte(nv.get("expiration", ""))
    nv["stock_price"] = nv.get("underlying_price", 0)

    structure = nv.get("spread_type")
    if structure in SPREAD_TYPES:
        _compute_spread_derived(nv)
    else:
        _compute_naked_derived(nv)

    # Trade direction from structure type
    if structure in ("bull_call", "long_call"):
        nv["trade_direction"] = "bullish"
    elif structure in ("bear_put", "long_put"):
        nv["trade_direction"] = "bearish"
    else:
        nv["trade_direction"] = None

    # Thesis-dependent derivations
    _compute_thesis_derived(nv)


# ── ATR_14 (reuse logic from options_chain) ──────────────────────────

def _compute_atr_14(candles: list[dict]) -> float | None:
    if len(candles) < 15:
        return None
    trs: list[float] = []
    for i in range(1, len(candles)):
        h = candles[i].get("high", 0) or 0
        l = candles[i].get("low", 0) or 0
        prev_c = candles[i - 1].get("close", 0) or 0
        if h <= 0 or l <= 0 or prev_c <= 0:
            continue
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    if len(trs) < 14:
        return None
    return round(sum(trs[-14:]) / 14, 4)


# ── IV percentile (reuse logic from options_chain) ───────────────────

def _compute_iv_percentile(candles: list[dict], current_atm_iv: float) -> float | None:
    closes = [
        c["close"] for c in candles
        if isinstance(c.get("close"), (int, float)) and c["close"] > 0
    ]
    if len(closes) < 30 or current_atm_iv <= 0:
        return None
    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    window = 20
    if len(log_returns) < window:
        return None
    realized_vols: list[float] = []
    for i in range(window, len(log_returns) + 1):
        wr = log_returns[i - window:i]
        mean = sum(wr) / window
        variance = sum((r - mean) ** 2 for r in wr) / (window - 1)
        rv = math.sqrt(variance) * math.sqrt(252)
        realized_vols.append(rv)
    if not realized_vols:
        return None
    below = sum(1 for rv in realized_vols if rv < current_atm_iv)
    return round(below / len(realized_vols) * 100, 1)


def _get_atm_iv(contracts: list[dict], underlying_price: float) -> float:
    if not contracts or underlying_price <= 0:
        return 0.30
    calls = [c for c in contracts if c.get("option_type") == "call"]
    if not calls:
        return 0.30
    calls_sorted = sorted(calls, key=lambda c: abs(c.get("strike", 0) - underlying_price))
    ivs = [
        c.get("implied_volatility", 0) or 0
        for c in calls_sorted[:5]
        if (c.get("implied_volatility", 0) or 0) > 0
    ]
    return sum(ivs) / len(ivs) if ivs else 0.30


# ── chart_state ──────────────────────────────────────────────────────

_CHART_STATE_MAP: dict[str, str] = {
    "BULLISH": "Bullish",
    "BEARISH": "Bearish",
    "MIXED": "Mixed",
    "NEUTRAL": "Neutral",
}


def _map_chart_state(sma_alignment: str | None) -> str:
    return _CHART_STATE_MAP.get(sma_alignment or "", "Neutral")


# ── §5.1 Input catalog ──────────────────────────────────────────────


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
    # ── RAW — thesis inputs ──
    "thesis_direction":       _raw("thesis_direction", "enum:bullish|bearish", "FAIL_CLOSED"),
    "thesis_target_price":    _raw("thesis_target_price", "number", "FAIL_CLOSED"),
    "thesis_risk_budget":     _raw("thesis_risk_budget", "number", "FAIL_CLOSED"),
    "thesis_timeframe_days":  _raw("thesis_timeframe_days", "number", "FAIL_CLOSED"),
    "thesis_conviction":      _raw("thesis_conviction", "enum:low|medium|high", "FAIL_OPEN"),
    # ── RAW — chain level ──
    "underlying_price":       _raw("underlying_price", "number", "FAIL_CLOSED"),
    "option_type":            _raw("option_type", "enum", "FAIL_CLOSED"),
    "expiration":             _raw("expiration", "date", "FAIL_CLOSED"),
    # ── RAW — spread legs ──
    "spread_type":            _raw("spread_type", "enum", "FAIL_CLOSED"),
    "long_strike":            _raw("long_strike", "number", "FAIL_CLOSED"),
    "short_strike":           _raw("short_strike", "number", "FAIL_CLOSED"),
    "long_bid":               _raw("long_bid", "number"),
    "long_ask":               _raw("long_ask", "number"),
    "short_bid":              _raw("short_bid", "number"),
    "short_ask":              _raw("short_ask", "number"),
    "long_delta":             _raw("long_delta", "number", "SKIP"),
    "short_delta":            _raw("short_delta", "number", "SKIP"),
    "long_theta":             _raw("long_theta", "number"),
    "short_theta":            _raw("short_theta", "number"),
    "long_iv":                _raw("long_iv", "number"),
    "short_iv":               _raw("short_iv", "number"),
    "spread_width":           _raw("spread_width", "number", "FAIL_CLOSED"),
    # ── RAW — naked option ──
    "strike":                 _raw("strike", "number", "FAIL_CLOSED"),
    "bid":                    _raw("bid", "number"),
    "ask":                    _raw("ask", "number"),
    "delta":                  _raw("delta", "number", "SKIP"),
    "theta":                  _raw("theta", "number"),
    "iv":                     _raw("iv", "number"),
    # ── DERIVED — core trade math ──
    "dte":                    _derived("dte", "number", "FAIL_CLOSED"),
    "stock_price":            _derived("stock_price", "number", "FAIL_CLOSED"),
    "net_debit":              _derived("net_debit", "number", "SKIP"),
    "cost":                   _derived("cost", "number", "FAIL_CLOSED"),
    "max_profit":             _derived("max_profit", "number", "SKIP"),
    "max_loss":               _derived("max_loss", "number", "FAIL_CLOSED"),
    "breakeven":              _derived("breakeven", "number", "FAIL_CLOSED"),
    "prob_of_profit":         _derived("prob_of_profit", "number"),
    "ev_raw":                 _derived("ev_raw", "number", "SKIP"),
    "reward_risk_ratio":      _derived("reward_risk_ratio", "number", "SKIP"),
    "net_theta":              _derived("net_theta", "number"),
    "mid_price":              _derived("mid_price", "number", "SKIP"),
    "trade_direction":        _derived("trade_direction", "enum:bullish|bearish", "SKIP"),
    "structure_type":         _derived("structure_type", "enum:vertical_spread|long_option", "FAIL_CLOSED"),
    # ── DERIVED — thesis-dependent ──
    "required_move_pct":      _derived("required_move_pct", "number", "SKIP"),
    "target_move_pct":        _derived("target_move_pct", "number"),
    "buffer_pct":             _derived("buffer_pct", "number", "SKIP"),
    "fits_budget":            _derived("fits_budget", "boolean"),
    "contracts":              _derived("contracts", "number"),
    # ── DERIVED — market context (SMA, ATR, IV) ──
    "sma_8":                  _derived("sma_8", "number", "SKIP"),
    "sma_21":                 _derived("sma_21", "number", "SKIP"),
    "sma_50":                 _derived("sma_50", "number", "SKIP"),
    "sma_alignment":          _derived("sma_alignment", "enum:BULLISH|BEARISH|MIXED|NEUTRAL", "SKIP"),
    "chart_state":            _derived("chart_state", "enum:Bullish|Bearish|Mixed|Neutral", "SKIP"),
    "atr_14":                 _derived("atr_14", "number", "SKIP"),
    "iv_percentile":          _derived("iv_percentile", "number", "SKIP"),
    "atm_iv":                 _derived("atm_iv", "number", "SKIP"),
    # ── COMPUTED ──
    "probability_matrix":     _computed("probability_matrix", "matrix"),
    "total_ev":               _computed("total_ev", "number"),
}


# ── Adapter ────────────────────────────────────────────────────────────


class DirectionalAdapter:
    """Input adapter for directional thesis comparison (§5 contract).

    Given a thesis (direction, target price, timeframe, budget, conviction),
    fetches the options chain and builds one Candidate per compatible
    (structure, strikes, expiry) combination.

    Bullish thesis → bull_call debit spreads + long_call
    Bearish thesis → bear_put debit spreads + long_put
    """

    def __init__(self) -> None:
        self._contracts: list[dict] = []
        self._underlying_price: float = 0.0

    # ── §5.1 — input catalog ──

    def input_catalog(self) -> list[CatalogEntry]:
        return list(_CATALOG.values())

    # ── §5 — produce candidates ──

    async def produce_candidates(
        self,
        scan_request: dict[str, Any],
    ) -> list[Candidate]:
        """Fetch chain data and build thesis-compatible Candidate records.

        scan_request keys:
            symbol (str):              required
            direction (str):           "bullish" or "bearish" (required)
            target_price (float):      where the thesis expects the stock to go
            timeframe_days (int):      expected timeframe for the move
            risk_budget (float):       max dollars to risk
            conviction (str):          "low", "medium", or "high" (default "medium")
            user_id (str|None):        for provider auth
            strike_range_pct (float):  default 10.0
        """
        await self._fetch_chain(scan_request)

        if not self._contracts or self._underlying_price <= 0:
            return []

        symbol = scan_request.get("symbol", "")
        direction = scan_request.get("direction", "bullish")
        price = self._underlying_price
        timeframe = scan_request.get("timeframe_days", 30)

        # Thesis values stamped onto every candidate
        thesis_values = {
            "thesis_direction": direction,
            "thesis_target_price": scan_request.get("target_price", 0),
            "thesis_risk_budget": scan_request.get("risk_budget", 0),
            "thesis_timeframe_days": timeframe,
            "thesis_conviction": scan_request.get("conviction", "medium"),
        }

        # Filter contracts by direction and timeframe
        if direction == "bullish":
            filtered = [
                c for c in self._contracts
                if c.get("option_type") == "call"
                and self._dte_in_range(c, timeframe)
            ]
            spread_type = "bull_call"
            naked_type = "long_call"
        else:
            filtered = [
                c for c in self._contracts
                if c.get("option_type") == "put"
                and self._dte_in_range(c, timeframe)
            ]
            spread_type = "bear_put"
            naked_type = "long_put"

        if not filtered:
            return []

        filtered.sort(key=lambda x: x["strike"])

        candidates: list[Candidate] = []

        # Build debit spreads
        candidates.extend(
            self._build_spreads(filtered, symbol, price, spread_type, thesis_values)
        )

        # Build naked options
        candidates.extend(
            self._build_naked(filtered, symbol, price, naked_type, thesis_values)
        )

        for c in candidates:
            _compute_derived(c)

        # Per-symbol market context (SMA, ATR, IV percentile, chart_state)
        ctx = await self._fetch_market_context(scan_request)
        if ctx:
            for c in candidates:
                for k, v in ctx.items():
                    c.named_values[k] = v

        log.debug(
            "DirectionalAdapter.produce_candidates: %d candidates for %s (%s)",
            len(candidates), symbol, direction,
        )
        return candidates

    # ── §5.2 — COMPUTED callback (engine ComputedAdapter protocol) ──

    def populate_computed(
        self,
        candidates: list[Candidate],
        needed: set[str],
    ) -> None:
        """Populate COMPUTED named values on surviving candidates."""
        if not needed:
            return
        log.debug(
            "DirectionalAdapter.populate_computed needed=%s, n=%d",
            needed, len(candidates),
        )
        for c in candidates:
            nv = c.named_values
            price = nv.get("underlying_price", 0)
            dte = nv.get("dte", 0)
            structure = nv.get("spread_type", "")

            iv = nv.get("long_iv") or nv.get("iv") or 0
            if iv <= 0:
                continue

            t_years = max(dte / 365.0, 0.001)

            if "probability_matrix" in needed:
                try:
                    pm = compute_probability_matrix(
                        current_price=price, iv=iv, dte=max(dte, 1),
                    )
                    nv["probability_matrix"] = {
                        "price_levels": pm.price_levels,
                        "dates": [d.isoformat() for d in pm.dates],
                        "matrix": pm.matrix,
                    }
                except Exception:
                    nv["probability_matrix"] = None

            if structure in NAKED_TYPES and "total_ev" in needed:
                mid = ((nv.get("bid", 0) or 0) + (nv.get("ask", 0) or 0)) / 2
                if mid > 0:
                    try:
                        nv["total_ev"] = compute_naked_long_option_ev(
                            option_type=nv.get("option_type", "call"),
                            strike=nv.get("strike", 0),
                            underlying_price=price,
                            iv=iv,
                            days_to_exp=max(dte, 1),
                            entry_price=mid,
                        )
                    except Exception:
                        nv["total_ev"] = None
                else:
                    nv["total_ev"] = None

    # ── internal: chain fetch ──

    async def _fetch_chain(self, scan_request: dict[str, Any]) -> None:
        provider = get_market_data_provider(scan_request.get("user_id"))
        symbol = scan_request["symbol"]
        api_sym = to_api_symbol_cached(
            symbol, settings.default_market_data_provider,
        )
        timeframe = scan_request.get("timeframe_days", 30)
        chain_data = await provider.get_chain(
            symbol=api_sym,
            min_dte=max(1, int(timeframe * 0.5)),
            max_dte=int(timeframe * 2.0),
            strike_range_pct=scan_request.get("strike_range_pct", 10.0),
            option_type=scan_request.get(
                "option_type",
                "call" if scan_request.get("direction") == "bullish" else "put",
            ),
        )
        self._contracts = chain_data.get("contracts", [])
        self._underlying_price = chain_data.get("underlying_price", 0)

    # ── internal: market context ──

    async def _fetch_market_context(
        self, scan_request: dict[str, Any],
    ) -> dict[str, Any]:
        """Fetch SMA, ATR_14, IV percentile, chart_state for the symbol."""
        ctx: dict[str, Any] = {}
        symbol = scan_request["symbol"]
        provider = get_market_data_provider(scan_request.get("user_id"))
        api_sym = to_api_symbol_cached(
            symbol, settings.default_market_data_provider,
        )

        candles: list[dict] = []
        if hasattr(provider, "get_candles"):
            try:
                candles = await provider.get_candles(api_sym, range_days=180)
            except Exception as exc:
                log.warning("OHLC candle fetch failed for %s: %s", symbol, exc)

        price = self._underlying_price

        if candles and price > 0:
            sma = compute_sma_signal(candles, price)
            ctx["sma_8"] = sma.get("sma_8")
            ctx["sma_21"] = sma.get("sma_21")
            ctx["sma_50"] = sma.get("sma_50")
            ctx["sma_alignment"] = sma.get("alignment")
            ctx["chart_state"] = _map_chart_state(sma.get("alignment"))
        else:
            ctx["sma_alignment"] = "NEUTRAL"
            ctx["chart_state"] = "Neutral"

        ctx["atr_14"] = _compute_atr_14(candles) if candles else None

        atm_iv = _get_atm_iv(self._contracts, price)
        ctx["atm_iv"] = atm_iv
        ctx["iv_percentile"] = (
            _compute_iv_percentile(candles, atm_iv) if candles else None
        )

        return ctx

    # ── internal: DTE range filter ──

    @staticmethod
    def _dte_in_range(contract: dict, target_days: int) -> bool:
        """Check if contract expiration is within ±50% of target timeframe."""
        try:
            exp_date = date.fromisoformat(contract["expiration"][:10])
            dte = (exp_date - date.today()).days
            return (target_days * 0.5) <= dte <= (target_days * 2.0)
        except (ValueError, TypeError, KeyError):
            return False

    # ── internal: spread building ──

    def _build_spreads(
        self,
        contracts: list[dict],
        symbol: str,
        price: float,
        spread_type: str,
        thesis_values: dict[str, Any],
    ) -> list[Candidate]:
        """Build all valid debit spread candidates from filtered contracts."""
        candidates: list[Candidate] = []
        n = len(contracts)

        for i in range(n):
            for j in range(i + 1, n):
                lower, upper = contracts[i], contracts[j]

                if spread_type == "bull_call":
                    long_leg, short_leg = lower, upper
                else:  # bear_put
                    long_leg, short_leg = upper, lower

                width = abs(long_leg["strike"] - short_leg["strike"])
                if width <= 0:
                    continue

                long_mid = ((long_leg.get("bid", 0) or 0) + (long_leg.get("ask", 0) or 0)) / 2
                short_mid = ((short_leg.get("bid", 0) or 0) + (short_leg.get("ask", 0) or 0)) / 2
                debit = long_mid - short_mid
                if debit <= 0.05:
                    continue
                if (width - debit) * 100 <= 0:
                    continue

                long_iv_raw = long_leg.get("implied_volatility") or long_leg.get("iv") or 0
                short_iv_raw = short_leg.get("implied_volatility") or short_leg.get("iv") or 0
                exp = long_leg["expiration"]

                cid = f"{symbol}_dir_{spread_type}_{long_leg['strike']}_{short_leg['strike']}_{exp}"
                c = Candidate(
                    candidate_id=cid,
                    candidate_type="directional",
                    symbol=symbol,
                    subject_type="THESIS_COMPARISON",
                    named_values={
                        **thesis_values,
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
                        "long_iv": _normalize_iv(long_iv_raw) or 0,
                        "short_iv": _normalize_iv(short_iv_raw) or 0,
                    },
                )
                candidates.append(c)

        return candidates

    # ── internal: naked option building ──

    def _build_naked(
        self,
        contracts: list[dict],
        symbol: str,
        price: float,
        naked_type: str,
        thesis_values: dict[str, Any],
    ) -> list[Candidate]:
        """Build naked long option candidates from filtered contracts."""
        candidates: list[Candidate] = []

        for c in contracts:
            iv_raw = c.get("implied_volatility") or c.get("iv") or 0
            exp = c["expiration"]
            opt_type = c.get("option_type", "call")

            cid = f"{symbol}_dir_{naked_type}_{c['strike']}_{exp}"
            candidates.append(Candidate(
                candidate_id=cid,
                candidate_type="directional",
                symbol=symbol,
                subject_type="THESIS_COMPARISON",
                named_values={
                    **thesis_values,
                    "underlying_price": price,
                    "spread_type": naked_type,
                    "option_type": opt_type,
                    "expiration": exp,
                    "strike": c["strike"],
                    "bid": c.get("bid", 0) or 0,
                    "ask": c.get("ask", 0) or 0,
                    "delta": _get_delta(c, price, exp),
                    "theta": c.get("theta", 0) or 0,
                    "iv": _normalize_iv(iv_raw) or 0,
                },
            ))

        return candidates
