---
allowedTools:
  - Bash
  - Write
  - Read
---

# JIRA-RESTRUCTURE-PROMPT.md

## Context

Restructure the OTA Jira project to align with the new JPD-based roadmap (OTA Roadmap project, key `OTAR`). Five operations:

1. **Create cross-project Polaris work item links** between OTAR Categories (Ideas) and OTA Epics
2. **Convert active OTA Subtasks to Stories** (preserve parent links)
3. **Rename OTA Epics** to drop legacy phase prefixes (2.0.x, 3.3.x, Sprint N, etc.)
4. **Append "Roadmap Category" link** to each Epic description
5. **Investigate duplicate Epics** (OTA-356 vs OTA-365, OTA-476 vs OTA-477) and report — no closures in this script

This is pure Jira admin via REST API. No application code is touched. Run from any directory; no venv required, but Python 3.10+ with `requests` is needed.

## Prerequisites

Before doing anything else:

1. `cat CLAUDE.md` — confirm the rest of project context is current
2. Verify Python and `requests` are available: `python --version` and `python -c "import requests; print(requests.__version__)"`
3. Verify `az` CLI is logged in: `az account show`

## Constants

```
JIRA_BASE = "https://tmtctech-team.atlassian.net/rest/api/3"
CLOUD_ID  = "53c395d7-bac7-4a5f-baf2-ee2b0f375a2b"
KV_VAULT  = "options-analyzer"
KV_TOKEN_SECRET = "jira-api-token"   # confirm exact secret name; adjust if different
```

## Phase 0 — Auth setup (do this first, then stop and confirm)

Build a Python script `jira_restructure.py` that:

1. Fetches the Jira API token from Key Vault:
   `az keyvault secret show --vault-name options-analyzer --name jira-api-token --query value -o tsv`
2. Asks the user for their Atlassian account email (one-time prompt; cache as env var `JIRA_EMAIL` for subsequent runs).
3. Sets up a `requests.Session()` with Basic Auth = `(email, token)` and `Accept: application/json`.
4. Verifies auth by hitting `GET /myself` — must return 200 with the user's accountId.

After Phase 0 succeeds, **STOP and report** the auth check result. Do not proceed to Phase 1 until confirmed.

## Phase 1 — Create cross-project Polaris work item links

Idempotent: for each (Idea, Epic) pair below, first `GET /issue/{epic_key}?fields=issuelinks` and check whether a "Polaris work item link" already exists pointing to that Idea key. Skip if it does. Create if it doesn't.

**Link payload:**
```json
{
  "type": {"name": "Polaris work item link"},
  "inwardIssue":  {"key": "<IDEA_KEY>"},
  "outwardIssue": {"key": "<EPIC_KEY>"}
}
```

POST to `/issueLink`.

**Target pairs (33 total — 5 already exist as noted, those will be skipped):**

| Idea | Epic | Status |
|---|---|---|
| OTAR-7 (Trade Evaluation Quality) | OTA-501 | already created |
| OTAR-7 | OTA-4 | already created |
| OTAR-7 | OTA-6 | already created |
| OTAR-7 | OTA-14 | already created |
| OTAR-7 | OTA-272 | already created |
| OTAR-7 | OTA-273 | needs creation |
| OTAR-7 | OTA-436 | needs creation |
| OTAR-8 (Trade-to-Strategy Journey) | OTA-329 | needs creation |
| OTAR-8 | OTA-376 | needs creation |
| OTAR-8 | OTA-393 | needs creation |
| OTAR-9 (Strategy-to-Trade Journey) | OTA-365 | needs creation |
| OTAR-10 (Position Management & Monitoring) | OTA-7 | needs creation |
| OTAR-11 (Trade Discovery & Scanning) | OTA-5 | needs creation |
| OTAR-11 | OTA-300 | needs creation |
| OTAR-11 | OTA-443 | needs creation |
| OTAR-14 (Live Trade Execution) | OTA-10 | needs creation |
| OTAR-16 (Insights & Agentic Platform) | OTA-11 | needs creation |
| OTAR-17 (Identity & Access) | OTA-455 | needs creation |
| OTAR-19 (Data Sources & Market Intelligence) | OTA-13 | needs creation |
| OTAR-19 | OTA-208 | needs creation |
| OTAR-19 | OTA-312 | needs creation |
| OTAR-21 (Backtesting & Strategy Validation) | OTA-12 | needs creation |
| OTAR-21 | OTA-14 | needs creation |
| OTAR-23 (UX Foundation & Design System) | OTA-8 | needs creation |
| OTAR-23 | OTA-329 | needs creation |
| OTAR-23 | OTA-356 | needs creation |
| OTAR-23 | OTA-365 | needs creation |
| OTAR-23 | OTA-376 | needs creation |
| OTAR-23 | OTA-393 | needs creation |
| OTAR-24 (Platform Operations & Observability) | OTA-9 | needs creation |
| OTAR-24 | OTA-236 | needs creation |
| OTAR-24 | OTA-476 | needs creation |
| OTAR-24 | OTA-477 | needs creation |
| OTAR-24 | OTA-498 | needs creation |

