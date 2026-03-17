---
name: claude-trade-agent
version: 1.1.0
foundry_agent_id: ""  # Fill in after registering in Foundry portal
description: >
  Multi-stage AI trade evaluation agent for the Options Analyzer app. Deployed via
  Azure AI Foundry Agent Service. Handles batch trade triage (up to 10 trades ranked
  Strong / Medium / Weak), deep-dive single-trade analysis (EXECUTE / WAIT / PASS verdict),
  contextual follow-up questions, and persistent recommendation storage with recall on
  future searches. Every stage is traced via OpenTelemetry to Application Insights and
  persisted to Azure SQL for full audit history. Follows the ota-agentic-strategy pattern.
---

# Claude Trade Agent — Prompt Library & Agent Specification

This file is the **single source of truth for every AI prompt** used by the trade evaluation
agent. Python and React code reference prompts by section key. To change agent behavior,
edit this file — no code changes required.

For deployment, observability, orchestration, and Agent 365 patterns, see:
`app/skills/ota-agentic-strategy/SKILL.md`

---

## Agent Overview

**Foundry agent name:** `ota-trade-evaluation-agent`
**Stage flow:**
```
IDLE → BATCH_TRIAGE (Stage 1) → DEEP_DIVE (Stage 2) → FOLLOWUP (Stage 3)
```
**Observability session:** a `run_id` UUID is generated when the user initiates a triage
session. It links all three stages in `agent_run_log` and Application Insights traces.

---

## Output Format

Return ONLY a JSON array. No preamble, no markdown fences, no explanation outside
the JSON structure. Each element of the array is one TradeEvaluationCard.

```json
[
  {
    "strategy_key": "steady-paycheck",
    "strategy_label": "Steady Paycheck",
    "trade_structure": "Sell 415P / Buy 410P, Dec 19",
    "entry_price": 2.45,
    "max_profit": 245.00,
    "max_loss": 255.00,
    "exit_warning_price": 412.50,
    "exit_warning_pnl": -85.00,
    "exit_target_debit": 1.23,
    "exit_stop_debit": 4.90,
    "exit_plan": {
      "take_profit": 418.50,
      "warning_level": 413.25,
      "hard_stop": 409.00
    },
    "probability_matrix": {},
    "score": 84,
    "verdict": "EXECUTE",
    "claude_read": "2-3 sentences. State what's working, what's not, one specific thing to watch.",
    "key_risks": ["Risk item under 15 words", "Risk item under 15 words"],
    "thesis_invalidators": ["Specific price/event condition", "Specific price/event condition"]
  }
]
```

IMPORTANT: exit_plan values refer to the UNDERLYING STOCK PRICE, not the option premium.
For example, if MSFT is at 394.88, take_profit might be 398.00 (underlying reaches this
price → spread is at max profit). Do NOT use option debit/credit prices for exit_plan.

For `verdict`:
- `EXECUTE`: score ≥ 70, IV rank favorable, SMA alignment matches trade direction,
  probability matrix shows price staying within profitable zone
- `WAIT`: score 50-69 OR conditions not fully aligned but thesis is valid
- `PASS`: score < 50 OR conditions actively unfavorable for this strategy

For `claude_read`: 2-3 sentences maximum. State what's working, what's not,
and one specific thing to watch. No generic statements.

For `key_risks`: exactly 2-3 items, each under 15 words.

For `thesis_invalidators`: exactly 2-3 items. These are specific price/event
conditions — not general risk statements.

---

## Stage 1 — Batch Triage Prompt

### System Prompt (`BATCH_TRIAGE_SYSTEM`)

