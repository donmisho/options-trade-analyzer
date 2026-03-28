# Skill: jira-spec-parser
Version: 1.0
Purpose: Parse a Jira ticket description and extract every testable assertion.

## Inputs
- `{{ticket_key}}` — e.g. OTA-274
- `{{ticket_summary}}` — ticket title
- `{{ticket_description}}` — full description text (ADF already extracted to plain text)

## Instructions

Extract every statement that can be verified by observing the running application.

### Categories
- **VISUAL** — color, size, layout, spacing, typography
- **BEHAVIORAL** — click handler, navigation, state change, conditional render
- **DATA** — API response shape, field presence, Pydantic schema
- **INTEGRATION** — provider factory routing, SKILL.md usage, endpoint path

### Extraction Rules
- Every color hex code → VISUAL assertion
- Every Pydantic field name → DATA assertion
- Every endpoint path → INTEGRATION assertion
- Every "never"/"always" statement → BEHAVIORAL assertion
- Every PascalCase component name → VISUAL existence assertion
- Ambiguous statements → mark `verifiable: false` with reason

## Output Format

```json
{
  "ticket_key": "OTA-{number}",
  "assertions": [
    {
      "id": "{ticket_key}-A{n}",
      "category": "VISUAL | BEHAVIORAL | DATA | INTEGRATION",
      "statement": "exact text from spec",
      "component": "ComponentName or null",
      "verifiable": true,
      "check_method": "brief description of how to verify"
    }
  ],
  "stats": {
    "total": 0,
    "visual": 0,
    "behavioral": 0,
    "data": 0,
    "integration": 0,
    "unverifiable": 0
  }
}
```
