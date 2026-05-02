# Jira Spec Parser
# Version: 1.0

## Purpose
Parse a Jira ticket description and extract every testable assertion.

## Input
- {{ticket_key}}: The Jira issue key (e.g., OTA-289)
- {{ticket_summary}}: The issue summary line
- {{ticket_description}}: The full description text

## Instructions
Read the ticket description carefully. Extract every statement that can
be verified by observing the running application. Categorize each as:

- VISUAL: color, size, layout, spacing, typography
- BEHAVIORAL: click handler, navigation, state change, conditional render
- DATA: API response shape, field presence, Pydantic schema compliance
- INTEGRATION: routing through provider factory, SKILL.md usage, endpoint path

## Extraction Rules
- Every color hex code in the description becomes a VISUAL assertion
- Every Pydantic field name becomes a DATA assertion
- Every endpoint path (e.g., /api/v1/...) becomes an INTEGRATION assertion
- Every "never" or "always" statement becomes a BEHAVIORAL assertion
- Every component name (PascalCase) becomes a VISUAL assertion for existence
- Every "sized to content" / "full-width" / layout directive becomes VISUAL
- If a statement is ambiguous, mark verifiable: false and note why

## Output Format (JSON)
```json
{
  "ticket_key": "{{ticket_key}}",
  "ticket_summary": "{{ticket_summary}}",
  "parsed_at": "ISO-8601",
  "assertions": [
    {
      "id": "A1",
      "category": "VISUAL",
      "statement": "EXECUTE verdict badge uses color #00C896",
      "component": "ClaudesRead",
      "verifiable": true,
      "check_method": "inspect computed style of verdict badge element"
    },
    {
      "id": "A2",
      "category": "DATA",
      "statement": "ev_commentary field is required in response — missing returns 422",
      "component": "/evaluate/structured endpoint",
      "verifiable": true,
      "check_method": "send request with ev_commentary omitted, expect 422"
    }
  ],
  "stats": {
    "total": 12,
    "visual": 4,
    "behavioral": 3,
    "data": 3,
    "integration": 2,
    "unverifiable": 0
  }
}
```
