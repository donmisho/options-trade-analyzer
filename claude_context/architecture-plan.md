# architecture-plan.md

**Last Updated:** 2026-05-18 UTC
**Instigating Ticket:** OTA-535 (Architecture Optimization Framework v1 Epic; absorbs cancelled OTA-244, OTA-246, OTA-247, OTA-474, OTA-475, OTA-521; merges and supersedes project-hierarchy.md; incorporates findings from the 2026-04-30 GPT-5.4 and Opus-4.7 architectural reviews; adds OTAR roadmap reference per OTA-495; links to OTAR-24 and OTAR-27)

---

This document is the architectural specification for the Options Trade Analyzer. It describes *why* the system is designed the way it is, what the foundational patterns are, how data and credentials flow through it, and how the code is organized into deployable units.

It is the source of truth for architecture. It is **not** the source of truth for business rules (formulas, gates, thresholds, computation), workflow (Jira, dev environment, deploy procedures), UI presentation, or auth flow specifics. Each of those has its own document. See **Source of Truth Documents** below.

This document supersedes `project-hierarchy.md`. The directory tree, API endpoint inventory, Azure resources table, and phase tracker that previously lived in `project-hierarchy.md` have been merged into the relevant sections here. `project-hierarchy.md` is scheduled for deletion under the Architecture Optimization Epic.

When this document and the actual code disagree, the disagreement is documented in the **Cleanup Roadmap** appendix at the bottom of this file. If the disagreement is not in the appendix, this document is wrong and should be updated; raise a ticket and add a change log entry.

---

## Source of Truth Documents

| Document | Subject |
|---|---|
| `CLAUDE.md` | Workflow, session protocol, Jira mechanics, dev environment, deploy procedures, house style |
| `architecture-plan.md` (this file) | Architectural patterns, system structure, data models, agent inventory, deployment architecture, phase history |
| `business-rules.md` | Scoring formulas, hard gates, PoP computation, health grade math, position lifecycle states, signal TTLs, validation baseline, cost guardrails |
| `UI-GUIDANCE.md` | UI visual contract — layout decisions, component patterns, color tokens, typography, dashboard rules |
| `auth-process.md` | Auth flows end-to-end — BFF OIDC, session lifecycle, PKCE, CSRF, token refresh, identity provider configuration |
| `SCHWAB-LOGIN-PROCESS.md` | Schwab OAuth flow specifically — authorization code flow, token manager behavior, refresh handling, dev cert requirements |
| `azure-naming-conventions.md` | Azure resource naming standards, tagging conventions, environment suffixes |

Conflict precedence: each document is authoritative within its own subject. Business rules referenced anywhere in this document point back to `business-rules.md`; if a rule is restated here, treat the restatement as illustrative and the canonical source as `business-rules.md`.

## Roadmap Reference

