# Skill: ui-compliance-check
Version: 1.0
Purpose: Execute compliance checks against the running application for each parsed assertion.

## Inputs
- `{{assertions_json}}` — output from jira-spec-parser skill
- `{{app_url}}` — default `http://localhost:5173`
- `{{api_url}}` — default `http://localhost:8000`

## Verification Methods by Category

### VISUAL
1. Navigate to the component in the browser
2. Inspect computed CSS for the target element
3. Compare color values as normalized hex
4. Capture screenshot

### BEHAVIORAL
1. Trigger the interaction (click, input, navigation)
2. Wait for state change
3. Verify outcome matches spec
4. Test both true/false cases for conditional renders

### DATA
1. Call the API endpoint directly
2. Validate response shape against Pydantic schema
3. Test 422 response for missing required fields

### INTEGRATION
1. Verify endpoint responds (not 404/405)
2. Check provider factory routing in server logs
3. Verify SKILL.md is loaded by SkillLoader when relevant

## Output Format

```json
{
  "ticket_key": "OTA-{number}",
  "run_timestamp": "ISO 8601",
  "results": [
    {
      "assertion_id": "{ticket_key}-A{n}",
      "status": "PASS | FAIL | SKIP | ERROR",
      "expected": "what the spec says",
      "actual": "what was observed",
      "screenshot_path": "agents/qa-ux/test-results/{ticket_key}-A{n}.png or null",
      "duration_ms": 0,
      "notes": "optional"
    }
  ],
  "summary": {
    "total": 0,
    "pass": 0,
    "fail": 0,
    "skip": 0,
    "error": 0,
    "pass_rate": 0.0
  }
}
```

## Rules
- NEVER skip an assertion — mark SKIP with reason if blocked
- Mark ERROR if the check itself fails (not the assertion)
- Always capture screenshots for FAIL results
- Only call endpoints listed in `APPROVED_ENDPOINTS.md`
