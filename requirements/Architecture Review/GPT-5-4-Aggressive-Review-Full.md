# Options Analyzer — Architecture Review Session
**Date:** 2026-04-30
**Prompt:** GPT 5-4 Aggressive Review Prompt
**Reviewer:** Claude Sonnet 4.6 (Claude Code)

---

# PROMPT

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
- "future flexibility" is not a valid defense unless the current implementation clearly benefits from it

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
- "old path + new path" coexistence
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
- "enterprise-shaped" code in a small-team codebase
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
- say "needs verification"
- do not fake certainty

If a component appears stale but you cannot prove it is unused:
- mark it as "likely stale, verify before deletion"

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
- "generic" modules that are product-specific
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
"If you hired me to simplify this repo without breaking momentum, what would I do in week 1, week 2, and week 3?"

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
- If something looks stale but might still be used indirectly, mark it "needs verification"
- If the codebase is overbuilt, say so plainly
- If the codebase is under-structured in critical areas, say that too

At the very end, provide one short section titled:

"Three Places I Would Start Cutting Complexity Tomorrow"

Now begin the review.

---

# REVIEW OUTPUT

---

# Options Analyzer — Aggressive Architecture Review

---

## 1. Brutal Executive Summary

**Overall assessment:** The codebase is **mildly-to-moderately overengineered** in some critical areas and shows clear signs of **partial migrations that were never completed**. The most damaging pattern is the existence of two parallel AI subsystems that do overlapping jobs under nearly identical names. Auth has the same problem — two coexisting auth flows. The core domain logic (scoring, position tracking, BFF identity) is genuinely well-structured. The provider adapter pattern is real and pulling its weight. Deployment infrastructure is clean.

**Top 5 sources of drag:**
1. **Dual AI stack** — `app/providers/ai/` (old, SDK-based, prose verdicts) and `app/ai/` (new, httpx-based, structured JSON verdicts) coexist with their own `FoundryAdapter`, `TradeVerdict`, and `prompts.py`. Both are live in production.
2. **Dual auth flows** — Legacy JWT/MSAL bridge (`entra_auth_routes.py`) and new BFF OIDC redirect flow (`identity_routes.py`) both registered, both serving `/auth/me`, with a comment in `main.py` explaining registration order to avoid conflict.
3. **18+ routers + global init pattern** — `main.py` imports and calls `init_*()` on 14+ route modules using module-level globals. Startup is a wall of imperative initialization; failure modes are invisible until runtime.
4. **`main.py` does OS-level package installation** — `_install_odbc_if_needed()` is 60+ lines of subprocess shell logic running inside the Python application entry point.
5. **Dead files never cleaned up** — Tradier adapter, `SchwabToken` model, archived frontend pages, `deviation_detector.py` (not imported), `Header.jsx` (retired), `FavoritesPage.css` (orphaned), scattered scratch/prototype/jira files.

**Top 5 things worth preserving:**
1. **BFF session management** — `auth/session_manager.py` is well-designed: Fernet encryption, atomic conditional updates, fire-and-forget token refresh, PKCE + signed state, CSRF middleware.
2. **Provider adapter pattern** — `providers/base.py` + `providers/factory.py` are clean. The abstraction justifies itself — Schwab and a future broker are meaningfully different.
3. **Skill loader** — `app/skills/skill_loader.py` with `{{variable}}` templates and `{{#if}}` conditionals is concise and correct. The SKILL.md architecture is sound.
4. **Hard gates sub-package** — `app/analysis/hard_gates/` is well-scoped. EarningsInWindowGate, NegativeEVGate are simple, tested, correctly registered.
5. **OpenTelemetry + durable audit log** — `agents/telemetry.py` + `agent_run_log` table is the right two-track observability pattern.

**Blunt conclusion: targeted cleanup + one moderate simplification (merge the AI stacks).**
This is not a redesign situation. The architecture is directionally correct. The problems are leftovers from migrations that were half-completed and never fully cleaned up.

---

## 2. Current Architecture As Actually Implemented

### Backend
- FastAPI, lifespan-based startup, 18 registered routers
- `app/main.py` is the orchestration file — 451 lines, does: ODBC installation, DB init, secrets, auth (both systems), 2 AI adapters, hard gates, telemetry, scheduler, health routes
- `app/core/config.py` — Pydantic Settings, clean
- `app/core/secrets.py` — Key Vault with `.env` fallback, clean
- `app/models/database.py` — 928 lines, 20+ ORM models, SQLAlchemy 2.x
- `app/models/session.py` — async engine, `get_db()`, `init_db()`
- `app/analysis/` — scoring engines (verticals, long calls, directional, B-S, strategy scorer, hard gates, health grade)
- `app/providers/` — market data providers (Schwab, Tradier), context sources (Finnhub), factory
- **`app/providers/ai/`** — OLD AI stack: `AIProvider` base, `AnthropicAdapter`, `FoundryAdapter` (SDK), text-verdict prompts
- **`app/ai/`** — NEW AI stack: `FoundryEvalAdapter` (httpx), Pydantic `TradeVerdict` schemas, JSON-structured prompts
- `app/agents/` — position monitor, insight engine, context store, telemetry, deviation_detector
- `app/skills/` — SKILL.md files + skill_loader
- `app/auth/` — `service.py` (JWT/TOTP/trade challenge), `session_manager.py` (BFF), `dependencies.py` (both), `providers.py` (OIDC provider config), `client_assertion.py` (certificate JWT)
- `app/api/` — 18 route files including duplicates and dead-weight routes

