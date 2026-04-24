---
allowedTools:
  - Bash
  - Read
  - Write
  - Edit
---

# OTA-508 — Finnhub EarningsCalendarProvider

**Wave:** AMZN April 22 Scoring Pipeline Fixes v2
**Parent Epic:** OTA-507 (Ongoing: Trade Evaluation Anomaly Resolution)
**Parent Feature:** OTA-501 (Scoring Pipeline Fixes v2 — AMZN Validation April 22)
**Blocks:** OTA-502 (Earnings-in-window hard gate), transitively OTA-506

## Context

Schwab's `instruments?projection=FUNDAMENTAL` endpoint inherited the stripped TDA shape and does not expose `nextEarningsDate`. OTA-502 cannot be implemented without an earnings data source. This Story implements `FinnhubEarningsSource` as the cheap interim adapter. Polygon.io will replace it later during Phase 3.3 backtesting work.

**Adapter contract:**
- `source_id = 'finnhub_earnings'`
- `signal_type = 'FUNDAMENTAL'`
- `ttl_seconds = 86400`
- 90-day forward window per call
- Async credentials throughout
- API key in Key Vault `options-analyzer` as `finnhub-api-key`

**Non-negotiable architectural constraint:**
Async credentials throughout. Use `azure.identity.aio.DefaultAzureCredential` and `azure.keyvault.secrets.aio.SecretClient`. NEVER sync `azure.identity` in async handlers. This is the same failure mode as the BFF identity production outage — we are not repeating it.

## Prerequisites

```bash
cat CLAUDE.md                              # confirm header timestamp is current
pwd                                        # should show ...options-analyzer
venv\Scripts\activate                      # Windows
git status                                 # uncommitted unrelated changes OK
```

If venv isn't activated or you're not in project root, STOP and report.

## Phase 0 — Verify Schwab fundamentals truly lacks earnings

Don't build the adapter if Schwab unexpectedly exposes the field. Five-minute proof.

```bash
grep -rn "FUNDAMENTAL" app/providers/ --include="*.py"
grep -rn "instruments" app/providers/schwab_market_data.py
```

Write `scratch/verify_schwab_earnings.py`:
- Use `SchwabMarketData` via `_get_provider()`
- Call fundamentals endpoint for AMZN, NVDA, AAPL
- Dump full JSON to `scratch/schwab_fundamentals_<symbol>.json`
- Print every field name recursively, grep output for `earnings|next.*earn|earn.*date` case-insensitive

**STOP and report:**
- Exact field names returned by Schwab fundamentals
- Whether ANY earnings-related field exists
- If earnings exists: do NOT proceed — report finding, ask Don whether to enhance Schwab adapter instead

Wait for confirmation before Phase 1.

## Phase 1 — Verify ContextSource and ContextStore exist

```bash
grep -rn "class ContextSource" app/
grep -rn "class ContextStore" app/
ls app/providers/
```

Expected files:
- `app/providers/context_source.py` — `ContextSource` ABC and `ContextSignal` dataclass
- `app/providers/context_store.py` — `ContextStore` with cache-or-fetch logic
- An existing `SchwabPriceContextSource` or equivalent reference implementation
- `ProviderFactory` (likely `app/providers/factory.py`) registering context sources

**STOP if any are missing.** The Phase 3.5 Stream A scaffolding may not have shipped yet. Report what's missing. Do NOT build on a missing foundation.

If everything exists, read each file in full and report:
- Exact `ContextSource` interface signature
- Exact `ContextSignal` shape
- How the existing reference source is registered with `ProviderFactory`
- How `ContextStore.fetch_or_cache(symbol, source_id)` (or equivalent) is invoked

Wait for confirmation before Phase 2.

## Phase 2 — Probe Finnhub before coding to a presumed schema

Never code against a guessed API response.

```bash
FINNHUB_KEY=$(az keyvault secret show --vault-name options-analyzer --name finnhub-api-key --query value -o tsv)
```

If the secret doesn't exist, STOP and report: "Secret 'finnhub-api-key' not found in vault 'options-analyzer'. Don needs to add it before this Story can proceed."

If the secret exists, hit Finnhub's earnings calendar for AMZN with a 90-day forward window. PowerShell-compatible (use Python for date math to avoid `date -d` portability issues):

```bash
python -c "from datetime import date, timedelta; t=date.today(); print(t.isoformat(), (t+timedelta(days=90)).isoformat())" > scratch/dates.txt
# Then assemble URL with those dates and fetch
```

Save response to `scratch/finnhub_amzn_raw.json` and pipe through `python -m json.tool`.

**STOP and report:**
- Exact response shape (wrapper key, fields, types)
- Whether AMZN has an earnings event in the window
- If AMZN has no earnings in the window, repeat for NVDA (reports more often)

