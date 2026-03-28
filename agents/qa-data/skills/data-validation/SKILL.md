# Skill: data-validation
Version: 1.0
Purpose: For a given config, compute independent expected values and compare against system output.

## Inputs
- `{{config}}` — a single config object from config-matrix (symbol, width, spread_type)
- `{{raw_chain_data}}` — raw option chain data from Schwab (or cached test data)
- `{{system_response}}` — the API response for the same config

## Steps

### 1. Independent Spread Construction
From raw chain data, construct spreads using **mid-price** per leg (never use system under test).

### 2. Independent Calculations
For each spread:
- **Max profit** (debit spread): `(width - entry_debit) × 100`
- **Max profit** (credit spread): `entry_credit × 100`
- **Max loss** (debit spread): `entry_debit × 100`
- **Max loss** (credit spread): `(width - entry_credit) × 100`
- **Net delta**: apply `abs()` to put leg deltas per OTA-274
- **Breakeven**: strike + debit (call) or strike - credit (put)

### 3. Filter Application
Apply filters independently:
- **Theta sentinel**: if `max_net_theta == 0`, the theta filter is disabled per OTA-281 — do not apply it
- Apply all other filters using the same parameter values as the system config

### 4. Comparison
Flag each discrepancy by type:
- `FALSE_NEGATIVE` — spread should appear in results but is missing
- `FALSE_POSITIVE` — spread appears in results but shouldn't
- `VALUE_MISMATCH` — spread is present but a calculated value differs
- `FILTER_MISMATCH` — filter pass/fail result differs

## Tolerances
- P&L values: exact match
- Greeks: ±0.001
- Prices: ±0.01

## Output Format

```json
{
  "config_id": "{symbol}-{width}-{spread_type}",
  "run_timestamp": "ISO 8601",
  "expected_count": 0,
  "actual_count": 0,
  "match_count": 0,
  "match_rate": 0.0,
  "status": "PASS | FAIL | ERROR",
  "anchor_trade_present": true,
  "anchor_trade_values_correct": true,
  "discrepancies": [
    {
      "type": "FALSE_NEGATIVE | FALSE_POSITIVE | VALUE_MISMATCH | FILTER_MISMATCH",
      "spread_id": "identifier",
      "details": "description",
      "filter_responsible": "filter name or null",
      "expected_value": "value",
      "actual_value": "value"
    }
  ]
}
```

## Rules
- NEVER use system under test for expected values
- Always use mid-price for spread construction
- Apply `abs()` to put deltas per OTA-274
- Treat `max_net_theta == 0` as sentinel per OTA-281 (disable filter)
- Log every comparison, not just failures
