"""
Screening scoring criteria — 16 registered formula implementations.

Each formula is pure: (named_values, params) -> float in [0, 100].
Thresholds and configurable values come from params (junction rows),
never from literals.

Legacy code in app/analysis/strategy_scorer.py is superseded by these
implementations and should be flagged for removal.

OTA-727
"""

from __future__ import annotations

import math

from app.options_rules.screening import screening_formula


# ── SP: Steady Paycheck ────────────────────────────────────────────────


@screening_formula("theta_margin_ratio")
def theta_margin_ratio(named_values: dict, params: dict) -> float:
    """Daily theta decay as a fraction of max loss (margin at risk).

    Formula: abs(net_theta) / max_loss * scale
    Legacy: strategy_scorer.py:208-211
    """
    net_theta = named_values.get("net_theta", 0)
    max_loss = named_values.get("max_loss", 0)
    scale = params.get("scale", 100.0)
    if max_loss <= 0:
        return 0.0
    raw = abs(net_theta) / max_loss
    return min(100.0, raw * scale)


@screening_formula("probability_of_profit")
def probability_of_profit(named_values: dict, params: dict) -> float:
    """Probability of profit from option delta.

    Uses long-leg delta (not 1 - short_delta), per business-rules.md.
    Legacy: strategy_scorer.py:238
    """
    pop = named_values.get("prob_of_profit", 0)
    # pop is already 0-100 scale from the vertical engine
    return min(100.0, max(0.0, float(pop)))


@screening_formula("expected_value")
def expected_value(named_values: dict, params: dict) -> float:
    """Expected value of the trade.

    Credit spreads: ev_raw from vertical engine.
    Long options: delta * underlying_price * move_pct - mid_price.
    Normalization: apply scale to map raw EV to [0, 100].

    Legacy: strategy_scorer.py:239 (credit), :424-430 (long)
    """
    ev_raw = named_values.get("ev_raw")
    if ev_raw is not None:
        # Credit spread path — ev_raw is pre-computed
        scale = params.get("scale", 1.0)
        return min(100.0, max(0.0, float(ev_raw) * scale))

    # Long option path — simple EV proxy
    delta = named_values.get("delta", 0)
    underlying_price = named_values.get("underlying_price", 0)
    mid_price = named_values.get("mid_price", 0)
    move_pct = params.get("move_pct", 0.05)
    scale = params.get("scale", 1.0)
    raw = delta * underlying_price * move_pct - mid_price
    return min(100.0, max(0.0, raw * scale))


@screening_formula("reward_risk")
def reward_risk(named_values: dict, params: dict) -> float:
    """Ratio of max profit to max loss.

    Legacy: strategy_scorer.py:240
    """
    rr = named_values.get("reward_risk_ratio")
    if rr is None:
        max_profit = named_values.get("max_profit", 0)
        max_loss = named_values.get("max_loss", 0)
        rr = max_profit / max_loss if max_loss > 0 else 0.0
    scale = params.get("scale", 100.0)
    return min(100.0, max(0.0, float(rr) * scale))


@screening_formula("iv_rank")
def iv_rank(named_values: dict, params: dict) -> float:
    """IV rank score.

    PROXY: ATM IV / divisor, clamped 0-1, scaled to 0-100.
    True IV rank requires historical-IV producer (future adapter).
    Legacy: strategy_scorer.py:249 — min(1.0, atm_iv / 0.60)
    """
    iv = named_values.get("iv_rank")
    if iv is not None:
        # True IV rank path (when adapter provides it)
        return min(100.0, max(0.0, float(iv)))

    # Proxy path: ATM IV / divisor
    atm_iv = named_values.get("atm_iv", 0)
    divisor = params.get("divisor", 0.60)
    if atm_iv <= 0 or divisor <= 0:
        return 50.0  # neutral default
    raw = min(1.0, atm_iv / divisor)
    return raw * 100.0


# ── WG: Weekly Grind ───────────────────────────────────────────────────


@screening_formula("theta_gamma_ratio")
def theta_gamma_ratio(named_values: dict, params: dict) -> float:
    """Ratio of theta decay to gamma risk.

    PROXY: abs(net_theta) / max_loss (same as theta_margin_ratio).
    True theta/gamma requires per-leg gamma propagation (future adapter).
    Legacy: strategy_scorer.py:213-220
    """
    net_theta = named_values.get("net_theta", 0)
    max_loss = named_values.get("max_loss", 0)
    scale = params.get("scale", 100.0)
    if max_loss <= 0:
        return 0.0
    raw = abs(net_theta) / max_loss
    return min(100.0, raw * scale)


@screening_formula("credit_width")
def credit_width(named_values: dict, params: dict) -> float:
    """Net credit received as a percentage of spread width.

    Formula: credit / width * 100
    Legacy: strategy_scorer.py:222-226
    """
    net_debit = named_values.get("net_debit", 0)
    spread_width = named_values.get("spread_width", 0)
    if spread_width <= 0:
        return 0.0
    credit = abs(net_debit)
    raw = credit / spread_width * 100.0
    return min(100.0, max(0.0, raw))


@screening_formula("liquidity")
def liquidity(named_values: dict, params: dict) -> float:
    """Combined liquidity from both legs' volume and open interest.

    Formula: (long_volume + short_volume + long_oi + short_oi) / scale * 100
    Legacy: strategy_scorer.py:228-233
    """
    total = (
        named_values.get("long_volume", 0)
        + named_values.get("short_volume", 0)
        + named_values.get("long_oi", 0)
        + named_values.get("short_oi", 0)
    )
    scale = params.get("scale", 10000.0)
    if scale <= 0:
        return 0.0
    return min(100.0, max(0.0, float(total) / scale * 100.0))


