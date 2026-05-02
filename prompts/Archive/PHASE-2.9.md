# PHASE-2.9 — Security Dashboard + Strategy Scorecard

## Objective

Build the per-symbol Security Dashboard page and the reusable `StrategyScorecard`
component that scores all strategies simultaneously for any symbol. This is the
primary entry point for trade discovery — replacing the current flow of navigating
to a strategy page and running analysis manually.

## Why This Phase First

Everything downstream (positions, Claude evaluation, insight engine) depends on
having a strategy scorecard. This is the foundation. It can be built entirely with
existing data — no new backend infrastructure beyond a new endpoint and four new
strategy configs.

## Dependencies

- Phases 2.1-2.8 complete (analysis engines, OptionsTerminal working)
- Schwab connected and returning live data
- No Azure SQL changes required for this phase

---

## Parallel Streams

This phase splits into two independent streams that can run simultaneously.

### Stream A — Backend (start immediately)
Strategy scoring endpoint + Black-Scholes utility + four strategy config schemas

### Stream B — Frontend (start immediately, use mock data)
SecurityDashboard page + StrategyScorecard component + ConfigDrawer strategy-awareness

Streams A and B integrate at the end of this phase.

---

## Stream A: Backend Work

### A1 — Four Strategy Config Schemas

Define the scoring parameters for the initial four strategies. These live in Python
as dataclasses that inform both the scoring engine and the frontend config schema.

**File**: `app/analysis/strategy_definitions.py` (new file)

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class ConfigField:
    key: str
    label: str
    type: str           # 'slider' | 'toggle' | 'number'
    min: float = 0
    max: float = 100
    default: float = 50
    step: float = 1
    unit: str = ''      # '%', 'days', 'delta', etc.

@dataclass
class StrategyDefinition:
    key: str
    label: str
    description: str
    trade_structure: str    # 'credit_spread' | 'debit_spread' | 'long_option'
    dte_min: int
    dte_max: int
    scoring_weights: dict   # metric_name → weight (must sum to 1.0)
    config_schema: List[ConfigField]

