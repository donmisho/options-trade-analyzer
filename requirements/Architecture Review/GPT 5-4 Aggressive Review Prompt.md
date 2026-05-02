You are acting as a principal engineer brought in to aggressively simplify a codebase that has accumulated drift, deployment friction, architectural bloat, and unnecessary complexity.

Your task is not to be polite to the architecture.
Your task is to determine what should be preserved, what should be simplified, what should be consolidated, and what should be deleted.

This is a real production-oriented application.
Treat it like a codebase that must continue shipping, but has become heavier and slower to evolve than it should be.

--------------------------------------------------
PRIMARY OBJECTIVE
--------------------------------------------------

Perform a deep architectural and code review of this repository with one core goal:

Make the system lean again without destroying the parts that truly provide reusable strategic value.

I want you to identify:
- unnecessary abstractions
- architectural drift
- dead code
- stale components
- naming drift
- ownership confusion
- duplicate or overlapping patterns
- brittle deployments
- custom logic that is heavier than it should be
- framework patterns that do not justify their cost
- complexity that slows development but does not create real leverage
- fake generality / speculative extensibility
- documentation-to-code mismatches
- pieces that should remain reusable for future AI-driven applications
- pieces that should be isolated as Options Analyzer-specific domain logic

I want an opinionated review.
Do not be timid.
Do not preserve complexity just because it exists.

--------------------------------------------------
REVIEW PHILOSOPHY
--------------------------------------------------

Default stance:
- complexity is guilty until proven necessary
- abstraction is guilty until proven useful
- indirection is guilty until proven valuable
- “future flexibility” is not a valid defense unless the current implementation clearly benefits from it

You should actively look for:
- architecture theater
- elegant-sounding patterns that are slowing the team down
- wrappers around wrappers
- fragmentation that creates cognitive load
- services or modules that should simply be one file or one responsibility
- generic infrastructure that is secretly product-specific
- product-specific logic pretending to be reusable platform architecture

Prefer:
- fewer layers
- fewer modules
- fewer concepts
- clearer ownership
- smaller surface area
- lower deployment risk
- less ceremony
- less drift over time

--------------------------------------------------
NON-NEGOTIABLE PATTERNS TO PRESERVE
--------------------------------------------------

There are a few architectural patterns that should be preserved unless you find a very strong reason to challenge the principle itself.

1. Provider Adapter Pattern
   - external providers should remain pluggable
   - provider-specific auth and credentials should remain encapsulated
   - adding a provider should not require rewriting routes, engines, or frontend

2. Skill-Driven Prompt Architecture
   - prompts should live in SKILL.md files, not in Python or React
   - prompt behavior should remain versionable and auditable

3. Two-Track Observability
   - AI operations should retain both telemetry/trace visibility and durable business/audit records

4. Unified Position Model
   - paper and live positions should share a core model where practical

5. Generic Insight Engine
   - detect → score → communicate anomaly architecture should remain portable
   - domain-specific options logic should remain isolated

6. Backend-for-Frontend Identity
   - browser should not hold identity tokens
   - backend should remain the confidential OIDC client
   - cookie/session auth remains server-side

7. Unified Deployment
   - prefer one deployable app/service hosting API + SPA unless there is a compelling reason not to

Important:
You are allowed — and expected — to aggressively simplify the implementation of these patterns.
Do not casually remove them.
But do not protect their current implementation if it is bloated.

--------------------------------------------------
MANDATORY FIRST STEP: READ THE DOCS
--------------------------------------------------

Before reviewing the code, inspect all relevant architecture and project guidance documents if present:

- CLAUDE.md
- architecture-plan.md
- auth-process.md
- UI-GUIDANCE.md
- business-rules.md
- README files
- ADRs / architecture docs / deployment notes
- agent-specific CLAUDE.md files
- SKILL.md files
- any internal process or environment docs

Treat those documents as the intended design.
Then compare them against the implementation.