### Frontend
- React + Vite, React Router v6 nested layout
- `web/src/App.jsx` — clean routing, 8+ `Navigate` redirects from retired routes
- `web/src/context/AppContext.jsx` — watchlist, favorites, activeSymbol (localStorage)
- `web/src/auth/msalConfig.js` — MSAL config still present despite BFF migration
- Pages: Dashboard, Trades, SecurityStrategies, Strategy, Positions, BrokerConnect — active
- Pages in `_archive/`: Analysis, LongCallsPage, VerticalsPage — dead but present
- Components with no active parent: `Header.jsx`/`Header.css` (retired per CLAUDE.md)
- `FavoritesPage.css`, `VerticalsPage.css` — orphaned CSS for redirected-away pages

### Auth
**Dual system coexisting:**
1. `identity_routes.py` — new BFF OIDC redirect (PKCE + signed state + httponly cookie + server-side session)
2. `entra_auth_routes.py` — old MSAL bridge (validates Entra `id_token`, issues our JWT)
3. Both registered with `/api/v1` prefix; both declare `GET /auth/me`; `identity_router` must be first
4. `dependencies.py` has TWO near-identical auth dependency functions: `get_current_user` and `get_session_user`

### Providers
- Schwab: active, OAuth-based, `SchwabTokenManager` + Key Vault token storage
- Tradier: adapter file exists (`providers/tradier.py`), **not registered in `PROVIDER_REGISTRY`**, effectively dead
- AI providers: TWO parallel stacks (see above)
- `PROVIDER_REGISTRY` and `CONTEXT_SOURCE_REGISTRY` are module-level mutable dicts

### AI/Skills/Agents
- `SkillLoader` in `app/skills/skill_loader.py` — good
- `claude-trade-agent` SKILL.md: used by `agent_routes.py` (triage/deep-dive/followup) — good
- `evaluation_routes.py`: uses `FoundryEvalAdapter` from `app/ai/` with inline JSON prompts from `app/ai/prompts.py` — **violates "prompts in SKILL.md" rule**
- `position-monitor` SKILL.md used by `position_monitor.py` — good
- `deviation_detector.py` — present but not imported anywhere (not in `__pycache__`)
- `app/ai/message_builder.py` — not visible in any import chain; likely dead

### Observability
- `app/agents/telemetry.py` — `invoke_with_tracing()` context manager sends spans to Application Insights
- `agent_run_log` — permanent SQL audit table, every AI call
- These two are properly connected via `otel_trace_id`
- Coherent and well-designed

### Deployment
- `build-on-push.yml` → artifact only (no deploy)
- `deploy-to-dev.yml` → manual, confirmed by `confirm_deploy=DEPLOY-DEV`, smoke test
- `deploy-to-prod.yml` → manual, confirmed by `confirm_deploy=DEPLOY`
- `rollback-prod.yml` → manual, previous `build_run_id`
- Backend: Azure App Service; Frontend: Azure Static Web Apps (separate deploy)
- **Backend serves the static frontend in production** (SPA fallback at bottom of `main.py`). Azure Static Web Apps also deploys the same frontend separately. This is confusing — two deploy paths for the frontend.

### Tests
- `tests/test_earnings_gate.py`, `test_negative_ev_gate.py`, `test_hard_gates.py`, `test_ai_schemas.py`, `test_amzn_regression.py` — all analysis-layer tests
- Zero auth tests, zero provider contract tests, zero route tests
- `conftest.py` exists but likely minimal

---

## 3. Highest-Value Simplification Opportunities

### 3.1 — Merge the Two AI Stacks
**Severity: Critical**

**Evidence:**
- `app/providers/ai/foundry_adapter.py` (L41): `class FoundryAdapter(AIProvider)` — SDK-based, prose output
- `app/ai/foundry_adapter.py` (L83): `class FoundryEvalAdapter` — httpx-based, JSON structured output
- Both instantiated in `main.py` lines 229–263 under names `ai_provider` and `eval_adapter`
- `app/providers/ai/prompts.py` has `SYSTEM_PROMPT` (prose)
- `app/ai/prompts.py` has `TRADE_EVALUATION_SYSTEM_PROMPT` (JSON-structured)
- `app/providers/ai/base.py` has `TradeVerdict` dataclass
- `app/ai/schemas.py` has `TradeVerdict` Pydantic model — same name, totally different shape

**Why current design is heavier than necessary:**
The old stack (`providers/ai/`) exists only to serve `agent_routes.py` (triage/deep-dive/followup). Its `evaluate_trade()` method is not used anywhere live — the only active AI evaluation path is `evaluation_routes.py` → `FoundryEvalAdapter`. The old adapters' `evaluate_trade()` and `follow_up()` methods are dead code. The `chat()` method is the only thing used, and it has an identical signature in both stacks.

