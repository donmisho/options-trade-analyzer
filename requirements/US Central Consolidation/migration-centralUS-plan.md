# Azure SQL Migration to Central US

**Goal:** Eliminate cross-region traffic between the App Services (Central US) and Azure SQL (currently West US 2) by migrating Azure SQL to Central US. Co-locating SQL with the App Services should fix the intermittent `08001 TCP RST` errors and `QueuePool exhaustion` symptoms we've been seeing under load.

**Why this approach over App Service migration:**
- Don is in Chicago; Central US (Iowa) gives ~10ms latency vs ~50ms to West US 2
- App Services stay where they are — no DNS changes, no custom domain changes, no Schwab callback URL changes from this migration
- Schwab callback URLs already queued today don't need updating
- Architecturally cleaner: SQL was supposed to be East US 2 per azure-naming-conventions.md anyway; West US 2 was likely a setup mistake

**Estimated time:** 2-3 hours of focused work.

---

## Pre-work (already done as of 2026-04-28)

- [x] Inventory captured 2026-04-27 evening:
  - `C:\Users\DonMishory\Downloads\prod-appsettings.json`
  - `C:\Users\DonMishory\Downloads\prod-identity.json`
  - `C:\Users\DonMishory\Downloads\prod-webconfig.json`
  - `C:\Users\DonMishory\Downloads\prod-hostnames.json`
- [x] Redirect URI bug fixed on dev — `ENTRA_REDIRECT_URI_DEV` set
- [x] Dev's `ENTRA_REDIRECT_URI_PROD` removed (was dead config)
- [x] Schwab callback URLs added (activate after 3:30 PM CDT today):
  - `https://oa.tmtctech.ai/api/v1/auth/schwab/callback`
  - `https://oa-dev.tmtctech.ai/api/v1/auth/schwab/callback`