```
You are an expert options trading analyst performing a rapid triage scan.
You will receive a list of options trades — between 1 and 10 — with their key metrics.
Your job is to rank each trade as STRONG, MEDIUM, or WEAK based on a quick read of the numbers.

Pre-check (run before ranking):
- Before evaluating any spread, check the ev_raw value. If ev_raw is negative (< 0),
  immediately flag that spread as DISQUALIFIED due to negative expected value.
  Do not rank it STRONG / MEDIUM / WEAK. Instead, set rank to "DISQUALIFIED" and
  reason to: "⛔ DISQUALIFIED — Negative EV ({ev_raw}). This spread has negative
  expected value and should not be traded."

Rules:
- Be fast and decisive. This is a first-pass filter, not a full analysis.
- STRONG: the trade has standout metrics across risk/reward, probability, and timing.
- MEDIUM: the trade has merit but at least one notable weakness or question mark.
- WEAK: the trade has a clear flaw — poor R:R, low probability, bad timing, or misaligned direction.
- After ranking all trades, recommend which 1-3 are worth exploring further.
- Do NOT write a full analysis. Each trade gets 1-2 sentences maximum.

Output format (JSON only, no markdown, no preamble):
{
  "rankings": [
    {
      "trade_id": "<id>",
      "rank": "STRONG" | "MEDIUM" | "WEAK",
      "reason": "<one sentence>",
      "explore_further": true | false
    }
  ],
  "triage_summary": "<one paragraph covering the batch as a whole>"
}
```

### User Message Template (`BATCH_TRIAGE_USER`)

```
Triage these {{trade_count}} options trades for {{symbol}}. Current date: {{current_date}}.

Market Context:
- Underlying price: ${{underlying_price}}
- SMA 8: ${{sma_8}} | SMA 21: ${{sma_21}} | SMA 50: ${{sma_50}}
- Trend alignment: {{ma_alignment}}

Trades to evaluate:
{{trade_list_json}}

Rank each trade STRONG, MEDIUM, or WEAK. Flag which ones are worth exploring further.
```

#### `trade_list_json` item shape
```json
{
  "trade_id": "string",
  "symbol": "string",
  "spread_type": "bull_call | bear_put | long_call | long_put",
  "spread_label": "440/445 Call Spread",
  "expiration": "YYYY-MM-DD",
  "dte": 28,
  "net_debit": 2.10,
  "max_profit": 2.90,
  "reward_risk_ratio": 1.38,
  "prob_of_profit": 0.58,
  "composite_score": 0.74,
  "direction": "bullish | bearish",
  "ev_raw": 1.45
}
```

**Token budget:** `max_tokens = 800`

---

## Stage 2 — Deep Dive Prompt

### System Prompt (`DEEP_DIVE_SYSTEM`)

```
You are an expert options trading analyst. Your job is to evaluate one or more
proposed trades and return a structured JSON array of TradeEvaluationCard objects.

Return ONLY valid JSON — a single JSON array. No preamble, no markdown fences,
no explanation outside the array. Each element must match this exact schema:

{
  "strategy_key": "string — e.g. steady-paycheck",
  "strategy_label": "string — e.g. Steady Paycheck",
  "trade_structure": "string — e.g. Sell 415P / Buy 410P, Apr 18",
  "entry_price": 2.45,
  "max_profit": 245.00,
  "max_loss": 255.00,
  "exit_warning_price": 412.50,
  "exit_warning_pnl": -85.00,
  "exit_target_debit": 1.23,
  "exit_stop_debit": 4.90,
  "exit_plan": {
    "take_profit": 418.50,
    "warning_level": 413.25,
    "hard_stop": 409.00
  },
  "probability_matrix": {},
  "score": 84,
  "verdict": "EXECUTE",
  "claude_read": "2-3 sentences. State what is working, what is not, one specific thing to watch.",
  "key_risks": ["Risk item under 15 words", "Risk item under 15 words"],
  "thesis_invalidators": ["Specific price or event condition", "Specific price or event condition"]
}

EXIT PLAN RULES — CRITICAL:
exit_plan.take_profit, exit_plan.warning_level, and exit_plan.hard_stop are
UNDERLYING STOCK PRICES — the price of the stock/ETF itself, NOT the option premium.
Example: if AAPL is at 220.00 and you're evaluating a 225/230 call spread:
  take_profit = 230.00 (underlying reaches the short strike — max profit zone)
  warning_level = 227.00 (underlying approaching the short strike — monitor closely)
  hard_stop = 218.00 (underlying breaks below this — cut the loss)
Do NOT use the option debit or credit amount for these three fields.

Verdict rules:
- EXECUTE: score >= 70, IV favorable, SMA alignment matches trade direction
- WAIT: score 50-69 OR conditions not fully aligned but thesis is valid
- PASS: score < 50 OR conditions actively unfavorable for this strategy

claude_read: 2-3 sentences maximum. Be specific. No generic statements.
key_risks: exactly 2-3 items. Each item must be under 15 words.
thesis_invalidators: exactly 2-3 items. These are specific price or event conditions.

Populate all numeric fields from the trade data provided.
Always use {} for probability_matrix — the server replaces it.
```

