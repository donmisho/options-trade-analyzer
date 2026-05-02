# CLAUDE-CODE-PROMPT-T1-BACKEND-BFF-AUTH.md

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

You are building the Backend-for-Frontend (BFF) identity management system for the Options Trade Analyzer. This replaces the fragile MSAL.js browser-side auth with server-side OIDC confidential client flow.

**Read these files first — do not skip:**
```bash
cat CLAUDE.md
cat architecture-plan.md | head -200
cat SCHWAB-LOGIN-PROCESS.md
cat app/api/schwab_auth_routes.py
cat app/providers/schwab_token_manager.py
cat app/core/config.py
cat app/core/secrets.py
cat app/auth/service.py
cat app/auth/dependencies.py
cat app/main.py
ls app/models/
cat app/models/database.py
cat app/models/session.py
```

**Jira tickets this prompt covers:**
- OTA-461: Session Store (user_sessions table + SessionManager)
- OTA-462: OIDC Auth Routes (login, callback, me, logout, status)
- OTA-463: CSRF Middleware + Auth Dependency + Schwab Route Protection

**Prerequisites:** Don has already completed OTA-460 (Entra confidential client registration). The following environment variables are set in `.env`:
- `ENTRA_CLIENT_ID`
- `ENTRA_TENANT_ID`
- `ENTRA_CERT_THUMBPRINT` (certificate thumbprint for client assertion)
- `ENTRA_REDIRECT_URI_DEV=https://127.0.0.1:8000/api/v1/auth/entra/callback`
- `ENTRA_REDIRECT_URI_PROD=https://oa.tmtctech.ai/api/v1/auth/entra/callback`

**Credential type: Certificate** (tenant policy blocks client secrets). The .pfx certificate is stored in Azure Key Vault (`options-analyzer` vault, certificate name `entra-bff-cert`). The backend uses this certificate to sign JWT client assertions for the token exchange — no client_secret parameter is used anywhere.

---

## Phase 1: Session Store (OTA-461)

### 1.1 Database Migration

Create the `user_sessions` table. Use the existing database session pattern from `app/models/session.py`.

```sql
CREATE TABLE user_sessions (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    session_id NVARCHAR(128) UNIQUE NOT NULL,
    user_id NVARCHAR(255) NOT NULL,
    provider NVARCHAR(50) NOT NULL DEFAULT 'entra',
    email NVARCHAR(255),
    display_name NVARCHAR(255),
    access_token_encrypted NVARCHAR(MAX),
    refresh_token_encrypted NVARCHAR(MAX),
    id_token NVARCHAR(MAX),
    token_expires_at DATETIME2,
    csrf_token NVARCHAR(128) NOT NULL,
    created_at DATETIME2 DEFAULT GETUTCDATE(),
    expires_at DATETIME2 NOT NULL,
    last_active_at DATETIME2 DEFAULT GETUTCDATE()
);

CREATE INDEX ix_user_sessions_session_id ON user_sessions(session_id);
CREATE INDEX ix_user_sessions_expires_at ON user_sessions(expires_at);
```

Run this migration against Azure SQL. Use the existing database connection pattern.

### 1.2 SessionManager

Create `app/auth/session_manager.py`:

```python
class SessionManager:
    """Server-side session management for BFF auth pattern."""
    
    async def create_session(self, user_profile: dict, tokens: dict, provider: str = "entra") -> str:
        """
        Create a new session. Returns session_id.
        - Generate cryptographically random session_id (secrets.token_urlsafe(64))
        - Generate CSRF token (secrets.token_urlsafe(32))
        - Encrypt access_token and refresh_token using Fernet key from Key Vault
        - Insert row into user_sessions
        - Session expires in 24 hours (configurable via settings)
        """
    
    async def get_session(self, session_id: str) -> Optional[dict]:
        """
        Look up session by session_id.
        - Return None if not found or expired
        - Update last_active_at on each access
        - If token_expires_at is within 5 minutes, trigger token refresh
        - Return: { user_id, email, display_name, provider, csrf_token, session_expires_at }
        """
    
    async def refresh_tokens(self, session_id: str) -> bool:
        """
        Server-side token refresh using the stored refresh_token.
        - POST to Entra token endpoint with grant_type=refresh_token
        - Uses client_id + JWT client assertion signed with certificate (same as login callback)
        - Update encrypted tokens and token_expires_at in database
        - Return True on success, False on failure (session should be invalidated on failure)
        """
    
    async def delete_session(self, session_id: str) -> None:
        """Hard delete session row."""
    
    async def cleanup_expired(self) -> int:
        """Delete all expired sessions. Return count deleted. Fire-and-forget."""
```

