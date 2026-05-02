# Repository Review Instructions

When reviewing this repository, optimize for simplicity, maintainability, and architectural clarity.

## Core Review Goals
- Identify architecture drift, dead code, stale abstractions, duplicate logic, and unnecessary complexity.
- Prefer deleting, consolidating, or simplifying over introducing new frameworks or layers.
- Preserve flexibility only where it is clearly valuable.
- Distinguish reusable platform patterns from Options Analyzer-specific domain logic.

## Architectural Principles To Preserve
- Provider Adapter Pattern: external providers should remain pluggable and provider-specific auth/credential handling should stay inside adapters.
- Skill-Driven Prompt Architecture: prompts belong in SKILL.md files, not hardcoded in Python or React.
- Two-Track Observability: preserve both telemetry/trace visibility and durable business/audit records.
- Unified Position Model: paper and live positions should share a core model where practical.
- Generic Insight Engine: keep reusable detect → score → communicate patterns generic; isolate options-specific behavior.
- Backend-for-Frontend Identity: browser should not hold identity tokens; backend remains confidential client; cookie/session auth should stay server-centric.
- Unified Deployment: prefer one app/service hosting API + SPA unless a strong reason exists to change.

## What To Look For
- Duplicate patterns or “old path + new path” coexistence
- Retired components still present
- Modules that are too generic and should be local/simple
- Modules that are too app-specific and should be isolated from reusable framework code
- Over-abstracted provider/agent/service patterns
- Auth naming drift, route drift, or service ownership drift
- Frontend state/context complexity that no longer pays for itself
- Deployment complexity hidden in scripts, config, or environment-specific branches
- Missing tests at key architectural seams

## Review Style
- Be concrete and evidence-based.
- Cite files/modules/functions as evidence.
- Prefer practical recommendations over theoretical ones.
- Clearly label findings as:
  - Must fix
  - Should fix
  - Nice to improve
- If docs and code conflict, explicitly say whether docs or code should become the source of truth.

## Output Preference
When asked for a review, return:
1. Executive summary
2. Current architecture as implemented
3. Drift findings
4. Dead code / tech debt inventory
5. Best-practice gaps
6. Lean target architecture
7. Prioritized refactor roadmap
8. Safe deletions / consolidations
9. Testing recommendations
10. Final “first / second / third” recommendation