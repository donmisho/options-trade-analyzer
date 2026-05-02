---
mode: 'agent'
description: 'Perform a full repository architecture review focused on simplification, drift, dead code, and best practices'
---

## Role
You are a principal engineer conducting a repository-wide architecture and maintainability review.

Your job is to review the current codebase and identify how to make it leaner, cleaner, easier to deploy, easier to maintain, and more reusable for:
1. the Options Analyzer application, and
2. similar AI-driven applications in the future.

Do not make code changes yet.
Do not produce patches yet.
First produce a structured review only.

## Review Goals
Analyze the repository for:
- architecture drift
- code bloat
- dead code
- stale abstractions
- duplicated logic
- overly complex module boundaries
- deployment friction
- poor ownership boundaries
- maintainability risks
- testability gaps
- security/auth design issues
- frontend/backend over-engineering
- domain logic that should be isolated from reusable platform architecture

## Preserve These Architectural Principles Unless There Is A Strong Reason Not To
- Provider Adapter Pattern
- Skill-Driven Prompt Architecture
- Two-Track Observability
- Unified Position Model
- Generic Insight Engine
- Backend-for-Frontend Identity
- Unified Deployment

## Mandatory Context
Before reviewing implementation details, inspect and use these documents as the intended architecture baseline if they exist in the repo:
- CLAUDE.md
- architecture-plan.md
- auth-process.md
- UI-GUIDANCE.md
- business-rules.md
- agent-specific CLAUDE.md files
- SKILL.md files

Treat those docs as architectural intent, then compare actual implementation against them.

## How To Review
Perform the review in this order:

### Phase 1 — Repository Inventory
- Build a mental model of the repository structure
- Identify backend, frontend, auth, providers, agents, skills, shared utilities, deployment/config assets, tests, and scripts
- Summarize the architecture as actually implemented today

### Phase 2 — Drift Analysis
Identify where implementation differs from documented intent:
- naming drift
- route drift
- service ownership drift
- old and new patterns coexisting
- retired components still present
- documentation claiming one thing while code does another

### Phase 3 — Lean Architecture Review
Find places where the architecture is heavier than necessary:
- wrappers around wrappers
- abstractions that no longer buy flexibility
- overly fragmented services/modules
- duplicate helper layers
- duplicate state/business rules
- provider-specific leakage into generic layers
- UI/state management complexity that could be collapsed

### Phase 4 — Dead Code / Tech Debt Review
Inspect for:
- unused modules
- unreachable code
- commented-out legacy code
- stale components
- obsolete routes
- outdated adapters
- temporary workarounds that became permanent
- files that appear retired but still remain in the repo

### Phase 5 — Best Practices Review
Evaluate:
- backend boundaries
- frontend composition and state boundaries
- auth/session security implementation
- config/settings hygiene
- secrets handling
- API consistency
- data model cohesion
- observability consistency
- deployment clarity
- local-vs-prod parity
- test strategy and confidence gaps

### Phase 6 — Lean Target Architecture
Recommend a simpler target architecture that:
- keeps the essential patterns
- reduces moving parts
- lowers deployment complexity
- lowers cognitive load
- preserves portability for future AI-driven apps

## Specific Areas To Inspect Carefully

### Auth / Identity
Review whether the BFF auth implementation is as simple as it should be.
Check for:
- naming drift across auth files/routes/services
- session lifecycle complexity
- token refresh complexity
- CSRF implementation clarity
- restart sensitivity
- in-memory cache risks
- custom auth logic that may be heavier than necessary

### Provider Architecture
Check whether providers are truly isolated behind interfaces and whether provider-specific assumptions leak into routes, engines, or frontend code.

### AI / Skills / Agents
Check whether prompts are consistently externalized, whether skills and agents are cleanly separated, and whether reusable AI app patterns are truly generic rather than accidentally tied to options/trading assumptions.

### Frontend Architecture
Check whether React pages/components/context/state are appropriately scoped, whether retired UI patterns still remain, and whether the strategy plugin/config model is right-sized.

### Domain / Data Model
Check whether models and tables reflect clear ownership, whether any entity has too many responsibilities, and whether the model is overly coupled to options-trading assumptions.

### Observability / Governance
Check whether telemetry, audit records, prompt versions, and run records are cohesive and consistently applied.

### Deployment / DevEx
Check whether the unified deployment approach is implemented as simply as possible, whether local dev and production are unnecessarily divergent, and whether hidden deployment complexity exists.

### Testing
Check where a small number of targeted automated tests would create the biggest confidence gains.

## Output Format
Return the review in this structure:

# 1. Executive Summary
- overall architectural health
- top 5 issues making the codebase heavier than necessary
- top 5 things worth preserving

# 2. Current Architecture As Implemented
- backend
- frontend
- auth
- providers
- AI/skills/agents
- observability
- deployment
- note differences from documented architecture

# 3. Architectural Drift Findings
For each finding include:
- Title
- Area
- Severity (Critical / High / Medium / Low)
- Evidence
- Why it matters
- Recommended fix

# 4. Dead Code / Tech Debt Inventory
For each item include:
- file/module/component
- confidence level
- why it appears stale
- safe to delete now? (Yes / No / Needs verification)
- recommended action

# 5. Best Practice Gaps
Organize by:
- backend
- frontend
- auth/security
- data model
- deployment/devex
- observability
- testing

# 6. Lean Target Architecture
Show:
- what should be merged
- what should be split
- what should be deleted
- what stays reusable
- what becomes Options Analyzer-specific domain logic

# 7. Prioritized Refactor Roadmap
Create:
- Quick Wins (1–2 days)
- Medium Refactors (up to 1 week)
- Strategic Refactors (multi-step)

For each item include:
- impact
- effort
- risk
- why it improves simplicity
- whether it improves future portability

# 8. Safe Deletions / Consolidations
List:
- delete
- merge
- rename
- archive
- keep

# 9. Testing Recommendations
- minimal high-value tests to add first
- smoke tests that would protect the most risk
- architectural contract tests worth adding

# 10. Final Recommendation
Answer directly:
“If I were to simplify this repo aggressively but safely, what would I do first, second, and third?”

## Review Style
- Be direct
- Be concrete
- Prefer simplification over elegance theater
- Do not suggest microservices unless absolutely necessary
- Do not suggest new frameworks without strong justification
- If an abstraction is not buying real flexibility, say so
- If a pattern is valuable and reusable, preserve it

## Final Appendix
Add:
- Questions I would ask before refactoring
- Assumptions that could change the recommendations
