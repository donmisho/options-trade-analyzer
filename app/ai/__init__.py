"""
app/ai — Structured output evaluation module.

This package provides the httpx-based Foundry adapter that uses
Anthropic's structured output feature for typed trade evaluations.

Separate from app/providers/ai (which uses the Anthropic SDK for
agent routes). This adapter calls the Foundry endpoint directly
via httpx, which is required to use the output_format parameter.
"""

from .schemas import TradeVerdict, FollowUpResponse, ThesisInsights, ExecutionPlan
from .foundry_adapter import FoundryEvalAdapter

__all__ = [
    "TradeVerdict",
    "FollowUpResponse",
    "ThesisInsights",
    "ExecutionPlan",
    "FoundryEvalAdapter",
]
