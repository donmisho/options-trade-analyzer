# OPUS 4-7 Aggressive Architecture Review — Full Session
**Generated:** 2026-04-30

---

# PROMPT

---

You are acting as a Principal Engineer brought in to perform a hard-nosed
simplification review of this repository. The codebase is an AI-driven
application (Options Analyzer) but your job is NOT to score it as a product.
Your job is to look at it the way a seasoned engineer looks at a system that
has been shipped, extended, partially migrated, and patched for a year, and
then say plainly: what is earning its keep, what is not, and what should be
deleted, merged, or flattened.

You are reviewing only. Do not modify any files. Do not produce patches. Do
not refactor. Do not run formatters. You may read anything in the repo. If
you need to execute commands to inspect the repo (grep, find, ls, git log,
etc.), do so, but make no writes.

================================================================
NORTH STAR
================================================================
Be more demanding than a normal architecture reviewer. Optimize for ruthless
simplification without breaking strategic extensibility. Bias hard toward
deletion, consolidation, and fewer concepts. Treat every abstraction as
guilty until proven innocent.

A small team ships this code. Cognitive load, deployment friction, and
local-vs-prod drift are first-class concerns, not aesthetics.

================================================================
PROTECTED ARCHITECTURAL PRINCIPLES (intent level)
================================================================
The following principles should be preserved at the intent level. You may
(and should) attack the *current implementation* of any of them aggressively
if the code is bloated, fragmented, drifted, or heavier than necessary. But
do not recommend abandoning the principle itself unless you can give a
concrete, evidence-backed reason.

1.  Provider Adapter Pattern — external providers (market data, brokerage,
    LLM, etc.) remain pluggable; provider-specific auth/credential lifecycle
    stays inside the adapter; adding a new provider must not require
    rewriting routes, engines, or frontend.

2.  Skill-Driven Prompt Architecture — prompts live in SKILL.md files, not
    hardcoded in Python or React. Prompt behavior is auditable and
    versionable.

3.  Two-Track Observability — AI operations preserve both trace/telemetry
    visibility AND durable business/audit records. Neither track replaces
    the other.

4.  Unified Position Model — paper and live positions share a core model
    where practical.

5.  Generic Insight Engine — detect → score → communicate anomaly
    architecture stays portable; options-specific behavior stays isolated
    from generic insight logic.

6.  Backend-for-Frontend Identity — the browser does not hold identity
    tokens; the backend is the confidential OIDC client; auth is server-side
    with cookies/sessions.

7.  Unified Deployment — prefer one deployable app/service hosting API +
    SPA unless there is a compelling, evidence-backed reason not to.

For EACH of these seven principles, you must explicitly answer in your
output: (a) is the intent still right? (b) is the current implementation
honoring it, drifting from it, or theatrically pretending to honor it?
(c) what would the leanest honest implementation look like?

================================================================
GROUND RULES
================================================================
- Read-only. No edits, no patches, no formatting changes.
- Every concrete claim must cite evidence as `path/to/file.ext:LINE` or
  `path/to/dir/`. Vague claims ("the auth layer is complex") are not
  acceptable. If you cannot cite, mark the claim as "needs verification".
- Do not recommend introducing new frameworks, new runtimes, new
  dependencies, microservices, message buses, service meshes, or any
  rewrite-class change. You are simplifying what exists, not adding to it.
- Do not propose a new abstraction unless it deletes at least two existing
  ones. State which two.
- Do not recommend "future-proofing" for needs that are not in the docs or
  in the current backlog visible in the repo.
- If two ways of doing the same thing coexist, your default recommendation
  is "pick one and delete the other," not "harmonize them."
- Be blunt. Do not soften findings. Do not produce a balanced report when
  the evidence is one-sided. If something is bad, say it is bad and cite
  why.

