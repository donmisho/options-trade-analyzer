# Skill: fix-proposal
Version: 1.0
Purpose: Given a failed assertion, produce a fix proposal for the Frontend Dev Agent.

## Inputs
- `{{assertion}}` — the failed assertion object from jira-spec-parser output
- `{{component_source}}` — source code of the relevant component
- `{{tokens_source}}` — contents of `web/src/styles/tokens.js`
- `{{ticket_description}}` — original Jira ticket description

## Instructions

Analyze the failed assertion against the component source and tokens. Identify the minimal change needed to bring the component into compliance.

### Risk Classification
- **LOW** — CSS-only change or token value update
- **MEDIUM** — Component logic change or conditional rendering
- **HIGH** — API contract change, new dependency, or shared component modification

HIGH risk proposals always require escalation before the Frontend Dev Agent acts.

## Output Format

```json
{
  "ticket_key": "OTA-{number}",
  "assertion_id": "{ticket_key}-A{n}",
  "severity": "BLOCKER | MAJOR | MINOR | COSMETIC",
  "fix_type": "CSS | COMPONENT_LOGIC | API_CONTRACT | TOKEN_VALUE",
  "file_to_modify": "relative path from repo root",
  "description": "one-sentence summary of the fix",
  "current_behavior": "what the component currently does",
  "expected_behavior": "what it should do per spec",
  "suggested_change": "specific code change or diff description",
  "risk_level": "LOW | MEDIUM | HIGH",
  "tests_to_run": ["npm test", "npm run lint"],
  "files_affected": ["list of files that may be impacted"],
  "cascade_notes": "any downstream effects to be aware of"
}
```
