# OTA-672 — Schwab Outbound Symbol Translation (Caller-Side Wiring) Cutover Log

**Date:** 2026-05-19
**Ticket:** OTA-672
**Commit:** `OTA-672 feat: schwab outbound symbol translation caller-side wiring`

---

## Architecture Decision: D1 — Sync Cached Helper

Instead of plumbing `AsyncSession` to every caller, a startup-loaded in-memory
cache (`app/services/symbol_cache.py`) provides a sync `to_api_symbol_cached(symbol, provider)`
that any caller can use without `db` or `await`. The cache is populated from
`symbol_reference.api_symbol` at startup and refreshed every 6 hours.

---

## Step 1 — Cache Module

| Action | Detail |
|--------|--------|
| New file | `app/services/symbol_cache.py` — `_api_symbol_cache` dict, `_refresh_api_symbol_cache()`, `start_symbol_cache_refresh_task()`, `to_api_symbol_cached(symbol, provider)` |
| Lifespan integration | `app/main.py` — cache populated after `init_db()` (step 1b), refresh task cancelled on shutdown (step 1.5) |
| Unit tests | `tests/services/test_symbol_cache.py` — 10 tests (6 sync lookup, 3 refresh, 1 integration) |

---

## Step 2 — Caller-Site Wiring

All upstream callers of `provider.get_quote()`, `provider.get_chain()`, and
`SchwabPriceContextSource.fetch()` now translate canonical → api_symbol before
invoking the provider method.

| # | File | Line(s) | Provider Method | Translation Added |
|---|------|---------|-----------------|-------------------|
| 1 | `app/api/market_routes.py` | 72 | `get_quote` | `api_sym = to_api_symbol_cached(sym, "schwab")` |
| 2 | `app/api/market_routes.py` | 133 | `get_chain` | `api_sym = to_api_symbol_cached(symbol, "schwab")` |
| 3 | `app/api/market_routes.py` | 259 | `get_quote` | `api_sym = to_api_symbol_cached(sym, "schwab")` (market overview loop) |
| 4 | `app/api/analysis_routes.py` | 189 | `get_chain` | `api_sym = to_api_symbol_cached(symbol, "schwab")` (`_fetch_chain` helper) |
| 5 | `app/api/analysis_routes.py` | 870/878 | `get_quote` | `api_sym = to_api_symbol_cached(sym, "schwab")` (scorecard) |
| 6 | `app/api/analysis_routes.py` | 871 | `get_price_history` | Same `api_sym` reused (scorecard parallel gather) |
| 7 | `app/api/position_routes.py` | 949 | `get_quote` | `api_sym = to_api_symbol_cached(sym, "schwab")` (batch health grades) |
| 8 | `app/api/position_routes.py` | 1033 | `get_quote` | `api_sym = to_api_symbol_cached(pos.symbol, "schwab")` (current prices) |
| 9 | `app/api/position_routes.py` | 1047/1080 | `get_option_chain` | Reuses `api_sym` from quote translation above |
| 10 | `app/api/position_routes.py` | 1258 | `get_quote` | `api_sym = to_api_symbol_cached(pos.symbol, "schwab")` (refresh) |
| 11 | `app/api/position_routes.py` | 1268 | `get_option_chain` | Reuses `api_sym` from quote translation above |
| 12 | `app/api/named_watchlist_routes.py` | 261 | `get_quote` | `api_sym = to_api_symbol_cached(symbol, "schwab")` |
| 13 | `app/api/export_routes.py` | 804 | `get_chain` | `api_sym = to_api_symbol_cached(symbol, "schwab")` |
| 14 | `app/api/mcp_routes.py` | 349 | `get_quote` | `api_ticker = to_api_symbol_cached(ticker, "schwab")` |
| 15 | `app/api/mcp_routes.py` | 459 | `get_chain` | `api_ticker = to_api_symbol_cached(ticker, "schwab")` |
| 16 | `app/api/mcp_routes.py` | 614/615 | `get_price_history` + `get_quote` | `api_ticker = to_api_symbol_cached(ticker, "schwab")` |
| 17 | `app/analysis/strategy_scorer.py` | 564 | `get_chain` | `api_sym = to_api_symbol_cached(symbol, "schwab")` |
| 18 | `app/analysis/chain_collection.py` | 49 | `get_chain` | `api_sym = to_api_symbol_cached(symbol, "schwab")` |
| 19 | `app/providers/schwab_context_source.py` | 63 | `get_quote` (via `fetch`) | `api_sym = to_api_symbol_cached(symbol, "schwab")` |

