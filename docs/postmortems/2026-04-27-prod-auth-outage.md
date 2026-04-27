# Postmortem: Prod Auth Outage — 2026-04-25 to 2026-04-27

## Symptom

Users hitting `https://oa.tmtctech.ai/` received Cloudflare 524 timeouts or
`auth_error=server_error` after completing the Entra login. The login callback
handler (`/api/v1/auth/entra/callback`) timed out trying to write a session
to the database.

Separately, app container restarts during this window failed at startup with:

```
[ERROR] app.models.session: Failed to initialize database:
(pyodbc.OperationalError) ('08001', '[08001] [Microsoft][ODBC Driver 18 for SQL Server]
TCP Provider: Error code 0x68 (104) (SQLDriverConnect)')
```

The container would crash, App Service would restart it, and the same crash
would repeat — a persistent crash loop that blocked all user traffic.

## Diagnostic Timeline

**~2026-04-25 02:54 UTC** — App Service restarted (Don, via Azure portal).
App crashed at startup due to DB being paused. Crash loop began.

**2026-04-25 03:19 UTC** — Azure SQL database auto-paused (confirmed via
activity log: `Microsoft.Sql/servers/databases/pause`).

**2026-04-25 03:58 UTC** — DB auto-resumed. App eventually recovered and ran
through April 25 and 26 without further startup crashes — but every idle period
of 60+ minutes would trigger another auto-pause, causing login failures when
users tried to authenticate after a quiet window.

**2026-04-27 19:17–19:22 UTC** — Two consecutive Entra login attempts failed:
first with `HYT00` (login timeout — DB was mid-resume), then with `08001`
(TCP RST — Gateway rejected the connection while the DB was still stabilizing).

**2026-04-27 19:44 UTC** — Don updated `DATABASE_URL` app setting (ineffective,
see "What didn't cause it" below). The setting change triggered App Service
restarts. Multiple startup attempts at 19:49, 19:55, 19:58 all failed with
`08001`. The DB then resumed (triggered by accumulated connection attempts),
and the 20:04 startup succeeded.

**2026-04-27 20:37 UTC** — Claude Code (this session) issued a controlled
restart while DB was confirmed Paused. Reproduced `08001` at `SQLDriverConnect`
in 7 seconds, confirming the mechanism.

**2026-04-27 ~20:38 UTC** — Auto-pause disabled:
```bash
az sql db update --resource-group options-analyzer-rg \
  --server options-analyzer-sql \
  --name options-analyzer-db \
  --auto-pause-delay -1
```
DB came Online. App recovered through the next restart cycle (one more
`HYT00` crash at 20:49 during the update's own resume cycle, then clean
startup thereafter).

**2026-04-27 ~20:55 UTC** — `https://oa.tmtctech.ai/api/v1/health` returns 200.
Login flow verified through Cloudflare.

## Root Cause

**Azure SQL Serverless auto-pause (60-minute idle timer) combined with no
retry logic in `init_db()`.**

The database is `GP_S_Gen5` Serverless tier with `autoPauseDelay=60` minutes.
After 60 minutes with no database connections, Azure pauses the database engine.

When the App Service container restarts while the database is Paused:

1. `_install_odbc_if_needed()` completes (ODBC Driver 18 was already installed, ~0s)
2. `DefaultAzureCredential` acquires an MSI token (~11 seconds) — this works
3. `init_db()` calls `engine.begin()` → fires `do_connect` → `SQLDriverConnect`
4. The Azure SQL Gateway receives the connection but the DB engine is paused
5. The Gateway sends TCP RST → ODBC error `08001` ("Connection reset by peer")
6. `init_db()` raises, lifespan crashes, App Service restarts the container
7. Return to step 1 — tight crash loop

The DB stays Paused throughout the loop because the TCP RST from the Gateway
does NOT trigger auto-resume. Auto-resume requires the connection to make it
past the TCP handshake stage (the Gateway must be able to proxy it). RST at
the Gateway level means no resume signal reaches the DB engine.

Note: when a LIVE USER triggers a login (and thus a DB connection) while the DB
is Paused, the Gateway sometimes produces `HYT00` (login timeout) instead of
`08001` (RST) — this occurs when the user's connection causes the Gateway to
begin the resume process. `HYT00` with the default 30-second ODBC timeout means
the resume takes longer than 30 seconds. `08001` appears on connections that
arrive when the Gateway is not in "resuming" state.

## What Did NOT Cause It

**`DATABASE_URL` query parameters are ignored by the app.** The session.py code
parses only `hostname`, `port`, and `database` from the URL. Auth parameters
(`authentication=ActiveDirectoryMsi`, etc.) are stripped and never passed to
the driver. Changing `DATABASE_URL` had zero effect on connection behavior.

**MSI / token acquisition was not broken.** Logs confirm:
`DefaultAzureCredential acquired a token from ManagedIdentityCredential` on
every startup attempt. SQL role memberships (db_datareader, db_datawriter,
db_ddladmin) were intact. The token was being injected correctly via
`SQL_COPT_SS_ACCESS_TOKEN`.

**SQL Server firewall rules were not the issue.** `AllowAllWindowsAzureIps`
and `AzureServices-AllIPs` were present and correct.

**No code change caused this.** The most recent code changes were April 13
(OTA-500 pool settings). The outage started April 25. No code was deployed
between April 24 and this session.

## Fix Applied

```bash
az sql db update \
  --resource-group options-analyzer-rg \
  --server options-analyzer-sql \
  --name options-analyzer-db \
  --auto-pause-delay -1
```

`-1` = never auto-pause. No code change, no deployment, no restart required.
The `az sql db update` command also triggers an immediate resume from Paused
state as a side effect.

Both prod (`options-analyzer-api`) and dev (`options-analyzer-api-dev`) connect
to the same database, so this fix covers both environments.

## Detection Gap

The `/health` endpoint (and `/api/v1/health`) returns a static JSON response
and does NOT exercise the database. The keep-alive worker that pings `/health`
cannot detect a paused database or a startup crash loop. The outage was
invisible to monitoring until users tried to log in.

## Follow-up Work (Proposed Stories)

1. **SQL-aware health check** — Add `/api/v1/health/db` that executes
   `SELECT 1` against Azure SQL. Wire this into monitoring so a paused DB
   triggers an alert before users are affected.

2. **`init_db()` retry logic** — Wrap the startup DB connect in a retry loop
   with exponential backoff (3 attempts, 30s apart). This would allow the app
   to survive a single DB resume event (~30-90 seconds) without crashing. Would
   eliminate the crash loop even if auto-pause is ever re-enabled.

3. **Cost review** — Disabling auto-pause on GP_S_Gen5 adds ~$15-30/month
   (0.5 vCore minimum capacity, 24/7). Evaluate whether this cost is acceptable
   vs. implementing the retry logic in #2 and re-enabling auto-pause with a
   longer delay (e.g., 4 hours).

4. **`CLAUDE.md` update** — Document the Azure SQL Serverless auto-pause
   behavior and the `session.py` token injection pattern for future debugging.
