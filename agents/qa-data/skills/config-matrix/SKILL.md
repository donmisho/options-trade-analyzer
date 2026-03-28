# Skill: config-matrix
Version: 1.0
Purpose: Generate and manage the complete test configuration matrix per OTA-280.

## Inputs
- `{{symbols}}` — default `["SPY","QQQ","MSFT","IWM"]`
- `{{widths}}` — default `[10, 20, 25, 30]`
- `{{spread_types}}` — default `["bull_call","bear_call","bull_put","bear_put"]`

## Instructions

Generate all permutations of symbols × widths × spread_types.

Default total: 4 × 4 × 4 = **64 configs**.

### Anchor Configs (always flag these)
- `MSFT-10-bull_call`
- `MSFT-20-bear_put`
- `MSFT-25-bull_put`

### Config ID Format
`{symbol}-{width}-{spread_type}` — must be deterministic and sortable.

## Output Format

```json
{
  "generated_at": "ISO 8601",
  "source_ticket": "OTA-280",
  "pass_threshold": 0.95,
  "anchor_trades": [
    {"config_id": "MSFT-10-bull_call", "description": "MSFT $10-wide bull call spread"},
    {"config_id": "MSFT-20-bear_put", "description": "MSFT $20-wide bear put spread"},
    {"config_id": "MSFT-25-bull_put", "description": "MSFT $25-wide bull put spread"}
  ],
  "configs": [
    {
      "config_id": "{symbol}-{width}-{spread_type}",
      "symbol": "SPY",
      "width": 10,
      "spread_type": "bull_call",
      "status": "PENDING",
      "is_anchor": false
    }
  ]
}
```

## Rules
- Generate ALL permutations — never skip any
- Config IDs must be deterministic and sortable
- Never generate duplicates
- Mark the three anchor configs with `"is_anchor": true`