STRATEGIES = {
    'steady-paycheck': StrategyDefinition(
        key='steady-paycheck',
        label='Steady Paycheck',
        description='30-45 DTE credit spreads, high IV rank, income focus',
        trade_structure='credit_spread',
        dte_min=25,
        dte_max=50,
        scoring_weights={
            'theta_margin_ratio': 0.30,
            'probability_of_profit': 0.25,
            'expected_value': 0.20,
            'reward_risk': 0.15,
            'iv_rank': 0.10,
        },
        config_schema=[
            ConfigField('dte_min', 'Min DTE', 'slider', 15, 45, 25, 1, 'days'),
            ConfigField('dte_max', 'Max DTE', 'slider', 30, 60, 50, 1, 'days'),
            ConfigField('delta_max', 'Max Short Delta', 'slider', 0.10, 0.45, 0.30, 0.01, 'Δ'),
            ConfigField('iv_rank_min', 'Min IV Rank', 'slider', 0, 100, 40, 5, '%'),
            ConfigField('exit_profit_pct', 'Take Profit At', 'slider', 25, 90, 50, 5, '%'),
            ConfigField('stop_loss_multiple', 'Stop Loss (credit ×)', 'slider', 1.5, 4.0, 2.0, 0.5, '×'),
        ]
    ),
    'weekly-grind': StrategyDefinition(
        key='weekly-grind',
        label='Weekly Grind',
        description='7-14 DTE credit spreads, Theta/Gamma efficiency focus',
        trade_structure='credit_spread',
        dte_min=5,
        dte_max=16,
        scoring_weights={
            'theta_gamma_ratio': 0.35,
            'probability_of_profit': 0.25,
            'credit_width_pct': 0.20,
            'expected_value': 0.15,
            'liquidity': 0.05,
        },
        config_schema=[
            ConfigField('dte_min', 'Min DTE', 'slider', 3, 10, 5, 1, 'days'),
            ConfigField('dte_max', 'Max DTE', 'slider', 7, 21, 14, 1, 'days'),
            ConfigField('delta_max', 'Max Short Delta', 'slider', 0.10, 0.35, 0.25, 0.01, 'Δ'),
            ConfigField('min_credit_width_pct', 'Min Credit/Width', 'slider', 15, 40, 25, 1, '%'),
            ConfigField('exit_profit_pct', 'Take Profit At', 'slider', 25, 75, 50, 5, '%'),
        ]
    ),
    'trend-rider': StrategyDefinition(
        key='trend-rider',
        label='Trend Rider',
        description='30-60 DTE long calls on strong SMA-aligned stocks',
        trade_structure='long_option',
        dte_min=25,
        dte_max=65,
        scoring_weights={
            'sma_alignment_score': 0.30,
            'delta_quality': 0.25,
            'expected_value': 0.20,
            'iv_percentile_cost': 0.15,
            'runway_score': 0.10,
        },
        config_schema=[
            ConfigField('dte_min', 'Min DTE', 'slider', 20, 45, 30, 1, 'days'),
            ConfigField('dte_max', 'Max DTE', 'slider', 45, 90, 60, 1, 'days'),
            ConfigField('delta_min', 'Min Long Delta', 'slider', 0.40, 0.70, 0.50, 0.01, 'Δ'),
            ConfigField('delta_max', 'Max Long Delta', 'slider', 0.50, 0.85, 0.70, 0.01, 'Δ'),
            ConfigField('iv_rank_max', 'Max IV Rank (avoid overpaying)', 'slider', 40, 100, 60, 5, '%'),
            ConfigField('min_sma_alignment', 'Require SMA Alignment', 'toggle', 0, 1, 1),
        ]
    ),
    'lottery-ticket': StrategyDefinition(
        key='lottery-ticket',
        label='Lottery Ticket',
        description='1-7 DTE deep OTM, asymmetric payout, catalyst required',
        trade_structure='long_option',
        dte_min=1,
        dte_max=8,
        scoring_weights={
            'payout_ratio': 0.45,
            'delta_otm_score': 0.25,
            'bid_ask_tightness': 0.20,
            'open_interest': 0.10,
        },
        config_schema=[
            ConfigField('dte_max', 'Max DTE', 'slider', 1, 14, 7, 1, 'days'),
            ConfigField('delta_max', 'Max Delta', 'slider', 0.05, 0.25, 0.15, 0.01, 'Δ'),
            ConfigField('min_payout_ratio', 'Min Payout Ratio', 'slider', 3, 15, 5, 0.5, ':1'),
            ConfigField('max_cost_per_contract', 'Max Cost/Contract', 'number', 10, 500, 100, 10, '$'),
        ]
    ),
}
```

### A2 — Strategy Scorer Engine

**File**: `app/analysis/strategy_scorer.py` (new file)

This engine takes a symbol, fetches its options chain once, and runs all four strategy
scoring functions against the same chain. Returns a list of strategy scores.

```python
async def score_all_strategies(
    symbol: str,
    provider,
    user_config: dict = None
) -> List[StrategyScore]:
    """
    Fetch chain once, run all strategies, return normalized 0-100 scores.
    Each StrategyScore includes: strategy_key, score, best_trade, signal_summary
    """
```

Key implementation note: fetch the options chain ONCE, pass it to all four scoring
functions. Do not make four separate chain requests. This is critical for quota management.

### A3 — Black-Scholes Probability Matrix

**File**: `app/analysis/black_scholes.py` (new file)

```python
def compute_probability_matrix(
    current_price: float,
    iv: float,              # annualized implied volatility as decimal (0.25 = 25%)
    dte: int,               # days to expiration
    risk_free_rate: float = 0.05,
    price_range_pct: float = 0.10,  # ±10%
    price_step: float = 10.0
) -> ProbabilityMatrix:
    """
    Returns probability of underlying being at each price level
    on dates: expiry-9, expiry-6, expiry-3, expiry.
    Uses Black-Scholes lognormal distribution — not Claude.
    """
```

### A4 — New API Endpoints

**File**: `app/api/analysis_routes.py` (add to existing)

```
POST /api/v1/analysis/scorecard
  Request: { symbol, user_config? }
  Response: { symbol, quote, sma_signal, strategies: [{ key, label, score, best_trade, signal_summary }] }

