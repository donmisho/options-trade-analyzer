"""Unit tests for AI structured output schemas."""

from app.ai.schemas import TradeVerdict, FollowUpResponse
from app.ai.foundry_adapter import _build_json_schema


def test_trade_verdict_schema():
    schema = _build_json_schema(TradeVerdict)
    assert schema["type"] == "object"
    assert "verdict" in schema["properties"]
    assert schema["additionalProperties"] is False
    # All top-level properties must be required
    for key in schema["properties"]:
        assert key in schema["required"], f"'{key}' not in required"


def test_trade_verdict_schema_nested_strict():
    """Nested objects must also have additionalProperties: false."""
    schema = _build_json_schema(TradeVerdict)
    # executionPlan is an object — check it's strict (may be $ref to $defs)
    exec_plan_ref = schema["properties"]["executionPlan"]
    if "$ref" in exec_plan_ref:
        ref_name = exec_plan_ref["$ref"].split("/")[-1]
        exec_plan_schema = schema["$defs"][ref_name]
    else:
        exec_plan_schema = exec_plan_ref
    assert exec_plan_schema.get("additionalProperties") is False


def test_follow_up_schema():
    schema = _build_json_schema(FollowUpResponse)
    assert "answer" in schema["properties"]
    assert "updated_verdict" in schema["properties"]
    assert schema["additionalProperties"] is False


def test_trade_verdict_parse():
    """Verify TradeVerdict can be instantiated with valid data."""
    verdict = TradeVerdict(
        verdict="EXECUTE",
        thesisInsights={
            "verdictAndThesis": [
                {"label": "SMA Alignment", "status": "pass", "text": "Price above all SMAs."}
            ],
            "tradeStructure": [
                {"label": "R:R Ratio", "status": "pass", "text": "R:R of 2.1 exceeds 1.5 minimum."}
            ],
            "probabilityAndVolatility": [
                {"label": "PoP", "status": "pass", "text": "72% probability of profit."}
            ],
            "riskAndExecution": [
                {"label": "Top Risk", "status": "caution", "text": "Earnings in 18 days."}
            ],
            "alternateConsiderations": [
                {"label": "Alternative", "status": "alt", "text": "Consider tighter spread."}
            ],
        },
        executionPlan={
            "verdict": "EXECUTE",
            "criteria": ["All SMAs aligned bullishly", "IV rank above 30"],
            "alerts": [],
            "ladder": [
                {"label": "Scale-Out 1 (50%)", "price": 590.0},
                {"label": "Hard Stop", "price": 560.0},
            ],
        },
    )
    assert verdict.verdict == "EXECUTE"
    assert len(verdict.executionPlan.ladder) == 2
    assert verdict.thesisInsights.verdictAndThesis[0].status == "pass"
