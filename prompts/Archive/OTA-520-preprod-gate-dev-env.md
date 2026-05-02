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
  - Bash(curl.exe:*)
  - Bash(git:*)
---

# OTA-520 · Pre-prod gate via dev environment — smoke test + rollback workflow

**Jira:** [OTA-520](https://tmtctech-team.atlassian.net/browse/OTA-520)
**Feature grouping:** OTA-511 (Deploy & Environment Operations)
**Prerequisites:** OTA-518 (manual-trigger deploy workflows) — shipped. OTA-519 (dev environment + `deploy-to-dev.yml`) — shipped.

---

## Design context (must read)

This Story replaces the originally-planned slot-swap design (which required upgrading from B1 to S1 at +$44/mo). Path 2 was chosen instead: use the dev environment as the pre-prod gate.

What this Story builds:

1. **Smoke test** appended to `deploy-to-dev.yml` — fails fast if the deployed artifact is broken
2. **`rollback-prod.yml`** workflow — re-deploys a previous successful build artifact to prod when prod goes bad
3. **Inline doc note** in CLAUDE.md describing the deploy flow and rollback RTO tradeoff (full doc rewrite is OTA-521)

What this Story does NOT change:

- `build-on-push.yml` (stable from OTA-518)
- `deploy-to-prod.yml` (stable from OTA-518)
- Azure resources (no new infrastructure)

The pre-prod gate is enforced by social contract: developer always deploys to dev first, verifies in browser at `oa-dev.tmtctech.ai`, then triggers prod deploy. There is no automated check preventing prod deploy without prior dev deploy — that automation would be more complexity than the gate is worth at solo-dev scale.

---

## Starting context — ALWAYS

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\activate
cat CLAUDE.md
```

Report the CLAUDE.md last-modified date. Confirm all three of these workflows exist (shipped by OTA-518 and OTA-519):

```powershell
ls .github/workflows/build-on-push.yml
ls .github/workflows/deploy-to-prod.yml
ls .github/workflows/deploy-to-dev.yml
```

If any are missing, STOP — prerequisites haven't landed.

---

## Phase 0 — Discovery (read-only)

Before any edits, characterize the workflows and endpoints we'll be touching.

### 0.1 Read the existing workflows

```powershell
cat .github/workflows/deploy-to-dev.yml
cat .github/workflows/deploy-to-prod.yml
cat .github/workflows/build-on-push.yml
```

Report:

1. The exact `azure/login` block from `deploy-to-prod.yml` — `rollback-prod.yml` will copy it verbatim
2. The exact `azure/webapps-deploy` block from `deploy-to-prod.yml` — `rollback-prod.yml` will copy and adapt it
3. The artifact name used in `build-on-push.yml`'s `actions/upload-artifact` step
4. Whether `deploy-to-prod.yml` uses `dawidd6/action-download-artifact` or some other artifact-fetcher — `rollback-prod.yml` will use the same pattern, just with a different `run_id` source

### 0.2 Verify the smoke-test endpoints exist on dev

```bash
curl.exe -s -o /dev/null -w "%{http_code}\n" https://oa-dev.tmtctech.ai/api/v1/health
curl.exe -s -o /dev/null -w "%{http_code}\n" https://oa-dev.tmtctech.ai/
curl.exe -s -o /dev/null -w "%{http_code}\n" https://oa-dev.tmtctech.ai/api/v1/auth/me
```

Report each response code. Expected:

- `/api/v1/health` → `200` (per project memory: keep-alive Worker hits this; it's the canonical health endpoint)
- `/` → `200` (SPA index)
- `/api/v1/auth/me` → `401` or `403` (no session cookie present — but routing reaches the endpoint, which is the proof we want)

If `/api/v1/health` returns anything other than 200, STOP and report. The smoke test design assumes that endpoint is the canonical liveness check; if it's broken, the smoke test is meaningless.

If `/api/v1/auth/me` returns `5xx`, STOP — that means dev's auth pathway is itself broken, which is a different problem to solve before this Story can ship.

If any endpoint returns `404`, the path may have changed since the prompt was written. Report the actual paths in use and we'll adjust the smoke test accordingly.

**STOP and report Phase 0.**

---

## Phase 1 — Add smoke test to `deploy-to-dev.yml`

Open `deploy-to-dev.yml` and append a new step after the existing `azure/webapps-deploy` step. Do NOT change anything that's already in the file.

```yaml
- name: Smoke test dev deploy
  id: smoke
  shell: bash
  run: |
    DEV_URL="https://oa-dev.tmtctech.ai"
    HEALTH_STATUS=""
    # Retry loop: B1 cold start can take 60-90 seconds after deploy
    for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
      HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "$DEV_URL/api/v1/health" || echo "000")
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

    SPA_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$DEV_URL/")
    if [ "$SPA_STATUS" != "200" ]; then
      echo "::error::SPA root returned $SPA_STATUS (expected 200)"
      exit 1
    fi

    # Auth endpoint reachability — non-5xx means routing works
    AUTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$DEV_URL/api/v1/auth/me")
    if [[ "$AUTH_STATUS" =~ ^5 ]]; then
      echo "::error::Auth endpoint returned 5xx ($AUTH_STATUS) — app crashed"
      exit 1
    fi

    echo "Smoke test passed."
    echo "dev_url=$DEV_URL" >> "$GITHUB_OUTPUT"