POST /api/v1/analysis/probability-matrix
  Request: { symbol, current_price, iv, dte }
  Response: { price_levels: [...], dates: [...], matrix: [[...]] }
```

---

## Stream B: Frontend Work

### B1 — SecurityDashboard Page

**File**: `web/src/pages/SecurityDashboard.jsx` (new file)

Layout:
```
┌─────────────────────────────────────────────┐
│  MSFT  415.23  +2.14 (+0.52%)               │  ← QuoteBar (existing component)
│  SMA: BULLISH  8>21>50                       │
├─────────────────────────────────────────────┤
│  [Candlestick chart with SMA overlays]       │  ← existing chart component
│                                              │
├─────────────────────────────────────────────┤
│  STRATEGY SCORECARD                          │
│  ┌─────────────────┬───────┬──────────────┐ │
│  │ Steady Paycheck │  84   │ ████████░░   │ │
│  │ Weekly Grind    │  71   │ ███████░░░   │ │
│  │ Trend Rider     │  91   │ █████████░   │ │
│  │ Lottery Ticket  │  23   │ ██░░░░░░░░   │ │
│  └─────────────────┴───────┴──────────────┘ │
│                                              │
│  [□ Steady Paycheck] [□ Trend Rider]         │  ← checkboxes to select
│  [Evaluate Selected ▶]                       │
└─────────────────────────────────────────────┘
```

State: selected strategy keys (array), scorecard data, loading state.

### B2 — StrategyScorecard Component

**File**: `web/src/components/StrategyScorecard.jsx` (new file)

Reusable component that accepts:
```javascript
props: {
  scores: [...],           // array of { key, label, score, best_trade, signal_summary }
  selectedKeys: [...],     // controlled selection state
  onSelectionChange: fn,
  onEvaluate: fn,
  loading: bool
}
```

Renders:
- Score bar for each strategy (0-100 gradient: red→yellow→green)
- Signal summary tooltip on hover
- Checkboxes for selection
- "Evaluate Selected" button (disabled until ≥1 selected)

This same component is also used in OptionsTerminal trade row expansion (Stage 2).

### B3 — Trade Row Expansion in OptionsTerminal

**File**: `web/src/pages/OptionsTerminal.jsx` (update Stage 2)

When a trade row is expanded (Stage 2), the expansion panel now includes:
1. Existing: math matrix + payoff diagram
2. **New**: `StrategyScorecard` for this specific trade
3. **New**: "Evaluate" button → triggers structured Claude evaluation for selected strategies

The StrategyScorecard in this context receives the trade as pre-populated context.
It shows which strategies this specific trade fits, scored 0-100.

### B4 — Strategy-Aware ConfigDrawer

**File**: `web/src/components/ConfigDrawer.jsx` (update)

ConfigDrawer now accepts an `activeStrategy` prop. When a strategy is active
(user is on SecurityDashboard or has expanded a trade), the drawer renders
the strategy's `configSchema` array instead of the static 14-field system vars.

Each field in `configSchema` maps to a UI control by its `type`:
- `'slider'` → range input with min/max/step/unit label
- `'toggle'` → checkbox
- `'number'` → number input with min/max

Default values come from the strategy definition. User overrides stored in
`analysisConfig.strategyOverrides[strategyKey]` in localStorage.

---

## Integration Testing (End of Phase 2.9)

Run these manually after both streams are complete and wired together:

**Test 1 — Scorecard loads for a symbol**
1. Connect Schwab, navigate to SecurityDashboard for MSFT
2. Scorecard should show 4 strategies with 0-100 scores
3. Scores should differ — if all are the same, scoring logic is not differentiating
4. Best trade shown for each strategy should be structurally appropriate
   (credit spread for Steady Paycheck/Weekly Grind, long call for Trend Rider/Lottery Ticket)

**Test 2 — Single chain fetch confirmed**
1. Open browser network tab
2. Load SecurityDashboard for any symbol
3. Verify exactly ONE call to `/api/v1/market/options/{symbol}` regardless of how
   many strategies are shown. Multiple calls = bug.

**Test 3 — ConfigDrawer is strategy-aware**
1. Open ConfigDrawer while on SecurityDashboard
2. Should show strategy-specific parameters, not generic system vars
3. Changing a slider should update the strategy config in localStorage
4. Re-running scorecard should use the updated config

**Test 4 — Trade row expansion includes scorecard**
1. Navigate to Verticals page, run analysis for any symbol
2. Expand a trade row
3. Strategy scorecard should appear in expansion with scores for that specific trade
4. Evaluate button should be present and enabled after selecting a strategy

**Test 5 — Black-Scholes matrix sanity check**
1. Call `POST /api/v1/analysis/probability-matrix` via Swagger for MSFT
2. Verify probabilities sum to approximately 1.0 across price levels for any given date
3. Verify probabilities decrease as price levels move further from current price
4. Verify probabilities decrease as dates get closer to expiry (less time = tighter distribution)

---

## Claude Code Prompts

### Prompt A1 (Stream A — run first)
```
Read CLAUDE.md and architecture-plan.md and PHASE-2.9.md.