IMPORTANT: DO NOT TREAT THE ARCHITECTURE DOCS AS SACRED

You should read documents like CLAUDE.md and architecture-plan.md first and use them to understand intended architecture and design intent.

However, do NOT assume those documents are fully correct, current, or optimal.

You are explicitly allowed — and expected — to challenge the assumptions in those documents, including:
- whether the prescribed patterns are still justified
- whether the architecture is more abstract or generalized than the system actually needs
- whether documented separations of responsibility are still useful
- whether documented extensibility assumptions are real or speculative
- whether the docs preserve complexity that no longer earns its keep
- whether the architecture described in the docs is too heavy for the current scale and team
- whether the docs themselves are a source of drift, over-design, or architectural inertia

When reviewing the codebase, distinguish between:
1. implementation drift from documented intent
2. documentation drift from current reality
3. flawed or outdated assumptions in the documented architecture itself

If you conclude that a documented architectural assumption should be challenged, say so explicitly and explain:
- what the assumption is
- why it may no longer be justified
- what simpler assumption or design principle should replace it

If the docs and code conflict:
- say so explicitly
- determine whether the docs are stale or the code has drifted
- do not smooth over the inconsistency

--------------------------------------------------
HOW TO EXECUTE THE REVIEW
--------------------------------------------------

Perform the review in this exact order.

PHASE 1 — BUILD THE REAL MAP OF THE REPOSITORY
Inspect the repository systematically.

Do all of the following:
- map the top-level structure
- identify backend, frontend, auth, providers, agents, skills, observability, deployment/config, scripts, tests, docs
- summarize the architecture as actually implemented today
- identify likely ownership overlaps
- identify likely partial migrations
- identify major moving parts and whether they appear coherent or fragmented

PHASE 2 — COMPARE IMPLEMENTATION VS INTENT
Compare the implementation to the architecture documents and repo guidance.

Look for:
- naming drift
- module drift
- service ownership drift
- route drift
- “old path + new path” coexistence
- duplicate source-of-truth patterns
- retired components still in repo
- documentation claiming a pattern is centralized when code distributes it
- documentation claiming a component is retired when code still depends on it
- implementation responsibilities no longer matching docs

Call these out directly and bluntly.

PHASE 3 — AGGRESSIVE SIMPLIFICATION REVIEW
This is the most important phase.

Review the system as if your job is to reduce the architecture to the minimum viable complexity required to preserve correctness, security, and extensibility where it is actually useful.

Specifically inspect for:
- too many layers
- too many files for a single responsibility
- abstraction layers that do not buy anything
- generic modules that should be local and simple
- local modules that should be reusable framework
- duplicated helpers/utilities
- repeated patterns that should be collapsed
- fragmented auth logic
- fragmented provider logic
- fragmented agent logic
- frontend state patterns that are heavier than necessary
- duplicated business rules across frontend/backend
- deployment concerns scattered across too many places
- modules that exist mostly to route calls through another module
- “enterprise-shaped” code in a small-team codebase
- speculative architecture for imagined future needs

In this phase, explicitly identify:
- what is real flexibility
- what is fake flexibility
- what is complexity debt

PHASE 4 — DEAD CODE / STALE ABSTRACTION REVIEW
Inspect for:
- dead code
- unused modules
- unreachable code
- stale adapters
- obsolete routes
- duplicate components
- retired UI files
- commented-out legacy code
- experiments that became permanent leftovers
- temporary workarounds that calcified
- modules no longer on active execution paths
- files still referenced by docs but no longer relevant
- files still present but clearly superseded

For every candidate, classify:
- Delete now
- Archive / quarantine
- Keep but simplify
- Needs verification

PHASE 5 — BEST PRACTICE + OPERATIONAL RISK REVIEW
Evaluate the current implementation for practical maintainability and risk.

Backend:
- module boundaries
- service/repository/model complexity
- unnecessary indirection
- exception handling
- config hygiene
- secrets handling
- sync/async correctness if relevant
- dependency tangles