# ── TR: Trend Rider ───────────────────────────────────────────────────


@screening_formula("sma_alignment_score")
def sma_alignment_score(named_values: dict, params: dict) -> float:
    """Score from SMA alignment classification.

    When the adapter provides a classification, maps:
      BULLISH → bullish_score, BEARISH → bearish_score,
      NEUTRAL → neutral_score, MIXED → mixed_score.
    Fallback: params.get("default_score", 50.0).

    Legacy: strategy_scorer.py:436 — 0.5 passthrough
    """
    classification = named_values.get("sma_alignment_classification")
    if classification is not None:
        classification_upper = str(classification).upper()
        score_map = {
            "BULLISH": params.get("bullish_score", 100.0),
            "BEARISH": params.get("bearish_score", 0.0),
            "NEUTRAL": params.get("neutral_score", 50.0),
            "MIXED": params.get("mixed_score", 25.0),
        }
        return min(100.0, max(0.0, float(score_map.get(
            classification_upper,
            params.get("default_score", 50.0),
        ))))
    return min(100.0, max(0.0, float(params.get("default_score", 50.0))))


@screening_formula("delta_quality")
def delta_quality(named_values: dict, params: dict) -> float:
    """Gaussian-like peak around a target delta range.

    Formula: max(0, 1 - |delta - center| / (half_range + smoothing)) * 100
    Legacy: strategy_scorer.py:389-392
    """
    delta = named_values.get("delta", 0)
    center = params.get("delta_center", 0.35)
    half_range = params.get("delta_half_range", 0.15)
    smoothing = params.get("smoothing", 0.05)
    denominator = half_range + smoothing
    if denominator <= 0:
        return 0.0
    raw = max(0.0, 1.0 - abs(delta - center) / denominator)
    return raw * 100.0


@screening_formula("iv_percentile_cost")
def iv_percentile_cost(named_values: dict, params: dict) -> float:
    """Linear inversion of raw IV. Lower IV = higher score.

    PROXY: true IV percentile requires historical-IV producer.
    Formula: max(0, 1 - iv_decimal / max_iv) * 100
    Legacy: strategy_scorer.py:414-418
    """
    iv_pct = named_values.get("iv", 0)
    # Normalize: if iv > 1, it's in percentage form (e.g. 35 = 35%)
    iv_decimal = iv_pct / 100.0 if iv_pct > 1 else iv_pct
    max_iv = params.get("max_iv", 1.0)
    if max_iv <= 0:
        return 0.0
    raw = max(0.0, 1.0 - iv_decimal / max_iv)
    return raw * 100.0


@screening_formula("runway_score")
def runway_score(named_values: dict, params: dict) -> float:
    """How many days of theta the premium can sustain.

    Formula: min(100, theta_runway_days / scale * 100)
    Legacy: strategy_scorer.py:420-422
    """
    runway_days = float(named_values.get("theta_runway_days", 0))
    scale = params.get("scale", 100.0)
    if scale <= 0:
        return 0.0
    return min(100.0, max(0.0, runway_days / scale * 100.0))


# ── LT: Lottery Ticket ────────────────────────────────────────────────


@screening_formula("payout_ratio")
def payout_ratio(named_values: dict, params: dict) -> float:
    """Expected payout multiple on a configured underlying move.

    Formula: (delta * underlying * move_pct * multiplier) / premium / scale * 100
    Legacy: strategy_scorer.py:399-407 — 10% move, multiplier 100
    """
    delta = named_values.get("delta", 0)
    underlying_price = named_values.get("underlying_price", 0)
    premium_dollars = named_values.get("premium_dollars", 0)
    move_pct = params.get("move_pct", 0.10)
    multiplier = params.get("multiplier", 100.0)
    scale = params.get("scale", 10.0)

    if premium_dollars <= 0 or scale <= 0:
        return 0.0
    raw = (delta * underlying_price * move_pct * multiplier) / premium_dollars
    return min(100.0, max(0.0, raw / scale * 100.0))


@screening_formula("delta_otm_score")
def delta_otm_score(named_values: dict, params: dict) -> float:
    """How far out-of-the-money. Lower delta = more OTM = higher score.

    Formula: max(0, 1 - delta / max_delta) * 100
    Legacy: strategy_scorer.py:394-397 — max_delta hardcoded 0.25
    """
    delta = named_values.get("delta", 0)
    max_delta = params.get("max_delta", 0.25)
    if max_delta <= 0:
        return 0.0
    raw = max(0.0, 1.0 - delta / max_delta)
    return raw * 100.0


@screening_formula("bid_ask_tightness")
def bid_ask_tightness(named_values: dict, params: dict) -> float:
    """Inverse of bid-ask spread percentage. Tighter = higher score.

    Formula: max(0, 1 - ba_pct / max_spread_pct) * 100
    Legacy: strategy_scorer.py:409-412 — max_spread_pct hardcoded 100.0
    """
    ba_pct = named_values.get("bid_ask_spread_pct", 0)
    max_spread_pct = params.get("max_spread_pct", 100.0)
    if max_spread_pct <= 0:
        return 0.0
    raw = max(0.0, 1.0 - ba_pct / max_spread_pct)
    return raw * 100.0


@screening_formula("open_interest")
def open_interest(named_values: dict, params: dict) -> float:
    """Open interest as a scoring signal.

    Formula: min(100, open_interest / scale * 100)
    Legacy: strategy_scorer.py:432-433 — raw passthrough
    """
    oi = float(named_values.get("open_interest", 0))
    scale = params.get("scale", 10000.0)
    if scale <= 0:
        return 0.0
    return min(100.0, max(0.0, oi / scale * 100.0))
