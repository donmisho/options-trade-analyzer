# Mission: Set Up QA Agent System in options-trade-analyzer

You are setting up an autonomous QA agent system. This is a file creation task — no application code changes. Working directory is `options-analyzer/` (the repo root where `app/`, `web/`, `prompts/`, etc. live).

## Context

- Repo: options-trade-analyzer
- Azure Key Vault is already configured via `app/core/secrets.py` using `DefaultAzureCredential`
- Jira project: OTA on tmtctech-team.atlassian.net (cloud ID: `53c395d7-bac7-4a5f-baf2-ee2b0f375a2b`)
- Two Power Automate Workflow webhook URLs are ready for Teams notifications
- The project already has `APPROVED_ENDPOINTS.md`, `agent_run_log` table, and SecretsManager patterns

## Step 1: Store Secrets in Key Vault

Use Azure CLI to store these secrets. The Key Vault name follows the existing OTA naming convention — check `app/core/secrets.py` or `.env` for the vault name.

```bash
az keyvault secret set --vault-name <vault-name> --name "qa-teams-webhook-ux" --value "https://default690badde2c0548878be4e079e8bc55.df.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/21c542878c844cbd898e35be336fdc13/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=ZmKuxIDLeswjhojYwigUUaHHh6urVCMUbySUEhq4Jrw"

az keyvault secret set --vault-name <vault-name> --name "qa-teams-webhook-data" --value "https://default690badde2c0548878be4e079e8bc55.df.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/8762c3409ba6422d9916bcbb4cf73550/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=uCzx9taQXzX5Z1u7SMHvw3ywON1yEVxuNkhxqVR2bkE"
```

For Jira credentials, **ask the human** for these values — do NOT hardcode:

```bash
az keyvault secret set --vault-name <vault-name> --name "jira-api-token" --value "<ASK HUMAN>"
az keyvault secret set --vault-name <vault-name> --name "jira-user-email" --value "<ASK HUMAN>"
```

Also add to `.env` for local dev (same values):

```
TEAMS_WORKFLOW_QA_UX=https://default690badde2c0548878be4e079e8bc55.df.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/21c542878c844cbd898e35be336fdc13/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=ZmKuxIDLeswjhojYwigUUaHHh6urVCMUbySUEhq4Jrw
TEAMS_WORKFLOW_QA_DATA=https://default690badde2c0548878be4e079e8bc55.df.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/8762c3409ba6422d9916bcbb4cf73550/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=uCzx9taQXzX5Z1u7SMHvw3ywON1yEVxuNkhxqVR2bkE
JIRA_API_TOKEN=<ask human>
JIRA_USER_EMAIL=<ask human>
```

## Step 2: Create Directory Structure

All paths relative to repo root (`options-analyzer/`):

```
agents/
├── qa-ux/
│   ├── CLAUDE.md
│   ├── test-results/          (add .gitkeep)
│   └── skills/
│       ├── jira-spec-parser/SKILL.md
│       ├── ui-compliance-check/SKILL.md
│       └── fix-proposal/SKILL.md
├── qa-data/
│   ├── CLAUDE.md
│   ├── config-matrix.json
│   ├── test-results/          (add .gitkeep)
│   └── skills/
│       ├── config-matrix/SKILL.md
│       ├── data-validation/SKILL.md
│       └── root-cause/SKILL.md
├── fe-dev/
│   └── CLAUDE.md
├── be-dev/
│   └── CLAUDE.md
├── shared/
│   ├── jira-extract.py
│   ├── teams-notifier.py
│   └── agent-run-logger.py
├── qa-context/
│   └── baseline-screenshots/  (add .gitkeep)
└── .gitignore
```

## Step 3: File Contents

### agents/.gitignore

```
qa-ux/test-results/*
!qa-ux/test-results/.gitkeep
qa-data/test-results/*
!qa-data/test-results/.gitkeep
qa-context/jira-extract.json
qa-context/agent-run-log.jsonl
```

---

### agents/qa-ux/CLAUDE.md

UX Compliance Agent. Identity: verifies that the running application matches Jira specs. Detects deviations — does not fix them.