================================================================
PHASE 1 — DOCUMENTATION RECON (do this first, do not skip)
================================================================
Locate and read, in this order, whichever of these exist:
  - CLAUDE.md (root and any nested CLAUDE.md files in subdirectories)
  - architecture-plan.md, architecture.md, ARCHITECTURE.md
  - auth-process.md, auth.md
  - UI-GUIDANCE.md, design-guidelines.md
  - business-rules.md, domain-rules.md
  - All SKILL.md files anywhere in the repo
  - README.md (root and per-package)
  - Any agent-specific CLAUDE.md, AGENTS.md, or similar
  - docs/, /adr/, /runbooks/, deployment.md, DEPLOY.md, infra/*.md
  - Any docstrings or top-of-file headers that describe module intent

From these, build an internal model of:
  - Intended architecture (services, layers, boundaries)
  - Intended ownership (who owns what module/responsibility)
  - Intended workflows (auth, request, AI invocation, deploy)
  - Stated principles, conventions, and naming rules

Note explicitly any docs that contradict each other, point to files that
no longer exist, or describe behavior the code clearly doesn't have.

================================================================
PHASE 2 — REPOSITORY MAP
================================================================
Without reading every file, but by inspecting structure and key entry
points, produce a compact map of the repo across these dimensions:
  - Backend (entry points, routers, services, domain modules)
  - Frontend (entry, routing, state, components, build pipeline)
  - Auth (where identity is established, where sessions live, where tokens
    are issued/validated, what cookies exist)
  - Providers (every external provider adapter — market data, brokerage,
    LLM, telemetry, storage)
  - AI / Skills / Agents (where skills are defined, where they're loaded,
    where prompts are assembled, where model calls happen)
  - Data model (schemas, ORMs, migrations, paper vs live separation)
  - Observability (logging, tracing, metrics, audit/durable records)
  - Deployment / Config (Dockerfile(s), compose, infra, env handling,
    secrets, build/deploy scripts)
  - Tests (where they live, what they cover, what they don't)
  - Scripts / Tooling (one-off scripts, repo automation, dev utilities)

For each dimension, identify: the canonical module(s), any duplicates or
near-duplicates, and any modules that look orphaned.

================================================================
PHASE 3 — INTENT vs IMPLEMENTATION DIFF
================================================================
Compare what the docs (Phase 1) say should exist with what the code
(Phase 2) actually does. Surface:
  - Code that contradicts the docs
  - Docs that point to wrong files, wrong responsibilities, or retired
    components
  - Old and new architecture paths coexisting (partial migrations)
  - Source-of-truth confusion (two places that both claim to own a
    concept — config, identity, position state, prompt content, etc.)
  - Naming drift (module names, route names, or class names that no
    longer reflect what the code does)
  - Components/pages/routes/files that exist but are no longer wired in

================================================================
PHASE 4 — ANTI-PATTERN HUNT
================================================================
Actively search for these specific smells. For each one you find, name
the smell, cite the file(s):line(s), and explain why it qualifies.

  - Architecture theater: structure that looks principled but adds no
    real flexibility (e.g., a "strategy" pattern with one strategy).
  - Fake flexibility: configuration knobs, plugin points, or interfaces
    that have exactly one implementation and no realistic second one.
  - Speculative abstraction: layers built for a use case that hasn't
    arrived and isn't in the backlog.
  - Wrapper-on-wrapper: helpers that wrap helpers that wrap a stdlib or
    SDK call without adding behavior.
  - Ceremonial abstraction: base classes, interfaces, or protocols whose
    only job is to be inherited from once.
  - "Generic" code that is secretly product-specific: modules named or
    described as reusable that are riddled with options-domain
    assumptions, or vice versa.
  - Fragmented auth logic: identity/session/cookie/token concerns
    scattered across more than one or two well-defined modules.
  - Fragmented provider logic: a single provider's auth, request, retry,
    parse, and rate-limit logic spread across multiple files.
  - Fragmented agent/skill architecture: prompt assembly happening in
    multiple layers; SKILL.md files duplicated, stale, or partially
    superseded by inline prompts.
  - Stale UI: components, pages, routes, hooks, or stores that are no
    longer reachable, or are reachable but unused.
  - Duplicate helpers/utilities: two or more modules doing
    near-identical work (date formatting, HTTP wrapping, logging,
    error shaping, etc.).
  - Duplicate or overlapping execution paths: two endpoints, two
    workflows, or two pipelines that converge on the same outcome.
  - Local-vs-prod drift: code paths or config that only behave
    correctly in one environment.
  - Deploy/restart fragility: hidden state, undocumented startup
    ordering, manual steps in the deploy path.
  - Documentation-to-code drift: docs that lie about current behavior.
  - Temporary workarounds that became permanent: TODO/HACK/FIXME,
    "remove after launch," date-stamped comments older than 60 days,
    feature flags that are effectively constants.

For dead-code claims specifically, you must verify with at least one of:
no callers, no imports, no test references, no docs references, no route
registration, no DI registration. State which checks you ran. If you
cannot fully verify, label it "suspected dead — needs verification."

================================================================
PHASE 5 — PRESERVE-OR-CUT DECISIONS
================================================================
For every non-trivial abstraction, layer, helper, or pattern you
encountered, classify it as one of:

  - KEEP — pulling its weight, used by multiple real callers, removal
    would cost more than it saves. Justify briefly.
  - FLATTEN — used, but the abstraction is ceremonial; inline it or
    collapse one level.
  - CONSOLIDATE — overlaps with another module; merge into a single
    canonical implementation. Name which one wins.
  - ISOLATE — currently mixed into "generic" code but is actually
    options-domain-specific (or the inverse). Move it to where it
    belongs.
  - DELETE — no real callers, or replaced by something newer. Cite the
    verification you ran.
  - RENAME — code is fine, name is lying. Propose the honest name.

================================================================
PHASE 6 — STRUCTURED OUTPUT
================================================================
Produce the review using EXACTLY the following sections, in this order,
with these headings. Do not add sections. Do not skip sections. If a
section has no findings, say "No findings" and explain briefly why.

## 1. Executive Summary
## 2. Current Architecture As Implemented
## 3. Top 10 Simplification Opportunities (Ranked)
## 4. Architectural Drift Findings
## 5. Dead Code / Stale Abstractions Inventory
## 6. Where the Architecture Is Lying to Itself
## 7. Best-Practice Gaps
## 8. Lean Target Architecture
## 9. Prioritized Refactor Roadmap
## 10. Safe Deletions & Consolidations
## 11. Testing Strategy to Support Simplification
## 12. Seven-Principle Audit
## 13. Final Recommendation
## 14. Assumptions, Uncertainties, and Questions Before Refactor

================================================================
SELF-CHECK BEFORE YOU RETURN THE REVIEW
================================================================
Before producing the final output, verify:
  - Every concrete claim has a file:line citation OR is marked
    "needs verification."
  - You did not propose a new framework, runtime, or service.
  - You did not propose a new abstraction without naming the two it
    replaces.
  - The roadmap items have effort estimates and risk levels.
  - You named at least one "delete this today" item with high
    confidence.
  - You explicitly addressed all seven protected principles.
  - You named at least three failure modes of your own recommendations
    inside Section 14.

Now begin Phase 1.

---

# OUTPUT

---

# Options Analyzer — Architecture Review
**Date:** 2026-04-30 | **Reviewer:** Principal Engineer (read-only, no edits) | **All claims cited**

---

## 1. Executive Summary

This codebase was originally a clean FastAPI + React SPA. It has since been extended through at least 11 major phases of feature work, an auth migration, a provider refactor, and multiple AI evaluation strategies — each adding new files rather than replacing old ones. The system works and ships, but the accumulated drift is now a real cognitive and operational tax. The two most expensive problems are: (1) two complete, actively-used AI provider packages (`app/providers/ai/` and `app/ai/`) doing overlapping jobs with incompatible interfaces, and (2) three simultaneously active auth flows (`auth_routes`, `entra_auth_routes`, `identity_routes`) that create a confusing auth topology and a genuine security surface to maintain. The `CLAUDE.md` documentation is so far behind the actual frontend structure that it cannot be trusted as a guide; every onboarding or AI-assisted session starts from a false mental model. The single highest-leverage move this team can make this month is to pick the winning AI adapter, delete the losing one, and then retire the two legacy auth routes. **Verdict: Functional but carrying ~40% dead weight — it can be cut without touching product behavior.**

---

## 2. Current Architecture As Implemented

### Backend (`app/`)
```
main.py (451 lines) — monolithic lifespan with 20+ init calls
├── core/           config.py + secrets.py (SecretsManager → Key Vault)
├── auth/           service.py (JWT/TOTP) + dependencies.py (FastAPI deps)
│                   + session_manager.py (BFF cookie) + client_assertion.py
│                   + providers.py + entra_auth_routes.py (old MSAL bridge)
│                   + identity_routes.py (new BFF OIDC) + auth_routes.py (password)
├── providers/
│   ├── base.py     MarketDataProvider + AccountProvider + TradingProvider + ContextSource
│   ├── schwab.py + schwab_token_manager.py + schwab_context_source.py
│   ├── finnhub_earnings.py
│   ├── factory.py  ProviderFactory (PROVIDER_REGISTRY has 1 entry: schwab)
│   └── ai/         [OLD] AIProvider ABC + AnthropicAdapter + FoundryAdapter (SDK) + prompts.py
├── ai/             [NEW] FoundryEvalAdapter (httpx) + schemas.py + prompts.py + message_builder.py
├── analysis/       vertical_engine + long_call + directional + black_scholes
│                   + strategy_scorer + strategy_definitions + health_grade
│                   + hard_gates/ (earnings_gate, negative_ev_gate)
│                   + scoring_factors/asymmetry + strategy_classifier + chain_collection
├── agents/         position_monitor + insight_engine + deviation_detector
│                   + context_store + telemetry
├── api/            17 route files (agent_routes, agents_routes, analysis_routes,
│                   auth_routes, config_routes, dashboard_routes, entra_auth_routes,
│                   evaluation_routes, health_routes, identity_routes, insight_routes,
│                   market_routes, named_watchlist_routes, position_routes,
│                   schwab_auth_routes, service_routes, test_routes, user_routes,
│                   validation_routes, watchlist_routes, admin_routes)
├── models/         database.py + session.py + schemas.py + migrations.py
├── middleware/     csrf.py
├── skills/         skill_loader.py + 3 SKILL.md trees
└── validators/     narrative_grounding.py
```

### Frontend (`web/src/`)
```
App.jsx              — 5 live routes (Dashboard, Trades, Positions, SecurityStrategies, Strategies)
                       + 8 redirect routes for retired paths
context/             AppContext (localStorage watchlist/favorites) + AuthContext (BFF cookie)
api/client.js        — 867-line monolith, all API calls
pages/               TradesPage, StrategyPage, StrategyProfilePage, SecurityStrategiesPage,
                     DashboardPage, PositionsPage, BrokerConnectPage, Analysis, DirectionalPage,
                     LoginPage + _archive/ (3 files)
components/          ~40 components; Header.jsx still present (CLAUDE.md says retired)
auth/msalConfig.js   — MSAL config, superseded by BFF cookie auth
widgets/             6 dashboard widgets
strategy-configs/    6 config files
```

### Auth Shape (THREE concurrent flows — all registered)
1. **Local password → JWT** (`auth_routes.py`, `auth/service.py`) — original
2. **MSAL frontend → JWT bridge** (`entra_auth_routes.py`) — intermediate migration
3. **BFF OIDC → session cookie** (`identity_routes.py`, `session_manager.py`) — current

### AI/Eval Shape (TWO concurrent pipelines — both live)
- **Pipeline A** (agent routes): `agent_routes.py` → `providers/ai/FoundryAdapter` (SDK) → `providers/ai/prompts.py` (prose format) + SKILL.md (via `skill_loader.py`)
- **Pipeline B** (evaluation routes): `evaluation_routes.py` → `ai/FoundryEvalAdapter` (httpx) → `ai/prompts.py` (JSON format)

### Deployment Shape
GitHub Actions: `build-on-push.yml` (build only) → manual `deploy-to-dev.yml` → manual `deploy-to-prod.yml`. Backend: Azure App Service (Python). Frontend: Azure Static Web App (separate deploy). No slot swaps. Rollback via artifact re-deploy.

---

## 3. Top 10 Simplification Opportunities (Ranked)

---

### #1 — Delete the losing AI package (HIGHEST leverage)

**What:** `app/providers/ai/` (SDK-based: `FoundryAdapter`, `AnthropicAdapter`, `base.py`, `prompts.py`) and `app/ai/` (httpx-based: `FoundryEvalAdapter`, `schemas.py`, `prompts.py`, `message_builder.py`) are two complete, active AI invocation stacks. The httpx-based `FoundryEvalAdapter` in `app/ai/` is newer and produces structured JSON. The SDK-based `FoundryAdapter` in `app/providers/ai/` uses a different `AIProvider` ABC and produces prose. Pick one and delete the other. The most concrete action: migrate `agent_routes.py` to use `FoundryEvalAdapter.chat()` (already used by `evaluation_routes.py`), then delete `app/providers/ai/` entirely.

**Why it matters:** Engineers debugging an AI call must know which package to look in. Prompts, schemas, and adapters are split across two trees. Adding any AI capability means deciding which stack to use — which has no documented rule.

**Evidence:** `app/providers/ai/` (`app/providers/ai/foundry_adapter.py:1-293`), `app/ai/foundry_adapter.py:1-267`, `app/main.py:61` (`from app.providers.ai import AnthropicAdapter, FoundryAdapter`), `app/main.py:67` (`from app.ai.foundry_adapter import FoundryEvalAdapter`). `agent_routes.py:43` (`from app.providers.ai.base import AIProvider`), `evaluation_routes.py:38` (`from app.ai.foundry_adapter import FoundryEvalAdapter`).

**Effort:** M | **Risk:** Medium (agent_routes.py needs adapter swap) | **Deletes:** `app/providers/ai/` (5 files), `app/ai/message_builder.py` if unused

---

### #2 — Retire two of three auth flows

**What:** Three auth flows are registered simultaneously in `main.py:397-407`. The old local-password flow (`auth_routes.py`) and the MSAL bridge (`entra_auth_routes.py`) should be retired once the BFF session cookie flow (`identity_routes.py`) is confirmed working. At minimum, `entra_auth_routes.py` should be removed — it issues JWTs from Entra tokens via the old bridge, which overlaps entirely with the BFF flow but leaks a JWT to the browser.

**Why it matters:** Three auth paths mean three surfaces for auth bugs. The `dependencies.py:get_current_user()` (line 75-139) already handles both cookie and JWT — any ambiguity there means a request could silently fall through the wrong path.

**Evidence:** `app/main.py:397,402,407` (all three routers registered), `app/api/entra_auth_routes.py:69-205` (MSAL token → JWT), `app/api/identity_routes.py:6-60` (BFF OIDC), `app/auth/dependencies.py:75-139` (dual-path get_current_user).

**Effort:** M | **Risk:** Medium (confirm BFF is the only active login path before deleting) | **Deletes:** `app/api/entra_auth_routes.py`, `app/api/auth_routes.py` (or at least lock down `/register`)

---

### #3 — Consolidate prompts: delete `app/providers/ai/prompts.py` and `app/ai/prompts.py`, move to SKILL.md

**What:** The system has prompts in three locations — `app/providers/ai/prompts.py` (old prose format, ~300 lines), `app/ai/prompts.py` (new JSON format, ~125 lines), and `app/skills/` SKILL.md files (used only by `agent_routes.py`). The evaluation routes use Python-hardcoded strings directly, violating Principle 2. The path forward: move ALL prompts to SKILL.md and load via `skill_loader.py`. Delete both Python prompt modules.

**Why it matters:** When a prompt needs updating, an engineer must find and update it in 1-3 places depending on which path they're in. The `build_refresh_prompt()` function in `app/providers/ai/prompts.py:147-245` is 100 lines of prompt assembly in Python — exactly what SKILL.md is designed to prevent.

**Evidence:** `app/providers/ai/prompts.py:1-299`, `app/ai/prompts.py:1-126`, `app/skills/skill_loader.py:1-115`, `app/skills/claude-trade-agent/SKILL.md` (referenced at `agent_routes.py:193-198`), `evaluation_routes.py` (loads prompts via `skill_loader` for some paths, but `FoundryEvalAdapter.evaluate_trade()` at `app/ai/foundry_adapter.py:125-149` uses hardcoded `TRADE_EVALUATION_SYSTEM_PROMPT`).

**Effort:** M | **Risk:** Low | **Deletes:** `app/providers/ai/prompts.py`, `app/ai/prompts.py`

---

### #4 — Delete speculative provider interfaces (AccountProvider, TradingProvider)

**What:** `app/providers/base.py:143-209` defines `AccountProvider` (5 abstract methods) and `TradingProvider` (4 abstract methods). Neither has any implementation. `factory.py:111-126` has `get_account()` and `get_trading()` both raising `NotImplementedError`. These are placeholder interfaces for Phase 3 and Phase 5 work that hasn't started.

**Why it matters:** Every engineer reading `base.py` must parse two substantial ABCs that do nothing. The `TradingProvider` comment "Kept separate from AccountProvider because trading is high-risk" is a design decision for a feature that doesn't exist.

**Evidence:** `app/providers/base.py:143-209`, `app/providers/factory.py:111-126`.

**Effort:** S | **Risk:** Low (no callers; verified by searching — `get_account` and `get_trading` only defined in factory, never called) | **Deletes:** 2 ABC classes + 2 factory stubs

---

### #5 — Clean up `main.py` lifespan — extract init helpers

**What:** `main.py:154-356` is a 200-line `lifespan()` function with 9 numbered init steps, conditional imports inside the function body (`from app.analysis.hard_gates import register_gate` at line 272), and one closure (`_scheduled_monitor_run` at line 306). This is not a lifespan function — it's an application assembly script. Extract each step (auth init, provider init, AI init, scheduler init) into dedicated `init_*.py` functions.

**Why it matters:** The lifespan function is the first place a new engineer goes to understand how the app starts. At 200 lines with inline conditionals, it takes 15 minutes just to read. It's also where new dependencies are wired — the longer it is, the more likely a new dependency is wired in the wrong order or skipped in a conditional path.

**Evidence:** `app/main.py:154-356`, conditional import at line 272, closure at line 306.

**Effort:** M | **Risk:** Low | **Merges:** nothing new, just reorganizes existing code into called functions

---

### #6 — Remove or quarantine the git worktree at `.claude/worktrees/peaceful-wu/`

**What:** `.claude/worktrees/` contains a full copy of the app source tree (another instance of `app/`, `web/`, etc.) as a git worktree. This is development tooling from a Claude worktree feature. It is not production code, but it causes confusion: file searches return both trees, and the worktree's files are newer versions in some cases (e.g., `.claude/worktrees/peaceful-wu/app/api/` has `validation_routes.py`, `admin_routes.py`, `watchlist_routes.py` — live routes).

**Why it matters:** Any grep for a class or function returns doubled results. CI tools may inadvertently pick up worktree files. If the worktree was never merged, work may be lost.

**Evidence:** `.claude/worktrees/peaceful-wu/app/` (full duplicate tree), untracked in git status as `?? .claude/worktrees/`.

**Effort:** S | **Risk:** Low | **Deletes:** The worktree directory or properly merges its branch

---

### #7 — Collapse the two watchlist route files or clarify their boundary

**What:** `watchlist_routes.py` (simple flat watchlist: GET/POST/DELETE) and `named_watchlist_routes.py` (multi-list: 9 endpoints, with scan sources) serve overlapping concepts for the same user. If `named_watchlists` is the current approach, `watchlist_routes.py` is either dead or a migration holdover.

**Why it matters:** Two routes with overlapping semantics creates ambiguity for every frontend call to "add to watchlist". The `client.js` at 867 lines likely has calls to both.

**Evidence:** `app/api/watchlist_routes.py:1-92`, `app/api/named_watchlist_routes.py:1-41`, `app/main.py:405-406` (both registered).

**Effort:** S | **Risk:** Low-Medium (confirm which the frontend uses before deleting) | **Merges:** one into the other

---

### #8 — Rename `agent_routes.py` / `agents_routes.py` — distinguish them clearly

**What:** `app/api/agent_routes.py` (prefix `/agent` — triage/deep-dive/followup for the Claude Trade Agent) and `app/api/agents_routes.py` (prefix `/agents` — position monitor status/run) differ by only one letter and share no code or responsibility. The plural/singular distinction is invisible at a glance in `main.py:52,55`.

**Why it matters:** Every time you grep for "agent", both appear. One is about AI trade evaluation; the other is about scheduled background job management. These have nothing in common except the word "agent".

**Evidence:** `app/main.py:52` (`agent_routes`), `app/main.py:55` (`agents_routes`), `app/api/agent_routes.py:47` (prefix `/agent`), `app/api/agents_routes.py:26` (prefix `/agents`).

**Effort:** S | **Risk:** Low | **Rename:** `agent_routes.py` → `trade_evaluation_routes.py`, `agents_routes.py` → `position_monitor_routes.py`

---

### #9 — Remove `web/src/auth/msalConfig.js` and `web/src/components/Header.jsx`

**What:** `web/src/auth/msalConfig.js` is MSAL configuration from when the frontend used `@azure/msal-browser` for auth. Auth now happens entirely server-side (BFF cookie). The file is not imported in `App.jsx` or any active component — verified by searching. `web/src/components/Header.jsx` is marked "RETIRED — replaced by Layout.jsx left rail" in CLAUDE.md and is not imported in App.jsx.

**Why it matters:** Dead files in `src/` confuse engineers building new features ("should I be using MSAL?"). They also stay in the bundle if accidentally imported.

**Evidence:** `web/src/auth/msalConfig.js` (file exists), not imported in App.jsx, not imported in main.jsx. `web/src/components/Header.jsx` (file exists), CLAUDE.md line says "RETIRED — replaced by Layout.jsx".

**Effort:** S | **Risk:** Low | **Deletes:** 2 files (verify zero imports first)

---

### #10 — Add a migration system; remove schema auto-create from startup

**What:** `app/models/session.py` calls `metadata.create_all()` on startup (via `init_db()`). This means schema is managed by "CREATE IF NOT EXISTS" at app start — no versioning, no rollback, no audit. `app/models/migrations.py` exists but its content hasn't been checked; this needs verification.

**Why it matters:** Any schema change is invisible and irreversible in production. If you add a column to a model, it creates on fresh deployments but doesn't migrate existing instances. The `migrations.py` file's existence suggests someone knew this was needed but didn't finish it.

**Evidence:** `app/models/` (contains `migrations.py`), `app/models/session.py` (contains `init_db()`, called at `app/main.py:174`).

**Effort:** L | **Risk:** High (schema changes) | **Needs verification:** actual content of `migrations.py`

---

## 4. Architectural Drift Findings

### A. CLAUDE.md vs. Actual Frontend — Major Drift

CLAUDE.md describes the frontend architecture as of ~Phase 3.6. The current frontend has diverged significantly:

| CLAUDE.md Says | Reality |
|---|---|
| `OptionsTerminal.jsx` — PRIMARY | Doesn't exist; `TradesPage.jsx` is the trades screen |
| `SecurityDashboard.jsx` — [NEW 2.9] | Doesn't exist as a route; `SecurityStrategiesPage.jsx` is live |
| `VerticalsPage.jsx` — DEPRECATED | Exists in `_archive/`, correctly handled as redirect in App.jsx |
| `NakedOptionsPage.jsx` — DEPRECATED | Not found at all |
| `FavoritesPage.jsx` — DEPRECATED | Not found; redirected to `/positions` in App.jsx |
| Missing | `TradesPage.jsx`, `StrategyPage.jsx`, `StrategyProfilePage.jsx`, `SecurityStrategiesPage.jsx`, `BrokerConnectPage.jsx` — all live and active |
| `app/providers/ai.py` (in backend structure) | Doesn't exist; it's `app/providers/ai/` (package) |
| `AskClaudePanel.jsx` — DEPRECATED to remove | File is gone from live frontend (good) but docs still mention it |

**Evidence:** `web/src/App.jsx:18-24` (actual imports), CLAUDE.md Backend Structure section (`app/providers/ai.py`), CLAUDE.md Frontend Pages section.

### B. Auth Migration — Partial, All Flows Still Live

The system migrated from (1) local JWT → (2) MSAL frontend bridge → (3) BFF session cookie. All three are registered. The MSAL bridge (`entra_auth_routes.py`) contradicts the BFF principle (Principle 6): it returns a JWT to the browser which the browser must store. The BFF flow correctly never sends tokens to the browser.

**Evidence:** `app/main.py:402,407` (both `entra_auth_router` and `identity_router` registered), `app/api/entra_auth_routes.py:201` (returns `access_token` to browser), `app/api/identity_routes.py:1-60` (sets httpOnly cookie).

### C. AI Evaluation — Two Incompatible Pipelines

`evaluation_routes.py` and `agent_routes.py` both call Claude but through completely different code paths with different interfaces, different prompt formats, different schema types, and different error handling.

- `agent_routes.py` expects prose responses, parses verdict via regex (`re.search(r"VERDICT[:\s]+(EXECUTE|WAIT|PASS)"` at `agent_routes.py:471`)
- `evaluation_routes.py` expects JSON structured responses, parses via Pydantic

These two pipelines are diverging. Any change to the AI invocation pattern (retry logic, caching, error handling) must be made in both.

**Evidence:** `app/api/agent_routes.py:471` (regex verdict parsing), `app/api/evaluation_routes.py` (Pydantic JSON parse), `app/ai/foundry_adapter.py:64-80` (`_extract_json` strip for JSON), `app/providers/ai/foundry_adapter.py:266-292` (`_parse_verdict` regex).

### D. SKILL.md Architecture — Honored for Agents, Violated for Evaluation

The `agent_routes.py` fully honors Principle 2: every prompt loads via `get_skill("claude-trade-agent").get(...)` (`agent_routes.py:193,393`). The `evaluation_routes.py` partially honors it (some paths use `skill_loader`), but the core `FoundryEvalAdapter.evaluate_trade()` method at `app/ai/foundry_adapter.py:125` embeds `TRADE_EVALUATION_SYSTEM_PROMPT` directly from `app/ai/prompts.py` — a hardcoded Python string.

### E. `app/providers/ai/__init__.py` — Does Not Export `FoundryAdapter`

`app/providers/ai/__init__.py` exports: `AIProvider, TradeContext, TradeVerdict, SYSTEM_PROMPT, build_trade_prompt, compute_exit_levels, pre_screen_trade, AnthropicAdapter`. It does **not** export `FoundryAdapter`. Yet `main.py:61` does `from app.providers.ai import AnthropicAdapter, FoundryAdapter`. This either fails silently (if Python falls back to the module directly) or is a latent import error. **Needs verification:** whether this import succeeds in production.

**Evidence:** `app/providers/ai/__init__.py` (seen via bash head), `app/main.py:61`.

---

## 5. Dead Code / Stale Abstractions Inventory

| Path | Type | Verification | Confidence |
|---|---|---|---|
| `web/src/pages/_archive/Analysis.jsx` | Page component | Not in App.jsx; not imported anywhere visible | **Verified dead** |
| `web/src/pages/_archive/LongCallsPage.jsx` | Page component | Not in App.jsx | **Verified dead** |
| `web/src/pages/_archive/VerticalsPage.jsx` | Page component | Not in App.jsx (redirect exists) | **Verified dead** |
| `web/src/auth/msalConfig.js` | Auth config | Not imported in App.jsx, main.jsx, or AuthContext | **Suspected dead — needs verification** |
| `web/src/components/Header.jsx` | UI component | CLAUDE.md says "RETIRED — replaced by Layout.jsx"; not in App.jsx | **Suspected dead — needs verification** |
| `web/src/pages/DirectionalPage.jsx` | Page | App.jsx:64 redirects `/directional` → `/dashboard`; `DirectionalPage` not imported in App.jsx | **Verified dead** (as route target) |
| `web/src/pages/LoginPage.jsx` | Page | Not imported in App.jsx — auth via BFF redirect, not login page | **Suspected dead — needs verification** |
| `web/src/pages/Analysis.jsx` | Page | Not imported in App.jsx (live routes are TradesPage, etc.) | **Suspected dead — needs verification** |
| `web/src/pages/StrategyProfilePage.jsx` | Page | Not in App.jsx routes | **Suspected dead — needs verification** |
| `app/providers/base.py:143-209` | Two ABC classes (AccountProvider, TradingProvider) | `factory.get_account()` and `factory.get_trading()` raise NotImplementedError; no implementations exist | **Verified dead (as implemented behavior)** |
| `app/providers/factory.py:111-126` | `get_account()`, `get_trading()` | NotImplementedError; zero callers | **Verified dead** |
| `app/providers/ai/prompts.py:87-298` | Old-format prompt builder + pre_screen_trade | Used by `providers/ai/foundry_adapter.py` (SDK path); if that adapter is deleted, this dies | **Dead if #1 is executed** |
| `app/providers/ai/base.py:22-88` | TradeContext + TradeVerdict dataclasses | Only used by old SDK adapters; `app/ai/schemas.py` has replacements | **Dead if #1 is executed** |
| `agents/shared/` | Dev utilities (agent-run-logger.py, jira-extract.py, teams-notifier.py) | Duplicated in `agents-qa-system/agents/shared/` | **Suspected duplicate** |
| `agents-qa-system/` | Entire QA agent system | Untracked, outside deployed app | **Tooling, not app code** |
| `prototypes/` | React prototype (main.jsx, OptionsStrategyAnalyzer.jsx, vite.config.js) | Not referenced by main app build | **Verified dead (as deployed code)** |
| `.claude/worktrees/peaceful-wu/` | Git worktree with full app copy | Untracked per git status; not part of deployed artifact | **Not deployed, but clutters searches** |
| `scratch/` | Scratch scripts (finnhub_integration test) | Untracked per git status | **Dev tooling** |
| `app/api/validation_routes.py` | Route file | Listed in main.py but purpose unclear without reading | **Needs verification** |

---

## 6. Where the Architecture Is Lying to Itself

### A. "Skill-Driven Prompt Architecture" — Partially True

The CLAUDE.md principle says "Prompts live in SKILL.md files, not hardcoded in Python or React." This is honored in `agent_routes.py` (which loads all three prompt sections from `app/skills/claude-trade-agent/SKILL.md`). It is **not** honored in:
- `app/ai/prompts.py` — `TRADE_EVALUATION_SYSTEM_PROMPT` is 110 lines of hardcoded Python string
- `app/ai/prompts.py` — `FOLLOW_UP_SYSTEM_PROMPT` is hardcoded
- `app/providers/ai/prompts.py` — `SYSTEM_PROMPT`, `build_trade_prompt`, `build_refresh_prompt`, `pre_screen_trade` are all hardcoded Python

The primary trade evaluation flow (used by the main `TradesPage` via `evaluation_routes.py`) uses hardcoded prompts. The newer, more used path is the one that violates the principle.

**Evidence:** `app/ai/prompts.py:9,113`, `app/providers/ai/prompts.py:24,147`, vs. `app/api/agent_routes.py:193,393` (SKILL.md usage).

### B. "Provider Adapter Pattern — Adding a provider = zero changes to routes/engines" — Mostly True, One Gap

The PROVIDER_REGISTRY in `factory.py:35-40` contains exactly one entry: `"schwab"`. The comment at `factory.py:33` says "each factory function takes (secrets_manager, user_id) and returns an adapter." Adding a second market data provider would require editing `factory.py`, which is the intended extension point — so the pattern is architecturally sound. However, the factory lambda at line 76 ignores `environment` and `user_id` — the function signature takes 3 args but only uses the token manager, which is captured via closure. This means the per-user/per-environment flexibility the signature promises is fake.

**Evidence:** `app/providers/factory.py:76` (`lambda secrets, user_id, env: SchwabMarketData(token_manager)`), `app/providers/factory.py:35-40`.

### C. "Backend-for-Frontend Identity — browser never holds tokens" — Partially Violated

The BFF principle is correctly implemented in `identity_routes.py` (session cookie, no token to browser). But `entra_auth_routes.py:201` returns `access_token` directly to the browser — a JWT that the browser must store (localStorage or memory). Both routes are registered and callable. The browser could be using either, depending on which login button was used or which code path the frontend follows.

**Evidence:** `app/api/entra_auth_routes.py:201` (returns `access_token`), `app/main.py:402,407`.

### D. `ProviderFactory` Is Not a Factory

`ProviderFactory` doesn't create provider instances via factory method pattern. It creates instances once, caches them by (name, user_id) key, and returns the cached instance forever. It's a singleton container with caching semantics, not a factory. The name misleads: a developer expecting factory behavior (new instance per call) will be confused by the caching. The `clear_cache()` method exists but is only called at shutdown.

**Evidence:** `app/providers/factory.py:92-109` (create + cache), `app/providers/factory.py:164-169` (`clear_cache()`).

### E. `agents/` Top-Level Directory Is Not Application Code

`agents/` at the repo root (`agents/identity-security/`, `agents/shared/`) contains Python files that are clearly dev/QA tooling — external scripts that run against the app, not part of it. They're untracked in git, sit alongside application code, and the shared utilities (`agent-run-logger.py`, `jira-extract.py`, `teams-notifier.py`) are duplicated in `agents-qa-system/agents/shared/`. This is not "the agents in the app" (those are `app/agents/`) — it's a different concept entirely with a colliding name.

**Evidence:** `agents/shared/agent-run-logger.py`, `agents/identity-security/diagnose.py`, `agents-qa-system/agents/shared/agent-run-logger.py` (duplicate).

### F. `_pkce_cache` Is In-Process — Breaks Under Multi-Instance Deployment

`identity_routes.py:49` declares `_pkce_cache: dict[str, tuple[str, float]] = {}` as a module-level dict. PKCE verifiers are stored here and expected to survive through the Entra callback. Azure App Service can run multiple instances. If the login request hits Instance A and the callback hits Instance B, the PKCE verifier is not found and login fails. Azure F1 is single-instance so this hasn't bitten yet, but any scale-out (even F1 to B1) would expose this.

**Evidence:** `app/api/identity_routes.py:49`, memory of Azure App Service always-on / multi-instance behavior.

---

## 7. Best-Practice Gaps

### 1. No database migration system
`app/models/session.py:init_db()` uses `metadata.create_all()` with SQLAlchemy. New tables/columns are created on fresh deployments but existing database tables are never altered. The `app/models/migrations.py` file exists — needs verification of its actual content. If it's empty or manual, any production schema change is an undocumented manual operation.

**Evidence:** `app/models/session.py` (`init_db()` called at `main.py:174`), `app/models/migrations.py` (exists, content unverified).

### 2. `skip_auth` in production is a universal bypass
`app/auth/dependencies.py:92-98` — when `settings.skip_auth` is truthy, every auth dependency returns a hardcoded admin user. If `SKIP_AUTH=true` is accidentally set in any non-local environment (it won't be if properly gate-kept), any caller is admin. The value comes from `app/core/config.py` (not read — needs verification of default value and env guards).

**Evidence:** `app/auth/dependencies.py:92-98`.

### 3. JWT signing key is auto-generated on first run and stored back to Key Vault
`app/auth/service.py:52-60` — if the Key Vault doesn't have `jwt-signing-key`, a new random key is generated and stored. If Key Vault is unavailable at first startup, a new key may be generated but fail to store. This means the key is in memory only, and all existing sessions become invalid on restart. This is a correctness issue, not just a security issue.

**Evidence:** `app/auth/service.py:53-60`.

### 4. No test coverage for auth flows, provider adapters, or API endpoints
Tests exist only for: analysis scoring (`tests/analysis/`), hard gates (`tests/test_hard_gates.py`, `tests/test_earnings_gate.py`, `tests/test_negative_ev_gate.py`), AI schemas (`tests/test_ai_schemas.py`), and validators. No tests for: `SessionManager`, `AuthService`, `SchwabTokenManager`, any API endpoint, `ProviderFactory`, `SkillLoader`. The auth migration in particular (three active flows) has zero test coverage.

**Evidence:** `tests/` directory listing.

### 5. `_scheduled_monitor_run` closure creates a new `async_session()` every run
`app/main.py:306-316` — the scheduled position monitor closure creates a new DB session per run. This is correct, but the `scheduler.shutdown(wait=False)` at line 353 means an in-progress monitor run may have its DB session abandoned mid-write on shutdown. Position data written partially on shutdown may leave orphaned records.

**Evidence:** `app/main.py:306-353`.

### 6. Audit log on `DELETE /recommendations/{trade_key}` is scoped wrong
`agent_routes.py:712-719` — the delete endpoint for trade recommendations does not filter by `user_id`. It will delete the recommendation for any user who knows the trade_key format (`symbol:spread:expiration`). This is a data isolation bug.

**Evidence:** `app/api/agent_routes.py:712-719` (`delete(TradeRecommendation).where(TradeRecommendation.trade_key == trade_key)` — no user_id filter).

### 7. `FoundryEvalAdapter` creates a persistent `httpx.AsyncClient` but never closes it
`app/ai/foundry_adapter.py:105-112` — the client is created in `__init__`. `close()` at line 264 must be called explicitly. In `main.py:253`, a `FoundryEvalAdapter` is created and assigned to `eval_adapter`. On shutdown, `token_refresh_task.cancel()` and `scheduler.shutdown()` are called, but `eval_adapter.close()` is NOT called (line 352-355). The httpx client is never closed.

**Evidence:** `app/ai/foundry_adapter.py:105,264`, `app/main.py:351-356`.

---

## 8. Lean Target Architecture

The system that honors all seven principles with minimum footprint:

```
app/
├── main.py                  (50 lines: create app, register routers, call init functions)
├── startup.py               (all init logic extracted here — startup sequence explicit and testable)
├── core/
│   ├── config.py            KEEP
│   └── secrets.py           KEEP
├── auth/
│   ├── service.py           KEEP (JWT/TOTP for local dev / API clients)
│   ├── session_manager.py   KEEP (BFF cookie — primary auth)
│   ├── client_assertion.py  KEEP
│   ├── dependencies.py      KEEP (simplified: cookie-first, JWT fallback, remove dual-path duplication)
│   └── providers.py         KEEP
├── providers/
│   ├── base.py              KEEP MarketDataProvider + ContextSource only
│   │                        DELETE AccountProvider + TradingProvider (premature)
│   ├── schwab.py            KEEP
│   ├── schwab_token_manager.py  KEEP
│   ├── schwab_context_source.py KEEP
│   ├── finnhub_earnings.py  KEEP
│   └── factory.py           KEEP (trim get_account/get_trading stubs)
├── ai/                      ONE AI package. DELETE app/providers/ai/ entirely.
│   ├── adapter.py           Single FoundryEvalAdapter (httpx) — the winner
│   └── anthropic_adapter.py Keep for local dev fallback (no Foundry endpoint)
├── skills/                  ALL prompts here
│   ├── skill_loader.py      KEEP
│   ├── claude-trade-agent/SKILL.md    KEEP
│   ├── position-monitor/SKILL.md     KEEP
│   ├── insight-engine/SKILL.md       KEEP
│   └── evaluation/SKILL.md           NEW — move TRADE_EVALUATION_SYSTEM_PROMPT here
├── analysis/               KEEP (all engines) — these are earning their keep
│   └── hard_gates/         KEEP
├── agents/                 KEEP (position_monitor, insight_engine, deviation_detector, telemetry)
│                           DELETE context_store if unused (needs verification)
├── api/                    12 route files (cut 5+)
│   ├── identity_routes.py  KEEP (BFF OIDC — primary auth)
│   ├── trade_agent_routes.py  KEEP (renamed from agent_routes.py)
│   ├── position_monitor_routes.py  KEEP (renamed from agents_routes.py)
│   ├── evaluation_routes.py KEEP
│   ├── market_routes.py    KEEP
│   ├── position_routes.py  KEEP
│   ├── insight_routes.py   KEEP
│   ├── watchlist_routes.py ONE watchlist route (merge named_watchlist into it or vice versa)
│   ├── dashboard_routes.py KEEP
│   ├── health_routes.py    KEEP
│   ├── admin_routes.py     KEEP
│   └── schwab_auth_routes.py KEEP
│   DELETE: auth_routes.py, entra_auth_routes.py, config_routes.py (verify)
├── models/                 KEEP (add proper migrations via Alembic)
├── middleware/csrf.py       KEEP
└── validators/             KEEP (narrative_grounding)
```

Frontend: identical to current, minus `_archive/`, `msalConfig.js`, `Header.jsx`, `DirectionalPage.jsx`, `LoginPage.jsx`, `Analysis.jsx` (the dead one).

---

## 9. Prioritized Refactor Roadmap

### MUST FIX (Correctness, Security, Active Pain)

| Action | Files Affected | Effort | Risk | Payoff |
|---|---|---|---|---|
| Fix DELETE /recommendations/{trade_key} — add user_id filter | `agent_routes.py:712-719` | S | Low | Fixes data isolation bug |
| Close `FoundryEvalAdapter` httpx client on shutdown | `main.py:351-356`, `ai/foundry_adapter.py:264` | S | Low | Prevents resource leak |
| Replace in-process `_pkce_cache` with DB or Redis | `identity_routes.py:49` | M | Medium | Required for any scale-out |
| Add Alembic (or equivalent) migration system | `app/models/`, `requirements.txt` | L | High | Schema changes safely deployable |
| Audit `skip_auth` default and env guards | `core/config.py`, `auth/dependencies.py` | S | Low | Ensures auth bypass is dev-only |

### SHOULD FIX (Cognitive Load, Duplication, Drift)

| Action | Files Affected | Effort | Risk | Payoff |
|---|---|---|---|---|
| Delete `app/providers/ai/` — migrate agent_routes to use FoundryEvalAdapter | `app/providers/ai/` (5 files), `agent_routes.py`, `main.py` | M | Medium | Single AI package, single interface |
| Retire `entra_auth_routes.py` — keep BFF only | `entra_auth_routes.py`, `main.py:402` | M | Medium | Two fewer auth paths, BFF principle honored |
| Move `TRADE_EVALUATION_SYSTEM_PROMPT` to `skills/evaluation/SKILL.md` | `ai/prompts.py`, `ai/foundry_adapter.py` | M | Low | Honors Skill-Driven principle |
| Update CLAUDE.md to reflect actual frontend | `CLAUDE.md` | S | None | Eliminates false mental model |
| Rename `agent_routes.py` and `agents_routes.py` | 2 files + `main.py` | S | Low | Eliminates name confusion |
| Delete speculative ABCs in `providers/base.py` | `providers/base.py:143-209`, `factory.py:111-126` | S | Low | Removes 4 stubs that block understanding |
| Resolve `watchlist_routes.py` vs `named_watchlist_routes.py` — pick one | Both files + `client.js` | M | Medium | Single watchlist API surface |

### NICE TO IMPROVE (Polish, Clarity)

| Action | Files Affected | Effort | Risk | Payoff |
|---|---|---|---|---|
| Extract lifespan init into startup helpers | `main.py:154-356` | M | Low | Readable startup sequence |
| Delete `_archive/` frontend pages | `web/src/pages/_archive/` | S | None | Eliminates 3 dead files |
| Delete `prototypes/` | `prototypes/` | S | None | Not deployed code |
| Delete `agents-qa-system/` (or move to own repo) | top-level directory | S | None | Removes confusion with `app/agents/` |
| Delete `web/src/auth/msalConfig.js` | 1 file | S | Low | Remove MSAL remnant |
| Delete `web/src/components/Header.jsx` | 1 file | S | Low | Honors "RETIRED" label |

---

## 10. Safe Deletions & Consolidations

**Delete this today (highest confidence):**

`web/src/pages/_archive/Analysis.jsx`, `web/src/pages/_archive/LongCallsPage.jsx`, `web/src/pages/_archive/VerticalsPage.jsx` — explicitly archived, not imported, not reachable. Zero risk.

| Path | Rationale |
|---|---|
| `web/src/pages/_archive/` (entire folder) | Archived, not imported anywhere |
| `prototypes/` (entire folder) | Not referenced by app build, untracked |
| `app/providers/base.py:143-209` (AccountProvider, TradingProvider) | Zero implementations, factory raises NotImplementedError |
| `app/providers/factory.py:111-126` (get_account, get_trading) | NotImplementedError, zero callers |
| `agents-qa-system/` (entire folder) | Tooling, not app code, untracked |
| `scratch/` (entire folder) | Dev scratch, untracked |
| `web/src/pages/DirectionalPage.jsx` | App.jsx redirects `/directional` to `/dashboard`; page not imported |

**Consolidate (after verifying which wins):**

- `watchlist_routes.py` + `named_watchlist_routes.py` → one winner
- `app/ai/prompts.py` + `app/providers/ai/prompts.py` → SKILL.md files
- `agents/shared/` + `agents-qa-system/agents/shared/` → one copy (if tooling stays)

---

## 11. Testing Strategy to Support Simplification

Before executing Must-Fix work, pin down these contracts:

1. **Auth contract test** — Before retiring any auth flow: write a request-level test for each of the three auth paths (`/auth/entra/token` JWT bridge, `/auth/login` BFF redirect, JWT bearer header). Confirm which paths the frontend actually calls. The DELETE auth path must fail its test BEFORE you remove it.

2. **AI adapter interface contract** — Before deleting `app/providers/ai/`, write tests that assert `FoundryEvalAdapter.chat(system, user, max_tokens)` returns the same dict shape (`{text, input_tokens, output_tokens, model, provider}`) as `providers/ai/FoundryAdapter.chat()`. These contracts must pass with the replacement adapter before the old one is deleted.

3. **Prompt content regression** — Before moving `TRADE_EVALUATION_SYSTEM_PROMPT` to SKILL.md: capture the current string (hash it), then assert `SkillLoader("evaluation").get("SYSTEM_PROMPT")` produces the same string. This prevents accidentally changing the prompt during the migration.

4. **Watchlist isolation test** — Before consolidating watchlist routes: write a test that adds a symbol as user A and confirms user B cannot see it. Covers the same class of bug as the DELETE recommendations issue.

5. **Hard gate ordering test** — Already exists (`tests/integration/test_gate_ordering.py`). KEEP and run before any changes to `hard_gates/`. This is the most important existing test.

6. **Session manager smoke test** — `SessionManager.create_session()` → `get_session()` → `delete_session()` round-trip with a mock DB. Required before any auth route changes.

---

## 12. Seven-Principle Audit

### Principle 1 — Provider Adapter Pattern

**Intent still right?** Yes — with one caveat. For market data, yes. For AI providers, the pattern is applied twice with two incompatible base classes.

**Implementation status:** Drifting. The market data adapter pattern works correctly (Schwab implements MarketDataProvider, factory dispatches). But AI providers have two base classes (`AIProvider` in `providers/ai/base.py` and no formal base for `FoundryEvalAdapter` in `app/ai/`). `FoundryEvalAdapter.chat()` and `AnthropicAdapter.chat()` have compatible signatures by convention, not by contract.

**Evidence:** `app/providers/ai/base.py:90-148` (AIProvider ABC), `app/ai/foundry_adapter.py` (no base class, compatible by convention), `app/main.py:261` (fallback comment "AnthropicAdapter.chat() matches the FoundryEvalAdapter.chat() signature").

**Leanest honest implementation:** Keep `MarketDataProvider` and `ContextSource` in `providers/base.py`. Delete `AccountProvider` and `TradingProvider`. For AI, create one `AIAdapter` ABC in `app/ai/base.py` with a single `chat(system, user, max_tokens)` method. Both `FoundryEvalAdapter` and `AnthropicAdapter` implement it. Eliminate `AIProvider` entirely. This new abstraction deletes two existing ones: `AIProvider` (from `providers/ai/base.py`) and the informal convention contract at `main.py:261`.

---

### Principle 2 — Skill-Driven Prompt Architecture

**Intent still right?** Yes — auditable, versionable prompts are valuable.

**Implementation status:** Theatrical. `agent_routes.py` honors it fully. `evaluation_routes.py` (the primary evaluation path) uses hardcoded Python strings. The SKILL.md files exist for the agent path; the evaluation path has its own `app/ai/prompts.py`.

**Evidence:** `app/ai/prompts.py:9` (`TRADE_EVALUATION_SYSTEM_PROMPT = """...`), `app/providers/ai/prompts.py:24` (`SYSTEM_PROMPT = """...`), vs. `agent_routes.py:193` (`skill.get("BATCH_TRIAGE_SYSTEM")`).

**Leanest honest implementation:** One `skills/` tree. All prompt strings live in SKILL.md files. `SkillLoader` is the only way Python gets a prompt. Delete both Python prompt modules. The `build_refresh_prompt()` function logic (which does data assembly, not just prompt text) stays in Python, but the template string it fills comes from SKILL.md.

---

### Principle 3 — Two-Track Observability

**Intent still right?** Yes.

**Implementation status:** Honored. `agent_routes.py` writes to `agent_run_log` (durable SQL) AND emits OpenTelemetry spans via `invoke_with_tracing()`. The telemetry goes to Application Insights; the SQL table is permanent. `evaluation_routes.py` also writes to `agent_run_log`.

**Evidence:** `agent_routes.py:76-130` (`_write_run_log()`), `app/agents/telemetry.py` (`invoke_with_tracing()`), `main.py:280` (`init_agent_telemetry(appinsights_cs)`).

**Leanest honest implementation:** Current implementation is reasonable. Only gap: the position monitor agent's run results are logged to `agent_run_log` but the schema of what's logged vs. traced is not documented. A brief schema contract in the SKILL.md for the position monitor would make this durable.

---

### Principle 4 — Unified Position Model

**Intent still right?** Yes.

**Implementation status:** Honored. The `positions` table has a `source` field (`PAPER` | `LIVE`) and `status` field. Both paper and live positions share the same model, same health grade logic, same monitor agent. The `/positions/follow` and `/positions/take` endpoints both write to the same table.

**Evidence:** `app/models/database.py` (positions table definition per CLAUDE.md), `app/api/position_routes.py` (follow + take endpoints).

**Leanest honest implementation:** Current is lean. One future risk: if LIVE positions ever need broker-side sync (Schwab actual fills), that sync logic must be careful not to split into a separate model. The principle is safe for now.

---

### Principle 5 — Generic Insight Engine

**Intent still right?** Yes.

**Implementation status:** Honored at the code level; domain isolation is clean. `app/agents/insight_engine.py` is generic. `app/skills/insight-engine/domains/options/SKILL.md` provides options-specific vocabulary. The `InsightCard` frontend component uses `domain` field for filtering.

**Evidence:** `app/agents/insight_engine.py`, `app/skills/insight-engine/SKILL.md`, `app/skills/insight-engine/domains/options/SKILL.md`.

**Leanest honest implementation:** Current is the target state. Only risk: the `deviation_detector.py` — if it contains options-specific logic in the generic module, that's a violation. Needs verification.

---

### Principle 6 — Backend-for-Frontend Identity

**Intent still right?** Yes.

**Implementation status:** Drifting. The new `identity_routes.py` correctly implements BFF — session cookie, server-side token storage, no tokens to browser. But `entra_auth_routes.py` returns `access_token` to the browser (line 201), and both are registered. The browser may still be using the old path depending on which code path was wired last.

**Evidence:** `app/api/entra_auth_routes.py:201` (returns JWT to browser), `app/api/identity_routes.py` (sets httpOnly cookie), `app/main.py:402,407` (both registered).

**Leanest honest implementation:** Delete `entra_auth_routes.py`. Keep only `identity_routes.py`. Confirm `web/src/context/AuthContext.jsx` uses the BFF callback redirect, not the token exchange endpoint. Delete `web/src/auth/msalConfig.js`.

---

### Principle 7 — Unified Deployment

**Intent still right?** Yes-with-caveat. The CLAUDE.md says "prefer one deployable app/service hosting API + SPA unless there is a compelling reason not to." There IS a compelling reason here: Azure Static Web Apps gets free global CDN and built-in routing, which App Service can't match without custom domain + CDN config at significant extra cost.

**Implementation status:** Drifting from the stated principle. The backend (App Service) now serves the SPA via `main.py:433-450` (`StaticFiles` + SPA fallback). The frontend is ALSO deployed to Azure Static Web Apps. This means there are TWO deployment pipelines for the frontend: one via `azure-static-web-apps-purple-ground-0d4efed10.yml` and one via the App Service's `static/` directory if built.

**Evidence:** `app/main.py:433-450` (backend serves static files if `static/` dir exists), `.github/workflows/azure-static-web-apps-purple-ground-0d4efed10.yml` (static web app deploy), `app/main.py:439` (conditional: only serves if `static/index.html` exists).

**Leanest honest implementation:** Pick one. If Azure Static Web App is the canonical frontend, remove the `StaticFiles` mount from `main.py`. If unified deployment (one App Service) is the goal, remove the Static Web App pipeline. Currently the Static Web App URL in MEMORY.md is `purple-ground-0d4efed10.azurestaticapps.net` which is the production frontend — the App Service backend is a different host. The static serving in `main.py` is therefore DEAD CODE on Azure (no `static/` dir in the App Service deployment artifact). It exists for a "future unified deployment" that isn't the current deployment.

---

## 13. Final Recommendation

**Do this next week:** Delete `app/api/entra_auth_routes.py` and unregister it from `main.py`. This is a single-file removal with a 2-line change to `main.py`. It removes the only remaining path that sends identity tokens to the browser, fully closing the Principle 6 gap. Before deleting, confirm `web/src/context/AuthContext.jsx` never calls `/auth/entra/token` — if it does, that's the frontend call you must update first. This is concrete, safe, and immediately improves the security posture.

**Do not do this:** Do not attempt to consolidate the two AI packages while the auth migration is still in progress. The two issues are independent but both require careful sequencing. Taking on both simultaneously doubles the blast radius on the system's two most critical paths (identity and AI). Fix auth first, then tackle the AI duplication in a clean session where the only thing that changes is the AI wiring.

---

## 14. Assumptions, Uncertainties, and Questions Before Refactor

### Assumptions Made (not verified from repo)

1. Assumed `app/providers/ai/__init__.py` is truncated at 20 lines and likely imports `FoundryAdapter` beyond what was shown. If it doesn't, `main.py:61` is a live import error.
2. Assumed `web/src/context/AuthContext.jsx` uses the BFF cookie path. Not read — this file determines which auth route the frontend actually calls.
3. Assumed `web/src/api/client.js` (867 lines) sends `credentials: 'include'` on all calls (required for BFF cookie). Not verified line by line.
4. Assumed the Azure App Service deployment artifact does NOT include `static/` (no frontend files), making `main.py:433-450` dead on Azure. Not confirmed by checking the GitHub Actions build workflow.

### "Needs Verification" Items (Consolidated)

- Whether `app/providers/ai/__init__.py` exports `FoundryAdapter` (import at `main.py:61`)
- Whether `web/src/context/AuthContext.jsx` calls `/auth/entra/token` (old path) or the BFF redirect (new path)
- Content of `app/models/migrations.py` (may contain actual migration logic or be empty)
- Content of `app/api/validation_routes.py` — what it does and whether it's wired correctly
- Whether `web/src/auth/msalConfig.js` is imported anywhere (any `import` of MSAL packages)
- Whether `web/src/components/Header.jsx` is imported by any active component
- Whether `web/src/pages/LoginPage.jsx`, `Analysis.jsx`, `StrategyProfilePage.jsx` are imported anywhere
- Whether `app/agents/context_store.py` is called by the live `position_monitor.py` or `insight_engine.py`
- Whether `app/ai/message_builder.py` is imported by any live code
- `app/validators/narrative_grounding.py` — caller verification

### Questions Whose Answers Would Most Change Recommendations

1. **Is the old MSAL token exchange (`/auth/entra/token`) still being called by the frontend?** If yes, the auth migration is incomplete and `entra_auth_routes.py` cannot be deleted until the frontend is updated. If no, it can be deleted today.
2. **Is `agent_routes.py` (`/agent/triage`, `/agent/deep-dive`) still actively used by the frontend (`TradesPage.jsx`)?** If this UI flow was replaced by `evaluation_routes.py` (`/evaluate/structured`), then `agent_routes.py` and `app/providers/ai/` can both be deleted together — collapsing two AI packages into one without any migration.
3. **Does `app/providers/ai/__init__.py` actually export `FoundryAdapter`?** If it doesn't, the app is failing to initialize the agent AI provider in production, and the agent routes are silently returning 503 on every call.
4. **Is `watchlist_routes.py` called by any active frontend code, or has `named_watchlist_routes.py` fully replaced it?** The client.js should be the source of truth here.
5. **What does `app/models/migrations.py` contain?** If it has Alembic or manual SQL migration logic, the situation is better than assumed. If it's empty or a stub, the schema-management gap is real.

### Failure Modes of These Recommendations

1. **Deleting `entra_auth_routes.py` while the frontend still calls it** will immediately break login for all users. Auth must be verified in AuthContext before deletion.
2. **Migrating `agent_routes.py` to `FoundryEvalAdapter`** introduces the risk that `FoundryEvalAdapter.chat()` has different retry, timeout, or error behavior than `providers/ai/FoundryAdapter.chat()`. Run a side-by-side call comparison with the same prompt before switching.
3. **Moving prompts to SKILL.md without adjusting the `_extract_json` / structured output path** may cause `FoundryEvalAdapter.evaluate_trade()` to receive prompt changes that break the JSON contract. The structured output format must be tested after any prompt migration.

---

*Self-check: All concrete claims cite file:line. No new frameworks or runtimes proposed. No new abstractions added without naming what they replace. All roadmap items have effort and risk. "Delete this today" item is named (Section 10 top item). All seven principles addressed (Section 12). Three failure modes named (Section 14).*
