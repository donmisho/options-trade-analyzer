# LOGIN-QA-AND-HARDENING.md
# QA Agent Prompt — Login Process Audit + Fix Recommendations

## Context

The Options Analyzer uses Schwab OAuth 2.0 for market data access. The login flow involves a self-signed SSL certificate (dev), a popup-based OAuth redirect, in-memory token storage, and polling-based connection detection. The product owner consistently needs to use InPrivate/Incognito browsing to successfully log in after any break in usage (backend restart, token expiry, overnight gap). This defeats the purpose of the connection indicator UX and wastes startup time.

**Your job**: Audit the entire login chain, reproduce the failures that force InPrivate usage, identify every root cause, and produce a prioritized list of code changes the dev agent can implement.

---

## Reference Files (read all before starting)

| File | What to look for |
|------|-----------------|
| `SCHWAB-LOGIN-PROCESS.md` (repo root) | Full OAuth flow documentation, troubleshooting table |
| `app/api/schwab_auth_routes.py` | Backend OAuth endpoints: `/login`, `/callback`, `/status` |
| `app/providers/schwab_token_manager.py` | Token storage, refresh logic, expiry tracking |
| `web/src/components/Header.jsx` | Frontend status indicator, popup open, polling logic |
| `web/src/api/client.js` | `getSchwabStatus()` and API base URL configuration |
| `web/vite.config.js` | Proxy config (`secure: false`, target `https://127.0.0.1:8000`) |
| `options-analyzer/.env` | `SCHWAB_CALLBACK_URL`, app key/secret |
| `key.pem` / `cert.pem` (repo root) | Self-signed SSL certificates |
| `web/src/App.jsx` or router file | Route definitions, app shell mounting |

---

## Phase 1: Static Code Audit

Read each file listed above and answer these questions. Log findings as you go.

### 1.1 — Certificate & HTTPS Layer

- [ ] Check `cert.pem` expiration date: run `openssl x509 -enddate -noout -in cert.pem`. Is it expired or expiring within 30 days?
- [ ] Check if the cert's Common Name (CN) or Subject Alternative Name (SAN) includes BOTH `127.0.0.1` AND `localhost`. Edge/Chrome treat these as different origins. If only `127.0.0.1` is in the cert but the user navigates to `https://localhost:5173`, the popup to `https://127.0.0.1:8000` is a cross-origin HTTPS request to an untrusted cert — the browser may silently block it.
- [ ] Check if `cert.pem` includes a SAN extension at all (modern browsers ignore CN without SAN).
- [ ] In `vite.config.js`: confirm `server.https` is configured (or that Vite runs on HTTPS). If the frontend is HTTP but the backend is HTTPS, mixed-content rules apply.
- [ ] Check if Vite's proxy config sets `changeOrigin: true` in addition to `secure: false`.

### 1.2 — OAuth Callback Flow

- [ ] In `schwab_auth_routes.py`, read the `/callback` handler. After token exchange succeeds, what HTML/response does it return to the popup window? Specifically:
  - Does it return a page that calls `window.close()`?
  - Does it set any cookies?
  - Does it return CORS headers?
  - What happens if the token exchange FAILS — does the popup show an error or just hang?
- [ ] Check if the `/callback` endpoint has any error handling for: invalid/expired auth code, network failure to Schwab token endpoint, malformed response from Schwab.
- [ ] Check if the `/login` endpoint adds a `state` parameter to the OAuth URL (CSRF protection). If not, note it as a security finding but not a login-failure cause.

### 1.3 — Token Manager

- [ ] In `schwab_token_manager.py`, how are tokens stored? Confirm in-memory (dict/class attribute). 
- [ ] Is there any file-based or DB-based token persistence for dev mode? If not, every backend restart (including `--reload` triggered by a file save) wipes tokens.
- [ ] Does the token manager's `refresh_token()` method handle Schwab returning an error (e.g., refresh token revoked, network timeout)? Or does it throw an unhandled exception that leaves the token state corrupted (e.g., old access token cleared but no new one stored)?
- [ ] After a failed refresh, does `get_status()` still return `connected: true` with stale data, or does it correctly flip to `connected: false`?
- [ ] Is there a race condition: if two API calls trigger simultaneous refresh attempts, could one overwrite the other's new token?

### 1.4 — Frontend Polling & Popup

