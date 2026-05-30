"""
Shared providers reused across OTA adapters.

Modules:
    schwab_client   — market data access via ProviderRegistry (never hardcoded)
    black_scholes   — canonical B-S probability computation (OTA-716)
    sma             — SMA signal computation (OTA-717)
"""

from app.ota_adapters._shared.black_scholes import (
    ProbabilityMatrix,
    compute_probability_matrix,
    black_scholes_probability,
    build_probability_matrix,
    compute_naked_long_option_ev,
    pdf_prob,
)
from app.ota_adapters._shared.schwab_client import get_market_data_provider
from app.ota_adapters._shared.sma import compute_sma_signal

__all__ = [
    "get_market_data_provider",
    "ProbabilityMatrix",
    "compute_probability_matrix",
    "black_scholes_probability",
    "build_probability_matrix",
    "compute_naked_long_option_ev",
    "pdf_prob",
    "compute_sma_signal",
]
