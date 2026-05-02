# Mission: Add Teams Approval Notifications to QA Agent System

The QA agent system currently asks for approvals only in the Claude Code terminal. Add Teams notifications for all approval requests so the human can see what needs attention from their phone or any device — just like working with real testers.

## Overview

Two changes:
1. Add a `post_approval_request` function to `agents/shared/teams-notifier.py`
2. Update `prompts/CLAUDE.md` and all four agent CLAUDE.md files to post approval requests to Teams before waiting

The pattern is **notify-and-wait**: the agent posts the approval request to Teams with full context, then waits for the human to respond in Claude Code. Teams is the notification channel — Claude Code is the response channel.

## Change 1: Update agents/shared/teams-notifier.py

Add a new `post_approval_request` function. This is the fourth public function alongside `post_finding`, `post_summary`, and `post_escalation`.

```python
def post_approval_request(
    channel: str,
    request_type: str,
    summary: str,
    details: str,
    options: list = None,
    qa_level: int = None,
    files_changed: list = None,
):
    """
    Post an approval request to Teams so the human sees it on any device.
    The human responds in Claude Code — Teams is notification only.

    Args:
        channel: qa-ux or qa-data (pick based on what the build touched)
        request_type: BUILD_COMPLETE | QA_RECOMMENDATION | PR_READY | 
                      FIX_APPROVAL | PUSH_APPROVAL | ESCALATION
        summary: One-line summary of what needs approval
        details: Full context — what was built, what changed, what's recommended
        options: Response options (default: ["Approve", "Adjust", "Skip"])
        qa_level: If this is a QA recommendation, the recommended level (0/1/2)
        files_changed: List of files modified in this build
    """
```

The Adaptive Card should include:

- Header with request_type and a color indicator (blue for BUILD_COMPLETE, amber for QA_RECOMMENDATION, green for PR_READY, red for ESCALATION)
- Summary line (bold)
- Details section (wrap: true)
- If qa_level is provided: show the level with its description (Level 0 = No QA, Level 1 = Targeted, Level 2 = Full regression)
- If files_changed is provided: show the list of files
- Footer: "Respond in Claude Code" with timestamp
- Response options shown as text (not action buttons — the response happens in Claude Code)

Example card content for a build complete:

```
🔨 Build Complete — Approval Needed

Summary: Completed OTA-304, OTA-305, OTA-306 across 3 parallel streams

Files changed:
- web/src/components/SymbolSearch.jsx
- web/src/components/SymbolSearch.css
- app/services/symbol_service.py
- app/routes/symbols.py

Recommended QA level: 2 (Full regression)
Reason: Changes span frontend and backend across 3 tickets

Respond in Claude Code with: Approve / Adjust / Skip

Posted at 2026-03-28 18:30 UTC
```

Example card for a PR ready:

```
✅ PR Ready — Review Needed

Summary: fix(OTA-274): Apply abs() to put leg deltas in net delta calculation

Branch: fix-data/ota-274-delta-abs
Files: app/services/vertical_engine.py (lines 145-152)
Tests: Full 64-config matrix PASS (96.9%), MSFT anchors PASS

Respond in Claude Code with: Merge / Review first / Reject

Posted at 2026-03-28 18:45 UTC
```

## Change 2: Update prompts/CLAUDE.md — Post-Build QA Gate section

Find the "Post-Build QA Gate" section. After the line that says `Run QA? [waiting for your answer]`, add:

```markdown
After stating your recommendation, also post it to Teams using `post_approval_request` from `agents/shared/teams-notifier.py` so the human can see it on any device. Use channel "qa-ux" for frontend-heavy builds, "qa-data" for backend-heavy builds, or "qa-ux" as default. Then wait for the human's response in this Claude Code session.

For any approval that requires human input (git push, PR creation, fix approval, QA level selection), always post to Teams first, then wait in Claude Code.
```

## Change 3: Update all four agent CLAUDE.md files

In each of the four agent CLAUDE.md files (`agents/qa-ux/CLAUDE.md`, `agents/qa-data/CLAUDE.md`, `agents/fe-dev/CLAUDE.md`, `agents/be-dev/CLAUDE.md`), find the "Requires human approval" section and add this line at the end:

```markdown
For all items requiring human approval: post the approval request to Teams using `post_approval_request` from `agents/shared/teams-notifier.py` before waiting. Include full context so the human can make a decision from any device. Use channel "qa-ux" for this agent (or "qa-data" for the data quality and backend dev agents). Then wait for the response in this Claude Code session.
```

Make sure qa-ux/CLAUDE.md and fe-dev/CLAUDE.md use channel `"qa-ux"`, and qa-data/CLAUDE.md and be-dev/CLAUDE.md use channel `"qa-data"`.

## Validation

After all changes:
1. Run `python -c "from agents.shared.teams_notifier import post_approval_request; post_approval_request('qa-ux', 'BUILD_COMPLETE', 'Test approval request', 'This is a test of the approval notification system.', qa_level=0, files_changed=['test.py'])"` — verify the card appears in Teams
2. Verify `prompts/CLAUDE.md` references `post_approval_request` in the QA gate section
3. Verify all four agent CLAUDE.md files reference `post_approval_request` in their approval sections
4. Commit to the `feature/qa-agent-system` branch

## Hard Rules

- Teams is notification only — the human always responds in Claude Code
- Every approval request must include enough context to make a decision without switching to Claude Code
- Never block on a Teams response — always wait in Claude Code
- The `post_approval_request` function must follow the same SecretsManager fallback pattern as the other functions in teams-notifier.py