**What should happen instead:**
Keep `FoundryEvalAdapter` and `AnthropicAdapter` but unify them under one directory (`app/ai/` or `app/providers/ai/`, pick one). Delete `providers/ai/foundry_adapter.py`, `providers/ai/anthropic_adapter.py`, `providers/ai/base.py`. Rename `FoundryEvalAdapter` to `FoundryAdapter`. Move `AnthropicAdapter` to match. The `chat()` interface is the common contract — formalize it.

---

### 3.2 — Remove ODBC Installer from Application Code
**Severity: High**

**Evidence:** `app/main.py:88-150` — `_install_odbc_if_needed()` is 60+ lines of OS-level subprocess shell code inside the FastAPI application entry point.

**Why current design is heavier than necessary:**
This is infrastructure-layer logic (OS package installation) embedded in application code. It runs synchronously at startup, blocks the event loop during package download (~60s on cold start), and is fragile (different Debian vs Ubuntu paths, apt-get version assumptions). It exists because bash startup scripts lose the Python PATH.

**What should happen instead:**
Use a proper `startup.sh` that installs ODBC before invoking Python, OR use an Azure App Service extension for ODBC, OR build a custom Docker image. The application should never be responsible for installing its own OS dependencies.

---

### 3.3 — Retire the JWT+MSAL Auth Bridge
**Severity: High**

**Evidence:**
- `app/api/entra_auth_routes.py` — validates Entra `id_token` from MSAL, creates local `User` row, returns custom JWT
- `app/api/identity_routes.py` — full BFF OIDC redirect flow, no MSAL dependency
- `main.py:397-398` — comment: "identity_router must be registered BEFORE auth_router: both have GET /auth/me"
- `app/auth/dependencies.py:75-139` (`get_current_user`) and `app/auth/dependencies.py:197-244` (`get_session_user`) — near-duplicate functions
- `web/src/auth/msalConfig.js` — MSAL still configured client-side

**Why current design is heavier than necessary:**
Two competing flows means any incoming request might be authenticated via either cookie+session or JWT Bearer. Both are in `dependencies.py`. Every auth decision point has to handle both cases. The legacy JWT path is only justified if you have non-browser API clients, but there are none visible.

**What should happen instead:**
Migrate fully to BFF session cookies. Remove `entra_auth_routes.py`, `msalConfig.js`, and the JWT fallback path from `get_current_user`. Merge `get_current_user` and `get_session_user` into one dependency. Remove `auth/service.py`'s JWT methods (but keep password/TOTP for future local auth option if needed).

---

### 3.4 — Collapse main.py Startup Ceremony
**Severity: High**

**Evidence:** `app/main.py` — 451 lines, imports 30+ symbols, calls 14+ `init_*()` functions, contains a scheduler setup, ODBC installer, CORS hardcode, and SPA static file mounting.

**Why current design is heavier than necessary:**
The global mutable `init_*()` pattern spreads startup state across 14 modules. If any `init_*()` is not called (e.g., due to a conditional), the corresponding route file silently returns 503. The initialization sequence is implicit and fragile. CORS origins are hardcoded, ignoring the `cors_origins` setting defined in `config.py`.

**What should happen instead:**
Reduce `init_*()` calls by using FastAPI's `Depends()` with module-level singletons or request state. Consolidate the 5-6 auth-related inits into one `init_auth_stack()`. Use `config.py`'s `cors_origins` instead of hardcoding.

---

### 3.5 — Move Prompts for Evaluation Routes into SKILL.md
**Severity: Medium**

**Evidence:**
- `app/ai/prompts.py` — `TRADE_EVALUATION_SYSTEM_PROMPT` is 111 lines of hardcoded JSON schema + evaluation instructions
- `FOLLOW_UP_SYSTEM_PROMPT` is another 14 lines
- `app/providers/ai/prompts.py` has `SYSTEM_PROMPT`, `build_trade_prompt()`, `pre_screen_trade()` also hardcoded

**Why current design is heavier than necessary:**
CLAUDE.md rule: "**Prompts in SKILL.md**: Never hardcode prompts in Python or React." The `agent_routes.py` follows this rule. `evaluation_routes.py` does not. This creates an inconsistency: some prompts are versionable and auditable, others are embedded Python strings.

**What should happen instead:**
Create `app/skills/trade-evaluation/SKILL.md` with `EVALUATION_SYSTEM`, `EVALUATION_USER`, `FOLLOWUP_SYSTEM` sections. Use `get_skill("trade-evaluation")` in `evaluation_routes.py`.

---

### 3.6 — Remove Tradier Adapter
**Severity: Medium**

**Evidence:**
- `app/providers/tradier.py` — full adapter, not in `PROVIDER_REGISTRY`
- Tradier is not registered, not reachable via `get_market_data()`
- CLAUDE.md: "Tradier — fallback only, dev/testing without Schwab"

**Why current design is heavier than necessary:**
The adapter exists but is unreachable through any code path. It just occupies space and creates the impression that Tradier is a live fallback.