- [ ] In `Header.jsx`, how is the popup opened? `window.open()` with specific dimensions/features?
- [ ] What URL does the popup open to — is it `https://127.0.0.1:8000/api/v1/auth/schwab/login` (direct to backend) or through the Vite proxy?
- [ ] Is the popup URL on the same origin as the main window? If not, can the main window detect when the popup closes? (`window.opener` cross-origin restrictions apply.)
- [ ] What happens if the popup is blocked by the browser's popup blocker? Is there a fallback or user-facing error?
- [ ] After the popup closes (either auto or manual), does the polling interval get cleared? Or does it keep polling indefinitely on a timer leak?
- [ ] If the user clicks "Disconnected" while a previous popup is still open, does it open a second popup?
- [ ] Is there any `catch` on the `getSchwabStatus()` polling call? If the backend is down or the self-signed cert is rejected, does the polling silently fail, throw to console, or crash the component?

### 1.5 — Browser Cache & HSTS Interactions

- [ ] Does the backend send any HSTS (`Strict-Transport-Security`) headers? If yes, once the browser sees HSTS from `127.0.0.1`, it will refuse to connect via HTTP or with an untrusted cert for the max-age duration — this is a known cause of "works in InPrivate but not in regular browser."
- [ ] Does the backend set `Cache-Control` headers on the `/status` endpoint? If the browser caches a `connected: false` response, the indicator could stay red even after successful login.
- [ ] Does `client.js` or Axios/fetch configuration cache GET responses?
- [ ] Check if Edge's HTTPS-first mode or automatic HTTPS upgrades could interfere with `127.0.0.1` requests.

---

## Phase 2: Runtime Testing

Start the backend and frontend. Test in a REGULAR browser window (not InPrivate). For each test, log the actual behavior.

### 2.1 — Clean Start (backend just started)

1. Start backend: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --ssl-keyfile key.pem --ssl-certfile cert.pem`
2. Start frontend: `cd web && npm run dev`
3. Open `https://localhost:5173` in Edge (regular window)
4. **Observe**: Does the page load? Any certificate warnings? Any console errors?
5. **Observe**: Does the header show "Disconnected"?
6. Click "Disconnected" — does a popup open?
7. **Observe**: Does the popup show the Schwab login page, a cert warning, or a blank page?
8. If cert warning: click through it. Does the Schwab login page then load?
9. Complete Schwab login. **Observe**: Does the popup close automatically? How long does it take?
10. **Observe**: Does the header update to "Connected"?
11. Open browser DevTools → Network tab. Check for any failed requests (red entries).
12. Open browser DevTools → Console. Check for any errors.
13. **Log all findings.**

### 2.2 — Simulated Token Expiry (backend restart)

1. With a connected session active, stop the backend (Ctrl+C).
2. **Observe**: Does the header change to "Disconnected" within a reasonable time? (It polls every 5 minutes for status.)
3. Restart the backend.
4. **Observe**: Does the header still show the old state? How long until it updates?
5. Click "Disconnected" to re-login.
6. **Observe**: Does the popup open and load Schwab, or does it hit a cached cert rejection?
7. Complete login. **Observe**: Does the flow complete successfully without needing InPrivate?
8. **Log all findings.**

### 2.3 — Stale Session (close browser, reopen)

1. With a connected session, close the browser entirely.
2. Reopen Edge (regular window). Navigate to `https://localhost:5173`.
3. **Observe**: Certificate warning? Page loads? Header state?
4. If "Disconnected", click it. Does the login flow work?
5. **Log all findings.**

### 2.4 — The InPrivate Comparison

1. Reproduce whatever failure occurred in 2.2 or 2.3.
2. Now open InPrivate and navigate to `https://localhost:5173`.
3. **Observe**: Does the same failure occur, or does it work cleanly?
4. **Document the specific difference** — this identifies what browser-cached state is causing the regular-window failure.

### 2.5 — Certificate Trust Check

1. In Edge, navigate directly to `https://127.0.0.1:8000/health` in a regular window.
2. **Observe**: Cert warning? Can you click through? Does the health endpoint respond?
3. Now navigate to `https://127.0.0.1:8000/api/v1/auth/schwab/status`.
4. **Observe**: Same behavior? Any difference?
5. Check `edge://net-internals/#hsts` — is there an HSTS entry for `127.0.0.1`?
6. Check `edge://settings/privacy` → Manage certificates — is the self-signed cert cached/rejected?

