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

# OTA-520 · Pre-prod regression gate — staging slot + smoke test + manual swap

**Jira:** [OTA-520](https://tmtctech-team.atlassian.net/browse/OTA-520)
**Feature grouping:** OTA-511 (Deploy & Environment Operations)
**Prerequisite:** OTA-518 (manual-trigger deploy workflow) — **must be shipped and verified in production before this Story starts.**

---

## Starting context — ALWAYS

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\activate
cat CLAUDE.md
```

Report the CLAUDE.md last-modified date. Confirm that:

- `.github/workflows/build-on-push.yml` exists (from OTA-518)
- `.github/workflows/deploy-to-prod.yml` exists (from OTA-518) and currently deploys directly to the production slot

If either is missing, STOP. OTA-518 hasn't landed yet and this Story's foundation isn't in place.

---

## Phase 0 — Discovery (read-only)

Before any change, characterize the current state of `options-analyzer-api`.

### 0.1 Azure state

```bash
az account show --output table
az webapp show --resource-group options-analyzer-rg --name options-analyzer-api --query "{name:name, location:location, sku:appServicePlanId, state:state}"
az webapp deployment slot list --resource-group options-analyzer-rg --name options-analyzer-api --output table
az webapp identity show --resource-group options-analyzer-rg --name options-analyzer-api
```

Report:

1. Confirm the active subscription matches the project. If not, STOP and flag.
2. Confirm App Service plan tier. It needs to be B1 or higher to support a deployment slot. If it's F1, STOP — this Story requires B1 (which should already be in place per the OTA-500 fix).
3. Report any existing slots. If a slot named `staging` already exists, STOP and report — we need to know if it's a leftover from earlier work or actively used.
4. Capture the **prod slot's MI principalId** and list the Key Vault role assignments it has. The staging slot will need the same set.

### 0.2 GitHub Actions state

Read `deploy-to-prod.yml` and report:

1. What deployment step it uses (`azure/webapps-deploy`, version, any slot parameter it already passes)
2. What auth mechanism (OIDC federated credentials, service principal secret, publish profile)
3. Which secrets it references

The smoke test and slot-swap workflows will reuse the same auth mechanism — do not invent a new one.

### 0.3 Key Vault state

```bash
az keyvault show --name options-analyzer --query "{name:name, location:location, rbac:properties.enableRbacAuthorization}"
az role assignment list --scope $(az keyvault show --name options-analyzer --query id -o tsv) --output table
```

Report the role assignments on the Key Vault. Confirm the prod slot's MI has `Key Vault Secrets User`. If it has something else (e.g., access policy-based, or `Contributor`), STOP and flag — we need to match the pattern exactly on the staging slot.

**STOP and report Phase 0 before proceeding.**

---

## Phase 1 — Create the staging slot (Azure infrastructure)

One focused infrastructure change. Slot creation does not affect the prod slot or its traffic — the slot starts empty and has its own hostname.

### 1.1 Create the slot

```bash
az webapp deployment slot create \
  --resource-group options-analyzer-rg \
  --name options-analyzer-api \
  --slot staging \
  --configuration-source options-analyzer-api
```

`--configuration-source` copies app settings from the prod slot as a starting point. We'll override environment-specific settings in 1.3.

Verify:

```bash
az webapp deployment slot list --resource-group options-analyzer-rg --name options-analyzer-api --output table
```

The staging slot should appear with `state=Running`. Its default hostname will be `options-analyzer-api-staging.azurewebsites.net`.

### 1.2 Enable System-Assigned Managed Identity on the slot

```bash
az webapp identity assign \
  --resource-group options-analyzer-rg \
  --name options-analyzer-api \
  --slot staging
```

Capture the `principalId` returned — you'll need it in 1.4.

### 1.3 Mark `ENVIRONMENT` as slot-specific

By default, app settings swap with the slot on slot swap. `ENVIRONMENT` must NOT swap — staging always stays `staging`, prod always stays `prod`, regardless of which code is in which slot.

```bash
az webapp config appsettings set \
  --resource-group options-analyzer-rg \
  --name options-analyzer-api \
  --slot staging \
  --settings ENVIRONMENT=staging \
  --slot-settings ENVIRONMENT
```

Then confirm on the prod slot:

```bash
az webapp config appsettings set \
  --resource-group options-analyzer-rg \
  --name options-analyzer-api \
  --slot-settings ENVIRONMENT
```

(Set `ENVIRONMENT=prod` on prod slot if it's not already, and mark as slot-specific there too. The `--slot-settings` flag without a value list marks the named key as sticky without changing its value.)

Verify both:

```bash
az webapp config appsettings list --resource-group options-analyzer-rg --name options-analyzer-api --slot staging --query "[?name=='ENVIRONMENT']"
az webapp config appsettings list --resource-group options-analyzer-rg --name options-analyzer-api --query "[?name=='ENVIRONMENT']"
```

Both should show `slotSetting: true`.

### 1.4 Grant Key Vault access to the staging slot's MI

Match the exact role assignment pattern from Phase 0.3. If the prod slot uses `Key Vault Secrets User`:

```bash
STAGING_PRINCIPAL_ID="<principalId from 1.2>"
KV_ID=$(az keyvault show --name options-analyzer --query id -o tsv)

az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee-object-id "$STAGING_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --scope "$KV_ID"
```

Verify the assignment:

```bash
az role assignment list --scope "$KV_ID" --assignee "$STAGING_PRINCIPAL_ID" --output table
```

### 1.5 Verify the slot responds

The slot has no code yet, so it will serve whatever the `--configuration-source` copied. Hit the slot URL to confirm routing works:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://options-analyzer-api-staging.azurewebsites.net/
```

Any 2xx or 3xx is fine; a 4xx means the slot is responding (good — it's alive but maybe without code). A 5xx or connection error means the slot isn't routing correctly — STOP and debug before proceeding.

### 1.6 Add Entra callback URI for the staging hostname

**This is a manual step in the Azure portal.** Don does this one.

Navigate to Azure Portal → Entra ID → App registrations → BFF app (client_id `f11ea8b8...`) → Authentication → Redirect URIs. Add:

```
https://options-analyzer-api-staging.azurewebsites.net/api/v1/auth/entra/callback
```

This is needed if Don wants to test full login flow against staging pre-swap. Without it, staging's smoke test still works (health check, SPA load, auth endpoint reachable) but end-to-end login would fail on staging. That's a deliberate narrowing — the full login flow is verified against prod post-swap by normal usage, and rolled back via rollback-prod.yml if broken.

Don: after adding the URI, confirm it saved and report.

**STOP and report Phase 1 complete before proceeding.**

---

## Phase 2 — Modify `deploy-to-prod.yml` to target the staging slot

OTA-518's `deploy-to-prod.yml` deploys directly to the production slot. This Story changes it to deploy to staging, run a smoke test, and then pause for manual swap.

### 2.1 Read the current file

```powershell
cat .github/workflows/deploy-to-prod.yml
```

Before editing: understand exactly what the current `azure/webapps-deploy` step looks like, because the change is minimal — add a `slot-name` parameter.

### 2.2 Edit the deploy step

Changes:

1. Add `slot-name: staging` to the `azure/webapps-deploy` step. The target App Service stays the same (`options-analyzer-api`); only the slot changes.
2. Rename the workflow (in the `name:` field at the top) from "Deploy to production" to "Deploy to staging (pre-prod gate)" so the Actions UI reflects the new behavior.
3. Update the trigger input `confirm_deploy` description to reflect staging:
   ```yaml
   inputs:
     confirm_deploy:
       description: 'Type DEPLOY to push build to staging slot for smoke test'
   ```

### 2.3 Add the smoke test step

Append a new step after the deploy step:

```yaml
- name: Smoke test staging slot
  id: smoke
  shell: bash
  run: |
    STAGING_URL="https://options-analyzer-api-staging.azurewebsites.net"
    HEALTH_STATUS=""
    # Retry loop: cold start can take 60-90 seconds on B1
    for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
      HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "$STAGING_URL/api/v1/health" || echo "000")
      if [ "$HEALTH_STATUS" = "200" ]; then
        echo "Health check passed on attempt $i"
        break
      fi
      echo "Attempt $i: health=$HEALTH_STATUS, sleeping 10s..."
      sleep 10
    done
    if [ "$HEALTH_STATUS" != "200" ]; then
      echo "::error::Health check failed after 12 attempts (~2 minutes). Final status: $HEALTH_STATUS"
      exit 1
    fi

    SPA_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$STAGING_URL/")
    if [ "$SPA_STATUS" != "200" ]; then
      echo "::error::SPA root returned $SPA_STATUS (expected 200)"
      exit 1
    fi

    # Auth endpoint reachability — a 4xx is fine (means routing works); 5xx means the app crashed
    AUTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$STAGING_URL/api/v1/auth/me")
    if [[ "$AUTH_STATUS" =~ ^5 ]]; then
      echo "::error::Auth endpoint returned 5xx ($AUTH_STATUS) — app is crashing"
      exit 1
    fi

    echo "Smoke test passed."
    echo "staging_url=$STAGING_URL" >> "$GITHUB_OUTPUT"

- name: Pause for human review
  shell: bash
  run: |
    echo "::notice::Smoke test passed. Review staging at ${{ steps.smoke.outputs.staging_url }}"
    echo "## ⏸ Staging ready for review" >> $GITHUB_STEP_SUMMARY
    echo "Build is deployed to staging and smoke tests pass." >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
    echo "**Staging URL:** ${{ steps.smoke.outputs.staging_url }}" >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
    echo "**Next steps:**" >> $GITHUB_STEP_SUMMARY
    echo "1. Verify staging manually at the URL above" >> $GITHUB_STEP_SUMMARY
    echo "2. If good, run **swap-staging-to-prod.yml** with confirm_swap=SWAP to promote" >> $GITHUB_STEP_SUMMARY
    echo "3. If bad, the bad build stays on staging (prod unaffected) — fix forward or redeploy" >> $GITHUB_STEP_SUMMARY
```

**Do NOT add an automatic swap step.** Manual swap is the entire safety property of this design.

Show the diff with `git diff .github/workflows/deploy-to-prod.yml`. STOP and report.

---

## Phase 3 — Create `swap-staging-to-prod.yml`

Single new file.

```yaml
name: Swap staging → prod
on:
  workflow_dispatch:
    inputs:
      confirm_swap:
        description: 'Type SWAP to promote staging slot to production'
        required: true
        default: ''

jobs:
  swap:
    runs-on: ubuntu-latest
    steps:
      - name: Validate confirm_swap input
        run: |
          if [ "${{ github.event.inputs.confirm_swap }}" != "SWAP" ]; then
            echo "::error::confirm_swap must equal 'SWAP'. Got: '${{ github.event.inputs.confirm_swap }}'"
            exit 1
          fi

      # Match the auth mechanism from deploy-to-prod.yml exactly.
      # Copy whatever azure/login step is already there — do not re-architect.
      - name: Azure login
        uses: azure/login@v2
        with:
          # ... exact same with: block as deploy-to-prod.yml ...

      - name: Swap staging to production
        shell: bash
        run: |
          az webapp deployment slot swap \
            --resource-group options-analyzer-rg \
            --name options-analyzer-api \
            --slot staging \
            --target-slot production

      - name: Log swap result
        shell: bash
        run: |
          echo "## ✅ Swap complete" >> $GITHUB_STEP_SUMMARY
          echo "Staging slot's code is now serving production at oa.tmtctech.ai" >> $GITHUB_STEP_SUMMARY
          echo "The previous production code is now in the staging slot." >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "If production breaks unexpectedly, run **rollback-prod.yml** with confirm_rollback=ROLLBACK to reverse." >> $GITHUB_STEP_SUMMARY
```

Save as `.github/workflows/swap-staging-to-prod.yml`. STOP and report.

---

## Phase 4 — Create `rollback-prod.yml`

Inverse of the swap workflow. Same az command — `az webapp deployment slot swap` just swaps whatever's in the two named slots. After a forward swap, running it again swaps back.

```yaml
name: Rollback production (swap back)
on:
  workflow_dispatch:
    inputs:
      confirm_rollback:
        description: 'Type ROLLBACK to revert production to the previous deploy'
        required: true
        default: ''

jobs:
  rollback:
    runs-on: ubuntu-latest
    steps:
      - name: Validate confirm_rollback input
        run: |
          if [ "${{ github.event.inputs.confirm_rollback }}" != "ROLLBACK" ]; then
            echo "::error::confirm_rollback must equal 'ROLLBACK'. Got: '${{ github.event.inputs.confirm_rollback }}'"
            exit 1
          fi

      - name: Azure login
        uses: azure/login@v2
        with:
          # ... exact same with: block as deploy-to-prod.yml ...

      - name: Swap to restore previous production
        shell: bash
        run: |
          az webapp deployment slot swap \
            --resource-group options-analyzer-rg \
            --name options-analyzer-api \
            --slot staging \
            --target-slot production

      - name: Log rollback result
        shell: bash
        run: |
          echo "## ↩️ Rollback complete" >> $GITHUB_STEP_SUMMARY
          echo "Production is serving the previous code again." >> $GITHUB_STEP_SUMMARY
          echo "The broken code is now in the staging slot for inspection." >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "**Important:** this only reverses the most recent swap. Running it twice puts the bad code back in prod." >> $GITHUB_STEP_SUMMARY
```

Save as `.github/workflows/rollback-prod.yml`. STOP and report.

---

## Phase 5 — Commit

One commit. The three file changes are a single logical unit — the staging pattern only works when all three are in place.

```powershell
git status
git add .github/workflows/deploy-to-prod.yml .github/workflows/swap-staging-to-prod.yml .github/workflows/rollback-prod.yml
git diff --cached
```

Confirm only the three workflow files are staged. If anything else is there, STOP and report.

Commit message:

```
OTA-520 feat: pre-prod staging slot with smoke test and manual swap

Modifies deploy-to-prod.yml to deploy to staging slot on
options-analyzer-api instead of production directly. Adds smoke test
loop (retry against cold-start for up to 2 minutes, check /health,
SPA root, auth endpoint) and pauses for human review.

Adds swap-staging-to-prod.yml (workflow_dispatch, confirm_swap=SWAP)
to promote staging → prod via az webapp deployment slot swap.

Adds rollback-prod.yml (workflow_dispatch, confirm_rollback=ROLLBACK)
that reverses the most recent swap — same az command, opposite effect.

Staging slot itself was provisioned via az CLI: system-assigned MI,
Key Vault Secrets User role, ENVIRONMENT=staging marked as slot-setting
(sticky on swap). Entra callback URI added for staging hostname.

Shared Azure SQL between slots is intentional — staging tests against
real data. Expand/contract migration discipline required (formalized
in OTA-522, tracked in OTA-523).

Closes OTA-520.
```

Push. Report the commit SHA.

**Do NOT trigger any deploy from within this session.** Don owns the first end-to-end verification run.

---

## Phase 6 — Manual end-to-end verification (Don does this)

Claude Code stops after Phase 5 and waits. Don runs the following and reports back:

### 6.1 Happy path

1. Trivial change to README.md, commit, push
2. `build-on-push.yml` fires, produces artifact
3. Trigger `deploy-to-prod.yml` with `confirm_deploy=DEPLOY`
4. Verify the workflow:
   - Deploys to staging slot (not prod)
   - Smoke test runs; passes; logs staging URL
   - Workflow completes successfully and pauses (no swap)
5. Open `https://options-analyzer-api-staging.azurewebsites.net/` in browser — app loads, README change visible
6. `oa.tmtctech.ai` still serves the PRE-deploy code (confirming no swap happened yet)
7. Trigger `swap-staging-to-prod.yml` with `confirm_swap=SWAP`
8. After swap completes, `oa.tmtctech.ai` now serves the NEW code with the README change
9. `options-analyzer-api-staging.azurewebsites.net` now serves the PREVIOUS code (because the swap moved prod's old code into the staging slot)

### 6.2 Rollback path

10. Trigger `rollback-prod.yml` with `confirm_rollback=ROLLBACK`
11. `oa.tmtctech.ai` reverts to the pre-step-7 code (no README change)
12. The staging slot now has the "new" code again

### 6.3 Confirm gates

13. Trigger `deploy-to-prod.yml` with `confirm_deploy=WRONG` — workflow aborts with error
14. Trigger `swap-staging-to-prod.yml` with `confirm_swap=WRONG` — workflow aborts with error
15. Trigger `rollback-prod.yml` with `confirm_rollback=WRONG` — workflow aborts with error

### 6.4 Smoke test failure path (optional but valuable)

16. Make a deliberately broken change (e.g., break an import in `app/main.py`), commit, push
17. Trigger `deploy-to-prod.yml` with `confirm_deploy=DEPLOY`
18. Deploy lands on staging; smoke test fails (health check returns 5xx or times out)
19. Workflow fails. Staging slot holds the broken code. **Prod unaffected — oa.tmtctech.ai still serves good code.**
20. Revert the broken commit, push, build runs, trigger deploy-to-prod again, smoke passes, swap, verify

If all 20 checks pass, OTA-520 is green. Report results in the Jira ticket comments.

---

## Out of scope

- Custom staging hostname (`oa-staging.tmtctech.ai`) — defer to a small follow-up Story if useful. Default `azurewebsites.net` hostname suffices.
- Auto-swap on smoke pass — deliberately rejected. Human-in-the-loop is the safety property.
- Separate staging Azure SQL — intentionally shared.
- Auto-rollback on post-swap failure detection — not needed; manual rollback workflow covers it.
- Alembic migration integration in the workflow — OTA-522 handles that.
- Documentation rewrite for CLAUDE.md and architecture-plan.md — OTA-521 owns the full rewrite.
- Any changes to Cloudflare, Entra beyond the one redirect URI in Phase 1.6, Schwab, or Azure SQL.

## Guardrails

- **Azure infrastructure phase (Phase 1) is atomic.** If any step fails, STOP and report — do not try to recover by adding new commands. Cleanup is manual.
- **Do NOT trigger any deploy-to-prod workflow from within this session.** Don verifies end-to-end.
- **Do NOT modify `build-on-push.yml`.** It's stable from OTA-518.
- **Do NOT change the auth mechanism on the deploy workflow.** Copy what OTA-518's workflow uses exactly.
- **Do NOT create migrations or touch Azure SQL.** Shared-SQL is intentional for this Story.
- **Do NOT add a custom domain binding to the staging slot.** Use the default hostname.
- **Do NOT mark any app setting other than `ENVIRONMENT` as slot-specific without explicit discussion.** App settings that swap with the slot are the default behavior and we want that for everything else.
- **Read before edit. Every time.**
- **If Phase 0 surfaces an existing `staging` slot, STOP.** It could be leftover configuration from unrelated work and deleting it blindly is destructive.
- **If Phase 0 shows the App Service plan is F1, STOP.** Slots require B1 or higher. OTA-500 should have already moved us to B1, but verify.

## What Claude Code hands off to Don

After Phase 5 commit:

1. Summary of the Azure changes made (staging slot created, MI assigned, Key Vault role granted, slot settings marked sticky)
2. Confirmation of the three workflow files added/modified
3. The Entra redirect URI that Don needs to add manually (Phase 1.6)
4. A reminder that Don runs the Phase 6 verification — Claude Code does not

## Sequencing after this Story

- OTA-519 (dev environment) and OTA-522 (Alembic) can run in parallel
- OTA-521 (docs rewrite) runs last, after OTA-518 / OTA-519 / OTA-520 / OTA-522 all land
- OTA-523 (Database Contract Actions) becomes active the moment the first expand/contract Alembic migration ships under OTA-522
