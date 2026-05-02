# Data Validation Engine
# Version: 1.0

## Purpose
For a given configuration, compute independent expected values and compare
against the system's output. This is the core comparison engine per OTA-280.

## Input
- {{config}}: A single test configuration from the matrix
- {{raw_chain_data}}: Raw option chain data for the symbol
- {{system_response}}: The API response from the system under test

## Validation Steps

### 1. Independent Spread Construction
From raw_chain_data, independently construct all valid spreads for the
given symbol/width/spread_type combination:
- Match option pairs by strike width
- Use mid-price for each leg: (bid + ask) / 2
- Calculate entry price as the net debit or credit

### 2. Independent Calculations Per Spread
For each independently constructed spread, calculate:
- **Max Profit:** For debits = (width - entry_price) × 100. For credits = entry_price × 100
- **Max Loss:** For debits = entry_price × 100. For credits = (width - entry_price) × 100
- **Net Delta:** Sum of leg deltas, using abs(delta) for put legs (per OTA-274)
- **Net Gamma:** Sum of leg gammas
- **Net Theta:** Sum of leg thetas
- **Net Vega:** Sum of leg vegas
- **Breakeven Price:** Depends on spread type and direction

### 3. Independent Filter Application
Apply each filter to the independently calculated values:
- Delta filter: compare abs(net_delta) against threshold
- Theta filter: if max_net_theta == 0, filter is disabled (sentinel per OTA-281)
- All other filters per the system's current configuration

### 4. Comparison
Compare the system's output against the independent results:
- **FALSE_NEGATIVE:** Spread passes independent filters but is missing from system output
- **FALSE_POSITIVE:** Spread is in system output but fails independent filters
- **VALUE_MISMATCH:** Spread present in both but P&L or Greek values differ beyond tolerance
- **FILTER_MISMATCH:** Spread present in both but filter pass/fail status differs

### 5. Tolerance
- P&L values: exact match required (integer cents)
- Greek values: tolerance of ±0.001 (floating point)
- Prices: tolerance of ±0.01 (penny precision)

## Output Format (JSON)
```json
{
  "config_id": "SPY-10-bull_call",
  "run_timestamp": "ISO-8601",
  "expected_count": 45,
  "actual_count": 43,
  "match_count": 42,
  "match_rate": 0.933,
  "status": "FAIL",
  "anchor_trade_present": true,
  "anchor_trade_values_correct": true,
  "discrepancies": [
    {
      "type": "FALSE_NEGATIVE",
      "spread_id": "SPY_450C_460C_2026-04-17",
      "details": "Filtered out by delta filter — system used raw delta, should use abs()",
      "filter_responsible": "max_net_delta",
      "expected_value": 0.35,
      "actual_value": -0.35
    },
    {
      "type": "VALUE_MISMATCH",
      "spread_id": "SPY_445C_455C_2026-04-17",
      "field": "max_profit",
      "expected_value": 520,
      "actual_value": 480,
      "delta": 40,
      "details": "Entry price calculated differently — possible bid/ask vs mid-price issue"
    }
  ]
}
```

## Rules
- Never use the system under test to compute expected values
- Always use mid-price for independent calculations
- Apply abs() to put leg deltas per OTA-274
- Treat max_net_theta == 0 as sentinel (filter disabled) per OTA-281
- Log every comparison, not just failures
