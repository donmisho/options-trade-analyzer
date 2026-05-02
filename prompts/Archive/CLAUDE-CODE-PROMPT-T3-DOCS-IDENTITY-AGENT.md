# CLAUDE-CODE-PROMPT-T3-DOCS-IDENTITY-AGENT.md

---
allowedTools:
  - Read
  - Write
  - Edit
  - Bash
  - mcp__atlassian__getJiraIssue
  - mcp__atlassian__transitionJiraIssue
---

## Context

You are creating the identity management documentation and the Identity & Security Agent for the Options Trade Analyzer. The BFF backend (T1) and frontend migration (T2) are already committed. This prompt documents what was built and creates the automated validation agent.

**Read these files first — do not skip:**
```bash
cat CLAUDE.md
cat architecture-plan.md
cat SCHWAB-LOGIN-PROCESS.md
cat app/auth/session_manager.py
cat app/auth/providers.py
cat app/api/identity_routes.py
cat app/middleware/csrf.py
cat app/auth/dependencies.py
cat web/src/context/AuthContext.jsx
cat web/src/components/ProtectedRoute.jsx
cat web/src/api/client.js
ls agents/
cat agents/qa-ux/CLAUDE.md | head -50
cat agents/qa-data/CLAUDE.md | head -50
```

**Jira tickets this prompt covers:**
- OTA-466: Write auth-process.md + Update architecture-plan.md and CLAUDE.md
- OTA-467: Agent Scaffold, Validation Test Suite, Diagnostic Mode

---

## Phase 1: auth-process.md (OTA-466)

Create `claude_context/auth-process.md` with a timestamp header per house style:

```
# Options Analyzer — auth-process.md (Updated YYYY-MM-DD HH:MM)
```

### Section 1: Architecture Decision Record

Write an ADR covering:
- **Status:** Accepted
- **Context:** MSAL.js redirect flow caused recurring production login failures (redirect loops, stale localStorage tokens, timing issues with `handleRedirectPromise`). Multi-IdP support and cross-cloud token management required.
- **Decision:** Backend-for-Frontend (BFF) pattern. FastAPI acts as OIDC confidential client. React SPA uses HttpOnly session cookies. No tokens in the browser.
- **Alternatives Considered:**
  1. Fix MSAL.js redirect bugs (tactical, recurring, Entra-only)
  2. Third-party auth gateway like Auth0 (unnecessary cost, only solves half the problem)
- **Consequences:** All auth complexity lives server-side. Adding a new IdP is a config change. Frontend auth code is ~50 lines total. Trade-off: session cookie requires CSRF protection (implemented).

### Section 2: Flow Diagrams

Write ASCII sequence diagrams (like the one in SCHWAB-LOGIN-PROCESS.md) for:

1. **Initial Login Flow:**
   Browser → GET /auth/login → FastAPI builds auth URL → redirect to Entra → user authenticates → Entra redirects to /auth/entra/callback with code → FastAPI exchanges code for tokens (server-to-server) → creates session in SQL → sets HttpOnly cookie → redirects to SPA → SPA calls GET /auth/me → receives user profile

2. **Session Resume (page refresh):**
   Browser sends cookie → SPA calls GET /auth/me → FastAPI reads cookie → looks up session → returns user profile (or refreshes tokens if needed)

3. **Token Refresh (transparent):**
   /auth/me detects token_expires_at < 5 minutes → SessionManager.refresh_tokens() → POST to Entra token endpoint with refresh_token + client_secret → updates session row → returns user profile

4. **Logout:**
   SPA calls POST /auth/logout with CSRF token → FastAPI deletes session → clears cookie → SPA redirects to login page

5. **Schwab Auth (coexistence):**
   User is already authenticated via session cookie → clicks Schwab connect → popup to /auth/schwab/login → Schwab OAuth → callback stores Schwab tokens in SchwabTokenManager → popup closes → all market data calls use Schwab tokens, all identity calls use session cookie

### Section 3: Entra App Registration

Document the registration created in OTA-460:
- App name, type (Web / confidential), supported account types
- Redirect URIs (dev + prod)
- API permissions (openid, profile, email, User.Read)
- Client secret management (Key Vault, rotation schedule)
- Keep the old SPA registration labeled as deprecated

### Section 4: Session Lifecycle

- Cookie: `ota_session`, HttpOnly, Secure, SameSite=Lax, path=/
- Session TTL: 24 hours (configurable via `SESSION_TTL_HOURS`)
- Token refresh: automatic when access_token is within 5 minutes of expiry
- Expiry behavior: /auth/me returns 401, frontend redirects to login
- Cleanup: `SessionManager.cleanup_expired()` runs on schedule, fire-and-forget

### Section 5: Multi-IdP Provider Registry

