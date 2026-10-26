```yaml
---
allowedTools:
  - Read
  - Grep
  - Glob
  - Edit
  - Bash(cat*)
  - Bash(git*)
  - Bash(python*)
  - Bash(pytest*)
  - Bash(alembic*)
  - Bash(uvicorn*)
  - Bash(Get-Process*)
  - Bash(Stop-Process*)
  - Bash(netstat*)
  - Bash(Invoke-RestMethod*)
  - Bash(az*)
---
```

# OTA-855 — Bring the Schwab account activity poller up on this machine

The poller was built and pushed on branch `OTA-855-account-activity-poller` (commit `41d873c`). This prompt makes the local machine run it end to end against the real Schwab account, verifies the Trader API payloads against the parser, and prepares the App Service settings. Do NOT run `git commit` or `git push` — Don holds the commit gate. Do NOT edit any file under `claude_context/`.

## Mechanism A — Required Reading (run first)

```powershell
Set-Location "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
cat claude_context/CLAUDE.md
cat claude_context/SCHWAB-LOGIN-PROCESS.md
cat claude_context/development-environment.md
cat claude_context/deployment-workflow.md
cat docs/runbooks/account-activity-poller.md
cat .env.example
```

## Mechanism B — Governing rules embedded

* The venv is `venv` (not `.venv`); activate it before any python, pytest, alembic or uvicorn command.
* Kill zombie Python and uvicorn processes before starting the backend; confirm nothing listens on port 8000.
* `.env` is never committed. Never print its secret values back into the chat; print only the four `BROKER_*` keys.
* Migrations are Alembic, expand-only. `alembic upgrade head` on the database `.env` points at is the dev path; production is migrated by hand after deploy, never from this machine.
* Provider routing is never hardcoded; the poller gets its adapter from the provider registry.
* Data Isolation Invariant: every broker_* row carries `user_id`.
* House style: dates `mm-dd-yyyy` in any UI text; no `$` in UI; PowerShell for every command.

## Step 1 — Check out the branch

```powershell
git fetch origin
git status
git checkout OTA-855-account-activity-poller
git pull origin OTA-855-account-activity-poller
git log --oneline -3
```

Confirm the top commit is `OTA-855 feat: Schwab account activity poller …`. If the working tree had uncommitted changes before checkout, stop and report them.

## Step 2 — Settings in `.env`

Read the current `.env` (do not echo secrets). Add these keys if absent, keeping every existing line as is:

```
BROKER_ACTIVITY_POLL_ENABLED=true
BROKER_ACTIVITY_USER_ID=
BROKER_ACCOUNT_LABELS=7892=Options,????=IRA
BROKER_ACTIVITY_DISPLAY_TZ=America/Chicago
```

`????` is the last four digits of the IRA account number. If they are not written anywhere in the repo or `.env`, **ask Don for them before continuing**; do not guess. The Options account ends in 7892 (the statement header the dashboard parses). Leave `BROKER_ACTIVITY_USER_ID` empty unless the users table holds more than one admin; then set it to Don's `users.id` (Entra OID).

## Step 3 — Dependencies, migration, tests

```powershell
venv\Scripts\activate
pip install -r requirements.txt
alembic current
alembic upgrade head
alembic current
pytest tests\agents\test_account_activity.py -q
pytest tests\services tests\test_changelog.py tests\test_data_isolation_contract.py -q
```

Expected: `alembic current` ends at `b7c2d4e6f8a1 (head)`; 20 passed in the agents file; the other suites green. `tests\lifespan\test_shutdown.py` is known red on main (an older migration against SQLite) and is not part of this ticket.

## Step 4 — Run the backend and sign in to Schwab again

```powershell
Get-Process python,uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force
netstat -ano | findstr ":8000"
uvicorn app.main:app --reload --ssl-keyfile=key.pem --ssl-certfile=cert.pem --host=127.0.0.1 --port=8000
```