**Token encryption:**
- Use `cryptography.fernet.Fernet`
- Encryption key stored in Key Vault as `session-encryption-key`
- If the key doesn't exist yet, generate one and store it:
  ```python
  from cryptography.fernet import Fernet
  key = Fernet.generate_key()
  # Store in Key Vault
  ```
- Use the existing `SecretsManager` pattern from `app/core/secrets.py`

### 1.3 Config Updates

Add to `app/core/config.py` (Pydantic Settings):
```python
# Identity Management
ENTRA_CLIENT_ID: str = ""
ENTRA_TENANT_ID: str = ""
ENTRA_CERT_THUMBPRINT: str = ""
ENTRA_REDIRECT_URI_DEV: str = "https://127.0.0.1:8000/api/v1/auth/entra/callback"
ENTRA_REDIRECT_URI_PROD: str = "https://oa.tmtctech.ai/api/v1/auth/entra/callback"
SESSION_TTL_HOURS: int = 24
SESSION_COOKIE_NAME: str = "ota_session"
```

**Checkpoint:** Verify the migration ran and SessionManager can create/read/delete a session in a quick test script.

---

## Phase 2: OIDC Auth Routes (OTA-462)

### 2.1 Provider Registry

Create `app/auth/providers.py`:

```python
"""
Identity provider registry. Each provider is a config dict.
Adding a new IdP = adding one entry here. Zero code changes elsewhere.

Credential type: Certificate-based client assertion (tenant policy blocks client secrets).
The backend signs a JWT assertion using the private key from Key Vault certificate `entra-bff-cert`.
"""

def get_provider_config(provider: str, settings) -> dict:
    """
    Returns provider config dict:
    {
        "authorize_url": str,
        "token_url": str,
        "userinfo_url": str,  # optional, Entra doesn't need it (claims in id_token)
        "client_id": str,
        "credential_type": "certificate",
        "cert_vault_name": str,  # Key Vault certificate name
        "cert_thumbprint": str,  # for x5t header in JWT assertion
        "scopes": list[str],
        "issuer": str,
    }
    """
    
    providers = {
        "entra": {
            "authorize_url": f"https://login.microsoftonline.com/{settings.ENTRA_TENANT_ID}/oauth2/v2.0/authorize",
            "token_url": f"https://login.microsoftonline.com/{settings.ENTRA_TENANT_ID}/oauth2/v2.0/token",
            "userinfo_url": None,  # Use id_token claims instead
            "client_id": settings.ENTRA_CLIENT_ID,
            "credential_type": "certificate",
            "cert_vault_name": "entra-bff-cert",
            "cert_thumbprint": settings.ENTRA_CERT_THUMBPRINT,
            "scopes": ["openid", "profile", "email", "User.Read"],
            "issuer": f"https://login.microsoftonline.com/{settings.ENTRA_TENANT_ID}/v2.0",
        },
        # Future: add "google", "github" entries here
        # Google uses client_secret (not blocked by Entra tenant policy)
    }
    
    if provider not in providers:
        raise ValueError(f"Unknown identity provider: {provider}")
    
    return providers[provider]
```

### 2.2 Client Assertion Builder

Create `app/auth/client_assertion.py`:

```python
"""
Builds JWT client assertions for certificate-based confidential client auth.
Used instead of client_secret (which is blocked by tenant policy).

The assertion is a short-lived JWT signed with the private key from the
Key Vault certificate. Entra verifies it against the uploaded public key.
"""

import base64
import hashlib
import time
import uuid

import jwt  # PyJWT
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding

class ClientAssertionBuilder:
    """
    Builds and caches the signing key loaded from Key Vault.
    Call build_assertion(token_url) to get a fresh JWT for each token request.
    """
    
    def __init__(self, vault_url: str, cert_name: str, client_id: str):
        self.vault_url = vault_url
        self.cert_name = cert_name
        self.client_id = client_id
        self._private_key = None
        self._x5t = None
    
    async def _load_certificate(self):
        """Load PFX from Key Vault (once, then cached)."""
        if self._private_key is not None:
            return
        
        from azure.identity.aio import DefaultAzureCredential
        from azure.keyvault.secrets.aio import SecretClient
        
        credential = DefaultAzureCredential()
        secret_client = SecretClient(vault_url=self.vault_url, credential=credential)
        
        try:
            # Key Vault exposes the PFX as a base64-encoded secret with the same name
            cert_secret = await secret_client.get_secret(self.cert_name)
            pfx_bytes = base64.b64decode(cert_secret.value)
            
            private_key, cert, _ = pkcs12.load_key_and_certificates(pfx_bytes, None)
            self._private_key = private_key
            
            # Build x5t: SHA-1 thumbprint of the DER-encoded certificate, base64url
            cert_der = cert.public_bytes(Encoding.DER)
            thumbprint = hashlib.sha1(cert_der).digest()
            self._x5t = base64.urlsafe_b64encode(thumbprint).rstrip(b'=').decode()
        finally:
            await credential.close()
            await secret_client.close()
    
    async def build_assertion(self, token_url: str) -> str:
        """Build a fresh JWT client assertion for a token request."""
        await self._load_certificate()
        
        now = int(time.time())
        payload = {
            "iss": self.client_id,
            "sub": self.client_id,
            "aud": token_url,
            "jti": str(uuid.uuid4()),
            "exp": now + 300,  # 5 minutes
            "iat": now,
            "nbf": now,
        }
        
        return jwt.encode(
            payload,
            self._private_key,
            algorithm="RS256",
            headers={"x5t": self._x5t},
        )
```