- name: Notify pre-prod ready
  shell: bash
  run: |
    echo "::notice::Smoke test passed. Verify dev manually at ${{ steps.smoke.outputs.dev_url }}"
    echo "## ✅ Dev deploy verified" >> $GITHUB_STEP_SUMMARY
    echo "Smoke tests passed. Build artifact verified on dev environment." >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
    echo "**Dev URL:** ${{ steps.smoke.outputs.dev_url }}" >> $GITHUB_STEP_SUMMARY
    echo "" >> $GITHUB_STEP_SUMMARY
    echo "**Next steps:**" >> $GITHUB_STEP_SUMMARY
    echo "1. Verify dev manually in browser at the URL above" >> $GITHUB_STEP_SUMMARY
    echo "2. If good, run **deploy-to-prod.yml** with confirm_deploy=DEPLOY to ship to production" >> $GITHUB_STEP_SUMMARY
    echo "3. If bad, the bad build stays on dev (prod unaffected) — fix forward or roll back dev with deploy-to-dev.yml" >> $GITHUB_STEP_SUMMARY
```

Show the diff:

```powershell
git diff .github/workflows/deploy-to-dev.yml
```

The diff should show only the two new appended steps. No existing lines modified.

**STOP and report.**

---

## Phase 2 — Create `rollback-prod.yml`

New file. Re-uses `deploy-to-prod.yml`'s deploy mechanism but with a different artifact source: instead of "latest successful build," it deploys "the build before whatever is currently in prod."

**Design decision required during this phase:** how to identify "the previous successful build."

Two options identified in the Story's Jira description:

- **Option A — auto-select N-1.** Workflow queries `build-on-push.yml`'s run history via GitHub API, filters by `conclusion=success`, sorts descending, takes the second result. Pro: fully automated rollback. Con: assumes "previous successful build" is the right rollback target, which may not be true if you've shipped two bad builds in a row.
- **Option B — operator passes `run_id`.** Workflow takes a `build_run_id` input. Operator looks up the desired run in GitHub Actions UI and pastes its ID. Pro: explicit, never wrong about which artifact gets deployed. Con: one extra manual step during what is already a stressful moment.

**Recommendation: Option B.** Rollback is exactly the moment when you don't want clever automation guessing on your behalf. The "extra manual step" is 30 seconds of copy/paste from the Actions UI; in exchange you get certainty about exactly which artifact is going to prod. Don should confirm this choice before the prompt proceeds.

**Pause and ask Don to confirm Option A vs Option B before writing the workflow file.**

---

## Phase 3 — Write `rollback-prod.yml` (Option B implementation)

Assuming Don confirms Option B (or substitute Option A logic if he overrides):

```yaml
name: Rollback production
on:
  workflow_dispatch:
    inputs:
      confirm_rollback:
        description: 'Type ROLLBACK to deploy a previous build to production'
        required: true
        default: ''
      build_run_id:
        description: 'Run ID of the build-on-push.yml run whose artifact should be deployed (find in GitHub Actions UI)'
        required: true
        default: ''

