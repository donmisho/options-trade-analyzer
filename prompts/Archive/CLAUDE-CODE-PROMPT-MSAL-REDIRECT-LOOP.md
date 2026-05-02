# Claude Code Prompt: Fix Production MSAL Login Redirect Loop (OTA-454)

**Jira:** OTA-454
**Scope:** Fix infinite login redirect loop on `https://oa.tmtctech.ai`. The app redirects to Microsoft login, user picks an account, Microsoft redirects back, but the app immediately redirects to login again — infinite loop.

---

## Context

- This is a **production-only** issue on `https://oa.tmtctech.ai`
- Entra ID app registration is confirmed correct:
  - `https://oa.tmtctech.ai` is registered as a **SPA** redirect URI (not Web)
  - Client ID: `d92400af-f868-4fc4-8a65-30c54982ccf0`
  - Tenant: `690badde-2c05-4887-8be4-e079e8bc55df`
  - PKCE flow with `response_type=code` + `code_challenge`
- Dev login at `localhost:5173` works fine
- The prior MSAL fix addressed stale localStorage tokens — this is a different issue

## Root Cause

**`handleRedirectPromise()` race condition.** After Microsoft redirects back to the app with the auth code in the URL fragment:

1. App loads and checks "is user authenticated?" 
2. `handleRedirectPromise()` has NOT yet resolved (it's async)
3. App sees no authenticated user → triggers `loginRedirect()` → loop

---

## Step 1: Read before changing anything

```bash
cat CLAUDE.md
```

Then discover the current auth initialization flow:

```bash
grep -rn "handleRedirectPromise\|isAuthenticated\|loginRedirect\|loginPopup\|inProgress\|InteractionStatus\|MsalProvider\|useMsal\|useIsAuthenticated\|acquireTokenSilent\|acquireTokenRedirect" web/src/ --include="*.jsx" --include="*.js" --include="*.tsx" | head -60
```

Read every file that appears in the results — especially:
- The MSAL initialization file (likely `main.jsx` or `App.jsx` or an `AuthProvider`)
- Any auth guard / protected route component
- Any component that calls `loginRedirect()`

**Do not make changes until you understand the full auth flow.**

## Step 2: Identify the exact race condition

Look for this pattern (the bug):

```javascript
// BAD: checking auth before handleRedirectPromise resolves
const accounts = msalInstance.getAllAccounts();
if (accounts.length === 0) {
  msalInstance.loginRedirect(...); // fires before redirect promise resolves!
}
```

Or this pattern with React hooks:

```javascript
// BAD: redirecting based on isAuthenticated before inProgress settles
const { inProgress } = useMsal();
const isAuthenticated = useIsAuthenticated();

// Missing check: if inProgress !== InteractionStatus.None, do nothing yet
if (!isAuthenticated) {
  // redirect to login — but inProgress might still be "handleRedirect"!
}
```

## Step 3: Apply the fix

The fix depends on which MSAL pattern the app uses. Here are the two common patterns:

### Pattern A: If using `@azure/msal-react` with `MsalProvider`

The `MsalProvider` handles `handleRedirectPromise()` internally. The bug is in a component that checks auth state without checking `inProgress`:

```jsx
import { useMsal, useIsAuthenticated } from '@azure/msal-react';
import { InteractionStatus } from '@azure/msal-browser';

function AuthGuard({ children }) {
  const { inProgress, instance } = useMsal();
  const isAuthenticated = useIsAuthenticated();

  // CRITICAL: Wait for MSAL to finish processing the redirect
  if (inProgress !== InteractionStatus.None) {
    return <LoadingSpinner message="Signing in..." />;
  }

  // Only AFTER inProgress is None, check auth state
  if (!isAuthenticated) {
    instance.loginRedirect({
      scopes: ['openid', 'profile', 'email', 'offline_access'],
    });
    return <LoadingSpinner message="Redirecting to login..." />;
  }

  return children;
}
```

### Pattern B: If using raw `PublicClientApplication` without MsalProvider

```javascript
const msalInstance = new PublicClientApplication(msalConfig);

// CRITICAL: await handleRedirectPromise BEFORE any auth check
async function initializeAuth() {
  try {
    const response = await msalInstance.handleRedirectPromise();
    if (response) {
      // Successfully processed redirect — user is now authenticated
      msalInstance.setActiveAccount(response.account);
      return response.account;
    }
  } catch (error) {
    console.error('Redirect promise failed:', error);
  }

  // Only NOW check for existing accounts
  const accounts = msalInstance.getAllAccounts();
  if (accounts.length > 0) {
    msalInstance.setActiveAccount(accounts[0]);
    return accounts[0];
  }

  // No accounts — trigger interactive login
  return null; // let the UI decide when to call loginRedirect
}
```

### Pattern C: If using `msalInstance.initialize()` (MSAL v3+)

```javascript
const msalInstance = new PublicClientApplication(msalConfig);

// MSAL v3 requires explicit initialization
await msalInstance.initialize();
const response = await msalInstance.handleRedirectPromise();

if (response) {
  msalInstance.setActiveAccount(response.account);
}

// NOW safe to render the app
```

## Step 4: Verify loading state exists

Ensure there is a visible loading indicator while MSAL is processing. The user should NEVER see a blank screen or a flash of the login page during redirect processing. Look for or create a simple loading component:

```jsx
function LoadingSpinner({ message = 'Loading...' }) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100vh',
      backgroundColor: 'var(--bg1, #0d1117)',
      color: 'var(--text, #e6edf3)',
    }}>
      <div style={{ fontSize: '14px', marginTop: '16px' }}>{message}</div>
    </div>
  );
}
```

## Step 5: Check for multiple loginRedirect() call sites

```bash
grep -rn "loginRedirect\|loginPopup" web/src/ --include="*.jsx" --include="*.js" --include="*.tsx"
```

Every single call site must be guarded by an `inProgress` check. If ANY call site fires `loginRedirect()` while `inProgress !== InteractionStatus.None`, the loop will continue.

## Step 6: Verify setActiveAccount is called

After a successful redirect, `msalInstance.setActiveAccount()` must be called with the returned account. Without this, subsequent `acquireTokenSilent()` calls may fail and trigger another redirect:

```bash
grep -rn "setActiveAccount" web/src/ --include="*.jsx" --include="*.js" --include="*.tsx"
```

If `setActiveAccount` is never called, add it in the `handleRedirectPromise()` success path.

---

## What NOT to change

- Do NOT modify Entra ID app registration (it's correct)
- Do NOT change Schwab OAuth flow
- Do NOT change backend auth endpoints or JWT handling
- Do NOT change the Tier 1/2/3 authorization system
- Do NOT change `staticwebapp.config.json`
- Do NOT switch `cacheLocation` in production — `localStorage` is correct for prod

## Acceptance Criteria

- [ ] Production login at `https://oa.tmtctech.ai` completes without looping
- [ ] Loading spinner displays while `handleRedirectPromise()` is processing
- [ ] No `loginRedirect()` call fires while `inProgress !== InteractionStatus.None`
- [ ] `setActiveAccount()` is called after successful redirect
- [ ] Dev login at `https://localhost:5173` still works
- [ ] After login, the app navigates to the dashboard (not a blank page)

## Commit Message

```
OTA-454 fix: resolve production MSAL login redirect loop

- Await handleRedirectPromise() before checking auth state
- Guard all loginRedirect() calls with inProgress check
- Add loading state during redirect processing
- Call setActiveAccount() on successful redirect
```