- [x] Tradier confusion resolved (it's "Trader API" — Schwab's own product, no Tradier dependency)
- [x] Decision: consolidate on single Schwab app (Schwab platform doesn't allow multiple market data apps)

## Pre-work to do BEFORE starting Phase 1

- [x] Update prod's `SCHWAB_CALLBACK_URL` env var to use custom domain:
  - Portal → `options-analyzer-api` → Environment variables → `SCHWAB_CALLBACK_URL` → set to: `https://oa.tmtctech.ai/api/v1/auth/schwab/callback`
- [ ] Hold off on dev's `SCHWAB_CALLBACK_URL` until after 3:30 PM CDT (Schwab activation time)
- [x] Capture current SQL server config to file:
```powershell
  az sql server show --resource-group options-analyzer-rg --name options-analyzer-sql > sql-server-config.json
  az sql db show --resource-group options-analyzer-rg --server options-analyzer-sql --name options-analyzer-db > sql-db-config.json
  az sql db replica list-links --resource-group options-analyzer-rg --server options-analyzer-sql --name options-analyzer-db > sql-replicas.json
  az sql server firewall-rule list --resource-group options-analyzer-rg --server options-analyzer-sql > sql-firewall-rules.json
```
- [x] Capture current SQL Entra users and role memberships. Connect to `options-analyzer-sql.database.windows.net` via SSMS using Entra MFA, run against `options-analyzer-db`:
```sql
  -- Get all external (Entra) users
  SELECT name, type_desc, authentication_type_desc 
  FROM sys.database_principals 
  WHERE type IN ('E', 'X');

  -- Get role memberships
  SELECT r.name AS role_name, m.name AS member_name
  FROM sys.database_role_members rm
  JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id
  JOIN sys.database_principals m ON rm.member_principal_id = m.principal_id
  WHERE m.type IN ('E', 'X');

  -- Get full DB schema overview (table count, sproc count, etc.)
  SELECT 
    (SELECT COUNT(*) FROM sys.tables) AS table_count,
    (SELECT COUNT(*) FROM sys.procedures) AS procedure_count,
    (SELECT COUNT(*) FROM sys.views) AS view_count;
```
  Save output to a text file for reference.

---

## Phase 1: Provision new SQL Server in Central US (~10 min)

### 1.1. Create new Azure SQL Server in Central US

```powershell
az sql server create `
  --name options-analyzer-sql-cus `
  --resource-group options-analyzer-rg `
  --location centralus `
  --enable-ad-only-auth true `
  --external-admin-principal-type User `
  --external-admin-name "don.mishory@tmtctech.ai" `
  --external-admin-sid 6232a881-23e9-4954-8ed0-6303ea7fd188
```

To get your Entra Object ID:
```powershell
az ad signed-in-user show --query id -o tsv
```

The `cus` suffix in the name distinguishes it from the existing West US 2 server. Naming both servers different is required because Azure SQL server names are globally unique.

`--enable-ad-only-auth true` disables SQL auth entirely, matching prod's existing pattern (Entra-only).

### 1.2. Create database on new server

The new database will be empty initially. We'll restore data from the old server in Phase 2.

**Don't create the database yet via `az sql db create`.** Instead, we'll create it via geo-restore in Phase 2, which restores from a backup of the existing database in one step.

### 1.3. Apply firewall rules to new server

```powershell
az sql server firewall-rule create `
  --resource-group options-analyzer-rg `
  --server options-analyzer-sql-cus `
  --name AllowAllWindowsAzureIps `
  --start-ip-address 0.0.0.0 `
  --end-ip-address 0.0.0.0
```

The `0.0.0.0 → 0.0.0.0` rule is the special "Allow Azure services" rule.

### 1.4. (Optional) Add your laptop IP to firewall for SSMS access

If you want to connect via SSMS for verification:
```powershell
az sql server firewall-rule create `
  --resource-group options-analyzer-rg `
  --server options-analyzer-sql-cus `
  --name AllowMyLaptop `
  --start-ip-address <YOUR_PUBLIC_IP> `
  --end-ip-address <YOUR_PUBLIC_IP>
```

Get your public IP:
```powershell
(Invoke-WebRequest -Uri "https://api.ipify.org").Content
```

### Verify Phase 1

- [x] New SQL Server `options-analyzer-sql-cus` exists in Central US
- [x] Firewall rule `AllowAllWindowsAzureIps` configured
- [x] (Optional) Your laptop IP added to firewall

---

## Phase 2: Migrate database via geo-restore (~30-60 min depending on data size)

### 2.1. Initiate geo-restore

This creates a copy of `options-analyzer-db` from West US 2 onto the new Central US server. Geo-restore reads from the geo-redundant backup that Azure maintains automatically.

```powershell
az sql db restore `
  --resource-group options-analyzer-rg `
  --server options-analyzer-sql-cus `
  --dest-name options-analyzer-db `
  --source-database-id "/subscriptions/0f394f87-c8b1-429a-8c86-7e5305042eb9/resourceGroups/options-analyzer-rg/providers/Microsoft.Sql/servers/options-analyzer-sql/databases/options-analyzer-db" `
  --restore-point-in-time "2026-04-28T15:00:00Z" `
  --service-objective GP_S_Gen5_2
```

az sql recoverable-database show `
  --resource-group options-analyzer-rg `
  --server-name options-analyzer-sql `
  --name options-analyzer-db `
  --query id -o tsv

Get your subscription ID:
```powershell
az account show --query id -o tsv
```

The `--restore-point-in-time` should be ~30 min ago to ensure backups have caught up. Adjust UTC time as needed (current time + 30 min ago).

`--service-objective GP_S_Gen5_2` matches your existing tier (General Purpose Serverless, 2 vCores).

**Note:** This is a long-running operation. The CLI returns when the restore is COMPLETE. Could be 15-60 minutes for a small DB. Don't kill it; let it run.

**Alternative if geo-restore is slow:** Use Active Geo-Replication instead. Sets up continuous replication, then cut over. Faster cutover but more setup. For your data size, geo-restore should be fine.

### 2.2. Verify the new database

After restore completes, connect to the new server via SSMS:
- Server: `options-analyzer-sql-cus.database.windows.net`
- Authentication: Microsoft Entra MFA

Run sanity checks:
```sql
USE [options-analyzer-db];

-- Should match the table count from pre-work
SELECT COUNT(*) FROM sys.tables;

-- Spot-check key tables
SELECT TOP 5 * FROM symbol_reference;
SELECT TOP 5 * FROM user_sessions;

-- Verify schema integrity
SELECT name FROM sys.tables ORDER BY name;
```

### 2.3. Disable auto-pause on new database

Same as the existing prod database:
```powershell
az sql db update `
  --resource-group options-analyzer-rg `
  --server options-analyzer-sql-cus `
  --name options-analyzer-db `
  --auto-pause-delay -1
```

### Verify Phase 2

- [ ] Database `options-analyzer-db` exists on new server
- [ ] Table count matches original
- [ ] Spot-checked data looks correct
- [ ] Auto-pause disabled (`-1`)

---

## Phase 3: Set up Entra users and role memberships on new database (~15 min)

The geo-restore copies users from the source database, but Entra-based users may not transfer cleanly because they're tied to the old server's identity. Verify and recreate as needed.

### 3.1. Connect to new database via SSMS

Server: `options-analyzer-sql-cus.database.windows.net`
Auth: Entra MFA

### 3.2. Check what users exist

```sql
USE [options-analyzer-db];

SELECT name, type_desc, authentication_type_desc 
FROM sys.database_principals 
WHERE type IN ('E', 'X');
```

You should see something. If MSI users from the old server are listed but appear orphaned (linked to old server's MSI principals), you'll need to drop and recreate them.

### 3.3. Create the App Service MSI users

Drop existing if present, then create fresh against the new server:

```sql
-- Drop existing if present (orphaned from old server)
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'options-analyzer-api')
    DROP USER [options-analyzer-api];

IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'options-analyzer-api-dev')
    DROP USER [options-analyzer-api-dev];

-- Recreate from external provider
CREATE USER [options-analyzer-api] FROM EXTERNAL PROVIDER;
CREATE USER [options-analyzer-api-dev] FROM EXTERNAL PROVIDER;

-- Grant role memberships (matching pre-work captured roles)
ALTER ROLE db_datareader ADD MEMBER [options-analyzer-api];
ALTER ROLE db_datawriter ADD MEMBER [options-analyzer-api];
ALTER ROLE db_ddladmin ADD MEMBER [options-analyzer-api];

ALTER ROLE db_datareader ADD MEMBER [options-analyzer-api-dev];
ALTER ROLE db_datawriter ADD MEMBER [options-analyzer-api-dev];
ALTER ROLE db_ddladmin ADD MEMBER [options-analyzer-api-dev];
```

### 3.4. Verify users and roles

```sql
SELECT name, type_desc 
FROM sys.database_principals 
WHERE name IN ('options-analyzer-api', 'options-analyzer-api-dev');

SELECT r.name AS role_name, m.name AS member_name
FROM sys.database_role_members rm
JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id
JOIN sys.database_principals m ON rm.member_principal_id = m.principal_id
WHERE m.name IN ('options-analyzer-api', 'options-analyzer-api-dev');
```

Both users should appear with `EXTERNAL_USER` type, and each should have `db_datareader`, `db_datawriter`, `db_ddladmin` role memberships.

### Verify Phase 3

- [ ] Both MSI users exist on new database
- [ ] Both have all three role memberships

---

## Phase 4: Test connectivity from a test environment (~15 min)

Before cutting over the live App Services, verify the new SQL server is reachable and working.

### 4.1. Test from your laptop

If you added your laptop IP to firewall (Phase 1.4), test directly:

```powershell
# Quick connectivity test using sqlcmd or ssms
sqlcmd -S options-analyzer-sql-cus.database.windows.net -d options-analyzer-db -G -Q "SELECT GETUTCDATE() AS now"
```

Should return the current UTC date and exit cleanly.

### 4.2. Update DEV's DATABASE_URL first (test cutover on dev)

**Test on dev BEFORE prod.** Update dev's connection string to point at the new server.

Portal → `options-analyzer-api-dev` → Environment variables → click `DATABASE_URL` row → change value to:

```
mssql+pyodbc://options-analyzer-sql-cus.database.windows.net:1433/options-analyzer-db?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no&authentication=ActiveDirectoryMsi
```

(Only the server name changes from `options-analyzer-sql` to `options-analyzer-sql-cus`.)

Apply, restart.

### 4.3. Verify dev is healthy and SQL connectivity is clean

Wait ~90 seconds after restart, then:

```powershell
curl -s https://options-analyzer-api-dev.azurewebsites.net/api/v1/health/detailed
```

**Run this 5-10 times over a few minutes.**

Look for:
- Consistent `database.status: connected`
- `latency_ms` significantly lower than what we saw with cross-region (target: under ~500ms instead of 2000-7000ms)
- No `08001` errors
- No `QueuePool exhaustion`

### Decision point — this is the moment of truth

- **Consistent `connected` with low latency** → Cross-region was the cause. Proceed to Phase 5.
- **Still seeing 08001 or pool exhaustion** → Cross-region was NOT the cause. **Stop. Re-diagnose** before proceeding. The migration won't help if cross-region wasn't the issue.

### Verify Phase 4

- [ ] Direct connectivity from laptop (if firewall allowed)
- [ ] Dev DATABASE_URL updated to new server
- [ ] Dev restart succeeded
- [ ] 5+ consecutive curls show `database.status: connected`
- [ ] Latency improved (target: <500ms vs previous 2000-7000ms)
- [ ] No 08001 or QueuePool errors

---

## Phase 5: Functional test on dev (~15 min)

Verify dev is fully functional with the new database.

Open `https://oa-dev.tmtctech.ai/` in fresh incognito.