- Location: `app/auth/providers.py`
- How to add a new IdP: add one dict entry with authorize_url, token_url, client_id, client_secret_vault_name, scopes
- Normalized user profile: `{ user_id, email, display_name, provider }`
- Frontend: add a button pointing to `/api/v1/auth/login?provider=<name>`

### Section 6: Cross-Cloud Token Management

Explain how all credentials coexist server-side:
- **Entra tokens:** encrypted in `user_sessions` table, managed by SessionManager
- **Schwab tokens:** in SchwabTokenManager (in-memory dev, Key Vault prod), associated with user session
- **Azure AI Foundry:** API key in Key Vault, accessed via SecretsManager
- **Future AWS:** IAM role or service account key in Key Vault, accessed by a new provider adapter
- **Future Google:** Service account JSON in Key Vault, accessed by a new provider adapter
- Key principle: the browser never sees or stores any of these tokens

### Section 7: Security Controls

- CSRF: custom `X-CSRF-Token` header required on POST/PATCH/PUT/DELETE
- Cookie flags: HttpOnly (no JS access), Secure (HTTPS only), SameSite=Lax
- Session fixation prevention: new session_id on every login
- Token encryption: Fernet, key in Key Vault
- Secret rotation: client secrets have 24-month expiry, Key Vault versioning
- Rate limiting: consider adding to /auth/login in future

### Section 8: Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Login page shows after authenticating | Callback failed silently | Check `?auth_error` query param, check backend logs |
| 401 on all API calls | Session expired or cookie not sent | Check cookie in browser DevTools, verify `credentials: 'include'` |
| 403 on POST/PATCH | Missing CSRF token | Verify `X-CSRF-Token` header in request |
| Schwab shows disconnected | Schwab tokens expired (separate from user session) | Click Schwab connect button |
| Login works in dev, not production | Redirect URI mismatch | Check Entra app registration redirect URIs |
| Cookie not set after callback | SameSite/Secure mismatch | Verify HTTPS on both frontend and backend |

### Section 9: Files Reference

| File | Purpose |
|------|---------|
| `app/auth/providers.py` | IdP provider registry |
| `app/auth/session_manager.py` | Server-side session CRUD + token encryption |
| `app/auth/dependencies.py` | `get_current_user` FastAPI dependency |
| `app/api/identity_routes.py` | BFF auth endpoints (login, callback, me, logout) |
| `app/middleware/csrf.py` | CSRF protection middleware |
| `web/src/context/AuthContext.jsx` | React auth state + login/logout functions |
| `web/src/components/ProtectedRoute.jsx` | Route guard |
| `web/src/api/client.js` | API client with cookie + CSRF support |
| `auth-process.md` | This document |

---

### Update architecture-plan.md

Add to the "Core Architectural Patterns" section, after Pattern 3:

```markdown
### Pattern 4: Backend-for-Frontend Identity

All user authentication flows through FastAPI as a confidential OIDC client.
The React SPA never handles tokens — it uses HttpOnly session cookies set by
the backend. Adding a new identity provider (Google, GitHub) requires one
config entry in `app/auth/providers.py` and zero frontend changes.

See `auth-process.md` for full details: flow diagrams, session lifecycle,
multi-IdP registry, and cross-cloud token management.

**Established flows**: Entra ID (OIDC), Schwab (OAuth 2.0 market data)
**Future flows**: Google, GitHub, AWS IAM, Google Cloud service accounts
```

Add to "Phase History":
```markdown
- **Identity Management Foundation**: BFF pattern migration — OTA-455 epic ✅
```

### Update CLAUDE.md

1. In the "Architecture" section, add Pattern 4 reference
2. In "Backend Structure", add `app/middleware/csrf.py` and note `identity_routes.py`
3. In "Development Commands", replace any MSAL references with:
   ```
   ### Identity Management
   - Login: navigate to https://localhost:5173, click "Sign in with Microsoft"
   - Session cookie: `ota_session` (HttpOnly, not visible in JS console)
   - Auth check: curl -b cookies.txt https://127.0.0.1:8000/api/v1/auth/me
   - CSRF: all POST/PATCH/DELETE require X-CSRF-Token header
   ```
4. In "Important Implementation Details", add a "BFF Auth Pattern" subsection referencing auth-process.md
5. Remove any mentions of MSAL, `handleRedirectPromise`, or browser-side token management
6. Add `auth-process.md` to the source-of-truth documents list

### Update SCHWAB-LOGIN-PROCESS.md

Add a note at the top:
```markdown
> **Scope Note:** This document covers Schwab market data OAuth only.
> For user identity management (Entra login, session management, multi-IdP),
> see `auth-process.md`.
```

---

## Phase 2: Identity & Security Agent (OTA-467)

### 2.1 Agent Scaffold