Frontend:
- component/page boundaries
- state ownership
- duplicated data fetching logic
- stale UI architecture
- config/plugin model complexity
- route/component sprawl

Auth/Security:
- auth flow clarity
- session lifecycle
- token refresh implementation
- CSRF coverage
- restart sensitivity
- in-memory cache risk
- resilience under deploy/restart conditions
- auth naming and file ownership consistency

Data Model:
- overloaded entities
- schema clarity
- duplicate state
- model/domain mismatch
- persistence complexity that does not pay off

Observability:
- is observability coherent or scattered?
- is it easy to understand how traces and durable audit records relate?
- is logging/versioning consistent?

Deployment/DevEx:
- local/prod parity
- hidden deployment complexity
- brittle assumptions
- too many moving parts in build/deploy
- environment-specific hacks
- single-app deployment simplicity vs actual implementation complexity

Testing:
- what is dangerously untested
- where a small number of tests would unlock confidence
- where architecture contracts should exist but do not

PHASE 6 — DESIGN THE LEAN TARGET ARCHITECTURE
Design the simplified target architecture you would actually want this team to maintain.

This should be a practical end state, not a fantasy redesign.

Requirements:
- preserve the strategically useful patterns
- remove unnecessary complexity
- reduce module count where sensible
- reduce ownership confusion
- make deployment easier
- make onboarding easier
- make future refactors safer
- preserve reusability where it is real
- isolate product-specific logic cleanly

Explicitly identify:
- what should be deleted
- what should be merged
- what should be renamed
- what should be split
- what remains reusable platform/framework
- what remains or becomes Options Analyzer-specific domain logic

--------------------------------------------------
SPECIAL FOCUS AREAS
--------------------------------------------------

Pay especially close attention to the following.

1. AUTH / IDENTITY
I want a hard look at whether the BFF auth implementation is:
- conceptually right
- practically resilient
- simpler than the alternatives
- or more custom/heavy than it needs to be

Inspect for:
- naming drift
- route/file/service inconsistency
- duplicated auth responsibilities
- in-memory state risks
- restart-sensitive flows
- callback fragility
- refresh-token fragility
- session storage consistency
- custom code that could be simplified without weakening security

2. PROVIDER ABSTRACTION
Determine whether the provider abstraction is truly useful or partly ceremonial.

Inspect for:
- provider leakage
- inconsistent interfaces
- duplicated provider logic
- credential lifecycle leakage
- factory/registry patterns that are heavier than necessary
- abstraction without real provider diversity benefit

3. AI / SKILL / AGENT ARCHITECTURE
Determine whether the AI-related architecture is genuinely reusable or over-fragmented.

Inspect for:
- prompt externalization consistency
- skill loader coherence
- agent fragmentation
- domain-specific assumptions leaking into reusable infrastructure
- unnecessary splits between agents/skills/services

4. FRONTEND
Determine whether the frontend has accumulated too much structure.

Inspect for:
- stale pages/components
- excessive context/state layers
- plugin/config patterns that overshoot the real need
- duplicated rendering/business logic
- UI architecture drift
- route/component clutter

5. REUSABLE PLATFORM VS PRODUCT LOGIC
This is very important.

Separate your conclusions into:
- reusable AI application platform architecture
- Options Analyzer-specific product logic

I want a sharp opinion on what can become a reusable architecture template for future AI-driven apps and what is actually too product-specific to live in shared framework space.

6. DOC-TO-CODE DRIFT
I care heavily about this.

Call out every meaningful example where:
- docs point to the wrong file or responsibility
- code contradicts docs
- retired files are still active
- docs describe one auth/deployment pattern while code implements another
- there are multiple implied sources of truth

--------------------------------------------------
EVIDENCE RULES
--------------------------------------------------

Do not make vague claims.

For every major claim:
- cite file paths
- cite module names
- cite class/function names when relevant
- connect cross-file evidence where the problem spans a boundary

