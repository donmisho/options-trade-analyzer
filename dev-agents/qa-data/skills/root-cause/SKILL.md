# Skill: root-cause
Version: 1.0
Purpose: Trace data discrepancies to specific functions in the codebase.

## Inputs
- `{{discrepancies}}` — array of discrepancy objects from data-validation output
- `{{source_files}}` — key files to examine:
  - `app/services/vertical_engine.py`
  - `app/services/filter_engine.py`
  - `app/services/greeks_calculator.py`
  - `app/services/pnl_calculator.py`
  - `app/providers/`

## Steps

### 1. Group Discrepancies
Group by `type` and `filter_responsible` to identify patterns.

### 2. Trace Code Path
For each group:
- Identify the function where the calculation diverges from expected behavior
- Find the specific line range
- Do not guess — trace the actual code path

### 3. Assess Impact
- How many of the 64 configs are affected
- Cascade effects on other calculations
- Whether any MSFT anchor trades are impacted

## Output Format

```json
{
  "root_causes": [
    {
      "id": "RC-{n}",
      "file": "relative path from repo root",
      "function": "function_name",
      "line_range": "e.g. 45-72",
      "issue": "description of the bug",
      "pattern": "e.g. abs() not applied to put delta",
      "affected_configs": 0,
      "fix_complexity": "LOW | MEDIUM | HIGH",
      "cascade_risk": "description of downstream effects",
      "suggested_fix": "specific code change description",
      "regression_test": "test that must pass after fix (always include MSFT anchor trades)",
      "jira_reference": "OTA-{number}"
    }
  ],
  "unresolved": [
    {
      "discrepancy_ids": ["list"],
      "reason": "why root cause cannot be determined",
      "next_steps": "what additional investigation is needed"
    }
  ]
}
```

## Rules
- NEVER guess at root causes — trace the actual code path
- Always identify a specific line range
- Always assess cascade risk
- Flag potential test data issues as unresolved rather than assigning blame
- Regression test must always include MSFT anchor trades (MSFT-10-bull_call, MSFT-20-bear_put, MSFT-25-bull_put)
