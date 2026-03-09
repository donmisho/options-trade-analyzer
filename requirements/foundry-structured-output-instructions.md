# Trade Evaluation AI — Foundry Migration & Structured Output Upgrade

## Context for Claude Code

This document contains implementation instructions for upgrading the Ask Claude trade evaluation feature. Read this ENTIRE document before writing any code. The codebase is at `C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer`.

### What exists today
- `app/api/evaluate_routes.py` — FastAPI endpoints: POST /api/v1/evaluate/trade, POST /api/v1/evaluate/followup, GET /api/v1/evaluate/health
- `app/ai/` directory — contains the AI adapter pattern with `AnthropicAdapter` and `FoundryAdapter`
- `app/core/secrets.py` — SecretsManager that reads from Azure Key Vault (production) or .env (dev)
- `app/core/config.py` — Settings model with environment variables
- Frontend `AskClaudePanel.jsx` component — sends trade data to backend, displays verdict
- `trade_evaluation_requirements.md` — current prompt spec (in project root)

### What we're changing
Three improvements to the AI evaluation pipeline, in order:
1. **Structured outputs** — Replace free-text response with typed JSON schema
2. **Prompt caching** — Cache the static system prompt across evaluations
3. **System/user message separation** — Split the monolithic prompt into system instructions vs. trade-specific data

### Infrastructure
- **Model endpoint**: `https://ota-foundry-resource.services.ai.azure.com/anthropic/v1/messages`
- **Model**: `claude-sonnet-4-6` deployed as a model (NOT an agent) in Azure AI Foundry
- **API key**: Will be stored in Azure Key Vault as `foundry-api-key`. For local dev, use .env: `FOUNDRY_API_KEY=<key>`
- **The Foundry endpoint speaks the Anthropic Messages API format** — same request/response shape as calling api.anthropic.com directly, just different base URL and auth header

---

## Step 1: Add Settings for Foundry

In `app/core/config.py`, add these settings to the Settings class:

```python
# AI Provider settings
ai_provider: str = "foundry"  # "foundry" or "anthropic"
foundry_endpoint: str = "https://ota-foundry-resource.services.ai.azure.com/anthropic/v1/messages"
foundry_model: str = "claude-sonnet-4-6"
anthropic_model: str = "claude-sonnet-4-6"  # fallback if calling Anthropic directly
```

In `.env`, add:
```
AI_PROVIDER=foundry
FOUNDRY_API_KEY=your-key-here
FOUNDRY_ENDPOINT=https://ota-foundry-resource.services.ai.azure.com/anthropic/v1/messages
```

The SecretsManager should resolve `foundry-api-key` from Key Vault in production, or `FOUNDRY_API_KEY` from .env in dev. Check how the existing Schwab secrets are resolved and follow the same pattern.

---

## Step 2: Define the Structured Output Schema

Create a new file: `app/ai/schemas.py`

This file defines the Pydantic models that represent the EXACT shape of Claude's response. The structured output feature guarantees Claude returns valid JSON matching this schema — no more text parsing.

```python
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
```

---

## Step 3: Define the System Prompt

Create a new file: `app/ai/prompts.py`

This separates the static system instructions from the dynamic trade data. The system prompt is cached by the Anthropic API — it only gets processed once per 5-minute window, saving tokens and latency on repeat evaluations.

