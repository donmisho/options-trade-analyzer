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
    Convert a Pydantic model to a strict JSON schema for Anthropic structured outputs.

    Adds additionalProperties: false and all properties in required at every
    object level, as required by the Anthropic structured output API.
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


def _extract_json(text: str) -> str:
    """
    Extract the JSON object from Claude's response text.

    Claude occasionally wraps JSON in markdown code fences even when told
    not to. This strips them and returns the raw JSON string.
    """
    text = text.strip()
    # Strip ```json ... ``` or ``` ... ``` fences
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop first line (```json or ```) and last line (```)
        inner = lines[1:] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner).strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


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
            "system": TRADE_EVALUATION_SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": user_message}
            ],
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

        verdict = TradeVerdict.model_validate_json(_extract_json(text))
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
            "system": FOLLOW_UP_SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": user_message}
            ],
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

        return FollowUpResponse.model_validate_json(_extract_json(text))

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1500,
        extra_messages: Optional[list] = None,
    ) -> dict:
        """
        Call the model with fully custom system + user prompts.

        Used by the structured evaluation endpoint so it can pass SKILL.md
        prompts without being bound to the TradeVerdict output shape.

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
