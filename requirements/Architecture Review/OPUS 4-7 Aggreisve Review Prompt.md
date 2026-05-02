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
- Every concrete claim must cite evidence as one of:
    - path/to/file.ext:LINE
    - path/to/file.ext:LINE-LINE
    - path/to/file.ext (with the symbol/class/function/route name named explicitly)
    - path/to/dir/ when the claim is about structure rather than code behavior
- Prefer exact line citations whenever practical.
- If exact lines are not practical for a structural claim, cite the file and the relevant
  symbol/section and mark the claim as structural rather than line-specific.
- Do not fabricate precision. If you cannot cite precisely, say "needs verification."
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
  - Exclude generated, vendored, and build-artifact paths from architectural judgment
  unless they are directly implicated in runtime behavior or deployment:
    - node_modules/
    - .next/
    - dist/
    - build/
    - coverage/
    - .venv/ / venv/
    - compiled assets
    - lockfiles
    - generated code
- You may note if generated artifacts are incorrectly committed, but do not spend review
  effort treating them as architecture.

================================================================
PHASE 1 — DOCUMENTATION RECON (do this first, do not skip)
================================================================
IMPORTANT: DO NOT TREAT THE ARCHITECTURE DOCS AS SACRED

You should read documents like CLAUDE.md, architecture-plan.md, and auth-process.md
first and use them to understand intended architecture and design intent.

However, do NOT assume those documents are fully correct, current, or optimal.

You are explicitly allowed — and expected — to challenge the assumptions in those
documents, including:
  - whether the prescribed patterns are still justified
  - whether the architecture is more abstract or generalized than the system actually needs
  - whether documented separations of responsibility are still useful
  - whether documented extensibility assumptions are real or speculative
  - whether the docs preserve complexity that no longer earns its keep
  - whether the documented architecture is too heavy for the current scale and team
  - whether the docs themselves are a source of drift, over-design, or architectural inertia

Distinguish clearly between:
  1. implementation drift from documented intent
  2. documentation drift from current reality
  3. flawed or outdated assumptions in the documented architecture itself

If you conclude that a documented architectural assumption should be challenged, say so
explicitly and explain:
  - what the assumption is
  - why it may no longer be justified
  - what simpler assumption or design principle should replace it

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
Five to ten sentences. Plain language. What is the overall health of
the codebase, what are the two or three things that matter most, and
what is the single highest-leverage move this team could make this
month. End with a one-line verdict.

## 2. Current Architecture As Implemented
A faithful description of what the code actually does today, not what
the docs say it does. Backend shape, frontend shape, auth shape,
provider shape, AI/skills shape, deployment shape. Include a simple
ASCII or bulleted topology if it helps. Cite anchor files.

Start from the real entry points first:
- backend app startup / main entry
- frontend app bootstrap / router root
- auth login/callback/session endpoints
- provider factory/registry entry points
- AI invocation entry points
- deploy/build entry points

Then walk inward toward helper layers.
Do not start from leaf utilities unless they are clearly central.

For each major concern (auth, config, provider routing, prompt loading, position state,
observability, deployment), identify the canonical owner module.
If there is no clear canonical owner, say so explicitly.
``

## 3. Top 10 Simplification Opportunities (Ranked)
Ranked by (impact ÷ effort). For each:
  - Title
  - What to do (concrete, one or two sentences)
  - Why it matters (cognitive load, deploy friction, drift, cost)
  - Evidence (files:lines)
  - Estimated effort: S / M / L
  - Risk: Low / Medium / High
  - What it deletes or merges

## 4. Architectural Drift Findings
Where the implementation has drifted from the intended architecture,
with citations. Include partial migrations and old+new coexistence.

## 5. Dead Code / Stale Abstractions Inventory
A list. For each item: path, type (module/route/component/helper/
config/flag/script), verification you ran, and confidence
(verified dead / suspected dead — needs verification).

When judging dead code, prefer runtime-path evidence over stylistic suspicion.
A file is not dead merely because it looks old.
A file is a deletion candidate when active execution paths, imports, route registration,
DI wiring, test references, docs references, and build references all fail to justify it.

If a file is only reachable through dynamic import, reflection, configuration lookup,
or string-based registration, say so explicitly and lower confidence accordingly.


## 6. Where the Architecture Is Lying to Itself
The hardest section. Places where the names, the docs, or the structure
imply one thing and the code does another. Fake flexibility. Strategies
with one strategy. Generic engines that aren't generic. BFFs that leak
tokens to the browser. Skill-driven prompts that are actually inline.
Be direct. Cite.

## 7. Best-Practice Gaps
Real, concrete gaps — not generic advice. Examples that count:
secrets handling, error boundaries, request idempotency, migration
hygiene, test coverage of critical paths, audit-record durability,
build reproducibility. Examples that do not count: "consider adding
more tests," "improve documentation."

## 8. Lean Target Architecture
Describe the simplest version of this system that still honors the
seven protected principles at the intent level. Be concrete: name the
modules that survive, the ones that merge, and the ones that die.
Show the topology. This is the destination the roadmap is aiming at.

## 9. Prioritized Refactor Roadmap
Three buckets. Each item must include: action, files affected,
estimated effort (S/M/L), risk, and the user-visible or
developer-visible payoff.
  - MUST FIX (correctness, security, deploy fragility, drift that is
    actively causing pain)
  - SHOULD FIX (cognitive load, duplication, ceremonial abstraction)
  - NICE TO IMPROVE (renames, doc cleanup, polish)

## 10. Safe Deletions & Consolidations
The subset of the roadmap that can be done immediately with low risk.
For each, give the exact paths and a one-line rationale. Include the
single highest-confidence "delete this today" item at the top.

## 11. Testing Strategy to Support Simplification
What tests must exist or be added BEFORE the Must-Fix work begins, so
that simplification is safe. Be specific about what to pin down
(contracts, golden outputs, auth flows, provider adapter behavior)
rather than asking for "more coverage."

## 12. Seven-Principle Audit
For each of the seven protected principles, in order:
  - Intent still right? (yes / yes-with-caveat / reconsider)
  - Implementation status (honored / drifting / theatrical)
  - Evidence (files:lines)
  - Leanest honest implementation (one paragraph)

## 13. Final Recommendation
Three to six sentences. If you had to pick ONE thing this team should
do next week, what is it and why. Then the ONE thing they should NOT
do, even though it might be tempting.

Also state explicitly:
- the one area the team should tackle first
- the one area the team should defer until tests or contracts are stronger
- the one area that may look ugly but is not actually the highest-leverage simplification target

## 14. Assumptions, Uncertainties, and Questions Before Refactor
List every assumption you made that you could not verify from the
repo. List every "needs verification" item from earlier sections in
one place. List the questions whose answers would most change your
recommendations.

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