```python
"""
System prompts for AI trade evaluation.

WHY this is a separate file: The system prompt is STATIC — it doesn't
change between evaluations. By isolating it:
  1. It can be prompt-cached (90% token cost savings on repeat calls)
  2. It's easy to version and review
  3. The evaluate endpoint only assembles the dynamic user message

The system prompt tells Claude HOW to evaluate. The user message tells
Claude WHAT to evaluate. Keeping them separate improves response quality
because Claude can clearly distinguish instructions from data.
"""

TRADE_EVALUATION_SYSTEM_PROMPT = """You are an expert options trading coach evaluating trade setups for a disciplined retail trader.

Your job is to assess whether a proposed options trade aligns with the trader's thesis, technical picture, and risk parameters — then deliver a clear, actionable verdict.

EVALUATION FRAMEWORK:

1. VERDICT — EXECUTE, WAIT, or PASS
   - EXECUTE: Thesis aligns with technicals, strikes make sense, risk is sized correctly. Enter now.
   - WAIT: The setup has merit but timing or strike selection is off. Revisit when conditions change.
   - PASS: Poor risk/reward, thesis contradicts technicals, or much better opportunities exist.

2. THESIS vs CHART ALIGNMENT
   - Do the SMAs support the directional thesis?
   - Is price extended, consolidating, or breaking out?
   - Flag if SMAs are flattening, diverging, or about to cross

3. RISK/REWARD QUALITY
   - Is R:R ratio acceptable? (minimum 1.5:1 preferred)
   - Does total cost fit within the risk budget?
   - For credit spreads: is the credit collected sufficient relative to the risk?
   - Comment on spread width vs premium paid/collected

4. PROBABILITY vs EXPECTED MOVE
   - Does the trader's price target actually reach the spread strikes?
   - Flag disconnects between expected move and strike selection
   - For credit spreads: is probability of profit reasonable for the risk taken?

5. RED FLAGS
   - Earnings within expiration window? (IV crush risk)
   - Is there a tighter/cheaper spread that better matches the thesis?
   - Liquidity concerns (low volume, wide bid-ask)?
   - Strike selection issues (deep ITM legs, inverted structures)?

6. EXIT PLAN
   - Always provide concrete price levels and time-based rules
   - For debit spreads: stop loss, scale-out, and full profit targets based on spread value
   - For credit spreads: buy-back targets, max pain thresholds, and assignment risk timing
   - Time stops: when theta acceleration makes holding unprofitable

TRADE STRUCTURE NOTES:
- "Buy" means the leg the trader is purchasing (paying premium)
- "Sell" means the leg the trader is selling (collecting premium)  
- net_cost > 0 means debit spread (trader pays upfront)
- net_cost < 0 means credit spread (trader collects upfront)
- For debit spreads: max_loss = net_cost, max_profit = width - net_cost
- For credit spreads: max_profit = net_credit, max_loss = width - net_credit

Be direct and specific. Reference actual numbers from the trade data. No generic advice."""


FOLLOW_UP_SYSTEM_PROMPT = """You are continuing a trade evaluation conversation. You previously evaluated a specific options trade and gave a verdict. The trader has a follow-up question.

Answer the question directly using the trade context provided. If the question changes your assessment, update the verdict. If it doesn't, leave updated_verdict as null.

Be concise and specific. Reference the actual trade numbers."""
```

---

## Step 4: Build the Foundry Adapter

Create or update: `app/ai/foundry_adapter.py`

This is the core implementation. It calls the Foundry endpoint using the Anthropic Messages API format with structured outputs and prompt caching.

```python
"""
Azure AI Foundry adapter for Claude API calls.

WHY Foundry instead of direct Anthropic:
  - Single gateway to any LLM (Claude, GPT, etc.) via config change
  - AI traffic stays within Azure for compliance
  - Usage tracking, rate limiting, cost management in Azure portal
  - Same Anthropic Messages API format — just different base URL

The Foundry endpoint at ota-foundry-resource.services.ai.azure.com
speaks the Anthropic Messages API natively. Request/response format
is identical to api.anthropic.com.

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

from app.core.config import settings
from app.ai.schemas import TradeVerdict, FollowUpResponse
from app.ai.prompts import TRADE_EVALUATION_SYSTEM_PROMPT, FOLLOW_UP_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _build_json_schema(model_class) -> dict:
    """
    Convert a Pydantic model to the JSON schema format required by
    the Anthropic structured output API.
    
    WHY we do this manually instead of using the SDK's .parse() method:
    We're calling via HTTP (through Foundry), not the Python SDK directly.
    So we need to build the output_format payload ourselves.
    """
    schema = model_class.model_json_schema()
    # Anthropic requires additionalProperties: false at all object levels
    # and all properties must be required
    def _enforce_strict(s):
        if s.get("type") == "object" and "properties" in s:
            s["additionalProperties"] = False
            s["required"] = list(s["properties"].keys())
            for prop in s["properties"].values():
                _enforce_strict(prop)
        if s.get("type") == "array" and "items" in s:
            _enforce_strict(s["items"])
        # Handle $defs / definitions
        for def_schema in s.get("$defs", {}).values():
            _enforce_strict(def_schema)
        return s
    
    return _enforce_strict(schema)


class FoundryAdapter:
    """
    Calls Claude via Azure AI Foundry's Anthropic-compatible endpoint.
    
    Usage:
        adapter = FoundryAdapter(api_key="...", endpoint="https://...")
        result = await adapter.evaluate_trade(user_message="...")
        print(result.verdict)  # "EXECUTE" | "WAIT" | "PASS"
    """
    
    def __init__(
        self,
        api_key: str,
        endpoint: str = None,
        model: str = None,
    ):
        self.api_key = api_key
        self.endpoint = endpoint or settings.foundry_endpoint
        self.model = model or settings.foundry_model
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
            "system": [
                {
                    "type": "text",
                    "text": TRADE_EVALUATION_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [
                {"role": "user", "content": user_message}
            ],
            "output_format": {
                "type": "json_schema",
                "schema": _build_json_schema(TradeVerdict),
            },
        }
        
        response = await self._client.post(self.endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
        
        # Extract the text content from the response
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text = block["text"]
                break
        
        # Parse the structured JSON into our Pydantic model
        verdict = TradeVerdict.model_validate_json(text)
        
        # Log cache performance for monitoring
        usage = data.get("usage", {})
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_write = usage.get("cache_creation_input_tokens", 0)
        if cache_read > 0:
            logger.info(f"Prompt cache HIT: {cache_read} tokens read from cache")
        elif cache_write > 0:
            logger.info(f"Prompt cache MISS: {cache_write} tokens written to cache")
        
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
            "system": [
                {
                    "type": "text",
                    "text": FOLLOW_UP_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [
                {"role": "user", "content": user_message}
            ],
            "output_format": {
                "type": "json_schema",
                "schema": _build_json_schema(FollowUpResponse),
            },
        }
        
        response = await self._client.post(self.endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
        
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text = block["text"]
                break
        
        return FollowUpResponse.model_validate_json(text)
    
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
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Foundry health check failed: {e}")
            return False
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
```