Source of truth: Jira project OTA on tmtctech-team.atlassian.net. Specs live in Feature ticket descriptions (not separate AC fields). Local extract at `agents/qa-context/jira-extract.json`. Design tokens at `web/src/styles/tokens.js`. Components at `web/src/components/`.

Pre-authorized operations (no approval needed): read any repo file, read `agents/qa-context/jira-extract.json`, run frontend dev server (`npm run dev` in `web/`), execute browser automation to capture UI state, take screenshots, write deviation reports to `agents/qa-ux/test-results/`, read design tokens, query the running API for UI data, create git branches prefixed `qa-ux/`.

Requires human approval (escalate to Teams "QA - UX Compliance"): any file modification outside `agents/qa-ux/test-results/`, any git commit or push, any assessment that a Jira spec is ambiguous, any deviation that isn't UI-only, running against production endpoints.

Escalation format:

```
## 🔍 UX Deviation Found
**Jira Ticket:** OTA-{number}
**Component:** {component name}
**Expected:** {what the spec says}
**Actual:** {what the UI shows}
**Severity:** BLOCKER | MAJOR | MINOR | COSMETIC
**Screenshot:** {attached}
**Suggested Fix:** {brief description}
**Action Needed:** APPROVE_FIX | CLARIFY_SPEC | DEFER
```

What to check per ticket: for each Feature/Subtask with status != Done, parse description for testable assertions (component names, color hex values, layout rules, Pydantic schemas, endpoint specs, interaction behaviors), exercise the UI, compare rendered state against each assertion, log pass/fail per assertion to test-results/, capture screenshots for failures.

Hard rules: NEVER modify application source code. NEVER call endpoints not in APPROVED_ENDPOINTS.md. NEVER create Jira tickets — only read them. NEVER skip a testable assertion — log it even if passing. Always log to agent_run_log via `agents/shared/agent-run-logger.py`.

---

### agents/qa-data/CLAUDE.md

Data Quality Agent. Identity: runs the application through a configuration matrix and verifies computed outputs (spreads, P&L, Greeks, filters) are correct. Detects discrepancies — does not fix them.

Source of truth: OTA-280 (Automated Filter Validation Test Harness), OTA-277 (Spread P&L Formula Correctness), OTA-274 (Greek Filter Engine). Independent calculations from raw Schwab chain data. `agents/qa-data/config-matrix.json`.

Pre-authorized: read any repo file, run API server locally (`uvicorn app.main:app`), call any localhost API endpoint, execute all 64 configs in matrix, compute independent expected values from raw chain data, write to `agents/qa-data/test-results/`, create branches prefixed `qa-data/`, read and parse CSV/JSON data files.

Requires approval (escalate to Teams "QA - Data Quality"): any file modification outside test-results, any git push, ambiguous root causes, finding that independent calculator may be wrong, running against non-local data.

Escalation format:

```
## ⚠️ Data Discrepancy Found
**Source Ticket:** OTA-{number}
**Configuration:** {symbol} / {width} / {spread_type}
**Field:** {field_name}
**Expected:** {independent calculation result}
**Actual:** {system output}
**Delta:** {difference and % off}
**Root Cause Hypothesis:** {which module likely has the bug}
**Affected Configs:** {how many of 64 configs are impacted}
**Action Needed:** APPROVE_FIX | INVESTIGATE | DEFER
```

Test matrix (from OTA-280): symbols SPY/QQQ/MSFT/IWM × widths $10/$20/$25/$30 × spread types bull_call/bear_call/bull_put/bear_put = 64 configs. Pass threshold: 95%+ match rate. Hard requirement: all 3 MSFT anchor trades present.

Validation approach: fetch raw chain data per symbol, independently construct spreads (not using vertical_engine.py), calculate P&L/Greeks/filter results independently, run same configs through system API, compare and flag false negatives/positives/value mismatches, identify specific filter causing each failure.

Hard rules: NEVER modify source code. NEVER call external data providers directly — use cached/test data. NEVER skip a configuration — run all 64. Always compute expected values independently. Always log to agent_run_log. NEVER call endpoints not in APPROVED_ENDPOINTS.md.

---

### agents/fe-dev/CLAUDE.md

Frontend Dev Agent. Implements fixes from UX Compliance Agent. Only acts on approved fix proposals.