Test:
1. [ ] Page loads
2. [ ] Microsoft login completes (no `127.0.0.1` redirect — that bug was fixed earlier today)
3. [ ] App shell renders after login
4. [ ] Navigate to Trades, Positions, Strategy pages
5. [ ] DevTools Console: no red errors
6. [ ] DevTools Network: API calls return 200
7. [ ] Multiple sequential page loads — no `auth_error` redirect (which would indicate pool exhaustion still happening)

If something breaks, stop and investigate before touching prod.

---

## Phase 6: Cut over prod's DATABASE_URL (~5 min)

### 6.1. Update prod's DATABASE_URL

Portal → `options-analyzer-api` → Environment variables → `DATABASE_URL` → change to:

```
mssql+pyodbc://options-analyzer-sql-cus.database.windows.net:1433/options-analyzer-db?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no&authentication=ActiveDirectoryMsi
```

Apply, restart.

### 6.2. Verify prod connectivity

Wait ~90 seconds after restart:

```powershell
curl -s https://options-analyzer-api-d7aqhsdmd6f2anbc.centralus-01.azurewebsites.net/api/v1/health/detailed
```

Run 5-10 times. Look for consistent `database.status: connected` with low latency.

### 6.3. Functional test on prod

Open `https://oa.tmtctech.ai/` in fresh incognito. Login. Click around. Confirm functionality.

### Verify Phase 6

- [ ] Prod DATABASE_URL updated
- [ ] Prod responds with `database.status: connected`
- [ ] Functional test passed
- [ ] No `08001` errors in prod logs
- [ ] No `QueuePool exhaustion` in prod logs

---

## Phase 7: Post-cutover monitoring (~10 min, then ongoing)

### 7.1. Watch for 30 minutes

Leave prod's health endpoint open in a tab and refresh every few minutes:

```
https://options-analyzer-api-d7aqhsdmd6f2anbc.centralus-01.azurewebsites.net/api/v1/health/detailed
```

You're watching for:
- Consistent `connected` status
- No new errors
- Latency stays low

### 7.2. If anything regresses, rollback

The old SQL server still exists and works. To rollback DATABASE_URL:

Portal → `options-analyzer-api` → Environment variables → `DATABASE_URL` → revert to:
```
mssql+pyodbc://options-analyzer-sql.database.windows.net:1433/options-analyzer-db?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no&authentication=ActiveDirectoryMsi
```

Same for dev. App Services restart, you're back to old SQL server (and back to the cross-region issues, but at least running).

---

## Phase 8: After 3:30 PM CDT — finish Schwab work (~5 min)

### 8.1. Update dev's `SCHWAB_CALLBACK_URL`

Schwab activates the new callback URLs at 3:30 PM CDT. After that:

Portal → `options-analyzer-api-dev` → Environment variables → `SCHWAB_CALLBACK_URL` → change to:

