# CLAUDE-CODE-PROMPT-UNIFIED-DEPLOYMENT.md

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

You are configuring the Options Trade Analyzer to serve the React frontend directly from FastAPI, eliminating the Azure Static Web App (SWA). This completes the BFF architecture — one domain, one deployment, cookies work natively.

**Read these files first — do not skip:**
```bash
cat CLAUDE.md
cat app/main.py
ls web/
cat web/vite.config.js
cat web/package.json
ls .github/workflows/ 2>/dev/null || echo "No workflows directory"
cat staticwebapp.config.json 2>/dev/null || echo "No staticwebapp.config.json"
cat app/api/identity_routes.py | head -80
```

**Jira tickets this prompt covers:**
- OTA-471: FastAPI Static File Mount + SPA Fallback Routing
- OTA-472: Unified GitHub Actions Build + Deploy Pipeline

---

## Phase 1: FastAPI Static File Serving (OTA-471)

### 1.1 Create the static directory

```bash
mkdir -p static
echo "static/" >> .gitignore
```

The `static/` directory will hold the React build output. It's populated during CI/CD, never committed.

### 1.2 Add SPA fallback to main.py

At the **very end** of `app/main.py`, after ALL router includes and middleware registrations, add:

```python
import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# --- Static Frontend (must be LAST — catch-all for SPA routing) ---
_static_dir = Path(__file__).resolve().parent.parent / "static"

if _static_dir.is_dir() and (_static_dir / "index.html").exists():
    # Serve static assets (JS, CSS, images) from /assets/
    app.mount("/assets", StaticFiles(directory=str(_static_dir / "assets")), name="static-assets")
    
    # SPA fallback: any non-API path serves index.html
    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        """Serve the React SPA. API routes take priority (registered first)."""
        file_path = _static_dir / path
        if file_path.is_file() and ".." not in path:
            return FileResponse(str(file_path))
        return FileResponse(str(_static_dir / "index.html"))
```

**Critical rules:**
- This MUST be the last thing in main.py. All `app.include_router()` calls and middleware must come before it.
- API routes registered earlier take priority over the catch-all.
- The `if _static_dir.is_dir()` check means dev mode (no static/ folder) still works — Vite dev server handles the frontend.

### 1.3 Update callback redirect

In `app/api/identity_routes.py`, find the callback route's redirect after successful login. It should redirect to `/` (relative path). Verify it's NOT hardcoded to `https://localhost:5173/` or any absolute URL. In production, `/` now serves the SPA from the same App Service.

For **dev mode**, the callback redirect URI is already going through the Vite proxy (`https://localhost:5173/api/v1/auth/entra/callback`), so the redirect to `/` will land on the Vite dev server at `localhost:5173/` — correct.

For **production**, the redirect to `/` will serve the SPA from FastAPI's static mount — correct.

### 1.4 Test locally

Build the React app and copy to static/:
```bash
cd web
npm run build
cd ..
cp -r web/dist/* static/
```

Start the backend WITHOUT the Vite dev server:
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --ssl-keyfile key.pem --ssl-certfile cert.pem
```

Navigate to `https://127.0.0.1:8000` — you should see the OTA login page served from FastAPI. Click "Sign in with Microsoft" — the full login flow should work.

**Note:** For this test, you'll need to temporarily use `https://127.0.0.1:8000/api/v1/auth/entra/callback` as the redirect URI (not the Vite proxy one). Or just verify the static serving works and test the full auth flow through Vite as usual.

**Checkpoint:**
- `https://127.0.0.1:8000` serves the React SPA
- `https://127.0.0.1:8000/api/v1/health` still returns the health check JSON
- `https://127.0.0.1:8000/api/v1/auth/me` still returns 401 (not the SPA)
- Client-side routes like `https://127.0.0.1:8000/positions` serve index.html (SPA routing)

---

## Phase 2: GitHub Actions Workflow (OTA-472)

### 2.1 Check for existing workflows

```bash
ls -la .github/workflows/ 2>/dev/null
cat .github/workflows/*.yml 2>/dev/null
```

If there's an existing SWA workflow, leave it for now (the cleanup prompt handles it). Create the new App Service workflow alongside it.

### 2.2 Create the unified workflow

Create `.github/workflows/deploy-app-service.yml`:

```yaml
name: Build and Deploy to App Service

on:
  push:
    branches:
      - main

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: web/package-lock.json

      - name: Install frontend dependencies
        run: |
          cd web
          npm ci

      - name: Build frontend
        run: |
          cd web
          npm run build

      - name: Copy frontend build to static/
        run: |
          mkdir -p static
          cp -r web/dist/* static/

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Install backend dependencies
        run: |
          pip install -r requirements.txt

      - name: Deploy to Azure App Service
        uses: azure/webapps-deploy@v3
        with:
          app-name: 'options-analyzer-api'
          publish-profile: ${{ secrets.AZURE_WEBAPP_PUBLISH_PROFILE }}
          package: .
```

### 2.3 Get the publish profile

Don needs to do this manually:

1. Go to Azure Portal → App Service `options-analyzer-api` → **Overview**
2. Click **Download publish profile** (top toolbar)
3. Go to GitHub repo → **Settings** → **Secrets and variables** → **Actions**
4. Create a new secret: `AZURE_WEBAPP_PUBLISH_PROFILE`
5. Paste the entire contents of the downloaded publish profile XML

### 2.4 App Service startup command

Verify the App Service startup command is set correctly. In Azure Portal → App Service → **Configuration** → **General settings** → **Startup Command**:

```
gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 120
```

If it's not set, set it. This ensures the App Service runs the FastAPI app with uvicorn workers.

### 2.5 Add static/ to .gitignore

Verify `static/` is in `.gitignore`:
```bash
grep "^static/" .gitignore || echo "static/" >> .gitignore
```

### 2.6 Update .gitignore for local testing

Also ensure the local test build doesn't get committed:
```bash
grep "^web/dist/" .gitignore || echo "web/dist/" >> .gitignore
```

---

## Verification Checklist

Before committing, verify:

```bash
# Static mount is at the end of main.py
tail -30 app/main.py

# GitHub Actions workflow exists
cat .github/workflows/deploy-app-service.yml

# .gitignore includes static/
grep "static/" .gitignore

# Local test: build and serve
cd web && npm run build && cd ..
cp -r web/dist/* static/
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --ssl-keyfile key.pem --ssl-certfile cert.pem
# Visit https://127.0.0.1:8000 — should see OTA login page
# Visit https://127.0.0.1:8000/api/v1/health — should see JSON
# Visit https://127.0.0.1:8000/positions — should see OTA login page (SPA fallback)
```

---

## House Style Rules

- Follow all patterns in CLAUDE.md
- The static mount MUST be the last thing in main.py
- Never commit the static/ directory or web/dist/
- API routes always take priority over the static catch-all
- Dev mode (Vite on port 5173) must still work — the static mount only activates when static/index.html exists

## Commit

```
OTA-471 OTA-472 feat: unified deployment — serve React from FastAPI, GitHub Actions pipeline
```

After commit, transition OTA-471 and OTA-472 to IN REVIEW (transition ID: 41).

**IMPORTANT:** After pushing, Don needs to:
1. Add the publish profile secret to GitHub (Step 2.3)
2. The push will trigger the workflow
3. Verify `oa.tmtctech.ai` serves the SPA and API from the same domain
4. Then run the post-deploy cleanup prompt (OTA-475)
