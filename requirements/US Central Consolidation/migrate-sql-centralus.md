---
allowedTools: Bash, Read, Write, Edit
description: OTA Azure SQL migration West US 2 → Central US via BACPAC export/import + MSI user setup
---

# OTA SQL Migration: West US 2 → Central US

## Mission

Complete the cross-region migration of `options-analyzer-db` from `options-analyzer-sql` (West US 2) to `options-analyzer-sql-cus` (Central US) via BACPAC export/import, then create MSI users for both App Services on the new database. The goal is to fix chronic `08001 TCP RST` errors caused by cross-region SQL connection latency.

**Stop on first error.** Do not silently continue. Migrations involve destructive operations — verify each phase before proceeding.

---

## Infrastructure Identifiers (do not change these)

| Item | Value |
|---|---|
| Subscription ID | `0f394f87-c8b1-429a-8c86-7e5305042eb9` |
| Resource group | `options-analyzer-rg` |
| Source SQL server | `options-analyzer-sql` (West US 2) |
| Destination SQL server | `options-analyzer-sql-cus` (Central US) |
| Database name | `options-analyzer-db` |
| Service objective | `GP_S_Gen5_2` |
| Storage account | `otaunstructured` |
| Storage container | `sqlbackups` |
| Prod App Service MSI | `options-analyzer-api` |
| Dev App Service MSI | `options-analyzer-api-dev` |
| Entra admin (destination) | TMTC Azure Admin |

---

## Pre-flight

Run these checks first. **Stop and report if any fail.**

1. `cat CLAUDE.md` to load project context.

2. Confirm Azure CLI is logged in as TMTC Azure Admin and on the right subscription:
   ```powershell
   az account show --query "{user:user.name, subscription:id, tenant:tenantId}" -o table
   ```
   Expected: `user` contains `admin@NETORGFT18092069`, `subscription` matches `0f394f87-...`. If wrong, run `az account set --subscription 0f394f87-c8b1-429a-8c86-7e5305042eb9` and re-verify.

3. Set up a migration log file. All commands and their output append here:
   ```powershell
   $script:logFile = "C:\Temp\sql-migration-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"
   New-Item -ItemType Directory -Path "C:\Temp" -Force | Out-Null
   "Migration started: $(Get-Date)" | Out-File $script:logFile
   ```

4. Locate SqlPackage. The user has the standalone .NET 10 build installed at `C:\Tools\sqlpackage\SqlPackage.exe`. If that path doesn't exist, download and extract the standalone zip (no .NET SDK required):
   ```powershell
   $sqlPackage = "C:\Tools\sqlpackage\SqlPackage.exe"
   if (-not (Test-Path $sqlPackage)) {
       Write-Host "SqlPackage not found at $sqlPackage — downloading standalone zip..."
       $sqlPkgDir = "C:\Tools\sqlpackage"
       New-Item -ItemType Directory -Path $sqlPkgDir -Force | Out-Null
       $zipPath = "$env:TEMP\sqlpackage.zip"
       Invoke-WebRequest -Uri "https://aka.ms/sqlpackage-windows" -OutFile $zipPath -UseBasicParsing
       Expand-Archive -Path $zipPath -DestinationPath $sqlPkgDir -Force
       Remove-Item $zipPath
   }
   # Verify it runs
   & $sqlPackage /version
   if ($LASTEXITCODE -ne 0) {
       Write-Error "SqlPackage failed to run. Stop and investigate."
       exit 1
   }
   Write-Host "SqlPackage ready at: $sqlPackage"
   ```

5. Confirm `SqlServer` PowerShell module is available (needed for Phase 6):
   ```powershell
   if (-not (Get-Module -ListAvailable -Name SqlServer)) {
       Install-Module SqlServer -Force -AllowClobber -Scope CurrentUser
   }
   Import-Module SqlServer
   ```

---

## Phase 1: Resolve any in-progress export