---

## Step 5: Build the User Message Formatter

Create: `app/ai/message_builder.py`

This builds the DYNAMIC user message from the frontend's trade data. It replaces the old monolithic prompt template. Note the use of buy/sell language instead of long/short.

```python
"""
Builds the user message for trade evaluation.

WHY this is separate from the system prompt:
  - System prompt = HOW to evaluate (static, cached)
  - User message = WHAT to evaluate (dynamic, changes every call)
  
This separation enables prompt caching — the system prompt is processed
once and cached for 5 minutes. Only the user message (which is short)
gets processed fresh each time.

The user message uses BUY/SELL language instead of long/short, and
net_cost with a sign instead of separate debit/credit fields. This
matches the display overhaul in the credit-spreads-and-display-plan.md.
"""


def build_trade_evaluation_message(
    # Market context
    symbol: str,
    current_price: float,
    sma_8: float,
    sma_21: float,
    sma_50: float,
    ma_alignment: str,
    # Thesis
    direction: str,
    conviction: str,
    price_target: float,
    timeframe_days: int,
    risk_budget: float,
    # Trade details
    strategy: str,
    strategy_label: str,
    buy_strike: float,
    sell_strike: float,
    option_type: str,
    expiration: str,
    net_cost: float,
    max_profit: float,
    max_loss: float,
    breakeven: float,
    reward_risk_ratio: float,
    prob_of_profit: float,
    composite_score: float,
    is_credit: bool = False,
    # Pre-calculated exit levels (computed client-side)
    exit_levels: dict = None,
) -> str:
    """
    Build the user message for a trade evaluation request.
    
    All arguments come from the frontend's trade payload and SMA data.
    Exit levels are computed client-side per trade_evaluation_requirements.md
    and passed in — we don't ask Claude to do math.
    """
    # Format cost display
    if is_credit:
        cost_display = f"Net Credit: ${abs(net_cost):.2f} (you collect)"
    else:
        cost_display = f"Net Debit: ${abs(net_cost):.2f} (you pay)"
    
    # Contracts that fit budget
    per_contract_cost = abs(net_cost) * 100
    num_contracts = max(1, int(risk_budget / per_contract_cost)) if per_contract_cost > 0 else 1
    total_cost = per_contract_cost * num_contracts
    
    msg = f"""TRADE EVALUATION REQUEST

=== MARKET CONTEXT ===
Asset: {symbol}
Current Price: ${current_price:.2f}
SMA 8: ${sma_8:.2f} | SMA 21: ${sma_21:.2f} | SMA 50: ${sma_50:.2f}
MA Alignment: {ma_alignment}

=== TRADER THESIS ===
Direction: {direction}
Conviction: {conviction}
Price Target: ${price_target:.2f}
Timeframe: {timeframe_days} days

=== PROPOSED TRADE ===
Strategy: {strategy_label}
Action: Buy {buy_strike} {option_type} / Sell {sell_strike} {option_type}
Expiration: {expiration}
{cost_display}
Max Profit: ${max_profit:.2f} per share (${max_profit * 100:.0f} per contract)
Max Loss: ${max_loss:.2f} per share (${max_loss * 100:.0f} per contract)
Breakeven: ${breakeven:.2f}
R:R Ratio: {reward_risk_ratio:.2f}
Prob of Profit: {prob_of_profit * 100:.0f}%
Composite Score: {composite_score:.2f}
Risk Budget: ${risk_budget:.0f} | Contracts: {num_contracts} | Total Cost: ${total_cost:.0f}"""
    
    if exit_levels:
        msg += f"""

=== PRE-CALCULATED EXIT LEVELS ===
Stop Loss (spread value): ${exit_levels.get('stopLoss', 0):.2f}
Warning Level: ${exit_levels.get('warningLevel', 0):.2f}
Scale-Out Target: ${exit_levels.get('scaleOutTarget', 0):.2f}
Full Profit Target: ${exit_levels.get('fullProfitTarget', 0):.2f}
Underlying Stop: ${exit_levels.get('underlyingStop', 0):.2f}
Time Stop: {exit_levels.get('timeStop', 'N/A')} days before expiration"""
    
    return msg
```

