---
allowedTools: ["Bash", "Read", "Write", "Edit"]
---

# OTA-540 — Alembic Init + Baseline + Expand/Contract Discipline

**Wave:** 1 (T1)
**Parent:** OTA-535 (Architecture Optimization Framework v1)
**Supersedes:** OTA-522 (closes both on completion)
**Sequence label:** `05012026-1`

This Story gates every subsequent schema change in the project. Land it before any other Story that touches `database.py`.

---

## Required reading

Before any code changes:

```bash
cat claude_context/CLAUDE.md
cat claude_context/architecture-plan.md
cat claude_context/business-rules.md
cat claude_context/azure-naming-conventions.md
```

Then targeted source reads:

```bash
cat app/models/session.py     # current init_db() with metadata.create_all()
cat app/models/database.py    # current schema models
cat app/main.py               # lifespan + startup wiring
ls .github/workflows/         # CI workflow files for the migration gate step
```

---

## Relevant Context — Do Not Deviate Without Escalation

**Source: architecture-plan.md § 2 (Schema Migration Strategy)**
Rule: Alembic is the chosen migration framework. All schema changes after this Story land must be expressed as versioned Alembic revisions. `metadata.create_all()` is no longer permitted as the production schema mechanism.

**Source: architecture-plan.md § 7 (Deployment Architecture) + Pattern 7**
Rule: Staging and production slots in the App Service share the same Azure SQL database. The slot swap pattern means both slots run simultaneously for a brief window. Therefore every schema change MUST follow expand/contract discipline:
1. Expand migration adds the new column/table without breaking the old code path
2. Application is deployed and runs against the expanded schema
3. After ≥14 days of prod stability on the new code, contract migration drops the obsolete column/table

**Source: OTA-523 — Database Contract Actions (perpetual tracking Story)**
Rule: When a contract migration is deferred, log a row in OTA-523's tracking table: migration rev, table, object, deferred action, expand deploy date, earliest safe drop, status. Do NOT track deferrals anywhere else.

**Source: claude_context/CLAUDE.md (Authentication)**
Rule: All Azure SQL connections use Entra ID (Microsoft Entra) auth — never SQL auth, never connection strings with passwords. Async credentials only (`azure.identity.aio`).

**Source: OTA-526 retro / OTA-527 (in flight)**
Rule: Claude Code commits + pushes + verifies the GitHub Actions build run. Claude Code does NOT trigger any deploy workflow. Don owns deploy.

---

## Scope (8 phases — STOP gates between each)

### Phase 1 — Install Alembic, dry-run init

```bash
pip install alembic
alembic init -t async alembic
```

Show Don the generated tree, the `alembic.ini`, and the default `env.py`.

**STOP. Wait for Don's "proceed."**

---

### Phase 2 — Configure Alembic for async SQLAlchemy + Azure SQL + Entra ID

Edit `alembic/env.py`:
- Import the project's async engine factory (do NOT instantiate a second engine — reuse `app/models/session.py`'s engine builder)
- Use `azure.identity.aio.DefaultAzureCredential` for Entra ID token acquisition (matches existing app pattern)
- Configure `target_metadata = Base.metadata` from `app/models/database.py`
- Set `compare_type=True` and `compare_server_default=True` in the migration context for accurate autogenerate

Edit `alembic.ini`:
- `sqlalchemy.url` left empty (the URL is built in `env.py` from app config — do NOT hardcode a URL)
- `script_location = alembic`
- `file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s` (sortable by date)

**Show diff. STOP.**

---

### Phase 3 — Generate baseline migration

```bash
alembic revision --autogenerate -m "baseline schema matching production"
```

Open the generated revision file. **Hand-verify** every operation against `database.py`:
- Confirm every existing prod table is represented
- Confirm column types, nullability, defaults match
- Remove any `op.drop_*` operations Alembic generated speculatively (baseline must be additive only)
- Confirm no tables missing (in particular: `sessions`, `positions`, `strategies`, `agent_run_log`, `symbol_reference`, plus any others present in prod)

