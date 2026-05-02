# Prod App Service Migration to West US 2

**Goal:** Eliminate cross-region traffic between the prod App Service (currently Central US) and Azure SQL (West US 2) by deploying a new prod App Service in West US 2 and cutting over traffic.

**Why:** Intermittent `08001 TCP RST` errors at SQL connection handshake have been plaguing prod under any meaningful load. Cross-region network round-trips during connection handshake are the most plausible standing root cause. Fix is structural — co-locate the App Service with the database.

**Estimated time:** 2–3 hours of focused work. Block 3 hours.

---

## Pre-work

### Status

- [x] Inventory captured tonight (2026-04-27 ~9:22 PM)
  - `C:\Users\DonMishory\Downloads\prod-appsettings.json`
  - `C:\Users\DonMishory\Downloads\prod-identity.json`
  - `C:\Users\DonMishory\Downloads\prod-webconfig.json`
  - `C:\Users\DonMishory\Downloads\prod-hostnames.json`
- [x] DATABASE_URL verified in `prod-appsettings.json` with all four parameters present

### Tomorrow morning, before starting Phase 1

- [ ] Take screenshot of Entra app registration's Redirect URIs page
  - Azure Portal → Entra ID → App registrations → search for client ID `f11ea8b8...` → Authentication → Redirect URIs
- [ ] Take screenshot of current prod App Service overview page
  - Capture: Status, URL, App Service Plan name, Region
  - This is the "before" reference for the migration
- [ ] Open the four JSON files in Notepad or VS Code for easy reference
- [ ] Decide: also migrate dev in this session?
  - **Recommended yes.** Adds ~1 hour. Eliminates the same cross-region tax for dev.

---

## Phase 1: Provision new prod App Service in West US 2 (~15 min)

### 1.1. Create new App Service Plan

```powershell
az appservice plan create `
  --name ASP-optionsanalyzer-westus2 `
  --resource-group options-analyzer-rg `
  --location westus2 `
  --sku B1 `
  --is-linux
```

### 1.2. Create new App Service

Temp name: `options-analyzer-api-v2` (we'll deal with naming in Phase 9)

```powershell
az webapp create `
  --name options-analyzer-api-v2 `
  --resource-group options-analyzer-rg `
  --plan ASP-optionsanalyzer-westus2 `
  --runtime "PYTHON:3.13"
```

### 1.3. Enable system-assigned managed identity

```powershell
az webapp identity assign `
  --name options-analyzer-api-v2 `
  --resource-group options-analyzer-rg
```

**Capture the new MSI's `principalId` from the output.** You'll need it for Phase 2.

### 1.4. Configure Always On

```powershell
az webapp config set `
  --name options-analyzer-api-v2 `
  --resource-group options-analyzer-rg `
  --always-on true
```

### Verify Phase 1

- [ ] New App Service exists in West US 2
- [ ] MSI principal ID captured
- [ ] Always On enabled

---

## Phase 2: Configure access for new MSI (~10 min)

### 2.1. Grant new MSI access to Key Vault

Replace `<NEW_MSI_PRINCIPAL_ID>` with the value from Phase 1.3.

```powershell
az keyvault set-policy `
  --name options-analyzer `
  --object-id <NEW_MSI_PRINCIPAL_ID> `
  --secret-permissions get list
```

### 2.2. Grant new MSI access to Azure SQL

In SSMS, connect to `options-analyzer-sql.database.windows.net` with Entra MFA.

Run against the `options-analyzer-db` database:

```sql
USE [options-analyzer-db];

CREATE USER [options-analyzer-api-v2] FROM EXTERNAL PROVIDER;

