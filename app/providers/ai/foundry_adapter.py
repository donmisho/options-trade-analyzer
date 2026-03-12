"""
Azure Foundry adapter for Claude.

WHY: This adapter calls Claude through Microsoft Foundry on Azure.
It uses the same Anthropic Python SDK but with the AnthropicFoundry
client class, which routes requests through your Azure resource
instead of directly to Anthropic.

ADVANTAGES OVER DIRECT:
  - Billing goes through your Azure subscription (one bill for everything)
  - Uses Entra ID auth (same as your SQL, Key Vault, App Service)
  - Full Azure Monitor/Log Analytics integration for cost tracking
  - Counts toward your Azure Consumption Commitment (MACC)
  - No separate Anthropic API key to manage

WHEN TO USE: Set AI_PROVIDER=foundry in your .env file, along with:
  - FOUNDRY_RESOURCE=ota-foundry  (your Foundry resource name)
  - FOUNDRY_DEPLOYMENT=claude-sonnet-4-6  (your deployment name)

AUTHENTICATION: Two options (configured in .env):
  1. Entra ID (recommended): Uses DefaultAzureCredential — same as your
     Key Vault and SQL connections. Works with `az login` locally and
     Managed Identity in production. No keys to manage.
  2. API key: Uses FOUNDRY_API_KEY from .env/Key Vault. Simpler to
     set up but less secure than Entra.
"""

import logging
import re
from typing import Optional

from .base import AIProvider, TradeContext, TradeVerdict
from .prompts import SYSTEM_PROMPT, build_trade_prompt, compute_exit_levels

logger = logging.getLogger(__name__)

# Default deployment name — matches what Azure creates when you deploy the model
DEFAULT_DEPLOYMENT = "claude-sonnet-4-6"


