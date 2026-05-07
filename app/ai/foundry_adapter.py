"""
Azure AI Foundry adapter — implements AIAdapter ABC.

Calls Claude via Azure AI Foundry's Anthropic-compatible endpoint
using raw httpx. All prompts are loaded from SKILL.md files via
skill_loader — no hardcoded prompt text in this module.

WHY Foundry instead of direct Anthropic:
  - Single gateway to any LLM via config change
  - AI traffic stays within Azure for compliance
  - Usage tracking, rate limiting, cost management in Azure portal
  - Same Anthropic Messages API format — just different base URL

WHY httpx instead of the Anthropic SDK:
  The Anthropic Python SDK does not yet expose the output_format
  parameter (structured outputs). Calling via raw httpx lets us
  pass the full Anthropic API payload, including output_format.
"""

import logging
from typing import Optional

import httpx

from app.ai.base import AIAdapter, ChatResult

logger = logging.getLogger(__name__)


class FoundryEvalAdapter(AIAdapter):
    """
    Calls Claude via Azure AI Foundry's Anthropic-compatible endpoint.

    Uses raw httpx (not the Anthropic SDK) to access the output_format
    structured output parameter that the SDK doesn't yet support.

    Usage:
        adapter = FoundryEvalAdapter(api_key="...", endpoint="https://...")
        result = await adapter.chat(system_prompt="...", user_message="...")
    """

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        model: str = "claude-sonnet-4-6",
    ):
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model
        self._client = httpx.AsyncClient(
            timeout=60.0,  # Trade evaluations can take 10-30s
            headers={
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
                "x-api-key": self.api_key,
            },
        )

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1500,
        extra_messages: Optional[list] = None,
    ) -> ChatResult:
        """
        Call the model with fully custom system + user prompts.

        extra_messages: optional additional turns to append after the initial
        user_message (e.g. assistant bad-response + correction turn for retry).

        Returns:
            {"text": str, "input_tokens": int, "output_tokens": int,
             "model": str, "provider": str}
        """
        messages = [{"role": "user", "content": user_message}]
        if extra_messages:
            messages.extend(extra_messages)

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages,
        }

        response = await self._client.post(self.endpoint, json=payload)
        if not response.is_success:
            logger.error(f"FoundryEvalAdapter.chat: {response.status_code}: {response.text[:300]}")
            response.raise_for_status()

        data = response.json()
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text = block["text"]
                break

        usage = data.get("usage", {})
        return {
            "text": text,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "model": data.get("model", self.model),
            "provider": "foundry",
        }

    async def health_check(self) -> bool:
        """Test connectivity to the Foundry endpoint."""
        try:
            payload = {
                "model": self.model,
                "max_tokens": 10,
                "messages": [
                    {"role": "user", "content": "Reply with just 'ok'."}
                ],
            }
            response = await self._client.post(self.endpoint, json=payload)
            return response.is_success
        except Exception as e:
            logger.error(f"FoundryEvalAdapter: Health check failed: {e}")
            return False

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