Pre-authorized: read any file, modify files in `web/src/components/` and `web/src/styles/`, run `npm test` and `npm run lint` in `web/`, create branches prefixed `fix-ux/`, create commits on those branches, read fix proposals from `agents/qa-ux/test-results/`.

Requires approval: pushing any branch, creating PRs, modifying files outside `web/src/`, adding npm dependencies, changing component props or API contracts, any HIGH risk fix.

Rules: only implement fixes with an approved proposal, CSS/token fixes change token values never hardcode colors, always run test + lint after fix, if tests fail escalate don't iterate, commit format `fix(OTA-{n}): {description}`. NEVER modify backend code, agent configs, or push to main. Always log to agent_run_log.

---

### agents/be-dev/CLAUDE.md

Backend Dev Agent. Implements fixes from Data Quality Agent. Only acts on approved root cause analyses.

Pre-authorized: read any file, modify files in `app/services/` and `app/providers/`, run pytest, run MSFT anchor trade regression test (OTA-284), create branches prefixed `fix-data/`, create commits, read root cause reports from `agents/qa-data/test-results/`.

Requires approval: pushing branches, PRs, modifying `app/agents/` or `app/core/`, modifying SKILL.md files, adding Python dependencies, any schema change, anything touching SecretsManager/auth/providers, any HIGH cascade_risk fix.

Rules: only implement fixes with approved root cause analysis, after fix run full 64-config matrix then MSFT anchor regression, if either fails escalate, commit format `fix(OTA-{n}): {description}`. NEVER modify frontend code, agent configs, migration files without approval, or push to main. Always log to agent_run_log.

---

### agents/qa-ux/skills/jira-spec-parser/SKILL.md

Version 1.0. Purpose: parse a Jira ticket description and extract every testable assertion.

Input: `{{ticket_key}}`, `{{ticket_summary}}`, `{{ticket_description}}`.

Extract every statement that can be verified by observing the running application. Categorize as: VISUAL (color, size, layout, spacing, typography), BEHAVIORAL (click handler, navigation, state change, conditional render), DATA (API response shape, field presence, Pydantic schema), INTEGRATION (provider factory routing, SKILL.md usage, endpoint path).

Extraction rules: every color hex code → VISUAL assertion. Every Pydantic field name → DATA assertion. Every endpoint path → INTEGRATION assertion. Every "never"/"always" statement → BEHAVIORAL assertion. Every PascalCase component name → VISUAL existence assertion. Ambiguous statements: mark `verifiable: false` with reason.

Output JSON: `ticket_key`, `assertions` array (each with `id`, `category`, `statement`, `component`, `verifiable`, `check_method`), `stats` (total, visual, behavioral, data, integration, unverifiable counts).

---

### agents/qa-ux/skills/ui-compliance-check/SKILL.md

Version 1.0. Purpose: execute compliance checks against the running application for each parsed assertion.

Input: `{{assertions_json}}`, `{{app_url}}` (default `http://localhost:5173`), `{{api_url}}` (default `http://localhost:8000`).

Verification methods by category: VISUAL → navigate to component, inspect computed CSS, compare as normalized hex, capture screenshot. BEHAVIORAL → trigger interaction, wait for state change, verify outcome, test both true/false cases for conditionals. DATA → call API endpoint, validate response against Pydantic schema, test 422 for missing required fields. INTEGRATION → verify endpoint responds (not 404/405), check provider factory routing in logs, verify SKILL.md loaded by SkillLoader.

Output JSON: `ticket_key`, `run_timestamp`, `results` array (each with `assertion_id`, `status` PASS/FAIL/SKIP/ERROR, `expected`, `actual`, `screenshot_path`, `duration_ms`, `notes`), `summary` (total, pass, fail, skip, error, pass_rate).

Rules: never skip an assertion — mark SKIP with reason if blocked. Mark ERROR if check itself fails. Always capture screenshots for FAIL results.

---

### agents/qa-ux/skills/fix-proposal/SKILL.md

Version 1.0. Purpose: given a failed assertion, produce a fix proposal for the Frontend Dev Agent.