class FoundryAdapter(AIProvider):
    """
    Calls Claude through Azure Foundry.
    
    Uses the same Anthropic SDK but with the AnthropicFoundry client,
    which routes through your Azure resource for billing and auth.
    
    Usage:
        # With Entra ID (recommended):
        adapter = FoundryAdapter(resource="ota-foundry")
        
        # With API key:
        adapter = FoundryAdapter(
            resource="ota-foundry",
            api_key="your-foundry-api-key"
        )
    """

    def __init__(
        self,
        resource: str,
        deployment: str = DEFAULT_DEPLOYMENT,
        api_key: Optional[str] = None,
    ):
        """
        Initialize the Foundry adapter.
        
        Args:
            resource: Your Azure Foundry resource name (e.g., "ota-foundry").
                     The SDK builds the URL: https://{resource}.services.ai.azure.com/anthropic/
            deployment: The deployment name you chose when deploying the model.
                       This becomes the "model" parameter in API calls.
            api_key: Optional Foundry API key. If not provided, uses Entra ID
                    via DefaultAzureCredential (recommended).
        
        WHY resource not URL: The SDK constructs the full URL from the
        resource name. This keeps your config simple — just the resource
        name, not a long URL that could have typos.
        """
        self.resource = resource
        self.deployment = deployment
        self._api_key = api_key
        self._client = None

    def _get_client(self):
        """
        Lazy-initialize the Foundry client.
        
        WHY lazy: Same reason as the Anthropic adapter — the azure.identity
        package might not be installed yet, and we want a clear error message.
        Also, Entra token providers need to be created at call time, not import time.
        """
        if self._client is None:
            try:
                from anthropic import AsyncAnthropicFoundry
            except ImportError:
                raise RuntimeError(
                    "The 'anthropic' package is required for the Foundry adapter. "
                    "Install it with: pip install anthropic --break-system-packages"
                )

            if self._api_key:
                # API key authentication (simpler but less secure)
                logger.info(
                    f"FoundryAdapter: Connecting to {self.resource} "
                    f"with API key auth"
                )
                self._client = AsyncAnthropicFoundry(
                    api_key=self._api_key,
                    resource=self.resource,
                )
            else:
                # Entra ID authentication (recommended)
                # Uses DefaultAzureCredential which:
                #   - Locally: uses your `az login` session
                #   - In Azure: uses Managed Identity
                try:
                    from azure.identity import (
                        DefaultAzureCredential,
                        get_bearer_token_provider,
                    )
                except ImportError:
                    raise RuntimeError(
                        "The 'azure-identity' package is required for Entra auth. "
                        "Install with: pip install azure-identity --break-system-packages"
                    )

                logger.info(
                    f"FoundryAdapter: Connecting to {self.resource} "
                    f"with Entra ID auth (DefaultAzureCredential)"
                )
                token_provider = get_bearer_token_provider(
                    DefaultAzureCredential(),
                    "https://cognitiveservices.azure.com/.default",
                )
                self._client = AsyncAnthropicFoundry(
                    resource=self.resource,
                    azure_ad_token_provider=token_provider,
                )

        return self._client

    async def evaluate_trade(self, context: TradeContext) -> TradeVerdict:
        """
        Send trade context to Claude via Foundry and get a verdict back.
        
        This works identically to the Anthropic adapter — same prompt,
        same response parsing. The only difference is the client class
        routes the request through Azure instead of directly to Anthropic.
        """
        client = self._get_client()

        user_prompt = build_trade_prompt(context)
        exit_levels = context.exit_levels or compute_exit_levels(context)

        logger.info(
            f"FoundryAdapter: Evaluating {context.symbol} "
            f"{context.spread} via {self.resource}/{self.deployment}"
        )

        try:
            response = await client.messages.create(
                model=self.deployment,  # deployment name, not model ID
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": user_prompt}
                ],
            )

            raw_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    raw_text += block.text

            verdict = self._parse_verdict(raw_text)

            input_tokens = response.usage.input_tokens if response.usage else 0
            output_tokens = response.usage.output_tokens if response.usage else 0

            logger.info(
                f"FoundryAdapter: Verdict={verdict}, "
                f"tokens={input_tokens}in/{output_tokens}out"
            )

            return TradeVerdict(
                verdict=verdict,
                raw_response=raw_text,
                exit_levels=exit_levels,
                model_used=self.deployment,
                provider="foundry",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        except Exception as e:
            logger.error(f"FoundryAdapter: API call failed: {e}")
            raise

    async def follow_up(
        self,
        question: str,
        conversation_history: list[dict],
    ) -> str:
        """
        Ask a follow-up question via Foundry.
        """
        client = self._get_client()

        messages = list(conversation_history)
        messages.append({"role": "user", "content": question})

        try:
            response = await client.messages.create(
                model=self.deployment,
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
            logger.error(f"FoundryAdapter: Follow-up failed: {e}")
            raise

    async def chat(self, system_prompt: str, user_message: str, max_tokens: int) -> dict:
        """Call the model with fully custom system/user prompts (used by agent routes)."""
        client = self._get_client()
        response = await client.messages.create(
            model=self.deployment,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        return {
            "text": text,
            "input_tokens": response.usage.input_tokens if response.usage else 0,
            "output_tokens": response.usage.output_tokens if response.usage else 0,
            "model": self.deployment,
            "provider": "foundry",
        }

    async def health_check(self) -> bool:
        """
        Verify the Foundry connection is working.
        """
        try:
            client = self._get_client()
            response = await client.messages.create(
                model=self.deployment,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception as e:
            logger.error(f"FoundryAdapter: Health check failed: {e}")
            return False

    @staticmethod
    def _parse_verdict(response_text: str) -> str:
        """
        Extract EXECUTE / WAIT / PASS from Claude's response.
        Same logic as the Anthropic adapter — shared for consistency.
        """
        text_upper = response_text.upper()

        match = re.search(r"VERDICT[:\s]+(\w+)", text_upper)
        if match:
            verdict = match.group(1).strip()
            if verdict in ("EXECUTE", "WAIT", "PASS"):
                return verdict

        first_200 = text_upper[:200]
        if "EXECUTE" in first_200:
            return "EXECUTE"
        elif "PASS" in first_200:
            return "PASS"
        elif "WAIT" in first_200:
            return "WAIT"

        logger.warning(
            "FoundryAdapter: Could not parse verdict from response, "
            "defaulting to WAIT"
        )
        return "WAIT"
