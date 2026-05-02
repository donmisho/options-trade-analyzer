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
---

# OTA-518 · Decouple commit from production deploy

**Jira:** [OTA-518](https://tmtctech-team.atlassian.net/browse/OTA-518)
**Feature grouping:** OTA-511 (Deploy & Environment Operations)
**Sessions:** Single session. Multiple phases with hard stops between them.

---

## Starting context — ALWAYS

```powershell
cd "C:\Users\DonMishory\OneDrive - jmholistic.com\VS Code Projects\Options Analyzer\options-analyzer"
.\venv\Scripts\activate
cat CLAUDE.md
```

Report the CLAUDE.md last-modified date so we confirm you're reading the current version.

---

## Phase 0 — Discovery (read-only)

Before any edits, enumerate and characterize the current GitHub Actions workflow state.

```powershell
ls .github/workflows/
```

For each `.yml` file found, read it and report:

1. **Filename**
2. **Triggers** — what events fire this workflow (push to main, workflow_dispatch, schedule, etc.)
3. **What it does** — build steps, deploy steps, target resources
4. **Which App Service it deploys to** (if any)
5. **Any secrets/env it depends on**

Report the full list before proceeding. Specifically flag:

- The workflow that currently auto-deploys to `options-analyzer-api` on push to main. This is the one we're splitting.
- Any SWA workflows (`azure-static-web-apps-*.yml`) — these are already deprecated per OTA-475 but may still exist; confirm if they're still active.
- Any other workflows (scheduled jobs, PR validation, etc.) — these are out of scope but should be documented so we don't break them.

**STOP and report.** Do not create or modify files yet.

**Guardrail:** If you find more than one workflow that deploys to prod, STOP and flag. The assumption of this Story is a single auto-deploy workflow. Two means the scope is bigger than planned.

---

## Phase 1 — Create `build-on-push.yml`

Single file add. No other edits.

**Purpose:** triggered on push to main. Builds frontend + backend. Produces a versioned deployment artifact as a GitHub Actions artifact. **Does NOT deploy.**

**Structure requirements:**

- Trigger: `on.push.branches: [main]`
- Job: `build`
- Steps:
  1. `actions/checkout@v4`
  2. `actions/setup-node@v4` with appropriate Node version (match whatever the existing workflow uses)
  3. `cd web && npm ci && npm run build`
  4. Copy `web/dist/` → `static/` at repo root
  5. `actions/setup-python@v5` with appropriate Python version (match existing)
  6. `pip install -r requirements.txt` (or mirror whatever install pattern the existing workflow uses — don't invent)
  7. Package: zip `app/`, `static/`, `requirements.txt`, and any startup scripts into a single artifact
  8. `actions/upload-artifact@v4` with a stable name (e.g., `deployment-package`) so `deploy-to-prod.yml` can find it by run ID or latest-successful
- Artifact retention: 30 days (default)

**What NOT to do:**

- Do NOT include an `azure/webapps-deploy` step. This workflow does not deploy.
- Do NOT include `workflow_dispatch` — this runs on push only.
- Do NOT touch existing workflows yet.

Save as `.github/workflows/build-on-push.yml`. Show the diff.

**STOP and report.** Do not commit yet.

---

## Phase 2 — Create `deploy-to-prod.yml`

Single file add. No other edits.

**Purpose:** triggered by manual `workflow_dispatch` only. Requires a `confirm_deploy` input string equal to `"DEPLOY"` to proceed. Downloads the latest successful artifact from `build-on-push.yml` and deploys to App Service `options-analyzer-api`.

**Structure requirements:**

- Trigger: `on.workflow_dispatch` only
- Inputs:
  ```yaml
  inputs:
    confirm_deploy:
      description: 'Type DEPLOY to confirm production deployment'
      required: true
      default: ''
  ```
- First job step: confirm gate
  ```yaml
  - name: Validate confirm_deploy input
    run: |
      if [ "${{ github.event.inputs.confirm_deploy }}" != "DEPLOY" ]; then
        echo "::error::confirm_deploy must equal 'DEPLOY'. Got: '${{ github.event.inputs.confirm_deploy }}'"
        exit 1
      fi
      echo "Confirm gate passed. Proceeding to deploy."
  ```
- Subsequent steps:
  1. Download latest successful artifact from `build-on-push.yml` — use `dawidd6/action-download-artifact@v6` with `workflow: build-on-push.yml` and `workflow_conclusion: success`, or equivalent
  2. Unzip artifact
  3. `azure/login@v2` — match the auth method the existing workflow uses (likely OIDC with federated credentials, or a service principal secret — **copy the pattern exactly, do not re-architect auth in this Story**)
  4. `azure/webapps-deploy@v3` targeting `options-analyzer-api` (production slot)

**What NOT to do:**

- Do NOT deploy to a staging slot — that's Story 3 (OTA-520). This Story keeps the prod target as-is.
- Do NOT add smoke tests — Story 3.
- Do NOT add a swap step — Story 3.
- Do NOT modify the App Service configuration in any way.
- Do NOT change the auth mechanism from what the existing workflow uses.

Save as `.github/workflows/deploy-to-prod.yml`. Show the diff.

**STOP and report.** Do not commit yet.

---

## Phase 3 — First commit: add the two new workflows

Commit only the two new files. The old workflow still exists at this point and will still auto-deploy this commit. That is **expected and harmless** — we're adding new workflows alongside, not yet disabling the old one.

```powershell
git status
git add .github/workflows/build-on-push.yml .github/workflows/deploy-to-prod.yml
git diff --cached
```

Confirm the diff shows only the two new files. If anything else is staged, report and stop.

Commit message:

```
OTA-518 feat: add build-on-push and deploy-to-prod workflows

Introduces the split workflow pattern:
- build-on-push.yml: builds on every push to main, publishes artifact,
  does not deploy
- deploy-to-prod.yml: workflow_dispatch only, requires confirm_deploy
  input to equal "DEPLOY", downloads latest build artifact and deploys
  to App Service options-analyzer-api

Old monolithic workflow still active in this commit — will be removed
in the follow-up commit within the same Story. This commit is expected
to trigger the existing auto-deploy one last time (as normal).

Part of OTA-518.
```

Push. Report:

- Commit SHA
- Confirmation that the old workflow fired on this push (visible in GitHub Actions UI)
- Confirmation that `build-on-push.yml` also ran and produced an artifact

If `build-on-push.yml` failed, STOP and report — the artifact needs to be proven working before Phase 5 removes the old fallback.

---

## Phase 4 — Manual verification (Don does this)

Before proceeding to Phase 5, Don manually verifies in the GitHub Actions UI:

1. Both new workflows appear under the Actions tab
2. `deploy-to-prod.yml` shows a "Run workflow" button with the `confirm_deploy` input field
3. The build artifact from `build-on-push.yml`'s run on Phase 3's commit is present and downloadable

Claude Code: wait for Don's confirmation before Phase 5.

**Optional but recommended:** Don triggers `deploy-to-prod.yml` manually with `confirm_deploy="WRONG"` to verify the gate rejects it. Then triggers with `confirm_deploy="DEPLOY"` to verify a successful deploy (at this point the old workflow's last auto-deploy and the new manual deploy should produce identical prod state since they deploy the same artifact). **Claude Code does not trigger either workflow — Don owns that call.**

---

## Phase 5 — Second commit: remove the old workflow

Once Don confirms Phase 4 is clean, delete the old auto-deploy workflow.

Use the filename identified in Phase 0 as "the workflow that auto-deploys to prod on push to main." Do not delete other workflows (scheduled jobs, PR validation, SWA deprecation-pending files — those are out of scope).

```powershell
git rm .github/workflows/<OLD_WORKFLOW_FILENAME>
git status
git diff --cached
```

Confirm only the one file is being deleted. If anything else is staged, report and stop.

Commit message:

```
OTA-518 feat: remove old auto-deploy workflow

Old monolithic build+deploy workflow replaced by the split pattern
added in the prior commit (build-on-push.yml + deploy-to-prod.yml).

After this commit:
- Push to main triggers build only; no auto-deploy
- Deploy to prod requires manual workflow_dispatch on deploy-to-prod.yml
  with confirm_deploy="DEPLOY"

Code & Test Complete status now accurately means "built, artifact ready,
awaiting manual deploy trigger" — not "already in prod."

Closes OTA-518.
```

Push. Report:

- Commit SHA
- Whether the old workflow fired one final time on this push (GitHub's behavior on delete-commits is not 100% deterministic; either outcome is expected and acceptable)

---

## Phase 6 — Post-commit validation (Don does this)

Don manually verifies the end state:

1. Make a trivial change (e.g., whitespace in README.md), commit, push
2. Observe in GitHub Actions:
   - `build-on-push.yml` triggers and succeeds, produces an artifact
   - No deploy workflow triggers
   - `oa.tmtctech.ai` continues serving the pre-this-commit code (confirming no auto-deploy happened)
3. Manually trigger `deploy-to-prod.yml` with `confirm_deploy="DEPLOY"` → verify deploy succeeds and the README change is now reflected at `oa.tmtctech.ai`

If any of these fail, Don reports and we diagnose before moving on to OTA-520.

---

## Out of scope (do not touch)

- Staging slot, smoke test, swap workflow → OTA-520 (Story 3)
- Dev environment → OTA-519 (Story 2)
- Documentation rewrite → OTA-521 (Story 4) — small inline CLAUDE.md note is OK; full rewrite belongs in Story 4
- Alembic → OTA-522 (Story 5)
- App Service config, Key Vault, Azure SQL, Cloudflare — none of these change in this Story
- Auth mechanism for the deploy workflow — copy whatever the existing workflow uses exactly; do not re-architect
- SWA deprecation cleanup → OTA-475 (separate Story, unrelated timing)

## Guardrails

- **Two commits, not one.** First commit adds new workflows; verify; then second commit removes the old one. Never both in one commit — too hard to diagnose if something goes wrong.
- **Do not trigger deploy-to-prod.yml from inside this session.** Don triggers it manually to verify.
- **If Phase 0 finds more than one auto-deploy workflow, STOP.** The scope assumes a single one.
- **If `build-on-push.yml` fails its first run in Phase 3, STOP.** We can't remove the old fallback until the replacement builds cleanly.
- **Do not modify the App Service configuration, scaling, or slot topology.** Those changes belong to Story 3.
- Read before edit. Every time.
- One file change per phase. No bundling.

## Sequencing after this Story

Story 3 (OTA-520) is the natural next ticket — it modifies `deploy-to-prod.yml` created here to deploy to a staging slot with smoke test + manual swap. Story 2 (OTA-519) and Story 5 (OTA-522) are independent and can run in parallel with Story 3 whenever convenient. Story 4 (OTA-521) lands last to document everything.