This builder is instantiated once at app startup and shared across identity routes and SessionManager for token refresh.

### 2.3 Identity Routes

Create `app/api/identity_routes.py`:

**GET /api/v1/auth/login**
```
Query params: provider (default: "entra")
1. Look up provider config
2. Generate PKCE code_verifier (secrets.token_urlsafe(64)) and code_challenge (S256)
3. Generate state parameter: sign a JSON payload { "return_url": "/", "provider": provider, "nonce": random } using itsdangerous.URLSafeTimedSerializer with a signing key from Key Vault
4. Store code_verifier in a temporary server-side cache keyed by state (use a simple dict with TTL, or a short-lived DB row — state is valid for 10 minutes max)
5. Build authorize URL with: client_id, redirect_uri, response_type=code, scope, state, code_challenge, code_challenge_method=S256, response_mode=query
6. Return RedirectResponse to the authorize URL
```

**GET /api/v1/auth/entra/callback**
```
Query params: code, state, error, error_description
1. If error param present: log it, redirect to SPA with ?auth_error=<message>
2. Validate state: unsign with URLSafeTimedSerializer (max_age=600 seconds)
3. Retrieve code_verifier from temporary cache using state
4. Build a JWT client assertion (this replaces client_secret):
   - Create a JWT with:
     - Header: { "alg": "RS256", "typ": "JWT", "x5t": base64url(sha1(cert_der)) }
     - Payload: {
         "iss": client_id,
         "sub": client_id,
         "aud": token_url,
         "jti": str(uuid4()),
         "exp": now + 300 seconds,
         "iat": now,
         "nbf": now
       }
   - Sign with the private key from Key Vault certificate `entra-bff-cert`
   - Use `cryptography` library to load the PFX and sign:
     ```python
     from azure.keyvault.certificates import CertificateClient
     from azure.keyvault.secrets import SecretClient
     from cryptography.hazmat.primitives.serialization import pkcs12
     import jwt  # PyJWT
     
     # Key Vault stores the PFX as a secret with the same name as the certificate
     secret_client = SecretClient(vault_url, credential)
     cert_secret = secret_client.get_secret("entra-bff-cert")
     pfx_bytes = base64.b64decode(cert_secret.value)
     private_key, cert, _ = pkcs12.load_key_and_certificates(pfx_bytes, None)
     
     # Build x5t (X.509 certificate SHA-1 thumbprint, base64url encoded)
     cert_der = cert.public_bytes(serialization.Encoding.DER)
     x5t = base64.urlsafe_b64encode(hashlib.sha1(cert_der).digest()).rstrip(b'=').decode()
     
     # Sign the assertion
     assertion = jwt.encode(payload, private_key, algorithm="RS256", headers={"x5t": x5t})
     ```
5. POST to token_url with:
   - grant_type=authorization_code
   - code=<code>
   - redirect_uri=<redirect_uri>
   - client_id=<client_id>
   - client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
   - client_assertion=<the signed JWT from step 4>
   - code_verifier=<code_verifier>
   (NOTE: NO client_secret parameter — the assertion replaces it)
6. Parse response: access_token, refresh_token, id_token, expires_in
7. Decode id_token (no signature verification needed — we got it directly from Entra over HTTPS):
   - Extract: oid (user_id), preferred_username (email), name (display_name)
8. Call SessionManager.create_session(user_profile, tokens, provider="entra")
9. Build RedirectResponse to return_url (from state) or "/"
10. Set cookie on the response:
   response.set_cookie(
       key=settings.SESSION_COOKIE_NAME,  # "ota_session"
       value=session_id,
       httponly=True,
       secure=True,
       samesite="lax",
       path="/",
       max_age=settings.SESSION_TTL_HOURS * 3600,
   )
11. Return the redirect response
```

