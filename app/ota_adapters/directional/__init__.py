"""
Directional thesis comparison adapter — OTA-752 feature.

Implements the Insight Engine §5 input adapter contract for the
directional comparison surface: given a thesis (ticker, direction,
conviction, target price, timeframe, budget), produce one candidate
per (structure, strikes, expiry) combination compatible with the
thesis direction.

OTA-753 (adapter + catalog)
"""

from app.ota_adapters.directional.adapter import DirectionalAdapter

__all__ = ["DirectionalAdapter"]
