# QA Harness — Strategy Routing & Scoring Pipeline

Validates the end-to-end scoring pipeline after every dev deploy.

## Phase 2 Status

Capture infrastructure complete. Single-symbol smoke test (VOO) passing.
Assertion layer (Phase 3) and full-universe run (Phase 4) are next.

## Run Command

From project root, with venv activated:

```powershell
python qa-harness/harness/runner.py --symbol VOO --runs 1
```

Flags:
- `--symbol` — ticker to capture (default: VOO)
- `--runs` — number of sequential runs (Phase 2: always 1)
- `--allow-market-hours` — override the market-closed requirement

## Output

Captures land in `qa-harness/captures/{symbol}/run-{timestamp}.json`.

## Requirements

- Python 3.11+ with `requests` (already in project requirements.txt)
- Dev server reachable at `https://oa-dev.tmtctech.ai`
- Schwab OAuth connected on dev
- `SKIP_AUTH=True` set on dev App Service (or provide session cookie via `QA_HARNESS_SESSION_COOKIE` env var)

## Architecture

```
qa-harness/
  harness/
    runner.py           — orchestrator
    config.py           — env, bounds, sampling config
    auth.py             — auth header provider
    capture/
      stage_1_card.py   — POST /api/v1/analyze/scorecard
      stage_2_trades.py — POST /analyze/verticals + /analyze/long-calls
      stage_3_detail.py — extracts detail inline from Stage 2
      stage_4_evaluate.py — POST /api/v1/evaluate/structured (sampled)
      stage_5_order.py  — placeholder (no API)
    filters/
      candidate_bounds.py — width + strike window filters
  captures/             — gitignored, raw JSON
  reports/              — gitignored except last_green.json
```
