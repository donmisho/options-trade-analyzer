"""
Shared providers reused across OTA adapters.

Modules:
    schwab_client   — market data access via ProviderRegistry (never hardcoded)
    black_scholes   — canonical B-S probability computation (body deferred to OTA-716)
"""

from app.ota_adapters._shared.schwab_client import get_market_data_provider
from app.ota_adapters._shared.black_scholes import compute_probability_matrix

__all__ = [
    "get_market_data_provider",
    "compute_probability_matrix",
]
