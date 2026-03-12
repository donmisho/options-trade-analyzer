"""
Structured output schemas for AI trade evaluation.

Phase 2.7: Updated to Thesis Matrix response format.
TradeVerdict now returns thesisInsights (5 collapsible groups) and
executionPlan (criteria + alerts + exit ladder), replacing the flat
text sections.

FollowUpResponse is unchanged.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional, List


# ─── Thesis Matrix ────────────────────────────────────────────────────────────

class ThesisRow(BaseModel):
    """One row in a Thesis Matrix group."""
    label: str = Field(description="Metric name, e.g. 'SMA Alignment'")
    status: str = Field(description="'pass', 'caution', 'risk', or 'alt'")
    text: str = Field(description="Concise insight — 1-2 sentences max")


class ThesisInsights(BaseModel):
    """Five grouped sections of the Thesis Matrix."""
    verdictAndThesis: List[ThesisRow] = Field(
        description="Verdict, SMA alignment, feasibility, timing signal"
    )
    tradeStructure: List[ThesisRow] = Field(
        description="R:R ratio, premium/width, budget utilization, breakeven cushion"
    )
    probabilityAndVolatility: List[ThesisRow] = Field(
        description="Probability assessment, volatility environment"
    )
    riskAndExecution: List[ThesisRow] = Field(
        description="Top risk flag, time decay analysis"
    )
    alternateConsiderations: List[ThesisRow] = Field(
        description="Alternative trade suggestion, re-entry condition"
    )


# ─── Execution Plan ───────────────────────────────────────────────────────────

class ExecutionAlert(BaseModel):
    """A watch alert with confirm or invalidation type."""
    type: str = Field(description="'confirm' or 'invalidation'")
    label: str = Field(description="Display label, e.g. 'Confirm Alert'")
    price: float = Field(description="The price level to watch")


class LadderRung(BaseModel):
    """One step on the exit ladder."""
    label: str = Field(description="e.g. 'Scale-Out 1 (50%)'")
    price: float = Field(description="The price level for this exit")


class ExecutionPlan(BaseModel):
    """
    Verdict-specific action plan.
    WAIT: criteria + alerts (confirm/invalidation), ladder empty.
    EXECUTE: criteria + ladder (exit steps), alerts empty.
    """
    verdict: str = Field(description="'WAIT' or 'EXECUTE' — matches top-level verdict")
    criteria: List[str] = Field(
        description="WAIT: trigger conditions to watch for. EXECUTE: confirmation criteria met."
    )
    alerts: List[ExecutionAlert] = Field(
        description="WAIT: confirm and invalidation price alerts. EXECUTE: empty list."
    )
    ladder: List[LadderRung] = Field(
        description="EXECUTE: scale-out, full exit, hard stop, underlying stop levels. WAIT: empty list."
    )


# ─── Top-level TradeVerdict ───────────────────────────────────────────────────

class TradeVerdict(BaseModel):
    """
    Complete structured response from Claude for trade evaluation.
    Maps directly to the AskClaudePanel Thesis Matrix + Action Command Center.
    """
    verdict: Literal["EXECUTE", "WAIT"] = Field(
        description="The trading decision — EXECUTE or WAIT"
    )
    thesisInsights: ThesisInsights = Field(
        description="Five grouped sections for the Thesis Matrix table"
    )
    executionPlan: ExecutionPlan = Field(
        description="Actionable plan with criteria, alerts (WAIT) or exit ladder (EXECUTE)"
    )


# ─── Follow-up (unchanged) ────────────────────────────────────────────────────

class FollowUpResponse(BaseModel):
    """Structured response for follow-up questions about an evaluated trade."""
    answer: str = Field(
        description="Direct answer to the follow-up question"
    )
    updated_verdict: Optional[Literal["EXECUTE", "WAIT"]] = Field(
        default=None,
        description="Only set if the follow-up changes the original verdict"
    )
    updated_rationale: Optional[str] = Field(
        default=None,
        description="Only set if verdict changed — explains why"
    )
