"""
Shared Schwab market data provider access for OTA adapters.

Wraps the existing ``ProviderRegistry`` — never duplicates or hardcodes
the Schwab client. Adapters call ``get_market_data_provider()`` to obtain
the active ``MarketDataProvider`` instance routed through settings.

OTA-713
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from app.providers.base import MarketDataProvider
    from app.providers.factory import ProviderRegistry

logger = logging.getLogger(__name__)

_registry: ProviderRegistry | None = None


def init_registry(registry: ProviderRegistry) -> None:
    """Called once at app startup to inject the live ProviderRegistry."""
    global _registry
    _registry = registry
    logger.info("ota_adapters._shared.schwab_client: registry initialised")


def get_market_data_provider(
    user_id: str | None = None,
) -> MarketDataProvider:
    """Return the active market data provider via ProviderRegistry + settings.

    Uses ``settings.default_market_data_provider`` to select the provider,
    exactly as the route-level ``_get_provider()`` helpers do.
    """
    if _registry is None:
        raise RuntimeError(
            "ProviderRegistry not initialised — call init_registry() at startup"
        )
    return _registry.get_market_data(
        settings.default_market_data_provider,
        user_id=user_id,
    )
