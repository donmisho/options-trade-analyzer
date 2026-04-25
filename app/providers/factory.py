"""
Provider factory: creates the right adapter based on provider name.

WHY a factory: The API endpoints don't pick providers directly. They ask
the factory for "the market data provider for this user." The factory looks
up the user's config, finds which provider they're using, and returns the
right adapter instance. This is how the system stays flexible — adding a
new provider means registering it here and writing its adapter class.

REGISTRATION: Each provider registers what interfaces it supports.
A CSV import might only support AccountProvider. The factory enforces this.
"""

import logging
from typing import Optional

from app.providers.base import MarketDataProvider, AccountProvider, TradingProvider, ContextSource
from app.providers.schwab import SchwabMarketData
from app.providers.finnhub_earnings import FinnhubEarningsSource
from app.core.secrets import SecretsManager
from app.core.config import settings

logger = logging.getLogger(__name__)

# Registry: source_id → factory function (no-arg callable → ContextSource instance)
# Stateless sources (no injected provider) are registered here directly.
# Sources that need an injected provider (e.g. SchwabPriceContextSource) are
# registered at runtime via register_context_source() after the provider is ready.
CONTEXT_SOURCE_REGISTRY: dict[str, ContextSource] = {
    "finnhub_earnings": FinnhubEarningsSource(),
}

# Registry: provider name → (capabilities, factory function)
# Each factory function takes (secrets_manager, user_id) and returns an adapter
PROVIDER_REGISTRY = {
    "schwab": {
        "capabilities": ["market_data"],
        "market_data": None,  # Set at runtime by init — needs token_manager
    },
}


class ProviderFactory:
    """
    Creates provider adapter instances based on user configuration.
    
    Usage:
        factory = ProviderFactory(secrets_manager)
        
        # Get the market data provider for a user
        provider = factory.get_market_data("schwab", user_id="don")
        chain = await provider.get_chain("QQQ")
    """

    def __init__(self, secrets_manager: SecretsManager):
        self.secrets = secrets_manager
        self._cache: dict[str, object] = {}

    def init_schwab(self, token_manager):
        """
        Initialize the Schwab provider with its token manager.

        WHY separate init: The Schwab adapter needs the SchwabTokenManager,
        which is created in main.py at startup. Unlike Tradier where we can
        create the adapter from just a token string, Schwab needs the full
        token manager for auto-refresh. So we register the factory function
        here after the token manager exists.
        """
        from app.providers.schwab import SchwabMarketData

        self._schwab_token_manager = token_manager

        # Now update the registry with a real factory function
        if "schwab" in PROVIDER_REGISTRY:
            PROVIDER_REGISTRY["schwab"]["market_data"] = (
                lambda secrets, user_id, env: SchwabMarketData(token_manager)
            )
            logger.info("ProviderFactory: Schwab market data adapter registered")

    def get_market_data(
        self,
        provider_name: str,
        user_id: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> MarketDataProvider:
        """
        Get a MarketDataProvider instance.
        
        Caches instances by (provider_name, user_id) to avoid creating
        new HTTP clients on every request.
        """
        cache_key = f"market_data:{provider_name}:{user_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        registry = PROVIDER_REGISTRY.get(provider_name)
        if not registry:
            raise ValueError(f"Unknown provider: {provider_name}")

        if "market_data" not in registry.get("capabilities", []):
            raise ValueError(f"Provider {provider_name} does not support market data")

        factory_fn = registry.get("market_data")
        if not factory_fn:
            raise ValueError(f"Provider {provider_name} market_data adapter not implemented")

        instance = factory_fn(self.secrets, user_id, environment)
        self._cache[cache_key] = instance
        return instance

    def get_account(
        self,
        provider_name: str,
        user_id: Optional[str] = None,
    ) -> AccountProvider:
        """Get an AccountProvider instance. (Phase 3)"""
        raise NotImplementedError("Account providers coming in Phase 3")

    def get_trading(
        self,
        provider_name: str,
        user_id: Optional[str] = None,
    ) -> TradingProvider:
        """Get a TradingProvider instance. (Phase 5)"""
        raise NotImplementedError("Trading providers coming in Phase 5")

    def list_providers(self) -> dict:
        """List all registered providers and their capabilities."""
        return {
            name: info["capabilities"]
            for name, info in PROVIDER_REGISTRY.items()
        }

    def register_context_source(self, source: ContextSource) -> None:
        """
        Register a ContextSource instance by its source_id.

        Used at startup to add sources that require injected providers
        (e.g. SchwabPriceContextSource needs the live SchwabMarketData instance).
        Stateless sources like FinnhubEarningsSource are pre-registered in
        CONTEXT_SOURCE_REGISTRY at module load time.
        """
        CONTEXT_SOURCE_REGISTRY[source.source_id] = source
        logger.info(f"ProviderFactory: context source registered — {source.source_id}")

    def get_context_source(self, source_id: str) -> ContextSource:
        """
        Return a registered ContextSource by source_id.

        Raises ValueError if the source_id is not registered.
        """
        source = CONTEXT_SOURCE_REGISTRY.get(source_id)
        if source is None:
            raise ValueError(
                f"Unknown context source: '{source_id}'. "
                f"Registered: {list(CONTEXT_SOURCE_REGISTRY.keys())}"
            )
        return source

    def list_context_sources(self) -> list[str]:
        """Return all registered context source IDs."""
        return list(CONTEXT_SOURCE_REGISTRY.keys())

    async def clear_cache(self):
        """Close all cached provider instances."""
        for key, instance in self._cache.items():
            if hasattr(instance, "close"):
                await instance.close()
        self._cache.clear()
