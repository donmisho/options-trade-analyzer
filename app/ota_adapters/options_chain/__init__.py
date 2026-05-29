"""
Options-chain screening adapter — OTA-712 feature.

Implements the Insight Engine §5 input adapter contract for the
options-chain screening surface: produce candidates from Schwab chain
data, declare the input catalog, and provide a COMPUTED callback.

OTA-713 (skeleton + interface), OTA-714–723 (producers + catalog)
"""

from app.ota_adapters.options_chain.adapter import OptionsChainAdapter

__all__ = ["OptionsChainAdapter"]