Strategic prioritization lives in the Jira Product Discovery project [OTA Roadmap (OTAR)](https://tmtctech-team.atlassian.net/jira/polaris/projects/OTAR). OTAR holds 12 strategic Categories that group all OTA delivery work. Each Epic in the OTA software project links to one OTAR Category via a Polaris work item link.

The architectural patterns and engines documented in this file map onto OTAR Categories as follows:

- **Pattern 6 (BFF Identity), `auth-process.md`** → OTAR-15 (Identity & Access)
- **Pattern 1 (Provider Adapter), Schwab integration, `SCHWAB-LOGIN-PROCESS.md`** → OTAR-19 (Data Sources & Market Intelligence)
- **Strategy System, scoring engines** → OTAR-7 (Trade Evaluation Quality), OTAR-9 (Strategy-to-Trade Journey)
- **Trade Evaluation flow, Black-Scholes Probability Matrix** → OTAR-7 (Trade Evaluation Quality), OTAR-8 (Trade-to-Strategy Journey)
- **Positions System (Pattern 4), Position Monitor Agent** → OTAR-10 (Position Management & Monitoring)
- **Hard Gates Pipeline, Validation Baseline** → OTAR-7 (Trade Evaluation Quality), OTAR-21 (Backtesting & Strategy Validation)
- **Insight Engine (Pattern 5), Multi-Agent Future, Agent 365 Readiness** → OTAR-16 (Insights & Agentic Platform)
- **Pattern 7 (deployment topology), Schema Migration Strategy, Resource Shutdown Discipline, Two-Track Observability (Pattern 3), `azure-naming-conventions.md`** → OTAR-24 (Platform Architecture, Operations, and Observability)
- **Backtesting Engine (planned)** → OTAR-21 (Backtesting & Strategy Validation)
- **UX Foundation, `UI-GUIDANCE.md`** → OTAR-23 (UX Foundation & Design System)
- **Trade Discovery, Scan v3, Named Watchlists, Symbol Search** → OTAR-11 (Trade Discovery & Scanning)
- **Live Trading (Phase 5)** → OTAR-12 (Live Trade Execution)

Historical delivery history (which features shipped when) lives in git history and Production Deployed Jira tickets. The Phase History section in §7 describes the system as it stands, not its evolution.

---

## ADR-1: Scoring Architecture — Deterministic Code with Agent-Driven Judgment

**Decision Date:** 2026-05-18 UTC
**Status:** Accepted

**Decision:** Do not consolidate code-based scoring into an LLM agent. The 15 bright-line scoring sites (strategy scorer, vertical engine, long option engine, strategy routing, strategy classifier, hard gates, asymmetry penalty, verdict banding, Black-Scholes matrix, health grade, narrative grounding validator) remain code-based. The 3 judgment sites (Claude Deep Dive Evaluation, Position Monitor Agent, Insight Engine) remain in their existing SKILL.md-mediated agent paths. Consumer-wiring deduplication (frontend strategy-configs mirror, score color threshold unification) proceeds as follow-up housekeeping work under the Architecture Optimization Epic.

**Scope:** No scoring sites move to agent. Existing agent-driven judgment paths (evaluation_routes.py Claude call, position_monitor.py, insight_engine.py) are unchanged. Frontend strategy metadata deduplication (web/src/strategy-configs/ → API-served config) and score color constant unification are the recommended follow-up.

**Constraints:**
- Scoring engines must remain deterministic to preserve D2/D3/D4 QA harness assertions at byte-equality tolerance.
- SKILL.md files remain the source of truth for all Claude prompt content; skill edits follow the governance model in the discovery document (Don approval, harness validation gate, git-versioned content hash).
- No page-load or timer-driven Claude calls for scoring (cost guardrail from business-rules.md applies).
- Frontend strategy metadata must be served from the backend STRATEGIES dict, not maintained as a static copy, to eliminate the structural source of compatibility drift.

**Supporting discovery:** The full 19-site catalog, latency analysis, cost projection, determinism analysis, reproducibility model, and governance model that informed this decision are archived at `docs/decisions/OTA-653-scoring-agent-discovery.md`.

**Change Log**

| Date | Story | Change |
|---|---|---|
| 2026-05-18 UTC | OTA-653 | Initial decision recorded. Scoring agent adoption declined: bright-line sites are deterministic and correct, judgment sites are already agent-driven, consolidation would degrade harness determinism assertions and increase cost and latency without quality benefit. |

---

# 1. Background and Patterns

## Core Architectural Patterns

These seven patterns are permanent foundations. Every new feature must align with them. The implementations of some patterns currently drift from the principle (the dual AI stack and the lingering MSAL auth bridge are the worst); those drifts are tracked in the **Cleanup Roadmap** appendix and are being actively addressed under the Architecture Optimization Epic. The principles themselves are not in question.

### Pattern 1 — Provider Adapter Pattern

All external sources — market data, AI models, brokerages, signal sources — implement a standard interface. Adding a new source requires writing one adapter class. Engines, routes, and the frontend never change. Each provider owns its own credential lifecycle (OAuth, federation, API key, service account); the calling code calls `provider.fetch()` and never knows how the credential was obtained. Provider lifecycle states (Active / Inactive / Deprecated / Removed) are first-class — see §3 for the full state machine.

### Pattern 2 — Skill-Driven Prompt Architecture

Every AI prompt lives in a `SKILL.md` file under `app/skills/{skill_name}/SKILL.md`. Python loads them via `app/skills/skill_loader.py`. No prompts are hardcoded in Python or React. Prompts are versionable, auditable, and tunable without code changes. The prompt version is recorded with every AI call in the `agent_run_log` audit table. This pattern is honored by `agent_routes.py` today; the trade-evaluation pipeline currently violates it with hardcoded strings in `app/ai/prompts.py` (see Cleanup Roadmap).

### Pattern 3 — Two-Track Observability

Every AI invocation produces two records simultaneously: an OpenTelemetry trace into Application Insights (`ota-insights`) for real-time monitoring, and a permanent business record in the `agent_run_log` SQL table for forever audit. The SQL record links back to the OTel trace via `trace_id`. This allows correlating "what did Claude recommend" with "what actually happened to the position." See §6 for deep-dive.

### Pattern 4 — Unified Position Model

Paper follows and live trades share an identical data model. The only distinguishing fields are `source` (PAPER | LIVE) and `status` (FOLLOWING | LIVE | CLOSED). The Positions page, monitoring agent, and aggregate analytics work identically for both. Live execution flips `source` from PAPER to LIVE without touching any other infrastructure. See §5 for the lifecycle and §business-rules.md for the state-transition rules.

### Pattern 5 — Generic Insight Engine

The Insight Engine is a domain-agnostic detect → score → communicate pattern. It is deployed first in the options domain but is designed for reuse in manufacturing, customer health, and any other monitoring scenario. Domain-specific behavior lives in per-domain `SKILL.md` files (`app/skills/insight-engine/domains/{domain}/SKILL.md`) and per-domain `ObservationSource` adapters. The deviation detection, insight data model, dashboard rendering, and dismissal flow are generic. See §5 for the full architecture and §1 Cross-App Reuse Plane for the multi-app strategy.

### Pattern 6 — Backend-for-Frontend Identity

FastAPI is the OIDC confidential client. The browser never holds an identity token. Auth state lives in an HttpOnly session cookie backed by a server-side session row encrypted with Fernet. PKCE protects the auth code exchange; signed state tokens prevent replay; CSRF middleware protects state-mutating endpoints. Per-IdP configuration is encapsulated in a provider registry so additional identity providers can be added without changing routes. The deep-dive lives in `auth-process.md`.

### Pattern 7 — Single Origin via Cloudflare → App Service

Each environment uses Cloudflare to proxy its custom domain directly to the App Service, which serves both the API and the SPA from a single origin:

- `oa-dev.tmtctech.ai` → Cloudflare → `options-analyzer-api-dev` (App Service, custom domain bound)
- `oa.tmtctech.ai` → Cloudflare → `options-analyzer-api` (App Service, custom domain bound)

The `build-on-push.yml` workflow builds the React SPA (`npm run build` in `web/`), copies the output to a `static/` directory, and bundles it alongside `app/` in the deployment artifact. At runtime, FastAPI serves the API at `/api/v1/*`, `/health`, and `/docs`, then falls back to the SPA via a `/{path:path}` catch-all route in `main.py` that serves `static/index.html` for any unmatched path. Same-origin is trivial — the API and SPA share the same App Service origin, so BFF session cookies (`HttpOnly`, `SameSite=Lax`) are sent on every request without proxy workarounds.

A Static Web App resource (`options-analyzer-web`, Free SKU) exists in the resource group and has its own deploy-on-push pipeline (`azure-static-web-apps-purple-ground-0d4efed10.yml`), but it is **not in the request path**. Cloudflare routes both custom domains to the App Service directly. The SWA is an orphan from an earlier architecture iteration and is a candidate for cleanup (see Cleanup Roadmap).

---

## Three-Layer Architecture

The system is conceptually three layers, each with a different cadence and a different audience.

**Layer 1 — Execution.** Synchronous user-driven work: market data fetch, option chain analysis, scoring, evaluation requests. The user is waiting. Latency budget is seconds. This is the FastAPI request/response path.

**Layer 2 — Orchestration.** Scheduled and event-driven background work: position monitoring, daily snapshots, insight generation, scheduled re-evaluation. The user is not waiting. Latency budget is minutes. This is the APScheduler-driven background job path.

**Layer 3 — Management (Agent 365).** Long-running, cross-cutting agents that observe, summarize, and escalate. Today this is the Insight Engine and the Position Monitor Agent. Future agents (the Multi-Agent Future, see §4) live here. Latency budget is hours-to-days. The audience is Don, not the immediate user session.

The layers communicate through the SQL database. They do not call each other directly. A Layer 2 monitor that detects a deviation writes to `insights`; the next Layer 1 page load reads from `insights`. This decoupling means a slow agent never blocks a user request, and a misbehaving agent doesn't take down the request path.

---

## Cross-App Reuse Plane

OTA is the first application in a planned TMTC ecosystem of AI-driven applications. A second application (a manufacturing operations / customer-health platform) is on the horizon and is intended to share infrastructure with OTA at the framework level. This plan is reflected in current decisions in three concrete ways.

**Per-app storage accounts.** OTA's unstructured storage lives in `otaunstructured` (Standard LRS, West US 2, in `options-analyzer-rg`). The manufacturing app will get its own `mfgunstructured` account in its own resource group. One storage account per application domain — never a shared "tmtc-shared-storage" pattern.

**Insight Engine as cross-domain.** Pattern 5 is intentionally domain-agnostic. The options-domain `SKILL.md` and `ObservationSource` adapters are isolated under `app/skills/insight-engine/domains/options/`. When the manufacturing app ships, its insight engine reuses the same generic core with `domains/manufacturing/` SKILL.md files and adapters. Domain-specific options logic must never leak into the generic engine; if it would, it gets refactored before merge.

**Framework-portable component tagging.** Components in `web/src/` that are intended for cross-app reuse are tagged `framework-portable` (e.g., `SymbolSearch`). The tag is a signal to maintainers that the component should not absorb OTA-specific assumptions. Same convention applies to backend modules where appropriate.

What is *not* cross-app: scoring engines (`app/analysis/`), strategy definitions, hard gates, the Schwab adapter, the trade evaluation prompt schema, and anything in `app/skills/claude-trade-agent/`. These are options-domain logic and will not appear in the manufacturing app.

The cross-app boundary is enforced by the SKILL.md domain split, the `framework-portable` tag, and per-app storage accounts. There is no formal package boundary today; if the cross-app surface grows large enough to warrant one (e.g., extracting the Insight Engine into a Python package), that's an explicit future decision.

---

## End-to-End Data Flow

This is the cross-cutting walk through how a single user action moves through the system. It ties the patterns and engines together.

A user opens the Trades page for AAPL and clicks "Find trades."

1. **Request enters Layer 1.** The browser sends a request to `/api/v1/analyze/verticals?symbol=AAPL` with the session cookie. SWA proxies it to App Service.
2. **Auth dependency resolves.** FastAPI's `get_session_user` dependency reads the cookie, looks up the session in `sessions`, decrypts the Fernet payload, returns the `User` object. If the session is expired or missing, the request returns 401 and the BFF redirect kicks in (see `auth-process.md`).
3. **Provider routing.** The route calls `_get_provider("market_data")` which consults the `PROVIDER_REGISTRY` and returns the Active Schwab adapter (Pattern 1). The adapter's credential lifecycle is opaque to the route — it pulls the current Schwab access token from `SchwabTokenManager` (which itself reads/refreshes from Key Vault), but the route never sees the token.
4. **Market data fetch.** `SchwabMarketData.get_quote()` and `get_chain()` return the symbol price and the option chain. Symbol reference data (the 8,568-row `symbol_reference` table in Azure SQL) is consulted for `apiSymbol` mapping for index symbols like `.INX → $SPX`.
5. **Hard gates run first.** The chain is fed through the registered hard gates (`app/analysis/hard_gates/`). EarningsInWindowGate consults the FinnhubEarnings provider (also Pattern 1) for AAPL's next earnings date and PASSes/FAILs candidates accordingly. NegativeEVGate filters on expected value. Pre-screen before scoring is the cost optimization that prevents Claude from ever seeing trades that would be auto-rejected (see business-rules.md → Hard Gates).
6. **Black-Scholes probability matrix.** For surviving candidates, `app/analysis/black_scholes.py` computes the probability of the underlying being at each price level (±10% in $10 steps) at expiry-9, expiry-6, expiry-3, expiry. This matrix is computed in Python, never by Claude. Claude receives it as context.
7. **Strategy scoring.** `app/analysis/strategy_scorer.py` scores each candidate against the active strategy (or all four strategies if scoring is multi-strategy). Scores are 0–100; thresholds and weights live in `business-rules.md` → Strategy Scoring.
8. **Response returns.** Frontend renders the scored candidates in the TradesPage card grid.

The user clicks a candidate to evaluate it.

9. **Evaluation request.** Browser POSTs to `/api/v1/evaluate/structured` with the trade payload. Auth dependency resolves as before.
10. **AI adapter dispatch.** The route calls the AI adapter's `chat()` method with the system prompt loaded from `app/skills/trade-evaluation/SKILL.md` (after the Cleanup Roadmap migration completes; today the prompt is hardcoded in `app/ai/prompts.py`) and the trade payload as the user message. The adapter (`FoundryEvalAdapter` calling Azure AI Foundry) returns the structured JSON verdict.
11. **Two-track observability fires.** An OTel span is opened around the call (`invoke_with_tracing()` in `app/agents/telemetry.py`) and writes to Application Insights. A row is inserted into `agent_run_log` with the prompt version, the input tokens, the output tokens, the verdict, and the OTel `trace_id`. Pattern 3.
12. **Verdict returns.** The Pydantic-validated `TradeVerdict` is sent back to the browser and rendered in the TradeEvaluationCard.

The user clicks "Follow this trade."

13. **Position created.** `/api/v1/positions/follow` writes a row to `positions` with `source=PAPER`, `status=FOLLOWING`, the entry price, the strikes, the expiration, and Claude's exit levels (target, stop, time-stop). Same table that holds live positions (Pattern 4).
14. **Position Monitor Agent picks it up.** Layer 2. The next scheduled run of the monitor (daily after market close, or on-demand) reads the position, computes the current health grade against the deterministic math in `app/analysis/health_grade.py`, and if a threshold is crossed (e.g., grade drops to D), calls the Insight Engine.
15. **Insight Engine generates.** `app/agents/insight_engine.py` calls Claude with the deviation context plus the options-domain SKILL.md, gets a structured insight, writes it to the `insights` table with `domain='options'`. Pattern 5.
16. **Dashboard reads.** Next time the user loads the dashboard, the InsightCard component pulls from `insights` filtered by `domain='options'` and renders the alert.

End to end: user action → Layer 1 sync work → Layer 2 background monitoring → Layer 3 cross-cutting insights → user sees the result. The patterns interlock; pulling any one out breaks the chain.

---

# 2. Data

## Data Models (Azure SQL)

The system uses a single Azure SQL database (`options-analyzer-db`, hosted on `options-analyzer-sql`, West US 2) accessed via SQLAlchemy 2.x async engine with Entra ID authentication only (no SQL auth). All ORM models live in `app/models/database.py` today (a 928-line single file slated for split into per-domain modules in the Cleanup Roadmap).

The active entities by functional area:

**Identity and session.** `User` (Entra OID, email, role, market_data_provider preference), `Session` (Fernet-encrypted token blob, expires_at, last_refreshed), `UserConfig` (per-user preferences and dashboard layout).

**Trade evaluation and audit.** `TradeRecommendation` (per-user trade keys with verdict, scope to user_id required — see Data Isolation Invariant below), `agent_run_log` (the durable two-track observability table — every AI call recorded with prompt version, tokens in/out, model, provider, OTel trace_id, latency, verdict shape).

**Positions.** `positions` (the unified PAPER/LIVE table per Pattern 4 — symbol, structure type, legs, entry price, exit levels stored at entry, status, source, health_grade, last_monitored_at), `position_history` (state transitions for audit).

**Strategies and scoring.** `strategy_configs` (server-side per-user strategy parameter overrides — table exists, currently has no API routes wired and zero rows; persistence model decision is OTA-514 work).

**Symbol reference and provider state.** `symbol_reference` (8,568 rows of symbol metadata including `apiSymbol` mappings for index symbols; lives in SQL because loading into browser memory was rejected as an architectural decision — too much data, slow page loads), `provider_state` (lifecycle state per provider per environment; populated under OTA-525).

**Insights.** `insights` (the generic Insight Engine output — domain, severity, title, body, source position_id, dismissed_at, surfaced_at).

**Watchlists.** `watchlists` and `watchlist_items` — backend is the sole source of truth (the previous "localStorage only" claim in older docs is wrong and was removed in the CLAUDE.md rewrite).

**Schwab token storage.** Historically `SchwabToken` table existed but was intentionally unused (Key Vault is the canonical store via `SchwabTokenManager`). Scheduled for table drop under the Cleanup Roadmap.

Primary key types are inconsistent across tables (`User.id` is `String(36)`, `TradeLog.id` is `Integer`, `Position.id` is `String(36)`) — this is real and known; standardization is in the Cleanup Roadmap with low priority.

## Data Isolation Invariant

Every CRUD endpoint that takes a resource ID **must** filter by `user_id`. This is non-negotiable, even in the current single-user development phase, because the system is designed for multi-user from day one and a missing filter is a data isolation bug regardless of how many users exist today.

The Opus-4.7 review caught one violation: `DELETE /recommendations/{trade_key}` in `agent_routes.py` does not filter by `user_id`, meaning any authenticated user who knows another user's trade_key format could delete that recommendation. This is fixed under the Cleanup Roadmap and added to the contract test suite to prevent regression.

The invariant is enforced by:

- A coding standard (every new endpoint that takes a resource ID gets a `user_id` filter, no exceptions).
- A planned contract test that exercises the invariant — user A creates a resource, user B authenticated as a different identity attempts to read/update/delete it, expects 404 or 403.
- Code review on every PR that touches a CRUD route.

## Schema Migration Strategy

The system uses **Alembic** for schema migrations, integrated with the SQLAlchemy async engine. Alembic is wired and operational as of OTA-540 (shipped 2026-05-01). OTA-522 is superseded by OTA-540.

The chosen migration discipline is **expand/contract**:

1. The expand migration adds the new column or table without breaking the old code path.
2. The application is deployed and runs against the expanded schema.
3. After production has been stable on the new code for at least 14 days (longer if the affected object is heavily used), the contract migration drops the obsolete column or table.

This discipline is required because the staging and production slots in the App Service share the same Azure SQL database. The slot swap pattern means both slots are running simultaneously for a brief window during the swap; if one slot expects a column the other has dropped, the swap would break.

Deferred contract migrations are tracked perpetually under OTA-523 (Database Contract Actions). When a contract migration ships, its row in OTA-523's tracking table updates to `dropped` and is preserved for audit.

**OTA-540 (shipped):** Alembic is now wired and operational. The baseline migration (`f9e59a180957`) represents the full production schema as of 2026-05-01.

`app/models/session.py` `init_db()` now runs `alembic upgrade head` at startup **in dev/staging only**. In production, `init_db()` is a no-op — migrations are applied manually as part of the deploy procedure:

1. Build artifact ships via `build-on-push.yml` → deploy to staging slot via `deploy-to-prod.yml`
2. Developer runs `alembic upgrade head` from a workstation with prod Entra credentials, pointed at the production Azure SQL database
3. Verify `alembic current` shows the expected revision
4. Promote staging to prod via `swap-staging-to-prod.yml`

The one-time production stamping procedure (for existing databases transitioning from `create_all()` to Alembic) is documented in `docs/runbooks/alembic-stamp-prod.md`.

The legacy `app/models/migrations.py` hand-written migration runner is superseded by Alembic for all new schema changes. It remains in place only for reference; it no longer runs at startup.

---

# 3. API and Integration

## Provider Adapter Pattern (Deep Dive)

The base interfaces live in `app/providers/base.py`:

```python
class MarketDataProvider(ABC):
    async def get_quote(self, symbol: str) -> dict
    async def get_chain(self, symbol: str, expiration: str) -> dict
    # ...

class ContextSource(ABC):
    source_id: str          # unique identifier e.g. "schwab_quotes"
    signal_type: str        # PRICE | SENTIMENT | FUNDAMENTAL | TECHNICAL | NEWS
    async def fetch(self, symbol: str) -> dict
    def normalize(self, raw: dict) -> ContextSignal
    def ttl_seconds(self) -> int
```

The dispatch happens through `ProviderFactory` (`app/providers/factory.py`), which is currently misnamed — it's a singleton container with caching, not a factory. It is scheduled for rename to `ProviderRegistry` in the Cleanup Roadmap. The existing `AccountProvider` and `TradingProvider` ABCs in `base.py` have zero implementations; they were placeholders for Phase 5 (live trading) work and are scheduled for deletion. When Phase 5 begins, a `BrokerageProvider` ABC will be added at that time with a clean shape informed by the actual brokerage requirements, not the current speculative shape.

Adding a new provider requires:

1. Creating an adapter class implementing the appropriate ABC (`MarketDataProvider`, `ContextSource`, etc.).
2. Adding the credentials to Key Vault.
3. Registering the adapter in `PROVIDER_REGISTRY` with an explicit lifecycle state (`active`, `inactive`).
4. Filing a Story documenting the addition.

Engines, routes, and the frontend require zero changes. The `_get_provider()` helper consulted by every route enforces this — if a route hardcodes a provider name, it is a code-review fail.

## Provider Lifecycle State Machine

Every provider has one of four lifecycle states. The state machine is formalized under OTA-525.

| State | Meaning | Encoding |
|---|---|---|
| **Active** | Registered in factory, live credentials in Key Vault, selectable at runtime, used by at least one code path | `PROVIDER_REGISTRY` entry with `state: "active"` |
| **Inactive** | Registered in factory, credentials may or may not exist in Key Vault, no live code path routes through it. Reactivation is a config flag flip, not a code change. | `PROVIDER_REGISTRY` entry with `state: "inactive"` |
| **Deprecated** | In codebase but flagged not for new use, with a documented end-date and migration plan for any callers | `PROVIDER_REGISTRY` entry with `state: "deprecated"` plus `end_date` and `migration_target` |
| **Removed** | Gone from codebase entirely, Key Vault credentials cleaned up | Not in `PROVIDER_REGISTRY` at all; no adapter file, no factory entry |

**Legal transitions:**

- *Active → Inactive* (deactivation): keep code, mark factory entry `inactive`, optionally retain credentials. Single Story per deactivation.
- *Inactive → Active* (reactivation): flip flag, verify credentials, smoke test. Single Story per reactivation.
- *Active or Inactive → Deprecated*: add end_date, document migration_target, communicate to users. Story.
- *Deprecated → Removed*: full code cleanup (adapter file, factory entry, config schema, env example, Key Vault credentials). Story (this is what OTA-524 did to Tradier).
- *Removed → anything*: not a transition. Returning a removed provider requires a fresh adapter implementation as a new Story.

**Current state (as of this document's last update):**

- **Schwab** — Active. Sole market-data provider. Sole brokerage credential source today.
- **Tradier** — Removed. Was previously the registered market data adapter; removed via OTA-524 on 2026-04-30. Returning Tradier would require a fresh adapter Story.
- **Finnhub Earnings** — Active. Provides earnings calendar context for the EarningsInWindowGate hard gate.
- **Anthropic Direct** — Active for local dev fallback only. Production traffic routes through Foundry.
- **Azure AI Foundry (Claude Sonnet 4.6)** — Active. Production AI provider.

The lifecycle state field is read from code at runtime. The frontend's data-source-picker conceptually already knows about state (the previous Tradier entry was labeled `active: False, "Market Data (Deprecated)"`); the formalized state field replaces that ad-hoc encoding.

## External Credential Management

Each provider adapter owns its credential lifecycle. The calling code calls `provider.fetch()` and never knows how the credential was obtained. OAuth, federation, API key, service account — the adapter chooses what's appropriate for its source. All credentials are stored and managed server-side; the browser never sees a provider credential.

| Credential | Auth Method | Where Stored | Managed By |
|---|---|---|---|
| Schwab market data | OAuth 2.0 (authorization code) | Key Vault `schwab-token` (production), in-memory (local dev with .env) | `SchwabTokenManager` |
| Azure AI Foundry | Entra ID (managed identity) or API key fallback | Key Vault `foundry-api-key` (when API key) or app's MSI (when Entra) | `SecretsManager` + `FoundryEvalAdapter` |
| Anthropic direct (dev fallback) | API key | Key Vault `anthropic-api-key` or local `.env` | `SecretsManager` + `AnthropicAdapter` |
| Finnhub earnings | API key | Key Vault `finnhub-api-key` | `SecretsManager` + `FinnhubEarnings` adapter |
| Future brokerage / data sources | Source-specific | Key Vault | New provider adapter per Pattern 1 |

`SecretsManager` (`app/core/secrets.py`) wraps Azure Key Vault with a `.env` fallback for local development. In Azure environments the App Service uses managed identity to read from Key Vault; the `.env` fallback is never used in production.

The JWT signing key (used by the legacy `auth_routes.py` local-password flow that is scheduled for removal) is auto-generated on first run and written back to Key Vault if absent. This pattern has a known failure mode: if Key Vault is unreachable on first startup, a new key is generated in memory but not persisted, invalidating all sessions on next restart. Cleanup item: enforce that the key must exist in Key Vault before app startup proceeds.

## Schwab Integration

Schwab is the sole Active market-data provider and the production OAuth integration. Specifics of the OAuth flow, token refresh discipline, and dev cert requirements live in `SCHWAB-LOGIN-PROCESS.md`. This document covers the architectural shape only.

Architecturally, Schwab integration consists of:

- `app/providers/schwab.py` — `SchwabMarketData(MarketDataProvider)` implementation. Quote, chain, account endpoints.
- `app/providers/schwab_token_manager.py` — `SchwabTokenManager` owning the token lifecycle. Reads from Key Vault on startup, refreshes ahead of expiry, writes back to Key Vault on refresh.
- `app/providers/schwab_context_source.py` — `SchwabContextSource(ContextSource)` for use in the Symbol Context Store.
- `app/api/schwab_auth_routes.py` — OAuth callback handlers.

Schwab requires HTTPS for the OAuth callback. Local dev runs FastAPI with a self-signed cert on `https://127.0.0.1:8000`. The cert is generated with Python's `cryptography` library, not OpenSSL CLI (line-continuation issues with PowerShell on Windows).

## Key API Endpoints

Routes live under `app/api/`. Current route file inventory:

| File | Prefix | Purpose | Status |
|---|---|---|---|
| `identity_routes.py` | `/auth` | BFF OIDC redirect flow (PKCE, signed state, HttpOnly cookie, server-side session). The current and only sanctioned login path. | Active |
| `auth_routes.py` | `/auth` | Legacy local-password flow (register, login, MFA). Scheduled for removal. | Deprecated |
| `entra_auth_routes.py` | `/auth` | Legacy MSAL bridge (Entra `id_token` → local JWT). Returns a JWT to the browser, violating Pattern 6. Scheduled for removal. | Deprecated |
| `schwab_auth_routes.py` | `/auth/schwab` | Schwab OAuth callback handlers. | Active |
| `market_routes.py` | `/market` | Quotes, option chains, symbol search, symbol reference lookup. | Active |
| `analysis_routes.py` | `/analyze` | Vertical, long-call, directional analysis endpoints. | Active |
| `evaluation_routes.py` | `/evaluate` | Structured Claude trade evaluation (`/evaluate/structured`, `/evaluate/follow-up`). The primary AI evaluation path. | Active |
| `agent_routes.py` | `/agent` | Trade agent triage / deep-dive / followup pipeline. Uses the SDK-based AI stack (legacy). Scheduled for rename to `trade_evaluation_routes.py` and migration to the unified AI adapter. | Active but drift |
| `agents_routes.py` | `/agents` | Position monitor scheduled-job status and on-demand runs. Scheduled for rename to `position_monitor_routes.py` to eliminate the singular/plural confusion. | Active |
| `position_routes.py` | `/positions` | Position CRUD, follow, take, close. | Active |
| `insight_routes.py` | `/insights` | Insight Engine output for the dashboard. | Active |
| `dashboard_routes.py` | `/dashboard` | Dashboard layout, widget config, media SAS URL generation. | Active |
| `watchlist_routes.py` | `/watchlist` | Flat watchlist CRUD. | Active — overlaps with named_watchlist_routes; consolidation pending |
| `named_watchlist_routes.py` | `/watchlists` | Multi-list watchlist with scan sources. | Active — overlaps with watchlist_routes; consolidation pending |
| `config_routes.py` | `/config` | User config GET/PUT. | Active |
| `service_routes.py` | `/services` | Service registry endpoints (data source picker). | Active |
| `health_routes.py` | `/health` | Liveness, readiness, dependency checks. | Active |
| `user_routes.py` | `/users` | User profile endpoints. | Active |
| `admin_routes.py` | `/admin` | Admin operations. | Active |
| `validation_routes.py` | `/validation` | Validation endpoints (purpose needs verification). | Active — needs review |
| `test_routes.py` | `/test` | Test endpoints. Should not exist in production. | Cleanup item |

The route layer is fragmented relative to its size. Consolidating overlapping route files (the two watchlist files, the two agent files) is in the Cleanup Roadmap.

---

# 4. AI Model Interaction

## Skill-Driven Prompt Architecture (Deep Dive)

The skill loader (`app/skills/skill_loader.py`) is a small template engine. SKILL.md files contain prompt sections demarcated by `## SectionName` headers. The loader supports `{{variable}}` interpolation and `{{#if variable}}...{{/if}}` conditionals. Python loads a skill once at startup and passes context dicts to render time.

```
app/skills/
├── skill_loader.py
├── claude-trade-agent/
│   └── SKILL.md             # BATCH_TRIAGE_SYSTEM, DEEP_DIVE_SYSTEM, FOLLOWUP_SYSTEM
├── position-monitor/
│   └── SKILL.md             # MONITOR_SYSTEM, DEVIATION_REPORT
└── insight-engine/
    ├── SKILL.md             # generic INSIGHT_SYSTEM
    └── domains/
        └── options/
            └── SKILL.md     # options-domain INSIGHT_USER template
```

The pattern is honored consistently for the agent pipeline. It is currently violated for the trade-evaluation pipeline — `app/ai/prompts.py` contains a 110-line hardcoded `TRADE_EVALUATION_SYSTEM_PROMPT` and a 14-line `FOLLOW_UP_SYSTEM_PROMPT`. Migration of these to a new `app/skills/trade-evaluation/SKILL.md` is in the Cleanup Roadmap. This is the highest-leverage consistency win in the AI layer.

When migration is complete, every AI invocation in the system will load its prompt via `get_skill(skill_name).get(section_name, **context)`. No exceptions. New AI features must use SKILL.md from day one.

## AI Adapter Contract

The system has two AI adapters today: `FoundryEvalAdapter` (httpx-based, calls Azure AI Foundry, returns structured JSON) and `AnthropicAdapter` (SDK-based, direct Anthropic API, used as a local-dev fallback). They share a `chat()` method by convention; they do not share an ABC.

The target is a single `AIAdapter` ABC defining the contract:

```python
class AIAdapter(ABC):
    async def chat(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
    ) -> dict:
        """
        Returns:
            {
                "text": str,                    # full response text
                "input_tokens": int,
                "output_tokens": int,
                "model": str,                   # e.g. "claude-sonnet-4-6"
                "provider": str,                # "foundry" | "anthropic"
            }
        """
```

Both adapters implement this single ABC. The legacy `AIProvider` ABC in `app/providers/ai/base.py` (with `evaluate_trade()` and `follow_up()` methods that returned prose) is deleted as part of the AI stack merge in the Cleanup Roadmap.

The contract is enforced by:

- The ABC itself (Python's `abc.abstractmethod`).
- A planned contract test that asserts `chat()` returns the documented dict shape for each adapter, run before any adapter swap.

Why the contract matters: today, swapping `agent_routes.py` from the SDK adapter to the httpx adapter (the cleanup goal) requires reading both adapters carefully because the convention is informal. With a real ABC, the swap is a one-line import change with confidence.

## Claude Structured Evaluation

The primary AI evaluation flow is:

1. **User triggers evaluation.** Frontend POSTs trade payload to `/evaluate/structured`.
2. **Route assembles context.** Pulls hard-gate results, B-S probability matrix, and any relevant ContextSource signals.
3. **Prompt loads.** System prompt loads from `SKILL.md` (post-cleanup; today from `app/ai/prompts.py`). User message contains the structured trade payload.
4. **AI adapter invokes.** `FoundryEvalAdapter.chat()` calls Foundry. Output is JSON (model is instructed to respond JSON-only).
5. **Two-track observability fires.** OTel span + `agent_run_log` row.
6. **Pydantic validates.** `TradeVerdict` model validates the JSON. Validation failures are caught and either retried (transient JSON malformation) or surfaced as evaluation errors.
7. **Verdict returns.** Frontend renders.

The `TradeVerdict` schema (`app/ai/schemas.py`) defines the structured output shape. This is the contract between Claude and the frontend; changes to the verdict shape require coordinated changes to the prompt schema and the frontend renderer.

For agent-style multi-turn flows (triage, deep-dive, follow-up), the flow uses `agent_routes.py` and the `claude-trade-agent` SKILL.md sections. After the AI stack merge, both flows use the same `FoundryEvalAdapter`; the difference is the SKILL.md section loaded.

## Agent Inventory and Agent CLAUDE.md Convention

Agents in the Layer 2/3 sense (background, scheduled, autonomous) live in `app/agents/`:

| Agent | File | Purpose | Layer |
|---|---|---|---|
| Position Monitor | `position_monitor.py` | Daily health-grade refresh on every active position; threshold-crossing escalation to Insight Engine | 2 |
| Insight Engine | `insight_engine.py` | Generic detect → score → communicate; called by Position Monitor on threshold crossings | 2 / 3 |
| Deviation Detector | `deviation_detector.py` | Identifies deviations from Claude's stored exit thesis. Currently not imported anywhere; needs verification of intent (alive vs abandoned) | needs verification |
| Context Store | `context_store.py` | Symbol Context Store for caching ContextSource signals | 2 |
| Telemetry | `telemetry.py` | `invoke_with_tracing()` context manager bridging OTel and `agent_run_log` | cross-cutting |

There is also a separate concept of "agents" — development tooling agents (UX QA agent, data QA agent, fe-dev agent, be-dev agent) that live in repo-root `agents/` directory and are NOT part of `app/`. These are dev tooling, not application code. The naming collision (top-level `agents/` vs `app/agents/`) is unfortunate; if it causes ongoing confusion, the top-level `agents/` directory should be renamed to `dev-agents/`.

**Agent CLAUDE.md Convention:** every dev tooling agent has its own `CLAUDE.md` file under its directory (`agents/qa-ux/CLAUDE.md`, `agents/qa-data/CLAUDE.md`, `agents/fe-dev/CLAUDE.md`, `agents/be-dev/CLAUDE.md`). When the QA gate behavior changes in the root `CLAUDE.md`, all four of these must stay in sync. This is a documented sync rule in `CLAUDE.md` Post-Build QA Gate section.

## The Multi-Agent Future

Today the agent layer is single-agent-per-task. Each agent (Position Monitor, Insight Engine) is a Python module with a `run()` method invoked by the scheduler. Communication between agents is via the SQL database.

The forward direction is multi-agent orchestration: a coordinator agent that decomposes a high-level user goal ("review my entire portfolio") into specialized sub-agent invocations (per-position monitor, cross-position correlation analysis, market-context summary, recommendation synthesis). The coordinator does not exist today. When it ships, it will live alongside the existing agents in `app/agents/coordinator.py` and use the same SKILL.md prompt convention.

Design constraints for any new agent:

- Must produce both an OTel span and an `agent_run_log` entry (Pattern 3, no exceptions).
- Must load its prompt from a SKILL.md file (Pattern 2, no exceptions).
- Must communicate with other agents through the SQL database, not direct calls.
- Must be invocable both on-demand (via API route) and on-schedule (via APScheduler).

## Agent 365 Readiness

Long-term, the system is designed to integrate with Microsoft 365 Copilot and the Microsoft 365 Agents fabric. The Layer 3 framing ("Management" agents that observe, summarize, and escalate to a human user) maps cleanly onto the M365 agent surface. The BFF identity pattern using Entra IDP (Pattern 6) is the foundation that makes M365 integration tractable — the user is already authenticated against the same identity provider, so an M365 agent reading from OTA's APIs can do so on behalf of the same user without a separate auth dance.

This is not active work. It informs design decisions today (don't break the Entra-only auth assumption; keep agent outputs in structured forms suitable for M365 surfaces) but does not constrain near-term feature work.

---

# 5. Application Patterns and Engines

## The Strategy System

A "strategy" in OTA is a named approach to options trading with a configuration schema, a scoring profile, and an explicit set of compatible trade structures. Today there are four strategies, currently named with the cute taxonomy (Steady Paycheck / Weekly Grind / Trend Rider / Lottery Ticket; abbreviated SP/WG/TR/LT). A redesign to mechanics-based names (e.g., "Income — Credit", "Directional — Debit") is on the future epic backlog; until that ships the cute names remain the canonical names.

**Strategy and structure are technically orthogonal axes, but each strategy declares an explicit `compatible_structures` map enumerating which trade structures it accepts.** A trade is scored against a strategy only if its structure is in that strategy's compatibility map. The scorer gates at pipeline entry: incompatible pairs return null and never reach Foundry. Multi-strategy fit is preserved within a structural family (e.g., a bull_put_credit at 30 DTE can fit both Steady Paycheck and Weekly Grind) but never across families. This reflects the trading reality that strategy is a mechanism — premium collection vs directional payoff vs long premium — not a metrics bucket. The canonical compatibility map lives in `business-rules.md` → Strategy Scoring.

**Architectural shape (rules in business-rules.md):**

- Each strategy has a config schema declaring its tunable parameters (DTE range, delta range, credit threshold, etc.) and a `compatible_structures` list.
- The scorer (`app/analysis/strategy_scorer.py`) reads the active strategy's config and the trade candidate. If the candidate's structure is not in `compatible_structures`, the scorer returns null and no further evaluation occurs for that strategy. Otherwise the scorer returns a 0–100 score plus per-metric breakdown.
- ConfigDrawer renders whatever schema the active strategy declares — fields, types, min/max/default/step. This replaces the old static 14-field systemVars approach.
- Strategy filtering uses the `trade_structure` field and the `compatible_structures` map, never hardcoded strategy names.

Frontend strategy config files live in `web/src/strategy-configs/` (`steady-paycheck.config.js`, `weekly-grind.config.js`, etc.) and are registered in `index.js`.

The DTE-range source-of-truth issue (two dicts in `strategy_definitions.py` that disagree) is tracked under OTA-513 and is a Cleanup Roadmap item.

## The Positions System

A position is a tracked options trade. The shape is defined in business-rules.md → Position Lifecycle. Architecturally:

- Single table (`positions`) per Pattern 4.
- `source` field distinguishes PAPER (followed for monitoring) from LIVE (actually executed via brokerage; Phase 5 work).
- `status` field tracks state machine (FOLLOWING / LIVE / CLOSED).
- Exit levels (target, stop, time-stop) stored at entry. These are Claude's recommendations from the evaluation; they don't change after entry unless the user explicitly updates them.
- Health grade (A–F) computed daily after market close by Position Monitor Agent, stored on the row, displayed in UI.

Position lifecycle transitions:

1. User clicks "Follow this trade" on an evaluated trade → row created with `source=PAPER`, `status=FOLLOWING`, exit levels populated.
2. Position Monitor Agent picks it up → updates `health_grade` and `last_monitored_at` daily.
3. Threshold crossings → Insight Engine called → insight written to `insights` table.
4. User clicks "Take Position" → status flips to `LIVE` (Phase 5 will additionally trigger brokerage order entry; today it records intent only).
5. User clicks "Close" or position expires → status flips to `CLOSED`.

The same agent and the same UI handle PAPER and LIVE positions. The only behavioral difference is whether brokerage order entry fires (Phase 5).

## Hard Gates Pipeline

Hard gates are pre-Claude filters that PASS or FAIL trade candidates before they reach scoring. They exist because Claude is expensive and slow; gates run cheap deterministic checks first.

Architecturally:

- Gates live in `app/analysis/hard_gates/` as a registered sub-package.
- Each gate implements an `evaluate(candidate, context) -> GateResult` interface.
- Gates are registered via `register_gate(gate_class)` at startup.
- Gate ordering is significant — gates run in registration order, and a single FAIL short-circuits subsequent gates.

Currently registered gates:

- `EarningsInWindowGate` — FAILs candidates with earnings within 5 days of expiration.
- `NegativeEVGate` — FAILs candidates with negative expected value.

Gate trigger conditions, thresholds, and behavioral rules (e.g., 0-DTE auto-PASS, credit % gates) live in `business-rules.md` → Hard Gates.

Adding a new gate is a single file plus one `register_gate(...)` call. Tests for the new gate are required and exercise both PASS and FAIL paths plus the registration call. The hard-gate ordering test (`tests/integration/test_gate_ordering.py`) is the most important existing test in the suite — it validates that the registration order is preserved and that short-circuit behavior is correct.

## The Insight Engine

The Insight Engine (`app/agents/insight_engine.py`) is a generic detect → score → communicate pattern. It is invoked by other agents (today, the Position Monitor) when a threshold crossing or deviation is detected. It calls Claude with a generic system prompt (`app/skills/insight-engine/SKILL.md`), loads a domain-specific user-message template (`app/skills/insight-engine/domains/options/SKILL.md`), gets a structured insight back, validates it against the `Insight` Pydantic schema, and writes it to the `insights` table with `domain='options'`.

The data model:

```
insights
├── id
├── domain                  # "options" | "manufacturing" | future
├── severity                # info | warning | critical
├── title                   # short, one-line
├── body                    # full insight text (markdown)
├── source_position_id      # FK to positions, nullable
├── source_event_id         # FK to whatever triggered (nullable)
├── surfaced_at             # when the insight first appeared
├── dismissed_at            # nullable; user-set
└── trace_id                # OTel link
```

The dashboard reads from this table filtered by `domain`. The `InsightCard` component renders any insight regardless of domain.

The architectural commitment: any options-specific assumption stays in the options SKILL.md or the OptionsObservationSource adapter. The generic core (deviation detector, scorer, communicator, schema validator) does not import anything from `app/analysis/`. Violation of this rule is a code-review fail.

The "Today's Actions" widget on the dashboard is currently a placeholder that will be wired to the Insight Engine output once the engine is processing live data flow. Until then, the widget shows static example content.

## Market Intelligence Aggregator

The Market Intelligence Aggregator is the collective name for the components that gather, cache, and serve external context for a symbol.

- **Symbol Context Store** (`app/agents/context_store.py`) — caches `ContextSignal` outputs per symbol with per-source TTLs. When a request asks for "current context for AAPL", the store returns cached signals that are still fresh, fetches signals that are stale, and returns the merged result. TTLs per signal type live in `business-rules.md` → Signal Freshness.
- **Position Monitor Agent** (`app/agents/position_monitor.py`) — uses the Context Store on every monitoring run. Hot-cached signals mean the daily monitor sweep doesn't hit external APIs for every position.

The Context Store's design follows the same Pattern 1 contract as market-data providers: any new context source (social sentiment, fundamentals, news) implements `ContextSource`, registers its `ttl_seconds()`, and the store handles caching and dispatch.

## Black-Scholes Probability Matrix

The probability matrix is computed in Python (`app/analysis/black_scholes.py`), never by Claude. Inputs are current price, IV, DTE, and risk-free rate. Output is a matrix of probabilities of the underlying being at each price level (±10% in $10 steps) at four time horizons (expiry-9, expiry-6, expiry-3, expiry).

Architecturally, this is significant for two reasons:

1. **Determinism.** Asking Claude for probability calculations would be slow, expensive, and non-deterministic. The same inputs would produce slightly different outputs across calls. Doing the math in Python guarantees reproducibility.
2. **Cost.** The matrix is computed once per evaluation request and fed to Claude as context. Claude reasons about the matrix; it does not produce it.

The math itself (the actual Black-Scholes formula and its application to the matrix shape) lives in `business-rules.md` → PoP Computation, when extracted under OTA-495.

---

# 6. Observability and Operations

## Two-Track Observability (Deep Dive)

Every AI invocation produces two records. They are linked by `trace_id`.

**Track 1 — OpenTelemetry trace into Application Insights.** The `invoke_with_tracing()` context manager (`app/agents/telemetry.py`) wraps every AI call. It opens an OTel span with attributes (model, provider, prompt_name, prompt_version, input_tokens, output_tokens, latency_ms) and exports to Application Insights (`ota-insights`). Spans are queryable in App Insights for real-time monitoring, alerting on latency or error rate spikes, and per-feature usage analysis. Spans expire from App Insights per the workspace retention policy (default 90 days).

**Track 2 — Durable business record in `agent_run_log`.** Every AI call also writes a row to the `agent_run_log` SQL table containing the full prompt rendered, the full response text, the prompt section name, the prompt version (hash of the SKILL.md file at invocation time), the input/output tokens, the model name, the provider name, the OTel `trace_id`, and the latency. This is permanent audit. It does not expire.

The two-track design exists because each track addresses a different question:

- *"Is the system healthy right now?"* → App Insights spans.
- *"What did Claude actually recommend on this trade three months ago, and what was the prompt at that time?"* → `agent_run_log`.

Neither track replaces the other. The `agent_run_log` table grows unbounded; a retention policy (e.g., archive to blob storage after 12 months) is a Cleanup Roadmap item but is not urgent at current call volume.

## Application Insights Integration

Application Insights instance: `ota-insights`. The connection string is sourced from Key Vault and passed to `init_agent_telemetry()` in the lifespan.

Today only AI calls are instrumented. Auth flows, market-data fetches, and DB operations are not traced. Expanding instrumentation to those layers is in the Cleanup Roadmap.

## Resource Shutdown Discipline

The lifespan teardown must close every async resource cleanly. Failure to close a resource causes connection leaks, abandoned DB sessions, or worse — partial writes mid-shutdown.

Resources that must close:

- **httpx clients** — the `FoundryEvalAdapter` creates a persistent `httpx.AsyncClient` in `__init__`. Its `close()` must be called during lifespan teardown. (Current state: not called. Cleanup Roadmap item.)
- **APScheduler** — `scheduler.shutdown(wait=True)` (not `wait=False`) so in-progress jobs complete before the process exits. Currently uses `wait=False`, which can leave a Position Monitor run with an abandoned DB session mid-write. Cleanup item.
- **Async DB engine** — `engine.dispose()` in the lifespan teardown.
- **Token refresh background task** — `task.cancel()` plus an `await task` to allow graceful exit.

This is enforced by:

- A documented checklist in this section.
- A test (planned) that exercises lifespan startup-then-immediate-shutdown and asserts no resource leaks.
- Code review on every PR that adds a new long-lived async resource.

When adding a new async resource that needs cleanup, add it to the list above and to the lifespan teardown in `app/main.py`.

---

# 7. Software Development and Deployment

## System Structure — Backend

```
app/
├── main.py                       # FastAPI entry, lifespan, router registration
├── core/
│   ├── config.py                 # Pydantic Settings; loads from .env + Key Vault
│   └── secrets.py                # SecretsManager (Key Vault + .env fallback)
├── auth/
│   ├── service.py                # Legacy JWT/TOTP (scheduled for retirement)
│   ├── dependencies.py           # FastAPI auth dependencies (cookie-first; JWT fallback during migration)
│   ├── session_manager.py        # BFF session management (Fernet-encrypted server-side sessions)
│   ├── client_assertion.py       # Certificate-based JWT client assertion for Entra confidential client
│   └── providers.py              # Per-IdP configuration registry
├── models/
│   ├── database.py               # SQLAlchemy ORM models (current 928-line single file; split planned)
│   ├── session.py                # Async engine, init_db()
│   ├── schemas.py                # Pydantic request/response schemas
│   └── migrations.py             # Alembic configuration entry
├── providers/
│   ├── base.py                   # MarketDataProvider, ContextSource ABCs
│   ├── factory.py                # ProviderRegistry (currently misnamed ProviderFactory; rename pending)
│   ├── schwab.py                 # SchwabMarketData adapter
│   ├── schwab_token_manager.py   # Schwab OAuth token lifecycle
│   ├── schwab_context_source.py  # Schwab context source for the Symbol Context Store
│   ├── finnhub_earnings.py       # Finnhub earnings calendar adapter
│   └── ai/                       # OLD AI stack — scheduled for deletion after merge into app/ai/
├── ai/                           # NEW AI stack — single AIAdapter ABC, FoundryEvalAdapter, AnthropicAdapter
│   ├── base.py                   # AIAdapter ABC (planned)
│   ├── foundry_adapter.py        # FoundryEvalAdapter (httpx, JSON-structured)
│   ├── anthropic_adapter.py      # Local-dev fallback
│   └── schemas.py                # TradeVerdict and other AI output schemas
├── analysis/
│   ├── vertical_engine.py        # Vertical spread scorer
│   ├── long_call_engine.py       # Long-call scorer
│   ├── directional_engine.py     # Strategy comparator
│   ├── strategy_scorer.py        # Multi-strategy scoring engine
│   ├── strategy_definitions.py   # Strategy parameter dictionaries (consolidation pending under OTA-513)
│   ├── black_scholes.py          # Probability matrix math
│   ├── health_grade.py           # Position health grade computation
│   ├── hard_gates/               # Registered hard gates sub-package (EarningsInWindowGate, NegativeEVGate)
│   └── scoring_factors/          # Per-metric scoring factor implementations
├── agents/
│   ├── position_monitor.py       # Daily position health refresh, threshold escalation
│   ├── insight_engine.py         # Generic detect → score → communicate
│   ├── deviation_detector.py     # Deviation-from-thesis detection (alive-or-abandoned needs verification)
│   ├── context_store.py          # Symbol Context Store
│   └── telemetry.py              # invoke_with_tracing(), Application Insights bridge
├── api/                          # 17+ route files (see Key API Endpoints in §3)
├── middleware/
│   └── csrf.py                   # CSRF middleware for BFF
├── skills/
│   ├── skill_loader.py           # Template engine ({{var}} + {{#if}})
│   ├── claude-trade-agent/SKILL.md
│   ├── position-monitor/SKILL.md
│   └── insight-engine/
│       ├── SKILL.md
│       └── domains/options/SKILL.md
└── validators/
    └── narrative_grounding.py    # Output validation for narrative AI responses
```

Items scheduled for removal under the Architecture Optimization Epic are flagged in the comments above. The structure post-cleanup is leaner: single `app/ai/` directory, single auth stack, renamed route files, and `database.py` split into per-domain modules.

## System Structure — Frontend

```
web/
├── package.json
├── vite.config.js                # HTTPS dev server with proxy to FastAPI
├── public/index.html
└── src/
    ├── main.jsx                  # Entry
    ├── App.jsx                   # Router (5 live routes + 8 redirects from retired paths)
    ├── api/
    │   └── client.js             # API bridge — currently 867-line monolith; split is a future cleanup item (low priority)
    ├── auth/
    │   └── (msalConfig.js scheduled for deletion — BFF auth doesn't use it)
    ├── context/
    │   ├── AppContext.jsx        # Watchlist, favorites, activeSymbol (session-only state)
    │   └── AuthContext.jsx       # Auth state derived from BFF cookie
    ├── pages/
    │   ├── DashboardPage.jsx
    │   ├── TradesPage.jsx        # Verticals + Puts & Calls merged (Sprint 4 work, complete)
    │   ├── StrategyPage.jsx      # Per-strategy page with editable params and scoped positions
    │   ├── StrategyProfilePage.jsx
    │   ├── SecurityStrategiesPage.jsx
    │   ├── PositionsPage.jsx     # v3 design with StrategyPill, health grade letter badges, versioned re-reads
    │   ├── BrokerConnectPage.jsx
    │   └── _archive/             # Scheduled for deletion (Analysis.jsx, LongCallsPage.jsx, VerticalsPage.jsx)
    ├── components/               # ~40 components including Header.jsx (retired, scheduled for deletion)
    ├── widgets/                  # 6 dashboard widgets
    └── strategy-configs/         # 6 strategy config files
```

Notable architectural decisions in the frontend:

- **`activeSymbol` is session-only.** It never persists to localStorage. This is a deliberate decision to prevent stale-symbol confusion across sessions.
- **Symbol reference data lives in Azure SQL, not browser memory.** The 8,568-symbol reference table would be too large to ship to the browser; lookups are server-side via `/api/v1/market/symbol/{key}`.
- **`SymbolSearch` is tagged `framework-portable`** for cross-app reuse (Cross-App Reuse Plane).
- **No state management library beyond React Context.** The decision to stay on plain Context + hooks was explicit; Redux or Zustand would be overhead at the current scale.

## Deployment Architecture

The deployment model is **manual-trigger with pre-prod slot gate**. It exists in this shape because an earlier auto-deploy on push caused a BFF outage (the trigger event for the entire deployment redesign).

```
git push origin main
        │
        ▼
build-on-push.yml ───► Artifact uploaded (no deploy)
        │
        ▼
[manual trigger]
deploy-to-prod.yml ───► Deploy to STAGING slot
        │              ───► Smoke test against staging
        │              ───► Pause for manual swap
        │
        ▼
[manual trigger]
swap-staging-to-prod.yml ───► Slot swap (staging becomes prod)
        │
        ▼
   [prod live]
        │
[if broken: manual trigger]
rollback-prod.yml ───► Re-swap (or redeploy prior build artifact)
```

Confirmation tokens are required to fire each manual workflow (`confirm_deploy=DEPLOY`, `confirm_swap=SWAP`, `confirm_rollback=ROLLBACK`). This makes accidental deploys impossible.

Dev deploys use `deploy-to-dev.yml` with `confirm_deploy=DEPLOY-DEV` and no slot. Dev is a single-slot environment; if dev breaks it gets fixed forward.

The staging and prod slots share the same Azure SQL database. This is what enforces the expand/contract migration discipline (see §2 Schema Migration Strategy).

A separate SWA deploy pipeline (`azure-static-web-apps-purple-ground-0d4efed10.yml`) also runs on push, deploying the SPA to the `options-analyzer-web` Static Web App. However, as documented in Pattern 7, the SWA is not in the request path — Cloudflare routes both custom domains directly to the App Service. The SWA pipeline is effectively a no-op from the user's perspective and is a candidate for removal alongside the orphan SWA resource.

### Request Routing — Cloudflare to App Service Direct

Both environments use the same routing pattern. Cloudflare proxies the custom domain to the App Service, which serves both API and SPA:

```
Browser → Cloudflare (oa-dev.tmtctech.ai) → options-analyzer-api-dev (App Service)
Browser → Cloudflare (oa.tmtctech.ai)     → options-analyzer-api     (App Service)
```

The custom domain is bound directly on the App Service (visible via `az webapp show --name <app> --query hostNames`). No SWA linked backend, no Cloudflare `/api/*` rewrite rule — the App Service handles all paths.

**Health endpoints:**
- `/health` → 200 JSON (root-level, no `/api/v1` prefix)
- `/api/v1/health/detailed` → 200 JSON (component-level: database, Schwab)
- `/api/v1/health` does **not** exist — this is a common mistake; the path falls through to the SPA catch-all and returns HTML

**Verifying the routing:**
```bash
# Should return JSON (not HTML)
curl -s https://oa-dev.tmtctech.ai/health
curl -s https://oa-dev.tmtctech.ai/api/v1/health/detailed

# Should return 307 redirect to Entra (BFF login initiation)
curl -s -o /dev/null -w "%{http_code}" https://oa-dev.tmtctech.ai/api/v1/auth/login

# Should return 401 JSON (auth middleware fires, no session cookie)
curl -s https://oa-dev.tmtctech.ai/api/v1/auth/me
```

If any of these return HTML instead of JSON/redirect/401, the App Service is not running correctly — check Kudu logs.

### Cold-start and runtime OS dependencies

The ODBC Driver 18 install runs inside `app/main.py` lifespan startup. This is the intentional pattern, not a workaround. It costs roughly 90 seconds on cold start. Always On is enabled on the App Service plan, so cold start happens only on app restart — not on idle wake — bounding the user-perceived latency penalty to deploys and rare unplanned restarts.

The alternative (a custom container image with ODBC pre-installed, deployed via Azure Container Registry) is documented as Option A in OTA-553. It is not pursued today because the recurring cost (~$5/mo registry, plus a Docker build step in CI) is not justified by the ~90s cold-start savings at current scale. Revisit when a broader containerization effort is undertaken or when cold-start becomes user-visible (e.g., autoscale-out scenarios where new instances spin up frequently).

A user-supplied `startup.sh` approach was attempted under OTA-545 Phase 2 and reverted on 2026-05-02. The App Service Linux Python (Oryx) runtime makes that pattern brittle. **Do not retry that specific approach.** The general goal of moving ODBC out of `main.py` is still achievable via Option A if/when justified.

References: OTA-553 (decision), OTA-545 (Phase 2 revert), OTA-601 (this update).

## Azure Resources Summary

| Resource | Name | Location | Tier | Tags |
|---|---|---|---|---|
| Resource Group | `options-analyzer-rg` | West US 2 | n/a | `project=options-trade-analyzer`, `owner=don` |
| App Service Plan (prod) | (per current naming convention) | West US 2 | B1 | `environment=prod`, `component=api` |
| App Service Plan (dev) | (per current naming convention) | West US 2 | B1 | `environment=dev`, `component=api` |
| App Service (prod) | `options-analyzer-api` (with `staging` slot) | West US 2 | n/a | `environment=prod`, `component=api` |
| App Service (dev) | `options-analyzer-api-dev` | West US 2 | n/a | `environment=dev`, `component=api` |
| Static Web App | `options-analyzer-web` (URL: `purple-ground-0d4efed10.4.azurestaticapps.net`) | Central US | Free | `environment=prod`, `component=web` — **orphan; not in request path (see Pattern 7)** |
| Azure SQL Server | `options-analyzer-sql` | West US 2 | n/a | `environment=prod`, `component=database` |
| Azure SQL Database | `options-analyzer-db` | West US 2 | n/a | `environment=prod`, `component=database` |
| Key Vault | `options-analyzer` | West US 2 | Standard | `component=secrets` |
| Storage (unstructured) | `otaunstructured` | West US 2 | Standard LRS | `component=storage` |
| Application Insights | `ota-insights` | West US 2 | n/a | `component=observability` |
| AI Foundry | `ota-foundry-resource` (model: `claude-sonnet-4-6`) | West US 2 | n/a | `component=ai` |

Resource naming standards and tagging conventions are fully specified in `azure-naming-conventions.md`. This table is a snapshot; the conventions doc is the source of truth for naming patterns.

The `otaunstructured` storage account is OTA-specific (per Cross-App Reuse Plane). The future manufacturing app will get its own `mfgunstructured` account.

## Phase History

| Phase | Status | Scope |
|---|---|---|
| Phase 0 | Complete | Security foundation: auth, MFA, JWT tiers (legacy local-password flow; superseded by BFF) |
| Phase 1 | Complete | Config layer + initial market-data adapter (Tradier; subsequently removed) |
| Phase 2 | Complete | Analysis engines: vertical, long-call, directional |
| Phase 2.3 | Complete | Dashboard layout |
| Phase 2.5 | Complete | AI provider layer (Anthropic direct + Foundry adapter) |
| Phase 2.9 | Complete | Multi-strategy scoring engine |
| Phase 2.10 | Complete | Positions Phase 2.10 (Stream B) |
| Phase 2.11 | Active | Black-Scholes probability matrix; structured Claude evaluation; trade detail Sections A–E |
| Phase 3 (general) | Active | Schwab OAuth + portfolio (Schwab is the sole Active market-data provider) |
| Phase 3.3 | Planned | Backtesting engine — Polygon.io as recommended historical data provider; 12 specific test securities; daily snapshot collection via Schwab already specified |
| Phase 3.5 | Planned | Additional signal sources (social sentiment, fundamentals) |
| Phase 3.6 | Planned | Insight Engine domain expansion |
| Phase 4 | Not started | MCP integration |
| Phase 5 | Not started | Live trading (order execution, per-trade MFA) |
| Architecture Optimization | In flight | Drift cleanup informed by 2026-04-30 reviews — see Cleanup Roadmap appendix |

Phase numbers are not strict ordering; phases overlap and some are perpetual (Insight Engine domain expansion will continue indefinitely). The phase tracker exists to communicate roadmap intent, not to enforce sequencing.

---

# Appendix: Cleanup Roadmap

The Architecture Optimization Epic (OTA-535) tracks the active drift items identified by the 2026-04-30 GPT-5.4 and Opus-4.7 architectural reviews. Items are organized by priority. Each is a candidate Story under the Epic; Don will validate scope and create the actual Stories.

## Must Fix — Correctness, Security, Active Pain

| Item | Why | Source |
|---|---|---|
| Add `user_id` filter to `DELETE /recommendations/{trade_key}` | Data isolation bug — any authenticated user could delete another user's recommendation | Opus-4.7 review |
| Close `FoundryEvalAdapter` httpx client on lifespan shutdown | Resource leak; not called today | Opus-4.7 review |
| Change scheduler shutdown from `wait=False` to `wait=True` | In-progress monitor runs can be abandoned mid-write on process exit | Opus-4.7 review |
| Audit `skip_auth` default and env guards | Production safety — accidental enable would bypass all auth | Opus-4.7 review |
| Initialize Alembic with baseline migration matching production schema | OTA-522. No production schema change can ship safely without it | OTA-522, both reviews |

## Should Fix — Drift, Duplication, Cognitive Load

| Item | Why | Source |
|---|---|---|
| Merge AI stacks: delete `app/providers/ai/` directory after migrating `agent_routes.py` to use `FoundryEvalAdapter` | Two complete AI invocation stacks doing overlapping jobs | Both reviews |
| Migrate `TRADE_EVALUATION_SYSTEM_PROMPT` and `FOLLOW_UP_SYSTEM_PROMPT` to `app/skills/trade-evaluation/SKILL.md` | Closes the Pattern 2 violation in the primary evaluation path | Both reviews |
| Retire `entra_auth_routes.py` (MSAL bridge) | Returns JWT to browser, violating Pattern 6 | Both reviews |
| Retire `auth_routes.py` (legacy local-password flow) or restrict to `/register` only | Three auth flows registered simultaneously | Opus-4.7 review |
| Rename `agent_routes.py` → `trade_evaluation_routes.py`, `agents_routes.py` → `position_monitor_routes.py` | Daily cognitive trap from singular/plural file naming | Both reviews |
| Rename `ProviderFactory` → `ProviderRegistry` | Misnomer; actual behavior is a singleton container with caching | Opus-4.7 review |
| Wire OTA-525 lifecycle states into `PROVIDER_REGISTRY` and `_SERVICE_REGISTRY` schemas | Lifecycle states defined but not encoded in code today | OTA-525 |
| Formalize `AIAdapter` ABC in `app/ai/base.py` | Adapter contract is convention-only today | Opus-4.7 review |
| Delete `AccountProvider` and `TradingProvider` ABCs from `providers/base.py` | Speculative; zero implementations | Both reviews |
| Resolve `watchlist_routes.py` vs `named_watchlist_routes.py` overlap | Two routes with overlapping semantics for the same user | Opus-4.7 review |
| Consolidate `STRATEGIES` and `STRATEGY_DEFINITIONS` dicts in `strategy_definitions.py` | Two dicts encoding the same DTE ranges with disagreeing values | OTA-513 |
| Decide and implement strategy config persistence model (localStorage vs `strategy_configs` table) | Table exists with no API routes, zero rows | OTA-514 |
| Wire `cors_origins` config setting to `main.py` (currently hardcoded) | Configuration drift | GPT-5.4 review |
| Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` repo-wide | Deprecated in Python 3.12+ | GPT-5.4 review |
| Remove ODBC installer from `main.py` startup | OS-level package install in app code; should be a startup script or custom image | GPT-5.4 review |
| Delete dead frontend files: `_archive/`, `Header.jsx`, `Header.css`, `msalConfig.js`, orphaned CSS files, `_old.png`, `react.svg` | Dead weight, surfaces in greps | Both reviews |
| Delete dead model: `SchwabToken` table from `database.py` and drop the table | Real DB table with no data, intentionally unused | GPT-5.4 review |
| Delete `app/providers/tradier.py` | Tradier is Removed per OTA-524; adapter file still in tree | Both reviews |
| Delete dev artifacts from repo root: `scratch/`, `ota-commits.txt`, `startup.log`, `db-url-setting.json`, `jira_updates/`, `agents-qa-system.zip` | Repo hygiene | GPT-5.4 review |
| Delete `.claude/worktrees/peaceful-wu/` git worktree | Duplicate code visibility in greps | Opus-4.7 review |
| Add `.gitignore` entries: `options_analyzer.db`, `cert.pem`, `key.pem`, `startup.log` | Stop committing these | GPT-5.4 review |

## Nice to Improve — Polish, Future-Proofing

| Item | Why | Source |
|---|---|---|
| Split `database.py` (928 lines) into per-domain modules | Cognitive load; not breaking anything | Both reviews |
| Extract `main.py` lifespan setup into `startup.py` helpers (after AI merge + auth retirement reduce its size naturally) | Readability | Both reviews |
| Move `_pkce_cache` from in-process dict to Azure SQL session table | Multi-instance safety (latent bug) | Opus-4.7 review |
| Standardize PK types across tables (currently mix of `String(36)` and `Integer`) | Cross-join consistency | Opus-4.7 review |
| Add OTel instrumentation to auth, market-data, and DB layers | Currently AI-only | Opus-4.7 review |
| Add `agent_run_log` retention policy (archive to blob after 12 months) | Unbounded table growth | Opus-4.7 review |
| Continue OTA-495 extraction: move display formatting precision rules and health grade letter/color mapping from CLAUDE.md to `business-rules.md` | Complete the "no business rules in CLAUDE.md" objective | OTA-495 |
| Migrate dev-tooling agents from top-level `agents/` to `dev-agents/` | Eliminate naming collision with `app/agents/` | Opus-4.7 review |

---

## Change Log

| Date | Ticket | Change |
|---|---|---|
| 2026-05-18 UTC | OTA-653 | Introduced ADR convention to this document. Added ADR-1: Scoring Architecture — Deterministic Code with Agent-Driven Judgment. Records the OTA-653 discovery outcome: scoring agent adoption declined; bright-line sites stay code, judgment sites are already agent-driven, consumer-wiring deduplication proceeds as housekeeping under OTA-535. |
| 2026-05-11 UTC | OTA-635 | Strategy System section amended. Removed the "Strategy identity is not tied to credit vs debit structure" framing, which proved trading-incorrect in production: bear_put debit spreads were scored against Steady Paycheck (a credit-focused strategy) producing scores like 57.00 while the narrative simultaneously rejected them as structurally incompatible — generating contradictory verdicts (WAIT pill with PASS narrative). New framing: strategy and structure remain technically orthogonal axes, but each strategy declares an explicit `compatible_structures` map. The scorer gates at pipeline entry; incompatible pairs return null and never reach Foundry. Canonical compatibility map lives in `business-rules.md` → Strategy Scoring. This decision is also a prerequisite for the future strategy-taxonomy redesign (mechanics-based names cannot replace cute names while pretending strategies are structure-agnostic). |
| 2026-05-06 UTC | OTA-601 | Added § Deployment Architecture subsection "Cold-start and runtime OS dependencies" recording the OTA-553 Option B decision: ODBC Driver 18 install in `app/main.py` lifespan is the intentional pattern. Documents the ~90s cold-start cost mitigated by Always On, the deferred Option A alternative (custom container image), and the explicit prohibition against retrying the user-supplied `startup.sh` approach (OTA-545 Phase 2, reverted 2026-05-02). |
| 2026-05-06 03:00 UTC | OTA-554 | Corrected Pattern 7 and Deployment Architecture to reflect actual request routing: Cloudflare proxies custom domains (`oa-dev.tmtctech.ai`, `oa.tmtctech.ai`) directly to the App Service — the SWA is not in the request path. Added "Request Routing — Cloudflare to App Service Direct" subsection with verification commands and health endpoint inventory. Fixed SWA SKU (was "Standard", actually "Free") and URL in Azure Resources Summary. Marked SWA as orphan candidate for cleanup. Removed incorrect claims that the `static/` directory is absent from the deployment artifact and that the SPA fallback in `main.py` is dead code — the build workflow bundles the SPA into `static/` and the App Service actively serves it. |
| 2026-05-01 21:30 UTC | OTA-540 | Schema Migration Strategy section updated: Alembic is now operational (baseline `f9e59a180957` ships with OTA-540). `init_db()` now runs `alembic upgrade head` in dev/staging; production migrations are manual (stamping procedure in `docs/runbooks/alembic-stamp-prod.md`). Updated § 2 to remove the "OTA-522 remains open" note and document the prod migration deploy procedure. |
| 2026-04-30 23:30 UTC | OTA-535 | Updated placeholder references to real ticket numbers throughout the document. Architecture Optimization Epic is OTA-535. New TMTC Application Framework OTAR Category is OTAR-27. The 12 cluster Stories (OTA-536 through OTA-547) and four reparented predecessor Stories (OTA-513, OTA-514, OTA-522, OTA-525) are now siblings under OTA-535. |
| 2026-04-30 22:50 UTC | OTA-495 | Added Roadmap Reference section after Source of Truth Documents, mapping each architectural pattern and engine to its umbrella OTAR Category. Establishes the OTA → OTAR Polaris-link relationship as the canonical strategic-prioritization linkage. Replaces the implicit "phase number" prioritization scheme that previously created cross-talk. |
| 2026-04-30 22:30 UTC | Architecture Optimization Epic (OTA-535) | Complete rewrite. Reorganized into seven categories: Background and Patterns, Data, API and Integration, AI Model Interaction, Application Patterns and Engines, Observability and Operations, Software Development and Deployment. Absorbed `project-hierarchy.md` content (directory tree → System Structure; API endpoints → Key API Endpoints; Azure resources → Azure Resources Summary; phase tracker → Phase History); `project-hierarchy.md` is now scheduled for deletion. Rewrote Pattern 7 from "one App Service serves API + SPA" to "Two Deployables, One Logical App, One Origin" reflecting Path B decision (SWA frontend, App Service backend, SWA-proxied unified origin). Added new sections: Provider Lifecycle State Machine (formalizes OTA-525 with state table, transition rules, and current state of each provider); AI Adapter Contract (single `AIAdapter` ABC target with documented `chat()` shape); Schema Migration Strategy (commits to Alembic per OTA-522 with expand/contract discipline); Resource Shutdown Discipline (explicit list of resources requiring lifespan close); Data Isolation Invariant (every CRUD endpoint filters by user_id); Cross-App Reuse Plane (OTA + manufacturing app sharing strategy with `framework-portable` tag, per-app storage accounts, SKILL.md domain split); Cleanup Roadmap appendix with 30+ items organized must-fix / should-fix / nice-to-improve, citing the 2026-04-30 GPT-5.4 and Opus-4.7 reviews. Removed business-rule content (scoring formulas, gate thresholds, health grade math, position lifecycle state rules) and replaced with pointers to `business-rules.md`. Updated Source of Truth Documents inventory to mirror CLAUDE.md. Updated to reflect cancelled stories OTA-244, OTA-246, OTA-247, OTA-474, OTA-475, OTA-521. |
| 2026-04-11 22:00 | (prior) | Previous version. See git history for prior changelog. |
