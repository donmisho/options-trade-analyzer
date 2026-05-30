"""
Shared Black-Scholes probability computation for OTA adapters.

This module is the canonical home for all Black-Scholes math used by
adapters and the legacy analysis/evaluation pipelines.  Moved here in
OTA-716 from ``app/analysis/black_scholes.py``; the old module now
re-exports from this location for backward compatibility.

Public API
----------
ProbabilityMatrix          — dataclass returned by compute_probability_matrix
compute_probability_matrix — lognormal PDF-based probability matrix
black_scholes_probability  — CDF P(S >= K) at expiry
build_probability_matrix   — dict-format matrix for Claude evaluation prompt
compute_naked_long_option_ev — total EV ($/contract) for a naked long option
pdf_prob                   — discrete PDF probability for a price bucket

OTA-713 (placeholder), OTA-716 (body)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List

from scipy.stats import norm


# ── ProbabilityMatrix dataclass ────────────────────────────────────────


@dataclass
class ProbabilityMatrix:
    price_levels: List[float]       # underlying price levels (x-axis)
    dates: List[date]               # [expiry-9, expiry-6, expiry-3, expiry]
    matrix: List[List[float]]       # matrix[date_idx][price_idx] = probability


# ── Core functions ─────────────────────────────────────────────────────


def compute_probability_matrix(
    current_price: float,
    iv: float,                      # annualized implied volatility as decimal (0.25 = 25%)
    dte: int,                       # days to expiration
    risk_free_rate: float = 0.05,
    price_range_pct: float = 0.10,  # +/-10%
    price_step: float = 10.0,
) -> ProbabilityMatrix:
    """
    Returns probability of underlying being at each price level
    on dates: expiry-9, expiry-6, expiry-3, expiry.
    Uses Black-Scholes lognormal distribution -- not Claude.
    """
    expiry = date.today() + timedelta(days=dte)
    snapshot_dates = [
        expiry - timedelta(days=9),
        expiry - timedelta(days=6),
        expiry - timedelta(days=3),
        expiry,
    ]
    today = date.today()
    snapshot_dates = [max(d, today) for d in snapshot_dates]

    # Build price levels
    low = current_price * (1 - price_range_pct)
    high = current_price * (1 + price_range_pct)
    price_levels: List[float] = []
    p = math.floor(low / price_step) * price_step
    while p <= high + price_step / 2:
        price_levels.append(round(p, 2))
        p += price_step

    matrix: List[List[float]] = []
    for snap_date in snapshot_dates:
        t_days = max((snap_date - today).days, 0)
        t_years = t_days / 365.0

        if t_years == 0:
            probs = [0.0] * len(price_levels)
            closest_idx = min(
                range(len(price_levels)),
                key=lambda i: abs(price_levels[i] - current_price),
            )
            probs[closest_idx] = 1.0
            matrix.append(probs)
            continue

        mu = (risk_free_rate - 0.5 * iv ** 2) * t_years
        sigma = iv * math.sqrt(t_years)

        raw = []
        for s in price_levels:
            if s <= 0:
                raw.append(0.0)
                continue
            z = (math.log(s / current_price) - mu) / sigma
            pdf_val = norm.pdf(z) / (s * sigma)
            raw.append(pdf_val)

        total = sum(raw)
        if total > 0:
            probs = [r / total for r in raw]
        else:
            probs = [1.0 / len(price_levels)] * len(price_levels)

        matrix.append(probs)

    return ProbabilityMatrix(
        price_levels=price_levels,
        dates=snapshot_dates,
        matrix=matrix,
    )


# ── Phase 2.9 -- CDF-based probability functions for the A2 scorer ────


def black_scholes_probability(
    S: float,       # current underlying price
    K: float,       # target price level
    T: float,       # time to expiry in years
    r: float,       # risk-free rate (e.g. 0.05)
    sigma: float,   # implied volatility as decimal (e.g. 0.30)
) -> float:
    """
    Probability that price >= K at time T using log-normal distribution.
    Returns float between 0.0 and 1.0.
    """
    if T <= 0 or sigma <= 0:
        return 1.0 if S >= K else 0.0
    d2 = (math.log(S / K) + (r - 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return float(norm.cdf(d2))


def build_probability_matrix(
    current_price: float,
    iv: float,              # decimal e.g. 0.30
    dte: int,               # days to expiry
    risk_free_rate: float = 0.05,
    price_range_pct: float = 0.10,   # +/- 10%
    price_step: float = 10.0,        # $10 steps
) -> Dict:
    """
    Build a probability matrix showing P(price >= level) at 4 time slices.
    Returns dict matching the schema expected by Claude's evaluation prompt.
    """
    T_full = dte / 365.0

    low = current_price * (1 - price_range_pct)
    high = current_price * (1 + price_range_pct)
    levels = []
    level = math.floor(low / price_step) * price_step
    while level <= high:
        levels.append(round(level, 2))
        level += price_step

    time_slices = {
        "expiry": T_full,
        "expiry_minus_3": max((dte - 3) / 365.0, 0.001),
        "expiry_minus_6": max((dte - 6) / 365.0, 0.001),
        "expiry_minus_9": max((dte - 9) / 365.0, 0.001),
    }

    matrix = {}
    for slice_name, T in time_slices.items():
        matrix[slice_name] = {
            str(level): round(black_scholes_probability(
                current_price, level, T, risk_free_rate, iv,
            ), 4)
            for level in levels
        }

    return {
        "current_price": current_price,
        "iv": iv,
        "dte": dte,
        "price_levels": levels,
        "probabilities": matrix,
    }


# ── Naked-option EV (moved from evaluation_routes.py OTA-676) ─────────


def compute_naked_long_option_ev(
    option_type: str,
    strike: float,
    underlying_price: float,
    iv: float,
    days_to_exp: int,
    entry_price: float,
    risk_free_rate: float = 0.05,
) -> float:
    """
    Compute total expected value in dollars per contract for a naked
    single-leg long option using the canonical lognormal probability matrix.

    Uses compute_probability_matrix() with a wide price range (+/-50%) to
    capture the full distribution including the modal outcome (option
    expiring worthless for OTM trades).

    Returns EV in dollars per contract.
    """
    pm = compute_probability_matrix(
        current_price=underlying_price,
        iv=iv,
        dte=max(days_to_exp, 1),
        risk_free_rate=risk_free_rate,
        price_range_pct=0.50,
        price_step=5.0,
    )

    expiry_probs = pm.matrix[-1]
    is_put = option_type.upper() in ("PUT", "P")

    total_ev = 0.0
    for price, prob in zip(pm.price_levels, expiry_probs):
        if is_put:
            intrinsic = max(0.0, strike - price)
        else:
            intrinsic = max(0.0, price - strike)
        pnl = (intrinsic - entry_price) * 100
        total_ev += pnl * prob

    return round(total_ev, 4)


# ── Discrete PDF probability (moved from evaluation_routes.py) ─────────


def pdf_prob(
    S0: float, K: float, dte: int, iv: float, r: float, step: float = 5.0,
) -> float:
    """Discrete PDF probability: P(underlying in [K-step/2, K+step/2] at expiry)."""
    T = max(dte / 365.0, 0.001)
    p_lo = black_scholes_probability(S0, K - step / 2, T, r, iv)
    p_hi = black_scholes_probability(S0, K + step / 2, T, r, iv)
    return round(max(0.0, p_lo - p_hi), 6)