Create the following structure:
```
agents/identity-security/
├── CLAUDE.md
├── tests/
│   ├── __init__.py
│   ├── test_auth_flows.py
│   └── test_security_controls.py
├── diagnose.py
└── baseline.json
```

### 2.2 Agent CLAUDE.md

Write `agents/identity-security/CLAUDE.md`:

```markdown
# Identity & Security Agent

## Purpose
Validates the BFF auth flow, session management, CSRF protection, and cookie
security. Detects regressions after code changes. Diagnoses common auth failures.

## When to Run
- After any change to files in `app/auth/`, `app/api/identity_routes.py`, 
  `app/middleware/csrf.py`, or `web/src/context/AuthContext.jsx`
- After deployment to production
- When auth issues are reported

## Test Inventory

### Auth Flow Tests (test_auth_flows.py)
1. Unauthenticated /me → 401
2. /login redirects to Entra (verify URL structure)
3. /login with invalid provider → 400
4. Session cookie flags (HttpOnly, Secure, SameSite)
5. Session expiry → /me returns 401
6. Logout clears session
7. Schwab routes require auth
8. Health endpoints don't require auth

### Security Control Tests (test_security_controls.py)
1. POST without CSRF token → 403
2. POST with valid CSRF token → passes
3. POST with wrong CSRF token → 403
4. Cookie not accessible via JS (HttpOnly)
5. Session ID is cryptographically random (length, entropy)
6. Tokens in DB are encrypted (not plaintext)

## Running

### Validation Mode
```bash
cd agents/identity-security
python -m pytest tests/ -v --tb=short
```

### Diagnostic Mode
```bash
cd agents/identity-security
python diagnose.py
```

## Regression Detection
Compare results against `baseline.json`. A test that was PASS and is now FAIL 
is a REGRESSION — mark severity BLOCKER. A test that was FAIL and is still FAIL
is a known issue.

After a clean run where all tests pass, update baseline.json with current results.
```

### 2.3 Test Suite

Create `agents/identity-security/tests/test_auth_flows.py`:

```python
"""
Auth flow validation tests.
Uses httpx (async) to test API endpoints directly.
No browser automation needed — these are API-level tests.

Prerequisites:
- Backend running at https://127.0.0.1:8000
- Entra app registration configured
- Database accessible

Note: Tests that require a real Entra login (callback with real code) 
are marked as integration tests and skipped in CI. They run in diagnostic mode.
"""
import httpx
import pytest

BASE_URL = "https://127.0.0.1:8000"

@pytest.fixture
def client():
    return httpx.AsyncClient(base_url=BASE_URL, verify=False)

@pytest.mark.asyncio
async def test_unauthenticated_me(client):
    """GET /auth/me without cookie returns 401"""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_login_redirect(client):
    """GET /auth/login redirects to Entra authorize URL"""
    response = await client.get("/api/v1/auth/login", follow_redirects=False)
    assert response.status_code in (302, 307)
    location = response.headers.get("location", "")
    assert "login.microsoftonline.com" in location
    assert "client_id=" in location
    assert "response_type=code" in location
    assert "code_challenge=" in location
    assert "state=" in location

@pytest.mark.asyncio
async def test_login_invalid_provider(client):
    """GET /auth/login?provider=invalid returns 400"""
    response = await client.get("/api/v1/auth/login?provider=invalid")
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_logout_without_session(client):
    """POST /auth/logout without session returns 401 or 200 (graceful)"""
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code in (200, 401)

@pytest.mark.asyncio
async def test_session_status_unauthenticated(client):
    """GET /auth/session/status without cookie returns authenticated=false"""
    response = await client.get("/api/v1/auth/session/status")
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is False

@pytest.mark.asyncio
async def test_schwab_requires_auth(client):
    """Schwab status endpoint requires user session"""
    response = await client.get("/api/v1/auth/schwab/status")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_health_no_auth(client):
    """Health endpoint accessible without auth"""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
```

Create `agents/identity-security/tests/test_security_controls.py`:

```python
"""
Security control validation tests.
Tests CSRF, cookie flags, and session security.
"""
import httpx
import pytest

BASE_URL = "https://127.0.0.1:8000"

@pytest.fixture
def client():
    return httpx.AsyncClient(base_url=BASE_URL, verify=False)

@pytest.mark.asyncio
async def test_csrf_post_without_token(client):
    """POST to protected route without X-CSRF-Token → 403"""
    # This requires an authenticated session to isolate CSRF from auth
    # Without auth, we get 401 first. Test structure:
    # 1. If we can create a test session, do so
    # 2. POST without CSRF → expect 403
    # For now, verify the middleware is registered by checking that
    # POST without both auth and CSRF returns 401 (auth checked first)
    response = await client.post("/api/v1/positions", json={})
    assert response.status_code == 401  # Auth blocks before CSRF

@pytest.mark.asyncio
async def test_login_redirect_state_signed(client):
    """Verify state parameter in login redirect is signed (not guessable)"""
    response = await client.get("/api/v1/auth/login", follow_redirects=False)
    location = response.headers.get("location", "")
    # Extract state param
    import urllib.parse
    parsed = urllib.parse.urlparse(location)
    params = urllib.parse.parse_qs(parsed.query)
    state = params.get("state", [""])[0]
    # State should be non-empty and reasonably long (signed)
    assert len(state) > 32, f"State param too short ({len(state)} chars), may not be signed"
```

