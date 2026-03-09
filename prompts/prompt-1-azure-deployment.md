# Session Prompt — Phase 3: Azure Deployment

## Who You Are Talking To
I am an experienced Microsoft AI consultant building a personal options trading analyzer
as both a working tool and a learning project. I have strong conceptual programming
understanding but limited hands-on coding experience. Always explain the "why" behind
each step, not just the "what." I work on Windows with PowerShell. Give all terminal
commands in PowerShell syntax.

## The Project
**Options Trade Analyzer** — a React + FastAPI web app for scoring and ranking options trades.
- GitHub: `https://github.com/donmisho/options-trade-analyzer`
- Backend: Python 3.13 FastAPI at `options-analyzer/app/`
- Frontend: React + Vite at `options-analyzer/web/`
- Local dev root: `C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer`
- Venv folder is `venv` (not `.venv`)

## What Is Already Built and Working
Phases 0-2 are complete and working end-to-end locally:
- JWT auth, MFA via TOTP, invite-code registration
- Schwab OAuth 2.0 fully implemented — live market data, sole provider
- Vertical spreads, long calls, and directional analysis engines
- React frontend with ConfigDrawer, SmaPanel, QuoteBar, FormulaBreakdown
- AI adapter pattern: `AnthropicAdapter` (direct) and `FoundryAdapter` (Azure AI Foundry),
  switchable via env config

## Existing Azure Resources
All in resource group `options-analyzer-rg` (pre-convention name, cannot be renamed).
Naming convention for new resources: `ota-` prefix. See `azure-naming-conventions.md`
in project knowledge.
- SQL Server: `options-analyzer-sql` (`options-analyzer-sql.database.windows.net`)
- SQL Database: `options-analyzer-db`
- App Service: `options-analyzer-api`
- Static Web App: `options-analyzer-web`
- Key Vault: `ota-kv`
- AI Foundry: `ota-foundry`
- **Authentication: Entra ID only — no SQL username/password anywhere**

## What We Are Doing This Session: Phase 3 Azure Deployment

The app currently runs only on my local machine. Phase 3 moves it to Azure so it is
always-on, properly secured, and accessible from anywhere. This must be complete before
building the AI agent features. Work through these steps in order.

### Step 1 — Azure SQL: Migrate from SQLite to Azure SQL
The existing database uses SQLite (a single local file). We need to:
- Update the SQLAlchemy connection string in `app/core/config.py` to use Azure SQL
- Auth method: **Entra ID token auth via `azure-identity`** — no username/password.
  Locally this uses `az login`. On App Service it uses Managed Identity (same code path).
- Run `az login` first if not already authenticated
- Migrate all existing tables: `Users`, `UserConfig`, `AuditLog`, `Favorites`
- Add new tables: `schwab_tokens` (so OAuth tokens survive restarts), `watchlists`
- Also add the agent observability tables defined in `app/skills/ota-agentic-strategy/SKILL.md`:
  `agent_run_log` and `trade_recommendations`
- Verify the connection works locally before touching App Service

Key packages needed: `pyodbc`, `aioodbc`, `azure-identity` (already in requirements.txt?
— verify first). ODBC Driver 18 for SQL Server must be installed locally.

### Step 2 — Azure Key Vault: Move secrets out of .env
- `SecretsManager` in `app/core/secrets.py` already has Key Vault support built in
- Secrets to migrate: Schwab app key, Schwab app secret, JWT signing key,
  Anthropic API key, database connection string
- Enable Managed Identity on the App Service so it can read Key Vault without stored credentials
- Verify locally using `az login` (DefaultAzureCredential will use the logged-in account)

### Step 3 — App Service: Deploy the FastAPI backend
- App Service `options-analyzer-api` already exists — we are deploying to it, not creating it
- Configure as Linux, Python 3.13
- Azure provides free managed SSL certs — configure HTTPS, removing the need for the
  self-signed cert that's currently used in local dev
- Environment variables to set on App Service:
  `AZURE_KEYVAULT_URL`, `APPLICATIONINSIGHTS_CONNECTION_STRING` (once ota-insights exists),
  `SCHWAB_CALLBACK_URL` (update to Azure domain)
- Set up startup command: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Configure health check endpoint

### Step 4 — Static Web App: Deploy the React frontend
- Static Web App `options-analyzer-web` already exists
- Build command: `npm run build` in `options-analyzer/web/`
- Configure API proxy rules: all `/api/*` requests route to the App Service backend URL
- Update CORS in the FastAPI backend to allow the Static Web App domain

### Step 5 — Schwab OAuth callback update
- Update callback URL in Schwab developer portal from `https://127.0.0.1:8000/...`
  to the Azure App Service URL
- Update Key Vault with the new callback URL value
- Test full OAuth flow: login → callback → tokens stored in Azure SQL `schwab_tokens` table

### Step 6 — Tagging and governance
- Verify all resources carry the four required tags:
  `project=options-trade-analyzer`, `environment=dev`, `component=<role>`, `owner=don`
- Set up a basic Azure Monitor cost alert so unexpected charges don't go unnoticed

## Important Patterns to Preserve
- **Entra ID auth only** for Azure SQL — no SQL credentials anywhere
- **SecretsManager abstraction** already handles local (.env) vs cloud (Key Vault) — don't bypass it
- **Provider adapter pattern** for AI calls — `FoundryAdapter` is primary, `AnthropicAdapter` is fallback
- Always give PowerShell commands for terminal steps

## What Is Not In Scope This Session
- Phase 2.6 (Claude Trade Agent) — that comes after Azure is stable
- Entra ID user authentication (replacing invite codes) — Phase 3.6, lower priority
- CI/CD pipeline — stretch goal

## Start Here
First, ask me to confirm the current state:
1. Is ODBC Driver 18 for SQL Server installed? (We were installing it at the end of a prior session)
2. Is Azure CLI installed and is `az login` working?
3. What is the current App Service URL for `options-analyzer-api`?

Then proceed with Step 1.
