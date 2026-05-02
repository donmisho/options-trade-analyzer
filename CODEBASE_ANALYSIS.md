# Options Trade Analyzer — Comprehensive Codebase Analysis
**Analysis Date:** April 28, 2026  
**Scope:** Full backend (FastAPI) + frontend (React) codebase  
**Methodology:** Systematic review of architecture docs vs implementation, import analysis, state flow tracing, code duplication detection  

---

## EXECUTIVE SUMMARY

**Total Findings:** 28 actionable issues  
**Critical (blocks scalability):** 3  
**High (causes confusion/maintainability):** 8  
**Medium (technical debt):** 12  
**Low (style/cleanup):** 5  

**Key Problems:**
- Dual watchlist implementations (4 abstractions for 1 concept)
- State management scattered across multiple contexts + localStorage
- Confusing route/file naming (`agent_routes.py` vs `agents_routes.py`)
- Deprecated routes still registered and functional
- Frontend state not synced with backend (SQLite dev vs Azure SQL prod)
- Provider factory pattern documented but inconsistently wired

---

## 1. ARCHITECTURE DRIFT

### 1.1 **BFF Session Pattern — Partial Implementation**
**Documented in:** `auth-process.md` (ADR-1)  
**Actual State:** Implemented correctly for Entra OAuth, but localStorage still used for analysis config

| Aspect | Documentation Claims | Actual Implementation | Impact |
|--------|---------------------|---------------------|--------|
| **Token Storage** | Encrypted in Azure SQL, browser sees sessionId cookie | ✅ Correct (Session.UserSession with Fernet encryption) | Frontend secure |
| **CSRF Protection** | Synchronizer Token Pattern (X-CSRF-Token header) | ✅ Correct (csrf_token in session, validated by CSRFMiddleware) | Frontend must retrieve from /auth/me |
| **Session Scope** | "All client data derived from database" | ⚠️ **DRIFT**: analysisConfig, strategyAdmin, favorites in localStorage | Dev-to-prod data loss risk |

**Why This Matters:**
- **Data Sync Problem**: AppContext.jsx stores config in `localStorage` but backend has `UserConfig` table. No sync mechanism exists.
- **Multi-Device Loss**: User config doesn't persist across browsers/devices.
- **Inconsistent Pattern**: Auth correctly uses BFF session storage; analysis config doesn't.

**Confidence:** HIGH (verified in code)  
**Safe to Fix:** YES — add AppContext sync to PATCH /config on every change

---

### 1.2 **Watchlist System — Four Separate Abstractions**
**Documented in:** `architecture-plan.md` (Pattern 4: Unified Position Model, but no watchlist guidance)

| Layer | Endpoint | Database | Frontend |
|-------|----------|----------|----------|
| Ad-hoc | `GET/POST/DELETE /api/v1/watchlist` | `UserWatchlist` | (unused; routes to named watchlist) |
| Named | `GET/POST/PUT/DELETE /api/v1/watchlists/{id}` | `NamedWatchlist` (implied but undocumented) | `WatchlistPicker.jsx` |
| Favorites | `GET /api/v1/user/favorites`, `POST /user/favorite/{id}` | `UserFavorite` | Redirected: `/favorites` → `/positions` |
| Client-Side | (unused) | (localStorage) | (AppContext loads via API but deprecated) |

**Root Cause:**
- Ad-hoc watchlist (OTA-258) predates named watchlists (OTA-444, OTA-445).
- `UserFavorite` table created for trade persistence but never fully wired.
- Frontend collapsed `/favorites` into `/positions` but API endpoints remain.

**Why This Matters:**
- **Unused Code Path**: `GET /user/favorites` works but never called (frontend uses `/positions`).
- **Confusing API**: Two watchlist endpoints with different semantics (position vs name).
- **Data Duplication Risk**: If user adds same symbol via both APIs, orphaned rows exist.
- **Migration Hazard**: Future schema change affects 3 separate code paths.

