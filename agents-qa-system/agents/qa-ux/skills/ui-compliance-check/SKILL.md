# UI Compliance Check
# Version: 1.0

## Purpose
Execute compliance checks against the running application for each assertion
extracted by the jira-spec-parser skill.

## Input
- {{assertions_json}}: The parsed assertions from jira-spec-parser
- {{app_url}}: The local dev server URL (default: http://localhost:5173)
- {{api_url}}: The local API URL (default: http://localhost:8000)

## Verification Methods by Category

### VISUAL assertions
- Navigate to the component's page in the running app
- Locate the target element by component name, test ID, or DOM structure
- Inspect computed CSS properties (color, background-color, font-size, width, etc.)
- For color assertions: compare as normalized hex values (lowercase, 6-digit)
- For layout assertions: measure bounding box dimensions
- Capture screenshot of the component in context
- Save screenshot to test-results/{ticket_key}/{assertion_id}.png

### BEHAVIORAL assertions
- Trigger the interaction (click, input change, navigation)
- Wait for state change (re-render, network request, route change)
- Observe the outcome and compare against the assertion
- For conditional rendering: test both the true and false cases
- For "never" assertions: verify the forbidden state cannot be reached

### DATA assertions
- Call the specified API endpoint with test data
- Validate response JSON against the Pydantic schema described in the ticket
- Check that all required fields are present and correctly typed
- For required-field assertions: send request with field omitted, expect 422
- For enum assertions: verify only valid values are accepted

### INTEGRATION assertions
- Verify endpoint exists and responds (not 404/405)
- Confirm routing goes through provider factory (check server logs)
- Verify SKILL.md is loaded by SkillLoader (check for cache hit in logs)
- Verify prompt text lives in SKILL.md, not hardcoded in Python

## Output Format (JSON)
```json
{
  "ticket_key": "OTA-289",
  "run_timestamp": "ISO-8601",
  "app_url": "http://localhost:5173",
  "api_url": "http://localhost:8000",
  "results": [
    {
      "assertion_id": "A1",
      "status": "PASS",
      "expected": "#00C896",
      "actual": "#00C896",
      "screenshot_path": "test-results/OTA-289/A1.png",
      "duration_ms": 1200,
      "notes": ""
    },
    {
      "assertion_id": "A2",
      "status": "FAIL",
      "expected": "422 response when ev_commentary missing",
      "actual": "200 response with null ev_commentary",
      "screenshot_path": null,
      "duration_ms": 340,
      "notes": "Endpoint accepts null instead of rejecting — Pydantic schema likely missing required constraint"
    }
  ],
  "summary": {
    "total": 12,
    "pass": 10,
    "fail": 1,
    "skip": 1,
    "error": 0,
    "pass_rate": 0.833
  }
}
```

## Rules
- Never skip an assertion — mark SKIP with reason if blocked
- Mark ERROR if the check itself fails (page won't load, element not found)
- Always capture screenshots for FAIL results
- Screenshots are informational for PASS results (optional)
- Duration is wall-clock time for the individual check