Wait for confirmation before Phase 3. Adapter normalization depends on the real schema.

## Phase 3 — Build FinnhubEarningsSource

Create `app/providers/finnhub_earnings.py`. Use the reference `ContextSource` from Phase 1 as the structural template.

**Required behaviors:**

1. **Credentials.** Async load API key from Key Vault using `azure.identity.aio.DefaultAzureCredential` + `azure.keyvault.secrets.aio.SecretClient`. Cache key in-instance after first fetch. Never log the key, never write it to scratch files.

2. **Fetch.** `httpx.AsyncClient` (not `requests`). Timeout 10s. On 429, retry once with backoff; do NOT retry indefinitely.

3. **Normalize.** Map Finnhub response to `ContextSignal`. The `signal_value` payload:
```python
   {
     "next_earnings_date": "YYYY-MM-DD" | None,  # soonest event in window
     "time_of_day": "bmo" | "amc" | "dmh" | None,
     "eps_estimate": float | None,
     "quarter": int | None,
     "fetched_at": "YYYY-MM-DDTHH:MM:SSZ",
   }
```

4. **TTL.** `ttl_seconds() -> int: return 86400`.

5. **Failure mode.** On 4xx/5xx/timeout/empty, return a `ContextSignal` with `next_earnings_date=None` and a `meta.notes` field: `"finnhub_no_data"` | `"finnhub_rate_limited"` | `"finnhub_5xx"` | `"finnhub_timeout"`. Do NOT raise. OTA-502 will treat null earnings as "unknown, do not gate."

6. **Observability.** Fire-and-forget OTel span. Attributes: `provider=finnhub_earnings`, `symbol`, `cache_status`, `latency_ms`. Wrap in `asyncio.create_task` or equivalent fire-and-forget. Never let observability block the fetch.

**House rules:**
- Finnhub base URL as module-top constant
- Secret names as module-top constants with comment
- Type hints on every public method
- Class-level docstring explaining `signal_value` payload shape (consumers will read this)

`git diff app/providers/` → STOP. Wait for review before Phase 4.

## Phase 4 — Register with ProviderFactory

`grep -rn "ProviderFactory" app/providers/` to find the registration site. Add `FinnhubEarningsSource` using the same pattern as the existing reference source. Import in `app/providers/__init__.py` if that's the pattern.

`git diff` → STOP.

## Phase 5 — Live integration test

Write `scratch/test_finnhub_integration.py`:
1. Instantiate `FinnhubEarningsSource` via `ProviderFactory` (using whatever accessor the factory exposes for context sources)
2. Call the adapter for AMZN via `ContextStore.fetch_or_cache(symbol='AMZN', source_id='finnhub_earnings')`
3. Print the normalized `ContextSignal`
4. Verify the row is written to `symbol_context`:
```sql
   SELECT TOP 1 * FROM symbol_context 
   WHERE symbol='AMZN' AND source_id='finnhub_earnings' 
   ORDER BY created_at DESC
```
5. Repeat for NVDA and AAPL

**Acceptance:**
- AMZN, NVDA, AAPL rows exist in `symbol_context` with `source_id='finnhub_earnings'`, `signal_type='FUNDAMENTAL'`
- `signal_value` JSON parses and contains `next_earnings_date` (or null + reason)
- Calling again within 24 hours returns cached row (no duplicate fetch); refetch occurs after TTL expires
- No credentials appear in logs, console output, or scratch files

## Phase 6 — Summary

Print:
- Files created (paths + line counts)
- Files modified (paths + `git diff --stat` counts)
- The three `signal_value` payloads for AMZN, NVDA, AAPL
- Any deviations from this prompt and why
- Explicit confirmation: "OTA-502 implementer can now call `ContextStore.fetch_or_cache(symbol, 'finnhub_earnings')` to get earnings data."

**Do not commit.** Don reviews and commits manually.

## Commit message format (when Don is ready to commit)

```
OTA-508: Finnhub EarningsCalendarProvider — interim earnings data source
```

## House rules summary

- `azure.identity.aio` and `azure.keyvault.secrets.aio` only — never sync variants in async handlers
- No hardcoded provider names — registration via `ProviderFactory` only
- `ContextSource` writes go through `ContextStore` — not direct SQL
- API keys never logged, never in scratch files, never committed
- Fail-soft on Finnhub errors — return `next_earnings_date=null` with reason, don't raise
- Fire-and-forget observability — never block the fetch
- STOP after every phase with a diff for review

## Exit criteria

- Phases 0–6 complete and approved
- AMZN/NVDA/AAPL rows visible in `symbol_context`
- OTA-502 is unblocked
- No commit made