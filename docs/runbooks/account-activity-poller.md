# Account activity poller (OTA-855)

Pulls the Schwab account statement into Azure SQL every 15 minutes in market hours and serves it back as the fill rows the Short-DTE Trade Lab dashboard reads. One Story, four moving parts:

| Part | Where |
|---|---|
| Trader API adapter | `app/providers/schwab_account.py` (`SchwabAccountActivity`), registered in `PROVIDER_REGISTRY` under the `account_activity` capability |
| Poller | `app/agents/account_activity_sync.py` (`AccountActivitySync`), scheduled in `app/main.py` next to the position monitor |
| Tables | `broker_accounts`, `broker_transactions`, `broker_orders`, `broker_fill_context`, `broker_sync_runs` (Alembic `b7c2d4e6f8a1`) |
| Read path | `GET /api/v1/account-activity/fills` and the MCP tool `get_trade_fills`, both through `app/services/trade_fills.py` |

## What one run does

1. `GET /trader/v1/accounts/accountNumbers` → one `broker_accounts` row per account (hash, last four digits, label).
2. `GET /trader/v1/accounts/{hash}/transactions?types=TRADE` from three days before the latest stored fill (59 days back on the first run, the API's limit) → new `activityId`s only into `broker_transactions`. The raw JSON is kept on every row; the normalized columns describe the fill the way the statement export does (`strikes_text` "495/500" long leg first, `structure` Vertical, `price` per spread, commissions and fees split).
3. `GET /trader/v1/accounts/{hash}/orders` over the same window plus seven days → `broker_orders`, upserted by `orderId`, so a stop that fired or a target that was cancelled updates in place. Bracket children carry `parent_order_id`.
4. For each new option fill: the underlying and option quotes at this poll and ATR14 (Wilder, from the daily candles before the trade date) → `broker_fill_context`. `atr_used` is |underlying net change| ÷ ATR14; `spread` is ask − bid, `spread_pct_mid` the spread over the mid. A fill older than six hours (a backfill) gets `kind = daily`: the day's candle stands in for the quote and no option spread is recorded.
5. One `broker_sync_runs` row per run with the window, the counts and any error.

The schedule fires every 15 minutes 09:00–16:45 ET Mon–Fri; the run stands down before 09:30. A manual run ignores the clock.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `BROKER_ACTIVITY_POLL_ENABLED` | `true` | Build and schedule the poller |
| `BROKER_ACTIVITY_USER_ID` | empty | `users.id` (Entra OID) that owns the pulled rows. Empty: the single active admin user, else the single user, else the run records an error |
| `BROKER_ACCOUNT_LABELS` | empty | Labels by the last four digits of the account number, e.g. `7892=Options,1234=IRA`. Unlabelled accounts show as `…7892` |
| `BROKER_ACTIVITY_DISPLAY_TZ` | `America/Chicago` | Wall-clock zone of `trade_datetime` in the fill rows, the zone the statement exports use |

No new secrets. The Trader API calls use the same `schwab-token-data` tokens as market data, so the Schwab developer app must have the **Accounts and Trading Production** product enabled; without it the transactions and orders calls answer 401/403 and the run records that message.

## Deploy

Expand-only migration, so the usual order applies: deploy, then on prod run `alembic upgrade head` from a workstation with prod Entra credentials, verify `alembic current` shows `b7c2d4e6f8a1`, then swap. Dev applies it at startup.

## Run it by hand (PowerShell)

```powershell
Set-Location "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
venv\Scripts\activate
alembic upgrade head
uvicorn app.main:app --reload --ssl-keyfile=key.pem --ssl-certfile=cert.pem --host=127.0.0.1 --port=8000
```

Then, signed in to the app in the browser (the BFF session cookie and CSRF token are required):

```powershell
# trigger a run now
Invoke-RestMethod -Method Post -Uri https://127.0.0.1:8000/api/v1/account-activity/run -WebSession $session -Headers @{ "X-CSRF-Token" = $csrf }
# last runs and the next scheduled time
Invoke-RestMethod -Uri https://127.0.0.1:8000/api/v1/account-activity/status -WebSession $session
# the fill rows the dashboard reads
Invoke-RestMethod -Uri "https://127.0.0.1:8000/api/v1/account-activity/fills?start=2026-10-01" -WebSession $session
```

Swagger at `https://127.0.0.1:8000/docs` is the simpler way to call the three routes from a signed-in browser.

## The dashboard as a reader

The MCP tool `get_trade_fills(start_date?, end_date?, account?, limit?)` returns `{columns, rows, count, as_of, display_tz, source}` with the rows in the statement's Trades-sheet columns plus `atr_used`, `atr14`, `underlying_net_change`, `option_bid`, `option_ask`, `spread`, `spread_pct_mid`, `context_kind`, `context_captured_at` and `context_lag_seconds`. With the `ota-market-data` server added as a connector in claude.ai, the dashboard's dataset becomes a live query on that connector calling this tool, and every open of the dashboard reads the latest fills under the viewer's own login.

## Tests

```powershell
pytest tests\agents\test_account_activity.py -q
```

Normalization, bracket flattening, ATR and context math, market-hours gating, and the sync against SQLite with a fake provider (first run, idempotent second run with an order state change, stand-down outside market hours, daily context for old fills, missing owner user, user-scoped fill rows).
