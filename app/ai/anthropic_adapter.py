"""
Anthropic direct API adapter — implements AIAdapter ABC.

Calls Claude directly through Anthropic's API (api.anthropic.com)
using the Anthropic Python SDK. Used as fallback when Azure Foundry
endpoint is not configured.

Set AI_PROVIDER=anthropic in .env and provide ANTHROPIC_API_KEY.
"""

import logging
from typing import Optional

from app.ai.base import AIAdapter, ChatResult

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"


class AnthropicAdapter(AIAdapter):
    """Calls Claude directly via Anthropic's API."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.model = model
        self._client = None
        self._api_key = api_key

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
            except ImportError:
                raise RuntimeError(
                    "The 'anthropic' package is required for the Anthropic adapter. "
                    "Install it with: pip install anthropic"
                )
        return self._client

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1500,
        extra_messages: Optional[list] = None,
    ) -> ChatResult:
        client = self._get_client()
        messages = [{"role": "user", "content": user_message}]
        if extra_messages:
            messages.extend(extra_messages)
        response = await client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        return {
            "text": text,
            "input_tokens": response.usage.input_tokens if response.usage else 0,
            "output_tokens": response.usage.output_tokens if response.usage else 0,
            "model": self.model,
            "provider": "anthropic",
        }

    async def health_check(self) -> bool:
        try:
            client = self._get_client()
            await client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception as e:
            logger.error(f"AnthropicAdapter: Health check failed: {e}")
            return False