Also verify there are no migrations for tables that are owned by another system (e.g., the `obb_*` tables written by the OpenBB Data Platform — those must NOT be in OTA's Alembic baseline).

**Show the verified baseline file. STOP.**

---

### Phase 4 — Document the production stamping procedure

Create `docs/runbooks/alembic-stamp-prod.md` with the one-time stamping procedure:

```markdown
# One-Time Production Database Alembic Stamp

After this Story ships and BEFORE deploying any subsequent migration:

1. Confirm the baseline revision file matches current prod schema (visual diff against `SELECT * FROM INFORMATION_SCHEMA.TABLES` etc.)
2. Run from a workstation with prod Entra credentials and prod Key Vault access:
   ```
   alembic stamp <baseline-revision-id>
   ```
3. Verify: `alembic current` should print the baseline revision id
4. Capture the output and attach to OTA-540 as a comment

This is a destructive operation in the sense that it tells Alembic "this DB is at this revision." Do NOT run `alembic upgrade head` against a non-stamped prod database — that would re-execute the baseline as if creating tables, which would fail.
```

**STOP.**

---

### Phase 5 — Replace `init_db()` `metadata.create_all()` with Alembic runner

In `app/models/session.py`:
- Replace the `metadata.create_all()` call with a function that runs `alembic upgrade head` against the dev database
- Production code path should not call this — App Service deploys do not run migrations on startup. Migrations are run manually as part of the deploy procedure (document this in `architecture-plan.md` § 7)

**Show the change. STOP.**

---

### Phase 6 — CI gate: schema-change-without-migration fails the build

Add a step to `.github/workflows/build-on-push.yml` (or whichever workflow runs on push to `main`):

```yaml
- name: Verify Alembic migration accompanies any database.py change
  run: |
    DB_CHANGED=$(git diff --name-only HEAD~1 HEAD | grep -c "app/models/database.py" || true)
    MIGRATION_ADDED=$(git diff --name-only HEAD~1 HEAD | grep -c "^alembic/versions/" || true)
    if [ "$DB_CHANGED" -gt 0 ] && [ "$MIGRATION_ADDED" -eq 0 ]; then
      echo "ERROR: app/models/database.py changed but no Alembic revision added"
      echo "All schema changes must be expressed as Alembic migrations following expand/contract discipline."
      exit 1
    fi
```

**Show the workflow change. STOP.**

---

### Phase 7 — Documentation updates

Update `claude_context/architecture-plan.md` § 2:
- Confirm the Schema Migration Strategy section reflects what was actually implemented (any deviation from the section as drafted should be reconciled here, not left as a doc-vs-code mismatch)

Update `claude_context/CLAUDE.md` Development Environment section, add subsection "Alembic Migrations":

```markdown
### Alembic Migrations

All schema changes MUST follow expand/contract discipline (architecture-plan.md § 2).

Common commands:

# Generate a migration after editing app/models/database.py
alembic revision --autogenerate -m "description"

# Run migrations against dev DB
alembic upgrade head

# Inspect current revision
alembic current

# Roll back one revision
alembic downgrade -1

# Stamp the database at a specific revision (DESTRUCTIVE — only for stamping new envs)
alembic stamp <revision-id>

When deferring a contract migration, log it in OTA-523 (Database Contract Actions).
```

**Show both doc diffs. STOP.**

---

### Phase 8 — Commit, push, verify build, STOP

After Don approves Phase 7:

```bash
git add alembic/ alembic.ini app/models/session.py .github/workflows/ docs/runbooks/alembic-stamp-prod.md claude_context/
git commit -m "OTA-540 OTA-522 feat: initialize Alembic with baseline + expand/contract discipline

- Initialized Alembic for async SQLAlchemy + Azure SQL (Entra ID auth)
- Baseline migration matching current production schema (hand-verified, additive only)
- Production stamping procedure documented in docs/runbooks/alembic-stamp-prod.md
- Replaced init_db() metadata.create_all() with Alembic migration runner for dev
- CI gate fails build if database.py changes lack a corresponding Alembic revision
- claude_context/architecture-plan.md § 2 reconciled with implementation
- claude_context/CLAUDE.md updated with Alembic command reference

Closes OTA-540, supersedes OTA-522.
Integrates with OTA-523 for deferred contract tracking."

git push origin main
```

Then verify the GitHub Actions build run completed successfully on the pushed commit. Report back with:

```
Branch: main
Commit: <sha> "OTA-540 OTA-522 feat: initialize Alembic..."
Push: confirmed pushed to origin/main at <time>
Build: GitHub Actions run <run-id> — <status>
Build artifact: <artifact-name> (<size>)
Ready for user to deploy via deploy-to-dev.yml

Next step (user action): trigger deploy-to-dev.yml via GitHub Actions UI, then run the one-time prod stamp per docs/runbooks/alembic-stamp-prod.md before any future migration ships.
```

**STOP. Do NOT trigger any deploy workflow.**

---

## Acceptance criteria (verify before final commit)

- [ ] `alembic.ini` and `alembic/` directory exist in repo root
- [ ] Baseline migration file represents current prod schema accurately (hand-verified)
- [ ] Stamping procedure documented in `docs/runbooks/alembic-stamp-prod.md`
- [ ] `alembic upgrade head` works against a fresh dev database
- [ ] CI workflow fails on a synthetic test branch where `database.py` is edited without an Alembic revision (test once, then revert the test)
- [ ] `claude_context/architecture-plan.md` § 2 matches implementation
- [ ] `claude_context/CLAUDE.md` includes Alembic command reference

## Out of scope (do NOT do in this Story)

- Splitting `database.py` into per-domain modules (OTA-547 backlog)
- PK type standardization (OTA-547 backlog)
- Any specific schema migration beyond baseline (separate Stories)
- Triggering any deploy workflow (Don's job)