**What should happen instead:**
Delete `app/providers/tradier.py`. If Tradier support is needed in the future, re-add it from git history.

---

## 4. Architectural Drift Findings

### 4.1 — `agent_routes.py` vs `agents_routes.py`: Same-name confusion
**Area:** API routing
**Severity: High**
**Evidence:** Both exist in `app/api/`. One letter difference. Different prefixes (`/agent` vs `/agents`). Different purposes.
**Why it matters:** Immediate cognitive overhead. Any developer editing the wrong file creates silent bugs.
**Fix:** Rename `agent_routes.py` → `trade_agent_routes.py` and `agents_routes.py` → `position_monitor_routes.py`.

---

### 4.2 — `SchwabToken` model declared dead in docs but still in codebase
**Area:** Data model
**Severity: Medium**
**Evidence:** `app/models/database.py:240-276` defines `SchwabToken`. MEMORY.md: "The SchwabToken DB model exists but is intentionally unused." The model is part of `init_db()` and creates an actual DB table.
**Why it matters:** Dead models create confusion. They're created in `init_db()` which creates real tables in production.
**Fix:** Delete `SchwabToken` from `database.py` and drop the table in production.

---

### 4.3 — `CORS_ORIGINS` config setting never used
**Area:** Configuration
**Severity: Medium**
**Evidence:**
- `config.py:65`: `cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]`
- `main.py:373-383`: `CORSMiddleware` hardcodes a completely different list of 5 origins
- The config setting is never referenced
**Fix:** Remove `cors_origins` from `config.py` or wire `main.py` to use it.

---

### 4.4 — Frontend deployed twice (Static Web App + backend static serving)
**Area:** Deployment
**Severity: Medium**
**Evidence:**
- `.github/workflows/azure-static-web-apps-purple-ground-0d4efed10.yml` — deploys frontend to Azure Static Web Apps
- `app/main.py:437-450` — SPA fallback serving `static/index.html` from the backend bundle
- It is unclear which frontend `oa.tmtctech.ai` actually resolves to
**Fix:** Pick one. Retire the Static Web App deploy or retire the backend static serving.

---

### 4.5 — `deviation_detector.py` not imported
**Area:** Agent architecture
**Severity: Low**
**Evidence:** `app/agents/deviation_detector.py` exists. No `__pycache__` entry. Not visible in any import chain.
**Fix:** Verify. If unused, delete.

---

### 4.6 — `app/ai/message_builder.py` not imported
**Area:** AI stack
**Severity: Low**
**Evidence:** File present in `app/ai/`. Not imported in `app/ai/__init__.py` or visible in any route.
**Fix:** Verify. If unused, delete.

---

### 4.7 — CLAUDE.md says `skill_loader.py` is in `app/agents/` — it's in `app/skills/`
**Area:** Doc-to-code drift
**Severity: Low**
**Evidence:** CLAUDE.md backend structure shows `app/agents/skill_loader.py`. Actual location: `app/skills/skill_loader.py`.
**Fix:** Update CLAUDE.md.

---

## 5. Dead Code / Stale Abstractions / Deletion Candidates

| File/Module | Classification | Confidence | Evidence | Rationale |
|---|---|---|---|---|
| `app/providers/tradier.py` | **Delete** | High | Not in `PROVIDER_REGISTRY`; no active execution path | True dead code |
| `app/providers/ai/foundry_adapter.py` | **Delete after merge** | High | Superseded by `app/ai/foundry_adapter.py`; `evaluate_trade()` unused | Old AI stack |
| `app/providers/ai/anthropic_adapter.py` | **Delete after merge** | High | `evaluate_trade()` and `follow_up()` unused; only `chat()` used | Old AI stack |
| `app/providers/ai/base.py` | **Delete after merge** | High | `AIProvider` ABC with `evaluate_trade()`/`follow_up()` not called; `TradeVerdict` dataclass conflicts with Pydantic model | Old AI stack |
| `app/providers/ai/prompts.py` | **Delete after merge** | High | `SYSTEM_PROMPT` (prose-based); `build_trade_prompt()`, `pre_screen_trade()` not on active evaluation path | Old AI stack |
| `app/ai/message_builder.py` | **Needs verification** | Medium | Not visible in imports | Possibly dead |
| `app/agents/deviation_detector.py` | **Needs verification** | Medium | No `__pycache__` match | Possibly dead |
| `app/models/database.py` `SchwabToken` class | **Delete** | High | Documented as unused; Key Vault is canonical token store | Dead model + real DB table |
| `app/api/entra_auth_routes.py` | **Delete after BFF migration** | Medium | Old MSAL bridge; `identity_routes.py` is the replacement | Legacy auth flow |
| `web/src/auth/msalConfig.js` | **Delete after BFF migration** | Medium | MSAL not used in BFF redirect flow | Legacy auth |
| `web/src/pages/_archive/` (all 3 files) | **Delete** | High | Archived, redirected-away pages | Dead frontend |
| `web/src/components/Header.jsx` + `Header.css` | **Delete** | High | CLAUDE.md: "RETIRED — replaced by Layout.jsx left rail" | Dead component |
| `web/src/pages/FavoritesPage.css` | **Delete** | High | Page is a `Navigate` redirect | Orphaned CSS |
| `web/src/pages/VerticalsPage.css` | **Delete** | High | Page is a `Navigate` redirect | Orphaned CSS |
| `web/src/assets/options-analyzer-logo_old.png` | **Delete** | High | Filename says `_old` | Dead asset |
| `web/src/assets/react.svg` | **Delete** | High | Default Vite scaffold file | Never used |
| `app/providers/ai/__init__.py` | **Delete after merge** | High | Will be empty after stack merge | |
| `agents-qa-system.zip`, `agents-qa-system/` | **Archive/Delete** | High | Not part of the application | Committed artifact |
| `scratch/` directory | **Delete** | High | Calibration scripts, test JSON files | Dev artifacts |
| `prototypes/` directory | **Archive** | Medium | Historical mockups | Not production |
| `jira_updates/`, `jira_restructure.py` | **Delete** | High | One-time Jira migration scripts | Dev artifacts |
| `data/` directory | **Archive** | Medium | CSV/SQL data files | Not application code |
| `ota-commits.txt`, `startup.log`, `db-url-setting.json` | **Delete** | High | Dev artifacts committed | Not production |
| `build-diagram-with-icons.ps1`, `build-diagram-with-icons.py` | **Archive** | Medium | Architecture diagram build scripts | Not application code |

