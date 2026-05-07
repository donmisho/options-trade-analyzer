"""
app/ai — Unified AI adapter package.

All AI invocations go through adapters in this package:
  - FoundryEvalAdapter: httpx-based, calls Azure AI Foundry endpoint
  - AnthropicAdapter: SDK-based, calls Anthropic API directly (fallback)

Both implement the AIAdapter ABC with a single chat() entry point.
"""

from .base import AIAdapter, ChatResult
from .schemas import TradeVerdict, FollowUpResponse, ThesisInsights, ExecutionPlan
from .foundry_adapter import FoundryEvalAdapter
from .anthropic_adapter import AnthropicAdapter

__all__ = [
    "AIAdapter",
    "ChatResult",
    "TradeVerdict",
    "FollowUpResponse",
    "ThesisInsights",
    "ExecutionPlan",
    "FoundryEvalAdapter",
    "AnthropicAdapter",
]
