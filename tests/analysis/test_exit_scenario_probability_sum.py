"""
OTA-676 invariant test — probability mass sums to 1.0.

Asserts that compute_probability_matrix() produces a normalized probability
distribution (sums to 1.0 ± 1e-6) across the discrete price grid at expiry
for representative trade types.
"""

import pytest

from app.analysis.black_scholes import compute_probability_matrix


@pytest.mark.parametrize(
    "label,current_price,iv,dte",
    [
        ("Bull put credit (SPY 530)",   530.0, 0.18, 30),
        ("Bear put debit (QQQ 450)",    450.0, 0.25, 30),
        ("Single long put (MSFT 410P)", 416.78, 0.2731, 58),
        ("Single long call (AAPL 200C)", 195.0, 0.30, 45),
        ("High IV short DTE",          100.0, 0.80, 7),
        ("Low IV long DTE",            300.0, 0.12, 90),
    ],
    ids=lambda x: x if isinstance(x, str) else None,
)
def test_probability_sum_equals_one(label, current_price, iv, dte):
    """Probability mass at expiry must sum to 1.0 ± 1e-6."""
    pm = compute_probability_matrix(
        current_price=current_price,
        iv=iv,
        dte=dte,
        price_range_pct=0.50,
        price_step=5.0,
    )

    expiry_probs = pm.matrix[-1]
    total = sum(expiry_probs)

    assert abs(total - 1.0) < 1e-6, (
        f"{label}: probability sum = {total}, expected 1.0 ± 1e-6"
    )


def test_default_range_also_sums_to_one():
    """Even with the default ±10% range, probabilities must sum to 1.0."""
    pm = compute_probability_matrix(
        current_price=416.78,
        iv=0.2731,
        dte=58,
    )

    expiry_probs = pm.matrix[-1]
    total = sum(expiry_probs)

    assert abs(total - 1.0) < 1e-6, (
        f"Default range probability sum = {total}, expected 1.0 ± 1e-6"
    )