### Skipped call sites

| File | Line | Reason |
|------|------|--------|
| `app/api/test_routes.py` | 86 | Hardcoded `"MSFT"` — diagnostic endpoint, not a production path |
| `app/api/export_routes.py` | 278 | `VIX_API_SYMBOL = "$VIX"` — already in api_symbol form |
| `app/api/export_routes.py` | 294-295 | Hardcoded `"SPY"`, `"QQQ"` — normal tickers, no translation needed |
| `app/providers/schwab.py` | 175 | Internal `self.get_quote(symbol)` inside `get_chain` — caller already passes api_symbol |
| `app/providers/schwab.py` | 432 | Health check `self.get_quote("SPY")` — normal ticker, no translation needed |

### Expanded scope beyond prompt

`get_price_history` and `get_option_chain` callers were also wired (rows 6, 9, 11, 16).
These Schwab methods also pass the symbol to the Schwab REST API and would fail for index
symbols without translation. Same one-liner pattern, zero additional risk.

---

## Step 3 — Docstring Updates

| File | Method | Contract note added |
|------|--------|---------------------|
| `app/providers/schwab.py` | `get_quote` | Expects api_symbol form; callers must translate via `to_api_symbol_cached` |
| `app/providers/schwab.py` | `get_chain` | Same contract note |
| `app/providers/schwab_context_source.py` | `fetch` | Accepts canonical; translates internally via `to_api_symbol_cached` |

---

## Step 4 — Architecture-plan.md

- Updated `Last Updated` header to `2026-05-19 UTC`
- Added contract note to Pattern 1 description
- Added Change Log entry referencing OTA-672

---

## Test Results

### pytest
```
513 passed, 2 skipped, 3 warnings in 23.59s
```
Matches baseline (503 from OTA-668 + 10 new symbol_cache tests = 513).

### Live SPX round-trip
**DEFERRED.** Backend not running; Schwab OAuth requires manual browser login.
Don to verify after backend startup:
1. Start backend with Schwab connected
2. `curl https://127.0.0.1:8000/api/v1/market/quote/SPX` (canonical form)
3. Confirm `to_api_symbol_cached("SPX", "schwab")` returns `"$SPX"`
4. Confirm Schwab returns a valid quote (last price, timestamp)

---

## Findings Not in Audit

- `test_routes.py:86` uses hardcoded `"MSFT"` — diagnostic endpoint only, not a production code path. Confirmed by reading context: `symbol="MSFT"` is a string literal in the `get_chain` call. Skipped.
- `get_price_history` and `get_option_chain` callers were not in the original 3-method audit scope but were wired for completeness (see "Expanded scope" above).
- `market_context.py:38` uses `VIX_API_SYMBOL = "$VIX"` directly in `get_price_history` — already api_symbol form, no translation needed.

---

## File Inventory

| Status | File |
|--------|------|
| NEW | `app/services/symbol_cache.py` |
| NEW | `tests/services/test_symbol_cache.py` |
| MODIFIED | `app/main.py` |
| MODIFIED | `app/api/market_routes.py` |
| MODIFIED | `app/api/analysis_routes.py` |
| MODIFIED | `app/api/position_routes.py` |
| MODIFIED | `app/api/named_watchlist_routes.py` |
| MODIFIED | `app/api/export_routes.py` |
| MODIFIED | `app/api/mcp_routes.py` |
| MODIFIED | `app/analysis/strategy_scorer.py` |
| MODIFIED | `app/analysis/chain_collection.py` |
| MODIFIED | `app/providers/schwab.py` |
| MODIFIED | `app/providers/schwab_context_source.py` |
| MODIFIED | `claude_context/architecture-plan.md` |

---

## Banner: SUCCESS (live SPX round-trip deferred to manual verification)