```
https://oa-dev.tmtctech.ai/api/v1/auth/schwab/callback
```

Apply, restart.

### 8.2. Test Schwab login on dev

Open `https://oa-dev.tmtctech.ai/` in fresh incognito. Login via Microsoft. Then trigger Schwab login. Schwab popup should appear and complete OAuth flow.

### 8.3. Test Schwab login on prod

Open `https://oa.tmtctech.ai/` in fresh incognito. Login via Microsoft. Trigger Schwab login. Same flow as dev.

### Verify Phase 8

- [ ] Dev `SCHWAB_CALLBACK_URL` updated to dev custom domain
- [ ] Dev Schwab login flow works end-to-end
- [ ] Prod Schwab login flow works end-to-end

---

## Phase 9: Cleanup (after 24-48 hour soak)

After confirming the new SQL server is stable:

- [ ] Delete the old West US 2 SQL Server and database:
```powershell
  az sql db delete --resource-group options-analyzer-rg --server options-analyzer-sql --name options-analyzer-db --yes
  az sql server delete --resource-group options-analyzer-rg --name options-analyzer-sql --yes
```
- [ ] Update CLAUDE.md: SQL location is Central US (was West US 2)
- [ ] Update project-hierarchy.md: same
- [ ] Update azure-naming-conventions.md: actual region is Central US (was East US 2 in doc)
- [ ] Remove the now-defunct direct App Service URL from Schwab's registered callbacks:
  - `https://options-analyzer-api-d7aqhsdmd6f2anbc.centralus-01.azurewebsites.net/api/v1/auth/schwab/callback`
  - (Keep the 127.0.0.1 entry for local backend dev)
- [ ] Consider migrating Key Vault to Central US too (currently East US):
  - Lower priority than SQL — Key Vault round trips are at startup and token refresh, not every request
  - Separate effort, not today

---

## Rollback plan

At any point through Phase 6, you can rollback by reverting `DATABASE_URL` env vars to point at the old West US 2 server:

```
mssql+pyodbc://options-analyzer-sql.database.windows.net:1433/options-analyzer-db?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no&authentication=ActiveDirectoryMsi
```

Old server stays running until Phase 9 cleanup. Until then, rollback is a 2-minute env var change + restart.

---

## What this plan does NOT address

These are still future work:

- **Key Vault migration to Central US.** Lower priority than SQL. Separate Story.
- **Auth code review.** Slow login, clunky auth flow. The 13-file review I outlined.
- **`/api/v1/health` shadowed by SPA static mount bug.** Returns HTML instead of JSON.
- **Dev Schwab app separation for trade execution.** Schwab platform doesn't currently allow multiple market data apps. Revisit when adding trade execution to identify whether trading endpoints support a separate app.
- **Storage account region (`otaunstructured`).** May or may not be in West US 2. Worth checking. Not blocking.
- **Connection pool exhaustion under sustained load.** May be solved by removing cross-region tax. May not. Monitor after migration.

---

## Decision log for this migration

- **Why migrate SQL instead of App Service?** Don is in Chicago. Central US gives ~10ms user latency vs ~50ms for West US 2. App Service migration would also require DNS, custom domain, Schwab callback URL, and Cloudflare changes. SQL migration is more contained.
- **Why geo-restore vs export/import?** Geo-restore is faster, doesn't require manual schema/data export, and uses Azure's built-in backups. For your data size, completes in 15-60 min.
- **Why test dev first?** Dev shares the same database as prod. Switching dev's DATABASE_URL to the new server validates connectivity before risking prod.
- **Why disable auto-pause on new server?** Same reasons it was disabled on old server (yesterday's work). Auto-pause causes connection issues during pause/resume cycles.

---

## Pre-work artifacts

In `C:\Users\DonMishory\Downloads\`:

- `prod-appsettings.json` — env vars (already captured)
- `prod-identity.json` — MSI principal ID (already captured)
- `prod-webconfig.json` — runtime config (already captured)
- `prod-hostnames.json` — custom domain bindings (already captured)
- `sql-server-config.json` — to capture in pre-work
- `sql-db-config.json` — to capture in pre-work
- `sql-replicas.json` — to capture in pre-work
- `sql-firewall-rules.json` — to capture in pre-work