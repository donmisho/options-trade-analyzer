# Claude Code Prompt — OTA-284
## MSFT Anchor Trade Regression Test Endpoint

### Ticket
- OTA-284: Add a dedicated regression test endpoint for the three MSFT anchor trades from 03-25-2026

### Prerequisite
**Run this prompt AFTER OTA-281/282/283 fixes are committed.** The anchor test validates those fixes are correct.

---

### Before You Start

```bash
cat app/routers/analysis_routes.py
cat app/engines/vertical_engine.py | head -80
```

Read the route registration pattern before adding the new endpoint.

---

### What to Build

Add a new **dev-only** endpoint:

```
POST /api/v1/test/filter-validation/msft-anchor
```

This endpoint is **dev-only** — gate it with a check on `settings.app_env` (or equivalent). If `app_env == "production"`, return `403`.

**What it does:**
1. Fetches the live MSFT options chain for the **May 15, 2026 expiration** via the Schwab provider
2. Runs the chain through `vertical_engine.py` with:
   - 25-point spread width
   - No restrictive filters (delta min=0, delta max=1.0, theta max=0, credit pct min=0)
3. Looks for all three anchor trades in the results

**Required anchor trades:**

| Spread | Entry (±0.05) | max_profit | max_loss |
|--------|--------------|-----------|----------|
| BEAR_PUT_DEBIT 370/345 | ~8.80 | 1620 | 880 |
| BEAR_PUT_DEBIT 350/325 | ~5.35 | 1965 | 535 |
| BEAR_CALL_CREDIT 395/420 | ~5.40 | 540 | 1960 |

**Response — success (all three found):**
```json
{
  "status": "pass",
  "results": [
    {
      "spread": "BEAR_PUT_DEBIT 370/345",
      "entry_price": 8.82,
      "max_profit": 1620,
      "max_loss": 880,
      "matched": true
    },
    ...
  ]
}
```

**Response — failure (one or more missing):**
```json
{
  "status": "fail",
  "failures": [
    {
      "spread": "BEAR_PUT_DEBIT 370/345",
      "reason": "Not found in results — no spread matched strikes 370/345 within entry price tolerance"
    }
  ]
}
```
Return HTTP `400` on failure so it's clearly distinguishable from a server error.

---

### Route File

Add the endpoint to a new file: `app/routers/test_routes.py`

Register it in `app/main.py` under the prefix `/api/v1/test` — only when `app_env != "production"`.

---

### House Style
- No `$` prefix anywhere in response values
- Entry price formatted `##.00`
- No dollar signs in any field name or value

---

### After Building

Test manually via Swagger at `https://127.0.0.1:8000/docs`:
1. Call the endpoint
2. Confirm all three anchors return `matched: true`
3. If any fail, it indicates the OTA-281/282/283 fixes are incomplete — do not commit until all three pass

---

### Commit Message
```
OTA-284 feat: MSFT anchor trade regression test endpoint
```
