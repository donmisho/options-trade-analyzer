"""
Phase 7 — AMZN April 22 regression fixtures (OTA-504 / OTA-509 / OTA-510)

These tests pin the exact AMZN inputs that produced contradictions in production
and verify that the full validation → retry → fallback cycle behaves correctly.

Fixture inputs (April 22 live data):
  price=255.36, sma_8=252.52, sma_21=252.39, sma_50=251.86
  expected_value=-5.86, p_max_profit=0.2985, p_max_loss=0.5666
"""

import math
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.validators.narrative_grounding import (
    EvaluationFields,
    ValidationError,
    validate_narrative,
)

# ── Fallback constant (must match evaluation_routes.py) ──────────────────────
FALLBACK_TEXT = (
    "Structured evaluation complete. See computed fields for details. "
    "Narrative unavailable this cycle."
)


# ── AMZN fixture ──────────────────────────────────────────────────────────────

def amzn_fields() -> EvaluationFields:
    """Exact inputs from AMZN April 22 live evaluation."""
    return EvaluationFields(
        price=255.36,
        sma_8=252.52,
        sma_21=252.39,
        sma_50=251.86,
        expected_value=-5.86,
    )


# AMZN contradicting narrative — reproduces the live production failure
AMZN_BAD_NARRATIVE = (
    "The positive EV of $89 and strong IV rank of 42% support the trade. "
    "AMZN sits just below all three SMAs with mixed trend alignment, "
    "with SMA-21 at 257.64 acting as overhead resistance."
)

# Corrected narrative — what Claude should say
AMZN_GOOD_NARRATIVE = (
    "The negative EV of -5.86 disqualifies this trade under current conditions. "
    "AMZN trades above all three SMAs (8/21/50) with bullish trend alignment; "
    "watch SMA-8 at 252.52 as the nearest support level."
)


# ── Validator: AMZN bad narrative flags all three codes ──────────────────────

class TestAmznRegressionValidator:

    def test_bad_narrative_flags_ev_contradiction(self):
        """AMZN bad narrative must produce EV_CONTRADICTION."""
        errors = validate_narrative(AMZN_BAD_NARRATIVE, amzn_fields())
        codes = [e.code for e in errors]
        assert "EV_CONTRADICTION" in codes

    def test_bad_narrative_flags_sma_position(self):
        """AMZN bad narrative must produce SMA_POSITION."""
        errors = validate_narrative(AMZN_BAD_NARRATIVE, amzn_fields())
        codes = [e.code for e in errors]
        assert "SMA_POSITION" in codes

    def test_bad_narrative_flags_sma_hallucination(self):
        """'SMA-21 at 257.64' vs input set ~252.x → SMA_HALLUCINATION."""
        errors = validate_narrative(AMZN_BAD_NARRATIVE, amzn_fields())
        codes = [e.code for e in errors]
        assert "SMA_HALLUCINATION" in codes

    def test_bad_narrative_total_error_count(self):
        """All three codes fire → at least 3 errors total."""
        errors = validate_narrative(AMZN_BAD_NARRATIVE, amzn_fields())
        assert len(errors) >= 3

    def test_good_narrative_zero_errors(self):
        """Corrected AMZN narrative passes all grounding rules."""
        errors = validate_narrative(AMZN_GOOD_NARRATIVE, amzn_fields())
        assert errors == []

    def test_p_max_profit_and_p_max_loss_in_input(self):
        """EvaluationFields accepts p_max_profit / p_max_loss fixture values without error."""
        # These are not validator fields yet, but confirm the fixture is self-consistent
        assert amzn_fields().price == 255.36
        assert amzn_fields().expected_value == -5.86
        # p_max_profit=0.2985 and p_max_loss=0.5666 are referenced in Phase 7 spec;
        # they inform the trade data but are not yet validator inputs — no assertion here


# ── Golden-path fixture ───────────────────────────────────────────────────────

def golden_fields() -> EvaluationFields:
    """Golden-path: positive EV, price above all SMAs."""
    return EvaluationFields(
        price=260.00,
        sma_8=252.52,
        sma_21=252.39,
        sma_50=251.86,
        expected_value=89.00,
    )


GOLDEN_NARRATIVE = (
    "AMZN trades above all three SMAs with bullish alignment confirming trend continuation. "
    "The positive expected value supports entry; IV rank of 38% is favorable for this structure. "
    "Watch SMA-8 at 252.52 as key near-term support — a close below would invalidate the thesis."
)