---

## Step 6: Update evaluate_routes.py

The existing evaluate routes need to be updated to use the new adapter and structured output. Here are the key changes:

### 6A. Initialize the adapter at startup

In `app/main.py`, during the lifespan startup, create the FoundryAdapter and make it available to the evaluate routes, similar to how `init_market_routes(provider_factory)` works:

```python
from app.ai.foundry_adapter import FoundryAdapter

# Inside lifespan startup:
foundry_api_key = secrets_manager.get_secret("foundry-api-key")
ai_adapter = FoundryAdapter(api_key=foundry_api_key)
init_evaluate_routes(ai_adapter)
```

### 6B. Update the evaluate endpoint

The POST /api/v1/evaluate/trade endpoint should:

1. Receive the trade data from the frontend (same request schema, but with new field names: `buy_strike`, `sell_strike`, `net_cost`, `is_credit`)
2. Call `build_trade_evaluation_message()` to assemble the user message
3. Call `adapter.evaluate_trade(user_message)` to get a `TradeVerdict`
4. Return the `TradeVerdict` as JSON directly (it's already a Pydantic model)

The response shape changes from a blob of text to structured JSON:

```json
{
  "verdict": "WAIT",
  "verdict_rationale": "Bearish thesis aligns with SMAs but strike selection creates a bullish structure",
  "thesis_alignment": "Price at $599.75 is below all three SMAs...",
  "risk_reward_quality": "R:R of 1.08 is well below the 1.5 minimum...",
  "probability_assessment": "With a $550 target requiring an 8.3% drop...",
  "red_flags": [
    "Buy leg at 630 is $30 ITM — massive intrinsic value cost",
    "Breakeven at $610.73 is ABOVE current price"
  ],
  "alternatives": [
    "590/550 bear put debit spread: costs ~$8-12, R:R of 3:1 to 4:1",
    "Single 590 put for a simple directional bet"
  ],
  "exit_plan": {
    "underlying_alerts": [
      {"label": "Profit trigger", "price_or_value": "$570.00", "action": "Check spread value, prepare to close"},
      {"label": "Full target", "price_or_value": "$550.00", "action": "Close spread, take profit"},
      {"label": "Thesis invalidated", "price_or_value": "$610.00", "action": "Close immediately"}
    ],
    "spread_value_alerts": [
      {"label": "Scale out", "price_or_value": "$30.83", "action": "Close 50-75% of position"},
      {"label": "Hard stop", "price_or_value": "$9.64", "action": "Close entire position"}
    ],
    "time_rules": [
      "If flat after 10 days, reassess — theta accelerating",
      "Never hold into final 7 days unless deep ITM",
      "If VIX spikes 20%+, evaluate early close"
    ]
  }
}
```

### 6C. Update the follow-up endpoint

POST /api/v1/evaluate/followup should call `adapter.follow_up()` and return a `FollowUpResponse`.

### 6D. Update the health endpoint

GET /api/v1/evaluate/health should call `adapter.health_check()`.

---

## Step 7: Update the Frontend

### 7A. Update `buildClaudeTrade()` in VerticalsPage.jsx

The trade object sent to AskClaudePanel needs to use the new field names. NOTE: This change depends on the credit spread engine changes from `credit-spreads-and-display-plan.md`. If those engine changes haven't been made yet, keep the existing field names and add a translation layer in the backend evaluate endpoint that maps `long_strike`/`short_strike` to `buy_strike`/`sell_strike`.

For now, the backend should accept BOTH old and new field names and normalize internally:

```python
# In the evaluate endpoint's request handler:
buy_strike = req.buy_strike or req.long_strike   # support both during transition
sell_strike = req.sell_strike or req.short_strike
```

### 7B. Update AskClaudePanel to render structured response

The panel currently parses free-text to extract the verdict. With structured output, the response is already typed JSON. Update the panel to:

1. Read `response.verdict` directly (no parsing needed)
2. Render `response.thesis_alignment`, `response.risk_reward_quality`, `response.probability_assessment` as collapsible sections
3. Render `response.red_flags` as a bullet list (already an array)
4. Render `response.alternatives` as a bullet list
5. Render `response.exit_plan` with the structured alert tables

The verdict banner color mapping stays the same:
- EXECUTE → green
- WAIT → yellow/amber  
- PASS → red

### 7C. Update follow-up handling

The follow-up response now has typed fields:
- `response.answer` — the direct answer text
- `response.updated_verdict` — only present if verdict changed (can be null)
- `response.updated_rationale` — only present if verdict changed

If `updated_verdict` is not null, update the verdict banner to reflect the new verdict.

---

## Step 8: Dependency Management

Install the `httpx` package if not already present (check requirements.txt):

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
pip install httpx
```

The `pydantic` package should already be installed (FastAPI requires it). Verify:

```powershell
pip show pydantic
```

No additional packages are needed. We're using raw `httpx` for the API call rather than the `anthropic` Python SDK because we're calling through Foundry's URL, not api.anthropic.com directly. httpx gives us full control over the request.

---

## Step 9: Testing

### 9A. Backend unit test

Create a simple test that verifies the structured output schema is valid:

```python
# tests/test_ai_schemas.py
from app.ai.schemas import TradeVerdict, FollowUpResponse
from app.ai.foundry_adapter import _build_json_schema

def test_trade_verdict_schema():
    schema = _build_json_schema(TradeVerdict)
    assert schema["type"] == "object"
    assert "verdict" in schema["properties"]
    assert schema["properties"]["verdict"]["enum"] == ["EXECUTE", "WAIT", "PASS"]
    assert schema["additionalProperties"] == False

def test_follow_up_schema():
    schema = _build_json_schema(FollowUpResponse)
    assert "answer" in schema["properties"]
    assert "updated_verdict" in schema["properties"]
```

### 9B. Manual integration test

Once the backend is wired up, test with:

```powershell
# Start the backend
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# In another terminal, test the health endpoint
curl -k https://127.0.0.1:8000/api/v1/evaluate/health

# Test a trade evaluation (you'll need a valid JWT — use the existing auth flow)
```

### 9C. Frontend test

1. Run the app locally (backend + frontend)
2. Select a symbol, wait for vertical spread analysis
3. Click the ✦ button on any trade to open Ask Claude
4. Fill in thesis (direction, target, budget)
5. Click "Evaluate This Trade"
6. Verify: verdict banner shows, sections render with structured data (not raw text)
7. Ask a follow-up question
8. Verify: follow-up response renders cleanly

---

## Important Notes

### Backward Compatibility
- The v1.0.0 codebase snapshots in project knowledge may be STALE. Always read the actual files on disk before editing.
- If evaluate_routes.py has been modified since v1.0.0, read the current version first and adapt these instructions to the current code structure.
- The frontend may still send `long_strike`/`short_strike` until the credit spread engine changes are implemented. The backend must handle both field name conventions during the transition.

### Error Handling
- If the Foundry endpoint returns a non-200 status, log the full response body (it contains error details) and return a 502 to the frontend with a user-friendly message.
- If structured output parsing fails (shouldn't happen with valid schema, but defensive coding), fall back to returning the raw text in an error response.
- Set a generous timeout (60s) on the httpx client — Claude evaluations with structured output can take 10-30 seconds.

### Prompt Caching Behavior
- The FIRST evaluation in a session costs ~25% more (cache write). Evaluations 2-N within 5 minutes cost ~90% less (cache read).
- If you change the system prompt text, the cache is invalidated. This is expected during development.
- The response's `usage` field shows `cache_read_input_tokens` and `cache_creation_input_tokens` — log these to verify caching is working.

### Structured Output Limitations
- Structured outputs are NOT compatible with extended thinking mode. We don't need extended thinking for trade evaluations — they're focused analytical tasks, not multi-step reasoning problems.
- The schema must use `additionalProperties: false` at all object levels. The `_build_json_schema()` helper enforces this.
- All properties must be listed in `required`. The helper enforces this too.

### Key Vault Secret Name
- The Foundry API key should be stored in Key Vault as `foundry-api-key`
- For local dev, use `FOUNDRY_API_KEY` in `.env`
- Follow the same resolution pattern used for `schwab-app-key` and `schwab-app-secret`