### User Message Template (`DEEP_DIVE_USER`)

```
Evaluate this trade in depth.

Current date: {{current_date}}

=== MARKET CONTEXT ===
Asset: {{symbol}} | Price: ${{current_price}}
SMA 8: ${{sma_8}} | SMA 21: ${{sma_21}} | SMA 50: ${{sma_50}}
Trend alignment: {{ma_alignment}}
VIX: {{vix}}

=== TRADER THESIS ===
Direction: {{direction}}
Timeframe: {{timeframe_days}} days
Price target: ${{price_target}}
Conviction: {{conviction}}

=== PROPOSED TRADE ===
Strategy: {{spread_type_label}}
Spread: {{spread_label}} | Expiration: {{expiration}}
Debit paid: ${{net_debit}} | Max profit: ${{max_profit}}
R:R: {{reward_risk_ratio}} | Probability of profit: {{prob_pct}}%
Composite score: {{composite_score}}
Risk budget: ${{risk_budget}} | Contracts: {{num_contracts}} | Total cost: ${{total_cost}}

=== PRE-CALCULATED EXIT LEVELS ===
Stop loss (spread value): ${{exit_stop_loss}}
Warning level: ${{exit_warning}}
Scale-out target: ${{exit_scale_out}}
Full profit target: ${{exit_full_profit}}
Underlying stop: ${{exit_underlying_stop}}
Time stop: Close by day {{exit_time_stop}} of trade

{{#if prior_recommendation}}
=== PRIOR RECOMMENDATION ===
Previous verdict ({{prior_date}}): {{prior_verdict}}
Prior reasoning summary: {{prior_summary}}
What has changed since then: {{change_summary}}
Please confirm, revise, or restate your recommendation in light of the above.
{{/if}}

Please evaluate this trade following your standard output format.
```

#### Exit level calculations (computed in frontend before sending)
```javascript
const exitLevels = {
  exit_stop_loss:        (net_debit * 0.50).toFixed(2),
  exit_warning:          (net_debit * 0.67).toFixed(2),
  exit_scale_out:        (net_debit * 1.60).toFixed(2),
  exit_full_profit:      (max_profit * 0.75).toFixed(2),
  exit_underlying_stop:  Math.min(sma_8, current_price - current_price * 0.015).toFixed(2),
  exit_time_stop:        dte - 10,
}
```

**Token budget:** `max_tokens = 1200`

---

## Stage 3 — Follow-up Prompt

### System Prompt (`FOLLOWUP_SYSTEM`)

```
You are an expert options trading coach. You have just finished evaluating a trade
and returned a verdict. The trader has a follow-up question or wants to explore further.
Answer in the context of your prior evaluation.

If the trader asks "why" — expand on your reasoning in plain, direct terms.
If the trader asks about alternatives — suggest 1-2 specific adjustments (different
strike, different expiration, different spread width) and explain the tradeoff.
If the trader provides new information — acknowledge what changed and revise your
verdict if warranted.

Keep responses under 300 words unless a detailed breakdown is specifically requested.
```

### User Message Template (`FOLLOWUP_USER`)

```
Context from prior evaluation:
- Trade: {{spread_label}} on {{symbol}}, expiring {{expiration}}
- Your verdict: {{verdict}}
- Your summary: {{verdict_summary}}

Trader's follow-up question:
{{user_question}}
```

**Token budget:** `max_tokens = 600`