### 2.6 — Popup Blocker Test

1. Enable popup blocking in Edge settings (or confirm it's at default).
2. Click "Disconnected."
3. **Observe**: Does Edge block the popup? Is there a notification? Does the app handle this gracefully?

---

## Phase 3: Produce Fix Recommendations

Based on your findings, write a structured report with this format for each issue found:

```
### ISSUE-N: [Short title]

**Symptom**: What the user sees
**Root cause**: What's actually happening technically
**Why InPrivate works**: Why a clean browser session avoids this
**Affected files**: List of files to change
**Recommended fix**: Specific code changes (describe what to add/modify/remove)
**Priority**: CRITICAL (blocks login) / HIGH (causes confusion) / MEDIUM (improvement)
```

### Known Likely Issues to Investigate

Based on the product owner's description, these are the most probable root causes. Confirm or rule out each one:

1. **HSTS poisoning**: The self-signed cert backend may send HSTS headers. Once cached, Edge refuses the self-signed cert silently. InPrivate has no HSTS cache → works.

2. **Stale cert rejection cache**: Edge remembers that it showed a cert warning for `127.0.0.1` and either (a) caches the "proceed anyway" exception which expires, or (b) caches the rejection permanently until cleared.

3. **Popup cross-origin cert block**: The main window is `https://localhost:5173` but the popup opens `https://127.0.0.1:8000`. The popup inherits the parent's cert trust context in regular mode but gets a fresh context in InPrivate.

4. **No SAN in certificate**: Modern Chrome/Edge requires Subject Alternative Name, not just Common Name. If the cert only has CN=127.0.0.1, the browser may reject it at the TLS level without even showing a warning page.

5. **Token manager silent corruption**: After backend restart, the token manager state is empty but the frontend polling may cache a previous `connected: true` response, creating a desync.

6. **Missing error handling in callback**: If the OAuth callback fails silently (no error page in popup), the user sees a hung popup, closes it manually, and the main window never detects success.

7. **Polling timer leak**: If a previous login attempt's polling interval was never cleared, multiple intervals could be stacking up, causing erratic behavior.

8. **`--reload` causing mid-flow restart**: If the dev saves a file while the OAuth flow is in progress, uvicorn's `--reload` restarts the backend mid-callback, losing the auth code exchange. The user sees a failed login with no clear error.

9. **Browser caching `/status` response**: If the GET `/status` response doesn't include `Cache-Control: no-store`, the browser could serve a stale cached response.

10. **Mixed localhost/127.0.0.1 origin confusion**: The frontend uses `localhost`, the backend uses `127.0.0.1`. These are different origins for cookie and cert purposes. Schwab's callback goes to `127.0.0.1`. The Vite proxy targets `127.0.0.1`. But the user's address bar says `localhost`.

---

## Phase 4: Dev Agent Handoff

After completing the report, organize fixes into a dev agent prompt with this structure:

```markdown
# LOGIN-HARDENING — Dev Agent Prompt

## Changes (in implementation order)

### Fix 1: [title]
**Files**: [list]
**What to do**: [specific instructions]
**How to verify**: [what to check after implementing]

### Fix 2: [title]
...

## Verification Checklist (run after all fixes)
- [ ] Fresh backend start → frontend loads → click Disconnected → login completes → Connected shows (regular browser, not InPrivate)
- [ ] Backend restart → re-login works without InPrivate
- [ ] Close browser → reopen → re-login works without InPrivate
- [ ] Popup blocked → user sees helpful error message
- [ ] Backend down during polling → no console errors, graceful degradation
- [ ] File save during `--reload` → token state recovers gracefully
```

---

## Important Constraints

- Schwab is the sole market data provider — this flow MUST work reliably
- Self-signed certs are acceptable for dev, but the flow should not require manual cert trust steps after initial setup
- InPrivate should NEVER be required for normal operation — that's the primary success criterion
- Do not change the Schwab callback URL (it's registered in the Schwab developer portal)
- Do not change the backend port (8000) or frontend port (5173) without discussing implications
- The backend runs on Windows (PowerShell) — test accordingly
- House style: no `$` prefix on monetary values, dates as `mm-dd-yyyy`, dark theme CSS variables only
