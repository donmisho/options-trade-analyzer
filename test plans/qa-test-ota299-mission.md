# Mission: Run Level 1 QA Validation Against OTA-299

You are the UX Compliance Agent. Load `agents/qa-ux/CLAUDE.md` for your behavioral rules and pre-authorized operations.

This is an **active build validation** run against a single completed ticket to test the QA agent system end-to-end.

## Setup

1. If `agents/qa-context/jira-extract.json` does not exist, run `python agents/shared/jira-extract.py` first to pull active tickets
2. Start the frontend dev server if not already running: `cd web && npm run dev`
3. Start the API server if not already running: `uvicorn app.main:app --reload`

## Target

Ticket: **OTA-299** — Wire TradeEvaluationView: Compose All Five Sections and Replace AskClaudePanel

## Execution Steps

### Step 1: Extract testable assertions
Read OTA-299 from the Jira extract (or fetch it directly if not in the extract since it may have status "Done"). Use the `agents/qa-ux/skills/jira-spec-parser/SKILL.md` approach to parse the ticket description and extract every testable assertion. Categorize each as VISUAL, BEHAVIORAL, DATA, or INTEGRATION.

Write the parsed assertions to `agents/qa-ux/test-results/OTA-299-assertions.json`.

### Step 2: Run compliance checks
For each extracted assertion, use the `agents/qa-ux/skills/ui-compliance-check/SKILL.md` approach to verify the assertion against the running application:

- VISUAL assertions: navigate to the TradeEvaluationView, inspect component rendering, check colors against design tokens
- BEHAVIORAL assertions: test interactions — does clicking/navigating produce the expected state changes
- DATA assertions: call the relevant API endpoints, verify response shapes match Pydantic schemas in the spec
- INTEGRATION assertions: verify routing through provider factory, verify SKILL.md usage, verify endpoint paths exist

### Step 3: Write results
Write the full compliance check results to `agents/qa-ux/test-results/OTA-299.json` using the output format defined in the ui-compliance-check SKILL.md.

### Step 4: Post to Teams
Use `agents/shared/teams-notifier.py` to:
- Post a summary to the "qa-ux" channel with pass/fail counts and pass rate
- Post individual findings for any FAIL results with ticket key, component, expected vs actual, severity, and suggested fix

### Step 5: Log the run
Use `agents/shared/agent-run-logger.py` to log this run with:
- agent_type: qa_ux
- run_type: compliance_check
- input_context: {"ticket_key": "OTA-299", "mode": "active_build_validation"}
- output_summary: the summary object from Step 3
- status: COMPLETE or FAILED based on results

## Important Notes

- This is the first real run of the QA system — if something in the agent tooling doesn't work (missing import, wrong path, etc.), fix it and note what you fixed
- If OTA-299 has status "Done" and isn't in the Jira extract (which only pulls status != Done), fetch it directly from the Jira API or read the ticket description from this context: OTA-299 wires the TradeEvaluationView by composing TradeIdentityHeader, ExitScenarioTable, OutcomeSummaryCard, ProbabilityMatrix, and ClaudesRead sections into a single view that replaces AskClaudePanel
- If the dev servers aren't running or the feature isn't deployed locally, report what you can check (file existence, code structure, API schema) and mark UI assertions as SKIP with reason "dev server not available"
- Follow all hard rules in your CLAUDE.md — especially: never modify application source code, log everything, post to Teams