---

## 6. Where The Architecture Is Lying To Itself

### "We have a provider adapter pattern" — but one provider is dead and another has two implementations
The `PROVIDER_REGISTRY` lists only `schwab`. Tradier is a file, not a provider. The "AI provider" registry (`providers/ai/`) exists alongside a second, incompatible AI stack (`app/ai/`). The factory manages market data providers cleanly. AI providers are bootstrapped by hand in `main.py` with conditional logic — not via the factory at all.

### "Prompts live in SKILL.md" — except for the main evaluation flow
The most trafficked AI path — `/evaluate/structured` — has its 111-line JSON prompt hardcoded in `app/ai/prompts.py`. The SKILL.md principle applies only to the agent triage/deep-dive pipeline. The architecture rule isn't enforced; it's selectively applied.

### "We have a single AI provider abstraction" — but we actually have three Foundry adapters
1. `app/providers/ai/foundry_adapter.py` — `FoundryAdapter(AIProvider)`, SDK-based, prose output
2. `app/ai/foundry_adapter.py` — `FoundryEvalAdapter`, httpx-based, JSON output
3. Both have a `health_check()` method. Both have a `chat()` method. Different signatures. Different callers. Different prompt conventions.

### "The factory pattern gives us provider flexibility" — but the factory has a hardcoded `schwab` singleton
`PROVIDER_REGISTRY` is a module-level dict with one entry. It's mutated by `init_schwab()`. There is no `register_market_data_provider()` API. Adding a new provider means manually editing the registry. This is closer to a named singleton lookup than a real factory.

### "We have unified deployment" — but there are two frontend deploy pipelines
`main.py` serves the SPA as a static fallback. The `.github/workflows/azure-static-web-apps-*.yml` deploys to a separate Azure Static Web Apps instance. It is not clear which one `oa.tmtctech.ai` actually resolves to.

### "Tier 3 TRADE access has per-trade challenge" — but all BFF-auth users get `role: 'admin'`
`dependencies.py:109,120` — any user authenticated via BFF session cookie returns `role: "admin"`. The three-tier security model (READ/WRITE/TRADE) is bypassed for all OIDC users. `require_admin` and `require_trader` are effectively dead as authorization gates for the primary auth path.

---

## 7. Best Practice Gaps

### Backend
- **Global mutable init pattern**: 14+ route files use `_var = None` + `init_*()`. No startup validation that all inits completed. Silent 503 on misconfiguration.
- **`datetime.utcnow()` used throughout**: Deprecated in Python 3.12+. Should be `datetime.now(timezone.utc)`. Half the codebase uses the old form.
- **`_pkce_cache` in `identity_routes.py`**: Module-level dict with stale-entry pruning. Not thread-safe under multi-worker. Acceptable for single worker, but undocumented assumption.
- **`JWKS_cache` in `entra_auth_routes.py`**: Same pattern, same risk.
- **No request logging middleware**: No structured access logs per request.

### Frontend
- **`web/src/auth/msalConfig.js`**: MSAL configured but BFF flow doesn't use it. May confuse future developers.
- **localStorage for watchlist/favorites**: Documented as "persistence gap" but has been true for the entire project lifetime.
- **No error boundary components**: A failed widget crashes the whole page.

### Auth/Security
- **PKCE cache is in-memory**: Survives only within a worker process. If App Service scales to 2 workers, a user whose `/auth/login` was handled by worker 1 may get `invalid_state` if the `/callback` hits worker 2. The App Service is F1/solo-worker today, but this is a latent bug.
- **id_token decoded without signature verification** (`identity_routes.py:256-263`): The comment says this is fine because "token came directly from Entra over HTTPS." Correct, but worth explicit documentation.
- **JWT `HS256` + shared secret**: The JWT secret is fetched from Key Vault on first call and cached in-process. Rotating the secret requires a process restart.
- **`skip_auth: bool` in Settings**: In production this should be enforced at the infra layer, not just by convention.