ALTER ROLE db_datareader ADD MEMBER [options-analyzer-api-v2];
ALTER ROLE db_datawriter ADD MEMBER [options-analyzer-api-v2];
ALTER ROLE db_ddladmin ADD MEMBER [options-analyzer-api-v2];
```

### Verify Phase 2

```sql
SELECT name, type_desc 
FROM sys.database_principals 
WHERE name = 'options-analyzer-api-v2';
```

Should return one row with `type_desc = EXTERNAL_USER`.

```sql
SELECT r.name AS role_name, m.name AS member_name
FROM sys.database_role_members rm
JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id
JOIN sys.database_principals m ON rm.member_principal_id = m.principal_id
WHERE m.name = 'options-analyzer-api-v2';
```

Should return three rows: `db_datareader`, `db_datawriter`, `db_ddladmin`.

---

## Phase 3: Replicate app settings (~10 min)

### 3.1. Set env vars via portal Advanced Edit

**Use the portal, not the CLI.** The portal handles `&` characters in DATABASE_URL correctly. The CLI from PowerShell does not.

1. Azure Portal → search for `options-analyzer-api-v2` → click the App Service
2. Left nav → Settings → Environment variables
3. Click the **App settings** tab
4. Click **Advanced edit**
5. Replace the JSON in the editor with the contents of `prod-appsettings.json` (from pre-work)
6. Click **OK**
7. Click **Apply** at the bottom of the main page
8. Confirm the restart prompt

### 3.2. Verify env vars

```powershell
az webapp config appsettings list `
  --name options-analyzer-api-v2 `
  --resource-group options-analyzer-rg `
  --query "[?name=='DATABASE_URL'].value" -o tsv
```

Should show the full URL with all four parameters:
```
mssql+pyodbc://options-analyzer-sql.database.windows.net:1433/options-analyzer-db?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no&authentication=ActiveDirectoryMsi
```

### Verify Phase 3

- [ ] DATABASE_URL has all four parameters
- [ ] All other env vars from `prod-appsettings.json` are present

---

## Phase 4: Deploy app code to new App Service (~15 min)

### 4.1. Modify deploy workflow

Two options:

**Option A (recommended):** Duplicate `deploy-to-prod.yml` as `deploy-to-prod-v2.yml`. In the new file:
- Change every reference to `options-analyzer-api` to `options-analyzer-api-v2`
- Change the smoke test URL to `https://options-analyzer-api-v2.azurewebsites.net/api/v1/health/detailed`
- Change the confirm_deploy guard string to `DEPLOY-V2` to avoid accidental triggering

**Option B:** Add a workflow input for target App Service. More flexible but more work.

Commit the new workflow to main and push.

### 4.2. Trigger the new deploy workflow

GitHub → Actions → `deploy-to-prod-v2.yml` → Run workflow → enter `DEPLOY-V2` in the confirm field.

Watch the build complete and the deploy succeed.

### 4.3. Verify new App Service is healthy

```powershell
curl -s https://options-analyzer-api-v2.azurewebsites.net/api/v1/health/detailed
```

**Run this 5-10 times in a row over a few minutes.**

What to look for:
- `database.status: connected` consistently
- `latency_ms` reasonable (under ~3000ms ideally)
- No `08001` errors

This is the moment of truth. If 08001 errors are gone here, the cross-region hypothesis was correct.

### Decision point

- **Consistent `connected`** → Cross-region was the cause. Proceed to Phase 5.
- **Intermittent `08001`** → Cross-region was NOT the only cause. **Stop and investigate** before cutover. Do not proceed to Phase 7 with broken connectivity.

### Verify Phase 4

- [ ] Deploy succeeded
- [ ] Smoke test passed
- [ ] 5+ consecutive curls returned `database.status: connected`

---

## Phase 5: Add new App Service URL to Entra redirect URIs (~5 min)

This is temporary for testing in Phase 6. After cutover, the existing `oa.tmtctech.ai` URI handles things.

1. Azure Portal → Entra ID → App registrations → find your app (client ID `f11ea8b8...`)
2. Authentication → Redirect URIs
3. Add: `https://options-analyzer-api-v2.azurewebsites.net/api/v1/auth/entra/callback`
4. Save

### Verify Phase 5

- [ ] New URI appears in the redirect URI list

---

