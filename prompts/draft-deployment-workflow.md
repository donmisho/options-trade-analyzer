# Deployment Workflow

**Last Updated:** 2026-05-06 UTC
**Governing Story:** OTA-583 (Documentation Governance — Project)
**Initial creation Subtask:** OTA-588

---

OTA's deployment workflow — slot-swap deploy gate, GitHub Actions confirmation tokens, dev environment topology, rollback procedure. Also documents the OTA-specific implementation of the cross-project Deployment Recording rule defined in profile-level `build-execution.md` Part 4.

Read this before deploying anything to a non-local environment, before authoring any change to a deploy workflow YAML, or before changing the Change Log feature.

---

## Deploy model

The OTA deploy model is **manual-trigger with pre-prod slot gate**. Pushing to `main` builds an artifact but does not deploy. Deploys are explicit, tokenized, and gated by a smoke test against the staging slot.

| Step | Trigger | Workflow | Confirmation Token | Effect |
|---|---|---|---|---|
| 1 — Build | `git push origin main` | `build-on-push.yml` | none | Builds and uploads artifact only. No deploy. |
| 2 — Deploy to staging slot | Manual via GitHub Actions UI | `deploy-to-prod.yml` | `confirm_deploy=DEPLOY` | Deploys artifact to `staging` slot, runs smoke test, pauses |
| 3 — Promote staging to prod | Manual via GitHub Actions UI | `swap-staging-to-prod.yml` | `confirm_swap=SWAP` | Slot swap: staging becomes prod, prod becomes staging |
| 4 — Emergency rollback | Manual via GitHub Actions UI | `rollback-prod.yml` | `confirm_rollback=ROLLBACK` | Re-swap (or redeploy a prior `build_run_id` artifact) |

Dev deploy uses `deploy-to-dev.yml` with `confirm_deploy=DEPLOY-DEV` and no slot. Dev is a single-slot environment; if dev breaks, it gets fixed forward, not rolled back.

## Single-change discipline

The blast radius of a deploy is small because the staging slot catches broken deploys before the swap, but **single-change deploys are still the rule**. Every deploy ships one logical change set. If multiple in-flight Stories are all in Code & Test Complete, deploy them one at a time unless they are interdependent and were specifically planned to ship together.

## Database migration discipline

The staging and prod slots **share the same Azure SQL database**. This forces **expand/contract** discipline on every schema change:

- Migrations must be additive only — new tables, new columns, new indexes
- Column drops and breaking schema changes are deferred to a follow-up after prod has been stable on the new code
- Deferred schema cleanups are tracked perpetually under **OTA-523 (Database Contract Actions)**
- Alembic is the migration tool; every schema change ships with an Alembic migration

If a Story requires a breaking schema change, the work splits across two deploys: one to add the new shape, one (later) to remove the old shape after the new code is stable.

## Rollback

Two rollback paths:

1. **Re-swap.** If the swap just happened and the issue is caught immediately, run `rollback-prod.yml` with `confirm_rollback=ROLLBACK` — this re-swaps, putting the prior version back in prod.
2. **Redeploy a prior build.** If the issue surfaces after additional work has staged, re-deploy a known-good artifact by passing its `build_run_id` to `rollback-prod.yml`.

Dev does not roll back. Dev breaks → fix forward.

---

## Deployment Recording (OTA implementation)

This section implements the cross-project rule defined in profile-level `build-execution.md` Part 4: every successful non-local deployment must produce a deploy-log record, queryable in-app at `/changelog`.

The full initial-build scope lives in the OTA Change Log Story (delivered as `OTA-changelog-page-story.md`; sits under OTA-511 Deploy & Environment Operations). This document captures the OTA-specific implementation contract that the Story will satisfy.

### Schema

Table `deploy_log`:

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | int | no | PK, autoincrement |
| `build_id` | varchar(64) | no | GitHub Actions run ID |
| `environment` | varchar(16) | no | "dev" or "prod" |
| `deployed_at` | datetime | no | UTC |
| `commit_sha` | varchar(40) | no | full SHA |
| `ticket_keys` | varchar(500) | no | comma-separated, e.g. "OTA-561,OTA-562" |
| `notes` | varchar(500) | yes | optional free-text |
| `created_at` | datetime | no | default now() |

Index on `deployed_at desc`. All schema changes via Alembic, additive only.

### Endpoints

- `POST /api/v1/changelog/record` — write endpoint
   - Auth: shared deploy token, validated against header `X-Deploy-Token`
   - Body: `{ build_id, environment, commit_sha, ticket_keys[], notes? }`
   - Response: `201 Created` with the row's `id`
- `GET /api/v1/changelog?limit=50&environment=prod` — read endpoint
   - Auth: standard BFF session cookie
   - Returns reverse-chronological list, default limit 50, max 200

### UI

- Route `/changelog`
- Component `ChangeLogPage.jsx` — table view, columns: Deployed At · Environment · Build ID · Commit · Tickets · Notes
- Nav link "Change Log" placed below "Settings" in `Layout.jsx` (peer of Settings, not sub-item)

### Deploy token

`DEPLOY_RECORDER_TOKEN` is a shared secret known to GitHub Actions and to the App Service.

- Stored in Azure Key Vault (`options-analyzer` vault, secret name `deploy-recorder-token`)
- Mirrored as a GitHub Actions secret of the same name
- Rotated annually or on personnel change
- Rotation procedure: generate new value → update Key Vault → update GitHub Actions secret → restart App Service to pick up new value → verify next deploy records correctly → no parallel-old-value period (the old value is invalidated immediately)

### Workflow updates required to satisfy the contract

- `deploy-to-dev.yml` — final step POSTs to `/api/v1/changelog/record` with `environment="dev"` after dev deploy succeeds
- `deploy-to-prod.yml` — staging deploy step does **not** record (this isn't the user-facing event)
- `swap-staging-to-prod.yml` — final step POSTs with `environment="prod"` after the swap succeeds
- `rollback-prod.yml` — adds a record with `notes="rollback to {prior_build_id}"` when the rollback completes

### Failure modes

- If the `POST /api/v1/changelog/record` call fails after a successful deploy, the deploy itself is not rolled back — but the workflow surfaces the failure visibly (red step in GitHub Actions). Don can manually insert the missing record by re-running just the recording step.
- If the App Service is down when the workflow tries to record, the record is lost. Acceptable because the GitHub Actions run history itself is the canonical event log; the Change Log page is a convenience surface.

---

## Change Log

| Date | Subtask | Change |
|---|---|---|
| 2026-05-06 UTC | OTA-588 | Initial creation. Content ported from `CLAUDE.md` (Deployment Workflow section) plus new Deployment Recording implementation scaffolding for the OTA Change Log feature. After this file lands, the corresponding section in CLAUDE.md becomes a one-paragraph pointer. The full Change Log feature build scope lives in the OTA-511 Story (`OTA-changelog-page-story.md`). |