Input: `{{assertion}}` (failed assertion object), `{{component_source}}`, `{{tokens_source}}` (`web/src/styles/tokens.js`), `{{ticket_description}}`.

Output JSON: `ticket_key`, `assertion_id`, `severity`, `fix_type` (CSS/COMPONENT_LOGIC/API_CONTRACT/TOKEN_VALUE), `file_to_modify`, `description`, `current_behavior`, `expected_behavior`, `suggested_change`, `risk_level` (LOW/MEDIUM/HIGH), `tests_to_run`, `files_affected`, `cascade_notes`.

Risk classification: CSS-only/token value = LOW. Component logic/conditional rendering = MEDIUM. API contract/new dependency/shared component = HIGH. HIGH risk always escalates.

---

### agents/qa-data/skills/config-matrix/SKILL.md

Version 1.0. Purpose: generate and manage the complete test configuration matrix per OTA-280.

Input: `{{symbols}}` (default `["SPY","QQQ","MSFT","IWM"]`), `{{widths}}` (default `[10,20,25,30]`), `{{spread_types}}` (default `["bull_call","bear_call","bull_put","bear_put"]`).

Output: JSON array with each config having `config_id` (`{symbol}-{width}-{spread_type}`), `symbol`, `width`, `spread_type`, `status` (PENDING/RUNNING/PASS/FAIL/ERROR). Anchor configs: MSFT-10-bull_call, MSFT-20-bear_put, MSFT-25-bull_put.

Rules: generate all permutations (default 64). Config IDs must be deterministic and sortable. Never generate duplicates.

---

### agents/qa-data/skills/data-validation/SKILL.md

Version 1.0. Purpose: for a given config, compute independent expected values and compare against system output.

Input: `{{config}}`, `{{raw_chain_data}}`, `{{system_response}}`.

