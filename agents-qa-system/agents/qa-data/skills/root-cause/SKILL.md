# Root Cause Analysis
# Version: 1.0

## Purpose
Given a set of data discrepancies from the validation engine, trace the
root cause to a specific function, module, or calculation in the codebase.
Produce a fix specification for the Backend Dev Agent.

## Input
- {{discrepancies}}: Array of discrepancy objects from data-validation
- {{source_files}}: Relevant source code files to examine

## Key Source Files in OTA
- app/services/vertical_engine.py — spread construction and filtering
- app/services/filter_engine.py — individual filter implementations
- app/services/greeks_calculator.py — Greek value computations
- app/services/pnl_calculator.py — P&L formulas
- app/providers/ — data provider layer (Schwab/Tradier)

## Analysis Steps

### 1. Pattern Detection
Group discrepancies by:
- type (FALSE_NEGATIVE, FALSE_POSITIVE, VALUE_MISMATCH, FILTER_MISMATCH)
- filter_responsible (if applicable)
- spread_type
- symbol

Look for systematic patterns: if all bull_put spreads fail the same way,
the root cause is likely in spread-type-specific logic, not a general bug.

### 2. Code Tracing
For each pattern:
- Identify the function that produces the wrong value
- Read the function source code
- Identify the exact line where the calculation diverges from expected
- Determine if the bug is in the function itself or in its inputs

### 3. Impact Assessment
- How many of the 64 configs are affected by this root cause?
- Does the fix have cascade effects on other calculations?
- Does the fix affect the MSFT anchor trades?

## Output Format (JSON)
```json
{
  "analysis_timestamp": "ISO-8601",
  "total_discrepancies_analyzed": 16,
  "root_causes": [
    {
      "id": "RC1",
      "file": "app/services/vertical_engine.py",
      "function": "calculate_net_delta",
      "line_range": "145-152",
      "issue": "Put leg delta not wrapped in abs() — raw negative delta used for net calculation",
      "pattern": "All put-containing spreads (bull_put, bear_put) have incorrect net delta",
      "affected_configs": 32,
      "affected_discrepancies": ["D1", "D4", "D7", "D12"],
      "fix_complexity": "LOW",
      "cascade_risk": "NONE — isolated calculation, no downstream dependents",
      "suggested_fix": "Line 148: change `net_delta += leg.delta` to `net_delta += abs(leg.delta) if leg.option_type == 'put' else leg.delta`",
      "regression_test": "Run MSFT anchor trade validation (OTA-284) + full 64-config matrix",
      "jira_reference": "OTA-274"
    }
  ],
  "unresolved": [
    {
      "discrepancy_ids": ["D15"],
      "reason": "Value difference within tolerance but flagged due to rounding — may be a test issue, not a code issue",
      "recommendation": "INVESTIGATE — human should review"
    }
  ]
}
```

## Rules
- Never guess at root causes — trace the actual code path
- Always identify the specific line range, not just the file
- Always assess cascade risk before recommending a fix
- If a discrepancy might be a test issue (not a code issue), flag it as unresolved
- Reference the Jira ticket that defines the correct behavior
- Regression test must always include MSFT anchor trades