The current export may be stuck or failing. Check status, capture error details, and cancel if necessary.

1. Get full operation status as JSON:
   ```powershell
   az sql db op list `
     --resource-group options-analyzer-rg `
     --server options-analyzer-sql `
     --database options-analyzer-db `
     -o json | ConvertFrom-Json | Where-Object { $_.operation -eq "ExportDatabase" }
   ```

2. Decision logic:
   - If state is `Succeeded` and the BACPAC blob in `sqlbackups` has size > 1 MB → **skip to Phase 4**.
   - If state is `InProgress` and `percentComplete` > 0 OR started less than 10 minutes ago → wait. Poll every 60 seconds for up to 30 minutes. If still 0% after 30 min, cancel.
   - If state is `Failed` or `Cancelled` → log the `errorCode` and `errorDescription`, then proceed to Phase 2 with a fresh export.
   - If `InProgress` for more than 30 min at 0% → cancel:
     ```powershell
     az sql db op cancel `
       --resource-group options-analyzer-rg `
       --server options-analyzer-sql `
       --database options-analyzer-db `
       --name <operation-id-from-step-1>
     ```

3. Verify source DB is online (serverless DBs can be paused, which delays exports):
   ```powershell
   az sql db show `
     --resource-group options-analyzer-rg `
     --server options-analyzer-sql `
     --database options-analyzer-db `
     --query "{status:status, paused:pausedDate, resumed:resumedDate}" -o table
   ```
   If `status` is `Paused`, run a no-op query to wake it (Phase 2 export will also wake it):
   ```powershell
   $token = (az account get-access-token --resource https://database.windows.net/ --query accessToken -o tsv)
   Invoke-Sqlcmd -ServerInstance "options-analyzer-sql.database.windows.net" -Database "options-analyzer-db" -AccessToken $token -Query "SELECT 1"
   ```

---

## Phase 2: Start fresh export with SAS auth

This bypasses any RBAC issues by using a short-lived SAS token instead of MSI/Entra auth on storage.

1. Generate a fresh BACPAC filename with current timestamp:
   ```powershell
   $bacpacName = "options-analyzer-db-$(Get-Date -Format 'yyyyMMdd-HHmm').bacpac"
   $bacpacUri = "https://otaunstructured.blob.core.windows.net/sqlbackups/$bacpacName"
   Write-Host "BACPAC target: $bacpacUri"
   ```

2. Generate a SAS token valid for 4 hours with write+create+read permissions:
   ```powershell
   $expiry = (Get-Date).ToUniversalTime().AddHours(4).ToString("yyyy-MM-ddTHH:mm:ssZ")
   $sasToken = az storage container generate-sas `
     --account-name otaunstructured `
     --name sqlbackups `
     --permissions rwcl `
     --expiry $expiry `
     --auth-mode key `
     -o tsv
   ```

3. Get the SQL admin equivalent — for Entra-only source server, get an access token:
   ```powershell
   # The source server is also Entra-only; use access token for export auth
   $sqlToken = (az account get-access-token --resource https://database.windows.net/ --query accessToken -o tsv)
   ```