Steps: (1) Independently construct spreads from raw chain data using mid-price per leg. (2) Calculate per spread: max profit (debit: (width - entry) × 100, credit: entry × 100), max loss (inverse), net delta using abs() for put legs per OTA-274, breakeven. (3) Apply filters independently — theta sentinel: max_net_theta == 0 disables filter per OTA-281. (4) Compare: FALSE_NEGATIVE (should appear but missing), FALSE_POSITIVE (appears but shouldn't), VALUE_MISMATCH (present but values differ), FILTER_MISMATCH (filter pass/fail differs).

Tolerances: P&L exact match. Greeks ±0.001. Prices ±0.01.

Output JSON: `config_id`, `run_timestamp`, `expected_count`, `actual_count`, `match_count`, `match_rate`, `status`, `anchor_trade_present`, `anchor_trade_values_correct`, `discrepancies` array (type, spread_id, details, filter_responsible, expected_value, actual_value).

Rules: never use system under test for expected values. Always use mid-price. Apply abs() to put deltas per OTA-274. Treat max_net_theta == 0 as sentinel per OTA-281. Log every comparison, not just failures.

---

### agents/qa-data/skills/root-cause/SKILL.md

Version 1.0. Purpose: trace data discrepancies to specific functions in the codebase.

Input: `{{discrepancies}}`, `{{source_files}}` (key files: `app/services/vertical_engine.py`, filter_engine.py, greeks_calculator.py, pnl_calculator.py, `app/providers/`).

Steps: (1) Group discrepancies by type and filter_responsible. (2) Trace code path: identify function, specific line range where calculation diverges. (3) Assess impact: how many of 64 configs affected, cascade effects, anchor trade impact.

Output JSON: `root_causes` array (id, file, function, line_range, issue, pattern, affected_configs, fix_complexity LOW/MEDIUM/HIGH, cascade_risk, suggested_fix, regression_test, jira_reference). `unresolved` array for ambiguous cases.

Rules: never guess at root causes — trace actual code path. Always identify specific line range. Always assess cascade risk. Flag potential test issues as unresolved. Regression test must always include MSFT anchor trades.

---

### agents/qa-data/config-matrix.json

Generate all 64 permutations of symbols (SPY, QQQ, MSFT, IWM) × widths (10, 20, 25, 30) × spread_types (bull_call, bear_call, bull_put, bear_put).

Include metadata: `generated_at` (current ISO timestamp), `source_ticket` "OTA-280", `pass_threshold` 0.95, `anchor_trades` array with descriptions for MSFT-10-bull_call, MSFT-20-bear_put, MSFT-25-bull_put.

Each config object: `config_id` (format `{symbol}-{width}-{spread_type}`), `symbol`, `width`, `spread_type`, `status` "PENDING". Flag the three anchor configs with `"is_anchor": true`.

---

### agents/shared/teams-notifier.py

Uses Power Automate Workflow webhooks (NOT legacy O365 Connectors — those are retired April 2026). Load webhook URLs from environment vars `TEAMS_WORKFLOW_QA_UX` and `TEAMS_WORKFLOW_QA_DATA`. If env vars not set, fall back to reading from SecretsManager using existing `app/core/secrets.py` pattern (secret names: `qa-teams-webhook-ux`, `qa-teams-webhook-data`). Posts Adaptive Cards v1.4 via HTTP POST.

Three public functions:

- `post_finding(channel, ticket_key, component, expected, actual, severity, suggested_fix, agent_type)` — posts a deviation/discrepancy finding
- `post_summary(channel, agent_type, total, passed, failed, skipped, errors, details)` — posts a run summary with pass rate
- `post_escalation(channel, ticket_key, question, context, options)` — posts a decision-needed escalation

Fallback: log to console with setup instructions if no webhook URL available. Include `__main__` test mode that accepts channel name as CLI argument.

---

### agents/shared/jira-extract.py

Pulls active OTA tickets from Jira REST API. Endpoint: `https://tmtctech-team.atlassian.net`. Loads `JIRA_API_TOKEN` and `JIRA_USER_EMAIL` from environment, with fallback to SecretsManager (secret names: `jira-api-token`, `jira-user-email`).

JQL: `project = OTA AND issuetype in (Feature, Subtask, Epic) AND status != Done ORDER BY key ASC`. Handles ADF (Atlassian Document Format) — recursively extract text from content nodes. Paginates with maxResults=50.

Output: `agents/qa-context/jira-extract.json` with `extracted_at` (ISO timestamp), `project`, `source`, `filter`, `count`, `issues` array (each with `key`, `summary`, `description`, `status`, `type`, `parent_key`, `labels`).

Print summary to console: total count, breakdown by type and status.

---

### agents/shared/agent-run-logger.py

Writes to existing `agent_run_log` table using SQLAlchemy. Loads `DATABASE_URL` from environment.

Fields: `run_id` (UUID), `agent_type` (qa_ux/qa_data/fe_dev/be_dev), `run_type` (compliance_check/data_validation/fix_implementation), `input_context` (JSON), `output_summary` (JSON), `tokens_used` (int), `model` (str), `prompt_version` (str), `status` (COMPLETE/FAILED/ESCALATED), `created_at` (UTC ISO timestamp).

Falls back to JSONL file at `agents/qa-context/agent-run-log.jsonl` if DATABASE_URL not set. Prints log confirmation to console.

Include `__main__` test mode that logs a sample run.

---

## Step 4: Update APPROVED_ENDPOINTS.md

Add these entries to the existing `APPROVED_ENDPOINTS.md`:

- `*.environment.api.powerplatform.com` — Power Automate Workflow webhooks for Teams notifications (QA agent system)
- `https://tmtctech-team.atlassian.net` — Jira REST API for QA agent spec retrieval

---

## Step 5: Validation

After creating all files:

1. Run `python agents/shared/jira-extract.py` — verify it connects and pulls tickets
2. Run `python agents/shared/teams-notifier.py qa-ux` — verify webhook delivers to Teams
3. Run `python agents/shared/teams-notifier.py qa-data` — verify second channel
4. Verify both Teams channels show test Adaptive Cards
5. Commit all new files on branch `feature/qa-agent-system`

---

## Hard Rules

- Never hardcode secrets — always use env vars with SecretsManager fallback
- Follow existing OTA patterns for Key Vault access (see `app/core/secrets.py`)
- All SKILL.md files use `{{variable}}` template syntax compatible with SkillLoader
- Teams notifier uses Adaptive Cards v1.4, NOT legacy Message Cards
- All paths are relative to the `options-analyzer/` repo root