### Data Model
- **`database.py` is 928 lines**: 20+ models in one file. Works today, will become unwieldy.
- **Mixed PK types**: `User` uses `String(36)`, `TradeLog` uses `Integer`, `Position` uses `String(36)`. Inconsistent and makes joining fragile.
- **`datetime.utcnow` default in ORM**: `Column(DateTime, default=datetime.utcnow)` — the function itself is deprecated in Python 3.12+. Should be `lambda: datetime.now(timezone.utc)`.
- **`SchwabToken` table is created by `init_db()` but intentionally unused**: Real DB table, real schema migration overhead, no data.

### Observability
- **`agent_run_log` stores full prompts in `Text` columns**: Good for auditability, but unbounded storage growth with no TTL or archive strategy.
- **Application Insights telemetry only on AI routes**: No spans for auth, market data, or DB calls.

### Deployment/DevEx
- **ODBC in app startup**: Infrastructure concern embedded in application layer.
- **`startup.sh` exists in repo but is not the actual startup command**: Appears to be a reference/fallback not actually used.
- **`options_analyzer.db` SQLite file committed**: Should be in `.gitignore`.
- **`cert.pem` and `key.pem` in repo root**: Self-signed certs should be in `.gitignore`.
- **Two `foundry_api_key` sources in Settings**: `foundry_api_key` (SDK path Settings field) and `foundry-api-key` (Key Vault secret name for httpx path) — non-obvious split.

### Testing
- **Zero auth tests**: The most complex and security-critical subsystem has no test coverage.
- **Zero provider contract tests**: No test that `SchwabMarketData.get_quote()` returns the expected shape.
- **Zero route integration tests**: No test that any route returns the expected HTTP status.
- **Test files that require live services**: `tests/test_amzn_regression.py` likely requires real Schwab data.

---

## 8. Lean Target Architecture

### Delete
- `app/providers/tradier.py`
- `app/providers/ai/` (entire directory, after AI stack merge)
- `app/api/entra_auth_routes.py` (after BFF migration completion)
- `web/src/auth/msalConfig.js`
- `web/src/pages/_archive/`
- `web/src/components/Header.jsx`, `Header.css`
- `web/src/pages/FavoritesPage.css`, `VerticalsPage.css`
- `web/src/assets/options-analyzer-logo_old.png`, `react.svg`
- `app/models/database.py` `SchwabToken` class (and drop table)
- `app/ai/message_builder.py` (after verification)
- `app/agents/deviation_detector.py` (after verification)
- Committed junk: `scratch/`, `ota-commits.txt`, `startup.log`, `db-url-setting.json`, `jira_updates/`, `jira_restructure.py`, `agents-qa-system.zip`, `agents-qa-system/`

### Merge
- `app/providers/ai/` into `app/ai/` — one AI directory, one `FoundryAdapter`, one `AnthropicAdapter`, one `chat()` interface
- `get_current_user` and `get_session_user` into one dependency in `dependencies.py`
- `app/api/agent_routes.py` init pattern and `app/api/agents_routes.py` init pattern → consolidate the `init_*()` pattern into a startup module

### Rename
- `app/api/agent_routes.py` → `app/api/trade_agent_routes.py`
- `app/api/agents_routes.py` → `app/api/position_monitor_routes.py`
- `FoundryEvalAdapter` → `FoundryAdapter` (after merge)

### Split
- `app/models/database.py` (928 lines, 20+ models) → at minimum `app/models/auth_models.py`, `app/models/analysis_models.py`, `app/models/position_models.py`

### Reusable platform architecture (portable to future AI apps)
- `app/skills/skill_loader.py` — the `{{variable}}` + `{{#if}}` template engine
- `app/auth/session_manager.py` — BFF session pattern with Fernet encryption
- `app/auth/client_assertion.py` — certificate-based JWT assertion for Entra
- `app/auth/providers.py` — identity provider config registry pattern
- `app/middleware/csrf.py` — CSRF middleware for BFF
- `app/agents/telemetry.py` — `invoke_with_tracing()` + Application Insights bridge
- `app/core/secrets.py` — Key Vault + env fallback SecretsManager
- Generic insight engine pattern (domain-agnostic deviation → score → communicate)