Watch the startup log for `Account activity poller ready` and `Account activity poller scheduled. Next run: …`. If it logs `Account activity poller disabled: …`, report the reason and stop.

Then in the browser, signed in to the app, open `https://127.0.0.1:8000/api/v1/auth/schwab/login` and complete the Schwab login once more. The Trader API calls need a token issued after the developer app's **Accounts and Trading Production** product was enabled; the old token covers market data only.

## Step 5 — First pull and payload check

From Swagger at `https://127.0.0.1:8000/docs`:

1. `POST /api/v1/account-activity/run` — expect `status: ok` with `accounts` ≥ 1 and `transactions_new` > 0 (the first run reaches 59 days back).
2. `GET /api/v1/account-activity/status` — the run is listed with its counts.
3. `GET /api/v1/account-activity/fills?start=2026-10-01` — rows in the Trades-sheet shape with `atr_used` and `spread_pct_mid` populated on today's fills (`context_kind` = `live`) and `context_kind` = `daily` on older ones.

If the run answers `status: error` naming a 401/403 from the Trader API, the developer app product or the re-login is the cause; report and stop.

Now verify the parser against the real payloads, since the field names were taken from client libraries rather than the portal. With the app's database tools or a short Python snippet in the venv, read `raw_json` from three `broker_transactions` rows (one single-leg fill, one vertical, one with fees) and two `broker_orders` rows (one with bracket children). Compare against what `app/services/broker_activity.py` reads: `transferItems[].instrument.{assetType,symbol,putCall,strikePrice,expirationDate,underlyingSymbol,optionPremiumMultiplier}`, `transferItems[].{amount,cost,price,positionEffect,feeType}`, `activityId`, `orderId`, `positionId`, `time`, `tradeDate`, `netAmount`; and for orders `orderLegCollection[].{instruction,positionEffect,quantity,instrument}`, `childOrderStrategies`, `stopPrice`, `enteredTime`, `closeTime`, `filledQuantity`. Check in the `fills` answer that `contract_price`, `net_profit_loss`, `total_fees`, `strike` ("580" or "495/500" with the long leg first) and `type` match the same fills in the thinkorswim statement export.

If any name or sign differs, fix `normalize_transaction` / `normalize_order` in `app/services/broker_activity.py`, update `tests/agents/test_account_activity.py` so its sample payloads use the real shape, rerun the tests, and leave the edits uncommitted for Don's review. Report every difference found.

## Step 6 — App Service settings (ask Don first)

The dev and prod App Services read environment variables, not `.env`. Ask Don for a go before running these, then apply the same four keys with the real IRA digits:

```powershell
az webapp config appsettings set --resource-group <rg> --name options-analyzer-api-dev --settings BROKER_ACTIVITY_POLL_ENABLED=true BROKER_ACTIVITY_USER_ID= BROKER_ACCOUNT_LABELS="7892=Options,????=IRA" BROKER_ACTIVITY_DISPLAY_TZ=America/Chicago
az webapp config appsettings set --resource-group <rg> --name options-analyzer-api --settings BROKER_ACTIVITY_POLL_ENABLED=true BROKER_ACTIVITY_USER_ID= BROKER_ACCOUNT_LABELS="7892=Options,????=IRA" BROKER_ACTIVITY_DISPLAY_TZ=America/Chicago
```

Take `<rg>` from `claude_context/azure-naming-conventions.md` or ask Don. Do not change any other setting.

## Step 7 — Report

End with: the `alembic current` value, the test counts, the first run's counts, the payload differences found (or "none"), the files you edited, and the next step for Don: merge the branch to main (the push triggers the build and moves OTA-855 to Code & Test Complete), deploy to the staging slot, run `alembic upgrade head` against prod from a workstation with prod Entra credentials, swap, then add the `ota-market-data` MCP server as a connector in claude.ai so the dashboard can read `get_trade_fills`.

Post-build QA level: 2 (schema change) — the targeted suites above plus the manual route exercise in Step 5.
