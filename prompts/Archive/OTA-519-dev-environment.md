---
allowedTools:
  - Read
  - Grep
  - Glob
  - Edit
  - Write
  - Bash(cd:*)
  - Bash(./venv/Scripts/activate*)
  - Bash(.\\venv\\Scripts\\activate*)
  - Bash(ls:*)
  - Bash(cat:*)
  - Bash(grep:*)
  - Bash(git:*)
  - Bash(az:*)
---

# OTA-519 · Dev environment on Azure

**Jira:** [OTA-519](https://tmtctech-team.atlassian.net/browse/OTA-519)
**Feature grouping:** OTA-511 (Deploy & Environment Operations)
**Prerequisite:** OTA-518 (manual-trigger deploy workflow) — shipped.

---

## Resource placement (CRITICAL — read before running)

This Story provisions resources across TWO resource groups. Get this right in Phase 0 and every subsequent az command flows correctly.

- **App Service Plan** `tmtc-plan-dev` → resource group **`tmtc-gneralpurpose-rg`** (shared TMTC infra RG). Generic name because this plan will host non-OTA TMTC dev apps over time (marketing site staging, openbb-data-platform dev, MCP experiments) on shared compute at $0 incremental per additional app.
- **App Service** `options-analyzer-api-dev` → resource group **`options-analyzer-rg`** (existing OTA RG). Stays in OTA's RG for project-scoped discoverability and cost grouping.
- Azure supports apps and plans in different RGs. The app references the plan by full resource ID.

**Spelling note:** the shared RG name is `tmtc-gneralpurpose-rg` — that's the actual spelling, including the typo. Do NOT "correct" it to `tmtc-generalpurpose-rg` — that RG does not exist.

## Starting context — ALWAYS

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\activate
cat CLAUDE.md
```

Report the CLAUDE.md last-modified date. Confirm that `.github/workflows/build-on-push.yml` and `.github/workflows/deploy-to-prod.yml` exist (shipped by OTA-518). If either is missing, STOP.

---

## Phase 0 — Discovery (read-only)

### 0.1 Subscription sanity

```bash
az account show --output table
```

Confirm the active subscription matches the OTA project. If not, STOP and flag.

### 0.2 Verify the shared RG exists and check its tags

```bash
az group show --name tmtc-gneralpurpose-rg --query "{name:name, location:location, tags:tags}"
```

If this returns "not found," STOP — the RG needs to exist before the plan can land there, and creating it is out of scope for this Story. Don will handle.

Report the RG's tags. If it has a consistent tagging pattern, note it — the plan we create should follow that pattern where relevant.

### 0.3 Production App Service + plan discovery

```bash
az webapp show \
  --resource-group options-analyzer-rg \
  --name options-analyzer-api \
  --query "{name:name, plan:appServicePlanId, kind:kind, runtime:siteConfig.linuxFxVersion, alwaysOn:siteConfig.alwaysOn, startup:siteConfig.appCommandLine, httpsOnly:httpsOnly}"
```

Capture for mirroring in Phases 1–2:

- Plan resource ID
- Runtime stack (e.g., `PYTHON|3.13`)
- Startup command
- Always On — should be true; flag if not
- httpsOnly — should be true; flag if not

Then plan details:

```bash
PROD_PLAN_ID=$(az webapp show --resource-group options-analyzer-rg --name options-analyzer-api --query appServicePlanId -o tsv)
az appservice plan show --ids "$PROD_PLAN_ID" --query "{name:name, sku:sku.name, tier:sku.tier, reserved:reserved, location:location}"
```

Report:

- Plan name (per project memory: `ASP-optionsanalyzerrg-94e9`)
- SKU (should be B1)
- `reserved: true` = Linux; `false` = Windows. The new plan must match.
- Region — the new plan must match.

### 0.4 Prod MI + Key Vault pattern

```bash
PROD_PRINCIPAL_ID=$(az webapp identity show --resource-group options-analyzer-rg --name options-analyzer-api --query principalId -o tsv)
KV_ID=$(az keyvault show --name options-analyzer --query id -o tsv)

az role assignment list --scope "$KV_ID" --assignee "$PROD_PRINCIPAL_ID" --output table
```

Confirm prod's MI has `Key Vault Secrets User`. Whatever role(s) it has, dev's MI will get the same set — no more, no less.

### 0.5 Prod app settings (for mirroring)

```bash
az webapp config appsettings list \
  --resource-group options-analyzer-rg \
  --name options-analyzer-api \
  --output json
```

Report the list (names only — redact any values that look like secrets). Flag environment-specific settings (`ENVIRONMENT=prod`, anything with `oa.tmtctech.ai`).

### 0.6 Entra BFF app registration (manual — Don)

`az cli` can't reliably introspect Entra without Graph permissions. Handoff:

> **Don:** Azure Portal → Entra ID → App registrations → the BFF app (client_id starts with `f11ea8b8`) → Authentication. Report the current redirect URIs. Expected: `https://127.0.0.1:8000/api/v1/auth/entra/callback` (local) and `https://oa.tmtctech.ai/api/v1/auth/entra/callback` (prod).

**STOP and report Phase 0 before proceeding.**

---

## Phase 1 — Create the shared dev App Service Plan in `tmtc-gneralpurpose-rg`

```bash
az appservice plan create \
  --name tmtc-plan-dev \
  --resource-group tmtc-gneralpurpose-rg \
  --sku B1 \
  --is-linux \
  --location "<match prod region from Phase 0.3>" \
  --tags project=tmtctech-general environment=dev component=hosting owner=don
```

(Use `--is-linux` only if Phase 0.3 showed `reserved: true`. For Windows, omit.)

**Critical:** the `--resource-group` is `tmtc-gneralpurpose-rg` (typo intentional), NOT `options-analyzer-rg`. Double-check before running.

Verify:

```bash
az appservice plan show \
  --name tmtc-plan-dev \
  --resource-group tmtc-gneralpurpose-rg \
  --query "{name:name, sku:sku.name, location:location, reserved:reserved, tags:tags}"
```

Confirm SKU=B1, all four tags present, region matches prod, `reserved` matches prod.

Capture plan's full resource ID for Phase 2:

```bash
DEV_PLAN_ID=$(az appservice plan show --name tmtc-plan-dev --resource-group tmtc-gneralpurpose-rg --query id -o tsv)
echo "$DEV_PLAN_ID"
```

Format:
`/subscriptions/<sub>/resourceGroups/tmtc-gneralpurpose-rg/providers/Microsoft.Web/serverfarms/tmtc-plan-dev`

**STOP and report.**

---

## Phase 2 — Create the dev App Service in `options-analyzer-rg`

App lives in OTA's RG, references plan by full resource ID since plan is in a different RG.

```bash
az webapp create \
  --name options-analyzer-api-dev \
  --resource-group options-analyzer-rg \
  --plan "$DEV_PLAN_ID" \
  --runtime "<match Phase 0.3 runtime, e.g., PYTHON:3.13>" \
  --tags project=options-trade-analyzer environment=dev component=api owner=don
```

Note the two RGs: `--resource-group options-analyzer-rg` (where the app lives) and the plan ID (referencing `tmtc-gneralpurpose-rg` where the plan lives).

Apply site config matching prod:

```bash
az webapp config set \
  --resource-group options-analyzer-rg \
  --name options-analyzer-api-dev \
  --startup-file "<exact startup command from Phase 0.3>" \
  --always-on true

az webapp update \
  --resource-group options-analyzer-rg \
  --name options-analyzer-api-dev \
  --https-only true
```

Verify:

```bash
az webapp show \
  --resource-group options-analyzer-rg \
  --name options-analyzer-api-dev \
  --query "{name:name, plan:appServicePlanId, runtime:siteConfig.linuxFxVersion, alwaysOn:siteConfig.alwaysOn, startup:siteConfig.appCommandLine, httpsOnly:httpsOnly, state:state}"
```

Every field should match prod (except `name` and `plan`). `plan` should point at `tmtc-plan-dev` in `tmtc-gneralpurpose-rg`. `state` should be `Running`.

Routability check:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://options-analyzer-api-dev.azurewebsites.net/
```

Any response code is fine. Connection error = broken.

**STOP and report.**

---

## Phase 3 — Enable MI and grant Key Vault access

```bash
az webapp identity assign \
  --resource-group options-analyzer-rg \
  --name options-analyzer-api-dev
```

Capture the `principalId`.

```bash
DEV_PRINCIPAL_ID=<paste principalId from previous command>
KV_ID=$(az keyvault show --name options-analyzer --query id -o tsv)

az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee-object-id "$DEV_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --scope "$KV_ID"
```

If Phase 0.4 showed additional prod roles, replicate them. Do NOT grant elevated roles — stick to prod's minimum.

Verify:

```bash
az role assignment list --scope "$KV_ID" --assignee "$DEV_PRINCIPAL_ID" --output table
```

Same role set as prod.

**STOP and report.**

---

## Phase 4 — Apply app settings

Use Phase 0.5's prod settings as baseline. Copy non-environment-specific verbatim; override environment-specific.

**Override or set fresh:**

- `ENVIRONMENT=dev`
- Anything Phase 0.5 flagged with `oa.tmtctech.ai`, `prod`, or env-specific values

**Copy verbatim from prod:**

- `AZURE_KEY_VAULT_URI` (shared vault)
- Azure SQL connection config (shared DB)
- Provider configs, feature flags, model endpoints
- Any runtime-required settings

Do NOT include anything you can't explain. Flag unclear settings before applying.

```bash
az webapp config appsettings set \
  --resource-group options-analyzer-rg \
  --name options-analyzer-api-dev \
  --settings \
    ENVIRONMENT=dev \
    <OTHER_SETTING_1>="value" \
    <OTHER_SETTING_2>="value"
```

Verify:

```bash
az webapp config appsettings list \
  --resource-group options-analyzer-rg \
  --name options-analyzer-api-dev \
  --output json
```

Same keys as prod with env overrides.

**STOP and report.**

---

## Phase 5 — DNS (manual — Don)

Claude Code can't edit Cloudflare. Handoff:

> **Don: Cloudflare dashboard for `tmtctech.ai`:**
>
> 1. DNS → Records → Add record
> 2. Type: `CNAME`
> 3. Name: `oa-dev`
> 4. Target: `options-analyzer-api-dev.azurewebsites.net`
> 5. Proxy status: **Proxied** (orange cloud) — match prod
> 6. TTL: Auto
> 7. Save
>
> Confirm propagation:
>
> ```
> nslookup oa-dev.tmtctech.ai
> ```
>
> Cloudflare proxy range in the result. 1–2 min propagation. Don't proceed to Phase 6 until this resolves.
>
> Report back when done.

**STOP and wait.**

---

## Phase 6 — Bind custom domain + managed cert

Only run after Phase 5.

### 6.1 Add hostname

```bash
az webapp config hostname add \
  --webapp-name options-analyzer-api-dev \
  --resource-group options-analyzer-rg \
  --hostname oa-dev.tmtctech.ai
```

If this errors with a domain-ownership failure, Azure may want an `asuid.oa-dev` TXT record. STOP and report — Don adds it in Cloudflare, then retry.

### 6.2 Create managed certificate

```bash
az webapp config ssl create \
  --resource-group options-analyzer-rg \
  --name options-analyzer-api-dev \
  --hostname oa-dev.tmtctech.ai
```

Provisioning 2–5 minutes. Failures often trace to Cloudflare proxy interfering with ACME challenge. STOP and report — Don may need to temporarily set Cloudflare to "DNS Only" (gray cloud), retry, then flip back to Proxied after cert issues.

### 6.3 Bind cert

```bash
CERT_THUMBPRINT=$(az webapp config ssl list \
  --resource-group options-analyzer-rg \
  --query "[?subjectName=='oa-dev.tmtctech.ai'].thumbprint" -o tsv)

az webapp config ssl bind \
  --resource-group options-analyzer-rg \
  --name options-analyzer-api-dev \
  --certificate-thumbprint "$CERT_THUMBPRINT" \
  --ssl-type SNI
```

### 6.4 Verify HTTPS

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://oa-dev.tmtctech.ai/
```

Any response = cert working. Cert error or connection refused = binding failed; STOP.

**STOP and report Phase 6 complete.**

---

## Phase 7 — Entra redirect URI (manual — Don)

> **Don: Azure Portal → Entra ID → App registrations → BFF app → Authentication:**
>
> 1. "Redirect URIs" (Web platform) → **Add URI**
> 2. Enter: `https://oa-dev.tmtctech.ai/api/v1/auth/entra/callback`
> 3. Save
>
> Verify it appears in the list. Report back.

**STOP and wait.**

---

## Phase 8 — Create `deploy-to-dev.yml`

Model on `deploy-to-prod.yml`. Only three differences:

1. `confirm_deploy` check is `"DEPLOY-DEV"` (not `"DEPLOY"`)
2. `azure/webapps-deploy` targets `options-analyzer-api-dev` in resource group `options-analyzer-rg` (same RG pattern as prod — the plan's different RG doesn't affect the deploy step)
3. Workflow name is "Deploy to dev"

**Do NOT:**

- Add smoke test — OTA-520
- Add rollback — OTA-520
- Modify `deploy-to-prod.yml` or `build-on-push.yml` — stable
- Invent new auth — copy `deploy-to-prod.yml`'s `azure/login` block exactly

Read prod workflow first:

```powershell
cat .github/workflows/deploy-to-prod.yml
```

Write `deploy-to-dev.yml`. Show diff against `deploy-to-prod.yml` — only the three expected differences.

**STOP and report.**

---

## Phase 9 — Commit

One commit, one file.

```powershell
git status
git add .github/workflows/deploy-to-dev.yml
git diff --cached
```

Only `deploy-to-dev.yml` staged. If anything else is there, STOP.

Commit message:

```
OTA-519 feat: dev environment on Azure + deploy-to-dev workflow

Azure resources provisioned via az CLI (Phases 1-6):

- App Service plan tmtc-plan-dev in tmtc-gneralpurpose-rg (B1 Linux,
  shared TMTC dev compute for future multi-app amortization)
- App Service options-analyzer-api-dev in options-analyzer-rg,
  references tmtc-plan-dev via full resource ID
- System-Assigned MI on dev app
- Key Vault Secrets User role granted to dev MI on options-analyzer
  vault (mirrors prod's credential topology exactly)
- App settings mirror prod with ENVIRONMENT=dev override; shared Azure
  SQL and shared Key Vault (intentional for current scale)
- Cloudflare CNAME oa-dev.tmtctech.ai -> App Service default hostname,
  proxied
- App Service managed certificate for oa-dev.tmtctech.ai
- Entra redirect URI added for BFF app:
  https://oa-dev.tmtctech.ai/api/v1/auth/entra/callback

This commit adds the workflow:

- deploy-to-dev.yml: workflow_dispatch only, confirm_deploy="DEPLOY-DEV",
  downloads latest build-on-push artifact, deploys to
  options-analyzer-api-dev

Serves as pre-prod gate under Path 2 (dev-as-staging). Smoke test
and rollback workflow are separate Story OTA-520.

Plan lives in shared TMTC infrastructure RG (tmtc-gneralpurpose-rg) to
amortize $13/mo across future TMTC dev apps at $0 incremental each.

Closes OTA-519.
```

Push. Report commit SHA.

---

## Phase 10 — Manual end-to-end verification (Don does this)

1. Trivial README change, commit, push
2. `build-on-push.yml` runs, artifact produced
3. GitHub Actions UI → `deploy-to-dev.yml` with `confirm_deploy=DEPLOY-DEV`
4. Verify:
   - Deploy succeeds, targets `options-analyzer-api-dev`
   - `https://oa-dev.tmtctech.ai/` serves SPA with README change
5. Browser login flow on dev URL:
   - Entra login completes
   - Callback to `oa-dev.tmtctech.ai/api/v1/auth/entra/callback` succeeds
   - `/auth/me` returns user info
6. Run a read-only scan against a symbol — confirms Schwab + KV + SQL work on dev
7. Confirm `oa.tmtctech.ai` (prod) continues serving pre-step-1 code — unaffected

Confirm gate:

8. `deploy-to-dev.yml` with `confirm_deploy=WRONG` — workflow aborts

Report in Jira OTA-519 comments.

---

## Out of scope

- Smoke test on `deploy-to-dev.yml` — OTA-520
- Rollback workflow — OTA-520
- Separate dev Azure SQL — shared intentionally
- Separate dev Schwab tokens — dev piggy-backs on prod's from KV
- Separate dev Entra app — dev shares BFF app with added redirect URI
- Auto-deploy on `develop` — rejected
- Migration of existing resources into `tmtc-gneralpurpose-rg` — new resources only
- Update to `azure-naming-conventions.md` — OTA-521 handles

## Guardrails

- **Resource group is the main footgun.** Plan lives in `tmtc-gneralpurpose-rg`. App lives in `options-analyzer-rg`. Every `az` command names the correct RG.
- **Do NOT touch prod.** Every az command should name `options-analyzer-api-dev`, `tmtc-plan-dev`, or their RGs. If you catch yourself typing `options-analyzer-api` (no `-dev` suffix) or the prod plan name, STOP.
- **Do NOT create a new Key Vault, Azure SQL, or Entra app.** Shared with prod.
- **Do NOT copy app settings you can't explain.** Flag unclear settings.
- **Do NOT modify existing workflows.**
- **Do NOT skip Phase 0.** Mirroring prod depends on knowing prod's config.
- **Do NOT run `deploy-to-dev.yml` from this session.** Don verifies.
- **Do NOT "correct" the RG name typo.** `tmtc-gneralpurpose-rg` is the actual name.
- **If any az command errors, STOP.** Understand first.
- Read before edit. One phase at a time. Report between phases.

## Sequencing after this Story

OTA-520 (smoke test + rollback) is next. OTA-522 (Alembic) can run in parallel. OTA-521 (docs rewrite) lands after all three — will add `tmtc-plan-dev` and the shared-RG pattern to `azure-naming-conventions.md`.
