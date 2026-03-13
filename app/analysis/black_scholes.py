import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List

from scipy.stats import norm


@dataclass
class ProbabilityMatrix:
    price_levels: List[float]       # underlying price levels (x-axis)
    dates: List[date]               # [expiry-9, expiry-6, expiry-3, expiry]
    matrix: List[List[float]]       # matrix[date_idx][price_idx] = probability


def compute_probability_matrix(
    current_price: float,
    iv: float,                      # annualized implied volatility as decimal (0.25 = 25%)
    dte: int,                       # days to expiration
    risk_free_rate: float = 0.05,
    price_range_pct: float = 0.10,  # ±10%
    price_step: float = 10.0
) -> ProbabilityMatrix:
    """
    Returns probability of underlying being at each price level
    on dates: expiry-9, expiry-6, expiry-3, expiry.
    Uses Black-Scholes lognormal distribution — not Claude.
    """
    expiry = date.today() + timedelta(days=dte)
    snapshot_dates = [
        expiry - timedelta(days=9),
        expiry - timedelta(days=6),
        expiry - timedelta(days=3),
        expiry,
    ]
    # Clamp any snapshot date that falls before today
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
            # At expiry, distribution collapses to a point — assign all probability
            # to the price level closest to current_price
            probs = [0.0] * len(price_levels)
            closest_idx = min(
                range(len(price_levels)),
                key=lambda i: abs(price_levels[i] - current_price)
            )
            probs[closest_idx] = 1.0
            matrix.append(probs)
            continue

        # Lognormal parameters
        # ln(S_T/S_0) ~ N((r - 0.5*σ²)*T, σ²*T)
        mu = (risk_free_rate - 0.5 * iv ** 2) * t_years
        sigma = iv * math.sqrt(t_years)

        # Compute PDF-based probability density for each price level
        # Use the lognormal PDF: f(S) = 1/(S*σ*sqrt(2π)) * exp(-(ln(S/S0) - mu)²/(2σ²))
        # Then normalize over the discrete price levels so probabilities sum to 1.
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
