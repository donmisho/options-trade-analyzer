# CLAUDE-CODE-PROMPT-T2-FRONTEND-BFF-AUTH.md

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

You are migrating the Options Trade Analyzer React frontend from MSAL.js browser-side auth to cookie-based BFF auth. The backend BFF routes (built by T1 prompt) handle all OIDC flows. The frontend's job is simple: send cookies, check `/auth/me`, and redirect to login if not authenticated.

**Read these files first — do not skip:**
```bash
cat CLAUDE.md
cat web/package.json
cat web/src/main.jsx
ls web/src/
cat web/src/App.jsx
cat web/src/api/client.js
cat web/src/components/Header.jsx
```

Then find all MSAL-related code:
```bash
grep -r "msal\|Msal\|MSAL\|useMsal\|useAccount\|MsalProvider\|acquireToken\|handleRedirect\|InteractionStatus\|loginRedirect\|loginPopup" web/src/ --include="*.jsx" --include="*.js" -l
```

Read every file that grep returns. Understand the full MSAL surface before removing anything.

**Jira tickets this prompt covers:**
- OTA-464: Remove MSAL.js Dependencies and All Browser Token Code
- OTA-465: Cookie-Based AuthContext, ProtectedRoute, Login Page, API Client

**Dependency:** The backend BFF routes (T1 prompt / OTA-461,462,463) should be committed before testing this frontend. However, you can write all the code in parallel — just test after T1 is done.

---

## Phase 1: Remove MSAL (OTA-464)

### 1.1 Uninstall Packages

```bash
cd web
npm uninstall @azure/msal-browser @azure/msal-react
```

### 1.2 Delete MSAL Config Files

Delete any MSAL configuration files. These may be named:
- `msalConfig.js`
- `authConfig.js`
- `msal.js`
- Any file in `web/src/` that exports `msalConfig` or `msalInstance`

### 1.3 Remove MSAL from App Entry Point

In `web/src/main.jsx` (or wherever the app root is):
- Remove `import { MsalProvider } from '@azure/msal-react'`
- Remove `import { PublicClientApplication } from '@azure/msal-browser'`
- Remove MSAL instance creation (`new PublicClientApplication(...)`)
- Remove `<MsalProvider instance={...}>` wrapper
- Remove any `handleRedirectPromise()` calls

### 1.4 Remove MSAL from Components

For every file found by the grep in the context step:
- Remove all `useMsal()` hook calls
- Remove all `useAccount()` hook calls  
- Remove all `useMsalAuthentication()` calls
- Remove all `useIsAuthenticated()` calls
- Remove all `InteractionStatus` imports and checks
- Remove all `acquireTokenSilent()` / `acquireTokenRedirect()` / `acquireTokenPopup()` calls
- Remove all `instance.loginRedirect()` / `instance.loginPopup()` calls
- Remove all `instance.logoutRedirect()` / `instance.logoutPopup()` calls
- Remove all `handleRedirectPromise()` calls and `.then()` chains

**Do not delete the components themselves** — just remove the MSAL imports and calls. They'll be rewired in Phase 2.

### 1.5 Remove MSAL from API Client

In `web/src/api/client.js`:
- Remove any MSAL instance imports
- Remove any `acquireTokenSilent` calls used to get Bearer tokens
- Remove any `Authorization: Bearer ${token}` header injection
- Leave the API call functions intact — just remove the auth header logic

### 1.6 Remove MSAL localStorage Cleanup

Search for and remove any code that cleans up MSAL localStorage/sessionStorage keys:
```bash
grep -r "localStorage\|sessionStorage" web/src/ --include="*.jsx" --include="*.js" | grep -i "msal"
```

### 1.7 Verify Clean Removal

```bash
# Must return nothing:
grep -r "msal\|Msal\|MSAL" web/src/ --include="*.jsx" --include="*.js"
grep -r "@azure/msal" web/package.json

# Must compile:
cd web && npm run build
```

The build will have errors from missing auth functions — that's expected. Phase 2 replaces them.

---

## Phase 2: Cookie-Based Auth (OTA-465)

### 2.1 AuthContext

Create `web/src/context/AuthContext.jsx`:

```jsx
import { createContext, useContext, useState, useEffect, useCallback } from 'react';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [csrfToken, setCsrfToken] = useState(null);

  const checkAuth = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/auth/me', {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        setUser(data);
        setIsAuthenticated(true);
        setCsrfToken(data.csrf_token);
      } else {
        setUser(null);
        setIsAuthenticated(false);
        setCsrfToken(null);
      }
    } catch (err) {
      console.error('Auth check failed:', err);
      setUser(null);
      setIsAuthenticated(false);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const login = useCallback((provider = 'entra') => {
    // Full page redirect to backend login endpoint
    window.location.href = `/api/v1/auth/login?provider=${provider}`;
  }, []);

  const logout = useCallback(async () => {
    try {
      await fetch('/api/v1/auth/logout', {
        method: 'POST',
        credentials: 'include',
        headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : {},
      });
    } catch (err) {
      console.error('Logout failed:', err);
    }
    setUser(null);
    setIsAuthenticated(false);
    setCsrfToken(null);
    // Redirect to login page
    window.location.href = '/';
  }, [csrfToken]);

  return (
    <AuthContext.Provider value={{ user, isAuthenticated, isLoading, csrfToken, login, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
```

### 2.2 ProtectedRoute

Create `web/src/components/ProtectedRoute.jsx`:

```jsx
import { useAuth } from '../context/AuthContext';
import LoginPage from '../pages/LoginPage';

export default function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    // Use the same startup loading indicator pattern if StartupProgress exists
    // Otherwise, a minimal centered spinner
    return (
      <div style={{ 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center', 
        height: '100vh',
        background: 'var(--bg0)',
        color: 'var(--text1)'
      }}>
        Loading...
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return children;
}
```