After Phase 1, **STOP and report** how many links were created vs skipped.

## Phase 2 — Convert active Subtasks to Stories

Find all OTA Subtasks not yet in a terminal status:

```
JQL: project = OTA AND issuetype = Subtask AND status NOT IN ("Code & Test Complete", "Production Deployed", "Done")
```

For each, capture `key`, `summary`, `parent.key`, `status.name`. Print the full list in a table. **STOP and ask the user to confirm before proceeding.** Do not auto-execute.

After confirmation, for each Subtask, PUT to `/issue/{key}` with:
```json
{"fields": {"issuetype": {"name": "Story"}}}
```

After conversion, GET the same issue and verify:
- `issuetype.name == "Story"`
- `parent.key` matches the original parent (Subtask → Story preserves the parent link in modern Jira; if it doesn't, restore it via a second PUT with `{"fields": {"parent": {"key": "<original>"}}}`)

Done Subtasks (in "Code & Test Complete", "Production Deployed", or "Done") are intentionally left alone — they are historical records.

After Phase 2, **STOP and report** counts.

## Phase 3 — Rename Epics (drop phase prefixes)

Idempotent: skip any Epic whose summary no longer matches the "Old" column (means it's already renamed).

PUT to `/issue/{key}` with `{"fields": {"summary": "<new>"}}`.

| Key | Old summary | New summary |
|---|---|---|
| OTA-4 | 2.0.x Pre-Flight Fixes + Scoring Pipeline | Pre-Flight Fixes & Scoring Pipeline |
| OTA-5 | 2.1.x Security Strategies Page | Security Strategies Page |
| OTA-6 | Structured Evaluation + Probability Matrix (Phase 2.11) | Structured Evaluation & Probability Matrix |
| OTA-7 | 2.2.x Positions & Portfolio | Positions & Portfolio |
| OTA-8 | 2.3.x Dashboard Overhaul | Dashboard Overhaul |
| OTA-9 | 2.4.x Infrastructure & Strategy Admin | Infrastructure & Strategy Admin |
| OTA-10 | 2.5.x Live Trading Preparation | Live Trading Preparation |
| OTA-11 | 3.x.x Agentic Platform | Agentic Platform |
| OTA-12 | 3.3.x Backtesting Engine | Backtesting Engine |
| OTA-13 | 4.x.x Intelligence Expansion | Intelligence Expansion |
| OTA-356 | Experience Framework v3 Sprint 2 — Strategy Pages + Positions Page v3 Redesign | Experience Framework v3 — Strategy Pages & Positions (initial scope) |
| OTA-365 | Experience Framework v3 Sprint 3 — Strategy Pages + Positions v3 Redesign | Experience Framework v3 — Strategy Pages & Positions Page |
| OTA-376 | Sprint 4 Experience Framework v3: Trade Wiring & Data Integration | Experience Framework v3 — Trade Wiring & Data Integration |
| OTA-393 | Sprint 5 Experience Framework v3: Integration, Polish & Cleanup | Experience Framework v3 — Integration, Polish & Cleanup |

OTA-14, OTA-208, OTA-236, OTA-272, OTA-273, OTA-300, OTA-312, OTA-329, OTA-436, OTA-455, OTA-476, OTA-477, OTA-498 already have no phase prefix — leave them alone.

After Phase 3, **report** counts and any mismatches.

## Phase 4 — Append "Roadmap Category" line to Epic descriptions

For each Epic in the mapping below, GET its current description. If the description does NOT already contain the string "Roadmap Category:", append at the end:

```

---

**Roadmap Category:** [OTAR-X — Category Name](https://tmtctech-team.atlassian.net/browse/OTAR-X)
```

If multiple Categories apply to one Epic, list both on separate lines. PUT the updated description back via `/issue/{key}` with `{"fields": {"description": "<new>"}}`.

**Note on description format:** Jira Cloud's REST API v3 expects descriptions in Atlassian Document Format (ADF) JSON, not raw markdown. Either (a) use the v2 API (`/rest/api/2/issue/{key}`) which accepts wiki markup, or (b) keep using v3 but wrap the new text in an ADF paragraph node. Pick whichever is simpler and document the choice in the script header.

**Mapping (Epic → primary Category, plus secondary if applicable):**

| Epic | Primary Category | Secondary |
|---|---|---|
| OTA-4 | OTAR-7 Trade Evaluation Quality | — |
| OTA-5 | OTAR-11 Trade Discovery & Scanning | — |
| OTA-6 | OTAR-7 Trade Evaluation Quality | — |
| OTA-7 | OTAR-10 Position Management & Monitoring | — |
| OTA-8 | OTAR-23 UX Foundation & Design System | — |
| OTA-9 | OTAR-24 Platform Operations & Observability | — |
| OTA-10 | OTAR-14 Live Trade Execution | — |
| OTA-11 | OTAR-16 Insights & Agentic Platform | — |
| OTA-12 | OTAR-21 Backtesting & Strategy Validation | — |
| OTA-13 | OTAR-19 Data Sources & Market Intelligence | — |
| OTA-14 | OTAR-7 Trade Evaluation Quality | OTAR-21 Backtesting |
| OTA-208 | OTAR-19 Data Sources | — |
| OTA-236 | OTAR-24 Platform Operations | — |
| OTA-272 | OTAR-7 Trade Evaluation Quality | — |
| OTA-273 | OTAR-7 Trade Evaluation Quality | — |
| OTA-300 | OTAR-11 Trade Discovery | — |
| OTA-312 | OTAR-19 Data Sources | — |
| OTA-329 | OTAR-23 UX Foundation | OTAR-8 Trade-to-Strategy |
| OTA-356 | OTAR-23 UX Foundation | — |
| OTA-365 | OTAR-23 UX Foundation | OTAR-9 Strategy-to-Trade |
| OTA-376 | OTAR-23 UX Foundation | OTAR-8 Trade-to-Strategy |
| OTA-393 | OTAR-23 UX Foundation | OTAR-8 Trade-to-Strategy |
| OTA-436 | OTAR-7 Trade Evaluation Quality | — |
| OTA-455 | OTAR-17 Identity & Access | — |
| OTA-476 | OTAR-24 Platform Operations | — |
| OTA-477 | OTAR-24 Platform Operations | — |
| OTA-498 | OTAR-24 Platform Operations | — |
| OTA-501 | OTAR-7 Trade Evaluation Quality | — |
| OTA-443 | OTAR-11 Trade Discovery | — |

After Phase 4, **report** counts and any 4xx errors.

## Phase 5 — Investigate duplicate Epics (READ-ONLY report)

Fetch full details of:
- OTA-356 and OTA-365
- OTA-476 and OTA-477

For each pair, output a side-by-side comparison:
- Summary
- Status
- Description (first 500 chars)
- Created date
- Child count (`GET /search?jql=parent={key}` and count results)
- Active children count (children not in "Code & Test Complete" / "Production Deployed" / "Done")

**Do not close, transition, or merge anything.** Just print the comparison so I can decide whether to close one of each pair as a duplicate.

## Exit criteria

Print a final summary table:
- Phase 1: X links created, Y skipped (already existed)
- Phase 2: X Subtasks converted, Y left as-is (Done states)
- Phase 3: X Epics renamed, Y skipped (already renamed)
- Phase 4: X descriptions updated, Y skipped (already had Roadmap Category)
- Phase 5: report printed, no changes made

If any phase had errors, list them with the issue key and the error message.

## House rules to enforce

- All API responses checked for `status_code != 200` — abort with the response body printed
- Never delete tickets
- Never transition tickets (the new workflow is set up but transitions are manual decisions)
- Print every PUT/POST before sending so the operation log is auditable
- Add `time.sleep(0.1)` between calls to be a good Atlassian citizen (rate limit is 100 req/min on Standard tier)