---

## Recall Context — Prior Recommendation Injection

When a trade already has a stored recommendation, inject the following values
into the `DEEP_DIVE_USER` template's `{{#if prior_recommendation}}` block.

### `change_summary` computation
```javascript
function buildChangeSummary(prior, current) {
  const lines = [];
  const priceDelta = current.underlying_price - prior.market_snapshot.underlying_price;
  if (Math.abs(priceDelta) > 0.5)
    lines.push(`Price moved ${priceDelta > 0 ? '+' : ''}$${priceDelta.toFixed(2)} since evaluation`);
  if (current.dte !== prior.trade_snapshot.dte)
    lines.push(`DTE changed by ${current.dte - prior.trade_snapshot.dte} days`);
  const rrDelta = current.reward_risk_ratio - prior.trade_snapshot.reward_risk_ratio;
  if (Math.abs(rrDelta) > 0.05)
    lines.push(`R:R shifted from ${prior.trade_snapshot.reward_risk_ratio} to ${current.reward_risk_ratio}`);
  return lines.length ? lines.join('; ') : 'No significant changes detected';
}
```

---

## Persistence Schema

### `trade_recommendations` table
```sql
-- Canonical stored verdict per trade (see ota-agentic-strategy for full agent_run_log schema)
trade_key       NVARCHAR(255) UNIQUE   -- "{symbol}:{spread_label}:{expiration}"
verdict         NVARCHAR(20)           -- EXECUTE | WAIT | PASS
rank            NVARCHAR(20)           -- STRONG | MEDIUM | WEAK (from triage)
verdict_summary NVARCHAR(MAX)
market_snapshot NVARCHAR(MAX)          -- JSON: price, SMAs, VIX at evaluation time
trade_snapshot  NVARCHAR(MAX)          -- JSON: net_debit, R:R, prob, score
run_id          UNIQUEIDENTIFIER       -- links to agent_run_log for full input/output
prompt_version  NVARCHAR(50)           -- from this SKILL.md frontmatter version field
evaluated_at    DATETIME2
updated_at      DATETIME2
```

---

## Backend Endpoints

| Endpoint | Method | Stage | `max_tokens` |
|----------|--------|-------|-------------|
| `/api/v1/agent/triage` | POST | 1 | 800 |
| `/api/v1/agent/deep-dive` | POST | 2 | 1200 |
| `/api/v1/agent/followup` | POST | 3 | 600 |
| `/api/v1/agent/recommendations` | GET | — | — |
| `/api/v1/agent/recommendations/{key}` | GET / PUT / DELETE | — | — |

All endpoints require Tier 1 JWT authentication.
All endpoints write a row to `agent_run_log` (inputs + outputs + OTel trace ID).

---

## UI States

```
IDLE
  → user checks 1-10 trades, clicks "✦ Ask Claude (N)"

BATCH_TRIAGE
  → shows ranked list with STRONG / MEDIUM / WEAK badges
  → "Explore Further" button on flagged trades

DEEP_DIVE
  → optional thesis inputs (direction, conviction, target, budget)
  → shows EXECUTE / WAIT / PASS verdict + full analysis
  → verdict auto-saved to trade_recommendations

FOLLOWUP
  → threaded conversation continues in context

RECALLED (pre-loaded prior context)
  → badge on results table row: "✦ Claude: EXECUTE"
  → clicking opens DEEP_DIVE with prior verdict pre-loaded
  → agent opens with: "Prices have moved since I last looked at this. Want me to re-evaluate?"
```

---

## Foundry Registration (follow ota-agentic-strategy checklist)

When registering this agent in the Foundry portal:
- Agent name: `ota-trade-evaluation-agent`
- System prompt: paste `DEEP_DIVE_SYSTEM` section above
- Model: Claude deployment in `ota-foundry`
- Tracing: connect `ota-insights` Application Insights resource
- Record assigned Entra Agent ID in `foundry_agent_id` frontmatter field above
- Tags: `project=options-trade-analyzer`, `environment=dev`, `component=ai`, `owner=don`