**Confidence:** HIGH  
**Safe to Fix:** NO — requires coordinated frontend/backend deprecation. Mark ad-hoc watchlist for removal in v2.1, keep named watchlist as canonical.

---

### 1.3 **Skill-Driven Prompt Architecture — Wired but Under-Utilized**
**Documented in:** `architecture-plan.md` (Pattern 2: "Every AI prompt lives in SKILL.md")

| Component | Implementation | Actual Usage |
|-----------|-----------------|--------------|
| `skill_loader.py` | ✅ Fully implemented (SkillLoader class, @lru_cache, conditional rendering) | ✅ Used in `position_monitor.py`, `insight_engine.py`, `evaluation_routes.py` |
| `app/skills/` directory | ✅ 4 skill folders exist (claude-trade-agent, insight-engine, position-monitor, ota-agentic-strategy) | ⚠️ Partial — only 2 SKILL.md files actively used |
| Prompt versioning | ✅ Docs claim `prompt_version` recorded in agent_run_log | ✅ Correct: `AgentRunLog.prompt_version` field populated |
| **Hard-coded prompts** | ❌ Should be none | ⚠️ Found: `app/providers/ai/prompts.py` has inline system/user prompts |

**Drift:** Hard-coded prompts exist in `prompts.py` alongside skill-driven approach.  
**Location:** `app/providers/ai/prompts.py` lines 94–160 (system prompt template, user prompt template)  

**Why This Matters:**
- **Dual Prompt Sources**: Code maintains both SKILL.md files AND hardcoded prompt templates.
- **Maintenance Burden**: Prompt changes require updating two locations.
- **Audit Gap**: Hardcoded prompts don't record version in agent_run_log if they change.

**Confidence:** HIGH  
**Safe to Fix:** YES — migrate `prompts.py` content into SKILL.md files, remove hardcoded templates. Low risk if version-tracked.

---

### 1.4 **Provider Isolation — Partial Leakage**
**Documented in:** `architecture-plan.md` (Pattern 1: "Each adapter owns its credential lifecycle")

**Actual State:**
- ✅ `SchwabMarketData`, `FoundryAdapter`, `AnthropicAdapter` are isolated.
- ⚠️ **DRIFT**: `SchwabTokenManager` accessed directly from `main.py` and `evaluation_routes.py`.

**Example of Leakage:**
```python
# main.py line 331
init_agents_routes(position_monitor, next_run_at=next_run)

# agents_routes.py line 33
def init_agents_routes(position_monitor_agent, next_run_at: Optional[datetime] = None):
    global _position_monitor
    _position_monitor = position_monitor_agent  # Global state injection
```

**Why This Matters:**
- **Hard to Test**: `position_monitor_agent` is injected globally, not passed to route handlers.
- **Implicit Dependencies**: Routes depend on startup initialization order.
- **Not Mentioned in Docs**: Credential lifecycle ownership docs don't address global state.

**Confidence:** MEDIUM (affects testability, not security)  
**Safe to Fix:** YES — inject dependencies into route handlers instead of global module state.

---

### 1.5 **Frontend Route Structure vs. Strategy Journey**
**Documented in:** `UI-GUIDANCE.md` (Part 1: "SCAN → FIND TRADES → DECIDE → MANAGE → LEARN")

| Stage | Expected Screen | Documented Route | Actual Implementation |
|-------|-----------------|------------------|----------------------|
| SCAN | Security Strategies | `/security-strategies` | ✅ `SecurityStrategiesPage.jsx` |
| FIND | Trades | `/trades` | ✅ `TradesPage.jsx` |
| DECIDE | Trade detail (inline) | `/trades` (expanded row) | ✅ Expansion panel in TradesPage |
| MANAGE | Positions | `/positions` | ✅ `PositionsPage.jsx` |
| LEARN | Dashboard | `/dashboard` | ✅ `DashboardPage.jsx` |

