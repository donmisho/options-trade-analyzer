# Options Analyzer — Project Hierarchy (Updated 2026-02-28)

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
│       │   └── directional_engine.py      ← Strategy comparator
│       │
│       └── api/                           ← API routes
│           ├── auth_routes.py             ← Login, register, MFA
│           ├── market_routes.py           ← Quotes, option chains
│           ├── config_routes.py           ← User config (GET/PUT)
│           ├── analysis_routes.py         ← Vertical, long call, directional analysis
│           └── evaluation_routes.py       ← 🆕 Trade evaluation via Claude (POST /evaluate/trade)
│
│
└── web/                                   ← React frontend (Vite, port 5173)
    ├── node_modules/
    ├── package.json
    ├── vite.config.js                     ← Proxy /api to backend with secure: false
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
        ├── components/                    ← 🔲 TODO: Move prototypes here
        │   ├── Layout.jsx                 ← Sidebar nav + top bar
        │   ├── Chart.jsx                  ← (placeholder)
        │   └── shared.jsx                 ← (placeholder)
        │
        └── pages/
            ├── VerticalsPage.jsx          ← Vertical spread analysis screen
            ├── LongCallsPage.jsx          ← Long call analysis screen
            └── (other pages planned)
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

## Phase Tracker

- Phase 0 ✅ Security (auth, MFA, JWT tiers)
- Phase 1 ✅ Config + Tradier market data adapter
- Phase 2 ✅ Analysis engines (code written, not tested end-to-end)
- Phase 2.5 ✅ AI provider layer (Anthropic direct + Foundry adapter)
- Phase 3 🔲 Portfolio (Schwab OAuth, positions)
- Phase 4 🔲 MCP integration
- Phase 5 🔲 Trading (order execution, per-trade MFA)
