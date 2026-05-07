# Options Analyzer — auth-process.md (Updated 2026-05-06 UTC)
# Epic: OTA-477 | Feature: OTA-482

## Table of Contents

- [ADR-1: BFF Identity Management](#adr-1-bff-identity-management)
- [ADR-2: Unified Deployment](#adr-2-unified-deployment)
- [Flow Diagrams](#flow-diagrams)
- [Entra App Registration](#entra-app-registration)
- [Session Lifecycle](#session-lifecycle)
- [Multi-IdP Provider Registry](#multi-idp-provider-registry)
- [Identity Credential Management](#identity-credential-management)
- [Deployment Architecture](#deployment-architecture)
- [Security Controls](#security-controls)
  - [CSRF (Synchronizer Token Pattern)](#csrf-synchronizer-token-pattern)
  - [Cookie Security Flags](#cookie-security-flags)
  - [Token Encryption](#token-encryption)
  - [OAuth State Parameter](#oauth-state-parameter)
  - [PKCE (Proof Key for Code Exchange)](#pkce-proof-key-for-code-exchange)
- [Troubleshooting](#troubleshooting)
- [Files Reference](#files-reference)

---

## ADR-1: BFF Identity Management

**Decision Date:** 2026-04 (OTA-455)
**Change Log:** Initial decision

FastAPI acts as a confidential OIDC client using the Backend-for-Frontend (BFF)
pattern. **BFF OIDC is the only sanctioned auth path.** Legacy local-password
auth (`auth_routes.py`) and the MSAL bridge (`entra_auth_routes.py`) were
retired in OTA-538.

- The React SPA never handles, stores, or sees identity tokens
- The backend exchanges authorization codes for tokens server-to-server
- Tokens are encrypted at rest in Azure SQL (`user_sessions` table) using Fernet (AES-128-CBC)
- The browser holds only an `HttpOnly` session cookie with a random 512-bit session ID
- CSRF protection is provided by the Synchronizer Token Pattern (`X-CSRF-Token` header)
- Entra uses certificate-based client assertions (`entra-bff-cert` in Key Vault). Tenant policy blocks client secrets for confidential apps.
- Adding a new IdP requires one config entry in `app/auth/providers.py` and zero frontend changes
- All auth complexity lives server-side. Frontend auth code is ~50 lines total.
- Session state is in Azure SQL — sessions survive server restarts and scale-out.

This document covers **user identity** only. External service credentials (Schwab,
Azure AI Foundry, future data providers) are managed by provider adapters under
Pattern 1 in `architecture-plan.md`.

---

## ADR-2: Unified Deployment

**Decision Date:** 2026-04 (OTA-455)
**Change Log:** Initial decision

FastAPI serves both the API (`/api/v1/*`) and the React SPA (from `static/`
directory) from a single App Service on a single domain (`oa.tmtctech.ai`).
Cloudflare provides CDN and edge caching. One GitHub Actions workflow handles
build and deploy.

- Same-origin cookies work natively — no proxy or CORS workarounds
- Single deployment artifact and pipeline
- Dev mode continues using Vite (port 5173) + FastAPI (port 8000) separately

---

## Flow Diagrams

### 1. Initial Login Flow

```
Browser                  FastAPI                 Entra                    Azure SQL
  |                         |                      |                          |
  |-- GET /auth/login ------>|                      |                          |
  |                         | generate PKCE         |                          |
  |                         | sign state param      |                          |
  |<-- 302 → Entra ---------|                      |                          |
  |                         |                      |                          |
  |-- GET /authorize -------------------------------->|                        |
  |                         |                      | user authenticates        |
  |<-- 302 → /auth/entra/callback?code=... ----------|                        |
  |                         |                      |                          |
  |-- GET /auth/entra/callback?code=&state= -------->|                        |
  |                         | validate state sig    |                          |
  |                         | retrieve PKCE verifier|                          |
  |                         |-- POST /token + assertion + code_verifier ------>|
  |                         |<-- { access_token, refresh_token, id_token } ----|
  |                         | decode id_token claims|                          |
  |                         | encrypt tokens ------->|                        |-- INSERT user_sessions
  |                         |                      |                          |
  |<-- 302 → / + Set-Cookie: ota_session=<id> ------|                        |
  |                         |                      |                          |
  |-- GET /auth/me (cookie) ->|                     |                          |
  |                         |-- SELECT user_sessions WHERE session_id=... ---->|
  |<-- { user_id, email, display_name, csrf_token } |                          |
```

### 2. Session Resume (Page Refresh)

```
Browser                  FastAPI                 Azure SQL
  |                         |                       |
  |-- GET /auth/me (cookie) ->|                     |
  |                         |-- SELECT user_sessions (active, not expired) -->|
  |                         |<-- session row --------|
  |                         | update last_active_at  |
  |<-- { user profile + csrf_token } --------------|
  |                         |                       |
  | [token within 5 min of expiry: background refresh scheduled]
```

### 3. Transparent Token Refresh

```
FastAPI                       Entra                    Azure SQL
  |                              |                          |
  | [background task, not blocking request]
  |-- SELECT session WHERE session_id=... ------------------>|
  |<-- { refresh_token_encrypted } --------------------------|
  | decrypt refresh_token        |                          |
  |-- POST /token + assertion + refresh_token ------------->|
  |<-- { new access_token, new refresh_token, expires_in } -|
  | encrypt new tokens           |                          |
  |-- UPDATE user_sessions SET access_token_encrypted, token_expires_at --->|
  | [request continues uninterrupted — user never sees this]
```

### 4. Logout

```
Browser                  FastAPI                 Azure SQL
  |                         |                       |
  |-- POST /auth/logout      |                       |
  |   X-CSRF-Token: <token>  |                       |
  |                         |-- DELETE user_sessions WHERE session_id=... -->|
  |<-- { "detail": "Logged out" }                    |
  |   Set-Cookie: ota_session=; Max-Age=0            |
  |                         |                       |
  | SPA clears state, redirects to /                 |
```

---

## Entra App Registration

**App type:** Web application (confidential client — NOT SPA)
**Supported account types:** Accounts in this organizational directory only (single-tenant)
**Client ID:** `f11ea8b8-bbce-474b-8d3f-758654245a73`

**Redirect URIs:**
- Dev: `https://127.0.0.1:8000/api/v1/auth/entra/callback`
- Production: `https://oa.tmtctech.ai/api/v1/auth/entra/callback`

**API permissions (delegated):**
- `openid` — OIDC sign-in
- `profile` — display name
- `email` — user email address
- `User.Read` — read user profile from Microsoft Graph

**Credential:** Certificate (`entra-bff-cert` in Key Vault). Private key stored in Key Vault;
public key uploaded to app registration. Backend builds a JWT assertion signed with the private
key on each token exchange. Key Vault versioning provides rollback.

---

## Session Lifecycle

| Parameter | Value | Config Key |
|-----------|-------|------------|
| Cookie name | `ota_session` | `SESSION_COOKIE_NAME` |
| Cookie flags | `HttpOnly`, `Secure`, `SameSite=Lax`, `path=/` | Hard-coded in identity_routes.py |
| Session TTL | 24 hours | `SESSION_TTL_HOURS` |
| Token refresh | Triggered when access_token expires in < 5 minutes | Hard-coded in session_manager.py |
| Session ID | `secrets.token_urlsafe(64)` — 512 bits, cryptographically random | session_manager.py |
| CSRF token | `secrets.token_urlsafe(32)` — per-session, returned by `/auth/me` | session_manager.py |

**Expiry behavior:**
- `/auth/me` returns `401` when session is expired or not found
- Frontend `AuthContext` receives `401` → sets `user = null` → `ProtectedRoute` renders `LoginPage`
- The expired session cookie is cleared by the server on the `401` response

**Cleanup:**
- `SessionManager.cleanup_expired()` runs fire-and-forget after each new session creation
- Deletes all rows where `expires_at <= NOW()`
- Non-blocking — failures are logged as warnings, not errors

**Session fixation prevention:**
- New `session_id` is generated on every login — `secrets.token_urlsafe(64)`
- The old session (if any) is not reused

---

## Multi-IdP Provider Registry

**Location:** `app/auth/providers.py`

Each identity provider is a single dict entry returned by `get_provider_config(provider, settings)`.
Adding a new provider = adding one entry. Zero code changes to routes or session manager.

**Dict shape:**
```python
{
    "authorize_url":    str,   # /oauth2/v2.0/authorize endpoint
    "token_url":        str,   # /oauth2/v2.0/token endpoint
    "userinfo_url":     Optional[str],  # None = use id_token claims
    "client_id":        str,
    "credential_type":  "certificate" | "secret",
    "cert_vault_name":  str,   # Key Vault cert name (certificate providers)
    "cert_thumbprint":  str,   # x5t JWT header (certificate providers)
    "scopes":           list[str],
    "issuer":           str,   # expected issuer claim for validation
}
```

**Normalized user profile** (returned to routes after any provider login):
```json
{ "user_id": "...", "email": "...", "display_name": "...", "provider": "entra" }
```

**Adding a new IdP:**
1. Add entry to `providers` dict in `app/auth/providers.py`
2. Ensure the relevant settings exist in `app/core/config.py`
3. Add a callback route for the provider if the authorization flow differs
4. Add a "Sign in with X" button to `LoginPage.jsx` pointing to `/api/v1/auth/login?provider=<n>`

**Current providers:** `entra` (Microsoft Entra ID)
**Future providers:** `google`, `github`, `azure_b2c`

---

## Identity Credential Management

Credentials scoped to **user identity** (proving who the user is). External service
credentials (Schwab, Foundry, future data providers) are managed under Pattern 1
in `architecture-plan.md`.

| Credential | Where Stored | Managed By |
|------------|-------------|------------|
| Entra access_token | `user_sessions` table, Fernet-encrypted | `SessionManager` — refreshed when within 5min of expiry |
| Entra refresh_token | `user_sessions` table, Fernet-encrypted | `SessionManager` — invalidated on logout |
| Session encryption key | Key Vault (`session-encryption-key`) | `SessionManager` — auto-generated on first run |
| Entra cert private key | Key Vault (`entra-bff-cert`) | `ClientAssertionBuilder` |

---

## Deployment Architecture

### Production

Cloudflare → App Service (`options-analyzer-api`). FastAPI serves the API at `/api/v1/*`
and the React SPA at `/` from the `static/` directory. One domain: `oa.tmtctech.ai`.
One GitHub Actions workflow builds the React app and deploys both to App Service.

Same-origin cookies work natively — the API and SPA share the same origin, so
`SameSite=Lax` cookies are sent on every request without proxy workarounds.

### Development

Two terminals:
- **Terminal 1:** FastAPI on port 8000 (`uvicorn app.main:app --reload --ssl-keyfile key.pem --ssl-certfile cert.pem`)
- **Terminal 2:** Vite dev server on port 5173 (`cd web && npm run dev`)

The Vite dev server proxies `/api/*` to the backend. The static file mount in FastAPI
only activates when `static/index.html` exists (production builds only), so it does not
interfere with the Vite dev server.

**Dev redirect URI:** Must go through Vite proxy (`https://localhost:5173`), not direct
to backend, because the auth callback redirects the browser to `/` which needs to serve
the React app.

---

## Security Controls

### CSRF (Synchronizer Token Pattern)

1. `GET /auth/me` returns `csrf_token` — a random 256-bit string tied to the session
2. The SPA stores it in memory (via `AuthContext` / `setCsrfTokenGlobal`) — NOT in localStorage
3. Every `POST`, `PATCH`, `PUT`, `DELETE` request includes `X-CSRF-Token: <token>` header
4. `CSRFMiddleware` (Starlette middleware) validates the header on all state-changing requests
5. An attacker can trigger the browser to send the cookie, but cannot read the `csrf_token`
   (same-origin policy blocks cross-origin reads from `GET /auth/me`)

**CSRF exemptions** (requests that skip the check):
- `GET`, `HEAD`, `OPTIONS` — no state change
- `/api/v1/auth/*` — login/callback are unauthenticated; logout only needs the cookie
- `/api/v1/health/*` — no state change
- Swagger UI routes — not a browser session context
- Requests without an `ota_session` cookie — will 401 at the route level

### Cookie Security Flags

| Flag | Value | Purpose |
|------|-------|---------|
| `HttpOnly` | true | JavaScript cannot read the cookie (document.cookie) |
| `Secure` | true | Cookie only sent over HTTPS |
| `SameSite` | Lax | Sent on same-site navigation, blocked on cross-site POST |
| `path` | / | Sent on all backend routes |

### Token Encryption

- Algorithm: Fernet (AES-128-CBC + HMAC-SHA256)
- Key: 256-bit random key stored in Key Vault as `session-encryption-key`
- Auto-generated on first run if not present
- Key rotation: re-encrypt existing sessions and rotate the Key Vault secret

### OAuth State Parameter

- Signed using `itsdangerous.URLSafeTimedSerializer` with the `jwt-signing-key` from Key Vault
- Payload: `{ provider, return_url, nonce }` — nonce prevents replay
- Max age: 10 minutes (`_PKCE_TTL = 600`)
- Verified in callback before processing the authorization code

### PKCE (Proof Key for Code Exchange)

- `code_verifier`: `secrets.token_urlsafe(64)` — 512 bits
- `code_challenge`: SHA-256 of verifier, base64url-encoded (S256 method)
- Verifier stored server-side in `_pkce_cache` keyed by state string
- Retrieved and cleared in callback (one-time use)
- Prevents authorization code interception attacks

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Login page shows after authenticating | Callback failed silently | Check `?auth_error=` query param in URL; check backend logs for "Identity:" entries |
| `auth_error=state_expired` in URL | User took >10 minutes to complete login | Refresh the page and try again; reduce network latency |
| `auth_error=invalid_state` in URL | PKCE verifier not found (server restart mid-login) | Retry login; verifier cache is in-memory and doesn't survive restarts |
| 401 on all API calls | Session expired or cookie not sent | Check `ota_session` cookie in DevTools → Application → Cookies; verify `credentials: 'include'` in API client |
| 403 on POST/PATCH/PUT/DELETE | Missing or wrong CSRF token | Verify `X-CSRF-Token` header is in the request; check that `/auth/me` ran successfully before the request |
| Schwab shows disconnected | Schwab tokens expired (independent of user session) | Click Schwab connect button in the UI |
| Login works in dev, not production | Redirect URI mismatch | Check Entra app registration → Authentication → Redirect URIs — must match exact backend URL |
| Cookie not set after callback | SameSite/Secure mismatch in dev | Verify backend is on HTTPS (127.0.0.1:8000 with certs); SPA must proxy via Vite HTTPS |
| `503 Identity provider not configured` | `ENTRA_TENANT_ID` or `ENTRA_CLIENT_ID` missing | Check `.env` file or App Service environment variables |
| Token refresh fails, user logged out | Refresh token expired or revoked | User must log in again; this is expected after 90-day inactivity |

---

## Files Reference

| File | Purpose |
|------|---------|
| `app/auth/providers.py` | IdP provider registry — all OIDC config per provider |
| `app/auth/session_manager.py` | Server-side session CRUD, token encryption/decryption, background refresh |
| `app/auth/dependencies.py` | `get_current_user` FastAPI dependency — accepts cookie or JWT Bearer |
| `app/auth/client_assertion.py` | Builds JWT client assertions signed with Key Vault cert |
| `app/api/identity_routes.py` | BFF auth endpoints: login, callback, me, logout, session/status |
| `app/middleware/csrf.py` | CSRF protection middleware — validates X-CSRF-Token header |
| `app/models/database.py` | `UserSession` SQLAlchemy model |
| `web/src/context/AuthContext.jsx` | React auth state: user, isAuthenticated, login(), logout() |
| `web/src/components/ProtectedRoute.jsx` | Route guard — renders LoginPage if not authenticated |
| `web/src/api/client.js` | API client with `credentials: 'include'` and CSRF header injection |
| `agents/identity-security/` | Validation test suite and diagnostic tool for auth flows |
| `auth-process.md` | This document |

---

## Change Log

| Date | Ticket | Change |
|---|---|---|
| 2026-05-06 UTC | OTA-538 | Retired `entra_auth_routes.py` (MSAL bridge) and `auth_routes.py` (legacy local-password auth). BFF OIDC via `identity_routes.py` is now the only auth path. Merged `get_session_user` and `get_current_user` into a single `get_current_user` resolver. Added `skip_auth` production assertion and required-secrets fail-loud check at startup. Updated Files Reference to reflect resolver rename. |
