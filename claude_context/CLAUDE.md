# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Options Analyzer is a FastAPI-based options analysis, portfolio tracking, and trading platform with:
- Multi-user support with three-tier security (READ/WRITE/TRADE)
- Pluggable provider architecture for market data, AI, and signal sources
- React web frontend for analyzing option spreads and naked positions
- AI-powered trade evaluation via Azure Foundry (Claude)
- Strategy scoring, position tracking, and outcome analytics
- Generic Insight Engine for anomaly detection and AI-generated alerts
- Future support for MCP integration, live trading, and additional signal sources

## Development Commands

### Backend (FastAPI)

```bash
# Setup
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Unix
pip install -r requirements.txt

# Run backend (with auto-reload)
uvicorn app.main:app --reload

# Run with HTTPS (required for Schwab OAuth)
uvicorn app.main:app --reload --ssl-keyfile=key.pem --ssl-certfile=cert.pem --host=127.0.0.1 --port=8000

# API docs
# https://127.0.0.1:8000/docs (Swagger UI)
# https://127.0.0.1:8000/health (Health check)
```

### Frontend (React + Vite)

```bash
cd web
npm install
npm run dev     # Starts dev server with HTTPS proxy to backend
npm run build   # Production build
npm run lint    # ESLint
```

**Important**: The Vite dev server runs on HTTPS (https://localhost:5173) and proxies `/api` requests
to the FastAPI backend at https://127.0.0.1:8000. Both use self-signed certificates in development.

### Testing

```bash
pytest                          # Run all tests
pytest tests/test_something.py  # Run specific file
pytest --cov=app                # With coverage
```

Note: Test infrastructure is minimal. Most validation happens via Swagger UI at /docs.

### Zombie Process Warning (Windows)

Before restarting the backend, always kill existing processes first:
```powershell
Get-Process python,uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force
netstat -ano | findstr ":8000"
```
Windows does not always release port 8000 cleanly. A zombie uvicorn process will answer
requests silently, making new route registrations invisible and causing confusing 404s.

---

## Architecture

### Provider Adapter Pattern

ALL external sources — market data, AI models, signal providers — implement a standard
abstract interface. Adding a new source = writing one adapter class. Zero changes to
engines, routes, or frontend.

**Rule**: Never hardcode a provider name in API routes. Always use `_get_provider()`
or `settings.default_market_data_provider`.

**Current providers**:
- `SchwabMarketData` — primary market data, OAuth-based
- `TradierMarketData` — fallback only, dev/testing without Schwab
- `AnthropicAdapter` — direct Claude API
- `FoundryAdapter` — Azure-hosted Claude (preferred)

**Future providers** (implement `ContextSource` interface):
- `SocialSentimentProvider`
- `FundamentalsProvider`
- `AlternateBrokerageProvider`

### Backend Structure

```
app/
├── main.py                          # FastAPI entry point, lifespan context, CORS
├── core/
│   ├── config.py                   # Pydantic Settings (from .env)
│   └── secrets.py                  # SecretsManager (Azure Key Vault + .env fallback)
├── auth/
│   ├── service.py                  # JWT, passwords, TOTP, trade challenges
│   └── dependencies.py             # require_tier1/2/3 FastAPI dependencies
├── models/
│   ├── database.py                 # SQLAlchemy models
│   ├── session.py                  # Async DB engine and session factory
│   └── schemas.py                  # Pydantic request/response schemas
├── providers/
│   ├── base.py                     # Abstract interfaces (MarketData, ContextSource)
│   ├── tradier.py                  # Tradier adapter (fallback)
│   ├── schwab.py                   # Schwab adapter (primary)
│   ├── schwab_token_manager.py     # OAuth token lifecycle
│   ├── factory.py                  # ProviderFactory
│   └── ai.py                       # AnthropicAdapter + FoundryAdapter
├── analysis/
│   ├── vertical_engine.py          # Bull call / bear put spread scoring
│   ├── long_call_engine.py         # Naked calls/puts scoring
│   ├── directional_engine.py       # SMA momentum + directional scoring
│   ├── black_scholes.py            # [NEW 2.11] Probability matrix computation
│   ├── strategy_scorer.py          # [NEW 2.9] Multi-strategy scorecard engine
│   └── strategy_definitions.py     # Strategy parameter definitions (thresholds, weights)
├── agents/
│   ├── position_monitor.py         # [NEW 3.5] Daily position health agent
│   ├── insight_engine.py           # [NEW 3.6] Generic insight detection + generation
│   └── skill_loader.py             # Loads SKILL.md files, fills variables
├── skills/
│   ├── claude-trade-agent/
│   │   └── SKILL.md
│   ├── position-monitor/
│   │   └── SKILL.md                # [NEW 3.5]
│   └── insight-engine/
│       ├── SKILL.md                # [NEW 3.6] Generic pattern
│       └── domains/
│           └── options/
│               └── SKILL.md        # [NEW 3.6] Options-specific vocabulary
└── api/
    ├── auth_routes.py
    ├── market_routes.py
    ├── config_routes.py
    ├── analysis_routes.py
    ├── schwab_auth_routes.py
    ├── evaluation_routes.py        # [UPDATED 2.11] Structured output, replaces AskClaude
    ├── dashboard_routes.py         # [NEW 2.3] Dashboard layout GET/PUT + media SAS URLs
    ├── position_routes.py          # [NEW 2.10] Position CRUD, follow, take-position
    └── insight_routes.py           # [NEW 3.6] Insight feed, dismiss
```

### Frontend Structure

```
web/
├── .env.production                      # Production API base URL (HTTPS)
├── staticwebapp.config.json             # Azure Static Web Apps routing fallback

web/src/
├── App.jsx                              # Routes + activeStrategy state
├── main.jsx                             # React root
├── context/
│   └── AppContext.jsx                   # activeSymbol, watchlist, favorites, prices
├── api/
│   └── client.js                        # API client functions
├── strategy-configs/                    # Strategy plugin system
│   ├── index.js                         # Registry: maps key → config object
│   ├── verticals.config.js
│   ├── long-calls.config.js
│   ├── steady-paycheck.config.js        # [NEW 2.9]
│   ├── weekly-grind.config.js           # [NEW 2.9]
│   ├── trend-rider.config.js            # [NEW 2.9]
│   └── lottery-ticket.config.js         # [NEW 2.9]
├── components/
│   ├── Layout.jsx                           # Left rail + watchlist toggle + Outlet
│   ├── Header.jsx                           # RETIRED — replaced by Layout.jsx left rail
│   ├── Watchlist.jsx
│   ├── QuoteBar.jsx
│   ├── ConfigDrawer.jsx                 # [UPDATED 2.9] Strategy-aware config schema
│   ├── StrategyScorecard.jsx            # [NEW 2.9] Multi-strategy score display
│   ├── TradeEvaluationCard.jsx          # [NEW 2.11] Structured Claude output card
│   ├── ProbabilityMatrix.jsx            # [NEW 2.11] B-S probability table
│   ├── PositionHealthBadge.jsx          # [NEW 2.10] A-F grade indicator
│   ├── InsightCard.jsx                  # [NEW 3.6] Dashboard insight feed card
│   ├── AskClaudePanel.jsx               # DEPRECATED — remove after 2.11 ships
│   └── ...
└── pages/
    ├── OptionsTerminal.jsx              # PRIMARY: 4-stage analysis shell
    ├── SecurityDashboard.jsx            # [NEW 2.9] Per-symbol strategy scorecard
    ├── PositionsPage.jsx                # [NEW 2.10] Replaces FavoritesPage
    ├── DashboardPage.jsx                # [UPDATED 3.6] Adds insight feed
    ├── VerticalsPage.jsx                # DEPRECATED
    ├── NakedOptionsPage.jsx             # DEPRECATED
    ├── DirectionalPage.jsx
    └── FavoritesPage.jsx                # DEPRECATED — replaced by PositionsPage
```

---

## Data Models (Azure SQL)

All tables use UNIQUEIDENTIFIER PKs and DATETIME2 timestamps.

### positions (Phase 2.10)

```sql
CREATE TABLE positions (
    position_id           UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    user_id               UNIQUEIDENTIFIER NOT NULL,
    symbol                NVARCHAR(20) NOT NULL,
    strategy_key          NVARCHAR(50) NOT NULL,       -- 'steady-paycheck', 'trend-rider'
    trade_structure       NVARCHAR(MAX) NOT NULL,      -- JSON: legs, strikes, expiry
    source                NVARCHAR(10) NOT NULL,       -- 'PAPER' | 'LIVE'
    status                NVARCHAR(20) NOT NULL,       -- 'FOLLOWING'|'LIVE'|'CLOSED'
    entry_price           DECIMAL(10,4),
    entry_date            DATETIME2 NOT NULL,
    entry_greeks          NVARCHAR(MAX),               -- JSON: delta, gamma, theta, vega
    entry_iv_rank         DECIMAL(5,2),
    entry_sma_alignment   NVARCHAR(MAX),               -- JSON: SMA values + signal
    entry_underlying_price DECIMAL(10,4),
    claude_probability_matrix NVARCHAR(MAX),           -- JSON: B-S matrix at entry
    claude_exit_levels    NVARCHAR(MAX),               -- JSON: warning, scale_out, stop
    claude_verdict        NVARCHAR(MAX),               -- JSON: full evaluation card
    claude_score          INT,                         -- 0-100
    health_grade          NVARCHAR(2),                 -- 'A'|'B'|'C'|'D'|'F'
    current_price         DECIMAL(10,4),               -- updated by monitor agent
    current_pnl           DECIMAL(10,4),               -- updated by monitor agent
    last_monitored_at     DATETIME2,
    exit_price            DECIMAL(10,4),
    exit_date             DATETIME2,
    exit_reason           NVARCHAR(50),                -- TARGET|WARNING|STOP|EXPIRED|MANUAL
    outcome_pnl           DECIMAL(10,4),
    created_at            DATETIME2 DEFAULT GETUTCDATE(),
    updated_at            DATETIME2 DEFAULT GETUTCDATE()
)
```

### symbol_context (Phase 3.5)

```sql
CREATE TABLE symbol_context (
    context_id    UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    symbol        NVARCHAR(20) NOT NULL,
    source_id     NVARCHAR(50) NOT NULL,
    signal_type   NVARCHAR(50) NOT NULL,
    signal_value  NVARCHAR(MAX) NOT NULL,
    captured_at   DATETIME2 DEFAULT GETUTCDATE(),
    expires_at    DATETIME2 NOT NULL
)
```

### insights (Phase 3.6)

```sql
CREATE TABLE insights (
    insight_id          UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    domain              NVARCHAR(50) NOT NULL,
    entity_id           NVARCHAR(100) NOT NULL,
    entity_label        NVARCHAR(200) NOT NULL,
    observation         NVARCHAR(MAX) NOT NULL,
    baseline            NVARCHAR(MAX) NOT NULL,
    deviation_score     INT NOT NULL,
    deviation_type      NVARCHAR(50) NOT NULL,
    title               NVARCHAR(200) NOT NULL,
    body                NVARCHAR(1000) NOT NULL,
    severity            NVARCHAR(20) NOT NULL,
    recommended_actions NVARCHAR(MAX),
    status              NVARCHAR(20) DEFAULT 'ACTIVE',
    source_signals      NVARCHAR(MAX),
    agent_run_id        UNIQUEIDENTIFIER,
    created_at          DATETIME2 DEFAULT GETUTCDATE(),
    dismissed_at        DATETIME2,
    acted_on_at         DATETIME2
)
```

### agent_run_log (Phase 2.6 — existing)

Every AI agent invocation writes one row. Never deleted.

---

## Key API Endpoints (New/Updated)

### Phase 2.9 — Strategy Scoring
- `POST /api/v1/analyze/scorecard` — runs all strategies for a symbol, returns 0-100 per strategy
- `POST /api/v1/analyze/probability-matrix` — Black-Scholes matrix for a trade

### Phase 2.11 — Structured Evaluation
- `POST /api/v1/evaluate/structured` — Claude deep dive, returns structured cards
- Replaces: `POST /api/v1/evaluate/trade` (deprecated)

### Phase 2.10 — Positions
- `POST /api/v1/positions/follow` — create paper position from evaluation
- `POST /api/v1/positions/take` — create live position (records intent, not yet wired to Schwab)
- `GET /api/v1/positions` — list with filters: status, source, symbol, strategy
- `PATCH /api/v1/positions/{id}/close` — close position, record outcome
- `GET /api/v1/positions/aggregate` — stats by strategy group

### Phase 3.5 — Position Monitor
- `POST /api/v1/agents/position-monitor/run` — on-demand trigger (also runs on schedule)

### Phase 3.6 — Insights
- `GET /api/v1/insights` — active insights feed, filtered by domain='options'
- `PATCH /api/v1/insights/{id}/dismiss` — dismiss insight

---

## Common Patterns

### Adding a New Strategy (Phase 2.9+)

1. Create `web/src/strategy-configs/your-strategy.config.js` with full config schema
2. Register in `strategy-configs/index.js`
3. Add scoring logic to `app/analysis/strategy_scorer.py`
4. Strategy scores appear in the scorecard panel and OptionsTerminal renders it automatically

### Adding a New Signal Source (Phase 3.5+)

1. Create `app/providers/your_source.py` implementing `ContextSource`
2. Register in `ProviderFactory`
3. Define `ttl_seconds()` for appropriate freshness window
4. Position Monitor Agent automatically picks it up on next run

### Adding a New Insight Domain (Phase 3.6+)

1. Create `app/skills/insight-engine/domains/your-domain/SKILL.md`
2. Create observation source adapter for the domain
3. Deploy with `domain='your-domain'` in insight records
4. Dashboard feed filters by domain automatically

### Adding a New API Endpoint

1. Define Pydantic schemas in `app/models/schemas.py`
2. Add route in appropriate `app/api/*_routes.py`
3. Add corresponding function to `web/src/api/client.js`

---

## Important Implementation Details

### Schwab OAuth Flow

Schwab requires HTTPS. Backend must run on https://127.0.0.1:8000 with self-signed certs.
See SCHWAB-LOGIN-PROCESS.md for full details.

### Black-Scholes Probability Matrix

Computed in `app/analysis/black_scholes.py`. NOT by Claude. Claude receives the
pre-computed matrix as context. Inputs: current price, IV, DTE, risk-free rate.
Output: probability of price at each level (±10% in $10 steps) at dates:
expiry-9, expiry-6, expiry-3, expiry.

### Strategy Config Schema

Each strategy config file exports a `configSchema` array. ConfigDrawer renders
whatever schema the active strategy defines. Fields have type, label, min, max,
default, and step. This replaces the static 14-field systemVars approach.

### Position Health Grade

Computed by Position Monitor Agent from deterministic math against Claude's exit
levels stored at position entry. Grade: A (on track) → F (thesis invalid).
Updated daily after market close. Also computable on-demand.

### Insight Engine Escalation

Position Monitor detects a threshold crossing → calls `InsightEngine.generate()`
with observation context → Claude call using domain SKILL.md → structured insight
written to SQL → appears on Dashboard feed. One Claude call per detected deviation
per position per day maximum.

### AskClaudePanel Deprecation

`AskClaudePanel` is retired in Phase 2.11. It is replaced by:
- `StrategyScorecard` — shows strategy scores per symbol or trade
- `TradeEvaluationCard` — shows Claude's structured output per strategy
- `ProbabilityMatrix` — shows B-S probability table

The new flow is: select strategies → single Evaluate call → structured cards back.
No open-ended chat. Claude is an analytical engine, not a conversationalist.

---

## UI Decisions — Read This First

All finalized UI decisions live in `UI-DECISIONS.md` in the project root.
Before building or modifying ANY frontend component, read that file.
It is the visual contract. When it conflicts with other sources, it wins.

Key decisions summarized:
- Nav: Left rail (220px fixed). Items top-to-bottom: Dashboard · Security Strategies · Verticals · Puts & Calls · Positions. Watchlist is a collapsible panel in the content area, not a column.
- Strategy tabs (Steady Paycheck etc.) do NOT appear in nav — scoring lenses only
- QuoteBar is ONE shared component used identically on every page
- Watchlist click navigates to Security Strategies for that symbol
- Verticals expansion: all 4 strategies shown in scorecard
- Puts & Calls expansion: only long_option strategies scored; credit_spread shown grayed out
- Strategy filtering MUST use trade_structure field, never hardcoded strategy names

---

## House Style Rules

- **Date format**: ALWAYS mm-dd-yyyy. With time: mm-dd-yyyy hh:mm. Use `formatDate()` from `web/src/utils/formatDate.js`. No other date formatting allowed.
- **No `$` in UI**: Display `567.23` not `$567.23`
- **Health pips**: Each pip is its own column — never group in a single cell
- **`getHealthPips` signature**: Always `getHealthPips(trade, systemVars)`
- **Schwab index symbols**: Use `apiSymbol` field for mapping (e.g. `.INX` → `$SPX`)
- **Provider routing**: Never hardcode `"tradier"` — always use `_get_provider()`
- **Prompts in SKILL.md**: Never hardcode prompts in Python or React
- **Position source labels**: Display "Paper" and "Live" (not "PAPER"/"LIVE") in UI
- **Health grades**: Display as letter (A/B/C/D/F) with color: A=green, B=teal, C=yellow, D=orange, F=red

## Known Limitations / Future Work

- No backend tests yet (validation via Swagger UI)
- MCP integration (Phase 4) not started
- Live trading execution (Phase 5) not started
- Social sentiment, fundamentals providers not yet built
- Watchlist/favorites not yet synced to backend (localStorage only)
