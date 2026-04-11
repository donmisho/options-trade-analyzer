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
