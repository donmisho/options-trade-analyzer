"""
Canonical AI adapter contract.

All AI adapters (Foundry httpx, Anthropic SDK, future providers) implement
this ABC. Callers invoke chat() and receive a uniform ChatResult dict
regardless of which provider is behind the curtain.

See architecture-plan.md § AI Adapter Contract.
"""

from abc import ABC, abstractmethod
from typing import Optional, TypedDict


class ChatResult(TypedDict):
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str


class AIAdapter(ABC):
    """Canonical AI invocation contract per architecture-plan.md § AI Adapter Contract."""

    @abstractmethod
    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1500,
        extra_messages: Optional[list] = None,
    ) -> ChatResult:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    async def close(self) -> None:
        """Release long-lived resources (httpx clients, SDK connections)."""