### Options Analyzer-specific domain logic
- All of `app/analysis/` — scoring engines, hard gates, Black-Scholes, strategy definitions
- `app/providers/schwab.py`, `schwab_token_manager.py` — Schwab-specific OAuth
- `app/providers/finnhub_earnings.py` — OTA-specific earnings data source
- `app/ai/prompts.py` — OTA-specific trade evaluation prompt (JSON schema reflects OTA's Thesis Matrix)
- `app/skills/claude-trade-agent/SKILL.md` — OTA trade evaluation pipeline
- `app/skills/position-monitor/SKILL.md` — OTA position health monitoring

---

## 9. Prioritized Refactor Roadmap

### Quick Wins (1–2 days each)

| Item | Impact | Effort | Risk | Why it reduces drag |
|---|---|---|---|---|
| Rename `agent_routes.py` → `trade_agent_routes.py` and `agents_routes.py` → `position_monitor_routes.py` | Medium | Low | Low | Eliminates daily cognitive friction |
| Delete dead files: `Header.jsx/css`, `FavoritesPage.css`, `VerticalsPage.css`, `_archive/`, `logo_old.png`, `react.svg` | Low | Low | Very Low | Reduces noise, signal clearer |
| Delete junk from repo root: `scratch/`, `ota-commits.txt`, `startup.log`, `db-url-setting.json`, jira artifacts | Low | Low | Very Low | Repo hygiene |
| Remove `SchwabToken` model from `database.py` | Low | Low | Low | Table is dead; model causes confusion |
| Fix `cors_origins` — wire `main.py` to use `config.py`'s setting | Medium | Low | Low | Enables env-level CORS config |
| Replace all `datetime.utcnow()` with `datetime.now(timezone.utc)` | Low | Low | Low | Removes Python 3.12 deprecation warnings |

### Medium Refactors (up to 1 week)

| Item | Impact | Effort | Risk | Notes |
|---|---|---|---|---|
| **Merge AI stacks** — collapse `app/providers/ai/` into `app/ai/`; one `FoundryAdapter`, one `AnthropicAdapter`, shared `chat()` interface | High | Medium | Medium | Test evaluation + agent routes after; improves portability to any future app |
| **Move evaluation prompts to SKILL.md** — `app/ai/prompts.py` → `app/skills/trade-evaluation/SKILL.md` | Medium | Low | Low | Enforces architecture rule; enables prompt versioning |
| **Merge `get_current_user` and `get_session_user`** in `dependencies.py` | Medium | Low | Low | Removes duplicate logic |
| **Split `database.py`** into 3-4 model files by domain | Low | Low | Very Low | Removes 928-line cognitive bottleneck |
| **Add `.gitignore` entries**: `options_analyzer.db`, `cert.pem`, `key.pem`, `startup.log` | Low | Very Low | Very Low | Stop committing these |

### Strategic Refactors (multi-step)

| Item | Impact | Effort | Risk | Notes |
|---|---|---|---|---|
| **Complete BFF migration** — retire `entra_auth_routes.py` + MSAL; enforce BFF as the only auth path | High | High | Medium | Requires frontend coordination; removes auth complexity permanently |
| **Remove ODBC installer from `main.py`** — move to Azure App Service startup script or custom image | High | Medium | Medium | Requires Azure infra change |
| **Unify frontend deployment** — retire Static Web App or retire backend static serving; pick one canonical path | Medium | Medium | Low | Removes ambiguity about which frontend is live |
| **Add auth + provider contract tests** | High | Medium | Low | Zero test coverage on most critical paths |

---

## 10. Safe Deletions / Consolidations

**Delete now (safe):**
- `web/src/pages/_archive/` (3 files)
- `web/src/components/Header.jsx`, `Header.css`
- `web/src/pages/FavoritesPage.css`, `VerticalsPage.css`
- `web/src/assets/options-analyzer-logo_old.png`, `react.svg`
- `scratch/` (5 files)
- `ota-commits.txt`, `startup.log`, `db-url-setting.json`
- `jira_updates/`, `jira_restructure.py`
- `agents-qa-system/`, `agents-qa-system.zip`

**Delete after merge (safe once AI stack is unified):**
- `app/providers/ai/` (entire directory)
- `app/providers/tradier.py`
- `SchwabToken` class from `database.py`

**Delete after verification:**
- `app/ai/message_builder.py`
- `app/agents/deviation_detector.py`

**Merge:**
- `get_current_user` + `get_session_user` → one function
- `app/providers/ai/` → `app/ai/`

**Rename:**
- `agent_routes.py` → `trade_agent_routes.py`
- `agents_routes.py` → `position_monitor_routes.py`
- `FoundryEvalAdapter` → `FoundryAdapter` (after merge)

**Keep:**
- `app/analysis/` (all scoring engines)
- `app/auth/session_manager.py`, `client_assertion.py`, `providers.py`
- `app/skills/skill_loader.py`
- `app/agents/telemetry.py`
- `app/core/secrets.py`
- `app/providers/factory.py` (with minor cleanup)
- `app/middleware/csrf.py`

---

## 11. Testing Strategy To Support Simplification

**Immediate smoke tests (add before any refactor):**
1. `POST /api/v1/auth/login` → redirects to Entra
2. `GET /api/v1/auth/me` with valid session cookie → returns user profile
3. `GET /api/v1/auth/me` without cookie → 401
4. `GET /api/v1/market/quote/AAPL` with auth → returns price
5. `POST /api/v1/evaluate/structured` with sample payload → returns `TradeVerdict`

**Highest-value auth tests:**
- PKCE callback with valid/invalid/expired state tokens
- Session cookie accepted on protected route
- JWT Bearer still accepted (during migration)
- CSRF rejection on POST without header
- Token refresh: session survives 5-minute token expiry window

**Provider contract tests:**
- `SchwabMarketData.get_quote()` returns `{"symbol", "price", "bid", "ask"}`
- `FoundryAdapter.chat()` returns `{"text", "input_tokens", "output_tokens", "model", "provider"}`
- `EarningsInWindowGate.evaluate()` returns `GateResult` with `triggered=True` when earnings within 5 days

**Deployment confidence tests (after each deploy):**
- `/health` returns 200
- `/api/v1/auth/session/status` returns 200
- DB connectivity check (already in health_routes)
- AI provider connectivity check (already in health_routes)

**Minimum viable regression suite:**
- Hard gates: earnings gate, negative EV gate (already written)
- AI schema validation: `TradeVerdict.model_validate_json()` on known-good response
- Auth: session creation, get_session, delete_session unit tests

---

## 12. Final Recommendation

**If you hired me to simplify this repo without breaking momentum, here's what I'd do:**

**Week 1 — Signal-to-noise:**
Rename `agent_routes.py` and `agents_routes.py` to sensible names. Delete the dead frontend files (Header, archive, orphaned CSS, old assets). Delete the junk from the repo root (scratch/, ota-commits.txt, startup.log, jira_updates, agents-qa-system). Delete `SchwabToken` from the model. Wire `cors_origins` config to `main.py`. Fix `.gitignore` for certs and SQLite. Add 5 smoke tests to the test suite. Result: the repo is immediately less confusing to navigate and the most common trip hazards are gone.

**Week 2 — Merge the AI stacks:**
Collapse `app/providers/ai/` into `app/ai/`. One `FoundryAdapter`, one `AnthropicAdapter`, one `chat()` interface. Update `agent_routes.py` imports. Run existing tests. Move the evaluation prompts from `app/ai/prompts.py` into a `app/skills/trade-evaluation/SKILL.md`. Verify `/evaluate/structured` and `/agent/triage` routes both work. Result: half the AI cognitive overhead is gone, the SKILL.md rule is enforced uniformly.

**Week 3 — Complete the BFF migration:**
Retire `entra_auth_routes.py`. Remove the JWT Bearer fallback from `get_current_user`. Merge the two auth dependency functions. Delete `msalConfig.js`. Test the full login/callback/me/logout flow. Add auth unit tests for session creation and CSRF rejection. Result: auth is one coherent system instead of two partially overlapping ones.

---

## Appendix A — Questions Before Any Refactor Starts

1. Is `entra_auth_routes.py` (MSAL bridge) actively used by any client today, or is the BFF redirect flow the only path?
2. Does `oa.tmtctech.ai` resolve to the App Service backend or the Static Web App? (Determines which frontend deploy pipeline to retire.)
3. Is `app/agents/deviation_detector.py` intentionally incomplete, or is it supposed to be wired into `insight_engine.py`?
4. Is `app/ai/message_builder.py` a work-in-progress or abandoned?
5. Are there any non-browser API clients (scripts, Excel Python) currently using the JWT Bearer auth path?

---

## Appendix B — Assumptions That Could Change The Recommendation

- **If multiple browser clients use the MSAL bridge:** the JWT auth path cannot be retired until all are migrated.
- **If App Service scales to 2+ workers:** the in-memory PKCE cache becomes a correctness bug requiring an external cache (Redis) or sticky sessions.
- **If live trading (Phase 5) ships soon:** the `require_trader`/role system needs to be validated — currently BFF users all get `role: 'admin'`.
- **If cost matters:** the `agent_run_log` grows unbounded. A retention policy or archival strategy is needed before this becomes expensive.

---

## Appendix C — Most Likely Sources of Bloat, Drift, and Deployment Friction

1. **Migration debt**: Both auth systems and both AI stacks are live simultaneously. The old was never retired after the new was built.
2. **No deletion discipline**: Files added, migrations done, old paths never cleaned. The prompts directory has 100+ archived prompt files. The repo root has log files.
3. **`main.py` gravity**: Because everything initializes there, it accumulates. Every new subsystem adds imports + init calls + startup log lines.
4. **The "it works in dev" trap**: The ODBC installer, the SQLite default, `skip_auth` — these dev accommodations become permanent fixtures because they work and no one prioritizes the clean version.

---

## Three Places I Would Start Cutting Complexity Tomorrow

1. **Delete `app/providers/ai/`** — Rename `FoundryEvalAdapter` → `FoundryAdapter` and update the two call sites in `main.py` and `agent_routes.py`. This collapses the most confusing architectural duplication in the entire codebase in about 2 hours. The `chat()` interface is already compatible.

2. **Rename `agent_routes.py` → `trade_agent_routes.py` and `agents_routes.py` → `position_monitor_routes.py`** — A 15-minute find-and-replace that immediately eliminates one of the highest-frequency cognitive hazards in the codebase.

3. **Delete the dead frontend files** (`Header.jsx/css`, `_archive/`, `FavoritesPage.css`, `VerticalsPage.css`, `logo_old.png`, `react.svg`) — 20 minutes, zero risk, the frontend immediately has less surface area to explain.
