# OTA-500 Session Expired Loop Fix — Claude Code Prompt

## Jira
- Ticket: OTA-500
- Commit prefix: `OTA-500`

## Problem — Read This Carefully

The login flow completes, startup steps all pass (including "Verifying user session" ✓), but when the app transitions to actual page content, **API data calls fail with "Session expired"**. This triggers AuthContext to reset authentication state, which re-mounts StartupProgress, which re-verifies the session (succeeds again), which transitions to page content (fails again) — creating an infinite loop.

**Observed behavior from production screenshots:**

1. Startup completes — all 6 steps green ✓ including "Verifying user session" (1.0s)
2. Dashboard renders → shows **"Failed to load dashboard layout"**
3. Security Strategies renders → flashes for 0.1 second → snaps back to StartupProgress
4. Positions renders → shows **"Could not load positions: Session expired"** → snaps back
5. Steady Paycheck renders → shows **"Could not load positions: Session expired"** → snaps back
6. Schwab shows **Connected** (green ✓) throughout — so Schwab auth is fine
7. The StartupProgress re-runs and completes successfully every time (all green ✓)

**Key insight:** The session IS valid (startup step 4 verifies it via `/auth/me`), but page-level data API calls are getting rejected. This is NOT a frontend state bug — the backend is returning errors on data endpoints while accepting the session on `/auth/me`.

## Preparation — Read These Files First

```bash
cat CLAUDE.md
cat claude_context/auth-process.md

# Backend session validation chain — READ IN THIS ORDER
cat app/auth/dependencies.py
cat app/auth/session_manager.py
cat app/api/identity_routes.py
cat app/middleware/csrf.py

# Data endpoints that are failing
cat app/api/dashboard_routes.py
cat app/api/position_routes.py
cat app/api/market_routes.py
cat app/api/config_routes.py

# Frontend error handling chain
cat web/src/api/client.js
cat web/src/context/AuthContext.jsx
cat web/src/components/ProtectedRoute.jsx
cat web/src/components/Layout.jsx
cat web/src/components/StartupProgress.jsx
cat web/src/App.jsx
```

Read ALL files. Do NOT skip any. Do NOT start fixing until you complete the diagnosis in Step 1.

## Step 1: Diagnose — Find Why Data Endpoints Reject Valid Sessions

The session is valid (startup proves it) but data endpoints reject it. Find which of these causes applies:

### Hypothesis A: API client is not sending the session cookie on data calls

The `/auth/me` call works (startup step 4). But maybe other API calls in `client.js` don't include `credentials: 'include'`, so the `ota_session` cookie doesn't get sent with data requests.

**How to check:** In `web/src/api/client.js`, verify that EVERY fetch/axios call includes `credentials: 'include'` (for fetch) or `withCredentials: true` (for axios). Check if there's a shared client instance vs. individual calls — one misconfigured call would cause this. Pay special attention to:
- Dashboard layout fetch
- Positions list fetch
- Config fetch
- Any call that uses a different function than the one `/auth/me` uses

### Hypothesis B: CSRF token is required but missing on GET requests

Per `auth-process.md`, CSRF should be exempt for GET/HEAD/OPTIONS. But check `app/middleware/csrf.py` — is the CSRF middleware accidentally requiring the `X-CSRF-Token` header on GET requests? A misconfigured CSRF check would return 403, which the frontend might be interpreting as "Session expired."

**How to check:** Read `app/middleware/csrf.py` and verify the method exemption logic. Also check whether the error responses from the backend include a status code of 401 vs 403 vs something else — the frontend error message "Session expired" might be a generic catch-all that masks the real HTTP status.

### Hypothesis C: The `get_session_user` dependency is failing with a misleading error

The auth dependency in `app/auth/dependencies.py` might be throwing "Session expired" for reasons other than actual session expiry — for example, a database query failure, a decryption error, or a missing field. The startup `/auth/me` endpoint might handle the dependency differently than data endpoints.

