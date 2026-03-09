"""Unit tests for AI structured output schemas."""

from app.ai.schemas import TradeVerdict, FollowUpResponse
from app.ai.foundry_adapter import _build_json_schema


def test_trade_verdict_schema():
    schema = _build_json_schema(TradeVerdict)
    assert schema["type"] == "object"
    assert "verdict" in schema["properties"]
    assert schema["properties"]["verdict"]["enum"] == ["EXECUTE", "WAIT", "PASS"]
    assert schema["additionalProperties"] is False
    # All top-level properties must be required
    for key in schema["properties"]:
        assert key in schema["required"], f"'{key}' not in required"


def test_trade_verdict_schema_nested_strict():
    """Nested objects must also have additionalProperties: false."""
    schema = _build_json_schema(TradeVerdict)
    # exit_plan is an object — check it's strict
    exit_plan_ref = schema["properties"]["exit_plan"]
    # Resolve $ref if needed
    if "$ref" in exit_plan_ref:
        ref_name = exit_plan_ref["$ref"].split("/")[-1]
        exit_plan_schema = schema["$defs"][ref_name]
    else:
        exit_plan_schema = exit_plan_ref
    assert exit_plan_schema.get("additionalProperties") is False


def test_follow_up_schema():
    schema = _build_json_schema(FollowUpResponse)
    assert "answer" in schema["properties"]
    assert "updated_verdict" in schema["properties"]
    assert schema["additionalProperties"] is False


def test_trade_verdict_parse():
    """Verify TradeVerdict can be instantiated with valid data."""
    verdict = TradeVerdict(
        verdict="EXECUTE",
        verdict_rationale="Strong bullish alignment with all SMAs.",
        thesis_alignment="Price is above all three SMAs.",
        risk_reward_quality="R:R of 2.1 exceeds the 1.5 minimum.",
        probability_assessment="Target of $590 reaches the short strike.",
        red_flags=[],
        alternatives=[],
        exit_plan={
            "underlying_alerts": [
                {"label": "Profit trigger", "price_or_value": "$590.00", "action": "Scale out 50%"}
            ],
            "spread_value_alerts": [
                {"label": "Hard stop", "price_or_value": "$0.60", "action": "Close entire position"}
            ],
            "time_rules": ["If flat after 10 days, reassess"],
        },
    )
    assert verdict.verdict == "EXECUTE"
    assert len(verdict.exit_plan.underlying_alerts) == 1
