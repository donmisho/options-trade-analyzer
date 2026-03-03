# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Options Analyzer is a FastAPI-based options analysis, portfolio tracking, and trading platform with:
- Multi-user support with three-tier security (READ/WRITE/TRADE)
- Pluggable brokerage provider architecture (currently Tradier + Schwab)
- React web frontend for analyzing option spreads and naked positions
- AI-powered trade evaluation (Anthropic or Azure Foundry)
- Future support for MCP integration and Excel/Python clients

## Development Commands

### Backend (FastAPI)

```bash
# Setup
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Unix
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env: add TRADIER_API_TOKEN and generate JWT_SIGNING_KEY

# Run backend (with auto-reload)
uvicorn app.main:app --reload

# Run with HTTPS (required for Schwab OAuth)
uvicorn app.main:app --reload --ssl-keyfile=key.pem --ssl-certfile=cert.pem --host=127.0.0.1 --port=8000

# API docs
# http://localhost:8000/docs (Swagger UI)
# http://localhost:8000/health (Health check)
```

### Frontend (React + Vite)

```bash
cd web
npm install
npm run dev     # Starts dev server with HTTPS proxy to backend
npm run build   # Production build
npm run lint    # ESLint
```

**Important**: The Vite dev server runs on HTTPS (https://localhost:5173) and proxies `/api` requests to the FastAPI backend at https://127.0.0.1:8000. Both use self-signed certificates in development.

### Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_something.py

# Run with coverage
pytest --cov=app
```

Note: Test infrastructure is minimal as of v1.3.0. Most validation happens via the Swagger UI at /docs during development.

## Architecture

### Provider Adapter Pattern

The core architectural decision is the **adapter pattern** for data sources. All market data, account, and trading operations go through abstract interfaces defined in `app/providers/base.py`:

- `MarketDataProvider`: Quote, option chain, expirations, strikes
- `AccountProvider`: Positions, balances, orders, P/L (Phase 3)
- `TradingProvider`: Preview, place, cancel orders (Phase 5)

**Why**: Adding a new brokerage requires writing one adapter class that implements these interfaces. Zero changes to API endpoints or analysis engines.

**Current providers**:
- `TradierMarketData` (app/providers/tradier.py) — sandbox and production market data
- `SchwabMarketData` (app/providers/schwab.py) — OAuth-based market data with auto-refreshing tokens

The `ProviderFactory` (app/providers/factory.py) creates provider instances based on user configuration and caches them by user_id to reuse HTTP clients.

### Backend Structure

```
app/
├── main.py                    # FastAPI app entry point, lifespan context, CORS
├── core/
│   ├── config.py             # Pydantic Settings (from .env)
│   └── secrets.py            # SecretsManager (Azure Key Vault + .env fallback)
├── auth/
│   ├── service.py            # AuthService: JWT, passwords, TOTP, trade challenges
│   └── dependencies.py       # FastAPI auth dependencies (Tier 1/2/3)
├── models/
│   ├── database.py           # SQLAlchemy models (User, UserConfig, AuditLog)
│   ├── session.py            # Async DB engine and session factory
│   └── schemas.py            # Pydantic request/response schemas
├── providers/
│   ├── base.py               # Abstract provider interfaces
│   ├── tradier.py            # Tradier adapter
│   ├── schwab.py             # Schwab adapter
│   ├── schwab_token_manager.py # OAuth token lifecycle for Schwab
│   ├── factory.py            # ProviderFactory
│   └── ai.py                 # AnthropicAdapter + FoundryAdapter for trade eval
├── analysis/
│   ├── vertical_engine.py    # Scores bull call / bear put spreads
│   ├── long_call_engine.py   # Scores naked calls/puts
│   └── directional_engine.py # Directional momentum + SMA logic
└── api/
    ├── auth_routes.py         # /register, /login, /mfa/*
    ├── market_routes.py       # /market/quote, /market/chain
    ├── config_routes.py       # /config (user preferences)
    ├── analysis_routes.py     # /analyze/verticals, /analyze/long-calls
    ├── schwab_auth_routes.py  # /auth/schwab/* OAuth flow
    └── evaluation_routes.py   # /evaluate/trade, /evaluate/follow-up (AI)
```

**Key patterns**:
1. **Lifespan context** (main.py): Initializes singletons (DB, SecretsManager, ProviderFactory, SchwabTokenManager) at startup
2. **Dependency injection**: `provider_factory` is initialized in lifespan, then passed to route modules via `init_*_routes(factory)`
3. **Three-tier auth**: Tier 1 (READ) = valid JWT, Tier 2 (WRITE) = JWT + MFA verified, Tier 3 (TRADE) = per-trade TOTP challenge

### Frontend Structure

```
web/src/
├── App.jsx                   # Routes: /verticals, /naked-options, /directional, /favorites
├── main.jsx                  # React root, wraps App in AppProvider
├── context/
│   └── AppContext.jsx        # Shared state: activeSymbol, watchlist, favorites, prices
├── api/
│   └── client.js             # API client functions (getQuote, analyzeVerticals, etc.)
├── components/
│   ├── Layout.jsx            # Header + Watchlist + <Outlet> for page content
│   ├── Header.jsx            # Logo, tabs, Schwab status, config button
│   ├── Watchlist.jsx         # Sidebar with live prices
│   ├── QuoteBar.jsx          # Top bar showing active symbol price + 52w range
│   ├── ResultsTable.jsx      # Sortable table of analyzed trades with star button
│   ├── ConfigDrawer.jsx      # Settings slideout (SMA periods, score weights)
│   ├── FormulaBreakdownPanel.jsx # Shows score formula + raw values
│   ├── AskClaudePanel.jsx    # AI trade evaluation slideout
│   └── ...                   # ScoreBar, Toast, SymbolInput, FavoritesTab, etc.
└── pages/
    ├── VerticalsPage.jsx     # Bull call / bear put spreads
    ├── NakedOptionsPage.jsx  # Naked calls/puts
    ├── DirectionalPage.jsx   # Long calls with directional momentum
    └── FavoritesPage.jsx     # Saved trades with current vs. saved prices
```

**State management**:
- `AppContext` provides `activeSymbol`, `watchlist`, `favorites`, `prices`, `configOpen` to all components
- `localStorage` persists watchlist, favorites (30-day TTL), and active symbol across sessions
- Live prices fetched in parallel using `Promise.all` on mount and watchlist changes

**Routing**:
- React Router v6 nested layout: `<Layout>` renders header + watchlist, child routes render in `<Outlet>`
- Default route `/` redirects to `/verticals`

### Analysis Engines

Located in `app/analysis/`, these score option trades using a composite weighted formula:

1. **VerticalEngine** (vertical_engine.py):
   - Generates all valid bull call and bear put spreads from an option chain
   - Scores each on: Expected Value (35%), Reward:Risk (25%), Probability (20%), Liquidity (15%), Theta Efficiency (5%)
   - Filters by delta range (0.15-0.45 short strike), min open interest (50), min volume (5), min R:R (0.5:1)
   - Returns sorted by composite score (0-100)

2. **LongCallEngine** (long_call_engine.py):
   - Scores naked calls/puts
   - Similar scoring: EV, R:R, Probability, Liquidity, Theta
   - Used by both NakedOptionsPage and DirectionalPage

3. **DirectionalEngine** (directional_engine.py):
   - Adds momentum analysis: 20/50/200 SMA alignment, 52-week range position
   - Combines technical indicators with LongCallEngine scores
   - Filters for trending stocks with directional bias

**Important**: All engines normalize raw metrics (e.g., $500 EV, 3.0 R:R) to 0-1 scores before applying weights. This makes the weights meaningful percentages.

### AI Trade Evaluation

Located in `app/providers/ai.py`, implements a provider abstraction for Claude:

- `AnthropicAdapter`: Direct calls to Anthropic API
- `FoundryAdapter`: Calls Azure Foundry (Azure-hosted Claude)

Both implement the same interface: `evaluate_trade(trade_details)` returns verdict + analysis + exit levels.

The AI provider is selected in `.env` via `AI_PROVIDER=anthropic` or `AI_PROVIDER=foundry`.

## Configuration

### Environment Variables (.env)

Required for local development:
```bash
DEBUG=true
JWT_SIGNING_KEY=<64-char hex>           # Generate: python -c "import secrets; print(secrets.token_hex(32))"
TRADIER_API_TOKEN=<your-token>          # From dash.tradier.com/settings/api
TRADIER_ENVIRONMENT=sandbox             # or "production"
SCHWAB_APP_KEY=<your-key>               # From developer.schwab.com
SCHWAB_APP_SECRET=<your-secret>
```

Optional:
```bash
AZURE_KEYVAULT_URL=https://your-vault.vault.azure.net  # For production
AI_PROVIDER=anthropic                   # or "foundry"
ANTHROPIC_API_KEY=<key>                 # For direct Anthropic
FOUNDRY_RESOURCE=<resource>             # For Azure Foundry
```

### Security Tiers

| Tier | Requires | Endpoints |
|------|----------|-----------|
| 1 (READ) | Valid JWT | /market/*, /analyze/*, /config (GET) |
| 2 (WRITE) | JWT + MFA verified | /config (PUT), trade journal |
| 3 (TRADE) | Per-trade TOTP challenge | /trade/* (Phase 5) |

Implemented in `app/auth/dependencies.py` via `require_tier1()`, `require_tier2()`, `require_tier3()` FastAPI dependencies.

### Database

SQLite (async via aiosqlite) for development. Tables auto-created on startup via `init_db()` in app/models/session.py.

Models: `User`, `UserConfig`, `AuditLog` (app/models/database.py).

Production will swap to PostgreSQL by changing `DATABASE_URL` in .env.

## Common Patterns

### Adding a New Provider

1. Create `app/providers/yourbroker.py` implementing `MarketDataProvider` (and/or `AccountProvider`, `TradingProvider`)
2. Register in `PROVIDER_REGISTRY` in `app/providers/factory.py`
3. Add any broker-specific config to `app/core/config.py`
4. Test via `/docs` Swagger UI

### Adding a New Analysis Engine

1. Create `app/analysis/your_engine.py` with a function that takes an option chain and returns scored trades
2. Add route in `app/api/analysis_routes.py`
3. Add frontend call in `web/src/api/client.js`
4. Create page component in `web/src/pages/YourPage.jsx`
5. Add route in `web/src/App.jsx`

### Adding a New API Endpoint

1. Define Pydantic request/response schemas in `app/models/schemas.py`
2. Add route function in appropriate `app/api/*_routes.py` file
3. Use dependency injection for `provider_factory` or `db: AsyncSession`
4. Add corresponding function to `web/src/api/client.js`

## Important Implementation Details

### Schwab OAuth Flow

Schwab requires HTTPS for OAuth callbacks. The backend must run on https://127.0.0.1:8000 with self-signed certs (key.pem, cert.pem).

Flow:
1. User clicks "Connect Schwab" → frontend opens `/auth/schwab/login`
2. Backend redirects to Schwab OAuth
3. User approves → Schwab redirects to `/auth/schwab/callback`
4. Backend exchanges code for access + refresh tokens
5. Tokens stored in database (encrypted in production via Key Vault)
6. `SchwabTokenManager` (app/providers/schwab_token_manager.py) auto-refreshes tokens before expiry

### Frontend HTTPS + Proxy

The Vite dev server (vite.config.js) runs on HTTPS using cert.pem/key.pem and proxies `/api/*` requests to the backend. This is required because:
1. Schwab OAuth callback needs HTTPS
2. Browsers block mixed content (HTTPS frontend → HTTP backend)

First time: Visit https://127.0.0.1:8000/docs and https://localhost:5173 and accept the self-signed cert warnings.

### Score Formula Architecture

All analysis engines follow this pattern:
1. Generate candidate trades from option chain
2. Filter out invalid trades (bad liquidity, extreme deltas, etc.)
3. Calculate raw metrics (EV in $, R:R ratio, probability as decimal)
4. Normalize each metric to 0-1 using min-max scaling across all candidates
5. Apply user weights (sum = 1.0) to normalized scores
6. Sum weighted scores → composite score (0-1, shown as 0-100 in UI)

The normalization step is critical: it allows comparing apples (dollars) to oranges (ratios) via consistent 0-1 scales.

### Favorites System

Trades can be starred from any analysis page. Favorites are stored in `localStorage` with:
- Original trade details (strikes, expiration, prices, scores)
- `savedAt` timestamp (30-day TTL)
- `savedDate` for display
- Unique `id` built from trade details to prevent duplicates

The FavoritesPage refetches current quotes and shows delta from saved price, allowing users to track if a trade idea improved or worsened since they bookmarked it.

## Known Limitations / Future Work

- No backend tests yet (validation via Swagger UI in development)
- SQLite in development; PostgreSQL for production
- MCP integration (Phase 4) not started
- Trading execution (Phase 5) not started
- No persistent favorites/watchlist sync to backend (currently localStorage only)