### 2.4 Diagnostic Script

Create `agents/identity-security/diagnose.py`:

```python
"""
Identity & Security Diagnostic Tool.
Run when auth issues are reported to identify root cause.

Usage: python diagnose.py [--base-url https://127.0.0.1:8000]
"""
import asyncio
import sys
import httpx

async def diagnose(base_url: str = "https://127.0.0.1:8000"):
    results = []
    
    async with httpx.AsyncClient(base_url=base_url, verify=False) as client:
        # Check 1: Backend reachable
        try:
            r = await client.get("/api/v1/health")
            results.append(("Backend reachable", r.status_code == 200, f"status={r.status_code}"))
        except Exception as e:
            results.append(("Backend reachable", False, str(e)))
        
        # Check 2: Auth endpoints registered
        try:
            r = await client.get("/api/v1/auth/login", follow_redirects=False)
            results.append(("Auth login route", r.status_code in (302, 307, 400), f"status={r.status_code}"))
        except Exception as e:
            results.append(("Auth login route", False, str(e)))
        
        # Check 3: /me endpoint exists
        try:
            r = await client.get("/api/v1/auth/me")
            results.append(("Auth me route", r.status_code in (200, 401), f"status={r.status_code}"))
        except Exception as e:
            results.append(("Auth me route", False, str(e)))
        
        # Check 4: Session status endpoint
        try:
            r = await client.get("/api/v1/auth/session/status")
            results.append(("Session status route", r.status_code == 200, f"status={r.status_code}"))
        except Exception as e:
            results.append(("Session status route", False, str(e)))
        
        # Check 5: Entra token endpoint reachable
        try:
            r = await client.get("https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration")
            results.append(("Entra reachable", r.status_code == 200, ""))
        except Exception as e:
            results.append(("Entra reachable", False, str(e)))
        
        # Check 6: Login redirect URL well-formed
        try:
            r = await client.get("/api/v1/auth/login", follow_redirects=False)
            loc = r.headers.get("location", "")
            has_client_id = "client_id=" in loc
            has_redirect = "redirect_uri=" in loc
            has_pkce = "code_challenge=" in loc
            ok = has_client_id and has_redirect and has_pkce
            detail = f"client_id={'Y' if has_client_id else 'N'} redirect_uri={'Y' if has_redirect else 'N'} PKCE={'Y' if has_pkce else 'N'}"
            results.append(("Login URL well-formed", ok, detail))
        except Exception as e:
            results.append(("Login URL well-formed", False, str(e)))
    
    # Print results
    print("\n" + "=" * 60)
    print("IDENTITY & SECURITY DIAGNOSTIC REPORT")
    print("=" * 60)
    
    all_pass = True
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        detail_str = f"  ({detail})" if detail else ""
        print(f"  [{status}] {name}{detail_str}")
    
    print("=" * 60)
    print(f"Result: {'ALL CHECKS PASSED' if all_pass else 'FAILURES DETECTED'}")
    print("=" * 60 + "\n")
    
    return 0 if all_pass else 1

if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "https://127.0.0.1:8000"
    exit_code = asyncio.run(diagnose(base))
    sys.exit(exit_code)
```

### 2.5 Baseline

Create `agents/identity-security/baseline.json`:
```json
{
  "generated_at": null,
  "note": "Populate after first clean test run: python -m pytest tests/ -v --json-report --json-report-file=baseline.json",
  "tests": {}
}
```

---

## Phase 3: Commit and Verify

### Verify all docs reference each other correctly:
```bash
grep -l "auth-process" claude_context/ architecture-plan.md CLAUDE.md SCHWAB-LOGIN-PROCESS.md
# Should find references in architecture-plan.md, CLAUDE.md, SCHWAB-LOGIN-PROCESS.md

grep -l "msal\|MSAL\|MsalProvider" CLAUDE.md architecture-plan.md
# Should find NOTHING (all MSAL references removed)
```

### Run the agent:
```bash
cd agents/identity-security
python -m pytest tests/ -v
python diagnose.py
```

## Commit

```
OTA-466 OTA-467 feat: auth-process.md documentation + identity-security agent scaffold
```

After commit, transition OTA-466 and OTA-467 to IN REVIEW (transition ID: 41).
