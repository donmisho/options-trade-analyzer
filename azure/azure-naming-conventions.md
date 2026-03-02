# Options Analyzer — Azure Naming & Tagging Conventions

## Resource Naming Pattern

All Azure resources for this project use the `ota-` prefix (**O**ptions **T**rade **A**nalyzer) followed by a short descriptor of what the resource does.

| Resource Type | Name | Region | Notes |
|--------------|------|--------|-------|
| Resource Group | `ota-rg` | — | Contains all project resources |
| Azure SQL Server | `ota-sql` | East US 2 | Database server |
| Azure SQL Database | `ota-db` | East US 2 | Application database |
| App Service (backend) | `ota-api` | East US 2 | FastAPI backend |
| Static Web App (frontend) | `ota-web` | East US 2 | React frontend |
| Key Vault | `ota-kv` | East US 2 | Secrets (API keys, JWT, OAuth tokens) |
| Microsoft Foundry | `ota-foundry` | East US 2 | Claude AI models for trade evaluation |
| App Service Plan | `ota-plan` | East US 2 | Hosting plan for ota-api |

> **Note**: Confirm existing resource names in the Azure Portal — some may have been created with slightly different names before this convention was established. Rename or alias where possible; at minimum, apply tags consistently.

---

## Required Tags (apply to ALL resources)

Every Azure resource in this project **must** have these four tags:

| Tag Key | Value | Purpose |
|---------|-------|---------|
| `project` | `options-trade-analyzer` | Groups all costs for this project. Matches the GitHub repo name. |
| `environment` | `dev` or `prod` | Distinguishes development from production resources. |
| `component` | See table below | Identifies the role of this specific resource. |
| `owner` | `don` | Who owns/manages this resource. |

### Component Tag Values

| Component Value | Used For |
|----------------|----------|
| `ai` | Microsoft Foundry (Claude models) |
| `api` | App Service (FastAPI backend) |
| `web` | Static Web App (React frontend) |
| `database` | Azure SQL Server + Database |
| `secrets` | Key Vault |
| `hosting` | App Service Plan |

---

## How to Use Tags for Cost Tracking

### View all project costs
1. Azure Portal → **Cost Management** → **Cost Analysis**
2. Add filter: `project` = `options-trade-analyzer`
3. This shows total spend across all resources

### Break down by component
1. Same view as above
2. Group by: `component`
3. See cost distribution: AI vs API vs Database vs Web vs Secrets

### Compare dev vs production
1. Filter by `project` = `options-trade-analyzer`
2. Group by: `environment`
3. See dev spend vs production spend side by side

---

## Adding Tags to Existing Resources

For any resource that doesn't have tags yet:
1. Open the resource in Azure Portal
2. Click **Tags** in the left sidebar
3. Add all four tags with appropriate values
4. Click **Apply**

This can be done without any downtime or service disruption.

---

## Future Resources

When creating any new Azure resource for this project:
1. Use the `ota-` prefix + short descriptor
2. Place in the same resource group (`ota-rg`)
3. Use East US 2 region for consistency
4. Apply all four tags during creation (the Tags step in the creation wizard)

Examples of future resources:
| Resource | Suggested Name | Component Tag |
|----------|---------------|---------------|
| Redis Cache (if needed) | `ota-cache` | `cache` |
| Application Insights | `ota-insights` | `monitoring` |
| Storage Account | `ota-storage` | `storage` |
| SignalR (if needed for live data) | `ota-signalr` | `realtime` |
