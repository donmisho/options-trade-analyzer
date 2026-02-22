# Options Analyzer API

A FastAPI-based options analysis, portfolio tracking, and (future) trading platform with multi-user support, per-trade MFA, and pluggable brokerage providers.

## Architecture

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   Web App    │   │ Excel/Python │   │  MCP (Claude) │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                   │
       └──────────┬───────┘───────────────────┘
                  ▼
        ┌─────────────────┐
        │  FastAPI (REST)  │  ← Single middle tier
        │  Auth + MFA      │
        │  Analysis Engine │
        └────────┬────────┘
                 ▼
        ┌─────────────────┐
        │ Provider Layer   │  ← Adapter pattern
        │ Tradier │ Schwab │
        └─────────────────┘
```

## Quick Start (Local Development)

```bash
# 1. Clone and install
cd options-analyzer
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env: add your Tradier sandbox token and generate a JWT key

# 3. Run
uvicorn app.main:app --reload

# 4. Open API docs
# http://localhost:8000/docs
```

## Project Structure

```
app/
├── main.py              # FastAPI entry point, wires everything together
├── core/
│   ├── config.py        # App settings (pydantic-settings, loads from .env)
│   └── secrets.py       # SecretsManager (Azure Key Vault + .env fallback)
├── auth/
│   ├── service.py       # Password hashing, JWT, TOTP, trade challenges
│   └── dependencies.py  # FastAPI auth middleware (Tier 1/2/3)
├── models/
│   ├── database.py      # SQLAlchemy models (users, config, trades, audit)
│   ├── session.py       # Async DB engine and session factory
│   └── schemas.py       # Pydantic request/response schemas
├── providers/
│   ├── base.py          # Abstract interfaces (MarketData, Account, Trading)
│   ├── tradier.py       # Tradier API adapter
│   └── factory.py       # Creates provider instances by name
├── analysis/            # (Phase 2: scoring, spreads, comparisons)
└── api/
    ├── auth_routes.py   # Register, login, MFA setup/verify
    ├── market_routes.py # Quotes, option chains, expirations
    └── config_routes.py # User analysis preferences
```

## Security Tiers

| Tier | Access | Requires | Example Endpoints |
|------|--------|----------|-------------------|
| 1 | READ | Valid JWT | Quotes, chains, analysis |
| 2 | WRITE | JWT + MFA verified | Config changes, trade journal |
| 3 | TRADE | Per-trade challenge + TOTP | Order execution (Phase 5) |

## Build Phases

- **Phase 0** ✅ Security foundation (auth, MFA, Key Vault, tiers)
- **Phase 1** ✅ Config + Tradier market data adapter
- **Phase 2** 🔲 Analysis engines (vertical spreads, long calls, scoring)
- **Phase 3** 🔲 Portfolio (Schwab account adapter, positions, P/L)
- **Phase 4** 🔲 MCP integration (Claude tools, read-only)
- **Phase 5** 🔲 Trading (per-trade MFA, preview→execute, kill switch)