4. Start the export. Use SharedAccessKey auth type with the SAS token, and pass the access token as the admin credential:
   ```powershell
   az sql db export `
     --resource-group options-analyzer-rg `
     --server options-analyzer-sql `
     --name options-analyzer-db `
     --storage-key-type SharedAccessKey `
     --storage-key "?$sasToken" `
     --storage-uri $bacpacUri `
     --auth-type ADToken `
     --token $sqlToken
   ```

   **If `--auth-type ADToken` is not supported by your az CLI version**, fall back to SqlPackage locally for the export:
   ```powershell
   & $sqlPackage `
     /Action:Export `
     /SourceConnectionString:"Server=tcp:options-analyzer-sql.database.windows.net,1433;Initial Catalog=options-analyzer-db;Authentication=Active Directory Default;Encrypt=True;" `
     /TargetFile:"C:\Temp\$bacpacName" `
     /p:CommandTimeout=0
   ```
   Then upload the local BACPAC to storage:
   ```powershell
   az storage blob upload `
     --account-name otaunstructured `
     --container-name sqlbackups `
     --name $bacpacName `
     --file "C:\Temp\$bacpacName" `
     --auth-mode key
   ```

5. Save the BACPAC name and URI for later phases:
   ```powershell
   "$bacpacName" | Out-File "C:\Temp\current-bacpac-name.txt"
   ```

---

## Phase 3: Wait for export completion

If using `az sql db export` (server-side), poll the operation:

```powershell
$timeout = (Get-Date).AddMinutes(45)
do {
    $op = az sql db op list `
      --resource-group options-analyzer-rg `
      --server options-analyzer-sql `
      --database options-analyzer-db `
      -o json | ConvertFrom-Json | Where-Object { $_.operation -eq "ExportDatabase" } | Sort-Object startTime -Descending | Select-Object -First 1
    Write-Host "$(Get-Date -Format 'HH:mm:ss') Export state: $($op.state) — $($op.percentComplete)%"
    if ($op.state -eq "Succeeded") { break }
    if ($op.state -in @("Failed","Cancelled")) {
        Write-Error "Export failed: $($op.errorDescription)"
        break
    }
    Start-Sleep -Seconds 30
} while ((Get-Date) -lt $timeout)
```

If using SqlPackage local export, the command is synchronous — proceed when it returns.

**Verify final BACPAC size** (should be at least 1 MB; the 4-byte placeholder means failure):
```powershell
$blobInfo = az storage blob show `
  --account-name otaunstructured `
  --container-name sqlbackups `
  --name $bacpacName `
  --auth-mode key `
  --query "{size:properties.contentLength, modified:properties.lastModified}" -o json | ConvertFrom-Json
Write-Host "BACPAC size: $($blobInfo.size) bytes"
if ($blobInfo.size -lt 1000000) {
    Write-Error "BACPAC is too small ($($blobInfo.size) bytes) — export likely failed silently. Stop and investigate."
    exit 1
}
```

---

## Phase 4: Pre-import destination checks

Before importing, confirm the destination is clean and ready.

1. Verify destination server is online:
   ```powershell
   az sql server show `
     --resource-group options-analyzer-rg `
     --name options-analyzer-sql-cus `
     --query "{state:state, location:location, fqdn:fullyQualifiedDomainName}" -o table
   ```
   Expected: `state = Ready`, `location = centralus`.

2. Verify your laptop IP is whitelisted on the destination firewall:
   ```powershell
   $myIp = (Invoke-WebRequest -Uri "https://api.ipify.org" -UseBasicParsing).Content.Trim()
   $firewallRules = az sql server firewall-rule list `
     --resource-group options-analyzer-rg `
     --server options-analyzer-sql-cus `
     -o json | ConvertFrom-Json
   $matched = $firewallRules | Where-Object { $myIp -ge $_.startIpAddress -and $myIp -le $_.endIpAddress }
   if (-not $matched) {
       Write-Host "Adding firewall rule for $myIp"
       az sql server firewall-rule create `
         --resource-group options-analyzer-rg `
         --server options-analyzer-sql-cus `
         --name "migration-laptop-$(Get-Date -Format 'yyyyMMdd')" `
         --start-ip-address $myIp `
         --end-ip-address $myIp
   }
   ```

3. Verify destination DB does not already exist (BACPAC import requires target to be absent):
   ```powershell
   $existingDb = az sql db show `
     --resource-group options-analyzer-rg `
     --server options-analyzer-sql-cus `
     --name options-analyzer-db 2>$null
   if ($existingDb) {
       Write-Host "Destination DB already exists. Stopping for confirmation."
       Write-Host "If this is from a previous failed import, delete it manually:"
       Write-Host "  az sql db delete --resource-group options-analyzer-rg --server options-analyzer-sql-cus --name options-analyzer-db --yes"
       exit 1
   }
   ```