## Phase 6: Functional test on new App Service (~15 min)

Open `https://options-analyzer-api-v2.azurewebsites.net/` in a fresh incognito window.

Test these in order:
1. [ ] Page loads (you see the OA login page)
2. [ ] Click Sign In, complete Entra login
3. [ ] Login redirects back to OA successfully (no 127.0.0.1 redirect)
4. [ ] App shell renders after login
5. [ ] Navigate: Dashboard, Trades, Positions, Strategy pages
6. [ ] DevTools Console (F12 → Console): no red errors during navigation
7. [ ] DevTools Network tab: API calls return 200 (some 401s are normal pre-login, but post-login should be 200)

### Decision point

- **All green** → Proceed to Phase 7.
- **Login fails** → Check redirect URI registration, check ENTRA_REDIRECT_URI_PROD env var.
- **API errors** → Check the relevant endpoint logs. Don't proceed to cutover until functional.

### Verify Phase 6

- [ ] Login works end-to-end
- [ ] App is functional
- [ ] No console errors

---

## Phase 7: Custom domain cutover (~15 min)

This is the step with real user impact. After this, traffic to `oa.tmtctech.ai` goes to the new App Service.

### 7.1. Add custom domain to new App Service

```powershell
az webapp config hostname add `
  --webapp-name options-analyzer-api-v2 `
  --resource-group options-analyzer-rg `
  --hostname oa.tmtctech.ai
```

If the command requires DNS verification (TXT record), it will tell you what to add. Add the TXT record in Cloudflare DNS, wait 1-2 minutes, then re-run.

### 7.2. Bind SSL certificate

Create managed certificate for the new App Service:

```powershell
az webapp config ssl create `
  --name options-analyzer-api-v2 `
  --resource-group options-analyzer-rg `
  --hostname oa.tmtctech.ai
```

Capture the thumbprint from the output. Then bind:

```powershell
az webapp config ssl bind `
  --name options-analyzer-api-v2 `
  --resource-group options-analyzer-rg `
  --certificate-thumbprint <THUMBPRINT_FROM_PREVIOUS_OUTPUT> `
  --ssl-type SNI
```

### 7.3. Update Cloudflare DNS

In Cloudflare DNS for `tmtctech.ai`:

1. Find the CNAME record for `oa`
2. Change value from:
   - `options-analyzer-api-d7aqhsdmd6f2anbc.centralus-01.azurewebsites.net`
3. To:
   - `options-analyzer-api-v2.azurewebsites.net`
4. Save

DNS propagation through Cloudflare is typically near-instant.

### 7.4. Test cutover

Wait 1-2 minutes, then:

```powershell
curl -s https://oa.tmtctech.ai/api/v1/health/detailed
```

Should return `database.status: connected`. Run several times to confirm consistency.

Open `https://oa.tmtctech.ai/` in fresh incognito. Login. Click around. Confirm functionality.

### Verify Phase 7

- [ ] Custom domain bound to new App Service
- [ ] SSL cert valid
- [ ] DNS pointing to new App Service
- [ ] Curl through `oa.tmtctech.ai` returns `connected`
- [ ] Login through `oa.tmtctech.ai` works

---

## Phase 8: Decommission old App Service (~5 min)

**Do NOT delete the old App Service yet.** Stop it but keep it for rollback.

```powershell
az webapp stop `
  --name options-analyzer-api `
  --resource-group options-analyzer-rg
```

After 24-48 hours of confirmed stable operation on the new App Service:

```powershell
# Verify the App Service Plan name first
az appservice plan list --resource-group options-analyzer-rg --output table

# Then delete (replace plan name with actual)
az webapp delete --name options-analyzer-api --resource-group options-analyzer-rg
az appservice plan delete --name <OLD_PLAN_NAME> --resource-group options-analyzer-rg
```

### Verify Phase 8

- [ ] Old App Service stopped
- [ ] New App Service handling all traffic
- [ ] Calendar reminder set for 48 hours from now to delete old resources

---