**How to check:** Read `get_session_user` in `dependencies.py`. Check if it:
- Catches exceptions and maps them all to "Session expired"
- Has different behavior when called from `/auth/me` vs. from data route dependencies
- Handles the case where the session exists but token decryption fails

### Hypothesis D: Session is being created but with wrong `expires_at`

The session might expire immediately due to a timezone mismatch (UTC vs local), a zero TTL, or `expires_at` being set to the creation time instead of creation + 24h.

**How to check:** Read `session_manager.py` — find where `expires_at` is calculated. Check if it uses `datetime.utcnow()` vs `datetime.now(timezone.utc)` vs `datetime.now()`. A mismatch between how `expires_at` is SET and how it's COMPARED could cause immediate expiry.

### Hypothesis E: `cleanup_expired()` is deleting the session it just created

Per `auth-process.md`, `cleanup_expired()` runs fire-and-forget after each new session creation. If there's a race condition or if the session's `expires_at` is in the past (due to Hypothesis D), the cleanup job would delete the freshly created session.

**How to check:** Read the cleanup logic. Check if there's a timing window where the session could be cleaned up between creation and the first data API call.

### Hypothesis F: Different API paths have different auth requirements

Maybe `/auth/me` accepts the session cookie directly, but data endpoints require a different auth mechanism (e.g., a Bearer token header that the frontend isn't sending).

**How to check:** Compare the FastAPI dependency injection on `/auth/me` route vs. dashboard/positions routes. Are they all using the same `get_session_user` dependency? Or do data routes use a different auth dependency?

### Hypothesis G: The frontend's error handler treats ANY error as "Session expired"

The API client might be catching network errors, 500s, or non-auth errors and labeling them all as "Session expired" in the UI. The actual backend error might be something entirely different (DB connection failure, missing table, serialization error).

**How to check:** In `client.js`, find the error handling logic. Check if it:
- Distinguishes 401 from other error codes
- Has a catch-all that assumes any error = session expired
- Triggers AuthContext logout/reset on non-401 errors

## Step 2: Add Backend Diagnostic Logging

Add temporary logging to trace EXACTLY what happens on a data request:

```python
# In app/auth/dependencies.py — inside get_session_user (or equivalent)
import logging
logger = logging.getLogger("ota.auth.diag")

# At the very start of the dependency function:
logger.info(f"[SESSION-DIAG] get_session_user called — checking for session cookie")

# After reading the cookie:
logger.info(f"[SESSION-DIAG] Cookie present: {bool(session_id)}, session_id prefix: {session_id[:8] if session_id else 'NONE'}...")

# After DB lookup:
logger.info(f"[SESSION-DIAG] DB lookup result: {'FOUND' if session else 'NOT FOUND'}")

# If session found, check expiry:
if session:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    logger.info(f"[SESSION-DIAG] expires_at={session.expires_at}, now={now}, expired={session.expires_at < now}")

# At any exception/rejection point:
logger.warning(f"[SESSION-DIAG] Session REJECTED — reason: {reason}")
```

```python
# In app/middleware/csrf.py — at the check point
logger.info(f"[SESSION-DIAG] CSRF check — method={request.method}, path={request.url.path}, has_token={bool(csrf_header)}")
```

Also add frontend logging:

```javascript
// In web/src/api/client.js — in the response handler
console.log('[SESSION-DIAG] API response:', {
  url: response.url || url,
  status: response.status,
  ok: response.ok,
  statusText: response.statusText
});

// In the error handler:
console.log('[SESSION-DIAG] API error caught:', {
  url,
  status: error?.response?.status || error?.status || 'unknown',
  message: error?.message,
  willResetAuth: /* whether this triggers logout */
});
```

## Step 3: Deploy and Check Logs

After adding the diagnostic logging:

1. Deploy to production (or test in dev)
2. Complete the login flow
3. When the loop happens, check:
   - **Azure App Service logs** — look for `[SESSION-DIAG]` entries. The sequence will show exactly where the session gets rejected.
   - **Browser console** — look for `[SESSION-DIAG]` entries. The status codes will reveal if it's 401, 403, 500, or something else.

## Step 4: Fix the Root Cause

Based on what the diagnostics reveal, fix the actual problem. Then ALSO add the frontend resilience fix to prevent the loop even if a transient error occurs:

### 4a. Fix whatever is causing the session rejection on data endpoints

This depends on the diagnosis. Common fixes:
- If `credentials: 'include'` is missing: add it to ALL API calls in client.js
- If CSRF is wrongly applied to GET: fix the method exemption in csrf.py
- If `expires_at` timezone is wrong: standardize on `datetime.now(timezone.utc)` everywhere
- If error handling maps everything to "Session expired": differentiate 401 from other errors

### 4b. Frontend resilience — prevent the loop regardless

Even after fixing the root cause, the frontend should NOT loop on transient errors. Add these safeguards:

**In `client.js` — only reset auth on definitive 401:**

```javascript
// Only trigger auth reset when the backend definitively says "not authenticated"
// Do NOT reset on 403 (CSRF), 500 (server error), network errors, or other failures
if (response.status === 401) {
  // Session is truly invalid — trigger re-auth
  // But NOT by resetting isAuthenticated — just redirect to login or show a message
  console.warn('[AUTH] Session invalid (401) — redirecting to login');
  sessionStorage.removeItem('ota_startup_complete');
  window.location.href = '/'; // Full reload to login page
  return; // Don't process further
}
// For all other errors, throw normally — let the page component show its error UI
// Do NOT touch auth state
```

**In `AuthContext.jsx` — never reset isAuthenticated from API error handlers:**

The AuthContext should ONLY change `isAuthenticated` based on:
1. Initial `/auth/me` check on mount (sets true or false)
2. Explicit logout action (sets false)

It should NEVER change `isAuthenticated` based on a data endpoint returning an error. If a page component's API call fails, that's the page component's problem to display — not a reason to re-run the entire startup flow.

**In `Layout.jsx` — persist startup completion in sessionStorage:**

```javascript
const startupDone = sessionStorage.getItem('ota_startup_complete') === 'true';
const [showStartup, setShowStartup] = useState(!startupDone);

const handleStartupComplete = () => {
  sessionStorage.setItem('ota_startup_complete', 'true');
  setShowStartup(false);
};

// Once startup is done, NEVER show it again in this session
// Even if data endpoints fail, show the page with error messages — not StartupProgress
```

**On logout — clear the flag:**

```javascript
sessionStorage.removeItem('ota_startup_complete');
```

## Step 5: Remove diagnostic logging

After the fix is verified, remove ALL `[SESSION-DIAG]` logging from both backend and frontend:

```bash
grep -rn "SESSION-DIAG" app/ --include="*.py"
grep -rn "SESSION-DIAG" web/src/ --include="*.jsx" --include="*.js"
```

Remove every match.

## Acceptance Criteria

1. After login + startup, Dashboard renders and **stays rendered** (even if dashboard layout API fails — show error message, not StartupProgress)
2. All nav pages render and stay visible — no flash-and-snap-back
3. Pages that fail to load data show their error messages (like "Failed to load dashboard layout") — they do NOT trigger a return to StartupProgress
4. Only a definitive 401 from `/auth/me` (not from data endpoints) should trigger re-authentication
5. Browser refresh with valid session skips StartupProgress
6. Logout clears startup flag
7. No `[SESSION-DIAG]` logging in committed code

## Commit

```
OTA-500: Fix session validation on data endpoints + prevent auth reset loop

- Diagnose and fix why data API calls return "Session expired" while /auth/me succeeds
- API client only resets auth state on 401 from /auth/me, not from data endpoints
- Persist startup-complete flag in sessionStorage (survives re-renders)
- Page components show their own error states instead of triggering startup re-run
- Clear startup flag on logout
```