---

## Phase 5: Import to destination

Use SqlPackage with `Active Directory Default` to authenticate via the `az login` session non-interactively. The BACPAC stays in storage; SqlPackage will read directly from the SAS URL.

```powershell
$bacpacName = (Get-Content "C:\Temp\current-bacpac-name.txt").Trim()

# Generate a fresh SAS for the import (read-only this time)
$expiry = (Get-Date).ToUniversalTime().AddHours(4).ToString("yyyy-MM-ddTHH:mm:ssZ")
$readSas = az storage blob generate-sas `
  --account-name otaunstructured `
  --container-name sqlbackups `
  --name $bacpacName `
  --permissions r `
  --expiry $expiry `
  --auth-mode key `
  --full-uri `
  -o tsv

# Download the BACPAC locally — SqlPackage import is more reliable from local file
$localBacpac = "C:\Temp\$bacpacName"
Invoke-WebRequest -Uri $readSas -OutFile $localBacpac -UseBasicParsing
Write-Host "Downloaded BACPAC to $localBacpac ($(((Get-Item $localBacpac).Length / 1MB).ToString('0.00')) MB)"

# Run the import
& $sqlPackage `
  /Action:Import `
  /SourceFile:$localBacpac `
  /TargetConnectionString:"Server=tcp:options-analyzer-sql-cus.database.windows.net,1433;Initial Catalog=options-analyzer-db;Authentication=Active Directory Default;Encrypt=True;TrustServerCertificate=False;Connection Timeout=60;" `
  /p:DatabaseEdition=GeneralPurpose `
  /p:DatabaseServiceObjective=GP_S_Gen5_2 `
  /p:CommandTimeout=0
```

**Verify the import created the DB:**
```powershell
az sql db show `
  --resource-group options-analyzer-rg `
  --server options-analyzer-sql-cus `
  --name options-analyzer-db `
  --query "{name:name, status:status, sku:sku, sizeBytes:currentSku, createdAt:creationDate}" -o table
```

---

## Phase 6: Create MSI users on the new database

Use `Invoke-Sqlcmd` with an Entra access token — fully non-interactive.

1. Write the SQL script to a temp file:
   ```powershell
   $sqlScript = @"
   IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'options-analyzer-api')
       CREATE USER [options-analyzer-api] FROM EXTERNAL PROVIDER;
   ALTER ROLE db_datareader ADD MEMBER [options-analyzer-api];
   ALTER ROLE db_datawriter ADD MEMBER [options-analyzer-api];
   ALTER ROLE db_ddladmin ADD MEMBER [options-analyzer-api];

   IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'options-analyzer-api-dev')
       CREATE USER [options-analyzer-api-dev] FROM EXTERNAL PROVIDER;
   ALTER ROLE db_datareader ADD MEMBER [options-analyzer-api-dev];
   ALTER ROLE db_datawriter ADD MEMBER [options-analyzer-api-dev];
   ALTER ROLE db_ddladmin ADD MEMBER [options-analyzer-api-dev];

   SELECT name, type_desc, authentication_type_desc
   FROM sys.database_principals
   WHERE type IN ('E', 'X')
   ORDER BY name;
   "@
   $sqlFile = "C:\Temp\create-msi-users.sql"
   $sqlScript | Out-File $sqlFile -Encoding UTF8
   ```

