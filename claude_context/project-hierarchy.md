# Options Analyzer — Project Hierarchy (Updated 2026-03-31 18:00)

```
Options Analyzer/                          ← VS Code workspace root
│
├── options-analyzer/                      ← The FastAPI backend
│   ├── venv/                              ← Python virtual environment (activate with .\venv\Scripts\Activate.ps1)
│   ├── .env                               ← Secrets + config (Tradier, Schwab, Anthropic, JWT, AI_PROVIDER)
│   ├── .env.example                       ← Template for .env
│   ├── requirements.txt                   ← Python dependencies
│   ├── README.md                          ← Project documentation
│   ├── options_analyzer.db                ← SQLite database (auto-created)
│   ├── certs/                             ← Self-signed SSL certs for local HTTPS
│   │   ├── key.pem
│   │   └── cert.pem
│   │
│   └── app/                               ← All Python code lives here
│       ├── main.py                        ← FastAPI entry point (initializes all providers + routers)
│       │
│       ├── core/                          ← Config & secrets
│       │   ├── config.py                  ← App settings (loads from .env) — includes AI provider settings
│       │   └── secrets.py                 ← SecretsManager (Key Vault + .env fallback)
│       │
│       ├── auth/                          ← Authentication (Phase 0)
│       │   ├── service.py                 ← Password hashing, JWT, TOTP
│       │   └── dependencies.py            ← Auth middleware (Tier 1/2/3)
│       │
│       ├── models/                        ← Data models
│       │   ├── database.py                ← SQLAlchemy models (User, UserConfig)
│       │   ├── session.py                 ← Async DB engine
│       │   └── schemas.py                 ← Pydantic request/response schemas
│       │
│       ├── providers/                     ← API adapters (adapter pattern)
│       │   ├── base.py                    ← Abstract interfaces (MarketData, Account, Trading)
│       │   ├── tradier.py                 ← Tradier market data adapter
│       │   ├── schwab_market_data.py      ← Schwab market data adapter
│       │   ├── schwab_token_manager.py    ← Schwab OAuth token management
│       │   ├── factory.py                 ← Creates provider instances by name
│       │   │
│       │   └── ai/                        ← 🆕 AI provider adapters (added 2026-02-28)
│       │       ├── __init__.py            ← Package exports
│       │       ├── base.py               ← AIProvider interface, TradeContext, TradeVerdict
│       │       ├── prompts.py            ← System prompt, prompt builder, exit levels, pre-screen
│       │       ├── anthropic_adapter.py  ← Direct Anthropic API (active — uses ANTHROPIC_API_KEY)
│       │       └── foundry_adapter.py    ← Azure Foundry adapter (Entra ID or API key auth)
│       │
│       ├── analysis/                      ← Analysis engines (Phase 2 — code written, not tested e2e)
│       │   ├── __init__.py                ← Package exports
│       │   ├── vertical_engine.py         ← Vertical spread scorer
│       │   ├── long_call_engine.py        ← Long call scorer
│       │   ├── directional_engine.py      ← Strategy comparator
│       │   ├── strategy_scorer.py         ← Phase 2.9 multi-strategy scoring engine
│       │   ├── strategy_definitions.py    ← Strategy parameter definitions (thresholds, weights)
│       │   └── black_scholes.py           ← Probability matrix math (Phase 2.11)
│       │
│       └── api/                           ← API routes
│           ├── auth_routes.py             ← Login, register, MFA
│           ├── market_routes.py           ← Quotes, option chains
│           ├── config_routes.py           ← User config (GET/PUT)
│           ├── analysis_routes.py         ← Vertical, long call, directional analysis
│           ├── evaluation_routes.py       ← Trade evaluation via Claude (POST /evaluate/trade)
│           ├── dashboard_routes.py        ← Phase 2.3 dashboard layout GET/PUT + media SAS URLs
│           └── position_routes.py         ← Phase 2.10 positions CRUD (5 endpoints)
│
│
└── web/                                   ← React frontend (Vite, port 5173)
    ├── node_modules/
    ├── package.json
    ├── vite.config.js                     ← Proxy /api to backend with secure: false
    ├── .env.production                    ← Production API base URL (HTTPS)
    ├── staticwebapp.config.json           ← Azure Static Web Apps routing fallback
    ├── public/
    │   └── index.html
    │
    └── src/
        ├── index.js
        ├── App.jsx                        ← Main app with routing
        │
        ├── api/
        │   └── client.js                 ← API bridge (needs evaluateTrade, followUp functions)
        │
        ├── components/                    ← Shared UI components
        │   ├── Layout.jsx                 ← Left rail (200px) — 4 primary items + strategy sub-nav
        │   ├── QuoteBar.jsx               ← Shared symbol header — one component, used everywhere
        │   ├── ResultsTable.jsx           ← Pure display table — controlled columns + expansion rows
        │   ├── StrategyPill.jsx           ← SP/WG/TR/LT abbreviated badge with CSS tooltip
        │   ├── TradeTypeBadge.jsx         ← Trade type badge — title case, bull=green/bear=red
        │   ├── ScoreCell.jsx              ← Score bar + number — threshold colors
        │   ├── StrategyScorecard.jsx      ← Phase 2.9 4-strategy score rows with selection
        │   ├── TradeEvaluationCard.jsx    ← Phase 2.11 structured evaluation result card
        │   ├── ProbabilityMatrix.jsx      ← Phase 2.11 Black-Scholes heatmap visualization
        │   ├── PositionHealthBadge.jsx    ← Phase 2.10 A-F health grade badge
        │   └── TradeDetail/               ← Sections A-E of inline trade detail expansion
        │       ├── index.js               ← Re-exports SectionA…SectionE
        │       ├── SectionA.jsx           ← Trade header (type badge, strikes, key metrics)
        │       ├── SectionB.jsx           ← Exit scenario table (price × P&L)
        │       ├── SectionC.jsx           ← Outcome summary (probabilities, EV)
        │       ├── SectionD.jsx           ← Probability matrix placeholder
        │       └── SectionE.jsx           ← Claude's Read (verdict, analysis, action buttons)
        │
        ├── utils/
        │   ├── formatDate.js              ← formatDate() — always mm-dd-yyyy
        │   └── strategyColors.js          ← STRATEGY_COLORS constant (SP/WG/TR/LT abbr + colors)
        │
        └── pages/
            ├── TradesPage.jsx             ← Trades screen — search, QuoteBar, chart, 3 sections
            ├── StrategyPage.jsx           ← /strategies/:key placeholder (full build in later session)
            ├── SecurityStrategiesPage.jsx ← Scan screen — card grid with 4-strategy score bars
            ├── PositionsPage.jsx          ← Phase 2.10 positions list with health grades
            ├── DashboardPage.jsx          ← Dashboard with insight feed
            ├── VerticalsPage.jsx          ← (deprecated — migrated to TradesPage)
            └── LongCallsPage.jsx          ← (deprecated — migrated to TradesPage)
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /api/v1/auth/register | None | Create account |
| POST | /api/v1/auth/login | None | Get JWT token |
| POST | /api/v1/auth/setup-mfa | Tier 1 | Enable TOTP |
| GET | /api/v1/market/quote/{symbol} | Tier 1 | Stock quote |
| GET | /api/v1/market/chain/{symbol} | Tier 1 | Option chain |
| GET | /api/v1/config | Tier 1 | User config |
| PUT | /api/v1/config | Tier 1 | Update config |
| POST | /api/v1/analyze/verticals | Tier 1 | Score vertical spreads |
| POST | /api/v1/analyze/long-calls | Tier 1 | Score long calls |
| POST | /api/v1/analyze/directional | Tier 1 | Compare strategies |
| **POST** | **/api/v1/evaluate/trade** | **Tier 1** | **🆕 Claude trade evaluation** |
| **POST** | **/api/v1/evaluate/follow-up** | **Tier 1** | **🆕 Follow-up question** |
| **GET** | **/api/v1/evaluate/health** | **None** | **🆕 AI provider health check** |

## .env Configuration (AI section)

```
# --- AI Provider ---
AI_PROVIDER=anthropic              # "anthropic" or "foundry"
ANTHROPIC_API_KEY=sk-ant-...       # Direct Anthropic API key

