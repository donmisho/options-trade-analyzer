"""
Azure AI Foundry adapter for structured output trade evaluations.

WHY Foundry instead of direct Anthropic:
  - Single gateway to any LLM via config change
  - AI traffic stays within Azure for compliance
  - Usage tracking, rate limiting, cost management in Azure portal
  - Same Anthropic Messages API format — just different base URL

WHY httpx instead of the Anthropic SDK:
  The Anthropic Python SDK does not yet expose the output_format
  parameter (structured outputs). Calling via raw httpx lets us
  pass the full Anthropic API payload, including output_format.

STRUCTURED OUTPUTS:
  We pass an output_format parameter with a JSON schema that Claude
  is constrained to follow. This eliminates parsing fragility —
  the verdict is always a typed field, never parsed from prose.

PROMPT CACHING:
  The system prompt is marked with cache_control: {"type": "ephemeral"}.
  First call builds the cache (25% premium). Subsequent calls within
  5 minutes read from cache at 90% discount. Since traders typically
  evaluate multiple trades per session, calls 2-N are significantly
  faster and cheaper.
"""

import json
import logging
from typing import Optional

import httpx

from app.ai.schemas import TradeVerdict, FollowUpResponse
from app.ai.prompts import TRADE_EVALUATION_SYSTEM_PROMPT, FOLLOW_UP_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _build_json_schema(model_class) -> dict:
    """
    Convert a Pydantic model to the JSON schema format required by
    the Anthropic structured output API.

    WHY we do this manually instead of using the SDK's .parse() method:
    We're calling via HTTP (through Foundry), not the Python SDK directly.
    So we need to build the output_format payload ourselves.

    Anthropic requires:
      - additionalProperties: false at all object levels
      - all properties listed in required
    """
    schema = model_class.model_json_schema()

    def _enforce_strict(s):
        if s.get("type") == "object" and "properties" in s:
            s["additionalProperties"] = False
            s["required"] = list(s["properties"].keys())
            for prop in s["properties"].values():
                _enforce_strict(prop)
        if s.get("type") == "array" and "items" in s:
            _enforce_strict(s["items"])
        for def_schema in s.get("$defs", {}).values():
            _enforce_strict(def_schema)
        return s

    return _enforce_strict(schema)


class FoundryEvalAdapter:
    """
    Calls Claude via Azure AI Foundry's Anthropic-compatible endpoint.

    Uses raw httpx (not the Anthropic SDK) to access the output_format
    structured output parameter that the SDK doesn't yet support.

    Usage:
        adapter = FoundryEvalAdapter(api_key="...", endpoint="https://...")
        result = await adapter.evaluate_trade(user_message="...", original_context="...")
        print(result.verdict)  # "EXECUTE" | "WAIT" | "PASS"
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

    async def evaluate_trade(self, user_message: str) -> TradeVerdict:
        """
        Send a trade evaluation request and get a structured verdict.

        Args:
            user_message: The formatted trade data (market context + thesis + trade details).
                         This is the DYNAMIC part — it changes every call.

        Returns:
            TradeVerdict with typed verdict, analysis sections, and exit plan.
        """
        payload = {
            "model": self.model,
            "max_tokens": 2000,
            "system": [
                {
                    "type": "text",
                    "text": TRADE_EVALUATION_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [
                {"role": "user", "content": user_message}
            ],
            "output_format": {
                "type": "json_schema",
                "schema": _build_json_schema(TradeVerdict),
            },
        }

        response = await self._client.post(self.endpoint, json=payload)
        if not response.is_success:
            body = response.text
            logger.error(f"FoundryEvalAdapter: API error {response.status_code}: {body}")
            response.raise_for_status()

        data = response.json()

        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text = block["text"]
                break

        verdict = TradeVerdict.model_validate_json(text)

        usage = data.get("usage", {})
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_write = usage.get("cache_creation_input_tokens", 0)
        if cache_read > 0:
            logger.info(f"FoundryEvalAdapter: Cache HIT — {cache_read} tokens read from cache")
        elif cache_write > 0:
            logger.info(f"FoundryEvalAdapter: Cache MISS — {cache_write} tokens written to cache")

        return verdict

    async def follow_up(
        self,
        original_trade_context: str,
        original_verdict: str,
        question: str,
    ) -> FollowUpResponse:
        """
        Handle a follow-up question about a previously evaluated trade.

        WHY we send the original context again: Claude has no memory between
        API calls. We need to re-send the trade details so Claude can answer
        in context. The system prompt is still cached, so the cost is minimal.
        """
        user_message = f"""ORIGINAL TRADE EVALUATION CONTEXT:
{original_trade_context}

ORIGINAL VERDICT: {original_verdict}

FOLLOW-UP QUESTION:
{question}"""

        payload = {
            "model": self.model,
            "max_tokens": 1000,
            "system": [
                {
                    "type": "text",
                    "text": FOLLOW_UP_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [
                {"role": "user", "content": user_message}
            ],
            "output_format": {
                "type": "json_schema",
                "schema": _build_json_schema(FollowUpResponse),
            },
        }

        response = await self._client.post(self.endpoint, json=payload)
        if not response.is_success:
            logger.error(f"FoundryEvalAdapter: Follow-up error {response.status_code}: {response.text}")
            response.raise_for_status()

        data = response.json()

        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text = block["text"]
                break

        return FollowUpResponse.model_validate_json(text)

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