2. Get a fresh access token and run the script:
   ```powershell
   $token = (az account get-access-token --resource https://database.windows.net/ --query accessToken -o tsv)
   $result = Invoke-Sqlcmd `
     -ServerInstance "options-analyzer-sql-cus.database.windows.net" `
     -Database "options-analyzer-db" `
     -AccessToken $token `
     -InputFile $sqlFile `
     -OutputAs DataRows
   $result | Format-Table
   ```

3. Verify both users appear in the output with `type_desc = EXTERNAL_USER`. **Stop and report if either is missing.**

---

## Phase 7: Connectivity verification

Quick smoke test — confirm an MSI-style connection works against the new DB.

```powershell
$token = (az account get-access-token --resource https://database.windows.net/ --query accessToken -o tsv)
$rowCount = Invoke-Sqlcmd `
  -ServerInstance "options-analyzer-sql-cus.database.windows.net" `
  -Database "options-analyzer-db" `
  -AccessToken $token `
  -Query "SELECT COUNT(*) AS row_count FROM symbol_reference"
Write-Host "symbol_reference rows on new DB: $($rowCount.row_count)"
```

Expected: ~8568 rows (this is the largest known table per project notes). **Stop if the table is missing or empty.**

Also list all tables to confirm schema migrated:
```powershell
$tables = Invoke-Sqlcmd `
  -ServerInstance "options-analyzer-sql-cus.database.windows.net" `
  -Database "options-analyzer-db" `
  -AccessToken $token `
  -Query "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"
$tables | Format-Table
Write-Host "Total tables migrated: $($tables.Count)"
```

---

## Phase 8: Final report

Output a summary block:

```
═══════════════════════════════════════════════════
OTA SQL Migration — Completion Report
═══════════════════════════════════════════════════
Date: <timestamp>
BACPAC file: <bacpac-name> (<size> MB)
Source: options-analyzer-sql.database.windows.net (West US 2)
Destination: options-analyzer-sql-cus.database.windows.net (Central US)
Database: options-analyzer-db
Service objective: GP_S_Gen5_2
Tables migrated: <count>
symbol_reference row count: <count>
MSI users created: options-analyzer-api, options-analyzer-api-dev
Log file: <log-path>
═══════════════════════════════════════════════════

NEXT STEPS (manual, not automated by this prompt):
1. Update DEV App Service DATABASE_URL via Azure portal Environment variables UI
   (do NOT use az CLI — PowerShell & escaping breaks the connection string)
   New value:
   mssql+pyodbc://options-analyzer-sql-cus.database.windows.net:1433/options-analyzer-db?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no&authentication=ActiveDirectoryMsi
2. Restart options-analyzer-api-dev App Service
3. Curl /api/v1/health/detailed 5–10 times, watch for consistent database.status: connected
4. Run dev functional test (login, navigation, no auth_error redirects)
5. After dev validates → repeat for prod (options-analyzer-api)
6. After 30 min monitoring → update SCHWAB_CALLBACK_URL on dev (Phase 8 of plan)
7. After 24–48h soak → delete old SQL server (options-analyzer-sql)
8. Update CLAUDE.md, project-hierarchy.md, azure-naming-conventions.md
```

---

## Failure handling

If any phase fails, **do not proceed**. Capture the error in the log file and report:
- Which phase failed
- Full error output
- Current state of source DB, destination DB, BACPAC blob
- Recommended next manual step

Common failure modes:
- **Export 0% for 30+ min**: source DB serverless paused — Phase 1.3 wake should fix
- **BACPAC < 1MB**: export silently failed, usually permissions; check operation `errorDescription`
- **Import "login failed for user"**: `az login` session expired; run `az login` again as TMTC Azure Admin
- **Import "User does not have permission"**: TMTC Azure Admin not set as Entra admin on destination; verify via `az sql server ad-admin list`
- **MSI CREATE USER fails with "Principal not found"**: App Service managed identities not yet provisioned, or names don't match — verify with `az webapp identity show`

---

## Do NOT

- Do NOT delete the old SQL server (`options-analyzer-sql`) — that's a manual cleanup step after 24–48h soak.
- Do NOT modify any App Service `DATABASE_URL` env vars — explicitly excluded; Don will do this via portal due to PowerShell `&` escaping issues.
- Do NOT touch Schwab callback URLs — separate phase.
- Do NOT proceed past a failed phase. Halt and report.