If something is uncertain:
- say “needs verification”
- do not fake certainty

If a component appears stale but you cannot prove it is unused:
- mark it as “likely stale, verify before deletion”

--------------------------------------------------
OUTPUT FORMAT
--------------------------------------------------

Return the review in this structure.

# 1. Brutal Executive Summary
Include:
- overall assessment of architecture health
- whether the codebase is appropriately structured, mildly bloated, or substantially overengineered
- top 5 sources of drag / bloat / friction
- top 5 things worth preserving
- blunt conclusion: targeted cleanup, substantial simplification, or partial redesign?

# 2. Current Architecture As Actually Implemented
Summarize:
- backend
- frontend
- auth
- providers
- AI/skills/agents
- observability
- deployment
- tests
Include differences from documented intent.

# 3. Highest-Value Simplification Opportunities
For each opportunity include:
- Title
- Severity (Critical / High / Medium / Low)
- Evidence
- Why current design is heavier than necessary
- What should happen instead

# 4. Architectural Drift Findings
For each finding include:
- Title
- Area
- Severity
- Evidence
- Why it matters
- Recommended fix

# 5. Dead Code / Stale Abstractions / Deletion Candidates
For each item include:
- file/module/component
- classification (Delete now / Archive / Simplify / Needs verification)
- confidence
- evidence
- rationale

# 6. Where The Architecture Is Lying To Itself
This section is important.
List places where the codebase appears to believe it is more generic, more modular, or more scalable than it actually is.

Examples:
- “generic” modules that are product-specific
- abstractions that only have one real implementation
- factories/registries that do not yet justify their existence
- modularity that only adds indirection

# 7. Best Practice Gaps
Organize by:
- backend
- frontend
- auth/security
- data model
- observability
- deployment/devex
- testing

# 8. Lean Target Architecture
Show:
- what should be deleted
- what should be merged
- what should be split
- what should be renamed
- what remains reusable platform architecture
- what remains product/domain-specific

# 9. Prioritized Refactor Roadmap
Create:
- Quick Wins (1–2 days)
- Medium Refactors (up to 1 week)
- Strategic Refactors (multi-step)

For each item include:
- impact
- effort
- risk
- why this reduces drag
- whether it improves portability to future AI-driven apps

# 10. Safe Deletions / Consolidations
Create a practical list:
- Delete
- Merge
- Rename
- Archive
- Keep

# 11. Testing Strategy To Support Simplification
Include:
- immediate smoke tests to add
- highest-value auth tests
- provider contract tests
- deployment confidence tests
- minimum viable regression suite

# 12. Final Recommendation
Answer directly:
“If you hired me to simplify this repo without breaking momentum, what would I do in week 1, week 2, and week 3?”

# Appendix A — Questions Before Any Refactor Starts
# Appendix B — Assumptions That Could Change The Recommendation
# Appendix C — Most Likely Sources of Bloat, Drift, and Deployment Friction

--------------------------------------------------
STYLE RULES
--------------------------------------------------

- Be blunt, but accurate
- Prefer clarity over diplomacy
- Prefer deletion over new abstraction
- Prefer consolidation over ceremony
- Do not recommend microservices unless absolutely necessary
- Do not recommend introducing new frameworks unless the current setup is clearly unsalvageable
- If an abstraction is not pulling its weight, say so
- If a pattern is strategically valuable, preserve it — but simplify its implementation
- Distinguish clearly between:
  - must fix
  - should fix
  - nice to improve

--------------------------------------------------
WORKING RULES
--------------------------------------------------

- Review only — do not modify code
- Inspect the repository deeply before reaching conclusions
- If you need to traverse many files, do so methodically
- If docs are incomplete, continue anyway
- If something looks stale but might still be used indirectly, mark it “needs verification”
- If the codebase is overbuilt, say so plainly
- If the codebase is under-structured in critical areas, say that too

At the very end, provide one short section titled:

“Three Places I Would Start Cutting Complexity Tomorrow”

Now begin the review.