# Options Analyzer — auth-process.md (Updated 2026-04-11 00:00)

## Architecture Decision Record — BFF Identity Management

**Status:** Accepted
**Decision Date:** 2026-04 (OTA-455 epic)

### Context

The original auth approach used MSAL.js as a browser-side OIDC client. Tokens were stored
in localStorage and the SPA managed the full redirect flow via `handleRedirectPromise`.
This caused recurring production failures:

- Redirect loops when `handleRedirectPromise` was called out of order or concurrently
- Stale localStorage tokens after browser restarts or tab duplication
- Timing issues between MSAL initialization and React rendering
- Each new identity provider (Google, GitHub, AWS) would require additional browser-side SDK work
- Tokens in localStorage are accessible to any JavaScript running in the page (XSS surface)

### Decision

Backend-for-Frontend (BFF) pattern. FastAPI acts as a confidential OIDC client.

- The React SPA never handles, stores, or sees tokens
- The backend exchanges authorization codes for tokens server-to-server
- Tokens are encrypted at rest in Azure SQL (`user_sessions` table) using Fernet (AES-128-CBC)
- The browser holds only an `HttpOnly` session cookie with a random 512-bit session ID
- CSRF protection is provided by the Synchronizer Token Pattern (`X-CSRF-Token` header)

**Credential type:** Entra uses certificate-based client assertions. Tenant policy blocks client
secrets for confidential apps. The backend signs a JWT using a private key from the Key Vault
certificate `entra-bff-cert`. Entra verifies it against the uploaded public key.

### Alternatives Considered

1. **Fix MSAL.js redirect bugs** — Tactical fix only. Root cause (tokens in browser, race conditions
   in `handleRedirectPromise`) remains. Would recur on every Entra SDK update. Entra-only.
2. **Third-party auth gateway (Auth0, Okta)** — Unnecessary cost (~$2/MAU). Solves browser-side
   token management but adds an external dependency for all auth decisions. Doesn't solve the
   multi-IdP server-side token coexistence problem (Schwab, Azure AI Foundry).

### Consequences

- All auth complexity lives server-side. Frontend auth code is ~50 lines total.
- Adding a new IdP (Google, GitHub) requires one config entry in `app/auth/providers.py` and zero
  frontend changes.
- Session cookie requires CSRF protection — implemented via `CSRFMiddleware` and the
  Synchronizer Token Pattern.
- Tokens are never visible in browser DevTools, network logs, or error reports.
- Session state is in Azure SQL — sessions survive server restarts and scale-out.

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

### 5. Schwab Auth Coexistence

```
Browser                  FastAPI                 Schwab                  Key Vault
  |                         |                      |                          |
  | [user already has ota_session cookie]           |                          |
  |-- GET /auth/schwab/login popup ----------------->|                        |
  |                         | Schwab OAuth          |                          |
  |-- GET /auth/schwab/callback?code= ------------->|                         |
  |                         |-- POST /token -------->|                        |
  |                         |<-- { access_token, refresh_token } -------------|
  |                         |-- store in SchwabTokenManager ----------------->|
  |   popup closes           |  (Key Vault in prod)  |                        |
  |                         |                       |                         |
  | All market data calls use Schwab tokens (server-side)
  | All identity calls use ota_session cookie
  | Both coexist — browser holds neither token
```

---

## Entra App Registration

**App type:** Web application (confidential client — NOT SPA)
**Supported account types:** Accounts in this organizational directory only (single-tenant)
**Redirect URIs:**
- Dev: `https://127.0.0.1:8000/api/v1/auth/entra/callback`
- Production: `https://options-analyzer-api-d7aqhsdmd6f2anbc.centralus-01.azurewebsites.net/api/v1/auth/entra/callback`

**API permissions (delegated):**
- `openid` — OIDC sign-in
- `profile` — display name
- `email` — user email address
- `User.Read` — read user profile from Microsoft Graph

**Credential:** Certificate (not client secret). Tenant policy blocks client secrets for
confidential apps. Certificate uploaded to app registration, private key stored in Key Vault
as `entra-bff-cert`. Backend builds a JWT assertion signed with the private key on each
token exchange.

**Old SPA registration:** The previous MSAL.js app registration (SPA redirect URI type) is
deprecated. It is kept in the tenant for rollback purposes only. New auth uses the Web
(confidential) registration above.

**Client secret management:** Certificate-based — no rotating secrets. Key Vault certificate
`entra-bff-cert` is the credential. Key Vault versioning provides rollback.

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
4. Add a "Sign in with X" button to `LoginPage.jsx` pointing to `/api/v1/auth/login?provider=<name>`

**Current providers:** `entra` (Microsoft Entra ID)
**Future providers:** `google`, `github`, `azure_b2c`

---

## Cross-Cloud Token Management

All credentials coexist server-side. The browser never stores or sees any of them.

| Credential | Where Stored | Managed By | Notes |
|------------|-------------|------------|-------|
| Entra access_token | `user_sessions` table, Fernet-encrypted | `SessionManager` | Refreshed automatically when within 5min of expiry |
| Entra refresh_token | `user_sessions` table, Fernet-encrypted | `SessionManager` | Used for transparent refresh; invalidated on logout |
| Schwab access_token | In-memory (dev) / Key Vault (prod) | `SchwabTokenManager` | Independent of user session |
| Schwab refresh_token | In-memory (dev) / Key Vault (prod) | `SchwabTokenManager` | `schwab-token-data` Key Vault secret |
| Azure AI Foundry API key | Key Vault | `SecretsManager` | `anthropic-api-key` secret |
| Session encryption key | Key Vault | `SessionManager` | `session-encryption-key` — auto-generated on first run |
| Entra cert private key | Key Vault | `ClientAssertionBuilder` | `entra-bff-cert` certificate |
| Future AWS | Key Vault | New provider adapter | IAM role key or service account |
| Future Google | Key Vault | New provider adapter | Service account JSON |

**Key principle:** The browser never sees or stores any token. All token management is
a server-side concern. Adding a new cloud credential = add one Key Vault secret and one
provider adapter.

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
| `app/auth/dependencies.py` | `get_session_user` FastAPI dependency — accepts cookie or JWT Bearer |
| `app/auth/client_assertion.py` | Builds JWT client assertions signed with Key Vault cert |
| `app/api/identity_routes.py` | BFF auth endpoints: login, callback, me, logout, session/status |
| `app/middleware/csrf.py` | CSRF protection middleware — validates X-CSRF-Token header |
| `app/models/database.py` | `UserSession` SQLAlchemy model |
| `web/src/context/AuthContext.jsx` | React auth state: user, isAuthenticated, login(), logout() |
| `web/src/components/ProtectedRoute.jsx` | Route guard — renders LoginPage if not authenticated |
| `web/src/api/client.js` | API client with `credentials: 'include'` and CSRF header injection |
| `agents/identity-security/` | Validation test suite and diagnostic tool for auth flows |
| `auth-process.md` | This document |
