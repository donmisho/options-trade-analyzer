# Fix Proposal Generator
# Version: 1.0

## Purpose
Given a failed assertion, produce a fix proposal that the Frontend Dev
Agent can implement without further clarification.

## Input
- {{assertion}}: The failed assertion object (from ui-compliance-check)
- {{component_source}}: The current source code of the affected component
- {{tokens_source}}: The current design tokens file (web/src/styles/tokens.js)
- {{ticket_description}}: The original Jira spec for context

## Analysis Steps
1. Read the failed assertion to understand expected vs actual
2. Read the component source to find where the incorrect value originates
3. Determine if the fix is:
   - TOKEN_VALUE: wrong color/size in tokens.js
   - CSS: wrong style applied in component
   - COMPONENT_LOGIC: wrong conditional rendering or state handling
   - API_CONTRACT: wrong data shape expected by component

## Output Format (JSON)
```json
{
  "ticket_key": "OTA-289",
  "assertion_id": "A1",
  "severity": "MAJOR",
  "fix_type": "CSS",
  "file_to_modify": "web/src/components/ClaudesRead.jsx",
  "description": "Verdict badge background uses wrong color token",
  "current_behavior": "Badge renders with #4CAF50 (generic green)",
  "expected_behavior": "Badge renders with #00C896 (Emerald Teal per spec)",
  "suggested_change": "Replace inline color with tokens.semantic.execute or add execute token if missing",
  "risk_level": "LOW",
  "tests_to_run": ["npm test -- --grep ClaudesRead"],
  "files_affected": ["web/src/components/ClaudesRead.jsx"],
  "cascade_notes": "No other components reference this color value"
}
```

## Risk Classification
- LOW: CSS-only change, token value change, text content change
- MEDIUM: Component logic change, conditional rendering, new prop
- HIGH: API contract change, new dependency, shared component modification

## Rules
- Every fix proposal must include the exact file to modify
- Every fix proposal must include at least one test to run
- HIGH risk proposals must include cascade_notes explaining downstream impact
- Never suggest adding new npm dependencies — escalate instead
- Always reference the Jira spec as the authority for expected behavior