class TestGoldenPath:

    def test_golden_narrative_zero_errors(self):
        """Golden-path narrative produces zero validator errors."""
        errors = validate_narrative(GOLDEN_NARRATIVE, golden_fields())
        assert errors == []

    def test_golden_path_positive_ev_not_flagged(self):
        """Positive EV in narrative + positive computed EV → EV rule silent."""
        errors = validate_narrative(GOLDEN_NARRATIVE, golden_fields())
        ev_errors = [e for e in errors if e.code == "EV_CONTRADICTION"]
        assert ev_errors == []

    def test_golden_path_sma_not_flagged(self):
        """Correct SMA positioning and values → SMA rules silent."""
        errors = validate_narrative(GOLDEN_NARRATIVE, golden_fields())
        sma_errors = [e for e in errors if e.code in ("SMA_POSITION", "SMA_HALLUCINATION")]
        assert sma_errors == []


# ── Retry / fallback simulation ───────────────────────────────────────────────
#
# Simulates the validation block from evaluate_structured() in evaluation_routes.py.
# Uses AsyncMock so we can exercise the retry + fallback logic without a live
# Foundry endpoint or FastAPI app.

async def _run_validation_cycle(
    initial_narrative: str,
    computed_fields: EvaluationFields,
    mock_adapter,
    system_prompt: str = "SYSTEM",
    user_message: str = "USER",
) -> tuple[str, bool, bool]:
    """
    Mirrors the OTA-504 validation block from evaluate_structured().

    Returns: (final_narrative, retry_triggered, fallback_used)
    """
    errors = validate_narrative(initial_narrative, computed_fields)
    if not errors:
        return initial_narrative, False, False

    # One retry
    retry_result = await mock_adapter.chat(system_prompt, user_message, max_tokens=3000)
    retry_narrative = retry_result["text"]
    retry_errors = validate_narrative(retry_narrative, computed_fields)

    if not retry_errors:
        return retry_narrative, True, False

    # Both attempts failed → fallback
    return FALLBACK_TEXT, True, True


@pytest.mark.asyncio
async def test_retry_succeeds_returns_clean_narrative():
    """
    First call returns bad narrative → validator fires → retry returns clean narrative
    → clean narrative is used, fallback NOT triggered.
    """
    mock_adapter = MagicMock()
    mock_adapter.chat = AsyncMock(return_value={"text": AMZN_GOOD_NARRATIVE, "input_tokens": 0, "output_tokens": 0})

    final, retry_triggered, fallback_used = await _run_validation_cycle(
        initial_narrative=AMZN_BAD_NARRATIVE,
        computed_fields=amzn_fields(),
        mock_adapter=mock_adapter,
    )

    assert retry_triggered is True
    assert fallback_used is False
    assert final == AMZN_GOOD_NARRATIVE
    assert validate_narrative(final, amzn_fields()) == []


@pytest.mark.asyncio
async def test_retry_also_fails_triggers_fallback():
    """
    First call bad → validator fires → retry also returns bad narrative
    → fallback text applied, NOT the hallucinated original.
    """
    mock_adapter = MagicMock()
    mock_adapter.chat = AsyncMock(return_value={"text": AMZN_BAD_NARRATIVE, "input_tokens": 0, "output_tokens": 0})

    final, retry_triggered, fallback_used = await _run_validation_cycle(
        initial_narrative=AMZN_BAD_NARRATIVE,
        computed_fields=amzn_fields(),
        mock_adapter=mock_adapter,
    )

    assert retry_triggered is True
    assert fallback_used is True
    assert final == FALLBACK_TEXT
    # Critically: the hallucinated original is NOT in the final output
    assert "positive EV of $89" not in final
    assert "257.64" not in final


@pytest.mark.asyncio
async def test_golden_path_no_retry():
    """
    Clean narrative on first pass → adapter.chat never called, no retry, no fallback.
    """
    mock_adapter = MagicMock()
    mock_adapter.chat = AsyncMock()

    final, retry_triggered, fallback_used = await _run_validation_cycle(
        initial_narrative=GOLDEN_NARRATIVE,
        computed_fields=golden_fields(),
        mock_adapter=mock_adapter,
    )

    assert retry_triggered is False
    assert fallback_used is False
    assert final == GOLDEN_NARRATIVE
    mock_adapter.chat.assert_not_called()


@pytest.mark.asyncio
async def test_retry_called_exactly_once():
    """Retry is capped at 1 — adapter.chat called at most once on bad narrative."""
    mock_adapter = MagicMock()
    mock_adapter.chat = AsyncMock(return_value={"text": AMZN_BAD_NARRATIVE, "input_tokens": 0, "output_tokens": 0})

    await _run_validation_cycle(
        initial_narrative=AMZN_BAD_NARRATIVE,
        computed_fields=amzn_fields(),
        mock_adapter=mock_adapter,
    )

    assert mock_adapter.chat.call_count == 1