**GET /api/v1/auth/me**
```
1. Read session_id from cookie
2. If no cookie: return 401 { "detail": "Not authenticated" }
3. Call SessionManager.get_session(session_id)
4. If session is None (not found or expired): clear cookie, return 401
5. Return 200:
   {
       "user_id": str,
       "email": str,
       "display_name": str,
       "provider": str,
       "csrf_token": str,
       "session_expires_at": str (ISO format)
   }
```

**POST /api/v1/auth/logout**
```
1. Read session_id from cookie
2. Call SessionManager.delete_session(session_id)
3. Build response (200 { "detail": "Logged out" })
4. Delete cookie: response.delete_cookie(key=settings.SESSION_COOKIE_NAME, path="/")
5. Return response
```

**GET /api/v1/auth/session/status**
```
1. Read session_id from cookie
2. If no cookie or session not found: return { "authenticated": false }
3. Return:
   {
       "authenticated": true,
       "expires_in_seconds": int,
       "provider": str,
       "user": str (display_name)
   }
```

### 2.4 Register Routes

In `app/main.py`, add:
```python
from app.api.identity_routes import router as identity_router
app.include_router(identity_router, prefix="/api/v1/auth", tags=["identity"])
```

### 2.5 Dependencies

Install required packages:
```bash
pip install itsdangerous httpx cryptography PyJWT
```
- `itsdangerous` — state parameter signing
- `httpx` — async HTTP client for token exchange (server-to-server)
- `cryptography` — Fernet encryption for stored tokens + loading PFX certificate from Key Vault
- `PyJWT` — building and signing JWT client assertions for Entra token exchange

Also ensure `azure-keyvault-certificates` is installed (for retrieving the certificate from Key Vault):
```bash
pip install azure-keyvault-certificates azure-keyvault-secrets azure-identity
```

Add all to `requirements.txt`.

**Checkpoint:** Start the backend. Navigate to `https://127.0.0.1:8000/api/v1/auth/login` in a browser. It should redirect to the Microsoft login page. After login, the callback should create a session and set a cookie. `GET /api/v1/auth/me` with the cookie should return the user profile.

---

## Phase 3: CSRF + Auth Dependency (OTA-463)

### 3.1 Auth Dependency

Create or update `app/auth/dependencies.py` — add a new dependency alongside existing ones:

```python
from fastapi import Request, HTTPException, Depends

async def get_current_user(request: Request) -> dict:
    """
    FastAPI dependency: extract and validate user session from cookie.
    Returns user profile dict or raises 401.
    """
    session_id = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    
    return session
```

### 3.2 CSRF Middleware

Create `app/middleware/csrf.py`:

```python
from starlette.middleware.base import BaseHTTPMiddleware

class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Require X-CSRF-Token header on state-changing requests.
    
    Exempt routes:
    - /api/v1/auth/login (GET anyway)
    - /api/v1/auth/*/callback
    - /api/v1/auth/schwab/* (has its own auth)
    - /api/v1/health/*
    - /docs, /openapi.json (Swagger)
    
    For all POST/PATCH/PUT/DELETE:
    1. Read session_id from cookie
    2. Look up session's csrf_token
    3. Compare with X-CSRF-Token header
    4. If mismatch or missing: return 403
    """
```

Register in `app/main.py`:
```python
app.add_middleware(CSRFMiddleware)
```

### 3.3 Protect Existing Routes

Add `current_user: dict = Depends(get_current_user)` to:
- All routes in `schwab_auth_routes.py` (Schwab login/status now requires authenticated user)
- All routes in analysis, positions, evaluate, agents routes
- Do NOT add to: identity routes (login/callback/me/status), health endpoints

### 3.4 Schwab Token Association

Update `SchwabTokenManager` to associate Schwab tokens with the authenticated user's session:
- When Schwab tokens are stored, include `user_id` from the current session
- This enables future multi-user support where each user has their own Schwab credentials
- For now, single-user behavior is preserved — just add the association field

**Checkpoint:** 
1. Without a session cookie, all protected routes return 401
2. With a valid session cookie, routes work as before
3. POST without X-CSRF-Token returns 403
4. POST with correct X-CSRF-Token passes
5. Schwab auth flow still works when user is authenticated

---

## House Style Rules

- Follow all patterns in CLAUDE.md
- Use existing `SecretsManager` for Key Vault access — never hardcode secrets
- Use existing database session pattern from `app/models/session.py`
- Fire-and-forget for session cleanup (never block request on maintenance tasks)
- All new routes must appear in Swagger (/docs)
- Log all auth events at INFO level with structured data (user_id, provider, event type)

## Commit

```
OTA-461 OTA-462 OTA-463 feat: BFF identity management — session store, OIDC routes, CSRF middleware
```

After commit, transition OTA-461, OTA-462, OTA-463 to IN REVIEW (transition ID: 41).