## Phase 9: Cleanup (after 48-hour soak)

- [ ] Update `deploy-to-prod.yml` to permanently target `options-analyzer-api-v2`
- [ ] Update smoke test URL in workflow
- [ ] Delete `deploy-to-prod-v2.yml` (or merge logic back into main workflow)
- [ ] Update `CLAUDE.md`: new App Service name, West US 2 region
- [ ] Update `project-hierarchy.md`: same
- [ ] Update `azure-naming-conventions.md`: reflect actual region (was East US 2 in doc, now West US 2 in reality)
- [ ] Remove temporary Entra redirect URI for `options-analyzer-api-v2.azurewebsites.net` (the `oa.tmtctech.ai` URI is enough)
- [ ] Delete old App Service and App Service Plan (after soak)
- [ ] Save the four pre-work JSON files to a permanent location or delete them

---

## Rollback plan

If at any point during Phase 7 the new App Service isn't healthy:

1. **Revert Cloudflare CNAME** for `oa` back to `options-analyzer-api-d7aqhsdmd6f2anbc.centralus-01.azurewebsites.net`
2. **Restart old App Service** if you stopped it:
```powershell
   az webapp start --name options-analyzer-api --resource-group options-analyzer-rg
```
3. You're back to the current state (intermittent 08001s, but functional)

The old App Service stays available until Phase 8 deletion, so rollback is always possible until then.

---

## Optional: Migrate dev in same session

If you decide to migrate dev too, repeat Phases 1-7 with these substitutions:

- App Service name: `options-analyzer-api-dev-v2`
- App Service Plan: same `ASP-optionsanalyzer-westus2` (can host multiple apps)
- Custom domain: `oa-dev.tmtctech.ai`
- Entra redirect URI: `https://oa-dev.tmtctech.ai/api/v1/auth/entra/callback`
- Smoke test URL: `https://options-analyzer-api-dev-v2.azurewebsites.net/api/v1/health/detailed`
- Deploy workflow: `deploy-to-dev-v2.yml`

You can run dev's migration in parallel with prod's, or sequentially. Sequential is safer (one variable at a time).

---

## What this plan does NOT address

These are still future work after the migration:

- **Connection pool exhaustion under load.** May be solved by removing cross-region tax. May not. Monitor after migration.
- **Auth code review** (slow login, clunky auth flow). Separate effort.
- **`/api/v1/health` shadowed by SPA static mount bug.** Returns HTML instead of JSON. Separate fix.
- **`127.0.0.1` redirect bug** when hitting App Service direct URLs (not custom domain). Separate investigation.
- **Schwab Key Vault `Forbidden` warning.** Separate Story.

The right next move after this migration succeeds is the deeper code review of these 13 files (covers most of the above as a coherent package):

- `app/main.py`
- `app/models/session.py`
- `app/models/database.py`
- `app/auth/session_manager.py`
- `app/auth/providers.py`
- `app/auth/dependencies.py`
- `app/auth/client_assertion.py`
- `app/api/identity_routes.py`
- `app/middleware/csrf.py`
- `app/core/secrets.py`
- `app/core/config.py`
- `web/src/context/AuthContext.jsx`
- `web/src/api/client.js`

---

## Decisions to make tomorrow morning

1. **Migrate dev in same session?** Recommended yes.
2. **Acceptable maintenance window for cutover?** Phase 7 has 1-2 minutes of DNS propagation.
3. **Any custom domains other than `oa.tmtctech.ai` to handle?** Check pre-work `prod-hostnames.json`.

---

## Pre-work artifacts (already captured 2026-04-27)

Located in `C:\Users\DonMishory\Downloads\`:

- `prod-appsettings.json` (1.8 KB) — env vars
- `prod-identity.json` (182 bytes) — MSI principal ID
- `prod-webconfig.json` (3.8 KB) — runtime config
- `prod-hostnames.json` (1.5 KB) — custom domain bindings

DATABASE_URL verified present in `prod-appsettings.json` with all four parameters.