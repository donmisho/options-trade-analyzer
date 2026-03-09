"""
Structured output schemas for AI trade evaluation.

WHY structured outputs: Instead of asking Claude to return formatted text
and then parsing it with regex/string matching, we define a JSON schema
that Claude is CONSTRAINED to follow at the token generation level. This
means:
  - The verdict is always one of exactly 3 values (no parsing ambiguity)
  - Every section is a typed field (no missing sections)
  - The frontend receives clean JSON it can render directly
  - Follow-up responses also have a guaranteed structure

The Anthropic API's structured output feature compiles this schema into
a grammar that restricts token generation. It's not "asking nicely" —
it's a hard constraint.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional


class PriceAlert(BaseModel):
    """A single price-based alert in the exit plan."""
    label: str = Field(description="Short name like 'Profit trigger' or 'Stop loss'")
    price_or_value: str = Field(description="The price level or spread value, e.g. '$445.00' or '$1.60'")
    action: str = Field(description="What to do when this level is hit")


class ExitPlan(BaseModel):
    """Structured exit plan with price alerts and time rules."""
    underlying_alerts: list[PriceAlert] = Field(
        description="Price alerts based on the underlying stock price"
    )
    spread_value_alerts: list[PriceAlert] = Field(
        description="Alerts based on the spread/option value itself"
    )
    time_rules: list[str] = Field(
        description="Time-based rules like 'Close if flat after 10 days'"
    )


class TradeVerdict(BaseModel):
    """
    The complete structured response from Claude for a trade evaluation.

    This is the output_format schema passed to the Anthropic API.
    Claude MUST return JSON matching this exact shape.
    """
    verdict: Literal["EXECUTE", "WAIT", "PASS"] = Field(
        description="The trading decision"
    )
    verdict_rationale: str = Field(
        description="One sentence explaining the verdict"
    )
    thesis_alignment: str = Field(
        description="Analysis of whether SMAs and technicals support the directional thesis"
    )
    risk_reward_quality: str = Field(
        description="Assessment of R:R ratio, cost vs budget, spread width vs premium"
    )
    probability_assessment: str = Field(
        description="Whether the price target reaches the spread strikes, probability reasonableness"
    )
    red_flags: list[str] = Field(
        description="List of specific concerns: earnings risk, liquidity issues, better alternatives. Empty list if none."
    )
    alternatives: list[str] = Field(
        description="Suggested alternative trades if the proposed one has issues. Empty list if trade is good."
    )
    exit_plan: ExitPlan = Field(
        description="Concrete exit plan with alerts and time rules"
    )


class FollowUpResponse(BaseModel):
    """Structured response for follow-up questions about an evaluated trade."""
    answer: str = Field(
        description="Direct answer to the follow-up question"
    )
    updated_verdict: Optional[Literal["EXECUTE", "WAIT", "PASS"]] = Field(
        default=None,
        description="Only set if the follow-up question changes the original verdict"
    )
    updated_rationale: Optional[str] = Field(
        default=None,
        description="Only set if verdict changed — explains why"
    )
