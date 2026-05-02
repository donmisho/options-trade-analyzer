# CLAUDE-CODE-PROMPT-POST-DEPLOY-CLEANUP.md

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

The unified deployment (OTA-471/472) is verified working in production. The React SPA is now served from FastAPI on the App Service. This prompt cleans up all Azure Static Web App (SWA) references and deprecated resources.

**PREREQUISITE:** Only run this prompt AFTER verifying that `oa.tmtctech.ai` serves the SPA and login works end-to-end in production. If production isn't working, STOP and fix that first.

**Read these files first:**
```bash
cat CLAUDE.md
cat architecture-plan.md
cat SCHWAB-LOGIN-PROCESS.md
ls .github/workflows/
cat staticwebapp.config.json 2>/dev/null || echo "No staticwebapp.config.json"
grep -rn "static.*web.*app\|staticwebapp\|SWA\|swa" CLAUDE.md architecture-plan.md --include="*.md" 2>/dev/null
grep -rn "static.*web.*app\|staticwebapp\|SWA\|swa" app/ web/src/ --include="*.py" --include="*.js" --include="*.jsx" 2>/dev/null
```

**Jira ticket:** OTA-475

---

## Phase 1: Remove SWA Files from Repo

### 1.1 Delete SWA config

```bash
rm -f staticwebapp.config.json
```

### 1.2 Delete or disable SWA GitHub Actions workflow

```bash
# Find SWA workflow files
ls .github/workflows/ | grep -i "static\|swa"
```

Delete any SWA-specific workflow files (typically named `azure-static-web-apps-*.yml`). Do NOT delete the new `deploy-app-service.yml`.

### 1.3 Remove SWA references from source code

Search and remove any SWA-specific configuration or references:
```bash
grep -rn "staticwebapp\|static.web.app\|SWA" app/ web/src/ --include="*.py" --include="*.js" --include="*.jsx" --include="*.json"
```

If any references are found, evaluate whether they should be removed or updated.

---

## Phase 2: Update Documentation

### 2.1 Update CLAUDE.md

**Remove:**
- Any references to `staticwebapp.config.json`
- Any references to Azure Static Web Apps routing
- Any references to SWA deployment

**Add/Update:**
- In the Architecture section, update the deployment model:
  ```markdown
  ### Deployment Model
  
  The app is deployed as a single Azure App Service. FastAPI serves both the
  API endpoints and the React SPA as static files. There is no separate
  frontend deployment.
  
  - **Production URL:** https://oa.tmtctech.ai (Cloudflare → App Service)
  - **API endpoints:** https://oa.tmtctech.ai/api/v1/*
  - **Frontend:** https://oa.tmtctech.ai/ (served from static/ directory)
  - **CI/CD:** GitHub Actions → App Service (single workflow)
  - **CDN:** Cloudflare (edge caching for static assets)
  
  The `static/` directory is built during CI/CD (`npm run build` → copy to
  static/) and never committed to the repo.
  ```

- Update the Backend Structure tree to include the static mount:
  ```
  static/                                  # React build output (CI/CD only, gitignored)
  ```

- In Development Commands, clarify the two modes:
  ```markdown
  ### Development (hot reload)
  - Terminal 1: Backend on https://127.0.0.1:8000 (uvicorn with SSL)
  - Terminal 2: Frontend on https://localhost:5173 (Vite dev server, proxies /api to backend)
  
  ### Production (unified)
  - App Service runs FastAPI which serves both API and static frontend
  - No separate frontend server or proxy needed
  ```

### 2.2 Update architecture-plan.md

Update the Phase 3 / Phase History entry:
```markdown
- **Phase 3**: Azure Deployment ✅ (live 2026-03-04 — unified App Service, SWA deprecated 2026-04-11)
```

Add to Core Architectural Patterns or update Pattern 4:
```markdown
### Pattern 5: Unified Deployment

FastAPI serves both the API and the React SPA from a single App Service.
Static files are built during CI/CD and mounted at the app root. Cloudflare
provides edge CDN. Heavy assets (images, documents) live in Azure Blob Storage
with their own CDN endpoint.

This pattern ensures same-origin cookies for BFF auth and eliminates
the need for separate frontend hosting (SWA, S3, etc.).
```

### 2.3 Update auth-process.md (if it exists)

If the T3 prompt has already created `auth-process.md`, update it to note:
- Same-origin deployment means no cross-domain cookie issues
- No proxy configuration needed in production
- Dev mode uses Vite proxy (localhost:5173 → 127.0.0.1:8000)

If auth-process.md doesn't exist yet, skip — the T3 prompt will create it with the correct information.

---

## Phase 3: Manual Steps (Instructions for Don)

Output these instructions at the end of the prompt for Don to execute manually:

```
=== MANUAL STEPS REQUIRED ===

1. DNS VERIFICATION
   - Go to Cloudflare dashboard
   - Verify oa.tmtctech.ai CNAME points to the App Service
     (options-analyzer-api-*.azurewebsites.net), NOT to the SWA
   - If it points to SWA, update the CNAME target to the App Service
   - Verify Cloudflare proxy (orange cloud) is enabled

2. DELETE SWA RESOURCE (only after DNS is verified pointing to App Service)
   - Go to Azure Portal → Static Web Apps → options-analyzer-web
   - Click Delete
   - Confirm deletion
   - Verify oa.tmtctech.ai still works after deletion

3. ENTRA APP REGISTRATION CLEANUP
   - Go to Entra ID → App registrations
   - Find the old "Options Analyzer" SPA registration
   - Click Deactivate (or Delete if you prefer)
   - In the BFF registration ("Options Trade Analyzer - BFF"):
     - Keep: https://127.0.0.1:8000/api/v1/auth/entra/callback (dev)
     - Keep: https://oa.tmtctech.ai/api/v1/auth/entra/callback (prod)
     - Remove: https://localhost:5173/api/v1/auth/entra/callback
       (no longer needed — dev callback goes through 127.0.0.1:8000 now
        since we can test unified serving locally)

4. VERIFY PRODUCTION
   - Navigate to https://oa.tmtctech.ai
   - Login with Microsoft → should authenticate and show dashboard
   - Test Schwab connect
   - Test all nav pages

=== END MANUAL STEPS ===
```

---

## Commit

```
OTA-475 chore: deprecate SWA — remove config, update docs, clean references
```

After commit, transition OTA-475 to IN REVIEW (transition ID: 41).