### 2.3 Login Page Update

Find the existing login page / login component. It currently uses MSAL's `loginRedirect` or `loginPopup`. Update it:

- Keep the exact same visual design (OTA logo, dark theme, "Property of TM Technologies, LLC." text, card container)
- Replace the MSAL button handler with a simple link:
  ```jsx
  <a 
    href="/api/v1/auth/login?provider=entra"
    style={{/* keep existing button styles */}}
  >
    <img src={microsoftLogo} alt="" /> Sign in with Microsoft
  </a>
  ```
  Or use an `onClick={() => login('entra')}` from useAuth — either works since `login()` just does a `window.location.href` redirect.
- No popup. No MSAL interaction. Just a redirect.

### 2.4 App Entry Point

Update `web/src/main.jsx`:

```jsx
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';

// Wrap the app:
<AuthProvider>
  <ProtectedRoute>
    {/* existing app content (Router, pages, etc.) */}
  </ProtectedRoute>
</AuthProvider>
```

### 2.5 API Client Update

Update `web/src/api/client.js`:

**Every fetch call must include:**
```javascript
credentials: 'include',  // sends the ota_session cookie
```

**State-changing requests (POST, PATCH, PUT, DELETE) must include the CSRF token.**

Create a helper:
```javascript
// At the top of client.js:
function getCsrfToken() {
  // Read from a module-level variable set by AuthContext
  // OR read from a meta tag
  // OR import from AuthContext (if using a shared module)
  return window.__OTA_CSRF_TOKEN || '';
}

// Update setCsrfToken to be callable from AuthContext:
export function setCsrfTokenGlobal(token) {
  window.__OTA_CSRF_TOKEN = token;
}
```

Then in AuthContext, after getting the CSRF token from /me:
```javascript
import { setCsrfTokenGlobal } from '../api/client';
// In checkAuth, after setCsrfToken(data.csrf_token):
setCsrfTokenGlobal(data.csrf_token);
```

**Update every API function** in client.js:
```javascript
// Before (example):
export async function getWatchlist() {
  const response = await fetch('/api/v1/watchlist');
  return response.json();
}

// After:
export async function getWatchlist() {
  const response = await fetch('/api/v1/watchlist', {
    credentials: 'include',
  });
  if (response.status === 401) {
    window.location.href = '/';
    return null;
  }
  return response.json();
}

// For POST/PATCH/DELETE:
export async function createPosition(data) {
  const response = await fetch('/api/v1/positions/follow', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': getCsrfToken(),
    },
    body: JSON.stringify(data),
  });
  if (response.status === 401) {
    window.location.href = '/';
    return null;
  }
  return response.json();
}
```

**Better: create a wrapper function** to avoid repeating this in every API call:
```javascript
async function apiFetch(url, options = {}) {
  const headers = { ...options.headers };
  
  if (['POST', 'PATCH', 'PUT', 'DELETE'].includes(options.method?.toUpperCase())) {
    headers['X-CSRF-Token'] = getCsrfToken();
  }
  
  const response = await fetch(url, {
    ...options,
    credentials: 'include',
    headers,
  });
  
  if (response.status === 401) {
    window.location.href = '/';
    return null;
  }
  
  return response;
}
```

Then refactor all API functions to use `apiFetch` instead of raw `fetch`.

### 2.6 Header Component Update

The Header currently shows Schwab connection status. It may also show user info from MSAL. Update:
- User display name: get from `useAuth()` → `user.display_name`
- Logout: call `logout()` from `useAuth()`
- Schwab status indicator: unchanged (still polls `/api/v1/auth/schwab/status`)

### 2.7 Vite Proxy Check

Verify `web/vite.config.js` proxies `/api` to the backend. The cookie will flow through the proxy in dev. Ensure:
```javascript
proxy: {
  '/api': {
    target: 'https://127.0.0.1:8000',
    secure: false,
    changeOrigin: true,
  }
}
```

The `secure: false` is needed for the self-signed cert. The cookie's `Secure` flag works because the Vite dev server also runs on HTTPS.

### 2.8 Verify

```bash
cd web && npm run build
# Must compile with zero errors

# Must return nothing:
grep -r "msal\|Msal\|MSAL\|acquireToken\|loginRedirect\|loginPopup" web/src/ --include="*.jsx" --include="*.js"

# Must find AuthContext and ProtectedRoute:
grep -r "useAuth\|AuthProvider\|ProtectedRoute" web/src/ --include="*.jsx" --include="*.js"
```

**Manual test checklist (after T1 backend is also running):**
1. Open `https://localhost:5173` → see login page (not authenticated)
2. Click "Sign in with Microsoft" → redirected to Entra
3. Select account → redirected back to app → authenticated, see dashboard
4. Refresh page → still authenticated (cookie persists)
5. Open new tab, go to `https://localhost:5173` → still authenticated
6. Click user name / logout → back to login page
7. All API calls work (watchlist loads, quotes load, etc.)
8. Schwab connect button still works

---

## House Style Rules

- Follow all UI rules from CLAUDE.md and UI-GUIDANCE.md
- Dark theme CSS variables only — never inline hex
- No `$` prefix on monetary values
- Buttons sized to content with fixed padding, never full-width
- Keep existing visual design for login page exactly as-is

## Commit

```
OTA-464 OTA-465 feat: frontend BFF auth migration — remove MSAL.js, cookie-based AuthContext
```

After commit, transition OTA-464 and OTA-465 to IN REVIEW (transition ID: 41).
