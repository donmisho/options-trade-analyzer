"""
AI provider package.

Provides trade evaluation via Claude, with two adapter options:
  - AnthropicAdapter: Direct to Anthropic's API (for development)
  - FoundryAdapter: Through Azure Foundry (for production / Azure-native)

Switch between them with the AI_PROVIDER setting in .env:
  AI_PROVIDER=anthropic   → uses ANTHROPIC_API_KEY
  AI_PROVIDER=foundry     → uses FOUNDRY_RESOURCE + Entra ID auth
"""

from .base import AIProvider, TradeContext, TradeVerdict
from .prompts import (
    SYSTEM_PROMPT,
    build_trade_prompt,
    compute_exit_levels,
    pre_screen_trade,
)
from .anthropic_adapter import AnthropicAdapter
from .foundry_adapter import FoundryAdapter

__all__ = [
    "AIProvider",
    "TradeContext",
    "TradeVerdict",
    "AnthropicAdapter",
    "FoundryAdapter",
    "SYSTEM_PROMPT",
    "build_trade_prompt",
    "compute_exit_levels",
    "pre_screen_trade",
]