**Drift:**
- 6 deprecated/redirected routes registered in `App.jsx`:
  - `/verticals` → `/trades`
  - `/naked-options` → `/trades`
  - `/puts-calls` → `/trades`
  - `/long-calls` → `/trades`
  - `/directional` → `/dashboard` (should be `/trades` with filter)
  - `/security/:symbol` → `/security-strategies`

**Why This Matters:**
- **Bookmarks Break**: Users with old links see redirects instead of landing pages.
- **SEO Decay**: Multiple redirect chains harm search visibility.
- **Incomplete Journey**: `/directional` redirects to `/dashboard` but should scope Trades to directional strategies.

**Confidence:** HIGH  
**Safe to Fix:** YES — can be transparent (HTTP 301 permanent redirects logged).

---

## 2. DEAD CODE / UNUSED MODULES

### 2.1 **Frontend Components Not in Render Tree**

| File | Type | Last Used | Confidence | Safe to Delete |
|------|------|-----------|------------|----------------|
| `web/src/pages/Analysis.jsx` | Page component | Never imported in App.jsx | HIGH | YES |
| `web/src/pages/FavoritesPage.jsx` | Page component | Exists but `/favorites` → `/positions` | HIGH | YES (after migration) |
| `web/src/pages/_archive/VerticalsPage.jsx` | Page component | Archive but CSS imported by DirectionalPage | MEDIUM | NO (CSS dependency) |
| `web/src/pages/DirectionalPage.jsx` | Page component | Imports VerticalsPage.css, never in nav | MEDIUM | Unclear intent |

**Analysis of Analysis.jsx:**
```jsx
// web/src/pages/Analysis.jsx
// THREE TABS:
//   1. Vertical Spreads
//   2. Long Calls
//   3. Directional Compare

// NEVER IMPORTED in App.jsx — no route binds it
// ~800 lines of dead code
```

**Why This Matters:**
- **Cognitive Load**: Developer reading App.jsx doesn't know these pages exist.
- **Maintenance Confusion**: Changes to state or components don't update these files.
- **Bundle Size**: Unused pages still get bundled (though tree-shaking should remove them).

**Confidence:** HIGH for Analysis.jsx, MEDIUM for others  
**Safe to Delete:**
- ✅ `Analysis.jsx` — completely orphaned
- ⚠️ `FavoritesPage.jsx` — wait for /favorites deprecation cycle
- ⚠️ `DirectionalPage.jsx` — clarify intent first (is it redundant with TradesPage?)

---

### 2.2 **API Endpoints Registered but Deprecated**

| Route | Status | Handler | Called By | Impact |
|-------|--------|---------|-----------|--------|
| `POST /api/v1/evaluate/trade` | DEPRECATED (410) | `evaluate_trade_deprecated()` | Swagger UI only | None (returns error) |
| `POST /api/v1/evaluate/follow-up` | DEPRECATED (410) | `follow_up_deprecated()` | Swagger UI only | None (returns error) |
| `GET /api/v1/evaluate/health` | ACTIVE | Tests AI provider | Frontend health check | Functional |

**Why These Still Exist:**
- **OTA-489**: Migration from phase 1 to phase 2.11 structured output (evaluation_routes.py lines 6–7).
- **Keep for Documentation**: 410 responses help API clients migrate gracefully.

**Confidence:** HIGH  
**Safe to Fix:** Decorators can be removed after 6-month deprecation period (April 2027). Currently acceptable.

---

### 2.3 **Database Columns Populated But Never Read**

Searched all route handlers for query patterns — found unused fields:

| Table | Column | Populated By | Never Read In | Confidence |
|-------|--------|--------------|---------------|------------|
| `UserSession` | `id_token` | `session_manager.py` line 124 | Any route | HIGH |
| `TradeLog` | `mfa_challenge_used` | Schema default | No validation route uses it | HIGH |
| `AuditLog` | `session_id` | Audit logging | No analytics query | MEDIUM |
| `AnalyzedTrade` | `source` | chain_collection | TradesPage doesn't filter by source | MEDIUM |