jobs:
  rollback:
    runs-on: ubuntu-latest
    steps:
      - name: Validate confirm_rollback
        run: |
          if [ "${{ github.event.inputs.confirm_rollback }}" != "ROLLBACK" ]; then
            echo "::error::confirm_rollback must equal 'ROLLBACK'. Got: '${{ github.event.inputs.confirm_rollback }}'"
            exit 1
          fi

      - name: Validate build_run_id
        run: |
          if [ -z "${{ github.event.inputs.build_run_id }}" ]; then
            echo "::error::build_run_id is required. Find the run ID in the Actions UI under build-on-push.yml."
            exit 1
          fi

      - name: Download artifact from specified build run
        uses: dawidd6/action-download-artifact@v6
        with:
          workflow: build-on-push.yml
          run_id: ${{ github.event.inputs.build_run_id }}
          name: <ARTIFACT_NAME from Phase 0.1>
          path: ./deployment-package

      # Copy azure/login block VERBATIM from deploy-to-prod.yml
      - name: Azure login
        uses: azure/login@v2
        with:
          # ... exact same with: block as deploy-to-prod.yml ...

      - name: Deploy artifact to production
        uses: azure/webapps-deploy@v3
        with:
          app-name: options-analyzer-api
          package: ./deployment-package
          # ... any other parameters that match deploy-to-prod.yml's deploy step ...

      - name: Log rollback result
        shell: bash
        run: |
          echo "## ↩️ Rollback complete" >> $GITHUB_STEP_SUMMARY
          echo "Production now serving the artifact from build run ID: ${{ github.event.inputs.build_run_id }}" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "**Important:** No automatic verification follows this step. Manually verify oa.tmtctech.ai is healthy." >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "**RTO:** ~3-5 minutes (deploy time). For faster recovery in the future, consider upgrading to S1 + slot-swap design." >> $GITHUB_STEP_SUMMARY
```

Critical: `azure/login` block and `azure/webapps-deploy` step must be byte-identical to `deploy-to-prod.yml`'s. Copy from Phase 0.1's report. Do not invent variations.

Show the file. STOP and report.

---

## Phase 4 — Inline CLAUDE.md note

Locate the section in CLAUDE.md that describes the development/deploy workflow (likely "Development Commands" or similar — read the file first to find the right place).

Add or update a brief inline section. Suggested content:

```markdown
## Deploy flow

After OTA-520 (April 2026), production deploys go through this sequence:

1. Commit to main → `build-on-push.yml` runs automatically, publishes artifact (no deploy)
2. Trigger `deploy-to-dev.yml` manually with `confirm_deploy=DEPLOY-DEV`
3. Smoke test runs against `oa-dev.tmtctech.ai` automatically; if it fails, deploy stops
4. Verify dev manually in browser
5. Trigger `deploy-to-prod.yml` manually with `confirm_deploy=DEPLOY` to ship
6. If prod breaks: trigger `rollback-prod.yml` with `confirm_rollback=ROLLBACK` and the `build_run_id` of the previous-known-good build

**Rollback RTO: ~3-5 minutes** (artifact re-deploy time). The slot-swap design (sub-second swap) was deferred to a future revisit when paying users / Phase 5 live trading justifies the +$44/mo S1 tier upgrade.

The "always deploy to dev first" gate is a social contract, not an automated check. There is nothing structurally preventing a deploy-to-prod without a prior deploy-to-dev — discipline is on the developer. This was a deliberate scoping choice to avoid the complexity of cross-workflow gating logic at solo-dev scale.
```

This is intentionally a placeholder. The full CLAUDE.md rewrite happens in OTA-521 — this Story just adds enough inline reference so the doc isn't actively misleading until the rewrite lands.

Show the diff:

```powershell
git diff CLAUDE.md
```

**STOP and report.**

---

## Phase 5 — Commit

One commit, three files: `deploy-to-dev.yml` (modified), `rollback-prod.yml` (new), `CLAUDE.md` (modified).

```powershell
git status
git add .github/workflows/deploy-to-dev.yml .github/workflows/rollback-prod.yml CLAUDE.md
git diff --cached
```

Confirm only those three files are staged. If anything else is there, STOP and report.

Commit message:

```
OTA-520 feat: pre-prod gate via dev environment + rollback workflow

Closes the pre-prod gap from OTA-518 without requiring an Azure tier
upgrade. Path 2 design (dev-as-staging) — see OTA-520 Jira description
for design history and the slot-swap design we deferred.

Changes in this commit:

- deploy-to-dev.yml: appended smoke test step (cold-start retry loop
  against /api/v1/health, SPA root, auth endpoint reachability) and a
  pre-prod-ready notification step. Existing deploy logic untouched.

- rollback-prod.yml: new workflow_dispatch-only workflow that takes a
  build_run_id input, downloads that artifact from build-on-push.yml's
  run history, and deploys it to production. Operator picks the
  rollback target explicitly — no clever automation about "N-1
  successful build" because rollback is exactly when you don't want
  clever automation guessing.

- CLAUDE.md: inline placeholder describing the new deploy flow and
  rollback RTO. Full doc rewrite owned by OTA-521.

Rollback RTO: ~3-5 min (deploy time, not seconds like slot swap would
give). Acceptable for current scale. Revisit when paying users exist
or Phase 5 live trading approaches.