Create app/analysis/strategy_definitions.py with the four strategy definitions
(steady-paycheck, weekly-grind, trend-rider, lottery-ticket) exactly as specified
in PHASE-2.9.md Stream A section A1. Include all dataclasses and the STRATEGIES dict.

Then create app/analysis/black_scholes.py implementing compute_probability_matrix()
as specified in section A2. Use scipy.stats.norm for the lognormal distribution.
The function should accept current_price, iv (annualized decimal), dte (days),
risk_free_rate, price_range_pct, and price_step. Return a ProbabilityMatrix dataclass
with price_levels, dates (expiry-9, expiry-6, expiry-3, expiry), and a 2D matrix
of probabilities.

Add scipy to requirements.txt if not already present.
```

### Prompt A2 (Stream A — after A1)
```
Read CLAUDE.md and architecture-plan.md and PHASE-2.9.md.

Create app/analysis/strategy_scorer.py implementing score_all_strategies() as
specified in PHASE-2.9.md section A2. The function must:
1. Fetch the options chain ONCE using the provider
2. Fetch current quote and SMA data
3. Run each strategy's scoring function against the same chain data
4. Return List[StrategyScore] with normalized 0-100 scores

For each strategy, compute the relevant metrics defined in its scoring_weights dict
in strategy_definitions.py. Normalize scores using min-max scaling across candidates
for each strategy independently.

Then add two new endpoints to app/api/analysis_routes.py:
- POST /api/v1/analysis/scorecard
- POST /api/v1/analysis/probability-matrix

Both require Tier 1 auth. Define Pydantic schemas in app/models/schemas.py first.
```

### Prompt B1 (Stream B — run simultaneously with A1)
```
Read CLAUDE.md and architecture-plan.md and PHASE-2.9.md.

Create web/src/components/StrategyScorecard.jsx as specified in PHASE-2.9.md
section B2. Use mock data for now — hardcode a mockScores array with four strategies
and scores [84, 71, 91, 23]. The component must:
1. Render a score bar for each strategy (colored gradient red→yellow→green)
2. Support checkbox selection of strategies
3. Show an "Evaluate Selected" button that is disabled until at least one is checked
4. Accept onEvaluate callback prop
5. Show a loading skeleton state when loading=true

Then create web/src/pages/SecurityDashboard.jsx as specified in section B1.
Wire it to use the mock StrategyScorecard. Add the route /security/:symbol to
App.jsx. Add a way to navigate to it from the Watchlist (clicking a symbol goes
to its SecurityDashboard).
```

### Prompt B2 (Stream B — after B1 and after A2 backend is ready)
```
Read CLAUDE.md and PHASE-2.9.md.

Wire SecurityDashboard.jsx to use real data from the backend:
1. Add getStrategyScorecard(symbol) to web/src/api/client.js calling POST /api/v1/analysis/scorecard
2. Replace mock data in SecurityDashboard with the real API call
3. Add loading and error states
4. Update StrategyScorecard to receive real scores

Then update web/src/pages/OptionsTerminal.jsx Stage 2 expansion to include
StrategyScorecard as specified in PHASE-2.9.md section B3. The component receives
the expanded trade as context — pass trade data to the scorecard endpoint as a
pre-populated trade.

Finally update ConfigDrawer as specified in section B4 to be strategy-aware,
rendering the strategy's configSchema when an activeStrategy is set.
```
