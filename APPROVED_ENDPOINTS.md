# Approved External Endpoints

QA agents and shared scripts are authorized to call only the endpoints listed here.
Any call to an unlisted external endpoint requires human approval.

## Market Data & Brokerage

| Endpoint | Purpose |
|----------|---------|
| `https://api.schwab.com` | Schwab market data and OAuth |
| `https://api.tradier.com` | Tradier market data (fallback/dev) |

## AI / Azure

| Endpoint | Purpose |
|----------|---------|
| `https://ota-foundry-resource.services.ai.azure.com` | Azure Foundry (Claude) AI inference |
| `https://options-analyzer.vault.azure.net` | Azure Key Vault secrets |
| `https://options-analyzer-sql.database.windows.net` | Azure SQL database |

## Jira / Atlassian

| Endpoint | Purpose |
|----------|---------|
| `https://tmtctech-team.atlassian.net` | Jira REST API for QA agent spec retrieval |

## Teams / Power Automate

| Endpoint | Purpose |
|----------|---------|
| `*.environment.api.powerplatform.com` | Power Automate Workflow webhooks for Teams notifications (QA agent system) |

## Local Development

| Endpoint | Purpose |
|----------|---------|
| `http://localhost:5173` | Frontend dev server (Vite) |
| `https://localhost:5173` | Frontend dev server (Vite, HTTPS) |
| `http://localhost:8000` | Backend API (uvicorn) |
| `https://127.0.0.1:8000` | Backend API (uvicorn, HTTPS) |
