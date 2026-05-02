# OTA-450: Fix Production API Base URL — MSAL Blank Screen

## Ticket
OTA-450 — BUG: Production build hits localhost:8000 backend — MSAL redirect fails with blank screen

## Problem
After MSAL redirect on the deployed Azure Static Web App, the app renders a blank screen. Console error:
```
[MSAL] Redirect processing failed: Error: Cannot reach the backend. Is it running on https://127.0.0.1:8000?
```
The production build is hardcoding or defaulting to `https://127.0.0.1:8000` instead of the Azure App Service URL.

## Context — How the Two Environments Work

| Environment | Frontend | Backend | API Routing |
|-------------|----------|---------|-------------|
| **Local dev** | Vite dev server (`https://localhost:5173`) | `https://127.0.0.1:8000` | Vite proxy in `vite.config.js` forwards `/api/*` to backend |
| **Production** | Azure Static Web Apps (`purple-ground-0d4efed10.4.azurestaticapps.net`) | Azure App Service | No proxy — frontend must call backend URL directly |

The fix must work for **both** environments. Vite's `import.meta.env` system handles this: `.env.development` values are used by `npm run dev`, and `.env.production` values are baked into `npm run build`.

---

## Step 0 — Read Project Context

```bash
cat CLAUDE.md
```

Then read these files to understand current state:

```bash
cat web/src/api/client.js
cat web/src/main.jsx
cat web/vite.config.js
cat web/.env.production
cat web/.env.development 2>/dev/null || echo "No .env.development file"
```

Look for:
- How `API_BASE_URL` or equivalent is currently set in `client.js`
- Any hardcoded `https://127.0.0.1:8000` references in frontend code
- What's currently in `.env.production`
- The error message "Cannot reach the backend" — find where it's thrown

---

## Step 1 — Create/Update Environment Files

### `web/.env.development` (create if missing)
```
# Dev: empty string = relative URLs, handled by Vite proxy
VITE_API_BASE_URL=
```

### `web/.env.production` (update)
```
# Production: Azure App Service backend URL (no trailing slash)
VITE_API_BASE_URL=https://options-analyzer-api.azurewebsites.net
```

**IMPORTANT:** Confirm the actual Azure App Service URL. Check the existing `.env.production` file — it may already have the correct URL. If the App Service name is different, use whatever is already configured. The key is that `VITE_API_BASE_URL` must be set and consumed.

---

## Step 2 — Update `web/src/api/client.js`

Find the API base URL configuration. It's likely one of these patterns:
- `const API_BASE = 'https://127.0.0.1:8000'` (hardcoded — wrong)
- `const API_BASE = import.meta.env.VITE_API_URL || 'https://127.0.0.1:8000'` (fallback to localhost — wrong in prod)
- No base URL at all (relative paths — would actually work with proxy but may not be the case)

**Change to:**
```javascript
const API_BASE = import.meta.env.VITE_API_BASE_URL || '';
```

The empty-string fallback means: in dev, if the env var is empty or missing, all API calls use relative URLs (`/api/v1/...`) which the Vite proxy picks up. In production, the env var provides the full URL prefix.

Make sure ALL `fetch()` or `axios` calls in `client.js` use this base:
```javascript
// Before (example)
fetch('https://127.0.0.1:8000/api/v1/health')
// After
fetch(`${API_BASE}/api/v1/health`)
```

Search the ENTIRE `web/src/` directory for any hardcoded `127.0.0.1:8000` or `localhost:8000` references:
```bash
grep -rn "127.0.0.1:8000\|localhost:8000" web/src/
```

Fix every occurrence to use `API_BASE` or `import.meta.env.VITE_API_BASE_URL`.

---

## Step 3 — Update `web/src/main.jsx`

Find the backend reachability check that produces the error message "Cannot reach the backend. Is it running on https://127.0.0.1:8000?". Update it to:

1. Use `import.meta.env.VITE_API_BASE_URL || ''` for the health check URL
2. Update the error message to reflect the actual target URL:
   ```javascript
   const apiBase = import.meta.env.VITE_API_BASE_URL || '';
   // ...in the catch block:
   throw new Error(`Cannot reach the backend at ${apiBase || 'proxy'}.`);
   ```

---

## Step 4 — Verify No Other Hardcoded URLs

```bash
# Full search for any remaining hardcoded backend URLs in frontend
grep -rn "127\.0\.0\.1:8000\|localhost:8000" web/src/ --include="*.js" --include="*.jsx" --include="*.ts" --include="*.tsx"
```

The ONLY place `127.0.0.1:8000` should appear is `web/vite.config.js` (the proxy target) — that's correct and should NOT be changed.

---

## Step 5 — Verify Locally

```bash
cd web
npm run dev
```

Open `https://localhost:5173` — confirm the app loads and API calls work through the Vite proxy. The console should NOT show any `127.0.0.1:8000` URLs in network requests (they should be relative `/api/v1/...` paths proxied by Vite).

Then test the build:
```bash
npm run build
grep -r "127.0.0.1" dist/ && echo "FAIL: localhost URL leaked into production build" || echo "PASS: no localhost URLs in build"
```

---

## Commit

```
git add web/.env.development web/.env.production web/src/api/client.js web/src/main.jsx
git commit -m "OTA-450: fix environment-aware API base URL for production builds

- Use VITE_API_BASE_URL env var in client.js and main.jsx
- Dev: empty string (Vite proxy handles routing)
- Production: Azure App Service URL baked into build
- Remove all hardcoded 127.0.0.1:8000 from frontend src
- Fixes blank screen after MSAL redirect in production"
```

---

## House Style Reminders
- Do NOT modify `vite.config.js` proxy target — `127.0.0.1:8000` is correct there
- Do NOT add trailing slash to `VITE_API_BASE_URL`
- The `.env.production` value is baked in at build time — changing it requires a rebuild + redeploy
