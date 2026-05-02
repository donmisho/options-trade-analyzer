# Configuration Matrix Generator
# Version: 1.0

## Purpose
Generate and manage the complete test configuration matrix for data
quality validation. Based on OTA-280 spec.

## Input
- {{symbols}}: Array of symbols (default: ["SPY","QQQ","MSFT","IWM"])
- {{widths}}: Array of strike widths in dollars (default: [10, 20, 25, 30])
- {{spread_types}}: Array of spread types
  (default: ["bull_call","bear_call","bull_put","bear_put"])

## Output
A JSON array of test configurations. Generate all permutations — never
skip combinations.

```json
[
  {
    "config_id": "SPY-10-bull_call",
    "symbol": "SPY",
    "width": 10,
    "spread_type": "bull_call",
    "status": "PENDING",
    "run_timestamp": null,
    "result": null,
    "match_count": null,
    "expected_count": null,
    "actual_count": null,
    "discrepancy_count": null
  }
]
```

## Config ID Format
{symbol}-{width}-{spread_type}

## Status Values
- PENDING: Not yet run
- RUNNING: Currently executing
- PASS: Match rate >= 95% and no anchor trade failures
- FAIL: Match rate < 95% or anchor trade missing/incorrect
- ERROR: Execution failed (API down, data unavailable, etc.)

## Anchor Trade Configs
The following configs contain MSFT anchor trades (from OTA-284) and have
a hard pass requirement regardless of overall match rate:
- MSFT-10-bull_call
- MSFT-20-bear_put
- MSFT-25-bull_put

## Rules
- Total configs must equal symbols × widths × spread_types
- Default matrix: 4 × 4 × 4 = 64 configurations
- Config IDs must be deterministic and sortable
- Never generate duplicates