# --- Azure Foundry (uncomment when quota approved) ---
# AI_PROVIDER=foundry
# FOUNDRY_RESOURCE=ota-foundry
# FOUNDRY_DEPLOYMENT=claude-sonnet-4-6
# FOUNDRY_API_KEY=                  # Leave empty for Entra ID auth
```

## Azure Resources

| Resource | Name | Tags |
|----------|------|------|
| Resource Group | (check portal) | project=options-trade-analyzer, environment=dev, owner=don |
| Azure SQL | (check portal) | component=database |
| App Service | (check portal) | component=api |
| Static Web App | (check portal) | component=web |
| Key Vault | (check portal) | component=secrets |
| **Foundry** | **ota-foundry** | **component=ai** (quota pending for Sonnet 4.6) |

## Startup & Shutdown

### Local Development

**Backend** (from `options-analyzer/`):
```bash
venv\Scripts\activate                          # Windows (PowerShell)
source venv/bin/activate                       # Mac/Linux

# Standard (no HTTPS — most features work)
uvicorn app.main:app --reload

# With HTTPS (required for Schwab OAuth)
uvicorn app.main:app --reload --ssl-keyfile=certs/key.pem --ssl-certfile=certs/cert.pem --host=127.0.0.1 --port=8000
```

**Frontend** (from `web/`):
```bash
npm run dev        # Starts HTTPS dev server on https://localhost:5173
```

To stop: `Ctrl+C` in each terminal.

---

### Azure (Production)

**Backend — App Service** (`options-analyzer-api`):
```bash
az webapp stop    --name options-analyzer-api --resource-group options-analyzer-rg
az webapp start   --name options-analyzer-api --resource-group options-analyzer-rg
az webapp restart --name options-analyzer-api --resource-group options-analyzer-rg
```

- **Cold start (~90s):** F1 Free tier has no Always On — app sleeps after 20 min idle. First request triggers cold start, which includes ODBC Driver 18 install. Subsequent restarts are ~30s (driver already cached).
- **Upgrade to B1 (~$13/mo):** Eliminates cold starts via Always On. Run: `az appservice plan update --name ASP-optionsanalyzerrg-94e9 --resource-group options-analyzer-rg --sku B1` then `az webapp config set --name options-analyzer-api --resource-group options-analyzer-rg --always-on true`

**Frontend — Static Web App** (`options-analyzer-web`):
- Always-on serverless hosting — no start/stop needed.
- Deploys automatically on push to `main` via GitHub Actions.

---

## Phase Tracker

- Phase 0 ✅ Security (auth, MFA, JWT tiers)
- Phase 1 ✅ Config + Tradier market data adapter
- Phase 2 ✅ Analysis engines (code written, not tested end-to-end)
- Phase 2.5 ✅ AI provider layer (Anthropic direct + Foundry adapter)
- Phase 3 🔲 Portfolio (Schwab OAuth, positions)
- Phase 4 🔲 MCP integration
- Phase 5 🔲 Trading (order execution, per-trade MFA)