Closes OTA-520.
```

Push. Report commit SHA.

**Do NOT trigger any deploy from within this session.** Don owns the verification run.

---

## Phase 6 — Manual end-to-end verification (Don does this)

Claude Code stops after Phase 5 and waits.

### 6.1 Happy path

1. Trivial change to README.md, commit, push
2. `build-on-push.yml` runs, publishes artifact. Note its run ID — you'll use it for the rollback test in 6.4.
3. Trigger `deploy-to-dev.yml` with `confirm_deploy=DEPLOY-DEV`
4. Verify the workflow:
   - Deploy succeeds (existing OTA-519 behavior)
   - **New:** Smoke test step runs, passes within ~2 minutes (cold start may take a few retry iterations — that's expected)
   - **New:** Workflow summary shows the dev URL with verification instructions
5. Open `https://oa-dev.tmtctech.ai/` — README change visible
6. Trigger `deploy-to-prod.yml` with `confirm_deploy=DEPLOY`
7. Verify `https://oa.tmtctech.ai/` now shows the README change

### 6.2 Smoke test failure path

8. Make a deliberately broken change (e.g., add `raise Exception("intentional break")` to `app/main.py`'s startup), commit, push
9. Wait for `build-on-push.yml` to publish the broken artifact
10. Trigger `deploy-to-dev.yml` with `confirm_deploy=DEPLOY-DEV`
11. Verify:
   - Deploy step succeeds (Azure successfully receives the artifact)
   - **Smoke test fails** within ~2 minutes (12 retries × 10s)
   - Workflow ends in failed state
   - Dev (`oa-dev.tmtctech.ai`) is now broken — that's expected
   - **Prod (`oa.tmtctech.ai`) is unaffected — still serves the README change from step 7**

12. Revert the broken commit, push, let `build-on-push.yml` run, trigger `deploy-to-dev.yml` again, verify it passes, then trigger `deploy-to-prod.yml` to restore dev's working state matching prod

### 6.3 Confirm-input gates

13. Trigger `deploy-to-dev.yml` with `confirm_deploy=WRONG` — workflow aborts (existing OTA-519 behavior)
14. Trigger `rollback-prod.yml` with `confirm_rollback=WRONG` and any build_run_id — workflow aborts at the confirm gate
15. Trigger `rollback-prod.yml` with `confirm_rollback=ROLLBACK` and empty `build_run_id` — workflow aborts at the build_run_id validation step

### 6.4 Rollback path

16. With prod currently serving the latest README-change build, trigger `rollback-prod.yml` with:
   - `confirm_rollback=ROLLBACK`
   - `build_run_id=<the run ID from step 2>` (the build immediately before the current prod build)
17. Verify the workflow:
   - Downloads the artifact from the specified run
   - Deploys to prod
   - Workflow summary logs the rollback with the run ID and RTO note
18. Verify `oa.tmtctech.ai` now serves the previous README content (without the change made in step 1)
19. Re-deploy the latest artifact via `deploy-to-prod.yml` to restore prod to current state

If all 19 checks pass, OTA-520 is green. Report results in OTA-520 Jira comments.

---

## Out of scope

- Automated check preventing prod deploy without prior dev deploy — deliberately rejected as gating-by-social-contract
- Slot-swap design — deferred per OTA-520's design history
- Auto-rollback on post-deploy failure detection — manual rollback workflow covers it
- Schema rollback coordinated with code rollback — handled by OTA-522 (Alembic) + OTA-523 (Database Contract Actions) expand/contract discipline
- Monitoring/alerting on post-deploy health — separate Story if needed
- Modifying `deploy-to-prod.yml` or `build-on-push.yml` — both stable

## Guardrails

- **Do NOT modify `deploy-to-prod.yml` or `build-on-push.yml`.** They're stable from OTA-518.
- **Do NOT change the auth mechanism in `rollback-prod.yml`.** Copy `deploy-to-prod.yml`'s `azure/login` block byte-for-byte.
- **Do NOT change anything in `deploy-to-dev.yml` other than appending the two new steps.** Read the diff carefully before committing.
- **Do NOT trigger any workflow from this session.** Don owns Phase 6.
- **Do NOT skip Phase 0.2.** If `/api/v1/health` isn't returning 200 on dev right now, the smoke test is built on a broken assumption.
- **Stop at Phase 2 and confirm Option A vs Option B with Don** before writing `rollback-prod.yml`. Default to Option B unless Don overrides.
- Read before edit. One phase at a time. Report between phases.

## Sequencing after this Story

OTA-522 (Alembic) and OTA-524 (Tradier cleanup) are both independent and can run in any order. OTA-521 (docs rewrite) lands last, after OTA-522 / OTA-524 ship, and turns the inline CLAUDE.md placeholder from this Story into a proper Environments / Deploy Flow section.