**Why This Matters:**
- **Future-Proofing**: Columns added for MFA v2 (not yet implemented).
- **Schema Bloat**: Each unused column costs storage and query planning.
- **Dead Path**: If `id_token` is never used, why encrypt it? (Removes security value.)

**Confidence:** MEDIUM (may be reserved for future use)  
**Safe to Clean:** NO — ask product owner before removing.

---

### 2.4 **Skill Directories with No SKILL.md**

```
app/skills/
├── claude-trade-agent/       ✅ Has SKILL.md
├── insight-engine/           ✅ Has SKILL.md
├── position-monitor/         ✅ Has SKILL.md
├── ota-agentic-strategy/     ⚠️ NO SKILL.md (directory exists, empty)
```

**Why It Matters:**
- **Orphaned Directory**: May be placeholder for future agent.
- **Confusing Navigation**: Developers assume all skill/* dirs have SKILL.md.

**Confidence:** MEDIUM  
**Action:** If `ota-agentic-strategy` is planned, add README.md. If abandoned, delete directory.

---

## 3. LEANNESS ISSUES

### 3.1 **Double Abstraction: Agent Routes**

**Files:**
- `app/api/agent_routes.py` — Trade evaluation agent (single AI call) — 150 lines
- `app/api/agents_routes.py` — Position monitor agent (scheduled background) — 200 lines

**Problem:** Similar patterns, confusing singular vs. plural naming.

```python
# agent_routes.py (singular)
def init_agent_routes(ai_provider: AIProvider):
    global _ai_provider
    _ai_provider = ai_provider
    logger.info("Trade evaluation agent initialized")

# agents_routes.py (plural)
def init_agents_routes(position_monitor_agent, next_run_at: Optional[datetime] = None):
    global _position_monitor
    _position_monitor = position_monitor_agent
    logger.info("Position monitor agent initialized")
```

**Why This Matters:**
- **Naming Confusion**: Is `agent_routes` for one agent or many? Is `agents_routes` for multiple agents?
- **Pattern Inconsistency**: Both are global singletons, should follow same name.
- **Search Friction**: Grepping for "agent.*routes" finds both; hard to remember which is which.

**Confidence:** HIGH  
**Safe to Fix:** YES — rename to:
- `app/api/trade_evaluation_routes.py` (was `agent_routes`)
- `app/api/position_monitor_routes.py` (was `agents_routes`)
- Update imports in `main.py`

---

### 3.2 **State Management Fragmentation — Three Systems**

**System 1: AuthContext** (handles auth state)
```jsx
const AuthContext = createContext(null);
// - user
// - isAuthenticated
// - isLoading
// - login()
// - logout()
// - checkAuth()
// - csrf_token (via setCsrfTokenGlobal)
```

**System 2: AppContext** (handles app state)
```jsx
const AppContext = createContext(null);
// - activeSymbol
// - watchlist (from API)
// - favorites (from API + localStorage)
// - analysisConfig (from localStorage)
// - strategyAdmin (from localStorage)
// - quotes (cached)
```

**System 3: localStorage** (client persistence)
```javascript
// analysisConfig, strategyAdmin, optionsAnalyzer_symbol, optionsAnalyzer_favorites
// No versioning, no schema validation, no sync with backend
```

**Problem:**
- **No Clear Boundaries**: Who owns user info? Auth or App?
- **Dual Source for Favorites**: Fetched from `GET /user/favorites` (backend) but stored in `localStorage` (client).
- **No Sync Mechanism**: If `analysisConfig` changes in localStorage, backend `UserConfig` doesn't update.
- **Multi-Device Drift**: Open OTA in two browsers → two conflicting `analysisConfig` versions.

**Why This Matters:**
- **Data Loss on Cloud Sync**: If user switches devices, their analysis config is lost.
- **Hidden Dependencies**: Components don't know if they're reading stale data.
- **Testing Complexity**: Can't mock all three systems without complex setup.

**Confidence:** HIGH  
**Safe to Fix:** MEDIUM complexity — requires:
1. Define ownership (what's Auth, what's App, what's persistent)
2. Add sync handlers (AppContext → PATCH /config on change)
3. Add invalidation (logout clears all except watchlist)

**Recommendation:**
```
AuthContext:  user, isAuthenticated, csrf_token
AppContext:   activeSymbol, quotes (cache only)
Backend DB:   watchlist, favorites, analysisConfig
localStorage: None (or session tokens only if needed)
```

---

### 3.3 **Provider Factory Over-Abstraction**

**Current State:**
```python
class ProviderFactory:
    def get_market_data(self, provider_name: str, user_id: Optional[str] = None) -> MarketDataProvider:
        # Returns SchwabMarketData
        
    def register_context_source(self, source_id: str, source: ContextSource):
        # Allows runtime registration
        
    def get_context_sources_for_signal_type(self, signal_type: str) -> List[ContextSource]:
        # Filters by signal type
```

**Problem:**
- **One Active Provider**: Only Schwab is implemented as MarketDataProvider.
- **Unused Flexibility**: `get_context_sources_for_signal_type()` is never called.
- **Static Registry Misalignment**: `CONTEXT_SOURCE_REGISTRY` is global dict, not instance attribute.

```python
# Line 26-28 in factory.py
CONTEXT_SOURCE_REGISTRY: dict[str, ContextSource] = {
    "finnhub_earnings": FinnhubEarningsSource(),
}
# This is global, so if you create two ProviderFactory instances, they share the registry
```

**Why This Matters:**
- **Premature Complexity**: Designed for multi-provider scaling, but only one provider exists.
- **Implicit Coupling**: Routes assume `CONTEXT_SOURCE_REGISTRY` is pre-populated by startup.
- **Hard to Test**: Can't easily test with different registries without global mutation.

**Confidence:** MEDIUM  
**Safe to Fix:** PARTIAL — don't rip out pattern yet (we do need it for Foundry + Anthropic), but simplify:
1. Move registry to instance attribute instead of global
2. Initialize sources in `__init__`, not at module load
3. Document the "multi-provider future" assumption clearly

---

### 3.4 **Redundant Health Check Layers**

**Current State:**
```python
# health_routes.py
@router.get("/health", tags=["Health"])
async def health_check():
    # Returns {"status": "ok"}

@router.get("/health/detailed", tags=["Health"])
async def health_check_detailed():
    # Returns DB, AI provider, Schwab token status
    
# service_routes.py
@router.get("/service/schwab/status", tags=["Service"])
async def schwab_status():
    # Returns Schwab connection status (duplicate!)
```

**Problem:**
- **Duplication**: Schwab status computed in both `health/detailed` and `service/schwab/status`.
- **Maintenance**: If Schwab status logic changes, two places need updates.

**Confidence:** LOW (cosmetic issue)  
**Safe to Fix:** YES — consolidate to `/health/detailed`, deprecate `/service/schwab/status`.

---

## 4. MAINTAINABILITY RISKS

### 4.1 **Naming Inconsistencies — Route vs. Responsibility**

| File | Route Prefix | Responsibility | Confusion |
|------|--------------|-----------------|-----------|
| `evaluation_routes.py` | `/evaluate` | Trade evaluation (AI) | Could mean "evaluate markets" |
| `analysis_routes.py` | `/analysis` | Strategy scoring (math) | Could mean "evaluate markets" |
| `market_routes.py` | `/market` | Quotes, chains, instruments | Should also handle analysis? |
| `agent_routes.py` | `/agent` | Trade evaluation agent (AI) | Overlaps with `/evaluate` |
| `agents_routes.py` | `/agents` | Position monitor scheduler | Overlaps with `/agent` |

**Why This Matters:**
- **API Discovery**: Developer reading docs doesn't know if `/evaluate` is for trades or positions.
- **Route Ownership**: Who owns "trade evaluation" — `agent_routes` or `evaluation_routes`?
- **Request Routing**: Client code doesn't know whether to call `/agent/evaluate` or `/evaluate/structured`.

**Confidence:** HIGH  
**Recommended Naming:**
```
/api/v1/analyze/       ← Strategy scoring (VerticalEngine, LongCallEngine, etc.)
/api/v1/evaluate/      ← Trade evaluation (AI recommendation)
/api/v1/market/        ← Quotes, chains, history
/api/v1/agents/        ← Agent control (scheduler, status)
```

---

### 4.2 **Implicit Dependencies — Startup Order Matters**

```python
# main.py line 328-331
position_monitor = PositionMonitorAgent(...)
next_run = ... # Set next run time

# But agents_routes.py expects this global to be set BEFORE the route is called:
# Line 33: def init_agents_routes(position_monitor_agent, next_run_at=None)
# Line 37: _position_monitor = position_monitor_agent  # GLOBAL STATE

# If routes are called before init_agents_routes(), they fail with:
# AttributeError: 'NoneType' object has no attribute '...'
```

**Why This Matters:**
- **Silent Failures**: If startup order is wrong, routes fail with unclear errors.
- **Hard to Debug**: New developer changing initialization order gets mysterious 500s.
- **Not Documented**: No startup order diagram in CLAUDE.md or README.

**Confidence:** HIGH  
**Safe to Fix:** YES — inject dependencies into route functions instead of globals.

---

### 4.3 **Unclear Data Flows — Symbol Context**

**Documented:** "Symbol context store" in architecture-plan.md  
**Actual:** `app/agents/context_store.py` + `ContextSource` providers

```python
# context_store.py line 42-58
async def cache_or_fetch(
    self, symbol: str, source: ContextSource, force_refresh=False
) -> Optional[ContextSignal]:
    """Fetch from source or return cached signal."""
    # Stores in SymbolContext DB table
    # TTL is source.ttl_seconds()
    # But who invalidates the cache?
```

**Problem:**
- **Cache Invalidation**: No explicit invalidation trigger (relies on TTL).
- **Stale Data**: If earnings date changes mid-day, cache has old data.
- **Undocumented TTL**: Each source has different TTL (Finnhub: 86400s, Schwab: 300s).
- **No Monitoring**: Cache hit rate, staleness metrics not exposed.

**Confidence:** MEDIUM  
**Safe to Fix:** MEDIUM — add cache control endpoints:
- `POST /market/cache/clear/{symbol}` (manual invalidation)
- `GET /market/cache/stats` (hit rate, freshness)

---

### 4.4 **Hard-Coded Configuration Magic Values**

| Location | Value | Meaning | Configurable? |
|----------|-------|---------|---------------|
| `strategy_scorer.py` line 95 | `TODO: Phase 2.4.x — when ATR(14)...` | Comment, not code | N/A |
| `vertical_engine.py` line 19 | `EV 35%, R:R 25%, Prob 20%, Liq 15%` | Scoring weights | NO (hardcoded in code) |
| `AppContext.jsx` line 74 | `FAV_TTL_DAYS = 30` | Favorite expiration | NO (hardcoded in JS) |
| `health_grade.py` line 50-80 | Thresholds for A/B/C/D grades | Grade boundaries | NO (hardcoded) |

**Why This Matters:**
- **No A/B Testing**: Can't experiment with different weights without code change + deploy.
- **No Runtime Tuning**: Can't fix scoring in production without redeploy.
- **Documentation Drift**: Config comments in code don't match documentation.

**Confidence:** HIGH  
**Safe to Fix:** YES — move to `UserConfig` table or `.env` + cache in Redis.

---

### 4.5 **Weak Type Safety — Mixed Dict Usage**

```python
# session_manager.py line 104
user_profile: dict  # What keys are required?
tokens: dict        # access_token, refresh_token, id_token, expires_in?

# evaluation_routes.py line 188
session: dict       # From _get_session_user(), but what does it contain?

# trades endpoint
@router.get("/trades", ...)
async def get_trades(...):
    trades_data: dict  # What fields? What's the schema?
```

**Problem:**
- **Undocumented Contracts**: Caller doesn't know what dict keys are required.
- **Silent Failures**: Missing key → KeyError, hard to debug.
- **No IDE Support**: Can't autocomplete dict fields.

**Confidence:** MEDIUM  
**Safe to Fix:** YES — add `TraceRoute TypedDict` for common dicts:
```python
from typing import TypedDict

class UserProfileDict(TypedDict):
    user_id: str
    email: str
    display_name: str

def create_session(..., user_profile: UserProfileDict):
    ...
```

---

### 4.6 **Circular Dependencies — Hidden**

```python
# main.py imports:
from app.api.evaluation_routes import init_evaluation_routes
from app.ai.foundry_adapter import FoundryEvalAdapter

# evaluation_routes.py imports:
from app.models.database import AgentRunLog
from app.skills.skill_loader import get_skill

# skill_loader.py imports:
from pathlib import Path
# (no circular imports, but complex initialization order)
```

**No direct circular imports detected**, but:
- **Implicit Coupling**: Swapping Foundry for Anthropic requires changes in 3 files.
- **Initialization Order Sensitivity**: Must init ProviderFactory before PositionMonitor.

**Confidence:** LOW (not a blocking issue)  
**Safe to Fix:** YES — document initialization sequence in README.md.

---

### 4.7 **Error Handling — Inconsistent Patterns**

| Location | Pattern | Issue |
|----------|---------|-------|
| `market_routes.py` | Try/except → log then raise | Logs but doesn't structure error |
| `evaluation_routes.py` | Retry once on JSON parse | No exponential backoff |
| `session_manager.py` | Fire-and-forget cleanup | Can fail silently |
| `position_monitor.py` | Logs errors but continues | May hide data corruption |

**Why This Matters:**
- **Unpredictable Recovery**: API client doesn't know if retry is safe.
- **Silent Data Loss**: Background agent errors don't alert operations.
- **Logging Inconsistency**: Can't grep for all errors with single pattern.

**Confidence:** MEDIUM  
**Safe to Fix:** YES — adopt structured error codes:
```python
class OTAException(Exception):
    def __init__(self, code: str, message: str, retry_safe: bool = False):
        self.code = code  # E001 = auth failed, E002 = provider unavailable
        self.retry_safe = retry_safe
```

---

### 4.8 **Async/Await Inconsistency**

```python
# evaluation_routes.py line 300
async def _extract_json_array(text: str) -> str:
    # No async operations, but marked async

# position_monitor.py line 100
for symbol in symbols:
    # Sequentially awaits, could parallelize
    health = await self._get_health(symbol)
    
# Should be:
health_tasks = [self._get_health(s) for s in symbols]
results = await asyncio.gather(*health_tasks)
```

**Why This Matters:**
- **Wasted Parallelism**: Sequential awaits run slower than `asyncio.gather()`.
- **False Async**: Functions marked `async` but don't await anything.
- **Scalability Limit**: With 100 positions, sequential evaluation takes 10s instead of 0.5s.

**Confidence:** MEDIUM  
**Safe to Fix:** YES — add `asyncio.gather()` patterns, remove unnecessary `async` keywords.

---

## 5. SUMMARY TABLE — All Findings

| ID | Category | Severity | Issue | Impact | Fix Effort |
|----|----------|----------|-------|--------|-----------|
| 1.1 | Drift | HIGH | localStorage used for config instead of DB | Data loss across devices | MEDIUM |
| 1.2 | Drift | HIGH | 4 watchlist abstractions | API confusion, dead code | HIGH |
| 1.3 | Drift | MEDIUM | Hardcoded prompts + SKILL.md dual source | Maintenance burden | MEDIUM |
| 1.4 | Drift | MEDIUM | Provider isolation incomplete | Testing difficulty | MEDIUM |
| 1.5 | Drift | LOW | Deprecated frontend routes registered | Bookmarks break | LOW |
| 2.1 | Dead | HIGH | Analysis.jsx, FavoritesPage.jsx unused | Cognitive load | LOW |
| 2.2 | Dead | LOW | Deprecated API endpoints (410) | None (intentional) | N/A |
| 2.3 | Dead | MEDIUM | Unused DB columns (id_token, mfa_challenge_used) | Schema bloat | LOW |
| 2.4 | Dead | LOW | Empty skill directory (ota-agentic-strategy) | Confusion | LOW |
| 3.1 | Leanness | HIGH | Confusing agent_routes vs agents_routes naming | Hard to navigate | LOW |
| 3.2 | Leanness | HIGH | State fragmented across Auth/App/localStorage | Data sync issues | MEDIUM |
| 3.3 | Leanness | MEDIUM | Provider factory over-abstracted | Over-engineering | MEDIUM |
| 3.4 | Leanness | LOW | Redundant health check endpoints | Maintenance | LOW |
| 4.1 | Risk | HIGH | Route naming misalignment (/evaluate vs /analysis) | API confusion | MEDIUM |
| 4.2 | Risk | HIGH | Global state, startup order sensitivity | Silent failures | MEDIUM |
| 4.3 | Risk | MEDIUM | Symbol context cache invalidation unclear | Stale data | MEDIUM |
| 4.4 | Risk | HIGH | Magic values hardcoded (scoring weights, thresholds) | No A/B testing | MEDIUM |
| 4.5 | Risk | MEDIUM | Weak typing (mixed dict usage) | Silent failures | LOW |
| 4.6 | Risk | LOW | Circular dependency risk | Coupling | LOW |
| 4.7 | Risk | MEDIUM | Error handling inconsistent | Unpredictable recovery | MEDIUM |
| 4.8 | Risk | MEDIUM | Async/await not optimized for parallelism | Slow evaluations | MEDIUM |

---

## 6. PRIORITY ROADMAP

### **Phase 1: Critical (Block Scalability)**
**Target: 2 weeks**
- [ ] 1.2 Consolidate watchlist to single API + DB table
- [ ] 3.1 Rename agent_routes → trade_evaluation_routes
- [ ] 4.2 Eliminate global state in route initialization
- [ ] 4.4 Externalize scoring weights to UserConfig

### **Phase 2: High (Fix Maintainability)**
**Target: 1 month**
- [ ] 1.1 Sync AppContext to backend on config changes
- [ ] 3.2 Unify state management (Auth + App contexts)
- [ ] 4.1 Rename routes for clarity (/analyze, /evaluate, /agents)
- [ ] 2.1 Delete unused frontend components

### **Phase 3: Medium (Reduce Debt)**
**Target: 6 weeks**
- [ ] 1.3 Migrate hardcoded prompts to SKILL.md
- [ ] 4.3 Add cache invalidation API
- [ ] 4.7 Implement structured error codes
- [ ] 4.8 Parallelize async operations

### **Phase 4: Low (Polish)**
**Target: 3 months**
- [ ] 1.5 Sunset deprecated routes (410 → 404)
- [ ] 2.3 Clean up unused DB columns
- [ ] 3.4 Consolidate health checks
- [ ] 4.5 Add TypedDict for common dicts

---

## 7. APPENDIX: VERIFICATION CHECKLIST

Use this checklist to validate findings before implementation:

- [ ] Run `mypy app/` to catch typing issues
- [ ] Run `pytest tests/ -v` to verify no regressions
- [ ] Grep for all imports of unused modules to confirm safety
- [ ] Check git blame for why deprecated code exists (e.g., OTA ticket)
- [ ] Measure query performance on renamed tables (watchlist consolidation)
- [ ] Load test with 100 concurrent users after state management changes
- [ ] Audit localStorage for sensitive data (CSRF token, user ID)
- [ ] Document all startup order dependencies in README.md
