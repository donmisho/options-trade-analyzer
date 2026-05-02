# Claude Code Prompt — MSAL Auth Fix
## Silent SSO Failure / Stale Token Cache

---

## Before you write a single line of code, read and report first.

Find and cat every file related to Microsoft authentication. Start here:

```
find web/src -name "*.js" -o -name "*.jsx" | xargs grep -l -i "msal\|acquireToken\|loginRedirect\|loginPopup\|MsalProvider\|PublicClientApplication" 2>/dev/null
```

Then cat each file found. Also check:

```
cat web/src/main.jsx
cat web/src/App.jsx
cat web/src/index.js 2>/dev/null || echo "not found"
```

Look for and report:
1. Where is `PublicClientApplication` instantiated? What is the `cache.cacheLocation` set to — `"localStorage"`, `"sessionStorage"`, or something else?
2. How is sign-in triggered? Is it `loginRedirect`, `loginPopup`, `acquireTokenSilent`, or a combination?
3. Is there a `handleRedirectPromise()` call anywhere? Where?
4. Is there error handling on the silent token acquisition path? What happens when `acquireTokenSilent` throws?
5. What happens on sign-out — is `logoutRedirect` or `logoutPopup` called, and does it clear the local cache?
6. Is there any code that checks for a cached account on app load and attempts silent sign-in automatically?

Report your findings as a numbered list matching the above before writing any code.

---

## Context

You are working on Options Analyzer, a FastAPI + React options trading analysis app.

**The problem:** In the dev environment, signing in with Microsoft succeeds roughly 2 out of 10 attempts. Most of the time the app redirects to Microsoft, then flips back to the "Sign in with Microsoft" login screen without completing authentication. Incognito mode works reliably every time.

**Root cause:** MSAL finds a stale cached account in `localStorage` from a previous session, attempts `acquireTokenSilent()` with that cached account, Microsoft rejects the token (expired or revoked), and the error is swallowed — causing the app to silently re-render the login screen instead of falling back to an interactive login prompt.

**Why Incognito works:** No cached account exists in a fresh Incognito session, so MSAL skips silent SSO entirely and goes straight to interactive login.

---

## The Fix

### Fix 1 — Silent SSO failure must fall back to interactive login

Find every place where `acquireTokenSilent` is called or where MSAL attempts to use a cached account. Ensure that any failure — including `InteractionRequiredAuthError`, `BrowserAuthError`, network errors, and all other MSAL error types — triggers an interactive login rather than silently failing.

The correct pattern:

```javascript
import {
  InteractionRequiredAuthError,
  BrowserAuthError
} from '@azure/msal-browser';

async function getToken(msalInstance, account, scopes) {
  try {
    // Attempt silent acquisition first
    const result = await msalInstance.acquireTokenSilent({
      account,
      scopes,
    });
    return result.accessToken;
  } catch (error) {
    // ANY failure → fall back to interactive login
    // Never silently re-render the login screen
    if (
      error instanceof InteractionRequiredAuthError ||
      error instanceof BrowserAuthError ||
      error.name === 'InteractionRequiredAuthError' ||
      error.name === 'BrowserAuthError'
    ) {
      // Clear stale account state before interactive login
      // to prevent the same silent failure on the next attempt
      try {
        await msalInstance.logoutRedirect({
          onRedirectNavigate: () => false  // clears cache without redirecting to Microsoft
        });
      } catch (clearError) {
        // If cache clear fails, proceed to interactive login anyway
        console.warn('Cache clear failed, proceeding with interactive login:', clearError);
      }
      // Fall through to interactive login
      await msalInstance.loginRedirect({ scopes });
    }
    throw error;
  }
}
```

If the app uses `loginRedirect` / `handleRedirectPromise` rather than `acquireTokenSilent`, find the `handleRedirectPromise` call and ensure it has a `.catch()` handler that triggers `loginRedirect` rather than silently failing.

### Fix 2 — Switch cache from localStorage to sessionStorage in dev

Find the `PublicClientApplication` config. Change `cacheLocation`:

```javascript
const msalConfig = {
  auth: {
    clientId: '...',
    authority: '...',
    redirectUri: '...',
  },
  cache: {
    cacheLocation: 'sessionStorage',  // was: 'localStorage'
    storeAuthStateInCookie: false,
  },
};
```

**Why:** `sessionStorage` tokens expire when the browser tab closes. This means stale tokens from yesterday never exist when you open the app today — the silent SSO failure can't happen. `localStorage` is appropriate for production where you want persistent sessions; `sessionStorage` is correct for dev where you're frequently restarting and re-testing.

**Important:** Check if `cacheLocation` is hardcoded or driven by an environment variable. If it's already environment-aware, set `sessionStorage` for the dev environment. If it's hardcoded to `localStorage`, change it directly — this is a dev fix and does not need to be environment-conditional, but adding a comment is good practice:

```javascript
cache: {
  // sessionStorage: tokens cleared on tab close — prevents stale silent SSO failures in dev
  // For production, consider switching to localStorage for persistent sessions
  cacheLocation: 'sessionStorage',
  storeAuthStateInCookie: false,
},
```

### Fix 3 — Clear MSAL cache on sign-out

Find the sign-out handler. Ensure it clears the MSAL cache completely before redirecting:

```javascript
async function handleSignOut(msalInstance) {
  const accounts = msalInstance.getAllAccounts();
  if (accounts.length > 0) {
    await msalInstance.logoutRedirect({
      account: accounts[0],
      postLogoutRedirectUri: 'https://localhost:5173/login',
    });
  } else {
    // No account found — clear manually and redirect
    msalInstance.clearCache();
    window.location.href = '/login';
  }
}
```

### Fix 4 — Add startup cache validation

On app load, before attempting any silent token acquisition, check whether the cached account's token is actually usable. If it's clearly expired, clear it and go straight to interactive login:

```javascript
// On app startup, before rendering protected routes:
const accounts = msalInstance.getAllAccounts();
if (accounts.length > 0) {
  const account = accounts[0];
  try {
    await msalInstance.acquireTokenSilent({
      account,
      scopes: ['User.Read'],  // or whatever scopes your app uses
    });
    // Token is valid — proceed normally
  } catch (error) {
    // Token is invalid or expired — clear everything and force interactive login
    console.warn('Startup token validation failed, clearing cache:', error.message);
    msalInstance.clearCache();
    // Do NOT attempt silent login again — go straight to interactive
    await msalInstance.loginRedirect({ scopes: ['User.Read'] });
  }
}
```

---

## What NOT to do

- Do not change anything about the Schwab OAuth flow — this fix is Microsoft/MSAL only
- Do not change the backend auth endpoints
- Do not change the Tier 1/2/3 authorization system
- Do not change JWT handling
- Do not remove the `storeAuthStateInCookie: false` setting if it exists

---

## Verification

After making the changes:

1. Log in successfully once
2. Close the browser tab (do NOT use Incognito)
3. Open a new tab to `https://localhost:5173`
4. The app should either:
   - Go directly to the login screen and complete sign-in on the first attempt, OR
   - If a valid session exists in sessionStorage (same browser session), use it silently
5. Repeat 5 times — should succeed every time
6. Open DevTools → Application → Storage → Session Storage → confirm MSAL keys are present
7. Close the tab, open a new one — Application → Storage → Session Storage should be empty (tokens cleared)
8. Sign in again — should succeed first attempt

---

## Definition of Done

- [ ] `cacheLocation` is set to `sessionStorage`
- [ ] Every `acquireTokenSilent` call has a catch handler that falls back to interactive login
- [ ] `handleRedirectPromise` (if used) has a catch handler that triggers `loginRedirect`
- [ ] Sign-out clears the MSAL cache before redirecting
- [ ] Startup cache validation clears stale tokens rather than silently failing
- [ ] Tested: 5 consecutive sign-ins from a non-Incognito tab all succeed on first attempt
- [ ] No changes to Schwab auth, backend endpoints, or JWT handling
