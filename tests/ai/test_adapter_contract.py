"""
Contract test for AIAdapter implementations.

Verifies that both FoundryEvalAdapter and AnthropicAdapter implement the
AIAdapter ABC and that chat() returns the correct ChatResult shape.

Requires live credentials — skip if not configured.
"""

import os
import pytest
from app.ai.base import AIAdapter, ChatResult


async def _assert_chat_contract(adapter: AIAdapter):
    """Verify an adapter's chat() returns the correct ChatResult shape."""
    assert isinstance(adapter, AIAdapter), f"{type(adapter).__name__} must inherit AIAdapter"

    result = await adapter.chat(
        system_prompt="You are a test assistant.",
        user_message="Reply with just 'OK'.",
        max_tokens=10,
    )
    assert isinstance(result, dict)
    for key in ("text", "input_tokens", "output_tokens", "model", "provider"):
        assert key in result, f"ChatResult missing key: {key}"
    assert isinstance(result["text"], str)
    assert isinstance(result["input_tokens"], int)
    assert isinstance(result["output_tokens"], int)
    assert isinstance(result["model"], str)
    assert isinstance(result["provider"], str)
    assert len(result["text"]) > 0


@pytest.mark.asyncio
async def test_foundry_adapter_contract():
    """FoundryEvalAdapter implements AIAdapter and returns ChatResult."""
    endpoint = os.environ.get("FOUNDRY_ENDPOINT")
    api_key = os.environ.get("FOUNDRY_API_KEY")
    if not endpoint or not api_key:
        pytest.skip("FOUNDRY_ENDPOINT and FOUNDRY_API_KEY not set")

    from app.ai.foundry_adapter import FoundryEvalAdapter
    adapter = FoundryEvalAdapter(api_key=api_key, endpoint=endpoint)
    await _assert_chat_contract(adapter)
    await adapter.close()


@pytest.mark.asyncio
async def test_anthropic_adapter_contract():
    """AnthropicAdapter implements AIAdapter and returns ChatResult."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    from app.ai.anthropic_adapter import AnthropicAdapter
    adapter = AnthropicAdapter(api_key=api_key)
    await _assert_chat_contract(adapter)


def test_foundry_is_ai_adapter_subclass():
    """FoundryEvalAdapter is a subclass of AIAdapter (no credentials needed)."""
    from app.ai.foundry_adapter import FoundryEvalAdapter
    assert issubclass(FoundryEvalAdapter, AIAdapter)


def test_anthropic_is_ai_adapter_subclass():
    """AnthropicAdapter is a subclass of AIAdapter (no credentials needed)."""
    from app.ai.anthropic_adapter import AnthropicAdapter
    assert issubclass(AnthropicAdapter, AIAdapter)
