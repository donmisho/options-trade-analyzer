"""
Narrative Grounding Validator — OTA-504 (OTA-509 + OTA-510)

Runs pre-emission to catch narrative-vs-data contradictions in Claude's
claude_read prose before it reaches the client.

Rules:
  OTA-509 — validate_ev_grounding:   blocks prose asserting positive EV when computed EV is negative
  OTA-510 — validate_sma_grounding:  blocks positional contradictions + numerical hallucinations

Usage:
    fields = EvaluationFields(price=255.36, sma_8=252.52, sma_21=252.39,
                               sma_50=251.86, expected_value=-5.86)
    errors = validate_narrative(narrative_text, fields)
    # empty list → grounded; non-empty → regenerate or use fallback
"""

import math
import re
from dataclasses import dataclass
from typing import Callable


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class ValidationError:
    code: str           # e.g. "EV_CONTRADICTION"
    message: str        # human-readable description of the violation
    field_context: str  # which input field was contradicted


@dataclass
class EvaluationFields:
    price: float
    sma_8: float
    sma_21: float
    sma_50: float
    expected_value: float  # total_ev from exit scenario; use math.nan if unavailable


# ── OTA-509: EV grounding rule ────────────────────────────────────────────────

def validate_ev_grounding(
    narrative_text: str,
    computed_fields: EvaluationFields,
) -> list[ValidationError]:
    """
    Block prose that asserts positive/favorable EV when computed EV is negative.

    Only fires when expected_value < 0. Does NOT flag narratives that correctly
    acknowledge negative EV (e.g. "the negative EV signals caution").
    """
    errors: list[ValidationError] = []

    if math.isnan(computed_fields.expected_value):
        return errors  # EV not available — skip rule

    if computed_fields.expected_value < 0:
        # Match "positive EV", "favorable EV", or "EV of $89" / "EV of 89"
        # Does NOT match "negative EV", "EV is negative", "EV of -5.86"
        if re.search(
            r"positive\s+ev|favorable\s+ev|ev\s+of\s+\$?\d",
            narrative_text,
            re.IGNORECASE,
        ):
            errors.append(ValidationError(
                code="EV_CONTRADICTION",
                message=(
                    f"Narrative asserts positive EV but computed EV is "
                    f"{computed_fields.expected_value:.2f}"
                ),
                field_context="expected_value",
            ))

    return errors


# ── OTA-510: SMA grounding rule ───────────────────────────────────────────────

def validate_sma_grounding(
    narrative_text: str,
    computed_fields: EvaluationFields,
) -> list[ValidationError]:
    """
    Two sub-rules:
      A — positional contradiction: narrative claims price is below SMA-50
          when price is actually above it (generalises to "all three SMAs").
      B — numerical hallucination: narrative cites an SMA value not present
          in the input set (tolerance: 10 cents).
    """
    errors: list[ValidationError] = []

    # ── Sub-rule A: positional contradiction ─────────────────────────────────
    # Fires when price > sma_50 but narrative claims "below ... 50" or "below all SMAs"
    if computed_fields.price > computed_fields.sma_50:
        if re.search(
            r"below.{0,30}(?:50|all\s+sma|all\s+three\s+sma)|under.{0,10}50",
            narrative_text,
            re.IGNORECASE,
        ):
            errors.append(ValidationError(
                code="SMA_POSITION",
                message=(
                    f"Narrative asserts below SMA-50 but price "
                    f"({computed_fields.price:.2f}) > SMA-50 ({computed_fields.sma_50:.2f})"
                ),
                field_context="sma_50",
            ))

    # ── Sub-rule B: numerical hallucination ──────────────────────────────────
    # Collect the three known SMA values; filter out NaN entries
    sma_values_in_input: set[float] = {
        v for v in (computed_fields.sma_8, computed_fields.sma_21, computed_fields.sma_50)
        if not math.isnan(v)
    }

    if sma_values_in_input:
        # Match patterns: "SMA-21 at 257.64", "SMA21 at 257.64", "sma 50 at $252.39"
        cited_values = re.findall(
            r"sma[- ]?\d+\s+at\s+\$?(\d+\.\d+)",
            narrative_text,
            re.IGNORECASE,
        )
        for v_str in cited_values:
            v = float(v_str)
            nearest = min(sma_values_in_input, key=lambda x: abs(x - v))
            if abs(v - nearest) > 0.10:  # 10-cent tolerance
                errors.append(ValidationError(
                    code="SMA_HALLUCINATION",
                    message=(
                        f"Narrative cites SMA value {v:.2f} not in input set "
                        f"{sorted(sma_values_in_input)}"
                    ),
                    field_context=f"sma_value_{v_str}",
                ))

    return errors


# ── Rule registry + composed entry point ─────────────────────────────────────

_RULES: list[Callable] = [
    validate_ev_grounding,
    validate_sma_grounding,
]


def validate_narrative(
    narrative_text: str,
    computed_fields: EvaluationFields,
) -> list[ValidationError]:
    """Run all grounding rules. Empty list = narrative is grounded."""
    errors: list[ValidationError] = []
    for rule in _RULES:
        errors.extend(rule(narrative_text, computed_fields))
    return errors
