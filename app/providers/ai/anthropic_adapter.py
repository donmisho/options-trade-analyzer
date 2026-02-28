"""
Anthropic direct API adapter.

WHY: This adapter calls Claude directly through Anthropic's API
(api.anthropic.com). It's the simplest path — just an API key
and the Anthropic Python SDK.

WHEN TO USE: Set AI_PROVIDER=anthropic in your .env file.
This is the default for development until your Azure Foundry
quota is approved.

COST: Claude Sonnet 4.5/4.6 is ~$3/million input tokens and
~$15/million output tokens. A single trade evaluation costs
roughly $0.01-0.02. Even heavy usage (20 evals/day) would be
well under $1/month.

AUTHENTICATION: Uses ANTHROPIC_API_KEY from your .env file
(loaded through SecretsManager for consistency).
"""

import logging
import re
from typing import Optional

from .base import AIProvider, TradeContext, TradeVerdict
from .prompts import SYSTEM_PROMPT, build_trade_prompt, compute_exit_levels

logger = logging.getLogger(__name__)

# The model to use — Sonnet 4.6 is the best balance of speed/quality/cost
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"


class AnthropicAdapter(AIProvider):
    """
    Calls Claude directly via Anthropic's API.
    
    Usage:
        adapter = AnthropicAdapter(api_key="sk-ant-...")
        verdict = await adapter.evaluate_trade(context)
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        """
        Initialize with an Anthropic API key.
        
        Args:
            api_key: Your Anthropic API key (starts with "sk-ant-")
            model: Which Claude model to use. Defaults to Sonnet.
        """
        self.model = model
        self._client = None
        self._api_key = api_key

    def _get_client(self):
        """
        Lazy-initialize the Anthropic client.
        
        WHY lazy: The anthropic package might not be installed yet.
        By importing it here instead of at the top of the file,
        we get a clear error message if it's missing, and the rest
        of the app can still start (e.g., if using Foundry instead).
        """
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
            except ImportError:
                raise RuntimeError(
                    "The 'anthropic' package is required for the Anthropic adapter. "
                    "Install it with: pip install anthropic --break-system-packages"
                )
        return self._client

    async def evaluate_trade(self, context: TradeContext) -> TradeVerdict:
        """
        Send trade context to Claude and get a verdict back.
        
        HOW IT WORKS:
        1. Build the prompt from the TradeContext (using prompts.py)
        2. Call Claude's Messages API with the system prompt + user prompt
        3. Parse the verdict (EXECUTE/WAIT/PASS) from the response
        4. Return a structured TradeVerdict with all the pieces
        """
        client = self._get_client()

        # Build the prompt
        user_prompt = build_trade_prompt(context)
        exit_levels = context.exit_levels or compute_exit_levels(context)

        logger.info(
            f"AnthropicAdapter: Evaluating {context.symbol} "
            f"{context.spread} via {self.model}"
        )

        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": user_prompt}
                ],
            )

            # Extract the text response
            raw_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    raw_text += block.text

            # Parse the verdict from the response
            verdict = self._parse_verdict(raw_text)

            # Token usage for cost tracking
            input_tokens = response.usage.input_tokens if response.usage else 0
            output_tokens = response.usage.output_tokens if response.usage else 0

            logger.info(
                f"AnthropicAdapter: Verdict={verdict}, "
                f"tokens={input_tokens}in/{output_tokens}out"
            )

            return TradeVerdict(
                verdict=verdict,
                raw_response=raw_text,
                exit_levels=exit_levels,
                model_used=self.model,
                provider="anthropic",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        except Exception as e:
            logger.error(f"AnthropicAdapter: API call failed: {e}")
            raise

    async def follow_up(
        self,
        question: str,
        conversation_history: list[dict],
    ) -> str:
        """
        Ask a follow-up question with full conversation context.
        
        The conversation_history includes the original evaluation
        and any prior follow-ups, so Claude can reference the
        specific trade being discussed.
        """
        client = self._get_client()

        # Build messages: system prompt + full history + new question
        messages = list(conversation_history)  # copy
        messages.append({"role": "user", "content": question})

        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=1500,
                system=SYSTEM_PROMPT,
                messages=messages,
            )

            raw_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    raw_text += block.text

            return raw_text

        except Exception as e:
            logger.error(f"AnthropicAdapter: Follow-up failed: {e}")
            raise

    async def health_check(self) -> bool:
        """
        Verify the Anthropic API connection is working.
        
        Sends a tiny request to confirm the API key is valid
        and the model is accessible.
        """
        try:
            client = self._get_client()
            response = await client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception as e:
            logger.error(f"AnthropicAdapter: Health check failed: {e}")
            return False

    @staticmethod
    def _parse_verdict(response_text: str) -> str:
        """
        Extract EXECUTE / WAIT / PASS from Claude's response.
        
        WHY parse: The UI shows the verdict as a color-coded banner
        (green/amber/red). We need to pull it out of the text reliably.
        
        Looks for patterns like:
          "⚡ VERDICT: EXECUTE"
          "VERDICT: WAIT"
          "**VERDICT: PASS**"
        """
        text_upper = response_text.upper()

        # Look for the verdict pattern
        match = re.search(r"VERDICT[:\s]+(\w+)", text_upper)
        if match:
            verdict = match.group(1).strip()
            if verdict in ("EXECUTE", "WAIT", "PASS"):
                return verdict

        # Fallback: look for the words anywhere near the top
        first_200 = text_upper[:200]
        if "EXECUTE" in first_200:
            return "EXECUTE"
        elif "PASS" in first_200:
            return "PASS"
        elif "WAIT" in first_200:
            return "WAIT"

        # If we can't parse it, default to WAIT (safest)
        logger.warning(
            "AnthropicAdapter: Could not parse verdict from response, "
            "defaulting to WAIT"
        )
        return "WAIT"
