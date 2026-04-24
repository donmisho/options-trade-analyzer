# OTA-512 API contract (T1 -> T2 handoff)

## localStorage read target (for T2 to consume)
- Top-level key: `analysisConfig`
- Nested path to overrides: `JSON.parse(localStorage.getItem('analysisConfig')).strategyOverrides[strategyKey]`
- Storage format: JSON string
- Written by:
  - `ConfigDrawer.jsx` lines 232-235 (gear icon apply)
  - `StrategyPage.jsx` lines 441-444 (inline param save)
  - `TradesPage.jsx` lines 473-476 (trades page param save)

## API client signature (confirmed in Phase 2)
- File: `web/src/api/client.js`
- New signature: `getStrategyScorecard(symbol, userConfig = null)`
- Also exported as alias: `runScorecard = getStrategyScorecard`
- Request body when userConfig is truthy and non-empty: `{ symbol, user_config: <object> }`
- Request body when userConfig is null/undefined/falsy: `{ symbol }` (no user_config key — `userConfig || undefined` serializes to omitted key in JSON.stringify)

## user_config shape expected by backend (confirmed in Phase 0 + Phase 3)
- Shape: **flat dict** — NOT nested per strategy key
- Fields the scorer reads (all optional, all fall back to strategy defaults):
  - `dte_min` — integer, minimum DTE filter
  - `dte_max` — integer, maximum DTE filter
  - `delta_min` — float, minimum delta filter
  - `delta_max` — float, maximum delta filter
  - `sma_alignment_score` — float 0-1, for trend-rider (from frontend SMA indicator)
  - `iv_rank_proxy` — float 0-100, explicit IV rank override
- Applied to ALL strategies uniformly — the same flat dict is passed to every scorer function.
  There is no per-strategy routing inside the backend. This is intentional.

## Transform from localStorage -> user_config
- localStorage stores overrides nested by strategy key:
  `{ strategyOverrides: { "weekly-grind": { dte_min: 5, dte_max: 21, ... }, "trend-rider": { ... } } }`
- Backend expects a flat dict for a single call: `{ dte_min: 5, dte_max: 21, ... }`
- **Transform required:** extract the per-strategy slice for the active strategy key.
  ```js
  const stored = JSON.parse(localStorage.getItem('analysisConfig') || '{}');
  const userConfig = stored.strategyOverrides?.[activeStrategyKey] || null;
  // pass userConfig as second arg to getStrategyScorecard
  ```
- For the batch "Find Trades" scan (all symbols, all strategies): the current call passes no
  userConfig. T2 must decide which strategy's overrides (if any) to apply to the batch call.
  One reasonable approach: no overrides on batch scan (keep null) since the scan covers all
  four strategies and overrides would distort cross-strategy comparison. T2 owns this decision.

## T2 responsibilities
- Read localStorage at scan time (not mount time).
- Extract `analysisConfig.strategyOverrides[activeStrategyKey]` for single-strategy calls.
- Pass result (or null if missing/empty) as second arg to `getStrategyScorecard`.
- Do NOT modify the API client. T1 owns it.
- Decide batch-scan behavior (see Transform note above).

## Verified curl commands (Phase 3 reference)

### Baseline — no user_config (default DTE behavior)
```
curl.exe -sk -X POST "https://127.0.0.1:8000/api/v1/analyze/scorecard" -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d "{\"symbol\": \"AAPL\"}"
```

### Override — dte_min=10, dte_max=20
```
curl.exe -sk -X POST "https://127.0.0.1:8000/api/v1/analyze/scorecard" -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d "{\"symbol\": \"AAPL\", \"user_config\": {\"dte_min\": 10, \"dte_max\": 20}}"
```

### Observed behavioral change (AAPL, 2026-04-24)
| Strategy | Baseline expiry | Override expiry | Baseline candidates | Override candidates |
|---|---|---|---|---|
| weekly-grind | 2026-04-29 (5 DTE) | 2026-05-04 (10 DTE) | 84 spreads | 47 spreads |
| steady-paycheck | 2026-05-22 (28 DTE) | 2026-05-04 (10 DTE) | 20 spreads | 47 spreads |
| trend-rider | 2026-05-29 (35 DTE) | 2026-05-08 (14 DTE) | 49 candidates | 32 candidates |
| lottery-ticket | 2026-04-27 (3 DTE) | 2026-05-08 (14 DTE) | 33 candidates | 32 candidates |

DTE filter applied uniformly across all strategies. Backend confirmed wired.
